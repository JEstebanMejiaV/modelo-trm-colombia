# Diccionario y trazabilidad de los datos

Este directorio contiene tres capas distintas. No deben confundirse los archivos fuente con la base mensual ni esta última con la matriz que finalmente entra a la estimación.

## Convenciones

- La fecha se guarda como el primer día del mes (`AAAA-MM-01`).
- La variable que se explica es el precio del dólar en Colombia, medido como COP por USD. Un aumento significa depreciación del peso colombiano.
- En las tablas, signo `+` significa que se espera un aumento de COP/USD; signo `−`, una disminución de COP/USD.
- `ln(x)` es el logaritmo natural; `Δx_t = x_t - x_{t-1}`; `L1` es un rezago mensual; `pp` significa puntos porcentuales.
- Los signos son hipótesis económicas, no resultados causales ni restricciones impuestas a la regresión.
- Las series diarias se convierten en promedios aritméticos mensuales. TES y Treasury se promedian por separado antes de calcular su spread, por lo que no se cruzan calendarios diarios con festivos diferentes.
- Los faltantes se conservan vacíos: no se sustituyen por cero. La única excepción actual es el IPC estadounidense de octubre de 2025, documentada abajo.

## Las tres capas

### 1. Datos fuente: `data/raw`

Son instantáneas de las descargas originales en JSON, CSV o Excel. `src/estimate_model.py` las lee, pero no las descarga ni las modifica. Los archivos que consume actualmente son:

| Archivo raw | Serie y fuente | Frecuencia de origen | Tratamiento al consolidar |
|---|---|---:|---|
| `trm_diaria_banrep.json` | TRM, BanRep/Superfinanciera, serie `1` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=1)) | Diaria | Promedio mensual |
| `brent_diario_fred.csv` | Brent spot Europa, EIA/FRED `DCOILBRENTEU` ([serie](https://fred.stlouisfed.org/series/DCOILBRENTEU)) | Diaria | Promedio mensual |
| `tasa_politica_diaria_banrep.json` | Tasa de política, BanRep `59` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=59)) | Diaria | Promedio mensual |
| `fed_funds_mensual_fred.csv` | Federal funds, Fed/FRED `FEDFUNDS` ([serie](https://fred.stlouisfed.org/series/FEDFUNDS)) | Mensual | Se lleva al primer día del mes |
| `dolar_amplio_diario_fred.csv` | Índice amplio nominal del USD, Fed/FRED `DTWEXBGS` ([serie](https://fred.stlouisfed.org/series/DTWEXBGS)) | Diaria | Promedio mensual |
| `vix_diario_fred.csv` | VIX, Cboe/FRED `VIXCLS` ([serie](https://fred.stlouisfed.org/series/VIXCLS)) | Diaria | Promedio mensual |
| `remesas_mensuales_banrep.json` | Ingresos de remesas, BanRep `15363` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15363)) | Mensual | Sin agregación adicional |
| `series_15360_15368.json` | Términos de intercambio, BanRep `15360` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15360)) | Mensual | El código selecciona solo `15360` |
| `reservas_netas_sin_flar_banrep.json` | Reservas netas sin FLAR, BanRep `15053` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15053)) | Mensual, cierre de mes | Sin agregación adicional |
| `tes_10y_banrep.json` | TES COP cero cupón a 10 años, BanRep `15274` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15274)) | Diaria | Promedio mensual |
| `treasury_10y_diario_fred.csv` | Treasury constant maturity a 10 años, Fed/FRED `DGS10` ([serie](https://fred.stlouisfed.org/series/DGS10)) | Diaria | Promedio mensual |
| `balanza_comercial_cambiaria_banrep.json` | Balanza comercial cambiaria, BanRep `16702` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=16702)) | Mensual | Sin agregación adicional |
| `flujos_capital_totales_banrep.json` | Movimientos netos de capital, BanRep `16706` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=16706)) | Mensual | Sin agregación adicional |
| `ipc_colombia_banrep.json` | IPC total nacional, DANE/BanRep `15000` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15000)) | Mensual | Sin agregación adicional |
| `ipc_eeuu_mensual_fred.csv` | CPI urbano total no ajustado, BLS/FRED `CPIAUCNS` ([serie](https://fred.stlouisfed.org/series/CPIAUCNS)) | Mensual | Interpolación excepcional indicada abajo |
| `brl_usd_mensual_fred.csv` | BRL por USD, OECD/FRED `CCUSMA02BRM618N` ([serie](https://fred.stlouisfed.org/series/CCUSMA02BRM618N)) | Mensual | Sin agregación adicional |
| `clp_usd_mensual_fred.csv` | CLP por USD, OECD/FRED `CCUSMA02CLM618N` ([serie](https://fred.stlouisfed.org/series/CCUSMA02CLM618N)) | Mensual | Sin agregación adicional |
| `mxn_usd_mensual_fred.csv` | MXN por USD, OECD/FRED `CCUSMA02MXM618N` ([serie](https://fred.stlouisfed.org/series/CCUSMA02MXM618N)) | Mensual | Sin agregación adicional |
| `balance_fiscal_gnc_mensual_trimestral.xlsx` | Balance del Gobierno Nacional Central, Ministerio de Hacienda ([fuente](https://www.minhacienda.gov.co/documents/d/portal/balance-fiscal-gnc-mensual-y-trimestral?download=true)) | Mensual/anual en hojas del archivo Excel | Se leen balance e ingresos en montos e ingresos como porcentaje del PIB |

El archivo de Brent que usa el código es `DCOILBRENTEU`, diario. La referencia `RBRTE` que puede aparecer en otros materiales corresponde a la versión mensual de EIA, no al encabezado del CSV raw actual.

### 2. Base mensual consolidada

`modelo_trm_datos_mensuales.csv` es la unión externa mensual de todas las fuentes y de las variables construidas. Actualmente tiene 1.364 filas, 45 columnas y va de enero de 1913 a agosto de 2026. La amplitud de fechas no implica que todas las columnas tengan datos en todo el período; por ejemplo, la fecha inicial proviene del IPC de EE. UU. y agosto de 2026 contiene solo las fuentes que ya estaban disponibles.

### 3. Muestra balanceada para estimación

`modelo_trm_muestra_estimacion.csv` contiene únicamente las 16 columnas de nivel o transformación previa necesarias para estimar. Se crea desde enero de 2006, se eliminan las filas con algún faltante y se exige frecuencia mensual sin huecos. La muestra actual tiene 244 meses, de enero de 2006 a abril de 2026.

Este CSV todavía no es la matriz final de regresores: durante la estimación se calculan primeras diferencias y rezagos. Para comparar todos los candidatos sobre las mismas fechas se reserva la muestra común correspondiente al máximo de tres rezagos de `Δln(TRM)`. Por ello, aunque BIC selecciona cero rezagos adicionales de TRM, la regresión efectiva usa 240 observaciones, de mayo de 2006 a abril de 2026.

## Diccionario de la base consolidada

Todas las columnas tienen frecuencia mensual después de la consolidación.

### Columnas fuente y fiscales básicas

| Columna exacta | Definición, unidad y origen | Uso/rezago y signo esperado | Cautela principal |
|---|---|---|---|
| `fecha` | Mes de referencia, guardado como `AAAA-MM-01`. | Índice temporal; sin signo ni rezago. | No representa necesariamente el día original de observación. |
| `trm_cop_usd` | Promedio mensual de la TRM diaria; COP por USD; BanRep `1`. | Variable objetivo; un aumento es depreciación del COP. | El promedio mensual oculta volatilidad intrames. |
| `brent_usd_barril` | Promedio mensual de Brent `DCOILBRENTEU`; USD/barril. | Se usa mediante `Δln_brent` en `t`; signo `−`. | Colombia no exporta exclusivamente Brent y petróleo también afecta riesgo y cuentas fiscales. |
| `tasa_politica_colombia_pct` | Promedio mensual de la tasa de política BanRep `59`; porcentaje efectivo anual. | Entra solo a través del diferencial de tasas; por sí sola se espera `−`. | Es una respuesta endógena a inflación, actividad y TRM. |
| `fed_funds_eeuu_pct` | Tasa federal funds mensual `FEDFUNDS`; porcentaje. | Se resta de la tasa colombiana; dentro del diferencial su signo mecánico es opuesto, `+` sobre COP/USD. | Una tasa de EE. UU. más alta también opera por canales globales no aislados aquí. |
| `indice_dolar_amplio` | Promedio mensual de `DTWEXBGS`; índice nominal amplio, ene-2006=100. | Se usa mediante `Δln_dolar_amplio` en `t`; signo `+`. | No es el DXY comercial de ICE. |
| `vix` | Promedio mensual de `VIXCLS`; puntos del índice VIX. | Se usa mediante `Δln_vix` en `t`; signo `+`. | Comparte shocks de aversión al riesgo con dólar amplio y monedas regionales. |
| `remesas_usd_millones` | Ingresos mensuales de remesas BanRep `15363`; millones de USD. | Alimenta el acumulado de 12 meses; signo esperado `−`. | Es estacional, se publica con rezago y puede reaccionar a la depreciación. |
| `terminos_intercambio` | Índice BanRep `15360`: precios de exportación relativos a precios de importación. | Robustez: se usaría como `Δln`, signo `−`, sustituyendo a Brent. | No se incluye junto con Brent en el núcleo para evitar duplicar el canal externo. |
| `reservas_netas_sin_flar_usd_millones` | Reservas internacionales netas sin FLAR, BanRep `15053`; millones de USD al cierre del mes. | Alimenta `Δln` con `L1`; signo esperado `−`. | La acumulación o venta de reservas puede responder a la propia TRM; no es un shock exógeno. |
| `tes_10y_colombia_pct` | Promedio mensual de la tasa cero cupón TES COP a 10 años, BanRep `15274`; porcentaje. | Se usa solo dentro del spread TES−UST; mayor TES sugiere signo `+`. | Incluye expectativas de inflación/depreciación, duración y liquidez; no es un CDS o EMBI. |
| `treasury_10y_eeuu_pct` | Promedio mensual de `DGS10`; porcentaje. | Se resta del TES en el spread. | Su signo aislado es ambiguo: estrecha mecánicamente el spread, pero tasas de EE. UU. altas pueden presionar al COP. |
| `balanza_comercial_cambiaria_usd_millones` | Exportaciones menos importaciones canalizadas en la balanza cambiaria, BanRep `16702`; millones de USD. | Se transforma con `asinh(flujo/1000)`, se diferencia y entra con `L1`; signo `−`. | Es flujo de caja cambiario, no la balanza de pagos por causación; es simultánea con la TRM. |
| `flujos_capital_usd_millones` | Movimientos netos totales de capital de la balanza cambiaria, BanRep `16706`; millones de USD. | Se transforma con `asinh(flujo/1000)`, se diferencia y entra con `L1`; signo `−` para entradas netas. | Muy volátil y endógeno; no confundir con la serie `16708`, que cubre solo sector real y Gobierno. |
| `ipc_colombia` | IPC DANE/BanRep `15000`; índice base dic-2018=100. | Alimenta inflación interanual; mayor inflación relativa sugiere signo `+`. | Es inflación observada, no expectativa; el nivel no entra directamente. |
| `ipc_eeuu` | CPI urbano total no ajustado `CPIAUCNS`; índice 1982–1984=100. | Alimenta inflación interanual; mayor inflación de EE. UU. reduce el diferencial, signo `−` dentro de este canal. | En el consolidado incluye la interpolación de 2025-10; el raw permanece vacío. |
| `brl_por_usd` | Reales brasileños por USD, OECD/FRED `CCUSMA02BRM618N`. | Alimenta el factor regional; aumento = depreciación regional, signo `+`. | No entra individualmente y comparte shocks con controles globales. |
| `clp_por_usd` | Pesos chilenos por USD, OECD/FRED `CCUSMA02CLM618N`. | Alimenta el factor regional; aumento = depreciación regional, signo `+`. | No entra individualmente. |
| `mxn_por_usd` | Pesos mexicanos por USD, OECD/FRED `CCUSMA02MXM618N`. | Alimenta el factor regional; aumento = depreciación regional, signo `+`. | No entra individualmente. |
| `balance_fiscal_miles_millones_cop` | Balance de caja mensual del GNC; miles de millones de COP; MinHacienda, hoja de montos, fila 31. Superávit es positivo y déficit negativo. | Insumo del acumulado de 12 meses; una mejora tendría signo `−`. | Dato observado, no sorpresa fiscal exógena. |
| `ingresos_totales_miles_millones_cop` | Ingresos totales mensuales del GNC; miles de millones de COP; hoja de montos, fila 8. | Auxiliar para inferir PIB; no entra y no tiene signo modelado. | El nivel puede tener estacionalidad fiscal. |
| `ingresos_totales_pct_pib` | Ingresos totales del GNC como porcentaje del PIB; hoja porcentual, fila 8. | Auxiliar para inferir PIB; no entra y no tiene signo modelado. | Se usa como denominador; ceros o faltantes no producen PIB implícito. |

### Columnas construidas

| Columna exacta | Fórmula, unidad y origen | Uso/rezago y signo esperado | Cautela principal |
|---|---|---|---|
| `pib_anual_miles_millones_cop_observado` | `100 × ingresos_totales_miles_millones_cop / ingresos_totales_pct_pib`; miles de millones de COP. | Auxiliar; sin signo modelado. | Es un PIB anual implícito observado mes a mes, no una descarga directa de cuentas nacionales. |
| `pib_anual_miles_millones_cop` | Mediana anual de `pib_anual_miles_millones_cop_observado`; miles de millones de COP. | Denominador fiscal; sin signo separado. | Todos los meses de un año reciben la misma mediana; puede incorporar información del resto de ese año. |
| `balance_fiscal_12m_miles_millones_cop` | Suma móvil de 12 meses del balance fiscal; miles de millones de COP. | Insumo del déficit; una mejora tendría signo `−`. | Requiere 12 observaciones y solapa once meses entre períodos consecutivos. |
| `deficit_fiscal_12m_pct_pib` | `−100 × balance_fiscal_12m / PIB_anual`; porcentaje del PIB, con déficit positivo. | El modelo usa `Δ` con `L1`; signo `+`. | No es un shock fiscal; depende del PIB implícito y de una ventana móvil. |
| `remesas_12m_usd_millones` | Suma móvil de 12 meses de remesas; millones de USD. | Alimenta `ln_remesas_12m`; signo `−`. | Suaviza estacionalidad, pero induce fuerte solapamiento temporal. |
| `diferencial_tasas_pp` | `tasa_politica_colombia_pct − fed_funds_eeuu_pct`; pp. | El modelo usa `Δ` con `L1`; signo `−`. | Diferencial nominal; no descuenta inflación esperada ni riesgo. |
| `spread_tes_ust_10y_pp` | `tes_10y_colombia_pct − treasury_10y_eeuu_pct`; pp. | El modelo usa `Δ` contemporáneo; signo `+`. | Proxy amplio de riesgo local, no prima soberana pura; uso contemporáneo implica nowcast, no pronóstico ex ante. |
| `ipc_eeuu_interpolado` | Bandera: `1` si el IPC de EE. UU. era vacío y fue interpolado internamente; `0` en otro caso. | Trazabilidad; no entra y no tiene signo. | Actualmente vale `1` solo en 2025-10. |
| `inflacion_colombia_interanual_pct` | `100 × (ipc_colombia / ipc_colombia_L12 − 1)`; porcentaje interanual. | Componente del diferencial; signo relativo `+`. | Observada y retrospectiva, no expectativa. |
| `inflacion_eeuu_interanual_pct` | `100 × (ipc_eeuu / ipc_eeuu_L12 − 1)`; porcentaje interanual. | Se resta al construir el diferencial; signo relativo `−`. | Hereda la interpolación de 2025-10. |
| `diferencial_inflacion_pp` | Inflación interanual de Colombia menos la de EE. UU.; pp. | Entra en nivel con `L1`; signo `+`. | Proxy de precios relativos observados; no mide expectativas comparables. |
| `asinh_balanza_comercial` | `asinh(balanza_comercial_cambiaria_usd_millones / 1000)`; transformación adimensional sobre USD miles de millones. | El modelo usa su primera diferencia con `L1`; signo `−`. | El nivel transformado no es estacionario; `asinh` conserva signo y admite cero, pero el coeficiente no es una elasticidad constante. |
| `asinh_flujos_capital` | `asinh(flujos_capital_usd_millones / 1000)`; transformación adimensional sobre USD miles de millones. | El modelo usa su primera diferencia con `L1`; signo `−`. | El nivel transformado no es estacionario; se mantienen las cautelas de escala y endogeneidad de los flujos. |
| `factor_monedas_regionales` | Promedio simple de los `z(Δln)` de BRL, CLP y MXN por USD. Media y desviación estándar poblacional (`ddof=0`) se calibran en 2006-01 a 2019-12. | Ya es una variable de cambio; entra contemporánea; signo `+`. | Exige las tres monedas (`skipna=False`), puede absorber información de VIX/dólar y no está disponible ex ante para todo el mes. |

### Logaritmos y controles

| Columna exacta | Definición | Uso/rezago y signo esperado | Cautela principal |
|---|---|---|---|
| `ln_trm` | `ln(trm_cop_usd)`, adimensional. | La dependiente es `Δln_trm`; aumento = depreciación. BIC selecciona `p=0`. | El cambio log no se multiplica por 100 en la regresión. |
| `ln_brent` | `ln(brent_usd_barril)`. | Se diferencia y entra en `t`; signo `−`. | Solo se calcula para valores positivos. |
| `ln_remesas_12m` | `ln(remesas_12m_usd_millones)`. | Se diferencia y entra con `L1`; signo `−`. | Puede reflejar respuesta de remitentes a la TRM. |
| `ln_dolar_amplio` | `ln(indice_dolar_amplio)`. | Se diferencia y entra en `t`; signo `+`. | Contemporáneo: útil para explicación/nowcast, no pronóstico puro. |
| `ln_vix` | `ln(vix)`. | Se diferencia y entra en `t`; signo `+`. | El modelo vuelve a calcular `D.ln_vix` a partir de esta columna. |
| `ln_terminos_intercambio` | `ln(terminos_intercambio)`. | Robustez: usar `Δ` en `t`, signo `−`; no está en la muestra actual. | Sustituir a Brent en una especificación alternativa. |
| `ln_reservas_netas_sin_flar` | `ln(reservas_netas_sin_flar_usd_millones)`. | Se diferencia y entra con `L1`; signo `−`. | Endogeneidad por intervención y valoración de activos. |
| `dln_vix` | `ln_vix − ln_vix_L1`. | No es un regresor separado en los modelos mensuales base/ampliado; se usa contemporáneo como variable fija en el ECM exploratorio. Signo `+`. | Duplica numéricamente `D.ln_vix`; no incluir ambos en la misma ecuación. |
| `dummy_pandemia_2020` | `1` entre 2020-03 y 2020-05, ambos inclusive; `0` en otro mes. | Control contemporáneo; se anticipa signo `+`, sin interpretación estructural. | Resume un episodio excepcional y no identifica un canal económico único. |

## Columnas de la muestra de estimación y temporización efectiva

El encabezado exacto de `modelo_trm_muestra_estimacion.csv` es:

```text
fecha,ln_trm,ln_brent,ln_remesas_12m,diferencial_tasas_pp,deficit_fiscal_12m_pct_pib,ln_dolar_amplio,ln_vix,dln_vix,spread_tes_ust_10y_pp,ln_reservas_netas_sin_flar,asinh_balanza_comercial,asinh_flujos_capital,diferencial_inflacion_pp,factor_monedas_regionales,dummy_pandemia_2020
```

La matriz del modelo ampliado se construye así:

| Entrada del CSV de muestra | Regresor efectivo | Rezago | Signo esperado |
|---|---|---:|:---:|
| `ln_trm` | `Δln_trm`, variable dependiente | `t` | objetivo |
| `ln_brent` | `Δln_brent` | `t` | `−` |
| `ln_remesas_12m` | `Δln_remesas_12m` | `L1` | `−` |
| `diferencial_tasas_pp` | `Δdiferencial_tasas_pp` | `L1` | `−` |
| `deficit_fiscal_12m_pct_pib` | `Δdeficit_fiscal_12m_pct_pib` | `L1` | `+` |
| `ln_dolar_amplio` | `Δln_dolar_amplio` | `t` | `+` |
| `ln_vix` | `Δln_vix` | `t` | `+` |
| `dln_vix` | Solo ECM exploratorio; no se agrega al modelo ampliado junto a `Δln_vix` | `t` | `+` |
| `spread_tes_ust_10y_pp` | `Δspread_tes_ust_10y_pp` | `t` | `+` |
| `ln_reservas_netas_sin_flar` | `Δln_reservas_netas_sin_flar` | `L1` | `−` |
| `asinh_balanza_comercial` | `Δasinh` | `L1` | `−` |
| `asinh_flujos_capital` | `Δasinh` | `L1` | `−` |
| `diferencial_inflacion_pp` | Nivel del diferencial interanual | `L1` | `+` |
| `factor_monedas_regionales` | Factor de cambios estandarizados | `t` | `+` |
| `dummy_pandemia_2020` | Dummy | `t` | Sin signo estructural |

Brent, dólar amplio, VIX, spread TES−Treasury y factor regional usan información realizada dentro del mismo mes que la TRM. Por tanto, el modelo ampliado es una contabilidad histórica o nowcast condicional; no es un pronóstico disponible al comienzo del mes ni una identificación causal.

## Interpolación de `CPIAUCNS` en octubre de 2025

El CSV raw actual contiene:

| Mes | `CPIAUCNS` raw |
|---|---:|
| 2025-09 | 324,800 |
| 2025-10 | vacío |
| 2025-11 | 324,122 |

`build_dataset()` aplica `interpolate(limit=1, limit_area="inside")` únicamente sobre la serie de IPC de EE. UU. Esto rellena como máximo una observación consecutiva por hueco interior, pero no extrapola extremos. En los datos actuales existe un único hueco, octubre de 2025, y el cálculo es:

```text
ipc_eeuu_2025-10 = (324,800 + 324,122) / 2 = 324,461
```

Consecuencias y trazabilidad:

- `data/raw/ipc_eeuu_mensual_fred.csv` permanece sin modificar y conserva la celda vacía.
- En `modelo_trm_datos_mensuales.csv`, `ipc_eeuu=324.461` y `ipc_eeuu_interpolado=1` en 2025-10.
- Con ese valor, `inflacion_eeuu_interanual_pct=2.786823965` y `diferencial_inflacion_pp=2.726629418` en ese mes.
- Todos los demás meses tienen `ipc_eeuu_interpolado=0`.
- Si una descarga futura incorpora el dato oficial, al reconstruir la base se usará ese valor y la bandera volverá automáticamente a cero.

La interpolación evita cortar la muestra balanceada, pero añade una observación estimada. Por ello debe conservarse la bandera y realizarse, como robustez, una estimación que excluya octubre de 2025 o que use otra fuente/vintage del IPC.
