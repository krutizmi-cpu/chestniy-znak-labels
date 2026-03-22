import io
import os
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from modules.generator import generate_datamatrix, generate_ean13, image_to_bytes

LABEL_FORMATS = {
    "58x40 mm (standard)": (58, 40),
    "58x60 mm": (58, 60),
    "40x30 mm": (40, 30),
    "60x40 mm": (60, 40),
    "100x50 mm": (100, 50),
    "A6 (105x148 mm)": (105, 148),
    "A4 (210x297 mm)": (210, 297),
}


def get_font(size_pt: int, bold: bool = False):
    """Load a Cyrillic-capable font, fall back to default."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans{}.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-{}.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-{}.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans{}.ttf",
    ]
    suffix_map = {
        "/usr/share/fonts/truetype/dejavu/DejaVuSans{}.ttf": "-Bold" if bold else "",
        "/usr/share/fonts/truetype/liberation/LiberationSans-{}.ttf": "Bold" if bold else "Regular",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-{}.ttf": "B" if bold else "R",
        "/usr/share/fonts/truetype/freefont/FreeSans{}.ttf": "Bold" if bold else "",
    }
    for tpl in candidates:
        path = tpl.format(suffix_map[tpl])
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size_pt)
            except Exception:
                pass
    return ImageFont.load_default()


def text_height(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


def wrap_text(text: str, font, max_width_px: int, draw: ImageDraw.ImageDraw) -> list:
    """Break text into lines fitting max_width_px."""
    if not text:
        return []
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] <= max_width_px:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines if lines else [text]


def build_label_image(
    kiz: str,
    label_format: str = "58x40 mm (standard)",
    article: str = "",
    name: str = "",
    supplier: str = "",
    barcode_val: str = "",
    dpi: int = 203,
) -> Image.Image:
    """
    Layout:
      LEFT  (~42%): DataMatrix QR
      RIGHT (~58%): text block (name, article, supplier, KIZ) + EAN-13 at bottom
    All text is auto-sized to fit within the available height.
    """
    w_mm, h_mm = LABEL_FORMATS.get(label_format, (58, 40))
    w_px = int(w_mm * dpi / 25.4)
    h_px = int(h_mm * dpi / 25.4)

    img = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w_px - 1, h_px - 1], outline="black", width=1)

    margin = max(4, int(1.2 * dpi / 25.4))  # ~1.2 mm

    # --- DataMatrix: 42% of width, centered vertically ---
    dm_size = min(h_px - margin * 2, int(w_px * 0.42) - margin)
    dm_size = max(dm_size, 20)
    dm_module = max(2, dm_size // 22)
    dm_img = generate_datamatrix(kiz, size=dm_module)
    dm_img = dm_img.resize((dm_size, dm_size), Image.NEAREST)
    dm_x = margin
    dm_y = (h_px - dm_size) // 2
    img.paste(dm_img, (dm_x, dm_y))

    # --- Text zone ---
    text_x = dm_x + dm_size + margin
    text_right = w_px - margin
    text_w = text_right - text_x
    if text_w < 10:
        return img

    # --- EAN-13 zone at bottom (reserve space if barcode present) ---
    has_ean = bool(barcode_val and len("".join(filter(str.isdigit, str(barcode_val)))) >= 8)
    ean_h = int(h_px * 0.26) if has_ean else 0
    ean_digit_h = int(dpi * 6 / 72) if has_ean else 0  # ~6pt for digit line
    bottom_reserve = ean_h + ean_digit_h + margin if has_ean else 0

    # Available height for text block
    text_area_h = h_px - margin * 2 - bottom_reserve

    # --- Compute font sizes that actually fit ---
    # Start with target pts and shrink until everything fits
    def try_layout(fs_name_pt, fs_body_pt, fs_small_pt):
        fn = get_font(fs_name_pt, bold=True)
        fb = get_font(fs_body_pt, bold=False)
        fs = get_font(fs_small_pt, bold=False)

        lines_name = wrap_text(name, fn, text_w, draw)[:2] if name else []
        lines_art = ([f"Арт: {article[:20]}"] if article else [])
        lines_supp = ([supplier[:25]] if supplier else [])

        # KIZ: show only first ~20 chars + last 6, wrapped
        kiz_short = kiz[:20] + "..." + kiz[-6:] if len(kiz) > 28 else kiz
        lines_kiz = wrap_text(kiz_short, fs, text_w, draw)

        total_h = 0
        lh_name = text_height(draw, "Ag", fn) + 1
        lh_body = text_height(draw, "Ag", fb) + 1
        lh_small = text_height(draw, "Ag", fs) + 1

        total_h += len(lines_name) * lh_name + (2 if lines_name else 0)
        total_h += len(lines_art) * lh_body + (2 if lines_art else 0)
        total_h += len(lines_supp) * lh_small + (2 if lines_supp else 0)
        total_h += len(lines_kiz) * lh_small

        return total_h, fn, fb, fs, lines_name, lines_art, lines_supp, lines_kiz, lh_name, lh_body, lh_small

    # Try decreasing font sizes until text fits
    for fs_name_pt in range(8, 4, -1):
        fs_body_pt = max(5, fs_name_pt - 1)
        fs_small_pt = max(4, fs_name_pt - 2)
        total_h, fn, fb, fs, lines_name, lines_art, lines_supp, lines_kiz, lh_name, lh_body, lh_small = \
            try_layout(fs_name_pt, fs_body_pt, fs_small_pt)
        if total_h <= text_area_h:
            break

    # --- Draw text top-down ---
    y = margin

    for line in lines_name:
        draw.text((text_x, y), line, fill="black", font=fn)
        y += lh_name
    if lines_name:
        y += 2

    for line in lines_art:
        draw.text((text_x, y), line, fill="#1a1a1a", font=fb)
        y += lh_body
    if lines_art:
        y += 2

    for line in lines_supp:
        draw.text((text_x, y), line, fill="#444444", font=fs)
        y += lh_small
    if lines_supp:
        y += 2

    for line in lines_kiz:
        draw.text((text_x, y), line, fill="#666666", font=fs)
        y += lh_small

    # --- EAN-13 at bottom ---
    if has_ean:
        digits = "".join(filter(str.isdigit, str(barcode_val)))
        try:
            ean_img = generate_ean13(barcode_val)
            ean_img = ean_img.resize((text_w, ean_h), Image.LANCZOS)
            ean_y = h_px - ean_h - ean_digit_h - margin
            img.paste(ean_img, (text_x, ean_y))
            # Digits below barcode
            fs_digit = get_font(max(4, int(dpi * 5 / 72)), bold=False)
            draw.text(
                (text_x + text_w // 2 - len(digits) * max(4, int(dpi * 5 / 72)) // 4, ean_y + ean_h + 1),
                digits, fill="black", font=fs_digit
            )
        except Exception:
            pass

    return img


def build_pdf(labels_data: list, label_format: str = "58x40 mm (standard)", dpi: int = 203) -> bytes:
    w_mm, h_mm = LABEL_FORMATS.get(label_format, (58, 40))
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w_mm * mm, h_mm * mm))
    for item in labels_data:
        kiz = item.get("kiz", "")
        if not kiz:
            continue
        img = build_label_image(
            kiz=kiz, label_format=label_format,
            article=str(item.get("article", "") or ""),
            name=str(item.get("name", "") or ""),
            supplier=str(item.get("supplier", "") or ""),
            barcode_val=str(item.get("barcode_val", "") or ""),
            dpi=dpi,
        )
        c.drawImage(ImageReader(io.BytesIO(image_to_bytes(img))), 0, 0, w_mm * mm, h_mm * mm)
        c.showPage()
    c.save()
    return buf.getvalue()


def build_pdf_a4(labels_data: list, label_format: str = "58x40 mm (standard)", dpi: int = 203) -> bytes:
    from reportlab.lib.pagesizes import A4
    w_mm, h_mm = LABEL_FORMATS.get(label_format, (58, 40))
    a4_w, a4_h = A4
    cols = max(1, int(210 / w_mm))
    rows = max(1, int(297 / h_mm))
    per_page = cols * rows
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    idx = 0
    while idx < len(labels_data):
        page_items = labels_data[idx: idx + per_page]
        for i, item in enumerate(page_items):
            kiz = item.get("kiz", "")
            if not kiz:
                continue
            col = i % cols
            row = i // cols
            x = col * w_mm * mm
            y = a4_h - (row + 1) * h_mm * mm
            img = build_label_image(
                kiz=kiz, label_format=label_format,
                article=str(item.get("article", "") or ""),
                name=str(item.get("name", "") or ""),
                supplier=str(item.get("supplier", "") or ""),
                barcode_val=str(item.get("barcode_val", "") or ""),
                dpi=dpi,
            )
            c.drawImage(ImageReader(io.BytesIO(image_to_bytes(img))), x, y, w_mm * mm, h_mm * mm)
        c.showPage()
        idx += per_page
    c.save()
    return buf.getvalue()
