"""
Prepares the downloaded Roboflow pothole OBB dataset for training with our
custom YOLOv8 model.

What this does:
  1. Reads OBB labels (9 values: class x1 y1 x2 y2 x3 y3 x4 y4)
  2. Keeps only pothole class (class 5 in source)
  3. Converts OBB corners -> axis-aligned bounding box (cx cy w h)
  4. Remaps to class 4 (pothole in our 8-class taxonomy)
  5. Creates 80/20 train/val split
  6. Writes data/pothole_prepared/ with a ready data.yaml

Usage:
    python prepare_pothole_dataset.py
"""

import os
import random
import shutil
from pathlib import Path

SRC_DIR     = Path("data/pothole2")
OUT_DIR     = Path("data/pothole_prepared")
# Both class 0 (POTHOLE) and class 1 (pothole) in this dataset map to our class 4
POTHOLE_SRC_CLASSES = {0, 1}
POTHOLE_DST_CLASS = 4    # class index in our 8-class taxonomy
SEED = 42

# Our 8-class taxonomy (for reference in data.yaml)
CLASSES = [
    "person", "furniture", "vehicle", "animal",
    "pothole", "water_puddle", "slippery_floor", "clear_path"
]


def obb_to_aabb(coords):
    """Convert 4-corner OBB coords (8 floats) to cx,cy,w,h (all normalised)."""
    xs = coords[0::2]
    ys = coords[1::2]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    cx = (x_min + x_max) / 2
    cy = (y_min + y_max) / 2
    w  = x_max - x_min
    h  = y_max - y_min
    return cx, cy, w, h


def process_label_file(src_label: Path):
    """
    Read an OBB label file, keep only pothole rows,
    return list of converted 'class cx cy w h' strings.
    """
    lines_out = []
    with open(src_label) as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            cls = int(parts[0])
            if cls not in POTHOLE_SRC_CLASSES:
                continue
            coords = list(map(float, parts[1:9]))   # 8 OBB coords
            cx, cy, w, h = obb_to_aabb(coords)
            # clamp to [0,1]
            cx = max(0.0, min(1.0, cx))
            cy = max(0.0, min(1.0, cy))
            w  = max(0.0, min(1.0, w))
            h  = max(0.0, min(1.0, h))
            lines_out.append(f"{POTHOLE_DST_CLASS} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    return lines_out


def copy_split(split_src_name: str, split_dst_name: str):
    """Copy one split (train/valid/test) from source dataset to output."""
    src_images = SRC_DIR / split_src_name / "images"
    src_labels = SRC_DIR / split_src_name / "labels"
    if not src_images.exists():
        return 0
    count = 0
    for img_path in src_images.glob("*.*"):
        label_path = src_labels / (img_path.stem + ".txt")
        if not label_path.exists():
            continue
        lines = process_label_file(label_path)
        if not lines:
            continue
        shutil.copy2(img_path, OUT_DIR / split_dst_name / "images" / img_path.name)
        out_label = OUT_DIR / split_dst_name / "labels" / (img_path.stem + ".txt")
        with open(out_label, "w") as f:
            f.write("\n".join(lines) + "\n")
        count += 1
    return count


def main():
    random.seed(SEED)

    # Create output dirs
    for split in ("train", "val"):
        (OUT_DIR / split / "images").mkdir(parents=True, exist_ok=True)
        (OUT_DIR / split / "labels").mkdir(parents=True, exist_ok=True)

    # Copy files using existing train/valid split from dataset
    train_count = copy_split("train", "train")
    val_count   = copy_split("valid", "val")
    print(f"Train: {train_count}  |  Val: {val_count}")

    # Write data.yaml
    data_yaml = OUT_DIR / "data.yaml"
    nc = len(CLASSES)
    names_str = "\n".join(f"  {i}: {c}" for i, c in enumerate(CLASSES))
    yaml_content = f"""path: {OUT_DIR.resolve().as_posix()}
train: train/images
val: val/images

nc: {nc}
names:
{names_str}
"""
    data_yaml.write_text(yaml_content)
    print(f"\nDataset ready at: {OUT_DIR.resolve()}")
    print(f"data.yaml written: {data_yaml.resolve()}")
    print("\nNext step - train the model:")
    print(f"  python train_custom_segmentation.py --epochs 50 --batch 16")
    print(f"  (or run: yolo detect train model=yolov8n.pt data={data_yaml.resolve()} epochs=50 imgsz=320)")


if __name__ == "__main__":
    main()
