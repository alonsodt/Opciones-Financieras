def delta_neutral_with_option(spot, K_atm, K_hedge, T, r, sigma, q=0.0, hedge_type="call"):
    """
    Neutraliza la delta de un straddle ATM usando una única opción adicional (ej: call OTM).
    Devuelve hedge_ratio y griegas antes/después.
    """
    call_atm = BlackScholesOption(spot, K_atm, T, r, sigma, "call", q=q)
    put_atm = BlackScholesOption(spot, K_atm, T, r, sigma, "put", q=q)

    delta_straddle = call_atm.delta() + put_atm.delta()
    gamma_straddle = call_atm.gamma() + put_atm.gamma()
    vega_straddle = call_atm.vega() + put_atm.vega()
    theta_straddle = call_atm.theta() + put_atm.theta()

    hedge_opt = BlackScholesOption(spot, K_hedge, T, r, sigma, hedge_type, q=q)
    hedge_ratio = -delta_straddle / hedge_opt.delta()

    total = {
        "Delta": delta_straddle + hedge_ratio * hedge_opt.delta(),
        "Gamma": gamma_straddle + hedge_ratio * hedge_opt.gamma(),
        "Vega":  vega_straddle  + hedge_ratio * hedge_opt.vega(),
        "Theta": theta_straddle + hedge_ratio * hedge_opt.theta()
    }

    base = {"Delta": delta_straddle, "Gamma": gamma_straddle, "Vega": vega_straddle, "Theta": theta_straddle}
    hedge = {"Delta": hedge_ratio * hedge_opt.delta(), "Gamma": hedge_ratio * hedge_opt.gamma(),
             "Vega": hedge_ratio * hedge_opt.vega(), "Theta": hedge_ratio * hedge_opt.theta()}

    return hedge_ratio, base, hedge, total


# =============================================================================
# 6) UTILIDADES DE PLOTS + RESÚMENES
# =============================================================================

def summarize_trades(df, title):
    print("\n" + "="*80)
    print(title)
    print("="*80)
    if df.empty:
        print("No hay trades.")
        return
    print(df[["entry","expiry","K","sigma_entry","pnl"]].head(10))
    print("\nEstadísticos P&L:")
    print(df["pnl"].describe())


def plot_equity_curves(eq1, eq2, label1="Straddle", label2="Delta-Hedged"):
    plt.figure(figsize=(12, 5))
    plt.plot(eq1.index, eq1.values, label=label1)
    plt.plot(eq2.index, eq2.values, label=label2)
    plt.axhline(0, linestyle="--", linewidth=1)
    plt.title("Equity curve (MTM acumulado por trades solapados)")
    plt.xlabel("Fecha")
    plt.ylabel("P&L ($)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def plot_hist_pnl(df1, df2, name1="Straddle", name2="Delta-Hedged"):
    plt.figure(figsize=(12, 5))
    plt.hist(df1["pnl"].values, bins=30, alpha=0.6, label=name1, edgecolor="black")
    plt.hist(df2["pnl"].values, bins=30, alpha=0.6, label=name2, edgecolor="black")
    plt.axvline(df1["pnl"].mean(), linestyle="--", linewidth=2)
    plt.axvline(df2["pnl"].mean(), linestyle="--", linewidth=2)
    plt.title("Distribución del P&L por trade")
    plt.xlabel("P&L ($)")
    plt.ylabel("Frecuencia")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()
