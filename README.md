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
La tabla se genera desde `results/explicacion/coeficientes_controles_externos.csv`.
<!-- /AUTO:coeficientes_controles_externos -->

### Métricas de controles externos

<!-- AUTO:metricas_controles_externos -->
Las métricas se generan desde los resultados versionados de explicación histórica.
<!-- /AUTO:metricas_controles_externos -->

### Coeficientes del marco macroeconómico integral

<!-- AUTO:coeficientes_marco_macro_integral -->
La tabla se genera desde `results/explicacion/coeficientes_marco_macro_integral.csv`.
<!-- /AUTO:coeficientes_marco_macro_integral -->

### Pesos explicativos

<!-- AUTO:pesos_shapley -->
Los pesos se generan desde `results/explicacion/pesos_explicativos_marco_macro_integral.csv`.
<!-- /AUTO:pesos_shapley -->

### Incertidumbre de los pesos

<!-- AUTO:bootstrap_intervalos -->
Los intervalos se generan desde `results/explicacion/intervalos_bootstrap_pesos_shapley.csv`.
<!-- /AUTO:bootstrap_intervalos -->

### Comparación de especificaciones

<!-- AUTO:comparacion_especificaciones -->
La comparación se genera desde `results/explicacion/comparacion_especificaciones.csv`.
<!-- /AUTO:comparacion_especificaciones -->

### Métricas del pronóstico

<!-- AUTO:metricas_pronostico -->
Las métricas se generan desde `results/pronostico/validacion_metricas_pronostico.csv`.
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
- [`deliverables/graficos/`](deliverables/graficos/README.md) contiene los cinco PNG generados desde resultados versionados.
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
