# Modelo econométrico de la TRM en Colombia

Modelo mensual de la tasa de cambio peso/dólar (TRM promedio mensual). Muestra: mayo 2006 – abril 2026 (240 obs. efectivas).
Dos productos independientes: uno explica ex post, otro intenta pronosticar. El primero funciona; el segundo no supera la caminata aleatoria.

---

# Parte A — Explicar la TRM

El modelo ampliado distribuye la variación mensual entre 12 factores macroeconómicos usando información contemporánea y rezagada. R² ajustado: **58,52%** (R² sin ajustar: 60,77%). Los tres factores principales — monedas regionales (30%), dólar amplio (20%) y EMBIG Colombia (18%) — capturan el 68% del poder explicativo total.

## Coeficientes del modelo ampliado

<!-- AUTO:coeficientes_ampliado -->
| Término | Coeficiente | p-valor |
|---|---:|---:|
| Constante | 0,00318 | 0,0945 |
| Δln términos de intercambio, mes actual | −0,09186 | 0,0014 |
| Δln remesas 12 meses, rezago 1 | 0,10076 | 0,3217 |
| Δ diferencial de tasas, rezago 1 | −0,00496 | 0,2946 |
| Δ déficit fiscal 12 meses/PIB, rezago 1 | −0,00075 | 0,8276 |
| Δln dólar amplio, mes actual | 0,24145 | 0,2524 |
| Δln VIX, mes actual | 0,01144 | 0,2422 |
| Δ EMBIG Colombia (pp), mes actual | 0,01710 | 0,1323 |
| Δln reservas netas sin FLAR, rezago 1 | −0,29366 | 0,0131 |
| Δ asinh(balanza comercial), rezago 1 | 0,04699 | <0,0001 |
| Δ asinh(flujos de capital), rezago 1 | 0,00065 | 0,8505 |
| Δ diferencial BEI 5 años (pp), rezago 1 | −0,00627 | 0,1771 |
| Factor regional BRL+CLP+MXN+PEN, mes actual | 0,01653 | <0,0001 |
| Pandemia marzo–mayo 2020 | −0,00272 | 0,6686 |
<!-- /AUTO:coeficientes_ampliado -->

## Descomposición Shapley (peso de cada factor)

Se calculan los 4.096 subconjuntos posibles y se promedia el aporte marginal en todos los órdenes de entrada. El bloque fijo (intercepto + pandemia) explica 1,78%; los 12 factores agregan 58,99 p.p.

<!-- AUTO:pesos_shapley -->
| Factor | Peso entre los 12 factores | Aporte al R² |
|---|---:|---:|
| Monedas regionales | 30,13% | 17,77 p,p, |
| Dólar amplio | 20,13% | 11,88 p,p, |
| Riesgo soberano EMBIG Colombia | 18,22% | 10,75 p,p, |
| VIX | 8,32% | 4,91 p,p, |
| Balanza comercial cambiaria | 7,37% | 4,35 p,p, |
| Términos de intercambio | 6,73% | 3,97 p,p, |
| Flujos netos de capital | 4,22% | 2,49 p,p, |
| Reservas internacionales | 2,58% | 1,52 p,p, |
| Remesas | 1,15% | 0,68 p,p, |
| Diferencial de compensación inflacionaria 5 años | 0,59% | 0,35 p,p, |
| Diferencial de tasas | 0,43% | 0,26 p,p, |
| Déficit fiscal | 0,13% | 0,07 p,p, |
<!-- /AUTO:pesos_shapley -->

<!-- AUTO:bootstrap_intervalos -->
La incertidumbre se evalúa con 200 réplicas de un *bootstrap* circular de bloques de 12 meses. Los intervalos percentiles del 95% de los tres factores principales son: Monedas regionales, **21,65%–34,72%**; Dólar amplio, **12,02%–26,98%**; Riesgo soberano EMBIG Colombia, **12,33%–26,56%**. Son intervalos de la asignación Shapley bajo remuestreo temporal, no intervalos de un efecto causal.
<!-- /AUTO:bootstrap_intervalos -->

## Comparación principal vs ampliado

<!-- AUTO:comparacion_modelos -->
| Métrica | Modelo principal | Modelo ampliado |
|---|---:|---:|
| Observaciones efectivas | 240 | 240 |
| R² | 49,45% | 60,77% |
| R² ajustado | 47,92% | 58,52% |
| MAPE, validación condicional de 48 meses | 2,01% | 1,70% |
| Acierto de dirección | 68,75% | 81,25% |
| R² condicional frente a caminata aleatoria | 31,92% | 47,42% |
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

El modelo de pronóstico usa los mismos 12 factores con rezagos de publicación (1–3 meses según disponibilidad). No emplea información contemporánea del mes objetivo.

## Resultado: no supera la caminata aleatoria

<!-- AUTO:metricas_pronostico -->
La validación expansiva de 48 meses obtiene MAPE de **2,63%**, acierto de dirección de **52,08%** y R² frente a la caminata aleatoria de **−10,98%**. La caminata obtiene MAPE de **2,39%**. Es decir, la ecuación explicativa no se convierte automáticamente en un buen pronóstico y, con esta información, el benchmark simple sigue siendo superior.
<!-- /AUTO:metricas_pronostico -->

## Evaluaciones adicionales

| Prueba | Resultado |
|---|---|
| Diebold-Mariano vs caminata | p = 0,21 — no se rechaza igualdad |
| Top-3 parsimonioso (mejor BIC) | MAPE 2,57% — tampoco supera la caminata |
| Combinación 50/50 con caminata | Sin mejora |
| Multihorizonte h=1,2,3,6 | R² negativo en todos los plazos |
| Threshold regression (VIX, dólar, EMBIG) | Sin regímenes significativos |

La relación entre factores y TRM es lineal pero con coeficientes que cambian en el tiempo. No hay no-linealidades explotables.

**Conclusión:** la TRM mensual es esencialmente imprevisible con estos factores macroeconómicos rezagados.

---

# Gráficos

Cinco PNGs en `graficos/`:

1. **Descomposición Shapley** — barras horizontales con intervalos bootstrap.
2. **Ajuste del modelo ampliado** — Δln(TRM) observado vs ajustado.
3. **Pronóstico vs caminata** — comparación de errores acumulados.
4. **Rolling window** — evolución temporal de coeficientes clave.
5. **Estabilidad de rangos** — Spearman por submuestra.

Ver [`graficos/README.md`](graficos/README.md) para cautelas de lectura.

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
