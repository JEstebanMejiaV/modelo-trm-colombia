# Registro de experimentos y cambios de modelo

## Propósito

`experiments/registry.json` registra qué se cambió, por qué se cambió, sobre qué modelo se construyó, qué datos/parámetros se usaron, qué métricas se obtuvieron y qué decisión se tomó. No reemplaza el provenance de una ejecución.

| Entidad | Qué identifica | Dónde vive |
|---|---|---|
| `experiment_id` | Especificación, hipótesis y variante | `experiments/registry.json` |
| `run_id` | Ejecución concreta con hashes y ambiente | `artifacts/runs/<run_id>/manifest.json` |
| `git_commit` | Estado del código y documentación | Manifest de corrida |
| `metrics` | Resultados resumidos con benchmark/split | Registro y outputs CSV |
| `parent_experiment_id` | Linaje de una variante | Registro |

## Flujo recomendado

1. Crear un experimento nuevo con un ID nuevo y `parent_experiment_id` si deriva de otro.
2. Registrar la hipótesis antes de ejecutar.
3. Ejecutar el runner del producto, no el script legacy directo, para obtener `experiment_id` en el manifest.
4. Copiar las métricas relevantes desde el CSV correcto, incluyendo unidad, ventana, benchmark y conjunto de información.
5. Documentar la decisión (`reference`, `selected`, `supporting`, `research` o `rejected`).
6. Validar y versionar el registro junto con el cambio de código/configuración.

## Consultas

```powershell
python -m trm_model.cli experiment-validate
python -m trm_model.cli experiment-list --status active
python -m trm_model.cli experiment-list --product long_horizon_research
python -m trm_model.cli experiment-show monthly_forecast.full.v1
```

La salida de `experiment-show` combina el registro versionado con los manifests locales encontrados en `artifacts/runs/`.

## Qué registrar en cada variante

- hipótesis falsable;
- diferencia frente al padre;
- archivos de código y configuración;
- fuentes y vintage policy;
- muestra, horizonte, rezagos y semillas;
- benchmark y split temporal;
- métricas con unidades explícitas;
- decisión y criterio de promoción/rechazo;
- rutas de evidencia.

## Reglas de interpretación

Una mejora en una métrica no basta para promocionar un modelo. Hay que comprobar leakage, cobertura PIT, estabilidad, benchmark, horizonte y consistencia con la categoría del producto. Las cifras de explicación histórica, forecast mensual, dirección diaria, VaR y research no son intercambiables.

El inventario inicial describe el estado conocido al crearse el registro; no inventa una historia de cambios anteriores que nunca se capturó. Los manifests de corrida anteriores a esta integración pueden no tener `experiment_id`.
