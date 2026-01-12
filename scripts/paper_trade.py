# scripts/paper_trade.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import sys
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
try:
    asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from dataclasses import dataclass
import argparse
import math
import time
from typing import Optional, Tuple, Dict

from ib_insync import (
    IB, Stock, Option, util,
    Contract, Bag, ComboLeg,
    LimitOrder, MarketOrder
)

# -------------------------
# Config
# -------------------------
@dataclass
class PaperConfig:
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 77

    symbol: str = "SPY"
    currency: str = "USD"
    exchange: str = "SMART"
    primary_exchange: str = "ARCA"

    target_days: int = 30
    qty: int = 1
    wait_fill_s: int = 20

    # market data type: 1=live, 2=frozen, 3=delayed, 4=delayed-frozen
    market_data_type: int = 3

# -------------------------
# Utils
# -------------------------
def _is_finite(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)

def norm_cdf(x: float) -> float:
    # CDF normal estándar vía erf (sin dependencias)
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def bs_call_put(S: float, K: float, T: float, r: float, q: float, sigma: float) -> Tuple[float, float]:
    """
    Black-Scholes con dividend yield continuo q.
    Devuelve (call, put).
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return float("nan"), float("nan")

    sqt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / sqt
    d2 = d1 - sqt

    disc_r = math.exp(-r * T)
    disc_q = math.exp(-q * T)

    call = S * disc_q * norm_cdf(d1) - K * disc_r * norm_cdf(d2)
    put  = K * disc_r * norm_cdf(-d2) - S * disc_q * norm_cdf(-d1)
    return float(call), float(put)

def years_from_days(days: int) -> float:
    # año ACT/365
    return max(1e-6, float(days) / 365.0)

# -------------------------
# Selección de expiry/strike (simple)
# -------------------------
def pick_expiry_near_days(expirations, target_days: int) -> str:
    import datetime as dt
    today = dt.date.today()
    best_exp = None
    best_diff = 10**9
    for e in expirations:
        try:
            d = dt.datetime.strptime(e, "%Y%m%d").date()
        except Exception:
            continue
        diff = abs((d - today).days - target_days)
        if diff < best_diff:
            best_diff = diff
            best_exp = e
    if best_exp is None:
        raise RuntimeError("No se pudo seleccionar expiración cercana.")
    return best_exp

def round_to_strike(S: float, strikes) -> float:
    s = float(S)
    strikes_sorted = sorted([float(k) for k in strikes], key=lambda k: abs(k - s))
    return strikes_sorted[0]

# -------------------------
# Construcción de contratos
# -------------------------
def qualify_spy_and_options(ib: IB, cfg: PaperConfig, S_ref: float) -> Tuple[Stock, str, float, Option, Option]:
    spy = Stock(cfg.symbol, cfg.exchange, cfg.currency, primaryExchange=cfg.primary_exchange)
    ib.qualifyContracts(spy)

    chains = ib.reqSecDefOptParams(spy.symbol, "", spy.secType, spy.conId)
    if not chains:
        raise RuntimeError("reqSecDefOptParams devolvió vacío.")
    chain = sorted(chains, key=lambda c: (len(c.expirations), len(c.strikes)), reverse=True)[0]

    expiry = pick_expiry_near_days(chain.expirations, cfg.target_days)
    K = round_to_strike(S_ref, chain.strikes)

    call = Option(cfg.symbol, expiry, K, "C", cfg.exchange, currency=cfg.currency,
                  multiplier=str(chain.multiplier), tradingClass=chain.tradingClass)
    put  = Option(cfg.symbol, expiry, K, "P", cfg.exchange, currency=cfg.currency,
                  multiplier=str(chain.multiplier), tradingClass=chain.tradingClass)

    ib.qualifyContracts(call, put)
    return spy, expiry, float(K), call, put

def build_straddle_bag(symbol: str, currency: str, exchange: str, call: Option, put: Option) -> Bag:
    bag = Bag()
    bag.symbol = symbol
    bag.secType = "BAG"
    bag.currency = currency
    bag.exchange = exchange
    leg_c = ComboLeg(conId=call.conId, ratio=1, action="BUY", exchange=exchange)
    leg_p = ComboLeg(conId=put.conId, ratio=1, action="BUY", exchange=exchange)
    bag.comboLegs = [leg_c, leg_p]
    return bag

# -------------------------
# Ejecución
# -------------------------
def place_and_wait(ib: IB, contract: Contract, order, timeout_s: int, dry_run: bool):
    if dry_run:
        print(f"[DRY-RUN] Would place order: {order} on {contract}")
        return None

    trade = ib.placeOrder(contract, order)
    t0 = time.time()

    while time.time() - t0 < timeout_s:
        ib.sleep(0.5)
        status = trade.orderStatus.status
        if status in ("Filled", "Cancelled", "Inactive"):
            break

    status = trade.orderStatus.status
    filled = trade.orderStatus.filled
    avg_fill = trade.orderStatus.avgFillPrice

    if status != "Filled":
        try:
            ib.cancelOrder(order)
            ib.sleep(0.5)
        except Exception:
            pass

    return {"status": status, "filled": filled, "avgFillPrice": avg_fill, "permId": trade.order.permId}

# -------------------------
# Inputs de precio (Opción 3)
# -------------------------
def load_inputs_csv(path: str) -> Dict[str, float]:
    """
    CSV mínimo esperado con cabecera:
    S0,iv,r,q
    694.5,0.18,0.05,0.012
    """
    import csv
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        row = next(reader)
    out = {}
    for k in ("S0", "iv", "r", "q"):
        if k in row and row[k] not in (None, ""):
            out[k] = float(row[k])
    return out

# -------------------------
# Main
# -------------------------
def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--send", action="store_true", help="Envía órdenes (si no, DRY-RUN).")
    parser.add_argument("--mode", choices=["combo", "legs", "both"], default="both")
    parser.add_argument("--order-type", choices=["LMT", "MKT"], default="LMT")
    parser.add_argument("--qty", type=int, default=1)
    parser.add_argument("--wait", type=int, default=20)

    # NUEVO: fuente de precios
    parser.add_argument("--price-source", choices=["bs", "csv", "ibkr"], default="bs",
                        help="bs=Black-Scholes (sin market data), csv=leer inputs, ibkr=usar mkt data/hist.")
    parser.add_argument("--csv-path", type=str, default="", help="Ruta CSV si --price-source=csv")

    # Parámetros BS / ejecución
    parser.add_argument("--S0", type=float, default=float("nan"), help="Spot (si bs y no csv).")
    parser.add_argument("--iv", type=float, default=0.20, help="Vol implícita (BS) ej 0.20")
    parser.add_argument("--r", type=float, default=0.05, help="Tipo libre de riesgo anual continuo aprox")
    parser.add_argument("--q", type=float, default=0.012, help="Dividend yield anual continuo aprox")
    parser.add_argument("--slip", type=float, default=0.03, help="Slippage/spread relativo para LMT (3% = 0.03)")

    args = parser.parse_args()

    cfg = PaperConfig(qty=args.qty, wait_fill_s=args.wait)
    dry_run = (not args.send)

    print("\n==============================")
    print(" PAPER TRADE STRADDLE (DEMO) ")
    print("==============================")
    print("DRY-RUN:", dry_run)
    print("MODE   :", args.mode)
    print("ORDER  :", args.order_type)
    print("PRICE  :", args.price_source)
    print()

    ib = IB()
    util.startLoop()
    ib.connect(cfg.host, cfg.port, clientId=cfg.client_id, timeout=10, readonly=False)
    ib.reqMarketDataType(cfg.market_data_type)  # delayed por defecto (si luego quieres ibkr)

    try:
        # 1) Construir inputs de pricing (sin depender de market live)
        S0 = args.S0
        iv = float(args.iv)
        r  = float(args.r)
        q  = float(args.q)

        if args.price_source == "csv":
            if not args.csv_path:
                raise RuntimeError("Falta --csv-path para --price-source=csv")
            d = load_inputs_csv(args.csv_path)
            S0 = d.get("S0", S0)
            iv = d.get("iv", iv)
            r  = d.get("r",  r)
            q  = d.get("q",  q)

        if args.price_source in ("bs", "csv"):
            if not _is_finite(S0) or S0 <= 0:
                raise RuntimeError("En modo bs/csv necesitas S0 válido (usa --S0 o --csv-path).")

        # 2) Contratos: usamos S0 como referencia para elegir strike cercano
        S_ref = float(S0) if args.price_source in ("bs", "csv") else float("nan")
        if args.price_source == "ibkr":
            # en ibkr, podrías pedir un snapshot/delayed; pero no lo recomiendo si quieres independencia.
            # Aun así, para no romper, pedimos un histórico simple del subyacente.
            # Si no quieres NADA de IBKR data, no uses 'ibkr'.
            bars = ib.reqHistoricalData(
                Stock(cfg.symbol, cfg.exchange, cfg.currency, primaryExchange=cfg.primary_exchange),
                endDateTime="", durationStr="5 D", barSizeSetting="1 day",
                whatToShow="TRADES", useRTH=True, formatDate=1, keepUpToDate=False
            )
            if not bars:
                raise RuntimeError("No pude obtener S0 via histórico IBKR.")
            S_ref = float(bars[-1].close)
            S0 = S_ref

        spy, expiry, K, call, put = qualify_spy_and_options(ib, cfg, S_ref)
        print(f"Selected: SPY {expiry} K={K}")
        print("CALL:", call.localSymbol, "conId:", call.conId)
        print("PUT :", put.localSymbol,  "conId:", put.conId)
        print("Underlying S0 (ref):", S0)

        # 3) Pricing teórico BS (para LMT si no hay mkt data)
        T = years_from_days(cfg.target_days)
        theo_c, theo_p = bs_call_put(float(S0), float(K), float(T), float(r), float(q), float(iv))
        if not (_is_finite(theo_c) and _is_finite(theo_p)):
            raise RuntimeError("BS devolvió NaN (revisa S0,K,T,iv,r,q).")

        theo_combo = theo_c + theo_p
        # slippage: para BUY ponemos un poquito por encima del teórico
        lmt_combo = round(theo_combo * (1.0 + args.slip), 2)
        lmt_call  = round(theo_c * (1.0 + args.slip), 2)
        lmt_put   = round(theo_p * (1.0 + args.slip), 2)

        print(f"Theo BS: call={theo_c:.2f} put={theo_p:.2f} combo={theo_combo:.2f} (iv={iv:.2%}, r={r:.2%}, q={q:.2%}, T~{T:.3f}y)")
        print(f"LMT BS : call={lmt_call:.2f} put={lmt_put:.2f} combo={lmt_combo:.2f} (slip={args.slip:.2%})")

        # --- COMBO ---
        if args.mode in ("combo", "both"):
            bag = build_straddle_bag(cfg.symbol, cfg.currency, cfg.exchange, call, put)

            if args.order_type == "MKT":
                order = MarketOrder("BUY", cfg.qty)
                print("\n[COMBO] MarketOrder BUY", cfg.qty)
            else:
                order = LimitOrder("BUY", cfg.qty, lmt_combo)
                print("\n[COMBO] LimitOrder BUY", cfg.qty, "LMT=", order.lmtPrice)

            res_combo = place_and_wait(ib, bag, order, cfg.wait_fill_s, dry_run)
            print("[COMBO] Result:", res_combo)

        # --- LEGS ---
        if args.mode in ("legs", "both"):
            if args.order_type == "MKT":
                oc = MarketOrder("BUY", cfg.qty)
                op = MarketOrder("BUY", cfg.qty)
            else:
                oc = LimitOrder("BUY", cfg.qty, lmt_call)
                op = LimitOrder("BUY", cfg.qty, lmt_put)

            print("\n[LEGS] First: CALL", "order=", oc)
            t_call = time.time()
            res_call = place_and_wait(ib, call, oc, cfg.wait_fill_s, dry_run)
            print("[LEGS] CALL result:", res_call)

            ib.sleep(2.0)

            print("\n[LEGS] Second: PUT", "order=", op)
            t_put = time.time()
            res_put = place_and_wait(ib, put, op, cfg.wait_fill_s, dry_run)
            print("[LEGS] PUT result:", res_put)

            print("\n[LEGS] Timing:")
            print(" - t(CALL):", round(t_call, 2))
            print(" - t(PUT) :", round(t_put, 2))
            print(" - Δt (s) :", round(t_put - t_call, 2))
            print("\n[LEGS] Nota: con price-source=bs/csv el análisis de legging es por simulación (no por quotes live).")

        print("\n✅ Done.")

    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    main()

