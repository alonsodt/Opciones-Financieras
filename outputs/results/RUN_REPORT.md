# Run report

Generado: `2026-01-07 17:27:20`


## Outputs (mapeados al enunciado)


### 1) Long straddle periódico (SPY)

- `outputs/results/daily_nohedge.csv`

- `outputs/results/trades_nohedge.csv`


### 2) Versión delta-hedged (subyacente)

- `outputs/results/daily_deltahedged.csv`

- `outputs/results/trades_deltahedged.csv`


### 3) Análisis P&L (métricas + gráficos)

- `outputs/results/summary_metrics.csv`

- `outputs/figures/equity_compare.png`

- `outputs/figures/drawdown_compare.png`

- `outputs/figures/rolling_vol_compare.png`


### 4) Ejecución: combo vs patas (legging)

- `outputs/results/execution_legging_summary.csv`


### 5) Delta-neutral con otra opción (impacto Gamma/Vega/Theta)

- `outputs/results/delta_neutral_option_summary.csv`


### 6) Reflexión SPX vs SPY

- `REFLEXION.md`


## Métricas clave


| strategy     | start               | end                 |   start_equity |   end_equity |   total_return |       cagr |   ann_vol |    sharpe |   sortino |   max_drawdown |    calmar |   hit_ratio |   avg_daily_ret |   std_daily_ret |
|:-------------|:--------------------|:--------------------|---------------:|-------------:|---------------:|-----------:|----------:|----------:|----------:|---------------:|----------:|------------:|----------------:|----------------:|
| No Hedge     | 2021-01-11 00:00:00 | 2026-01-07 00:00:00 |         100000 |      91750.2 |     -0.0824978 | -0.0171672 | 0.0488308 | -0.330239 | -0.494137 |      -0.125726 | -0.136545 |    0.398244 |    -6.39914e-05 |      0.00307605 |
| Delta-Hedged | 2021-01-11 00:00:00 | 2026-01-07 00:00:00 |         100000 |      84359.1 |     -0.156409  | -0.033629  | 0.0331226 | -1.01623  | -1.95828  |      -0.172715 | -0.194708 |    0.348763 |    -0.000133572 |      0.00208653 |

