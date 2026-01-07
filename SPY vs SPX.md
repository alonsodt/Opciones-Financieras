# Reflexión: Uso de SPX frente a SPY en una estrategia Long Straddle

## 1. Introducción

En esta práctica se ha construido y analizado una estrategia **Long Straddle periódico** sobre el ETF SPY, incluyendo una versión con cobertura delta y una simulación del proceso de ejecución de órdenes.  
El objetivo de esta reflexión es analizar **qué habría cambiado** si, en lugar de utilizar SPY como subyacente, se hubiera empleado el índice **SPX**, atendiendo tanto a aspectos operativos como a implicaciones en el riesgo, los costes y la gestión de la estrategia.

La comparación es especialmente relevante, ya que ambos subyacentes replican el S&P 500, pero presentan diferencias estructurales importantes que afectan directamente a la operativa con opciones.

---

## 2. Diferencias estructurales entre SPY y SPX

Aunque SPY y SPX están altamente correlacionados, no son equivalentes desde el punto de vista de derivados:

| Característica | SPY | SPX |
|---------------|-----|-----|
| Tipo de subyacente | ETF | Índice |
| Liquidación | Física (entrega de ETF) | En efectivo (cash-settled) |
| Estilo de ejercicio | Americano | Europeo |
| Multiplicador | 100 | 100 |
| Dividendos | Sí (reales) | No (implícitos en el índice) |
| Tamaño nocional | Más pequeño | Mucho mayor |
| Asignación anticipada | Posible | No |
| Uso típico | Trading / retail | Institucional |

Estas diferencias condicionan de forma directa la implementación práctica de la estrategia.

---

## 3. Impacto en la estrategia Long Straddle

### 3.1 Ejecución de la estrategia

En SPY, las opciones son **americanas**, lo que introduce el riesgo de **ejercicio anticipado**, especialmente en calls cerca de fechas ex-dividendo.  
En una estrategia long straddle esto no es habitual, pero sigue siendo un riesgo operativo que debe tenerse en cuenta.

En SPX, al ser opciones **europeas**, este riesgo desaparece completamente. La liquidación se produce únicamente al vencimiento y siempre en efectivo, lo que simplifica la gestión.

Además, los **spreads en SPX** suelen ser más ajustados en términos relativos, aunque el mayor nocional implica un mayor impacto absoluto de cualquier deslizamiento.

---

### 3.2 Gestión del riesgo y coberturas delta

En la práctica se ha implementado una cobertura delta con el subyacente (SPY) y una alternativa utilizando otra opción.

- **Con SPY**:
  - La cobertura delta se realiza fácilmente con el propio ETF.
  - Permite ajustes finos y frecuentes.
  - Es más accesible para cuentas pequeñas.

- **Con SPX**:
  - No existe subyacente negociable directamente.
  - La cobertura delta se realiza mediante **futuros sobre el S&P 500** o ETFs correlacionados.
  - Esto introduce una capa adicional de complejidad y posibles desajustes (basis risk).

Por tanto, aunque SPX es conceptualmente más “limpio”, SPY resulta más flexible para estrategias con cobertura dinámica.

---

### 3.3 Volatilidad implícita y pricing

En el caso de SPX, la volatilidad implícita está más estrechamente relacionada con el **VIX**, ya que este índice se construye directamente a partir de opciones SPX.  
Esto implica que, al utilizar SPX, la estimación de volatilidad implícita es más directa y consistente.

En SPY, la volatilidad implícita puede diferir ligeramente debido a:
- dividendos discretos,
- microestructura del ETF,
- efectos de oferta y demanda del mercado retail.

No obstante, para el horizonte temporal y el enfoque del ejercicio, estas diferencias no invalidan el uso de SPY como proxy.

---

## 4. Costes y tamaño de la operativa

Uno de los factores más relevantes es el **tamaño nocional**:

- Un straddle en SPX implica una exposición mucho mayor.
- Esto se traduce en:
  - mayores requisitos de capital,
  - mayor impacto de errores de ejecución,
  - menor accesibilidad para cuentas pequeñas.

SPY permite:
- escalar la estrategia,
- analizar resultados con menor riesgo absoluto,
- realizar backtests más realistas para un entorno académico o semi-profesional.

---

## 5. Ventajas e inconvenientes resumidos

### SPY – Ventajas
- Mayor accesibilidad.
- Cobertura delta sencilla.
- Adecuado para backtesting y experimentación.
- Menor riesgo operativo absoluto.

### SPY – Inconvenientes
- Riesgo (teórico) de asignación anticipada.
- Dividendos introducen pequeñas distorsiones.
- Volatilidad implícita menos “pura” que en SPX.

### SPX – Ventajas
- Opciones europeas (sin asignación anticipada).
- Liquidación en efectivo.
- Relación directa con el VIX.
- Entorno más institucional.

### SPX – Inconvenientes
- Mayor tamaño nocional.
- Operativa más compleja.
- Cobertura delta indirecta.
- Menos flexible para ajustes frecuentes.

---

## 6. Conclusión

Si esta estrategia Long Straddle se hubiera implementado sobre **SPX en lugar de SPY**, el análisis teórico habría sido más limpio y alineado con un entorno institucional, especialmente en lo relativo a volatilidad implícita y ausencia de asignación anticipada.

Sin embargo, para los objetivos de esta práctica —construcción de estrategia, análisis de P&L, simulación de ejecución y coberturas— **SPY resulta una elección más adecuada**, ya que:
- permite una implementación más flexible,
- facilita la cobertura delta,
- reduce el tamaño del riesgo,
- y es más representativo de un entorno operativo realista para un trader o gestor en formación.

En definitiva, **SPY es preferible para el desarrollo y testeo de la estrategia**, mientras que **SPX sería el candidato natural para una implementación institucional a mayor escala**.

