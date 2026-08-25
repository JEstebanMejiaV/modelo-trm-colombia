# Compatibilidad legacy

## Interfaces conservadas

| Interfaz | Propósito |
|---|---|
| `python src/estimate_model.py` | Entry point histórico de estimación |
| `trm-monthly` | Wrapper instalable de `pipelines.monthly:run_monthly` |
| `src/model/` | Econometría y APIs históricas durante la migración |
| Rutas bajo `results/` | Compatibilidad con gráficos, workbook y checks |
| Scripts individuales | Exploración y reconstrucción de entregables |

## Regla de transición

La compatibilidad no debe convertirse en una segunda fuente de verdad. Un wrapper puede conservar nombres y firmas históricos, pero la implementación nueva debe delegar en el core target o reexportar una única lógica.

`src/estimate_model.py` ya documenta y ejecuta esa delegación. En cambio, la dependencia interna de `trm_model.monthly` hacia `model` sigue siendo una excepción registrada hasta completar la migración.

## Cambios permitidos

- Añadir adapters explícitos.
- Mantener rutas de output heredadas mientras el catálogo las clasifique.
- Reexportar símbolos con pruebas de paridad.
- Añadir warnings cuando un entry point legacy usa una política temporal distinta.

## Cambios que requieren revisión

- Cambiar nombres o ownership de CSVs.
- Cambiar muestra, transformaciones o rezagos.
- Cambiar el significado de `latest_available`, `baseline` o `vintage_backtest`.
- Hacer que un wrapper escriba outputs fuera de su manifest.
- Eliminar `src/model` antes de demostrar paridad de coeficientes, métricas y outputs.
