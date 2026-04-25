"""
SIT Battery Dataset Loader
===========================
Provides ``SITDataset`` and ``CellData`` classes for convenient access to
the SIT LiFePO₄ battery ageing dataset.

Typical usage
-------------
>>> from sit_utils import SITDataset
>>> ds = SITDataset("../Data")
>>> cell = ds.get_cell("001-3")
>>> fade = cell.capacity_fade()          # DataFrame with cycle-level capacity
>>> cycle = cell.get_cycle(10)           # time-series for cycle 10
>>> ds.plot_capacity_fade(groups=["G1", "G2"])
"""

from __future__ import annotations

import os
import re
import glob
import warnings
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Group / cell registry
# ---------------------------------------------------------------------------
GROUP_REGISTRY: dict[str, dict] = {
    "G1": {
        "cells": [
            "001-1", "001-2", "001-3", "001-4",
            "001-5", "001-6", "001-7", "001-8",
            "101-1", "101-3",
        ],
        "c_rate": "1C",
        "environment": "ambient",
        "mode": "deep_cycling",
    },
    "G2": {
        "cells": ["002-1", "002-2", "002-3", "002-4"],
        "c_rate": "1C",
        "environment": "40C_chamber",
        "mode": "deep_cycling",
    },
    "G3": {
        "cells": ["002-5", "002-7", "003-1", "003-3", "003-5", "003-7"],
        "c_rate": "2C",
        "environment": "40C_chamber",
        "mode": "deep_cycling",
    },
    "G4": {
        "cells": ["ch5", "ch7"],
        "c_rate": "micro",
        "environment": "ambient",
        "mode": "micro_cycling",
    },
}

# Map cell ID → tester folder
_CELL_TESTER_MAP: dict[str, str] = {}
for _cid in ["001-1", "001-2", "001-3", "001-4",
             "001-5", "001-6", "001-7", "001-8"]:
    _CELL_TESTER_MAP[_cid] = "Repower_001"
for _cid in ["002-1", "002-2", "002-3", "002-4",
             "002-5", "002-7"]:
    _CELL_TESTER_MAP[_cid] = "Repower_002"
for _cid in ["003-1", "003-3", "003-5", "003-7"]:
    _CELL_TESTER_MAP[_cid] = "Repower_003"
for _cid in ["101-1", "101-3"]:
    _CELL_TESTER_MAP[_cid] = "Chroma_101"
for _cid in ["ch5", "ch7"]:
    _CELL_TESTER_MAP[_cid] = "Chroma_101"

# Map cell ID → group
_CELL_GROUP_MAP: dict[str, str] = {}
for _grp, _info in GROUP_REGISTRY.items():
    for _cid in _info["cells"]:
        _CELL_GROUP_MAP[_cid] = _grp

# Unified column names produced by the loader
UNIFIED_COLUMNS = [
    "time_s", "voltage_V", "current_A", "capacity_Ah",
    "energy_Wh", "temperature_C",
]


# ---------------------------------------------------------------------------
# CellData — wrapper around one cell's data
# ---------------------------------------------------------------------------
class CellData:
    """Provides convenient access to a single cell's cycling and capacity data."""

    def __init__(self, cell_id: str, data_root: str | Path):
        self.cell_id = cell_id
        self.data_root = Path(data_root)
        self.tester = _CELL_TESTER_MAP.get(cell_id)
        self.group = _CELL_GROUP_MAP.get(cell_id)
        if self.tester is None:
            raise ValueError(
                f"Unknown cell ID '{cell_id}'. "
                f"Valid IDs: {sorted(_CELL_TESTER_MAP.keys())}"
            )

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
    def _f_folder(self) -> Path:
        """Path to the Cycle_Data folder for this cell."""
        return (
            self.data_root / self.tester / "Cycle_Data" / self.cell_id
        )

    def _d_file(self) -> Optional[Path]:
        """Path to the Cycle_Summary CSV for this cell."""
        candidate = self.data_root / "Cycle_Summary" / f"{self.cell_id}.csv"
        return candidate if candidate.is_file() else None

    def _d_file_list(self) -> Optional[Path]:
        """Deprecated — returns None (D_File_List no longer published)."""
        return None

    def _temp_file(self) -> Optional[Path]:
        """Path to the standalone per-cell temperature CSV."""
        candidate = (
            self.data_root / self.tester / "Temperature"
            / f"{self.cell_id}_temperature.csv"
        )
        return candidate if candidate.is_file() else None

    def _micro_folder(self) -> Optional[Path]:
        """Path to the Micro_Cycling folder for G4 cells (Channel_5 / Channel_7)."""
        channel_map = {"ch5": "Channel_5", "ch7": "Channel_7"}
        folder_name = channel_map.get(self.cell_id)
        if folder_name is None:
            return None
        candidate = self.data_root / self.tester / "Micro_Cycling" / folder_name
        return candidate if candidate.is_dir() else None

    # ------------------------------------------------------------------
    # Simplified cycle files (F folder)
    # ------------------------------------------------------------------
    def list_cycle_files(self) -> list[Path]:
        """Return sorted list of simplified-cycle XLSX files.

        For deep-cycling cells these are per-cycle XLSX files.
        For micro-cycling cells (G4) this returns an empty list;
        use ``list_micro_files()`` instead.
        """
        folder = self._f_folder()
        if not folder.is_dir():
            return []
        return sorted(folder.glob("*.xlsx"))

    def get_cycle(self, cycle_num: int) -> pd.DataFrame:
        """Load a single cycle's time-series data (1-indexed).

        Returns a DataFrame with unified column names.
        """
        files = self.list_cycle_files()
        if cycle_num < 1 or cycle_num > len(files):
            raise IndexError(
                f"Cycle {cycle_num} out of range [1, {len(files)}] "
                f"for cell {self.cell_id}"
            )
        return self._load_f_file(files[cycle_num - 1])

    def get_cycles(
        self, start: int = 1, end: Optional[int] = None
    ) -> dict[int, pd.DataFrame]:
        """Load a range of cycles. Returns {cycle_num: DataFrame}."""
        files = self.list_cycle_files()
        end = end or len(files)
        return {
            i: self._load_f_file(files[i - 1])
            for i in range(start, min(end, len(files)) + 1)
        }

    def _load_f_file(self, fpath: Path) -> pd.DataFrame:
        """Read one cycle data XLSX and return a unified DataFrame."""
        df = pd.read_excel(fpath)
        return self._unify_columns(df)

    @staticmethod
    def _unify_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Map vendor-specific column names to unified schema."""
        col_map: dict[str, str] = {}
        for c in df.columns:
            cl = c.lower()
            if "relative time" in cl or c == "time_s":
                col_map[c] = "time_s"
            elif "voltage" in cl:
                col_map[c] = "voltage_V"
            elif "current" in cl:
                col_map[c] = "current_A"
            elif cl in ("capacity(ah)", "capacity_ah"):
                col_map[c] = "capacity_Ah"
            elif "energy" in cl or cl in ("wh",):
                col_map[c] = "energy_Wh"
            elif "celsius" in cl or "temperature" in cl:
                # Take the first temperature column if multiple exist
                if "temperature_C" not in col_map.values():
                    col_map[c] = "temperature_C"
        out = df.rename(columns=col_map)
        # Keep only unified + any unmapped
        return out

    # ------------------------------------------------------------------
    # Capacity fade (from Cycle_Summary CSV or cycle files)
    # ------------------------------------------------------------------
    def capacity_fade(self) -> pd.DataFrame:
        """Return a DataFrame with columns ``[cycle, capacity_Ah]``.

        Uses the Cycle_Summary CSV when available; otherwise reads
        each cycle data file to estimate discharge capacity.
        """
        d_file = self._d_file()
        if d_file is not None:
            return self._fade_from_summary(d_file)
        return self._fade_from_f()

    def _fade_from_summary(self, fpath: Path) -> pd.DataFrame:
        """Parse a Cycle_Summary CSV for discharge capacity per cycle."""
        df = pd.read_csv(fpath)
        dis = df[df["Type"] == "discharge"].copy()
        dis = dis.reset_index(drop=True)
        out = pd.DataFrame({
            "cycle": range(1, len(dis) + 1),
            "capacity_Ah": dis["Capacity_Ah"].values,
        })
        return out

    def _fade_from_f(self) -> pd.DataFrame:
        """Estimate discharge capacity from each cycle data file."""
        files = self.list_cycle_files()
        caps = []
        for i, f in enumerate(files, 1):
            try:
                df = pd.read_excel(f, sheet_name="Discharge")
                df = self._unify_columns(df)
                # Discharge = negative current; capacity = max Ah during discharge
                if "capacity_Ah" in df.columns:
                    caps.append({"cycle": i, "capacity_Ah": df["capacity_Ah"].max()})
            except Exception:
                continue
        return pd.DataFrame(caps)

    # ------------------------------------------------------------------
    # Temperature
    # ------------------------------------------------------------------
    def load_temperature(self) -> pd.DataFrame:
        """Load the standalone per-cell temperature CSV.

        Returns a DataFrame with columns ``[datetime, temperature_C]``.
        Raises FileNotFoundError if no temperature file exists.
        """
        tf = self._temp_file()
        if tf is None:
            raise FileNotFoundError(
                f"No temperature file found for cell {self.cell_id}"
            )
        df = pd.read_csv(tf, parse_dates=["datetime"])
        return df

    @property
    def has_temperature(self) -> bool:
        """Whether a standalone temperature CSV is available."""
        return self._temp_file() is not None

    # ------------------------------------------------------------------
    # Micro-cycling (G4 cells only)
    # ------------------------------------------------------------------
    def list_micro_files(self) -> list[Path]:
        """Return sorted list of micro-cycling CSV files (G4 cells only)."""
        folder = self._micro_folder()
        if folder is None or not folder.is_dir():
            return []
        return sorted(folder.glob("*.csv"))

    def load_micro_file(self, index: int) -> pd.DataFrame:
        """Load a single micro-cycling CSV by index (0-based).

        The raw Chroma export has 4 header lines followed by the data.
        """
        files = self.list_micro_files()
        if index < 0 or index >= len(files):
            raise IndexError(
                f"Micro file index {index} out of range [0, {len(files)-1}] "
                f"for cell {self.cell_id}"
            )
        return pd.read_csv(files[index], skiprows=4)

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------
    @property
    def total_cycles(self) -> int:
        """Total number of available cycle files."""
        return len(self.list_cycle_files())

    @property
    def num_cycles(self) -> int:
        """Alias for ``total_cycles``."""
        return self.total_cycles

    def __repr__(self) -> str:
        return (
            f"CellData('{self.cell_id}', group={self.group}, "
            f"tester={self.tester}, cycles={self.total_cycles})"
        )


# ---------------------------------------------------------------------------
# SITDataset — top-level entry point
# ---------------------------------------------------------------------------
class SITDataset:
    """Top-level handle to the SIT battery degradation dataset.

    Parameters
    ----------
    data_root : str or Path
        Path to the root folder containing Repower_001/, Repower_002/,
        Repower_003/, Chroma_101/ and Documentation/.
    """

    def __init__(self, data_root: str | Path):
        self.data_root = Path(data_root)
        if not self.data_root.is_dir():
            raise FileNotFoundError(
                f"Data root not found: {self.data_root}"
            )
        # Pre-build cell objects for all known IDs whose folders exist
        self._cells: dict[str, CellData] = {}
        for cell_id in sorted(_CELL_TESTER_MAP.keys()):
            try:
                c = CellData(cell_id, self.data_root)
                if (c._f_folder().is_dir()
                        or c._d_file() is not None
                        or c._micro_folder() is not None):
                    self._cells[cell_id] = c
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Cell access
    # ------------------------------------------------------------------
    def get_cell(self, cell_id: str) -> CellData:
        """Return a ``CellData`` object for the given cell ID."""
        if cell_id in self._cells:
            return self._cells[cell_id]
        return CellData(cell_id, self.data_root)

    def list_cells(self, group: Optional[str] = None) -> list[str]:
        """List available cell IDs, optionally filtered by group."""
        ids = list(self._cells.keys())
        if group:
            grp = GROUP_REGISTRY.get(group, {})
            allowed = set(grp.get("cells", []))
            ids = [c for c in ids if c in allowed]
        return ids

    def get_group(self, group: str) -> list[CellData]:
        """Return list of ``CellData`` objects for a group (G1–G4)."""
        return [self._cells[c] for c in self.list_cells(group)]

    # ------------------------------------------------------------------
    # Capacity fade (batch)
    # ------------------------------------------------------------------
    def capacity_fade_all(
        self, groups: Optional[list[str]] = None
    ) -> pd.DataFrame:
        """Build a combined capacity-fade DataFrame for multiple groups.

        Returns columns: ``cell_id, group, cycle, capacity_Ah``.
        """
        frames = []
        cells = []
        if groups:
            for g in groups:
                cells.extend(self.get_group(g))
        else:
            cells = list(self._cells.values())

        for c in cells:
            try:
                fade = c.capacity_fade()
                fade["cell_id"] = c.cell_id
                fade["group"] = c.group
                frames.append(fade)
            except Exception as exc:
                warnings.warn(f"Skipping {c.cell_id}: {exc}")
        if not frames:
            return pd.DataFrame(columns=["cell_id", "group", "cycle", "capacity_Ah"])
        return pd.concat(frames, ignore_index=True)[
            ["cell_id", "group", "cycle", "capacity_Ah"]
        ]

    # ------------------------------------------------------------------
    # Plotting helpers
    # ------------------------------------------------------------------
    def plot_capacity_fade(
        self,
        groups: Optional[list[str]] = None,
        ax=None,
        title: str = "Capacity Fade Curves",
    ):
        """Plot capacity vs cycle number for selected groups.

        Parameters
        ----------
        groups : list of str, optional
            e.g. ["G1", "G2"]. If None, plots all groups.
        ax : matplotlib Axes, optional
        title : str

        Returns
        -------
        matplotlib Axes
        """
        import matplotlib.pyplot as plt

        fade_df = self.capacity_fade_all(groups)
        if fade_df.empty:
            warnings.warn("No capacity data found.")
            return None

        if ax is None:
            _, ax = plt.subplots(figsize=(10, 5))

        group_colours = {"G1": "#1f77b4", "G2": "#ff7f0e",
                         "G3": "#2ca02c", "G4": "#d62728"}

        for cell_id, cdf in fade_df.groupby("cell_id"):
            grp = cdf["group"].iloc[0]
            colour = group_colours.get(grp, "#888888")
            ax.plot(
                cdf["cycle"], cdf["capacity_Ah"],
                linewidth=0.8, alpha=0.7, color=colour,
                label=f"{cell_id} ({grp})",
            )

        # De-duplicate legend labels
        handles, labels = ax.get_legend_handles_labels()
        seen: dict[str, int] = {}
        unique_h, unique_l = [], []
        for h, l in zip(handles, labels):
            grp_tag = l.split("(")[-1].rstrip(")")
            if grp_tag not in seen:
                seen[grp_tag] = 0
                unique_h.append(h)
                unique_l.append(grp_tag)

        ax.legend(unique_h, unique_l, loc="upper right")
        ax.set_xlabel("Cycle number")
        ax.set_ylabel("Discharge capacity (Ah)")
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        return ax

    # ------------------------------------------------------------------
    # Summary table
    # ------------------------------------------------------------------
    def summary(self) -> pd.DataFrame:
        """Return a one-row-per-cell summary DataFrame."""
        rows = []
        for cell_id, c in self._cells.items():
            row = {
                "cell_id": cell_id,
                "group": c.group,
                "tester": c.tester,
                "total_cycles": c.total_cycles,
            }
            try:
                fade = c.capacity_fade()
                if not fade.empty:
                    row["initial_capacity_Ah"] = fade["capacity_Ah"].iloc[0]
                    row["final_capacity_Ah"] = fade["capacity_Ah"].iloc[-1]
                    row["retention_pct"] = round(
                        100 * row["final_capacity_Ah"] / row["initial_capacity_Ah"], 2
                    )
            except Exception:
                pass
            rows.append(row)
        return pd.DataFrame(rows)

    def __repr__(self) -> str:
        return (
            f"SITDataset(root='{self.data_root}', "
            f"cells={len(self._cells)})"
        )
