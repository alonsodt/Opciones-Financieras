# scripts/run_all.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from datetime import datetime

import pandas as pd

from src.ibkr_data import IBKRData, IBKRConfig
from src.pricing import sigma_proxy_hv_vix
from src.strategy import simulate_periodic_straddle, StraddleParams, PricingParams, HedgeParams
from src.analytics import run_analytics, AnalyticsConfig
from src.execution import ExecutionParams, simulate_legging_cost
from src.backtest import delta_neutral_with_option


ROOT = Path(__file__).resolve().parents[1]
OUT_RES = ROOT / "outputs" / "results"
OUT_FIG = ROOT / "outputs" / "figures"
OUT_RES.mkdir(parents=True, exist_ok=True)
OUT_FIG.mkdir(parents=True, exist_ok=True)


def _ensure_dt(df: pd.DataFrame) -> pd.DataFrame:
    if "datetime" not in df.columns and "Unnamed: 0" in df.columns:
        df = df.rename(columns={"Unnamed: 0": "datetime"})
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"])
    return df


def run_backtests() -> tuple[Path, Path, Path, Path]:
    """
    Enunciado:
    1) estrategia long straddle periódico SPY
    2) versión delta-hedged con subyacente
    """
    print("\n==============================")
    print("1-2) BACKTEST: No hedge vs Delta-hedged")
    print("==============================")

    cfg = IBKRConfig(host="127.0.0.1", port=7497, client_id=28, use_market_data=False)
    ibd = IBKRData(cfg)

    try:
        ibd.connect()
        spy = ibd.stock("SPY")
        df_spy = ibd.historical_bars(spy, duration="5 Y", bar_size="1 day")[["datetime", "close"]]
        df_vix = ibd.historical_vix(duration="5 Y", bar_size="1 day")
    finally:
        ibd.disconnect()

    df_sig = sigma_proxy_hv_vix(
        df_spy=df_spy,
        df_vix=df_vix,
        hv_window=20,
        hv_annualization=252,
        vix_weight=0.6,
        sigma_floor=0.05,
        sigma_cap=2.0,
    )
    (OUT_RES / "spy_sigma_proxy_hv_vix.csv").write_text("", encoding="utf-8")  # touch for clarity
    df_sig.to_csv(OUT_RES / "spy_sigma_proxy_hv_vix.csv", index=False)

    str_params = StraddleParams(expiry_target_days=30, roll_frequency="M", strike_round=1.0, contracts=1, multiplier=100)
    prc_params = PricingParams(vol_window=20, vol_annualization=252, risk_free_rate=0.0, dividend_yield=0.0, days_in_year=365)
    initial_cash = 100000.0

    # No hedge
    hedge_off = HedgeParams(enabled=False)
    daily_no, trades_no = simulate_periodic_straddle(
        df_sig[["datetime", "close", "sigma_proxy"]].copy(),
        str_params, prc_params, hedge_off,
        initial_cash=initial_cash,
        sigma_col="sigma_proxy",
    )
    p_daily_no = OUT_RES / "daily_nohedge.csv"
    p_trades_no = OUT_RES / "trades_nohedge.csv"
    daily_no.to_csv(p_daily_no)
    trades_no.to_csv(p_trades_no, index=False)

    # Delta-hedged
    hedge_on = HedgeParams(enabled=True, target_delta=0.0, rebalance_threshold=50.0)
    daily_h, trades_h = simulate_periodic_straddle(
        df_sig[["datetime", "close", "sigma_proxy"]].copy(),
        str_params, prc_params, hedge_on,
        initial_cash=initial_cash,
        sigma_col="sigma_proxy",
    )
    p_daily_h = OUT_RES / "daily_deltahedged.csv"
    p_trades_h = OUT_RES / "trades_deltahedged.csv"
    daily_h.to_csv(p_daily_h)
    trades_h.to_csv(p_trades_h, index=False)

    print("OK:", p_daily_no.name, p_daily_h.name, p_trades_no.name, p_trades_h.name)
    return p_daily_no, p_daily_h, p_trades_no, p_trades_h


def run_analytics_block(p_daily_no: Path, p_daily_h: Path):
    """
    Enunciado:
    3) Analizar P&L histórico de ambas versiones
    """
    print("\n==============================")
    print("3) ANALYTICS: métricas + gráficos")
    print("==============================")

    cfg = AnalyticsConfig(periods_per_year=252, rf_annual=0.0, rolling_vol_window=63)
    _, _, summary = run_analytics(
        daily_nohedge_path=p_daily_no,
        daily_hedged_path=p_daily_h,
        out_results_dir=OUT_RES,
        out_figures_dir=OUT_FIG,
        cfg=cfg
    )
    print("\nSummary (head):")
    print(summary[["strategy", "total_return", "cagr", "ann_vol", "sharpe", "max_drawdown", "calmar", "hit_ratio"]])
    return summary


def run_execution_legging(p_trades_no: Path, p_daily_no: Path):
    """
    Enunciado:
    4) Simular envío de órdenes: combo vs patas, riesgo de legging
    """
    print("\n==============================")
    print("4) EXECUTION: combo vs legs (legging risk)")
    print("==============================")

    trades = _ensure_dt(pd.read_csv(p_trades_no))
    daily = _ensure_dt(pd.read_csv(p_daily_no)).set_index("datetime").sort_index()

    if "type" not in trades.columns:
        raise ValueError("trades_nohedge.csv debe tener columna 'type' (esperado: ROLL_OPEN).")

    opens = trades[trades["type"] == "ROLL_OPEN"].copy()
    if opens.empty:
        raise ValueError(f"No hay filas type=ROLL_OPEN. Types disponibles: {trades['type'].unique().tolist()}")

    if "S" not in daily.columns or "sigma" not in daily.columns:
        raise ValueError("daily_nohedge.csv debe tener columnas 'S' y 'sigma' para simular legging.")

    prc = PricingParams(days_in_year=365)
    params = ExecutionParams(
        slippage_bps_combo=1.0,
        slippage_bps_leg=2.0,
        leg_delay_seconds=2.0,
        n_sims=3000,
        seed=42,
        contracts=1,
        multiplier=100,
    )

    rows = []
    for _, r in opens.iterrows():
        t = pd.Timestamp(r["datetime"])
        if "K" not in r.index or "expiry" not in r.index:
            raise ValueError("En trades_nohedge.csv espero columnas 'K' y 'expiry' en las filas ROLL_OPEN.")

        K = float(r["K"])
        expiry = pd.Timestamp(r["expiry"])

        S = float(daily.loc[t, "S"])
        sigma = float(daily.loc[t, "sigma"])
        T = max((expiry - t).days / prc.days_in_year, 1e-9)

        out = simulate_legging_cost(S=S, K=K, T=T, r=0.0, sigma=sigma, q=0.0, params=params, order="C_then_P")
        rows.append({"datetime": t, "S": S, "K": K, "sigma": sigma, "T_years": T, **out})

    df = pd.DataFrame(rows).sort_values("datetime")
    out_path = OUT_RES / "execution_legging_summary.csv"
    df.to_csv(out_path, index=False)

    print("Saved:", out_path.name)
    print(df[["datetime", "sigma", "legging_extra_mean", "total_extra_mean", "total_extra_p90", "total_extra_p99"]].tail(5))
    return out_path


def run_delta_neutral_option_demo():
    """
    Enunciado:
    5) Neutralizar Delta con otra opción e implicaciones para Gamma/Vega/Theta
    """
    print("\n==============================")
    print("5) DELTA NEUTRAL con OTRA OPCIÓN: impacto en griegas")
    print("==============================")

    # Escenario representativo (puedes ajustar)
    S = 688.25
    sigma = 0.125
    r = 0.0
    q = 0.0
    T = 30 / 365
    K_atm = round(S)

    scenarios = [
        ("Hedge CALL ATM", "C", K_atm),
        ("Hedge PUT  ATM", "P", K_atm),
        ("Hedge CALL 2% OTM", "C", round(S * 1.02)),
        ("Hedge PUT  2% OTM", "P", round(S * 0.98)),
    ]

    rows = []
    for name, right, K_hedge in scenarios:
        res = delta_neutral_with_option(
            S=S,
            K_straddle=K_atm,
            K_hedge=K_hedge,
            T=T,
            r=r,
            sigma=sigma,
            q=q,
            hedge_right=right,
            days_in_year=365
        )
        rows.append({
            "scenario": name,
            "K_straddle": K_atm,
            "K_hedge": K_hedge,
            "n_hedge": res.n_hedge,
            "total_delta": res.total["delta"],
            "base_gamma": res.base["gamma"],
            "total_gamma": res.total["gamma"],
            "base_vega_1pct": res.base["vega_1pct"],
            "total_vega_1pct": res.total["vega_1pct"],
            "base_theta_day": res.base["theta_day"],
            "total_theta_day": res.total["theta_day"],
        })

    df = pd.DataFrame(rows)
    out_path = OUT_RES / "delta_neutral_option_summary.csv"
    df.to_csv(out_path, index=False)

    print("Saved:", out_path.name)
    print(df)
    return out_path


def write_run_report(summary_df: pd.DataFrame):
    report = OUT_RES / "RUN_REPORT.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    txt = []
    txt.append(f"# Run report\n\nGenerado: `{now}`\n\n")
    txt.append("## Outputs (mapeados al enunciado)\n\n")
    txt.append("### 1) Long straddle periódico (SPY)\n")
    txt.append("- `outputs/results/daily_nohedge.csv`\n")
    txt.append("- `outputs/results/trades_nohedge.csv`\n\n")
    txt.append("### 2) Versión delta-hedged (subyacente)\n")
    txt.append("- `outputs/results/daily_deltahedged.csv`\n")
    txt.append("- `outputs/results/trades_deltahedged.csv`\n\n")
    txt.append("### 3) Análisis P&L (métricas + gráficos)\n")
    txt.append("- `outputs/results/summary_metrics.csv`\n")
    txt.append("- `outputs/figures/equity_compare.png`\n")
    txt.append("- `outputs/figures/drawdown_compare.png`\n")
    txt.append("- `outputs/figures/rolling_vol_compare.png`\n\n")
    txt.append("### 4) Ejecución: combo vs patas (legging)\n")
    txt.append("- `outputs/results/execution_legging_summary.csv`\n\n")
    txt.append("### 5) Delta-neutral con otra opción (impacto Gamma/Vega/Theta)\n")
    txt.append("- `outputs/results/delta_neutral_option_summary.csv`\n\n")
    txt.append("### 6) Reflexión SPX vs SPY\n")
    txt.append("- `REFLEXION.md`\n\n")

    txt.append("## Métricas clave\n\n")
    txt.append(summary_df.to_markdown(index=False))
    txt.append("\n")

    report.write_text("\n".join(txt), encoding="utf-8")
    print("\n📝 Report:", report)


def main():
    print("\n==============================")
    print("   PRACTICA 4 - RUN ALL")
    print("==============================")
    print("IMPORTANTE: abre TWS y deja API activa.\n")

    p_daily_no, p_daily_h, p_trades_no, _ = run_backtests()
    summary = run_analytics_block(p_daily_no, p_daily_h)
    run_execution_legging(p_trades_no, p_daily_no)
    run_delta_neutral_option_demo()
    write_run_report(summary)

    print("\n✅ Pipeline completo generado. Revisa outputs/results y outputs/figures.\n")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()

