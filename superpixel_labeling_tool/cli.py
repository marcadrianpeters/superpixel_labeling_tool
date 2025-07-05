#!/usr/bin/env python3
"""
Run superpixel segmentation on a dataset using a base directory layout.
"""

from pathlib import Path
import argparse
from typing import Tuple

from superpixel_labeling_tool.segmentation import SegmenterConfig, process_dataset


def parse_int_tuple(text: str, length: int) -> Tuple[int, ...]:
    """Parse a comma-separated string into a tuple of ints of fixed length."""
    parts = [int(p.strip()) for p in text.split(",")]
    if len(parts) != length:
        raise argparse.ArgumentTypeError(
            f"Expected {length} comma-separated ints, got: {text}")
    return tuple(parts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run SLIC superpixel segmentation on a dataset with fixed subfolder layout."
    )

    parser.add_argument("base_dir", type=Path,
                        help="Root folder containing an 'input/' subfolder. Outputs go to sibling folders.")

    parser.add_argument("--pixels_per_superpixel", type=int, default=150,
                        help="Target number of pixels per superpixel (default: 150)")
    parser.add_argument("--downscale_factor", type=float, default=1.0,
                        help="Downscale factor applied before segmentation (default: 1.0)")
    parser.add_argument("--overlay_alpha", type=float, default=0.7,
                        help="Alpha blending strength for overlay visualization (default: 0.7)")
    parser.add_argument("--overlay_color", type=lambda s: parse_int_tuple(s, 3), default=(128, 128, 128),
                        help="RGB color for superpixel boundaries (default: 128,128,128)")
    parser.add_argument("--num_workers", type=int, default=1,
                        help="Number of parallel processes for segmentation (default: 1)")

    return parser


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)

    base_dir = args.base_dir.expanduser().resolve()
    input_dir = base_dir / "input"
    output_masks = base_dir / "superpixel_masks"
    output_overlays = base_dir / "superpixel_overlays"

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    output_masks.mkdir(parents=True, exist_ok=True)
    output_overlays.mkdir(parents=True, exist_ok=True)

    config = SegmenterConfig(
        input_dir=input_dir,
        output_masks=output_masks,
        output_overlays=output_overlays,
        pixels_per_superpixel=args.pixels_per_superpixel,
        downscale_factor=args.downscale_factor,
        overlay_alpha=args.overlay_alpha,
        overlay_color=args.overlay_color,
        num_workers=args.num_workers,
    )

    process_dataset(config)


if __name__ == "__main__":
    main()
