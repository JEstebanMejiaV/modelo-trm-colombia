# Reproducibilidad

## Qué se reproduce

Una corrida reproducible debe poder reconstruir, con el mismo checkout y las mismas entradas:

- muestra y transformaciones;
- especificación y rezagos;
- coeficientes y métricas;
- outputs tabulares;
- gráficos y workbook;
- manifest con hashes y ambiente.

Esto no equivale por sí solo a un backtest point-in-time: una corrida puede ser byte-reproducible con `latest_available` y aun así usar revisiones que no estaban disponibles en el origen histórico.

## Entorno

- Python declarado: `>=3.12,<3.15`.
- Dependencias base: `requirements.lock`.
- Dependencias opcionales: `requirements-optional.lock` y extras de `pyproject.toml`.
- Instalación editable: `python -m pip install -e . --no-deps`.
- El wheel no contiene datos, configs, schemas ni resultados; la operación de datos es checkout-bound.

## Determinismo

La configuración común fija, entre otros, HAC de seis meses, holdout de 48 meses, 14 jugadores Shapley, 200 réplicas, bloques de 12 meses, 64 permutaciones y semilla `20260823`. Productos diarios o de ML pueden tener parámetros de determinismo adicionales declarados en sus módulos y manifests.

## Evidencia

El manifest de corrida registra:

- `run_id`, producto, estado y timestamps UTC;
- commit y estado Git;
- archivos de configuración y hashes;
- inputs efectivos y hashes;
- outputs efectivos y hashes;
- árbol de contratos y código;
- versión de Python, plataforma y paquetes;
- conjunto de información, política de vintage, origen y warnings.

La comparación de un resultado debe usar el manifest de la corrida y no solo los archivos bajo `results/`.

## Reproducción limpia

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
python -m pip install -e . --no-deps
trm-model validate
trm-model run-monthly
python .\src\check_reproducibility.py
```

Si el checkout está sucio, el manifest lo registra. Un `git_dirty=true` no invalida automáticamente el cálculo, pero impide tratarlo como una referencia limpia sin revisar los cambios.
