# Resultados econométricos

> Índice del área: [`docs/operacion/salidas.md`](../docs/operacion/salidas.md) · [`docs/README.md`](../docs/README.md).
>
> Este README conserva el diccionario de archivos heredados. Para saber qué produjo una corrida concreta, use `artifacts/runs/<run_id>/manifest.json`; para ownership general, use [`output_catalog.json`](output_catalog.json).

Esta carpeta contiene las salidas tabulares del modelo mensual de la TRM, organizadas en tres subcarpetas según su propósito:

```
results/
├── explicacion/   ← Modelos que explican con información contemporánea
├── pronostico/    ← Modelo que pronostica solo con información rezagada
├── robustez/      ← Pruebas de estacionariedad, ECM y robustez BEI
├── metadata.json  ← Controles de conciliación y SHA-256
└── output_catalog.json ← Ownership de cada output y estatus del producto
```

`results/` es un exportador de compatibilidad heredado: conserva las rutas que
usan los checks, gráficos y workbook existentes. El hecho de que un archivo
esté bajo `results/pronostico/` no significa que pertenezca al pronóstico
mensual. `output_catalog.json` es el inventario ejecutable de ownership: separa
`monthly_forecast`, `daily_direction`, `daily_volatility` y
`long_horizon_research` sin mover los CSV versionados. Los manifests de producto
en `pipelines/manifests/` y `research/manifests/` declaran el contrato futuro;
los wrappers de `pipelines/` permiten ejecutar los entry points legacy de forma
explícita.

Todas las estimaciones describen asociaciones estadísticas; no identifican efectos causales.

## `explicacion/` — Contabilidad histórica

Modelos que usan realizaciones contemporáneas de algunos factores. Sirven para descomponer qué movió la TRM *ex post*, no para pronosticar.

| Archivo | Contenido |
|---|---|
| `coeficientes_controles_externos.csv` | Coeficientes HAC de Controles externos y financieros (6 factores + pandemia) |
| `coeficientes_marco_macro_integral.csv` | Coeficientes HAC del marco macroeconómico integral (14 factores agrupados; 4 monedas regionales) |
| `diagnosticos_controles_externos.csv` | Ljung-Box, ARCH, Jarque-Bera, RESET, CUSUM |
| `diagnosticos_marco_macro_integral.csv` | Igual para el marco macroeconómico integral |
| `ajuste_historico_controles_externos.csv` | Ajuste de un paso, residuos mensuales |
| `ajuste_historico_marco_macro_integral.csv` | Igual para el marco macroeconómico integral |
| `contribuciones_controles_externos.csv` | Descomposición mensual: coeficiente × regresor |
| `contribuciones_marco_macro_integral.csv` | Igual para el marco macroeconómico integral |
| `validacion_metricas_controles_externos.csv` | MAPE, acierto y MAE en validación expansiva de 48 meses |
| `validacion_metricas_marco_macro_integral.csv` | Igual para el marco macroeconómico integral |
| `validacion_predicciones_controles_externos.csv` | Predicciones mensuales de la validación |
| `validacion_predicciones_marco_macro_integral.csv` | Igual para el marco macroeconómico integral |
| `comparacion_especificaciones.csv` | R², BIC, MAPE y acierto de las especificaciones descriptivas |
| `seleccion_rezagos_adl_diferencias.csv` | Grid BIC para rezagos de Controles externos y financieros |
| `seleccion_rezagos_marco_macro_integral.csv` | Grid BIC para rezagos del marco macroeconómico integral |
| `pesos_explicativos_marco_macro_integral.csv` | Descomposición Shapley/LMG exacta del R² |
| `intervalos_bootstrap_pesos_shapley.csv` | Intervalos del 95% por bloques de 12 meses |
| `estabilidad_submuestras_marco_macro_integral.csv` | Coeficientes y Shapley en 5 cortes |
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
| `cobertura_vintages_pronostico.csv` | Cobertura de vintages por factor (3 de 14 factores activos completos) |
| `variables_globales_series.csv` | Señales mensuales globales, transformaciones y factor agrupado |
| `variables_globales_evaluacion.csv` | Evaluación OOS de señales globales individuales y agregadas |
| `comparacion_modelos_diarios.csv` | Comparación OOS de modelos diarios, incluido HAR con globales rezagadas |
| `backtest_largo_plazo_resumen.csv` | Backtest OOS a 6, 12, 18 y 24 meses |
| `wavelets_comparacion_bandas.csv` | Evaluación OOS por bandas de frecuencia |
| `panel_em_estimaciones.csv` | Estimaciones del panel de monedas emergentes |
| `volatilidad_modelos_garch.csv` | Comparación GARCH, EGARCH, GJR-GARCH y GARCH + VIX |
| `volatilidad_var_backtest.csv` | Violaciones y pruebas de cobertura de VaR |
| `diebold_mariano_pronostico.csv` | Test DM vs caminata (p = 0.21, no rechaza igualdad) |
| `comparacion_parsimoniosos_pronostico.csv` | Top-3, top-5, top-7 y marco macroeconómico integral de 14 factores comparados |
| `coeficientes_pronostico_parsimonioso.csv` | Coeficientes del top-3 (monedas, dólar, EMBIG) |
| `validacion_metricas_parsimonioso.csv` | MAPE 2.57% del pronóstico parsimonioso |
| `validacion_predicciones_parsimonioso.csv` | Predicciones mensuales del top-3 |
| `diagnosticos_pronostico_parsimonioso.csv` | Pruebas residuales del top-3 |
| `backtest_genuino_parcial.csv` | Revisiones de DTWEXBGS y VIXCLS (vintages vs último) |
| `comparacion_forecast_combination.csv` | 50/50 e inversa-MSE vs caminata |
| `pronostico_multihorizonte.csv` | R² vs caminata en h=1,2,3,6 meses (todos negativos) |

La validación es **pseudo-tiempo-real**: respeta el calendario de publicación pero usa el último vintage disponible de cada serie. El test Diebold-Mariano no rechaza igualdad de capacidad predictiva al 5%.

## `robustez/` — Pruebas de robustez y contraste ECM

Análisis complementarios que informan decisiones de especificación pero no producen el resultado de referencia.

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
| `rolling_window_coeficientes.csv` | 120 ventanas × 14 coeficientes del marco macroeconómico integral |
| `rolling_window_estabilidad.csv` | Resumen: std, CV, cambios de signo (10/14 inestables) |
| `threshold_regression.csv` | Test de Chow con VIX, dólar y EMBIG como umbrales |
| `garch_residuos_marco_macro_integral.csv` | GARCH(1,1): persistencia 0.94, vol 2.12%/mes |
| `comparacion_estimadores_robustos.csv` | OLS vs Huber-T vs LAD |
| `coeficientes_robustos_vs_ols.csv` | Coeficientes clave por estimador |
| `outliers_huber_identificados.csv` | 35 meses downweighted por Huber |
| `comparacion_mejoras_explicacion.csv` | 5 extensiones: interacciones, asimetría, PCA, outliers, combinado |
| `mejoras_explicacion_parte2.csv` | PDL dólar, intervención, estimación robusta |
| `evaluacion_variables_candidatas.csv` | MICH, NFCI, T10Y2Y, STLFSI (ninguna aporta) |

El ECM es exploratorio: la prueba bounds no confirma cointegración al 5%, por lo que las especificaciones mensuales permanecen en diferencias.

## Variables internas de Colombia

La especificación integral añade el factor `Actividad y precios domésticos`, con `D.ln_ise_total_dane.L0` y `D.ln_ipc_colombia.L0` en la explicación histórica y `.L2` en el pronóstico. Ambas series cubren 244/244 meses de 2006-01 a 2026-04 y se mantienen sin imputación. GEIH, IPI e IPP se conservan como candidatas auditadas fuera de la matriz balanceada por cobertura incompleta. La trazabilidad completa está en `data/variables_internas_cobertura.csv`.

## Resultados globales y de horizonte largo

La base mensual global se integra como un factor agrupado en la explicación histórica para evitar una explosión de jugadores Shapley y controlar colinealidad. El factor `Condiciones financieras, commodities y actividad internacional` reúne 17 términos activos: rendimientos y expectativas de EE. UU., commodities, incertidumbre, condiciones financieras, desempleo, actividad industrial y fletes/logística. Sus series y transformaciones se describen en `data/base_global_mensual.csv` y su cobertura en `data/base_global_cobertura.csv`; high-yield, TED, `UNRATE` y China quedan como candidatos documentados cuando no cubren la muestra completa. No se imputa ningún faltante.

La señal `delta_actividad_us_12m` obtiene R² OOS de 12,8% a 12 meses (DM p = 0,006). La wavelet D3+D4+D5 alcanza 45,9% y el panel EM aproximadamente 43,8%. En el corto plazo diario, el mejor HAR con globales mensuales y señales globales adicionales tiene R² OOS de 13,4%, pero dirección de 41,2% y Sharpe −3,91. Estas métricas no son intercambiables: cada una corresponde a una frecuencia, horizonte y benchmark distintos.


- `D.variable` = primera diferencia mensual.
- `.L0` = contemporáneo; `.L1` = un mes de rezago.
- `ln` = logaritmo natural; `asinh` = seno hiperbólico inverso.
- Los errores estándar son HAC con ventana de 6 meses.
- Un p-valor bajo no demuestra causalidad.

## Metadatos

`metadata.json` resume muestra, métricas, parámetros del bootstrap, cobertura de vintages y SHA-256 de las instantáneas clave.
