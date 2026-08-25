# Registro de experimentos y modelos

Este directorio registra **especificaciones**, no solo ejecuciones.

- `experiment_id`: identidad inmutable de una hipótesis, configuración y decisión.
- `run_id`: ejecución concreta, registrada en `artifacts/runs/<run_id>/manifest.json`.
- `parent_experiment_id`: variante derivada de un experimento anterior.
- `metrics`: resultados resumidos con unidad, benchmark y split.
- `evidence`: rutas a CSV, metadata o diagnósticos que respaldan la decisión.

El registro inicial está en [`registry.json`](registry.json) y se valida contra [`schemas/experiment_registry.json`](../schemas/experiment_registry.json). Los experimentos nuevos deben agregarse, no sobrescribir un ID existente.

## Consultar

```powershell
python -m trm_model.cli experiment-validate
python -m trm_model.cli experiment-list
python -m trm_model.cli experiment-list --product monthly_forecast
python -m trm_model.cli experiment-show monthly_forecast.full.v1
```

También están disponibles los comandos instalados `trm-model experiment-list` y equivalentes cuando el entry point está correctamente instalado.

## Registrar una variante

1. Copie esta plantilla en un archivo fuera del registro, por ejemplo `experiments/new_experiment.json`.
2. Use un `experiment_id` nuevo; no reutilice el ID de la especificación padre.
3. Declare hipótesis, cambio, código, configuración, inputs, parámetros y métricas.
4. Registre la ejecución con el runner del producto.
5. Complete `metrics`, `decision` y `evidence` y agregue el registro:

```powershell
python -m trm_model.cli experiment-register --file .\experiments\new_experiment.json
python -m trm_model.cli experiment-validate
```

El comando rechaza IDs duplicados y padres inexistentes. La historia de cada edición queda en Git; los manifests de corrida relacionan el `experiment_id` con el commit, inputs, outputs y ambiente efectivos.

## Plantilla mínima

```json
{
  "schema_version": 1,
  "experiment_id": "monthly_forecast.new_feature.v1",
  "product_id": "monthly_forecast",
  "model_id": "forecast_new_feature",
  "title": "Nueva variante de pronóstico",
  "status": "planned",
  "change_type": "feature",
  "created_at_utc": "2026-08-23T00:00:00Z",
  "parent_experiment_id": "monthly_forecast.full.v1",
  "hypothesis": "La nueva señal mejora el error fuera de muestra.",
  "change_summary": "Se agrega una señal con rezago documentado.",
  "code_paths": ["src/trm_model/monthly/specifications.py"],
  "config_paths": ["configs/products/monthly_forecast.toml"],
  "input_sources": ["source_registry"],
  "parameters": {"lag": 1},
  "metrics": [],
  "decision": {
    "outcome": "pending",
    "rationale": "Pendiente de validación expansiva.",
    "promotion_criteria": ["No leakage", "Superar benchmark en ventana fijada"]
  },
  "evidence": [],
  "tags": ["forecast", "monthly"],
  "notes": []
}
```

## Límites actuales

El registro inicial reconstruye el inventario de especificaciones vigentes y resultados versionados; no puede reconstruir cambios históricos que nunca se registraron. Los outputs bajo `results/` pueden ser sobrescritos por una nueva corrida. Para una auditoría completa conserve el manifest de corrida y, si se requiere conservar los bytes, archive los outputs fuera de `results/` con una política de retención.
