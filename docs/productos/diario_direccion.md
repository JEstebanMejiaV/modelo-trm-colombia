# Producto diario de dirección

`daily_direction` es un producto de apoyo para evaluar modelos de dirección de la TRM a horizonte de un día. No modifica el producto mensual ni debe presentarse como su sustituto.

## Contrato

- Manifest: [`pipelines/manifests/daily_direction.json`](../../pipelines/manifests/daily_direction.json).
- Configuración: [`configs/products/daily_direction.toml`](../../configs/products/daily_direction.toml).
- Entry point: [`pipelines/daily_direction.py`](../../pipelines/daily_direction.py).
- Código de modelos: `src/forecast_daily/` y `src/forecast_short_term.py`.
- Outputs: ownership en [`results/output_catalog.json`](../../results/output_catalog.json).

El contrato declara frecuencia diaria, horizonte de un día, información `pseudo_real_time`, política `latest_available`, benchmark `random_walk` y estado `supporting`.

## Qué evalúa

El producto compara especificaciones direccionales y modelos de aprendizaje automático con sus diagnósticos, importancias de variables y búsquedas de hiperparámetros cuando están disponibles. Los resultados de clasificación, R², dirección, Sharpe o cualquier otra métrica solo son válidos para la muestra, frecuencia y benchmark del CSV correspondiente.

El mejor resultado descrito en la documentación actual puede tener R² OOS positivo, pero dirección o Sharpe desfavorables. Por eso una métrica estadística positiva no se interpreta como estrategia rentable ni como recomendación.

## Ejecución

```powershell
trm-model run-daily-direction
trm-daily-direction
```

La ruta puede requerir los extras `daily` y, según el modelo, `rnn`. Verifique el error y el manifest de corrida antes de interpretar un output. Si el entorno no tiene las dependencias opcionales, el producto mensual base no debería declararse fallido por esa razón.

## Límites

- La información es pseudo-tiempo-real y usa `latest_available`; no es automáticamente un backtest PIT.
- Es un producto de apoyo con ownership separado.
- Los outputs de búsqueda de hiperparámetros son investigación/diagnóstico, no necesariamente el modelo seleccionado.
- No hay que mezclar sus métricas con la validación mensual o de largo plazo.
