# Mecanismo de transmisión de la TRM

## Teoría empírica de la tasa de cambio en Colombia

Este documento presenta el mecanismo de transmisión que emerge del modelo econométrico. La actualización con variables globales FRED conserva la lectura por canales, pero recalcula los pesos: el modelo ampliado tiene 13 factores, R² = 64,84%, R² ajustado = 61,10% y MAPE condicional = 1,62%. El bloque `Variables globales nuevas` agrupa diez términos y recibe 17,33% del peso Shapley; no debe desagregarse como jugadores independientes sin recalcular la descomposición.

## Diagrama de transmisión

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CHOQUES GLOBALES                                  │
│                                                                         │
│  ┌──────────────┐    ┌───────────┐    ┌─────────────────────┐          │
│  │ Dólar amplio │    │    VIX    │    │  Factor regional    │          │
│  │  (Fed/USD)   │    │  (Cboe)   │    │  BRL+CLP+MXN+PEN   │          │
│  └──────┬───────┘    └─────┬─────┘    └──────────┬──────────┘          │
│         │                  │                     │                      │
│         │ +0,24            │ +0,01               │ +0,017              │
│         │ [20,1%]          │ [8,3%]              │ [30,1%]             │
│         │                  │                     │                      │
│         ├──────────────────┼─────────────────────┤                      │
│         │         ρ = 0,35 │          ρ = 0,39   │                      │
│         └─────────┬────────┴─────────────────────┘                      │
│                   │                                                      │
│                   ▼ CANAL GLOBAL (65,9% del peso total)                  │
└───────────────────┼─────────────────────────────────────────────────────┘
                    │
                    │
┌───────────────────┼─────────────────────────────────────────────────────┐
│                   │     RIESGO SOBERANO                                  │
│                   │                                                      │
│         ┌─────────▼──────────┐                                          │
│         │ EMBIG Colombia     │                                          │
│         │ (Reuters/JPMorgan) │                                          │
│         │  +0,017 [18,2%]   │                                          │
│         └─────────┬──────────┘                                          │
│                   │ ρ = 0,60 con dólar                                   │
│                   │ ρ = 0,64 con VIX                                     │
│                   │                                                      │
│                   ▼ CANAL DE RIESGO LOCAL (18,2% del peso)               │
└───────────────────┼─────────────────────────────────────────────────────┘
                    │
                    │
┌───────────────────┼─────────────────────────────────────────────────────┐
│                   │     SECTOR EXTERNO COLOMBIA                          │
│                   │                                                      │
│  ┌────────────────┼────────────────────────────────────────────┐        │
│  │                │                                            │        │
│  ▼                ▼                    ▼                  ▼    │        │
│ ┌──────────┐ ┌──────────┐ ┌───────────────┐ ┌──────────────┐ │        │
│ │Términos  │ │Balanza   │ │Flujos de      │ │Reservas      │ │        │
│ │intercamb.│ │comercial │ │capital        │ │internac.     │ │        │
│ │ -0,09    │ │ +0,047   │ │ +0,001        │ │ -0,29        │ │        │
│ │ [6,7%]   │ │ [7,4%]   │ │ [4,2%]        │ │ [2,6%]       │ │        │
│ └──────────┘ └──────────┘ └───────────────┘ └──────────────┘ │        │
│                                                                │        │
│           CANAL EXTERNO COLOMBIA (21,0% del peso)              │        │
└────────────────────────────────────────────────────────────────┼────────┘
                                                                 │
                                                                 │
┌────────────────────────────────────────────────────────────────┼────────┐
│                   POLÍTICA DOMÉSTICA                            │        │
│                                                                │        │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐ │        │
│  │Diferencial   │  │Déficit       │  │Diferencial BEI      │ │        │
│  │de tasas      │  │fiscal        │  │5 años Col-EEUU      │ │        │
│  │ -0,005       │  │ -0,001       │  │ -0,006              │ │        │
│  │ [0,4%]       │  │ [0,1%]       │  │ [0,6%]              │ │        │
│  └──────────────┘  └──────────────┘  └─────────────────────┘ │        │
│                                                                │        │
│           CANAL DE POLÍTICA (1,1% del peso)                    │        │
└────────────────────────────────────────────────────────────────┼────────┘
                                                                 │
                    ┌────────────────────────────────────────────┘
                    │
                    ▼
          ┌─────────────────┐
          │                 │
          │   Δ ln(TRM)     │
          │   COP por USD   │
          │                 │
          │  R² = 64,84%    │
          │  MAPE = 1,62%   │
          │                 │
          └─────────────────┘
```

## Interpretación cuantitativa por canal

### Canal global (65,9% del poder explicativo)

| Componente | Peso Shapley | Coeficiente | Lectura |
|---|---|---|---|
| Factor regional (BRL+CLP+MXN+PEN) | 30,1% | +0,017 | Un z-score de presión regional se asocia con +1,7% en TRM |
| Dólar amplio (DTWEXBGS) | 20,1% | +0,241 | Un +1% del USD global se asocia con +0,24% en TRM |
| VIX | 6,71% | +0,019 | Un cambio del VIX se asocia con depreciación, con incertidumbre HAC |
| Variables globales nuevas (10 términos) | 17,33% | Bloque agrupado | Se compone de tasas, commodities, incertidumbre, estrés financiero y actividad de EE. UU.; sus términos se describen en `data/README.md` |

Estos tres factores comparten ~40% de su variación (ρ dólar-VIX = 0,35; ρ dólar-regional = 0,39; ρ VIX-regional = 0,39). Son manifestaciones del mismo fenómeno: **risk-on/risk-off global**. Cuando el apetito por riesgo cae, el dólar se fortalece, el VIX sube y las monedas emergentes se deprecian simultáneamente.

**Implicación**: la TRM colombiana es primordialmente un activo de riesgo global. Casi el 60% de su variación mensual responde a fuerzas sobre las que la política económica local tiene poco control inmediato.

### Canal de riesgo soberano (18,2%)

| Componente | Peso Shapley | Coeficiente | Lectura |
|---|---|---|---|
| EMBIG Colombia | 18,2% | +0,017 | Un +1 pp de spread se asocia con +1,7% en TRM |

El EMBIG está altamente correlacionado con el dólar (ρ = 0,60) y el VIX (ρ = 0,64), pero Shapley le asigna su propio 18% porque contiene información idiosincrática de Colombia no capturada por los factores globales puros.

**Implicación**: el mercado de deuda externa colombiana aporta una señal propia sobre la percepción de riesgo-país. Deterioros crediticios (o mejoras) tienen un canal independiente hacia la TRM.

### Canal externo Colombia (21,0%)

| Componente | Peso Shapley | Coeficiente | Lectura |
|---|---|---|---|
| Balanza comercial cambiaria | 7,4% | +0,047 | Asinh del flujo; signo contraintuitivo |
| Términos de intercambio | 6,7% | -0,092 | Un +10% se asocia con -0,9% en TRM |
| Flujos netos de capital | 4,2% | +0,001 | Coeficiente casi nulo |
| Reservas internacionales | 2,6% | -0,294 | Un +10% se asocia con -2,9% en TRM |

Los términos de intercambio (dominados por petróleo y carbón) deprecian el COP cuando caen: una mejora de 10% aprecia la TRM en 0,9%. Las reservas tienen el mayor coeficiente individual (-0,29), pero su peso Shapley es bajo (2,6%) porque varían poco y comparten señal con otros factores.

**Implicación**: la cuenta corriente y la posición externa importan, pero menos que los factores globales. Colombia no tiene el "petro-peso" que se le atribuye — los términos de intercambio solo pesan 6,7%.

### Canal de política doméstica (1,1%)

| Componente | Peso Shapley | Coeficiente | Lectura |
|---|---|---|---|
| Diferencial BEI 5 años | 0,6% | -0,006 | Marginal |
| Diferencial de tasas | 0,4% | -0,005 | Marginal |
| Déficit fiscal | 0,1% | -0,001 | Irrelevante |

**Implicación**: la política monetaria (tasas), fiscal (déficit) y las expectativas de inflación (BEI) explican en conjunto apenas el 1,1% de la variación mensual de la TRM. Esto no significa que no importen en horizontes más largos, pero su efecto mensual es absorbido por las demás variables.

## Síntesis: Teoría de la TRM colombiana

```
La TRM colombiana se comporta como un activo de riesgo global
con un componente idiosincrático de spread soberano.

   66% = Canal global ampliado (dólar + VIX + monedas EM + variables globales nuevas)
   15% = Riesgo-país Colombia (EMBIG)
   17% = Sector externo (TI, balanza, capitales, reservas, remesas)
    2% = Política doméstica (tasas, fiscal, inflación)
   ────
   100% = R² incremental de los 13 factores
```

### Proposiciones derivadas

1. **La TRM no es un "petro-peso"**: los términos de intercambio (proxy del petróleo) pesan solo 6,7%. El canal dominante es global, no de commodities.

2. **La política monetaria no mueve la TRM en el corto plazo**: el diferencial de tasas pesa 0,4%. BanRep influye más vía EMBIG (credibilidad → spread → TRM) que vía carry trade directo.

3. **Las intervenciones cambiarias son irrelevantes**: el coeficiente es cero (p = 0,77). BanRep interviene REACTIVAMENTE, no preventivamente.

4. **El contagio regional domina**: cuando Brasil, Chile y México se deprecian, Colombia lo hace más intensamente (factor regional = 30%). Es el mayor predictor individual.

5. **La TRM es imprevisible a un mes**: ninguna combinación de estos factores rezagados supera la caminata aleatoria. La explicación funciona porque usa info contemporánea, pero los coeficientes son inestables en el tiempo.

6. **La volatilidad viene en clusters**: GARCH muestra persistencia de 0,94. Un mes volátil predice otro mes volátil, pero no la dirección.

## Limitación fundamental

Este modelo describe **asociaciones estadísticas**, no mecanismos causales. La correlación dólar→TRM no implica que comprar dólares cause depreciación del COP; ambas pueden responder al mismo shock global subyacente. La descomposición Shapley distribuye la variación explicada, pero no identifica quién causa qué.

Para causalidad se necesitarían choques exógenos (sorpresas de política, eventos geopolíticos) o instrumentos válidos — no observaciones mensuales de equilibrio.
