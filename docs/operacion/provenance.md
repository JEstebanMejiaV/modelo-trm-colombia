# Provenance y manifests de corrida

## Dos tipos de manifest

### Manifest de producto

Los JSON de `pipelines/manifests/` y `research/manifests/` declaran configuración, frecuencia, información, benchmark, estado, fuentes de specs, outputs y caveats. Son contratos declarativos; no sustituyen la ejecución.

### Manifest de corrida

`artifacts/runs/<run_id>/manifest.json` registra lo que una corrida concreta intentó y produjo. Su `source_of_truth` operativo es el artifact de corrida, no una lista narrativa en README.

## Ciclo de estado

El runner común escribe un manifest `running`, ejecuta el callable y termina en `success` o `failed`. Una falla registra tipo y mensaje; no debe ocultarse detrás de outputs que quedaron de una corrida previa. El runner valida que los outputs seleccionados estén dentro del ownership declarado y que no se dupliquen entre productos.

Para `monthly_bundle`, la reconciliación comprueba:

- producto de corrida `monthly_bundle`;
- productos propietarios `monthly_explanation`, `monthly_forecast` y `robustness`;
- 42 outputs top-level;
- igualdad entre outputs top-level y outputs por producto;
- ausencia de ownership doble.

## Campos de interpretación

Antes de usar un artifact revise al menos:

- `status` y `error`;
- `git_commit` y `git_dirty`;
- `config_records` y `contract_tree_sha256`;
- `input_files`/`input_records`;
- `output_files`/`products`;
- `run_context.information_set`;
- `run_context.vintage_policy`;
- `origin_date`, `snapshot_manifest` y `input_policy` cuando sea PIT;
- `warnings` y ambiente.

Un manifest exitoso demuestra que la corrida terminó bajo sus contratos; no demuestra que el modelo sea causal, que el pronóstico supere la caminata o que el vintage sea históricamente completo.

## Validación

El validador local de contratos está en `src/trm_model/validation/contracts.py` y comprueba schemas JSON, hashes del árbol de contratos y estructura de documentos. El contrato de outputs generado está en `src/trm_model/output_contract.py`.
