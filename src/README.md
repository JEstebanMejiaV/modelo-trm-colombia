# Código de estimación y construcción del archivo Excel

Esta carpeta contiene seis programas con responsabilidades separadas:

| Archivo | Función |
|---|---|
| `estimate_model.py` | Lee las fuentes, construye la base mensual, estima los modelos base y ampliado, calcula validaciones, diagnósticos y pesos Shapley, y actualiza `data/` y `results/`. |
| `check_outputs.py` | Comprueba integridad de datos, muestra común, conciliación Shapley y sincronización entre los CSV y el archivo Excel. |
| `check_reproducibility.py` | Compara los resultados regenerados con la versión comprometida usando tolerancias numéricas, para no confundir ruido de plataforma con un cambio econométrico. |
| `build_workbook.mjs` | Construye el archivo Excel, genera las 11 hojas, exporta vistas previas y actualiza `deliverables/modelo_trm_colombia.xlsx`. |
| `build_charts.py` | Construye cuatro gráficos PNG independientes desde los CSV de `results/` y los guarda en `graficos/`. |
| `check_charts.py` | Verifica que los PNG tengan el formato esperado y correspondan a los CSV y al generador actual mediante huellas SHA-256. |

## Flujo del proyecto

```text
data/raw
   ↓
build_dataset()
   ↓
data/modelo_trm_datos_mensuales.csv
   ↓
modelo base + modelo ampliado + ECM exploratorio
   ↓
results/*.csv y results/metadata.json
   ├──→ src/build_charts.py → graficos/*.png
   ↓
build_workbook.mjs
   ↓
deliverables/modelo_trm_colombia.xlsx
```

## Especificaciones econométricas

`BASE_FACTOR_SPECS` y `EXPANDED_FACTOR_SPECS` declaran cada factor, su grupo, transformación y rezago. `make_timed_difference_design()` usa esas especificaciones para evitar mantener dos diseños manuales distintos.

- Factores contemporáneos: Brent, dólar amplio, VIX, spread TES–Treasury y monedas regionales.
- Factores rezagados un mes: remesas, diferencial de tasas, déficit fiscal, reservas, balanza cambiaria, capitales y diferencial de inflación.
- Variable dependiente: cambio mensual del logaritmo de la TRM.
- Inferencia: OLS con errores estándar HAC de seis meses.
- Selección dinámica: BIC entre cero y tres rezagos de la variación de la TRM; la selección actual es cero.
- Comparación: modelo base y ampliado usan exactamente las mismas fechas efectivas.

La temporización contemporánea hace que el modelo ampliado sea una explicación histórica o *nowcast*, no un pronóstico disponible antes de observar el mes.
En la validación recursiva se reestiman los coeficientes, pero se conserva la cantidad de rezagos seleccionada con la muestra completa. Además, el denominador fiscal anual usa la mediana del PIB implícito de todos los meses del año. Estas son razones adicionales para denominarla validación condicional pseudo-fuera de muestra.

## Pesos explicativos

`exact_shapley_r2()` calcula los 4.096 subconjuntos de 12 factores. Cada factor entra con todos sus términos y recibe su aporte marginal medio al R². El control automático exige que:

- los aportes sumen el R² incremental;
- los pesos entre factores sumen 100%;
- ningún aporte sea negativo dentro de la muestra actual;
- el archivo Excel coincida con los CSV versionados.

Los pesos son descriptivos. No identifican causalidad ni sustituyen pruebas de estabilidad por submuestras.

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
3. Reconstruir y revisar los cuatro PNG de `graficos/`.
4. Ejecutar `python src/check_charts.py` para verificar su sincronización.
5. Revisar las 11 vistas previas en `outputs/modelo_trm_colombia/previews/`.
6. Ejecutar `python src/check_outputs.py`.
7. Ejecutar `python src/check_reproducibility.py` después de una reestimación limpia sobre una versión ya comprometida.
8. Confirmar que no existan cambios inesperados ni errores de formato.

## Mejoras econométricas futuras

- backtest verdaderamente ex ante con calendario de publicación y vintages;
- validación temporal con más de un punto de corte y comparación Diebold–Mariano;
- estabilidad por submuestras y ventanas móviles;
- intervalos Shapley mediante bootstrap por bloques;
- modelo explícito de volatilidad para el ARCH residual;
- sustitución del spread TES–Treasury por EMBI o CDS reproducible;
- expectativas de inflación comparables y factor regional con PEN como robustez.
