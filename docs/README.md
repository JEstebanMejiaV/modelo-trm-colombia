# Documentación del modelo TRM Colombia

Esta es la entrada canónica de documentación. El repositorio separa la narrativa explicativa de los contratos ejecutables: la documentación describe el uso y las cautelas; `configs/`, `schemas/`, `src/trm_model/output_contract.py`, manifests y tests determinan el comportamiento verificable.

## Ruta recomendada

1. [`01_contexto_y_alcance.md`](01_contexto_y_alcance.md): propósito, estado actual y límites.
2. [`02_inicio_rapido.md`](02_inicio_rapido.md): instalación y primera validación.
3. [`productos/mensual.md`](productos/mensual.md): explicación histórica y pronóstico mensual.
4. [`productos/diario_direccion.md`](productos/diario_direccion.md) y [`productos/diario_volatilidad.md`](productos/diario_volatilidad.md): productos diarios de apoyo.
5. [`productos/investigacion_largo_plazo.md`](productos/investigacion_largo_plazo.md): señales exploratorias de 6–24 meses.
6. [`operacion/salidas.md`](operacion/salidas.md) y [`operacion/provenance.md`](operacion/provenance.md): outputs y evidencia de las corridas.
7. [`operacion/experimentos.md`](operacion/experimentos.md): variantes, hipótesis, métricas y decisiones.

## Por audiencia

### Quien usa resultados

- [Productos](productos/mensual.md)
- [Interpretación del modelo mensual](metodologia/modelo_mensual.md)
- [Salidas y workbook](operacion/salidas.md)
- [Gráficos](../deliverables/graficos/README.md)

### Quien ejecuta el proyecto

- [Inicio rápido](02_inicio_rapido.md)
- [Comandos operativos](operacion/comandos.md)
- [Reproducibilidad](operacion/reproducibilidad.md)
- [Vintages point-in-time](datos/vintages_point_in_time.md)

### Quien mantiene el código

- [Arquitectura actual](desarrollo/arquitectura_actual.md)
- [Arquitectura objetivo](arquitectura_target.md)
- [Compatibilidad legacy](desarrollo/compatibilidad_legacy.md)
- [Validación y CI](desarrollo/validacion_ci.md)

## Fuente de verdad por tipo de hecho

| Hecho | Fuente de verdad | Evidencia secundaria |
|---|---|---|
| Comportamiento ejecutable | Código y tests | Esta documentación |
| Inputs y transformaciones | `data/catalog/sources.json`, loaders y specs | [`datos/fuentes_y_catalogo.md`](datos/fuentes_y_catalogo.md) |
| Configuración de producto | `configs/products/*.toml` | Páginas de producto |
| Contrato de outputs | `src/trm_model/output_contract.py`, manifests y `schemas/` | [`operacion/salidas.md`](operacion/salidas.md) |
| Output efectivamente producido | `artifacts/runs/<run_id>/manifest.json` | `results/` |
| Estado PIT | `trm-model vintage-status` y cobertura versionada | [`datos/vintages_point_in_time.md`](datos/vintages_point_in_time.md) |
| Métricas actuales | CSV/JSON versionados y checks | README, cuando hay bloques AUTO |
| Decisiones futuras | [`arquitectura_target.md`](arquitectura_target.md) | Documentos de desarrollo |

## Estado que debe permanecer visible

- `monthly_bundle` es el bundle mensual principal; los outputs se distribuyen entre explicación, pronóstico y robustez.
- El contrato ejecutable mensual contiene 45 outputs generados: 27 de `monthly_explanation`, 8 de `monthly_forecast` y 10 de `robustness`.
- El catálogo general incluye outputs de productos diarios e investigación; su lista completa está en [`results/output_catalog.json`](../results/output_catalog.json).
- El forecast mensual es pseudo-tiempo-real hasta completar snapshots históricos por factor.
- El baseline de vintages existente es válido como baseline, pero no habilita un backtest genuino completo.

## Documentos de referencia local

Los README de `data/`, `results/`, `deliverables/`, `deliverables/graficos/` y `src/` conservan detalles técnicos de cada área y enlazan aquí. No son índices alternativos del proyecto.
