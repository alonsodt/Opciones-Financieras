# scripts/paper_trade_straddle.py
# -*- coding: utf-8 -*-

"""
Paper trading (demo) de un Long Straddle en SPY:
- Envío como COMBO (BAG)
- Envío como LEGS (call y put por separado)
- Modo seguro por defecto: DRY-RUN (no envía)
- Para enviar: añadir flag --send

Requisitos:
- TWS abierto + API activa
- Cuenta demo/paper (recomendado)
"""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from ib_insync import IB, Stock, Option, util, Contract, Bag, ComboLeg, LimitOrder, MarketOrder


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
    qty: int = 1                 # contratos (1 = 1 call + 1 put)
    limit_buffer: float = 0.10   # dólares de colchón para limit (si no hay bid/ask)
    wait_fill_s: int = 20        # cuánto esperar fill antes de cancelar

    # market data type: 1=live, 2=frozen, 3=delayed, 4=delayed-frozen
    market_data_type: int = 3


# -------------------------
# Helpers de precio
# -------------------------
def _is_finite(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)


def mid_from_ticker(t) -> Optional[float]:
    bid = getattr(t, "bid", None)
    ask = getattr(t, "ask", None)
    if _is_finite(bid) and _is_finite(ask) and bid > 0 and ask > 0:
        return 0.5 * (float(bid) + float(ask))
    last = getattr(t, "last", None)
    if _is_finite(last) and last > 0:
        return float(last)
    close = getattr(t, "close", None)
    if _is_finite(close) and close > 0:
        return float(close)
    return None


def last_close_from_history(ib: IB, contract: Contract) -> float:
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr="5 D",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
        keepUpToDate=False,
    )
    if not bars:
        return float("nan")
    return float(bars[-1].close)


# -------------------------
# Selección de expiry/strike (muy simple)
# -------------------------
def pick_expiry_near_days(expirations, target_days: int) -> str:
    # expirations viene en formato 'YYYYMMDD'
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
    # elige strike más cercano a spot
    s = float(S)
    strikes_sorted = sorted([float(k) for k in strikes], key=lambda k: abs(k - s))
    return strikes_sorted[0]


# -------------------------
# Construcción de contratos
# -------------------------
def qualify_spy_and_options(ib: IB, cfg: PaperConfig) -> Tuple[Stock, str, float, Option, Option]:
    # Subyacente
    spy = Stock(cfg.symbol, cfg.exchange, cfg.currency, primaryExchange=cfg.primary_exchange)
    ib.qualifyContracts(spy)

    # Precio referencia (intentamos mktData, si no, histórico)
    t_spy = ib.reqMktData(spy, "", False, False)
    ib.sleep(1.0)
    S = mid_from_ticker(t_spy)
    if S is None:
        S = last_close_from_history(ib, spy)

    if not _is_finite(S) or S <= 0:
        raise RuntimeError("No pude obtener spot/ref price para SPY.")

    # Option chain
    chains = ib.reqSecDefOptParams(spy.symbol, "", spy.secType, spy.conId)
    if not chains:
        raise RuntimeError("reqSecDefOptParams devolvió vacío.")
    chain = sorted(chains, key=lambda c: (len(c.expirations), len(c.strikes)), reverse=True)[0]

    expiry = pick_expiry_near_days(chain.expirations, cfg.target_days)
    K = round_to_strike(S, chain.strikes)

    call = Option(cfg.symbol, expiry, K, "C", cfg.exchange, currency=cfg.currency, multiplier=str(chain.multiplier), tradingClass=chain.tradingClass)
    put  = Option(cfg.symbol, expiry, K, "P", cfg.exchange, currency=cfg.currency, multiplier=str(chain.multiplier), tradingClass=chain.tradingClass)

    ib.qualifyContracts(call, put)

    return spy, expiry, float(K), call, put


def build_straddle_bag(symbol: str, currency: str, exchange: str, call: Option, put: Option) -> Bag:
    """
    Construye un BAG (combo) con 1 call + 1 put (ambas BUY).
    """
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
# Envío / control fills
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
        # cancel si no ha llenado
        try:
            ib.cancelOrder(order)
            ib.sleep(0.5)
        except Exception:
            pass

    return {
        "status": status,
        "filled": filled,
        "avgFillPrice": avg_fill,
        "permId": trade.order.permId,
    }


def get_underlying_snapshot(ib: IB, spy: Stock) -> Optional[float]:
    t = ib.reqMktData(spy, "", False, False)
    ib.sleep(1.0)
    return mid_from_ticker(t)


def estimate_combo_limit(ib: IB, call: Option, put: Option, fallback_buffer: float) -> float:
    """
    Intenta estimar un precio límite para el combo:
    - mid(call)+mid(put) si hay datos
    - si no hay datos, usa close histórico y añade un buffer
    """
    tc = ib.reqMktData(call, "", False, False)
    tp = ib.reqMktData(put, "", False, False)
    ib.sleep(1.0)

    mc = mid_from_ticker(tc)
    mp = mid_from_ticker(tp)
    if mc is not None and mp is not None:
        return float(mc + mp)

    # fallback: histórico close (muy aproximado)
    c_close = last_close_from_history(ib, call)
    p_close = last_close_from_history(ib, put)
    base = 0.0
    if _is_finite(c_close) and c_close > 0:
        base += float(c_close)
    if _is_finite(p_close) and p_close > 0:
        base += float(p_close)

    if base <= 0:
        # último recurso: buffer mínimo
        base = 1.0

    return float(base + fallback_buffer)


# -------------------------
# Main
# -------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Si se incluye, envía órdenes de verdad. Si no, DRY-RUN.")
    parser.add_argument("--mode", choices=["combo", "legs", "both"], default="both", help="Tipo de ejecución.")
    parser.add_argument("--order-type", choices=["LMT", "MKT"], default="LMT", help="Tipo de orden.")
    parser.add_argument("--qty", type=int, default=1, help="Nº de straddles (1=1 call + 1 put).")
    parser.add_argument("--wait", type=int, default=20, help="Segundos máximos esperando fill.")
    args = parser.parse_args()

    cfg = PaperConfig(qty=args.qty, wait_fill_s=args.wait)
    dry_run = (not args.send)

    print("\n==============================")
    print(" PAPER TRADE STRADDLE (DEMO) ")
    print("==============================")
    print("DRY-RUN:", dry_run)
    print("MODE   :", args.mode)
    print("ORDER  :", args.order_type)
    print()

    ib = IB()
    util.startLoop()  # por si lo ejecutas en entorno tipo IPython (no molesta en .py)

    ib.connect(cfg.host, cfg.port, clientId=cfg.client_id, timeout=10, readonly=False)
    ib.reqMarketDataType(cfg.market_data_type)

    try:
        spy, expiry, K, call, put = qualify_spy_and_options(ib, cfg)
        print(f"Selected: SPY {expiry} K={K}")
        print("CALL:", call.localSymbol, "conId:", call.conId)
        print("PUT :", put.localSymbol,  "conId:", put.conId)

        # Snapshot antes
        S0 = get_underlying_snapshot(ib, spy)
        if S0 is None:
            S0 = last_close_from_history(ib, spy)
        print("Underlying snapshot S0:", S0)

        # --- COMBO ---
        if args.mode in ("combo", "both"):
            bag = build_straddle_bag(cfg.symbol, cfg.currency, cfg.exchange, call, put)

            if args.order_type == "MKT":
                order = MarketOrder("BUY", cfg.qty)
                print("\n[COMBO] MarketOrder BUY", cfg.qty)
            else:
                limit_px = estimate_combo_limit(ib, call, put, cfg.limit_buffer)
                # Para comprar, ponemos límite un poco más alto para aumentar prob. fill
                order = LimitOrder("BUY", cfg.qty, round(limit_px + cfg.limit_buffer, 2))
                print("\n[COMBO] LimitOrder BUY", cfg.qty, "LMT=", order.lmtPrice)

            res_combo = place_and_wait(ib, bag, order, cfg.wait_fill_s, dry_run)
            print("[COMBO] Result:", res_combo)

        # --- LEGS ---
        if args.mode in ("legs", "both"):
            # Orden por patas: primero call, luego put (simple y defendible)
            if args.order_type == "MKT":
                oc = MarketOrder("BUY", cfg.qty)
                op = MarketOrder("BUY", cfg.qty)
            else:
                # Intentamos mid por pata; si no, histórico + buffer
                tc = ib.reqMktData(call, "", False, False); ib.sleep(0.7)
                tp = ib.reqMktData(put,  "", False, False); ib.sleep(0.7)
                mc = mid_from_ticker(tc) or (last_close_from_history(ib, call) + cfg.limit_buffer)
                mp = mid_from_ticker(tp) or (last_close_from_history(ib, put)  + cfg.limit_buffer)
                oc = LimitOrder("BUY", cfg.qty, round(float(mc) + cfg.limit_buffer, 2))
                op = LimitOrder("BUY", cfg.qty, round(float(mp) + cfg.limit_buffer, 2))

            print("\n[LEGS] First: CALL", "order=", oc)
            S_call = get_underlying_snapshot(ib, spy) or last_close_from_history(ib, spy)
            t_call = time.time()
            res_call = place_and_wait(ib, call, oc, cfg.wait_fill_s, dry_run)
            print("[LEGS] CALL result:", res_call)

            # delay para enfatizar legging (puedes bajarlo si quieres)
            ib.sleep(2.0)

            print("\n[LEGS] Second: PUT", "order=", op)
            S_put = get_underlying_snapshot(ib, spy) or last_close_from_history(ib, spy)
            t_put = time.time()
            res_put = place_and_wait(ib, put, op, cfg.wait_fill_s, dry_run)
            print("[LEGS] PUT result:", res_put)

            # Medición legging en vivo
            print("\n[LEGS] Underlying snapshots:")
            print(" - S at CALL:", S_call, "t=", round(t_call, 2))
            print(" - S at PUT :", S_put,  "t=", round(t_put, 2))
            if _is_finite(S_call) and _is_finite(S_put):
                print(" - ΔS:", float(S_put) - float(S_call))

            print("\n[LEGS] Nota: esta medición es *real-time* y no sustituye al análisis histórico.")
            print("      Para la práctica, el riesgo de legging se analiza con la simulación (outputs/results/execution_legging_summary.csv).")

        print("\n✅ Done.")

    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
