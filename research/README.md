# Investigación separada

Los módulos de `src/forecast_longterm/` y `src/exploration/` son investigación exploratoria, no componentes del producto mensual primario. Su contrato está en [`manifests/long_horizon_research.json`](manifests/long_horizon_research.json).

Antes de presentar una señal como backtest genuino debe reconstruirse cada filtro, probabilidad, wavelet y variable auxiliar dentro de la información disponible en cada fecha de origen. La regresión expansiva posterior no corrige por sí sola un filtro calculado sobre toda la muestra.
