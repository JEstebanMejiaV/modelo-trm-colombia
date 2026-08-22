import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const ROOT = path.resolve(".");
const OUTPUT_DIR = process.env.MODEL_OUTPUT_DIR
  ? path.resolve(process.env.MODEL_OUTPUT_DIR)
  : path.join(ROOT, "outputs", "modelo_trm_colombia");
const PREVIEW_DIR = path.join(OUTPUT_DIR, "previews");
const OUTPUT_XLSX = path.join(OUTPUT_DIR, "modelo_trm_colombia.xlsx");
const DELIVERABLE_XLSX = path.join(ROOT, "deliverables", "modelo_trm_colombia.xlsx");

await fs.mkdir(PREVIEW_DIR, { recursive: true });
await fs.mkdir(path.dirname(DELIVERABLE_XLSX), { recursive: true });

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

function firstValue(row, ...keys) {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(row, key) && row[key] !== "") return row[key];
  }
  return "";
}

function columnLetter(columnNumber) {
  let value = columnNumber;
  let out = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    out = String.fromCharCode(65 + remainder) + out;
    value = Math.floor((value - 1) / 26);
  }
  return out;
}

function pct(value, digits = 1) {
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

const metadata = JSON.parse(await fs.readFile(path.join(ROOT, "results/metadata.json"), "utf8"));
const sampleStart = new Date(`${metadata.muestra_inicio}T00:00:00Z`);
sampleStart.setUTCMonth(sampleStart.getUTCMonth() - 1);
const sourceStart = sampleStart.toISOString().slice(0, 10);
const raw = (await readCsv("data/modelo_trm_datos_mensuales.csv"))
  .filter((r) => r.fecha >= sourceStart && r.fecha <= metadata.muestra_fin);
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
const expandedCoefs = await readCsv("results/coeficientes_modelo_ampliado.csv");
const expandedDiagnostics = await readCsv("results/diagnosticos_modelo_ampliado.csv");
const expandedFit = await readCsv("results/ajuste_historico_modelo_ampliado.csv");
const expandedContributions = await readCsv("results/contribuciones_modelo_ampliado.csv");
const expandedValidationMetrics = await readCsv("results/validacion_metricas_modelo_ampliado.csv");
const expandedValidationPredictions = await readCsv("results/validacion_predicciones_modelo_ampliado.csv");
const explanatoryWeights = await readCsv("results/pesos_explicativos_modelo_ampliado.csv");
const modelComparison = await readCsv("results/comparacion_modelos.csv");

const coefByTerm = Object.fromEntries(coefs.map((r) => [r.termino, n(r.coeficiente)]));
const coefRecordByTerm = Object.fromEntries(coefs.map((r) => [r.termino, r]));
const coefRowByTerm = Object.fromEntries(coefs.map((r, i) => [r.termino, 6 + i]));
const modelMetric = validationMetrics.find((r) => r.modelo.startsWith("ADL"));
const rwMetric = validationMetrics.find((r) => r.modelo.startsWith("Caminata"));
const expandedModelMetric = expandedValidationMetrics.find((r) => !r.modelo.toLowerCase().includes("caminata")) ?? expandedValidationMetrics[0];
const baseComparison = modelComparison.find((r) => /principal|base/i.test(r.modelo)) ?? modelComparison[0];
const expandedComparison = modelComparison.find((r) => /ampli/i.test(r.modelo)) ?? modelComparison.at(-1);

const TERM_LABELS = {
  const: "Intercepto",
  "D.ln_brent.L0": "Δ ln Brent (t)",
  "D.ln_dolar_amplio.L0": "Δ ln índice dólar amplio (t)",
  "D.ln_vix.L0": "Δ ln VIX (t)",
  "D.ln_remesas_12m.L1": "Δ ln remesas 12m (t−1)",
  "D.diferencial_tasas_pp.L1": "Δ diferencial tasas (t−1)",
  "D.deficit_fiscal_12m_pct_pib.L1": "Δ déficit fiscal 12m/PIB (t−1)",
  "D.spread_tes_ust_10y_pp.L0": "Δ spread TES–UST 10 años (t)",
  "D.ln_reservas_netas_sin_flar.L1": "Δ ln reservas netas sin FLAR (t−1)",
  "D.asinh_balanza_comercial.L1": "Δ asinh balanza comercial cambiaria (t−1)",
  "D.asinh_flujos_capital.L1": "Δ asinh flujo neto de capital (t−1)",
  "diferencial_inflacion_pp.L1": "Diferencial de inflación interanual (t−1)",
  "factor_monedas_regionales.L0": "Factor de monedas regionales (t)",
  factor_monedas_regionales: "Factor de monedas regionales (t)",
  dummy_pandemia_2020: "Dummy pandemia 2020",
};

function termLabel(term) {
  return TERM_LABELS[term] ?? term
    .replace(/^D\./, "Δ ")
    .replace(/\.L0$/, " (t)")
    .replace(/\.L1$/, " (t−1)")
    .replaceAll("_", " ");
}

const orderedWeights = [...explanatoryWeights].sort(
  (a, b) => n(b.peso_entre_factores_pct) - n(a.peso_entre_factores_pct)
);

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
  "Modelo_ampliado",
  "Pesos_explicativos",
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
  sheet.getRange("A1:AZ400").format.font = { name: "Aptos", color: COLORS.dark };
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

  card(s, "A5:B5", "A6:B7", "Observaciones modelo ampliado", n(expandedComparison.observaciones));
  card(s, "C5:D5", "C6:D7", "R² ajustado principal", pct(baseComparison.r_cuadrado_ajustado));
  card(s, "E5:F5", "E6:F7", "R² ajustado ampliado", pct(expandedComparison.r_cuadrado_ajustado), COLORS.green);
  card(s, "A9:B9", "A10:B11", "MAPE ampliado", `${Number(expandedComparison.mape_pct).toFixed(2)}%`, COLORS.green);
  card(s, "C9:D9", "C10:D11", "Acierto de dirección ampliado", `${Number(expandedComparison.acierto_direccion_pct).toFixed(1)}%`, COLORS.green);
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
    ["Brent", "+10%", "−0,49%", "Aprecia el COP", n(coefRecordByTerm["D.ln_brent.L0"].p_valor), "Consistente con mayor ingreso externo petrolero"],
    ["Índice amplio del dólar", "+1%", "+1,22%", "Deprecia el COP", n(coefRecordByTerm["D.ln_dolar_amplio.L0"].p_valor), "Es el factor con mayor precisión estadística"],
    ["VIX", "+10%", "+0,37%", "Deprecia el COP", n(coefRecordByTerm["D.ln_vix.L0"].p_valor), "Captura episodios globales de aversión al riesgo"],
    ["Remesas, acumulado 12m (t−1)", "+10%", "+2,50%", "Deprecia el COP", n(coefRecordByTerm["D.ln_remesas_12m.L1"].p_valor), "Signo contrario al canal de oferta; probable endogeneidad"],
    ["Diferencial tasas CO−EE. UU. (t−1)", "+1 pp", "−0,99%", "Aprecia el COP", n(coefRecordByTerm["D.diferencial_tasas_pp.L1"].p_valor), "Compatible con un mayor retorno relativo"],
    ["Déficit fiscal 12m/PIB (t−1)", "+1 pp", "+0,43%", "Deprecia el COP", n(coefRecordByTerm["D.deficit_fiscal_12m_pct_pib.L1"].p_valor), "Signo esperado, pero estimación imprecisa"],
    ["Pandemia, mar–may 2020", "Dummy = 1", "+0,82%", "Deprecia el COP", n(coefRecordByTerm.dummy_pandemia_2020.p_valor), "Control de episodio extraordinario"],
    ["Conclusión", "—", "—", "—", null, "Dólar global, petróleo y VIX dominan el movimiento mensual"],
  ];
  header(s, "A19:F19");
  s.getRange("E20:E27").format.numberFormat = "0.0000";
  s.getRange("A19:F27").format.wrapText = true;
  s.getRange("A19:F27").format.borders = { preset: "all", style: "thin", color: "#D9E1F2" };
  s.getRange("A27:F27").format = { fill: COLORS.green, font: { bold: true, color: COLORS.dark }, wrapText: true };

  section(s, "A29:F29", "Alcance y cautelas");
  s.getRange("A30:B37").values = [
    ["1", "La regresión identifica asociaciones dinámicas; no demuestra causalidad."],
    ["2", "La validación es condicional: usa realizaciones contemporáneas de Brent, dólar amplio y VIX; no equivale a un pronóstico en tiempo real."],
    ["3", "Los residuos presentan colas no normales; para inferencia se reportan errores HAC."],
    ["4", "El resultado positivo de remesas puede reflejar respuesta de los hogares a depreciaciones u otros shocks simultáneos."],
    ["5", "La prueba bounds no confirma cointegración al 5%; el ECM se muestra solo como contraste exploratorio."],
    ["6", "El déficit fiscal tiene el signo esperado, pero su p-valor de 0,189 no permite afirmar un efecto distinto de cero al 5%."],
    ["7", "En el modelo ampliado, ARCH-LM tiene p<0,001: persiste volatilidad condicional no explicada."],
    ["8", "Los residuos ampliados tampoco son normales. HAC protege la inferencia sobre la media, pero no sustituye un modelo explícito de volatilidad."],
  ];
  s.mergeCells("B30:F30"); s.mergeCells("B31:F31"); s.mergeCells("B32:F32");
  s.mergeCells("B33:F33"); s.mergeCells("B34:F34"); s.mergeCells("B35:F35"); s.mergeCells("B36:F36"); s.mergeCells("B37:F37");
  s.getRange("A30:F37").format = { fill: COLORS.amber, wrapText: true, borders: { preset: "all", style: "thin", color: "#E6B800" } };
  s.getRange("A30:A37").format = { fill: COLORS.navy, font: { bold: true, color: COLORS.white }, horizontalAlignment: "center", verticalAlignment: "center" };

  section(s, "H29:N29", "Comparación del modelo principal y el ampliado");
  s.getRange("H30:N30").values = [["Modelo", "Obs.", "R² ajustado", "AIC", "BIC", "MAPE", "Dirección"]];
  s.getRange(`H31:N${30 + modelComparison.length}`).values = modelComparison.map((r) => [
    r.modelo,
    n(r.observaciones),
    n(r.r_cuadrado_ajustado),
    n(r.aic),
    n(r.bic),
    n(r.mape_pct) / 100,
    n(r.acierto_direccion_pct) / 100,
  ]);
  header(s, "H30:N30");
  addTable(s, `H30:N${30 + modelComparison.length}`, "ComparacionModelosResumenTable");
  s.getRange(`J31:J${30 + modelComparison.length}`).format.numberFormat = "0.0%";
  s.getRange(`K31:L${30 + modelComparison.length}`).format.numberFormat = "0.00";
  s.getRange(`M31:N${30 + modelComparison.length}`).format.numberFormat = "0.0%";

  section(s, "A38:F38", "Peso explicativo Shapley del modelo ampliado");
  const summaryWeights = orderedWeights.slice(0, 8);
  s.getRange("A39:F39").values = [["Factor", "Grupo", "Contribución al R²", "Peso entre factores", "Peso del R² total", "Lectura"]];
  s.getRange(`A40:F${39 + summaryWeights.length}`).values = summaryWeights.map((r) => [
    r.factor,
    r.grupo,
    n(r.shapley_r2),
    n(r.peso_entre_factores_pct) / 100,
    n(r.peso_r2_total_pct) / 100,
    "Participación explicativa, no efecto causal",
  ]);
  header(s, "A39:F39");
  addTable(s, `A39:F${39 + summaryWeights.length}`, "PesosResumenTable");
  s.getRange(`C40:E${39 + summaryWeights.length}`).format.numberFormat = "0.0%";
  s.getRange(`A39:F${39 + summaryWeights.length}`).format.wrapText = true;
  s.getRange(`A40:F${39 + summaryWeights.length}`).format.rowHeight = 30;

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
  title(s, "A1:AB1", "Datos fuente mensuales");
  subtitle(s, "A2:AB3", "Niveles utilizados para construir los modelos principal y ampliado. Los indicadores diarios se convierten a promedio mensual. Los espacios en blanco representan observaciones no disponibles y nunca se sustituyen por cero. Única excepción: el IPC de EE. UU. de octubre de 2025 se interpola linealmente y se identifica con una bandera visible.");
  const heads = [
    "Mes", "TRM (COP/USD)", "Brent (USD/barril)", "Remesas (USD mill.)", "Remesas 12m (USD mill.)",
    "Tasa política Colombia (%)", "Fed funds (%)", "Diferencial tasas (pp)", "Balance fiscal mensual (miles mill. COP)",
    "Déficit fiscal 12m (% PIB)", "Índice dólar amplio", "VIX", "Términos de intercambio", "Dummy pandemia",
    "Reservas netas sin FLAR (USD mill.)", "TES Colombia 10 años (%)", "Treasury EE. UU. 10 años (%)", "Spread TES−UST (pp)",
    "Balanza comercial cambiaria (USD mill.)", "Flujo neto total de capital (USD mill.)", "IPC Colombia", "IPC EE. UU.",
    "Diferencial inflación interanual (pp)", "BRL por USD", "CLP por USD", "MXN por USD", "Factor monedas regionales", "IPC EE. UU. interpolado",
  ];
  s.getRange("A5:AB5").values = [heads];
  const matrix = raw.map((r) => [
    r.fecha.slice(0, 7), n(r.trm_cop_usd), n(r.brent_usd_barril), n(r.remesas_usd_millones), n(r.remesas_12m_usd_millones),
    n(r.tasa_politica_colombia_pct), n(r.fed_funds_eeuu_pct), n(r.diferencial_tasas_pp), n(r.balance_fiscal_miles_millones_cop),
    n(r.deficit_fiscal_12m_pct_pib), n(r.indice_dolar_amplio), n(r.vix), n(r.terminos_intercambio), n(r.dummy_pandemia_2020),
    n(firstValue(r, "reservas_netas_sin_flar_usd_millones", "reservas_netas_sin_flar_millones_usd")),
    n(firstValue(r, "tes_10y_colombia_pct", "tes_colombia_10y_pct")),
    n(firstValue(r, "treasury_10y_eeuu_pct", "ust_10y_eeuu_pct")),
    n(firstValue(r, "spread_tes_ust_10y_pp", "diferencial_tes_ust_10y_pp")),
    n(firstValue(r, "balanza_comercial_cambiaria_usd_millones", "balance_comercial_cambiario_usd_millones")),
    n(firstValue(r, "flujos_capital_usd_millones", "flujo_neto_total_capital_usd_millones")),
    n(firstValue(r, "ipc_colombia", "ipc_colombia_indice")),
    n(firstValue(r, "ipc_eeuu", "ipc_eeuu_indice")),
    n(firstValue(r, "diferencial_inflacion_pp", "diferencial_inflacion_interanual_pp")),
    n(r.brl_por_usd), n(r.clp_por_usd), n(r.mxn_por_usd), n(r.factor_monedas_regionales), n(r.ipc_eeuu_interpolado),
  ]);
  const end = 5 + matrix.length;
  s.getRange(`A6:AB${end}`).values = matrix;
  header(s, "A5:AB5");
  addTable(s, `A5:AB${end}`, "DatosFuenteTable");
  s.getRange(`B6:E${end}`).format.numberFormat = "#,##0.00";
  s.getRange(`F6:H${end}`).format.numberFormat = "0.00";
  s.getRange(`I6:I${end}`).format.numberFormat = "#,##0.00;[Red]-#,##0.00";
  s.getRange(`J6:M${end}`).format.numberFormat = "0.00";
  s.getRange(`N6:N${end}`).format.numberFormat = "0";
  s.getRange(`O6:O${end}`).format.numberFormat = "#,##0.00";
  s.getRange(`P6:R${end}`).format.numberFormat = "0.00";
  s.getRange(`S6:T${end}`).format.numberFormat = "#,##0.00;[Red]-#,##0.00";
  s.getRange(`U6:W${end}`).format.numberFormat = "0.00";
  s.getRange(`X6:Z${end}`).format.numberFormat = "#,##0.0000";
  s.getRange(`AA6:AA${end}`).format.numberFormat = "0.000000";
  s.getRange(`AB6:AB${end}`).format.numberFormat = "0";
  s.getRange(`AB6:AB${end}`).conditionalFormats.add("cellIs", { operator: "equal", formula: 1, format: { fill: COLORS.amber, font: { bold: true, color: COLORS.dark } } });
  s.getRange(`A5:AB${end}`).format.verticalAlignment = "center";
  s.getRange("A:A").format.columnWidth = 12;
  s.getRange("B:C").format.columnWidth = 16;
  s.getRange("D:E").format.columnWidth = 18;
  s.getRange("F:H").format.columnWidth = 16;
  s.getRange("I:I").format.columnWidth = 24;
  s.getRange("J:N").format.columnWidth = 18;
  s.getRange("O:W").format.columnWidth = 21;
  s.getRange("X:AB").format.columnWidth = 18;
  s.getRange("A5:AB5").format.rowHeight = 54;
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
    O5: "Fuente: Banco de la República, reservas internacionales netas sin FLAR, serie 15053.",
    P5: "Fuente: Banco de la República, tasa cero cupón TES en pesos a 10 años, serie 15274; promedio mensual.",
    Q5: "Fuente: U.S. Treasury/FRED, DGS10; promedio mensual de observaciones diarias.",
    R5: "Construcción: TES Colombia 10 años menos Treasury de EE. UU. a 10 años.",
    S5: "Fuente: Banco de la República, balanza comercial cambiaria, serie 16702.",
    T5: "Fuente: Banco de la República, flujo neto total de capital, serie 16706.",
    U5: "Fuente: Banco de la República, IPC total nacional, serie 15000.",
    V5: "Fuente: U.S. Bureau of Labor Statistics/FRED, CPIAUCNS. Octubre de 2025 se interpola linealmente por ser la única observación interna faltante.",
    W5: "Construcción: inflación interanual de Colombia menos inflación interanual de EE. UU., en puntos porcentuales.",
    X5: "Fuente: OECD vía FRED, CCUSMA02BRM618N; reales brasileños por dólar.",
    Y5: "Fuente: OECD vía FRED, CCUSMA02CLM618N; pesos chilenos por dólar.",
    Z5: "Fuente: OECD vía FRED, CCUSMA02MXM618N; pesos mexicanos por dólar.",
    AA5: "Construcción: promedio igual ponderado de los retornos mensuales estandarizados de BRL, CLP y MXN por USD. Las medias y desviaciones se calibran con 2006–2019.",
    AB5: "Bandera de trazabilidad: 1 únicamente en octubre de 2025, cuando CPIAUCNS se interpola linealmente para no cortar el diferencial de inflación interanual; 0 en los demás meses.",
  };
  for (const [cell, text] of Object.entries(comments)) wb.comments.addThread({ cell: s.getRange(cell) }, text);
}

// Transformaciones auditables
{
  const s = sheets.Transformaciones;
  title(s, "A1:AA1", "Transformaciones del modelo");
  subtitle(s, "A2:AA3", "Todas las transformaciones son fórmulas enlazadas a Datos_fuente. Δ indica cambio mensual; ln indica logaritmo natural; asinh conserva el signo de los flujos y reduce el peso de valores extremos. Los rezagos se aplican al estimar cada especificación.");
  const heads = [
    "Mes", "ln TRM", "Δln TRM", "ln Brent", "Δln Brent", "ln remesas 12m", "Δln remesas 12m", "Diferencial tasas", "Δ diferencial", "Déficit 12m/PIB", "Δ déficit", "ln dólar amplio", "Δln dólar amplio", "ln VIX", "Δln VIX", "Pandemia",
    "ln reservas netas sin FLAR", "Δln reservas", "Spread TES−UST 10 años", "Δ spread TES−UST", "asinh balanza (USD miles de millones)", "Δ asinh balanza", "asinh flujos (USD miles de millones)", "Δ asinh flujos", "Diferencial inflación", "Δ diferencial inflación", "Factor regional estandarizado",
  ];
  s.getRange("A5:AA5").values = [heads];
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
      `=IF('Datos_fuente'!O${src}="","",LN('Datos_fuente'!O${src}))`,
      first ? "" : `=IF(OR(Q${r}="",Q${r - 1}=""),"",Q${r}-Q${r - 1})`,
      `='Datos_fuente'!R${src}`,
      first ? "" : `=IF(OR(S${r}="",S${r - 1}=""),"",S${r}-S${r - 1})`,
      `=IF('Datos_fuente'!S${src}="","",ASINH('Datos_fuente'!S${src}/1000))`,
      first ? "" : `=IF(OR(U${r}="",U${r - 1}=""),"",U${r}-U${r - 1})`,
      `=IF('Datos_fuente'!T${src}="","",ASINH('Datos_fuente'!T${src}/1000))`,
      first ? "" : `=IF(OR(W${r}="",W${r - 1}=""),"",W${r}-W${r - 1})`,
      `='Datos_fuente'!W${src}`,
      first ? "" : `=IF(OR(Y${r}="",Y${r - 1}=""),"",Y${r}-Y${r - 1})`,
      `='Datos_fuente'!AA${src}`,
    ];
  });
  const end = 5 + formulas.length;
  s.getRange(`A6:AA${end}`).formulas = formulas;
  header(s, "A5:AA5");
  addTable(s, `A5:AA${end}`, "TransformacionesTable");
  s.getRange(`B6:G${end}`).format.numberFormat = "0.000000";
  s.getRange(`H6:K${end}`).format.numberFormat = "0.0000";
  s.getRange(`L6:O${end}`).format.numberFormat = "0.000000";
  s.getRange(`P6:P${end}`).format.numberFormat = "0";
  s.getRange(`Q6:R${end}`).format.numberFormat = "0.000000";
  s.getRange(`S6:T${end}`).format.numberFormat = "0.0000";
  s.getRange(`U6:X${end}`).format.numberFormat = "0.000000";
  s.getRange(`Y6:Z${end}`).format.numberFormat = "0.0000";
  s.getRange(`AA6:AA${end}`).format.numberFormat = "0.000000";
  s.getRange("A:A").format.columnWidth = 12;
  s.getRange("B:AA").format.columnWidth = 18;
  s.getRange("A5:AA5").format.rowHeight = 48;
  s.freezePanes.freezeRows(5);
  s.freezePanes.freezeColumns(1);
  wb.comments.addThread({ cell: s.getRange("U5") }, "Escala auditable: el flujo original en USD millones se divide por 1.000 antes de aplicar asinh, igual que en la estimación en Python.");
  wb.comments.addThread({ cell: s.getRange("W5") }, "Escala auditable: el flujo original en USD millones se divide por 1.000 antes de aplicar asinh, igual que en la estimación en Python.");
  wb.comments.addThread({ cell: s.getRange("AA5") }, "Promedio igual ponderado de retornos mensuales estandarizados de BRL, CLP y MXN por USD. Medias y desviaciones calibradas entre enero de 2006 y diciembre de 2019.");
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
      `=$B$${coefRowByTerm.const}`,
      `=$B$${coefRowByTerm["D.ln_brent.L0"]}*'Transformaciones'!E${tr}`,
      `=$B$${coefRowByTerm["D.ln_dolar_amplio.L0"]}*'Transformaciones'!M${tr}`,
      `=$B$${coefRowByTerm["D.ln_vix.L0"]}*'Transformaciones'!O${tr}`,
      `=$B$${coefRowByTerm["D.ln_remesas_12m.L1"]}*'Transformaciones'!G${tr - 1}`,
      `=$B$${coefRowByTerm["D.diferencial_tasas_pp.L1"]}*'Transformaciones'!I${tr - 1}`,
      `=$B$${coefRowByTerm["D.deficit_fiscal_12m_pct_pib.L1"]}*'Transformaciones'!K${tr - 1}`,
      `=$B$${coefRowByTerm.dummy_pandemia_2020}*'Transformaciones'!P${tr}`,
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

// Modelo ampliado
{
  const s = sheets.Modelo_ampliado;
  title(s, "A1:W1", "Modelo ampliado: nuevos canales domésticos y regionales");
  subtitle(
    s,
    "A2:W3",
    "Extiende el modelo principal con una prima local amplia, reservas, balanza comercial cambiaria, flujos de capital, diferencial de inflación y un factor de monedas regionales. Los coeficientes y pesos describen asociaciones; no identifican efectos causales.",
    COLORS.paleBlue
  );

  s.getRange("A5:G5").values = [["Variable", "Coeficiente", "EE HAC", "t", "p-valor", "IC 95% inferior", "IC 95% superior"]];
  const expandedCoefEnd = 5 + expandedCoefs.length;
  s.getRange(`A6:G${expandedCoefEnd}`).values = expandedCoefs.map((r) => [
    termLabel(r.termino),
    n(r.coeficiente),
    n(r.error_estandar_hac),
    n(r.estadistico_t),
    n(r.p_valor),
    n(r.ic_95_inferior),
    n(r.ic_95_superior),
  ]);
  header(s, "A5:G5");
  addTable(s, `A5:G${expandedCoefEnd}`, "CoeficientesModeloAmpliadoTable");
  s.getRange(`B6:G${expandedCoefEnd}`).format.numberFormat = "0.000000";
  s.getRange(`E6:E${expandedCoefEnd}`).conditionalFormats.add("cellIs", {
    operator: "lessThan",
    formula: 0.05,
    format: { fill: COLORS.green, font: { bold: true, color: "#006100" } },
  });

  s.getRange("I5:N5").values = [["Indicador", "Valor", "Lectura", "Indicador", "Valor", "Lectura"]];
  s.getRange("I6:N9").values = [
    ["R²", n(expandedComparison.r_cuadrado), "Variación explicada dentro de muestra", "AIC", n(expandedComparison.aic), "Comparación relativa"],
    ["R² ajustado", n(expandedComparison.r_cuadrado_ajustado), "Penaliza el número de parámetros", "BIC", n(expandedComparison.bic), "Comparación relativa"],
    ["Observaciones", n(expandedComparison.observaciones), "Muestra común completa", "MAPE condicional", n(expandedComparison.mape_pct) / 100, "Ventana de validación"],
    ["Acierto dirección", n(expandedComparison.acierto_direccion_pct) / 100, "Signo del cambio mensual", "Inferencia", "HAC", "Errores robustos"],
  ];
  header(s, "I5:N5");
  s.getRange("I5:N9").format = { wrapText: true, borders: { preset: "all", style: "thin", color: "#D9E1F2" } };
  s.getRange("J6:J7").format.numberFormat = "0.0%";
  s.getRange("J9:J9").format.numberFormat = "0.0%";
  s.getRange("M6:M7").format.numberFormat = "0.00";
  s.getRange("M8:M8").format.numberFormat = "0.0%";

  section(s, "I12:L12", "Diagnósticos del modelo ampliado");
  s.getRange("I13:L13").values = [["Prueba", "Estadístico", "p-valor", "Lectura"]];
  const expandedDiagRows = expandedDiagnostics.map((r) => {
    const p = n(r.p_valor);
    let reading = "Referencia";
    if (/Jarque/i.test(r.prueba)) reading = p < 0.05 ? "Residuos no normales" : "No se rechaza normalidad";
    else if (/Durbin/i.test(r.prueba)) reading = "Cercano a 2";
    else if (/CUSUM/i.test(r.prueba)) reading = p >= 0.05 ? "Sin inestabilidad detectada" : "Posible inestabilidad";
    else if (/RESET/i.test(r.prueba)) reading = p >= 0.05 ? "Sin evidencia de mala forma funcional" : "Revisar forma funcional";
    else if (/ARCH/i.test(r.prueba)) reading = p >= 0.05 ? "Sin ARCH detectado" : "Heterocedasticidad condicional";
    else reading = p >= 0.05 ? "Sin autocorrelación detectada" : "Autocorrelación residual";
    return [r.prueba, n(r.estadistico), p, reading];
  });
  const expandedDiagEnd = 13 + expandedDiagRows.length;
  s.getRange(`I14:L${expandedDiagEnd}`).values = expandedDiagRows;
  header(s, "I13:L13");
  addTable(s, `I13:L${expandedDiagEnd}`, "DiagnosticosModeloAmpliadoTable");
  s.getRange(`J14:K${expandedDiagEnd}`).format.numberFormat = "0.0000";

  const contributionKeys = Object.keys(expandedContributions[0] ?? {}).filter((key) => key !== "fecha");
  const contributionByDate = new Map(expandedContributions.map((r) => [r.fecha, r]));
  const contributionHeaders = contributionKeys.map((key) => key === "ajuste_total" ? "Ajuste total de contribuciones" : termLabel(key));
  const fitHeaderRow = Math.max(22, expandedCoefEnd + 3, expandedDiagEnd + 3);
  const expandedHeads = [
    "Mes", "Δln TRM observado", "Δln TRM ajustado", "Residuo", "TRM observada", "TRM ajustada 1 paso",
    ...contributionHeaders,
    "Diferencia de control",
  ];
  const expandedLastCol = columnLetter(expandedHeads.length);
  s.getRange(`A${fitHeaderRow}:${expandedLastCol}${fitHeaderRow}`).values = [expandedHeads];
  const expandedRows = expandedFit.map((r) => {
    const contributions = contributionByDate.get(r.fecha) ?? {};
    return [
      r.fecha.slice(0, 7),
      n(r.cambio_log_observado),
      n(r.cambio_log_ajustado),
      n(r.residuo_cambio_log),
      n(r.trm_observada),
      n(r.trm_ajustada_un_paso),
      ...contributionKeys.map((key) => n(contributions[key])),
      null,
    ];
  });
  const expandedDataStart = fitHeaderRow + 1;
  const expandedDataEnd = fitHeaderRow + expandedRows.length;
  s.getRange(`A${expandedDataStart}:${expandedLastCol}${expandedDataEnd}`).values = expandedRows;
  const adjustmentIndex = contributionKeys.indexOf("ajuste_total");
  if (adjustmentIndex >= 0) {
    const adjustmentCol = columnLetter(7 + adjustmentIndex);
    s.getRange(`${expandedLastCol}${expandedDataStart}:${expandedLastCol}${expandedDataEnd}`).formulas = expandedRows.map((_, i) => {
      const row = expandedDataStart + i;
      return [`=C${row}-${adjustmentCol}${row}`];
    });
  }
  header(s, `A${fitHeaderRow}:${expandedLastCol}${fitHeaderRow}`);
  addTable(s, `A${fitHeaderRow}:${expandedLastCol}${expandedDataEnd}`, "AjusteModeloAmpliadoTable");
  s.getRange(`B${expandedDataStart}:D${expandedDataEnd}`).format.numberFormat = "0.000000";
  s.getRange(`E${expandedDataStart}:F${expandedDataEnd}`).format.numberFormat = "#,##0.00";
  if (expandedHeads.length > 6) s.getRange(`G${expandedDataStart}:${expandedLastCol}${expandedDataEnd}`).format.numberFormat = "0.000000";
  s.getRange(`${expandedLastCol}${expandedDataStart}:${expandedLastCol}${expandedDataEnd}`).format.fill = COLORS.paleBlue;

  const expandedChart = s.charts.add("line", { chartType: "line", title: "TRM observada y ajuste ampliado", hasLegend: true });
  const observedSeries = expandedChart.series.add("TRM observada");
  observedSeries.categoryFormula = `'Modelo_ampliado'!$A$${expandedDataStart}:$A$${expandedDataEnd}`;
  observedSeries.formula = `'Modelo_ampliado'!$E$${expandedDataStart}:$E$${expandedDataEnd}`;
  observedSeries.fill = COLORS.navy;
  const fittedSeries = expandedChart.series.add("TRM ajustada");
  fittedSeries.categoryFormula = `'Modelo_ampliado'!$A$${expandedDataStart}:$A$${expandedDataEnd}`;
  fittedSeries.formula = `'Modelo_ampliado'!$F$${expandedDataStart}:$F$${expandedDataEnd}`;
  fittedSeries.fill = COLORS.teal;
  expandedChart.titleTextStyle.fontSize = 12;
  expandedChart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 8 } };
  expandedChart.yAxis = { numberFormatCode: "#,##0" };
  expandedChart.setPosition("O5", "W18");

  s.getRange("A:A").format.columnWidth = 12;
  s.getRange("B:G").format.columnWidth = 18;
  // H is a spacer in the upper panel but contains the Brent contribution in
  // the detailed table, so it must remain wide enough for numeric values.
  s.getRange("H:H").format.columnWidth = 18;
  s.getRange("I:N").format.columnWidth = 18;
  s.getRange("O:W").format.columnWidth = 13;
  s.getRange(`A${fitHeaderRow}:${expandedLastCol}${fitHeaderRow}`).format.rowHeight = 48;
  s.getRange(`A5:${expandedLastCol}${expandedDataEnd}`).format.wrapText = true;
  s.freezePanes.freezeRows(fitHeaderRow);
  s.freezePanes.freezeColumns(1);
}

// Pesos explicativos
{
  const s = sheets.Pesos_explicativos;
  title(s, "A1:R1", "Peso explicativo de cada factor: descomposición Shapley del R²");
  subtitle(
    s,
    "A2:R3",
    "La descomposición reparte el R² incremental entre factores promediando todos los órdenes posibles de entrada. Así distribuye la información compartida entre variables correlacionadas. Es una medida descriptiva dentro de muestra, no una participación causal ni una garantía de pronóstico.",
    COLORS.amber
  );

  const weightsStart = 11;
  const weightsEnd = weightsStart + orderedWeights.length - 1;
  section(s, "A5:B5", "Control de suma Shapley");
  s.getRange("A6:B8").values = [["Suma Shapley", null], ["R² incremental", null], ["Diferencia", null]];
  section(s, "D5:E5", "Reconciliación del R²");
  s.getRange("D6:E8").values = [["R² base + incremental", null], ["R² completo", null], ["Diferencia", null]];
  section(s, "G5:H5", "Control de participaciones");
  s.getRange("G6:H8").values = [["Suma peso entre factores", null], ["Porción del R² total", null], ["Diferencia frente a 100%", null]];

  s.getRange("A10:H10").values = [[
    "Factor", "Grupo", "Shapley R²", "Peso entre factores", "Peso del R² total", "R² base", "R² completo", "R² incremental",
  ]];
  s.getRange(`A${weightsStart}:H${weightsEnd}`).values = orderedWeights.map((r) => [
    r.factor,
    r.grupo,
    n(r.shapley_r2),
    n(r.peso_entre_factores_pct) / 100,
    n(r.peso_r2_total_pct) / 100,
    n(r.r2_base),
    n(r.r2_completo),
    n(r.r2_incremental),
  ]);
  header(s, "A10:H10");
  addTable(s, `A10:H${weightsEnd}`, "PesosExplicativosTable");
  s.getRange(`C${weightsStart}:H${weightsEnd}`).format.numberFormat = "0.0%";
  s.getRange(`A10:H${weightsEnd}`).format.wrapText = true;
  s.getRange(`A${weightsStart}:H${weightsEnd}`).format.rowHeight = 30;

  s.getRange("B6:B8").formulas = [
    [`=SUM(C${weightsStart}:C${weightsEnd})`],
    [`=MAX(H${weightsStart}:H${weightsEnd})`],
    ["=B6-B7"],
  ];
  s.getRange("E6:E8").formulas = [
    [`=MAX(F${weightsStart}:F${weightsEnd})+MAX(H${weightsStart}:H${weightsEnd})`],
    [`=MAX(G${weightsStart}:G${weightsEnd})`],
    ["=E6-E7"],
  ];
  s.getRange("H6:H8").formulas = [
    [`=SUM(D${weightsStart}:D${weightsEnd})`],
    [`=SUM(E${weightsStart}:E${weightsEnd})`],
    ["=H6-1"],
  ];
  s.getRange("A6:B8").format = { borders: { preset: "all", style: "thin", color: "#D9E1F2" }, wrapText: true };
  s.getRange("D6:E8").format = { borders: { preset: "all", style: "thin", color: "#D9E1F2" }, wrapText: true };
  s.getRange("G6:H8").format = { borders: { preset: "all", style: "thin", color: "#D9E1F2" }, wrapText: true };
  s.getRange("B6:B8").format.numberFormat = "0.0000%";
  s.getRange("E6:E8").format.numberFormat = "0.0000%";
  s.getRange("H6:H8").format.numberFormat = "0.0000%";
  for (const cell of ["B8", "E8", "H8"]) {
    s.getRange(cell).conditionalFormats.add("cellIs", {
      operator: "between",
      formula: [-0.00000001, 0.00000001],
      format: { fill: COLORS.green, font: { bold: true, color: "#006100" } },
    });
  }

  const weightsChart = s.charts.add("bar", { chartType: "bar", title: "Participación de cada factor en la explicación incremental", hasLegend: false });
  const weightSeries = weightsChart.series.add("Peso entre factores");
  weightSeries.categoryFormula = `'Pesos_explicativos'!$A$${weightsStart}:$A$${weightsEnd}`;
  weightSeries.formula = `'Pesos_explicativos'!$D$${weightsStart}:$D$${weightsEnd}`;
  weightSeries.fill = COLORS.blue;
  weightsChart.titleTextStyle.fontSize = 12;
  weightsChart.yAxis = { numberFormatCode: "0%" };
  weightsChart.setPosition("J5", "R24");

  const noteRow = weightsEnd + 2;
  subtitle(
    s,
    `A${noteRow}:H${noteRow + 2}`,
    "Cómo leer: un peso de 25% indica que ese factor recibe una cuarta parte del R² incremental atribuible al conjunto de factores. Con variables correlacionadas, Shapley divide la explicación compartida al promediar todas las secuencias de inclusión.",
    COLORS.paleGray
  );
  s.getRange("A:A").format.columnWidth = 32;
  s.getRange("B:B").format.columnWidth = 22;
  s.getRange("C:H").format.columnWidth = 18;
  s.getRange("I:I").format.columnWidth = 3;
  s.getRange("J:R").format.columnWidth = 12;
  s.freezePanes.freezeRows(10);
  s.freezePanes.freezeColumns(2);
}

// Validación
{
  const s = sheets.Validacion;
  title(s, "A1:R1", "Validación condicional pseudo-fuera de muestra");
  subtitle(s, "A2:R3", "Ventana expansiva de 48 meses (mayo de 2022–abril de 2026). La evaluación es condicional: usa valores contemporáneos ya realizados de Brent, dólar amplio, VIX, spread TES−UST y monedas regionales. Es una prueba explicativa, no un pronóstico genuinamente disponible en tiempo real.", COLORS.amber);

  s.getRange("A5:F5").values = [["Modelo", "Observaciones", "MAE (log)", "RMSE (log)", "MAPE", "Acierto dirección"]];
  const displayedValidationMetrics = [
    ["Modelo principal", modelMetric],
    ["Modelo ampliado", expandedModelMetric],
    ["Caminata aleatoria", rwMetric],
  ];
  s.getRange("A6:F8").values = displayedValidationMetrics.map(([label, r]) => [label, n(r.observaciones), n(r.mae_log), n(r.rmse_log), n(r.mape_pct) / 100, n(r.acierto_direccion_pct) === null ? null : n(r.acierto_direccion_pct) / 100]);
  header(s, "A5:F5");
  addTable(s, "A5:F8", "MetricasValidacionTable");
  s.getRange("C6:D8").format.numberFormat = "0.0000";
  s.getRange("E6:F8").format.numberFormat = "0.0%";
  s.getRange("A6:F6").format.fill = COLORS.paleBlue;
  s.getRange("A7:F7").format.fill = COLORS.green;
  s.getRange("A6:F8").format.rowHeight = 30;

  s.getRange("H5:J5").values = [["Comparación", "Resultado", "Lectura"]];
  s.getRange("H6:J9").values = [
    ["Reducción de MAE ampliado", 1 - n(expandedModelMetric.mae_log) / n(rwMetric.mae_log), "Mejora frente a la caminata aleatoria"],
    ["Reducción de RMSE ampliado", 1 - n(expandedModelMetric.rmse_log) / n(rwMetric.rmse_log), "Mejora frente a la caminata aleatoria"],
    ["Dirección correcta ampliado", n(expandedModelMetric.acierto_direccion_pct) / 100, "Signo mensual acertado"],
    ["Mejora de MAPE vs. principal (p.p.)", n(modelMetric.mape_pct) - n(expandedModelMetric.mape_pct), "Diferencia en puntos porcentuales; positivo indica mejora"],
  ];
  header(s, "H5:J5");
  s.getRange("H5:J9").format.borders = { preset: "all", style: "thin", color: "#D9E1F2" };
  s.getRange("I6:I9").format.numberFormat = "0.0%";
  s.getRange("I9").format.numberFormat = "0.00 \"p.p.\"";
  s.getRange("H5:J9").format.wrapText = true;
  s.getRange("H6:J9").format.rowHeight = 38;

  const baseHeads = ["Mes", "ln TRM observada", "ln TRM modelo principal", "ln TRM caminata", "Δln observado", "Δln modelo principal", "TRM observada", "TRM modelo principal", "TRM caminata"];
  const expandedHeads = ["Mes", "ln TRM observada", "ln TRM modelo ampliado", "ln TRM caminata", "Δln observado", "Δln modelo ampliado", "TRM observada", "TRM modelo ampliado", "TRM caminata"];
  s.getRange("A11:I11").values = [baseHeads];
  const valRows = validationPredictions.map((r) => [
    r.fecha.slice(0, 7), n(r.ln_trm_observada), n(r.ln_trm_modelo_condicional), n(r.ln_trm_caminata_aleatoria), n(r.cambio_log_observado), n(r.cambio_log_modelo), n(r.trm_observada), n(r.trm_modelo_condicional), n(r.trm_caminata_aleatoria),
  ]);
  const valEnd = 11 + valRows.length;
  const expandedValHeader = valEnd + 3;
  const expandedValRows = expandedValidationPredictions.map((r) => [
    r.fecha.slice(0, 7),
    n(r.ln_trm_observada),
    n(firstValue(r, "ln_trm_modelo_condicional", "ln_trm_modelo_ampliado_condicional")),
    n(r.ln_trm_caminata_aleatoria),
    n(r.cambio_log_observado),
    n(firstValue(r, "cambio_log_modelo", "cambio_log_modelo_ampliado")),
    n(r.trm_observada),
    n(firstValue(r, "trm_modelo_condicional", "trm_modelo_ampliado_condicional")),
    n(r.trm_caminata_aleatoria),
  ]);
  const expandedValEnd = expandedValHeader + expandedValRows.length;
  s.getRange(`A12:I${valEnd}`).values = valRows;
  header(s, "A11:I11");
  addTable(s, `A11:I${valEnd}`, "PrediccionesValidacionTable");
  s.getRange(`B12:F${valEnd}`).format.numberFormat = "0.000000";
  s.getRange(`G12:I${valEnd}`).format.numberFormat = "#,##0.00";

  s.getRange("K25:O25").values = [["Mes", "TRM observada", "Modelo principal condicional", "Modelo ampliado condicional", "Caminata aleatoria"]];
  s.getRange(`K26:O${25 + valRows.length}`).formulas = valRows.map((_, i) => {
    const r = 12 + i;
    const expandedRow = expandedValHeader + 1 + i;
    return [`=A${r}`, `=G${r}`, `=H${r}`, `=H${expandedRow}`, `=I${r}`];
  });
  header(s, "K25:O25");
  s.getRange(`L26:O${25 + valRows.length}`).format.numberFormat = "#,##0";
  const chart = s.charts.add("line", s.getRange(`K25:O${25 + valRows.length}`));
  chart.title = "Validación condicional: observada, modelos y caminata";
  chart.titleTextStyle.fontSize = 12;
  chart.hasLegend = true;
  chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 8 } };
  chart.yAxis = { numberFormatCode: "#,##0" };
  chart.setPosition("K5", "R22");

  section(s, `A${expandedValHeader - 1}:I${expandedValHeader - 1}`, "Predicciones condicionales del modelo ampliado");
  s.getRange(`A${expandedValHeader}:I${expandedValHeader}`).values = [expandedHeads];
  s.getRange(`A${expandedValHeader + 1}:I${expandedValEnd}`).values = expandedValRows;
  header(s, `A${expandedValHeader}:I${expandedValHeader}`);
  addTable(s, `A${expandedValHeader}:I${expandedValEnd}`, "PrediccionesValidacionAmpliadaTable");
  s.getRange(`B${expandedValHeader + 1}:F${expandedValEnd}`).format.numberFormat = "0.000000";
  s.getRange(`G${expandedValHeader + 1}:I${expandedValEnd}`).format.numberFormat = "#,##0.00";

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
  subtitle(s, "A2:N3", "Las pruebas se interpretan al 5%. No se detecta autocorrelación residual. El modelo principal no muestra ARCH, pero el ampliado sí presenta volatilidad condicional; la no normalidad aconseja mantener inferencia HAC y cautela en episodios extremos.");

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

  section(s, "J14:M14", "Diagnósticos del modelo ampliado");
  s.getRange("J15:M15").values = [["Prueba", "Estadístico", "p-valor", "Lectura"]];
  const expandedDiagnosticRows = expandedDiagnostics.map((r) => {
    const p = n(r.p_valor);
    let reading = "Referencia";
    if (/Jarque/i.test(r.prueba)) reading = p < 0.05 ? "Residuos no normales" : "No se rechaza normalidad";
    else if (/ARCH/i.test(r.prueba)) reading = p < 0.05 ? "Volatilidad condicional pendiente" : "Sin ARCH detectado";
    else if (/CUSUM/i.test(r.prueba)) reading = p >= 0.05 ? "Sin inestabilidad detectada" : "Posible inestabilidad";
    else if (/RESET/i.test(r.prueba)) reading = p >= 0.05 ? "Forma funcional aceptable" : "Revisar forma funcional";
    else if (/Durbin/i.test(r.prueba)) reading = "Cercano a 2";
    else reading = p >= 0.05 ? "Sin autocorrelación detectada" : "Autocorrelación residual";
    return [r.prueba, n(r.estadistico), p, reading];
  });
  const expandedDiagnosticEnd = 15 + expandedDiagnosticRows.length;
  s.getRange(`J16:M${expandedDiagnosticEnd}`).values = expandedDiagnosticRows;
  header(s, "J15:M15");
  addTable(s, `J15:M${expandedDiagnosticEnd}`, "DiagnosticosAmpliadosTable");
  s.getRange(`K16:L${expandedDiagnosticEnd}`).format.numberFormat = "0.0000";
  for (let i = 0; i < expandedDiagnostics.length; i += 1) {
    if (/ARCH|Jarque/i.test(expandedDiagnostics[i].prueba)) s.getRange(`J${16 + i}:M${16 + i}`).format.fill = COLORS.red;
  }
  subtitle(s, `J${expandedDiagnosticEnd + 2}:N${expandedDiagnosticEnd + 4}`, "HAC protege la inferencia sobre la ecuación de media frente a heterocedasticidad y autocorrelación moderadas; no modela la dinámica de volatilidad detectada por ARCH-LM.", COLORS.amber);

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
  subtitle(s, "A2:I3", "El modelo principal conserva el núcleo parsimonioso; el ampliado integra seis canales adicionales. La comparación y los pesos Shapley permiten evaluar cuánto añaden sin confundir asociación con causalidad.");
  const rows = [
    ["Objetivo", "TRM promedio mensual", "Modelo principal", "COP por USD", "Δln", "+ = depreciación", "Variable dependiente", "Precio del dólar en Colombia", "Promedios mensuales ocultan movimientos diarios"],
    ["Commodities", "Brent", "Modelo principal", "USD/barril", "Δln contemporáneo", "−", "Ingreso externo", "Exportaciones, IED e ingresos fiscales", "No acompañar con términos de intercambio en el núcleo"],
    ["Divisas", "Remesas recibidas", "Modelo principal", "Acumulado 12m en USD", "Δln, rezago 1", "− esperado", "Oferta de divisas", "Flujo estable de dólares", "Puede responder a la propia depreciación"],
    ["Monetario", "Diferencial tasas CO−EE. UU.", "Modelo principal", "Tasa política − Fed funds", "Δ pp, rezago 1", "−", "Retorno relativo", "Carry e ingreso de capital", "Tasas nominales; endógenas a inflación y TRM"],
    ["Fiscal", "Déficit GNC", "Modelo principal", "Acumulado 12m / PIB", "Δ pp, rezago 1", "+", "Riesgo fiscal", "Financiación y prima de riesgo", "Dato observado no es un shock fiscal exógeno"],
    ["Global", "Índice amplio del dólar", "Modelo principal", "Fed DTWEXBGS", "Δln contemporáneo", "+", "Fortaleza global USD", "Factor global común", "No es el DXY comercial de ICE"],
    ["Global", "VIX", "Modelo principal", "Promedio mensual", "Δln contemporáneo", "+", "Aversión al riesgo", "Risk-off y salida de emergentes", "Correlacionado con dólar global"],
    ["Externo", "Términos de intercambio", "Robustez alta", "BanRep 15360", "Δln", "−", "Poder de compra externo", "Incluye más exportaciones que petróleo", "Sustituir a Brent, no sumarlo automáticamente"],
    ["Riesgo", "Spread TES−UST a 10 años", "Modelo ampliado", "BanRep 15274 − FRED DGS10", "Δ pp, contemporáneo", "+", "Prima local amplia", "Prima exigida a activos colombianos", "Combina riesgo país, duración y expectativas de tasas"],
    ["Reservas", "Reservas internacionales netas sin FLAR", "Modelo ampliado", "BanRep 15053", "Δln, rezago 1", "−", "Colchón externo", "Capacidad de intervención y liquidez", "La acumulación de reservas puede responder a la TRM"],
    ["Comercio", "Balanza comercial cambiaria", "Modelo ampliado", "BanRep 16702", "Δ asinh, rezago 1", "−", "Oferta neta de divisas", "Exportaciones menos importaciones canalizadas", "Es simultánea con la depreciación"],
    ["Precios", "Inflación observada CO−EE. UU.", "Modelo ampliado", "BanRep 15000 − FRED CPIAUCNS", "Diferencial interanual, rezago 1", "+", "Paridad de poder de compra", "Presiones relativas de precios", "Proxy observada, no expectativa de inflación"],
    ["Mercado", "Monedas regionales", "Modelo ampliado", "BRL, CLP y MXN por USD", "Promedio igual de z(Δln), base 2006–2019", "+", "Contagio regional", "Captura shocks latinoamericanos comunes", "Comparte información con VIX y dólar global"],
    ["Flujos", "Flujo neto total de capital", "Modelo ampliado", "BanRep 16706", "Δ asinh, rezago 1", "−", "Demanda de activos COP", "Resume entradas y salidas de capital", "Altamente endógeno y volátil"],
    ["Riesgo", "EMBI/CDS Colombia", "Extensión futura", "Spread soberano", "Nivel o Δ", "+", "Riesgo específico", "Fiscal, político y refinanciación", "Sin descarga oficial pública estable para toda la muestra"],
    ["Política", "Intervención cambiaria", "Extensión futura", "Compras/ventas BanRep", "USD, rezago", "+ compras", "Demanda oficial de USD", "Importante en episodios puntuales", "Respuesta de política, no shock puro"],
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
    if (status === "Modelo principal") s.getRange(`C${row}`).format.fill = COLORS.green;
    else if (status === "Modelo ampliado") s.getRange(`C${row}`).format.fill = COLORS.paleBlue;
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
  subtitle(s, "A2:G3", "Enlaces oficiales o distribuidores públicos de las series. La columna Uso distingue el modelo principal, el ampliado, las pruebas de robustez y la documentación.");
  const rows = [
    ["Banco de la República", "TRM diaria, serie 1", "Diaria → mensual", "1991–2026", "Modelo principal", "Promedio mensual", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=1"],
    ["Banco de la República", "Tasa de política, serie 59", "Diaria → mensual", "1998–2026", "Modelo principal", "Promedio mensual", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=59"],
    ["Banco de la República", "Remesas, serie 15363", "Mensual", "2000–2026", "Modelo principal", "Acumulado móvil 12 meses", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15363"],
    ["Ministerio de Hacienda", "Balance fiscal GNC", "Mensual", "2004–2026", "Modelo principal", "Balance de caja; déficit positivo tras cambiar signo", "https://www.minhacienda.gov.co/documents/d/portal/balance-fiscal-gnc-mensual-y-trimestral?download=true"],
    ["U.S. EIA / FRED", "Brent DCOILBRENTEU", "Diaria → mensual", "1987–2026", "Modelo principal", "Promedio mensual, USD por barril", "https://fred.stlouisfed.org/series/DCOILBRENTEU"],
    ["U.S. EIA", "Brent RBRTE", "Mensual", "1987–2026", "Verificación", "Referencia mensual equivalente", "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?f=M&n=PET&s=RBRTE"],
    ["Federal Reserve / FRED", "Federal funds FEDFUNDS", "Mensual", "1954–2026", "Modelo principal", "Promedio mensual", "https://fred.stlouisfed.org/series/FEDFUNDS"],
    ["Federal Reserve / FRED", "Índice amplio USD DTWEXBGS", "Diaria → mensual", "2006–2026", "Modelo principal", "Índice nominal amplio", "https://fred.stlouisfed.org/series/DTWEXBGS"],
    ["Cboe / FRED", "VIXCLS", "Diaria → mensual", "1990–2026", "Modelo principal", "Promedio mensual", "https://fred.stlouisfed.org/series/VIXCLS"],
    ["Banco de la República", "Términos de intercambio 15360", "Mensual", "1995–2026", "Robustez", "Sustituto de Brent", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15360"],
    ["Banco de la República", "Reservas netas sin FLAR 15053", "Mensual", "1960–2026", "Modelo ampliado", "Log y rezago", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15053"],
    ["Banco de la República", "TES en pesos a 10 años 15274", "Diaria → mensual", "2003–2026", "Modelo ampliado", "Tasa cero cupón; promedio mensual", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15274"],
    ["U.S. Treasury / FRED", "Treasury 10 años DGS10", "Diaria → mensual", "1962–2026", "Modelo ampliado", "Promedio mensual; se resta de TES 10 años", "https://fred.stlouisfed.org/series/DGS10"],
    ["Banco de la República", "Balanza comercial cambiaria 16702", "Mensual", "2001–2026", "Modelo ampliado", "Δ asinh y rezago", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=16702"],
    ["Banco de la República", "Flujo neto total de capital 16706", "Mensual", "2001–2026", "Modelo ampliado", "Δ asinh y rezago", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=16706"],
    ["Banco de la República", "IPC total nacional 15000", "Mensual", "1954–2026", "Modelo ampliado", "Inflación interanual", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15000"],
    ["U.S. BLS / FRED", "IPC urbano no ajustado CPIAUCNS", "Mensual", "1913–2026", "Modelo ampliado", "Inflación interanual; octubre de 2025 interpolado", "https://fred.stlouisfed.org/series/CPIAUCNS"],
    ["OECD / FRED", "BRL por USD CCUSMA02BRM618N", "Mensual", "1994–2026", "Modelo ampliado", "Factor regional a partir de Δln", "https://fred.stlouisfed.org/series/CCUSMA02BRM618N"],
    ["OECD / FRED", "CLP por USD CCUSMA02CLM618N", "Mensual", "1960–2026", "Modelo ampliado", "Factor regional a partir de Δln", "https://fred.stlouisfed.org/series/CCUSMA02CLM618N"],
    ["OECD / FRED", "MXN por USD CCUSMA02MXM618N", "Mensual", "1957–2026", "Modelo ampliado", "Factor regional a partir de Δln", "https://fred.stlouisfed.org/series/CCUSMA02MXM618N"],
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
  { range: "Modelo_ampliado!A5:N22", rows: 18, cols: 14 },
  { range: "Pesos_explicativos!A1:H24", rows: 24, cols: 8 },
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
  ["Datos_fuente", "A1:AB24"],
  ["Transformaciones", "A1:AA24"],
  ["Modelo_principal", "A1:W32"],
  ["Modelo_ampliado", "A1:W36"],
  ["Pesos_explicativos", "A1:R30"],
  ["Validacion", "A1:R30"],
  ["ECM_exploratorio", "A1:H30"],
  ["Diagnosticos", "A1:N34"],
  ["Variables", "A1:I23"],
  ["Fuentes", "A1:G30"],
];
for (const [sheetName, range] of renderSpecs) {
  const preview = await wb.render({ sheetName, range, scale: 1, format: "png" });
  const filename = `${sheetName.toLowerCase()}.png`;
  await fs.writeFile(path.join(PREVIEW_DIR, filename), new Uint8Array(await preview.arrayBuffer()));
}

const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(OUTPUT_XLSX);
if (path.resolve(OUTPUT_XLSX) !== path.resolve(DELIVERABLE_XLSX)) {
  await fs.copyFile(OUTPUT_XLSX, DELIVERABLE_XLSX);
}
await fs.writeFile(path.join(OUTPUT_DIR, "qa_inspect.txt"), `${keyChecks.join("\n\n")}\n\nERROR SCAN\n${errors.ndjson}\n`, "utf8");

console.log(JSON.stringify({
  output: OUTPUT_XLSX,
  deliverable: DELIVERABLE_XLSX,
  rows_source: raw.length,
  rows_model: fit.length,
  rows_model_expanded: expandedFit.length,
  explanatory_factors: explanatoryWeights.length,
  rows_validation: validationPredictions.length,
  previews: renderSpecs.map(([name]) => path.join(PREVIEW_DIR, `${name.toLowerCase()}.png`)),
  error_scan: errors.ndjson,
}, null, 2));
