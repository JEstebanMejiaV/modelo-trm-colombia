# Modelo econométrico de la TRM en Colombia

Modelo mensual de la tasa de cambio peso/dólar (TRM promedio mensual). Muestra: mayo 2006 – abril 2026 (240 obs. efectivas).
Dos productos independientes: uno explica ex post, otro intenta pronosticar. El primero funciona; el segundo no supera la caminata aleatoria.

---

# Parte A — Explicar la TRM

El modelo ampliado distribuye la variación mensual entre 13 factores macroeconómicos usando información contemporánea y rezagada. R² ajustado: **62,80%** (R² sin ajustar: 67,47%). Los principales bloques son monedas regionales (24,59%), condiciones financieras, commodities y actividad internacional (21,62%), dólar amplio (15,46%) y EMBIG Colombia (14,26%); juntos concentran 75,93% del peso entre factores.

## Coeficientes del modelo ampliado

<!-- AUTO:coeficientes_ampliado -->
| Término | Coeficiente | p-valor |
|---|---:|---:|
| Constante | 0,00249 | 0,1712 |
| Δln términos de intercambio, mes actual | 0,01682 | 0,6915 |
| Δln remesas 12 meses, rezago 1 | 0,16805 | 0,1388 |
| Δ diferencial de tasas, rezago 1 | 0,00109 | 0,8366 |
| Δ déficit fiscal 12 meses/PIB, rezago 1 | 0,00003 | 0,9938 |
| Δln dólar amplio, mes actual | 0,16176 | 0,3627 |
| Δln VIX, mes actual | 0,01464 | 0,1687 |
| Δ EMBIG Colombia (pp), mes actual | 0,02478 | 0,0204 |
| Δln reservas netas sin FLAR, rezago 1 | −0,25123 | 0,0381 |
| Δ asinh(balanza comercial), rezago 1 | 0,05448 | <0,0001 |
| Δ asinh(flujos de capital), rezago 1 | 0,00066 | 0,8324 |
| Δ diferencial BEI 5 años (pp), rezago 1 | −0,00240 | 0,5755 |
| Factor regional BRL+CLP+MXN+PEN, mes actual | 0,01758 | <0,0001 |
| `D.yield_real_10y_tips_pct.L0` | −344,51234 | 0,2405 |
| `D.yield_real_5y_us_pct.L0` | −0,09219 | 0,1268 |
| `D.yield_2y_us_pct.L0` | −325,01023 | 0,2153 |
| `D.yield_10y_us_pct.L0` | 669,61408 | 0,0373 |
| `D.spread_10y_2y_us_pct.L0` | −325,05115 | 0,2152 |
| `D.breakeven_5y_us_pct.L0` | −0,10116 | 0,0839 |
| `D.breakeven_10y_us_pct.L0` | −344,43964 | 0,2406 |
| `D.epu_global.L0` | −0,00001 | 0,6528 |
| `D.estres_financiero_stl.L0` | 0,00383 | 0,5106 |
| `D.nfci_chicago.L0` | 0,02803 | 0,5832 |
| `D.anfci_chicago.L0` | −0,04698 | 0,2677 |
| `D.ln_brent_global.L0` | −0,02448 | 0,4578 |
| `D.ln_commodities_global.L0` | −0,15359 | 0,0160 |
| `D.desempleo_us_pct.L0` | −0,00915 | 0,0916 |
| `D.ln_empleo_manufactura_us.L0` | 0,05646 | 0,9271 |
| `D.ln_produccion_industrial_us.L0` | −0,54247 | 0,1272 |
| `D.ln_fletes_transporte_us.L0` | 0,22241 | 0,0922 |
| Pandemia marzo–mayo 2020 | 0,00515 | 0,5874 |
<!-- /AUTO:coeficientes_ampliado -->

## Descomposición Shapley (peso de cada factor)

Se calculan los **8.192 subconjuntos** posibles y se promedia el aporte marginal en todos los órdenes de entrada. El bloque fijo (intercepto + pandemia) explica 1,78%; los 13 factores agregan 65,69 p.p.

<!-- AUTO:pesos_shapley -->
| Factor | Peso entre los 13 factores | Aporte al R² |
|---|---:|---:|
| Monedas regionales | 24,59% | 16,15 p.p. |
| Condiciones financieras, commodities y actividad internacional | 21,62% | 14,20 p.p. |
| Dólar amplio | 15,46% | 10,15 p.p. |
| Riesgo soberano EMBIG Colombia | 14,26% | 9,37 p.p. |
| Balanza comercial cambiaria | 6,47% | 4,25 p.p. |
| VIX | 6,12% | 4,02 p.p. |
| Términos de intercambio | 4,29% | 2,82 p.p. |
| Flujos netos de capital | 3,40% | 2,24 p.p. |
| Reservas internacionales | 2,03% | 1,33 p.p. |
| Remesas | 1,15% | 0,75 p.p. |
| Diferencial de compensación inflacionaria 5 años | 0,32% | 0,21 p.p. |
| Diferencial de tasas | 0,20% | 0,13 p.p. |
| Déficit fiscal | 0,10% | 0,06 p.p. |
<!-- /AUTO:pesos_shapley -->

<!-- AUTO:bootstrap_intervalos -->
La incertidumbre se evalúa con 200 réplicas de un *bootstrap* circular de bloques de 12 meses. Los intervalos percentiles del 95% de los tres factores principales son: Monedas regionales, **17,68%–28,59%**; Condiciones financieras, commodities y actividad internacional, **18,18%–30,36%**; Dólar amplio, **9,05%–19,64%**. Son intervalos de la asignación Shapley bajo remuestreo temporal, no intervalos de un efecto causal.
<!-- /AUTO:bootstrap_intervalos -->

## Comparación principal vs ampliado

<!-- AUTO:comparacion_modelos -->
| Métrica | Modelo principal | Modelo ampliado |
|---|---:|---:|
| Observaciones efectivas | 240 | 240 |
| R² | 49,45% | 67,47% |
| R² ajustado | 47,92% | 62,80% |
| MAPE, validación condicional de 48 meses | 2,01% | 1,51% |
| Acierto de dirección | 68,75% | 83,33% |
| R² condicional frente a caminata aleatoria | 31,92% | 55,07% |
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
- R² condicional frente a caminata aleatoria: **31,92%**.
<!-- /AUTO:metricas_principal -->

## Robustez y estabilidad

Un modelo combinado (interacciones + asimetría + outliers) eleva el R² a 66% y resuelve la heterocedasticidad ARCH. La jerarquía Shapley es robusta en submuestras (Spearman 0,91–0,98), pero los coeficientes individuales son inestables: rolling window de 120 meses muestra que 10/14 cambian significativamente entre mitades.

---

# Parte B — Pronosticar la TRM

El modelo de pronóstico usa los 13 factores agrupados con rezagos de publicación (1–3 meses según disponibilidad). No emplea información contemporánea del mes objetivo.

## Resultado: no supera la caminata aleatoria

<!-- AUTO:metricas_pronostico -->
La validación expansiva de 48 meses obtiene MAPE de **2,58%**, acierto de dirección de **50,00%** y R² frente a la caminata aleatoria de **−4,84%**. La caminata obtiene MAPE de **2,39%**. Es decir, la ecuación explicativa no se convierte automáticamente en un buen pronóstico y, con esta información, el benchmark simple sigue siendo superior.
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

La base global mensual activa reúne 17 componentes balanceados: rendimientos reales y nominales de EE. UU., expectativas de inflación a 5 y 10 años, pendiente 10Y–2Y, Brent, commodities, incertidumbre de política económica, STLFSI, NFCI, ANFCI, desempleo estadounidense `LRUN64TTUSM156S`, empleo manufacturero, producción industrial y fletes/logística. High-yield, TED, `UNRATE` y los indicadores de China se conservan como candidatos con cobertura incompleta o faltantes publicados; no se imputan ni entran al modelo balanceado. La cobertura completa se audita en `data/base_global_cobertura.csv`. El bloque se mantiene agrupado para controlar colinealidad y conservar una descomposición Shapley tractable con 13 jugadores.

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
