# Estimación, inferencia y post-estimación

## Tres preguntas distintas

La documentación separa tres operaciones:

1. **Estimación:** qué ecuación se ajusta, con qué transformaciones, rezagos y criterio de selección.
2. **Inferencia:** cuánta incertidumbre tiene un coeficiente bajo la especificación ajustada.
3. **Validación predictiva:** qué tan bien pronostica en una ventana fuera de muestra frente a un benchmark.

Un resultado de una categoría no responde automáticamente las otras dos.

## Estimación actual

La ruta mensual usa el core en `src/trm_model/monthly/`, pero el core aún importa componentes de `src/model/` durante la transición. `src/estimate_model.py` es un wrapper compatible que delega en `trm_model.monthly.core`; no debe leerse como una segunda implementación independiente.

La estimación vigente incluye selección de rezagos por BIC, OLS robusto a través de la fachada histórica y uso de una muestra común para comparar especificaciones. Los parámetros principales son:

- muestra balanceada: enero de 2006 a abril de 2026;
- observaciones efectivas mensuales: 240;
- rezagos adicionales candidatos de la TRM: 0–3;
- HAC: seis meses;
- factores Shapley: 14.

## Inferencia

Los CSV de coeficientes reportan estimaciones y p-valores HAC. Los diagnósticos incluyen pruebas de autocorrelación, ARCH, normalidad, RESET y estabilidad cuando están disponibles. Un p-valor bajo indica incompatibilidad con una hipótesis estadística dentro del diseño; no demuestra causalidad ni estabilidad fuera de muestra.

Los coeficientes de variables contemporáneas deben interpretarse como asociaciones condicionales. En particular, dólar, VIX, EMBIG, monedas regionales, balanza, capitales, reservas, remesas y política monetaria pueden reaccionar al mismo shock o a la propia TRM.

## ECM y largo plazo

El contraste ARDL–ECM, sus bounds y los vectores de largo plazo viven en `results/robustez/`. La prueba bounds actual no confirma cointegración al 5%; por ello los coeficientes de largo plazo son exploratorios y no reemplazan la especificación mensual en diferencias.

El diferencial BEI a cinco años se reporta con alternativas de nivel, diferencia, tendencia, quiebre y agregación sobre fechas comunes. La especificación vigente usa primera diferencia y rezago de un mes, pero ninguna prueba aislada determina una interpretación económica definitiva.

## Criterio de separación

Al documentar un resultado, indique siempre:

- el nombre de la especificación;
- la muestra y el conjunto de información;
- si el término es contemporáneo o rezagado;
- si la métrica es ajuste, inferencia, contribución o pronóstico;
- el archivo de resultados y el manifest de corrida que lo respaldan.
