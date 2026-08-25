# Código de estimación y construcción del archivo Excel

> Índice de desarrollo: [`docs/desarrollo/arquitectura_actual.md`](../docs/desarrollo/arquitectura_actual.md) · [`docs/desarrollo/compatibilidad_legacy.md`](../docs/desarrollo/compatibilidad_legacy.md) · [`docs/desarrollo/validacion_ci.md`](../docs/desarrollo/validacion_ci.md).
>
> Este README conserva el mapa técnico de scripts. El estado normativo de productos, contratos, provenance y límites está en [`docs/README.md`](../docs/README.md). La migración target es incremental: `trm_model.monthly` todavía consume componentes de `model`.

Esta carpeta contiene el pipeline de estimación, validación y documentación del modelo. Los scripts se organizan en dos niveles: el pipeline principal (que produce los resultados versionados) y los scripts de exploración (que informan decisiones pero no forman parte de la corrida oficial).

## Pipeline principal

| Archivo | Función |
|---|---|
| `estimate_model.py` | Orquestador principal. Importa del paquete `model/`, estima las especificaciones de controles externos y financieros, el marco macroeconómico integral y el pronóstico, calcula Shapley, Diebold-Mariano, modelos parsimoniosos y actualiza `data/`, `results/` y `README.md`. |
| `archive_vintage.py` | Crea snapshots inmutables por fecha de origen. Descarga vintages FRED via API (`FRED_API_KEY`) y genera la matriz de cobertura. |
| `build_charts.py` | Construye cinco gráficos PNG desde los CSV de `results/` y los guarda en `graficos/`. |
| `build_workbook.mjs` | Construye el archivo Excel de 14 hojas y actualiza `deliverables/modelo_trm_colombia.xlsx` cuando está disponible `@oai/artifact-tool`. |
| `sync_workbook_openpyxl.py` | Fallback reproducible: sincroniza el workbook versionado con los CSV actuales usando `openpyxl`, incluido el bloque global, tablas de robustez, coeficientes y pronóstico. |
| `check_outputs.py` | Comprueba integridad: conciliación Shapley, sincronización CSV-Excel, cobertura de vintages. |
| `check_reproducibility.py` | Compara resultados regenerados vs versión comprometida con tolerancias numéricas. |
| `check_charts.py` | Verifica que los PNG correspondan a los CSV y al generador actual via SHA-256. |

## Scripts de exploración

| Archivo | Función |
|---|---|
| `extended_forecast.py` | Pronóstico parsimonioso (top-3), backtest genuino parcial, GARCH(1,1) y forecast combination. |
| `advanced_diagnostics.py` | Rolling window (120 meses), pronóstico multihorizonte (h=1,2,3,6) y threshold regression. |
| `improve_explanation_2.py` | PDL del dólar amplio, intervención cambiaria BanRep y estimación robusta (Huber, LAD). |
| `forecast_short_term.py` | Pronóstico diario/semanal con señales mensuales globales rezagadas y comparación OOS. |
| `forecast_longterm/` | Señales de largo plazo, filtros, Markov, BN, panel EM, wavelets, cointegración, carry y volatilidad. |

## Paquete `trm_model/`

La capa instalable concentra rutas (`paths.py`), catálogo de fuentes, contratos,
validación de leakage, hashes, ambiente y manifests de corrida. Sus loaders y
transformaciones llaman explícitamente al paquete `model/` durante la
migración; no duplican la econometría mensual. La CLI se instala como
`trm-model` y ofrece `validate`, `run-monthly`, `run-daily-direction`,
`run-daily-volatility`, `run-research` y `vintage-status`. Los wrappers de
productos adicionales están en `pipelines/`; sus outputs se clasifican en
`results/output_catalog.json`.


Toda la lógica de estimación está modularizada en `src/model/`:

| Módulo | Responsabilidad |
|---|---|
| `config.py` | Constantes, especificaciones de factores, dataclasses |
| `loaders.py` | Carga de datos raw y `build_dataset()` |
| `transforms.py` | Diseño matricial, selección de rezagos |
| `estimation.py` | OLS robusto, ARDL, ECM, diagnósticos |
| `validation.py` | Validación expansiva y contribuciones |
| `shapley.py` | Descomposición Shapley exacta + bootstrap |
| `bei.py` | Estacionariedad, tendencias y robustez del BEI |
| `readme_sync.py` | Actualización automática de bloques del README |

## Flujo del proyecto

```text
data/raw
   ↓
build_dataset()
   ↓
data/modelo_trm_datos_mensuales.csv
   ↓
Controles externos y financieros + marco macroeconómico integral histórico + pronóstico rezagado + ECM exploratorio
   ↓
results/*.csv y results/metadata.json
   ├──→ src/build_charts.py → graficos/*.png
   ↓
build_workbook.mjs
   ↓
deliverables/modelo_trm_colombia.xlsx
```

## Especificaciones econométricas

`REFERENCE_FACTOR_SPECS`, `INTEGRATED_FACTOR_SPECS_3/4` y `FORECAST_FACTOR_SPECS_3/4` declaran cada factor, su grupo, transformación y rezago. `make_timed_difference_design()` usa esas especificaciones para mantener una sola ruta de construcción.

- Factores contemporáneos del histórico: términos de intercambio, dólar amplio, VIX, EMBIG Colombia, factor regional de cuatro monedas, el factor `Actividad y precios domésticos` (ISE total DANE e IPC Colombia) y los 17 términos del bloque `Condiciones financieras, commodities y actividad internacional`.
- Factores rezagados un mes: remesas, diferencial de tasas, déficit fiscal, reservas, balanza cambiaria, capitales y primera diferencia del BEI a cinco años.
- En el pronóstico, mercados, tasas, riesgo y commodities usan `.L1`; empleo, desempleo y fletes/logística de EE. UU. usan `.L2` conforme al calendario de disponibilidad. Los candidatos de China quedan fuera del score completo por cobertura incompleta.
- Variable dependiente: cambio mensual del logaritmo de la TRM.
- Inferencia: OLS con errores estándar HAC de seis meses.
- Selección dinámica: BIC entre cero y tres rezagos de la variación de la TRM; la selección actual es cero.
- Comparación: las especificaciones de controles externos y financieros y del marco macroeconómico integral usan exactamente las mismas fechas efectivas.

Los términos de intercambio entran como `D.ln_terminos_intercambio.L0`; su rezago de publicación cercano a dos meses refuerza que el uso contemporáneo es explicativo *ex post*. El riesgo soberano entra como `D.embig_colombia_pp.L0`: se promedia diariamente el EMBIG Colombia de BCRPData y se convierte de puntos básicos a puntos porcentuales. Debe mantenerse la atribución a BCRPData y a sus fuentes originales Reuters/J.P. Morgan; la descarga pública no equivale a una licencia abierta sobre la metodología o la marca EMBIG.

El diferencial BEI a cinco años entra como `D.diferencial_bei_5y_pp.L1`. Para Colombia se restan los promedios mensuales de TES nominales y TES UVR al mismo horizonte; luego se resta la compensación estadounidense `BKEVEN05`. `build_bei_aggregations()` conserva también una versión limitada a fechas diarias comunes. `bei_stationarity_tests()` y `bei_trend_break_models()` evalúan constante, tendencia y quiebres; `bei_model_specification_comparison()` contrasta seis variantes sobre la misma muestra. Es una compensación de inflación de mercado, no una expectativa pura. Las fuentes, fórmulas y cautelas se detallan en [`data/README.md`](../data/README.md).

La temporización contemporánea hace que el marco macroeconómico integral sea una explicación histórica o *nowcast*, no un pronóstico disponible antes de observar el mes. El factor `Actividad y precios domésticos` reúne el ISE total DANE y el IPC Colombia: ambos entran como `D.ln_ise_total_dane.L0` y `D.ln_ipc_colombia.L0` en la explicación y con `.L2` en el pronóstico. GEIH, IPI e IPP se auditan en `data/variables_internas_cobertura.csv`, pero permanecen fuera de la matriz balanceada por cobertura incompleta. PEN, descargado de BCRPData `PN01207PM`, mejora BIC, R² ajustado y MAPE de esa explicación frente al factor de tres monedas.

El modelo de pronóstico usa `FORECAST_FACTOR_SPECS_3/4`: todos los factores económicos entran con uno a tres meses de rezago conforme a `FORECAST_AVAILABILITY`. BIC selecciona el factor de tres monedas y un rezago de `Δln(TRM)`. La validación es pseudo-tiempo-real porque respeta disponibilidad, pero usa el último *vintage* de las fuentes. Un backtest genuino exige reconstruir cada origen con las versiones que existían entonces.

En las validaciones recursivas se reestiman los coeficientes, pero se conserva la cantidad de rezagos seleccionada con la muestra completa. Además, el denominador fiscal anual usa la mediana del PIB implícito de todos los meses del año. Estas cautelas deben permanecer visibles.

## Pesos explicativos

`exact_shapley_r2()` calcula los **16.384 subconjuntos de 14 factores**. Cada factor entra con todos sus términos y recibe su aporte marginal medio al R². El factor `Condiciones financieras, commodities y actividad internacional` se conserva como un único jugador, aunque sus contribuciones mensuales se calculan término por término. El control automático exige que:

- los aportes sumen el R² incremental;
- los pesos entre factores sumen 100%;
- ningún aporte sea negativo dentro de la muestra actual;
- el archivo Excel coincida con los CSV versionados.

Los pesos son descriptivos. No identifican causalidad ni sustituyen pruebas de estabilidad por submuestras.

`block_bootstrap_shapley()` usa 200 réplicas de bloques circulares de 12 meses y 64 permutaciones antitéticas por réplica. `subsample_stability()` calcula Shapley exacto y coeficientes HAC en cinco cortes. La semilla fija hace reproducibles los intervalos, pero no elimina la incertidumbre de especificación.

## Archivo de vintages

`archive_vintage.py` no forma parte de la ejecución normal del estimador porque requiere acceso a los proveedores. Un snapshot completo se crea con `snapshot --origin-date`; las fechas existentes no se sobrescriben. `alfred-history` intenta recuperar los 48 orígenes, valida que cada observación sea anterior a su origen y reanuda desde caché, pero solo publica el consolidado cuando las 288 respuestas están completas. La validación pseudo-tiempo-real cubre 48 meses; solo 3 de los 14 factores activos tienen vintages históricos completos (dólar amplio, VIX y monedas regionales). La base global mensual usa el último vintage disponible, por lo que sus señales también se interpretan con esta cautela.

## Reproducción

Desde la raíz del repositorio:

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

`python .\src\estimate_model.py` permanece como entry point legacy. La CLI
nueva registra hashes de inputs/outputs y ambiente en un manifest por corrida;
`results/output_catalog.json` mantiene la clasificación sin mover los CSV.

La construcción del archivo Excel puede usar el generador Node cuando el entorno privado está disponible. En este workspace `@oai/artifact-tool` no está publicado, por lo que la ruta reproducible es el fallback local:

```powershell
python .\src\sync_workbook_openpyxl.py
python .\src\check_outputs.py
python .\src\check_reproducibility.py
```

El generador Node original sigue disponible para entornos que sí tengan el paquete:

```powershell
node .\src\build_workbook.mjs
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
