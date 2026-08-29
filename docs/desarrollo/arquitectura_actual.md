# Arquitectura actual

## Capas observadas

```text
CLI / entry points
        ↓
pipelines y wrappers
        ↓
trm_model: paths, contratos, provenance, validación
        ↓
trm_model.monthly.core
        ↓
model: loaders, specs, transforms, estimación, validación y Shapley
        ↓
data/raw, data/vintages, results, deliverables, artifacts
```

La separación target ya tiene módulos en `src/trm_model/`, pero la ruta mensual actual todavía conserva una dependencia inversa de transición: `trm_model.monthly.core` importa componentes de `src/model/`. La documentación debe decir “migración incremental”, no “independencia completa”.

## Entry points

- `trm-model validate`: contratos, fuentes activas y leakage.
- `trm-model run-monthly`: bundle mensual y manifest `monthly_bundle`.
- `trm-model run-daily-direction`: wrapper diario.
- `trm-model run-daily-volatility`: wrapper de volatilidad.
- `trm-model run-research --module`: wrapper de investigación.
- `trm-model vintage-status`: estado PIT.
- `src/estimate_model.py`: compatibilidad, delega al core mensual.
- `pipelines/monthly.py`: wrapper compatible y consulta de los 45 outputs.

## Provenance

`trm_model.provenance.runner.run_product` ofrece un runner común para validar manifests, revisar inputs, escribir estados de corrida y reconciliar outputs. El bundle mensual tiene además lógica específica en `trm_model.cli` porque reúne tres ownerships.

## Límites actuales

- Los manifests declarativos no son una garantía de que todos sus outputs se produzcan en cada runner.
- El catálogo `results/output_catalog.json` contiene outputs heredados que coexisten con el contrato de generación mensual.
- `latest_available` no produce un backtest PIT automáticamente.
- Los README históricos todavía contienen detalles que pueden divergir si no se regeneran o validan contra CSVs.

## Dirección objetivo

La arquitectura objetivo está documentada en [`../arquitectura_target.md`](../arquitectura_target.md). Sus checkboxes son criterios de migración, no afirmaciones de cumplimiento actual. El siguiente paso técnico es centralizar loader, specs y transformaciones en `trm_model.monthly`, demostrar paridad y mantener `src/model` como fachada de compatibilidad.
