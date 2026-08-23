# Gráficos explicativos del modelo de TRM

Esta carpeta presenta cuatro lecturas visuales del modelo fuera del archivo Excel. Cada imagen se reconstruye con `python src/build_charts.py` a partir de los CSV versionados en `results/`; no contiene cifras digitadas manualmente. `metadata.json` registra las huellas de las fuentes y del generador, y `python src/check_charts.py` verifica que los PNG estén sincronizados. Los CSV se normalizan a diez cifras significativas antes de calcular la huella para tolerar diferencias irrelevantes de plataforma sin ocultar cambios visibles en los gráficos.

## 1. Peso explicativo de los factores

![Peso explicativo Shapley](01_pesos_explicativos.png)

Ordena los 12 factores por su participación en el R² incremental asignado mediante Shapley/LMG. Los pesos suman 100% dentro del bloque de factores. No son porcentajes causales del precio del dólar: dependen de la muestra, la especificación y la información compartida entre variables correlacionadas.

## 2. Comparación de desempeño

![Desempeño de los modelos](02_desempeno_modelos.png)

Compara el modelo principal y el ampliado mediante R² ajustado, MAPE, mejora condicional frente a la caminata aleatoria y acierto de dirección. Cada panel indica si un valor mayor o menor es preferible. La validación sigue siendo condicional y pseudo-fuera de muestra.

## 3. TRM observada y comparadores

![TRM observada frente a modelos](03_validacion_trm.png)

Muestra la TRM observada, las estimaciones condicionales principal y ampliada y la caminata aleatoria durante los 48 meses de validación. Sirve para identificar episodios en los que el modelo acompaña o se aleja del movimiento observado; no representa un pronóstico que hubiera estado disponible al inicio de cada mes.

## 4. Dirección y magnitud típica

![Efectos típicos estandarizados](04_efectos_tipicos.png)

Estandariza cada regresor a un movimiento de una desviación estándar para comparar variables con unidades diferentes. Un punto a la derecha se asocia con depreciación del COP y uno a la izquierda, con apreciación. Las líneas son intervalos HAC del 95%; un punto vacío indica que el intervalo cruza cero.

Este gráfico responde una pregunta distinta al peso Shapley. El efecto estandarizado muestra dirección, magnitud parcial e incertidumbre del coeficiente completo; Shapley distribuye la capacidad explicativa, incluida la señal compartida. Por eso un factor puede tener peso visible y un coeficiente impreciso.

## Cautelas comunes

- Los cuatro gráficos describen asociaciones estadísticas, no causalidad.
- Brent, dólar amplio, VIX, spread TES–Treasury y monedas regionales usan información contemporánea realizada.
- Balanza, capitales, reservas, remesas, tasas y déficit pueden responder a la propia TRM.
- La balanza comercial tiene signo estimado positivo, contrario al esperado; esto puede reflejar simultaneidad o composición de los flujos.
- ARCH-LM y Jarque–Bera alertan sobre volatilidad condicional y colas no normales.
