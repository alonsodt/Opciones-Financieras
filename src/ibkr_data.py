# src/ibkr_data.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Tuple, Dict, Any, Optional

import pandas as pd
from ib_insync import IB, Stock, Option, util


# =============================
# Helpers
# =============================
def ensure_ipython_loop() -> None:
    """En notebooks evita problemas con el event loop."""
    try:
        from IPython import get_ipython
        ip = get_ipython()
        if ip is not None and getattr(ip, "kernel", None) is not None:
            util.startLoop()
    except Exception:
        pass


def _is_finite_pos(x: Any) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x) and x > 0


def mid_price(ticker) -> float:
    """Mid = (bid+ask)/2 si existe; si no, last; si no, close; si no, NaN."""
    bid = getattr(ticker, "bid", None)
    ask = getattr(ticker, "ask", None)
    if _is_finite_pos(bid) and _is_finite_pos(ask):
        return 0.5 * (float(bid) + float(ask))

    last = getattr(ticker, "last", None)
    if _is_finite_pos(last):
        return float(last)

    close = getattr(ticker, "close", None)
    if _is_finite_pos(close):
        return float(close)

    return float("nan")


# =============================
# Config
# =============================
@dataclass
class IBKRConfig:
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1
    readonly: bool = False
    timeout: int = 10

    # Para BACKTEST: ponlo en False (por defecto).
    # Si lo pones True, se harán reqMktData y pueden aparecer 10089/10091 sin subs.
    use_market_data: bool = False

    # Market data type: 1=live, 2=frozen, 3=delayed, 4=delayed-frozen
    market_data_type: int = 3

    # Filtrar warnings típicos de subscripción
    suppress_error_codes: tuple[int, ...] = (10089, 10091)


# =============================
# Main class
# =============================
class IBKRData:
    """
    Cliente IBKR robusto para backtest:
    - Históricos (reqHistoricalData) como fuente principal (sin depender de subscripciones)
    - Option chain (reqSecDefOptParams) + qualifyContracts
    - Market data (reqMktData) opcional (desactivado por defecto)
    """

    def __init__(self, cfg: IBKRConfig):
        self.cfg = cfg
        self.ib = IB()
        self._error_handler_installed = False

    # -------------------------
    # Connection + error filter
    # -------------------------
    def _install_error_filter(self) -> None:
        if self._error_handler_installed:
            return

        def on_error(reqId, errorCode, errorString, contract):
            # Silencia mensajes de subscripción típicos
            if errorCode in self.cfg.suppress_error_codes:
                return
            # Si no está filtrado, lo imprimimos
            print(f"IBKR Error {errorCode}, reqId {reqId}: {errorString}, contract: {contract}")

        self.ib.errorEvent += on_error
        self._error_handler_installed = True

    def connect(self) -> None:
        ensure_ipython_loop()

        if self.ib.isConnected():
            self.ib.disconnect()

        self.ib.connect(
            self.cfg.host,
            self.cfg.port,
            clientId=self.cfg.client_id,
            timeout=self.cfg.timeout,
            readonly=self.cfg.readonly
        )

        self._install_error_filter()

        # Solo relevante si use_market_data=True
        self.ib.reqMarketDataType(self.cfg.market_data_type)

    def disconnect(self) -> None:
        if self.ib.isConnected():
            self.ib.disconnect()

    # -------------------------
    # Contracts
    # -------------------------
    def stock(self, symbol: str, exchange: str = "SMART", currency: str = "USD") -> Stock:
        stk = Stock(symbol, exchange, currency)
        self.ib.qualifyContracts(stk)
        return stk

    # -------------------------
    # Historical bars (core)
    # -------------------------
    def historical_bars(
        self,
        contract,
        end: str = "",
        duration: str = "10 Y",
        bar_size: str = "1 day",
        what: str = "TRADES",
        use_rth: bool = True
    ) -> pd.DataFrame:
        bars = self.ib.reqHistoricalData(
            contract,
            endDateTime=end,
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=what,
            useRTH=use_rth,
            formatDate=1,
            keepUpToDate=False
        )
        df = util.df(bars)
        if df.empty:
            return df

        df = df.rename(columns={"date": "datetime"})
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)
        return df

    def last_close_from_history(
        self,
        contract,
        duration: str = "5 D",
        use_rth: bool = True
    ) -> float:
        bars = self.ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=use_rth,
            formatDate=1,
            keepUpToDate=False
        )
        if not bars:
            return float("nan")
        return float(bars[-1].close)

    def reference_price(self, contract) -> float:
        """
        Para BACKTEST: SOLO históricos (evita reqMktData => evita 10089/10091).
        Si en algún momento quieres live/delayed, activa cfg.use_market_data=True.
        """
        if not self.cfg.use_market_data:
            return self.last_close_from_history(contract)

        # Si lo activas, intentamos mktData pero sin romper si no hay datos.
        try:
            t = self.ib.reqMktData(contract, "", False, False)
            self.ib.sleep(1.5)
            last = getattr(t, "last", None)
            if _is_finite_pos(last):
                return float(last)
            close = getattr(t, "close", None)
            if _is_finite_pos(close):
                return float(close)
        except Exception:
            pass

        return self.last_close_from_history(contract)

    # -------------------------
    # Option chain
    # -------------------------
    def option_chain_params(self, symbol: str, exchange: str = "SMART", currency: str = "USD"):
        stk = self.stock(symbol, exchange=exchange, currency=currency)
        chains = self.ib.reqSecDefOptParams(stk.symbol, "", stk.secType, stk.conId)
        if not chains:
            raise RuntimeError("reqSecDefOptParams devolvió vacío. Revisa permisos/contrato.")

        best = sorted(
            chains,
            key=lambda c: (len(getattr(c, "expirations", [])), len(getattr(c, "strikes", []))),
            reverse=True
        )[0]
        return best

    def pick_expiry_near_days(self, expirations: Iterable[str], target_days: int = 30) -> str:
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
            raise RuntimeError("No se pudo seleccionar expiración.")
        return best_exp

    def find_valid_atm_straddle(
        self,
        symbol: str,
        expiry: str,
        strikes: Iterable[float],
        trading_class: str,
        multiplier: str,
        exchange: str = "SMART",
        currency: str = "USD",
        tries: int = 25
    ) -> Tuple[float, Option, Option]:
        stk = self.stock(symbol, exchange=exchange, currency=currency)
        S = self.reference_price(stk)
        if not _is_finite_pos(S):
            raise RuntimeError("No se pudo obtener spot/ref price del subyacente.")

        sorted_strikes = sorted(strikes, key=lambda k: abs(float(k) - S))[:tries]

        for K in sorted_strikes:
            K = float(K)
            c = Option(symbol, expiry, K, "C", exchange, currency=currency,
                       multiplier=str(multiplier), tradingClass=trading_class)
            p = Option(symbol, expiry, K, "P", exchange, currency=currency,
                       multiplier=str(multiplier), tradingClass=trading_class)

            self.ib.qualifyContracts(c, p)

            if getattr(c, "conId", 0) not in (0, None) and getattr(p, "conId", 0) not in (0, None):
                return K, c, p

        raise RuntimeError(f"No se encontró strike ATM válido para expiry={expiry} probando {tries} strikes.")

    # -------------------------
    # Option snapshot (optional)
    # -------------------------
    def option_snapshot_light(self, opt: Option, sleep_s: float = 1.5) -> Dict[str, Any]:
        """
        Snapshot ligero SOLO si cfg.use_market_data=True.
        Si está False, devuelve NaNs (para que no intentes usarlo en backtest).
        """
        self.ib.qualifyContracts(opt)

        if not self.cfg.use_market_data:
            return {
                "localSymbol": getattr(opt, "localSymbol", None),
                "conId": getattr(opt, "conId", None),
                "bid": float("nan"),
                "ask": float("nan"),
                "last": float("nan"),
                "close": float("nan"),
                "mid": float("nan"),
            }

        t = self.ib.reqMktData(opt, "", False, False)
        self.ib.sleep(sleep_s)

        return {
            "localSymbol": getattr(opt, "localSymbol", None),
            "conId": getattr(opt, "conId", None),
            "bid": getattr(t, "bid", float("nan")),
            "ask": getattr(t, "ask", float("nan")),
            "last": getattr(t, "last", float("nan")),
            "close": getattr(t, "close", float("nan")),
            "mid": mid_price(t),
        }


# =============================
# Manual smoke test
# =============================
if __name__ == "__main__":
    # IMPORTANTE: para evitar 10089/10091 en consola, deja use_market_data=False
    cfg = IBKRConfig(host="127.0.0.1", port=7497, client_id=28, use_market_data=False)
    ibd = IBKRData(cfg)

    try:
        ibd.connect()

        spy = ibd.stock("SPY")
        px = ibd.reference_price(spy)
        print("SPY ref price (history-based):", px)

        chain = ibd.option_chain_params("SPY")
        expiry = ibd.pick_expiry_near_days(chain.expirations, target_days=30)

        K, c, p = ibd.find_valid_atm_straddle(
            symbol="SPY",
            expiry=expiry,
            strikes=chain.strikes,
            trading_class=chain.tradingClass,
            multiplier=chain.multiplier
        )
        print("Expiry:", expiry, "K:", K, "Call:", c.localSymbol, "Put:", p.localSymbol)

        # Snapshot solo si lo activas (si no, devuelve NaNs sin pedir market data)
        print("Call snapshot:", ibd.option_snapshot_light(c))
        print("Put snapshot:", ibd.option_snapshot_light(p))

        df = ibd.historical_bars(spy, duration="2 Y", bar_size="1 day")
        print("Hist bars tail:\n", df.tail(3))

    finally:
        ibd.disconnect()
