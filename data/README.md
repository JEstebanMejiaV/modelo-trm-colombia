# Diccionario y trazabilidad de los datos

> Índice del área: [`docs/datos/README.md`](../docs/datos/README.md) · fuentes y catálogo · transformaciones · vintages · política de faltantes.
>
> Este archivo conserva el diccionario técnico exhaustivo, las URLs y las notas de atribución. El registro ejecutable de fuentes es [`data/catalog/sources.json`](catalog/sources.json); los contratos están en [`schemas/`](../schemas/).

Este directorio contiene tres capas distintas. No deben confundirse los archivos fuente con la base mensual ni esta última con la matriz que finalmente entra a la estimación.

## Registro canónico de fuentes

`data/catalog/sources.json` es el registro canónico de proveedor, serie, archivo
raw, transformación, rezago de disponibilidad y atribución. `data/vintages/`
conserva snapshots y manifiestos por fecha de origen; no reemplaza el catálogo.
Los contratos ejecutables correspondientes viven en `schemas/`.


- La fecha se guarda como el primer día del mes (`AAAA-MM-01`).
- La variable que se explica es el precio del dólar en Colombia, medido como COP por USD. Un aumento significa depreciación del peso colombiano.
- En las tablas, signo `+` significa que se espera un aumento de COP/USD; signo `−`, una disminución de COP/USD.
- `ln(x)` es el logaritmo natural; `Δx_t = x_t - x_{t-1}`; `L1` es un rezago mensual; `pp` significa puntos porcentuales y `pb`, puntos básicos (`100 pb = 1 pp`).
- Los signos son hipótesis económicas, no resultados causales ni restricciones impuestas a la regresión.
- Las series diarias se convierten en promedios aritméticos mensuales usando únicamente las observaciones publicadas. La especificación activa promedia por separado las dos curvas TES y el BEI estadounidense; la robustez también calcula el diferencial solo sobre fechas diarias comunes.
- Los faltantes se conservan vacíos: no se sustituyen por cero ni se interpolan en la capa activa.

## Las tres capas

### 1. Datos fuente: `data/raw`

Son instantáneas de las descargas originales en JSON, CSV o Excel. `src/estimate_model.py` las lee, pero no las descarga ni las modifica. Los archivos que consume actualmente son:

| Archivo raw | Serie y fuente | Frecuencia de origen | Tratamiento al consolidar |
|---|---|---:|---|
| `trm_diaria_banrep.json` | TRM, BanRep/Superfinanciera, serie `1` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=1)) | Diaria | Promedio mensual |
| `tasa_politica_diaria_banrep.json` | Tasa de política, BanRep `59` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=59)) | Diaria | Promedio mensual |
| `fed_funds_mensual_fred.csv` | Federal funds, Fed/FRED `FEDFUNDS` ([serie](https://fred.stlouisfed.org/series/FEDFUNDS)) | Mensual | Se lleva al primer día del mes |
| `dolar_amplio_diario_fred.csv` | Índice amplio nominal del USD, Fed/FRED `DTWEXBGS` ([serie](https://fred.stlouisfed.org/series/DTWEXBGS)) | Diaria | Promedio mensual |
| `vix_diario_fred.csv` | VIX, Cboe/FRED `VIXCLS` ([serie](https://fred.stlouisfed.org/series/VIXCLS)) | Diaria | Promedio mensual |
| `remesas_mensuales_banrep.json` | Ingresos de remesas, BanRep `15363` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15363)) | Mensual | Sin agregación adicional |
| `series_15360_15368.json` | Índice de términos de intercambio, BanRep `15360` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15360)) | Mensual | El código selecciona solo `15360`; se conserva el mes de referencia publicado |
| `reservas_netas_sin_flar_banrep.json` | Reservas netas sin FLAR, BanRep `15053` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15053)) | Mensual, cierre de mes | Sin agregación adicional |
| `embig_colombia_diario_bcrp.json` | EMBIG Colombia, BCRPData `PD04715XD` ([serie](https://estadisticas.bcrp.gob.pe/estadisticas/series/diarias/tasas-de-interes-embig-variacion-en-pbs), [API](https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PD04715XD/json/2006-1-1/2026-4-30/esp)); fuentes originales indicadas por BCRP: Reuters/J.P. Morgan | Diaria, puntos básicos | Promedio mensual de observaciones publicadas; luego se divide entre `100` para expresarlo en pp |
| `tes_5y_pesos_banrep.json` | TES cero cupón en pesos a 5 años, BanRep `15273` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15273)) | Diaria, porcentaje | Promedio mensual por separado |
| `tes_5y_uvr_banrep.json` | TES cero cupón en UVR a 5 años, BanRep `15276` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15276)) | Diaria, porcentaje real | Promedio mensual por separado |
| `bei_5y_eeuu_diario_fed.csv` | Compensación de inflación cero cupón a 5 años `BKEVEN05`, modelo Gürkaynak–Sack–Wright del Federal Reserve Board ([datos y metodología](https://www.federalreserve.gov/data/tips-yield-curve-and-inflation-compensation.htm), [tabla](https://www.federalreserve.gov/data/yield-curve-tables/feds200805_1.html)) | Diaria, porcentaje, capitalización continua | Promedio mensual de `BKEVEN05` |
| `balanza_comercial_cambiaria_banrep.json` | Balanza comercial cambiaria, BanRep `16702` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=16702)) | Mensual | Sin agregación adicional |
| `flujos_capital_totales_banrep.json` | Movimientos netos de capital, BanRep `16706` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=16706)) | Mensual | Sin agregación adicional |
| `brl_usd_mensual_fred.csv` | BRL por USD, OECD/FRED `CCUSMA02BRM618N` ([serie](https://fred.stlouisfed.org/series/CCUSMA02BRM618N)) | Mensual | Sin agregación adicional |
| `clp_usd_mensual_fred.csv` | CLP por USD, OECD/FRED `CCUSMA02CLM618N` ([serie](https://fred.stlouisfed.org/series/CCUSMA02CLM618N)) | Mensual | Sin agregación adicional |
| `mxn_usd_mensual_fred.csv` | MXN por USD, OECD/FRED `CCUSMA02MXM618N` ([serie](https://fred.stlouisfed.org/series/CCUSMA02MXM618N)) | Mensual | Sin agregación adicional |
| `pen_usd_mensual_bcrp.json` | PEN por USD, promedio interbancario del período, BCRPData `PN01207PM` ([serie](https://estadisticas.bcrp.gob.pe/estadisticas/series/mensuales/resultados/PN01207PM/html), [API](https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PN01207PM/json/2005-12/2026-4/esp)) | Mensual | Sin agregación adicional; se conserva 2005-12 para calcular el cambio de 2006-01 |
| `ipc_colombia_banrep.json` | Índice de precios al consumidor, BanRep `15000` ([datos](https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15000)) | Mensual | Sin agregación adicional; se transforma en logaritmo y primera diferencia sin imputación |
| `ise_dane_12actividades_jun2026.xlsx` | Indicador de Seguimiento a la Economía (ISE) total, DANE, Cuadro 2 | Mensual | Se selecciona el total nacional; logaritmo y primera diferencia; se conservan vacíos sin imputación |
| `ise_dane_9actividades_jun2026.xlsx` | ISE DANE, Cuadro 2 de 9 actividades | Mensual | Instantánea de contraste sectorial; la especificación activa usa el total de 12 agrupaciones |
| `geih_dane_desestacionalizado_jun2026.xlsx` | GEIH DANE desestacionalizada, total nacional | Mensual | Candidata auditada; no se empalma ni imputa porque faltan 2 meses de la muestra |
| `geih_dane_jun2026.xlsx` | GEIH DANE original, total nacional | Mensual | Candidata auditada; no se empalma ni imputa porque faltan 5 meses de la muestra |
| `ipi_dane_jun2026.xlsx` | Índice de Producción Industrial (IPI) total, DANE | Mensual | Candidata auditada; comienza en 2014-01 y queda fuera de la muestra balanceada |
| `ipp_dane_jul2026.xlsx` | Índice de Precios del Productor (IPP), producción nacional total, DANE | Mensual | Candidata auditada; comienza en 2014-12 y queda fuera de la muestra balanceada |
| `balance_fiscal_gnc_mensual_trimestral.xlsx` | Balance del Gobierno Nacional Central, Ministerio de Hacienda ([fuente](https://www.minhacienda.gov.co/documents/d/portal/balance-fiscal-gnc-mensual-y-trimestral?download=true)) | Mensual/anual en hojas del archivo Excel | Se leen balance e ingresos en montos e ingresos como porcentaje del PIB |

En la construcción activa, las dos tasas TES y `BKEVEN05` se agregan por separado antes de formar el diferencial Colombia−EE. UU. Para comprobar el efecto de calendarios distintos, el consolidado conserva además una versión calculada solo con fechas en las que existen simultáneamente las tres observaciones diarias y registra cuántos días comunes quedan en cada mes.

#### Atribución y condiciones de reutilización

- Las series colombianas deben atribuirse al Banco de la República con su identificador. Su [aviso legal](https://www.banrep.gov.co/es/aviso-legal) remite las series incluidas en el Portal de Datos Abiertos a las condiciones de ese portal; la presencia de una descarga pública no elimina posibles derechos de terceros.
- [BCRPData permite reproducir](https://estadisticas.bcrp.gob.pe/estadisticas/series/ayuda/condiciones-de-uso) total o parcialmente el contenido del portal si se cita la fuente. Para `PD04715XD` debe conservarse la atribución “BCRPData; fuentes originales Reuters/J.P. Morgan”. No se presenta como una licencia Creative Commons ni como una autorización general sobre la metodología o marca EMBIG.
- Para `PN01207PM` se cita BCRPData y se conserva la denominación “tipo de cambio interbancario promedio del período”.
- Para `BKEVEN05` se debe citar al Board of Governors of the Federal Reserve System y el trabajo de Gürkaynak, Sack y Wright. La Junta publica el CSV como dato de investigación; es un producto revisable, no una publicación estadística oficial.
- Los demás archivos obtenidos vía FRED deben citar tanto la fuente original como FRED y respetar la etiqueta de derechos de cada serie según sus [condiciones de uso](https://fred.stlouisfed.org/legal/terms/). La publicación de una serie por FRED no revoca restricciones del proveedor original.
- El archivo fiscal debe atribuirse al Ministerio de Hacienda y Crédito Público. Estas notas documentan procedencia y uso técnico; no sustituyen una revisión jurídica para redistribución comercial.

#### Instantáneas heredadas, no consumidas

Estos archivos se conservan únicamente para auditoría histórica y comparaciones de robustez. La construcción activa no los lee ni genera a partir de ellos variables sustitutas.

| Archivo raw heredado | Uso anterior | Motivo del retiro de la capa activa |
|---|---|---|
| `brent_diario_fred.csv` | Brent `DCOILBRENTEU` | Sustituido por el índice de términos de intercambio de Colombia. |
| `tes_10y_banrep.json` | TES COP cero cupón a 10 años | Formaba parte del proxy TES−Treasury; sustituido por EMBIG Colombia. |
| `treasury_10y_diario_fred.csv` | Treasury `DGS10` | Formaba parte del proxy TES−Treasury; sustituido por EMBIG Colombia. |

| `ipc_eeuu_mensual_fred.csv` | Inflación estadounidense realizada | Sustituido por `BKEVEN05`; ya no se interpola `CPIAUCNS`. |

### 2. Base mensual consolidada

`modelo_trm_datos_mensuales.csv` es la unión externa mensual de las fuentes activas y de las variables construidas. Sus dimensiones y extremos dependen del último corte de cada fuente; la amplitud del índice no implica que todas las columnas tengan datos en todos los meses. Las instantáneas heredadas enumeradas arriba no amplían este calendario ni aportan columnas al consolidado.

### 3. Muestra balanceada para estimación

`modelo_trm_muestra_estimacion.csv` contiene las 18 columnas de nivel o transformación previa necesarias para estimar y comparar la robustez BEI. Se crea desde enero de 2006, se eliminan las filas con algún faltante y se exige frecuencia mensual sin huecos. El corte objetivo tiene 244 meses, de enero de 2006 a abril de 2026.

Este CSV todavía no es la matriz final de regresores: durante la estimación se calculan primeras diferencias y rezagos. Para comparar todos los candidatos sobre las mismas fechas se reserva la muestra común correspondiente al máximo de tres rezagos de `Δln(TRM)`. Por ello, aunque BIC selecciona cero rezagos adicionales de TRM, la regresión efectiva usa 240 observaciones, de mayo de 2006 a abril de 2026.

## Diccionario de la base consolidada

Todas las columnas tienen frecuencia mensual después de la consolidación.

### Columnas fuente y fiscales básicas

| Columna exacta | Definición, unidad y origen | Uso/rezago y signo esperado | Cautela principal |
|---|---|---|---|
| `fecha` | Mes de referencia, guardado como `AAAA-MM-01`. | Índice temporal; sin signo ni rezago. | No representa necesariamente el día original de observación. |
| `trm_cop_usd` | Promedio mensual de la TRM diaria; COP por USD; BanRep `1`. | Variable objetivo; un aumento es depreciación del COP. | El promedio mensual oculta volatilidad intrames. |
| `tasa_politica_colombia_pct` | Promedio mensual de la tasa de política BanRep `59`; porcentaje efectivo anual. | Entra solo a través del diferencial de tasas; por sí sola se espera `−`. | Es una respuesta endógena a inflación, actividad y TRM. |
| `fed_funds_eeuu_pct` | Tasa federal funds mensual `FEDFUNDS`; porcentaje. | Se resta de la tasa colombiana; dentro del diferencial su signo mecánico es opuesto, `+` sobre COP/USD. | Una tasa de EE. UU. más alta también opera por canales globales no aislados aquí. |
| `indice_dolar_amplio` | Promedio mensual de `DTWEXBGS`; índice nominal amplio, ene-2006=100. | Se usa mediante `Δln_dolar_amplio` en `t`; signo `+`. | No es el DXY comercial de ICE. |
| `vix` | Promedio mensual de `VIXCLS`; puntos del índice VIX. | Se usa mediante `Δln_vix` en `t`; signo `+`. | Comparte shocks de aversión al riesgo con dólar amplio y monedas regionales. |
| `remesas_usd_millones` | Ingresos mensuales de remesas BanRep `15363`; millones de USD. | Alimenta el acumulado de 12 meses; signo esperado `−`. | Es estacional, se publica con rezago y puede reaccionar a la depreciación. |
| `terminos_intercambio` | Índice BanRep `15360`: precios de exportación relativos a precios de importación. | Variable activa: se usa mediante `Δln_terminos_intercambio` en `t`; signo `−`. | Se publica aproximadamente dos meses después del mes de referencia; su uso contemporáneo es explicación ex post, no información disponible en tiempo real. |
| `reservas_netas_sin_flar_usd_millones` | Reservas internacionales netas sin FLAR, BanRep `15053`; millones de USD al cierre del mes. | Alimenta `Δln` con `L1`; signo esperado `−`. | La acumulación o venta de reservas puede responder a la propia TRM; no es un shock exógeno. |
| `embig_colombia_pb` | Promedio mensual de `PD04715XD`; diferencial EMBIG Colombia en puntos básicos. | Alimenta `embig_colombia_pp`; un aumento del riesgo soberano sugiere signo `+`. | EMBIG es una canasta de deuda externa con composición y duración variables; no es un CDS a cinco años ni una prima estructural pura. |
| `tes_5y_pesos_colombia_pct` | Promedio mensual de TES cero cupón nominal en pesos a 5 años, BanRep `15273`; porcentaje. | Primer componente de `bei_colombia_5y_pct`; sin entrada separada. | Incorpora tasa real esperada, compensación de inflación y primas de plazo, liquidez y riesgo. |
| `tes_5y_uvr_colombia_pct` | Promedio mensual de TES cero cupón en UVR a 5 años, BanRep `15276`; porcentaje real. | Se resta de la tasa nominal para formar `bei_colombia_5y_pct`; sin entrada separada. | Las curvas nominal y UVR pueden diferir en liquidez, tributación y primas; su resta no es una encuesta de expectativas. |
| `bei_eeuu_5y_pct` | Promedio mensual de `BKEVEN05`; compensación de inflación cero cupón a 5 años, porcentaje con capitalización continua. | Se resta del BEI colombiano; sin entrada separada. | Incluye primas de riesgo de inflación y liquidez. Es un producto de investigación del Federal Reserve Board sujeto a revisión y cambios metodológicos. |
| `tes_5y_pesos_comun_pct` | Promedio mensual del TES nominal limitado a fechas con TES UVR y `BKEVEN05` disponibles simultáneamente. | Insumo de robustez; no entra en la especificación activa. | Puede usar pocos días en meses con calendarios o faltantes diferentes. |
| `tes_5y_uvr_comun_pct` | Promedio mensual del TES UVR sobre las mismas fechas diarias comunes. | Insumo de robustez; no entra en la especificación activa. | Comparte la pérdida de observaciones de la intersección diaria. |
| `bei_eeuu_5y_comun_pct` | Promedio mensual de `BKEVEN05` sobre fechas diarias comunes. | Insumo de robustez; no entra en la especificación activa. | La intersección no corrige diferencias de liquidez o metodología entre mercados. |
| `balanza_comercial_cambiaria_usd_millones` | Exportaciones menos importaciones canalizadas en la balanza cambiaria, BanRep `16702`; millones de USD. | Se transforma con `asinh(flujo/1000)`, se diferencia y entra con `L1`; signo `−`. | Es flujo de caja cambiario, no la balanza de pagos por causación; es simultánea con la TRM. |
| `flujos_capital_usd_millones` | Movimientos netos totales de capital de la balanza cambiaria, BanRep `16706`; millones de USD. | Se transforma con `asinh(flujo/1000)`, se diferencia y entra con `L1`; signo `−` para entradas netas. | Muy volátil y endógeno; no confundir con la serie `16708`, que cubre solo sector real y Gobierno. |
| `brl_por_usd` | Reales brasileños por USD, OECD/FRED `CCUSMA02BRM618N`. | Alimenta el factor regional; aumento = depreciación regional, signo `+`. | No entra individualmente y comparte shocks con controles globales. |
| `clp_por_usd` | Pesos chilenos por USD, OECD/FRED `CCUSMA02CLM618N`. | Alimenta el factor regional; aumento = depreciación regional, signo `+`. | No entra individualmente. |
| `mxn_por_usd` | Pesos mexicanos por USD, OECD/FRED `CCUSMA02MXM618N`. | Alimenta el factor regional; aumento = depreciación regional, signo `+`. | No entra individualmente. |
| `pen_por_usd` | Soles peruanos por USD, promedio interbancario del período; BCRPData `PN01207PM`. | Alimenta el factor regional de cuatro monedas; aumento = depreciación regional, signo `+`. | No entra individualmente; su inclusión se compara por separado en explicación y pronóstico. |
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
| `embig_colombia_pp` | `embig_colombia_pb / 100`; puntos porcentuales. | El modelo usa `Δ` contemporáneo; signo `+`. | Reescala el indicador, no cambia su contenido. Al usar el promedio del propio mes, es explicativo/nowcast y no un predictor disponible al inicio del mes. |
| `bei_colombia_5y_pct` | `tes_5y_pesos_colombia_pct − tes_5y_uvr_colombia_pct`; compensación de inflación de mercado a 5 años, pp. | Componente colombiano del diferencial; sin entrada separada. | Igualar horizonte mejora comparabilidad, pero no elimina las primas de inflación, plazo y liquidez ni diferencias entre los mercados nominal y UVR. |
| `diferencial_bei_5y_pp` | `bei_colombia_5y_pct − bei_eeuu_5y_pct`; pp, ambos a horizonte de 5 años y agregados por separado. | El modelo usa `Δ` con `L1`; signo `+`. | El nivel es sensible a tendencia: ADF con tendencia no rechaza raíz unitaria al 5% y KPSS con tendencia rechaza estacionariedad. |
| `diferencial_bei_5y_comun_pp` | Diferencial calculado diariamente y promediado solo sobre fechas comunes de TES nominal, TES UVR y `BKEVEN05`; pp. | Robustez en nivel y primera diferencia; no es la especificación activa. | Conserva menos observaciones intrames; el mínimo observado es 4 días comunes. |
| `diferencia_comun_menos_separada_pp` | `diferencial_bei_5y_comun_pp − diferencial_bei_5y_pp`; pp. | Diagnóstico de agregación; no entra como regresor. | Una diferencia pequeña no implica equivalencia conceptual entre los mercados. |
| `dias_tes_pesos`, `dias_tes_uvr`, `dias_bei_eeuu`, `dias_comunes_bei` | Número de observaciones diarias publicadas usadas por mes en cada componente y en su intersección. | Control de cobertura intrames. | No mide calidad ni liquidez de las cotizaciones. |
| `asinh_balanza_comercial` | `asinh(balanza_comercial_cambiaria_usd_millones / 1000)`; transformación adimensional sobre USD miles de millones. | El modelo usa su primera diferencia con `L1`; signo `−`. | El nivel transformado no es estacionario; `asinh` conserva signo y admite cero, pero el coeficiente no es una elasticidad constante. |
| `asinh_flujos_capital` | `asinh(flujos_capital_usd_millones / 1000)`; transformación adimensional sobre USD miles de millones. | El modelo usa su primera diferencia con `L1`; signo `−`. | El nivel transformado no es estacionario; se mantienen las cautelas de escala y endogeneidad de los flujos. |
| `factor_monedas_regionales_3` | Promedio simple de los `z(Δln)` de BRL, CLP y MXN por USD. Media y desviación estándar poblacional (`ddof=0`) se calibran en 2006-01 a 2019-12. | Entra en `t` en la robustez histórica de tres monedas y con `L1` en el pronóstico seleccionado. | Exige las tres monedas (`skipna=False`) y puede absorber información de VIX/dólar. |
| `factor_monedas_regionales_4` | Misma construcción con BRL, CLP, MXN y PEN. | Es el factor activo de la explicación histórica y entra en `t`; signo `+`. | PEN mejora el ajuste histórico, pero no el BIC ni el MAPE del pronóstico. |
| `factor_monedas_regionales` | Alias explícito de `factor_monedas_regionales_4`. | Conserva compatibilidad con salidas anteriores; la especificación activa usa el nombre numerado. | No debe confundirse con el factor de tres monedas seleccionado para pronóstico. |

### Variables internas de Colombia

La cobertura de las descargas nacionales se audita en [`variables_internas_cobertura.csv`](variables_internas_cobertura.csv). El corte de estimación abarca 244 meses, de 2006-01 a 2026-04.

| Variable | Fuente y archivo | Cobertura en la muestra | Estado y tratamiento |
|---|---|---:|---|
| `ise_total_dane` → `ln_ise_total_dane` | DANE, ISE total del `ise_dane_12actividades_jun2026.xlsx`, Cuadro 2 | 244/244 | Activa; `ln(x)` y primera diferencia. Se activa el total para no añadir simultáneamente los 15 sectores y provocar colinealidad. |
| `ipc_colombia_indice` → `ln_ipc_colombia` | Banco de la República, serie `15000`, `ipc_colombia_banrep.json` | 244/244 | Activa; `ln(x)` y primera diferencia. No se interpolan ni rellenan observaciones. |
| GEIH DANE original y desestacionalizada | `geih_dane_jun2026.xlsx` y `geih_dane_desestacionalizado_jun2026.xlsx` | 239/244 y 242/244 | Candidatas no activas por faltantes dentro de la muestra y ruptura metodológica; se dejan vacías. |
| IPI DANE total | `ipi_dane_jun2026.xlsx` | 148/244 | Candidata no activa: empieza en 2014-01; no se extiende hacia atrás. |
| IPP DANE producción nacional total | `ipp_dane_jul2026.xlsx` | 133/244 | Candidata no activa: empieza en 2014-12; no se empalma artificialmente. |

Las dos variables activas forman el factor Shapley **Actividad y precios domésticos**, grupo `Condiciones internas`. En la explicación histórica entran como `D.ln_ise_total_dane.L0` y `D.ln_ipc_colombia.L0`; en el pronóstico se usa `L2` para respetar el rezago conservador de publicación. La ausencia de cobertura completa es una razón para excluir GEIH, IPI e IPP, no una invitación a imputar.

### Base global mensual FRED

`base_global_mensual.csv` consolida las series internacionales, sus candidatos y el identificador de cobertura. La especificación balanceada activa 17 términos en un único factor denominado `Condiciones financieras, commodities y actividad internacional`: rendimientos reales y nominales de EE. UU., expectativas de inflación a 5 y 10 años, pendiente 10Y–2Y, Brent, commodities, EPU global, STLFSI, NFCI, ANFCI, desempleo estadounidense, empleo manufacturero, producción industrial y fletes/logística. La cobertura de cada origen, incluidos los candidatos, se registra en `base_global_cobertura.csv`.

| Bloque | Series activas | Transformación histórica | Uso de pronóstico |
|---|---|---|---|
| Rendimientos y expectativas EE. UU. | `yield_real_10y_tips_pct`, `yield_real_5y_us_pct`, `yield_2y_us_pct`, `yield_10y_us_pct`, `spread_10y_2y_us_pct`, `breakeven_5y_us_pct`, `breakeven_10y_us_pct` | Primera diferencia en unidades de origen | `.L1` |
| Commodities | `ln_brent_global`, `ln_commodities_global` | Logaritmo y primera diferencia | `.L1` |
| Riesgo e incertidumbre | `epu_global`, `estres_financiero_stl`, `nfci_chicago`, `anfci_chicago` | Primera diferencia | `.L1` |
| Actividad, empleo y logística | `desempleo_us_pct`, `ln_empleo_manufactura_us`, `ln_produccion_industrial_us`, `ln_fletes_transporte_us` | Desempleo en diferencia; las demás, logaritmo y primera diferencia | `.L2` por disponibilidad |

La base conserva además candidatos sin forzar su entrada al modelo: `high_yield_oas_pct` (high-yield), `ted_spread_pct` (TED), `desempleo_us_bls_pct` (`UNRATE`) y cuatro indicadores de China (`precios_importacion_china`, `produccion_industrial_china`, `indicador_lider_china`, `ipc_china`). High-yield no tiene una descarga utilizable que cubra 2006–2026; TED termina en 2022-01; `UNRATE` conserva un faltante publicado en 2025-10; y los indicadores chinos terminan antes o tienen faltantes dentro de la muestra. Ninguna de estas series se interpola, se rellena con cero o se incluye en la matriz balanceada. El identificador de oro solicitado devuelve HTTP 400 y no se sustituye silenciosamente.

El desempleo activo usa `LRUN64TTUSM156S`, una serie mensual completa en la ventana 2006-01–2026-04. El modelo histórico utiliza el bloque global con información contemporánea realizada; el pronóstico aplica rezagos de publicación: mercados, tasas, riesgo y commodities con `.L1`, y empleo, desempleo y fletes con `.L2`. Las señales de China se mantienen exploratorias y no entran en `score_global` completo cuando no cubren toda la ventana. Agrupar los 17 términos evita aumentar los jugadores Shapley, controla la colinealidad y conserva exactamente 14 factores al incorporar el bloque interno de actividad y precios domésticos.

`data/base_global_cobertura.csv` exige para cada serie activa `estado=activa`, `cubre_muestra_completa=True` y 244 observaciones en la muestra. El registro conserva también las columnas de candidatos aunque estén vacías, para que una descarga fallida o una cobertura incompleta sea auditable en lugar de desaparecer.

### Logaritmos y controles

| Columna exacta | Definición | Uso/rezago y signo esperado | Cautela principal |
|---|---|---|---|
| `ln_trm` | `ln(trm_cop_usd)`, adimensional. | La dependiente es `Δln_trm`; aumento = depreciación. BIC selecciona `p=0`. | El cambio log no se multiplica por 100 en la regresión. |
| `ln_terminos_intercambio` | `ln(terminos_intercambio)`. | Se diferencia y entra en `t`; signo `−`. | Solo se calcula para valores positivos. Su rezago de publicación de aproximadamente dos meses impide usar el dato de `t` para un pronóstico disponible en `t`. |
| `ln_remesas_12m` | `ln(remesas_12m_usd_millones)`. | Se diferencia y entra con `L1`; signo `−`. | Puede reflejar respuesta de remitentes a la TRM. |
| `ln_dolar_amplio` | `ln(indice_dolar_amplio)`. | Se diferencia y entra en `t`; signo `+`. | Contemporáneo: útil para explicación/nowcast, no pronóstico puro. |
| `ln_vix` | `ln(vix)`. | Se diferencia y entra en `t`; signo `+`. | El modelo vuelve a calcular `D.ln_vix` a partir de esta columna. |
| `ln_reservas_netas_sin_flar` | `ln(reservas_netas_sin_flar_usd_millones)`. | Se diferencia y entra con `L1`; signo `−`. | Endogeneidad por intervención y valoración de activos. |
| `dln_vix` | `ln_vix − ln_vix_L1`. | No es un regresor separado en los modelos mensuales referencia/integral; se usa contemporáneo como variable fija en el ECM exploratorio. Signo `+`. | Duplica numéricamente `D.ln_vix`; no incluir ambos en la misma ecuación. |
| `dummy_pandemia_2020` | `1` entre 2020-03 y 2020-05, ambos inclusive; `0` en otro mes. | Control contemporáneo; se anticipa signo `+`, sin interpretación estructural. | Resume un episodio excepcional y no identifica un canal económico único. |

## Columnas de la muestra de estimación y temporización efectiva

El encabezado exacto de `modelo_trm_muestra_estimacion.csv` es:

```text
fecha,ln_trm,ln_terminos_intercambio,ln_remesas_12m,diferencial_tasas_pp,deficit_fiscal_12m_pct_pib,ln_dolar_amplio,ln_vix,dln_vix,embig_colombia_pp,ln_reservas_netas_sin_flar,asinh_balanza_comercial,asinh_flujos_capital,diferencial_bei_5y_pp,diferencial_bei_5y_comun_pp,factor_monedas_regionales_3,factor_monedas_regionales_4,ln_ise_total_dane,ln_ipc_colombia,yield_real_10y_tips_pct,yield_real_5y_us_pct,yield_2y_us_pct,yield_10y_us_pct,spread_10y_2y_us_pct,breakeven_5y_us_pct,breakeven_10y_us_pct,ln_brent_global,ln_commodities_global,epu_global,estres_financiero_stl,nfci_chicago,anfci_chicago,desempleo_us_pct,ln_empleo_manufactura_us,ln_produccion_industrial_us,ln_fletes_transporte_us,dummy_pandemia_2020
```

La matriz del marco macroeconómico integral se construye así:

| Entrada del CSV de muestra | Regresor efectivo | Rezago | Signo esperado |
|---|---|---:|:---:|
| `ln_trm` | `Δln_trm`, variable dependiente | `t` | objetivo |
| `ln_terminos_intercambio` | `Δln_terminos_intercambio` | `t` | `−` |
| `ln_remesas_12m` | `Δln_remesas_12m` | `L1` | `−` |
| `diferencial_tasas_pp` | `Δdiferencial_tasas_pp` | `L1` | `−` |
| `deficit_fiscal_12m_pct_pib` | `Δdeficit_fiscal_12m_pct_pib` | `L1` | `+` |
| `ln_dolar_amplio` | `Δln_dolar_amplio` | `t` | `+` |
| `ln_vix` | `Δln_vix` | `t` | `+` |
| `dln_vix` | Solo ECM exploratorio; no se agrega al marco macroeconómico integral junto a `Δln_vix` | `t` | `+` |
| `embig_colombia_pp` | `Δembig_colombia_pp` | `t` | `+` |
| `ln_reservas_netas_sin_flar` | `Δln_reservas_netas_sin_flar` | `L1` | `−` |
| `asinh_balanza_comercial` | `Δasinh` | `L1` | `−` |
| `asinh_flujos_capital` | `Δasinh` | `L1` | `−` |
| `diferencial_bei_5y_pp` | Primera diferencia del diferencial de compensación de inflación a 5 años | `L1` | `+` |
| `factor_monedas_regionales_4` | Factor de cuatro monedas | `t` en la explicación histórica | `+` |
| `ln_ise_total_dane` y `ln_ipc_colombia` | Factor `Actividad y precios domésticos`: `Δln_ise_total_dane` y `Δln_ipc_colombia` | `L0` histórico; `L2` pronóstico | Actividad `+`; inflación según la asociación estimada |
| `factor_monedas_regionales_3` | Factor de tres monedas | `L1` en el pronóstico seleccionado | `+` |
| `dummy_pandemia_2020` | Dummy | `t` | Sin signo estructural |

Términos de intercambio, dólar amplio, VIX, EMBIG y factor regional usan información referida o realizada dentro del mismo mes que la TRM. Por tanto, el marco macroeconómico integral es una contabilidad histórica o nowcast condicional; no es un pronóstico disponible al comienzo del mes ni una identificación causal. La restricción es todavía más clara para términos de intercambio: aunque entra como `Δln` contemporáneo para explicar el episodio económico de `t`, BanRep suele publicar ese dato alrededor de dos meses después.

### Calendario del modelo de pronóstico

La ecuación de pronóstico evita regresores contemporáneos: términos de intercambio y déficit usan `L3`; remesas, reservas, balanza y flujos de capital usan `L2`; tasas, dólar amplio, VIX, EMBIG, el último cambio completo del diferencial BEI y el factor regional de tres monedas usan `L1`; ISE total e IPC Colombia se incorporan al factor interno con `L2`. La variable dependiente incorpora un rezago propio seleccionado por BIC. El detalle factor por factor está en `results/calendario_disponibilidad_pronostico.csv`.

Este calendario evita anticipar el valor del mes objetivo, pero la base usa la última revisión hoy disponible de cada serie. Por tanto, la prueba es pseudo-tiempo-real. `data/vintages/` añade un archivo inmutable hacia adelante, cataloga versiones fiscales y deja una recuperación ALFRED reanudable. La cobertura histórica versionada sigue en cero; consulte `data/vintages/README.md` y `results/cobertura_vintages_pronostico.csv`.

### Archivo por fecha de origen

`src/archive_vintage.py snapshot --origin-date AAAA-MM-DD` descarga todas las fuentes activas en una carpeta nueva, registra hora UTC, URL final, tamaño, tipo de contenido y SHA-256, y se niega a sobrescribir una fecha existente. El baseline `2026-08-23` referencia y fija las huellas de `data/raw` sin duplicar archivos grandes.

La ruta ALFRED solicita, serie por serie, FEDFUNDS, dólar amplio, VIX, BRL, CLP y MXN para 2022-05 a 2026-04, y rechaza observaciones posteriores al origen. El servidor cortó las conexiones individuales durante esta actualización, por lo que no se versiona un consolidado incompleto. El historial oficial de versiones fiscales fue catalogado, pero el portal bloqueó la descarga automatizada de los binarios; ninguna versión se cuenta como recuperada sin XLSX y SHA-256.

## Lectura de las tres sustituciones

1. **Términos de intercambio en lugar de Brent.** `Δln_terminos_intercambio_t` resume el cambio en el poder de compra externo de las exportaciones colombianas frente a sus importaciones. Una mejora suele reducir COP/USD, de ahí el signo esperado negativo. Es una medida más amplia y específica para Colombia que un solo precio petrolero, pero su publicación con cerca de dos meses de rezago obliga a tratarla como explicación ex post.
2. **EMBIG Colombia en lugar de TES−Treasury.** `embig_colombia_pb` es el promedio mensual de las observaciones diarias publicadas; `embig_colombia_pp = embig_colombia_pb / 100`. El modelo usa `Δembig_colombia_pp_t`: un aumento representa mayor prima soberana y se asocia con depreciación. El indicador es preferible al antiguo spread de monedas y duraciones distintas, pero sigue siendo una canasta propietaria de composición cambiante y no un CDS de vencimiento constante.
3. **Compensación de inflación a cinco años en lugar de inflación realizada.** Primero se promedian por separado los TES nominales y UVR a cinco años; después se calcula `bei_colombia_5y_pct`. `bei_eeuu_5y_pct` es el promedio mensual de `BKEVEN05`. El diferencial Colombia−EE. UU. entra en primera diferencia con `L1`, porque su nivel es sensible a tendencias y quiebres. La versión sobre fechas diarias comunes se conserva como robustez: su correlación con la separada es 99,97%, pero en el peor mes usa solo 4 días. Ambas medidas incluyen primas de riesgo de inflación y liquidez; son compensaciones de mercado comparables, no expectativas puras ni encuestas.

Las tres sustituciones mejoran la correspondencia económica de los controles, pero no resuelven simultaneidad, revisiones de datos ni identificación causal. Las cinco instantáneas nuevas —incluido PEN— se descargaron el 23 de agosto de 2026; `results/metadata.json` registra la fecha y el SHA-256 de cada archivo para detectar revisiones o cambios accidentales.
