# Pronóstico de TRM a un día

Comparación de 11 modelos para predecir el retorno diario de la TRM usando información pública rezagada un día.

## Resultado principal

**Ningún modelo supera la caminata aleatoria de forma estadísticamente significativa (DM test, 5%).**

La TRM diaria es esencialmente imprevisible con factores macroeconómicos y financieros rezagados. Esto es consistente con la hipótesis de eficiencia débil del mercado cambiario colombiano.

## Ranking de modelos (250 días de backtest, ago-2025 a may-2026)

| # | Modelo | Tipo | R² vs caminata | DM p-valor | Dirección |
|---|---|---|---:|---:|---:|
| 1 | XGBoost | ML | +0,38% | 0,89 | 32,4% |
| 2 | Random Forest | ML | +0,37% | 0,85 | 30,4% |
| 3 | **Caminata aleatoria** | — | **0,00%** | — | **50,0%** |
| 4 | LightGBM | ML | -0,16% | 0,96 | 33,2% |
| 5 | Lasso | Lineal | -0,44% | 0,43 | 31,2% |
| 6 | Elastic Net | Lineal | -0,44% | 0,43 | 31,2% |
| 7 | LSTM + Atención | RNN | -1,03% | 0,45 | 30,4% |
| 8 | Ridge | Lineal | -1,40% | 0,43 | 27,6% |
| 9 | OLS | Lineal | -2,28% | 0,32 | 30,8% |
| 10 | LSTM | RNN | -5,50% | 0,04** | 34,8% |
| 11 | GRU | RNN | -10,37% | 0,001*** | 33,2% |

Las RNN (LSTM y GRU) son **significativamente peores** que la caminata — overfittean los datos de entrenamiento.

## Optimización de XGBoost

Se ejecutó una búsqueda aleatoria de 100 configuraciones con TimeSeriesSplit (5 folds temporales):

| Parámetro | Default | Optimizado |
|---|---|---|
| `n_estimators` | 200 | 100 |
| `max_depth` | 3 | 4 |
| `learning_rate` | 0.05 | 0.01 |
| `subsample` | 0.8 | 0.8 |
| `colsample_bytree` | 0.8 | 0.6 |
| `reg_alpha` | 0.1 | 0.0 |
| `reg_lambda` | 1.0 | 5.0 |

| Métrica | Default | Optimizado |
|---|---|---|
| R² vs caminata | +0,38% | +0,30% |
| Sharpe anualizado | -0,39 | +0,22 |
| DM p-valor | 0,89 | 0,79 |

La optimización no cambia la conclusión: ambos están dentro del ruido estadístico.

## Features más importantes (ML)

Promedio de importancia entre Random Forest, XGBoost y LightGBM:

| Feature | Importancia |
|---|---|
| `vol_trm_22d` (volatilidad realizada 22d) | 43,4% |
| `r_vix_L1` (retorno VIX ayer) | 31,8% |
| `d_embig_L1` (cambio EMBIG ayer) | 31,1% |
| `dia_semana` (efecto calendario) | 29,0% |
| `embig_nivel` (nivel EMBIG) | 26,7% |
| `vix_nivel` (nivel VIX) | 23,7% |
| `r_trm_ma22` (momentum 22d) | 22,7% |
| `r_dolar_ma22` (momentum dólar 22d) | 22,0% |
| `r_dolar_ma5` (momentum dólar 5d) | 21,7% |
| `vol_trm_5d` (volatilidad realizada 5d) | 18,7% |

Los factores de **volatilidad** y **riesgo** (VIX, EMBIG) dominan, no los retornos rezagados. Esto sugiere que ML captura variación condicional de la volatilidad, no dirección.

## Arquitectura

```
src/forecast_daily/
├── __init__.py
├── data.py              Carga + 23 features (retornos, momentum, vol, calendario)
├── models.py            8 estimadores: OLS, Ridge, Lasso, ElasticNet, RF, XGBoost, LightGBM
├── rnn_models.py        3 RNNs: LSTM, GRU, LSTM+Atención (PyTorch)
├── optimize_xgboost.py  Grid search con TimeSeriesSplit (100 trials)
├── run.py               Orquestador: backtest 250 días + comparación
└── README.md
```

## Uso

```bash
# Comparación completa (11 modelos)
python src/forecast_daily/run.py

# Solo optimización de XGBoost
python src/forecast_daily/optimize_xgboost.py
```

Requiere: `pip install xgboost lightgbm scikit-learn torch`

## Interpretación

1. **La caminata es imbatible a frecuencia diaria** — el retorno diario de la TRM tiene relación señal/ruido ≈ 0.
2. **Los modelos más complejos overfittean más** — OLS < Ridge < RF/XGBoost < LSTM < GRU (de menos a más overfitting).
3. **La señal está en la volatilidad, no en la dirección** — vol_trm_22d es el feature #1 pero no predice signo.
4. **La señal diaria es frágil** — en otro período de test, el HAR con mercados, condiciones financieras y globales mensuales rezagadas dio R²=13,41%, pero dirección 41,2% y Sharpe anualizado −3,91. La inestabilidad temporal de los coeficientes explica por qué una mejora de RMSE no basta para construir una estrategia.
5. **Consistente con eficiencia débil** — información pública rezagada no permite superar sistemáticamente al mercado.
