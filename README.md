# Modelo econométrico de la TRM en Colombia

Modelo mensual de la tasa de cambio peso/dólar (TRM promedio mensual). Muestra: mayo 2006 – abril 2026 (240 obs. efectivas).
Dos productos independientes: uno explica ex post, otro intenta pronosticar. El primero funciona; el segundo no supera la caminata aleatoria.

---

# Parte A — Explicar la TRM

El modelo ampliado distribuye la variación mensual entre 13 factores macroeconómicos usando información contemporánea y rezagada. R² ajustado: **61,10%** (R² sin ajustar: 64,84%). Los principales bloques son monedas regionales (25,59%), variables globales nuevas (17,33%), dólar amplio (16,30%) y EMBIG Colombia (14,98%); juntos concentran 74,20% del peso entre factores.

## Coeficientes del modelo ampliado

<!-- AUTO:coeficientes_ampliado -->
| Término | Coeficiente | p-valor |
|---|---:|---:|
| Constante | 0,00322 | 0,0858 |
| Δln términos de intercambio, mes actual | −0,03918 | 0,2491 |
| Δln remesas 12 meses, rezago 1 | 0,15426 | 0,2153 |
| Δ diferencial de tasas, rezago 1 | −0,00353 | 0,4707 |
| Δ déficit fiscal 12 meses/PIB, rezago 1 | 0,00012 | 0,9708 |
| Δln dólar amplio, mes actual | 0,18804 | 0,4020 |
| Δln VIX, mes actual | 0,01948 | 0,0756 |
| Δ EMBIG Colombia (pp), mes actual | 0,02433 | 0,0196 |
| Δln reservas netas sin FLAR, rezago 1 | −0,22791 | 0,0804 |
| Δ asinh(balanza comercial), rezago 1 | 0,05237 | <0,0001 |
| Δ asinh(flujos de capital), rezago 1 | 0,00129 | 0,7217 |
| Δ diferencial BEI 5 años (pp), rezago 1 | −0,00472 | 0,2299 |
| Factor regional BRL+CLP+MXN+PEN, mes actual | 0,01679 | <0,0001 |
| `D.yield_real_10y_tips_pct.L0` | −0,05899 | 0,0131 |
| `D.yield_2y_us_pct.L0` | −489,29009 | 0,0364 |
| `D.yield_10y_us_pct.L0` | 489,34280 | 0,0364 |
| `D.spread_10y_2y_us_pct.L0` | −489,28232 | 0,0364 |
| `D.ln_brent_global.L0` | −0,01855 | 0,5520 |
| `D.ln_commodities_global.L0` | −0,13545 | 0,0290 |
| `D.epu_global.L0` | −0,00001 | 0,6577 |
| `D.estres_financiero_stl.L0` | −0,00427 | 0,3587 |
| `D.ln_empleo_manufactura_us.L0` | 0,81522 | 0,0108 |
| `D.ln_produccion_industrial_us.L0` | −0,34897 | 0,2242 |
| Pandemia marzo–mayo 2020 | −0,00086 | 0,9222 |
<!-- /AUTO:coeficientes_ampliado -->

## Descomposición Shapley (peso de cada factor)

Se calculan los **8.192 subconjuntos** posibles y se promedia el aporte marginal en todos los órdenes de entrada. El bloque fijo (intercepto + pandemia) explica 1,78%; los 13 factores agregan 63,06 p.p.

<!-- AUTO:pesos_shapley -->
| Factor | Peso entre los 13 factores | Aporte al R² |
|---|---:|---:|
| Monedas regionales | 25,59% | 16,14 p,p, |
| Variables globales nuevas | 17,33% | 10,93 p,p, |
| Dólar amplio | 16,30% | 10,28 p,p, |
| Riesgo soberano EMBIG Colombia | 14,98% | 9,45 p,p, |
| Balanza comercial cambiaria | 6,84% | 4,31 p,p, |
| VIX | 6,71% | 4,23 p,p, |
| Términos de intercambio | 4,63% | 2,92 p,p, |
| Flujos netos de capital | 3,55% | 2,24 p,p, |
| Reservas internacionales | 2,02% | 1,28 p,p, |
| Remesas | 1,14% | 0,72 p,p, |
| Diferencial de compensación inflacionaria 5 años | 0,47% | 0,30 p,p, |
| Diferencial de tasas | 0,30% | 0,19 p,p, |
| Déficit fiscal | 0,13% | 0,08 p,p, |
<!-- /AUTO:pesos_shapley -->

<!-- AUTO:bootstrap_intervalos -->
La incertidumbre se evalúa con 200 réplicas de un *bootstrap* circular de bloques de 12 meses. Los intervalos percentiles del 95% de los tres factores principales son: Monedas regionales, **18,64%–31,13%**; Variables globales nuevas, **13,10%–25,82%**; Dólar amplio, **9,56%–21,27%**. Son intervalos de la asignación Shapley bajo remuestreo temporal, no intervalos de un efecto causal.
<!-- /AUTO:bootstrap_intervalos -->

## Comparación principal vs ampliado

<!-- AUTO:comparacion_modelos -->
| Métrica | Modelo principal | Modelo ampliado |
|---|---:|---:|
| Observaciones efectivas | 240 | 240 |
| R² | 49,45% | 64,84% |
| R² ajustado | 47,92% | 61,10% |
| MAPE, validación condicional de 48 meses | 2,01% | 1,62% |
| Acierto de dirección | 68,75% | 79,17% |
| R² condicional frente a caminata aleatoria | 31,92% | 48,40% |
<!-- /AUTO:comparacion_modelos -->

## Modelo principal (7 factores)

<!-- AUTO:coeficientes_principal -->
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
<!-- /AUTO:coeficientes_principal -->

<!-- AUTO:metricas_principal -->
- MAPE condicional: **2,01%**.
- Acierto de dirección: **68,75%**.
- R² condicional frente a caminata aleatoria: **0,32%**.
<!-- /AUTO:metricas_principal -->

## Robustez y estabilidad

Un modelo combinado (interacciones + asimetría + outliers) eleva el R² a 66% y resuelve la heterocedasticidad ARCH. La jerarquía Shapley es robusta en submuestras (Spearman 0,91–0,98), pero los coeficientes individuales son inestables: rolling window de 120 meses muestra que 10/14 cambian significativamente entre mitades.

---

# Parte B — Pronosticar la TRM

El modelo de pronóstico usa los 13 factores agrupados con rezagos de publicación (1–3 meses según disponibilidad). No emplea información contemporánea del mes objetivo.

## Resultado: no supera la caminata aleatoria

<!-- AUTO:metricas_pronostico -->
La validación expansiva de 48 meses obtiene MAPE de **2,68%**, acierto de dirección de **58,33%** y R² frente a la caminata aleatoria de **−13,38%**. La caminata obtiene MAPE de **2,39%**. Es decir, la ecuación explicativa no se convierte automáticamente en un buen pronóstico y, con esta información, el benchmark simple sigue siendo superior.
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

El pronóstico diario se recalculó incorporando cuatro señales mensuales globales rezagadas (`global_rates_mom`, `global_commodities_mom`, `global_risk_mom` y `global_activity_mom`). El mejor modelo diario, HAR con globales mensuales, alcanza R² OOS de **13,20%**, pero su acierto direccional es **41,6%** y su Sharpe anualizado **−4,03**; por tanto, no se presenta como una estrategia rentable ni como éxito direccional.

A horizontes largos, la señal `delta_actividad_us_12m` obtiene R² OOS de **12,8%** a 12 meses y prueba DM con p = **0,006**. La descomposición wavelet D3+D4+D5 alcanza **45,9%** de R² OOS, mientras que el panel EM recalculado alcanza aproximadamente **43,8%**. Estos resultados son señales de horizonte largo y no deben mezclarse con el pronóstico mensual de corto plazo.

La volatilidad se recalculó con especificaciones GARCH y VIX: **GARCH + VIX** tiene el menor BIC. En el backtest de VaR al 95% registra 31 violaciones de 500 observaciones (**6,2%**, frente a 5% esperado). La evidencia es útil para medir riesgo, no constituye recomendación de inversión.

La base global mensual activa reúne diez componentes FRED: tasas reales y nominales de EE. UU., pendiente 10Y–2Y, Brent, commodities, incertidumbre de política económica, estrés financiero de St. Louis, empleo manufacturero y producción industrial. Se excluyeron oro por error HTTP 400 del identificador solicitado y series con cobertura incompleta; desempleo de EE. UU. no entra por un faltante dentro de la muestra activa. El factor se mantiene agrupado para controlar colinealidad y conservar una descomposición Shapley tractable.

**Conclusión:** las variables globales mejoran la explicación histórica y aportan señales específicas a horizontes largos, pero el pronóstico mensual disponible ex ante continúa por debajo de la caminata aleatoria.

---

# Gráficos

Cinco PNGs en `deliverables/graficos/`:

1. **Descomposición Shapley** — barras horizontales con intervalos bootstrap.
2. **Desempeño de los modelos** — explicación histórica, pronóstico mensual y benchmark.
3. **Validación de la TRM** — realizaciones, ajustes, pronóstico y caminata aleatoria.
4. **Efectos típicos estandarizados** — asociaciones parciales del modelo ampliado; el factor global agrupado aparece como una sola fila.
5. **ECM y elasticidades** — corto plazo, largo plazo y velocidad de ajuste.

Ver [`deliverables/graficos/README.md`](deliverables/graficos/README.md) para cautelas de lectura.

---

# Estructura del proyecto

```
modelo-trm-colombia/
├── data/
│   ├── raw/                 19 fuentes activas
│   └── vintages/            Snapshots inmutables + ALFRED (8537 filas)
├── deliverables/
│   ├── modelo_trm_colombia.xlsx   Excel final (14 hojas)
│   └── graficos/                  5 PNGs explicativos + metadata
├── results/
│   ├── explicacion/         21 CSVs — modelos y Shapley
│   ├── pronostico/          16 CSVs — pronóstico y validación
│   └── robustez/            18 CSVs — ECM, BEI, rolling, threshold
├── src/
│   ├── model/               Paquete modular (9 módulos)
│   ├── exploration/         Scripts de exploración (no-pipeline)
│   ├── estimate_model.py    Orquestador principal
│   ├── build_charts.py      Genera los 5 PNGs
│   ├── build_workbook.mjs   Genera el Excel
│   ├── archive_vintage.py   Descarga y archiva vintages
│   └── check_*.py           3 scripts de validación
└── requirements.txt
```

---

# Reproducir

```powershell
pip install -r requirements.txt
python .\src\estimate_model.py
node .\src\build_workbook.mjs
python .\src\build_charts.py
```

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
