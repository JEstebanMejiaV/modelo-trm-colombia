# Archivo Excel del modelo de TRM

> Índice del área: [`docs/operacion/salidas.md`](../docs/operacion/salidas.md) · [`docs/README.md`](../docs/README.md).
>
> Este README describe las hojas del workbook y su ruta de auditoría. El archivo efectivo es [`modelo_trm_colombia.xlsx`](modelo_trm_colombia.xlsx); las cifras deben reconciliarse con los CSV y el manifest de corrida.

`modelo_trm_colombia.xlsx` reúne en un solo archivo Excel los datos, transformaciones, estimaciones, controles y fuentes del modelo mensual de COP por USD. Está diseñado para lectura ejecutiva y auditoría técnica.

## Contenido de las 14 hojas

1. **Resumen**: métricas de las especificaciones de controles externos y financieros y del marco macroeconómico integral, lectura económica, comparación descriptiva, pesos Shapley y cautelas de interpretación.
2. **Datos_fuente**: niveles mensuales de todas las series activas. Incluye ISE total DANE, IPC Colombia, PEN por USD, términos de intercambio, EMBIG Colombia, curvas TES nominal y UVR a cinco años, compensación de inflación estadounidense y la base global FRED consolidada.
3. **Transformaciones**: fórmulas enlazadas a `Datos_fuente` para logaritmos, primeras diferencias, rezagos auditables, transformaciones `asinh`, diferencial BEI, factores regionales y el bloque `Condiciones financieras, commodities y actividad internacional`.
4. **Controles_externos**: coeficientes con errores HAC, métricas del ajuste y reconstrucción mensual por contribuciones. Las referencias a coeficientes se determinan por nombre del término, no por una posición fija.
5. **Marco_macro_integral**: coeficientes y diagnósticos del marco macroeconómico integral, ajuste histórico, contribución mensual de cada término y control que reconcilia la suma de contribuciones con el cambio ajustado.
6. **Pesos_explicativos**: descomposición Shapley/LMG del R² incremental, tabla completa, gráfico de columnas y controles de suma del R² y de las participaciones.
7. **Robustez**: intervalos bootstrap de los pesos, estabilidad por submuestras y cobertura de vintages. Es completamente tabular y no añade gráficos al archivo Excel.
8. **BEI_robustez**: comparación tabular de nivel, primera diferencia, tendencias, quiebres y agregación sobre promedios separados o fechas comunes. No añade gráficos al archivo Excel.
9. **Validacion**: comparación de las especificaciones de controles externos y financieros, del marco macroeconómico integral y de la caminata aleatoria; métricas agregadas, observaciones mensuales y gráfico de TRM observada frente a los comparadores.
10. **Pronostico**: comparación regional 3–4, calendario de disponibilidad, coeficientes, diagnósticos y predicciones del modelo con información rezagada. Es una hoja tabular, sin gráfico añadido.
11. **ECM_exploratorio**: prueba bounds, valores críticos y coeficientes de corto y largo plazo del contraste ARDL–ECM. Se identifica expresamente como exploratorio.
12. **Diagnosticos**: pruebas de integración, selección de rezagos y diagnósticos residuales de las especificaciones de controles externos y financieros y del marco macroeconómico integral, con alertas visibles para ARCH y no normalidad.
13. **Variables**: mapa económico de variables, transformación, signo esperado, canal, justificación, cautela y estado dentro de las especificaciones de controles externos y financieros, del marco macroeconómico integral o del pronóstico.
14. **Fuentes**: organismo, código, frecuencia, cobertura, uso, tratamiento y URL de cada serie.

### Variables internas activas

`Datos_fuente` y `Transformaciones` incluyen `ln_ise_total_dane` y `ln_ipc_colombia`. Ambas cubren 244/244 meses y se calculan con logaritmo y primera diferencia sin imputación. GEIH, IPI e IPP aparecen en la matriz de cobertura, pero no se activan por faltantes o inicio tardío.

## Ruta de auditoría recomendada

1. Empiece en `Fuentes` para identificar el organismo y código de cada serie.
2. Compruebe los niveles y unidades en `Datos_fuente`. Los vacíos se conservan como faltantes en la capa activa.
3. Siga las fórmulas de `Transformaciones`. El factor regional de tres monedas usa BRL, CLP y MXN; el de cuatro agrega PEN. Ambos promedian `z(Δln)` con parámetros calibrados en 2006–2019.
4. En `Controles_externos` o `Marco_macro_integral`, verifique que cada cambio ajustado sea la suma del intercepto y las contribuciones de sus regresores. El residuo debe ser cambio observado menos cambio ajustado.
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
- `Validacion` es condicional porque usa realizaciones contemporáneas. `Pronostico` usa rezagos de publicación, pero solo 3 de 14 factores activos tienen vintages versionados completos para los 48 orígenes; por eso sigue siendo pseudo-tiempo-real.
- En la muestra actual, el marco macroeconómico integral se reporta con métricas regeneradas desde los CSV y el peso Shapley del bloque `Condiciones financieras, commodities y actividad internacional`; la tabla `comparacion_especificaciones.csv` es la referencia numérica vigente.
- El pronóstico mensual obtiene MAPE de `2,49%`, acierto de dirección de `52,08%`, frente a `2,39%` de la caminata aleatoria, y R² frente a ese benchmark de `−1,46%`.
- En el marco macroeconómico integral, Jarque–Bera rechaza normalidad al 5%, pero ARCH-LM no rechaza heterocedasticidad condicional (p = `0,220`); RESET no rechaza al 5% (p = `0,162`). No se detecta autocorrelación ni inestabilidad CUSUM (p = `0,722`).
- Remesas, flujos de capital, reservas y variables fiscales pueden responder a la propia TRM; sus coeficientes pueden reflejar endogeneidad.
- Los términos de intercambio se usan contemporáneamente para explicación *ex post*, pero suelen publicarse con cerca de dos meses de rezago.
- EMBIG Colombia procede de BCRPData, que identifica como fuentes originales a Reuters/J.P. Morgan. Debe conservarse esa atribución; la disponibilidad de la descarga no constituye una licencia abierta sobre la metodología o la marca EMBIG.
- El diferencial BEI a cinco años entra en primera diferencia porque el nivel es sensible a tendencias. La agregación sobre fechas comunes es casi idéntica, pero puede conservar solo 4 días en un mes. El BEI compara compensaciones de mercado, no expectativas puras.
- Los factores regionales están estandarizados con una ventana histórica fija; su escala no representa un cambio porcentual directo de una moneda concreta. PEN mejora la explicación histórica, no el pronóstico.
- La prueba bounds no confirma cointegración al 5%. Los resultados de largo plazo del ECM son exploratorios.

## Resultados de corto y largo plazo

El archivo Excel documenta el modelo mensual y sus salidas auditables. Los análisis diarios y de largo plazo se mantienen tabulares en `results/pronostico/`: el mejor HAR con señales globales adicionales tiene R² OOS de 13,41%, aunque dirección 41,2% y Sharpe −3,91; la señal global de actividad a 12 meses alcanza R² OOS de 12,8% (DM p = 0,006), y la wavelet D3+D4+D5 45,9%. No se deben comparar estas cifras sin considerar frecuencia, horizonte y benchmark.

Cuando `@oai/artifact-tool` no está disponible, `src/sync_workbook_openpyxl.py` reconstruye las tablas auditables del entregable desde los CSV actuales y deja el workbook marcado para recálculo al abrirlo en Excel.

## Uso recomendado

Para una explicación mensual, combine las contribuciones de `Marco_macro_integral` con los pesos de `Pesos_explicativos`. Para una decisión ex ante, use `Pronostico` y mantenga la caminata aleatoria como benchmark. No mezcle las métricas históricas y de pronóstico ni base una conclusión en una sola celda.
