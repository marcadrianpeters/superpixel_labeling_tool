from __future__ import annotations

import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Tuple, Optional, Union

import cv2
import numpy as np
from skimage.segmentation import find_boundaries, slic
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class SegmenterConfig:
    """Configuration for superpixel segmentation pipeline."""
    input_dir: Path
    output_masks: Path
    output_overlays: Optional[Path] = None
    pixels_per_superpixel: int = 150
    downscale_factor: float = 1.0
    overlay_alpha: float = 0.7
    overlay_color: Tuple[int, int, int] = (128, 128, 128)
    num_workers: int = 1

    def asdict(self) -> dict:
        return asdict(self)


def downscale_image(image: np.ndarray, factor: float) -> np.ndarray:
    """Resize image by a given factor, preserving aspect ratio."""
    if factor == 1.0:
        return image
    height, width = image.shape[:2]
    new_dims = (int(width * factor), int(height * factor))
    return cv2.resize(image, new_dims, interpolation=cv2.INTER_AREA)


def overlay_boundaries(image_bgr: np.ndarray, labels: np.ndarray,
                       color: Tuple[int, int, int] = (255, 0, 0),
                       alpha: float = 0.7) -> np.ndarray:
    """Overlay superpixel boundaries on the image."""
    output = image_bgr.astype(np.float32)
    boundaries_mask = find_boundaries(labels, mode='outer')
    output[boundaries_mask] = (
        1 - alpha) * output[boundaries_mask] + alpha * np.array(color, np.float32)
    return np.clip(output, 0, 255).astype(np.uint8)


def segment_image(image_bgr: np.ndarray, config: SegmenterConfig) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Segment image into superpixels using SLIC.

    Args:
        image_bgr: Input BGR image.
        config: Configuration parameters.

    Returns:
        labels: Superpixel labels as uint16 ndarray.
        overlay: Overlay image if enabled, else None.
    """
    if image_bgr.size == 0:
        raise ValueError("Input image is empty")

    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    image_rgb = downscale_image(image_rgb, config.downscale_factor)

    total_pixels = image_rgb.shape[0] * image_rgb.shape[1]
    n_segments = max(2, min(65532, total_pixels //
                     config.pixels_per_superpixel))

    labels = slic(image_rgb, n_segments=n_segments,
                  slic_zero=True).astype(np.uint16)

    # Resize labels back to original image size
    labels = cv2.resize(
        labels, (image_bgr.shape[1], image_bgr.shape[0]), interpolation=cv2.INTER_NEAREST)

    overlay = None
    if config.output_overlays is not None:
        overlay = overlay_boundaries(
            image_bgr, labels, config.overlay_color, config.overlay_alpha)

    return labels, overlay


def _process_single_image(image_path: Path, config: SegmenterConfig) -> None:
    """Load image, segment superpixels, and save outputs."""
    image = cv2.imread(str(image_path))
    if image is None:
        logger.warning(f"Could not read image: {image_path}")
        return

    labels, overlay = segment_image(image, config)

    mask_output_path = config.output_masks / f"{image_path.stem}.png"
    mask_output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(mask_output_path), labels, [
                cv2.IMWRITE_PNG_COMPRESSION, 3])
    logger.debug(f"Saved mask to {mask_output_path}")

    if overlay is not None and config.output_overlays is not None:
        overlay_output_path = config.output_overlays / image_path.name
        overlay_output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(overlay_output_path), overlay)
        logger.debug(f"Saved overlay to {overlay_output_path}")


def _process_image_wrapper(args: Tuple[Path, SegmenterConfig]) -> None:
    image_path, config = args
    _process_single_image(image_path, config)


def process_dataset(config: SegmenterConfig) -> None:
    """Process all images in the input directory using configured parallelism."""
    supported_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff'}
    images = sorted(p for p in config.input_dir.iterdir()
                    if p.suffix.lower() in supported_extensions)

    if not images:
        logger.warning(f"No supported images found in {config.input_dir}")
        return

    workers = max(1, config.num_workers)
    if workers == 1:
        for image_path in tqdm(images, desc="Segmenting images", unit="image"):
            _process_single_image(image_path, config)
    else:
        args_list = [(p, config) for p in images]
        with ProcessPoolExecutor(max_workers=workers) as executor:
            list(tqdm(executor.map(_process_image_wrapper, args_list), total=len(images),
                      desc="Segmenting images", unit="image"))


def segment_image_cropped(config: SegmenterConfig,
                          filename: Union[str, Path],
                          x1: int, y1: int, x2: int, y2: int
                          ) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Segment a cropped region of an image and merge back with full image mask.

    Args:
        config: Configuration object.
        filename: Filename relative to input directory.
        x1, y1, x2, y2: Bounding box coordinates (top-left inclusive, bottom-right exclusive).

    Returns:
        labels_full: Full-size label mask with cropped region segmented.
        overlay_full: Overlay image or None if overlays disabled.
    """
    img_path = config.input_dir / filename
    image = cv2.imread(str(img_path))
    if image is None:
        raise FileNotFoundError(f"Image not found: {img_path}")

    height, width = image.shape[:2]
    x1_clipped, y1_clipped = max(0, x1), max(0, y1)
    x2_clipped, y2_clipped = min(width, x2), min(height, y2)

    if x1_clipped >= x2_clipped or y1_clipped >= y2_clipped:
        raise ValueError(f"Invalid crop bounding box: {(x1, y1, x2, y2)}")

    roi = image[y1_clipped:y2_clipped, x1_clipped:x2_clipped].copy()

    labels_roi, _ = segment_image(roi, config)
    next_label = int(labels_roi.max()) + 1

    labels_full = np.full((height, width), next_label, dtype=np.uint16)
    labels_full[y1_clipped:y2_clipped, x1_clipped:x2_clipped] = labels_roi

    overlay_full = None
    if config.output_overlays is not None:
        overlay_full = overlay_boundaries(
            image, labels_full, config.overlay_color, config.overlay_alpha)

    # Save outputs
    stem = Path(filename).stem
    mask_out_path = config.output_masks / f"{stem}.png"
    mask_out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(mask_out_path), labels_full,
                [cv2.IMWRITE_PNG_COMPRESSION, 3])

    if overlay_full is not None:
        overlay_out_path = config.output_overlays / \
            f"{stem}{Path(filename).suffix}"
        overlay_out_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(overlay_out_path), overlay_full)

    return labels_full, overlay_full
