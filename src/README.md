# Código de estimación y construcción del archivo Excel

Esta carpeta contiene siete programas con responsabilidades separadas:

| Archivo | Función |
|---|---|
| `estimate_model.py` | Lee las fuentes, construye la base mensual, estima los modelos base, ampliado y de pronóstico, compara factores regionales 3–4, calcula validaciones, diagnósticos, pesos Shapley, intervalos por bloques y estabilidad por submuestras, y actualiza `data/` y `results/`. |
| `archive_vintage.py` | Crea snapshots inmutables por fecha de origen, recupera vintages históricos disponibles y genera la matriz de cobertura del pronóstico. |
| `check_outputs.py` | Comprueba integridad de datos, muestra común, conciliación Shapley y sincronización entre los CSV y el archivo Excel. |
| `check_reproducibility.py` | Compara los resultados regenerados con la versión comprometida usando tolerancias numéricas, para no confundir ruido de plataforma con un cambio econométrico. |
| `build_workbook.mjs` | Construye el archivo Excel, genera las 14 hojas, exporta vistas previas y actualiza `deliverables/modelo_trm_colombia.xlsx`. |
| `build_charts.py` | Construye cinco gráficos PNG independientes desde los CSV de `results/` y los guarda en `graficos/`. |
| `check_charts.py` | Verifica que los PNG tengan el formato esperado y correspondan a los CSV y al generador actual mediante huellas SHA-256. |

## Flujo del proyecto

```text
data/raw
   ↓
build_dataset()
   ↓
data/modelo_trm_datos_mensuales.csv
   ↓
modelo base + modelo ampliado histórico + pronóstico rezagado + ECM exploratorio
   ↓
results/*.csv y results/metadata.json
   ├──→ src/build_charts.py → graficos/*.png
   ↓
build_workbook.mjs
   ↓
deliverables/modelo_trm_colombia.xlsx
```

## Especificaciones econométricas

`BASE_FACTOR_SPECS`, `EXPANDED_FACTOR_SPECS_3/4` y `FORECAST_FACTOR_SPECS_3/4` declaran cada factor, su grupo, transformación y rezago. `make_timed_difference_design()` usa esas especificaciones para mantener una sola ruta de construcción.

- Factores contemporáneos del histórico: términos de intercambio, dólar amplio, VIX, EMBIG Colombia y factor regional de cuatro monedas.
- Factores rezagados un mes: remesas, diferencial de tasas, déficit fiscal, reservas, balanza cambiaria, capitales y primera diferencia del BEI a cinco años.
- Variable dependiente: cambio mensual del logaritmo de la TRM.
- Inferencia: OLS con errores estándar HAC de seis meses.
- Selección dinámica: BIC entre cero y tres rezagos de la variación de la TRM; la selección actual es cero.
- Comparación: modelo base y ampliado usan exactamente las mismas fechas efectivas.

Los términos de intercambio entran como `D.ln_terminos_intercambio.L0`; su rezago de publicación cercano a dos meses refuerza que el uso contemporáneo es explicativo *ex post*. El riesgo soberano entra como `D.embig_colombia_pp.L0`: se promedia diariamente el EMBIG Colombia de BCRPData y se convierte de puntos básicos a puntos porcentuales. Debe mantenerse la atribución a BCRPData y a sus fuentes originales Reuters/J.P. Morgan; la descarga pública no equivale a una licencia abierta sobre la metodología o la marca EMBIG.

El diferencial BEI a cinco años entra como `D.diferencial_bei_5y_pp.L1`. Para Colombia se restan los promedios mensuales de TES nominales y TES UVR al mismo horizonte; luego se resta la compensación estadounidense `BKEVEN05`. `build_bei_aggregations()` conserva también una versión limitada a fechas diarias comunes. `bei_stationarity_tests()` y `bei_trend_break_models()` evalúan constante, tendencia y quiebres; `bei_model_specification_comparison()` contrasta seis variantes sobre la misma muestra. Es una compensación de inflación de mercado, no una expectativa pura. Las fuentes, fórmulas y cautelas se detallan en [`data/README.md`](../data/README.md).

La temporización contemporánea hace que el modelo ampliado sea una explicación histórica o *nowcast*, no un pronóstico disponible antes de observar el mes. PEN, descargado de BCRPData `PN01207PM`, mejora BIC, R² ajustado y MAPE de esa explicación frente al factor de tres monedas.

El modelo de pronóstico usa `FORECAST_FACTOR_SPECS_3/4`: todos los factores económicos entran con uno a tres meses de rezago conforme a `FORECAST_AVAILABILITY`. BIC selecciona el factor de tres monedas y un rezago de `Δln(TRM)`. La validación es pseudo-tiempo-real porque respeta disponibilidad, pero usa el último *vintage* de las fuentes. Un backtest genuino exige reconstruir cada origen con las versiones que existían entonces.

En las validaciones recursivas se reestiman los coeficientes, pero se conserva la cantidad de rezagos seleccionada con la muestra completa. Además, el denominador fiscal anual usa la mediana del PIB implícito de todos los meses del año. Estas cautelas deben permanecer visibles.

## Pesos explicativos

`exact_shapley_r2()` calcula los 4.096 subconjuntos de 12 factores. Cada factor entra con todos sus términos y recibe su aporte marginal medio al R². El control automático exige que:

- los aportes sumen el R² incremental;
- los pesos entre factores sumen 100%;
- ningún aporte sea negativo dentro de la muestra actual;
- el archivo Excel coincida con los CSV versionados.

Los pesos son descriptivos. No identifican causalidad ni sustituyen pruebas de estabilidad por submuestras.

`block_bootstrap_shapley()` usa 200 réplicas de bloques circulares de 12 meses y 64 permutaciones antitéticas por réplica. `subsample_stability()` calcula Shapley exacto y coeficientes HAC en cinco cortes. La semilla fija hace reproducibles los intervalos, pero no elimina la incertidumbre de especificación.

## Archivo de vintages

`archive_vintage.py` no forma parte de la ejecución normal del estimador porque requiere acceso a los proveedores. Un snapshot completo se crea con `snapshot --origin-date`; las fechas existentes no se sobrescriben. `alfred-history` intenta recuperar los 48 orígenes, valida que cada observación sea anterior a su origen y reanuda desde caché, pero solo publica el consolidado cuando las 288 respuestas están completas. En esta actualización el proveedor cortó las conexiones, por lo que la cobertura sigue en cero. `coverage` regenera el CSV y CI valida las huellas versionadas sin volver a conectarse a Internet.

## Reproducción

Desde la raíz del repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python .\src\estimate_model.py
python .\src\build_charts.py
```

La construcción del archivo Excel requiere un entorno Node compatible con `@oai/artifact-tool`:

```powershell
node .\src\build_workbook.mjs
python .\src\check_outputs.py
python .\src\check_reproducibility.py
```

Por defecto, las vistas previas y el reporte de inspección quedan en `outputs/modelo_trm_colombia/`. Se puede cambiar esa carpeta con la variable `MODEL_OUTPUT_DIR`. El constructor actualiza además el archivo versionado en `deliverables/` para reducir el riesgo de desincronización.

## Controles antes de publicar

1. Ejecutar la estimación.
2. Reconstruir el archivo Excel cuando cambien resultados o documentación interna.
3. Reconstruir y revisar los cinco PNG de `graficos/`.
4. Ejecutar `python src/check_charts.py` para verificar su sincronización.
5. Revisar las 14 vistas previas en `outputs/modelo_trm_colombia/previews/`.
6. Ejecutar `python src/check_outputs.py`.
7. Ejecutar `python src/check_reproducibility.py` después de una reestimación limpia sobre una versión ya comprometida.
8. Confirmar que no existan cambios inesperados ni errores de formato.

## Mejoras econométricas futuras

- validación temporal con más de un punto de corte y comparación Diebold–Mariano;
- ventanas móviles adicionales y pruebas formales de quiebre;
- completar vintages BanRep/BCRPData si los proveedores publican historiales revisados;
- modelo explícito de volatilidad para el ARCH residual;
- comparación de modelos de pronóstico más parsimoniosos y combinaciones de pronósticos.
