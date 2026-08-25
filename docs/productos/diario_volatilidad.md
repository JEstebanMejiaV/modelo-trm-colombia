# Producto diario de volatilidad y VaR

`daily_volatility` estima volatilidad condicional y evalúa VaR de la TRM. Es un producto de apoyo para medición de riesgo de mercado; no es una recomendación de inversión ni altera el modelo mensual.

## Contrato

- Manifest: [`pipelines/manifests/daily_volatility.json`](../../pipelines/manifests/daily_volatility.json).
- Configuración: [`configs/products/daily_volatility.toml`](../../configs/products/daily_volatility.toml).
- Entry point: [`pipelines/daily_volatility.py`](../../pipelines/daily_volatility.py).
- Código: `src/volatility_model.py` y el wrapper de pipeline.
- Outputs: `results/pronostico/volatilidad_modelos_garch.csv`, `volatilidad_serie_condicional.csv` y `volatilidad_var_backtest.csv`.

El contrato declara frecuencia diaria, horizonte de un día, información `pseudo_real_time`, política `latest_available`, benchmark `conditional_volatility`, estado `supporting`, niveles VaR 90%, 95% y 99%, y una evaluación de 500 días.

## Lectura de resultados

Las comparaciones GARCH, EGARCH, GJR-GARCH y GARCH con VIX sirven para evaluar ajuste y riesgo condicional. El backtest de VaR debe leerse junto con el nivel de confianza, el número de violaciones, la ventana y las pruebas de cobertura. Una tasa de violaciones distinta al nivel nominal no demuestra por sí sola que un modelo sea inútil o que una estrategia sea rentable.

La evidencia versionada actualmente reporta 31 violaciones de 500 observaciones al 95% para la especificación documentada. Esta cifra es diagnóstica de esa corrida y debe verificarse en el CSV antes de publicarla.

## Ejecución

```powershell
trm-model run-daily-volatility
trm-daily-volatility
```

La dependencia `arch` es opcional y las rutas diarias pueden no estar disponibles en una instalación mínima. La ausencia de este producto no invalida la explicación o el pronóstico mensual.

## Límites

- No sustituye un sistema de límites, stress testing o validación independiente.
- Usa la política de vintage declarada por el manifest; no se debe rotular como histórico PIT sin snapshots adecuados.
- No mezcle VaR, volatilidad diaria y métricas de dirección o de horizonte largo.
