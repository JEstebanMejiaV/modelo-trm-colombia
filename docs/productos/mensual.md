# Producto mensual

El producto mensual agrupa tres ownerships relacionados:

- `monthly_explanation`: explicación histórica mensual.
- `monthly_forecast`: pronóstico mensual pseudo-tiempo-real.
- `robustness`: contrastes de robustez y ECM exploratorio.

La entrada operativa es `trm-model run-monthly`; el runner usa `monthly_bundle` como `product_id` de corrida. Los contratos declarativos están en [`configs/products/`](../../configs/products/) y [`pipelines/manifests/`](../../pipelines/manifests/).

## Estado y preguntas

| Parte | Información | Pregunta | Estado |
|---|---|---|---|
| Explicación | `ex_post`, `latest_available` | ¿Qué factores se asociaron con la variación observada? | Primaria, operativa |
| Pronóstico | `pseudo_real_time`, `latest_available` | ¿Qué se puede predecir con rezagos conservadores? | Primaria, pero no PIT completa |
| Robustez | Complementaria | ¿Cambian las conclusiones bajo especificaciones alternativas? | Supporting |

## Muestra y variable objetivo

La muestra consolidada cubre `2006-01` a `2026-04` (244 meses). La matriz mensual balanceada de estimación tiene 240 observaciones efectivas, de mayo de 2006 a abril de 2026, tras reservar la muestra común para diferencias y rezagos. La variable dependiente es `Δln(TRM)`; un aumento de COP/USD es depreciación del peso.

## Explicación histórica

Las especificaciones principales son:

- `Controles externos y financieros`: especificación de referencia.
- `Marco macroeconómico integral`: 14 factores Shapley, cuatro monedas regionales y el bloque global agrupado.

La explicación puede usar términos contemporáneos como términos de intercambio, dólar amplio, VIX, EMBIG, monedas regionales y el bloque global. Por tanto, es una contabilidad histórica o *nowcast* condicional. No es una observación causal ni una predicción que estuviera disponible al inicio del mes.

La especificación integral conserva el factor `Actividad y precios domésticos` (ISE total DANE e IPC Colombia) y un jugador agrupado de `Condiciones financieras, commodities y actividad internacional` con 17 términos. La documentación económica detallada está en [`metodologia/modelo_mensual.md`](../metodologia/modelo_mensual.md) y [`../mecanismo_transmision.md`](../mecanismo_transmision.md).

La lectura operativa combina tres salidas que no deben confundirse:

- `interpretacion_factores_marco_macro_integral.csv`: ficha por factor con descripción económica, términos, rezagos, coeficiente HAC cuando existe, IC 95%, estabilidad, contribución media y narrativa dinámica.
- `contribuciones_factores_marco_macro_integral.csv`: contabilidad mensual firmada agregada por factor; incluye `otros_componentes`, `ajuste_total` y `cierre_contable`.
- `pesos_explicativos_marco_macro_integral.csv`: participación Shapley en el R² incremental, no una contribución mensual ni un efecto causal.

Los bloques compuestos no se fuerzan a tener un coeficiente único. La narrativa usa “se asocia con” y distingue si el IC cruza cero; ninguna de estas salidas construye escenarios `do()` o contrafactuales.

## Pronóstico mensual

El pronóstico usa un calendario conservador de disponibilidad. Los factores económicos no entran contemporáneamente al mes objetivo; los rezagos efectivos están en [`results/pronostico/calendario_disponibilidad_pronostico.csv`](../../results/pronostico/calendario_disponibilidad_pronostico.csv). La composición regional seleccionada es BRL, CLP y MXN; PEN se conserva en la comparación histórica.

La evaluación versionada actual reporta MAPE aproximado de 2,49%, acierto direccional de 52,08% y R² de -1,46% frente a la caminata aleatoria. La caminata obtiene MAPE aproximado de 2,39%. Estas cifras deben leerse junto con el manifest y [`results/metadata.json`](../../results/metadata.json), no como una garantía futura.

El pronóstico es **pseudo-tiempo-real**: respeta los rezagos, pero usa la última revisión disponible. Solo 3 de 14 factores tienen cobertura histórica completa en el registro actual; `backtest_genuino_disponible` es `false`.

## Estimación, inferencia y validación

- Estimación: OLS con errores HAC de seis meses y selección BIC de 0–3 rezagos de la variación de TRM; la selección vigente es `p=0` para el modelo mensual principal.
- Shapley: 14 jugadores, 16.384 subconjuntos, 200 réplicas bootstrap de bloques circulares de 12 meses para intervalos.
- Validación: holdout expansivo de 48 meses y comparación explícita con caminata aleatoria.
- ECM/bounds: exploratorio; la prueba no confirma cointegración al 5%.

La separación conceptual está en [`metodologia/estimacion_inferencia.md`](../metodologia/estimacion_inferencia.md) y [`metodologia/validacion_predictiva.md`](../metodologia/validacion_predictiva.md).

## Outputs

El contrato de outputs generado por la ruta mensual está en [`src/trm_model/output_contract.py`](../../src/trm_model/output_contract.py): 45 archivos, distribuidos como 27 de explicación, 8 de pronóstico y 10 de robustez. Los manifests declarativos y el catálogo general pueden contener outputs heredados o diagnósticos adicionales; la corrida efectiva se determina por `artifacts/runs/<run_id>/manifest.json`.

Consulte [`operacion/salidas.md`](../operacion/salidas.md) para la diferencia entre contrato declarado, outputs generados y catálogo histórico.

## Reglas de interpretación

- No compare MAPE histórico condicional con MAPE ex ante sin declarar el conjunto de información.
- No interprete Shapley como porcentaje causal.
- No use los coeficientes de la explicación para reclamar superioridad predictiva.
- La contabilidad mensual agregada por factor reconcilia `suma_factores + otros_componentes` con `ajuste_total`; el cierre contable debe ser cero.
- La ficha distingue bloques compuestos sin coeficiente único y reporta los términos que forman cada bloque.
- No complete faltantes ni trate un snapshot parcial como backtest completo.
