#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ozon 买家端前台 (www.ozon.ru) 综合采集脚本。
支持：搜索关键词、类目、单/多 SKU 列表、批量库存提取、1 星差评排雷。

用法示例：
  # 1. 搜索关键词并抓取 2 页（含 stock_max 批量库存与 1 星差评）：
  python3 scripts/collect_buyer.py --keyword "сквиш" --pages 2 --reviews 1 --sort score_asc --out data/buyer_search.json

  # 2. 针对指定 SKU 抓取商品详情画像与差评：
  python3 scripts/collect_buyer.py --sku 5081332378 --sku 5527434733 --reviews 2 --sort score_asc --out data/sku_audit.json

  # 3. 按 SKU 列表文件批量查询：
  python3 scripts/collect_buyer.py --file skus.txt --threads 8 --out data/batch_skus.json
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ozon_buyer.collector import main

if __name__ == "__main__":
    main()
