# scripts/run_results.py
# -*- coding: utf-8 -*-

from pathlib import Path
import matplotlib.pyplot as plt

from src.ibkr_data import IBKRData, IBKRConfig
from src.pricing import sigma_proxy_hv_vix
from src.strategy import (
    simulate_periodic_straddle,
    StraddleParams,
    PricingParams,
    HedgeParams,
)

ROOT = Path(__file__).resolve().parents[1]
OUT_RES = ROOT / "outputs" / "results"
OUT_FIG = ROOT / "outputs" / "figures"
OUT_RES.mkdir(parents=True, exist_ok=True)
OUT_FIG.mkdir(parents=True, exist_ok=True)


def max_drawdown(equity_series):
    peak = equity_series.cummax()
    dd = equity_series / peak - 1.0
    return float(dd.min())


def plot_series(series, title, ylabel, save_path: Path):
    plt.figure()
    series.plot()
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel(ylabel)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()


def summarize(daily, name: str):
    eq = daily["equity"].astype(float)
    eq0 = float(eq.iloc[0])
    eq1 = float(eq.iloc[-1])
    total_return = eq1 / eq0 - 1.0
    dd = max_drawdown(eq)

    # Retornos diarios para stats simples
    rets = eq.pct_change().dropna()
    vol = float(rets.std()) if len(rets) else float("nan")
    mean = float(rets.mean()) if len(rets) else float("nan")

    # Sharpe simple (sin rf) anualizado 252
    sharpe = (mean / vol) * (252 ** 0.5) if vol and vol > 0 else float("nan")

    print(f"\n==== {name} ====")
    print(f"Start equity : {eq0:,.2f}")
    print(f"End equity   : {eq1:,.2f}")
    print(f"Total return : {total_return*100:,.2f}%")
    print(f"Max drawdown : {dd*100:,.2f}%")
    print(f"Daily mean   : {mean*100:,.4f}%")
    print(f"Daily vol    : {vol*100:,.4f}%")
    print(f"Sharpe (252) : {sharpe:,.3f}")

    return {
        "name": name,
        "start_equity": eq0,
        "end_equity": eq1,
        "total_return": total_return,
        "max_drawdown": dd,
        "daily_mean": mean,
        "daily_vol": vol,
        "sharpe_252": sharpe,
    }


def main():
    # ============================
    # 1) IBKR: descargar SPY y VIX
    # ============================
    cfg = IBKRConfig(host="127.0.0.1", port=7497, client_id=28, use_market_data=False)
    ibd = IBKRData(cfg)

    try:
        ibd.connect()

        spy = ibd.stock("SPY")
        df_spy = ibd.historical_bars(spy, duration="5 Y", bar_size="1 day")[["datetime", "close"]]

        df_vix = ibd.historical_vix(duration="5 Y", bar_size="1 day")

    finally:
        ibd.disconnect()

    # ============================
    # 2) Sigma proxy HV + VIX
    # ============================
    df_sig = sigma_proxy_hv_vix(
        df_spy=df_spy,
        df_vix=df_vix,
        hv_window=20,
        hv_annualization=252,
        vix_weight=0.6,
        sigma_floor=0.05,
        sigma_cap=2.0,
    )

    print("\n--- Sigma proxy tail ---")
    print(df_sig.tail())
    print(
        "sigma_proxy last:", df_sig["sigma_proxy"].iloc[-1],
        "HV last:", df_sig["hv"].iloc[-1],
        "VIX last:", df_sig["vix"].iloc[-1],
    )

    # Guardamos sigma proxy
    df_sig.to_csv(OUT_RES / "spy_sigma_proxy_hv_vix.csv", index=False)

    # ============================
    # 3) Parámetros estrategia
    # ============================
    initial_cash = 100000.0

    str_params = StraddleParams(
        expiry_target_days=30,
        roll_frequency="M",   # "W" si quieres semanal
        strike_round=1.0,
        contracts=1,
        multiplier=100,
    )

    prc_params = PricingParams(
        vol_window=20,
        vol_annualization=252,
        risk_free_rate=0.0,
        dividend_yield=0.0,
        days_in_year=365,
    )

    # ============================
    # 4) Backtest sin hedge
    # ============================
    hedge_off = HedgeParams(enabled=False)
    daily_no, trades_no = simulate_periodic_straddle(
        df_sig[["datetime", "close", "sigma_proxy"]].copy(),
        str_params,
        prc_params,
        hedge_off,
        initial_cash=initial_cash,
        sigma_col="sigma_proxy",
    )

    daily_no.to_csv(OUT_RES / "daily_nohedge.csv")
    trades_no.to_csv(OUT_RES / "trades_nohedge.csv", index=False)

    plot_series(daily_no["equity"], "Equity - Long Straddle (No Hedge)", "Equity", OUT_FIG / "equity_nohedge.png")

    # Extra plots útiles
    plot_series(daily_no["sigma"].dropna(), "Sigma used (proxy)", "Sigma", OUT_FIG / "sigma_proxy.png")

    # ============================
    # 5) Backtest delta-hedged
    # ============================
    # Threshold en shares (por multiplicador=100)
    hedge_on = HedgeParams(enabled=True, target_delta=0.0, rebalance_threshold=50.0)

    daily_h, trades_h = simulate_periodic_straddle(
        df_sig[["datetime", "close", "sigma_proxy"]].copy(),
        str_params,
        prc_params,
        hedge_on,
        initial_cash=initial_cash,
        sigma_col="sigma_proxy",
    )

    daily_h.to_csv(OUT_RES / "daily_deltahedged.csv")
    trades_h.to_csv(OUT_RES / "trades_deltahedged.csv", index=False)

    plot_series(daily_h["equity"], "Equity - Long Straddle (Delta-Hedged)", "Equity", OUT_FIG / "equity_deltahedged.png")

    # ============================
    # 6) Resumen comparativo
    # ============================
    stats_no = summarize(daily_no, "NO HEDGE")
    stats_h  = summarize(daily_h, "DELTA HEDGED")

    # Guardar resumen
    summary_path = OUT_RES / "summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        for s in (stats_no, stats_h):
            f.write(f"==== {s['name']} ====\n")
            f.write(f"Start equity : {s['start_equity']:.2f}\n")
            f.write(f"End equity   : {s['end_equity']:.2f}\n")
            f.write(f"Total return : {s['total_return']*100:.4f}%\n")
            f.write(f"Max drawdown : {s['max_drawdown']*100:.4f}%\n")
            f.write(f"Daily mean   : {s['daily_mean']*100:.6f}%\n")
            f.write(f"Daily vol    : {s['daily_vol']*100:.6f}%\n")
            f.write(f"Sharpe (252) : {s['sharpe_252']:.4f}\n\n")

    print("\nSaved outputs:")
    print(" -", OUT_RES / "spy_sigma_proxy_hv_vix.csv")
    print(" -", OUT_RES / "daily_nohedge.csv")
    print(" -", OUT_RES / "daily_deltahedged.csv")
    print(" -", OUT_RES / "summary.txt")
    print(" -", OUT_FIG / "equity_nohedge.png")
    print(" -", OUT_FIG / "equity_deltahedged.png")
    print(" -", OUT_FIG / "sigma_proxy.png")

    # Un tip rápido para validar si el hedge está “operando demasiado”
    if not trades_h.empty:
        n_hedges = int((trades_h["type"] == "HEDGE_TRADE").sum()) if "type" in trades_h.columns else len(trades_h)
        print(f"\nDelta-hedge trades: {n_hedges} (mira trades_deltahedged.csv)")
    else:
        print("\nDelta-hedge trades: 0 (quizá threshold demasiado alto)")


if __name__ == "__main__":
    main()
