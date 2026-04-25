# SIT Battery Degradation Dataset — Code

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Python utilities and Jupyter notebooks for working with the
**SIT Battery Degradation Dataset** —
22 large-format prismatic LiFePO₄ cells (50 Ah, 3.2 V nominal; Narada FE50B)
cycled over ~18 months at Singapore Institute of Technology (SIT).

> **Dataset download (required):**
> The raw cycling data (~14,800 xlsx/csv files) is published separately at the
> SIT Institutional Research Repository.
> DOI: `[insert SIT IRR DOI here]`
> Download and extract so that `Data/` sits next to this `Code/` folder:
>
> ```
> your-working-directory/
> ├── Data/          ← downloaded from SIT IRR
> │   ├── Repower_001/
> │   ├── Repower_002/
> │   ├── Repower_003/
> │   └── Chroma_101/
> └── Code/          ← this repository
>     ├── sit_utils/
>     ├── 01_quickstart.ipynb
>     └── ...
> ```

---

## Quick start

```bash
# 1  Clone this repository
git clone https://github.com/karthicgrepo/sit-battery-dataset-code.git
cd sit-battery-dataset-code

# 2  Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS

# 3  Install dependencies
pip install -r requirements.txt

# 4  Launch Jupyter
jupyter notebook
```

Open **`01_quickstart.ipynb`** and follow the cells.

---

## Repository layout

```
sit-battery-dataset-code/
├── sit_utils/                    Python loader package
│   ├── __init__.py
│   └── loader.py                 SITDataset / CellData classes
├── 01_quickstart.ipynb           Load data, plot a cycle, view capacity fade
├── 02_capacity_fade_analysis.ipynb
│                                 Temperature & C-rate effect comparisons
├── 03_feature_extraction.ipynb
│                                 Per-cycle health indicators → feature_matrix.csv
├── 04_rul_prediction.ipynb       RUL prediction (curve extrapolation, Ridge ML)
├── requirements.txt
└── README.md
```

---

## `sit_utils` API

```python
from sit_utils import SITDataset, CellData

ds = SITDataset("../Data")      # point to the Data root
ds.list_cells()                 # → ['001-1', '001-2', ..., '101-3', 'ch5', 'ch7']
ds.list_cells(group="G2")       # → cells in a specific group

cell = ds.get_cell("001-1")     # CellData instance
cell.num_cycles                 # → 876
cycle_df = cell.get_cycle(1)    # unified DataFrame (time_s, voltage_V, ...)
fade = cell.capacity_fade()     # DataFrame[cycle, capacity_Ah]

# Temperature data (available for all 20 deep-cycling cells)
temp_df = cell.load_temperature()   # DataFrame[datetime, temperature_C]
cell.has_temperature                # → True

# Micro-cycling (G4 cells: ch5, ch7)
mc = ds.get_cell("ch5")
mc.list_micro_files()               # sorted list of raw CSV Paths
mc_df = mc.load_micro_file(0)       # load one micro-cycling CSV

# Group-level helpers
fade_all = ds.capacity_fade_all()          # all deep-cycling cells combined
ds.plot_capacity_fade(groups=["G1","G2"])   # matplotlib plot
summary = ds.summary()                     # per-cell statistics table
```

### Unified column schema

| Column          | Unit | Description                          |
|-----------------|------|--------------------------------------|
| `time_s`        | s    | Relative time from cycle start       |
| `voltage_V`     | V    | Terminal voltage                     |
| `current_A`     | A    | Current (positive = charge)          |
| `capacity_Ah`   | Ah   | Cumulative capacity within the cycle |
| `energy_Wh`     | Wh   | Cumulative energy                    |
| `temperature_C` | °C   | Surface temperature (where available)|

---

## Experimental groups

| Group | Cells | Discharge C-rate | Environment | Cycling mode  |
|-------|------:|:----------------:|:-----------:|:-------------:|
| G1    | 10    | 1C (50 A)        | Ambient     | Deep cycling  |
| G2    | 4     | 1C (50 A)        | 40 °C       | Deep cycling  |
| G3    | 6     | 2C (100 A)       | 40 °C       | Deep cycling  |
| G4    | 2     | —                | Ambient     | Micro cycling |

> **G4 note:** Micro-cycling data (`ch5`, `ch7`) uses raw Chroma CSV exports.
> Use `cell.list_micro_files()` / `cell.load_micro_file(index)` to access them.
> Capacity fade methods apply to deep-cycling cells (G1–G3) only.

---

## Notebooks summary

| # | Notebook | What it does |
|---|----------|-------------|
| 1 | `01_quickstart` | Loads one cell, plots V/I/T for a single cycle, plots capacity fade, compares groups |
| 2 | `02_capacity_fade_analysis` | Overlays all 20 deep-cycling cells, isolates temperature effect (G1 vs G2), C-rate effect (G2 vs G3), quantifies G1 variability |
| 3 | `03_feature_extraction` | Extracts per-cycle health indicators and writes `feature_matrix.csv` (generated output, not in repo) |
| 4 | `04_rul_prediction` | Predicts Remaining Useful Life via quadratic/linear extrapolation and cross-cell Ridge regression with leave-one-cell-out CV |

---

## Requirements

- Python ≥ 3.9
- pandas, numpy, openpyxl, matplotlib, scikit-learn, jupyter

See `requirements.txt` for pinned minimum versions.

---

## Citation

If you use this code or dataset, please cite the associated publication:

> Ponnambalam, K., Balakrishnan, S., Soh, C. B., Sharma, A. & Lee, S. S.
> "Multi-condition ageing dataset for large-format prismatic LiFePO₄ batteries
> with per-cell thermal monitoring." *Scientific Data* (under review, 2026).
> Code DOI: https://doi.org/10.5281/zenodo.XXXXXXX

---

## Authors

Karthickumar Ponnambalam¹, B. Sivaneasan², Chew Beng Soh¹, Anurag Sharma¹, Sze Sing Lee¹

¹ Newcastle University in Singapore  
² Singapore Institute of Technology

---

## License

This code is released under the **MIT License** — see [LICENSE](LICENSE) for details.  
The accompanying dataset is released under **CC BY 4.0**.
