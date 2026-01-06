# scripts/run_delta_neutral_option.py
# -*- coding: utf-8 -*-

import pandas as pd

from src.backtest import delta_neutral_with_option, describe_implications


def main():
    # Escenario ejemplo (puedes poner el último día real de tu daily)
    S = 688.25
    sigma = 0.125
    r = 0.0
    q = 0.0
    T = 30 / 365  # 30 días
    K_atm = round(S)  # ATM aproximado

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
        imp = describe_implications(res)

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
            "gamma_change": imp["gamma_change_vs_base"],
            "vega_change": imp["vega_change_vs_base"],
            "theta_change": imp["theta_change_vs_base"],
        })

    df = pd.DataFrame(rows)
    # más legible
    pd.set_option("display.max_columns", None)
    print(df)

    print("\nInterpretación rápida:")
    print("- Delta total ~0 (por construcción).")
    print("- Si el hedge option tiene gamma/vega, las añades (o las reduces si n sale negativo).")
    print("- Normalmente empeoras theta (más negativa) porque añades más valor temporal.")

if __name__ == "__main__":
    main()
