"""
clip_classifier.py  —  Phase 3
────────────────────────────────
Uses OpenAI CLIP to generate rich product descriptions.

CLIP works differently from MobileNet:
- MobileNet: image → 1000 fixed ImageNet classes
- CLIP:       image vs text → similarity score

We give CLIP a list of candidate descriptions and it picks
the one most similar to the image. This gives much richer,
more specific results.

Example:
  MobileNet → "sari"
  CLIP      → "red banarasi silk saree with golden border"
"""

import torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel


# ── Candidate descriptions CLIP picks from ────────────────────────────────────
# These are all the text options we give CLIP.
# The more specific and varied, the better the results.

FASHION_CANDIDATES = [
    # ── Sarees & Indian Ethnic (Women) ────────────────────────────
    "red silk saree with golden border",
    "blue banarasi silk saree",
    "green kanjivaram silk saree",
    "pink georgette saree",
    "yellow cotton saree",
    "white linen saree",
    "purple chiffon saree",
    "orange silk saree",
    "maroon wedding saree",
    "black silk saree with embroidery",
    "women's ethnic saree",
    "women's designer saree",

    # ── Kurta / Kurti ─────────────────────────────────────────────
    "women's printed kurti",
    "men's kurta ethnic wear",
    "blue cotton kurti",
    "red embroidered kurti",
    "white men's kurta",
    "men's silk kurta",

    # ── Lehenga / Salwar ──────────────────────────────────────────
    "women's lehenga choli",
    "bridal lehenga red",
    "women's salwar kameez",
    "women's anarkali suit",

    # ── Dresses (Western Women) ───────────────────────────────────
    "women's red party dress",
    "women's blue floral dress",
    "women's black evening gown",
    "women's casual summer dress",
    "women's white maxi dress",
    "women's pink mini dress",

    # ── Tops & Shirts ─────────────────────────────────────────────
    "men's blue formal shirt",
    "men's white formal shirt",
    "men's casual check shirt",
    "women's white blouse top",
    "women's crop top",
    "men's polo t-shirt",
    "men's round neck t-shirt",
    "men's striped t-shirt",

    # ── Jeans & Trousers ──────────────────────────────────────────
    "men's slim fit blue jeans",
    "women's skinny jeans",
    "men's black formal trousers",
    "men's cargo pants",
    "women's palazzo pants",

    # ── Jackets & Coats ───────────────────────────────────────────
    "men's black leather jacket",
    "men's denim jacket",
    "women's woolen coat",
    "men's bomber jacket",
    "men's blazer suit jacket",

    # ── Footwear ──────────────────────────────────────────────────
    "men's white running shoes",
    "men's black leather shoes",
    "women's high heel shoes",
    "women's flat sandals",
    "men's sports sneakers",
    "women's wedge heels",
    "men's formal oxford shoes",
    "women's ankle boots",
    "men's sports shoes",
    "women's casual sneakers",

    # ── Bags ──────────────────────────────────────────────────────
    "women's brown leather handbag",
    "women's clutch purse",
    "men's black backpack",
    "women's tote bag",
    "men's laptop bag",
    "women's crossbody bag",

    # ── Jewellery ─────────────────────────────────────────────────
    "women's gold necklace",
    "women's diamond earrings",
    "women's gold bangles",
    "women's silver ring",
    "women's pearl necklace",
    "men's gold chain",

    # ── Watches ───────────────────────────────────────────────────
    "men's black dial wrist watch",
    "women's rose gold watch",
    "men's sports digital watch",
    "men's leather strap watch",

    # ── Sportswear ────────────────────────────────────────────────
    "men's sports track pants",
    "men's gym t-shirt",
    "women's yoga pants leggings",
    "men's football jersey",
    "women's sports bra",

    # ── Sunglasses ────────────────────────────────────────────────
    "men's aviator sunglasses",
    "women's cat eye sunglasses",
    "men's wayfarer sunglasses",
]


# ── Category map: candidate text → category ───────────────────────────────────
def _extract_category(description: str) -> str:
    desc = description.lower()
    if any(w in desc for w in ["saree", "sari"]):         return "saree"
    if any(w in desc for w in ["kurti", "kurta"]):        return "kurta"
    if any(w in desc for w in ["lehenga"]):               return "lehenga"
    if any(w in desc for w in ["salwar", "anarkali"]):    return "salwar"
    if any(w in desc for w in ["dress", "gown"]):         return "dress"
    if any(w in desc for w in ["shirt", "blouse", "top"]): return "top"
    if any(w in desc for w in ["t-shirt", "polo", "tee"]): return "tshirt"
    if any(w in desc for w in ["jeans", "trouser", "pant", "palazzo"]): return "bottomwear"
    if any(w in desc for w in ["jacket", "coat", "blazer", "bomber"]): return "outerwear"
    if any(w in desc for w in ["shoe", "heel", "sandal", "sneaker", "boot"]): return "footwear"
    if any(w in desc for w in ["bag", "purse", "backpack", "tote"]):  return "bag"
    if any(w in desc for w in ["necklace", "earring", "bangle", "ring", "chain"]): return "jewellery"
    if any(w in desc for w in ["watch"]):                 return "watch"
    if any(w in desc for w in ["sunglasses"]):            return "sunglasses"
    if any(w in desc for w in ["sport", "gym", "yoga", "track"]): return "sportswear"
    return "fashion"


# ── Load CLIP model once ──────────────────────────────────────────────────────
print("[CLIP] Loading CLIP model (openai/clip-vit-base-patch32)...")
print("[CLIP] First run will download ~400MB. Please wait...")

_clip_model     = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
_clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
_clip_model.eval()
print("[CLIP] Ready.")


def classify(image_path: str) -> dict:
    """
    Phase 3 classification — CLIP.

    Returns:
        {
            "clip_description" : "red silk saree with golden border",
            "category"         : "saree",
            "base_keyword"     : "red silk saree with golden border",
            "confidence"       : 0.91,
            "top5"             : [...]
        }
    """
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception as e:
        return _default(f"Cannot open image: {e}")

    try:
        # Process image + all candidate texts together
        inputs = _clip_processor(
            text=FASHION_CANDIDATES,
            images=image,
            return_tensors="pt",
            padding=True
        )

        with torch.no_grad():
            outputs    = _clip_model(**inputs)
            logits     = outputs.logits_per_image[0]     # shape: [num_candidates]
            probs      = logits.softmax(dim=0)

        # Top 5 matches
        top5_probs, top5_idx = torch.topk(probs, 5)
        top5 = [
            {
                "label"      : FASHION_CANDIDATES[i.item()],
                "confidence" : round(p.item(), 4)
            }
            for p, i in zip(top5_probs, top5_idx)
        ]

        print(f"[CLIP] Top5: {top5}")

        best        = top5[0]
        description = best["label"]
        confidence  = best["confidence"]
        category    = _extract_category(description)

        return {
            "clip_description" : description,
            "category"         : category,
            "base_keyword"     : description,
            "confidence"       : confidence,
            "top5"             : top5,
        }

    except Exception as e:
        print(f"[CLIP] Inference error: {e}")
        return _default(str(e))


def _default(error: str) -> dict:
    return {
        "clip_description" : "",
        "category"         : "fashion",
        "base_keyword"     : "fashion clothing",
        "confidence"       : 0.0,
        "top5"             : [],
        "error"            : error,
    }
