# Contexto y alcance

## Propósito

El proyecto estudia la TRM promedio mensual de Colombia, medida en COP por USD. Su núcleo econométrico mensual tiene dos usos que deben mantenerse separados:

- **Explicación histórica:** describe asociaciones entre variaciones de la TRM y factores contemporáneos o rezagados.
- **Pronóstico mensual:** intenta predecir el siguiente mes usando un calendario conservador de disponibilidad.

También existen productos diarios de apoyo, volatilidad/VaR e investigación de señales de largo plazo. No son sustitutos del producto mensual.

## Estado actual

| Elemento | Estado documentado |
|---|---|
| Producto mensual | Principal y operativo; conserva outputs heredados y contratos target en transición. |
| Explicación histórica | `ex_post`; puede usar realizaciones contemporáneas y no es evidencia causal. |
| Pronóstico mensual | `pseudo_real_time`; usa rezagos de publicación y el último vintage disponible. |
| Backtest histórico genuino | No disponible para todos los factores. La cobertura conocida es 3/14. |
| Productos diarios | De apoyo; no modifican la econometría mensual. |
| Investigación de largo plazo | Exploratoria; puede contener filtros que no son válidos para operación ex ante. |
| Datos faltantes | Se conservan y pueden impedir una corrida; no se imputan silenciosamente. |

## Qué significa la TRM

La variable es COP/USD. Un aumento representa depreciación del peso colombiano frente al dólar. Las fechas mensuales se guardan normalmente como el primer día del mes (`AAAA-MM-01`) aunque las fuentes originales puedan ser diarias o publicarse con otra convención.

## Qué no afirma el proyecto

- No presenta coeficientes como efectos causales.
- No presenta la explicación contemporánea como pronóstico ex ante.
- No llama backtest genuino a una evaluación que usa el último vintage revisado.
- No convierte una señal estadística en recomendación de inversión.
- No rellena una serie incompleta para aumentar la muestra.

## Contratos importantes

- Registro de fuentes: [`data/catalog/sources.json`](../data/catalog/sources.json).
- Configuración común: [`configs/common.toml`](../configs/common.toml).
- Configuraciones de producto: [`configs/products/`](../configs/products/).
- Schemas: [`schemas/`](../schemas/).
- Ownership de outputs: [`results/output_catalog.json`](../results/output_catalog.json) y [`src/trm_model/output_contract.py`](../src/trm_model/output_contract.py).
- Provenance de corrida: [`artifacts/runs/`](../artifacts/runs/).
