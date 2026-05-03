#!/usr/bin/env python3
"""
Generate sample dataset for Smart Cane segmentation model training.
Creates synthetic images and labels for testing the training pipeline.

Usage:
    python generate_sample_dataset.py [--images 50] [--seed 42]
"""

import os
import cv2
import numpy as np
import argparse
from pathlib import Path
from typing import List, Tuple

# Class IDs
CLASSES = {
    0: "person",
    1: "furniture",
    2: "vehicle",
    3: "animal",
    4: "pothole",
    5: "water_puddle",
    6: "slippery_floor",
    7: "clear_path"
}

CLASS_COLORS = {
    0: (255, 100, 100),  # Blue-ish
    1: (100, 255, 100),  # Green-ish
    2: (100, 100, 255),  # Red-ish
    3: (255, 255, 100),  # Cyan-ish
    4: (255, 100, 255),  # Magenta-ish
    5: (100, 255, 255),  # Yellow-ish
    6: (200, 100, 50),   # Brown-ish
    7: (200, 200, 200),  # Gray-ish
}

def generate_random_polygon(h: int, w: int, min_points: int = 4, max_points: int = 8) -> List[Tuple[int, int]]:
    """Generate random polygon points."""
    num_points = np.random.randint(min_points, max_points + 1)
    center_x = np.random.randint(w // 4, 3 * w // 4)
    center_y = np.random.randint(h // 4, 3 * h // 4)
    radius = np.random.randint(20, 100)
    
    angles = np.linspace(0, 2 * np.pi, num_points, endpoint=False)
    # Add randomness to radii to make non-circular polygons
    radii = radius + np.random.randint(-30, 30, num_points)
    radii = np.clip(radii, 10, 150)
    
    points = []
    for angle, r in zip(angles, radii):
        x = int(center_x + r * np.cos(angle))
        y = int(center_y + r * np.sin(angle))
        x = np.clip(x, 0, w - 1)
        y = np.clip(y, 0, h - 1)
        points.append((x, y))
    
    return points

def create_sample_image_with_objects(h: int = 320, w: int = 320, num_objects: int = 3) -> Tuple[np.ndarray, List[Tuple]]:
    """
    Create a sample image with random colored shapes and return image + label info.
    
    Returns:
        Tuple of (image, objects_list) where objects_list contains (class_id, polygon_points)
    """
    # Create background (simulating a scene)
    img = np.ones((h, w, 3), dtype=np.uint8) * np.random.randint(100, 200, (3,))
    
    # Add some texture
    noise = np.random.randint(-20, 20, (h, w, 3), dtype=np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    objects = []
    num_objects = np.random.randint(1, num_objects + 1)
    
    for _ in range(num_objects):
        class_id = np.random.randint(0, 8)
        polygon = generate_random_polygon(h, w)
        
        # Draw polygon on image
        pts = np.array(polygon, dtype=np.int32)
        color = CLASS_COLORS[class_id]
        cv2.fillPoly(img, [pts], color)
        cv2.polylines(img, [pts], True, (0, 0, 0), 2)
        
        # Add some noise to the shape
        for _ in range(5):
            pt = np.random.choice(len(polygon))
            cv2.circle(img, polygon[pt], np.random.randint(1, 5), (0, 0, 0), -1)
        
        objects.append((class_id, polygon))
    
    return img, objects

def polygon_to_yolo_format(polygon: List[Tuple[int, int]], h: int, w: int) -> str:
    """Convert polygon to YOLO format (normalized coordinates)."""
    coords = []
    for x, y in polygon:
        norm_x = x / w
        norm_y = y / h
        coords.append(f"{norm_x:.4f} {norm_y:.4f}")
    return " ".join(coords)

def generate_dataset(num_images: int = 50, output_dir: str = "data", seed: int = 42):
    """Generate sample dataset with images and labels."""
    
    np.random.seed(seed)
    
    output_path = Path(output_dir)
    
    # Create directory structure
    for split in ["train", "val", "test"]:
        (output_path / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_path / "labels" / split).mkdir(parents=True, exist_ok=True)
    
    # Split: 70% train, 15% val, 15% test
    train_count = int(num_images * 0.7)
    val_count = int(num_images * 0.15)
    test_count = num_images - train_count - val_count
    
    splits = {
        "train": train_count,
        "val": val_count,
        "test": test_count
    }
    
    image_id = 0
    
    for split, count in splits.items():
        print(f"Generating {count} images for {split}...")
        for i in range(count):
            # Create image with random objects
            img, objects = create_sample_image_with_objects(h=320, w=320, num_objects=3)
            
            # Save image
            img_name = f"{split}_{image_id:04d}.jpg"
            img_path = output_path / "images" / split / img_name
            cv2.imwrite(str(img_path), img)
            
            # Create label file
            label_name = f"{split}_{image_id:04d}.txt"
            label_path = output_path / "labels" / split / label_name
            
            with open(label_path, 'w') as f:
                for class_id, polygon in objects:
                    yolo_coords = polygon_to_yolo_format(polygon, 320, 320)
                    f.write(f"{class_id} {yolo_coords}\n")
            
            image_id += 1
            
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{count} done...")
    
    # Create dataset.yaml
    yaml_path = output_path / "dataset.yaml"
    with open(yaml_path, 'w') as f:
        f.write(f"""path: {output_path.absolute()}
train: images/train
val: images/val
test: images/test

nc: 8
names:
  0: person
  1: furniture
  2: vehicle
  3: animal
  4: pothole
  5: water_puddle
  6: slippery_floor
  7: clear_path
""")
    
    print(f"\n✓ Dataset generated successfully!")
    print(f"  Total images: {num_images}")
    print(f"  Train: {train_count}, Val: {val_count}, Test: {test_count}")
    print(f"  Location: {output_path.absolute()}")
    print(f"\nNext: python train_custom_segmentation.py --epochs 50 --batch 8")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate sample dataset for Smart Cane segmentation model"
    )
    parser.add_argument(
        "--images", type=int, default=50,
        help="Number of sample images to generate (default: 50)"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed (default: 42)"
    )
    parser.add_argument(
        "--output", type=str, default="data",
        help="Output directory (default: data)"
    )
    
    args = parser.parse_args()
    
    generate_dataset(
        num_images=args.images,
        output_dir=args.output,
        seed=args.seed
    )
