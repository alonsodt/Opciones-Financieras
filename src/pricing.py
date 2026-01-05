# src/pricing.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Dict

import numpy as np
import pandas as pd

OptionType = Literal["C", "P"]


# =========================
# Normal PDF / CDF
# =========================
_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)

def norm_pdf(x: float) -> float:
    return _INV_SQRT_2PI * math.exp(-0.5 * x * x)

def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# =========================
# Vol helpers
# =========================
def hist_vol_close(close: pd.Series, window: int = 20, annualization: int = 252) -> pd.Series:
    """
    Volatilidad histórica anualizada usando log-returns y rolling std.
    """
    close = close.astype(float)
    rets = np.log(close / close.shift(1))
    return rets.rolling(window).std() * math.sqrt(annualization)


# =========================
# BS + Greeks (report-friendly)
# =========================
@dataclass
class BSGreeks:
    price: float
    delta: float
    gamma: float
    vega_1pct: float    # cambio de precio por +1% (0.01) de vol
    theta_day: float    # cambio de precio por 1 día (convención 365 días)


def bs_price_greeks(
    S: float,
    K: float,
    T: float,               # años
    r: float,
    sigma: float,
    opt_type: OptionType,
    q: float = 0.0,
    days_in_year: int = 365
) -> BSGreeks:
    """
    Black-Scholes europea con dividend yield q.

    Devuelve:
    - vega_1pct: por +1 punto de vol (p.ej. 20%->21%)
    - theta_day: por día (dividiendo la theta anual entre days_in_year)

    Nota: internamente se calcula la theta "por año" (porque T está en años),
    y luego se convierte a diaria.
    """
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        nan = float("nan")
        return BSGreeks(nan, nan, nan, nan, nan)

    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT

    Nd1 = norm_cdf(d1)
    Nd2 = norm_cdf(d2)
    n_d1 = norm_pdf(d1)

    disc_r = math.exp(-r * T)
    disc_q = math.exp(-q * T)

    if opt_type == "C":
        price = disc_q * S * Nd1 - disc_r * K * Nd2
        delta = disc_q * Nd1
        theta_year = (-disc_q * (S * n_d1 * sigma) / (2 * sqrtT)
                      - r * disc_r * K * Nd2
                      + q * disc_q * S * Nd1)
    else:
        Nmd1 = norm_cdf(-d1)
        Nmd2 = norm_cdf(-d2)
        price = disc_r * K * Nmd2 - disc_q * S * Nmd1
        delta = -disc_q * Nmd1
        theta_year = (-disc_q * (S * n_d1 * sigma) / (2 * sqrtT)
                      + r * disc_r * K * Nmd2
                      - q * disc_q * S * Nmd1)

    gamma = disc_q * n_d1 / (S * sigma * sqrtT)

    # Vega "por 1.0" de vol (100 puntos) -> vega_1pct = /100
    vega = disc_q * S * n_d1 * sqrtT
    vega_1pct = vega / 100.0

    theta_day = theta_year / float(days_in_year)

    return BSGreeks(
        price=float(price),
        delta=float(delta),
        gamma=float(gamma),
        vega_1pct=float(vega_1pct),
        theta_day=float(theta_day)
    )


def straddle_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    q: float = 0.0,
    days_in_year: int = 365
) -> Dict[str, float]:
    """
    Long straddle = long call + long put.
    Devuelve greeks agregadas en unidades "visuales":
    - vega_1pct
    - theta_day
    """
    call = bs_price_greeks(S, K, T, r, sigma, "C", q=q, days_in_year=days_in_year)
    put  = bs_price_greeks(S, K, T, r, sigma, "P", q=q, days_in_year=days_in_year)

    return {
        "price": call.price + put.price,
        "delta": call.delta + put.delta,
        "gamma": call.gamma + put.gamma,
        "vega_1pct": call.vega_1pct + put.vega_1pct,
        "theta_day": call.theta_day + put.theta_day,
        "call_price": call.price,
        "put_price": put.price,
    }

def sigma_proxy_hv_vix(
    df_spy: pd.DataFrame,
    df_vix: pd.DataFrame,
    hv_window: int = 20,
    hv_annualization: int = 252,
    vix_weight: float = 0.6,
    sigma_floor: float = 0.05,
    sigma_cap: float = 2.00,
) -> pd.DataFrame:
    """
    Construye una sigma proxy dinámica:
      sigma = w*(VIX/100) + (1-w)*HV
    donde HV es vol histórica anualizada rolling (log-returns).
    VIX es % anualizado (~30 días) -> VIX/100.

    Devuelve df con columnas: close, hv, vix, sigma_proxy
    """
    if "datetime" not in df_spy.columns or "close" not in df_spy.columns:
        raise ValueError("df_spy necesita columnas: datetime, close")
    if "datetime" not in df_vix.columns or "vix_close" not in df_vix.columns:
        raise ValueError("df_vix necesita columnas: datetime, vix_close")

    spy = df_spy.copy()
    spy["datetime"] = pd.to_datetime(spy["datetime"]).dt.tz_localize(None)
    spy = spy.sort_values("datetime").set_index("datetime")

    vix = df_vix.copy()
    vix["datetime"] = pd.to_datetime(vix["datetime"]).dt.tz_localize(None)
    vix = vix.sort_values("datetime").set_index("datetime")

    # HV anualizada
    hv = hist_vol_close(spy["close"], window=hv_window, annualization=hv_annualization)
    spy["hv"] = hv

    # VIX -> sigma
    # VIX close suele venir en puntos (ej 18.5) => 0.185
    spy["vix"] = vix["vix_close"].reindex(spy.index).ffill()
    spy["sigma_vix"] = spy["vix"] / 100.0

    # Mezcla
    w = float(vix_weight)
    spy["sigma_proxy"] = w * spy["sigma_vix"] + (1.0 - w) * spy["hv"]

    # Limpieza (floor/cap para evitar valores raros o NaNs al inicio)
    spy["sigma_proxy"] = spy["sigma_proxy"].clip(lower=sigma_floor, upper=sigma_cap)

    return spy.reset_index()[["datetime", "close", "hv", "vix", "sigma_proxy"]]
