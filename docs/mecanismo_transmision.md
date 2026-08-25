# Mecanismo de transmisión de la TRM

## Lectura empírica

El modelo ampliado describe asociaciones dinámicas entre la variación mensual de la TRM y 13 factores. La muestra común cubre mayo de 2006 a abril de 2026, con 240 observaciones efectivas. El R² es 67,47%, el R² ajustado 62,80%, el MAPE histórico condicional 1,51% y el acierto de dirección 83,33%.

La ampliación conserva un único jugador Shapley para el bloque **Condiciones financieras, commodities y actividad internacional**. Ese jugador reúne 17 términos activos: rendimientos reales y nominales de EE. UU., expectativas de inflación a 5 y 10 años, pendiente 10Y–2Y, Brent, commodities, EPU global, STLFSI, NFCI, ANFCI, desempleo estadounidense, empleo manufacturero, producción industrial y fletes/logística. La agrupación evita que la colinealidad y la explosión combinatoria de jugadores hagan ilegible la descomposición.

El desempleo activo usa `LRUN64TTUSM156S`, que cubre la muestra completa. High-yield, TED, `UNRATE` y los indicadores de China permanecen como candidatos documentados cuando no cubren la ventana; no se interpolan ni se incorporan al modelo balanceado. La cobertura se audita en `data/base_global_cobertura.csv`.

## Canales y pesos Shapley

Los pesos son participaciones descriptivas del R² incremental, no efectos causales. Se calculan sobre los 8.192 subconjuntos de los 13 factores y suman 100% entre factores.

| Canal o factor | Peso entre factores | Coeficiente principal | Lectura cautelosa |
|---|---:|---:|---|
| Monedas regionales BRL, CLP, MXN y PEN | 24,59% | +0,01758 | La depreciación regional se mueve junto con la TRM; contiene shocks globales compartidos. |
| Condiciones financieras, commodities y actividad internacional | 21,62% | Bloque de 17 términos | Agrupa tasas, expectativas, riesgo, commodities, actividad, desempleo y logística. |
| Dólar amplio | 15,46% | +0,16176 | La fortaleza global del USD se asocia con depreciación del COP. |
| Riesgo soberano EMBIG Colombia | 14,26% | +0,02478 | El spread contiene riesgo idiosincrático, liquidez y aversión global al riesgo. |
| Balanza comercial cambiaria | 6,47% | +0,05448 | El signo estimado es contrario al canal simple de oferta de divisas; puede reflejar simultaneidad. |
| VIX | 6,12% | +0,01464 | Aversión global al riesgo; comparte información con el dólar y las monedas regionales. |
| Términos de intercambio | 4,29% | +0,01682 | La entrada contemporánea es explicación histórica, no información disponible al inicio del mes. |
| Flujos netos de capital | 3,40% | +0,00066 | Alta volatilidad y endogeneidad reducen la precisión del coeficiente. |
| Reservas internacionales | 2,03% | −0,25123 | El coeficiente grande no implica un peso explicativo grande; la intervención puede responder a la TRM. |
| Remesas | 1,15% | +0,16805 | El signo no coincide con una lectura simple de oferta de dólares; puede haber respuesta a shocks cambiarios. |
| Diferencial BEI 5 años | 0,32% | −0,00240 | Compensación de mercado, no expectativa pura; entra en primera diferencia y con L1. |
| Diferencial de tasas | 0,20% | +0,00109 | Diferencial nominal endógeno; no identifica un shock monetario. |
| Déficit fiscal | 0,10% | +0,00003 | Participación marginal y coeficiente impreciso. |

El canal global y regional —monedas regionales, dólar amplio, VIX y el bloque financiero/internacional— suma 67,79% del peso entre factores. El riesgo soberano aporta 14,26%, el sector externo colombiano 17,34% y la política doméstica 0,61%. Esta suma organiza la lectura; no debe interpretarse como una partición causal de la depreciación.

## Secuencia de transmisión

```text
Condiciones financieras, expectativas y actividad internacional
        │
        ├── dólar global, tasas, BEI, NFCI/ANFCI, EPU, VIX
        ├── commodities y fletes/logística
        └── empleo, producción y desempleo de EE. UU.
                         │
                         ▼
             apetito por riesgo y liquidez internacional
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   monedas EM       EMBIG Colombia    precios/flujo externo
  BRL-CLP-MXN-PEN       riesgo país     TI, balanza, capitales,
                                      reservas y remesas
        └────────────────┼────────────────┘
                         ▼
                 Δ ln(TRM): COP por USD
```

Un episodio de aversión al riesgo puede fortalecer el dólar, depreciar las monedas regionales y elevar el EMBIG al mismo tiempo. Shapley distribuye la señal compartida entre esos factores; no demuestra que uno de ellos cause los demás.

## Explicación histórica frente a pronóstico

La explicación histórica usa algunos valores contemporáneos realizados: términos de intercambio, dólar amplio, VIX, EMBIG, monedas regionales y los términos del bloque global. Por eso sirve para responder qué variables se movieron junto con la TRM *ex post* o como nowcast condicional.

El pronóstico mensual evita regresores contemporáneos y aplica el calendario de publicación:

- mercados, rendimientos, riesgo, commodities y diferencial BEI: `.L1`;
- remesas, reservas, balanza y flujos de capital: `.L2`;
- términos de intercambio y déficit fiscal: `.L3`;
- empleo, desempleo y fletes/logística: `.L2`;
- factor regional seleccionado: BRL, CLP y MXN con `.L1`.

La validación mensual obtiene MAPE 2,58%, frente a 2,39% de la caminata aleatoria, y R² −4,84% frente a ese benchmark. El resultado confirma que un buen ajuste histórico con información contemporánea no es automáticamente un pronóstico ex ante. Además, el backtest sigue siendo pseudo-tiempo-real porque solo 3 de los 13 factores tienen vintages históricos completos para los 48 orígenes.

## BEI, candidatos y política de faltantes

El diferencial BEI compara la compensación inflacionaria colombiana a cinco años —TES nominal menos TES UVR— con `BKEVEN05` de EE. UU. Se promedian por separado las curvas y se conserva una versión sobre fechas diarias comunes como robustez. La primera diferencia con rezago de un mes es la especificación vigente por estabilidad; el nivel obtiene un BIC algo menor en la comparación mecánica, pero su evidencia de estacionariedad cambia al incluir tendencia o quiebres. Ninguna de las dos medidas es una expectativa pura: incorpora primas de inflación, plazo, liquidez y riesgo.

Las series candidatas se tratan como evidencia de cobertura, no como datos que deban completarse artificialmente:

| Candidato | Estado | Decisión |
|---|---|---|
| High-yield OAS `BAMLH0A0HYM2` | Descarga/cobertura no utilizable para 2006–2026 | Documentado, fuera del modelo. |
| TED `TEDRATE` | Termina en 2022-01 | Documentado, fuera del modelo. |
| `UNRATE` | Faltante publicado en 2025-10 | Se conserva el vacío; el modelo usa `LRUN64TTUSM156S`. |
| Indicadores de China | Varias series terminan antes de abril de 2026 o tienen faltantes | Exploratorios; no entran al score global completo. |

La regla es conservar la columna y la cobertura, pero no interpolar, transportar el último valor, convertir el faltante en cero ni seleccionar una muestra distinta solo para hacer entrar el candidato.

## Diagnósticos y límites

En el ampliado, Jarque–Bera rechaza normalidad al 5% (`p = 0,004`), mientras ARCH-LM no rechaza heterocedasticidad condicional (`p = 0,147`). No se detecta autocorrelación relevante; RESET (`p = 0,241`) y CUSUM (`p = 0,617`) no rechazan la forma funcional ni una inestabilidad global. Los errores estándar HAC se mantienen para la inferencia de la media, pero no convierten las asociaciones en relaciones causales.

La prueba bounds del ECM es no concluyente al 5%: el p-valor del límite I(1) es aproximadamente 0,075. Por ello, el modelo principal permanece en primeras diferencias y los coeficientes de largo plazo del ECM son exploratorios.

## Conclusión

La TRM colombiana se comporta en la muestra como una moneda emergente expuesta a un factor global y regional común, con un componente adicional de riesgo soberano y canales externos domésticos. Las nuevas expectativas de inflación, condiciones financieras, desempleo estadounidense, actividad industrial y fletes enriquecen la información disponible y elevan la explicación histórica, pero los candidatos incompletos no justifican imputaciones. La evidencia de pronóstico mensual exige mantener la caminata aleatoria como benchmark y separar siempre la explicación contemporánea de la disponibilidad ex ante.
