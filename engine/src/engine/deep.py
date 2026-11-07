"""Deep-learning forecasters with the same interface as the others, so that every score,
baseline and explanation applies to them unchanged.

They read the same design table as Ridge, Random Forest and XGBoost: lags of the response and
its drivers, and the calendar. The recurrent and convolutional ones arrange the lag columns
as a sequence, from the oldest lag to last month, one channel per series and a second channel
saying whether that lag was chosen; the calendar joins after the sequence. The series are a
few hundred months long, so the networks are small, trained full-batch with early stopping on
the last part of the training years, and seeded so that a refit gives the same model.
"""

import re

import numpy as np
import pandas as pd
import torch
from sklearn.base import BaseEstimator, RegressorMixin
from torch import nn

LAG = re.compile(r"^(.*)_lag(\d+)$")
torch.set_num_threads(1)  # many small fits run side by side; threads would only contend


def layout(columns: list[str]) -> tuple[list[str], int, list[tuple[int, int, int]], list[int]]:
    """Series names, the longest lag, (column, series, step) for every lag column, and the
    positions of the columns that are not lags."""
    series, lags, statics = [], [], []
    for i, c in enumerate(columns):
        m = LAG.match(c)
        if m:
            if m.group(1) not in series:
                series.append(m.group(1))
            lags.append((i, series.index(m.group(1)), int(m.group(2))))
        else:
            statics.append(i)
    longest = max((lag for _, _, lag in lags), default=1)
    cells = [(i, s, longest - lag) for i, s, lag in lags]  # step 0 is the oldest lag
    return series, longest, cells, statics


class Net(nn.Module):
    def __init__(self, kind: str, channels: int, steps: int, statics: int, hidden: int):
        super().__init__()
        self.kind = kind
        if kind == "lstm":
            self.body = nn.LSTM(channels, hidden, batch_first=True)
            width = hidden
        elif kind == "gru":
            self.body = nn.GRU(channels, hidden, batch_first=True)
            width = hidden
        elif kind == "cnn":
            # dilated causal convolutions over the lag window, as a temporal convolutional net
            self.body = nn.Sequential(
                nn.Conv1d(channels, hidden, 3, padding=2, dilation=1),
                nn.ReLU(),
                nn.Conv1d(hidden, hidden, 3, padding=4, dilation=2),
                nn.ReLU(),
            )
            width = hidden
        else:  # mlp over the flattened window
            self.body = nn.Sequential(nn.Linear(channels * steps, hidden), nn.ReLU())
            width = hidden
        self.head = nn.Sequential(
            nn.Linear(width + statics, hidden), nn.ReLU(), nn.Linear(hidden, 1)
        )

    def forward(self, seq: torch.Tensor, static: torch.Tensor) -> torch.Tensor:
        if self.kind in ("lstm", "gru"):
            out, _ = self.body(seq)
            h = out[:, -1]
        elif self.kind == "cnn":
            h = self.body(seq.transpose(1, 2))[:, :, : seq.shape[1]][:, :, -1]
        else:
            h = self.body(seq.flatten(1))
        return self.head(torch.cat([h, static], dim=1)).squeeze(1)


class DeepRegressor(RegressorMixin, BaseEstimator):
    """A small network forecasting from the design table, as a scikit-learn regressor."""

    def __init__(
        self,
        kind: str = "lstm",
        hidden: int = 32,
        lr: float = 5e-3,
        weight_decay: float = 1e-4,
        epochs: int = 500,
        patience: int = 50,
        random_state: int = 0,
    ):
        self.kind = kind
        self.hidden = hidden
        self.lr = lr
        self.weight_decay = weight_decay
        self.epochs = epochs
        self.patience = patience
        self.random_state = random_state

    def _tensors(self, X) -> tuple[torch.Tensor, torch.Tensor]:
        values = (np.asarray(X, dtype=float) - self.mean_) / self.scale_
        values = np.nan_to_num(values)
        n = len(values)
        seq = np.zeros((n, self.steps_, 2 * len(self.series_)), dtype=np.float32)
        for col, s, step in self.cells_:
            seq[:, step, s] = values[:, col]
            seq[:, step, len(self.series_) + s] = 1.0  # this lag was chosen
        static = (
            values[:, self.statics_].astype(np.float32)
            if self.statics_
            else np.zeros((n, 0), np.float32)
        )
        return torch.from_numpy(seq), torch.from_numpy(static)

    def fit(self, X, y):
        columns = (
            list(X.columns)
            if isinstance(X, pd.DataFrame)
            else [f"x{i}" for i in range(np.shape(X)[1])]
        )
        self.series_, self.steps_, self.cells_, self.statics_ = layout(columns)
        if not self.cells_:  # no lag columns: every column is a step of one series
            self.series_, self.steps_ = ["x"], len(columns)
            self.cells_ = [(i, 0, i) for i in range(len(columns))]
            self.statics_ = []
        values = np.asarray(X, dtype=float)
        self.mean_ = np.nanmean(values, axis=0)
        self.scale_ = np.nanstd(values, axis=0)
        self.scale_[self.scale_ == 0] = 1
        target = np.asarray(y, dtype=float)
        self.y_mean_, self.y_scale_ = target.mean(), target.std() or 1.0
        t = torch.tensor((target - self.y_mean_) / self.y_scale_, dtype=torch.float32)
        seq, static = self._tensors(X)

        torch.manual_seed(self.random_state)
        self.net_ = Net(self.kind, seq.shape[2], self.steps_, static.shape[1], self.hidden)
        optimiser = torch.optim.Adam(
            self.net_.parameters(), lr=self.lr, weight_decay=self.weight_decay
        )
        # the last sixth of the training rows, in time order, decides when to stop
        cut = max(1, int(len(t) * 5 / 6))
        best, best_state, waited = np.inf, None, 0
        for _ in range(self.epochs):
            self.net_.train()
            optimiser.zero_grad()
            loss = nn.functional.mse_loss(self.net_(seq[:cut], static[:cut]), t[:cut])
            loss.backward()
            optimiser.step()
            self.net_.eval()
            with torch.no_grad():
                held = (
                    nn.functional.mse_loss(self.net_(seq[cut:], static[cut:]), t[cut:]).item()
                    if cut < len(t)
                    else loss.item()
                )
            if held < best - 1e-6:
                best, waited = held, 0
                best_state = {k: v.clone() for k, v in self.net_.state_dict().items()}
            else:
                waited += 1
                if waited >= self.patience:
                    break
        if best_state is not None:
            self.net_.load_state_dict(best_state)
        self.n_features_in_ = len(columns)
        return self

    def predict(self, X):
        seq, static = self._tensors(X)
        self.net_.eval()
        with torch.no_grad():
            out = self.net_(seq, static).numpy()
        return out * self.y_scale_ + self.y_mean_

    def gradients(self, X) -> np.ndarray:
        """Gradient × input for every row and column: each input's local push on the forecast,
        in the units of the forecast, as the networks' own explanation."""
        seq, static = self._tensors(X)
        seq.requires_grad_(True)
        static.requires_grad_(True)
        self.net_.eval()
        self.net_(seq, static).sum().backward()
        n = len(seq)
        out = np.zeros((n, self.n_features_in_))
        g_seq = (seq.grad * seq).detach().numpy()
        for col, s, step in self.cells_:
            out[:, col] = g_seq[:, step, s]
        if self.statics_:
            g_static = (static.grad * static).detach().numpy()
            for j, col in enumerate(self.statics_):
                out[:, col] = g_static[:, j]
        return out * self.y_scale_
