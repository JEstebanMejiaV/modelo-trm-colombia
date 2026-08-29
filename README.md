# Modelo TRM Colombia

Modelo econométrico y conjunto de productos de apoyo para estudiar y pronosticar la tasa representativa del mercado (TRM) de Colombia, expresada como pesos colombianos por dólar estadounidense (COP/USD).

> **Estado de lectura:** el producto mensual es la referencia principal; los productos diarios son de apoyo y el análisis de largo plazo es investigación. La documentación distingue siempre entre explicación histórica, pronóstico ex ante y evidencia exploratoria.

## Empezar

1. Lea [`docs/README.md`](docs/README.md), el índice documental.
2. Revise [`docs/01_contexto_y_alcance.md`](docs/01_contexto_y_alcance.md) para conocer el alcance y las limitaciones.
3. Instale el entorno y ejecute la validación:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
python -m pip install -e . --no-deps
trm-model validate
python -m pytest -q
```

En macOS/Linux, active `.venv/bin/activate` y use `python -m pip` con los mismos comandos.

## Productos

| Producto | Estado | Frecuencia | Pregunta que responde | Documentación |
|---|---|---:|---|---|
| `monthly_explanation` | Primario | Mensual | ¿Qué factores se movieron junto con la TRM? | [`productos/mensual.md`](docs/productos/mensual.md) |
| `monthly_forecast` | Primario, pseudo-tiempo-real | Mensual | ¿Cómo funciona un pronóstico con rezagos de publicación? | [`productos/mensual.md`](docs/productos/mensual.md) |
| `daily_direction` | Apoyo | Diario | ¿Qué modelos predicen la dirección diaria? | [`productos/diario_direccion.md`](docs/productos/diario_direccion.md) |
| `daily_volatility` | Apoyo | Diario | ¿Cómo se comportan la volatilidad y el VaR? | [`productos/diario_volatilidad.md`](docs/productos/diario_volatilidad.md) |
| `long_horizon_research` | Investigación | Mensual, 6–24 meses | ¿Qué señales exploratorias aparecen a horizontes largos? | [`productos/investigacion_largo_plazo.md`](docs/productos/investigacion_largo_plazo.md) |

## Lectura correcta de los resultados

- La **explicación histórica** usa algunas realizaciones contemporáneas. Es descriptiva o *nowcast* condicional; no es un pronóstico disponible antes del mes.
- El **pronóstico mensual** respeta rezagos de publicación, pero usa el último *vintage* disponible. Por eso sigue rotulado pseudo-tiempo-real.
- La cobertura PIT actualmente no habilita un backtest histórico completo: el snapshot baseline es válido, pero no elegible para todos los factores; la cobertura registrada es 3 de 14 factores y `genuine_backtest_available=false`.
- No se imputan faltantes, no se hace `ffill` ilimitado y no se inventan revisiones históricas.
- Los coeficientes, pesos Shapley y métricas describen asociaciones estadísticas. No identifican efectos causales.

## Métricas regeneradas

Los siguientes bloques se actualizan mediante `src/model/readme_sync.py` al ejecutar la estimación mensual. No edite manualmente su contenido entre los marcadores.

### Coeficientes de controles externos

<!-- AUTO:coeficientes_controles_externos -->
| Término | Coeficiente | p-valor HAC | Lectura aproximada |
|---|---:|---:|---|
| Constante | −0,00059 | 0,7250 | No hay evidencia de una deriva mensual adicional. |
| Δln términos de intercambio, mes actual | −0,10008 | 0,0007 | Una mejora de 10% se asocia con una TRM cerca de 100.1% menor. |
| Δln remesas 12 meses, rezago 1 | 0,27652 | 0,0243 | Un aumento de 10% se asocia con una TRM cerca de 276.5% mayor; el signo contrario al canal simple de oferta de divisas aconseja cautela por endogeneidad. |
| Δ diferencial de tasas, rezago 1 | −0,00990 | 0,0436 | Un aumento de 1 punto porcentual en el cambio del diferencial se asocia con una TRM cerca de 0.99% menor. |
| Δ déficit fiscal 12 meses/PIB, rezago 1 | 0,00485 | 0,1447 | Un aumento de 1 punto porcentual se asocia con una TRM cerca de 0.48% mayor, pero la estimación no es precisa al 5%. |
| Δln dólar amplio, mes actual | 1,27461 | <0,0001 | Un aumento de 1% del dólar global se asocia con una TRM cerca de 127.46% mayor. |
| Δln VIX, mes actual | 0,03836 | <0,0001 | Un aumento de 10% del VIX se asocia con una TRM cerca de 38.36% mayor. |
| Pandemia marzo–mayo 2020 | 0,01081 | 0,0200 | Se asocia con una TRM alrededor de 1.1% mayor, condicionado a los demás factores. |
<!-- /AUTO:coeficientes_controles_externos -->

### Métricas de controles externos

<!-- AUTO:metricas_controles_externos -->
- MAPE condicional: **2,01%**.
- Acierto de dirección: **68,75%**.
- R² condicional frente a caminata aleatoria: **31,92%**.
<!-- /AUTO:metricas_controles_externos -->

### Coeficientes del marco macroeconómico integral

<!-- AUTO:coeficientes_marco_macro_integral -->
| Término | Coeficiente | p-valor |
|---|---:|---:|
| Constante | 0,00567 | 0,0103 |
| Δln términos de intercambio, mes actual | 0,01482 | 0,7322 |
| Δln remesas 12 meses, rezago 1 | 0,19704 | 0,0571 |
| Δ diferencial de tasas, rezago 1 | 0,00345 | 0,5264 |
| Δ déficit fiscal 12 meses/PIB, rezago 1 | −0,00012 | 0,9714 |
| Δln dólar amplio, mes actual | 0,20247 | 0,2746 |
| Δln VIX, mes actual | 0,01656 | 0,1121 |
| Δ EMBIG Colombia (pp), mes actual | 0,02779 | 0,0104 |
| Δln reservas netas sin FLAR, rezago 1 | −0,23794 | 0,0487 |
| Δ asinh(balanza comercial), rezago 1 | 0,05473 | <0,0001 |
| Δ asinh(flujos de capital), rezago 1 | 0,00060 | 0,8380 |
| Δ diferencial BEI 5 años (pp), rezago 1 | −0,00172 | 0,6793 |
| Δln ISE total DANE, mes actual | −0,21001 | 0,0187 |
| Δln IPC Colombia, mes actual | −0,70708 | 0,0561 |
| Factor regional BRL+CLP+MXN+PEN, mes actual | 0,01614 | <0,0001 |
| Δ rendimiento real EE. UU. 10 años, mes actual | −285,78701 | 0,3113 |
| Δ rendimiento real EE. UU. 5 años, mes actual | −0,09764 | 0,1208 |
| Δ Treasury EE. UU. 2 años, mes actual | −415,41215 | 0,1054 |
| Δ Treasury EE. UU. 10 años, mes actual | 701,29852 | 0,0304 |
| Δ pendiente 10Y–2Y EE. UU., mes actual | −415,45712 | 0,1053 |
| Δ compensación inflacionaria EE. UU. 5 años, mes actual | −0,10213 | 0,0980 |
| Δ compensación inflacionaria EE. UU. 10 años, mes actual | −285,71881 | 0,3114 |
| Δ incertidumbre económica global, mes actual | −0,00002 | 0,5317 |
| Δ estrés financiero STL, mes actual | 0,00342 | 0,5641 |
| Δ índice de condiciones financieras Chicago, mes actual | 0,02482 | 0,6076 |
| Δ índice ajustado de condiciones financieras Chicago, mes actual | −0,04764 | 0,2327 |
| Δln Brent global, mes actual | −0,01447 | 0,6360 |
| Δln índice global de commodities, mes actual | −0,16719 | 0,0084 |
| Δ desempleo EE. UU. armonizado, mes actual | −0,01132 | 0,0376 |
| Δln empleo manufacturero EE. UU., mes actual | 0,08917 | 0,8764 |
| Δln producción industrial EE. UU., mes actual | −0,57942 | 0,1017 |
| Δln fletes de transporte, mes actual | 0,24884 | 0,0585 |
| Pandemia marzo–mayo 2020 | −0,00267 | 0,7999 |
<!-- /AUTO:coeficientes_marco_macro_integral -->

### Pesos explicativos

<!-- AUTO:pesos_shapley -->
| Factor | Peso entre los 14 factores | Aporte al R² |
|---|---:|---:|
| Monedas regionales | 23,55% | 15,72 p.p. |
| Condiciones financieras, commodities y actividad internacional | 21,63% | 14,44 p.p. |
| Dólar amplio | 15,11% | 10,09 p.p. |
| Riesgo soberano EMBIG Colombia | 14,12% | 9,43 p.p. |
| Balanza comercial cambiaria | 6,36% | 4,25 p.p. |
| VIX | 6,10% | 4,07 p.p. |
| Términos de intercambio | 4,15% | 2,77 p.p. |
| Flujos netos de capital | 3,29% | 2,20 p.p. |
| Actividad y precios domésticos | 2,02% | 1,35 p.p. |
| Reservas internacionales | 1,94% | 1,30 p.p. |
| Remesas | 1,17% | 0,78 p.p. |
| Diferencial de compensación inflacionaria 5 años | 0,30% | 0,20 p.p. |
| Diferencial de tasas | 0,18% | 0,12 p.p. |
| Déficit fiscal | 0,09% | 0,06 p.p. |
<!-- /AUTO:pesos_shapley -->

### Ficha dinámica por factor

<!-- AUTO:interpretacion_factores -->
La tabla distingue asociación parcial HAC, contribución mensual firmada y participación Shapley en el R² incremental. Los factores compuestos no tienen coeficiente ni signo único; todas las lecturas son no causales.
| Factor | Grupo | Términos y rezagos | Participación en R² incremental | Contribución media mensual | Lectura dinámica |
|---|---|---|---:|---:|---|
| Términos de intercambio | Sector externo Colombia | cambio logarítmico de términos de intercambio, contemporáneo | 4,15% | 0,00% | En la ecuación de variación mensual, un aumento del regresor se asocia con una variación mensual de la TRM mayor; coeficiente 0,0148 y 0 (contemporáneo). El IC95% cruza cero, por lo que la dirección es imprecisa en esta muestra. Su contribución contable media fue 0.002% de Δln TRM y fue positiva en 54.2% de los meses. En 2020 en adelante coincidieron los signos de 100.0% de sus términos con los de la muestra completa. Señal económica: Señal de ingresos externos y condiciones comerciales; puede recoger otros cambios simultáneos. Asociación histórica parcial; no es un efecto causal ni un escenario contrafactual. |
| Remesas | Sector externo Colombia | cambio logarítmico de remesas de 12 meses, rezago 1 | 1,17% | 0,11% | En la ecuación de variación mensual, un aumento del regresor se asocia con una variación mensual de la TRM mayor; coeficiente 0,1970 y 1. El IC95% cruza cero, por lo que la dirección es imprecisa en esta muestra. Su contribución contable media fue 0.111% de Δln TRM y fue positiva en 74.6% de los meses. En 2020 en adelante coincidieron los signos de 100.0% de sus términos con los de la muestra completa. Señal económica: Señal de flujos de divisas de hogares y de actividad externa. Asociación histórica parcial; no es un efecto causal ni un escenario contrafactual. |
| Diferencial de tasas | Política doméstica | cambio del diferencial de tasas, rezago 1 | 0,18% | 0,01% | En la ecuación de variación mensual, un aumento del regresor se asocia con una variación mensual de la TRM mayor; coeficiente 0,0034 y 1. El IC95% cruza cero, por lo que la dirección es imprecisa en esta muestra. Su contribución contable media fue 0.007% de Δln TRM y fue positiva en 45.0% de los meses. En 2020 en adelante coincidieron los signos de 100.0% de sus términos con los de la muestra completa. Señal económica: Señal de condiciones monetarias relativas y de valoración financiera. Asociación histórica parcial; no es un efecto causal ni un escenario contrafactual. |
| Déficit fiscal | Política doméstica | cambio del déficit fiscal de 12 meses sobre PIB, rezago 1 | 0,09% | -0,00% | En la ecuación de variación mensual, un aumento del regresor se asocia con una variación mensual de la TRM menor; coeficiente -0,0001 y 1. El IC95% cruza cero, por lo que la dirección es imprecisa en esta muestra. Su contribución contable media fue -0.000% de Δln TRM y fue positiva en 48.8% de los meses. En 2020 en adelante coincidieron los signos de 0.0% de sus términos con los de la muestra completa. Señal económica: Señal de condiciones fiscales y percepción de riesgo, potencialmente correlacionada con el ciclo. Asociación histórica parcial; no es un efecto causal ni un escenario contrafactual. |
| Dólar amplio | Mercados financieros globales | cambio logarítmico del dólar amplio, contemporáneo | 15,11% | 0,01% | En la ecuación de variación mensual, un aumento del regresor se asocia con una variación mensual de la TRM mayor; coeficiente 0,2025 y 0 (contemporáneo). El IC95% cruza cero, por lo que la dirección es imprecisa en esta muestra. Su contribución contable media fue 0.015% de Δln TRM y fue positiva en 49.2% de los meses. En 2020 en adelante coincidieron los signos de 100.0% de sus términos con los de la muestra completa. Señal económica: Señal agregada de valoración internacional del dólar. Asociación histórica parcial; no es un efecto causal ni un escenario contrafactual. |
| VIX | Mercados financieros globales | cambio logarítmico del VIX, contemporáneo | 6,10% | 0,00% | En la ecuación de variación mensual, un aumento del regresor se asocia con una variación mensual de la TRM mayor; coeficiente 0,0166 y 0 (contemporáneo). El IC95% cruza cero, por lo que la dirección es imprecisa en esta muestra. Su contribución contable media fue 0.004% de Δln TRM y fue positiva en 45.4% de los meses. En 2020 en adelante coincidieron los signos de 0.0% de sus términos con los de la muestra completa. Señal económica: Señal de tensión y volatilidad financiera internacional. Asociación histórica parcial; no es un efecto causal ni un escenario contrafactual. |
| Riesgo soberano EMBIG Colombia | Riesgo local | cambio del EMBIG Colombia, contemporáneo | 14,12% | 0,01% | En la ecuación de variación mensual, un aumento del regresor se asocia con una variación mensual de la TRM mayor; coeficiente 0,0278 y 0 (contemporáneo). El IC95% no cruza cero al 5% en la inferencia HAC. Su contribución contable media fue 0.008% de Δln TRM y fue positiva en 45.8% de los meses. En 2020 en adelante coincidieron los signos de 100.0% de sus términos con los de la muestra completa. Señal económica: Señal de riesgo soberano percibido y condiciones de financiamiento externo. Asociación histórica parcial; no es un efecto causal ni un escenario contrafactual. |
| Reservas internacionales | Sector externo Colombia | cambio logarítmico de reservas netas sin FLAR, rezago 1 | 1,94% | -0,15% | En la ecuación de variación mensual, un aumento del regresor se asocia con una variación mensual de la TRM menor; coeficiente -0,2379 y 1. El IC95% no cruza cero al 5% en la inferencia HAC. Su contribución contable media fue -0.147% de Δln TRM y fue positiva en 30.4% de los meses. En 2020 en adelante coincidieron los signos de 100.0% de sus términos con los de la muestra completa. Señal económica: Señal de liquidez externa y de operaciones que pueden responder a la propia dinámica cambiaria. Asociación histórica parcial; no es un efecto causal ni un escenario contrafactual. |
| Balanza comercial cambiaria | Sector externo Colombia | cambio de asinh de la balanza comercial cambiaria, rezago 1 | 6,36% | 0,01% | En la ecuación de variación mensual, un aumento del regresor se asocia con una variación mensual de la TRM mayor; coeficiente 0,0547 y 1. El IC95% no cruza cero al 5% en la inferencia HAC. Su contribución contable media fue 0.015% de Δln TRM y fue positiva en 48.8% de los meses. En 2020 en adelante coincidieron los signos de 100.0% de sus términos con los de la muestra completa. Señal económica: Señal de flujos comerciales; la transformación asinh conserva el signo y reduce la influencia de extremos. Asociación histórica parcial; no es un efecto causal ni un escenario contrafactual. |
| Flujos netos de capital | Sector externo Colombia | cambio de asinh de flujos netos de capital, rezago 1 | 3,29% | -0,00% | En la ecuación de variación mensual, un aumento del regresor se asocia con una variación mensual de la TRM mayor; coeficiente 0,0006 y 1. El IC95% cruza cero, por lo que la dirección es imprecisa en esta muestra. Su contribución contable media fue -0.001% de Δln TRM y fue positiva en 49.6% de los meses. En 2020 en adelante coincidieron los signos de 100.0% de sus términos con los de la muestra completa. Señal económica: Señal de entradas y salidas de capital que también pueden reaccionar a la TRM. Asociación histórica parcial; no es un efecto causal ni un escenario contrafactual. |
| Diferencial de compensación inflacionaria 5 años | Política doméstica | cambio del diferencial de compensación inflacionaria a 5 años, rezago 1 | 0,30% | -0,00% | En la ecuación de variación mensual, un aumento del regresor se asocia con una variación mensual de la TRM menor; coeficiente -0,0017 y 1. El IC95% cruza cero, por lo que la dirección es imprecisa en esta muestra. Su contribución contable media fue -0.002% de Δln TRM y fue positiva en 47.9% de los meses. En 2020 en adelante coincidieron los signos de 0.0% de sus términos con los de la muestra completa. Señal económica: Señal financiera que combina expectativas, primas de riesgo y liquidez; no es una expectativa pura de inflación. Asociación histórica parcial; no es un efecto causal ni un escenario contrafactual. |
| Actividad y precios domésticos | Condiciones internas | cambio logarítmico del ISE total DANE, contemporáneo; cambio logarítmico del IPC Colombia, contemporáneo | 2,02% | -0,34% | Actividad y precios domésticos es un bloque compuesto por 2 términos (cambio logarítmico del ISE total DANE, contemporáneo; cambio logarítmico del IPC Colombia, contemporáneo). No tiene un coeficiente ni un signo único; los signos estimados por término son cambio logarítmico del ISE total DANE, contemporáneo: negativo; cambio logarítmico del IPC Colombia, contemporáneo: negativo. La lectura recomendada es su suma de contribuciones mensuales y no una dirección global. Su contribución contable media fue -0.342% de Δln TRM y fue positiva en 15.0% de los meses. En 2020 en adelante coincidieron los signos de 100.0% de sus términos con los de la muestra completa. Señal económica: Bloque de dos señales internas con coeficientes separados; su suma mensual es interpretable como contabilidad, no como un parámetro único. Asociación histórica parcial; no es un efecto causal ni un escenario contrafactual. |
| Monedas regionales | Regional | factor regional de BRL, CLP, MXN y PEN, contemporáneo | 23,55% | -0,01% | En la ecuación de variación mensual, un aumento del regresor se asocia con una variación mensual de la TRM mayor; coeficiente 0,0161 y 0 (contemporáneo). El IC95% no cruza cero al 5% en la inferencia HAC. Su contribución contable media fue -0.014% de Δln TRM y fue positiva en 44.6% de los meses. En 2020 en adelante coincidieron los signos de 100.0% de sus términos con los de la muestra completa. Señal económica: Señal común de monedas comparables; no separa shocks regionales simultáneos. Asociación histórica parcial; no es un efecto causal ni un escenario contrafactual. |
| Condiciones financieras, commodities y actividad internacional | Condiciones financieras y actividad internacional | cambio del rendimiento real TIPS de EE. UU. a 10 años, contemporáneo; cambio del rendimiento real de EE. UU. a 5 años, contemporáneo; cambio del Treasury de EE. UU. a 2 años, contemporáneo; cambio del Treasury de EE. UU. a 10 años, contemporáneo; cambio de la pendiente Treasury 10Y–2Y, contemporáneo; cambio de la compensación inflacionaria de EE. UU. a 5 años, contemporáneo; cambio de la compensación inflacionaria de EE. UU. a 10 años, contemporáneo; cambio de incertidumbre de política económica global, contemporáneo; cambio del estrés financiero STL, contemporáneo; cambio del índice de condiciones financieras de Chicago, contemporáneo; cambio del índice ajustado de condiciones financieras de Chicago, contemporáneo; cambio logarítmico del Brent global, contemporáneo; cambio logarítmico del índice global de commodities, contemporáneo; cambio del desempleo armonizado de EE. UU., contemporáneo; cambio logarítmico del empleo manufacturero de EE. UU., contemporáneo; cambio logarítmico de la producción industrial de EE. UU., contemporáneo; cambio logarítmico de fletes de transporte, contemporáneo | 21,63% | -0,04% | Condiciones financieras, commodities y actividad internacional es un bloque compuesto por 17 términos (cambio del rendimiento real TIPS de EE. UU. a 10 años, contemporáneo; cambio del rendimiento real de EE. UU. a 5 años, contemporáneo; cambio del Treasury de EE. UU. a 2 años, contemporáneo; cambio del Treasury de EE. UU. a 10 años, contemporáneo; cambio de la pendiente Treasury 10Y–2Y, contemporáneo; cambio de la compensación inflacionaria de EE. UU. a 5 años, contemporáneo; cambio de la compensación inflacionaria de EE. UU. a 10 años, contemporáneo; cambio de incertidumbre de política económica global, contemporáneo; cambio del estrés financiero STL, contemporáneo; cambio del índice de condiciones financieras de Chicago, contemporáneo; cambio del índice ajustado de condiciones financieras de Chicago, contemporáneo; cambio logarítmico del Brent global, contemporáneo; cambio logarítmico del índice global de commodities, contemporáneo; cambio del desempleo armonizado de EE. UU., contemporáneo; cambio logarítmico del empleo manufacturero de EE. UU., contemporáneo; cambio logarítmico de la producción industrial de EE. UU., contemporáneo; cambio logarítmico de fletes de transporte, contemporáneo). No tiene un coeficiente ni un signo único; los signos estimados por término son cambio del rendimiento real TIPS de EE. UU. a 10 años, contemporáneo: negativo; cambio del rendimiento real de EE. UU. a 5 años, contemporáneo: negativo; cambio del Treasury de EE. UU. a 2 años, contemporáneo: negativo; cambio del Treasury de EE. UU. a 10 años, contemporáneo: positivo; cambio de la pendiente Treasury 10Y–2Y, contemporáneo: negativo; cambio de la compensación inflacionaria de EE. UU. a 5 años, contemporáneo: negativo; cambio de la compensación inflacionaria de EE. UU. a 10 años, contemporáneo: negativo; cambio de incertidumbre de política económica global, contemporáneo: negativo; cambio del estrés financiero STL, contemporáneo: positivo; cambio del índice de condiciones financieras de Chicago, contemporáneo: positivo; cambio del índice ajustado de condiciones financieras de Chicago, contemporáneo: negativo; cambio logarítmico del Brent global, contemporáneo: negativo; cambio logarítmico del índice global de commodities, contemporáneo: negativo; cambio del desempleo armonizado de EE. UU., contemporáneo: negativo; cambio logarítmico del empleo manufacturero de EE. UU., contemporáneo: positivo; cambio logarítmico de la producción industrial de EE. UU., contemporáneo: negativo; cambio logarítmico de fletes de transporte, contemporáneo: positivo. La lectura recomendada es su suma de contribuciones mensuales y no una dirección global. Su contribución contable media fue -0.037% de Δln TRM y fue positiva en 50.0% de los meses. En 2020 en adelante coincidieron los signos de 64.7% de sus términos con los de la muestra completa. Señal económica: Bloque de múltiples términos con escalas y rezagos distintos; no tiene un coeficiente ni un signo económico único. Asociación histórica parcial; no es un efecto causal ni un escenario contrafactual. |
<!-- /AUTO:interpretacion_factores -->

### Incertidumbre de los pesos

<!-- AUTO:bootstrap_intervalos -->
La incertidumbre se evalúa con 200 réplicas de un *bootstrap* circular de bloques de 12 meses. Los intervalos percentiles del 95% de los tres factores principales son: Monedas regionales, **16,63%–27,30%**; Condiciones financieras, commodities y actividad internacional, **17,56%–31,73%**; Dólar amplio, **8,74%–20,85%**. Son intervalos de la asignación Shapley bajo remuestreo temporal, no intervalos de un efecto causal.
<!-- /AUTO:bootstrap_intervalos -->

### Comparación de especificaciones

<!-- AUTO:comparacion_especificaciones -->
| Métrica | Controles externos y financieros | Marco macroeconómico integral |
|---|---:|---:|
| Observaciones efectivas | 240 | 240 |
| R² | 49,45% | 68,54% |
| R² ajustado | 47,92% | 63,67% |
| MAPE, validación condicional de 48 meses | 2,01% | 1,49% |
| Acierto de dirección | 68,75% | 83,33% |
| R² condicional frente a caminata aleatoria | 31,92% | 56,87% |
<!-- /AUTO:comparacion_especificaciones -->

### Métricas del pronóstico

<!-- AUTO:metricas_pronostico -->
La validación expansiva de 48 meses obtiene MAPE de **2,49%**, acierto de dirección de **52,08%** y R² frente a la caminata aleatoria de **−1,46%**. La caminata obtiene MAPE de **2,39%**. Es decir, la ecuación explicativa no se convierte automáticamente en un buen pronóstico y, con esta información, el benchmark simple sigue siendo superior.
<!-- /AUTO:metricas_pronostico -->

## Ejecutar productos

```powershell
trm-model validate
trm-model vintage-status
trm-model run-monthly
trm-model run-daily-direction
trm-model run-daily-volatility
trm-model run-research --module <nombre>
```

Los productos diarios y algunos módulos de investigación requieren dependencias opcionales. Consulte [`docs/02_inicio_rapido.md`](docs/02_inicio_rapido.md) y [`docs/operacion/comandos.md`](docs/operacion/comandos.md) antes de ejecutarlos.

El entry point histórico `python .\src\estimate_model.py` se conserva por compatibilidad. La CLI y los runners registran la corrida en `artifacts/runs/<run_id>/manifest.json` cuando el producto dispone de runner target.

## Resultados, workbook y gráficos

- [`results/`](results/README.md) conserva las salidas tabulares y sus contratos de ownership.
- [`deliverables/modelo_trm_colombia.xlsx`](deliverables/README.md) es el entregable ejecutivo y auditable del producto mensual.
- [`deliverables/graficos/`](deliverables/graficos/README.md) contiene los seis PNG generados desde resultados versionados: Shapley, desempeño, validación, asociaciones estandarizadas, ECM y contribuciones mensuales.
- [`results/output_catalog.json`](results/output_catalog.json) es el inventario ejecutable de ownership; no mantenga una segunda lista manual en este README.

## Arquitectura y desarrollo

- [`docs/desarrollo/arquitectura_actual.md`](docs/desarrollo/arquitectura_actual.md): qué está implementado hoy y qué sigue en transición.
- [`docs/arquitectura_target.md`](docs/arquitectura_target.md): arquitectura objetivo y decisiones de migración; no debe leerse como estado ya completado.
- [`docs/metodologia/estimacion_inferencia.md`](docs/metodologia/estimacion_inferencia.md): frontera entre ajuste, inferencia y validación predictiva.
- [`docs/desarrollo/compatibilidad_legacy.md`](docs/desarrollo/compatibilidad_legacy.md): entry points históricos y wrappers.

## Estructura mínima del repositorio

```text
configs/       contratos TOML por producto
 data/         raw, catálogo, bases curadas y vintages
pipelines/     runners y manifests de productos
research/      investigación y sus manifests
results/       outputs versionados y catálogo de ownership
schemas/       contratos JSON
src/trm_model/ implementación target, CLI y provenance
src/model/     compatibilidad y econometría en transición
tests/         pruebas de contrato y comportamiento
deliverables/  workbook y gráficos
artifacts/     manifests de corridas
```

Para conocer la arquitectura completa, los contratos y las reglas de publicación, vaya a [`docs/README.md`](docs/README.md).
