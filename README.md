# Superpixel Labeling Tool

This project provides an interactive GUI to accelerate image annotation using superpixel segmentation. It uses SLIC-based superpixels to divide images into coherent regions, enabling users to label entire segments instead of individual pixels - significantly reducing annotation time and effort.

![Superpixel GUI Screenshot](assets/screenshot.png)

---

## Features

- PyQt6-based GUI for efficient, manual region labeling using superpixels.  
- Batch-compatible pre-segmentation pipeline using SLIC.  
- Optional overlay visualization to aid labeling accuracy.  
- Jupyter and CLI support for preprocessing.  
- Parallel processing support for faster segmentation.  
- Progress logging in `label_log.csv`.  
- Auto-save on close, Ctrl+S, and after each frame.  
- Installable via pip or available as standalone binaries.  

> **Note:** This tool is designed for binary segmentation labeling. Multi-class annotation is supported through multiple runs, each targeting a different class.

---

## Quick Start Options

### **Option 1:** Use via PyPI (Recommended for Python Users)

```bash
pip install superpixel_labeling_tool
```

Then run:

- **GUI**:  
  ```bash
  superpixel_labeling_tool
  ```

- **CLI for preprocessing**:  
  ```bash
  run_superpixel_segmentation /path/to/dataset --pixels_per_superpixel 150
  ```

---

### **Option 2:** Use Prebuilt Executables (No Python Required)

Download the latest release from the [Releases page](https://github.com/marcadrianpeters/superpixel_labeling_tool/releases):

1. **Download**  
   - **Linux:** `superpixel_labeling_tool-linux`  
   - **Windows:** `superpixel_labeling_tool.exe`

2. **Make executable (Linux)**  
   ```bash
   chmod +x superpixel_labeling_tool-linux
   ```

3. **Run**  
   - **Linux:** `./superpixel_labeling_tool-linux`  
   - **Windows:** Double-click `superpixel_labeling_tool.exe`

> On Windows, a security warning may appear. Click **“Run anyway”** to proceed.

4. **Select Your Dataset Folder**  
   The folder must contain an `input/` subdirectory with images.

---

## GUI Controls

- **Left-click:** Select/deselect superpixel.  
- **Right-click drag:** Brush select.  
- **D:** Change brush mode.  
- **F:** Fill enclosed holes.  
- **X:** Toggle superpixel boundary visibility.  
- **C:** Toggle segmentation mask visibility.  
- **R + Drag on image:** Regenerate superpixels in selected region.  
- **<- / -> (Arrow keys):** Navigate images.  
- **Space:** Pause/unpause.

---

## Dataset Structure & Workflow

Your dataset must follow this structure:

```
/path/to/dataset/
├── input/                  # Required: input images
├── superpixel_masks/       # Optional: generated via CLI or GUI
└── segmentation_masks/     # Created by GUI for labeled output
```

### **Step 1**: Precompute Superpixels (Optional)

```bash
run_superpixel_segmentation /path/to/dataset --pixels_per_superpixel 150 --num_workers 4
```

> If `superpixel_masks/` is missing, you can generate them via **R + drag** in the GUI.

### **Step 2:** Launch the GUI

```bash
superpixel_labeling_tool
```
---

## From Source (for Developers)

### **Prerequisites:**

- Python 3.12
- Git

### **Setup:**

Clone the repo and run:

#### Linux/macOS

```bash
bash install_env.sh
source .venv/bin/activate
```

#### Windows (PowerShell)

```powershell
.\setup.ps1
.\.venv\Scripts\Activate.ps1
```

> If scripts are blocked, use:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```

---

## Licensing Notice

This project uses open-source packages, including libraries under the [GPLv3 License](https://www.gnu.org/licenses/gpl-3.0.en.html). Redistribution of modified versions must comply with GPLv3 terms.