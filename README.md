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

El R² ajustado sube de 48,6% a 57,2%. En la misma validación condicional de 48 meses, el MAPE baja de 2,03% a 1,77% y el acierto de dirección se mantiene en 72,9%. El modelo ampliado es una **contabilidad histórica/nowcast** porque incorpora dentro del mes las variables financieras globales, el spread TES–Treasury y el factor regional. No es un pronóstico ex ante ni una identificación causal.

Los diagnósticos no detectan autocorrelación ni inestabilidad de parámetros, pero ARCH-LM y Jarque–Bera rechazan ausencia de volatilidad condicional y normalidad. Los errores HAC fortalecen la inferencia de la ecuación de media; no modelan la volatilidad ni las colas extremas.

El peso se calcula mediante una descomposición Shapley/LMG exacta del R². Esta estima los 4.096 subconjuntos posibles de los 12 factores y reparte entre ellos la información compartida. Los porcentajes siguientes suman 100% de la fracción explicada incremental por los factores; el bloque base —intercepto, dinámica de TRM y pandemia— se mantiene aparte.

| Factor | Peso Shapley entre factores | Aporte al R² |
|---|---:|---:|
| Monedas regionales | 26,6% | 15,36 p.p. |
| Dólar amplio | 23,7% | 13,66 p.p. |
| Spread TES–Treasury a 10 años | 13,7% | 7,88 p.p. |
| Petróleo Brent | 9,6% | 5,52 p.p. |
| VIX | 9,2% | 5,33 p.p. |
| Balanza comercial cambiaria | 7,6% | 4,40 p.p. |
| Flujos netos de capital | 4,4% | 2,55 p.p. |
| Reservas internacionales | 2,4% | 1,39 p.p. |
| Remesas | 1,1% | 0,61 p.p. |
| Diferencial de inflación | 0,8% | 0,48 p.p. |
| Diferencial de tasas | 0,8% | 0,48 p.p. |
| Déficit fiscal | 0,1% | 0,07 p.p. |

Estos pesos miden ajuste estadístico dentro de esta muestra. No miden causalidad, importancia estructural ni cuánto cambiaría la TRM ante una intervención. Cuando dos factores son correlacionados, Shapley distribuye su señal compartida promediando todos los órdenes de entrada.

## Decisión metodológica

Se estimó también un ARDL–ECM. La prueba bounds produjo F = 3,414 y p-valor del límite I(1) = 7,31%. La cointegración no es concluyente al 5%; por eso el ECM se conserva solo como contraste exploratorio y el modelo principal se presenta en diferencias para evitar una regresión espuria en niveles.

Los resultados describen asociaciones dinámicas, no efectos causales. Para hacer afirmaciones causales se necesitarían shocks identificados, como sorpresas monetarias, cambios fiscales inesperados o shocks petroleros externos.

## Qué representa cada variable

La TRM está expresada como COP por USD: un aumento significa depreciación del peso colombiano. En la columna “signo esperado”, `+` indica una asociación esperada con una TRM mayor y `−` con una TRM menor.

| Variable | Qué mide y fuente | Entrada al modelo | Signo esperado | Interpretación y cautela |
|---|---|---|:---:|---|
| TRM | Precio promedio mensual del dólar en pesos; Banco de la República, serie 1 | `Δln(TRM)`, variable dependiente | — | El cambio logarítmico aproxima la variación porcentual mensual. |
| Petróleo Brent | Ingreso externo asociado al principal producto de exportación; EIA/FRED DCOILBRENTEU agregado a mes, comparable con RBRTE | `Δln`, mes actual | − | Un petróleo más caro suele aumentar la oferta de divisas. También afecta actividad, inversión y cuentas fiscales. |
| Índice amplio del dólar | Fortaleza general del USD frente a monedas de socios comerciales; FRED, DTWEXBGS | `Δln`, mes actual | + | Separa un movimiento global del dólar de un choque exclusivamente colombiano. |
| VIX | Incertidumbre y aversión global al riesgo; Cboe, distribuido en la base por FRED como VIXCLS | `Δln`, mes actual | + | En episodios de aversión al riesgo suele salir capital de mercados emergentes. |
| Remesas | Dólares enviados a Colombia; Banco de la República, serie 15363 | `Δln` del acumulado 12 meses, rezago 1 | − | El signo estimado es positivo; puede reflejar que los hogares reciben más remesas cuando el peso ya se ha depreciado. |
| Diferencial de tasas | Tasa de política de Colombia menos federal funds | Cambio en puntos porcentuales, rezago 1 | − | Un mayor retorno relativo puede apoyar al COP, pero las tasas también responden a inflación y TRM. |
| Déficit fiscal | Negativo del balance de caja del GNC acumulado 12 meses como porcentaje del PIB; MinHacienda | Cambio en puntos porcentuales, rezago 1 | + | Mayor necesidad de financiación puede elevar la prima de riesgo. Su coeficiente no es preciso al 5%. |
| Spread TES–Treasury 10 años | TES COP cero cupón de BanRep 15274 menos Treasury DGS10 | Cambio en puntos porcentuales, mes actual | + | Es un proxy amplio de prima local; incluye inflación, devaluación esperada, duración y liquidez. No es EMBI ni CDS. |
| Reservas internacionales | Activos externos netos sin FLAR; Banco de la República, serie 15053 | `Δln`, rezago 1 | − | Más reservas pueden reforzar la capacidad de intervención, pero también reaccionan a la propia TRM. |
| Balanza comercial cambiaria | Exportaciones menos importaciones canalizadas por el mercado cambiario; BanRep 16702 | `Δasinh(flujo/1.000)`, rezago 1 | − | Se diferencia porque el nivel transformado no es estacionario. Su coeficiente estimado es positivo, contrario al signo esperado; puede reflejar simultaneidad, composición o endogeneidad y no debe leerse causalmente. |
| Flujos netos de capital | Entradas menos salidas netas de capital; BanRep 16706 | `Δasinh(flujo/1.000)`, rezago 1 | − | Se diferencia porque el nivel transformado no es estacionario. La serie 16706 es el total, no solo sector real y Gobierno. |
| Diferencial de inflación | Inflación interanual Colombia menos EE. UU.; BanRep 15000 y FRED CPIAUCNS | Nivel en puntos porcentuales, rezago 1 | + | Es inflación realizada, no expectativa. Octubre de 2025 de EE. UU. se interpola y queda marcado. |
| Monedas regionales | Movimiento común de BRL, CLP y MXN por USD; OECD/FRED | Promedio igual de `z(Δln)`, mes actual | + | Un valor positivo significa depreciación regional. Los parámetros se calibran con 2006–2019. |
| Pandemia 2020 | Control para marzo–mayo de 2020 | Indicador 0/1 | — | Evita atribuir completamente un episodio extremo a los factores económicos; no tiene interpretación estructural. |
| Términos de intercambio | Poder de compra de las exportaciones; BanRep 15360 | Alternativa `Δln`, fuera del modelo ampliado | − | Se usa como sustituto de Brent en robustez, no simultáneamente en el núcleo. |

Notación: `Δ` es cambio mensual, `ln` es logaritmo natural, `rezago 1` usa la observación del mes anterior y `asinh` conserva el signo de flujos positivos y negativos reduciendo la influencia de valores extremos.

## Construcción y temporización

- TRM, tasa de política, Brent, índice amplio del dólar y VIX: promedio mensual de datos diarios.
- Remesas: flujo mensual en dólares; el modelo usa el acumulado móvil de 12 meses en logaritmos.
- Diferencial de tasas: tasa de política de Colombia menos federal funds, en puntos porcentuales.
- Déficit fiscal: negativo del balance de caja mensual del Gobierno Nacional Central; se acumula durante 12 meses y se divide por el PIB nominal anual implícito en las tablas de MinHacienda.
- Riesgo local: promedio mensual de la tasa TES COP cero cupón a 10 años menos el Treasury estadounidense a 10 años. Es un proxy amplio de prima local, no un EMBI ni un CDS.
- Reservas: cambio del logaritmo de las reservas internacionales netas sin FLAR, rezagado un mes.
- Balanza comercial y capitales: primero se aplica `asinh(flujo/1.000)` para admitir valores positivos, negativos y cero; luego se toma el cambio mensual y se usa con un rezago. Las pruebas de integración rechazan usar sus niveles transformados como estacionarios.
- Diferencial de inflación: inflación interanual observada de Colombia menos la de EE. UU., rezagada un mes. La única ausencia interna de CPIAUCNS, octubre de 2025, se interpola linealmente y queda marcada en los datos.
- Factor regional: promedio de los cambios logarítmicos estandarizados de BRL, CLP y MXN por USD. Media y volatilidad se calibran en 2006–2019; un valor positivo representa depreciación regional.
- Variables globales contemporáneas: Brent, dólar amplio y VIX.
- Variables domésticas de publicación lenta rezagadas un mes: remesas, diferencial de tasas, déficit fiscal, reservas, balanza, capitales e inflación.
- El denominador fiscal usa la mediana del PIB implícito de todos los meses del año; puede incorporar información posterior dentro del mismo año y es otra razón para tratar la validación como condicional.
- Términos de intercambio se conserva como alternativa de robustez que sustituye a Brent; no se incluye a la vez para evitar duplicar el canal petrolero.

El diccionario completo de columnas, unidades, códigos de fuente y cautelas está en [`data/README.md`](data/README.md).

## Archivos principales

- `deliverables/modelo_trm_colombia.xlsx`: archivo Excel final con resumen, datos, fórmulas, estimaciones, pesos, validación, diagnósticos y fuentes.
- `src/estimate_model.py`: prepara los datos, estima los modelos y guarda los resultados.
- `src/build_workbook.mjs`: construye el archivo Excel auditable a partir de los resultados.
- `src/build_charts.py`: reconstruye los cuatro gráficos PNG independientes.
- `graficos/`: imágenes explicativas y guía de lectura.
- `data/modelo_trm_datos_mensuales.csv`: base mensual consolidada.
- `results/pesos_explicativos_modelo_ampliado.csv`: descomposición Shapley exacta.
- `results/comparacion_modelos.csv`: comparación base–ampliado sobre la misma muestra.
- `results/`: coeficientes, diagnósticos, pruebas, contribuciones y validación.

## Documentación por carpeta

- [`data/README.md`](data/README.md): fuentes, columnas, unidades, transformaciones, rezagos y calidad de los datos.
- [`src/README.md`](src/README.md): flujo de estimación, funciones principales y reproducción técnica.
- [`results/README.md`](results/README.md): significado y uso de cada resultado CSV y de `metadata.json`.
- [`deliverables/README.md`](deliverables/README.md): contenido y ruta de auditoría de las 11 hojas del archivo Excel.
- [`graficos/README.md`](graficos/README.md): cuatro gráficos independientes sobre pesos, desempeño, validación y efectos típicos.

## Reproducir la estimación

Con Python, pandas, NumPy, SciPy, statsmodels, openpyxl y Matplotlib instalados:

```powershell
python .\src\estimate_model.py
python .\src\build_charts.py
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
