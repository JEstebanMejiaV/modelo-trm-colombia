# Resultados econométricos

Esta carpeta contiene las salidas tabulares del modelo mensual de la TRM, organizadas en tres subcarpetas según su propósito:

```
results/
├── explicacion/   ← Modelos que explican con información contemporánea
├── pronostico/    ← Modelo que pronostica solo con información rezagada
├── robustez/      ← Pruebas de estacionariedad, ECM y robustez BEI
└── metadata.json  ← Controles de conciliación y SHA-256
```

Todas las estimaciones describen asociaciones estadísticas; no identifican efectos causales.

## `explicacion/` — Contabilidad histórica

Modelos que usan realizaciones contemporáneas de algunos factores. Sirven para descomponer qué movió la TRM *ex post*, no para pronosticar.

| Archivo | Contenido |
|---|---|
| `coeficientes_modelo_principal.csv` | Coeficientes HAC del modelo base (6 factores + pandemia) |
| `coeficientes_modelo_ampliado.csv` | Coeficientes HAC del modelo ampliado (12 factores, 4 monedas) |
| `diagnosticos_modelo_principal.csv` | Ljung-Box, ARCH, Jarque-Bera, RESET, CUSUM |
| `diagnosticos_modelo_ampliado.csv` | Igual para el ampliado |
| `ajuste_historico_modelo_principal.csv` | Ajuste de un paso, residuos mensuales |
| `ajuste_historico_modelo_ampliado.csv` | Igual para el ampliado |
| `contribuciones_modelo_principal.csv` | Descomposición mensual: coeficiente × regresor |
| `contribuciones_modelo_ampliado.csv` | Igual para el ampliado |
| `validacion_metricas_modelo_principal.csv` | MAPE, acierto y MAE en validación expansiva de 48 meses |
| `validacion_metricas_modelo_ampliado.csv` | Igual para el ampliado |
| `validacion_predicciones_modelo_principal.csv` | Predicciones mensuales de la validación |
| `validacion_predicciones_modelo_ampliado.csv` | Igual para el ampliado |
| `comparacion_modelos.csv` | R², BIC, MAPE y acierto: principal vs ampliado |
| `seleccion_rezagos_adl_diferencias.csv` | Grid BIC para rezagos del modelo base |
| `seleccion_rezagos_modelo_ampliado.csv` | Grid BIC para rezagos del ampliado |
| `pesos_explicativos_modelo_ampliado.csv` | Descomposición Shapley/LMG exacta del R² |
| `intervalos_bootstrap_pesos_shapley.csv` | Intervalos del 95% por bloques de 12 meses |
| `estabilidad_submuestras_modelo_ampliado.csv` | Coeficientes y Shapley en 5 cortes |
| `estabilidad_submuestras_resumen.csv` | Correlación de rangos y cambio máximo de peso |
| `comparacion_factor_regional.csv` | BRL+CLP+MXN vs +PEN en explicación y pronóstico |
| `pruebas_integracion.csv` | ADF y KPSS para todas las variables |

La validación es **condicional**: usa realizaciones contemporáneas de términos de intercambio, dólar amplio, VIX, EMBIG y monedas regionales.

## `pronostico/` — Pronóstico con rezagos de publicación

Modelo que solo usa información disponible al inicio del mes objetivo. Ningún factor económico entra en `.L0`.

| Archivo | Contenido |
|---|---|
| `coeficientes_modelo_pronostico.csv` | Coeficientes HAC del pronóstico seleccionado |
| `diagnosticos_modelo_pronostico.csv` | Pruebas residuales |
| `seleccion_rezagos_modelo_pronostico.csv` | Grid BIC para 0–3 rezagos de Δln(TRM) |
| `validacion_metricas_pronostico.csv` | MAPE, acierto y R² vs caminata aleatoria |
| `validacion_predicciones_pronostico.csv` | Predicciones mensuales pseudo-tiempo-real |
| `calendario_disponibilidad_pronostico.csv` | Rezago conservador de cada factor |
| `cobertura_vintages_pronostico.csv` | Cobertura de vintages por factor (0/12 completos) |

La validación es **pseudo-tiempo-real**: respeta el calendario de publicación pero usa el último vintage disponible de cada serie.

## `robustez/` — Pruebas de robustez y contraste ECM

Análisis complementarios que informan decisiones de especificación pero no producen el resultado principal.

| Archivo | Contenido |
|---|---|
| `comparacion_agregacion_bei_5y.csv` | Diferencial BEI: medias separadas vs fechas comunes |
| `comparacion_especificaciones_bei_5y.csv` | 6 variantes del BEI (nivel, Δ, tendencia, quiebre) |
| `pruebas_estacionariedad_bei_5y.csv` | ADF, KPSS y Zivot-Andrews del diferencial BEI |
| `tendencias_quiebres_bei_5y.csv` | Media, tendencia y tendencia segmentada del BEI |
| `bounds_resumen.csv` | Estadístico F y p-valores I(0)/I(1) del bounds test |
| `bounds_criticos.csv` | Valores críticos por percentil |
| `coeficientes_corto_plazo_ecm.csv` | Dinámica de corto plazo del ECM |
| `coeficientes_largo_plazo_ecm.csv` | Vector cointegrante normalizado (exploratorio) |
| `seleccion_rezagos_ecm.csv` | Grid AIC/BIC/HQIC del ARDL |
| `diagnosticos_ecm.csv` | Pruebas residuales del contraste ECM |

El ECM es exploratorio: la prueba bounds no confirma cointegración al 5%, por lo que el modelo principal permanece en diferencias.

## Convenciones de lectura

- `D.variable` = primera diferencia mensual.
- `.L0` = contemporáneo; `.L1` = un mes de rezago.
- `ln` = logaritmo natural; `asinh` = seno hiperbólico inverso.
- Los errores estándar son HAC con ventana de 6 meses.
- Un p-valor bajo no demuestra causalidad.

## Metadatos

`metadata.json` resume muestra, métricas, parámetros del bootstrap, cobertura de vintages y SHA-256 de las instantáneas clave.
