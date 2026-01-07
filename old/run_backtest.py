# scripts/run_backtest.py
# -*- coding: utf-8 -*-

from pathlib import Path
import matplotlib.pyplot as plt

from src.ibkr_data import IBKRData, IBKRConfig
from src.pricing import sigma_proxy_hv_vix
from src.strategy import simulate_periodic_straddle, StraddleParams, PricingParams, HedgeParams

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

    # guardamos sigma proxy
    df_sig.to_csv(OUT_RES / "spy_sigma_proxy_hv_vix.csv", index=False)

    # Params
    str_params = StraddleParams(expiry_target_days=30, roll_frequency="M", strike_round=1.0, contracts=1, multiplier=100)
    prc_params = PricingParams(vol_window=20, vol_annualization=252, risk_free_rate=0.0, dividend_yield=0.0, days_in_year=365)
    initial_cash = 100000.0

    # NO HEDGE
    hedge_off = HedgeParams(enabled=False)
    daily_no, trades_no = simulate_periodic_straddle(
        df_sig[["datetime", "close", "sigma_proxy"]].copy(),
        str_params, prc_params, hedge_off,
        initial_cash=initial_cash,
        sigma_col="sigma_proxy",
    )
    daily_no.to_csv(OUT_RES / "daily_nohedge.csv")
    trades_no.to_csv(OUT_RES / "trades_nohedge.csv", index=False)
    plot_equity(daily_no, "Equity - Long Straddle (No Hedge)", OUT_FIG / "equity_nohedge.png")

    # DELTA HEDGED
    hedge_on = HedgeParams(enabled=True, target_delta=0.0, rebalance_threshold=50.0)
    daily_h, trades_h = simulate_periodic_straddle(
        df_sig[["datetime", "close", "sigma_proxy"]].copy(),
        str_params, prc_params, hedge_on,
        initial_cash=initial_cash,
        sigma_col="sigma_proxy",
    )
    daily_h.to_csv(OUT_RES / "daily_deltahedged.csv")
    trades_h.to_csv(OUT_RES / "trades_deltahedged.csv", index=False)
    plot_equity(daily_h, "Equity - Long Straddle (Delta-Hedged)", OUT_FIG / "equity_deltahedged.png")

    print("\nOK. Files written:")
    print(" -", OUT_RES / "daily_nohedge.csv")
    print(" -", OUT_RES / "daily_deltahedged.csv")
    print(" -", OUT_FIG / "equity_nohedge.png")
    print(" -", OUT_FIG / "equity_deltahedged.png")

if __name__ == "__main__":
    main()

