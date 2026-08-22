# Modelo econométrico de la TRM en Colombia

Este proyecto estima un modelo mensual para explicar la variación del precio del dólar en Colombia, medido como pesos colombianos por dólar estadounidense (TRM promedio mensual).

## Modelo base

La especificación preferida es un modelo en primeras diferencias:

\[
\Delta\ln(TRM_t)=c+\beta_1\Delta\ln(Brent_t)+\beta_2\Delta\ln(Dólar\ amplio_t)+\beta_3\Delta\ln(VIX_t)
+\beta_4\Delta\ln(Remesas\ 12m_{t-1})+\beta_5\Delta(Diferencial\ de\ tasas_{t-1})
+\beta_6\Delta(Déficit\ fiscal\ 12m/PIB_{t-1})+\beta_7Pandemia_t+u_t
\]

La muestra común cubre enero de 2006 a abril de 2026. La regresión efectiva tiene 240 observaciones, desde mayo de 2006, por las diferencias y rezagos. Los errores estándar son HAC con una ventana de seis meses.

| Variable | Coeficiente | p-valor | Lectura aproximada |
|---|---:|---:|---|
| Cambio del log de Brent | −0,0517 | 0,0002 | Un aumento de 10% del Brent se asocia con una TRM 0,49% menor. |
| Cambio del log del índice amplio del dólar | 1,2150 | <0,0001 | Un aumento de 1% del dólar global se asocia con una TRM 1,22% mayor. |
| Cambio del log del VIX | 0,0386 | <0,0001 | Un aumento de 10% del VIX se asocia con una TRM 0,37% mayor. |
| Cambio del log de remesas de 12 meses, rezagado | 0,2629 | 0,0241 | El signo es contrario al canal simple de oferta de divisas y probablemente refleja endogeneidad. |
| Cambio del diferencial de tasas Colombia–EE. UU., rezagado | −0,0099 | 0,0391 | Un aumento de 1 punto porcentual se asocia con una TRM 0,99% menor. |
| Cambio del déficit fiscal de 12 meses como % del PIB, rezagado | 0,0043 | 0,1894 | Tiene el signo esperado, pero no es estadísticamente preciso al 5%. |

El R² ajustado es 48,6%. En una validación expansiva de 48 meses, el modelo condicional obtiene un MAPE de 2,03% y acierta la dirección en 72,9% de los meses. Esa validación utiliza los valores contemporáneos realizados de Brent, dólar amplio y VIX, por lo que no equivale a un pronóstico verdaderamente disponible en tiempo real.

## Modelo ampliado y peso de cada factor

La segunda especificación conserva el modelo base e integra seis bloques: spread TES–Treasury a 10 años, reservas internacionales netas sin FLAR, balanza comercial cambiaria, movimientos netos de capital, diferencial de inflación y un factor de monedas regionales. Base y ampliado usan exactamente los mismos 240 meses efectivos.

El R² ajustado sube de 48,6% a 55,3%. En la misma validación condicional de 48 meses, el MAPE baja de 2,03% a 1,65%; el acierto de dirección pasa de 72,9% a 70,8%. El modelo ampliado es una **contabilidad histórica/nowcast** porque incorpora dentro del mes las variables financieras globales, el spread TES–Treasury y el factor regional. No es un pronóstico ex ante ni una identificación causal.

El peso se calcula mediante una descomposición Shapley/LMG exacta del R². Esta estima los 4.096 subconjuntos posibles de los 12 factores y reparte entre ellos la información compartida. Los porcentajes siguientes suman 100% de la fracción explicada incremental por los factores; el bloque base —intercepto, dinámica de TRM y pandemia— se mantiene aparte.

| Factor | Peso Shapley entre factores | Aporte al R² |
|---|---:|---:|
| Monedas regionales | 29,1% | 16,29 p.p. |
| Dólar amplio | 26,1% | 14,59 p.p. |
| Spread TES–Treasury a 10 años | 15,1% | 8,43 p.p. |
| Petróleo Brent | 10,9% | 6,10 p.p. |
| VIX | 10,0% | 5,59 p.p. |
| Reservas internacionales | 3,5% | 1,94 p.p. |
| Balanza comercial cambiaria | 1,5% | 0,83 p.p. |
| Flujos netos de capital | 1,2% | 0,65 p.p. |
| Remesas | 1,1% | 0,62 p.p. |
| Diferencial de inflación | 0,9% | 0,52 p.p. |
| Diferencial de tasas | 0,5% | 0,26 p.p. |
| Déficit fiscal | 0,1% | 0,08 p.p. |

Estos pesos miden ajuste estadístico dentro de esta muestra. No miden causalidad, importancia estructural ni cuánto cambiaría la TRM ante una intervención. Cuando dos factores son correlacionados, Shapley distribuye su señal compartida promediando todos los órdenes de entrada.

## Decisión metodológica

Se estimó también un ARDL–ECM. La prueba bounds produjo F = 3,414 y p-valor del límite I(1) = 7,31%. La cointegración no es concluyente al 5%; por eso el ECM se conserva solo como contraste exploratorio y el modelo principal se presenta en diferencias para evitar una regresión espuria en niveles.

Los resultados describen asociaciones dinámicas, no efectos causales. Para hacer afirmaciones causales se necesitarían shocks identificados, como sorpresas monetarias, cambios fiscales inesperados o shocks petroleros externos.

## Construcción de variables

- TRM, tasa de política, Brent, índice amplio del dólar y VIX: promedio mensual de datos diarios.
- Remesas: flujo mensual en dólares; el modelo usa el acumulado móvil de 12 meses en logaritmos.
- Diferencial de tasas: tasa de política de Colombia menos federal funds, en puntos porcentuales.
- Déficit fiscal: negativo del balance de caja mensual del Gobierno Nacional Central; se acumula durante 12 meses y se divide por el PIB nominal anual implícito en las tablas de MinHacienda.
- Riesgo local: promedio mensual de la tasa TES COP cero cupón a 10 años menos el Treasury estadounidense a 10 años. Es un proxy amplio de prima local, no un EMBI ni un CDS.
- Reservas: cambio del logaritmo de las reservas internacionales netas sin FLAR, rezagado un mes.
- Balanza comercial y capitales: `asinh(flujo/1.000)` para admitir valores positivos, negativos y cero; ambas variables entran con un rezago.
- Diferencial de inflación: inflación interanual observada de Colombia menos la de EE. UU., rezagada un mes. La única ausencia interna de CPIAUCNS, octubre de 2025, se interpola linealmente y queda marcada en los datos.
- Factor regional: promedio de los cambios logarítmicos estandarizados de BRL, CLP y MXN por USD. Media y volatilidad se calibran en 2006–2019; un valor positivo representa depreciación regional.
- Variables globales contemporáneas: Brent, dólar amplio y VIX.
- Variables domésticas de publicación lenta rezagadas un mes: remesas, diferencial de tasas, déficit fiscal, reservas, balanza, capitales e inflación.
- Términos de intercambio se conserva como alternativa de robustez que sustituye a Brent; no se incluye a la vez para evitar duplicar el canal petrolero.

## Archivos principales

- `deliverables/modelo_trm_colombia.xlsx`: archivo Excel final con resumen, datos, fórmulas, estimaciones, pesos, validación, diagnósticos y fuentes.
- `src/estimate_model.py`: prepara los datos, estima los modelos y guarda los resultados.
- `src/build_workbook.mjs`: construye el archivo Excel auditable a partir de los resultados.
- `data/modelo_trm_datos_mensuales.csv`: base mensual consolidada.
- `results/pesos_explicativos_modelo_ampliado.csv`: descomposición Shapley exacta.
- `results/comparacion_modelos.csv`: comparación base–ampliado sobre la misma muestra.
- `results/`: coeficientes, diagnósticos, pruebas, contribuciones y validación.

## Reproducir la estimación

Con Python, pandas, NumPy, SciPy, statsmodels y openpyxl instalados:

```powershell
python .\src\estimate_model.py
```

Las series fuente descargadas están en `data/raw`. Sus enlaces y tratamientos exactos aparecen en la hoja `Fuentes` del archivo Excel final.

## Fuentes

- Colombia: [Banco de la República — tasas de cambio y sector externo](https://www.banrep.gov.co/es/estadisticas-economicas/series-historicas/tasas-cambio-sector-externo) y [Ministerio de Hacienda — balance del Gobierno Nacional Central](https://www.minhacienda.gov.co/politica-fiscal/cifras-de-politica-fiscal/gobierno-nacional-central/balance).
- Petróleo: [EIA — Brent](https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?f=M&n=PET&s=RBRTE), distribuido también por FRED.
- Controles estadounidenses: [FRED — dólar amplio](https://fred.stlouisfed.org/series/DTWEXBGS), federal funds, Treasury a 10 años e IPC.
- Riesgo global: [Cboe — VIX](https://www.cboe.com/tradable_products/vix/vix_historical_data).
- Monedas regionales: OECD, distribuidas por FRED, para BRL, CLP y MXN por USD.

## Robusteces pendientes

Las siguientes extensiones quedan como análisis de sensibilidad:

1. Sustituir el proxy TES–Treasury por CDS a cinco años o EMBI Colombia con una fuente redistribuible.
2. Sustituir Brent por términos de intercambio.
3. Reemplazar inflación realizada por expectativas de inflación comparables.
4. Incorporar PEN desde el BCRP y comparar el factor regional de tres y cuatro monedas.
5. Separar explicación histórica de un pronóstico genuino con rezagos de publicación y datos en tiempo real.
6. Añadir intervalos Shapley mediante bootstrap por bloques y estimaciones por submuestras.
