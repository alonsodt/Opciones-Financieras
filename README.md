# Práctica 4 – Opciones Financieras  
**Long Straddle sobre SPY, Delta-Hedging y Ejecución con IBKR**

## Introducción

Esta práctica tiene como objetivo el diseño, implementación y análisis de una estrategia con opciones financieras utilizando datos reales de mercado obtenidos a través de la API de **Interactive Brokers (IBKR)**.

El trabajo se centra en una estrategia **long straddle periódico sobre el ETF SPY**, su versión **delta-hedged**, el análisis del **P&L histórico**, la **simulación del riesgo de ejecución** (combo vs patas) y una reflexión conceptual sobre el uso de **SPX frente a SPY**.  
Adicionalmente, se incluye como extra un ejemplo de **paper trading** en cuenta demo de IBKR.

Todo el análisis principal se realiza mediante **backtesting reproducible**, desacoplado del estado real de la cuenta.

---

## Objetivos de la práctica

La práctica cubre los siguientes puntos del enunciado:

1. Construcción de una estrategia **long straddle periódico sobre SPY**  
2. Modificación a una versión **delta-hedged usando el subyacente**  
3. Análisis del **P&L histórico** de ambas versiones  
4. Simulación de envío de órdenes **como combo y como patas**, analizando el *legging risk*  
5. Estudio de la **neutralización de Delta con otra opción** y su impacto en Gamma, Vega y Theta  
6. Reflexión final: **SPX vs SPY**

---

## Estructura del proyecto

```text
practica-4-opciones/
├─ README.md
├─ REFLEXION.md
├─ requirements.txt
├─ config/
│  └─ config.yaml
├─ src/
│  ├─ ibkr_data.py      # Conexión a IBKR y descarga de datos
│  ├─ pricing.py        # Black-Scholes y griegas
│  ├─ strategy.py       # Long straddle y delta-hedge
│  ├─ execution.py      # Simulación de ejecución (legging)
│  ├─ analytics.py      # Métricas y gráficos
│  ├─ backtest.py       # Neutralización de delta con opciones
│  └─ utils.py
├─ scripts/
│  ├─ run_all.py        # Script principal (ejecuta toda la práctica)
│  └─ paper_trade.py    # (Extra) Paper trading en cuenta demo IBKR
└─ outputs/
   ├─ results/
   └─ figures/
````

---

## Cómo ejecutar la práctica

### Ejecución principal (recomendada)

Toda la práctica se ejecuta desde la raíz del proyecto con un único comando:

```bash
python -m scripts.run_all
```

Este script:

* Descarga datos históricos desde IBKR (SPY y VIX)
* Calcula una volatilidad proxy combinando HV y VIX
* Ejecuta el backtest del long straddle (con y sin hedge)
* Genera métricas de rendimiento y riesgo
* Simula el riesgo de ejecución (combo vs patas)
* Analiza la neutralización de delta con otra opción
* Guarda resultados y gráficos en la carpeta `outputs/`

El proceso es **totalmente reproducible** y no depende del estado de la cuenta demo.

---

### Paper trading (opcional)

Se incluye un script para enviar órdenes reales en **cuenta demo de IBKR**:

```bash
python -m scripts.paper_trade --send --mode both --order-type LMT
```

Este script permite:

* Enviar un long straddle como **combo (BAG)**
* Enviar el straddle como **patas separadas**
* Observar el *legging risk* en tiempo real

> Nota: el paper trading es **opcional** y no afecta al análisis principal.
> Se recomienda usar **Python 3.13** por compatibilidad con `ib_insync`.

---

## Uso de IBKR y enfoque del backtest

Aunque la API de IBKR está conectada, se utiliza **exclusivamente como fuente de datos**:

* Precios históricos del subyacente (SPY)
* Cadenas de opciones
* Histórico del índice VIX

El **backtest es autocontenido**, con un capital inicial fijado en 100.000 €, independiente del balance de la cuenta demo de IBKR.
Esto es necesario para poder analizar el P&L histórico de forma consistente y reproducible.

---

## Estrategias analizadas

### Long Straddle periódico

La estrategia consiste en la compra simultánea de una call y una put **ATM**, con vencimiento cercano a 30 días, realizando un *roll* periódico.
Es una estrategia convexa que se beneficia de movimientos fuertes del subyacente y de incrementos de volatilidad, pero sufre en entornos laterales debido al **theta decay**.

### Long Straddle Delta-Hedged

Se añade una cobertura dinámica de Delta mediante el subyacente.
Esta versión reduce la volatilidad de la equity curve, pero también elimina parte de la convexidad direccional, lo que puede empeorar el rendimiento en ausencia de movimientos significativos.

---

## Resultados y métricas

Para ambas estrategias se calculan, entre otras, las siguientes métricas:

* Retorno total
* CAGR
* Volatilidad anualizada
* Sharpe ratio
* Máximo drawdown
* Calmar ratio
* Hit ratio

Los resultados se almacenan en:

```text
outputs/results/summary_metrics.csv
outputs/figures/equity_compare.png
outputs/figures/drawdown_compare.png
outputs/figures/rolling_vol_compare.png
```

---

## Ejecución y legging risk

Se simula el envío de órdenes de dos formas:

* **Combo (BAG)**: ejecución atómica
* **Patas separadas**: ejecución secuencial con retraso

El análisis cuantifica el coste adicional esperado y los escenarios extremos (p90, p99), mostrando cómo el *legging risk* aumenta con la volatilidad.

Resultados en:

```text
outputs/results/execution_legging_summary.csv
```

---

## Neutralización de Delta con otra opción

Se estudia la neutralización de Delta del straddle utilizando una opción adicional (ATM y OTM), analizando el impacto sobre:

* Gamma
* Vega (por cambio del 1%)
* Theta diaria

Resultados en:

```text
outputs/results/delta_neutral_option_summary.csv
```

---

## Reflexión final: SPX vs SPY

La reflexión conceptual sobre las diferencias entre utilizar SPX o SPY (liquidez, tamaño del contrato, cash settlement, fiscalidad y ejecución) se encuentra en:

---

## Conclusión

La práctica muestra que:

* Las estrategias long volatility no son rentables de forma estructural sin un adecuado contexto de mercado
* El delta-hedging reduce la volatilidad del P&L, pero puede empeorar el rendimiento
* La ejecución introduce riesgos reales que deben ser cuantificados
* Un enfoque modular y reproducible es clave en investigación cuantitativa

---

**Autor:** Alonso Díaz Tapia
**Máster:** IA aplicada a los Mercados Financieros (MIAX)
Si quieres, en un último mensaje puedo revisar el `REFLEXION.md` para que tenga exactamente el mismo tono académico que este README.
```
