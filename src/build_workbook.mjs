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

function effectText(coefficient, proportionalChange = null) {
  const beta = Number(coefficient);
  const effect = proportionalChange === null
    ? 100 * (Math.exp(beta) - 1)
    : 100 * (Math.exp(beta * Math.log1p(proportionalChange)) - 1);
  const sign = effect > 0 ? "+" : effect < 0 ? "−" : "";
  return `${sign}${Math.abs(effect).toFixed(2).replace(".", ",")}%`;
}

function directionText(coefficient) {
  return Number(coefficient) >= 0 ? "Deprecia el COP" : "Aprecia el COP";
}

const metadata = JSON.parse(await fs.readFile(path.join(ROOT, "results/metadata.json"), "utf8"));
const sampleStart = new Date(`${metadata.muestra_inicio}T00:00:00Z`);
sampleStart.setUTCMonth(sampleStart.getUTCMonth() - 1);
const sourceStart = sampleStart.toISOString().slice(0, 10);
const raw = (await readCsv("data/modelo_trm_datos_mensuales.csv"))
  .filter((r) => r.fecha >= sourceStart && r.fecha <= metadata.muestra_fin);
const coefs = await readCsv("results/explicacion/coeficientes_modelo_principal.csv");
const diagnostics = await readCsv("results/explicacion/diagnosticos_modelo_principal.csv");
const validationMetrics = await readCsv("results/explicacion/validacion_metricas_modelo_principal.csv");
const validationPredictions = await readCsv("results/explicacion/validacion_predicciones_modelo_principal.csv");
const integration = await readCsv("results/explicacion/pruebas_integracion.csv");
const adlLags = await readCsv("results/explicacion/seleccion_rezagos_adl_diferencias.csv");
const bounds = await readCsv("results/robustez/bounds_resumen.csv");
const boundsCritical = await readCsv("results/robustez/bounds_criticos.csv");
const ecmLong = await readCsv("results/robustez/coeficientes_largo_plazo_ecm.csv");
const ecmShort = await readCsv("results/robustez/coeficientes_corto_plazo_ecm.csv");
const fit = await readCsv("results/explicacion/ajuste_historico_modelo_principal.csv");
const expandedCoefs = await readCsv("results/explicacion/coeficientes_modelo_ampliado.csv");
const expandedDiagnostics = await readCsv("results/explicacion/diagnosticos_modelo_ampliado.csv");
const expandedFit = await readCsv("results/explicacion/ajuste_historico_modelo_ampliado.csv");
const expandedContributions = await readCsv("results/explicacion/contribuciones_modelo_ampliado.csv");
const expandedValidationMetrics = await readCsv("results/explicacion/validacion_metricas_modelo_ampliado.csv");
const expandedValidationPredictions = await readCsv("results/explicacion/validacion_predicciones_modelo_ampliado.csv");
const explanatoryWeights = await readCsv("results/explicacion/pesos_explicativos_modelo_ampliado.csv");
const shapleyIntervals = await readCsv("results/explicacion/intervalos_bootstrap_pesos_shapley.csv");
const stabilityDetail = await readCsv("results/explicacion/estabilidad_submuestras_modelo_ampliado.csv");
const stabilitySummary = await readCsv("results/explicacion/estabilidad_submuestras_resumen.csv");
const vintageCoverage = await readCsv("results/pronostico/cobertura_vintages_pronostico.csv");
const beiAggregation = await readCsv("results/robustez/comparacion_agregacion_bei_5y.csv");
const beiStationarity = await readCsv("results/robustez/pruebas_estacionariedad_bei_5y.csv");
const beiTrends = await readCsv("results/robustez/tendencias_quiebres_bei_5y.csv");
const beiSpecifications = await readCsv("results/robustez/comparacion_especificaciones_bei_5y.csv");
const modelComparison = await readCsv("results/explicacion/comparacion_modelos.csv");
const regionalComparison = await readCsv("results/explicacion/comparacion_factor_regional.csv");
const forecastAvailability = await readCsv("results/pronostico/calendario_disponibilidad_pronostico.csv");
const forecastCoefs = await readCsv("results/pronostico/coeficientes_modelo_pronostico.csv");
const forecastDiagnostics = await readCsv("results/pronostico/diagnosticos_modelo_pronostico.csv");
const forecastMetrics = await readCsv("results/pronostico/validacion_metricas_pronostico.csv");
const forecastPredictions = await readCsv("results/pronostico/validacion_predicciones_pronostico.csv");

const coefByTerm = Object.fromEntries(coefs.map((r) => [r.termino, n(r.coeficiente)]));
const coefRecordByTerm = Object.fromEntries(coefs.map((r) => [r.termino, r]));
const coefRowByTerm = Object.fromEntries(coefs.map((r, i) => [r.termino, 6 + i]));
const modelMetric = validationMetrics.find((r) => r.modelo.startsWith("ADL"));
const rwMetric = validationMetrics.find((r) => r.modelo.startsWith("Caminata"));
const expandedModelMetric = expandedValidationMetrics.find((r) => !r.modelo.toLowerCase().includes("caminata")) ?? expandedValidationMetrics[0];
const baseComparison = modelComparison.find((r) => /principal|base/i.test(r.modelo)) ?? modelComparison[0];
const expandedComparison = modelComparison.find((r) => /ampli/i.test(r.modelo)) ?? modelComparison.at(-1);
const forecastMetric = forecastMetrics.find((r) => !r.modelo.toLowerCase().includes("caminata")) ?? forecastMetrics[0];
const forecastWalkMetric = forecastMetrics.find((r) => r.modelo.toLowerCase().includes("caminata")) ?? forecastMetrics.at(-1);

const TERM_LABELS = {
  const: "Intercepto",
  "D.ln_terminos_intercambio.L0": "Δ ln términos de intercambio (t)",
  "D.ln_dolar_amplio.L0": "Δ ln índice dólar amplio (t)",
  "D.ln_vix.L0": "Δ ln VIX (t)",
  "D.ln_remesas_12m.L1": "Δ ln remesas 12m (t−1)",
  "D.diferencial_tasas_pp.L1": "Δ diferencial tasas (t−1)",
  "D.deficit_fiscal_12m_pct_pib.L1": "Δ déficit fiscal 12m/PIB (t−1)",
  "D.embig_colombia_pp.L0": "Δ EMBIG Colombia (t)",
  "D.ln_reservas_netas_sin_flar.L1": "Δ ln reservas netas sin FLAR (t−1)",
  "D.asinh_balanza_comercial.L1": "Δ asinh balanza comercial cambiaria (t−1)",
  "D.asinh_flujos_capital.L1": "Δ asinh flujo neto de capital (t−1)",
  "diferencial_bei_5y_pp.L1": "Diferencial BEI 5 años (t−1)",
  "D.diferencial_bei_5y_pp.L1": "Δ diferencial BEI 5 años (t−1)",
  "factor_monedas_regionales_4.L0": "Factor regional BRL, CLP, MXN y PEN (t)",
  "factor_monedas_regionales_3.L1": "Factor regional BRL, CLP y MXN (t−1)",
  factor_monedas_regionales_3: "Factor regional de tres monedas",
  factor_monedas_regionales_4: "Factor regional de cuatro monedas",
  ln_trm: "ln TRM (normalizado = 1)",
  ln_terminos_intercambio: "ln términos de intercambio",
  ln_remesas_12m: "ln remesas 12m",
  diferencial_tasas_pp: "Diferencial de tasas (pp)",
  deficit_fiscal_12m_pct_pib: "Déficit fiscal 12m/PIB (pp)",
  ln_dolar_amplio: "ln índice dólar amplio",
  dummy_pandemia_2020: "Dummy pandemia 2020",
};

function termLabel(term) {
  return TERM_LABELS[term] ?? term
    .replace(/^D\./, "Δ ")
    .replace(/\.L0$/, " (t)")
    .replace(/\.L1$/, " (t−1)")
    .replace(/\.L2$/, " (t−2)")
    .replace(/\.L3$/, " (t−3)")
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
  "Robustez",
  "BEI_robustez",
  "Validacion",
  "Pronostico",
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
    "Se separan dos usos: explicación histórica con información contemporánea y pronóstico de un mes con rezagos de publicación. Muestra común: enero de 2006 a abril de 2026."
  );

  card(s, "A5:B5", "A6:B7", "Observaciones modelo ampliado", n(expandedComparison.observaciones));
  card(s, "C5:D5", "C6:D7", "R² ajustado principal", pct(baseComparison.r_cuadrado_ajustado));
  card(s, "E5:F5", "E6:F7", "R² ajustado ampliado", pct(expandedComparison.r_cuadrado_ajustado), COLORS.green);
  card(s, "A9:B9", "A10:B11", "MAPE explicación histórica", `${Number(expandedComparison.mape_pct).toFixed(2)}%`, COLORS.green);
  card(s, "C9:D9", "C10:D11", "MAPE pronóstico publicado", `${Number(forecastMetric.mape_pct).toFixed(2)}%`, COLORS.amber);
  card(s, "E9:F9", "E10:F11", "R² pronóstico vs. caminata", pct(metadata.pronostico_r2_vs_caminata), COLORS.red);

  section(s, "A13:F13", "Especificación principal");
  subtitle(
    s,
    "A14:F16",
    "Δln(TRM)t = c + β1Δln(términos de intercambio)t + β2Δln(dólar amplio)t + β3Δln(VIX)t + β4Δln(remesas 12m)t−1 + β5Δ(diferencial de tasas)t−1 + β6Δ(déficit 12m/PIB)t−1 + β7 pandemia + ut",
    COLORS.paleGray
  );

  section(s, "A18:F18", "Lectura de los resultados (asociaciones, no efectos causales)");
  const termsCoef = n(coefRecordByTerm["D.ln_terminos_intercambio.L0"].coeficiente);
  const dollarCoef = n(coefRecordByTerm["D.ln_dolar_amplio.L0"].coeficiente);
  const vixCoef = n(coefRecordByTerm["D.ln_vix.L0"].coeficiente);
  const remittancesCoef = n(coefRecordByTerm["D.ln_remesas_12m.L1"].coeficiente);
  const ratesCoef = n(coefRecordByTerm["D.diferencial_tasas_pp.L1"].coeficiente);
  const fiscalCoef = n(coefRecordByTerm["D.deficit_fiscal_12m_pct_pib.L1"].coeficiente);
  const pandemicCoef = n(coefRecordByTerm.dummy_pandemia_2020.coeficiente);
  s.getRange("A19:F27").values = [
    ["Variable", "Movimiento ilustrativo", "Efecto aproximado en TRM", "Signo", "p-valor", "Lectura"],
    ["Términos de intercambio", "+10%", effectText(termsCoef, 0.10), directionText(termsCoef), n(coefRecordByTerm["D.ln_terminos_intercambio.L0"].p_valor), "Poder de compra externo; el dato se publica con rezago"],
    ["Índice amplio del dólar", "+1%", effectText(dollarCoef, 0.01), directionText(dollarCoef), n(coefRecordByTerm["D.ln_dolar_amplio.L0"].p_valor), "Fortaleza global del dólar"],
    ["VIX", "+10%", effectText(vixCoef, 0.10), directionText(vixCoef), n(coefRecordByTerm["D.ln_vix.L0"].p_valor), "Captura episodios globales de aversión al riesgo"],
    ["Remesas, acumulado 12m (t−1)", "+10%", effectText(remittancesCoef, 0.10), directionText(remittancesCoef), n(coefRecordByTerm["D.ln_remesas_12m.L1"].p_valor), "Puede reflejar endogeneidad y shocks simultáneos"],
    ["Diferencial tasas CO−EE. UU. (t−1)", "+1 pp", effectText(ratesCoef), directionText(ratesCoef), n(coefRecordByTerm["D.diferencial_tasas_pp.L1"].p_valor), "Retorno nominal relativo; no es un shock exógeno"],
    ["Déficit fiscal 12m/PIB (t−1)", "+1 pp", effectText(fiscalCoef), directionText(fiscalCoef), n(coefRecordByTerm["D.deficit_fiscal_12m_pct_pib.L1"].p_valor), "Prima fiscal; revise el intervalo antes de concluir"],
    ["Pandemia, mar–may 2020", "Dummy = 1", effectText(pandemicCoef), directionText(pandemicCoef), n(coefRecordByTerm.dummy_pandemia_2020.p_valor), "Control de episodio extraordinario"],
    ["Conclusión", "—", "—", "—", null, "La magnitud, la precisión y el peso Shapley responden preguntas distintas"],
  ];
  header(s, "A19:F19");
  s.getRange("E20:E27").format.numberFormat = "0.0000";
  s.getRange("A19:F27").format.wrapText = true;
  s.getRange("A19:F27").format.borders = { preset: "all", style: "thin", color: "#D9E1F2" };
  s.getRange("A27:F27").format = { fill: COLORS.green, font: { bold: true, color: COLORS.dark }, wrapText: true };

  section(s, "A29:F29", "Alcance y cautelas");
  s.getRange("A30:B37").values = [
    ["1", "La regresión identifica asociaciones dinámicas; no demuestra causalidad."],
    ["2", "La hoja Validacion mide explicación condicional con realizaciones contemporáneas; la hoja Pronostico usa únicamente datos rezagados según su calendario de publicación."],
    ["3", "Los residuos presentan colas no normales; para inferencia se reportan errores HAC."],
    ["4", "El resultado positivo de remesas puede reflejar respuesta de los hogares a depreciaciones u otros shocks simultáneos."],
    ["5", "La prueba bounds no confirma cointegración al 5%; el ECM se muestra solo como contraste exploratorio."],
    ["6", "El déficit fiscal y los demás factores deben interpretarse con sus intervalos de confianza; el signo aislado no basta."],
    ["7", "En el ampliado, ARCH-LM y Jarque–Bera rechazan al 5%; RESET no rechaza la forma funcional."],
    ["8", "El backtest del pronóstico usa el último vintage disponible: respeta rezagos, pero sigue siendo pseudo-tiempo-real hasta archivar versiones históricas de cada publicación."],
  ];
  s.mergeCells("B30:F30"); s.mergeCells("B31:F31"); s.mergeCells("B32:F32");
  s.mergeCells("B33:F33"); s.mergeCells("B34:F34"); s.mergeCells("B35:F35"); s.mergeCells("B36:F36"); s.mergeCells("B37:F37");
  s.getRange("A30:F37").format = { fill: COLORS.amber, wrapText: true, borders: { preset: "all", style: "thin", color: "#E6B800" } };
  s.getRange("A30:A37").format = { fill: COLORS.navy, font: { bold: true, color: COLORS.white }, horizontalAlignment: "center", verticalAlignment: "center" };

  const summaryComparison = [
    ...modelComparison,
    {
      modelo: "Pronóstico publicación",
      observaciones: metadata.pronostico_observaciones,
      r_cuadrado_ajustado: metadata.pronostico_r_cuadrado_ajustado,
      aic: metadata.pronostico_aic,
      bic: metadata.pronostico_bic,
      mape_pct: metadata.pronostico_mape_pct,
      acierto_direccion_pct: metadata.pronostico_acierto_direccion_pct,
    },
  ];
  section(s, "H29:N29", "Explicación histórica frente a pronóstico publicado");
  s.getRange("H30:N30").values = [["Modelo", "Obs.", "R² ajustado", "AIC", "BIC", "MAPE", "Dirección"]];
  s.getRange(`H31:N${30 + summaryComparison.length}`).values = summaryComparison.map((r) => [
    r.modelo,
    n(r.observaciones),
    n(r.r_cuadrado_ajustado),
    n(r.aic),
    n(r.bic),
    n(r.mape_pct) / 100,
    n(r.acierto_direccion_pct) / 100,
  ]);
  header(s, "H30:N30");
  addTable(s, `H30:N${30 + summaryComparison.length}`, "ComparacionModelosResumenTable");
  s.getRange(`J31:J${30 + summaryComparison.length}`).format.numberFormat = "0.0%";
  s.getRange(`K31:L${30 + summaryComparison.length}`).format.numberFormat = "0.00";
  s.getRange(`M31:N${30 + summaryComparison.length}`).format.numberFormat = "0.0%";

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
  s.getRange("H:H").format.columnWidth = 20;
  s.getRange("I:J").format.columnWidth = 16;
  s.getRange("K:N").format.columnWidth = 12;
  s.freezePanes.freezeRows(3);
}

// Datos fuente
{
  const s = sheets.Datos_fuente;
  title(s, "A1:AC1", "Datos fuente mensuales");
  subtitle(s, "A2:AC3", "Niveles utilizados para construir la explicación histórica y el pronóstico con rezagos de publicación. Las series diarias se promedian por mes sin imputar faltantes. El diferencial BEI usa promedios mensuales separados de cada curva; mide compensación inflacionaria de mercado, no una expectativa pura.");
  const heads = [
    "Mes", "TRM (COP/USD)", "Términos de intercambio", "Remesas (USD mill.)", "Remesas 12m (USD mill.)",
    "Tasa política Colombia (%)", "Fed funds (%)", "Diferencial tasas (pp)", "Balance fiscal mensual (miles mill. COP)",
    "Déficit fiscal 12m (% PIB)", "Índice dólar amplio", "VIX", "Dummy pandemia", "Reservas netas sin FLAR (USD mill.)",
    "EMBIG Colombia (pb)", "EMBIG Colombia (pp)", "Balanza comercial cambiaria (USD mill.)", "Flujo neto total de capital (USD mill.)",
    "TES pesos cero cupón 5 años (%)", "TES UVR cero cupón 5 años (%)", "BEI Colombia 5 años (%)", "BEI EE. UU. 5 años (%)", "Diferencial BEI 5 años (pp)",
    "BRL por USD", "CLP por USD", "MXN por USD", "PEN por USD", "Factor regional 3 monedas", "Factor regional 4 monedas",
  ];
  s.getRange("A5:AC5").values = [heads];
  const matrix = raw.map((r) => [
    r.fecha.slice(0, 7), n(r.trm_cop_usd), n(r.terminos_intercambio), n(r.remesas_usd_millones), n(r.remesas_12m_usd_millones),
    n(r.tasa_politica_colombia_pct), n(r.fed_funds_eeuu_pct), n(r.diferencial_tasas_pp), n(r.balance_fiscal_miles_millones_cop),
    n(r.deficit_fiscal_12m_pct_pib), n(r.indice_dolar_amplio), n(r.vix), n(r.dummy_pandemia_2020),
    n(firstValue(r, "reservas_netas_sin_flar_usd_millones", "reservas_netas_sin_flar_millones_usd")),
    n(r.embig_colombia_pb), n(r.embig_colombia_pp),
    n(firstValue(r, "balanza_comercial_cambiaria_usd_millones", "balance_comercial_cambiario_usd_millones")),
    n(firstValue(r, "flujos_capital_usd_millones", "flujo_neto_total_capital_usd_millones")),
    n(r.tes_5y_pesos_colombia_pct), n(r.tes_5y_uvr_colombia_pct), n(r.bei_colombia_5y_pct), n(r.bei_eeuu_5y_pct), n(r.diferencial_bei_5y_pp),
    n(r.brl_por_usd), n(r.clp_por_usd), n(r.mxn_por_usd), n(r.pen_por_usd),
    n(r.factor_monedas_regionales_3), n(r.factor_monedas_regionales_4),
  ]);
  const end = 5 + matrix.length;
  s.getRange(`A6:AC${end}`).values = matrix;
  header(s, "A5:AC5");
  addTable(s, `A5:AC${end}`, "DatosFuenteTable");
  s.getRange(`B6:C${end}`).format.numberFormat = "#,##0.00";
  s.getRange(`D6:E${end}`).format.numberFormat = "#,##0.00";
  s.getRange(`F6:H${end}`).format.numberFormat = "0.00";
  s.getRange(`I6:I${end}`).format.numberFormat = "#,##0.00;[Red]-#,##0.00";
  s.getRange(`J6:L${end}`).format.numberFormat = "0.00";
  s.getRange(`M6:M${end}`).format.numberFormat = "0";
  s.getRange(`N6:N${end}`).format.numberFormat = "#,##0.00";
  s.getRange(`O6:P${end}`).format.numberFormat = "0.00";
  s.getRange(`Q6:R${end}`).format.numberFormat = "#,##0.00;[Red]-#,##0.00";
  s.getRange(`S6:W${end}`).format.numberFormat = "0.00";
  s.getRange(`X6:AA${end}`).format.numberFormat = "#,##0.0000";
  s.getRange(`AB6:AC${end}`).format.numberFormat = "0.000000";
  s.getRange(`A5:AC${end}`).format.verticalAlignment = "center";
  s.getRange("A:A").format.columnWidth = 12;
  s.getRange("B:C").format.columnWidth = 16;
  s.getRange("D:E").format.columnWidth = 18;
  s.getRange("F:H").format.columnWidth = 16;
  s.getRange("I:I").format.columnWidth = 24;
  s.getRange("J:N").format.columnWidth = 18;
  s.getRange("O:W").format.columnWidth = 21;
  s.getRange("X:AC").format.columnWidth = 18;
  s.getRange("A5:AC5").format.rowHeight = 54;
  s.freezePanes.freezeRows(5);
  s.freezePanes.freezeColumns(1);

  const comments = {
    B5: "Fuente: Banco de la República, serie diaria TRM 1; promedio mensual. https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=1",
    C5: "Fuente: Banco de la República, índice de términos de intercambio según índices encadenados, serie mensual 15360.",
    D5: "Fuente: Banco de la República, remesas de trabajadores, serie 15363.",
    F5: "Fuente: Banco de la República, tasa de política, serie diaria 59; promedio mensual.",
    G5: "Fuente: Federal Reserve/FRED, FEDFUNDS, promedio mensual.",
    I5: "Fuente: Ministerio de Hacienda, balance fiscal del Gobierno Nacional Central, metodología de caja.",
    K5: "Fuente: Federal Reserve/FRED, índice nominal amplio del dólar DTWEXBGS; promedio mensual.",
    L5: "Fuente: Cboe vía FRED, VIXCLS; promedio mensual.",
    N5: "Fuente: Banco de la República, reservas internacionales netas sin FLAR, serie 15053.",
    O5: "Fuente: BCRPData, serie diaria PD04715XD; fuentes originales Reuters/J.P. Morgan. Promedio mensual de observaciones publicadas.",
    P5: "Construcción: EMBIG Colombia en puntos básicos dividido por 100; 100 pb = 1 pp.",
    Q5: "Fuente: Banco de la República, balanza comercial cambiaria, serie 16702.",
    R5: "Fuente: Banco de la República, flujo neto total de capital, serie 16706.",
    S5: "Fuente: Banco de la República, curva cero cupón TES en pesos a 5 años, serie 15273; promedio mensual.",
    T5: "Fuente: Banco de la República, curva cero cupón TES UVR a 5 años, serie 15276; promedio mensual.",
    U5: "Construcción: TES pesos 5 años menos TES UVR 5 años. Es compensación inflacionaria implícita, no una expectativa pura.",
    V5: "Fuente: Federal Reserve Board, curva Gürkaynak–Sack–Wright BKEVEN05, cero cupón a 5 años y capitalización continua; promedio mensual.",
    W5: "Construcción: BEI Colombia 5 años menos BEI EE. UU. 5 años. Las curvas se promedian por separado; incluye primas de riesgo inflacionario y liquidez.",
    X5: "Fuente: OECD vía FRED, CCUSMA02BRM618N; reales brasileños por dólar.",
    Y5: "Fuente: OECD vía FRED, CCUSMA02CLM618N; pesos chilenos por dólar.",
    Z5: "Fuente: OECD vía FRED, CCUSMA02MXM618N; pesos mexicanos por dólar.",
    AA5: "Fuente: BCRPData PN01207PM, tipo de cambio interbancario promedio; soles peruanos por dólar. https://estadisticas.bcrp.gob.pe/estadisticas/series/mensuales/resultados/PN01207PM/html",
    AB5: "Construcción: promedio igual ponderado de retornos mensuales estandarizados de BRL, CLP y MXN por USD. Medias y desviaciones calibradas con 2006–2019.",
    AC5: "Construcción activa de la explicación histórica: promedio igual ponderado de retornos mensuales estandarizados de BRL, CLP, MXN y PEN por USD. Medias y desviaciones calibradas con 2006–2019.",
  };
  for (const [cell, text] of Object.entries(comments)) wb.comments.addThread({ cell: s.getRange(cell) }, text);
}

// Transformaciones auditables
{
  const s = sheets.Transformaciones;
  title(s, "A1:AB1", "Transformaciones del modelo");
  subtitle(s, "A2:AB3", "Todas las transformaciones son fórmulas enlazadas a Datos_fuente. Δ indica cambio mensual; ln indica logaritmo natural; asinh conserva el signo de los flujos y reduce el peso de valores extremos. Los rezagos cambian entre la explicación histórica y el pronóstico.");
  const heads = [
    "Mes", "ln TRM", "Δln TRM", "ln términos de intercambio", "Δln términos de intercambio", "ln remesas 12m", "Δln remesas 12m", "Diferencial tasas", "Δ diferencial", "Déficit 12m/PIB", "Δ déficit", "ln dólar amplio", "Δln dólar amplio", "ln VIX", "Δln VIX", "Pandemia",
    "ln reservas netas sin FLAR", "Δln reservas", "EMBIG Colombia (pp)", "Δ EMBIG Colombia", "asinh balanza (USD miles de millones)", "Δ asinh balanza", "asinh flujos (USD miles de millones)", "Δ asinh flujos", "Diferencial BEI 5 años", "Δ diferencial BEI", "Factor regional 3 monedas", "Factor regional 4 monedas",
  ];
  s.getRange("A5:AB5").values = [heads];
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
      `='Datos_fuente'!M${src}`,
      `=IF('Datos_fuente'!N${src}="","",LN('Datos_fuente'!N${src}))`,
      first ? "" : `=IF(OR(Q${r}="",Q${r - 1}=""),"",Q${r}-Q${r - 1})`,
      `='Datos_fuente'!P${src}`,
      first ? "" : `=IF(OR(S${r}="",S${r - 1}=""),"",S${r}-S${r - 1})`,
      `=IF('Datos_fuente'!Q${src}="","",ASINH('Datos_fuente'!Q${src}/1000))`,
      first ? "" : `=IF(OR(U${r}="",U${r - 1}=""),"",U${r}-U${r - 1})`,
      `=IF('Datos_fuente'!R${src}="","",ASINH('Datos_fuente'!R${src}/1000))`,
      first ? "" : `=IF(OR(W${r}="",W${r - 1}=""),"",W${r}-W${r - 1})`,
      `='Datos_fuente'!W${src}`,
      first ? "" : `=IF(OR(Y${r}="",Y${r - 1}=""),"",Y${r}-Y${r - 1})`,
      `='Datos_fuente'!AB${src}`,
      `='Datos_fuente'!AC${src}`,
    ];
  });
  const end = 5 + formulas.length;
  s.getRange(`A6:AB${end}`).formulas = formulas;
  header(s, "A5:AB5");
  addTable(s, `A5:AB${end}`, "TransformacionesTable");
  s.getRange(`B6:G${end}`).format.numberFormat = "0.000000";
  s.getRange(`H6:K${end}`).format.numberFormat = "0.0000";
  s.getRange(`L6:O${end}`).format.numberFormat = "0.000000";
  s.getRange(`P6:P${end}`).format.numberFormat = "0";
  s.getRange(`Q6:R${end}`).format.numberFormat = "0.000000";
  s.getRange(`S6:T${end}`).format.numberFormat = "0.0000";
  s.getRange(`U6:X${end}`).format.numberFormat = "0.000000";
  s.getRange(`Y6:Z${end}`).format.numberFormat = "0.0000";
  s.getRange(`AA6:AB${end}`).format.numberFormat = "0.000000";
  s.getRange("A:A").format.columnWidth = 12;
  s.getRange("B:AB").format.columnWidth = 18;
  s.getRange("A5:AB5").format.rowHeight = 48;
  s.freezePanes.freezeRows(5);
  s.freezePanes.freezeColumns(1);
  wb.comments.addThread({ cell: s.getRange("U5") }, "Escala auditable: el flujo original en USD millones se divide por 1.000 antes de aplicar asinh, igual que en la estimación en Python.");
  wb.comments.addThread({ cell: s.getRange("W5") }, "Escala auditable: el flujo original en USD millones se divide por 1.000 antes de aplicar asinh, igual que en la estimación en Python.");
  wb.comments.addThread({ cell: s.getRange("AA5") }, "Promedio igual ponderado de retornos mensuales estandarizados de BRL, CLP y MXN por USD. Medias y desviaciones calibradas entre enero de 2006 y diciembre de 2019.");
  wb.comments.addThread({ cell: s.getRange("AB5") }, "Promedio igual ponderado de retornos mensuales estandarizados de BRL, CLP, MXN y PEN por USD. Es la composición activa de la explicación histórica.");
}

// Modelo principal
{
  const s = sheets.Modelo_principal;
  title(s, "A1:W1", "Modelo principal: variación mensual de la TRM");
  subtitle(s, "A2:W3", "OLS con errores estándar HAC (6 meses). BIC seleccionó cero rezagos adicionales de Δln(TRM). Términos de intercambio, dólar amplio y VIX entran en t; remesas, diferencial de tasas y déficit fiscal entran con un mes de rezago.");
  s.getRange("A5:G5").values = [["Variable", "Coeficiente", "EE HAC", "t", "p-valor", "IC 95% inferior", "IC 95% superior"]];
  const labels = {
    const: "Intercepto",
    "D.ln_terminos_intercambio.L0": "Δ ln términos de intercambio (t)",
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
    "Mes", "Δln TRM observado", "Constante", "Términos de intercambio", "Dólar amplio", "VIX", "Remesas t−1", "Tasas t−1", "Fiscal t−1", "Pandemia", "Δln TRM ajustado", "Residuo", "TRM observada", "TRM ajustada 1 paso",
  ]];
  const dateToTransformRow = Object.fromEntries(raw.map((r, i) => [r.fecha, 6 + i]));
  const modelFormulas = fit.map((r, i) => {
    const row = modelHeaderRow + 1 + i;
    const tr = dateToTransformRow[r.fecha];
    return [
      `='Transformaciones'!A${tr}`,
      `='Transformaciones'!C${tr}`,
      `=$B$${coefRowByTerm.const}`,
      `=$B$${coefRowByTerm["D.ln_terminos_intercambio.L0"]}*'Transformaciones'!E${tr}`,
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
    "Explicación histórica ex post. Extiende el modelo principal con EMBIG Colombia, reservas, balanza comercial cambiaria, flujos de capital, diferencial de compensación inflacionaria a 5 años y un factor regional de BRL, CLP, MXN y PEN. Los coeficientes y pesos describen asociaciones; no identifican efectos causales.",
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
  // H is a spacer in the upper panel but contains a detailed contribution in
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

// Robustez: intervalos, submuestras y cobertura de vintages (sin gráficos)
{
  const s = sheets.Robustez;
  title(s, "A1:P1", "Robustez de los pesos y cobertura de datos en tiempo real");
  subtitle(
    s,
    "A2:P3",
    "Los intervalos Shapley usan 200 réplicas de bloques circulares de 12 meses. Las submuestras revelan cuánto cambian pesos, rangos y signos. La cobertura de vintages sigue incompleta: el ejercicio de pronóstico continúa siendo pseudo-tiempo-real.",
    COLORS.amber
  );

  section(s, "A5:H5", "Incertidumbre de los pesos Shapley");
  s.getRange("A6:H6").values = [[
    "Factor", "Peso puntual", "Mediana bootstrap", "IC 95% inferior", "IC 95% superior", "Ancho IC", "Prob. top 3", "Réplicas",
  ]];
  const intervalRows = [...shapleyIntervals].sort((a, b) => n(b.peso_puntual_pct) - n(a.peso_puntual_pct));
  s.getRange(`A7:H${6 + intervalRows.length}`).values = intervalRows.map((r) => [
    r.factor,
    n(r.peso_puntual_pct) / 100,
    n(r.peso_bootstrap_mediana_pct) / 100,
    n(r.ic_95_inferior_pct) / 100,
    n(r.ic_95_superior_pct) / 100,
    (n(r.ic_95_superior_pct) - n(r.ic_95_inferior_pct)) / 100,
    n(r.probabilidad_top3_pct) / 100,
    n(r.replicas_validas),
  ]);
  header(s, "A6:H6");
  addTable(s, `A6:H${6 + intervalRows.length}`, "IntervalosShapleyTable");
  s.getRange(`B7:G${6 + intervalRows.length}`).format.numberFormat = "0.0%";
  s.getRange(`A7:H${6 + intervalRows.length}`).format.rowHeight = 28;

  section(s, "J5:P5", "Estabilidad por submuestras");
  s.getRange("J6:P6").values = [[
    "Submuestra", "Obs.", "R² ajustado", "Spearman rangos", "Mediana |Δ peso|", "Máx. |Δ peso|", "Mismo signo / 12",
  ]];
  s.getRange(`J7:P${6 + stabilitySummary.length}`).values = stabilitySummary.map((r) => [
    r.submuestra,
    n(r.observaciones),
    n(r.r2_ajustado),
    n(r.correlacion_spearman_rangos_vs_completa),
    n(r.mediana_diferencia_abs_peso_pp) / 100,
    n(r.max_diferencia_abs_peso_pp) / 100,
    n(r.factores_mismo_signo_de_12),
  ]);
  header(s, "J6:P6");
  addTable(s, `J6:P${6 + stabilitySummary.length}`, "EstabilidadResumenTable");
  s.getRange(`L7:O${6 + stabilitySummary.length}`).format.numberFormat = "0.0%";
  s.getRange(`J7:P${6 + stabilitySummary.length}`).format.rowHeight = 31;

  section(s, "A21:G21", "Peso de cada factor por submuestra");
  const subSamples = stabilitySummary.map((r) => r.submuestra);
  s.getRange("A22:G22").values = [["Factor", "Grupo", ...subSamples]];
  const stabilityByFactor = intervalRows.map((interval) => {
    const factorRows = stabilityDetail.filter((r) => r.factor === interval.factor);
    const bySubsample = Object.fromEntries(factorRows.map((r) => [r.submuestra, n(r.peso_entre_factores_pct) / 100]));
    const group = factorRows[0]?.grupo ?? "";
    return [interval.factor, group, ...subSamples.map((label) => bySubsample[label] ?? null)];
  });
  s.getRange(`A23:G${22 + stabilityByFactor.length}`).values = stabilityByFactor;
  header(s, "A22:G22");
  addTable(s, `A22:G${22 + stabilityByFactor.length}`, "PesosSubmuestrasTable");
  s.getRange(`C23:G${22 + stabilityByFactor.length}`).format.numberFormat = "0.0%";
  s.getRange(`A23:G${22 + stabilityByFactor.length}`).format.rowHeight = 28;

  section(s, "I21:P21", "Cobertura de vintages en los 48 orígenes");
  s.getRange("I22:P22").values = [[
    "Factor", "Estado", "Orígenes", "Cobertura", "Apto", "Archivo desde", "Fuentes", "Detalle",
  ]];
  s.getRange(`I23:P${22 + vintageCoverage.length}`).values = vintageCoverage.map((r) => [
    r.factor,
    r.estado_vintages_2022_05_a_2026_04,
    n(r.origenes_completos_de_48),
    n(r.cobertura_pct) / 100,
    String(r.apto_backtest_genuino).toLowerCase() === "true" ? "Sí" : "No",
    r.archivo_hacia_adelante_desde,
    r.fuentes,
    r.detalle,
  ]);
  header(s, "I22:P22");
  addTable(s, `I22:P${22 + vintageCoverage.length}`, "CoberturaVintagesTable");
  s.getRange(`L23:L${22 + vintageCoverage.length}`).format.numberFormat = "0.0%";
  s.getRange(`I23:P${22 + vintageCoverage.length}`).format.rowHeight = 42;
  for (let i = 0; i < vintageCoverage.length; i += 1) {
    const row = 23 + i;
    const complete = String(vintageCoverage[i].apto_backtest_genuino).toLowerCase() === "true";
    s.getRange(`J${row}:M${row}`).format.fill = complete ? COLORS.green : COLORS.amber;
  }

  subtitle(
    s,
    "A37:P39",
    "Lectura: intervalos amplios o cambios de signo entre cortes indican incertidumbre de asignación, aunque el peso puntual sea alto. Tener 48 vintages en un factor no basta para un backtest genuino: todos los factores utilizados en cada origen deben estar completos.",
    COLORS.paleGray
  );
  s.getRange("A:A").format.columnWidth = 34;
  s.getRange("B:B").format.columnWidth = 22;
  s.getRange("C:H").format.columnWidth = 16;
  s.getRange("I:I").format.columnWidth = 34;
  s.getRange("J:J").format.columnWidth = 25;
  s.getRange("K:M").format.columnWidth = 15;
  s.getRange("N:N").format.columnWidth = 15;
  s.getRange("O:O").format.columnWidth = 28;
  s.getRange("P:P").format.columnWidth = 42;
  s.getRange("A6:P39").format.wrapText = true;
  s.freezePanes.freezeRows(6);
  s.freezePanes.freezeColumns(2);
}

// Robustez del diferencial BEI (sin gráficos)
{
  const s = sheets.BEI_robustez;
  const activeBei = beiSpecifications.find((r) => r.especificacion.includes("vigente"));
  const levelBei = beiSpecifications.find((r) => r.especificacion.includes("Nivel") && r.especificacion.includes("referencia"));
  const commonDays = beiAggregation.map((r) => n(r.dias_comunes)).filter((value) => value !== null).sort((a, b) => a - b);
  const medianCommonDays = commonDays.length % 2
    ? commonDays[Math.floor(commonDays.length / 2)]
    : (commonDays[commonDays.length / 2 - 1] + commonDays[commonDays.length / 2]) / 2;
  title(s, "A1:L1", "Robustez del diferencial de compensación inflacionaria a cinco años");
  subtitle(
    s,
    "A2:L3",
    `Se adopta Δ diferencial BEI con promedios mensuales separados y rezago de un mes: la primera diferencia es la especificación vigente por estabilidad; el nivel obtiene BIC ${n(levelBei.bic).toFixed(2)} frente a ${n(activeBei.bic).toFixed(2)} en la variante diferenciada. La evidencia de raíz unitaria del nivel cambia al incluir tendencia o quiebre.`,
    COLORS.amber
  );

  section(s, "A5:L5", "Comparación dentro del modelo ampliado — misma muestra de 240 meses");
  s.getRange("A6:L6").values = [[
    "Especificación", "Agregación", "Transformación", "Extensión", "R² ajustado", "BIC", "Coef. BEI", "p HAC", "MAPE cond.", "R² validación", "Quiebre", "Cautela",
  ]];
  s.getRange(`A7:L${6 + beiSpecifications.length}`).values = beiSpecifications.map((r) => [
    r.especificacion,
    r.agregacion_bei,
    r.transformacion_bei,
    r.extension_deterministica,
    n(r.r_cuadrado_ajustado),
    n(r.bic),
    n(r.coeficiente_bei_pre_quiebre),
    n(r.p_valor_hac_bei_pre_quiebre),
    n(r.mape_condicional_pct) / 100,
    n(r.r2_validacion_condicional_vs_caminata),
    r.fecha_quiebre_za || "—",
    String(r.quiebre_elegido_con_muestra_completa).toLowerCase() === "true" ? "Quiebre elegido ex post" : "Comparación regular",
  ]);
  header(s, "A6:L6");
  addTable(s, `A6:L${6 + beiSpecifications.length}`, "EspecificacionesBeiTable");
  s.getRange(`E7:E${6 + beiSpecifications.length}`).format.numberFormat = "0.000";
  s.getRange(`F7:H${6 + beiSpecifications.length}`).format.numberFormat = "0.0000";
  s.getRange(`I7:J${6 + beiSpecifications.length}`).format.numberFormat = "0.00%";
  s.getRange(`A7:L${6 + beiSpecifications.length}`).format.rowHeight = 34;

  section(s, "A15:F15", "Comparación de agregación mensual");
  s.getRange("A16:C16").values = [["Métrica", "Valor", "Lectura"]];
  const aggregationSummary = [
    ["Correlación entre agregaciones", n(metadata.diferencial_bei_5y_correlacion_agregaciones), "Prácticamente idénticas en el conjunto de la muestra"],
    ["Diferencia media común − separada", n(metadata.diferencial_bei_5y_diferencia_media_comun_menos_separada_pp), "Puntos porcentuales"],
    ["Máxima diferencia absoluta", n(metadata.diferencial_bei_5y_max_diferencia_abs_agregacion_pp), "Puntos porcentuales; ocurre en un mes con pocos cruces"],
    ["Mínimo de días comunes", n(metadata.diferencial_bei_5y_min_dias_comunes_mes), "La intersección puede perder gran parte del mes"],
    ["Mediana de días comunes", medianCommonDays, "Días con las tres curvas observadas"],
  ];
  s.getRange(`A17:C${16 + aggregationSummary.length}`).values = aggregationSummary;
  header(s, "A16:C16");
  addTable(s, `A16:C${16 + aggregationSummary.length}`, "AgregacionBeiResumenTable");
  s.getRange("B17:B17").format.numberFormat = "0.00%";
  s.getRange("B18:B19").format.numberFormat = "0.0000";
  s.getRange("B20:B21").format.numberFormat = "0";

  section(s, "A24:L24", "Estacionariedad con constante, tendencia y quiebre endógeno");
  const stationarityRows = beiStationarity.filter((r) => (
    (r.prueba === "ADF" && ["constante", "constante_tendencia"].includes(r.deterministico))
    || (r.prueba === "KPSS" && r.deterministico === "constante_tendencia")
    || (r.prueba === "Zivot-Andrews" && r.deterministico === "constante_tendencia_con_quiebre")
  ));
  s.getRange("A25:K25").values = [[
    "Agregación", "Transformación", "Prueba", "Determinístico", "H₀", "N", "Estadístico", "p-valor", "Rezagos", "Fecha quiebre", "Crítico 5%",
  ]];
  s.getRange(`A26:K${25 + stationarityRows.length}`).values = stationarityRows.map((r) => [
    r.agregacion,
    r.transformacion,
    r.prueba,
    r.deterministico,
    r.hipotesis_nula,
    n(r.n),
    n(r.estadistico),
    n(r.p_valor),
    n(r.rezagos),
    r.fecha_quiebre || "—",
    n(r.critico_5_pct),
  ]);
  header(s, "A25:K25");
  addTable(s, `A25:K${25 + stationarityRows.length}`, "EstacionariedadBeiTable");
  s.getRange(`G26:H${25 + stationarityRows.length}`).format.numberFormat = "0.0000";
  s.getRange(`K26:K${25 + stationarityRows.length}`).format.numberFormat = "0.0000";
  s.getRange(`A26:K${25 + stationarityRows.length}`).format.rowHeight = 31;

  const trendsStart = 27 + stationarityRows.length;
  section(s, `A${trendsStart}:L${trendsStart}`, "Tendencias determinísticas del propio diferencial BEI");
  s.getRange(`A${trendsStart + 1}:L${trendsStart + 1}`).values = [[
    "Agregación", "Modelo", "Quiebre ZA", "N", "R² ajustado", "BIC", "Tendencia pp/año", "p tendencia", "Cambio nivel", "p nivel", "Cambio pendiente", "p pendiente",
  ]];
  s.getRange(`A${trendsStart + 2}:L${trendsStart + 1 + beiTrends.length}`).values = beiTrends.map((r) => [
    r.agregacion,
    r.modelo_deterministico,
    r.fecha_quiebre_za,
    n(r.observaciones),
    n(r.r_cuadrado_ajustado),
    n(r.bic),
    n(r.tendencia_pp_por_ano),
    n(r.p_valor_hac_tendencia),
    n(r.cambio_nivel_quiebre_pp),
    n(r.p_valor_hac_cambio_nivel),
    n(r.cambio_pendiente_pp_por_ano),
    n(r.p_valor_hac_cambio_pendiente),
  ]);
  header(s, `A${trendsStart + 1}:L${trendsStart + 1}`);
  addTable(s, `A${trendsStart + 1}:L${trendsStart + 1 + beiTrends.length}`, "TendenciasBeiTable");
  s.getRange(`E${trendsStart + 2}:L${trendsStart + 1 + beiTrends.length}`).format.numberFormat = "0.0000";
  s.getRange(`A${trendsStart + 2}:L${trendsStart + 1 + beiTrends.length}`).format.rowHeight = 32;

  const noteRow = trendsStart + beiTrends.length + 3;
  subtitle(
    s,
    `A${noteRow}:L${noteRow + 2}`,
    "Lectura conjunta: el nivel parece estacionario con constante, pero deja de ser concluyente al incluir tendencia; Zivot–Andrews tampoco rechaza raíz unitaria al 5%. El quiebre de 2009 se seleccionó con toda la muestra y no mejora el BIC del modelo de TRM. La primera diferencia separada ofrece el mejor BIC, conserva casi el mismo desempeño condicional y evita depender de una fecha de quiebre estimada ex post.",
    COLORS.paleGray
  );
  s.getRange("A:A").format.columnWidth = 34;
  s.getRange("B:B").format.columnWidth = 27;
  s.getRange("C:D").format.columnWidth = 19;
  s.getRange("E:L").format.columnWidth = 15;
  s.getRange(`A1:L${noteRow + 2}`).format.wrapText = true;
  s.freezePanes.freezeRows(6);
  s.freezePanes.freezeColumns(2);
}

// Validación
{
  const s = sheets.Validacion;
  title(s, "A1:R1", "Validación condicional pseudo-fuera de muestra");
  subtitle(s, "A2:R3", "Ventana expansiva de 48 meses (mayo de 2022–abril de 2026). La evaluación usa valores contemporáneos ya realizados de términos de intercambio, dólar amplio, VIX, EMBIG y monedas regionales. Es una prueba explicativa condicional, no un pronóstico genuinamente disponible en tiempo real.", COLORS.amber);

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

// Pronóstico con calendario de publicación, sin gráficos nuevos dentro de Excel
{
  const s = sheets.Pronostico;
  title(s, "A1:P1", "Pronóstico mensual con rezagos de publicación");
  subtitle(
    s,
    "A2:P3",
    "Objetivo: pronosticar la TRM promedio del mes t al inicio de t. Ningún factor económico del mes objetivo entra contemporáneamente. El backtest respeta un calendario conservador de publicación, pero usa el último vintage disponible; por eso es pseudo-tiempo-real, no una validación histórica de vintages genuinos.",
    COLORS.amber
  );

  section(s, "A5:F5", "Desempeño en la ventana expansiva de 48 meses");
  s.getRange("A6:F6").values = [["Modelo", "Observaciones", "MAE (log)", "RMSE (log)", "MAPE", "Acierto dirección"]];
  s.getRange("A7:F8").values = [forecastMetric, forecastWalkMetric].map((r) => [
    r.modelo,
    n(r.observaciones),
    n(r.mae_log),
    n(r.rmse_log),
    n(r.mape_pct) / 100,
    n(r.acierto_direccion_pct) === null ? null : n(r.acierto_direccion_pct) / 100,
  ]);
  header(s, "A6:F6");
  addTable(s, "A6:F8", "MetricasPronosticoTable");
  s.getRange("C7:D8").format.numberFormat = "0.0000";
  s.getRange("E7:F8").format.numberFormat = "0.0%";
  s.getRange("A7:F7").format.fill = COLORS.amber;

  section(s, "H5:P5", "Lectura de desempeño");
  s.mergeCells("H6:I6"); s.mergeCells("J6:K6"); s.mergeCells("L6:P6");
  s.getRange("H6:P6").values = [["Indicador", null, "Valor", null, "Lectura", null, null, null, null]];
  header(s, "H6:P6");
  const performanceRows = [
    ["Composición regional", metadata.pronostico_factor_regional_monedas, "Seleccionada por menor BIC; PEN no mejora BIC ni MAPE del pronóstico."],
    ["MAPE", n(forecastMetric.mape_pct) / 100, `La caminata obtiene ${(n(forecastWalkMetric.mape_pct)).toFixed(2)}%; el pronóstico no la mejora.`],
    ["R² frente a caminata", metadata.pronostico_r2_vs_caminata, "Un valor negativo indica mayor error cuadrático que la caminata aleatoria."],
    ["Estado del backtest", "Pseudo-tiempo-real", "Respeta rezagos de publicación, pero usa el último vintage disponible."],
    ["Conclusión", "Benchmark honesto", "La explicación histórica mejora con PEN; la precisión ex ante sigue siendo limitada."],
  ];
  for (let i = 0; i < performanceRows.length; i += 1) {
    const row = 7 + i;
    s.mergeCells(`H${row}:I${row}`);
    s.mergeCells(`J${row}:K${row}`);
    s.mergeCells(`L${row}:P${row}`);
    s.getRange(`H${row}:P${row}`).values = [[performanceRows[i][0], null, performanceRows[i][1], null, performanceRows[i][2], null, null, null, null]];
  }
  s.getRange("H7:P11").format = { wrapText: true, borders: { preset: "all", style: "thin", color: "#D9E1F2" } };
  s.getRange("J8:K9").format.numberFormat = "0.0%";
  s.getRange("H7:P11").format.rowHeight = 34;

  section(s, "A12:J12", "Comparación del factor regional: tres frente a cuatro monedas");
  s.getRange("A13:J13").values = [["Uso", "Monedas", "R² ajustado", "BIC", "MAPE", "Dirección", "R² vs. caminata", "Coef. regional", "p-valor HAC", "Correlación 3–4"]];
  s.getRange(`A14:J${13 + regionalComparison.length}`).values = regionalComparison.map((r) => [
    r.uso,
    r.monedas,
    n(r.r_cuadrado_ajustado),
    n(r.bic),
    n(r.mape_pct) / 100,
    n(r.acierto_direccion_pct) / 100,
    n(r.r2_validacion_vs_caminata),
    n(r.coeficiente_factor_regional),
    n(r.p_valor_hac_factor_regional),
    n(r.correlacion_factores_3_4),
  ]);
  header(s, "A13:J13");
  addTable(s, `A13:J${13 + regionalComparison.length}`, "ComparacionFactorRegionalTable");
  s.getRange(`C14:C${13 + regionalComparison.length}`).format.numberFormat = "0.0%";
  s.getRange(`D14:D${13 + regionalComparison.length}`).format.numberFormat = "0.00";
  s.getRange(`E14:G${13 + regionalComparison.length}`).format.numberFormat = "0.0%";
  s.getRange(`H14:J${13 + regionalComparison.length}`).format.numberFormat = "0.0000";
  s.getRange(`A14:J${13 + regionalComparison.length}`).format.rowHeight = 34;

  section(s, "A19:D19", "Calendario conservador de disponibilidad al inicio del mes t");
  s.getRange("A20:D20").values = [["Factor", "Rezago (meses)", "Frecuencia/publicación", "Regla utilizada"]];
  s.getRange(`A21:D${20 + forecastAvailability.length}`).values = forecastAvailability.map((r) => [
    r.factor,
    n(r.rezago_meses_modelo),
    r.frecuencia_y_publicacion,
    r.regla_disponibilidad_al_inicio_del_mes_t,
  ]);
  header(s, "A20:D20");
  addTable(s, `A20:D${20 + forecastAvailability.length}`, "CalendarioDisponibilidadTable");
  s.getRange(`A20:D${20 + forecastAvailability.length}`).format.wrapText = true;
  s.getRange(`A21:D${20 + forecastAvailability.length}`).format.rowHeight = 34;

  section(s, "F19:L19", "Coeficientes del modelo de pronóstico seleccionado");
  s.getRange("F20:L20").values = [["Variable", "Coeficiente", "EE HAC", "t", "p-valor", "IC 95% inferior", "IC 95% superior"]];
  s.getRange(`F21:L${20 + forecastCoefs.length}`).values = forecastCoefs.map((r) => [
    termLabel(r.termino),
    n(r.coeficiente),
    n(r.error_estandar_hac),
    n(r.estadistico_t),
    n(r.p_valor),
    n(r.ic_95_inferior),
    n(r.ic_95_superior),
  ]);
  header(s, "F20:L20");
  addTable(s, `F20:L${20 + forecastCoefs.length}`, "CoeficientesPronosticoTable");
  s.getRange(`G21:L${20 + forecastCoefs.length}`).format.numberFormat = "0.000000";
  s.getRange(`J21:J${20 + forecastCoefs.length}`).conditionalFormats.add("cellIs", {
    operator: "lessThan",
    formula: 0.05,
    format: { fill: COLORS.green, font: { bold: true, color: "#006100" } },
  });

  section(s, "N19:P19", "Diagnósticos");
  s.getRange("N20:P20").values = [["Prueba", "Estadístico", "p-valor"]];
  s.getRange(`N21:P${20 + forecastDiagnostics.length}`).values = forecastDiagnostics.map((r) => [
    r.prueba,
    n(r.estadistico),
    n(r.p_valor),
  ]);
  header(s, "N20:P20");
  addTable(s, `N20:P${20 + forecastDiagnostics.length}`, "DiagnosticosPronosticoTable");
  s.getRange(`O21:P${20 + forecastDiagnostics.length}`).format.numberFormat = "0.0000";

  const forecastHeader = Math.max(38, 22 + forecastCoefs.length);
  section(s, `A${forecastHeader - 1}:I${forecastHeader - 1}`, "Predicciones de un mes con información disponible al origen");
  s.getRange(`A${forecastHeader}:I${forecastHeader}`).values = [["Mes", "ln TRM observada", "ln TRM pronóstico", "ln TRM caminata", "Δln observado", "Δln pronóstico", "TRM observada", "TRM pronóstico", "TRM caminata"]];
  const forecastRows = forecastPredictions.map((r) => [
    r.fecha.slice(0, 7),
    n(r.ln_trm_observada),
    n(r.ln_trm_pronostico_publicacion),
    n(r.ln_trm_caminata_aleatoria),
    n(r.cambio_log_observado),
    n(r.cambio_log_pronostico),
    n(r.trm_observada),
    n(r.trm_pronostico_publicacion),
    n(r.trm_caminata_aleatoria),
  ]);
  const forecastEnd = forecastHeader + forecastRows.length;
  s.getRange(`A${forecastHeader + 1}:I${forecastEnd}`).values = forecastRows;
  header(s, `A${forecastHeader}:I${forecastHeader}`);
  addTable(s, `A${forecastHeader}:I${forecastEnd}`, "PrediccionesPronosticoTable");
  s.getRange(`B${forecastHeader + 1}:F${forecastEnd}`).format.numberFormat = "0.000000";
  s.getRange(`G${forecastHeader + 1}:I${forecastEnd}`).format.numberFormat = "#,##0.00";

  s.getRange("A:A").format.columnWidth = 38;
  s.getRange("B:B").format.columnWidth = 22;
  s.getRange("C:D").format.columnWidth = 25;
  s.getRange("E:E").format.columnWidth = 16;
  s.getRange("F:F").format.columnWidth = 30;
  s.getRange("G:L").format.columnWidth = 14;
  s.getRange("M:M").format.columnWidth = 3;
  s.getRange("N:N").format.columnWidth = 25;
  s.getRange("O:P").format.columnWidth = 16;
  s.freezePanes.freezeRows(3);
  s.freezePanes.freezeColumns(1);
}

// ECM exploratorio
{
  const s = sheets.ECM_exploratorio;
  const bounds95 = boundsCritical.find((r) => Math.abs(n(r.percentile) - 95) < 0.01) ?? boundsCritical.at(-1);
  const boundsDecision = n(bounds[0].p_valor_i1) < 0.05 ? "sí confirma" : "no confirma";
  title(s, "A1:H1", "ARDL–ECM exploratorio");
  subtitle(s, "A2:H3", `La prueba bounds ${boundsDecision} cointegración al 5%: F = ${n(bounds[0].estadistico_f).toFixed(3)}, límite superior = ${n(bounds95.upper).toFixed(3)} y p-valor I(1) = ${(100 * n(bounds[0].p_valor_i1)).toFixed(2).replace(".", ",")}%. Los coeficientes de largo plazo son exploratorios.`, COLORS.amber);
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

  section(s, "A18:G18", "Vector cointegrante normalizado (largo plazo exploratorio; invertir signo para efecto sobre ln TRM)");
  s.getRange("A19:G19").values = [["Variable", "Coeficiente", "EE", "t", "p-valor", "IC 95% inferior", "IC 95% superior"]];
  s.getRange(`A20:G${19 + ecmLong.length}`).values = ecmLong.map((r) => [termLabel(r.termino), n(r.coeficiente_largo_plazo), n(r.error_estandar), n(r.estadistico_t), n(r.p_valor), n(r.ic_95_inferior), n(r.ic_95_superior)]);
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
  subtitle(s, "A2:N3", "Las pruebas se interpretan al 5%. No se detecta autocorrelación residual. El ampliado presenta ARCH y residuos no normales, mientras RESET no rechaza la forma funcional. HAC fortalece la inferencia de la media, pero no modela la volatilidad condicional.");

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
    ["Externo", "Términos de intercambio", "Modelo principal", "BanRep 15360", "Δln contemporáneo", "−", "Poder de compra externo", "Precios relativos de exportaciones e importaciones", "Su publicación tiene rezago; el uso contemporáneo es explicativo ex post"],
    ["Divisas", "Remesas recibidas", "Modelo principal", "Acumulado 12m en USD", "Δln, rezago 1", "− esperado", "Oferta de divisas", "Flujo estable de dólares", "Puede responder a la propia depreciación"],
    ["Monetario", "Diferencial tasas CO−EE. UU.", "Modelo principal", "Tasa política − Fed funds", "Δ pp, rezago 1", "−", "Retorno relativo", "Carry e ingreso de capital", "Tasas nominales; endógenas a inflación y TRM"],
    ["Fiscal", "Déficit GNC", "Modelo principal", "Acumulado 12m / PIB", "Δ pp, rezago 1", "+", "Riesgo fiscal", "Financiación y prima de riesgo", "Dato observado no es un shock fiscal exógeno"],
    ["Global", "Índice amplio del dólar", "Modelo principal", "Fed DTWEXBGS", "Δln contemporáneo", "+", "Fortaleza global USD", "Factor global común", "No es el DXY comercial de ICE"],
    ["Global", "VIX", "Modelo principal", "Promedio mensual", "Δln contemporáneo", "+", "Aversión al riesgo", "Risk-off y salida de emergentes", "Correlacionado con dólar global"],
    ["Riesgo", "EMBIG Colombia", "Modelo ampliado", "BCRPData PD04715XD", "Δ pp, contemporáneo", "+", "Riesgo soberano externo", "Prima de bonos soberanos frente a Treasuries", "Canasta con duración y composición variables; no es CDS a 5 años"],
    ["Reservas", "Reservas internacionales netas sin FLAR", "Modelo ampliado", "BanRep 15053", "Δln, rezago 1", "−", "Colchón externo", "Capacidad de intervención y liquidez", "La acumulación de reservas puede responder a la TRM"],
    ["Comercio", "Balanza comercial cambiaria", "Modelo ampliado", "BanRep 16702", "Δ asinh, rezago 1", "−", "Oferta neta de divisas", "Exportaciones menos importaciones canalizadas", "Es simultánea con la depreciación"],
    ["Precios", "Diferencial BEI 5 años CO−EE. UU.", "Modelo ampliado", "BanRep 15273−15276 menos Fed BKEVEN05", "Primera diferencia en pp, rezago 1", "+", "Cambio en la compensación inflacionaria relativa", "La diferencia es robustamente estacionaria y mejora BIC", "Incluye primas de riesgo de inflación y liquidez; el nivel es sensible a tendencia y quiebre"],
    ["Mercado", "Monedas regionales", "Modelo ampliado", "BRL, CLP, MXN y PEN por USD", "Promedio igual de z(Δln), base 2006–2019", "+", "Contagio regional", "PEN mejora la explicación histórica frente a tres monedas", "Comparte información con VIX y dólar global"],
    ["Pronóstico", "Modelo de un mes", "Pronóstico publicado", "Variables disponibles al inicio de t", "Rezagos de 1 a 3 meses", "—", "Predicción ex ante", "Composición regional de tres monedas seleccionada por BIC", "Backtest pseudo-tiempo-real: faltan vintages históricos"],
    ["Flujos", "Flujo neto total de capital", "Modelo ampliado", "BanRep 16706", "Δ asinh, rezago 1", "−", "Demanda de activos COP", "Resume entradas y salidas de capital", "Altamente endógeno y volátil"],
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
  subtitle(s, "A2:G3", "Enlaces oficiales o distribuidores públicos de las series activas. EMBIG se redistribuye conforme a las condiciones de BCRPData, con atribución a BCRPData y a sus fuentes originales Reuters/J.P. Morgan; no se afirma una licencia abierta del índice subyacente.");
  const rows = [
    ["Banco de la República", "TRM diaria, serie 1", "Diaria → mensual", "1991–2026", "Modelo principal", "Promedio mensual", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=1"],
    ["Banco de la República", "Tasa de política, serie 59", "Diaria → mensual", "1998–2026", "Modelo principal", "Promedio mensual", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=59"],
    ["Banco de la República", "Remesas, serie 15363", "Mensual", "2000–2026", "Modelo principal", "Acumulado móvil 12 meses", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15363"],
    ["Ministerio de Hacienda", "Balance fiscal GNC", "Mensual", "2004–2026", "Modelo principal", "Balance de caja; déficit positivo tras cambiar signo", "https://www.minhacienda.gov.co/documents/d/portal/balance-fiscal-gnc-mensual-y-trimestral?download=true"],
    ["Federal Reserve / FRED", "Federal funds FEDFUNDS", "Mensual", "1954–2026", "Modelo principal", "Promedio mensual", "https://fred.stlouisfed.org/series/FEDFUNDS"],
    ["Federal Reserve / FRED", "Índice amplio USD DTWEXBGS", "Diaria → mensual", "2006–2026", "Modelo principal", "Índice nominal amplio", "https://fred.stlouisfed.org/series/DTWEXBGS"],
    ["Cboe / FRED", "VIXCLS", "Diaria → mensual", "1990–2026", "Modelo principal", "Promedio mensual", "https://fred.stlouisfed.org/series/VIXCLS"],
    ["Banco de la República", "Términos de intercambio 15360", "Mensual", "1995–2026", "Modelo principal", "Índice encadenado; Δln contemporáneo en explicación ex post", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15360"],
    ["Banco de la República", "Reservas netas sin FLAR 15053", "Mensual", "1960–2026", "Modelo ampliado", "Log y rezago", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15053"],
    ["BCRPData", "EMBIG Colombia PD04715XD", "Diaria → mensual", "2006–2026", "Modelo ampliado", "Promedio mensual; pb/100; fuentes originales Reuters/J.P. Morgan", "https://estadisticas.bcrp.gob.pe/estadisticas/series/diarias/tasas-de-interes-embig-variacion-en-pbs"],
    ["Banco de la República", "TES pesos cero cupón 5 años 15273", "Diaria → mensual", "2003–2026", "Modelo ampliado", "Promedio mensual separado; comparación adicional sobre fechas comunes", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15273"],
    ["Banco de la República", "TES UVR cero cupón 5 años 15276", "Diaria → mensual", "2003–2026", "Modelo ampliado", "Promedio mensual separado; comparación adicional sobre fechas comunes", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15276"],
    ["Federal Reserve Board", "GSW BKEVEN05", "Diaria → mensual", "2003–2026", "Modelo ampliado", "Promedio separado; robustez con fechas comunes; producto de investigación revisable", "https://www.federalreserve.gov/data/yield-curve-tables/feds200805_1.html"],
    ["Banco de la República", "Balanza comercial cambiaria 16702", "Mensual", "2001–2026", "Modelo ampliado", "Δ asinh y rezago", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=16702"],
    ["Banco de la República", "Flujo neto total de capital 16706", "Mensual", "2001–2026", "Modelo ampliado", "Δ asinh y rezago", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=16706"],
    ["OECD / FRED", "BRL por USD CCUSMA02BRM618N", "Mensual", "1994–2026", "Modelo ampliado", "Factor regional a partir de Δln", "https://fred.stlouisfed.org/series/CCUSMA02BRM618N"],
    ["OECD / FRED", "CLP por USD CCUSMA02CLM618N", "Mensual", "1960–2026", "Modelo ampliado", "Factor regional a partir de Δln", "https://fred.stlouisfed.org/series/CCUSMA02CLM618N"],
    ["OECD / FRED", "MXN por USD CCUSMA02MXM618N", "Mensual", "1957–2026", "Modelo ampliado", "Factor regional a partir de Δln", "https://fred.stlouisfed.org/series/CCUSMA02MXM618N"],
    ["BCRPData", "PEN por USD PN01207PM", "Mensual", "1995–2026", "Modelo ampliado y comparación regional", "Interbancario promedio; factor regional a partir de Δln", "https://estadisticas.bcrp.gob.pe/estadisticas/series/mensuales/resultados/PN01207PM/html"],
    ["Cboe", "VIX histórico", "Diaria", "1990–2026", "Verificación", "Fuente primaria del VIX", "https://www.cboe.com/tradable_products/vix/vix_historical_data"],
    ["Banco de la República", "Portal de sector externo", "Varias", "Histórico", "Documentación", "Metodologías de TRM, remesas y sector externo", "https://www.banrep.gov.co/es/estadisticas-economicas/series-historicas/tasas-cambio-sector-externo"],
    ["BCRPData", "Condiciones de uso", "Documentación", "Vigente", "Licencia/atribución", "Permite reproducción con cita de la fuente; revisar derechos del índice subyacente", "https://estadisticas.bcrp.gob.pe/estadisticas/series/ayuda/condiciones-de-uso"],
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
  { range: "Robustez!A1:P39", rows: 39, cols: 16 },
  { range: "BEI_robustez!A1:L54", rows: 54, cols: 12 },
  { range: "Validacion!A5:J16", rows: 12, cols: 10 },
  { range: "Pronostico!A5:P32", rows: 28, cols: 16 },
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
  ["Datos_fuente", "A1:AC24"],
  ["Transformaciones", "A1:AB24"],
  ["Modelo_principal", "A1:W32"],
  ["Modelo_ampliado", "A1:W36"],
  ["Pesos_explicativos", "A1:R30"],
  ["Robustez", "A1:P39"],
  ["BEI_robustez", "A1:L54"],
  ["Validacion", "A1:R30"],
  ["Pronostico", "A1:P42"],
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
  rows_forecast_validation: forecastPredictions.length,
  previews: renderSpecs.map(([name]) => path.join(PREVIEW_DIR, `${name.toLowerCase()}.png`)),
  error_scan: errors.ndjson,
}, null, 2));
