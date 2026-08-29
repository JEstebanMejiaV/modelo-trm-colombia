# Salidas, ownership y entregables

## Tres fuentes que no deben confundirse

1. **Contrato ejecutable:** [`src/trm_model/output_contract.py`](../../src/trm_model/output_contract.py) define los outputs que el runner mensual genera y reconcilia.
2. **Catálogo general:** [`results/output_catalog.json`](../../results/output_catalog.json) clasifica outputs heredados y productos nuevos, incluidos diarios y research.
3. **Manifest efectivo:** `artifacts/runs/<run_id>/manifest.json` dice qué outputs produjo una corrida concreta y con qué hashes.

## Bundle mensual generado

El contrato estático actual exige 45 outputs:

| Ownership | Cantidad | Función |
|---|---:|---|
| `monthly_explanation` | 27 | datos derivados, ficha por factor, contabilidad mensual, coeficientes, ajuste, Shapley y validación histórica |
| `monthly_forecast` | 8 | calendario, selección, coeficientes, diagnósticos y validación del forecast |
| `robustness` | 10 | BEI, ECM, bounds y diagnósticos de robustez |
| **Total** | **45** | bundle mensual |

Los manifests declarativos y el catálogo de compatibilidad pueden incluir más outputs históricos, de investigación o diagnósticos que no se escriben en cada ejecución de `run-monthly`. Esa diferencia es intencional durante la migración, pero debe mantenerse visible y reconciliada.

## Outputs heredados

`results/` conserva rutas esperadas por gráficos, workbook y checks. Que un archivo esté bajo `results/pronostico/` no significa automáticamente que pertenezca a `monthly_forecast`; el ownership se determina por el catálogo y el manifest.

## Entregables

- Workbook: [`deliverables/modelo_trm_colombia.xlsx`](../../deliverables/modelo_trm_colombia.xlsx).
- Explicación del workbook: [`deliverables/README.md`](../../deliverables/README.md).
- Gráficos: [`deliverables/graficos/`](../../deliverables/graficos/).
- Metadatos: [`results/metadata.json`](../../results/metadata.json).

Los gráficos y el workbook deben reconstruirse desde CSV versionados y validarse con sus checks. No se deben editar cifras manualmente dentro del entregable para corregir una discrepancia del pipeline.

## Publicación mínima

Antes de publicar un output registre:

- producto y ownership;
- run ID y commit;
- conjunto de información y política PIT;
- ventana, frecuencia y benchmark;
- fuente CSV/JSON exacta;
- limitaciones y warnings;
- check que lo validó.
