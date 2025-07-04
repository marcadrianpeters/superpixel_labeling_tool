# Superpixel Labeling GUI

This project provides an interactive GUI tool to accelerate image annotation by leveraging superpixel segmentation. It uses SLIC-based superpixels to divide images into coherent regions, enabling users to label entire segments instead of individual pixels, significantly reducing annotation time and effort.

![Superpixel GUI Screenshot](screenshot.png)

## Features

- PyQt6-based GUI for efficient, manual region labeling using superpixels.
- Batch-compatible pre-segmentation pipeline using SLIC.
- Optional overlay visualization to aid labeling accuracy.
- Jupyter and CLI support for preprocessing.
- Parallel processing support for faster segmentation.
- Logs labeling status (`unlabeled`, `labeled`, `skip`, `review`) in `label_log.csv`.  
- Status updates automatically or via GUI selection.  
- All progress is saved on close, Ctrl+S, and after each frame change.

> **Note:** This tool is designed for binary segmentation labeling. Multi-class annotation is supported through multiple runs, each targeting a different class.

---

## Installation & Setup

### Prerequisites

- **Python 3.12** must be installed and accessible via `python` or `python3`.

> This project is tested with Python 3.12. Older versions may produce unpredictable results.

---

### Quick Setup

The project includes setup scripts for Linux/macOS and Windows (PowerShell) to create a virtual environment and install all dependencies.

#### Linux/macOS

```bash
bash install_env.sh
```

#### Windows (PowerShell)

```powershell
.\setup.ps1
```

> **Execution Policy Note**: If PowerShell restricts script execution, temporarily allow it for the session:
>
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```

---

### Activating the Environment

Before running scripts or the GUI, activate the virtual environment:

#### Linux/macOS

```bash
source .venv/bin/activate
```

#### Windows (PowerShell)

```powershell
.\.venv\Scripts\Activate.ps1
```

---

## Workflow Overview

The GUI now launches via a file dialog to select the dataset directory — no CLI argument is required. However, the dataset **must** follow the required directory structure and either include precomputed superpixel masks or have them manually generated via the GUI.

### Step 1: Precompute Superpixel Masks (Optional but Recommended)

```bash
python run_superpixel_segmentation.py /path/to/dataset \
  --pixels_per_superpixel 150 \
  --num_workers 4
```

- `--pixels_per_superpixel`: Controls the superpixel size.
- `--num_workers`: Number of parallel processes for speedup.

> This step is optional: if `superpixel_masks/` is missing, you can regenerate superpixels manually from within the GUI using **`R` + drag**.

---

### Step 2: Launch the GUI for Labeling

```bash
python gui.py
```

You will be prompted to select a dataset directory via a file dialog.

Expected directory structure:

```
/path/to/dataset/
├── input/                  # input images (required)
├── superpixel_masks/       # optional; can be generated via GUI or script
└── segmentation_masks/     # created by GUI; stores labeled masks
```

> **Note:** If `segmentation_masks/` is missing, it will be created automatically.  
> If `superpixel_masks/` is absent, **you must manually generate masks** using `R` + drag before labeling.

---

## GUI Controls

- **Left-click:** Select/deselect superpixel.
- **Right-click drag:** Brush select.
- **D:** Change brush mode.
- **F:** Fill enclosed holes.
- **X:** Toggle superpixel boundary visibility.
- **C:** Toggle segmentation mask visibility.
- **R + Drag on image:** Regenerate superpixels in selected region.
- **<- / -> (Arrow keys):** Navigate to next or previous image.
- **Space:** Pause/unpause.

> **Hint:** When using `R` + drag, a bounding box is drawn and the superpixels within it are re-segmented, while superpixel outside are kept. This enables rapid creation of segmentation masks with locally adaptive levels of detail.

---

## Licensing Notice

This project uses open-source packages, including libraries under the [GPLv3 License](https://www.gnu.org/licenses/gpl-3.0.en.html). Redistribution of modified versions must comply with GPLv3 terms.