# Changelog

Todos los cambios relevantes del proyecto están documentados aquí. El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [Unreleased]

### Pendiente de merge

- PR #15: Modelo combinado (interacciones + asimetría + outliers) → R² 66%, ARCH resuelto.

---

## [0.8.0] — 2026-08-23

### Añadido

- **Vintages ALFRED completos** (PR #11): 288/288 requests exitosas via API FRED. Cobertura sube a 3/12 factores aptos para backtest genuino.
- **Test Diebold-Mariano** (PR #11): DM stat = -1.26, p = 0.21. No se rechaza igualdad de capacidad predictiva entre pronóstico y caminata aleatoria.
- **Modelos parsimoniosos** (PR #11): top-3 factores tiene mejor BIC (-947.6) y MAPE (2.57%) que los 12 completos.
- **Pronóstico parsimonioso activo** (PR #12): top-3 Shapley (monedas, dólar, EMBIG) como especificación evaluada.
- **Backtest genuino parcial** (PR #12): compara vintages reales vs último. VIX revisiones de hasta 27.5%; dólar amplio estable (0.18%).
- **GARCH(1,1)** (PR #12): persistencia 0.94, volatilidad incondicional 2.12%/mes. Confirma clusters de volatilidad.
- **Forecast combination** (PR #12): 50/50 e inversa-MSE mejoran sobre pronóstico puro pero no superan la caminata.
- **Rolling window 120 meses** (PR #13): 10/14 coeficientes inestables entre mitades. Importancia relativa estable, coeficientes individuales no.
- **Pronóstico multihorizonte** (PR #13): R² negativo vs caminata en h=1,2,3,6. TRM imprevisible a cualquier horizonte.
- **Threshold regression** (PR #13): sin no-linealidades significativas (VIX p=0.074, dólar p=0.437, EMBIG p=0.490).
- **Variables candidatas** (commit directo): MICH, NFCI, T10Y2Y, STLFSI evaluadas. Ninguna aporta al pronóstico.
- **PDL dólar amplio**: efecto casi todo contemporáneo, rezagos 1-3 no aportan.
- **Intervención cambiaria BanRep**: coef = 0.00006, p = 0.77 — no significativa.
- **Estimación robusta** (Huber-T, LAD): 35 outliers identificados. OLS con HAC es razonable; los outliers no sesgan los resultados.
- **Mejoras al modelo de explicación** (PR #15): interacciones dólar×VIX, EMBIG×regional; asimetría del dólar; dummies de outliers.

### Cambiado

- **Migración del pipeline** (PR #14): `estimate_model.py` reducido de 2,901 a 1,319 líneas importando del paquete `src/model/`.
- **Organización de results/** (PR #10): 38 CSVs movidos a `explicacion/`, `pronostico/` y `robustez/`.
- **Auto-actualización del README** (commit dfc0142): 7 bloques numéricos se regeneran automáticamente al correr `estimate_model.py`.
- Documentación completa actualizada (READMEs de `src/`, `results/` y raíz).

---

## [0.7.0] — 2026-08-23

### Añadido

- **Robustez del diferencial BEI** (PR #7): ADF, KPSS, Zivot-Andrews; comparación de agregación (medias separadas vs fechas comunes); tendencias y quiebres; 6 especificaciones comparadas.
- **Paquete modular `src/model/`** (PR #9): 9 módulos (config, loaders, transforms, estimation, validation, shapley, bei, readme_sync, `__init__`).
- **Separación explicación/pronóstico** (PR #8): `estimate_explanation()` y `estimate_forecast()` como funciones wrapper.

### Cambiado

- Archivos de validación renombrados: `validacion_metricas.csv` → `validacion_metricas_modelo_principal.csv` (consistencia de naming).
- `build_charts.py`, `build_workbook.mjs`, `check_outputs.py` actualizados con nuevas rutas.

### Corregido

- Referencia residual a `validacion_predicciones.csv` en `build_charts.py` línea 874 (fix CI).

---

## [0.6.0] — 2026-08-23

### Añadido

- **Vintages y Shapley** (PR #6): `archive_vintage.py` para snapshots inmutables. Bootstrap por bloques de 12 meses (200 réplicas × 64 permutaciones). Estabilidad por submuestras en 5 cortes.
- **Cobertura de vintages**: manifiesto y CSV de cobertura por factor.

---

## [0.5.0] — 2026-08-23

### Añadido

- **Proxies regionales y pronóstico** (PR #5): Factor de 4 monedas (BRL, CLP, MXN, PEN). Comparación 3 vs 4 monedas. Modelo de pronóstico con rezagos de publicación.
- Calendario de disponibilidad de cada factor.
- Validación pseudo-tiempo-real de 48 meses.

---

## [0.4.0] — 2026-08-22

### Añadido

- **Gráficos explicativos** (PR #4): 5 PNGs independientes con `build_charts.py`. Verificación SHA-256 con `check_charts.py`. Elasticidades y ajuste del ECM.

---

## [0.3.0] — 2026-08-22

### Corregido

- **Documentación y estacionariedad** (PR #3): notas metodológicas, corrección de flujos no estacionarios.

---

## [0.2.0] — 2026-08-22

### Añadido

- **Modelo ampliado y pesos explicativos** (PR #2): 12 factores, descomposición Shapley/LMG exacta del R², archivo Excel de 14 hojas.

---

## [0.1.0] — 2026-08-22

### Añadido

- **Modelo econométrico inicial** (PR #1): especificación en primeras diferencias con 6 factores + pandemia. Errores HAC. Validación condicional. ECM exploratorio.
- Estructura del proyecto: `data/raw/`, `results/`, `src/`, `deliverables/`, `graficos/`.
- CI con GitHub Actions (`model-check.yml`).
