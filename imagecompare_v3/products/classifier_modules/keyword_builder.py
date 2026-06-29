"""
keyword_builder.py
───────────────────
Combines outputs from mobilenet + color_detector (Phase 2)
or clip + color_detector (Phase 3) into a final search keyword.

Phase 1:  base_keyword only               → "silk saree"
Phase 2:  color + base_keyword            → "red silk saree"
Phase 3:  clip_description + color check  → "red banarasi silk saree women"
"""


def build_keyword(
    base_keyword : str,
    color_name   : str  = "",
    phase        : str  = "mobilenet",
    clip_desc    : str  = "",
) -> str:
    """
    Build the final search keyword.

    Args:
        base_keyword : from MobileNet label map or CLIP
        color_name   : from OpenCV color detector
        phase        : 'mobilenet' or 'clip'
        clip_desc    : full CLIP description (Phase 3 only)

    Returns:
        Final search keyword string
    """

    if phase == "clip":
        # Phase 3 — CLIP already gives rich description
        # Only prepend color if it's not already mentioned in the description
        if color_name and color_name not in clip_desc.lower():
            keyword = f"{color_name} {clip_desc}"
        else:
            keyword = clip_desc
    else:
        # Phase 1 & 2 — MobileNet base keyword + color prefix
        if color_name:
            # Don't duplicate if color already in keyword
            if color_name.lower() not in base_keyword.lower():
                keyword = f"{color_name} {base_keyword}"
            else:
                keyword = base_keyword
        else:
            keyword = base_keyword

    return keyword.strip()
