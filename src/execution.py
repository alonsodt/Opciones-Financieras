# src/execution.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Literal

import numpy as np

from src.pricing import bs_price_greeks


LegOrder = Literal["C_then_P", "P_then_C"]


@dataclass
class ExecutionParams:
    slippage_bps_combo: float = 1.0     # bps sobre el precio (1bp = 0.01%)
    slippage_bps_leg: float = 2.0       # más slippage por ir a patas
    leg_delay_seconds: float = 2.0
    n_sims: int = 5000
    seed: int = 123

    multiplier: int = 100
    contracts: int = 1

    # para convertir tiempo a años
    seconds_in_year: float = 365.0 * 24 * 60 * 60


def _apply_slippage(price: float, bps: float) -> float:
    return price * (1.0 + bps / 10000.0)


def price_straddle_combo(
    S: float, K: float, T: float, r: float, sigma: float, q: float,
    params: ExecutionParams
) -> Dict[str, float]:
    """
    Precio de ejecución del straddle como COMBO (sin legging).
    """
    call = bs_price_greeks(S, K, T, r, sigma, "C", q=q)
    put  = bs_price_greeks(S, K, T, r, sigma, "P", q=q)

    raw = (call.price + put.price)
    px = _apply_slippage(raw, params.slippage_bps_combo)

    total = px * params.contracts * params.multiplier
    return {
        "raw_straddle": raw,
        "exec_straddle": px,
        "total_cost": total
    }


def simulate_legging_cost(
    S: float, K: float, T: float, r: float, sigma: float, q: float,
    params: ExecutionParams,
    order: LegOrder = "C_then_P"
) -> Dict[str, float]:
    """
    Simula abrir el straddle por patas con un delay.
    Devuelve coste medio, percentiles y coste extra vs combo.
    """
    rng = np.random.default_rng(params.seed)

    dt_years = params.leg_delay_seconds / params.seconds_in_year

    # Movimiento del subyacente durante el delay (GBM approx en nivel, suficiente para práctica)
    dS = rng.normal(loc=0.0, scale=S * sigma * np.sqrt(dt_years), size=params.n_sims)
    S2 = S + dS

    # Precios pata 1 en S (antes del delay)
    call1 = bs_price_greeks(S, K, T, r, sigma, "C", q=q).price
    put1  = bs_price_greeks(S, K, T, r, sigma, "P", q=q).price

    # Precios pata 2 en S2 (después del delay)
    call2 = np.array([bs_price_greeks(float(s), K, T, r, sigma, "C", q=q).price for s in S2])
    put2  = np.array([bs_price_greeks(float(s), K, T, r, sigma, "P", q=q).price for s in S2])

    # Coste total por simulación
    if order == "C_then_P":
        raw_legs = call1 + put2
    else:
        raw_legs = put1 + call2

    exec_legs = _apply_slippage(raw_legs, params.slippage_bps_leg)

    # combo baseline
    combo = price_straddle_combo(S, K, T, r, sigma, q, params)
    combo_exec = combo["exec_straddle"]

    extra = exec_legs - combo_exec

    # multiplicadores
    total_exec_legs = exec_legs * params.contracts * params.multiplier
    total_extra = extra * params.contracts * params.multiplier

    def pct(x, p): return float(np.percentile(x, p))

    return {
        "combo_exec": float(combo_exec),
        "legs_exec_mean": float(np.mean(exec_legs)),
        "legging_extra_mean": float(np.mean(extra)),
        "legging_extra_p50": pct(extra, 50),
        "legging_extra_p90": pct(extra, 90),
        "legging_extra_p99": pct(extra, 99),

        "total_cost_legs_mean": float(np.mean(total_exec_legs)),
        "total_extra_mean": float(np.mean(total_extra)),
        "total_extra_p90": pct(total_extra, 90),
        "total_extra_p99": pct(total_extra, 99),
    }

