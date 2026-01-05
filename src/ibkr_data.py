# src/ibkr_data.py
# -*- coding: utf-8 -*-

from __future__ import annotations

# ======================================================
# FIX EVENT LOOP (CRÍTICO PARA ib_insync / eventkit)
# ======================================================
import asyncio
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# ======================================================
# Imports
# ======================================================
import math
from dataclasses import dataclass
from typing import Iterable, Tuple, Dict, Any

import pandas as pd
from ib_insync import IB, Stock, Option, Index, util


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
    use_market_data: bool = False

    # 1=live, 2=frozen, 3=delayed, 4=delayed-frozen
    market_data_type: int = 3

    # Filtrar warnings típicos de subscripción
    suppress_error_codes: tuple[int, ...] = (10089, 10091)


# =============================
# Main class
# =============================
class IBKRData:
    """
    Cliente IBKR robusto para backtest:
    - Históricos como fuente principal
    - Market data live opcional (desactivado por defecto)
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
            if errorCode in self.cfg.suppress_error_codes:
                return
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

    def index(self, symbol: str, exchange: str = "CBOE", currency: str = "USD") -> Index:
        idx = Index(symbol, exchange, currency)
        self.ib.qualifyContracts(idx)
        return idx

    # -------------------------
    # Historical bars (CORE)
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
        df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)
        df = df.sort_values("datetime").reset_index(drop=True)
        return df

    def last_close_from_history(self, contract, duration: str = "5 D", use_rth: bool = True) -> float:
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
        if not self.cfg.use_market_data:
            return self.last_close_from_history(contract)

        try:
            t = self.ib.reqMktData(contract, "", False, False)
            self.ib.sleep(1.5)
            if _is_finite_pos(getattr(t, "last", None)):
                return float(t.last)
            if _is_finite_pos(getattr(t, "close", None)):
                return float(t.close)
        except Exception:
            pass

        return self.last_close_from_history(contract)

    # -------------------------
    # VIX historical
    # -------------------------
    def historical_vix(
        self,
        duration: str = "10 Y",
        bar_size: str = "1 day",
        use_rth: bool = True
    ) -> pd.DataFrame:
        """
        Descarga histórico diario del VIX (CBOE).
        """
        vix = self.index("VIX", exchange="CBOE", currency="USD")
        df = self.historical_bars(
            vix,
            duration=duration,
            bar_size=bar_size,
            what="TRADES",
            use_rth=use_rth
        )

        if df.empty:
            return df

        df = df[["datetime", "close"]].copy()
        df = df.rename(columns={"close": "vix_close"})
        return df
