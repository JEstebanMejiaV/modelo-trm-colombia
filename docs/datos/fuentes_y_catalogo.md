# Fuentes y catálogo de datos

## Capas de datos

El proyecto distingue tres niveles:

1. `data/raw/`: descargas o instantáneas de origen; no son la matriz de regresores.
2. Bases mensuales consolidadas: unión de fuentes y variables construidas.
3. Muestra balanceada: columnas necesarias para estimación, con diferencias y rezagos calculados después.

El detalle de series, proveedores, códigos, unidades y atribución se conserva en [`data/README.md`](../../data/README.md). El registro canónico para loaders y validación es [`data/catalog/sources.json`](../../data/catalog/sources.json); sus reglas estructurales están en [`schemas/source_registry.json`](../../schemas/source_registry.json).

## Fuentes activas resumidas

| Bloque | Ejemplos | Transformación principal |
|---|---|---|
| TRM y política | BanRep series 1 y 59 | Promedios mensuales de series diarias |
| Sector externo | términos de intercambio, remesas, reservas, balanza y capitales | niveles, acumulados, log/asinh y diferencias |
| Mercados globales | dólar amplio, VIX, tasas y BEI | promedios, logaritmos y diferencias |
| Riesgo local | EMBIG Colombia BCRPData | promedio mensual y conversión pb a pp |
| Monedas regionales | BRL, CLP, MXN y PEN por USD | cambios logarítmicos estandarizados |
| Economía doméstica | ISE total DANE e IPC Colombia | logaritmo y primera diferencia |
| Bloque global | expectativas, commodities, finanzas, empleo, actividad y logística de EE. UU. | términos agrupados y rezagos de disponibilidad |

## Registro y atribución

Cada fuente debe conservar proveedor, identificador, archivo raw, frecuencia, transformación, disponibilidad y referencia de descarga. Para BanRep, BCRPData, MinHacienda, FRED y Federal Reserve Board se deben conservar las atribuciones y condiciones descritas en `data/README.md`.

La existencia de una URL pública no implica que todos los datos o metodologías tengan licencia libre para redistribución comercial. La documentación técnica no sustituye una revisión jurídica de reutilización.

## Criterios de inclusión

Una variable activa debe tener:

- cobertura suficiente para la muestra que declara el producto;
- transformación reproducible;
- unidad y signo interpretables;
- política de publicación o rezago documentada;
- tratamiento explícito de faltantes;
- trazabilidad a un archivo raw y, cuando corresponda, a un snapshot.

GEIH, IPI, IPP, high-yield, TED, `UNRATE` e indicadores de China se conservan como candidatos auditables cuando no cumplen la cobertura. No deben desaparecer del catálogo ni entrar por imputación.

## Archivos principales

- [`data/modelo_trm_datos_mensuales.csv`](../../data/modelo_trm_datos_mensuales.csv): consolidado mensual.
- [`data/modelo_trm_muestra_estimacion.csv`](../../data/modelo_trm_muestra_estimacion.csv): muestra balanceada previa al diseño final.
- `data/base_global_mensual.csv` y `data/base_global_cobertura.csv`: bloque global y cobertura.
- `data/variables_internas_cobertura.csv`: auditoría de variables internas.
- [`data/vintages/`](../../data/vintages/): snapshots y manifests por origen.

## Regla de consistencia

Si la narrativa y el catálogo discrepan, el catálogo/manifest y el código de carga deben investigarse primero. No se debe corregir una discrepancia editando solo un README.
