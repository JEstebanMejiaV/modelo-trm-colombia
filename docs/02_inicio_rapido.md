# Inicio rápido

## Requisitos

El proyecto se prueba con Python `>=3.12,<3.15`. Las dependencias base y de QA están fijadas en `requirements.lock`; los extras opcionales están declarados en [`pyproject.toml`](../pyproject.toml).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
python -m pip install -e . --no-deps
```

Para productos opcionales puede instalar:

```powershell
python -m pip install -e ".[daily,test]" --no-deps
python -m pip install -e ".[longterm,risk]" --no-deps
```

Use los rangos y locks del repositorio; no añada dependencias de ejecución sin actualizar el contrato de instalación y la validación de CI.

## Primera validación

Desde la raíz del checkout:

```powershell
trm-model validate
python -m pytest -q
```

`validate` comprueba fuentes activas, ownership de manifests, contratos de producto y specs de pronóstico. Los tests cubren contratos y comportamiento del repositorio. Ninguno de los dos comandos demuestra que el forecast sea un backtest PIT completo.

## Ejecutar el bundle mensual

```powershell
trm-model run-monthly
```

La corrida llama el core mensual target, produce los 45 outputs generados del bundle y escribe un manifest bajo `artifacts/runs/<run_id>/manifest.json`. Para conservar el entry point histórico también existe:

```powershell
python .\src\estimate_model.py
trm-monthly
```

## Productos adicionales

```powershell
trm-model run-daily-direction
trm-model run-daily-volatility
trm-model run-research --module <nombre>
trm-model vintage-status
```

Consulte [`operacion/comandos.md`](operacion/comandos.md) para requisitos, entradas y límites de cada comando. Los wrappers diarios y de research pueden requerir extras que no forman parte del runtime base.

## Reconstruir entregables

```powershell
python .\src\build_charts.py
python .\src\sync_workbook_openpyxl.py
python .\src\check_charts.py
python .\src\check_outputs.py
python .\src\check_reproducibility.py
```

La ruta `build_workbook.mjs` requiere el entorno privado que provee `@oai/artifact-tool`; el fallback `sync_workbook_openpyxl.py` es la ruta reproducible disponible en el checkout.

## Checkout-bound

El wheel contiene código y entry points, pero no empaqueta `data/raw`, `configs/`, `schemas/`, `results/` ni manifests. `trm-model validate` y la estimación requieren ejecutarse desde el checkout o con `TRM_MODEL_ROOT` apuntando a uno completo. La prueba de wheel en CI solo verifica importación y los contratos que no dependen de datos.

## Después de una corrida

1. Revise el manifest efectivo en `artifacts/runs/`.
2. Compruebe el estado y ownership de outputs.
3. Si cambiaron resultados, regenere gráficos y workbook.
4. Ejecute los checks de publicación.
5. No presente una corrida `latest_available` como backtest genuino.
