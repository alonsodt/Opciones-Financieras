
# scripts/run_backtest.py
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

# =========================
# Outputs
# =========================
ROOT = Path(__file__).resolve().parents[1]
OUT_RES = ROOT / "outputs" / "results"
OUT_FIG = ROOT / "outputs" / "figures"
OUT_RES.mkdir(parents=True, exist_ok=True)
OUT_FIG.mkdir(parents=True, exist_ok=True)


def plot_equity(daily, title: str, save_path: Path):
    plt.figure()
    daily["equity"].plot()
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel("Equity")
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()


def main():
    # ================
    # 1) Conectar IBKR
    # ================
    cfg = IBKRConfig(host="127.0.0.1", port=7497, client_id=28, use_market_data=False)
    ibd = IBKRData(cfg)

    try:
        ibd.connect()

        # ============================
        # 2) Descargar históricos SPY
        # ============================
        spy = ibd.stock("SPY")
        df_spy = ibd.historical_bars(spy, duration="5 Y", bar_size="1 day")[["datetime", "close"]]

        # ============================
        # 3) Descargar histórico VIX
        # ============================
        df_vix = ibd.historical_vix(duration="5 Y", bar_size="1 day")

    finally:
        ibd.disconnect()

    # ============================
    # 4) Sigma proxy HV + VIX
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

    print(df_sig.tail())
    print(
        "sigma_proxy last:",
        df_sig["sigma_proxy"].iloc[-1],
        "HV last:",
        df_sig["hv"].iloc[-1],
        "VIX last:",
        df_sig["vix"].iloc[-1],
    )

    # ============================
    # 5) Parámetros estrategia
    # ============================
    str_params = StraddleParams(
        expiry_target_days=30,
        roll_frequency="M",    # cámbialo a "W" si quieres semanal
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

    initial_cash = 100000.0

    # ============================
    # 6) Backtest SIN hedge
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

    daily_no.to_csv(OUT_RES / "daily_straddle_nohedge.csv")
    trades_no.to_csv(OUT_RES / "trades_straddle_nohedge.csv", index=False)
    plot_equity(daily_no, "SPY Long Straddle (No Hedge) - Equity", OUT_FIG / "equity_nohedge.png")

    # ============================
    # 7) Backtest CON delta hedge
    # ============================
    # OJO: el threshold está en "shares" (delta cartera ≈ shares).
    # Para 1 straddle *100, deltas del orden decenas de shares.
    hedge_on = HedgeParams(enabled=True, target_delta=0.0, rebalance_threshold=50.0)

    daily_h, trades_h = simulate_periodic_straddle(
        df_sig[["datetime", "close", "sigma_proxy"]].copy(),
        str_params,
        prc_params,
        hedge_on,
        initial_cash=initial_cash,
        sigma_col="sigma_proxy",
    )

    daily_h.to_csv(OUT_RES / "daily_straddle_deltahedged.csv")
    trades_h.to_csv(OUT_RES / "trades_straddle_deltahedged.csv", index=False)
    plot_equity(daily_h, "SPY Long Straddle (Delta-Hedged) - Equity", OUT_FIG / "equity_deltahedged.png")

    # ============================
    # 8) Resumen rápido por consola
    # ============================
    def summary(daily, name):
        eq0 = float(daily["equity"].iloc[0])
        eq1 = float(daily["equity"].iloc[-1])
        ret = (eq1 / eq0) - 1.0
        dd = (daily["equity"] / daily["equity"].cummax() - 1.0).min()
        print(f"\n{name}")
        print(f"  Start equity: {eq0:,.2f}")
        print(f"  End equity  : {eq1:,.2f}")
        print(f"  Total return: {ret*100:,.2f}%")
        print(f"  Max drawdown: {dd*100:,.2f}%")

    summary(daily_no, "NO HEDGE")
    summary(daily_h, "DELTA HEDGED")

    print("\nSaved:")
    print(" -", OUT_RES / "daily_straddle_nohedge.csv")
    print(" -", OUT_RES / "daily_straddle_deltahedged.csv")
    print(" -", OUT_FIG / "equity_nohedge.png")
    print(" -", OUT_FIG / "equity_deltahedged.png")


if __name__ == "__main__":
    main()
