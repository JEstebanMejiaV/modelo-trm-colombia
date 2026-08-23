# Modelo econométrico de la TRM en Colombia

Este proyecto estima un modelo mensual para explicar la variación del precio del dólar en Colombia, medido como pesos colombianos por dólar estadounidense (TRM promedio mensual). La muestra balanceada cubre enero de 2006 a abril de 2026 (244 meses); las diferencias y los rezagos dejan 240 observaciones efectivas, de mayo de 2006 a abril de 2026.

Hay dos lecturas complementarias:

- El **modelo principal** es una especificación parsimoniosa en primeras diferencias.
- El **modelo ampliado histórico** distribuye la explicación entre 12 factores y usa el factor regional de cuatro monedas: BRL, CLP, MXN y PEN.
- El **modelo de pronóstico** usa solo información rezagada que razonablemente estaría disponible al inicio del mes objetivo. Su factor regional conserva BRL, CLP y MXN porque esa composición obtiene menor BIC que la alternativa con PEN.

## Modelo principal

La ecuación preferida es:

$$
\begin{aligned}
\Delta\ln(\mathrm{TRM}_t) =\;& c
+ \beta_1\Delta\ln(\mathrm{Términos\ de\ intercambio}_t)
+ \beta_2\Delta\ln(\mathrm{Dólar\ amplio}_t)
+ \beta_3\Delta\ln(\mathrm{VIX}_t)\\
&+ \beta_4\Delta\ln(\mathrm{Remesas\ 12m}_{t-1})
+ \beta_5\Delta(\mathrm{Diferencial\ de\ tasas}_{t-1})\\
&+ \beta_6\Delta(\mathrm{Déficit\ fiscal\ 12m/PIB}_{t-1})
+ \beta_7\mathrm{Pandemia}_t + u_t .
\end{aligned}
$$

Los errores estándar son HAC con una ventana de seis meses. Los coeficientes describen asociaciones parciales dentro de la muestra, manteniendo constantes los demás regresores.

<!-- AUTO:coeficientes_principal -->
| Término | Coeficiente | p-valor HAC | Lectura aproximada |
|---|---:|---:|---|
| Constante | −0,00059 | 0,7250 | No hay evidencia de una deriva mensual adicional. |
| \(\Delta\ln\) términos de intercambio, mes actual | −0,10008 | 0,0007 | Una mejora de 10% se asocia con una TRM cerca de 100.1% menor. |
| \(\Delta\ln\) remesas 12 meses, rezago 1 | 0,27652 | 0,0243 | Un aumento de 10% se asocia con una TRM cerca de 276.5% mayor; el signo contrario al canal simple de oferta de divisas aconseja cautela por endogeneidad. |
| \(\Delta\) diferencial de tasas, rezago 1 | −0,00990 | 0,0436 | Un aumento de 1 punto porcentual en el cambio del diferencial se asocia con una TRM cerca de 0.99% menor. |
| \(\Delta\) déficit fiscal 12 meses/PIB, rezago 1 | 0,00485 | 0,1447 | Un aumento de 1 punto porcentual se asocia con una TRM cerca de 0.48% mayor, pero la estimación no es precisa al 5%. |
| \(\Delta\ln\) dólar amplio, mes actual | 1,27461 | <0,0001 | Un aumento de 1% del dólar global se asocia con una TRM cerca de 127.46% mayor. |
| \(\Delta\ln\) VIX, mes actual | 0,03836 | <0,0001 | Un aumento de 10% del VIX se asocia con una TRM cerca de 38.36% mayor. |
| Indicador de pandemia, marzo–mayo de 2020 | 0,01081 | 0,0200 | Se asocia con una TRM alrededor de 1.1% mayor, condicionado a los demás factores. |
<!-- /AUTO:coeficientes_principal -->

El R² es 49,45% y el R² ajustado es 47,92%. En una validación expansiva de 48 meses, el modelo obtiene:

<!-- AUTO:metricas_principal -->
- MAPE condicional: **2,01%**.
- Acierto de dirección: **68,75%**.
- R² condicional frente a caminata aleatoria: **0,32%**.
<!-- /AUTO:metricas_principal -->

La validación usa los valores realizados dentro del mes de términos de intercambio, dólar amplio y VIX. Por ello mide capacidad explicativa condicional, no desempeño de un pronóstico en tiempo real.

## Modelo ampliado

El modelo ampliado conserva los siete términos del principal e incorpora seis bloques adicionales:

1. cambio contemporáneo del EMBIG Colombia;
2. cambio rezagado de reservas internacionales netas sin FLAR;
3. cambio rezagado de la balanza comercial cambiaria transformada;
4. cambio rezagado de los movimientos netos de capital transformados;
5. cambio rezagado del **Diferencial de compensación inflacionaria 5 años** Colombia–EE. UU.; y
6. factor contemporáneo de monedas regionales.

Base y ampliado usan los mismos 240 meses efectivos. Los coeficientes finales del ampliado son:

<!-- AUTO:coeficientes_ampliado -->
| Término | Coeficiente | p-valor |
|---|---:|---:|
| Constante | 0,00318 | 0,0945 |
| \(\Delta\ln\) términos de intercambio, mes actual | −0,09186 | 0,0014 |
| \(\Delta\ln\) remesas 12 meses, rezago 1 | 0,10076 | 0,3217 |
| \(\Delta\) diferencial de tasas, rezago 1 | −0,00496 | 0,2946 |
| \(\Delta\) déficit fiscal 12 meses/PIB, rezago 1 | −0,00075 | 0,8276 |
| \(\Delta\ln\) dólar amplio, mes actual | 0,24145 | 0,2524 |
| \(\Delta\ln\) VIX, mes actual | 0,01144 | 0,2422 |
| \(\Delta\) EMBIG Colombia, en puntos porcentuales, mes actual | 0,01710 | 0,1323 |
| \(\Delta\ln\) reservas netas sin FLAR, rezago 1 | −0,29366 | 0,0131 |
| \(\Delta\,\mathrm{asinh}\) balanza comercial cambiaria, rezago 1 | 0,04699 | <0,0001 |
| \(\Delta\,\mathrm{asinh}\) movimientos netos de capital, rezago 1 | 0,00065 | 0,8505 |
| \(\Delta\) diferencial de compensación inflacionaria 5 años, rezago 1 | −0,00627 | 0,1771 |
| Factor regional BRL, CLP, MXN y PEN, mes actual | 0,01653 | <0,0001 |
| Indicador de pandemia, marzo–mayo de 2020 | −0,00272 | 0,6686 |
<!-- /AUTO:coeficientes_ampliado -->

La transformación \(\mathrm{asinh}\) conserva el signo y admite ceros, pero sus coeficientes no son elasticidades constantes. La significancia individual tampoco debe confundirse con el peso explicativo: un factor puede compartir mucha información con otros y, por multicolinealidad, tener un p-valor individual alto.

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

Los diagnósticos de ambos modelos no detectan autocorrelación a 12 meses y CUSUM no rechaza estabilidad. En el modelo principal, Jarque–Bera rechaza normalidad y ARCH-LM no rechaza al 5% (p = 0,080). En el ampliado, Jarque–Bera y ARCH-LM rechazan normalidad y homocedasticidad; RESET no rechaza al 5% (p = 0,078). Los errores HAC robustecen la inferencia de la ecuación de media, pero no modelan volatilidad ni colas extremas.

## Robustez del diferencial BEI

El nivel del diferencial parece estacionario si solo se incluye constante —ADF p = 0,013 y KPSS no rechaza—, pero la conclusión cambia con tendencia: ADF da p = 0,054 y KPSS rechaza estacionariedad. Zivot–Andrews con constante, tendencia y quiebre selecciona enero de 2009, pero tampoco rechaza raíz unitaria al 5% (p = 0,089). La primera diferencia sí supera ADF, KPSS y Zivot–Andrews en ambas agregaciones.

En la ecuación ampliada, la primera diferencia con promedios separados tiene el menor BIC: **−1103,45**, frente a **−1101,29** para el nivel. Su MAPE condicional es **1,70%**, apenas 0,009 p.p. mayor que el nivel. Un quiebre de coeficiente elegido ex post en enero de 2009 empeora el BIC a −1093,39 y ni el cambio de coeficiente ni el efecto posterior son significativos al 5%; por eso no se adopta.

La agregación sobre fechas comunes produce una serie casi idéntica a los promedios separados: correlación de **99,97%**, diferencia media de 0,00004 p.p. y máxima de 0,156 p.p. Sin embargo, algunos meses conservan apenas **4 días comunes** —mediana: 19—. Se mantienen los promedios separados, que aprovechan toda la información publicada de cada mercado.

## Cuánto pesa cada factor

El peso se calcula mediante una descomposición Shapley/LMG exacta del R². Se estiman los 4.096 subconjuntos posibles de los 12 factores y se promedia su aporte marginal en todos los órdenes de entrada.

El bloque fijo —intercepto, dinámica seleccionada de TRM y pandemia— explica 1,78% de la variación. Los 12 factores elevan el R² a 60,77%, un incremento de 58,99 puntos porcentuales. La columna “peso” reparte ese incremento y suma 100%.

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

Estos pesos miden ajuste estadístico en esta muestra. No miden causalidad, importancia estructural ni el efecto de una intervención. Cuando dos factores están correlacionados, Shapley distribuye su señal compartida; por eso el peso no es igual al tamaño o a la significancia de un coeficiente.

<!-- AUTO:bootstrap_intervalos -->
La incertidumbre se evalúa con 200 réplicas de un *bootstrap* circular de bloques de 12 meses. Los intervalos percentiles del 95% de los tres factores principales son: Monedas regionales, **21,65%–34,72%**; Dólar amplio, **12,02%–26,98%**; Riesgo soberano EMBIG Colombia, **12,33%–26,56%**. Son intervalos de la asignación Shapley bajo remuestreo temporal, no intervalos de un efecto causal.
<!-- /AUTO:bootstrap_intervalos -->

La jerarquía general es estable en cinco cortes: la correlación de rangos de Spearman frente a la muestra completa va de **0,909 a 0,979**. La submuestra 2020–2026 conserva el signo de **9 de 12** coeficientes y el mayor cambio individual de peso alcanza **6,60 p.p.**. Por eso la estabilidad de rangos no debe confundirse con estabilidad paramétrica.

## Tres monedas, cuatro monedas y PEN

El PEN procede de [BCRPData, serie `PN01207PM`](https://estadisticas.bcrp.gob.pe/estadisticas/series/mensuales/resultados/PN01207PM/html) y se incorpora como soles por USD. Para cada moneda se calcula `Δln`, se estandariza con media y desviación estándar poblacional de 2006–2019 y después se toma un promedio simple. La correlación entre los factores de tres y cuatro monedas es 95,81%.

| Uso | Composición | R² ajustado | BIC | MAPE 48 meses |
|---|---|---:|---:|---:|
| Explicación histórica | BRL, CLP y MXN | 56,35% | −1091,27 | 1,83% |
| Explicación histórica | BRL, CLP, MXN y PEN | **58,52%** | **−1103,45** | **1,70%** |
| Pronóstico con información rezagada | BRL, CLP y MXN | **10,20%** | **−913,69** | **2,63%** |
| Pronóstico con información rezagada | BRL, CLP, MXN y PEN | 9,74% | −912,46 | 2,69% |

La selección depende del propósito: PEN mejora la explicación histórica, pero no mejora el pronóstico. Por eso el ampliado histórico usa cuatro monedas y el pronóstico usa tres.

## Pronóstico con rezagos de publicación

Esta ecuación pronostica la TRM promedio del mes `t` al inicio de `t`. No usa factores económicos del mes objetivo: términos de intercambio y déficit entran con tres meses de rezago; remesas, reservas, balanza y capitales con dos; dólar amplio, VIX, EMBIG, tasas, compensación inflacionaria y monedas regionales con uno. BIC selecciona además un rezago de `Δln(TRM)`.

<!-- AUTO:metricas_pronostico -->
La validación expansiva de 48 meses obtiene MAPE de **2,63%**, acierto de dirección de **52,08%** y R² frente a la caminata aleatoria de **−10,98%**. La caminata obtiene MAPE de **2,39%**. Es decir, la ecuación explicativa no se convierte automáticamente en un buen pronóstico y, con esta información, el benchmark simple sigue siendo superior.
<!-- /AUTO:metricas_pronostico -->

La evaluación es **pseudo-tiempo-real**: respeta el calendario de publicación, pero usa la última versión disponible de cada serie. El repositorio ahora archiva descargas por fecha de origen y deja implementada una recuperación ALFRED reanudable; sin embargo, el proveedor cortó las conexiones individuales y el paquete multiserie se descartó por contener datos posteriores al origen. Por ello **0 de 12 factores** tienen todavía cobertura versionada completa para los 48 orígenes. Las series de BanRep y BCRPData también carecen aquí de una historia integral de revisiones. La matriz de cobertura está en `results/pronostico/cobertura_vintages_pronostico.csv`.

## Corto y largo plazo: ECM exploratorio

También se estima un ARDL–ECM como contraste. La prueba *bounds* produce F = 3,402, con p-valor de 0,55% para el límite I(0) y de 7,46% para el límite I(1). La cointegración no es concluyente al 5%, de modo que el modelo principal permanece en diferencias para evitar una regresión espuria en niveles.

El coeficiente de ajuste del ECM es −0,0901 (p = 0,00012): condicionalmente, cerca de 9,0% de una brecha se corrige cada mes y la vida media discreta estimada es 7,34 meses (intervalo aproximado de 4,77 a 15,12). Esta velocidad es ilustrativa porque la prueba *bounds* no valida de forma concluyente la relación de largo plazo.

La salida de largo plazo reporta un **vector cointegrante normalizado**, no respuestas de equilibrio ni elasticidades causales directas. Solo el término de dólar amplio es individualmente significativo en ese vector; además, los niveles del ECM presentan colinealidad alta. Por ello no se presenta como una relación de largo plazo aceptada mientras la evidencia de cointegración siga siendo inconclusa.

## Qué representa cada variable

La TRM está expresada como COP por USD: un aumento significa depreciación del peso colombiano. En las entradas, \(\Delta\) es cambio mensual, \(\ln\) es logaritmo natural, `L1` usa el mes anterior y `t` usa información referida al mismo mes.

| Variable activa | Qué mide y fuente | Entrada al modelo | Interpretación y cautela |
|---|---|---|---|
| TRM | Precio promedio mensual del dólar en pesos; [Banco de la República/Superfinanciera, serie 1](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=1). | \(\Delta\ln(\mathrm{TRM})\), variable dependiente. | El cambio logarítmico aproxima la variación porcentual mensual; el promedio oculta volatilidad intrames. |
| Términos de intercambio | Índice mensual encadenado de precios de exportación relativos a importación, base geométrica 2000 = 100; [BanRep, serie 15360](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15360). | \(\Delta\ln\), en `t`; signo esperado negativo. | Una mejora aumenta el poder de compra externo y suele apoyar al COP. Se publica cerca de dos meses después del mes de referencia, por lo que su uso contemporáneo es explicación *ex post*. |
| Índice amplio del dólar | Fortaleza nominal del USD frente a monedas de socios comerciales; [Federal Reserve/FRED, DTWEXBGS](https://fred.stlouisfed.org/series/DTWEXBGS). | \(\Delta\ln\), en `t`; signo esperado positivo. | Separa un movimiento global del dólar de un choque exclusivamente colombiano. No es el DXY de ICE. |
| VIX | Volatilidad implícita y aversión global al riesgo; [Cboe](https://www.cboe.com/tradable_products/vix/vix_historical_data), serie distribuida por FRED como `VIXCLS`. | \(\Delta\ln\), en `t`; signo esperado positivo. | Comparte shocks con dólar amplio, EMBIG y monedas regionales. |
| Remesas | Ingresos mensuales de remesas en millones de USD; [BanRep, serie 15363](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15363). | \(\Delta\ln\) del acumulado móvil de 12 meses, `L1`; signo esperado negativo. | El acumulado reduce estacionalidad, pero solapa once meses. El signo positivo estimado puede reflejar respuesta de los remitentes a una depreciación previa. |
| Diferencial de tasas | Tasa de política colombiana, [BanRep 59](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=59), menos [federal funds, FEDFUNDS](https://fred.stlouisfed.org/series/FEDFUNDS); puntos porcentuales. | \(\Delta\), `L1`; signo esperado negativo. | Un mayor retorno relativo puede apoyar al COP, pero ambas tasas responden endógenamente al ciclo, la inflación y la TRM. |
| Déficit fiscal | Negativo del balance de caja del GNC acumulado 12 meses como porcentaje del PIB; [Ministerio de Hacienda](https://www.minhacienda.gov.co/politica-fiscal/cifras-de-politica-fiscal/gobierno-nacional-central/balance). | \(\Delta\), `L1`; signo esperado positivo. | Es un resultado observado, no un shock fiscal. El PIB anual implícito se aproxima con la mediana del año y puede incorporar información posterior dentro del mismo año. |
| Riesgo soberano EMBIG Colombia | Diferencial soberano diario publicado por [BCRPData, PD04715XD](https://estadisticas.bcrp.gob.pe/estadisticas/series/diarias/tasas-de-interes-embig-variacion-en-pbs), con fuentes originales Reuters/J.P. Morgan. | Promedio mensual en puntos básicos, dividido por 100; el modelo usa \(\Delta\) en puntos porcentuales en `t`. Signo esperado positivo. | Es una canasta de deuda externa con composición y duración variables, no un CDS a cinco años ni una prima estructural pura. El uso contemporáneo es condicional y la metodología del índice es propietaria. |
| Reservas internacionales | Reservas internacionales netas sin FLAR; [BanRep, serie 15053](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15053). | \(\Delta\ln\), `L1`; signo esperado negativo. | La acumulación o venta de reservas puede responder a la propia TRM; también influyen valoración y operaciones oficiales. |
| Balanza comercial cambiaria | Exportaciones menos importaciones canalizadas por el mercado cambiario; [BanRep, serie 16702](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=16702). | \(\Delta\mathrm{asinh}(\mathrm{flujo}/1.000)\), `L1`; signo esperado negativo. | Es flujo de caja cambiario, no balanza de pagos por causación. El signo positivo estimado puede reflejar simultaneidad, composición o endogeneidad. |
| Movimientos netos de capital | Total de movimientos netos de capital de la balanza cambiaria; [BanRep, serie 16706](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=16706). | \(\Delta\mathrm{asinh}(\mathrm{flujo}/1.000)\), `L1`; signo esperado negativo para entradas netas. | Es una serie muy volátil y endógena; el coeficiente ampliado es prácticamente nulo, aunque el factor comparte ajuste con otros regresores. |
| Diferencial de compensación inflacionaria 5 años | Colombia: promedio mensual separado de TES cero cupón nominal [BanRep 15273](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15273) menos TES UVR [BanRep 15276](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15276). EE. UU.: promedio mensual de `BKEVEN05` del modelo [Gürkaynak–Sack–Wright del Federal Reserve Board](https://www.federalreserve.gov/data/tips-yield-curve-and-inflation-compensation.htm). | Colombia menos EE. UU., nivel en puntos porcentuales, `L1`; signo esperado positivo. | Es compensación de mercado, no una expectativa pura ni una encuesta: contiene primas de riesgo de inflación, plazo y liquidez. Con constante y rezagos BIC, ADF (p = 0,013) y KPSS (p ≥ 0,10) favorecen usar el nivel, pero el resultado es sensible a tendencia y selección de rezagos; no constituye una prueba definitiva. |
| Monedas regionales | Movimiento común de BRL, CLP y MXN por USD, OECD/FRED, y PEN por USD, [BCRPData `PN01207PM`](https://estadisticas.bcrp.gob.pe/estadisticas/series/mensuales/resultados/PN01207PM/html). | Promedio igual de cambios logarítmicos estandarizados. El histórico usa cuatro monedas en `t`; el pronóstico, tres monedas en `L1`. | Media y volatilidad se calibran con 2006–2019. Comparte shocks con controles globales; PEN mejora el ajuste histórico, pero no la comparación BIC de pronóstico. |
| Pandemia 2020 | Indicador para marzo–mayo de 2020. | Variable 0/1 en `t`; sin signo estructural. | Evita atribuir por completo un episodio extremo a los factores económicos; no representa un mecanismo económico único. |

## Construcción y temporización

- TRM, tasa de política, dólar amplio, VIX, EMBIG Colombia y las dos curvas TES a cinco años se agregan a promedio mensual desde observaciones diarias.
- Los componentes colombiano y estadounidense de la compensación inflacionaria se promedian **por separado** antes de restarlos; no se cruzan calendarios diarios distintos.
- Remesas se acumulan en una ventana móvil de 12 meses antes de aplicar el logaritmo.
- El déficit es el negativo del balance de caja mensual del GNC acumulado 12 meses, dividido por el PIB nominal anual implícito en las tablas fiscales.
- Balanza comercial y movimientos de capital usan \(\mathrm{asinh}(\mathrm{flujo}/1.000)\) para admitir valores positivos, negativos y cero; después se diferencian y se rezagan.
- Se guardan factores regionales de tres monedas —BRL, CLP y MXN— y cuatro —las anteriores más PEN—. Ambos son promedios de `z(Δln)` con parámetros calibrados en 2006–2019.
- Variables contemporáneas del ampliado: términos de intercambio, dólar amplio, VIX, EMBIG Colombia y monedas regionales.
- Variables rezagadas un mes: remesas, diferencial de tasas, déficit fiscal, reservas, balanza comercial, movimientos de capital y Diferencial de compensación inflacionaria 5 años.
- El pronóstico usa solo rezagos de uno a tres meses según el calendario de disponibilidad documentado en `results/pronostico/calendario_disponibilidad_pronostico.csv`.

El modelo histórico y el pronóstico son productos distintos. El primero explica con realizaciones contemporáneas; el segundo evita esa anticipación, aunque todavía necesita archivos de *vintages* para una validación genuina en tiempo real. El diccionario completo está en [`data/README.md`](data/README.md).

## Trazabilidad heredada — insumos eliminados

Los siguientes archivos se conservaron como instantáneas heredadas hasta agosto 2026 y fueron eliminados del repositorio al confirmar que no entran en el modelo activo:

| Insumo eliminado | Uso anterior | Sustitución activa |
|---|---|---|
| Brent (`brent_diario_fred.csv`) | Indicador de ingreso externo ligado al petróleo. | Índice de términos de intercambio de Colombia. |
| TES a 10 años y Treasury a 10 años (`tes_10y_banrep.json`, `treasury_10y_diario_fred.csv`) | Proxy TES–Treasury de riesgo local. | EMBIG Colombia mensual. |
| IPC de Colombia y EE. UU. (`ipc_colombia_banrep.json`, `ipc_eeuu_mensual_fred.csv`) | Diferencial de inflación realizada. | Diferencial de compensación inflacionaria de mercado a cinco años. |

Si se necesitan para auditoría histórica, están accesibles en el historial de git.

## Archivos principales

- `deliverables/modelo_trm_colombia.xlsx`: archivo Excel final con resumen, datos, fórmulas, estimaciones, pesos, validación, diagnósticos y fuentes.
- `src/estimate_model.py`: prepara los datos, estima los modelos y guarda los resultados.
- `src/build_workbook.mjs`: construye el archivo Excel auditable a partir de los resultados.
- `src/build_charts.py`: reconstruye los gráficos PNG independientes.
- `src/archive_vintage.py`: crea snapshots inmutables, recupera históricos disponibles y calcula cobertura por factor.
- `graficos/`: imágenes explicativas y guía de lectura.
- `data/vintages/`: manifiestos fechados, catálogo histórico verificado y reglas del archivo hacia adelante.
- `data/modelo_trm_datos_mensuales.csv`: base mensual consolidada.
- `results/explicacion/pesos_explicativos_modelo_ampliado.csv`: descomposición Shapley exacta.
- `results/explicacion/intervalos_bootstrap_pesos_shapley.csv`: intervalos de los pesos mediante bloques mensuales.
- `results/explicacion/estabilidad_submuestras_resumen.csv`: estabilidad de rangos, pesos y signos por corte temporal.
- `results/explicacion/comparacion_modelos.csv`: comparación principal–ampliado sobre la misma muestra.
- `results/pronostico/`: coeficientes, validación y cobertura del pronóstico con rezagos.
- `results/robustez/`: ECM exploratorio, pruebas BEI y contraste de especificaciones.
- `results/`: metadatos de conciliación y control.

## Documentación por carpeta

- [`data/README.md`](data/README.md): fuentes, columnas, unidades, transformaciones, rezagos y calidad de los datos.
- [`src/README.md`](src/README.md): flujo de estimación, funciones principales y reproducción técnica.
- [`results/README.md`](results/README.md): significado y uso de cada resultado CSV y de `metadata.json`.
- [`deliverables/README.md`](deliverables/README.md): contenido y ruta de auditoría del archivo Excel.
- [`graficos/README.md`](graficos/README.md): gráficos independientes y cautelas de lectura.

## Reproducir

Con las dependencias de Python y Node.js instaladas:

```powershell
python .\src\estimate_model.py
node .\src\build_workbook.mjs
python .\src\build_charts.py
```

Las instantáneas fuente están en `data/raw`. Sus enlaces y tratamientos aparecen en la hoja `Fuentes` del archivo Excel final; `data/vintages/2026-08-23/manifest.json` registra la referencia inicial de todas las fuentes activas y `results/metadata.json` conserva los controles clave.

## Fuentes y condiciones de uso

- Series colombianas: [Banco de la República — tasas de cambio y sector externo](https://www.banrep.gov.co/es/estadisticas-economicas/series-historicas/tasas-cambio-sector-externo). Deben citarse Banco de la República e identificador de serie. Su [aviso legal](https://www.banrep.gov.co/es/aviso-legal) remite las series del Portal de Datos Abiertos a sus condiciones y advierte que pueden existir derechos de terceros.
- Balance fiscal: [Ministerio de Hacienda — Gobierno Nacional Central](https://www.minhacienda.gov.co/politica-fiscal/cifras-de-politica-fiscal/gobierno-nacional-central/balance), con atribución al Ministerio de Hacienda y Crédito Público.
- EMBIG Colombia: [BCRPData, serie `PD04715XD`](https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PD04715XD/json/2006-1-1/2026-4-30/esp). Sus [condiciones de uso](https://estadisticas.bcrp.gob.pe/estadisticas/series/ayuda/condiciones-de-uso) permiten reproducir contenido del portal con cita. Debe preservarse la atribución “BCRPData; fuentes originales Reuters/J.P. Morgan”; no se afirma una licencia Creative Commons ni autorización general sobre la metodología o marca EMBIG.
- PEN por USD: [BCRPData, serie `PN01207PM`](https://estadisticas.bcrp.gob.pe/estadisticas/series/mensuales/resultados/PN01207PM/html), promedio interbancario del período. Se reproduce citando BCRPData conforme a sus [condiciones de uso](https://estadisticas.bcrp.gob.pe/estadisticas/series/ayuda/condiciones-de-uso).
- Compensación estadounidense a cinco años: [`BKEVEN05`, Federal Reserve Board](https://www.federalreserve.gov/data/yield-curve-tables/feds200805_1.html), con cita al Board of Governors y a Gürkaynak, Sack y Wright. Es un producto de investigación revisable, no una publicación estadística oficial.
- Controles globales: [FRED — dólar amplio](https://fred.stlouisfed.org/series/DTWEXBGS), [FRED — federal funds](https://fred.stlouisfed.org/series/FEDFUNDS) y [Cboe — VIX](https://www.cboe.com/tradable_products/vix/vix_historical_data). Las series distribuidas por FRED deben citar también la fuente original y respetar los derechos indicados para cada serie.
- Monedas regionales: OECD, distribuidas por FRED, para BRL, CLP y MXN por USD; BCRPData para PEN por USD.

Estas notas documentan procedencia y uso técnico; no sustituyen una revisión jurídica si se planea redistribución comercial.

## Limitaciones y extensiones

### Completado

- Vintages ALFRED descargados (288/288 via API FRED). Cobertura: 3/12 factores aptos para backtest genuino. BanRep y BCRPData no publican vintages.
- Diebold-Mariano aplicado: p = 0.21, no se rechaza igualdad de capacidad predictiva entre el pronóstico y la caminata aleatoria.
- Modelos parsimoniosos evaluados: el top-3 factores tiene mejor BIC y MAPE que los 12 completos.
- GARCH(1,1) ajustado: persistencia 0.94, volatilidad incondicional 2.12%/mes.
- Rolling window (120 meses): 10/14 coeficientes inestables entre mitades.
- Pronóstico multihorizonte (h=1,2,3,6): R² negativo vs caminata en todos los horizontes.
- Threshold regression: sin no-linealidades significativas (VIX, dólar, EMBIG como umbrales).
- Variables candidatas evaluadas (MICH, NFCI, T10Y2Y, STLFSI): ninguna aporta al pronóstico.
- Modelo combinado (interacciones + asimetría + outliers): R² 66%, ARCH resuelto.

### Pendiente

1. Adoptar formalmente el modelo combinado como especificación activa (requiere actualizar el pipeline principal).
2. Completar el backtest genuino para los 6 factores con vintages parciales (usar los CSV FRED descargados para recalcular pronósticos reales).
3. Conseguir vintages de BanRep/BCRPData si los proveedores eventualmente los publican.
4. Implementar scheduled snapshots (GitHub Actions cron) para archivo mensual hacia adelante.
