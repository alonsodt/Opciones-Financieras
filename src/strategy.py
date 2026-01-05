# src/strategy.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Literal, Dict, Any, Tuple, List

import numpy as np
import pandas as pd

from src.pricing import bs_price_greeks, straddle_greeks, hist_vol_close


RollFreq = Literal["W", "M"]


# =========================
# Config dataclasses (simple)
# =========================
@dataclass
class StraddleParams:
    expiry_target_days: int = 30
    roll_frequency: RollFreq = "M"        # "W" o "M"
    strike_round: float = 1.0             # 1.0 para strikes enteros (SPY suele ir por 1)
    contracts: int = 1                    # nº de straddles (call+put)
    multiplier: int = 100                 # SPY options multiplier


@dataclass
class PricingParams:
    vol_window: int = 20
    vol_annualization: int = 252
    risk_free_rate: float = 0.0
    dividend_yield: float = 0.0
    days_in_year: int = 365


@dataclass
class HedgeParams:
    enabled: bool = False
    target_delta: float = 0.0
    rebalance_threshold: float = 0.05     # hedge si |delta - target| > threshold


# =========================
# Internal helpers
# =========================
def _to_timestamp(x) -> pd.Timestamp:
    return pd.Timestamp(x).tz_localize(None) if getattr(x, "tzinfo", None) else pd.Timestamp(x)


def _roll_dates(index: pd.DatetimeIndex, freq: RollFreq) -> pd.DatetimeIndex:
    """
    Devuelve fechas de roll dentro de un índice diario.
    - M: primer día de cada mes presente en index
    - W: primer día de cada semana (lunes) presente en index
    """
    idx = pd.DatetimeIndex(index).tz_localize(None)

    if freq == "M":
        # primer día disponible por mes
        grp = pd.Series(idx).groupby([idx.year, idx.month]).min()
        return pd.DatetimeIndex(grp.values)
    elif freq == "W":
        # lunes de cada semana (o primer día disponible de esa semana)
        # agrupamos por ISO year/week
        iso = idx.isocalendar()
        grp = pd.Series(idx).groupby([iso["year"].values, iso["week"].values]).min()
        return pd.DatetimeIndex(grp.values)
    else:
        raise ValueError("roll_frequency debe ser 'W' o 'M'.")


def _pick_expiry_date(roll_date: pd.Timestamp, target_days: int) -> pd.Timestamp:
    """
    Para el backtest teórico (sin chain histórica), aproximamos la expiración como:
    roll_date + target_days.
    Luego, si cae en fin de semana, la movemos al viernes anterior.
    """
    exp = roll_date + pd.Timedelta(days=int(target_days))

    # Ajuste simple: si sábado/domingo -> viernes
    while exp.weekday() >= 5:
        exp = exp - pd.Timedelta(days=1)

    return exp


def _round_to_step(x: float, step: float) -> float:
    if step <= 0:
        return float(x)
    return round(x / step) * step


# =========================
# Main strategy simulator
# =========================
def simulate_periodic_straddle(
    df_spy: pd.DataFrame,
    straddle: StraddleParams,
    pricing: PricingParams,
    hedge: HedgeParams,
    initial_cash: float = 100000.0
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Simula:
    - Long straddle periódico (roll W/M)
    - (Opcional) delta-hedge con subyacente (shares) usando tus griegas BS.

    Inputs:
    - df_spy: DataFrame con columnas: ['datetime','close'] mínimo.
    - straddle: parámetros de roll y tamaño.
    - pricing: parámetros de vol y BS.
    - hedge: reglas de hedge.
    - initial_cash: cash inicial.

    Outputs:
    - daily: MTM diario, greeks, hedge, equity
    - trades: eventos de roll y hedge (simulados)
    """
    if "datetime" not in df_spy.columns or "close" not in df_spy.columns:
        raise ValueError("df_spy debe tener columnas: datetime, close")

    df = df_spy.copy()
    df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)
    df = df.sort_values("datetime").reset_index(drop=True)
    df = df.set_index("datetime")
    idx = df.index

    # sigma histórica rolling (anualizada)

    if sigma_col in df.columns:
        df["sigma"] = df[sigma_col].astype(float)
    else:
        df["sigma"] = hist_vol_close(df["close"], window=pricing.vol_window, annualization=pricing.vol_annualization)


    # fechas de roll
    roll_dates = set(_roll_dates(idx, straddle.roll_frequency))

    # Estado de la “posición actual”
    current_K: Optional[float] = None
    current_expiry: Optional[pd.Timestamp] = None
    in_position: bool = False

    # Hedge (shares del subyacente)
    shares = 0.0

    # Cash/equity tracking
    cash = float(initial_cash)

    # Logs
    daily_rows: List[Dict[str, Any]] = []
    trades_rows: List[Dict[str, Any]] = []

    # Helpers: pricing multipliers
    contracts = float(straddle.contracts)
    mult = float(straddle.multiplier)

    for t in idx:
        S = float(df.loc[t, "close"])
        sigma = float(df.loc[t, "sigma"]) if math.isfinite(float(df.loc[t, "sigma"])) else float("nan")
        r = float(pricing.risk_free_rate)
        q = float(pricing.dividend_yield)

        # 1) Si toca roll (o aún no estamos posicionados), abrimos nuevo straddle
        if (t in roll_dates) or (not in_position) or (current_expiry is not None and t >= current_expiry):
            # Cerrar posición anterior (si existe) al precio teórico del día t
            if in_position and current_K is not None and current_expiry is not None:
                T_old = max((current_expiry - t).days / pricing.days_in_year, 1e-9)

                if math.isfinite(sigma):
                    old = straddle_greeks(S, current_K, T_old, r, sigma, q=q, days_in_year=pricing.days_in_year)
                    opt_value_old = old["price"] * contracts * mult
                else:
                    opt_value_old = float("nan")

                # En este backtest teórico: cerramos a valor teórico -> cash aumenta por valor de la posición
                if math.isfinite(opt_value_old):
                    cash += opt_value_old

                trades_rows.append({
                    "datetime": t,
                    "type": "ROLL_CLOSE",
                    "K": current_K,
                    "expiry": current_expiry,
                    "contracts": contracts,
                    "option_value": opt_value_old
                })

            # Abrir nuevo straddle
            current_expiry = _pick_expiry_date(t, straddle.expiry_target_days)
            current_K = _round_to_step(S, straddle.strike_round)
            in_position = True

            # Coste de abrir (pagas prima teórica)
            if math.isfinite(sigma):
                T_new = max((current_expiry - t).days / pricing.days_in_year, 1e-9)
                new = straddle_greeks(S, current_K, T_new, r, sigma, q=q, days_in_year=pricing.days_in_year)
                opt_value_new = new["price"] * contracts * mult
            else:
                opt_value_new = float("nan")

            if math.isfinite(opt_value_new):
                cash -= opt_value_new

            trades_rows.append({
                "datetime": t,
                "type": "ROLL_OPEN",
                "K": current_K,
                "expiry": current_expiry,
                "contracts": contracts,
                "option_value": opt_value_new
            })

            # Nota: no tocamos hedge aquí; se gestiona abajo según delta

        # 2) Mark-to-market del straddle actual
        if in_position and current_K is not None and current_expiry is not None and math.isfinite(sigma):
            T = max((current_expiry - t).days / pricing.days_in_year, 1e-9)
            st = straddle_greeks(S, current_K, T, r, sigma, q=q, days_in_year=pricing.days_in_year)
            opt_price = st["price"]                 # por 1 straddle (call+put) y 1x
            opt_value = opt_price * contracts * mult

            # Greeks cartera (en unidades por 1 subyacente)
            # Delta de una opción es por 1 acción; para cartera: *contracts*mult
            port_delta = st["delta"] * contracts * mult
            port_gamma = st["gamma"] * contracts * mult
            port_vega_1pct = st["vega_1pct"] * contracts * mult
            port_theta_day = st["theta_day"] * contracts * mult

        else:
            T = float("nan")
            opt_price = float("nan")
            opt_value = 0.0
            port_delta = 0.0
            port_gamma = 0.0
            port_vega_1pct = 0.0
            port_theta_day = 0.0

        # 3) Delta hedge con subyacente (si enabled)
        hedge_trade = 0.0
        if hedge.enabled and in_position and math.isfinite(port_delta):
            # Delta total incluyendo el hedge actual en acciones
            total_delta = port_delta + shares  # porque 1 share = delta 1

            if abs(total_delta - hedge.target_delta) > hedge.rebalance_threshold:
                # Ajustamos shares para acercarnos al target
                desired_shares = hedge.target_delta - port_delta
                hedge_trade = desired_shares - shares  # compra(+)/venta(-)

                # Ejecutamos a precio S (sin slippage/fees aquí; eso irá en execution.py)
                cash -= hedge_trade * S
                shares = desired_shares

                trades_rows.append({
                    "datetime": t,
                    "type": "HEDGE_TRADE",
                    "shares_trade": hedge_trade,
                    "shares_pos": shares,
                    "price": S,
                    "cash_after": cash
                })

        # 4) Equity (cash + MTM opciones + MTM hedge)
        equity = cash + opt_value + shares * S

        daily_rows.append({
            "datetime": t,
            "S": S,
            "sigma": sigma,
            "K": current_K,
            "expiry": current_expiry,
            "T_years": T,
            "contracts": contracts,
            "shares": shares,

            "opt_price_straddle": opt_price,
            "opt_value": opt_value,

            "delta_opt": port_delta,
            "gamma_opt": port_gamma,
            "vega_1pct_opt": port_vega_1pct,
            "theta_day_opt": port_theta_day,

            "cash": cash,
            "equity": equity,
        })

    daily = pd.DataFrame(daily_rows).set_index("datetime")
    trades = pd.DataFrame(trades_rows)
    if not trades.empty:
        trades["datetime"] = pd.to_datetime(trades["datetime"]).dt.tz_localize(None)
        trades = trades.sort_values("datetime").reset_index(drop=True)

    return daily, trades

