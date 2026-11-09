"""V2 Cookie supply gate — the hard prerequisite for every online buyer call.

Design contract (spec 4.4, plan Task 0):

* Cookie supply is a PROACTIVELY WARMED POOL, not a per-request challenge
  solver. The gate owns minting, leasing, dead-marking and replenishing; the
  benchmark adapters only LEASE sessions, never mint themselves.
* Allowed: headless bare-Chromium warmup with a single batched CDP
  ``Network.setUserAgentOverride`` (userAgent + acceptLanguage + platform +
  userAgentMetadata), in-pool rotation on marked-invalid tickets, re-minting
  after expiry.
* FORBIDDEN: any proxy / egress-IP rotation (user vetoed three times),
  forging cross-account identity, infinite retry on a dead ticket. A 401/403/
  429/challenge kills THAT ticket and the caller leases the next one; only
  after three consecutive tickets are rejected does the source stop. 3xx is
  a normal search-page redirect and is NOT a rejection.
* Leakage: logs/reports carry only ``cookie_id`` and cookie LENGTH. The raw
  ``cookie_header`` value is never serialised.

Offline the pool logic is fully unit-tested with an injected mint function.
The real CDP mint is only exercised via ``--mint-once`` and the documented
online smoke; it opens a real browser and touches the network.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional

from collector.benchmark import fingerprint

# --- tuned constants (from measured baseline; re-tune after the 12h run) ----
DEFAULT_MAX_USES = 30          # ~30 requests before a cookie starts 403-ing
DEFAULT_WATERMARK = 1          # one serial warmup channel is enough at 4.6 pg/s
ABT_MIN_LEN = 580              # abt_data length that signals a finished challenge
ABT_STABLE_POLLS = 2           # two consecutive identical abt_data reads
MINT_TIMEOUT_S = 25.0          # challenge-pass budget per mint
CDP_PORT_BASE = 9400           # ephemeral base; we bind 0 by scanning /json/list
TARGET_URL = "https://www.ozon.ru/"

# Case variants of proxy env vars that must NEVER reach the browser.
_PROXY_ENV_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
    "ALL_PROXY", "all_proxy", "https_proxy", "HTTPS_PROXY",
)


class PoolEmpty(RuntimeError):
    """No live session to lease. Caller must replenish() first; lease() must
    never silently open a browser."""


class MintFailed(RuntimeError):
    """Warmup could not pass the challenge within budget."""


@dataclass
class Session:
    id: str
    cookie_header: str
    ua: str
    impersonate: str
    profile_id: str
    minted_at: float
    use_count: int = 0
    state: str = "fresh"  # fresh | leased | dead

    @property
    def is_live(self) -> bool:
        return self.state != "dead"


# ---------------------------------------------------------------------------
# Pure, testable helpers
# ---------------------------------------------------------------------------
def strip_proxy_env(env: Optional[dict] = None) -> dict:
    """Return a copy of ``env`` with every proxy variable removed."""
    src = os.environ if env is None else env
    out = {k: v for k, v in src.items() if k.lower() not in
           {"http_proxy", "https_proxy", "all_proxy"}}
    return out


def build_launch_args(
    chromium_bin: str,
    port: int,
    user_data_dir: str,
    headless: bool = True,
) -> List[str]:
    """Bare-Chromium launch args. NO --proxy-server; --no-proxy-server is forced
    so a leftover ambient proxy can never be inherited by the browser."""
    args = [
        chromium_bin,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-proxy-server",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--window-size=1280,800",
        "about:blank",
    ]
    if headless:
        args.insert(1, "--headless=new")
    return args


def session_redacted(s: Session) -> dict:
    """Serialise a session for logs/events WITHOUT the cookie value.

    Allowed: id, length, profile, impersonate, minted_at, use_count, state.
    Forbidden: cookie_header (and any substring of it)."""
    return {
        "id": s.id,
        "profile_id": s.profile_id,
        "impersonate": s.impersonate,
        "ua": s.ua,
        "cookie_len": len(s.cookie_header),
        "minted_at": s.minted_at,
        "use_count": s.use_count,
        "state": s.state,
    }


# ---------------------------------------------------------------------------
# Pool
# ---------------------------------------------------------------------------
class CookieSupply:
    """Pool of live buyer sessions. Thread-safe; single process for now."""

    def __init__(
        self,
        mint_fn: Optional[Callable[..., Session]] = None,
        clock: Callable[[], float] = time.time,
        max_uses: int = DEFAULT_MAX_USES,
        watermark: int = DEFAULT_WATERMARK,
    ) -> None:
        self._sessions: Dict[str, Session] = {}
        self._mint_fn = mint_fn or self._real_mint
        self._clock = clock
        self.max_uses = max_uses
        self.watermark = watermark
        self._lock = threading.Lock()

    # -- mint (operator / background driven; never implicit on lease) -------
    def mint(self, profile_hint: Optional[str] = None) -> Session:
        s = self._mint_fn(profile_hint=profile_hint)
        if not isinstance(s, Session):
            raise MintFailed("mint_fn did not return a Session")
        with self._lock:
            self._sessions[s.id] = s
        return s

    # -- lease (least-used, never mints) -----------------------------------
    def lease(self) -> Session:
        with self._lock:
            live = [s for s in self._sessions.values() if s.is_live]
            if not live:
                raise PoolEmpty("no live session; replenish() before leasing")
            # least-used; tie-break by id for determinism
            chosen = sorted(live, key=lambda s: (s.use_count, s.id))[0]
            chosen.use_count += 1
            chosen.state = "leased"
            return chosen

    # -- dead-marking: drop from rotation, KEEP use_count as evidence ------
    def mark_dead(self, session_id: str) -> None:
        with self._lock:
            s = self._sessions.get(session_id)
            if s is not None:
                s.state = "dead"  # use_count intentionally NOT reset

    # -- replenish to watermark (explicit, blocking browser work) ----------
    def replenish(self, watermark: Optional[int] = None) -> int:
        target = self.watermark if watermark is None else watermark
        if target < 1:
            raise ValueError("watermark must be >= 1")
        while self.available_count() < target:
            self.mint()
        return self.available_count()

    def available_count(self) -> int:
        with self._lock:
            return sum(1 for s in self._sessions.values() if s.is_live)

    def snapshot(self) -> List[dict]:
        with self._lock:
            return [session_redacted(s) for s in self._sessions.values()]

    # ------------------------------------------------------------------
    # Real CDP mint (only used when mint_fn is the default)
    # ------------------------------------------------------------------
    def _real_mint(self, profile_hint: Optional[str] = None) -> Session:
        import websocket  # local import: tests never need it

        profile = fingerprint.pick(os_filter=profile_hint)
        problems = fingerprint.audit(profile)
        if problems:
            raise MintFailed(f"fingerprint not self-consistent: {problems}")

        chromium_bin = "/usr/local/bin/chromium"
        if not os.path.isfile(chromium_bin):
            raise MintFailed(f"chromium not found at {chromium_bin}")

        udd = tempfile.mkdtemp(prefix="ozon-v2-")
        port = _free_port()
        proc = None
        ws = None
        t0 = time.time()
        try:
            env = strip_proxy_env(dict(os.environ))
            proc = subprocess.Popen(
                build_launch_args(chromium_bin, port, udd, headless=True),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
            )

            ws_url = _wait_for_devtools(port)
            if not ws_url:
                raise MintFailed("CDP devtools endpoint never came up")
            ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
            cid = [0]

            def call(method, params=None, tmo=30):
                cid[0] += 1
                my = cid[0]
                ws.send(json.dumps({"id": my, "method": method, "params": params or {}}))
                deadline = time.time() + tmo
                while time.time() < deadline:
                    res = json.loads(ws.recv())
                    if res.get("id") == my:
                        return res
                raise MintFailed(f"CDP {method} timed out")

            def evaluate(js):
                r = call("Runtime.evaluate",
                         {"expression": js, "awaitPromise": True, "returnByValue": True})
                return r.get("result", {}).get("result", {}).get("value")

            call("Page.enable")
            call("Runtime.enable")
            call("Network.enable")
            # four-field batch override (the whole point of headless)
            call("Network.setUserAgentOverride", fingerprint.cdp_override(profile))
            call("Emulation.setDeviceMetricsOverride", fingerprint.emulation_metrics(profile))
            call("Page.navigate", {"url": TARGET_URL})

            abt_prev = None
            stable = 0
            while time.time() - t0 < MINT_TIMEOUT_S:
                time.sleep(0.6)
                cookies = call("Network.getAllCookies", tmo=10).get("result", {}).get("cookies", [])
                abt = next((c.get("value", "") for c in cookies if c.get("name") == "abt_data"), "")
                here = evaluate("location.href") or ""
                if len(abt) >= ABT_MIN_LEN:
                    if abt == abt_prev:
                        stable += 1
                    else:
                        stable = 0
                    abt_prev = abt
                    if stable >= ABT_STABLE_POLLS and "abt_att=1" in here:
                        break
            else:
                raise MintFailed("challenge did not finish within budget")

            cookies = call("Network.getAllCookies", tmo=10).get("result", {}).get("cookies", [])
            ozon = [c for c in cookies if "ozon" in (c.get("domain") or "")]
            cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in ozon)
            if len(abt_prev or "") < ABT_MIN_LEN:
                raise MintFailed("no usable abt_data exported")

            return Session(
                id=uuid.uuid4().hex[:12],
                cookie_header=cookie_header,
                ua=profile["ua"],
                impersonate=profile["impersonate"],
                profile_id=profile["id"],
                minted_at=self._clock(),
                use_count=0,
                state="fresh",
            )
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
            if proc is not None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    pass
            shutil.rmtree(udd, ignore_errors=True)


def _free_port() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_devtools(port: int, attempts: int = 40) -> Optional[str]:
    for _ in range(attempts):
        time.sleep(0.25)
        try:
            raw = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2).read()
            tabs = json.loads(raw.decode("utf-8"))
            for tab in tabs:
                if tab.get("type") == "page" and tab.get("webSocketDebuggerUrl"):
                    return tab["webSocketDebuggerUrl"]
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="V2 cookie supply gate")
    ap.add_argument("--mint-once", action="store_true",
                    help="warm a single session, print a REDACTED event, exit")
    ap.add_argument("--profile", default=None, help="macOS | Windows | Linux")
    args = ap.parse_args(argv)

    if args.mint_once:
        # never inherit ambient proxies into the browser process
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
            os.environ.pop(k, None)
        sup = CookieSupply()
        t0 = time.time()
        try:
            s = sup.mint(profile_hint=args.profile)
        except MintFailed as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return 2
        elapsed = time.time() - t0
        ev = session_redacted(s)
        ev["elapsed_s"] = round(elapsed, 3)
        ev["ok"] = True
        print(json.dumps(ev, ensure_ascii=False))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
