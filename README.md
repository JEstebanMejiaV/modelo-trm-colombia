# Modelo econométrico de la TRM en Colombia

Este proyecto estima un modelo mensual para explicar la variación del precio del dólar en Colombia, medido como pesos colombianos por dólar estadounidense (TRM promedio mensual).

## Resultado principal

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

## Decisión metodológica

Se estimó también un ARDL–ECM. La prueba bounds produjo F = 3,414 y p-valor del límite I(1) = 7,31%. La cointegración no es concluyente al 5%; por eso el ECM se conserva solo como contraste exploratorio y el modelo principal se presenta en diferencias para evitar una regresión espuria en niveles.

Los resultados describen asociaciones dinámicas, no efectos causales. Para hacer afirmaciones causales se necesitarían shocks identificados, como sorpresas monetarias, cambios fiscales inesperados o shocks petroleros externos.

## Construcción de variables

- TRM, tasa de política, Brent, índice amplio del dólar y VIX: promedio mensual de datos diarios.
- Remesas: flujo mensual en dólares; el modelo usa el acumulado móvil de 12 meses en logaritmos.
- Diferencial de tasas: tasa de política de Colombia menos federal funds, en puntos porcentuales.
- Déficit fiscal: negativo del balance de caja mensual del Gobierno Nacional Central; se acumula durante 12 meses y se divide por el PIB nominal anual implícito en las tablas de MinHacienda.
- Variables globales contemporáneas: Brent, dólar amplio y VIX.
- Variables domésticas rezagadas un mes: remesas, diferencial de tasas y déficit fiscal.

## Archivos principales

- `deliverables/modelo_trm_colombia.xlsx`: libro final con resumen, datos, fórmulas, estimación, validación, diagnósticos y fuentes.
- `src/estimate_model.py`: prepara los datos, estima los modelos y guarda los resultados.
- `src/build_workbook.mjs`: construye el libro auditable a partir de los resultados.
- `data/modelo_trm_datos_mensuales.csv`: base mensual consolidada.
- `results/`: coeficientes, diagnósticos, pruebas y validación.

## Reproducir la estimación

Con Python, pandas, NumPy, SciPy, statsmodels y openpyxl instalados:

```powershell
python .\src\estimate_model.py
```

Las series fuente descargadas están en `data/raw`. Sus enlaces y tratamientos exactos aparecen en la hoja `Fuentes` del libro final.

## Extensiones recomendadas

Las siguientes ampliaciones deben probarse por bloques, no todas a la vez:

1. Riesgo soberano específico de Colombia: CDS a cinco años o EMBI, si se consigue una fuente reproducible.
2. Términos de intercambio como sustituto de Brent.
3. Inflación esperada Colombia–EE. UU. para construir un diferencial real de tasas.
4. Monedas regionales —BRL, CLP, MXN y PEN— como factor común latinoamericano.
5. Reservas internacionales, balanza comercial, flujos de capital e intervención cambiaria, con rezagos y pruebas de endogeneidad.
