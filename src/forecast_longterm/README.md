# Señales de largo plazo para la TRM (6-24 meses)

## Hallazgo principal

A largo plazo (6-24 meses), la TRM exhibe **reversión a la media**: cuando está lejos de su tendencia de equilibrio, tiende a corregir. Esta señal tiene un R² in-sample de 50% a 12 meses, pero **no funciona out-of-sample** con el filtro HP expanding porque el endpoint bias del HP invalida la señal en tiempo real.

## Definición de largo plazo

**6 a 24 meses.** Es el horizonte en que los fundamentales macroeconómicos dominan al ruido de corto plazo, pero donde los coeficientes de la relación también son inestables.

## Resultados in-sample (evaluación retrospectiva)

Usando el filtro HP estándar (con toda la muestra — incluye look-ahead):

| Señal | 6 meses | 12 meses | 18 meses | 24 meses |
|---|---|---|---|---|
| Z-score HP (TRM vs tendencia) | R²=36%, p<0,001 | R²=51%, p<0,001 | R²=48%, p<0,001 | R²=30%, p<0,001 |
| Desviación HP (%) | R²=38%, p<0,001 | R²=48%, p<0,001 | R²=43%, p<0,001 | R²=29%, p<0,001 |
| Dólar amplio vs tendencia | R²=14%, p=0,002 | R²=31%, p<0,001 | R²=33%, p<0,001 | R²=21%, p<0,001 |
| Score compuesto | R²=10%, p=0,009 | R²=14%, p=0,048 | R²=15%, p=0,021 | R²=9%, p=0,030 |

Interpretación: cuando la TRM está 1 desviación estándar por encima de su tendencia, el retorno esperado a 12 meses es **-8,1%** (apreciación).

## Resultados out-of-sample (backtest genuino)

Usando HP expanding (calcula tendencia SOLO con datos hasta t) y estima β solo con datos pasados:

| Horizonte | R² OOS | Dirección | DM p-valor | Correlación |
|---|---|---|---|---|
| 6 meses | -12,7% | 46,8% | 0,16 | 0,06 |
| 12 meses | -26,3% | 51,8% | 0,05 | 0,07 |
| 18 meses | -41,3% | 58,0% | 0,03 | **0,56** |
| 24 meses | -135,9% | 31,8% | <0,001 | **0,75** |

**El R² OOS es negativo** en todos los horizontes. La señal es peor que la caminata aleatoria en términos de MSE.

**PERO** la correlación pronóstico-realizado a 18-24 meses es alta (0,56-0,75). Esto indica que la señal contiene información direccional pero el β estimado con datos pasados no la captura bien (es altamente inestable: media ≈ 0 ± 9).

## Por qué la discrepancia in-sample vs out-of-sample

1. **Endpoint bias del HP**: el filtro HP asigna la tendencia del FUTURO a los extremos de la muestra. En tiempo real, los últimos 2-3 años de la tendencia son ruidosos.
2. **Inestabilidad del β**: la velocidad de reversión cambia según el régimen macro. En 2006-2014 fue ~-1.4; en 2020-2026 es más rápida.
3. **La señal tiene timing incorrecto**: sabe CUÁNTO corregirá pero no CUÁNDO empieza la corrección.

## Implicaciones prácticas

- **Para cobertura corporativa**: si la TRM está significativamente por encima de su tendencia de 5 años, la probabilidad de apreciación a 12-24 meses es alta (correlación 0,56-0,75). Esto justifica no cubrir al 100% posiciones cortas en USD.
- **Para inversión**: la señal NO es suficiente para timing de mercado (R² OOS negativo, Sharpe negativo). Pero combinada con otros indicadores de régimen macro, podría mejorar.
- **Para política económica**: confirma que desviaciones extremas de la TRM real son temporales (convergencia PPP de largo plazo).

## Estructura

```
src/forecast_longterm/
├── __init__.py
├── signals.py       5 señales + evaluación in-sample (regresión predictiva)
├── backtest.py      Backtest OOS con HP expanding (sin look-ahead)
└── README.md
```

## Señales implementadas

| # | Señal | Cómo se construye | Hipótesis |
|---|---|---|---|
| 1 | Desviación HP | ln(TRM) − tendencia HP(λ=14400) | Reversión a la media del tipo de cambio real |
| 2 | Z-score HP | Desviación / std rolling 60m | Normalizada para comparar entre períodos |
| 3 | Dólar amplio vs HP | ln(DXY) − tendencia HP | Si el USD global está caro, TRM también corregirá |
| 4 | Diferencial de tasas reales | (iCol−BEI_col) − (iFed−BEI_us) | Carry trade real: atrae capital si alto |
| 5 | Score compuesto | Promedio de z-scores (con signos ajustados) | Combinación diversificada |

## Uso

```bash
# Evaluación in-sample (rápida)
python src/forecast_longterm/signals.py

# Backtest out-of-sample (lento: calcula HP expanding)
python src/forecast_longterm/backtest.py
```

## Conclusión

La reversión a la media de la TRM es un fenómeno REAL (la correlación a 18-24 meses es 0,56-0,75), pero no es explotable con un modelo lineal simple en tiempo real. El problema no es la señal — es la estimación del β y el timing.

Posibles extensiones para mejorar:
- Usar tendencias alternativas al HP (promedio móvil de 5 años, PPP de la OCDE)
- Estimar β con regime-switching (Markov)
- Combinar con señales de momentum macro (ciclo Fed, petróleo)
