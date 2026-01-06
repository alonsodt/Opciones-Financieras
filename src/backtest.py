# src/backtest.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Dict, Any

import numpy as np

from src.pricing import bs_price_greeks, straddle_greeks


Right = Literal["C", "P"]


@dataclass
class DeltaNeutralOptionHedgeResult:
    n_hedge: float
    base: Dict[str, float]
    hedge: Dict[str, float]
    total: Dict[str, float]


def _scale_greeks(g: Dict[str, float], factor: float) -> Dict[str, float]:
    return {k: float(v) * factor for k, v in g.items()}


def delta_neutral_with_option(
    S: float,
    K_straddle: float,
    K_hedge: float,
    T: float,
    r: float,
    sigma: float,
    q: float = 0.0,
    hedge_right: Right = "C",
    days_in_year: int = 365
) -> DeltaNeutralOptionHedgeResult:
    """
    Neutraliza delta del straddle usando OTRA opción (call o put).
    Devuelve n (cantidad de hedge option) y el impacto en Gamma/Vega/Theta.
    Todo en unidades "por 1 acción" (sin multiplicador ni contratos).
    """

    # Base: straddle
    base = straddle_greeks(S, K_straddle, T, r, sigma, q=q, days_in_year=days_in_year)

    # Hedge option
    h = bs_price_greeks(S, K_hedge, T, r, sigma, hedge_right, q=q, days_in_year=days_in_year)
    hedge = {
        "price": h.price,
        "delta": h.delta,
        "gamma": h.gamma,
        "vega_1pct": h.vega_1pct,
        "theta_day": h.theta_day,
    }

    # n para delta-neutral: base_delta + n*hedge_delta = 0
    if abs(hedge["delta"]) < 1e-8:
        raise ValueError("Delta de la opción hedge ~0; no se puede neutralizar delta con esta opción.")

    n = - base["delta"] / hedge["delta"]

    total = {
        "price": base["price"] + n * hedge["price"],
        "delta": base["delta"] + n * hedge["delta"],
        "gamma": base["gamma"] + n * hedge["gamma"],
        "vega_1pct": base["vega_1pct"] + n * hedge["vega_1pct"],
        "theta_day": base["theta_day"] + n * hedge["theta_day"],
    }

    return DeltaNeutralOptionHedgeResult(
        n_hedge=float(n),
        base=base,
        hedge=hedge,
        total=total
    )


def describe_implications(res: DeltaNeutralOptionHedgeResult) -> Dict[str, Any]:
    """
    Devuelve un resumen interpretativo simple (sin texto largo).
    """
    base = res.base
    total = res.total

    def pct_change(a, b):
        # cambio relativo de base->total
        if abs(a) < 1e-12:
            return np.nan
        return (b / a) - 1.0

    return {
        "n_hedge": res.n_hedge,
        "delta_total": total["delta"],
        "gamma_change_vs_base": pct_change(base["gamma"], total["gamma"]),
        "vega_change_vs_base": pct_change(base["vega_1pct"], total["vega_1pct"]),
        "theta_change_vs_base": pct_change(base["theta_day"], total["theta_day"]),
    }

