# Archivo Excel del modelo de TRM

`modelo_trm_colombia.xlsx` reúne en un solo archivo Excel los datos, transformaciones, estimaciones, controles y fuentes del modelo mensual de COP por USD. Está diseñado para lectura ejecutiva y auditoría técnica.

## Contenido de las 11 hojas

1. **Resumen**: principales métricas del modelo principal y el ampliado, lectura económica de la especificación base, comparación de desempeño, pesos Shapley destacados y cautelas de interpretación.
2. **Datos_fuente**: niveles mensuales de todas las series. Incluye unidades, comentarios con enlaces y la bandera `IPC EE. UU. interpolado`, que vale 1 únicamente en octubre de 2025.
3. **Transformaciones**: fórmulas enlazadas a `Datos_fuente` para logaritmos, primeras diferencias, rezagos auditables, transformaciones `asinh`, diferenciales y factor regional.
4. **Modelo_principal**: coeficientes con errores HAC, métricas del ajuste y reconstrucción mensual por contribuciones. Las referencias a coeficientes se determinan por nombre del término, no por una posición fija.
5. **Modelo_ampliado**: coeficientes y diagnósticos de la especificación ampliada, ajuste histórico, contribución mensual de cada término y control que reconcilia la suma de contribuciones con el cambio ajustado.
6. **Pesos_explicativos**: descomposición Shapley/LMG del R² incremental, tabla completa, gráfico de columnas y controles de suma del R² y de las participaciones.
7. **Validacion**: comparación del modelo principal, el ampliado y la caminata aleatoria; métricas agregadas, observaciones mensuales y gráfico de TRM observada frente a los comparadores.
8. **ECM_exploratorio**: prueba bounds, valores críticos y coeficientes de corto y largo plazo del contraste ARDL–ECM. Se identifica expresamente como exploratorio.
9. **Diagnosticos**: pruebas de integración, selección de rezagos y diagnósticos residuales de los modelos principal y ampliado, con alertas visibles para ARCH y no normalidad.
10. **Variables**: mapa económico de variables, transformación, signo esperado, canal, justificación, cautela y estado dentro del modelo principal, ampliado o extensiones futuras.
11. **Fuentes**: organismo, código, frecuencia, cobertura, uso, tratamiento y URL de cada serie.

## Ruta de auditoría recomendada

1. Empiece en `Fuentes` para identificar el organismo y código de cada serie.
2. Compruebe los niveles y unidades en `Datos_fuente`. Los vacíos no se reemplazan por cero. La única interpolación interna documentada es CPIAUCNS de octubre de 2025 y queda marcada en una columna específica.
3. Siga las fórmulas de `Transformaciones`. La balanza y los flujos se convierten de USD millones a USD miles de millones, pasan por `asinh` y entran como primeras diferencias rezagadas; el factor regional es el promedio igual ponderado de retornos estandarizados de BRL, CLP y MXN, con parámetros calibrados en 2006–2019.
4. En `Modelo_principal` o `Modelo_ampliado`, verifique que cada cambio ajustado sea la suma del intercepto y las contribuciones de sus regresores. El residuo debe ser cambio observado menos cambio ajustado.
5. En `Pesos_explicativos`, compruebe tres identidades: la suma Shapley coincide con el R² incremental; R² base más R² incremental coincide con R² completo; y los pesos entre factores suman 100%, salvo redondeo.
6. Use `Validacion` para recalcular MAE, RMSE, MAPE y acierto de dirección y comparar con la caminata aleatoria.
7. Termine en `Diagnosticos` y `ECM_exploratorio` antes de extraer conclusiones económicas.

## Cómo interpretar los pesos

El peso Shapley responde cuánto aporta cada factor a la explicación incremental dentro de la muestra, promediando todos los órdenes de entrada de las variables. Esto distribuye la información compartida entre factores correlacionados.

No equivale al tamaño del coeficiente, a su p-valor ni a un porcentaje causal del precio del dólar. Los pesos pueden cambiar con la muestra, las transformaciones, los rezagos y la agrupación de variables.

## Cautelas principales

- Las regresiones describen asociaciones dinámicas; no prueban causalidad.
- La validación es condicional porque usa realizaciones contemporáneas de varios factores. No es un pronóstico estrictamente disponible en tiempo real.
- El modelo ampliado mejora varias métricas de ajuste y error, pero no supera al principal en todos los criterios, incluido el acierto de dirección.
- ARCH-LM rechaza ausencia de volatilidad condicional en el modelo ampliado y Jarque–Bera rechaza normalidad. HAC fortalece la inferencia de la ecuación de media, pero no modela la volatilidad ni las colas extremas.
- Remesas, flujos de capital, reservas y variables fiscales pueden responder a la propia TRM; sus coeficientes pueden reflejar endogeneidad.
- La interpolación del IPC estadounidense afecta una sola observación y está identificada para que pueda excluirse en una prueba de sensibilidad.
- El factor regional está estandarizado con una ventana histórica fija; su escala no representa un cambio porcentual directo de una moneda concreta.
- La prueba bounds no confirma cointegración al 5%. Los resultados de largo plazo del ECM son exploratorios.

## Uso recomendado

Para una explicación mensual, combine el signo y magnitud de las contribuciones en `Modelo_ampliado` con los pesos de `Pesos_explicativos`. Para comparar especificaciones, use conjuntamente R² ajustado, AIC/BIC, validación frente a caminata aleatoria y diagnósticos. No base una conclusión en una sola celda o indicador.
