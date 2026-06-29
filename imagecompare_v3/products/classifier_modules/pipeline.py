"""
pipeline.py  -  Updated for Phase 4A and 4B
---------------------------------------------
Routes to the correct classifier based on CLASSIFIER_PHASE in settings.py

Phase values:
    'mobilenet'    -> Phase 1+2  MobileNetV2 + OpenCV color
    'clip'         -> Phase 3    CLIP + OpenCV color
    'fashion_clip' -> Phase 4A   FashionCLIP + OpenCV color
    'google_lens'  -> Phase 4B   Google Lens API + OpenCV color
"""

from django.conf import settings
from .color_detector  import detect_color
from .keyword_builder import build_keyword


def run_pipeline(image_path: str) -> dict:
    """
    Run full classification pipeline.
    Always returns the same dict structure regardless of phase.

    Returns:
        {
            "phase"              : "fashion_clip",
            "detected_label"     : "women red floral print cotton kurti",
            "category"           : "kurti",
            "confidence"         : 0.89,
            "detected_color"     : "red",
            "color_hex"          : "#DC143C",
            "clip_description"   : "",
            "fashion_attributes" : { category, color, pattern, gender, fabric },
            "google_lens_data"   : { visual_matches, shopping_results },
            "search_keyword"     : "women red floral print cotton kurti",
            "top5"               : [...],
        }
    """

    phase = getattr(settings, 'CLASSIFIER_PHASE', 'mobilenet')
    print(f"\n[Pipeline] Phase: {phase} | Image: {image_path}")

    # ── Step 1: Run selected classifier ───────────────────────────
    if phase == 'fashion_clip':
        from .fashion_clip_classifier import classify
        clf_result = classify(image_path)

    elif phase == 'google_lens':
        from .google_lens_classifier import classify
        clf_result = classify(image_path)

    elif phase == 'clip':
        from .clip_classifier import classify
        clf_result = classify(image_path)

    else:
        # Default: mobilenet (Phase 1 + 2)
        from .mobilenet_classifier import classify
        clf_result = classify(image_path)

    print(f"[Pipeline] Classifier: {clf_result}")

    # ── Step 2: OpenCV color detection (all phases) ───────────────
    # Skip color detection for Google Lens — it already has full description
    if phase == 'google_lens':
        color_result = {"color_name": "", "color_hex": ""}
    else:
        color_result = detect_color(image_path)

    print(f"[Pipeline] Color: {color_result}")

    # ── Step 3: Build final search keyword ────────────────────────
    if phase == 'fashion_clip':
        # FashionCLIP already builds its own rich keyword
        # Color is already included in base_keyword from FashionCLIP
        search_keyword = clf_result.get('base_keyword', '')

    elif phase == 'google_lens':
        # Google Lens returns exact product label — use directly
        search_keyword = clf_result.get('base_keyword', '')

    else:
        # Phase 1/2/3 — combine classifier output with color
        search_keyword = build_keyword(
            base_keyword = clf_result.get('base_keyword', ''),
            color_name   = color_result.get('color_name', ''),
            phase        = phase,
            clip_desc    = clf_result.get('clip_description', ''),
        )

    print(f"[Pipeline] Final keyword: '{search_keyword}'")

    # ── Step 4: Return unified result ─────────────────────────────
    return {
        "phase"              : phase,
        "detected_label"     : clf_result.get('detected_label') or clf_result.get('base_keyword', ''),
        "category"           : clf_result.get('category', 'fashion'),
        "confidence"         : clf_result.get('confidence', 0.0),
        "detected_color"     : color_result.get('color_name', ''),
        "color_hex"          : color_result.get('color_hex', ''),
        "clip_description"   : clf_result.get('clip_description', ''),
        "fashion_attributes" : clf_result.get('all_attributes', {}),
        "google_lens_data"   : {
            "visual_matches"  : clf_result.get('visual_matches', []),
            "shopping_results": clf_result.get('shopping_results', []),
            "knowledge_graph" : clf_result.get('knowledge_graph', {}),
        },
        "search_keyword"     : search_keyword,
        "top5"               : clf_result.get('top5', []),
        "error"              : clf_result.get('error', ''),
    }
