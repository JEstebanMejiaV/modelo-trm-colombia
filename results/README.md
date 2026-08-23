# Resultados econométricos

Esta carpeta contiene las salidas tabulares del modelo mensual de la TRM. La especificación principal usa seis factores económicos y una dummy de pandemia; la ampliada lleva el total a 12 factores al agregar EMBIG Colombia, reservas, balanza comercial cambiaria, flujos de capital, diferencial BEI a cinco años y monedas regionales. También se separa una ecuación de pronóstico que solo usa información rezagada. Todas las estimaciones describen asociaciones estadísticas; no identifican efectos causales.

## Convenciones de lectura

- `D.variable` indica primera diferencia mensual.
- `.L0` indica que la variable entra contemporáneamente y `.L1`, con un mes de rezago.
- `ln` es logaritmo natural. En una relación log–log, el coeficiente se aproxima a una elasticidad para cambios pequeños.
- Las variables en puntos porcentuales se interpretan por un cambio de 1 pp, no por 1%.
- `asinh` es el seno hiperbólico inverso aplicado a flujos expresados en miles de millones de USD. Conserva el signo y reduce la influencia de valores extremos.
- Los errores estándar de los modelos principal y ampliado son HAC. El `p_valor` y los intervalos de confianza deben leerse con esa inferencia robusta.
- Un p-valor bajo indica incompatibilidad con un coeficiente cero bajo los supuestos del modelo; no demuestra causalidad ni importancia económica por sí solo.

## Coeficientes, ajuste y contribuciones

### `coeficientes_modelo_principal.csv`

Coeficientes de la ecuación principal en diferencias. Las columnas contienen el término, coeficiente, error estándar HAC, estadístico t, p-valor e intervalo de confianza del 95%.

### `coeficientes_modelo_ampliado.csv`

La misma estructura para el modelo ampliado. Para comparar magnitudes deben respetarse las unidades y transformaciones: no es válido comparar directamente un coeficiente logarítmico con otro medido en puntos porcentuales o `asinh`.

Tres términos requieren una lectura particular:

- `D.ln_terminos_intercambio.L0` es el cambio logarítmico contemporáneo de los términos de intercambio. El dato se publica con un rezago aproximado de dos meses, por lo que sirve para explicación *ex post*, no para un pronóstico disponible al comienzo de `t`.
- `D.embig_colombia_pp.L0` es el cambio contemporáneo del promedio mensual de EMBIG Colombia, convertido de puntos básicos a puntos porcentuales. La instantánea procede de BCRPData, que atribuye la serie a Reuters/J.P. Morgan; debe conservarse esa atribución y no interpretarse la descarga pública como licencia abierta sobre la metodología o marca EMBIG.
- `diferencial_bei_5y_pp.L1` es la compensación de inflación colombiana a cinco años menos la estadounidense, rezagada un mes. El BEI incorpora primas de riesgo de inflación y diferencias de liquidez: es compensación de mercado, no una expectativa pura ni una encuesta.
- `factor_monedas_regionales_4.L0` es el promedio igual de cambios log estandarizados de BRL, CLP, MXN y PEN por USD. PEN procede de BCRPData `PN01207PM`. Es contemporáneo y pertenece a la explicación histórica, no al pronóstico seleccionado.

### `ajuste_historico_modelo_principal.csv` y `ajuste_historico_modelo_ampliado.csv`

Reconstruyen, por mes, el cambio logarítmico observado y ajustado, el nivel de TRM observado, el ajuste de un paso y el residuo. El ajuste de un paso parte de la TRM observada del mes anterior; por ello no es una trayectoria de pronóstico recursivo de largo horizonte.

### `contribuciones_modelo_principal.csv` y `contribuciones_modelo_ampliado.csv`

Descomponen el cambio logarítmico ajustado de cada mes en `coeficiente × regresor`. Incluyen el intercepto, cada término y la dummy de pandemia. `ajuste_total` debe ser igual a la suma horizontal de las contribuciones, salvo diferencias mínimas de redondeo.

Estas contribuciones sirven para explicar un mes concreto: valor positivo implica presión de depreciación del COP frente al USD y valor negativo, presión de apreciación. No deben confundirse con los pesos Shapley, que resumen capacidad explicativa a lo largo de toda la muestra.

## Peso explicativo Shapley

### `pesos_explicativos_modelo_ampliado.csv`

Aplica una descomposición Shapley/LMG exacta del incremento del R² sobre el bloque base. El bloque base contiene intercepto, la dinámica seleccionada de la TRM y la dummy de pandemia; con la selección actual no entran rezagos adicionales de la TRM.

- `factor`, `grupo` y `terminos`: identificación económica y términos que forman cada factor.
- `coeficiente_modelo` y `p_valor_hac`: resultado del término en la regresión completa. El peso Shapley y la significancia responden preguntas distintas.
- `shapley_r2`: aporte del factor al R² en unidades decimales.
- `aporte_r2_puntos_porcentuales`: el mismo aporte expresado en puntos porcentuales de R².
- `peso_entre_factores_pct`: participación dentro del R² incremental atribuible a los factores. Debe sumar 100%, salvo redondeo.
- `peso_r2_total_pct`: aporte del factor como porcentaje del R² completo. Su suma es menor que 100% cuando el bloque base también explica variación.
- `r2_base`, `r2_completo` y `r2_incremental`: controles de conciliación. Debe cumplirse `r2_base + r2_incremental = r2_completo` y la suma de `shapley_r2` debe coincidir con `r2_incremental`.

Shapley promedia todos los órdenes posibles de incorporación y reparte la información compartida entre variables correlacionadas. El resultado depende de la especificación, muestra y agrupación elegidas; no mide participación causal ni importancia estructural permanente.

### `intervalos_bootstrap_pesos_shapley.csv`

Añade incertidumbre de remuestreo a los pesos puntuales. Usa 200 réplicas de bloques circulares de 12 meses para conservar dependencia local; dentro de cada réplica aproxima la asignación Shapley con 64 permutaciones antitéticas y una semilla fija. Reporta media, mediana, intervalo percentil del 95%, probabilidad de quedar entre los tres primeros factores y los parámetros de reproducción. El peso puntual sigue siendo el Shapley exacto de 4.096 subconjuntos.

Los intervalos de monedas regionales (`20,66%–34,56%`), dólar amplio (`11,87%–27,43%`) y EMBIG Colombia (`12,23%–26,21%`) se solapan. Esto respalda que el grupo dominante es robusto, pero no un orden exacto e inmutable entre sus integrantes.

### `estabilidad_submuestras_modelo_ampliado.csv` y `estabilidad_submuestras_resumen.csv`

Reestiman la especificación ampliada en la muestra completa, ambas mitades, prepandemia y 2020 en adelante. El detalle incluye coeficiente, p-valor HAC, Shapley exacto, rango, cambio de peso y coincidencia de signo. El resumen reporta R² ajustado, correlación de rangos de Spearman y desviaciones absolutas frente a la muestra completa.

La correlación de rangos permanece entre `0,944` y `0,972`. No obstante, 2020–2026 conserva el signo de solo 7 de 12 coeficientes y registra un cambio máximo de peso de `6,71 p.p.`. La importancia relativa es más estable que los signos parciales; ambos resultados deben mostrarse juntos.

## Comparación de modelos

### `comparacion_modelos.csv`

Compara la especificación base y la ampliada sobre la misma muestra.

- R² y R² ajustado mayores indican más variación explicada dentro de muestra; el ajustado penaliza parámetros adicionales.
- AIC y BIC menores favorecen el modelo bajo su penalización respectiva, siempre que la variable dependiente y la muestra sean iguales.
- `mape_pct` menor indica menor error porcentual absoluto medio en la validación condicional.
- `acierto_direccion_pct` mayor indica más meses con el signo correcto del cambio.
- `r2_validacion_condicional_vs_caminata` compara errores cuadrados con la caminata aleatoria; valores positivos indican mejora en la validación expansiva condicional. No es un R² de pronóstico ex ante porque usa algunos predictores contemporáneos ya realizados.

No debe elegirse un modelo con una sola métrica. En los resultados actuales, el ampliado histórico de cuatro monedas mejora el R² ajustado (`0,581` frente a `0,479`), AIC (`−1150,02` frente a `−1103,31`), BIC (`−1101,29` frente a `−1075,46`), MAPE condicional (`1,69%` frente a `2,01%`), acierto de dirección (`81,25%` frente a `68,75%`) y R² condicional frente a la caminata (`0,490` frente a `0,319`).

## Factor regional y pronóstico

### `comparacion_factor_regional.csv`

Compara los factores regionales de tres monedas —BRL, CLP y MXN— y cuatro —las anteriores más PEN— en dos usos distintos. Contiene R² ajustado, BIC, validación, coeficiente regional y p-valor HAC. En la muestra actual, cuatro monedas dominan en la explicación histórica, mientras tres monedas obtienen menor BIC y MAPE en el pronóstico. `correlacion_factores_3_4` es 0,9581.

### `calendario_disponibilidad_pronostico.csv`

Documenta el rezago conservador asignado a cada factor y la regla de información disponible al comienzo del mes objetivo. Ningún factor económico usa `.L0`.

### `seleccion_rezagos_modelo_pronostico.csv`

Compara de cero a tres rezagos de `Δln(TRM)` mediante AIC, BIC y R² ajustado. BIC selecciona un rezago.

### `coeficientes_modelo_pronostico.csv`

Reporta coeficientes e inferencia HAC de la ecuación seleccionada. Los términos económicos usan rezagos de uno a tres meses y el factor regional activo es `factor_monedas_regionales_3.L1`.

### `validacion_metricas_pronostico.csv` y `validacion_predicciones_pronostico.csv`

Miden una ventana expansiva de 48 meses para el pronóstico y la caminata aleatoria. El pronóstico obtiene MAPE de 2,63%, acierto de dirección de 47,92% y R² frente a caminata de −0,115; la caminata obtiene MAPE de 2,39%. El resultado documenta que el modelo explicativo no supera el benchmark cuando se restringe la información al origen.

### `diagnosticos_modelo_pronostico.csv`

Incluye las mismas pruebas residuales del resto de ecuaciones. No rechaza autocorrelación, ARCH, RESET ni inestabilidad al 5%; Jarque–Bera sí rechaza normalidad.

La validación respeta rezagos de publicación, pero usa la versión más reciente disponible de cada serie. Se denomina **pseudo-tiempo-real**: `cobertura_vintages_pronostico.csv` muestra que 0 de 12 factores tienen los 48 orígenes versionados completos. Un backtest genuino exige cobertura simultánea de todos los factores.

### `cobertura_vintages_pronostico.csv`

Resume por factor el proveedor, estado, orígenes completos, porcentaje de cobertura, fecha inicial del archivo hacia adelante y aptitud individual para un backtest genuino. La ruta ALFRED está implementada con validación y caché reanudable, pero el proveedor cortó la descarga individual; el paquete multiserie fue rechazado porque contenía observaciones posteriores al origen. Las series de BanRep/BCRPData y el balance fiscal tampoco tienen una colección binaria completa por fecha de origen.

## Validación condicional

### `validacion_metricas.csv` y `validacion_metricas_modelo_ampliado.csv`

Presentan observaciones, MAE y RMSE en logaritmos, MAPE y acierto de dirección para una ventana expansiva de 48 meses. Cada archivo incluye su modelo y la caminata aleatoria como referencia.

### `validacion_predicciones.csv` y `validacion_predicciones_modelo_ampliado.csv`

Contienen las observaciones mensuales de esa validación: TRM observada, estimación condicional, caminata aleatoria y cambios logarítmicos. Permiten recalcular las métricas y revisar meses extremos.

La validación es explicativa y condicional: utiliza realizaciones contemporáneas de términos de intercambio, dólar amplio, VIX, EMBIG Colombia y monedas regionales. No representa un pronóstico estrictamente disponible en tiempo real; además, los términos de intercambio de `t` suelen conocerse cerca de dos meses después.
Los coeficientes se reestiman en cada ventana expansiva, pero la cantidad de rezagos queda fijada por la selección hecha con la muestra completa. El denominador fiscal anual también usa la mediana del PIB implícito de todos los meses del año, por lo que no reproduce un conjunto de datos con vintages en tiempo real.

## Diagnósticos y selección

### `diagnosticos_modelo_principal.csv` y `diagnosticos_modelo_ampliado.csv`

Incluyen Ljung–Box y Breusch–Godfrey para autocorrelación, ARCH-LM para volatilidad condicional, Jarque–Bera para normalidad, Ramsey RESET para forma funcional, CUSUM para estabilidad y Durbin–Watson como referencia. La interpretación usual se hace al 5%.

Al 5%, el modelo ampliado rechaza ausencia de ARCH (`p = 0,0007`) y normalidad (`p = 0,0002`), pero RESET no rechaza (`p = 0,101`). No hay evidencia de autocorrelación en Ljung–Box o Breusch–Godfrey ni de inestabilidad según CUSUM. HAC protege la inferencia de la ecuación de media frente a heterocedasticidad y autocorrelación de forma robusta, pero no modela la volatilidad ni normaliza las colas.

### `seleccion_rezagos_adl_diferencias.csv` y `seleccion_rezagos_modelo_ampliado.csv`

Comparan de cero a tres rezagos del cambio de la TRM mediante AIC, BIC y R² ajustado. El BIC mínimo respalda la alternativa parsimoniosa seleccionada.

### `pruebas_integracion.csv`

Reporta ADF y KPSS para niveles y diferencias, con número de observaciones y rezagos. ADF tiene como nula la presencia de raíz unitaria; KPSS, la estacionariedad. Para el diferencial BEI, la especificación con constante y rezagos BIC favorece el nivel, pero el resultado es sensible a tendencia y selección de rezagos; no debe presentarse como una conclusión definitiva. Todas las pruebas requieren cautela ante quiebres estructurales.

## Contraste ARDL–ECM

### `seleccion_rezagos_ecm.csv`

Compara combinaciones de rezagos del ARDL mediante AIC, BIC, HQIC y log-verosimilitud.

### `bounds_resumen.csv` y `bounds_criticos.csv`

`bounds_resumen.csv` contiene el estadístico F y p-valores frente a los casos I(0) e I(1); `bounds_criticos.csv`, los límites por percentil. La evidencia actual de cointegración al 5% es no concluyente porque el p-valor I(1) supera 0,05.

### `coeficientes_corto_plazo_ecm.csv` y `coeficientes_largo_plazo_ecm.csv`

Separan la dinámica de corto plazo y las relaciones normalizadas de largo plazo del ECM. `coeficientes_largo_plazo_ecm.csv` reporta el vector cointegrante con el coeficiente de `ln_trm` normalizado a 1. Para expresar la respuesta de equilibrio de la TRM ante una explicativa se debe invertir el signo de ese término —y de los extremos de su intervalo—. En variables logarítmicas el resultado es una elasticidad; en tasas o déficit medidos en puntos porcentuales es una semielasticidad. Dado que la prueba bounds no confirma cointegración al 5%, estos valores son exploratorios y no deben presentarse como un equilibrio estable.

### `diagnosticos_ecm.csv`

Contiene las pruebas residuales del contraste ECM con la misma lógica general de los diagnósticos anteriores.

## Nombres heredados en copias locales

En carpetas locales antiguas pueden aparecer `ajuste_historico.csv`, `coeficientes_corto_plazo.csv`, `coeficientes_largo_plazo.csv`, `diagnosticos.csv` o `seleccion_rezagos.csv`. Son alias obsoletos: el proyecto actual no los regenera ni los versiona. Para automatizaciones y citas deben usarse los nombres explícitos que terminan en `_modelo_principal`, `_modelo_ampliado` o `_ecm`.

## Metadatos

`metadata.json` resume muestra, observaciones, temporización, métricas, selección de rezagos, resultados bounds, comparación regional, especificación de pronóstico y controles de conciliación Shapley. También registra parámetros del bootstrap, estabilidad reciente, cobertura de vintages, fecha de archivo y SHA-256 de las instantáneas clave.
