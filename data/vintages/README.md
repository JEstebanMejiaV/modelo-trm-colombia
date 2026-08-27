# Archivo de vintages

`data/catalog/sources.json` es el registro canónico de todas las entradas activas del modelo, incluidos los insumos DANE y la base global mensual curada. El archivo histórico `sources.json` de esta carpeta se conserva sólo como vista de compatibilidad de vintages; los comandos de archivado ya leen el catálogo canónico para evitar divergencias.

## Uso

```powershell
trm-archive-vintage snapshot --origin-date AAAA-MM-DD
```

El comando descarga todas las fuentes activas en `data/vintages/AAAA-MM-DD/files/`. Se niega a sobrescribir una fecha existente. Una carpeta parcial sin `manifest.json` no constituye un snapshot completo.

La referencia inicial se creó con:

```powershell
trm-archive-vintage baseline --origin-date 2026-08-23
```

Ese baseline apunta a las instantáneas `data/raw/` ya versionadas y fija sus huellas, sin duplicar archivos grandes. Las descargas posteriores sí se guardan por separado.

La variante `long_horizon_research.wavelet_optimization.v1` no puede usar un baseline como snapshot PIT. Para incorporar el target histórico se debe aportar un archivo oficial y un JSON de evidencia cuyo `as_of_date` coincida con el origen:

```powershell
trm-archive-vintage import-pit `
  --origin-date AAAA-MM-DD `
  --available-through AAAA-MM-DD `
  --vintage-id banrep-trm-1-AAAA-MM-DD `
  --source-file ruta\al\archivo-oficial.csv `
  --evidence-file ruta\a\evidence.json
```

La evidencia debe declarar `provider`, `source_url` HTTPS, `as_of_date`, `retrieved_utc` y `method`; opcionalmente puede declarar `source_sha256`. El comando copia el archivo a `data/vintages/<origin>/files/`, escribe provenance, verifica bytes/SHA-256 y ejecuta el resolver PIT. Se niega a leer `data/raw`, outputs históricos o sobrescribir una fecha existente. No descarga ni recorta la serie, por lo que una descarga actual del endpoint de BanRep no constituye por sí sola un vintage histórico.

Cuando exista un panel de outcomes auditado dentro del proyecto, se puede pasarlo a la corrida con `--label-panel`; el loader rechaza `data/raw`, datos posteriores al `Data_Cutoff` y meses ausentes, sin imputación. Todos los orígenes usados para entrenamiento y evaluación deben materializarse y declararse explícitamente antes de ejecutar el backtest.

## Históricos recuperados

- `trm-archive-vintage alfred-history` intenta recuperar cada origen mensual de 2022-05 a 2026-04 para `FEDFUNDS`, `DTWEXBGS`, `VIXCLS`, BRL, CLP y MXN. Las respuestas se piden serie por serie porque el paquete multiserie no aplicó correctamente la fecha histórica a todas las columnas. La descarga se reanuda desde `historical/alfred_cache/`, valida que no haya observaciones futuras y solo crea el consolidado cuando las 288 respuestas están completas. En esta actualización el servidor cortó las conexiones individuales: no se versiona un consolidado incompleto ni se cuenta cobertura ALFRED.
- `historical/minhacienda/version_history.json` cataloga las versiones oficiales del balance fiscal GNC publicadas entre octubre de 2025 y junio de 2026. El portal devolvió una página de validación al intentar descargar los binarios, por lo que todavía no se cuentan como vintages recuperados. `trm-archive-vintage fiscal-history` permite reintentar y solo acepta archivos XLSX válidos con SHA-256.
- `historical/banrep_trm_1_current_2026-08-25.json` conserva una descarga actual de la serie TRM `banrep_trm_1`; su provenance está en el sidecar homónimo. Tiene 712.414 bytes, SHA-256 `92b4c8043e42036ee82c6022106e73a291fb92cf0395a039a085f514fbb14269` y llega hasta 2026-08-26. No es un vintage PIT porque la respuesta no contiene evidencia `as-of`, `vintage` ni historial de revisiones; no reemplaza `data/raw` ni el baseline.
- `results/cobertura_vintages_pronostico.csv` muestra qué factores tienen cobertura completa, parcial o ausente para los 48 orígenes del ejercicio.

La recuperación histórica sigue incompleta. Se catalogaron ocho versiones fiscales oficiales, pero el portal bloqueó sus binarios; ALFRED cortó las solicitudes individuales y el paquete multiserie se descartó porque contenía datos posteriores al origen. Las series activas de BanRep y BCRPData tampoco exponen aquí una historia completa de revisiones. Por ello, el resultado vigente conserva la denominación **pseudo-tiempo-real**. Solo podrá convertirse en backtest genuino para un origen cuando todos sus factores tengan el vintage correspondiente.

## Reglas de integridad

- No se reemplaza ni corrige un snapshot fechado; una nueva descarga usa otra fecha.
- `manifest.json` es parte del dato y debe versionarse junto con los archivos que describe.
- El código valida SHA-256 antes de aceptar un vintage histórico.
- La fecha de origen es la fecha de información simulada; `retrieved_utc` es la fecha técnica de descarga.
- Las credenciales nunca se escriben en esta carpeta. El endpoint público de ALFRED usado aquí evita almacenar una clave FRED.

Las condiciones de reutilización siguen siendo las de cada proveedor. En especial, EMBIG se atribuye a “BCRPData; fuentes originales Reuters/J.P. Morgan” y no se presenta como una serie con licencia Creative Commons.
