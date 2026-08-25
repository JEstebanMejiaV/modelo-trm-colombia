# Modelos diarios

Los modelos diarios se documentan separadamente del modelo mensual porque cambian la frecuencia, la variable objetivo, los inputs y el benchmark.

## Dirección

`daily_direction` evalúa la dirección diaria y algunos modelos de clasificación/regresión, incluidos modelos opcionales de aprendizaje automático. Su contrato, fuentes y outputs están en [`productos/diario_direccion.md`](../productos/diario_direccion.md) y [`pipelines/manifests/daily_direction.json`](../../pipelines/manifests/daily_direction.json).

## Volatilidad y VaR

`daily_volatility` estima volatilidad condicional y realiza backtests VaR con niveles nominales de 90%, 95% y 99% sobre 500 días según la configuración. Sus outputs no deben compararse directamente con MAPE mensual o R² OOS de research.

## Información disponible

Los productos diarios se declaran `pseudo_real_time` y `latest_available`. Esa etiqueta describe la política operativa del manifest, no garantiza que exista una historia PIT completa de cada input.

## Publicación

Para publicar una métrica diaria deben indicarse al menos:

- producto y manifest;
- frecuencia y horizonte;
- ventana de evaluación;
- benchmark;
- inputs y política de vintage;
- si el resultado es primario, diagnóstico o research;
- advertencias económicas, especialmente cuando una métrica de ajuste no implica capacidad direccional o rentabilidad.
