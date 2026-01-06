# src/analytics.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# =========================
# Metrics helpers
# =========================
def _to_series(x) -> pd.Series:
    if isinstance(x, pd.Series):
        return x
    return pd.Series(x)

def equity_to_returns(equity: pd.Series) -> pd.Series:
    equity = equity.astype(float)
    return equity.pct_change().dropna()

def max_drawdown(equity: pd.Series) -> float:
    eq = equity.astype(float)
    peak = eq.cummax()
    dd = eq / peak - 1.0
    return float(dd.min())

def drawdown_series(equity: pd.Series) -> pd.Series:
    eq = equity.astype(float)
    peak = eq.cummax()
    return (eq / peak - 1.0).astype(float)

def annualized_return(equity: pd.Series, periods_per_year: int = 252) -> float:
    eq = equity.astype(float)
    if len(eq) < 2:
        return float("nan")
    total = eq.iloc[-1] / eq.iloc[0]
    n_periods = len(eq) - 1
    return float(total ** (periods_per_year / n_periods) - 1.0)

def annualized_vol(returns: pd.Series, periods_per_year: int = 252) -> float:
    r = returns.astype(float)
    if len(r) < 2:
        return float("nan")
    return float(r.std() * np.sqrt(periods_per_year))

def sharpe_ratio(returns: pd.Series, rf_annual: float = 0.0, periods_per_year: int = 252) -> float:
    r = returns.astype(float)
    if len(r) < 2:
        return float("nan")
    rf_daily = rf_annual / periods_per_year
    excess = r - rf_daily
    vol = excess.std()
    if vol <= 0:
        return float("nan")
    return float(excess.mean() / vol * np.sqrt(periods_per_year))

def sortino_ratio(returns: pd.Series, rf_annual: float = 0.0, periods_per_year: int = 252) -> float:
    r = returns.astype(float)
    if len(r) < 2:
        return float("nan")
    rf_daily = rf_annual / periods_per_year
    excess = r - rf_daily
    downside = excess[excess < 0]
    dd = downside.std()
    if dd <= 0:
        return float("nan")
    return float(excess.mean() / dd * np.sqrt(periods_per_year))

def hit_ratio(returns: pd.Series) -> float:
    r = returns.astype(float)
    if len(r) == 0:
        return float("nan")
    return float((r > 0).mean())

def calmar_ratio(equity: pd.Series, periods_per_year: int = 252) -> float:
    cagr = annualized_return(equity, periods_per_year=periods_per_year)
    mdd = abs(max_drawdown(equity))
    if mdd <= 0:
        return float("nan")
    return float(cagr / mdd)

def rolling_vol(returns: pd.Series, window: int = 63, periods_per_year: int = 252) -> pd.Series:
    r = returns.astype(float)
    return r.rolling(window).std() * np.sqrt(periods_per_year)


# =========================
# Main analysis
# =========================
@dataclass
class AnalyticsConfig:
    periods_per_year: int = 252
    rf_annual: float = 0.0
    rolling_vol_window: int = 63  # ~3 meses


def compute_metrics(daily: pd.DataFrame, cfg: AnalyticsConfig) -> Dict[str, Any]:
    if "equity" not in daily.columns:
        raise ValueError("daily debe contener columna 'equity'")

    equity = daily["equity"].astype(float)
    rets = equity_to_returns(equity)

    metrics = {
        "start": equity.index.min(),
        "end": equity.index.max(),
        "start_equity": float(equity.iloc[0]),
        "end_equity": float(equity.iloc[-1]),
        "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1.0),
        "cagr": annualized_return(equity, periods_per_year=cfg.periods_per_year),
        "ann_vol": annualized_vol(rets, periods_per_year=cfg.periods_per_year),
        "sharpe": sharpe_ratio(rets, rf_annual=cfg.rf_annual, periods_per_year=cfg.periods_per_year),
        "sortino": sortino_ratio(rets, rf_annual=cfg.rf_annual, periods_per_year=cfg.periods_per_year),
        "max_drawdown": max_drawdown(equity),
        "calmar": calmar_ratio(equity, periods_per_year=cfg.periods_per_year),
        "hit_ratio": hit_ratio(rets),
        "avg_daily_ret": float(rets.mean()) if len(rets) else float("nan"),
        "std_daily_ret": float(rets.std()) if len(rets) else float("nan"),
    }
    return metrics


def _save_plot(figpath: Path):
    figpath.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(figpath)
    plt.close()


def plot_equity_compare(daily_a: pd.DataFrame, daily_b: pd.DataFrame, label_a: str, label_b: str, figpath: Path):
    plt.figure()
    daily_a["equity"].astype(float).plot(label=label_a)
    daily_b["equity"].astype(float).plot(label=label_b)
    plt.title("Equity Curve Comparison")
    plt.xlabel("Date")
    plt.ylabel("Equity")
    plt.legend()
    _save_plot(figpath)


def plot_drawdown_compare(daily_a: pd.DataFrame, daily_b: pd.DataFrame, label_a: str, label_b: str, figpath: Path):
    dda = drawdown_series(daily_a["equity"])
    ddb = drawdown_series(daily_b["equity"])

    plt.figure()
    dda.plot(label=label_a)
    ddb.plot(label=label_b)
    plt.title("Drawdown Comparison")
    plt.xlabel("Date")
    plt.ylabel("Drawdown")
    plt.legend()
    _save_plot(figpath)


def plot_returns_hist(daily: pd.DataFrame, title: str, figpath: Path):
    rets = equity_to_returns(daily["equity"])
    plt.figure()
    plt.hist(rets.values, bins=60)
    plt.title(title)
    plt.xlabel("Daily Return")
    plt.ylabel("Frequency")
    _save_plot(figpath)


def plot_rolling_vol_compare(daily_a: pd.DataFrame, daily_b: pd.DataFrame, cfg: AnalyticsConfig, label_a: str, label_b: str, figpath: Path):
    ra = equity_to_returns(daily_a["equity"])
    rb = equity_to_returns(daily_b["equity"])
    v_a = rolling_vol(ra, window=cfg.rolling_vol_window, periods_per_year=cfg.periods_per_year)
    v_b = rolling_vol(rb, window=cfg.rolling_vol_window, periods_per_year=cfg.periods_per_year)

    plt.figure()
    v_a.plot(label=label_a)
    v_b.plot(label=label_b)
    plt.title(f"Rolling Volatility ({cfg.rolling_vol_window}d)")
    plt.xlabel("Date")
    plt.ylabel("Annualized Vol")
    plt.legend()
    _save_plot(figpath)


def load_daily_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Soporta index guardado como primera columna
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime")
    else:
        # si se guardó con index -> suele llamarse "datetime" al leer; si no, "Unnamed: 0"
        if "Unnamed: 0" in df.columns:
            df["Unnamed: 0"] = pd.to_datetime(df["Unnamed: 0"])
            df = df.rename(columns={"Unnamed: 0": "datetime"}).set_index("datetime")
        else:
            raise ValueError(f"No encuentro columna datetime en {path.name}")
    df = df.sort_index()
    return df


def run_analytics(
    daily_nohedge_path: Path,
    daily_hedged_path: Path,
    out_results_dir: Path,
    out_figures_dir: Path,
    cfg: AnalyticsConfig = AnalyticsConfig(),
    label_nohedge: str = "No Hedge",
    label_hedged: str = "Delta-Hedged",
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Carga CSVs, calcula métricas, genera plots.
    Devuelve: daily_no, daily_h, summary_df
    """
    out_results_dir.mkdir(parents=True, exist_ok=True)
    out_figures_dir.mkdir(parents=True, exist_ok=True)

    daily_no = load_daily_csv(daily_nohedge_path)
    daily_h = load_daily_csv(daily_hedged_path)

    m_no = compute_metrics(daily_no, cfg)
    m_h = compute_metrics(daily_h, cfg)

    summary = pd.DataFrame([
        {"strategy": label_nohedge, **m_no},
        {"strategy": label_hedged, **m_h},
    ])

    summary.to_csv(out_results_dir / "summary_metrics.csv", index=False)

    # Plots comparativos
    plot_equity_compare(daily_no, daily_h, label_nohedge, label_hedged, out_figures_dir / "equity_compare.png")
    plot_drawdown_compare(daily_no, daily_h, label_nohedge, label_hedged, out_figures_dir / "drawdown_compare.png")
    plot_rolling_vol_compare(daily_no, daily_h, cfg, label_nohedge, label_hedged, out_figures_dir / "rolling_vol_compare.png")

    # Plots individuales
    plot_returns_hist(daily_no, f"Daily Returns Histogram - {label_nohedge}", out_figures_dir / "hist_returns_nohedge.png")
    plot_returns_hist(daily_h, f"Daily Returns Histogram - {label_hedged}", out_figures_dir / "hist_returns_deltahedged.png")

    return daily_no, daily_h, summary

