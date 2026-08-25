# Validación predictiva

## Benchmark

El benchmark principal del pronóstico mensual es la caminata aleatoria. La comparación debe conservar la misma ventana, variable objetivo y definición de error para el modelo y el benchmark.

## Explicación versus pronóstico

La validación de `monthly_explanation` es condicional: puede usar realizaciones contemporáneas y responde cuánto reproduce la variación observada bajo información ex post. No representa lo que habría conocido un usuario al inicio del mes.

La validación de `monthly_forecast` aplica rezagos de publicación y un holdout expansivo de 48 meses. Sin embargo, su política vigente es `latest_available`: usa la última versión disponible de cada serie. Por eso se llama pseudo-tiempo-real y no backtest genuino.

## Métricas

Las métricas principales son MAPE, acierto de dirección, R² frente a la caminata aleatoria, MAE y, cuando corresponde, Diebold–Mariano. El archivo canónico de métricas mensuales es [`results/pronostico/validacion_metricas_pronostico.csv`](../../results/pronostico/validacion_metricas_pronostico.csv); la predicción por origen está en `validacion_predicciones_pronostico.csv`.

La corrida versionada actual informa aproximadamente:

- modelo: MAPE 2,49%, dirección 52,08%;
- caminata aleatoria: MAPE 2,39%;
- R² del modelo frente a caminata: -1,46%;
- Diebold–Mariano: no rechaza igualdad en el resultado documentado.

Estas cifras son un corte de resultados, no un compromiso de desempeño futuro.

## Requisitos para un backtest genuino

Cada origen histórico debe reconstruirse con:

1. un snapshot fechado;
2. hashes y archivos exactos del snapshot;
3. cobertura de todos los factores activos;
4. ausencia de observaciones posteriores al origen;
5. ninguna imputación o fallback a `data/raw`;
6. manifest que registre `origin_date`, snapshot y política `vintage_backtest`.

El reporte de cobertura actual marca solo 3 de 14 factores completos y `backtest_genuino_disponible=false`. Un archivo parcial puede servir para auditar cobertura, pero no para afirmar una historia completa de información disponible.

## Errores comunes

- Usar el R² histórico contemporáneo como prueba de pronóstico.
- Comparar modelos con ventanas distintas.
- Reportar una señal de research como forecast mensual.
- Llamar “tiempo real” a un resultado construido con revisiones actuales.
- Omitir el benchmark o el horizonte al presentar MAPE y dirección.
