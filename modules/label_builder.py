import io
import os
import textwrap
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
    """Load a font that supports Cyrillic. Falls back to default."""
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
    # Last resort: default bitmap font (no Cyrillic but won't crash)
    return ImageFont.load_default()


def wrap_text(text: str, font, max_width_px: int, draw: ImageDraw.ImageDraw) -> list:
    """Break text into lines that fit within max_width_px."""
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
    Layout (left to right):
      LEFT:  DataMatrix (square, ~40% width)
      RIGHT: Name (top), Article, Supplier, KIZ full text (wrapped), EAN-13 barcode (bottom)
    """
    w_mm, h_mm = LABEL_FORMATS.get(label_format, (58, 40))
    w_px = int(w_mm * dpi / 25.4)
    h_px = int(h_mm * dpi / 25.4)

    img = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(img)

    # Thin border
    draw.rectangle([0, 0, w_px - 1, h_px - 1], outline="black", width=1)

    margin = max(3, int(1.5 * dpi / 25.4))  # ~1.5mm

    # --- DataMatrix zone (left side, square) ---
    dm_size = h_px - margin * 2
    dm_module = max(2, dm_size // 22)
    dm_img = generate_datamatrix(kiz, size=dm_module)
    dm_img = dm_img.resize((dm_size, dm_size), Image.NEAREST)
    dm_x = margin
    dm_y = margin
    img.paste(dm_img, (dm_x, dm_y))

    # --- Text zone (right of DataMatrix) ---
    text_x = dm_x + dm_size + margin
    text_right = w_px - margin
    text_w = text_right - text_x
    text_y = margin

    # Font sizes in px (converted from pt at 203 dpi)
    fs_name = max(10, int(8 * dpi / 72))
    fs_body = max(8, int(7 * dpi / 72))
    fs_small = max(7, int(6 * dpi / 72))

    font_name = get_font(fs_name, bold=True)
    font_body = get_font(fs_body, bold=False)
    font_small = get_font(fs_small, bold=False)

    y = text_y

    # 1. Product name (bold, wrapped)
    if name:
        lines = wrap_text(name, font_name, text_w, draw)
        for line in lines[:3]:  # max 3 lines
            draw.text((text_x, y), line, fill="black", font=font_name)
            bbox = draw.textbbox((0, 0), line, font=font_name)
            y += (bbox[3] - bbox[1]) + 1
        y += 2

    # 2. Article
    if article:
        art_text = f"Art: {article}"
        draw.text((text_x, y), art_text, fill="#222222", font=font_body)
        bbox = draw.textbbox((0, 0), art_text, font=font_body)
        y += (bbox[3] - bbox[1]) + 2

    # 3. Supplier
    if supplier:
        supp_text = supplier[:30]
        draw.text((text_x, y), supp_text, fill="#444444", font=font_small)
        bbox = draw.textbbox((0, 0), supp_text, font=font_small)
        y += (bbox[3] - bbox[1]) + 2

    # 4. Full KIZ (wrapped, small font, grey)
    kiz_lines = wrap_text(kiz, font_small, text_w, draw)
    for line in kiz_lines:
        draw.text((text_x, y), line, fill="#555555", font=font_small)
        bbox = draw.textbbox((0, 0), line, font=font_small)
        y += (bbox[3] - bbox[1]) + 1

    # 5. EAN-13 barcode at bottom right zone
    if barcode_val:
        digits = "".join(filter(str.isdigit, str(barcode_val)))
        if len(digits) >= 8:
            ean_img = generate_ean13(barcode_val)
            # Scale to fit text zone width
            ean_w = text_w
            ean_h = max(20, int(h_px * 0.28))
            ean_img = ean_img.resize((ean_w, ean_h), Image.LANCZOS)
            ean_y = h_px - ean_h - margin - int(fs_small * 1.3)
            img.paste(ean_img, (text_x, ean_y))
            # Print barcode number below
            draw.text(
                (text_x + ean_w // 2 - len(digits) * fs_small // 4, ean_y + ean_h + 1),
                digits,
                fill="black",
                font=font_small
            )

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
            kiz=kiz,
            label_format=label_format,
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
                kiz=kiz,
                label_format=label_format,
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
