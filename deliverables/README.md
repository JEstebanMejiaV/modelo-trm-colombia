# Archivo Excel del modelo de TRM

`modelo_trm_colombia.xlsx` reúne en un solo archivo Excel los datos, transformaciones, estimaciones, controles y fuentes del modelo mensual de COP por USD. Está diseñado para lectura ejecutiva y auditoría técnica.

## Contenido de las 14 hojas

1. **Resumen**: principales métricas del modelo principal y el ampliado, lectura económica de la especificación base, comparación de desempeño, pesos Shapley destacados y cautelas de interpretación.
2. **Datos_fuente**: niveles mensuales de todas las series activas. Incluye PEN por USD, términos de intercambio, EMBIG Colombia, curvas TES nominal y UVR a cinco años, compensación de inflación estadounidense y la base global FRED consolidada.
3. **Transformaciones**: fórmulas enlazadas a `Datos_fuente` para logaritmos, primeras diferencias, rezagos auditables, transformaciones `asinh`, diferencial BEI, factores regionales y el bloque de variables globales nuevas.
4. **Modelo_principal**: coeficientes con errores HAC, métricas del ajuste y reconstrucción mensual por contribuciones. Las referencias a coeficientes se determinan por nombre del término, no por una posición fija.
5. **Modelo_ampliado**: coeficientes y diagnósticos de la especificación ampliada, ajuste histórico, contribución mensual de cada término y control que reconcilia la suma de contribuciones con el cambio ajustado.
6. **Pesos_explicativos**: descomposición Shapley/LMG del R² incremental, tabla completa, gráfico de columnas y controles de suma del R² y de las participaciones.
7. **Robustez**: intervalos bootstrap de los pesos, estabilidad por submuestras y cobertura de vintages. Es completamente tabular y no añade gráficos al archivo Excel.
8. **BEI_robustez**: comparación tabular de nivel, primera diferencia, tendencias, quiebres y agregación sobre promedios separados o fechas comunes. No añade gráficos al archivo Excel.
9. **Validacion**: comparación del modelo principal, el ampliado y la caminata aleatoria; métricas agregadas, observaciones mensuales y gráfico de TRM observada frente a los comparadores.
10. **Pronostico**: comparación regional 3–4, calendario de disponibilidad, coeficientes, diagnósticos y predicciones del modelo con información rezagada. Es una hoja tabular, sin gráfico añadido.
11. **ECM_exploratorio**: prueba bounds, valores críticos y coeficientes de corto y largo plazo del contraste ARDL–ECM. Se identifica expresamente como exploratorio.
12. **Diagnosticos**: pruebas de integración, selección de rezagos y diagnósticos residuales de los modelos principal y ampliado, con alertas visibles para ARCH y no normalidad.
13. **Variables**: mapa económico de variables, transformación, signo esperado, canal, justificación, cautela y estado dentro del modelo principal, ampliado o pronóstico.
14. **Fuentes**: organismo, código, frecuencia, cobertura, uso, tratamiento y URL de cada serie.

## Ruta de auditoría recomendada

1. Empiece en `Fuentes` para identificar el organismo y código de cada serie.
2. Compruebe los niveles y unidades en `Datos_fuente`. Los vacíos se conservan como faltantes en la capa activa.
3. Siga las fórmulas de `Transformaciones`. El factor regional de tres monedas usa BRL, CLP y MXN; el de cuatro agrega PEN. Ambos promedian `z(Δln)` con parámetros calibrados en 2006–2019.
4. En `Modelo_principal` o `Modelo_ampliado`, verifique que cada cambio ajustado sea la suma del intercepto y las contribuciones de sus regresores. El residuo debe ser cambio observado menos cambio ajustado.
5. En `Pesos_explicativos`, compruebe tres identidades: la suma Shapley coincide con el R² incremental; R² base más R² incremental coincide con R² completo; y los pesos entre factores suman 100%, salvo redondeo.
6. En `Robustez`, contraste el peso puntual con su intervalo, los cortes temporales y la cobertura de vintages.
7. En `BEI_robustez`, compruebe por qué se adopta la primera diferencia y cuánto cambia al cruzar calendarios diarios.
8. Use `Validacion` solo para la explicación condicional con realizaciones contemporáneas.
9. Use `Pronostico` para comprobar el calendario de publicación, la selección de tres monedas y la comparación honesta con la caminata aleatoria.
10. Termine en `Diagnosticos` y `ECM_exploratorio` antes de extraer conclusiones económicas.

## Cómo interpretar los pesos

El peso Shapley responde cuánto aporta cada factor a la explicación incremental dentro de la muestra, promediando todos los órdenes de entrada de las variables. Esto distribuye la información compartida entre factores correlacionados.

No equivale al tamaño del coeficiente, a su p-valor ni a un porcentaje causal del precio del dólar. Los pesos pueden cambiar con la muestra, las transformaciones, los rezagos y la agrupación de variables.

## Cautelas principales

- Las regresiones describen asociaciones dinámicas; no prueban causalidad.
- `Validacion` es condicional porque usa realizaciones contemporáneas. `Pronostico` usa rezagos de publicación, pero solo 3 de 13 factores activos tienen vintages versionados completos para los 48 orígenes; por eso sigue siendo pseudo-tiempo-real.
- En la muestra actual, el ampliado alcanza R² ajustado de `0,611`, MAPE condicional de `1,62%` y acierto de dirección de `79,17%`; el peso Shapley del bloque global es `17,33%`.
- El pronóstico mensual obtiene MAPE de `2,68%`, frente a `2,39%` de la caminata aleatoria, y R² frente a ese benchmark de `−13,38%`.
- En el ampliado, ARCH-LM y Jarque–Bera rechazan sus hipótesis nulas; RESET no rechaza al 5%. No se detecta autocorrelación ni inestabilidad CUSUM.
- Remesas, flujos de capital, reservas y variables fiscales pueden responder a la propia TRM; sus coeficientes pueden reflejar endogeneidad.
- Los términos de intercambio se usan contemporáneamente para explicación *ex post*, pero suelen publicarse con cerca de dos meses de rezago.
- EMBIG Colombia procede de BCRPData, que identifica como fuentes originales a Reuters/J.P. Morgan. Debe conservarse esa atribución; la disponibilidad de la descarga no constituye una licencia abierta sobre la metodología o la marca EMBIG.
- El diferencial BEI a cinco años entra en primera diferencia porque el nivel es sensible a tendencias. La agregación sobre fechas comunes es casi idéntica, pero puede conservar solo 4 días en un mes. El BEI compara compensaciones de mercado, no expectativas puras.
- Los factores regionales están estandarizados con una ventana histórica fija; su escala no representa un cambio porcentual directo de una moneda concreta. PEN mejora la explicación histórica, no el pronóstico.
- La prueba bounds no confirma cointegración al 5%. Los resultados de largo plazo del ECM son exploratorios.

## Resultados de corto y largo plazo

El archivo Excel documenta el modelo mensual y sus salidas auditables. Los análisis diarios y de largo plazo se mantienen tabulares en `results/pronostico/`: el mejor HAR con señales globales tiene R² OOS de 13,20%, aunque dirección 41,6% y Sharpe −4,03; la señal global de actividad a 12 meses alcanza R² OOS de 12,8% (DM p = 0,006), y la wavelet D3+D4+D5 45,9%. No se deben comparar estas cifras sin considerar frecuencia, horizonte y benchmark.

## Uso recomendado

Para una explicación mensual, combine las contribuciones de `Modelo_ampliado` con los pesos de `Pesos_explicativos`. Para una decisión ex ante, use `Pronostico` y mantenga la caminata aleatoria como benchmark. No mezcle las métricas históricas y de pronóstico ni base una conclusión en una sola celda.
