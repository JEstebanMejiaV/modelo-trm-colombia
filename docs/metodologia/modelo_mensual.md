# Metodología del modelo mensual

## Variable objetivo

La variable objetivo es el cambio mensual del logaritmo de la TRM promedio mensual:

```text
Δln(TRM_t) = ln(TRM_t) − ln(TRM_{t−1})
```

La unidad de la TRM es COP/USD; un aumento es depreciación del peso.

## Especificaciones

Las especificaciones canónicas están en [`src/trm_model/monthly/specifications.py`](../../src/trm_model/monthly/specifications.py). Durante la migración, la econometría validada también se conserva en `src/model/config.py` y sus módulos relacionados. Las dos rutas no deben divergir sin una prueba de paridad.

| Especificación | Uso | Factores |
|---|---|---:|
| `REFERENCE_FACTOR_SPECS` | Controles externos y financieros | 6 factores principales más controles |
| `INTEGRATED_FACTOR_SPECS_4` | Marco macroeconómico integral | 14 jugadores, cuatro monedas regionales |
| `FORECAST_FACTOR_SPECS_3/4` | Pronóstico con disponibilidad | Variantes regionales comparadas por BIC |

## Factores y bloques

El marco integral contiene, entre otros:

- términos de intercambio;
- remesas;
- diferencial de tasas y déficit fiscal;
- dólar amplio y VIX;
- EMBIG Colombia;
- reservas, balanza comercial y flujos de capital;
- diferencial BEI a cinco años;
- actividad y precios domésticos (ISE total e IPC Colombia);
- factor regional de monedas;
- bloque de 17 términos de condiciones financieras, commodities y actividad internacional.

El bloque global es un solo jugador para Shapley, aunque sus contribuciones mensuales se calculan término a término. Así se controla la colinealidad y se evita aumentar artificialmente el número de jugadores.

## Transformaciones y rezagos

- Variables positivas: logaritmo y primera diferencia cuando corresponde.
- Flujos con valores cero o signo: transformación `asinh` antes de diferenciar.
- Curvas diarias: promedio mensual de observaciones publicadas; BEI colombiano y estadounidense se promedian por separado.
- Factores regionales: promedio de cambios logarítmicos estandarizados; la calibración histórica está fijada en 2006–2019.
- Explicación histórica: admite algunos términos contemporáneos realizados.
- Pronóstico: aplica rezagos de disponibilidad; el calendario auditable está en `results/pronostico/calendario_disponibilidad_pronostico.csv`.

Las fórmulas y el diccionario completo están en [`data/README.md`](../../data/README.md) y en [`datos/transformaciones.md`](../datos/transformaciones.md).

## Estimación

La selección dinámica evalúa de cero a tres rezagos de `Δln(TRM)` y usa BIC. El resultado vigente para la especificación mensual principal es `p=0`. La inferencia usa errores estándar HAC con seis meses de rezago máximo.

La matriz de estimación debe estar balanceada. Si falta una observación de una variable activa, el pipeline falla explícitamente en lugar de crear una observación sintética.

## Shapley/LMG

La descomposición calcula el aporte marginal promedio de cada jugador sobre el R² incremental frente a la base. Con 14 jugadores se evalúan `2^14 = 16.384` subconjuntos. Los intervalos se estiman con 200 réplicas de bootstrap circular de bloques de 12 meses y 64 permutaciones antitéticas, con semilla `20260823`.

Un peso Shapley:

- no es un coeficiente;
- no es un p-valor;
- no es una elasticidad;
- no es un porcentaje causal del movimiento del dólar.

## Mecanismo económico

La narrativa de transmisión entre condiciones globales, monedas regionales, riesgo soberano y flujos externos está en [`../mecanismo_transmision.md`](../mecanismo_transmision.md). Esa narrativa organiza canales plausibles; no convierte una regresión observacional en identificación causal.
