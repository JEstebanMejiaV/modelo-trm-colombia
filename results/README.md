# Resultados econométricos

Esta carpeta contiene las salidas tabulares del modelo mensual de la TRM. La especificación principal usa siete regresores y la ampliada agrega riesgo TES–Treasury, reservas, balanza comercial cambiaria, flujos de capital, diferencial de inflación y monedas regionales. Todas las estimaciones describen asociaciones estadísticas; no identifican efectos causales.

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

## Comparación de modelos

### `comparacion_modelos.csv`

Compara la especificación base y la ampliada sobre la misma muestra.

- R² y R² ajustado mayores indican más variación explicada dentro de muestra; el ajustado penaliza parámetros adicionales.
- AIC y BIC menores favorecen el modelo bajo su penalización respectiva, siempre que la variable dependiente y la muestra sean iguales.
- `mape_pct` menor indica menor error porcentual absoluto medio en la validación condicional.
- `acierto_direccion_pct` mayor indica más meses con el signo correcto del cambio.
- `r2_validacion_condicional_vs_caminata` compara errores cuadrados con la caminata aleatoria; valores positivos indican mejora en la validación expansiva condicional. No es un R² de pronóstico ex ante porque usa algunos predictores contemporáneos ya realizados.

No debe elegirse un modelo con una sola métrica. En los resultados actuales, el ampliado mejora R², criterios de información, MAPE y R² frente a la caminata, y mantiene el mismo acierto de dirección que el principal.

## Validación condicional

### `validacion_metricas.csv` y `validacion_metricas_modelo_ampliado.csv`

Presentan observaciones, MAE y RMSE en logaritmos, MAPE y acierto de dirección para una ventana expansiva de 48 meses. Cada archivo incluye su modelo y la caminata aleatoria como referencia.

### `validacion_predicciones.csv` y `validacion_predicciones_modelo_ampliado.csv`

Contienen las observaciones mensuales de esa validación: TRM observada, estimación condicional, caminata aleatoria y cambios logarítmicos. Permiten recalcular las métricas y revisar meses extremos.

La validación es explicativa y condicional: utiliza realizaciones contemporáneas de factores globales, riesgo TES–Treasury y monedas regionales. No representa un pronóstico estrictamente disponible en tiempo real.
Los coeficientes se reestiman en cada ventana expansiva, pero la cantidad de rezagos queda fijada por la selección hecha con la muestra completa. El denominador fiscal anual también usa la mediana del PIB implícito de todos los meses del año, por lo que no reproduce un conjunto de datos con vintages en tiempo real.

## Diagnósticos y selección

### `diagnosticos_modelo_principal.csv` y `diagnosticos_modelo_ampliado.csv`

Incluyen Ljung–Box y Breusch–Godfrey para autocorrelación, ARCH-LM para volatilidad condicional, Jarque–Bera para normalidad, Ramsey RESET para forma funcional, CUSUM para estabilidad y Durbin–Watson como referencia. La interpretación usual se hace al 5%.

El modelo ampliado rechaza ausencia de ARCH y normalidad. HAC protege la inferencia de la ecuación de media, pero no sustituye un modelo explícito de volatilidad ni elimina el riesgo de colas extremas.

### `seleccion_rezagos_adl_diferencias.csv` y `seleccion_rezagos_modelo_ampliado.csv`

Comparan de cero a tres rezagos del cambio de la TRM mediante AIC, BIC y R² ajustado. El BIC mínimo respalda la alternativa parsimoniosa seleccionada.

### `pruebas_integracion.csv`

Reporta ADF y KPSS para niveles y diferencias, con número de observaciones y rezagos. ADF tiene como nula la presencia de raíz unitaria; KPSS, la estacionariedad. Deben interpretarse conjuntamente y con cautela ante quiebres estructurales.

## Contraste ARDL–ECM

### `seleccion_rezagos_ecm.csv`

Compara combinaciones de rezagos del ARDL mediante AIC, BIC, HQIC y log-verosimilitud.

### `bounds_resumen.csv` y `bounds_criticos.csv`

`bounds_resumen.csv` contiene el estadístico F y p-valores frente a los casos I(0) e I(1); `bounds_criticos.csv`, los límites por percentil. La evidencia actual de cointegración al 5% es no concluyente porque el p-valor I(1) supera 0,05.

### `coeficientes_corto_plazo_ecm.csv` y `coeficientes_largo_plazo_ecm.csv`

Separan la dinámica de corto plazo y las relaciones normalizadas de largo plazo del ECM. Dado que la prueba bounds no confirma cointegración al 5%, los coeficientes de largo plazo son exploratorios y no deben presentarse como un equilibrio estable.

### `diagnosticos_ecm.csv`

Contiene las pruebas residuales del contraste ECM con la misma lógica general de los diagnósticos anteriores.

## Nombres heredados en copias locales

En carpetas locales antiguas pueden aparecer `ajuste_historico.csv`, `coeficientes_corto_plazo.csv`, `coeficientes_largo_plazo.csv`, `diagnosticos.csv` o `seleccion_rezagos.csv`. Son alias obsoletos: el proyecto actual no los regenera ni los versiona. Para automatizaciones y citas deben usarse los nombres explícitos que terminan en `_modelo_principal`, `_modelo_ampliado` o `_ecm`.

## Metadatos

`metadata.json` resume muestra, observaciones, temporización, métricas, selección de rezagos, resultados bounds, construcción del factor regional, interpolación documentada del IPC estadounidense y controles de conciliación Shapley.
