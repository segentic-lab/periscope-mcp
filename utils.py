import os
from PIL import Image, ImageChops
import config


def compare_screenshots(
    path1: str, path2: str, threshold: int = 10
) -> dict:
    """Compare two screenshots pixel-by-pixel.

    Args:
        path1: Path to first screenshot
        path2: Path to second screenshot
        threshold: Color difference threshold 0-255 (pixels with diff > threshold are marked)

    Returns dict with diff_percentage, diff_image_path, and dimensions info.
    """
    if not os.path.exists(path1):
        return {"success": False, "error": f"Screenshot not found: {path1}"}
    if not os.path.exists(path2):
        return {"success": False, "error": f"Screenshot not found: {path2}"}

    img1 = Image.open(path1).convert("RGB")
    img2 = Image.open(path2).convert("RGB")

    # Pad to same dimensions if different; area outside a smaller image is
    # counted as different (it exists in only one screenshot).
    w = max(img1.width, img2.width)
    h = max(img1.height, img2.height)
    missing_mask = Image.new("L", (w, h), 0)
    for img in (img1, img2):
        if img.size != (w, h):
            outside = Image.new("L", (w, h), 255)
            outside.paste(0, (0, 0, img.width, img.height))
            missing_mask = ImageChops.lighter(missing_mask, outside)
    if img1.size != (w, h):
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
        canvas.paste(img1, (0, 0))
        img1 = canvas
    if img2.size != (w, h):
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
        canvas.paste(img2, (0, 0))
        img2 = canvas

    # Vectorized per-channel comparison (the previous per-pixel Python loop
    # took minutes on full-page screenshots): a pixel differs when any channel
    # deviates by more than `threshold`.
    delta = ImageChops.difference(img1, img2)
    bands = [b.point(lambda p: 255 if p > threshold else 0) for b in delta.split()]
    mask = bands[0]
    for b in bands[1:]:
        mask = ImageChops.lighter(mask, b)
    mask = ImageChops.lighter(mask, missing_mask)

    total = w * h
    diff_count = mask.histogram()[255]
    diff_percentage = round((diff_count / total) * 100, 2) if total > 0 else 0

    # Diff image: changed pixels red, unchanged area dimmed
    dimmed = img1.point(lambda p: p // 3)
    red = Image.new("RGB", (w, h), (255, 0, 0))
    diff_img = Image.composite(red, dimmed, mask)

    # Save diff image
    diff_dir = os.path.join(config.DATA_DIR, "diffs")
    os.makedirs(diff_dir, exist_ok=True)
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    diff_path = os.path.join(diff_dir, f"diff_{timestamp}.png")
    diff_img.save(diff_path)

    return {
        "success": True,
        "diff_percentage": diff_percentage,
        "diff_pixels": diff_count,
        "total_pixels": total,
        "diff_image_path": diff_path,
        "dimensions": {"width": w, "height": h},
        "screenshot1": path1,
        "screenshot2": path2,
        "threshold": threshold,
    }
