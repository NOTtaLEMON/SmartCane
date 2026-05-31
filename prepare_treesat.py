import shutil
from pathlib import Path

src = Path(r'C:\Users\ragha\Documents\CODE\SEM2EL\TREESAT')
dst = Path(r'C:\Users\ragha\Documents\CODE\SEM2EL\TREESAT_prepared')

def poly_to_bbox(vals):
    xs = [vals[i] for i in range(0, 8, 2)]
    ys = [vals[i] for i in range(1, 8, 2)]
    x_min = max(0.0, min(xs))
    x_max = min(1.0, max(xs))
    y_min = max(0.0, min(ys))
    y_max = min(1.0, max(ys))
    cx = (x_min + x_max) / 2
    cy = (y_min + y_max) / 2
    w  = x_max - x_min
    h  = y_max - y_min
    return cx, cy, w, h

for split in ['train', 'valid', 'test']:
    (dst / split / 'images').mkdir(parents=True, exist_ok=True)
    (dst / split / 'labels').mkdir(parents=True, exist_ok=True)
    for img in (src / split / 'images').iterdir():
        lbl = src / split / 'labels' / (img.stem + '.txt')
        if not lbl.exists():
            continue
        out_lines = []
        for line in lbl.read_text().strip().splitlines():
            parts = line.split()
            if len(parts) != 9:
                continue
            cx, cy, w, h = poly_to_bbox([float(v) for v in parts[1:]])
            if w <= 0 or h <= 0:
                continue
            out_lines.append(f'0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}')
        if not out_lines:
            continue
        (dst / split / 'labels' / lbl.name).write_text('\n'.join(out_lines))
        shutil.copy(img, dst / split / 'images' / img.name)

yaml_content = "train: train/images\nval: valid/images\ntest: test/images\n\nnc: 1\nnames: ['tree']\n"
(dst / 'data.yaml').write_text(yaml_content)

for split in ['train', 'valid', 'test']:
    count = len(list((dst / split / 'images').iterdir()))
    print(f'{split}: {count} images')
print('data.yaml written')
