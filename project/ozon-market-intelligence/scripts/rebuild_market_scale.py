#!/usr/bin/env python3
"""Rebuild P6 Gross / Net-est / CR4 market scale from toys.db."""
import argparse
import sqlite3
from pathlib import Path
import pandas as pd
import numpy as np

def aggregate(df, group_col):
    rows = []
    for key, g in df.groupby(group_col, dropna=False, sort=False):
        if g["sku"].duplicated().any():
            raise ValueError(f"Duplicate SKU in {group_col}={key}")
        matched = g[g["gross_units_28d"].notna()]
        net = matched[matched["redemption_rate_pct"].notna()]
        gross_units = matched["gross_units_28d"].sum()
        net_units = net["net_units_est_28d"].sum()
        gross_gmv = matched["gross_gmv_rub_28d"].sum()
        net_gmv = net["net_gmv_est_rub_28d"].sum()
        top_gross = matched.sort_values(
            ["gross_units_28d", "sku"], ascending=[False, True]
        ).head(4)
        top_net = net.sort_values(
            ["net_units_est_28d", "sku"], ascending=[False, True]
        ).head(4)
        rows.append({
            group_col: key,
            "p8_unique_sku_count": len(g),
            "p6_matched_sku_count": len(matched),
            "p6_match_coverage_pct": len(matched) / len(g) * 100 if len(g) else np.nan,
            "redemption_known_sku_count": len(net),
            "redemption_missing_matched_sku_count": len(matched) - len(net),
            "gross_units_28d": gross_units,
            "net_units_est_28d": net_units,
            "gross_gmv_rub_28d": gross_gmv,
            "net_gmv_est_rub_28d": net_gmv,
            "gross_asp_rub": gross_gmv / gross_units if gross_units else np.nan,
            "net_asp_est_rub": net_gmv / net_units if net_units else np.nan,
            "cr4_gross_pct": top_gross["gross_units_28d"].sum() / gross_units * 100 if gross_units else np.nan,
            "cr4_net_est_pct": top_net["net_units_est_28d"].sum() / net_units * 100 if net_units else np.nan,
            "top4_gross_sku_ids": "|".join(top_gross["sku"].astype(str)),
            "top4_net_est_sku_ids": "|".join(top_net["sku"].astype(str)),
        })
    return pd.DataFrame(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to toys.db")
    ap.add_argument("--out", required=True, help="Output directory")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    bridge = pd.read_sql_query(
        "SELECT keyword, sku, cluster_id FROM fact_keyword_sku", con
    )
    p8 = pd.read_sql_query(
        "SELECT keyword, sku, position, seller_id AS seller_id_p8, price AS listed_price_rub "
        "FROM keyword_sku", con
    )
    p6 = pd.read_sql_query(
        "SELECT sku, sold_count, gmv_sum, avg_price, redemption_rate, seller_id "
        "FROM sku_snapshot_v2", con
    )
    dim_cluster = pd.read_sql_query("SELECT * FROM dim_cluster", con)
    con.close()

    for frame in (bridge, p8, p6):
        frame["sku"] = frame["sku"].astype(str)
    p6 = p6.rename(columns={
        "sold_count": "gross_units_28d",
        "gmv_sum": "gross_gmv_rub_28d",
        "avg_price": "avg_price_rub",
        "redemption_rate": "redemption_rate_pct",
    })
    p6["net_units_est_28d"] = (
        pd.to_numeric(p6["gross_units_28d"], errors="coerce")
        * pd.to_numeric(p6["redemption_rate_pct"], errors="coerce") / 100
    )
    p6["net_gmv_est_rub_28d"] = (
        p6["net_units_est_28d"] * pd.to_numeric(p6["avg_price_rub"], errors="coerce")
    )

    keyword_rows = bridge.merge(p8, on=["keyword", "sku"], how="left", validate="one_to_one")
    keyword_rows = keyword_rows.merge(p6, on="sku", how="left", validate="many_to_one")
    keyword_market = aggregate(keyword_rows, "keyword")

    cluster_rows = bridge.loc[bridge["cluster_id"].notna(), ["cluster_id", "sku"]].drop_duplicates()
    cluster_rows = cluster_rows.merge(p6, on="sku", how="left", validate="many_to_one")
    cluster_market = dim_cluster[["cluster_id", "name_kw", "n_kw", "total_vol", "avg_g30", "avg_cr4", "avg_homo", "n_sku", "total_sales"]].merge(
        aggregate(cluster_rows, "cluster_id"), on="cluster_id", how="left", validate="one_to_one"
    )

    keyword_market.to_csv(out / "keyword_market_1642.csv", index=False, encoding="utf-8-sig")
    cluster_market.to_csv(out / "cluster_market_165.csv", index=False, encoding="utf-8-sig")
    keyword_rows.to_csv(out / "keyword_sku_detail.csv", index=False, encoding="utf-8-sig")
    cluster_rows.to_csv(out / "cluster_sku_detail.csv", index=False, encoding="utf-8-sig")
    print(f"wrote {len(keyword_market)} keywords and {len(cluster_market)} clusters")

if __name__ == "__main__":
    main()
