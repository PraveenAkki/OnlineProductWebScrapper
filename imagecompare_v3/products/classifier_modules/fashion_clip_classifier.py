"""
fashion_clip_classifier.py  -  Phase 4A
-----------------------------------------
Uses FashionCLIP — a CLIP model fine-tuned on 800,000 real
e-commerce fashion product images from multiple online stores.

Why better than plain CLIP (Phase 3)?
  - Plain CLIP trained on generic internet images
  - FashionCLIP trained ONLY on fashion e-commerce data
  - Understands: category, color, pattern, style, gender, fabric

Example results:
  Plain CLIP    -> "red dress"
  FashionCLIP   -> "women's red floral printed cotton kurti"

Install:
  python -m pip install fashion-clip

First run downloads the model (~400MB) from HuggingFace.
Cached locally after that.
"""

from PIL import Image
import numpy as np


# ---------------------------------------------------------------------------
# Fashion attribute candidates
# FashionCLIP compares image against these text labels
# and picks the closest match for each attribute group.
# ---------------------------------------------------------------------------

CATEGORIES = [
    "saree", "silk saree", "banarasi saree", "kanjivaram saree",
    "georgette saree", "cotton saree", "chiffon saree",
    "kurti", "kurta", "anarkali kurti", "printed kurti",
    "lehenga", "lehenga choli", "bridal lehenga",
    "salwar kameez", "churidar", "palazzo suit",
    "dress", "maxi dress", "mini dress", "midi dress", "wrap dress",
    "gown", "evening gown", "party dress",
    "top", "blouse", "crop top", "tank top",
    "shirt", "formal shirt", "casual shirt", "check shirt",
    "t-shirt", "polo t-shirt", "round neck t-shirt",
    "jeans", "skinny jeans", "slim fit jeans", "wide leg jeans",
    "trousers", "formal trousers", "palazzo pants", "cargo pants",
    "jacket", "denim jacket", "leather jacket", "bomber jacket",
    "blazer", "formal blazer", "coat", "overcoat", "trench coat",
    "sneakers", "running shoes", "sports shoes", "casual shoes",
    "formal shoes", "loafers", "oxford shoes", "boots", "ankle boots",
    "heels", "stilettos", "wedges", "flat sandals", "kolhapuri sandals",
    "handbag", "tote bag", "sling bag", "clutch", "backpack",
    "wallet", "purse", "crossbody bag",
    "necklace", "gold necklace", "pearl necklace",
    "earrings", "jhumka earrings", "stud earrings", "drop earrings",
    "bangles", "bracelet", "ring", "gold ring", "mangalsutra",
    "watch", "analog watch", "digital watch", "smartwatch",
    "sunglasses", "aviator sunglasses", "wayfarer sunglasses",
    "cap", "hat", "beanie",
    "swimwear", "bikini", "swimsuit",
    "sportswear", "gym wear", "yoga pants", "track pants",
    "innerwear", "lingerie",
    "scarf", "dupatta", "stole", "shawl",
    "sherwani", "men ethnic wear", "nehru jacket",
]

COLORS = [
    "red", "dark red", "maroon", "crimson",
    "blue", "navy blue", "royal blue", "sky blue", "light blue",
    "green", "dark green", "olive green", "mint green",
    "yellow", "mustard yellow", "golden yellow",
    "orange", "peach", "coral",
    "pink", "hot pink", "baby pink", "rose pink", "magenta",
    "purple", "violet", "lavender", "indigo",
    "white", "off white", "cream", "ivory",
    "black", "charcoal", "dark grey",
    "grey", "silver grey",
    "brown", "tan", "camel", "beige", "khaki",
    "gold", "silver", "rose gold",
    "multicolor", "printed", "tie dye",
]

PATTERNS = [
    "solid plain", "floral print", "geometric print",
    "abstract print", "animal print", "stripes",
    "checks", "polka dots", "paisley", "ikat",
    "embroidered", "embellished", "sequin work",
    "block print", "digital print", "batik print",
    "lace work", "mirror work", "thread work",
    "zari work", "bandhani", "tie dye",
    "plain", "textured", "woven",
]

GENDERS = [
    "women", "men", "unisex", "girls", "boys",
]

FABRICS = [
    "silk", "cotton", "polyester", "georgette",
    "chiffon", "velvet", "denim", "linen",
    "satin", "rayon", "crepe", "net",
    "wool", "leather", "synthetic",
]


# ---------------------------------------------------------------------------
# Load FashionCLIP model once at module level
# ---------------------------------------------------------------------------
print("[FashionCLIP] Loading model (first run downloads ~400MB)...")
try:
    from fashion_clip.fashion_clip import FashionCLIP as FC
    _fclip = FC('fashion-clip')
    print("[FashionCLIP] Model ready.")
    MODEL_LOADED = True
except Exception as e:
    print(f"[FashionCLIP] Failed to load: {e}")
    print("[FashionCLIP] Run: python -m pip install fashion-clip")
    _fclip = None
    MODEL_LOADED = False


# ---------------------------------------------------------------------------
# Classify function
# ---------------------------------------------------------------------------
def classify(image_path: str) -> dict:
    """
    Phase 4A - FashionCLIP classification.

    Returns:
        {
            "category"         : "kurti",
            "color"            : "red",
            "pattern"          : "floral print",
            "gender"           : "women",
            "fabric"           : "cotton",
            "base_keyword"     : "women red floral print cotton kurti",
            "confidence"       : 0.87,
            "all_attributes"   : {...}
        }
    """
    if not MODEL_LOADED or _fclip is None:
        return _default("FashionCLIP model not loaded. Run: pip install fashion-clip")

    try:
        image = Image.open(image_path).convert("RGB")
    except Exception as e:
        return _default(f"Cannot open image: {e}")

    try:
        # FashionCLIP encodes image and text candidates separately
        # then computes cosine similarity
        image_embeddings = _fclip.encode_images([image], batch_size=1)

        results = {}

        # Score each attribute group separately
        for attr_name, candidates in [
            ("category", CATEGORIES),
            ("color",    COLORS),
            ("pattern",  PATTERNS),
            ("gender",   GENDERS),
            ("fabric",   FABRICS),
        ]:
            text_embeddings = _fclip.encode_text(candidates, batch_size=32)

            # Cosine similarity: image vs each candidate
            sims = np.dot(image_embeddings, text_embeddings.T)[0]
            top_idx  = int(np.argmax(sims))
            top_score = float(sims[top_idx])

            top3 = sorted(
                zip(candidates, sims.tolist()),
                key=lambda x: x[1],
                reverse=True
            )[:3]

            results[attr_name] = {
                "value"      : candidates[top_idx],
                "confidence" : round(top_score, 4),
                "top3"       : [{"label": l, "score": round(s, 4)} for l, s in top3],
            }

        print(f"[FashionCLIP] Results: { {k: v['value'] for k, v in results.items()} }")

        # Build keyword from detected attributes
        gender   = results["gender"]["value"]
        color    = results["color"]["value"]
        pattern  = results["pattern"]["value"]
        fabric   = results["fabric"]["value"]
        category = results["category"]["value"]

        # Smart keyword: avoid duplicating color if pattern already describes it
        parts = [gender, color]
        if pattern not in ("solid plain", "plain"):
            parts.append(pattern)
        if fabric not in ("synthetic", "polyester"):
            parts.append(fabric)
        parts.append(category)

        base_keyword = " ".join(parts)

        return {
            "category"       : category,
            "color"          : color,
            "pattern"        : pattern,
            "gender"         : gender,
            "fabric"         : fabric,
            "base_keyword"   : base_keyword,
            "confidence"     : results["category"]["confidence"],
            "all_attributes" : results,
            "top5"           : results["category"]["top3"],
        }

    except Exception as e:
        print(f"[FashionCLIP] Inference error: {e}")
        return _default(str(e))


def _default(error: str) -> dict:
    return {
        "category"     : "fashion",
        "color"        : "",
        "pattern"      : "",
        "gender"       : "",
        "fabric"       : "",
        "base_keyword" : "fashion clothing",
        "confidence"   : 0.0,
        "all_attributes": {},
        "top5"         : [],
        "error"        : error,
    }
