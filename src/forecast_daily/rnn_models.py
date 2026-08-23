"""
Redes neuronales recurrentes para pronóstico diario de TRM.

Implementa LSTM y GRU con PyTorch:
- Secuencias de 22 días (1 mes hábil) como input
- Pronóstico del retorno del día siguiente
- Entrenamiento con early stopping sobre validación temporal
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader


# ─────────────────────────────────────────────────────────────────────────────
# DATASET
# ─────────────────────────────────────────────────────────────────────────────


class SequenceDataset(Dataset):
    """Convierte features tabulares en secuencias para RNN."""

    def __init__(self, X: np.ndarray, y: np.ndarray, seq_length: int = 22):
        self.seq_length = seq_length
        self.X = torch.tensor(X, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.float32)

    def __len__(self):
        return len(self.X) - self.seq_length

    def __getitem__(self, idx):
        # Secuencia de seq_length días → predecir el día siguiente
        x_seq = self.X[idx : idx + self.seq_length]
        target = self.y[idx + self.seq_length]
        return x_seq, target


# ─────────────────────────────────────────────────────────────────────────────
# MODELOS
# ─────────────────────────────────────────────────────────────────────────────


class LSTMModel(nn.Module):
    """LSTM de una capa con proyección lineal al retorno."""

    def __init__(self, input_size: int, hidden_size: int = 32, num_layers: int = 1, dropout: float = 0.1):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )
        self.fc = nn.Linear(hidden_size, 1)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        # x: (batch, seq_len, features)
        lstm_out, _ = self.lstm(x)
        # Usar solo el último hidden state
        last_hidden = lstm_out[:, -1, :]
        out = self.fc(self.dropout(last_hidden))
        return out.squeeze(-1)


class GRUModel(nn.Module):
    """GRU de una capa — más simple que LSTM, a menudo igual de efectivo."""

    def __init__(self, input_size: int, hidden_size: int = 32, num_layers: int = 1, dropout: float = 0.1):
        super().__init__()
        self.gru = nn.GRU(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )
        self.fc = nn.Linear(hidden_size, 1)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        gru_out, _ = self.gru(x)
        last_hidden = gru_out[:, -1, :]
        out = self.fc(self.dropout(last_hidden))
        return out.squeeze(-1)


class LSTMAttentionModel(nn.Module):
    """LSTM + atención temporal simple (weighted average de hidden states)."""

    def __init__(self, input_size: int, hidden_size: int = 32, num_layers: int = 1):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
        )
        self.attention = nn.Linear(hidden_size, 1)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x):
        lstm_out, _ = self.lstm(x)  # (batch, seq_len, hidden)
        # Attention weights
        attn_weights = torch.softmax(self.attention(lstm_out), dim=1)  # (batch, seq_len, 1)
        context = (attn_weights * lstm_out).sum(dim=1)  # (batch, hidden)
        out = self.fc(context)
        return out.squeeze(-1)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRENAMIENTO
# ─────────────────────────────────────────────────────────────────────────────


def train_rnn(
    model: nn.Module,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    seq_length: int = 22,
    epochs: int = 100,
    batch_size: int = 64,
    lr: float = 0.001,
    patience: int = 10,
) -> nn.Module:
    """Entrena un modelo RNN con early stopping."""
    train_dataset = SequenceDataset(X_train, y_train, seq_length)
    val_dataset = SequenceDataset(X_val, y_val, seq_length)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=len(val_dataset), shuffle=False)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    criterion = nn.MSELoss()

    best_val_loss = float("inf")
    patience_counter = 0
    best_state = None

    for epoch in range(epochs):
        # Train
        model.train()
        for x_batch, y_batch in train_loader:
            optimizer.zero_grad()
            pred = model(x_batch)
            loss = criterion(pred, y_batch)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

        # Validate
        model.eval()
        with torch.no_grad():
            for x_val_batch, y_val_batch in val_loader:
                val_pred = model(x_val_batch)
                val_loss = criterion(val_pred, y_val_batch).item()

        # Early stopping
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = model.state_dict().copy()
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    return model


def predict_rnn(
    model: nn.Module,
    X: np.ndarray,
    seq_length: int = 22,
) -> np.ndarray:
    """Genera predicciones para todo el array X."""
    model.eval()
    X_tensor = torch.tensor(X, dtype=torch.float32)
    predictions = []
    with torch.no_grad():
        for i in range(seq_length, len(X)):
            x_seq = X_tensor[i - seq_length : i].unsqueeze(0)
            pred = model(x_seq).item()
            predictions.append(pred)
    return np.array(predictions)


# ─────────────────────────────────────────────────────────────────────────────
# INTERFACE PARA run.py
# ─────────────────────────────────────────────────────────────────────────────


def fit_lstm(X_train, y_train, X_test, seq_length=22, hidden_size=32):
    """Entrena LSTM y genera predicciones en test."""
    # Normalizar features
    mean = X_train.values.mean(axis=0)
    std = X_train.values.std(axis=0) + 1e-8
    X_tr_norm = (X_train.values - mean) / std
    X_te_norm = (X_test.values - mean) / std

    # Split train/val (últimos 250 días de train como validación)
    val_size = min(250, len(X_tr_norm) // 5)
    X_tr = X_tr_norm[:-val_size]
    y_tr = y_train.values[:-val_size]
    X_vl = X_tr_norm[-val_size:]
    y_vl = y_train.values[-val_size:]

    input_size = X_tr.shape[1]
    model = LSTMModel(input_size=input_size, hidden_size=hidden_size)

    model = train_rnn(model, X_tr, y_tr, X_vl, y_vl, seq_length=seq_length)

    # Predicción en test: necesitamos las últimas seq_length obs del train + test
    X_full_test = np.vstack([X_tr_norm[-seq_length:], X_te_norm])
    y_full_test = np.concatenate([y_train.values[-seq_length:], np.zeros(len(X_test))])
    preds = predict_rnn(model, X_full_test, seq_length=seq_length)

    return preds[:len(X_test)]


def fit_gru(X_train, y_train, X_test, seq_length=22, hidden_size=32):
    """Entrena GRU y genera predicciones en test."""
    mean = X_train.values.mean(axis=0)
    std = X_train.values.std(axis=0) + 1e-8
    X_tr_norm = (X_train.values - mean) / std
    X_te_norm = (X_test.values - mean) / std

    val_size = min(250, len(X_tr_norm) // 5)
    X_tr = X_tr_norm[:-val_size]
    y_tr = y_train.values[:-val_size]
    X_vl = X_tr_norm[-val_size:]
    y_vl = y_train.values[-val_size:]

    input_size = X_tr.shape[1]
    model = GRUModel(input_size=input_size, hidden_size=hidden_size)

    model = train_rnn(model, X_tr, y_tr, X_vl, y_vl, seq_length=seq_length)

    X_full_test = np.vstack([X_tr_norm[-seq_length:], X_te_norm])
    preds = predict_rnn(model, X_full_test, seq_length=seq_length)

    return preds[:len(X_test)]


def fit_lstm_attention(X_train, y_train, X_test, seq_length=22, hidden_size=32):
    """Entrena LSTM con atención temporal."""
    mean = X_train.values.mean(axis=0)
    std = X_train.values.std(axis=0) + 1e-8
    X_tr_norm = (X_train.values - mean) / std
    X_te_norm = (X_test.values - mean) / std

    val_size = min(250, len(X_tr_norm) // 5)
    X_tr = X_tr_norm[:-val_size]
    y_tr = y_train.values[:-val_size]
    X_vl = X_tr_norm[-val_size:]
    y_vl = y_train.values[-val_size:]

    input_size = X_tr.shape[1]
    model = LSTMAttentionModel(input_size=input_size, hidden_size=hidden_size)

    model = train_rnn(model, X_tr, y_tr, X_vl, y_vl, seq_length=seq_length)

    X_full_test = np.vstack([X_tr_norm[-seq_length:], X_te_norm])
    preds = predict_rnn(model, X_full_test, seq_length=seq_length)

    return preds[:len(X_test)]
