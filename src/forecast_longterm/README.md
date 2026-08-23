# Señales de largo plazo para la TRM (6-24 meses)

## Hallazgo central

La TRM exhibe **reversión a la media** a horizontes de 6-24 meses. Cuando está lejos de su tendencia de 5 años, tiende a corregir. Esta señal tiene correlación de 0,51 con el retorno futuro a 12 meses y acierta la dirección el 66% del tiempo — pero no es explotable como estrategia de MSE por la inestabilidad del β.

## Definición de largo plazo

**6 a 24 meses.** Horizonte donde los fundamentales macro dominan al ruido de corto plazo.

---

## Señales evaluadas

### Tendencias de equilibrio (para medir desviación)

| Tendencia | R² OOS 12m | Correlación | Dirección | Ventaja |
|---|---|---|---|---|
| **MA 60 meses (z-score)** | -0,8% | **0,51** | **66%** | Sin endpoint bias |
| MA 60 meses (%) | -32,8% | 0,34 | 59% | Interpretable |
| MA 36 meses | -11,0% | -0,20 | 52% | Más reactiva |
| HP filter (in-sample) | R²=51% | — | — | Look-ahead bias |
| Tendencia lineal rolling | -23,1% | -0,10 | 57% | Inestable |

**La MA de 60 meses normalizada es la mejor señal.** El HP filter solo funciona in-sample por endpoint bias.

### Momentum macro

| Señal | R² OOS 12m | Correlación | Interpretación |
|---|---|---|---|
| Ciclo Fed (Δfed_funds 12m) | +2,6% | -0,10 | Fed subiendo → depreciación futura (marginal) |
| Score macro compuesto | +2,5% | -0,26 | Combinación de Fed + TI + EMBIG |
| Δ EMBIG 6 meses | +0,4% | -0,11 | Riesgo subiendo → sin señal clara |
| Momentum TI 12 meses | -6,4% | -0,12 | No funciona |

El ciclo de la Fed tiene el mejor R² OOS (+2,6%) pero no es significativo (p = 0,57).

### Markov switching (2 regímenes)

El modelo identifica dos estados de la TRM relativa a su MA-60:

| Régimen | % del tiempo | Retorno medio 12m | Volatilidad 12m | Persistencia |
|---|---|---|---|---|
| **0 — Tranquilo** | 54,5% | +0,3% | 5,3% | p(stay) = 96% |
| **1 — Turbulento** | 45,5% | +8,7% | 16,5% | p(stay) = 5% |

Interpretación:
- En el **régimen tranquilo** (54% del tiempo): la TRM está moderadamente sobre tendencia y no corrige. Alta persistencia (96% de quedarse).
- En el **régimen turbulento** (45% del tiempo): la TRM está muy desviada y la corrección promedio es +8,7% a 12 meses. Transitorio (solo 5% de persistencia = dura ~1 mes).

El régimen turbulento corresponde a los episodios de overshooting (2008, 2015, 2020, 2022) seguidos de correcciones fuertes.

---

## In-sample vs Out-of-sample

| Método | R² 12m in-sample | R² 12m OOS | Por qué difieren |
|---|---|---|---|
| HP filter (full sample) | **51%** | **-26%** | Endpoint bias: HP usa datos futuros |
| MA 60m (z-score) | ~20% | **-0,8%** | β inestable entre regímenes |
| Ciclo Fed | ~5% | +2,6% | Poca señal pero sin bias |

La discrepancia masiva del HP (51% → -26%) demuestra que los backtests con HP deben usar HP expanding o alternativas sin look-ahead.

---

## Implicaciones prácticas

### Para cobertura corporativa

Si la TRM está 1+ desviaciones estándar por encima de su MA-60 (z-score > 1):
- Probabilidad de apreciación a 12 meses: **66%**
- No cubrir al 100% las posiciones cortas en USD puede ser racional

### Para timing de inversiones

La señal NO es suficiente para market timing (Sharpe negativo) porque:
- Acierta la dirección pero no la magnitud exacta
- La corrección puede tardar meses en materializarse
- En el régimen turbulento la volatilidad es 3× mayor

### Para política económica

Confirma convergencia PPP de largo plazo: desviaciones extremas del tipo de cambio real son temporales (~7 meses de vida media en el régimen turbulento).

---

## Estructura

```
src/forecast_longterm/
├── __init__.py
├── signals.py            5 señales base + evaluación in-sample
├── backtest.py           Backtest OOS con HP expanding (sin look-ahead)
├── extended_signals.py   Tendencias alternativas, Markov, momentum macro
└── README.md
```

## Uso

```bash
# Evaluación in-sample (rápida, 30 seg)
python src/forecast_longterm/signals.py

# Backtest OOS genuino (lento, 3 min — calcula HP expanding)
python src/forecast_longterm/backtest.py

# Extensiones: MA 60m, Markov, momentum macro (2 min)
python src/forecast_longterm/extended_signals.py
```

## Resultados guardados

```
results/pronostico/
├── senales_largo_plazo.csv                  Evaluación in-sample por horizonte
├── senales_largo_plazo_series.csv           Series temporales de las señales
├── backtest_largo_plazo_6m/12m/18m/24m.csv  Pronósticos OOS mes a mes
├── backtest_largo_plazo_resumen.csv         Métricas OOS por horizonte
├── senales_extendidas_largo_plazo.csv       Tendencias alt + momentum
├── series_tendencias_alternativas.csv       MA 60m, MA 36m, lineal rolling
├── series_momentum_macro.csv                Ciclo Fed, TI, EMBIG, diferencial
├── markov_regimes_largo_plazo.csv           Probabilidad de cada régimen por mes
└── markov_parametros_largo_plazo.csv        Resumen de los 2 estados
```
