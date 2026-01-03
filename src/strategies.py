@dataclass
class StraddlePosition:
    entry_date: pd.Timestamp
    expiry: pd.Timestamp
    K: float
    entry_spot: float
    sigma_entry: float
    r_entry: float
    q_entry: float
    call_entry_price: float
    put_entry_price: float
    contracts: int = 1  # 1 contrato (multiplicador 100)

    @property
    def premium_paid(self):
        return (self.call_entry_price + self.put_entry_price) * 100 * self.contracts


def build_monthly_straddles(spy_df, r_series, target_days=30, rule="M",
                            use_chain_iv_on_entry=True, realized_vol_window=20):
    """
    Construye una lista de straddles con roll periódico.
    - En cada fecha de entrada: elige vencimiento ~30 días y strike ATM.
    - sigma_entry: IV del chain (si disponible) o realized vol (fallback).
    - precios de entrada: mid de call/put ATM (si hay chain); si no, BS con sigma_entry.
    """
    ticker = yf.Ticker("SPY")
    q = get_dividend_yield_proxy(spy_df)

    entry_dates = pick_monthly_entry_dates(spy_df, rule=rule)
    rv = realized_vol(spy_df["adj_close"], window=realized_vol_window)

    positions = []

    for d in entry_dates:
        if d not in spy_df.index:
            continue
        spot = float(spy_df.loc[d, "adj_close"])
        r = float(r_series.reindex(spy_df.index).ffill().loc[d]) if d in r_series.index or True else 0.04

        # Intentar chain para obtener expiry/strikes/IV
        expiry_str = None
        call_mid = put_mid = None
        K = None
        sigma_entry = np.nan

        try:
            expiries = ticker.options
            expiry_str = choose_expiry_from_chain(expiries, target_days=target_days)
            if expiry_str is None:
                raise ValueError("Sin expiries")
            chain = ticker.option_chain(expiry_str)
            calls = chain.calls.copy()
            puts = chain.puts.copy()

            K = get_atm_strike_from_chain(calls, spot)

            call_row = calls.loc[calls["strike"].astype(float) == K].iloc[0]
            put_row = puts.loc[puts["strike"].astype(float) == K].iloc[0]

            call_mid = get_mid_price(call_row)
            put_mid = get_mid_price(put_row)

            if use_chain_iv_on_entry:
                iv_call = get_iv_from_chain_row(call_row)
                iv_put = get_iv_from_chain_row(put_row)
                sigma_entry = np.nanmean([iv_call, iv_put])

        except Exception:
            # si Yahoo falla ese día: no hay chain fiable => usaremos BS
            expiry_str = None

        # fallback de sigma
        if not np.isfinite(sigma_entry) or sigma_entry <= 0:
            sigma_entry = float(rv.loc[d]) if np.isfinite(rv.loc[d]) else 0.20

        # fallback de expiry si no hay chain
        if expiry_str is None:
            expiry = (d + pd.Timedelta(days=target_days))
        else:
            expiry = pd.to_datetime(expiry_str)

        # tiempo en años desde entry hasta expiry
        T = max((expiry - d).days / 365.0, 1/365)

        # si no tenemos precios del chain, valoramos con BS en entry
        if (call_mid is None) or (put_mid is None) or (call_mid == 0) or (put_mid == 0) or (K is None):
            K = float(round(spot))  # ATM aproximado
            call_mid = BlackScholesOption(spot, K, T, r, sigma_entry, "call", q=q).price()
            put_mid = BlackScholesOption(spot, K, T, r, sigma_entry, "put", q=q).price()

        pos = StraddlePosition(
            entry_date=d,
            expiry=expiry,
            K=float(K),
            entry_spot=spot,
            sigma_entry=float(sigma_entry),
            r_entry=float(r),
            q_entry=float(q),
            call_entry_price=float(call_mid),
            put_entry_price=float(put_mid),
            contracts=1,
        )
        positions.append(pos)

    return positions


def price_straddle_bs(spot, K, T, r, sigma, q=0.0):
    call = BlackScholesOption(spot, K, T, r, sigma, "call", q=q)
    put = BlackScholesOption(spot, K, T, r, sigma, "put", q=q)
    return call.price(), put.price(), call, put


def backtest_straddle(spy_df, r_series, positions, mark_sigma="entry",
                      realized_vol_window=20):
    """
    Backtest de P&L diario del straddle "no hedged":
    - Marcaje diario por BS:
        mark_sigma="entry" -> sigma constante (la de entrada)
        mark_sigma="realized" -> sigma rolling diaria (proxy)
    """
    rv = realized_vol(spy_df["adj_close"], window=realized_vol_window)
    r_daily = r_series.reindex(spy_df.index).ffill().fillna(0.04)

    # Resultado diario: equity curve y P&L de cada posición
    equity = pd.Series(0.0, index=spy_df.index)
    pnl_trades = []

    for pos in positions:
        # rango de vida de la posición
        life_idx = spy_df.index[(spy_df.index >= pos.entry_date) & (spy_df.index <= pos.expiry)]
        if len(life_idx) < 2:
            continue

        # coste inicial (premium pagada)
        premium = pos.premium_paid

        # mark-to-market diario
        vals = []
        for d in life_idx:
            spot = float(spy_df.loc[d, "adj_close"])
            T = max((pos.expiry - d).days / 365.0, 1/365)

            r = float(r_daily.loc[d])
            q = pos.q_entry

            if mark_sigma == "realized":
                sigma = float(rv.loc[d]) if np.isfinite(rv.loc[d]) else pos.sigma_entry
            else:
                sigma = pos.sigma_entry

            call_p, put_p, _, _ = price_straddle_bs(spot, pos.K, T, r, sigma, q=q)
            val = (call_p + put_p) * 100 * pos.contracts
            vals.append(val)

        vals = pd.Series(vals, index=life_idx)
        trade_pnl = vals.iloc[-1] - premium
        pnl_trades.append({
            "entry": pos.entry_date,
            "expiry": pos.expiry,
            "K": pos.K,
            "premium": premium,
            "final_value": float(vals.iloc[-1]),
            "pnl": float(trade_pnl),
            "sigma_entry": pos.sigma_entry
        })

        # añadimos la curva del trade al equity (overlapping: sumamos MTM)
        equity.loc[life_idx] += (vals - premium)

    trades_df = pd.DataFrame(pnl_trades).sort_values("entry").reset_index(drop=True)
    return equity, trades_df


def backtest_delta_hedged_straddle(spy_df, r_series, positions,
                                  hedge_rebalance="daily",
                                  mark_sigma="entry",
                                  realized_vol_window=20,
                                  transaction_cost_bps=1.0):
    """
    Backtest delta-hedged:
    - Mantienes el straddle y ajustas la posición en subyacente para neutralizar delta.
    - Se rebalancea 'daily' (por defecto).
    - Costes de transacción (bps) aplicados al notional del subyacente en cada rebalanceo.

    Output:
      equity_curve (serie)
      trades (resumen por trade)
    """
    rv = realized_vol(spy_df["adj_close"], window=realized_vol_window)
    r_daily = r_series.reindex(spy_df.index).ffill().fillna(0.04)

    equity = pd.Series(0.0, index=spy_df.index)
    trades_out = []

    tc = transaction_cost_bps / 10000.0  # bps -> decimal

    for pos in positions:
        life_idx = spy_df.index[(spy_df.index >= pos.entry_date) & (spy_df.index <= pos.expiry)]
        if len(life_idx) < 2:
            continue

        # Estado del hedge
        shares = 0.0
        cash = -pos.premium_paid  # pagas la prima al entrar
        cumulative_tc = 0.0

        # MTM diario
        mtm_series = []

        for i, d in enumerate(life_idx):
            spot = float(spy_df.loc[d, "adj_close"])
            T = max((pos.expiry - d).days / 365.0, 1/365)
            r = float(r_daily.loc[d])
            q = pos.q_entry

            if mark_sigma == "realized":
                sigma = float(rv.loc[d]) if np.isfinite(rv.loc[d]) else pos.sigma_entry
            else:
                sigma = pos.sigma_entry

            call_p, put_p, call_obj, put_obj = price_straddle_bs(spot, pos.K, T, r, sigma, q=q)
            opt_value = (call_p + put_p) * 100 * pos.contracts

            # Delta del straddle (por 1 contrato)
            delta = (call_obj.delta() + put_obj.delta()) * 100 * pos.contracts

            # rebalance
            if hedge_rebalance == "daily":
                target_shares = -delta  # neutraliza delta
                d_shares = target_shares - shares
                if abs(d_shares) > 1e-8:
                    # comprar/vender subyacente: afecta cash
                    trade_notional = d_shares * spot
                    # coste transacción
                    this_tc = abs(trade_notional) * tc
                    cumulative_tc += this_tc
                    cash -= trade_notional
                    cash -= this_tc
                    shares = target_shares

            # MTM total: opciones + shares*spot + cash
            mtm = opt_value + shares * spot + cash
            mtm_series.append(mtm)

        mtm_series = pd.Series(mtm_series, index=life_idx)
        trade_pnl = float(mtm_series.iloc[-1])  # ya está neto de prima (en cash inicial)
        trades_out.append({
            "entry": pos.entry_date,
            "expiry": pos.expiry,
            "K": pos.K,
            "sigma_entry": pos.sigma_entry,
            "pnl": trade_pnl,
            "tc_total": cumulative_tc
        })

        equity.loc[life_idx] += mtm_series

    trades_df = pd.DataFrame(trades_out).sort_values("entry").reset_index(drop=True)
    return equity, trades_df
