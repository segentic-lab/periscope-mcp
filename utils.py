import os
from PIL import Image
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

    # Resize to same dimensions if different
    w = max(img1.width, img2.width)
    h = max(img1.height, img2.height)
    if img1.size != (w, h):
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
        canvas.paste(img1, (0, 0))
        img1 = canvas
    if img2.size != (w, h):
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
        canvas.paste(img2, (0, 0))
        img2 = canvas

    pixels1 = img1.load()
    pixels2 = img2.load()
    diff_img = Image.new("RGB", (w, h), (0, 0, 0))
    diff_pixels = diff_img.load()

    diff_count = 0
    total = w * h

    for y in range(h):
        for x in range(w):
            r1, g1, b1 = pixels1[x, y]
            r2, g2, b2 = pixels2[x, y]
            dr = abs(r1 - r2)
            dg = abs(g1 - g2)
            db = abs(b1 - b2)
            if dr > threshold or dg > threshold or db > threshold:
                diff_count += 1
                diff_pixels[x, y] = (255, 0, 0)
            else:
                # Dim the unchanged area
                diff_pixels[x, y] = (r1 // 3, g1 // 3, b1 // 3)

    diff_percentage = round((diff_count / total) * 100, 2) if total > 0 else 0

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
