# Pronóstico de la TRM a largo plazo (6-24 meses)

## Hallazgo central

La TRM colombiana tiene **reversión a la media predecible** a horizontes de 6-24 meses. La mejor señal (wavelet D3+D4+D5) explica el **46% de la variación del retorno futuro a 12 meses** out-of-sample, con acierto de dirección del 74% y significancia estadística al 0,1%.

Este contraste con el corto plazo es el resultado más importante del proyecto:

| Horizonte | Mejor R² OOS | p-valor | Interpretación |
|---|---|---|---|
| 1 día | 0,7% | 0,62 | Imprevisible (eficiencia débil) |
| 1 mes | -11% | 0,21 | Imprevisible |
| **6 meses** | **21%** | **0,03** | Predecible |
| **12 meses** | **46%** | **<0,001** | Muy predecible |
| **18 meses** | **46%** | **<0,001** | Muy predecible |

---

## Ranking de señales (12 meses, out-of-sample)

| # | Señal | R² OOS | Correlación | Dirección | DM p |
|---|---|---|---|---|---|
| 1 | Wavelet D3+D4+D5 (8-64m) | **45,9%** | 0,689 | 74,4% | <0,001 |
| 2 | Panel EM (BRL+CLP+MXN+COP) | **43,8%** | 0,620 | 78,2% | <0,001 |
| 3 | CF filter (6-96m) | **40,3%** | 0,629 | 81,8% | <0,001 |
| 4 | D5 sola (32-64m) | 33,7% | 0,612 | 69,9% | 0,006 |
| 5 | Vol realizada 12m | **16,1%** | 0,226 | 69,5% | 0,001 |
| 6 | BN transitorio | 4,0% | -0,158 | 53,4% | 0,30 |
| 7 | Carry z-score | 8,4% | 0,354 | 58,9% | 0,34 |
| 8 | MA 60 meses (z-score) | -0,8% | 0,510 | 66,0% | 0,95 |
| 9 | Cointegración TRM-dólar | -15,4% | -0,040 | 54,3% | 0,09 |
| 10 | HP expanding | -17,8% | -0,021 | 57,8% | 0,13 |

---

## ¿Dónde está la señal? Análisis por frecuencia

La descomposición wavelet revela que el poder predictivo está **concentrado en la banda de 32-64 meses** (ciclo de 3-5 años):

| Banda wavelet | Período | R² OOS | Poder predictivo |
|---|---|---|---|
| D1 | 2-4 meses | -2,1% | Ninguno (ruido) |
| D2 | 4-8 meses | -1,8% | Ninguno |
| D3 | 8-16 meses | 1,1% | Marginal |
| D4 | 16-32 meses | 4,0% | Débil |
| **D5** | **32-64 meses** | **33,7%** | **Fuerte** |
| A5 tendencia | >64 meses | -4,9% | Ninguno |
| **D3+D4+D5** | **8-64 meses** | **45,9%** | **Máximo** |

La señal de 32-64 meses corresponde al **ciclo de la Reserva Federal y del dólar global**: subida de tasas → dólar fuerte → EM deprecian → Fed afloja → corrección. Este ciclo dura 3-5 años y es lo que genera la reversión a la media.

---

## ¿Es un fenómeno solo de Colombia? No — es regional

El análisis de panel con 4 monedas EM confirma que la reversión es un fenómeno compartido:

| Moneda | β individual | t-HAC | R² | Dirección OOS |
|---|---|---|---|---|
| COP | -1,127 | -5,07 | 44,7% | **83,5%** |
| BRL | -1,121 | -8,31 | 45,0% | 72,6% |
| CLP | -1,115 | -8,23 | 48,3% | 75,4% |
| MXN | -1,146 | -6,86 | 47,3% | 81,1% |

Los β son **idénticos** (~-1,13). La velocidad de reversión es la misma en los 4 países. El driver es el ciclo del dólar global, no factores locales.

Correlación de ciclos CF entre monedas: 0,60 – 0,71 (factor común fuerte).

---

## Regímenes (Markov switching)

El modelo identifica dos estados de la TRM relativa a su tendencia:

| Régimen | % del tiempo | Retorno medio 12m | Volatilidad | Persistencia |
|---|---|---|---|---|
| Tranquilo | 55% | +0,3% | 5,3% | 96% (dura ~25 meses) |
| Turbulento | 45% | +8,7% | 16,5% | 5% (dura ~1 mes) |

El régimen turbulento corresponde a episodios de **overshooting** (2008, 2015, 2020, 2022) seguidos de correcciones fuertes.

---

## ¿Por qué CF y wavelets funcionan pero HP y MA no?

| Filtro | R² OOS | Por qué |
|---|---|---|
| CF filter | 40,3% | Asimétrico — mínimo look-ahead |
| Wavelet D3+D4+D5 | 45,9% | Descomposición exacta en frecuencias |
| HP estándar | 40,2% (ilusión) | Endpoint bias masivo — usa datos futuros |
| HP expanding | -17,8% | Pierde la señal por endpoint noise |
| MA 60 meses | -32,8% | Demasiado suave — β inestable |

El HP filter tiene R²=51% in-sample pero FALLA out-of-sample porque su endpoint bias le da información del futuro. El CF filter y las wavelets no sufren este problema (o lo sufren mucho menos).

---

## Señal complementaria: volatilidad realizada

La vol realizada a 12 meses es la **única señal significativa que no mide desviación de tendencia**:

| Señal | R² OOS | DM p | Interpretación |
|---|---|---|---|
| Vol TRM 12m | 16,1% | 0,001 | Variance risk premium: alta vol → depreciación futura |

Períodos de alta volatilidad predicen depreciación adicional — es una prima de riesgo, no reversión a la media. Es complementaria al CF filter.

---

## Lo que NO funciona a largo plazo

| Señal | R² OOS | Por qué falla |
|---|---|---|
| Cointegración TRM-dólar | -15,4% | No están cointegradas (Johansen: 0 relaciones) |
| Diferencial de tasas nominal | 0,8% | UIP falla pero de forma no explotable |
| Carry Sharpe | -2,4% | El ajuste por vol no mejora |
| Carry neto de EMBIG | -11,1% | Endogeneidad: EMBIG y TRM se mueven juntos |
| Momentum TI 12m | -6,4% | Sin poder predictivo forward |
| Ciclo de la Fed | +2,6% | Marginal, no significativo |

---

## Estado actual de la señal (agosto 2026)

| Indicador | Valor | Interpretación |
|---|---|---|
| Desviación CF | -12,0% | TRM por debajo de tendencia |
| BN transitorio | -14,8% | Ídem |
| Vol realizada 12m | 9,6% anualizada | Normal (mediana histórica ~10%) |
| Prob. régimen turbulento | 22% | Régimen tranquilo |
| Panel EM (4 monedas) | Todas cerca de tendencia | Sin estrés regional |

**Lectura actual**: la TRM está moderadamente por debajo de su equilibrio de largo plazo. La señal sugiere depreciación futura, pero sin urgencia (régimen tranquilo, vol normal).

---

## Implicaciones prácticas

### Para tesorería corporativa

- Si la señal CF > +1σ (TRM cara): considerar no cubrir posiciones cortas en USD al 100%
- Si la señal CF < -1σ (TRM barata): considerar cubrir más agresivamente
- **Acierto: 74-82% a 12 meses** según la señal usada

### Para inversión de portafolio

- La señal no da timing preciso (Sharpe negativo por timing error)
- Útil como **tilt estratégico**: sobreponderar/subponderar exposición a COP
- Combinar con vol realizada para sizing de posición

### Para política económica

- Confirma convergencia PPP de largo plazo (~β = -1,13, vida media ~9 meses en régimen turbulento)
- Las desviaciones extremas son temporales pero pueden durar 2-3 años
- La intervención cambiaria no es necesaria si el mercado corrige solo a largo plazo

---

## Estructura del código

```
src/forecast_longterm/
├── README.md                  Este informe
├── signals.py                 5 señales base + evaluación in-sample
├── backtest.py                Backtest OOS con HP expanding
├── extended_signals.py        MA 60m, Markov switching, momentum macro
├── compare_filters.py         8 filtros comparados OOS
├── cf_markov_strategy.py      CF filter + Markov combinado
├── beveridge_nelson.py        Descomposición BN (permanente vs transitorio)
├── panel_em.py                Panel de 4 monedas EM
├── wavelets.py                Descomposición por frecuencia (Daubechies-4)
├── cointegration.py           Cointegración TRM-dólar (resultado negativo)
└── carry_factor.py            Factor de carry y vol realizada
```

## Resultados guardados

```
results/pronostico/
├── senales_largo_plazo.csv                  In-sample por horizonte
├── backtest_largo_plazo_*.csv               OOS por horizonte (HP expanding)
├── senales_extendidas_largo_plazo.csv       MA + momentum
├── comparacion_filtros_tendencia.csv        8 filtros OOS
├── cf_markov_estrategia.csv                 CF puro vs CF×Markov
├── cf_markov_senales.csv                    Series temporales CF+régimen
├── beveridge_nelson_*.csv                   Permanente y transitorio
├── panel_em_*.csv                           Panel 4 monedas
├── wavelets_*.csv                           Componentes por frecuencia
├── cointegracion_*.csv                      Tests y residuos
├── carry_factor_*.csv                       Señales de carry
├── markov_*.csv                             Regímenes identificados
└── series_*.csv                             Tendencias y momentum
```

## Uso

```bash
# Señal principal (CF filter) — 30 segundos
python src/forecast_longterm/cf_markov_strategy.py

# Análisis completo de wavelets — 1 minuto
python src/forecast_longterm/wavelets.py

# Panel EM (4 monedas) — 2 minutos
python src/forecast_longterm/panel_em.py

# Comparación de 8 filtros — 3 minutos (HP expanding lento)
python src/forecast_longterm/compare_filters.py

# Todos los análisis — 10 minutos total
python src/forecast_longterm/signals.py
python src/forecast_longterm/backtest.py
python src/forecast_longterm/extended_signals.py
python src/forecast_longterm/compare_filters.py
python src/forecast_longterm/cf_markov_strategy.py
python src/forecast_longterm/beveridge_nelson.py
python src/forecast_longterm/panel_em.py
python src/forecast_longterm/wavelets.py
python src/forecast_longterm/cointegration.py
python src/forecast_longterm/carry_factor.py
```
