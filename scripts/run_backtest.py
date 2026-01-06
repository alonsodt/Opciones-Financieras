# scripts/run_analytics.py
# -*- coding: utf-8 -*-

from pathlib import Path
from src.analytics import run_analytics, AnalyticsConfig

ROOT = Path(__file__).resolve().parents[1]

def main():
    daily_no = ROOT / "outputs" / "results" / "daily_nohedge.csv"
    daily_h  = ROOT / "outputs" / "results" / "daily_deltahedged.csv"

    out_res = ROOT / "outputs" / "results"
    out_fig = ROOT / "outputs" / "figures"

    cfg = AnalyticsConfig(
        periods_per_year=252,
        rf_annual=0.0,
        rolling_vol_window=63
    )

    _, _, summary = run_analytics(
        daily_nohedge_path=daily_no,
        daily_hedged_path=daily_h,
        out_results_dir=out_res,
        out_figures_dir=out_fig,
        cfg=cfg
    )

    print("\nSaved: outputs/results/summary_metrics.csv")
    print(summary[["strategy", "total_return", "cagr", "ann_vol", "sharpe", "max_drawdown", "calmar", "hit_ratio"]])

if __name__ == "__main__":
    main()



if __name__ == "__main__":
    main()
