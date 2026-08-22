import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const ROOT = path.resolve(".");
const OUTPUT_DIR = path.join(ROOT, "outputs", "01a02b58-9c08-7db2-9c7a-783427ec09df");
const PREVIEW_DIR = path.join(OUTPUT_DIR, "previews");
const OUTPUT_XLSX = path.join(OUTPUT_DIR, "modelo_trm_colombia.xlsx");

await fs.mkdir(PREVIEW_DIR, { recursive: true });

function parseCsv(text) {
  text = text.replace(/^\uFEFF/, "");
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = false;
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += ch;
    }
  }
  if (field.length || row.length) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }
  const headers = rows.shift();
  return rows
    .filter((r) => r.some((x) => x !== ""))
    .map((r) => Object.fromEntries(headers.map((h, i) => [h, r[i] ?? ""])));
}

async function readCsv(rel) {
  return parseCsv(await fs.readFile(path.join(ROOT, rel), "utf8"));
}

function n(value) {
  if (value === "" || value === null || value === undefined) return null;
  const out = Number(value);
  return Number.isFinite(out) ? out : null;
}

function pct(value, digits = 1) {
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

const raw = (await readCsv("data/modelo_trm_datos_mensuales.csv"))
  .filter((r) => r.fecha >= "2005-12-01" && r.fecha <= "2026-04-01");
const coefs = await readCsv("results/coeficientes_modelo_principal.csv");
const diagnostics = await readCsv("results/diagnosticos_modelo_principal.csv");
const validationMetrics = await readCsv("results/validacion_metricas.csv");
const validationPredictions = await readCsv("results/validacion_predicciones.csv");
const integration = await readCsv("results/pruebas_integracion.csv");
const adlLags = await readCsv("results/seleccion_rezagos_adl_diferencias.csv");
const bounds = await readCsv("results/bounds_resumen.csv");
const boundsCritical = await readCsv("results/bounds_criticos.csv");
const ecmLong = await readCsv("results/coeficientes_largo_plazo_ecm.csv");
const ecmShort = await readCsv("results/coeficientes_corto_plazo_ecm.csv");
const fit = await readCsv("results/ajuste_historico_modelo_principal.csv");
const metadata = JSON.parse(await fs.readFile(path.join(ROOT, "results/metadata.json"), "utf8"));

const coefByTerm = Object.fromEntries(coefs.map((r) => [r.termino, n(r.coeficiente)]));
const modelMetric = validationMetrics.find((r) => r.modelo.startsWith("ADL"));
const rwMetric = validationMetrics.find((r) => r.modelo.startsWith("Caminata"));

const COLORS = {
  navy: "#17365D",
  blue: "#2F75B5",
  teal: "#0F766E",
  green: "#E2F0D9",
  amber: "#FFF2CC",
  red: "#FCE4D6",
  paleBlue: "#D9EAF7",
  paleGray: "#F2F2F2",
  midGray: "#D9E1F2",
  dark: "#1F2937",
  white: "#FFFFFF",
};

const wb = Workbook.create();
const sheetNames = [
  "Resumen",
  "Datos_fuente",
  "Transformaciones",
  "Modelo_principal",
  "Validacion",
  "ECM_exploratorio",
  "Diagnosticos",
  "Variables",
  "Fuentes",
];
const sheets = Object.fromEntries(sheetNames.map((name) => [name, wb.worksheets.add(name)]));
await wb.comments.setSelf({ displayName: "Equipo de análisis" });

function baseSheet(sheet) {
  sheet.showGridLines = false;
  sheet.getRange("A1:Z300").format.font = { name: "Aptos", color: COLORS.dark };
}

function title(sheet, range, text) {
  sheet.mergeCells(range);
  const r = sheet.getRange(range);
  r.values = [[text]];
  r.format = {
    fill: COLORS.navy,
    font: { bold: true, color: COLORS.white },
    verticalAlignment: "center",
  };
  r.format.rowHeight = 30;
}

function subtitle(sheet, range, text, fill = COLORS.paleBlue) {
  sheet.mergeCells(range);
  const r = sheet.getRange(range);
  r.values = [[text]];
  r.format = {
    fill,
    font: { color: COLORS.dark },
    wrapText: true,
    verticalAlignment: "center",
  };
  r.format.rowHeight = 36;
}

function section(sheet, range, text) {
  sheet.mergeCells(range);
  const r = sheet.getRange(range);
  r.values = [[text]];
  r.format = {
    fill: COLORS.blue,
    font: { bold: true, color: COLORS.white },
    verticalAlignment: "center",
  };
  r.format.rowHeight = 22;
}

function header(sheet, range) {
  sheet.getRange(range).format = {
    fill: COLORS.navy,
    font: { bold: true, color: COLORS.white },
    wrapText: true,
    verticalAlignment: "center",
    horizontalAlignment: "center",
    borders: { preset: "all", style: "thin", color: "#B4C6E7" },
  };
}

function addTable(sheet, range, name) {
  const table = sheet.tables.add(range, true, name);
  table.style = "TableStyleMedium2";
  table.showBandedRows = true;
  table.showFilterButton = true;
  return table;
}

function card(sheet, labelRange, valueRange, label, value, fill = COLORS.paleBlue) {
  sheet.mergeCells(labelRange);
  sheet.mergeCells(valueRange);
  sheet.getRange(labelRange).values = [[label]];
  sheet.getRange(labelRange).format = {
    fill,
    font: { bold: true, color: COLORS.navy },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: COLORS.blue },
  };
  sheet.getRange(valueRange).values = [[value]];
  sheet.getRange(valueRange).format = {
    fill: COLORS.white,
    font: { bold: true, color: COLORS.navy },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: COLORS.blue },
  };
  sheet.getRange(labelRange).format.rowHeight = 22;
  sheet.getRange(valueRange).format.rowHeight = 30;
}

for (const sheet of Object.values(sheets)) baseSheet(sheet);

// Resumen
{
  const s = sheets.Resumen;
  title(s, "A1:N2", "Modelo econométrico de la TRM en Colombia");
  subtitle(
    s,
    "A3:N3",
    "Modelo mensual para explicar variaciones de COP por USD. Muestra común: enero de 2006 a abril de 2026; estimación principal en primeras diferencias con errores HAC."
  );

  card(s, "A5:B5", "A6:B7", "Observaciones en niveles", metadata.observaciones);
  card(s, "C5:D5", "C6:D7", "R² ajustado", pct(metadata.adl_r_cuadrado_ajustado));
  card(s, "E5:F5", "E6:F7", "MAPE condicional", `${Number(modelMetric.mape_pct).toFixed(2)}%`);
  card(s, "A9:B9", "A10:B11", "Acierto de dirección", `${Number(modelMetric.acierto_direccion_pct).toFixed(1)}%`, COLORS.green);
  card(s, "C9:D9", "C10:D11", "MAE vs. caminata aleatoria", `${((1 - n(modelMetric.mae_log) / n(rwMetric.mae_log)) * 100).toFixed(1)}% menor`, COLORS.green);
  card(s, "E9:F9", "E10:F11", "Cointegración al 5%", "No concluyente", COLORS.amber);

  section(s, "A13:F13", "Especificación principal");
  subtitle(
    s,
    "A14:F16",
    "Δln(TRM)t = c + β1Δln(Brent)t + β2Δln(dólar amplio)t + β3Δln(VIX)t + β4Δln(remesas 12m)t−1 + β5Δ(diferencial de tasas)t−1 + β6Δ(déficit 12m/PIB)t−1 + β7 pandemia + ut",
    COLORS.paleGray
  );

  section(s, "A18:F18", "Lectura de los resultados (asociaciones, no efectos causales)");
  s.getRange("A19:F27").values = [
    ["Variable", "Movimiento ilustrativo", "Efecto aproximado en TRM", "Signo", "p-valor", "Lectura"],
    ["Brent", "+10%", "−0,49%", "Aprecia el COP", n(coefs[1].p_valor), "Consistente con mayor ingreso externo petrolero"],
    ["Índice amplio del dólar", "+1%", "+1,22%", "Deprecia el COP", n(coefs[2].p_valor), "Es el factor con mayor precisión estadística"],
    ["VIX", "+10%", "+0,37%", "Deprecia el COP", n(coefs[3].p_valor), "Captura episodios globales de aversión al riesgo"],
    ["Remesas, acumulado 12m (t−1)", "+10%", "+2,50%", "Deprecia el COP", n(coefs[4].p_valor), "Signo contrario al canal de oferta; probable endogeneidad"],
    ["Diferencial tasas CO−EE. UU. (t−1)", "+1 pp", "−0,99%", "Aprecia el COP", n(coefs[5].p_valor), "Compatible con un mayor retorno relativo"],
    ["Déficit fiscal 12m/PIB (t−1)", "+1 pp", "+0,43%", "Deprecia el COP", n(coefs[6].p_valor), "Signo esperado, pero estimación imprecisa"],
    ["Pandemia, mar–may 2020", "Dummy = 1", "+0,82%", "Deprecia el COP", n(coefs[7].p_valor), "Control de episodio extraordinario"],
    ["Conclusión", "—", "—", "—", null, "Dólar global, petróleo y VIX dominan el movimiento mensual"],
  ];
  header(s, "A19:F19");
  s.getRange("E20:E27").format.numberFormat = "0.0000";
  s.getRange("A19:F27").format.wrapText = true;
  s.getRange("A19:F27").format.borders = { preset: "all", style: "thin", color: "#D9E1F2" };
  s.getRange("A27:F27").format = { fill: COLORS.green, font: { bold: true, color: COLORS.dark }, wrapText: true };

  section(s, "A29:F29", "Alcance y cautelas");
  s.getRange("A30:F35").values = [
    ["1", "La regresión identifica asociaciones dinámicas; no demuestra causalidad."],
    ["2", "La validación es condicional: usa realizaciones contemporáneas de Brent, dólar amplio y VIX; no equivale a un pronóstico en tiempo real."],
    ["3", "Los residuos presentan colas no normales; para inferencia se reportan errores HAC."],
    ["4", "El resultado positivo de remesas puede reflejar respuesta de los hogares a depreciaciones u otros shocks simultáneos."],
    ["5", "La prueba bounds no confirma cointegración al 5%; el ECM se muestra solo como contraste exploratorio."],
    ["6", "El déficit fiscal tiene el signo esperado, pero su p-valor de 0,189 no permite afirmar un efecto distinto de cero al 5%."],
  ];
  s.mergeCells("B30:F30"); s.mergeCells("B31:F31"); s.mergeCells("B32:F32");
  s.mergeCells("B33:F33"); s.mergeCells("B34:F34"); s.mergeCells("B35:F35");
  s.getRange("A30:F35").format = { fill: COLORS.amber, wrapText: true, borders: { preset: "all", style: "thin", color: "#E6B800" } };
  s.getRange("A30:A35").format = { fill: COLORS.navy, font: { bold: true, color: COLORS.white }, horizontalAlignment: "center", verticalAlignment: "center" };

  section(s, "H5:N5", "TRM observada y ajuste de un paso (muestra anual)");
  s.getRange("H37:J37").values = [["Mes", "TRM observada", "TRM ajustada"]];
  const helperRows = [];
  for (let i = 0; i < fit.length; i += 12) helperRows.push(i);
  if (helperRows.at(-1) !== fit.length - 1) helperRows.push(fit.length - 1);
  const helperStart = 38;
  s.getRange(`H${helperStart}:J${helperStart + helperRows.length - 1}`).formulas = helperRows.map((i) => {
    const modelRow = 18 + i;
    return [`='Modelo_principal'!A${modelRow}`, `='Modelo_principal'!M${modelRow}`, `='Modelo_principal'!N${modelRow}`];
  });
  header(s, "H37:J37");
  s.getRange(`I${helperStart}:J${helperStart + helperRows.length - 1}`).format.numberFormat = "#,##0";
  const chart = s.charts.add("line", s.getRange(`H37:J${helperStart + helperRows.length - 1}`));
  chart.title = "El modelo reproduce parte importante de los giros de la TRM";
  chart.titleTextStyle.fontSize = 12;
  chart.hasLegend = true;
  chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
  chart.yAxis = { numberFormatCode: "#,##0" };
  chart.setPosition("H6", "N27");

  s.getRange("A1:N58").format.verticalAlignment = "center";
  s.getRange("A:A").format.columnWidth = 22;
  s.getRange("B:B").format.columnWidth = 24;
  s.getRange("C:D").format.columnWidth = 17;
  s.getRange("E:E").format.columnWidth = 14;
  s.getRange("F:F").format.columnWidth = 34;
  s.getRange("G:G").format.columnWidth = 3;
  s.getRange("H:H").format.columnWidth = 14;
  s.getRange("I:J").format.columnWidth = 16;
  s.getRange("K:N").format.columnWidth = 12;
  s.freezePanes.freezeRows(3);
}

// Datos fuente
{
  const s = sheets.Datos_fuente;
  title(s, "A1:N1", "Datos fuente mensuales");
  subtitle(s, "A2:N3", "Niveles utilizados para construir el modelo. Los indicadores diarios se convierten a promedio mensual. Los espacios en blanco representan observaciones no disponibles; no se imputan con ceros.");
  const heads = [
    "Mes", "TRM (COP/USD)", "Brent (USD/barril)", "Remesas (USD mill.)", "Remesas 12m (USD mill.)",
    "Tasa política Colombia (%)", "Fed funds (%)", "Diferencial tasas (pp)", "Balance fiscal mensual (miles mill. COP)",
    "Déficit fiscal 12m (% PIB)", "Índice dólar amplio", "VIX", "Términos de intercambio", "Dummy pandemia",
  ];
  s.getRange("A5:N5").values = [heads];
  const matrix = raw.map((r) => [
    r.fecha.slice(0, 7), n(r.trm_cop_usd), n(r.brent_usd_barril), n(r.remesas_usd_millones), n(r.remesas_12m_usd_millones),
    n(r.tasa_politica_colombia_pct), n(r.fed_funds_eeuu_pct), n(r.diferencial_tasas_pp), n(r.balance_fiscal_miles_millones_cop),
    n(r.deficit_fiscal_12m_pct_pib), n(r.indice_dolar_amplio), n(r.vix), n(r.terminos_intercambio), n(r.dummy_pandemia_2020),
  ]);
  const end = 5 + matrix.length;
  s.getRange(`A6:N${end}`).values = matrix;
  header(s, "A5:N5");
  addTable(s, `A5:N${end}`, "DatosFuenteTable");
  s.getRange(`B6:E${end}`).format.numberFormat = "#,##0.00";
  s.getRange(`F6:H${end}`).format.numberFormat = "0.00";
  s.getRange(`I6:I${end}`).format.numberFormat = "#,##0.00;[Red]-#,##0.00";
  s.getRange(`J6:M${end}`).format.numberFormat = "0.00";
  s.getRange(`N6:N${end}`).format.numberFormat = "0";
  s.getRange(`A5:N${end}`).format.verticalAlignment = "center";
  s.getRange("A:A").format.columnWidth = 12;
  s.getRange("B:C").format.columnWidth = 16;
  s.getRange("D:E").format.columnWidth = 18;
  s.getRange("F:H").format.columnWidth = 16;
  s.getRange("I:I").format.columnWidth = 24;
  s.getRange("J:N").format.columnWidth = 18;
  s.getRange("A5:N5").format.rowHeight = 42;
  s.freezePanes.freezeRows(5);
  s.freezePanes.freezeColumns(1);

  const comments = {
    B5: "Fuente: Banco de la República, serie diaria TRM 1; promedio mensual. https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=1",
    C5: "Fuente: EIA vía FRED, DCOILBRENTEU; promedio mensual de observaciones diarias.",
    D5: "Fuente: Banco de la República, remesas de trabajadores, serie 15363.",
    F5: "Fuente: Banco de la República, tasa de política, serie diaria 59; promedio mensual.",
    G5: "Fuente: Federal Reserve/FRED, FEDFUNDS, promedio mensual.",
    I5: "Fuente: Ministerio de Hacienda, balance fiscal del Gobierno Nacional Central, metodología de caja.",
    K5: "Fuente: Federal Reserve/FRED, índice nominal amplio del dólar DTWEXBGS; promedio mensual.",
    L5: "Fuente: Cboe vía FRED, VIXCLS; promedio mensual.",
    M5: "Fuente: Banco de la República, índice de términos de intercambio, serie 15360. Se conserva como variable de robustez, no entra al modelo base junto con Brent.",
  };
  for (const [cell, text] of Object.entries(comments)) wb.comments.addThread({ cell: s.getRange(cell) }, text);
}

// Transformaciones auditables
{
  const s = sheets.Transformaciones;
  title(s, "A1:P1", "Transformaciones del modelo");
  subtitle(s, "A2:P3", "Todas las transformaciones son fórmulas enlazadas a Datos_fuente. Δ indica cambio mensual; ln indica logaritmo natural. Las variables domésticas rezagadas se aplican en la hoja Modelo_principal.");
  const heads = ["Mes", "ln TRM", "Δln TRM", "ln Brent", "Δln Brent", "ln remesas 12m", "Δln remesas 12m", "Diferencial tasas", "Δ diferencial", "Déficit 12m/PIB", "Δ déficit", "ln dólar amplio", "Δln dólar amplio", "ln VIX", "Δln VIX", "Pandemia"];
  s.getRange("A5:P5").values = [heads];
  const formulas = raw.map((_, i) => {
    const r = 6 + i;
    const src = r;
    const first = i === 0;
    return [
      `='Datos_fuente'!A${src}`,
      `=IF('Datos_fuente'!B${src}="","",LN('Datos_fuente'!B${src}))`,
      first ? "" : `=IF(OR(B${r}="",B${r - 1}=""),"",B${r}-B${r - 1})`,
      `=IF('Datos_fuente'!C${src}="","",LN('Datos_fuente'!C${src}))`,
      first ? "" : `=IF(OR(D${r}="",D${r - 1}=""),"",D${r}-D${r - 1})`,
      `=IF('Datos_fuente'!E${src}="","",LN('Datos_fuente'!E${src}))`,
      first ? "" : `=IF(OR(F${r}="",F${r - 1}=""),"",F${r}-F${r - 1})`,
      `='Datos_fuente'!H${src}`,
      first ? "" : `=IF(OR(H${r}="",H${r - 1}=""),"",H${r}-H${r - 1})`,
      `='Datos_fuente'!J${src}`,
      first ? "" : `=IF(OR(J${r}="",J${r - 1}=""),"",J${r}-J${r - 1})`,
      `=IF('Datos_fuente'!K${src}="","",LN('Datos_fuente'!K${src}))`,
      first ? "" : `=IF(OR(L${r}="",L${r - 1}=""),"",L${r}-L${r - 1})`,
      `=IF('Datos_fuente'!L${src}="","",LN('Datos_fuente'!L${src}))`,
      first ? "" : `=IF(OR(N${r}="",N${r - 1}=""),"",N${r}-N${r - 1})`,
      `='Datos_fuente'!N${src}`,
    ];
  });
  const end = 5 + formulas.length;
  s.getRange(`A6:P${end}`).formulas = formulas;
  header(s, "A5:P5");
  addTable(s, `A5:P${end}`, "TransformacionesTable");
  s.getRange(`B6:G${end}`).format.numberFormat = "0.000000";
  s.getRange(`H6:K${end}`).format.numberFormat = "0.0000";
  s.getRange(`L6:O${end}`).format.numberFormat = "0.000000";
  s.getRange(`P6:P${end}`).format.numberFormat = "0";
  s.getRange("A:A").format.columnWidth = 12;
  s.getRange("B:P").format.columnWidth = 16;
  s.getRange("A5:P5").format.rowHeight = 38;
  s.freezePanes.freezeRows(5);
  s.freezePanes.freezeColumns(1);
}

// Modelo principal
{
  const s = sheets.Modelo_principal;
  title(s, "A1:W1", "Modelo principal: variación mensual de la TRM");
  subtitle(s, "A2:W3", "OLS con errores estándar HAC (6 meses). BIC seleccionó cero rezagos adicionales de Δln(TRM). Brent, dólar amplio y VIX entran en t; remesas, diferencial de tasas y déficit fiscal entran con un mes de rezago.");
  s.getRange("A5:G5").values = [["Variable", "Coeficiente", "EE HAC", "t", "p-valor", "IC 95% inferior", "IC 95% superior"]];
  const labels = {
    const: "Intercepto",
    "D.ln_brent.L0": "Δ ln Brent (t)",
    "D.ln_dolar_amplio.L0": "Δ ln índice dólar amplio (t)",
    "D.ln_vix.L0": "Δ ln VIX (t)",
    "D.ln_remesas_12m.L1": "Δ ln remesas 12m (t−1)",
    "D.diferencial_tasas_pp.L1": "Δ diferencial tasas (t−1)",
    "D.deficit_fiscal_12m_pct_pib.L1": "Δ déficit fiscal 12m/PIB (t−1)",
    dummy_pandemia_2020: "Dummy pandemia 2020",
  };
  s.getRange("A6:G13").values = coefs.map((r) => [labels[r.termino], n(r.coeficiente), n(r.error_estandar_hac), n(r.estadistico_t), n(r.p_valor), n(r.ic_95_inferior), n(r.ic_95_superior)]);
  header(s, "A5:G5");
  addTable(s, "A5:G13", "CoeficientesModeloTable");
  s.getRange("B6:G13").format.numberFormat = "0.000000";
  s.getRange("E6:E13").conditionalFormats.add("cellIs", { operator: "lessThan", formula: 0.05, format: { fill: COLORS.green, font: { bold: true, color: "#006100" } } });

  s.getRange("I5:N5").values = [["Indicador", "Valor", "Lectura", "Indicador", "Valor", "Lectura"]];
  s.getRange("I6:N9").values = [
    ["R²", metadata.adl_r_cuadrado, "Variación explicada dentro de muestra", "AIC", metadata.adl_aic, "Comparación relativa"],
    ["R² ajustado", metadata.adl_r_cuadrado_ajustado, "Penaliza número de parámetros", "BIC", metadata.adl_bic, "Seleccionó p=0"],
    ["Observaciones", metadata.adl_observaciones, "Mayo 2006–abril 2026", "HAC", 6, "Ventana mensual"],
    ["Frecuencia", "Mensual", "Promedio mensual de series diarias", "Objetivo", "Δln(TRM)", "Aumento = depreciación"],
  ];
  header(s, "I5:N5");
  s.getRange("I5:N9").format.borders = { preset: "all", style: "thin", color: "#D9E1F2" };
  s.getRange("J6:J7").format.numberFormat = "0.0%";
  s.getRange("M6:M7").format.numberFormat = "0.00";
  s.getRange("I5:N9").format.wrapText = true;

  const modelHeaderRow = 17;
  s.getRange(`A${modelHeaderRow}:N${modelHeaderRow}`).values = [[
    "Mes", "Δln TRM observado", "Constante", "Brent", "Dólar amplio", "VIX", "Remesas t−1", "Tasas t−1", "Fiscal t−1", "Pandemia", "Δln TRM ajustado", "Residuo", "TRM observada", "TRM ajustada 1 paso",
  ]];
  const dateToTransformRow = Object.fromEntries(raw.map((r, i) => [r.fecha, 6 + i]));
  const modelFormulas = fit.map((r, i) => {
    const row = modelHeaderRow + 1 + i;
    const tr = dateToTransformRow[r.fecha];
    return [
      `='Transformaciones'!A${tr}`,
      `='Transformaciones'!C${tr}`,
      "=$B$6",
      `=$B$7*'Transformaciones'!E${tr}`,
      `=$B$8*'Transformaciones'!M${tr}`,
      `=$B$9*'Transformaciones'!O${tr}`,
      `=$B$10*'Transformaciones'!G${tr - 1}`,
      `=$B$11*'Transformaciones'!I${tr - 1}`,
      `=$B$12*'Transformaciones'!K${tr - 1}`,
      `=$B$13*'Transformaciones'!P${tr}`,
      `=SUM(C${row}:J${row})`,
      `=B${row}-K${row}`,
      `='Datos_fuente'!B${tr}`,
      `=EXP('Transformaciones'!B${tr - 1}+K${row})`,
    ];
  });
  const modelEnd = modelHeaderRow + fit.length;
  s.getRange(`A${modelHeaderRow + 1}:N${modelEnd}`).formulas = modelFormulas;
  header(s, `A${modelHeaderRow}:N${modelHeaderRow}`);
  addTable(s, `A${modelHeaderRow}:N${modelEnd}`, "AjusteModeloTable");
  s.getRange(`B${modelHeaderRow + 1}:L${modelEnd}`).format.numberFormat = "0.000000";
  s.getRange(`M${modelHeaderRow + 1}:N${modelEnd}`).format.numberFormat = "#,##0.00";
  s.getRange(`K${modelHeaderRow + 1}:L${modelEnd}`).format.fill = COLORS.paleBlue;

  s.getRange("P17:R17").values = [["Mes", "TRM observada", "TRM ajustada"]];
  const sampleIdx = [];
  for (let i = 0; i < fit.length; i += 12) sampleIdx.push(i);
  if (sampleIdx.at(-1) !== fit.length - 1) sampleIdx.push(fit.length - 1);
  s.getRange(`P18:R${17 + sampleIdx.length}`).formulas = sampleIdx.map((i) => {
    const r = modelHeaderRow + 1 + i;
    return [`=A${r}`, `=M${r}`, `=N${r}`];
  });
  header(s, "P17:R17");
  s.getRange(`Q18:R${17 + sampleIdx.length}`).format.numberFormat = "#,##0";
  const chart = s.charts.add("line", s.getRange(`P17:R${17 + sampleIdx.length}`));
  chart.title = "Ajuste de un paso, muestra anual";
  chart.titleTextStyle.fontSize = 12;
  chart.hasLegend = true;
  chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
  chart.yAxis = { numberFormatCode: "#,##0" };
  chart.setPosition("P2", "W15");

  s.getRange("A:A").format.columnWidth = 12;
  s.getRange("B:B").format.columnWidth = 18;
  s.getRange("C:L").format.columnWidth = 14;
  s.getRange("M:N").format.columnWidth = 18;
  s.getRange("O:O").format.columnWidth = 3;
  s.getRange("P:P").format.columnWidth = 12;
  s.getRange("Q:R").format.columnWidth = 16;
  s.getRange("S:W").format.columnWidth = 11;
  s.getRange("A5:N17").format.wrapText = true;
  s.getRange("A17:N17").format.rowHeight = 42;
  s.freezePanes.freezeRows(17);
  s.freezePanes.freezeColumns(1);
}

// Validación
{
  const s = sheets.Validacion;
  title(s, "A1:R1", "Validación fuera de muestra");
  subtitle(s, "A2:R3", "Ventana expansiva de 48 meses (mayo de 2022–abril de 2026). La evaluación es condicional: usa valores contemporáneos ya realizados de Brent, dólar amplio y VIX. Es una prueba explicativa, no un pronóstico genuinamente disponible en tiempo real.", COLORS.amber);

  s.getRange("A5:F5").values = [["Modelo", "Observaciones", "MAE (log)", "RMSE (log)", "MAPE", "Acierto dirección"]];
  s.getRange("A6:F7").values = validationMetrics.map((r) => [r.modelo, n(r.observaciones), n(r.mae_log), n(r.rmse_log), n(r.mape_pct) / 100, n(r.acierto_direccion_pct) === null ? null : n(r.acierto_direccion_pct) / 100]);
  header(s, "A5:F5");
  addTable(s, "A5:F7", "MetricasValidacionTable");
  s.getRange("C6:D7").format.numberFormat = "0.0000";
  s.getRange("E6:F7").format.numberFormat = "0.0%";
  s.getRange("A6:F6").format.fill = COLORS.green;
  s.getRange("A6:F7").format.rowHeight = 30;

  s.getRange("H5:J5").values = [["Comparación", "Resultado", "Lectura"]];
  s.getRange("H6:J8").values = [
    ["Reducción de MAE", 1 - n(modelMetric.mae_log) / n(rwMetric.mae_log), "Mejora frente a la caminata aleatoria"],
    ["Reducción de RMSE", 1 - n(modelMetric.rmse_log) / n(rwMetric.rmse_log), "Mejora frente a la caminata aleatoria"],
    ["Dirección correcta", n(modelMetric.acierto_direccion_pct) / 100, "35 de 48 meses, aproximadamente"],
  ];
  header(s, "H5:J5");
  s.getRange("H5:J8").format.borders = { preset: "all", style: "thin", color: "#D9E1F2" };
  s.getRange("I6:I8").format.numberFormat = "0.0%";
  s.getRange("H5:J8").format.wrapText = true;
  s.getRange("H6:J8").format.rowHeight = 38;

  const heads = ["Mes", "ln TRM observada", "ln TRM modelo", "ln TRM caminata", "Δln observado", "Δln modelo", "TRM observada", "TRM modelo", "TRM caminata"];
  s.getRange("A11:I11").values = [heads];
  const valRows = validationPredictions.map((r) => [
    r.fecha.slice(0, 7), n(r.ln_trm_observada), n(r.ln_trm_modelo_condicional), n(r.ln_trm_caminata_aleatoria), n(r.cambio_log_observado), n(r.cambio_log_modelo), n(r.trm_observada), n(r.trm_modelo_condicional), n(r.trm_caminata_aleatoria),
  ]);
  const valEnd = 11 + valRows.length;
  s.getRange(`A12:I${valEnd}`).values = valRows;
  header(s, "A11:I11");
  addTable(s, `A11:I${valEnd}`, "PrediccionesValidacionTable");
  s.getRange(`B12:F${valEnd}`).format.numberFormat = "0.000000";
  s.getRange(`G12:I${valEnd}`).format.numberFormat = "#,##0.00";

  s.getRange("K25:N25").values = [["Mes", "TRM observada", "Modelo condicional", "Caminata aleatoria"]];
  s.getRange(`K26:N${25 + valRows.length}`).formulas = valRows.map((_, i) => {
    const r = 12 + i;
    return [`=A${r}`, `=G${r}`, `=H${r}`, `=I${r}`];
  });
  header(s, "K25:N25");
  s.getRange(`L26:N${25 + valRows.length}`).format.numberFormat = "#,##0";
  const chart = s.charts.add("line", s.getRange(`K25:N${25 + valRows.length}`));
  chart.title = "Validación condicional: TRM observada vs. comparadores";
  chart.titleTextStyle.fontSize = 12;
  chart.hasLegend = true;
  chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 8 } };
  chart.yAxis = { numberFormatCode: "#,##0" };
  chart.setPosition("K5", "R22");

  s.getRange("A:A").format.columnWidth = 28;
  s.getRange("B:B").format.columnWidth = 15;
  s.getRange("C:F").format.columnWidth = 17;
  s.getRange("G:I").format.columnWidth = 17;
  s.getRange("J:J").format.columnWidth = 30;
  s.getRange("K:K").format.columnWidth = 12;
  s.getRange("L:N").format.columnWidth = 17;
  s.getRange("O:R").format.columnWidth = 11;
  s.getRange("A11:I11").format.rowHeight = 36;
  s.freezePanes.freezeRows(11);
  s.freezePanes.freezeColumns(1);
}

// ECM exploratorio
{
  const s = sheets.ECM_exploratorio;
  title(s, "A1:H1", "ARDL–ECM exploratorio");
  subtitle(s, "A2:H3", "La prueba bounds no confirma cointegración al 5%: F = 3,414 está por debajo del límite superior de 3,627 y el p-valor I(1) es 7,31%. Los coeficientes de largo plazo se muestran como contraste y no deben interpretarse como un equilibrio estable.", COLORS.amber);
  section(s, "A5:D5", "Prueba bounds");
  s.getRange("A6:D6").values = [["F", "p-valor I(0)", "p-valor I(1)", "Decisión al 5%"]];
  s.getRange("A7:D7").values = [[n(bounds[0].estadistico_f), n(bounds[0].p_valor_i0), n(bounds[0].p_valor_i1), "No concluyente"]];
  header(s, "A6:D6");
  s.getRange("A6:D7").format.borders = { preset: "all", style: "thin", color: "#D9E1F2" };
  s.getRange("A7:C7").format.numberFormat = "0.0000";
  s.getRange("D7").format.fill = COLORS.amber;

  section(s, "A10:C10", "Valores críticos bounds");
  s.getRange("A11:C11").values = [["Percentil", "Límite inferior I(0)", "Límite superior I(1)"]];
  s.getRange(`A12:C${11 + boundsCritical.length}`).values = boundsCritical.map((r) => [n(r.percentile) / 100, n(r.lower), n(r.upper)]);
  header(s, "A11:C11");
  addTable(s, `A11:C${11 + boundsCritical.length}`, "BoundsCriticosTable");
  s.getRange(`A12:A${11 + boundsCritical.length}`).format.numberFormat = "0.0%";
  s.getRange(`B12:C${11 + boundsCritical.length}`).format.numberFormat = "0.000";

  section(s, "A18:G18", "Coeficientes de largo plazo (solo exploratorios)");
  s.getRange("A19:G19").values = [["Variable", "Coeficiente", "EE", "t", "p-valor", "IC 95% inferior", "IC 95% superior"]];
  s.getRange(`A20:G${19 + ecmLong.length}`).values = ecmLong.map((r) => [r.termino, n(r.coeficiente_largo_plazo), n(r.error_estandar), n(r.estadistico_t), n(r.p_valor), n(r.ic_95_inferior), n(r.ic_95_superior)]);
  header(s, "A19:G19");
  addTable(s, `A19:G${19 + ecmLong.length}`, "ECMLargoPlazoTable");
  s.getRange(`B20:G${19 + ecmLong.length}`).format.numberFormat = "0.000000";

  section(s, "F5:H5", "Dinámica de ajuste");
  s.getRange("F6:H9").values = [
    ["Parámetro", "Valor", "Lectura"],
    ["Velocidad de ajuste", metadata.velocidad_ajuste, "Negativa y significativa en la ecuación auxiliar"],
    ["ARDL seleccionado", "(1,1)", "Un rezago común"],
    ["Uso recomendado", "Robustez", "No usar sus coeficientes como elasticidades firmes"],
  ];
  header(s, "F6:H6");
  s.getRange("F6:H9").format.borders = { preset: "all", style: "thin", color: "#D9E1F2" };
  s.getRange("G7:G7").format.numberFormat = "0.0000";
  s.getRange("F6:H9").format.wrapText = true;

  s.getRange("A:A").format.columnWidth = 24;
  s.getRange("B:G").format.columnWidth = 18;
  s.getRange("H:H").format.columnWidth = 34;
  s.freezePanes.freezeRows(3);
}

// Diagnósticos
{
  const s = sheets.Diagnosticos;
  title(s, "A1:N1", "Diagnósticos y selección del modelo");
  subtitle(s, "A2:N3", "Las pruebas se interpretan al 5%. La ausencia de autocorrelación y ARCH respalda la dinámica escogida; la no normalidad de los residuos aconseja mantener inferencia robusta y cautela en episodios extremos.");

  section(s, "A5:D5", "Diagnósticos del modelo principal");
  s.getRange("A6:D6").values = [["Prueba", "Estadístico", "p-valor", "Lectura"]];
  const diagRows = diagnostics.map((r) => {
    const p = n(r.p_valor);
    let reading = "Referencia";
    if (r.prueba.includes("Jarque")) reading = p < 0.05 ? "Residuos no normales" : "No se rechaza normalidad";
    else if (r.prueba.includes("Durbin")) reading = "Cercano a 2";
    else if (r.prueba.includes("CUSUM")) reading = p >= 0.05 ? "Sin inestabilidad detectada" : "Posible inestabilidad";
    else if (r.prueba.includes("RESET")) reading = p >= 0.05 ? "Sin evidencia de mala forma funcional" : "Revisar forma funcional";
    else if (r.prueba.includes("ARCH")) reading = p >= 0.05 ? "Sin ARCH detectado" : "Heterocedasticidad condicional";
    else reading = p >= 0.05 ? "Sin autocorrelación detectada" : "Autocorrelación residual";
    return [r.prueba, n(r.estadistico), p, reading];
  });
  s.getRange(`A7:D${6 + diagRows.length}`).values = diagRows;
  header(s, "A6:D6");
  addTable(s, `A6:D${6 + diagRows.length}`, "DiagnosticosModeloTable");
  s.getRange(`B7:C${6 + diagRows.length}`).format.numberFormat = "0.0000";
  const jbIndex = diagnostics.findIndex((r) => r.prueba.includes("Jarque"));
  if (jbIndex >= 0) s.getRange(`A${7 + jbIndex}:D${7 + jbIndex}`).format.fill = COLORS.red;

  section(s, "F5:I5", "Selección de rezagos de Δln(TRM)");
  s.getRange("F6:I6").values = [["p", "AIC", "BIC", "R² ajustado"]];
  s.getRange(`F7:I${6 + adlLags.length}`).values = adlLags.map((r) => [n(r.p_cambio_trm), n(r.aic), n(r.bic), n(r.r_cuadrado_ajustado)]);
  header(s, "F6:I6");
  addTable(s, `F6:I${6 + adlLags.length}`, "SeleccionRezagosTable");
  s.getRange(`G7:H${6 + adlLags.length}`).format.numberFormat = "0.00";
  s.getRange(`I7:I${6 + adlLags.length}`).format.numberFormat = "0.0%";
  s.getRange("F7:I7").format.fill = COLORS.green;

  section(s, "A17:H17", "Pruebas de integración");
  s.getRange("A18:H18").values = [["Variable", "Transformación", "n", "ADF", "p ADF", "Rezagos ADF", "KPSS", "p KPSS"]];
  s.getRange(`A19:H${18 + integration.length}`).values = integration.map((r) => [r.variable, r.transformacion, n(r.n), n(r.adf_estadistico), n(r.adf_p), n(r.adf_rezagos), n(r.kpss_estadistico), n(r.kpss_p)]);
  header(s, "A18:H18");
  addTable(s, `A18:H${18 + integration.length}`, "IntegracionTable");
  s.getRange(`D19:H${18 + integration.length}`).format.numberFormat = "0.0000";

  section(s, "J5:N5", "Criterios de decisión");
  s.getRange("J6:N11").values = [
    ["Elemento", "Criterio", "Resultado", "Implicación", "Acción"],
    ["BIC", "Mínimo", "p=0", "Modelo parsimonioso", "No agregar rezagos de TRM"],
    ["Autocorrelación", "p>0,05", "Cumple", "Dinámica adecuada", "Mantener especificación"],
    ["ARCH", "p>0,05", "Cumple", "Sin ARCH detectado", "Mantener HAC"],
    ["Normalidad", "p>0,05", "No cumple", "Colas extremas", "No basar conclusiones en normalidad"],
    ["Bounds", "p I(1)<0,05", "No cumple", "Sin cointegración firme", "Usar diferencias como modelo principal"],
  ];
  header(s, "J6:N6");
  s.getRange("J6:N11").format = { wrapText: true, borders: { preset: "all", style: "thin", color: "#D9E1F2" } };
  s.getRange("J10:N11").format.fill = COLORS.amber;
  s.getRange("J7:N11").format.rowHeight = 38;

  s.getRange("A:B").format.columnWidth = 24;
  s.getRange("C:H").format.columnWidth = 14;
  s.getRange("I:I").format.columnWidth = 14;
  s.getRange("J:N").format.columnWidth = 18;
  s.freezePanes.freezeRows(3);
}

// Variables incluidas y propuestas
{
  const s = sheets.Variables;
  title(s, "A1:I1", "Mapa de variables: núcleo y extensiones");
  subtitle(s, "A2:I3", "La especificación base es deliberadamente parsimoniosa. Las extensiones deben probarse por bloques para evitar multicolinealidad, sobreajuste y doble conteo del mismo shock.");
  const rows = [
    ["Objetivo", "TRM promedio mensual", "Incluida", "COP por USD", "Δln", "+ = depreciación", "Variable dependiente", "Precio del dólar en Colombia", "Promedios mensuales ocultan movimientos diarios"],
    ["Commodities", "Brent", "Incluida", "USD/barril", "Δln contemporáneo", "−", "Ingreso externo", "Exportaciones, IED e ingresos fiscales", "No acompañar con términos de intercambio en el núcleo"],
    ["Divisas", "Remesas recibidas", "Incluida", "Acumulado 12m en USD", "Δln, rezago 1", "− esperado", "Oferta de divisas", "Flujo estable de dólares", "Puede responder a la propia depreciación"],
    ["Monetario", "Diferencial tasas CO−EE. UU.", "Incluida", "Tasa política − Fed funds", "Δ pp, rezago 1", "−", "Retorno relativo", "Carry e ingreso de capital", "Tasas nominales; endógenas a inflación y TRM"],
    ["Fiscal", "Déficit GNC", "Incluida", "Acumulado 12m / PIB", "Δ pp, rezago 1", "+", "Riesgo fiscal", "Financiación y prima de riesgo", "Dato observado no es un shock fiscal exógeno"],
    ["Global", "Índice amplio del dólar", "Incluida", "Fed DTWEXBGS", "Δln contemporáneo", "+", "Fortaleza global USD", "Factor global común", "No es el DXY comercial de ICE"],
    ["Global", "VIX", "Incluida", "Promedio mensual", "Δln contemporáneo", "+", "Aversión al riesgo", "Risk-off y salida de emergentes", "Correlacionado con dólar global"],
    ["Externo", "Términos de intercambio", "Robustez alta", "BanRep 15360", "Δln", "−", "Poder de compra externo", "Incluye más exportaciones que petróleo", "Sustituir a Brent, no sumarlo automáticamente"],
    ["Riesgo", "EMBI/CDS Colombia", "Prioridad alta", "Spread soberano", "Nivel o Δ", "+", "Riesgo específico", "Fiscal, político y refinanciación", "EMBI no tiene descarga oficial pública estable"],
    ["Reservas", "Reservas internacionales netas", "Prioridad media", "BanRep 15053", "Δln, rezago 1", "−", "Colchón externo", "Capacidad de intervención y liquidez", "Intervención responde a la TRM"],
    ["Comercio", "Balanza comercial/cambiaria", "Prioridad media", "BanRep 16702 o DANE", "USD o % PIB", "−", "Oferta neta de divisas", "Exportaciones menos importaciones", "Simultánea con la depreciación"],
    ["Precios", "Inflación esperada CO−EE. UU.", "Prioridad alta", "Encuestas/breakeven", "Diferencial", "+ largo plazo", "Paridad de poder de compra", "Mejora diferencial real de tasas", "Disponibilidad histórica homogénea"],
    ["Mercado", "Monedas regionales", "Prioridad alta", "BRL, CLP, MXN, PEN", "Factor o promedio Δln", "+", "Contagio regional", "Captura shocks emergentes comunes", "Evitar duplicar VIX y dólar global"],
    ["Flujos", "Capital de portafolio/IED", "Prioridad media", "BanRep 16708", "USD, rezago", "−", "Demanda de activos COP", "Explica episodios de entrada/salida", "Altamente endógeno"],
    ["Política", "Intervención cambiaria", "Prioridad media", "Compras/ventas BanRep", "USD, rezago", "+ compras", "Demanda oficial de USD", "Importante en episodios puntuales", "Respuesta de política, no shock puro"],
  ];
  s.getRange("A5:I5").values = [["Bloque", "Variable", "Estatus", "Proxy/medición", "Transformación", "Signo sobre COP/USD", "Canal", "Justificación", "Cautela"]];
  s.getRange(`A6:I${5 + rows.length}`).values = rows;
  header(s, "A5:I5");
  addTable(s, `A5:I${5 + rows.length}`, "MapaVariablesTable");
  s.getRange(`A5:I${5 + rows.length}`).format.wrapText = true;
  s.getRange(`A6:I${5 + rows.length}`).format.rowHeight = 38;
  for (let i = 0; i < rows.length; i += 1) {
    const row = 6 + i;
    const status = rows[i][2];
    if (status === "Incluida") s.getRange(`C${row}`).format.fill = COLORS.green;
    else if (status.includes("alta")) s.getRange(`C${row}`).format.fill = COLORS.paleBlue;
    else s.getRange(`C${row}`).format.fill = COLORS.amber;
  }
  s.getRange("A:A").format.columnWidth = 14;
  s.getRange("B:B").format.columnWidth = 25;
  s.getRange("C:C").format.columnWidth = 16;
  s.getRange("D:G").format.columnWidth = 21;
  s.getRange("H:I").format.columnWidth = 31;
  s.getRange("A5:I5").format.rowHeight = 40;
  s.freezePanes.freezeRows(5);
  s.freezePanes.freezeColumns(2);
}

// Fuentes
{
  const s = sheets.Fuentes;
  title(s, "A1:G1", "Fuentes y trazabilidad");
  subtitle(s, "A2:G3", "Enlaces oficiales o distribuidores públicos de las series. La columna Uso indica si la variable entra al modelo base o se conserva como extensión/robustez.");
  const rows = [
    ["Banco de la República", "TRM diaria, serie 1", "Diaria → mensual", "1991–2026", "Modelo base", "Promedio mensual", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=1"],
    ["Banco de la República", "Tasa de política, serie 59", "Diaria → mensual", "1998–2026", "Modelo base", "Promedio mensual", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=59"],
    ["Banco de la República", "Remesas, serie 15363", "Mensual", "2000–2026", "Modelo base", "Acumulado móvil 12 meses", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15363"],
    ["Ministerio de Hacienda", "Balance fiscal GNC", "Mensual", "2004–2026", "Modelo base", "Balance de caja; déficit positivo tras cambiar signo", "https://www.minhacienda.gov.co/documents/d/portal/balance-fiscal-gnc-mensual-y-trimestral?download=true"],
    ["U.S. EIA / FRED", "Brent DCOILBRENTEU", "Diaria → mensual", "1987–2026", "Modelo base", "Promedio mensual", "https://fred.stlouisfed.org/series/DCOILBRENTEU"],
    ["Federal Reserve / FRED", "Federal funds FEDFUNDS", "Mensual", "1954–2026", "Modelo base", "Promedio mensual", "https://fred.stlouisfed.org/series/FEDFUNDS"],
    ["Federal Reserve / FRED", "Índice amplio USD DTWEXBGS", "Diaria → mensual", "2006–2026", "Modelo base", "Índice nominal amplio", "https://fred.stlouisfed.org/series/DTWEXBGS"],
    ["Cboe / FRED", "VIXCLS", "Diaria → mensual", "1990–2026", "Modelo base", "Promedio mensual", "https://fred.stlouisfed.org/series/VIXCLS"],
    ["Banco de la República", "Términos de intercambio 15360", "Mensual", "1995–2026", "Robustez", "Sustituto de Brent", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15360"],
    ["Banco de la República", "Reservas netas sin FLAR 15053", "Mensual", "1960–2026", "Propuesta", "Log y rezago", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15053"],
    ["Banco de la República", "Balanza comercial cambiaria 16702", "Mensual", "2001–2026", "Propuesta", "Flujo USD", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=16702"],
    ["Banco de la República", "Flujos de capital 16708", "Mensual", "2001–2026", "Propuesta", "Flujo USD, rezagado", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=16708"],
    ["Cboe", "VIX histórico", "Diaria", "1990–2026", "Verificación", "Fuente primaria del VIX", "https://www.cboe.com/tradable_products/vix/vix_historical_data"],
    ["Banco de la República", "Portal de sector externo", "Varias", "Histórico", "Documentación", "Metodologías de TRM, remesas y sector externo", "https://www.banrep.gov.co/es/estadisticas-economicas/series-historicas/tasas-cambio-sector-externo"],
  ];
  s.getRange("A5:G5").values = [["Organismo", "Serie/código", "Frecuencia", "Cobertura", "Uso", "Tratamiento", "URL"]];
  s.getRange(`A6:G${5 + rows.length}`).values = rows;
  header(s, "A5:G5");
  addTable(s, `A5:G${5 + rows.length}`, "FuentesTable");
  s.getRange(`A5:G${5 + rows.length}`).format.wrapText = true;
  s.getRange(`A6:G${5 + rows.length}`).format.rowHeight = 42;
  s.getRange("A:A").format.columnWidth = 25;
  s.getRange("B:B").format.columnWidth = 30;
  s.getRange("C:F").format.columnWidth = 20;
  s.getRange("G:G").format.columnWidth = 72;
  s.freezePanes.freezeRows(5);
  s.freezePanes.freezeColumns(2);
}

// Verificaciones estructurales y visuales antes de exportar.
const keyChecks = [];
for (const spec of [
  { range: "Resumen!A1:N35", rows: 35, cols: 14 },
  { range: "Modelo_principal!A5:N22", rows: 18, cols: 14 },
  { range: "Validacion!A5:J16", rows: 12, cols: 10 },
]) {
  const out = await wb.inspect({ kind: "table", range: spec.range, include: "values,formulas", tableMaxRows: spec.rows, tableMaxCols: spec.cols, maxChars: 16000 });
  keyChecks.push(out.ndjson);
}
const errors = await wb.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});

const renderSpecs = [
  ["Resumen", "A1:N58"],
  ["Datos_fuente", "A1:N24"],
  ["Transformaciones", "A1:P24"],
  ["Modelo_principal", "A1:W32"],
  ["Validacion", "A1:R30"],
  ["ECM_exploratorio", "A1:H30"],
  ["Diagnosticos", "A1:N34"],
  ["Variables", "A1:I21"],
  ["Fuentes", "A1:G20"],
];
for (const [sheetName, range] of renderSpecs) {
  const preview = await wb.render({ sheetName, range, scale: 1, format: "png" });
  const filename = `${sheetName.toLowerCase()}.png`;
  await fs.writeFile(path.join(PREVIEW_DIR, filename), new Uint8Array(await preview.arrayBuffer()));
}

const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(OUTPUT_XLSX);
await fs.writeFile(path.join(OUTPUT_DIR, "qa_inspect.txt"), `${keyChecks.join("\n\n")}\n\nERROR SCAN\n${errors.ndjson}\n`, "utf8");

console.log(JSON.stringify({
  output: OUTPUT_XLSX,
  rows_source: raw.length,
  rows_model: fit.length,
  rows_validation: validationPredictions.length,
  previews: renderSpecs.map(([name]) => path.join(PREVIEW_DIR, `${name.toLowerCase()}.png`)),
  error_scan: errors.ndjson,
}, null, 2));
