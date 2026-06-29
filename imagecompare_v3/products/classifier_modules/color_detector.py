"""
color_detector.py  —  Phase 2
──────────────────────────────
Uses OpenCV + KMeans clustering to find the dominant color
in a product image and map it to a human-readable color name.

How it works:
    1. Load image with OpenCV
    2. Resize to 150×150 (faster processing)
    3. Remove background pixels (very light/white = background)
    4. Run KMeans clustering on remaining pixels
    5. Most common cluster = dominant color
    6. Map RGB → nearest named color
"""

import cv2
import numpy as np


# ── Named color map (RGB values) ──────────────────────────────────────────────
# We compare detected RGB against these to find the closest name
COLOR_NAMES = {
    "red"         : (220,  20,  60),
    "dark red"    : (139,   0,   0),
    "orange"      : (255, 140,   0),
    "yellow"      : (255, 215,   0),
    "green"       : ( 34, 139,  34),
    "dark green"  : (  0, 100,   0),
    "blue"        : ( 30, 144, 255),
    "dark blue"   : (  0,   0, 139),
    "navy blue"   : (  0,   0, 128),
    "purple"      : (128,   0, 128),
    "violet"      : (238, 130, 238),
    "pink"        : (255, 105, 180),
    "hot pink"    : (255,  20, 147),
    "brown"       : (139,  69,  19),
    "beige"       : (245, 245, 220),
    "cream"       : (255, 253, 208),
    "white"       : (255, 255, 255),
    "black"       : (  0,   0,   0),
    "grey"        : (128, 128, 128),
    "silver"      : (192, 192, 192),
    "gold"        : (255, 215,   0),
    "maroon"      : (128,   0,   0),
    "teal"        : (  0, 128, 128),
    "cyan"        : (  0, 255, 255),
    "magenta"     : (255,   0, 255),
    "coral"       : (255, 127,  80),
    "peach"       : (255, 218, 185),
    "lavender"    : (230, 230, 250),
    "mustard"     : (255, 219,  88),
    "olive"       : (128, 128,   0),
    "turquoise"   : ( 64, 224, 208),
    "indigo"      : ( 75,   0, 130),
    "rust"        : (183,  65,  14),
    "off white"   : (255, 250, 240),
    "charcoal"    : ( 54,  69,  79),
}


def detect_color(image_path: str) -> dict:
    """
    Detect dominant color from image file.

    Returns:
        {
            "color_name" : "red",
            "color_hex"  : "#DC143C",
            "rgb"        : [220, 20, 60],
            "confidence" : 0.73
        }
    """
    try:
        # ── 1. Load image ──────────────────────────────────────────
        img = cv2.imread(image_path)
        if img is None:
            return _default_color()

        # Convert BGR (OpenCV default) → RGB
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # ── 2. Resize for speed ────────────────────────────────────
        img = cv2.resize(img, (150, 150))

        # ── 3. Flatten to list of pixels ──────────────────────────
        pixels = img.reshape(-1, 3).astype(np.float32)

        # ── 4. Remove background (near-white pixels) ──────────────
        # Background pixels are very bright (all channels > 220)
        not_background = ~(
            (pixels[:, 0] > 220) &
            (pixels[:, 1] > 220) &
            (pixels[:, 2] > 220)
        )
        pixels = pixels[not_background]

        if len(pixels) < 100:
            # Image is mostly white background — use all pixels
            pixels = img.reshape(-1, 3).astype(np.float32)

        # ── 5. KMeans clustering — find 5 dominant color clusters ──
        k = min(5, len(pixels))
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 0.1)
        flags = cv2.KMEANS_RANDOM_CENTERS

        _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 10, flags)

        # ── 6. Find the most common cluster ───────────────────────
        label_counts = np.bincount(labels.flatten())
        dominant_idx = np.argmax(label_counts)
        dominant_rgb = centers[dominant_idx].astype(int).tolist()
        confidence   = round(label_counts[dominant_idx] / len(labels), 2)

        # ── 7. Map to nearest color name ──────────────────────────
        color_name = _nearest_color_name(dominant_rgb)
        color_hex  = '#{:02X}{:02X}{:02X}'.format(*dominant_rgb)

        return {
            "color_name" : color_name,
            "color_hex"  : color_hex,
            "rgb"        : dominant_rgb,
            "confidence" : confidence,
        }

    except Exception as e:
        print(f"[ColorDetector] Error: {e}")
        return _default_color()


def _nearest_color_name(rgb: list) -> str:
    """Find the closest named color using Euclidean distance in RGB space."""
    r, g, b = rgb
    min_dist  = float('inf')
    best_name = "multicolor"

    for name, (cr, cg, cb) in COLOR_NAMES.items():
        dist = ((r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2) ** 0.5
        if dist < min_dist:
            min_dist  = dist
            best_name = name

    return best_name


def _default_color() -> dict:
    return {
        "color_name" : "",
        "color_hex"  : "",
        "rgb"        : [],
        "confidence" : 0.0,
    }
