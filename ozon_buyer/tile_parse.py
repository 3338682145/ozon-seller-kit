"""买家前台 tile 卡片的纯解析工具：无网络、无 IO、无副作用。

为什么单独抽出来
----------------
`ozon_buyer/collector.py` 与 `ozon_buyer/http.py` 各维护了一份 tile 解析，关键语义分叉：

1. `is_advert` 两处都写 `bool(...get("advertLite"))`，把「字段缺失」和「明确不是广告」
   压成同一个 `False`，广告密度会被系统性低估。
2. `stock_max` 直接透传 `maxItems`，可能是字符串 `"12"`，也可能是 missing；
   下游无法区分「没有库存上限信息」和「库存上限为 0」。
3. 抓取 widget 的 key 匹配范围不同：collector 认 `searchResultsV2`/`tileGrid`/`tile`
   三种，http 只认 `tileGridDesktop`，同一份响应可能一处有结果、另一处返回空。

这里把三处语义收敛成纯函数，供两个调用点共用，并能完全离线单测
（不依赖 curl_cffi、浏览器或真实网络）。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

# entrypoint-api 的商品卡片可能挂在多种 widget key 下，历史上三种都出现过。
TILE_WIDGET_KEYWORDS: Tuple[str, ...] = ("searchResultsV2", "tileGrid", "tile")

_ADVERT_PATH: Tuple[str, ...] = ("trackingInfo", "click", "custom", "advertLite")

_MISSING = object()


def is_tile_widget_key(key: Any) -> bool:
    """判断一个 widgetStates 的 key 是否可能承载商品卡片列表。"""
    if not isinstance(key, str):
        return False
    return any(word in key for word in TILE_WIDGET_KEYWORDS)


def _unwrap_body(page_json: Any) -> Any:
    """entrypoint-api 有时把 payload 包在 body 字段里（字符串化 JSON）。"""
    if isinstance(page_json, dict) and "body" in page_json:
        body = page_json["body"]
        if isinstance(body, str):
            try:
                return json.loads(body)
            except (json.JSONDecodeError, TypeError):
                return {}
        return body if isinstance(body, dict) else {}
    return page_json


def iter_tile_items(
    page_json: Any, errors: Optional[List[Dict[str, Any]]] = None
) -> Iterator[Tuple[str, Dict[str, Any]]]:
    """逐个产出 ``(widget_key, tile_payload)``。

    `tile_payload` 是解析后的 dict，调用方自己取 `items`。
    单个 widget 解析失败不会中断整页：错误记到 `errors`（若传入），
    这样「解析失败」与「页面真的没有商品」不再混为一谈。
    """
    root = _unwrap_body(page_json)
    if not isinstance(root, dict):
        return
    widget_states = root.get("widgetStates") or {}
    if not isinstance(widget_states, dict):
        return
    for key, raw in widget_states.items():
        if not is_tile_widget_key(key):
            continue
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError) as exc:
            if errors is not None:
                errors.append({"widget": key, "error": f"JSONDecodeError: {exc}"})
            continue
        if isinstance(payload, dict):
            yield key, payload
        elif errors is not None:
            errors.append({"widget": key, "error": f"payload is {type(payload).__name__}, expected dict"})


def _dig(obj: Any, path: Tuple[str, ...], default: Any = _MISSING) -> Any:
    cur = obj
    for name in path:
        if not isinstance(cur, dict) or name not in cur:
            return default
        cur = cur[name]
    return cur


def parse_advert_flag(tile: Any) -> Optional[bool]:
    """广告位标记，三态语义。

    - ``True``：明确是广告位
    - ``False``：明确不是广告位
    - ``None``：字段缺失或值为 null —— **未知，不得当成自然位**

    旧实现 `bool(advertLite)` 会把 None 变成 False；本函数刻意不这么做。
    遇到无法判断的结构体（dict/list）同样返回 None，避免猜测。
    """
    value = _dig(tile if isinstance(tile, dict) else {}, _ADVERT_PATH)
    if value is _MISSING or value is None:
        return None
    if isinstance(value, (dict, list)):
        return None
    return bool(value)


def _as_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        digits = re.sub(r"[^\d]", "", value.replace("\u202f", "").replace("\u00a0", ""))
        return int(digits) if digits else None
    return None


def parse_stock_max(tile: Any) -> Optional[int]:
    """购物车可加购上限 `maxItems`，规范成 int 或 None。

    路径按实测优先级：``multiButton.ozonButton.addToCart.quantityButton`` →
    ``ozonButton.quantityButton`` → ``multiButton.quantityButton`` →
    ``mainState[type=quantityButton].quantityButton``。

    注意：这是**页面代理值**（最多可加购多少件），不等于经过仓储核验的实物库存。
    返回 None 表示该卡片没有给出上限，而不是 0。
    """
    if not isinstance(tile, dict):
        return None

    multi_button = tile.get("multiButton") or {}
    ozon_button = multi_button.get("ozonButton") if isinstance(multi_button, dict) else None
    ozon_button = ozon_button or {}

    quantity_button: Any = {}
    if isinstance(ozon_button, dict):
        add_to_cart = ozon_button.get("addToCart") or {}
        if isinstance(add_to_cart, dict):
            quantity_button = add_to_cart.get("quantityButton")
        if not quantity_button:
            quantity_button = ozon_button.get("quantityButton")
    if not quantity_button and isinstance(multi_button, dict):
        quantity_button = multi_button.get("quantityButton")

    if isinstance(quantity_button, dict):
        candidate = quantity_button.get("maxItems")
        if candidate is not None:
            return _as_int(candidate)

    for state in tile.get("mainState") or []:
        if isinstance(state, dict) and state.get("type") == "quantityButton":
            fallback = (state.get("quantityButton") or {}).get("maxItems")
            return _as_int(fallback)

    return None
