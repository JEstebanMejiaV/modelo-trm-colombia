# Modelo econométrico de la TRM en Colombia

Modelo mensual de la tasa de cambio peso/dólar (TRM promedio mensual). Muestra: mayo 2006 – abril 2026 (240 obs. efectivas).
Dos productos independientes: uno explica ex post, otro intenta pronosticar. El primero funciona; el segundo no supera la caminata aleatoria.

---

# Parte A — Explicar la TRM

El marco macroeconómico integral distribuye la variación mensual entre 14 factores macroeconómicos usando información contemporánea y rezagada. Incluye el factor interno **Actividad y precios domésticos**, construido con el ISE total DANE y el IPC Colombia, además de los controles externos, financieros, regionales y globales. Las cifras de ajuste y los pesos se regeneran automáticamente desde los resultados versionados.

## Coeficientes del marco macroeconómico integral

<!-- AUTO:coeficientes_marco_macro_integral -->
| Término | Coeficiente | p-valor |
|---|---:|---:|
| Constante | 0,00567 | 0,0103 |
| Δln términos de intercambio, mes actual | 0,01482 | 0,7322 |
| Δln remesas 12 meses, rezago 1 | 0,19704 | 0,0571 |
| Δ diferencial de tasas, rezago 1 | 0,00345 | 0,5264 |
| Δ déficit fiscal 12 meses/PIB, rezago 1 | −0,00012 | 0,9714 |
| Δln dólar amplio, mes actual | 0,20247 | 0,2746 |
| Δln VIX, mes actual | 0,01656 | 0,1121 |
| Δ EMBIG Colombia (pp), mes actual | 0,02779 | 0,0104 |
| Δln reservas netas sin FLAR, rezago 1 | −0,23794 | 0,0487 |
| Δ asinh(balanza comercial), rezago 1 | 0,05473 | <0,0001 |
| Δ asinh(flujos de capital), rezago 1 | 0,00060 | 0,8380 |
| Δ diferencial BEI 5 años (pp), rezago 1 | −0,00172 | 0,6793 |
| `D.ln_ise_total_dane.L0` | −0,21001 | 0,0187 |
| `D.ln_ipc_colombia.L0` | −0,70708 | 0,0561 |
| Factor regional BRL+CLP+MXN+PEN, mes actual | 0,01614 | <0,0001 |
| `D.yield_real_10y_tips_pct.L0` | −285,78701 | 0,3113 |
| `D.yield_real_5y_us_pct.L0` | −0,09764 | 0,1208 |
| `D.yield_2y_us_pct.L0` | −415,41215 | 0,1054 |
| `D.yield_10y_us_pct.L0` | 701,29852 | 0,0304 |
| `D.spread_10y_2y_us_pct.L0` | −415,45712 | 0,1053 |
| `D.breakeven_5y_us_pct.L0` | −0,10213 | 0,0980 |
| `D.breakeven_10y_us_pct.L0` | −285,71881 | 0,3114 |
| `D.epu_global.L0` | −0,00002 | 0,5317 |
| `D.estres_financiero_stl.L0` | 0,00342 | 0,5641 |
| `D.nfci_chicago.L0` | 0,02482 | 0,6076 |
| `D.anfci_chicago.L0` | −0,04764 | 0,2327 |
| `D.ln_brent_global.L0` | −0,01447 | 0,6360 |
| `D.ln_commodities_global.L0` | −0,16719 | 0,0084 |
| `D.desempleo_us_pct.L0` | −0,01132 | 0,0376 |
| `D.ln_empleo_manufactura_us.L0` | 0,08917 | 0,8764 |
| `D.ln_produccion_industrial_us.L0` | −0,57942 | 0,1017 |
| `D.ln_fletes_transporte_us.L0` | 0,24884 | 0,0585 |
| Pandemia marzo–mayo 2020 | −0,00267 | 0,7999 |
<!-- /AUTO:coeficientes_marco_macro_integral -->

## Descomposición Shapley (peso de cada factor)

Se calculan los **16.384 subconjuntos** posibles y se promedia el aporte marginal en todos los órdenes de entrada. El bloque fijo (intercepto + pandemia) y los 14 factores se reportan con la misma convención descriptiva; la tabla siguiente se actualiza automáticamente al reestimar.

<!-- AUTO:pesos_shapley -->
| Factor | Peso entre los 14 factores | Aporte al R² |
|---|---:|---:|
| Monedas regionales | 23,55% | 15,72 p,p, |
| Condiciones financieras, commodities y actividad internacional | 21,63% | 14,44 p,p, |
| Dólar amplio | 15,11% | 10,09 p,p, |
| Riesgo soberano EMBIG Colombia | 14,12% | 9,43 p,p, |
| Balanza comercial cambiaria | 6,36% | 4,25 p,p, |
| VIX | 6,10% | 4,07 p,p, |
| Términos de intercambio | 4,15% | 2,77 p,p, |
| Flujos netos de capital | 3,29% | 2,20 p,p, |
| Actividad y precios domésticos | 2,02% | 1,35 p,p, |
| Reservas internacionales | 1,94% | 1,30 p,p, |
| Remesas | 1,17% | 0,78 p,p, |
| Diferencial de compensación inflacionaria 5 años | 0,30% | 0,20 p,p, |
| Diferencial de tasas | 0,18% | 0,12 p,p, |
| Déficit fiscal | 0,09% | 0,06 p,p, |
<!-- /AUTO:pesos_shapley -->

<!-- AUTO:bootstrap_intervalos -->
La incertidumbre se evalúa con 200 réplicas de un *bootstrap* circular de bloques de 12 meses. Los intervalos percentiles del 95% de los tres factores principales son: Monedas regionales, **16,63%–27,30%**; Condiciones financieras, commodities y actividad internacional, **17,56%–31,73%**; Dólar amplio, **8,74%–20,85%**. Son intervalos de la asignación Shapley bajo remuestreo temporal, no intervalos de un efecto causal.
<!-- /AUTO:bootstrap_intervalos -->

## Comparación de especificaciones descriptivas

<!-- AUTO:comparacion_especificaciones -->
| Métrica | Controles externos y financieros | Marco macroeconómico integral |
|---|---:|---:|
| Observaciones efectivas | 240 | 240 |
| R² | 49,45% | 68,54% |
| R² ajustado | 47,92% | 63,67% |
| MAPE, validación condicional de 48 meses | 2,01% | 1,49% |
| Acierto de dirección | 68,75% | 83,33% |
| R² condicional frente a caminata aleatoria | 31,92% | 56,87% |
<!-- /AUTO:comparacion_especificaciones -->

## Controles externos y financieros

<!-- AUTO:coeficientes_controles_externos -->
| Término | Coeficiente | p-valor HAC | Lectura aproximada |
|---|---:|---:|---|
| Constante | −0,00059 | 0,7250 | No hay evidencia de una deriva mensual adicional. |
| Δln términos de intercambio, mes actual | −0,10008 | 0,0007 | Una mejora de 10% se asocia con una TRM cerca de 100.1% menor. |
| Δln remesas 12 meses, rezago 1 | 0,27652 | 0,0243 | Un aumento de 10% se asocia con una TRM cerca de 276.5% mayor; el signo contrario al canal simple de oferta de divisas aconseja cautela por endogeneidad. |
| Δ diferencial de tasas, rezago 1 | −0,00990 | 0,0436 | Un aumento de 1 punto porcentual en el cambio del diferencial se asocia con una TRM cerca de 0.99% menor. |
| Δ déficit fiscal 12 meses/PIB, rezago 1 | 0,00485 | 0,1447 | Un aumento de 1 punto porcentual se asocia con una TRM cerca de 0.48% mayor, pero la estimación no es precisa al 5%. |
| Δln dólar amplio, mes actual | 1,27461 | <0,0001 | Un aumento de 1% del dólar global se asocia con una TRM cerca de 127.46% mayor. |
| Δln VIX, mes actual | 0,03836 | <0,0001 | Un aumento de 10% del VIX se asocia con una TRM cerca de 38.36% mayor. |
| Pandemia marzo–mayo 2020 | 0,01081 | 0,0200 | Se asocia con una TRM alrededor de 1.1% mayor, condicionado a los demás factores. |
<!-- /AUTO:coeficientes_controles_externos -->

<!-- AUTO:metricas_controles_externos -->
- MAPE condicional: **2,01%**.
- Acierto de dirección: **68,75%**.
- R² condicional frente a caminata aleatoria: **0,32%**.
<!-- /AUTO:metricas_controles_externos -->

## Robustez y estabilidad

Un modelo combinado (interacciones + asimetría + outliers) eleva el R² a 66% y resuelve la heterocedasticidad ARCH. La jerarquía Shapley es robusta en submuestras (Spearman 0,91–0,98), pero los coeficientes individuales son inestables: rolling window de 120 meses muestra que 10/14 cambian significativamente entre mitades.

## Variables internas de Colombia

La especificación integral activa un único factor descriptivo de **Actividad y precios domésticos** para evitar colinealidad entre indicadores sectoriales. Sus términos históricos son `D.ln_ise_total_dane.L0` y `D.ln_ipc_colombia.L0`; en el pronóstico ambos usan `L2`. El ISE total DANE y el IPC Colombia cubren los **244 meses** de enero de 2006 a abril de 2026 y se incorporan sin ceros, interpolaciones, extrapolaciones ni empalmes artificiales. GEIH, IPI e IPP permanecen auditados como candidatos porque no cubren toda la muestra. La matriz completa de cobertura está en [`data/variables_internas_cobertura.csv`](data/variables_internas_cobertura.csv).

---

# Parte B — Pronosticar la TRM

El modelo de pronóstico usa los 14 factores agrupados con rezagos de publicación (1–3 meses según disponibilidad). No emplea información contemporánea del mes objetivo.

## Resultado: no supera la caminata aleatoria

<!-- AUTO:metricas_pronostico -->
La validación expansiva de 48 meses obtiene MAPE de **2,49%**, acierto de dirección de **52,08%** y R² frente a la caminata aleatoria de **−1,46%**. La caminata obtiene MAPE de **2,39%**. Es decir, la ecuación explicativa no se convierte automáticamente en un buen pronóstico y, con esta información, el benchmark simple sigue siendo superior.
<!-- /AUTO:metricas_pronostico -->

## Evaluaciones adicionales

| Prueba | Resultado |
|---|---|
| Diebold-Mariano vs caminata | p = 0,21 — no se rechaza igualdad |
| Top-3 parsimonioso (mejor BIC) | MAPE 2,57% — tampoco supera la caminata |
| Combinación 50/50 con caminata | Sin mejora |
| Multihorizonte h=1,2,3,6 | R² negativo en todos los plazos |
| Threshold regression (VIX, dólar, EMBIG) | Sin regímenes significativos |

La relación entre factores y TRM es lineal pero con coeficientes que cambian en el tiempo. No hay no-linealidades explotables en el pronóstico mensual rezagado.

## Pronóstico corto y largo plazo con variables globales

El pronóstico diario se recalculó incorporando señales mensuales de mercados, condiciones financieras, commodities, actividad y logística con rezagos de disponibilidad. El mejor modelo diario, HAR con globales mensuales, alcanza R² OOS de **13,41%**, pero su acierto direccional es **41,2%** y su Sharpe anualizado **−3,91**; por tanto, no se presenta como una estrategia rentable ni como éxito direccional.

A horizontes largos, la señal `delta_actividad_us_12m` obtiene R² OOS de **12,8%** a 12 meses y prueba DM con p = **0,006**. La descomposición wavelet D3+D4+D5 alcanza **45,9%** de R² OOS, mientras que el panel EM recalculado alcanza aproximadamente **43,8%**. Estos resultados son señales de horizonte largo y no deben mezclarse con el pronóstico mensual de corto plazo.

La volatilidad se recalculó con especificaciones GARCH y VIX: **GARCH + VIX** tiene el menor BIC. En el backtest de VaR al 95% registra 31 violaciones de 500 observaciones (**6,2%**, frente a 5% esperado). La evidencia es útil para medir riesgo, no constituye recomendación de inversión.

La base global mensual activa reúne 17 componentes balanceados: rendimientos reales y nominales de EE. UU., expectativas de inflación a 5 y 10 años, pendiente 10Y–2Y, Brent, commodities, incertidumbre de política económica, STLFSI, NFCI, ANFCI, desempleo estadounidense `LRUN64TTUSM156S`, empleo manufacturero, producción industrial y fletes/logística. High-yield, TED, `UNRATE` y los indicadores de China se conservan como candidatos con cobertura incompleta o faltantes publicados; no se imputan ni entran al modelo balanceado. La cobertura completa se audita en `data/base_global_cobertura.csv`. El bloque se mantiene agrupado para controlar colinealidad y conservar una descomposición Shapley tractable con 14 jugadores.

**Conclusión:** las variables globales mejoran la explicación histórica y aportan señales específicas a horizontes largos, pero el pronóstico mensual disponible ex ante continúa por debajo de la caminata aleatoria.

---

# Gráficos

Cinco PNGs en `deliverables/graficos/`:

1. **Descomposición Shapley** — barras horizontales con intervalos bootstrap.
2. **Desempeño de los modelos** — explicación histórica, pronóstico mensual y benchmark.
3. **Validación de la TRM** — realizaciones, ajustes, pronóstico y caminata aleatoria.
4. **Efectos típicos estandarizados** — asociaciones parciales del marco macroeconómico integral; el factor global agrupado aparece como una sola fila.
5. **ECM y elasticidades** — corto plazo, largo plazo y velocidad de ajuste.

Ver [`deliverables/graficos/README.md`](deliverables/graficos/README.md) para cautelas de lectura.

---

# Estructura del proyecto

```
modelo-trm-colombia/
├── configs/              Configuración común y contratos por producto
├── data/
│   ├── raw/              Fuentes originales versionadas
│   ├── catalog/          Registro canónico de fuentes
│   └── vintages/         Snapshots inmutables y cobertura histórica
├── deliverables/         Workbook y gráficos publicables
├── pipelines/            Wrappers y manifests de productos
├── research/             Señales exploratorias y manifests long-term
├── results/              Exportador legacy + output_catalog.json
├── schemas/              Contratos JSON ejecutables
├── src/
│   ├── trm_model/        Paquete instalable, CLI y provenance
│   ├── model/            Econometría mensual validada, conservada
│   ├── forecast_daily/   Producto diario opcional
│   ├── forecast_longterm/ Investigación separada
│   └── estimate_model.py Entry point legacy compatible
├── tests/                Smoke/contract tests
├── pyproject.toml        Instalación y extras opcionales
├── requirements.lock     Runtime base + QA fijado
└── requirements-optional.lock  ML/RNN/wavelets/riesgo opcional
```

---

# Reproducir

## Alcance de la distribución instalable

El wheel contiene el código Python y los entry points (`trm-model`, `trm-monthly` y
los wrappers opcionales), pero no empaqueta `data/raw`, `data/catalog`,
`configs/`, `schemas/`, `results/` ni los manifests del checkout. Por diseño, la
CLI de validación y la estimación son **checkout-bound**: ejecútelas desde la raíz
del repositorio o defina `TRM_MODEL_ROOT` apuntando a un checkout completo. El
wheel se prueba fuera del checkout para importación y entry points; la
reproducción de datos, contratos y resultados se valida contra el repositorio
versionado.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
python -m pip install -e . --no-deps
trm-model validate
python -m pytest
trm-model run-monthly
python .\src\build_charts.py
```

`trm-model run-monthly` conserva el entry point legacy, escribe los CSV existentes
y registra un manifest de corrida en `artifacts/runs/<run_id>/manifest.json`.
También sigue disponible `python .\src\estimate_model.py` para compatibilidad.
Los productos diario, volatilidad y long-term tienen wrappers en `pipelines/` y
requieren sus extras opcionales. No se descarga ninguna fuente durante una
estimación; para FRED, defina `FRED_API_KEY` solo al ejecutar descargas.

Los datos fuente están en `data/raw/`. El detalle de cada serie está en [`data/README.md`](data/README.md).

---

# Fuentes

| Serie | Proveedor | Frecuencia |
|---|---|---|
| TRM | BanRep (serie 1) | Diaria → mensual |
| Términos de intercambio | BanRep (serie 15360) | Mensual |
| Dólar amplio (DTWEXBGS) | Federal Reserve / FRED | Diaria → mensual |
| VIX (VIXCLS) | Cboe / FRED | Diaria → mensual |
| Federal funds (FEDFUNDS) | Federal Reserve / FRED | Mensual |
| Tasa de política | BanRep (serie 59) | Diaria → mensual |
| Remesas | BanRep (serie 15363) | Mensual |
| Déficit fiscal GNC | MinHacienda | Mensual |
| EMBIG Colombia (PD04715XD) | BCRPData | Diaria → mensual |
| Reservas netas sin FLAR | BanRep (serie 15053) | Mensual |
| Balanza comercial cambiaria | BanRep (serie 16702) | Mensual |
| Movimientos netos de capital | BanRep (serie 16706) | Mensual |
| TES 5Y nominal / UVR | BanRep (series 15273, 15276) | Diaria → mensual |
| BEI 5Y EE.UU. (BKEVEN05) | Fed Board (GSW) | Diaria → mensual |
| BRL, CLP, MXN por USD | OECD / FRED | Mensual |
| PEN por USD (PN01207PM) | BCRPData | Mensual |

Detalle completo de URLs, transformaciones y rezagos en [`data/README.md`](data/README.md).
