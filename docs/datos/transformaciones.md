# Transformaciones y calendario de disponibilidad

## Convenciones

- La fecha mensual se representa por el primer día del mes.
- `ln(x)` es logaritmo natural para valores positivos.
- `D.x` es la primera diferencia mensual.
- `asinh(x)` conserva signo y permite ceros en flujos.
- `.Lk` indica el rezago mensual `k`.
- `pp` son puntos porcentuales y `pb` puntos básicos.

## Agregación diaria

Las series diarias se convierten en promedios aritméticos mensuales usando únicamente observaciones publicadas. Para el diferencial BEI se construye la especificación activa con promedios separados de TES nominal, TES UVR y `BKEVEN05`; también se calcula una variante sobre fechas comunes como robustez.

El promedio mensual de una serie contemporánea puede ser válido para explicación histórica y, al mismo tiempo, inválido como input disponible al inicio del mes. La transformación matemática no resuelve el problema temporal.

## Factores principales

| Factor | Construcción | Uso histórico | Uso de forecast |
|---|---|---|---|
| TRM | `ln(TRM)` y `D.ln(TRM)` | Dependiente | Dependiente |
| Remesas | suma móvil de 12 meses y log | rezago | calendario conservador |
| Fiscal | balance móvil de 12 meses / PIB implícito | rezago | rezago más largo |
| Comercio/capitales | `asinh(flujo/1000)` y diferencia | rezago | calendario conservador |
| BEI | TES nominal − TES UVR − BEI EE. UU. | diferencia, rezago | diferencia con disponibilidad |
| Regional | media de `z(D.ln(moneda))` | 3/4 monedas, contemporáneo | composición seleccionada y rezagada |
| ISE/IPC | log y primera diferencia | contemporáneo en explicación | `L2` según especificación |
| Global | diferencias de rendimientos/índices y log-diferencias | bloque contemporáneo | mercados `L1`, actividad/empleo/logística `L2` |

La lista ejecutable de términos está en [`src/trm_model/monthly/specifications.py`](../../src/trm_model/monthly/specifications.py); la descripción de unidades y fuentes está en [`data/README.md`](../../data/README.md).

## Disponibilidad

El archivo [`results/pronostico/calendario_disponibilidad_pronostico.csv`](../../results/pronostico/calendario_disponibilidad_pronostico.csv) es la referencia de rezagos del forecast. No sustituirlo por una tabla escrita manualmente si cambia el código.

## Faltantes

Los faltantes se mantienen como `NaN`/vacíos en las capas de datos. El modelo balanceado exige cobertura completa de las variables activas y falla con un diagnóstico de meses faltantes. Un candidato incompleto puede documentarse y excluirse; no se puede completar mediante cero, interpolación o `ffill` ilimitado.

## Peligros de interpretación

- `D.ln_dolar_amplio.L0`, `D.ln_vix.L0` y términos similares son contemporáneos, no señales ex ante.
- Un rezago de un mes en la serie de referencia no garantiza que el valor estuviera publicado en una fecha específica si el proveedor tiene revisiones.
- Un promedio mensual mezcla días con distintas fechas de publicación.
- La estandarización regional fija escala estadística; no equivale a una depreciación porcentual directa.
