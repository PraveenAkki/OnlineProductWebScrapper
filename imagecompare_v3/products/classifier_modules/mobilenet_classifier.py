"""
mobilenet_classifier.py  —  Phase 1
─────────────────────────────────────
Loads MobileNetV2 pre-trained on ImageNet.
Classifies image → category + base keyword.

Used alone in Phase 1.
Used together with color_detector in Phase 2.
Replaced by CLIP in Phase 3.
"""

import torch
import torchvision.transforms as transforms
import torchvision.models as tv_models
from PIL import Image
import urllib.request


# ── ImageNet label → (category, base_keyword) ────────────────────────────────
LABEL_MAP = {
    # Tops
    "jersey"          : ("tshirt",     "sports jersey t-shirt"),
    "t-shirt"         : ("tshirt",     "cotton t-shirt"),
    "sweatshirt"      : ("sweatshirt", "sweatshirt hoodie"),
    "cardigan"        : ("cardigan",   "women's cardigan sweater"),
    "suit"            : ("suit",       "men's formal suit"),
    "lab coat"        : ("shirt",      "formal white shirt"),
    "trench coat"     : ("coat",       "women's trench coat"),
    "fur coat"        : ("coat",       "women's winter coat"),
    "kimono"          : ("kurti",      "women's kurti ethnic wear"),

    # Indian ethnic
    "sari"            : ("saree",      "silk saree"),
    "sarong"          : ("saree",      "women's saree"),
    "silk"            : ("saree",      "silk saree"),

    # Bottoms
    "jean"            : ("jeans",      "slim fit jeans"),
    "miniskirt"       : ("skirt",      "women's mini skirt"),
    "overskirt"       : ("skirt",      "women's skirt"),

    # Dresses
    "gown"            : ("gown",       "women's evening gown"),
    "wedding gown"    : ("gown",       "women's bridal wedding gown"),
    "costume"         : ("dress",      "women's party dress"),

    # Footwear
    "running shoe"    : ("shoes",      "running shoes"),
    "sneaker"         : ("sneakers",   "casual sneakers"),
    "loafer"          : ("shoes",      "loafer shoes"),
    "sandal"          : ("sandals",    "women's sandals"),
    "boot"            : ("boots",      "ankle boots"),
    "high heel"       : ("heels",      "women's high heel shoes"),
    "clog"            : ("shoes",      "clog shoes"),
    "sock"            : ("socks",      "cotton socks"),

    # Bags
    "handbag"         : ("handbag",    "women's handbag"),
    "purse"           : ("purse",      "women's purse clutch"),
    "backpack"        : ("backpack",   "casual backpack"),
    "wallet"          : ("wallet",     "men's leather wallet"),
    "suitcase"        : ("luggage",    "travel suitcase luggage"),

    # Accessories
    "sunglasses"      : ("sunglasses", "UV protection sunglasses"),
    "watch"           : ("watch",      "wrist watch"),
    "necklace"        : ("necklace",   "gold necklace"),
    "bracelet"        : ("bracelet",   "bracelet jewellery"),
    "ring"            : ("ring",       "gold finger ring"),
    "earring"         : ("earrings",   "gold earrings"),
    "umbrella"        : ("umbrella",   "foldable umbrella"),
    "bow tie"         : ("tie",        "men's bow tie"),
    "cap"             : ("cap",        "men's casual cap"),
    "cowboy hat"      : ("hat",        "men's hat"),
    "bonnet"          : ("hat",        "women's hat"),

    # Sportswear
    "swimming trunks" : ("swimwear",   "men's swimming trunks"),
    "bikini"          : ("swimwear",   "women's swimwear bikini"),

    # Generic
    "dress"           : ("dress",      "women's fashion dress"),
    "shirt"           : ("shirt",      "formal shirt"),
    "blouse"          : ("blouse",     "women's blouse top"),
    "jacket"          : ("jacket",     "jacket"),
    "blazer"          : ("blazer",     "men's blazer"),
    "pant"            : ("pants",      "trousers"),
    "trouser"         : ("pants",      "formal trousers"),
    "kurta"           : ("kurta",      "men's kurta ethnic wear"),
}

DEFAULT_CATEGORY = "fashion"
DEFAULT_KEYWORD  = "fashion clothing"


# ── Load model once ───────────────────────────────────────────────────────────
print("[MobileNet] Loading MobileNetV2...")
_model = tv_models.mobilenet_v2(weights=tv_models.MobileNet_V2_Weights.IMAGENET1K_V1)
_model.eval()
print("[MobileNet] Ready.")

_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std =[0.229, 0.224, 0.225]
    ),
])


def _load_labels() -> list:
    url = "https://raw.githubusercontent.com/pytorch/hub/master/imagenet_classes.txt"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return [line.strip() for line in r.read().decode().splitlines()]
    except Exception:
        return [str(i) for i in range(1000)]

_labels = _load_labels()


def classify(image_path: str) -> dict:
    """
    Phase 1 classification — MobileNetV2 only.

    Returns:
        {
            "detected_label" : "sari, saree",
            "category"       : "saree",
            "base_keyword"   : "silk saree",
            "confidence"     : 0.87,
            "top5"           : [...]
        }
    """
    try:
        img    = Image.open(image_path).convert("RGB")
        tensor = _transform(img).unsqueeze(0)
    except Exception as e:
        return _default(f"Cannot open image: {e}")

    with torch.no_grad():
        output = _model(tensor)

    probs           = torch.nn.functional.softmax(output[0], dim=0)
    top5_probs, top5_idx = torch.topk(probs, 5)

    top5 = [
        {"label": _labels[i.item()], "confidence": round(p.item(), 4)}
        for p, i in zip(top5_probs, top5_idx)
    ]

    print(f"[MobileNet] Top5: {top5}")

    # Match against label map
    for pred in top5:
        label = pred["label"].lower()
        conf  = pred["confidence"]
        for key, (category, keyword) in LABEL_MAP.items():
            if key in label:
                return {
                    "detected_label" : pred["label"],
                    "category"       : category,
                    "base_keyword"   : keyword,
                    "confidence"     : conf,
                    "top5"           : top5,
                }

    # No match — use top label directly as keyword
    return {
        "detected_label" : top5[0]["label"] if top5 else "unknown",
        "category"       : DEFAULT_CATEGORY,
        "base_keyword"   : top5[0]["label"] if top5 else DEFAULT_KEYWORD,
        "confidence"     : top5[0]["confidence"] if top5 else 0.0,
        "top5"           : top5,
    }


def _default(error: str) -> dict:
    return {
        "detected_label" : "unknown",
        "category"       : DEFAULT_CATEGORY,
        "base_keyword"   : DEFAULT_KEYWORD,
        "confidence"     : 0.0,
        "top5"           : [],
        "error"          : error,
    }
