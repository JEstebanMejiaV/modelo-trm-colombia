# Investigación de señales de largo plazo

`long_horizon_research` reúne módulos exploratorios para horizontes de 6 a 24 meses. No es un producto primario de pronóstico y no puede promocionarse automáticamente por obtener un R² OOS positivo.

## Contrato

- Manifest: [`research/manifests/long_horizon_research.json`](../../research/manifests/long_horizon_research.json).
- Configuración: [`configs/products/long_horizon_research.toml`](../../configs/products/long_horizon_research.toml).
- Código y explicación detallada: [`src/forecast_longterm/README.md`](../../src/forecast_longterm/README.md).
- Entry point general: `trm-model run-research --module <nombre>`.
- Outputs: grupo `long_horizon_research` en [`results/output_catalog.json`](../../results/output_catalog.json).

El contrato declara estado `research`, información `exploratory`, política `latest_available`, benchmark `random_walk` y horizonte base de seis meses.

## Módulos

El conjunto incluye wavelets, filtros de tendencia, Beveridge–Nelson, Markov switching, panel de monedas emergentes, cointegración, carry, señales globales y backtests a distintos horizontes. Cada módulo tiene supuestos distintos; no deben combinarse sus cifras como si fueran una única especificación.

## Estado de la evidencia

La documentación actual reporta señales fuertes en algunas combinaciones de horizonte y frecuencia, especialmente para wavelets y panel EM, pero también muestra que otras evaluaciones agregadas no superan la caminata aleatoria. Esa aparente contradicción no se resuelve con una cifra resumen: hay que revisar la ventana OOS, la reconstrucción de la señal, el benchmark y si el filtro usó la muestra completa.

El manifest advierte que algunos filtros, probabilidades suavizadas y wavelets existentes pueden usar información de toda la muestra. Hasta reconstruir cada señal dentro de cada ventana OOS, los resultados son exploratorios y no son evidencia operativa ex ante.

La variante `long_horizon_research.backtest_embargo.v1` corrigió la disponibilidad temporal de las etiquetas forward en los evaluadores rolling: el entrenamiento de un origen t excluye las observaciones cuyo horizonte aún no terminó. En el backtest agregado HP expanding, el R² OOS corregido fue −22,8% a 6 meses, −63,1% a 12 meses, −177,0% a 18 meses y −459,7% a 24 meses. La corrección revela que las cifras históricas estaban sobreestimadas; no se promociona ninguna señal y los filtros CF, wavelet y Markov aún requieren reconstrucción point-in-time por origen.

## Ejecución

```powershell
trm-model run-research --module <nombre>
```

Los scripts individuales también pueden ejecutarse desde el checkout, pero debe documentarse cuál se ejecutó y con qué inputs. Los extras de largo plazo, como `PyWavelets`, son opcionales.

## Criterio de promoción

Una señal solo debería proponerse para producto cuando tenga:

1. reconstrucción point-in-time por origen;
2. benchmark y horizonte fijados antes de la evaluación;
3. ventana OOS sin filtros que miren el futuro;
4. estabilidad en submuestras;
5. manifest de inputs/outputs y revisión metodológica;
6. una página de producto separada de la investigación si se aprueba.

No se deben formular recomendaciones financieras a partir de estas señales.
