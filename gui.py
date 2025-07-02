"""
PyQt6-based interactive tool for annotating images using superpixel masks.

This tool loads RGB images alongside their corresponding superpixel segmentation masks,
allowing users to visually select, deselect, and modify superpixel regions via
clicking and brushing. It provides features like boundary overlay toggling, hole filling
within selections, brush mode switching (add/remove), and keyboard shortcuts for
efficient navigation and editing.

The tool saves binary segmentation masks for each image based on user selections and
maintains a CSV log tracking the labeling status (unlabeled, labeled, skipped, review)
to support organized annotation workflows.

Designed to streamline semi-automated image segmentation labeling by leveraging
superpixel segmentation for faster and more precise region selection.
"""

from __future__ import annotations
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout
import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.segmentation import find_boundaries
from scipy.ndimage import binary_fill_holes

from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QPoint, QSize, QRect
from PyQt6.QtGui import QImage, QPixmap, QAction, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QSlider, QProgressBar, QToolBar, QMessageBox, QLabel, QRubberBand,
    QComboBox
)


import time

from superpixel_segmentation import segment_image_cropped, SegmenterConfig

# ---------------------------------------------------------------- utilities


def natural_sort(seq):
    import re
    return sorted(seq, key=lambda s: [
        int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))
    ])


def pil2qimage(im: Image.Image) -> QImage:
    if im.mode == "RGB":
        return QImage(im.tobytes(), im.width, im.height, QImage.Format.Format_RGB888)
    if im.mode == "RGBA":
        return QImage(im.tobytes(), im.width, im.height, QImage.Format.Format_RGBA8888)
    return pil2qimage(im.convert("RGBA"))

# ---------------------------------------------------------------- ImageView


class ImageView(QGraphicsView):
    BND_RGBA = (0, 0, 255, 64)
    HIL_RGBA = (0, 255, 0, 64)        # more transparent highlight
    CLICK_THRESH = 4  # px

    def __init__(self, hint_cb):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setTransformationAnchor(self.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(self.ViewportAnchor.AnchorUnderMouse)
        self.setMouseTracking(True)
        self._hint = hint_cb                    # show transient hints

        self.rgb:  Image.Image | None = None
        self.mask: np.ndarray | None = None
        self.sel:  set[int] = set()

        self.bnd_item: QGraphicsPixmapItem | None = None
        self.hil_item: QGraphicsPixmapItem | None = None
        self._regen_mode = False
        self._rb = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self._rb_origin: QPoint | None = None

        self.pan_start: QPointF | None = None
        self.dragging = False
        self.brushing = False
        self.brush_add = True                 # True add, False remove
        self.show_bnd = True
        self.show_hil = True

    regionSelected = pyqtSignal(int, int, int, int)   # x1, y1, x2, y2

    def enable_region_mode(self):
        """Next left‑drag draws a rectangle instead of panning."""
        self._regen_mode = True
        self._hint("Draw a rectangle to recompute super‑pixels")

    def _leave_region_mode(self):
        self._regen_mode = False

    # ----------------------------------------------------------- data load

    def load(self, rgb: Image.Image, mask: np.ndarray | None):
        self.scene.clear()
        self.rgb, self.mask, self.sel = rgb, mask, set()

        self.scene.addPixmap(QPixmap.fromImage(pil2qimage(rgb))).setZValue(0)
        if mask is not None:
            b = find_boundaries(mask, mode="thick", background=0)
            rgba = np.zeros((*mask.shape, 4), np.uint8)
            rgba[b] = self.BND_RGBA
            qb = QImage(rgba.data, mask.shape[1], mask.shape[0],
                        rgba.strides[0], QImage.Format.Format_RGBA8888)
            self.bnd_item = self.scene.addPixmap(QPixmap.fromImage(qb))
            self.bnd_item.setZValue(1)
            self.bnd_item.setVisible(self.show_bnd)
        else:
            self.bnd_item = None
        self.hil_item = None
        self.setSceneRect(QRectF(0, 0, rgb.width, rgb.height))
        self.resetTransform()
        self.fitInView(self.sceneRect(),
                       Qt.AspectRatioMode.KeepAspectRatio)  # auto zoom

    # ------------------------------------------------------ overlay refresh

    def _refresh_hilite(self):
        if self.mask is None or not self.sel:
            if self.hil_item:
                self.scene.removeItem(self.hil_item)
                self.hil_item = None
            return

        # create sel_mask and QImage as before...
        sel_mask = np.isin(self.mask, np.fromiter(self.sel, self.mask.dtype))
        rgba = np.zeros((*sel_mask.shape, 4), np.uint8)
        rgba[sel_mask] = self.HIL_RGBA
        qh = QImage(rgba.data, sel_mask.shape[1], sel_mask.shape[0],
                    rgba.strides[0], QImage.Format.Format_RGBA8888)
        pm = QPixmap.fromImage(qh)

        if self.hil_item is None:
            self.hil_item = self.scene.addPixmap(pm)
            self.hil_item.setZValue(2)
        else:
            self.hil_item.setPixmap(pm)

        # New: respect the flag
        self.hil_item.setVisible(self.show_hil)

    # --------------------------------------------------------- interaction

    def wheelEvent(self, event):
        zoom_in_factor = 1.25
        zoom_out_factor = 1 / zoom_in_factor
        zoom_factor = zoom_in_factor if event.angleDelta().y() > 0 else zoom_out_factor
        self.scale(zoom_factor, zoom_factor)

    def mousePressEvent(self, ev):
        if self._regen_mode and ev.button() == Qt.MouseButton.LeftButton:
            self._rb_origin = ev.pos()
            self._rb.setGeometry(QRect(self._rb_origin, QSize()))
            self._rb.show()
            return                    # don’t start panning
        elif ev.button() == Qt.MouseButton.LeftButton:
            self.pan_start = ev.pos()
            self.dragging = False
        elif ev.button() == Qt.MouseButton.RightButton:
            self.brushing = True
            self._brush(ev.pos())
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._regen_mode and self._rb_origin:
            self._rb.setGeometry(QRect(self._rb_origin, ev.pos()).normalized())
            return
        elif ev.buttons() & Qt.MouseButton.LeftButton and self.pan_start:
            d = ev.pos() - self.pan_start
            if d.manhattanLength() >= self.CLICK_THRESH:
                self.dragging = True
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            self.pan_start = ev.pos()
        if self.brushing:
            self._brush(ev.pos())
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._regen_mode and ev.button() == Qt.MouseButton.LeftButton:
            self._rb.hide()
            p1 = self.mapToScene(self._rb_origin)
            p2 = self.mapToScene(ev.pos())
            x1, y1 = map(int, (min(p1.x(), p2.x()), min(p1.y(), p2.y())))
            x2, y2 = map(int, (max(p1.x(), p2.x()), max(p1.y(), p2.y())))
            self.regionSelected.emit(x1, y1, x2, y2)
            self._leave_region_mode()
            return
        elif ev.button() == Qt.MouseButton.LeftButton and self.pan_start:
            if not self.dragging:
                self._toggle_sp(ev.pos())
            self.pan_start = None
        elif ev.button() == Qt.MouseButton.RightButton:
            self.brushing = False
        super().mouseReleaseEvent(ev)

    # -------------------------------------------------- helpers
    def _pos2id(self, pos) -> int | None:
        if self.mask is None:
            return None
        p = self.mapToScene(pos)
        x, y = int(p.x()), int(p.y())
        if 0 <= x < self.mask.shape[1] and 0 <= y < self.mask.shape[0]:
            return int(self.mask[y, x])
        return None

    def _toggle_sp(self, pos):
        sp = self._pos2id(pos)
        if sp is None:
            return
        (self.sel.remove if sp in self.sel else self.sel.add)(sp)
        self._refresh_hilite()

    def toggle_hil(self):
        """Toggle whether selection highlight is shown."""
        # Flip the flag
        self.show_hil = not getattr(self, "show_hil", True)
        # If there's an existing highlight item, update its visibility
        if self.hil_item:
            self.hil_item.setVisible(self.show_hil)
        mode = "ON" if self.show_hil else "OFF"
        self._hint(f"Selection overlay: {mode}")
        return mode

    def _brush(self, pos):
        sp = self._pos2id(pos)
        if sp is None:
            return
        if self.brush_add:
            if sp not in self.sel:
                self.sel.add(sp)
        else:
            if sp in self.sel:
                self.sel.remove(sp)
        self._refresh_hilite()

    def fill(self):
        if self.mask is None or not self.sel:
            return
        filled = binary_fill_holes(np.isin(self.mask, list(self.sel)))
        self.sel.update(map(int, np.unique(self.mask[filled])))
        self._refresh_hilite()

    def toggle_brush_mode(self):
        self.brush_add = not self.brush_add
        mode = "Add" if self.brush_add else "Remove"
        self._hint(f"Brush = {mode}")
        return mode

# ---------------------------------------------------------------- MainWindow


class PixelsPerSPDialog(QDialog):
    def __init__(self, initial_value: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adjust Superpixel Parameter")
        self.value = initial_value

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Pixels per superpixel:"))

        self.edit = QLineEdit(str(initial_value), self)
        layout.addWidget(self.edit)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("OK", self)
        btn_cancel = QPushButton("Cancel", self)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

    def get_value(self):
        try:
            val = int(self.edit.text())
            if val <= 0:
                raise ValueError("Value must be positive")
            return val
        except Exception:
            return None


class MainWindow(QMainWindow):
    CSV_NAME = "label_log.csv"
    STATUSES = ("unlabeled", "labeled", "skip", "review")

    def __init__(self, base: Path):
        super().__init__()
        self.base = base
        self.in_dir = base / "input"
        self.mask_dir = base / "superpixel_masks"
        self.out_dir = base / "segmentation_masks"
        self.setWindowTitle(f"Superpixel Segmentation Tool ({base.name})")
        for d in (self.in_dir, self.mask_dir, self.out_dir):
            d.mkdir(exist_ok=True)

        self.images = natural_sort([
            p for p in self.in_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
        ])
        if not self.images:
            QMessageBox.critical(self, "Err", "No images in input/")
            sys.exit(1)

        self.cfg = SegmenterConfig(
            input_dir=self.in_dir,
            output_masks=self.mask_dir,
            output_overlays=self.base / "superpixel_overlays",
            pixels_per_superpixel=150,
            num_workers=1,
        )

        # ------------ CSV ledger  (id, filename, status, seconds)
        self.csv_path = base / self.CSV_NAME

        if self.csv_path.exists():
            # → trust the CSV completely, do **not** rescan input/ dir
            self.images, self.status, self.time_spent = [], {}, {}
            with self.csv_path.open() as f:
                for row in csv.DictReader(f):
                    self.images.append(self.in_dir / row["filename"])
                    self.status[row["filename"]] = row["status"]
                    self.time_spent[row["filename"]] = float(
                        row.get("seconds", 0))
        else:
            # → first run: enumerate directory and create fresh ledger
            self.images = natural_sort([
                p for p in self.in_dir.iterdir()
                if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
            ])
            self.status = {p.name: "unlabeled" for p in self.images}
            self.time_spent = {p.name: 0.0 for p in self.images}
            self._write_csv()

        # start on first image without a saved segmentation mask
        self.idx = next((i for i, p in enumerate(self.images)
                         if not (self.out_dir / f"{p.stem}_binary.png").exists()), 0)

        # ------------- central image view
        self.view = ImageView(self._hint)

        self.view.regionSelected.connect(self.regen_superpixels)

        # ------------- horizontal toolbar (top)
        tb = QToolBar("Tools")
        tb.setIconSize(QSize(24, 24))
        tb.setOrientation(Qt.Orientation.Horizontal)

        def make_act(text, slot, sc=None):
            if sc is None:
                sc = QKeySequence()  # empty shortcut
            return QAction(text, self, triggered=slot, shortcut=sc)
        tb.addAction(make_act("🖌 Brush mode (d)", self.toggle_brush, "d"))
        tb.addAction(make_act("➕ Select all", self.select_all))
        tb.addAction(make_act("✖ Clear",      self.clear_sel))
        tb.addAction(make_act("⬛ Fill (f)",       self.fill_inner, "f"))
        tb.addAction(make_act("🔲 Toggle bounds (x)", self.toggle_overlay, "x"))
        tb.addAction(make_act("🔳 Toggle selection (c)",
                     self.toggle_selection_overlay, "c"))
        tb.addSeparator()
        self.status_combo = QComboBox()
        self.status_combo.addItems(self.STATUSES)
        self.status_combo.currentTextChanged.connect(
            self._combo_status_changed)
        tb.addWidget(self.status_combo)
        tb.addSeparator()
        tb.addAction(make_act("♻ Regenerate superpixel (r)",
                     self.start_regen_mode, "r"))
        tb.addSeparator()
        tb.addAction(make_act("⏸ Pause (Space)", self._toggle_pause, "space"))
        tb.addSeparator()

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        # ------------- navigation / progress bar (bottom)
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.clicked.connect(self.prev_image)
        self.btn_next = QPushButton("Next ▶")
        self.btn_next.clicked.connect(self.next_image)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(len(self.images))
        self.slider.setValue(self.idx + 1)
        self.slider.valueChanged.connect(self._slider_changed)

        self.idx_edit = QLineEdit(str(self.idx + 1))
        self.idx_edit.setMaximumWidth(60)
        self.idx_edit.returnPressed.connect(self._edit_changed)

        self.go_btn = QPushButton("Go")
        self.go_btn.clicked.connect(self._edit_changed)

        self.total_lbl = QLabel(f"/ {len(self.images)}")

        self.prog = QProgressBar()
        self.prog.setRange(0, len(self.images))
        self._update_progress()
        self.prog.setTextVisible(True)

        bottom_bar = QHBoxLayout()
        for w in (self.btn_prev, self.slider, self.idx_edit, self.go_btn,
                  self.total_lbl, self.prog, self.btn_next):
            bottom_bar.addWidget(w)
        bottom_widget = QWidget()
        bottom_widget.setLayout(bottom_bar)

        # ------------- main layout
        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(4, 4, 4, 4)
        v.addWidget(self.view)        # image view in the middle
        v.addWidget(bottom_widget)    # navigation at the bottom
        self.setCentralWidget(central)

        self.resize(1200, 800)

        # ---- timing ----------------------------------------------------
        self.start_time: float | None = None     # current‑image stopwatch start
        self.paused = False                      # pause flag
        self.pause_overlay: QWidget | None = None  # full‑size black widget

        self._load_current()

        # Left arrow → previous image
        sc_prev = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        sc_prev.setContext(Qt.ShortcutContext.WindowShortcut)
        sc_prev.activated.connect(self.prev_image)

        # Right arrow → next image
        sc_next = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        sc_next.setContext(Qt.ShortcutContext.WindowShortcut)
        sc_next.activated.connect(self.next_image)

    # ------------------------------ keep pause overlay full‑size

    def resizeEvent(self, event):
        """Ensure the black pause overlay always covers the whole window."""
        super().resizeEvent(event)
        if self.pause_overlay and self.pause_overlay.isVisible():
            self.pause_overlay.setGeometry(self.centralWidget().rect())

    # ------------------------------ graceful shutdown

    def closeEvent(self, event):
        """Save timer, mask, and CSV when the user closes the window."""
        # add elapsed time for the current image
        if 0 <= self.idx < len(self.images) and self.start_time is not None and not self.paused:
            fname = self.images[self.idx].name
            self.time_spent[fname] += time.perf_counter() - self.start_time

        # save mask (status‑safe) and csv
        self._save_binary_mask()   # calls _write_csv() internally

        super().closeEvent(event)

    # ------------------------------ hint helper
    def _hint(self, msg, msec=2000):
        self.statusBar().showMessage(msg, msec)

    # ------------------------------ CSV ledger helpers
    def _write_csv(self):
        with self.csv_path.open("w", newline="") as f:
            w = csv.DictWriter(
                f, fieldnames=["id", "filename", "status", "seconds"])
            w.writeheader()
            for idx, p in enumerate(self.images):
                w.writerow({
                    "id": idx,
                    "filename": p.name,
                    "status": self.status[p.name],
                    "seconds": int(self.time_spent[p.name])
                })

    # ------------------------------ progress helper
    def _update_progress(self):
        labeled_count = sum(1 for img in self.images
                            if (self.out_dir / f"{img.stem}_binary.png").exists())
        self.prog.setValue(labeled_count)
        total = len(self.images)
        # Count statuses in the CSV-ledger dict: self.status maps filename -> status
        counts = {"labeled": 0, "skip": 0, "review": 0}
        for fname, status in self.status.items():
            if status in counts:
                counts[status] += 1
        # “Processed” = any of labeled/skip/review
        processed = counts["labeled"] + counts["skip"] + counts["review"]
        # Update the bar
        self.prog.setRange(0, total)
        self.prog.setValue(processed)
        # Show breakdown text
        # Show only "processed/total", e.g. "10/30"
        # Use Qt’s built-in placeholders: %v = value, %m = maximum
        self.prog.setFormat("%v/%m")

    # ------------------------------ navigation
    def _load_current(self):
        """Load the image at self.idx, reset timer, and refresh all UI state."""
        # ----- bounds check -------------------------------------------------
        if not (0 <= self.idx < len(self.images)):
            self._hint("Done")
            return

        # ----- leave any paused state --------------------------------------
        if self.pause_overlay is not None:
            self.pause_overlay.deleteLater()
            self.pause_overlay = None
        self.paused = False
        for w in (
            self.btn_prev, self.btn_next, self.slider,
            self.idx_edit, self.go_btn, self.status_combo
        ):
            w.setEnabled(True)

        # ----- load RGB + superpixel mask ----------------------------------
        p = self.images[self.idx]
        m = self.mask_dir / f"{p.stem}.png"
        rgb = Image.open(p).convert("RGB")
        mask = np.array(Image.open(m), dtype=np.uint16) if m.exists() else None
        self.view.load(rgb, mask)

        # ----- start new timer ---------------------------------------------
        self.start_time = time.perf_counter()

        # ----- restore previous selection (if any) -------------------------
        bin_path = self.out_dir / f"{p.stem}_binary.png"
        if bin_path.exists() and mask is not None:
            binary = np.array(Image.open(bin_path), dtype=bool)
            sel_ids = np.unique(mask[binary])
            sel_ids = sel_ids[sel_ids != 0]
            self.view.sel = set(map(int, sel_ids))
            self.view._refresh_hilite()

        # ----- update navigation widgets -----------------------------------
        # slider (block to avoid recursion)
        self.slider.blockSignals(True)
        self.slider.setValue(self.idx + 1)
        self.slider.blockSignals(False)

        # index edit & progress bar
        self.idx_edit.setText(str(self.idx + 1))
        self._update_progress()

        # status combo (no signal while setting)
        self.status_combo.blockSignals(True)
        self.status_combo.setCurrentText(self.status[p.name])
        self.status_combo.blockSignals(False)

    def _save_current_and_jump(self, target_idx):
        # 1) stop timer for the image we are leaving
        if 0 <= self.idx < len(self.images) and self.start_time is not None and not self.paused:
            fname = self.images[self.idx].name
            self.time_spent[fname] += time.perf_counter() - self.start_time

        # 2) always save current mask
        if 0 <= self.idx < len(self.images):
            self._save_binary_mask()
        if 0 <= target_idx < len(self.images):
            self.idx = target_idx
            self._load_current()

    def prev_image(self):
        if self.paused:
            return
        self._save_current_and_jump(self.idx - 1)

    def next_image(self):
        if self.paused:
            return
        self._save_current_and_jump(self.idx + 1)

    def _slider_changed(self, v):
        if self.paused:
            return
        self._save_current_and_jump(v - 1)

    def _edit_changed(self):
        if self.paused:
            return
        try:
            i = int(self.idx_edit.text()) - 1
        except ValueError:
            self.idx_edit.setText(str(self.idx + 1))
            return
        self._save_current_and_jump(i)

    # ------------------------------ status ops
    def set_status(self, s):
        fname = self.images[self.idx].name
        self.status[fname] = s
        self.status_combo.setCurrentText(s)
        self._write_csv()
        # For skip/review we still advance.
        self.next_image()

    def _combo_status_changed(self, text: str):
        fname = self.images[self.idx].name
        self.status[fname] = text
        self._write_csv()

    def _toggle_pause(self):
        """
        Pause ↔ resume the timer and UI.

        • While paused
            – elapsed time for the current image is added to self.time_spent
            – navigation widgets are disabled
            – a full‑window black overlay with a centred “PAUSED” label is shown
        • When resumed
            – overlay is removed
            – navigatv()
        self.next_image()ion widgets are re‑enabled
            – timer (self.start_time) restarts
        """
        if self.paused:                       # ---------- RESUME ----------
            self.paused = False
            self.start_time = time.perf_counter()

            if self.pause_overlay is not None:
                self.pause_overlay.deleteLater()
                self.pause_overlay = None

            # re‑enable nav / status widgets
            for w in (
                self.btn_prev, self.btn_next, self.slider,
                self.idx_edit, self.go_btn, self.status_combo
            ):
                w.setEnabled(True)

            self._hint("Resumed")

        else:                                 # ---------- PAUSE ----------
            self.paused = True

            # accumulate elapsed time so far
            if self.start_time is not None:
                fname = self.images[self.idx].name
                self.time_spent[fname] += time.perf_counter() - self.start_time

            # disable nav / status widgets
            for w in (
                self.btn_prev, self.btn_next, self.slider,
                self.idx_edit, self.go_btn, self.status_combo
            ):
                w.setEnabled(False)

            # create full‑window black overlay
            self.pause_overlay = QWidget(self.centralWidget())
            self.pause_overlay.setStyleSheet("background:black;")
            self.pause_overlay.setGeometry(self.centralWidget().rect())

            # centred “PAUSED” label
            lbl = QLabel("⏸  PAUSED")                 # parent set via layout
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color:white; font-size:72px;")

            lay = QVBoxLayout(self.pause_overlay)     # centre vertically
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addStretch()
            lay.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
            lay.addStretch()

            self.pause_overlay.show()
            self.pause_overlay.raise_()

            self._hint("Paused – press Space to resume")

    # ------------------------------ mask save

    def _save_binary_mask(self):
        if self.view.mask is None:
            return
        sel = np.isin(
            self.view.mask,
            np.fromiter(self.view.sel, self.view.mask.dtype)
        ) if self.view.sel else np.zeros_like(self.view.mask, bool)
        out_path = self.out_dir / f"{self.images[self.idx].stem}_binary.png"
        Image.fromarray((sel.astype(np.uint8) * 255)).save(out_path, "PNG")
        # update status & CSV
        fname = self.images[self.idx].name
        if self.status[fname] in {"unlabeled", "labeled"}:
            self.status[fname] = "labeled" if sel.any() else "unlabeled"
        self._write_csv()

    # ------------------------------ paint helpers
    def select_all(self):
        if self.view.mask is not None:
            self.view.sel = set(np.unique(self.view.mask))
            self.view._refresh_hilite()

    def clear_sel(self):
        self.view.sel.clear()
        self.view._refresh_hilite()

    def fill_inner(self):
        self.view.fill()

    def toggle_overlay(self):
        self.view.show_bnd = not self.view.show_bnd
        if self.view.bnd_item:
            self.view.bnd_item.setVisible(self.view.show_bnd)

    def toggle_hil(self):
        """Toggle whether selection highlight is shown."""
        self.show_hil = not self.show_hil
        if self.hil_item:
            self.hil_item.setVisible(self.show_hil)
        # You may want to give feedback via hint callback:
        mode = "ON" if self.show_hil else "OFF"
        self._hint(f"Selection overlay: {mode}")
        return mode

    def toggle_selection_overlay(self):
        """Toggle the selection highlight overlay in the ImageView."""
        # Delegate to ImageView.toggle_hil (which flips flag and updates visibility)
        mode = self.view.toggle_hil()
        # Optionally: give status bar feedback
        # Already done inside toggle_hil via hint, so this may be redundant.
        # self._hint(f"Selection overlay toggled {mode}")

    def toggle_brush(self):
        self.view.toggle_brush_mode()

    # ------------------------------ keys
    def keyPressEvent(self, e):
        # block everything except Space during pause
        if self.paused and e.key() != Qt.Key.Key_Space:
            return
        # check if Ctrl is pressed
        if e.key() == Qt.Key.Key_S and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+S pressed
            self._save_binary_mask()
            self._hint("Mask saved")  # optional UI feedback
            return

        # existing mapping for other keys
        key_map = {
            Qt.Key.Key_Left: self.prev_image,
            Qt.Key.Key_Right: self.next_image,
            Qt.Key.Key_Space: self._toggle_pause,
        }
        fn = key_map.get(e.key())
        if fn:
            fn()
        else:
            super().keyPressEvent(e)

            # ------------------------------ super‑pixel regeneration  (3.3)

    def start_regen_mode(self):
        """Called by the toolbar button – puts ImageView into rectangle mode."""
        self.view.enable_region_mode()

    def regen_superpixels(self, x1, y1, x2, y2):
        dialog = PixelsPerSPDialog(self.cfg.pixels_per_superpixel, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            val = dialog.get_value()
            if val is None:
                QMessageBox.warning(
                    self, "Invalid input", "Pixels per superpixel must be a positive integer.")
                return
            self.cfg.pixels_per_superpixel = val
        else:
            return  # user canceled, no regeneration

        fname = self.images[self.idx].name
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            segment_image_cropped(self.cfg, fname, x1, y1, x2, y2)
            self._hint("Super‑pixels updated")
        except Exception as e:
            QMessageBox.critical(self, "Error regenerating SP", str(e))
        finally:
            QApplication.restoreOverrideCursor()
            self._load_current()


# ---------------------------------------------------------------- entry


def main():
    if len(sys.argv) != 2:
        print("Usage: python labeling_tool_qt.py /path/to/base_dir")
        sys.exit(1)

    app = QApplication(sys.argv)

    # ---- global UI style (bigger fonts)
    app.setStyleSheet("""
        QWidget            { font-size: 16px; }
        QToolBar QToolButton { font-size: 16px; }
        QProgressBar       { min-height: 16px; }
    """)

    win = MainWindow(Path(sys.argv[1]).resolve())
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
