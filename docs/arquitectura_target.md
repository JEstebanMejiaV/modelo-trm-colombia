# Arquitectura target del modelo TRM Colombia

> Documento de decisión y destino de migración. Para el estado ejecutable actual consulte [`desarrollo/arquitectura_actual.md`](desarrollo/arquitectura_actual.md); para la entrada documental consulte [`README.md`](README.md).

**Estado:** objetivo de migración, con implementación incremental; no describe cumplimiento completo
**Última revisión:** 2026-08-23
**Alcance:** producto mensual de explicación y pronóstico, productos diarios de apoyo, investigación de largo plazo, provenance y vintages point-in-time.

## 1. Propósito y límites

La arquitectura target separa el dominio econométrico, la preparación de datos, los contratos de producto y la operación de las corridas. Debe conservar la econometría mensual validada en `f592c15`, los outputs heredados y los entry points legacy mientras se invierte gradualmente la dependencia hacia `trm_model`.

El producto mensual es el único producto que puede considerarse primario en este momento. `daily_direction` y `daily_volatility` son productos de apoyo. `long_horizon_research` es investigación y no puede promocionarse automáticamente a producto de pronóstico.

El forecast mensual conserva la etiqueta **pseudo-tiempo-real** mientras no exista un snapshot point-in-time completo para todos los factores de la especificación. No se permite imputar, interpolar, hacer `ffill` ilimitado ni sustituir silenciosamente una observación faltante para obtener cobertura PIT.

## 2. Capas target

```text
interfaces / CLI / entry points
            |
      orchestration
            |
 products + contracts + provenance
            |
 monthly domain: specs -> features -> estimation -> result objects
            |
 data access: registry -> snapshots/vintages -> curated frames
            |
 storage: data/raw, data/vintages, results, artifacts/runs
```

### 2.1 `trm_model.data`

Responsabilidades:

- Resolver la raíz del proyecto y rutas mediante `ProjectPaths`.
- Leer el registro canónico de fuentes.
- Cargar snapshots raw o snapshots PIT fechados.
- Validar existencia, SHA-256, cobertura temporal, frecuencia y fecha de publicación.
- Rechazar fuentes faltantes en lugar de rellenarlas artificialmente.
- Exponer frames curados y trazables al dominio mensual.

No debe contener selección de modelos, escritura de README ni lógica de presentación.

### 2.2 `trm_model.monthly`

Responsabilidades target:

- Mantener las especificaciones de factores y sus rezagos.
- Construir el dataset mensual y sus transformaciones.
- Ejecutar la estimación mensual y devolver objetos de resultados.
- Separar cálculo econométrico de escritura de CSV, workbook, README y metadata.
- Consumir `information_set`, `origin_date` y `vintage_policy` explícitos.

Los módulos en `src/model` pueden permanecer temporalmente como reexportes de compatibilidad. La dependencia final debe ir de `model` hacia `trm_model.monthly`, no de `trm_model.monthly` hacia `model` para loader, specs o transformaciones.

La separación post-estimación queda explícita:

- `trm_model.monthly.estimation` ajusta modelos, explora rezagos y selecciona especificaciones por BIC.
- `trm_model.monthly.inference` recibe resultados ya ajustados y calcula covarianzas HAC, errores estándar, intervalos, pruebas de integración, bounds y diagnósticos.
- La validación predictiva y las contribuciones permanecen en su capa de validación; no se confunden con evidencia inferencial sobre parámetros.
- `src/model/estimation.py` conserva la fachada histórica y reexporta ambos módulos, sin mantener una segunda implementación.

### 2.3 `trm_model.products`

Cada producto debe declarar:

- `product_id`, frecuencia, horizonte y benchmark;
- información disponible y política de vintages;
- especificaciones consumidas;
- ownership de outputs;
- estado: `primary`, `supporting` o `research`;
- runner y política de errores.

Los manifests son contratos. No sustituyen un runner: el runner debe consumirlos y producir resultados compatibles con ellos.

### 2.4 `trm_model.provenance`

Toda corrida debe producir un manifest con:

- identificador reproducible de corrida;
- commit y estado Git;
- configuración y hashes de contratos;
- árbol de código;
- inputs efectivos y hashes;
- outputs efectivamente producidos y hashes;
- ambiente Python y paquetes;
- producto, información disponible, origen temporal y política de vintage;
- warnings, error y estado final;
- ownership por producto sin duplicidades.

`results/` conserva los outputs de compatibilidad. `artifacts/runs/<run_id>/manifest.json` es la fuente de provenance de la corrida.

### 2.5 `interfaces`

La CLI target debe ofrecer al menos:

```text
trm-model validate
trm-model run-monthly
trm-model run-daily-direction
trm-model run-daily-volatility
trm-model run-research --module <nombre>
trm-model vintage-status
```

Los entry points legacy (`estimate_model.py`, wrappers de `pipelines/` y scripts históricos) deben seguir funcionando, pero delegando en la implementación target.

## 3. Dirección de dependencias

### Permitido

- `interfaces` -> `orchestration` -> `products`/`monthly`/`data`/`provenance`.
- `monthly` -> `data` y utilidades econométricas compartidas.
- `products` -> contratos y runners.
- `provenance` -> `paths`, hashes y ambiente.
- `model` legacy -> `trm_model` durante la transición.

### Prohibido en la arquitectura final

- `trm_model` importando `estimate_model` para ejecutar el core.
- `trm_model.data` importando scripts de presentación.
- Specs ejecutables duplicadas entre TOML, `model.config` y código.
- Runners que descubran o sobrescriban outputs fuera de su contrato.
- Una corrida PIT que lea `data/raw` como fallback cuando existe un origen fechado.
- Rellenar faltantes para convertir un snapshot incompleto en un backtest.
- Presentar resultados `latest_available` como backtest genuino.

## 4. Estado de productos

| Producto | Estado target | Situación actual | Criterio de promoción |
|---|---|---|---|
| `monthly_explanation` | `primary` | Operativo; outputs y ownership mensuales definidos | Core target sin dependencia inversa de legacy y paridad demostrada |
| `monthly_forecast` | `primary`, pseudo-tiempo-real | Operativo con rezagos conservadores | Vintages PIT completos por factor y backtest por origen |
| `robustness` | `primary/supporting` | Operativo dentro del bundle mensual | Runner y provenance común, o permanencia explícita dentro de `monthly_bundle` |
| `daily_direction` | `supporting` | Wrapper de `forecast_daily` | Runner/provenance propios y política temporal documentada |
| `daily_volatility` | `supporting` | Wrapper de `volatility_model` | Runner/provenance propios y política de `ffill` explícita |
| `long_horizon_research` | `research` | Módulos exploratorios independientes | OOS point-in-time, benchmark, estabilidad y revisión de promoción |

## 5. Política de información y vintages

### 5.1 Modos admitidos

- `latest_available`: usa la última versión disponible de cada fuente; puede servir para operación/pseudo-tiempo-real, pero no es un backtest histórico genuino.
- `vintage_backtest`: exige `origin_date`, manifest de snapshot válido, archivos exactos del snapshot, hashes coincidentes y cobertura de todos los factores. No permite fallback a raw ni imputación.
- `baseline`: fija el estado raw versionado en una fecha; no equivale a una historia de revisiones.

### 5.2 Requisitos de un snapshot PIT

Cada carpeta `data/vintages/<origin_date>/` debe contener:

1. `manifest.json` validado contra schema;
2. todos los archivos efectivos del conjunto de información de la fecha;
3. SHA-256 y tamaño de cada archivo;
4. proveedor, URL o referencia de descarga, fecha de recuperación y fecha de origen;
5. cobertura suficiente para los factores solicitados;
6. ausencia de observaciones posteriores a la fecha de origen;
7. política explícita para series que no publican revisiones históricas.

El estado debe distinguir `complete`, `partial`, `unavailable` y `invalid`. Un snapshot parcial no puede alimentar un backtest genuino.

### 5.3 Cobertura actual conocida

La cobertura vigente de `results/pronostico/cobertura_vintages_pronostico.csv` solo marca completas las series FRED de dólar amplio, VIX y el factor de tres monedas BRL/CLP/MXN. El conjunto de 14 factores no está completo; por eso `metadata.json` debe mantener `backtest_genuino_disponible=false`.

La recuperación de BanRep, BCRPData, MinHacienda, DANE, BEI y la base global requiere snapshots históricos reales. Si un proveedor no publica vintages, debe declararse la limitación; no se debe reconstruir una revisión histórica como si fuera observada.

## 6. Criterios de salida de la migración

La migración target se considera cerrada únicamente cuando se cumplen todos los criterios aplicables:

### A. Arquitectura y dependencias

- [ ] Existe este documento y cada excepción legacy está registrada.
- [ ] `trm_model.monthly` contiene el loader, specs y transformaciones canónicas.
- [ ] `src/estimate_model.py` solo reexporta y delega en el core target.
- [ ] `trm_model` no importa `estimate_model` para ejecutar la estimación.
- [ ] `src/model` funciona como compatibilidad y no como fuente duplicada.
- [ ] No hay factor specs ejecutables duplicadas sin validación de igualdad.

### B. Paridad econométrica

- [ ] La muestra, número de observaciones, selección de rezagos, coeficientes y métricas coinciden con la baseline tolerada.
- [ ] Los 45 outputs mensuales se producen con los mismos nombres y ownership.
- [ ] No cambian las reglas de faltantes: se falla explícitamente ante cobertura insuficiente.
- [ ] El README, metadata y workbook se generan desde objetos de resultados, sin alterar el cálculo.

### C. Runners y provenance

- [ ] Existe un runner común para mensual, diario, volatilidad y research.
- [ ] Cada runner escribe `running`, `success` o `failed` de forma atómica y registra el error.
- [ ] Cada output declarado se reconcilia con el manifest de la corrida.
- [ ] Las corridas diarias y de research no se presentan como producto primario por accidente.
- [ ] La CLI valida contratos antes de ejecutar y no deja outputs fuera de ownership.

### D. Vintages y forecast

- [ ] Cada corrida `vintage_backtest` usa exclusivamente el snapshot de su `origin_date`.
- [ ] Todos los factores de la especificación tienen cobertura completa o el origen se marca no apto.
- [ ] No existe imputación artificial, fallback silencioso ni observación futura.
- [ ] El forecast sigue rotulado pseudo-tiempo-real hasta cumplir el punto anterior.
- [ ] Los resultados reportan cobertura por origen y por factor.

### E. Calidad y operación

- [ ] Tests de contrato, temporalidad, paridad y runner pasan en CI.
- [ ] El wheel o el modo checkout-bound están documentados y verificados con un entorno limpio.
- [ ] Las fuentes tienen controles de frescura, cobertura y schema.
- [ ] Los artifacts tienen índice, retención y mecanismo de comparación entre corridas si se habilita operación periódica.

## 7. Secuencia de migración

1. Centralizar specs, loader y transformaciones en `trm_model.monthly`.
2. Mover el core mensual y dejar `estimate_model.py` como wrapper.
3. Ejecutar paridad contra la baseline y congelar los contratos de outputs.
4. Generalizar el runner/provenance para productos de apoyo e investigación.
5. Añadir validación estricta de snapshots y el comando `vintage-status`.
6. Recuperar vintages reales por proveedor, sin imputación.
7. Habilitar el backtest genuino solo para orígenes con cobertura completa.
8. Promover research únicamente después de revisión OOS y de información disponible.

## 8. Decisión explícita sobre datos faltantes

La ausencia de una serie histórica o de un vintage no se resuelve creando valores sintéticos. La corrida debe fallar o excluir el origen y registrar la razón. En particular, high-yield, TED, desempleo estadounidense alternativo, otros horizontes de inflación, condiciones financieras adicionales, logística y China solo pueden entrar como factores productivos cuando tengan cobertura, fecha de publicación y política PIT verificables.
