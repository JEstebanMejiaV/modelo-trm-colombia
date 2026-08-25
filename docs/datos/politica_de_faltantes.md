# Política de faltantes

## Regla principal

Un dato faltante es información ausente, no un valor que deba adivinarse. La capa activa conserva el vacío y el pipeline debe fallar o excluir el factor/origen con una razón auditable.

## Prohibiciones

No se permite, sin una decisión metodológica explícita y un contrato actualizado:

- reemplazar por cero;
- interpolar linealmente;
- hacer `ffill` ilimitado;
- extrapolar hacia atrás;
- empalmar índices incompatibles;
- usar `data/raw` para completar un snapshot PIT;
- seleccionar silenciosamente otra muestra para que un candidato entre.

## Consecuencia para el modelo

La muestra balanceada solo incluye variables activas con cobertura completa en el corte que declara. GEIH, IPI, IPP, high-yield, TED, `UNRATE` e indicadores de China pueden permanecer en cobertura/candidatos, pero no entran si no cumplen la regla.

En un backtest PIT, un snapshot parcial se marca `partial`, `unavailable` o `invalid` según corresponda y no se presenta como origen elegible.

## Auditoría

Toda excepción legítima debe declarar:

- variable y proveedor;
- naturaleza del faltante;
- regla aplicada;
- período afectado;
- impacto sobre muestra y producto;
- archivo o manifest que permite reproducirla.

La ausencia de una serie no se resuelve editando únicamente la documentación. Debe reflejarse en catálogo, loader, validación y manifest.
