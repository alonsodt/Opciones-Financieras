# scripts/run_execution_sim.py
# -*- coding: utf-8 -*-

from pathlib import Path
import pandas as pd

from src.execution import ExecutionParams, simulate_legging_cost
from src.strategy import PricingParams


ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "outputs" / "results"


def _ensure_datetime_col(df: pd.DataFrame) -> pd.DataFrame:
    if "datetime" not in df.columns:
        # Si viene como index guardado
        if "Unnamed: 0" in df.columns:
            df = df.rename(columns={"Unnamed: 0": "datetime"})
        else:
            raise ValueError("No encuentro columna 'datetime'.")
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df


def main():
    trades_path = RES / "trades_nohedge.csv"
    daily_path  = RES / "daily_nohedge.csv"

    if not trades_path.exists():
        raise FileNotFoundError(f"No existe {trades_path}. Ejecuta antes scripts.run_backtest.")
    if not daily_path.exists():
        raise FileNotFoundError(f"No existe {daily_path}. Ejecuta antes scripts.run_backtest.")

    trades = pd.read_csv(trades_path)
    trades = _ensure_datetime_col(trades)

    daily = pd.read_csv(daily_path)
    daily = _ensure_datetime_col(daily).set_index("datetime").sort_index()

    # Nos quedamos con aperturas (si tu columna type tiene otro nombre, ajústalo)
    if "type" not in trades.columns:
        raise ValueError("trades_nohedge.csv debe tener columna 'type' (ej: ROLL_OPEN).")

    opens = trades[trades["type"] == "ROLL_OPEN"].copy()
    if opens.empty:
        # fallback: si tu backtest usa otro label
        candidates = trades["type"].unique().tolist()
        raise ValueError(f"No hay filas type=ROLL_OPEN. Types disponibles: {candidates}")

    # Parametrización de simulación
    params = ExecutionParams(
        slippage_bps_combo=1.0,
        slippage_bps_leg=2.0,
        leg_delay_seconds=2.0,
        n_sims=3000,
        seed=42,
        contracts=1,
        multiplier=100,
    )

    prc = PricingParams(days_in_year=365)

    rows = []
    for _, r in opens.iterrows():
        t = pd.Timestamp(r["datetime"])

        # Columnas esperadas en trades: K y expiry
        if "K" not in r.index or "expiry" not in r.index:
            raise ValueError("En trades_nohedge.csv espero columnas 'K' y 'expiry' en las filas ROLL_OPEN.")

        K = float(r["K"])
        expiry = pd.Timestamp(r["expiry"])

        # Columnas esperadas en daily: S y sigma (si no, ajusta a tu naming real)
        if "S" not in daily.columns:
            raise ValueError("En daily_nohedge.csv espero columna 'S' (precio subyacente).")
        if "sigma" not in daily.columns:
            raise ValueError("En daily_nohedge.csv espero columna 'sigma' (vol usada).")

        S = float(daily.loc[t, "S"])
        sigma = float(daily.loc[t, "sigma"])

        # Tiempo a vencimiento en años
        T = max((expiry - t).days / prc.days_in_year, 1e-9)

        out = simulate_legging_cost(
            S=S, K=K, T=T, r=0.0, sigma=sigma, q=0.0,
            params=params,
            order="C_then_P",
        )

        rows.append({
            "datetime": t,
            "K": K,
            "S": S,
            "sigma": sigma,
            "T_years": T,
            **out
        })

    df = pd.DataFrame(rows).sort_values("datetime")

    out_path = RES / "execution_legging_summary.csv"
    df.to_csv(out_path, index=False)

    print("\nSaved:", out_path)
    print(df[["datetime", "sigma", "legging_extra_mean", "total_extra_mean", "total_extra_p90", "total_extra_p99"]].tail(10))


if __name__ == "__main__":
    main()
