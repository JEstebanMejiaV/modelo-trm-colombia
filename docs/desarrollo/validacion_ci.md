# Validación y CI

## Checks locales

La validación completa recomendada es:

```powershell
python -m compileall -q src pipelines research tests
python src/check_architecture.py
trm-model validate
python -m pytest -q
trm-model run-monthly
python src/build_charts.py
python src/sync_workbook_openpyxl.py
python src/check_charts.py
python src/check_reproducibility.py
python src/check_outputs.py
```

El orden importa: primero se validan contratos y arquitectura; luego se generan outputs; al final se comprueba sincronización y reproducibilidad.

## CI actual

El workflow [`model-check.yml`](../../.github/workflows/model-check.yml) ejecuta en GitHub Actions:

- Python 3.12 y dependencias lock;
- construcción e importación de un wheel checkout-bound;
- `compileall`;
- `check_architecture.py`;
- `trm-model validate`;
- pytest;
- `trm-model run-monthly`;
- reconciliación de manifest, 26 inputs y 42 outputs;
- reconstrucción y check de gráficos;
- fallback del workbook;
- reproducibilidad y checks de outputs.

## Qué demuestra CI

CI demuestra que la ruta versionada pasa los controles definidos para ese checkout. No convierte automáticamente el forecast en backtest PIT ni demuestra causalidad. La revisión de un cambio debe comprobar además que la documentación conserva las etiquetas de producto, benchmark, información y límites.

## Documentación como contrato auxiliar

Los enlaces a código, manifests y outputs deben ser relativos y verificables. Si cambia un comando, ruta o cifra fija, actualice la página canónica o reemplace la cifra por un enlace a la fuente generada. No agregue una segunda lista manual de ownership.
