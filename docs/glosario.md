# Glosario

| Término | Significado en este repositorio |
|---|---|
| `COP/USD` | Pesos colombianos por dólar; un aumento es depreciación del COP. |
| `Δ` / `D.` | Primera diferencia mensual. |
| `.L0` | Término contemporáneo. |
| `.L1`, `.L2`, `.L3` | Rezago de uno, dos o tres meses. |
| `ex_post` | Usa realizaciones contemporáneas; sirve para explicación histórica/nowcast. |
| `pseudo_real_time` | Respeta rezagos de publicación, pero puede usar la última revisión disponible. |
| `vintage_backtest` | Evaluación que exige snapshots PIT fechados y completos. |
| `latest_available` | Última versión disponible de una fuente. |
| `baseline` | Estado raw versionado en una fecha; no equivale a historia de revisiones. |
| PIT | *Point-in-time*: información disponible en una fecha de origen concreta. |
| Shapley/LMG | Descomposición del R² incremental por aportes marginales promedio; no causal. |
| HAC | Error estándar robusto a heterocedasticidad y autocorrelación bajo una ventana declarada. |
| BIC | Criterio usado para comparar especificaciones y rezagos. |
| MAPE | Error porcentual absoluto medio. |
| R² OOS | R² fuera de muestra; siempre requiere declarar ventana y benchmark. |
| ECM | Modelo de corrección de errores; aquí se reporta como contraste exploratorio. |
| Ownership | Producto responsable de un output, sin duplicidad. |
| Manifest de producto | Contrato declarativo de configuración, outputs y caveats. |
| Manifest de corrida | Registro efectivo de inputs, outputs, hashes, estado y ambiente. |
| Output de compatibilidad | Archivo heredado que se conserva bajo `results/` aunque el runner target tenga otra organización. |
