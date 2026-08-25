# Comandos operativos

Ejecute los comandos desde la raíz del checkout, salvo que `TRM_MODEL_ROOT` esté configurado.

| Acción | Comando | Producto/efecto | Dependencias |
|---|---|---|---|
| Validar repositorio | `trm-model validate` | fuentes, contratos y leakage | runtime base |
| Estado de vintages | `trm-model vintage-status` | snapshots y cobertura PIT | runtime base |
| Bundle mensual | `trm-model run-monthly` | explicación, forecast y robustez generados | runtime base |
| Dirección diaria | `trm-model run-daily-direction` | `daily_direction` | extras `daily` según modelo |
| Volatilidad diaria | `trm-model run-daily-volatility` | `daily_volatility` | extra `risk`/`arch` según ruta |
| Investigación | `trm-model run-research --module <nombre>` | módulo research | extras del módulo |
| Wrapper mensual | `trm-monthly` | compatibilidad con runner mensual | runtime base |
| Wrapper legacy | `python .\src\estimate_model.py` | estimación histórica compatible | runtime base |
| Gráficos | `python .\src\build_charts.py` | cinco PNGs | matplotlib/Pillow |
| Workbook fallback | `python .\src\sync_workbook_openpyxl.py` | Excel versionado | openpyxl |
| Checks gráficos | `python .\src\check_charts.py` | hashes y sincronización | runtime base |
| Checks outputs | `python .\src\check_outputs.py` | CSV/Excel/coverage | runtime base |
| Reproducibilidad | `python .\src\check_reproducibility.py` | comparación con baseline | runtime base |
| Tests | `python -m pytest -q` | smoke/contratos | extra `test` |

## Orden recomendado de publicación

```powershell
trm-model validate
trm-model run-monthly
python .\src\build_charts.py
python .\src\sync_workbook_openpyxl.py
python .\src\check_charts.py
python .\src\check_outputs.py
python .\src\check_reproducibility.py
python -m pytest -q
```

Si un comando falla, conserve el mensaje, el estado del checkout y el manifest `failed` antes de volver a intentar. No publique outputs viejos como si fueran de la corrida fallida.

## Descargas

La estimación normal no descarga fuentes. `trm-archive-vintage` y scripts de adquisición pueden requerir `FRED_API_KEY` u otras condiciones de proveedor; deben ejecutarse por separado y dejar una evidencia de descarga.
