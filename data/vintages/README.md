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

## Históricos recuperados

- `trm-archive-vintage alfred-history` intenta recuperar cada origen mensual de 2022-05 a 2026-04 para `FEDFUNDS`, `DTWEXBGS`, `VIXCLS`, BRL, CLP y MXN. Las respuestas se piden serie por serie porque el paquete multiserie no aplicó correctamente la fecha histórica a todas las columnas. La descarga se reanuda desde `historical/alfred_cache/`, valida que no haya observaciones futuras y solo crea el consolidado cuando las 288 respuestas están completas. En esta actualización el servidor cortó las conexiones individuales: no se versiona un consolidado incompleto ni se cuenta cobertura ALFRED.
- `historical/minhacienda/version_history.json` cataloga las versiones oficiales del balance fiscal GNC publicadas entre octubre de 2025 y junio de 2026. El portal devolvió una página de validación al intentar descargar los binarios, por lo que todavía no se cuentan como vintages recuperados. `trm-archive-vintage fiscal-history` permite reintentar y solo acepta archivos XLSX válidos con SHA-256.
- `results/cobertura_vintages_pronostico.csv` muestra qué factores tienen cobertura completa, parcial o ausente para los 48 orígenes del ejercicio.

La recuperación histórica sigue incompleta. Se catalogaron ocho versiones fiscales oficiales, pero el portal bloqueó sus binarios; ALFRED cortó las solicitudes individuales y el paquete multiserie se descartó porque contenía datos posteriores al origen. Las series activas de BanRep y BCRPData tampoco exponen aquí una historia completa de revisiones. Por ello, el resultado vigente conserva la denominación **pseudo-tiempo-real**. Solo podrá convertirse en backtest genuino para un origen cuando todos sus factores tengan el vintage correspondiente.

## Reglas de integridad

- No se reemplaza ni corrige un snapshot fechado; una nueva descarga usa otra fecha.
- `manifest.json` es parte del dato y debe versionarse junto con los archivos que describe.
- El código valida SHA-256 antes de aceptar un vintage histórico.
- La fecha de origen es la fecha de información simulada; `retrieved_utc` es la fecha técnica de descarga.
- Las credenciales nunca se escriben en esta carpeta. El endpoint público de ALFRED usado aquí evita almacenar una clave FRED.

Las condiciones de reutilización siguen siendo las de cada proveedor. En especial, EMBIG se atribuye a “BCRPData; fuentes originales Reuters/J.P. Morgan” y no se presenta como una serie con licencia Creative Commons.
