"""Carga y feature engineering para pronóstico diario de TRM."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"


MONTH_NUMBERS_ES = {
    "Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Ago": 8, "Sep": 9, "Set": 9, "Oct": 10, "Nov": 11, "Dic": 12,
}


def load_daily_features() -> pd.DataFrame:
    """
    Carga datos diarios y construye features para pronóstico a t+1.

    Todos los features usan información disponible en t (rezagados).
    La variable objetivo es r_trm_{t+1} = ln(TRM_{t+1}) - ln(TRM_t).
    """
    # --- TRM diaria ---
    trm_raw = json.loads((RAW / "trm_diaria_banrep.json").read_text("utf-8"))
    trm_df = pd.DataFrame(trm_raw[0]["data"], columns=["ts", "trm"])
    trm_df["fecha"] = pd.to_datetime(trm_df["ts"], unit="ms", utc=True).dt.tz_convert(None).dt.normalize()
    trm_df["trm"] = pd.to_numeric(trm_df["trm"], errors="coerce")
    trm = trm_df.dropna().set_index("fecha")["trm"].sort_index().groupby(level=0).mean()

    # --- Dólar amplio ---
    dolar_raw = pd.read_csv(RAW / "dolar_amplio_diario_fred.csv")
    dolar_raw.columns = ["fecha", "dolar"]
    dolar_raw["fecha"] = pd.to_datetime(dolar_raw["fecha"], errors="coerce")
    dolar_raw["dolar"] = pd.to_numeric(dolar_raw["dolar"], errors="coerce")
    dolar = dolar_raw.dropna().set_index("fecha")["dolar"].sort_index()

    # --- VIX ---
    vix_raw = pd.read_csv(RAW / "vix_diario_fred.csv")
    vix_raw.columns = ["fecha", "vix"]
    vix_raw["fecha"] = pd.to_datetime(vix_raw["fecha"], errors="coerce")
    vix_raw["vix"] = pd.to_numeric(vix_raw["vix"], errors="coerce")
    vix = vix_raw.dropna().set_index("fecha")["vix"].sort_index()

    # --- EMBIG Colombia ---
    embig_raw = json.loads((RAW / "embig_colombia_diario_bcrp.json").read_text("utf-8"))
    embig_rows = []
    for obs in embig_raw.get("periods", []):
        parts = str(obs.get("name", "")).strip().split(".")
        values = obs.get("values") or []
        if len(parts) != 3 or not values or parts[1] not in MONTH_NUMBERS_ES:
            continue
        year = int(parts[2])
        year += 2000 if year < 70 else 1900
        date = pd.Timestamp(year=year, month=MONTH_NUMBERS_ES[parts[1]], day=int(parts[0]))
        value = pd.to_numeric(str(values[0]).replace(",", "."), errors="coerce")
        if pd.notna(value):
            embig_rows.append((date, float(value)))
    embig = pd.Series(
        [v for _, v in embig_rows],
        index=pd.DatetimeIndex([d for d, _ in embig_rows]),
    ).sort_index().groupby(level=0).mean()
    embig.name = "embig_pb"

    # --- Combinar ---
    daily = pd.DataFrame({"trm": trm, "dolar": dolar, "vix": vix, "embig_pb": embig})
    daily = daily.sort_index().ffill(limit=5)

    # --- Retornos ---
    daily["r_trm"] = np.log(daily["trm"]).diff()
    daily["r_dolar"] = np.log(daily["dolar"]).diff()
    daily["r_vix"] = np.log(daily["vix"]).diff()
    daily["d_embig"] = daily["embig_pb"].diff() / 100

    # --- Features (todo rezagado, disponible en t para predecir t+1) ---
    features = pd.DataFrame(index=daily.index)

    # Retornos rezagados
    for lag in [1, 2, 3, 5]:
        features[f"r_trm_L{lag}"] = daily["r_trm"].shift(lag)
        features[f"r_dolar_L{lag}"] = daily["r_dolar"].shift(lag)

    features["r_vix_L1"] = daily["r_vix"].shift(1)
    features["r_vix_L2"] = daily["r_vix"].shift(2)
    features["d_embig_L1"] = daily["d_embig"].shift(1)
    features["d_embig_L2"] = daily["d_embig"].shift(2)

    # Promedios móviles (momentum)
    features["r_trm_ma5"] = daily["r_trm"].rolling(5).mean().shift(1)
    features["r_trm_ma22"] = daily["r_trm"].rolling(22).mean().shift(1)
    features["r_dolar_ma5"] = daily["r_dolar"].rolling(5).mean().shift(1)
    features["r_dolar_ma22"] = daily["r_dolar"].rolling(22).mean().shift(1)

    # Volatilidad realizada
    features["vol_trm_5d"] = daily["r_trm"].rolling(5).std().shift(1)
    features["vol_trm_22d"] = daily["r_trm"].rolling(22).std().shift(1)
    features["vol_dolar_5d"] = daily["r_dolar"].rolling(5).std().shift(1)
    features["vix_nivel"] = daily["vix"].shift(1)

    # Nivel del EMBIG (riesgo país)
    features["embig_nivel"] = daily["embig_pb"].shift(1) / 100

    # Día de la semana (efecto calendario)
    features["dia_semana"] = daily.index.dayofweek.astype(float)

    # Interacciones clave (del modelo mensual)
    features["dolar_x_vix"] = features["r_dolar_L1"] * features["r_vix_L1"]

    # Target: retorno de mañana
    target = daily["r_trm"].shift(-1)  # r_{t+1}
    target.name = "target"

    # Combinar y limpiar
    dataset = pd.concat([target, features], axis=1).loc["2006-02-01":].dropna()

    return dataset


def train_test_split_temporal(
    dataset: pd.DataFrame, holdout_days: int = 250
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Split temporal: train con todo menos los últimos holdout_days."""
    n = len(dataset)
    split = n - holdout_days
    train = dataset.iloc[:split]
    test = dataset.iloc[split:]
    X_train = train.drop(columns="target")
    y_train = train["target"]
    X_test = test.drop(columns="target")
    y_test = test["target"]
    return X_train, X_test, y_train, y_test
