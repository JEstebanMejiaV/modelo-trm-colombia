# Vintages point-in-time

## Políticas admitidas

| Política | Uso | ¿Backtest genuino? |
|---|---|---|
| `latest_available` | Última revisión disponible; operación o pseudo-tiempo-real | No |
| `baseline` | Raw versionado en una fecha de corte | No equivale a revisiones históricas |
| `vintage_backtest` | Snapshot de un `origin_date` con todos los inputs efectivos | Sí, solo si está completo y validado |

## Qué exige un vintage elegible

Un origen `vintage_backtest` debe tener:

1. `data/vintages/<origin_date>/manifest.json` válido contra `schemas/vintage_manifest.json`;
2. todos los archivos efectivos del conjunto de información;
3. hashes y tamaños verificables;
4. cobertura suficiente de cada factor;
5. ausencia de observaciones posteriores al origen;
6. política explícita para fuentes sin historia de revisiones;
7. manifest de corrida que registre `origin_date`, `snapshot_manifest` y `snapshot_only`.

El runner común rechaza una corrida PIT sin origen o manifest explícitos, valida el snapshot y no permite declarar imputación artificial.

## Estado vigente

El baseline [`data/vintages/2026-08-23/manifest.json`](../../data/vintages/2026-08-23/manifest.json) describe referencias inmutables al raw versionado para esa fecha. Es útil para reproducibilidad de un corte, pero no representa una secuencia de revisiones históricas por origen.

La cobertura de forecast en [`results/pronostico/cobertura_vintages_pronostico.csv`](../../results/pronostico/cobertura_vintages_pronostico.csv) y [`results/metadata.json`](../../results/metadata.json) indica:

- factores completos: 3 de 14;
- orígenes ALFRED recuperados: 0 en el corte documentado;
- `backtest_genuino_disponible`: `false`.

Por tanto, el forecast mensual debe permanecer rotulado pseudo-tiempo-real.

## Qué no hacer

- No usar `data/raw` como fallback silencioso cuando se solicita un origen PIT.
- No llenar observaciones faltantes para hacer elegible un origen.
- No interpretar `latest_available` como información histórica disponible entonces.
- No construir una revisión histórica artificial a partir de datos publicados hoy.
- No promover un snapshot parcial a backtest completo.

## Comandos

```powershell
trm-model vintage-status
trm-archive-vintage snapshot --origin-date YYYY-MM-DD
trm-archive-vintage alfred-history
```

Los comandos de archivo pueden requerir credenciales y acceso a proveedores. La recuperación externa debe ejecutarse deliberadamente; una corrida normal no descarga fuentes.
