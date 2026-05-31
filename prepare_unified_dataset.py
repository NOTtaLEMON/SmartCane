"""
Merges all raw datasets into one unified training set.

Final class taxonomy (6 classes):
  0: person
  1: vehicle      (LCV, auto, bus, car, cart, cycle, e-rickshaw, motorbike, rickshaw, tractor, truck)
  2: pothole
  3: electric_pole
  4: tree
  5: steps_kerb
"""

import shutil
from pathlib import Path

BASE = Path(r'C:\Users\ragha\Documents\CODE\SEM2EL\data')
OUT  = BASE / 'unified'

# Clean and recreate output dirs
if OUT.exists():
    shutil.rmtree(OUT)
for split in ['train', 'val']:
    (OUT / split / 'images').mkdir(parents=True)
    (OUT / split / 'labels').mkdir(parents=True)


def copy_split(src_images, src_labels, split, prefix, class_map, skip_classes=None):
    src_images = Path(src_images)
    src_labels = Path(src_labels)
    out_images = OUT / split / 'images'
    out_labels = OUT / split / 'labels'

    if not src_images.exists():
        print(f"  SKIP (missing): {src_images}")
        return 0

    count = 0
    for img_file in src_images.iterdir():
        if img_file.suffix.lower() not in ('.jpg', '.jpeg', '.png'):
            continue
        label_file = src_labels / (img_file.stem + '.txt')
        if not label_file.exists():
            continue

        new_lines = []
        with open(label_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                orig_class = int(parts[0])
                if skip_classes and orig_class in skip_classes:
                    continue
                if orig_class not in class_map:
                    continue
                new_class = class_map[orig_class]
                new_lines.append(f"{new_class} {' '.join(parts[1:])}")

        if not new_lines:
            continue

        new_stem = f"{prefix}_{img_file.stem}"
        shutil.copy2(img_file, out_images / (new_stem + img_file.suffix))
        with open(out_labels / (new_stem + '.txt'), 'w') as f:
            f.write('\n'.join(new_lines))
        count += 1
    return count


# ── vehicle dataset ──────────────────────────────────────────────────────────
# classes: LCV(0) auto(1) bus(2) car(3) cart(4) cycle(5) e-rickshaw(6)
#          motorbike(7) person(8) rickshaw(9) tractor(10) truck(11)
VEH_MAP = {0:1, 1:1, 2:1, 3:1, 4:1, 5:1, 6:1, 7:1, 8:0, 9:1, 10:1, 11:1}
n = copy_split(BASE/'raw/vehicle/train/images', BASE/'raw/vehicle/train/labels', 'train', 'veh', VEH_MAP)
print(f"vehicle     train: {n}")
n = copy_split(BASE/'raw/vehicle/valid/images', BASE/'raw/vehicle/valid/labels', 'val',   'veh', VEH_MAP)
print(f"vehicle     val:   {n}")

# ── pothole dataset (pothole_prepared labels use class 4 → remap to 2) ───────
n = copy_split(BASE/'pothole_prepared/train/images', BASE/'pothole_prepared/train/labels', 'train', 'pot', {4:2})
print(f"pothole     train: {n}")
n = copy_split(BASE/'pothole_prepared/val/images',   BASE/'pothole_prepared/val/labels',   'val',   'pot', {4:2})
print(f"pothole     val:   {n}")

# ── electric_pole dataset (class 0 → 3) ──────────────────────────────────────
n = copy_split(BASE/'raw/electric_pole/train/images', BASE/'raw/electric_pole/train/labels', 'train', 'elp', {0:3})
print(f"elec_pole   train: {n}")
n = copy_split(BASE/'raw/electric_pole/valid/images', BASE/'raw/electric_pole/valid/labels', 'val',   'elp', {0:3})
print(f"elec_pole   val:   {n}")

# ── tree dataset (class 0 → 4) ────────────────────────────────────────────────
n = copy_split(BASE/'raw/tree/train/images', BASE/'raw/tree/train/labels', 'train', 'tre', {0:4})
print(f"tree        train: {n}")
n = copy_split(BASE/'raw/tree/valid/images', BASE/'raw/tree/valid/labels', 'val',   'tre', {0:4})
print(f"tree        val:   {n}")

# ── steps_kerb dataset (class 0=object skip, class 1=stairs → 5) ─────────────
n = copy_split(BASE/'raw/steps_kerb/train/images', BASE/'raw/steps_kerb/train/labels', 'train', 'stk', {1:5}, skip_classes={0})
print(f"steps_kerb  train: {n}")
n = copy_split(BASE/'raw/steps_kerb/valid/images', BASE/'raw/steps_kerb/valid/labels', 'val',   'stk', {1:5}, skip_classes={0})
print(f"steps_kerb  val:   {n}")

# ── write data.yaml ───────────────────────────────────────────────────────────
yaml_path = OUT / 'data.yaml'
yaml_path.write_text(
    f"train: {(OUT / 'train/images').as_posix()}\n"
    f"val:   {(OUT / 'val/images').as_posix()}\n\n"
    f"nc: 6\n"
    f"names: ['person', 'vehicle', 'pothole', 'electric_pole', 'tree', 'steps_kerb']\n"
)

total_train = len(list((OUT / 'train/images').iterdir()))
total_val   = len(list((OUT / 'val/images').iterdir()))
print(f"\nDone!")
print(f"Total train: {total_train} images")
print(f"Total val:   {total_val} images")
print(f"data.yaml:   {yaml_path}")
