"""Device fingerprint pool — VENDORED from ozon-cookie-harvester.

Source of truth: ``ozon-cookie-harvester/ozon_cookie/profiles.py`` (same author,
same repo lineage). This file is a verbatim vendor of that module so the V2
cookie supply gate does not re-implement fingerprint logic. DO NOT hand-edit
individual rows to "improve" a value: each row is one self-consistent real
device, and cross-row assembly is exactly what ``audit()`` rejects.

Why this module exists (from the upstream docstring):
Ozon's challenge cross-checks three places --
  1. the ``User-Agent`` request header,
  2. ``sec-ch-ua*`` request headers,
  3. in-page ``navigator.userAgentData`` --
and a single mismatch (e.g. page says Mac, request headers say Linux) yields
403 or a half-baked challenge. The only fix is one CDP
``Network.setUserAgentOverride`` call carrying ``userAgent`` + ``acceptLanguage``
+ ``platform`` + ``userAgentMetadata`` in the SAME batch, plus a matching
``Emulation.setDeviceMetricsOverride``.

Public surface (matches upstream):
  * ``PROFILES``, ``CHROME_MAJORS``, ``IMPERSONATE_MAP``
  * ``pick(os_filter=None, seed=None) -> dict``
  * ``cdp_override(profile, accept_language=...) -> dict``
  * ``emulation_metrics(profile) -> dict``
  * ``audit(profile) -> list[str]``  (empty list == self-consistent)
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Device table. Each row is ONE real device; never splice fields across rows.
# ---------------------------------------------------------------------------
PROFILES: List[Dict[str, Any]] = [
    # ---- macOS Apple Silicon ----
    {
        "id": "macbook-pro-14-m3",
        "os": "macOS",
        "ua_platform": "Macintosh; Intel Mac OS X 10_15_7",
        "platform": "macOS",
        "platform_ver": "14.6.1",
        "arch": "arm",
        "bitness": "64",
        "model": "",
        "mobile": False,
        "screen_w": 1512, "screen_h": 982, "dpr": 2.0,
        "cores": 12, "memory_gb": 8,
    },
    {
        "id": "macbook-air-13-m2",
        "os": "macOS",
        "ua_platform": "Macintosh; Intel Mac OS X 10_15_7",
        "platform": "macOS",
        "platform_ver": "13.6.7",
        "arch": "arm",
        "bitness": "64",
        "model": "",
        "mobile": False,
        "screen_w": 1470, "screen_h": 956, "dpr": 2.0,
        "cores": 8, "memory_gb": 8,
    },
    {
        "id": "imac-24-m1",
        "os": "macOS",
        "ua_platform": "Macintosh; Intel Mac OS X 10_15_7",
        "platform": "macOS",
        "platform_ver": "15.1.0",
        "arch": "arm",
        "bitness": "64",
        "model": "",
        "mobile": False,
        "screen_w": 2240, "screen_h": 1260, "dpr": 2.0,
        "cores": 8, "memory_gb": 8,
    },
    # ---- macOS Intel ----
    {
        "id": "macbook-pro-16-intel",
        "os": "macOS",
        "ua_platform": "Macintosh; Intel Mac OS X 10_15_7",
        "platform": "macOS",
        "platform_ver": "12.7.6",
        "arch": "x86",
        "bitness": "64",
        "model": "",
        "mobile": False,
        "screen_w": 1728, "screen_h": 1117, "dpr": 2.0,
        "cores": 8, "memory_gb": 8,
    },
    # ---- Windows 11 ----
    {
        "id": "win11-desktop-1080p",
        "os": "Windows",
        "ua_platform": "Windows NT 10.0; Win64; x64",
        "platform": "Windows",
        "platform_ver": "15.0.0",
        "arch": "x86",
        "bitness": "64",
        "model": "",
        "mobile": False,
        "screen_w": 1920, "screen_h": 1080, "dpr": 1.0,
        "cores": 8, "memory_gb": 8,
    },
    {
        "id": "win11-laptop-1440p",
        "os": "Windows",
        "ua_platform": "Windows NT 10.0; Win64; x64",
        "platform": "Windows",
        "platform_ver": "15.0.0",
        "arch": "x86",
        "bitness": "64",
        "model": "",
        "mobile": False,
        "screen_w": 2560, "screen_h": 1440, "dpr": 1.0,
        "cores": 12, "memory_gb": 8,
    },
    # ---- Windows 10 ----
    {
        "id": "win10-desktop-1080p",
        "os": "Windows",
        "ua_platform": "Windows NT 10.0; Win64; x64",
        "platform": "Windows",
        "platform_ver": "10.0.0",
        "arch": "x86",
        "bitness": "64",
        "model": "",
        "mobile": False,
        "screen_w": 1920, "screen_h": 1080, "dpr": 1.0,
        "cores": 4, "memory_gb": 8,
    },
    # ---- Linux desktop ----
    {
        "id": "linux-ubuntu-1080p",
        "os": "Linux",
        "ua_platform": "X11; Linux x86_64",
        "platform": "Linux",
        "platform_ver": "",
        "arch": "x86",
        "bitness": "64",
        "model": "",
        "mobile": False,
        "screen_w": 1920, "screen_h": 1080, "dpr": 1.0,
        "cores": 8, "memory_gb": 8,
    },
]

# Chrome major candidates. Must stay aligned with what curl_cffi can impersonate.
CHROME_MAJORS = [131, 136, 140, 146, 152, 156]

IMPERSONATE_MAP = {
    131: "chrome131",
    136: "chrome136",
    140: "chrome140",
    146: "chrome146",
    152: "chrome152_macos",
    156: "chrome152_macos",  # curl_cffi has no chrome156; fall back to 152
}


def full_version(major: int) -> str:
    return f"{major}.0.0.0"


def ua_for(profile: Dict[str, Any], major: int) -> str:
    return (
        f"Mozilla/5.0 ({profile['ua_platform']}) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{full_version(major)} Safari/537.36"
    )


def brands_for(major: int) -> List[Dict[str, str]]:
    """Approximate ``sec-ch-ua`` brand list (GREASE). Golden sampling from a
    real same-version Chromium is preferred; this is the fallback."""
    grease_ver = ["8", "99", "24"][major % 3]
    grease_name = ["Not A Brand", "Not_A Brand", "Not;A Brand"][major % 3]
    pairs = [
        {"brand": grease_name, "version": grease_ver},
        {"brand": "Chromium", "version": str(major)},
        {"brand": "Google Chrome", "version": str(major)},
    ]
    order = major % 3
    if order == 1:
        pairs = [pairs[1], pairs[0], pairs[2]]
    elif order == 2:
        pairs = [pairs[2], pairs[1], pairs[0]]
    return pairs


def pick(os_filter: Optional[str] = None, seed: Optional[int] = None) -> Dict[str, Any]:
    rnd = random.Random(seed)
    pool = PROFILES
    if os_filter:
        pool = [p for p in PROFILES if p["os"].lower() == os_filter.lower()]
        if not pool:
            raise ValueError(f"no profile matches os={os_filter}")
    profile = dict(rnd.choice(pool))
    profile["chrome_major"] = rnd.choice(CHROME_MAJORS)
    profile["ua"] = ua_for(profile, profile["chrome_major"])
    profile["impersonate"] = IMPERSONATE_MAP.get(profile["chrome_major"], "chrome146")
    return profile


def cdp_override(
    profile: Dict[str, Any],
    accept_language: str = "ru-RU,ru;q=0.9,en-US;q=0.8",
) -> Dict[str, Any]:
    """``Network.setUserAgentOverride`` params. userAgentMetadata MUST be sent
    in the same batch as userAgent; otherwise the browser keeps the host's
    real platform and produces the contradiction that triggers 403."""
    major = profile["chrome_major"]
    ver = str(major)
    return {
        "userAgent": profile["ua"],
        "acceptLanguage": accept_language,
        "platform": profile["platform"],
        "userAgentMetadata": {
            "brands": brands_for(major),
            "fullVersionList": [
                {"brand": "Chromium", "version": f"{ver}.0.0.0"},
                {"brand": "Google Chrome", "version": f"{ver}.0.0.0"},
            ],
            "fullVersion": f"{ver}.0.0.0",
            "platform": profile["platform"],
            "platformVersion": profile["platform_ver"],
            "architecture": profile["arch"],
            "model": profile["model"],
            "mobile": profile["mobile"],
            "bitness": profile["bitness"],
        },
    }


def emulation_metrics(profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "width": profile["screen_w"],
        "height": profile["screen_h"],
        "deviceScaleFactor": profile["dpr"],
        "mobile": profile["mobile"],
        "screenWidth": profile["screen_w"],
        "screenHeight": profile["screen_h"],
    }


def audit(profile: Dict[str, Any]) -> List[str]:
    """Self-consistency check. Returns a list of problems (empty == OK)."""
    problems: List[str] = []
    ua = profile.get("ua", "")
    plat = profile.get("platform")

    if plat == "macOS" and "Macintosh" not in ua:
        problems.append("platform=macOS 但 UA 不含 Macintosh")
    if plat == "Windows" and "Windows NT" not in ua:
        problems.append("platform=Windows 但 UA 不含 Windows NT")
    if plat == "Linux" and "Linux" not in ua:
        problems.append("platform=Linux 但 UA 不含 Linux")

    major = profile.get("chrome_major")
    if major and f"Chrome/{major}." not in ua:
        problems.append(f"chrome_major={major} 与 UA 内的 Chrome 版本不一致")

    if plat == "macOS" and "Mac OS X 10_15_7" not in ua:
        problems.append("macOS 的 UA 平台段应固定为 Mac OS X 10_15_7")
    if plat == "Windows" and "Windows NT 10.0" not in ua:
        problems.append("Windows 的 UA 平台段应固定为 Windows NT 10.0")
    if profile.get("memory_gb", 0) > 8:
        problems.append("deviceMemory 会被 Chrome 夹到 8，填更大值属于异常")
    if plat == "Linux" and profile.get("platform_ver"):
        problems.append("Linux 的 sec-ch-ua-platform-version 应为空")
    if profile.get("mobile") is True and not profile.get("model"):
        problems.append("mobile=True 时 model 不能为空")
    return problems
