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


def get_font(size_px: int, bold: bool = False):
    """Load Cyrillic font, fallback to default."""
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
                return ImageFont.truetype(path, size_px)
            except Exception:
                pass
    return ImageFont.load_default()


def _text_size(draw, text, font):
    """Get text width and height."""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _wrap_text(text, font, max_width, draw, max_lines=None):
    """Wrap text by words; if a word is too long, break it by characters."""
    if not text:
        return []
    words = str(text).split()
    lines = []
    current = ""
    
    for word in words:
        test = (current + " " + word).strip()
        w, _ = _text_size(draw, test, font)
        
        if w <= max_width:
            current = test
        else:
            # Word doesn't fit
            if current:
                lines.append(current)
            
            # Check if single word fits
            word_w, _ = _text_size(draw, word, font)
            if word_w <= max_width:
                current = word
            else:
                # Word too long - break by characters
                chars = list(word)
                temp = ""
                for ch in chars:
                    test_ch = temp + ch
                    ch_w, _ = _text_size(draw, test_ch, font)
                    if ch_w <= max_width:
                        temp = test_ch
                    else:
                        if temp:
                            lines.append(temp)
                        temp = ch
                if temp:
                    current = temp
                else:
                    current = ""
    
    if current:
        lines.append(current)
    
    result = lines if lines else [str(text)]
    if max_lines and len(result) > max_lines:
        result = result[:max_lines]
    return result


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
    VERTICAL layout:
      TOP: Name (full width, bold, 1-2 lines)
      MIDDLE LEFT: DataMatrix (square)
      MIDDLE RIGHT: Article + Supplier (stacked text)
      BOTTOM: KIZ code (small, full width)
      BOTTOM: EAN-13 barcode (if present)
    """
    w_mm, h_mm = LABEL_FORMATS.get(label_format, (58, 40))
    w_px = int(w_mm * dpi / 25.4)
    h_px = int(h_mm * dpi / 25.4)

    img = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w_px - 1, h_px - 1], outline="black", width=1)

    mg = max(4, int(0.8 * dpi / 25.4))  # ~0.8mm margin

    # Font sizes
    fs_name = max(9, int(10 * dpi / 72))    # ~10pt для названия
    fs_body = max(7, int(8 * dpi / 72))     # ~8pt для артикула/поставщика
    fs_small = max(6, int(6 * dpi / 72))    # ~6pt для КИЗ

    font_name = get_font(fs_name, bold=True)
    font_body = get_font(fs_body, bold=False)
    font_small = get_font(fs_small, bold=False)

    y = mg
    full_w = w_px - mg * 2

    # 1. NAME at top (full width, 1-2 lines max)
    if name:
        name_lines = _wrap_text(name, font_name, full_w, draw, max_lines=2)
        for line in name_lines:
            draw.text((mg, y), line, fill="#000000", font=font_name)
            _, lh = _text_size(draw, line, font_name)
            y += lh + 2
        y += 3

    # 2. DataMatrix + Article/Supplier zone
    # DataMatrix square (left side, ~40% of width)
    dm_size = min(int(full_w * 0.35), h_px - y - mg - 50)  # reserve 50px for bottom
    dm_size = max(dm_size, 30)
    dm_module = max(2, dm_size // 22)
    dm_img = generate_datamatrix(kiz, size=dm_module)
    dm_img = dm_img.resize((dm_size, dm_size), Image.NEAREST)
    dm_x = mg
    dm_y = y
    img.paste(dm_img, (dm_x, dm_y))

    # Text zone to the right of DataMatrix
    text_x = dm_x + dm_size + mg
    text_w = w_px - text_x - mg
    text_y = dm_y

    if article:
        art_text = f"Арт: {article[:20]}"
        draw.text((text_x, text_y), art_text, fill="#222222", font=font_body)
        _, lh = _text_size(draw, art_text, font_body)
        text_y += lh + 2

    if supplier:
        supp_lines = _wrap_text(supplier, font_body, text_w, draw, max_lines=2)
        for line in supp_lines:
            draw.text((text_x, text_y), line, fill="#444444", font=font_body)
            _, lh = _text_size(draw, line, font_body)
            text_y += lh + 1

    # Move y below DataMatrix
    y = dm_y + dm_size + mg

    # 3. KIZ code (small, full width, abbrev if needed)
    kiz_short = kiz[:20] + ".." + kiz[-8:] if len(kiz) > 30 else kiz
    kiz_lines = _wrap_text(kiz_short, font_small, full_w, draw, max_lines=2)
    for line in kiz_lines:
        draw.text((mg, y), line, fill="#666666", font=font_small)
        _, lh = _text_size(draw, line, font_small)
        y += lh + 1
    y += 2

    # 4. EAN-13 at bottom (if present)
    digits = "".join(filter(str.isdigit, str(barcode_val or "")))
    if len(digits) >= 8:
        try:
            ean_img = generate_ean13(barcode_val)
            ean_h = int(h_px * 0.22)
            ean_img = ean_img.resize((full_w, ean_h), Image.LANCZOS)
            ean_y = h_px - ean_h - mg - 12
            img.paste(ean_img, (mg, ean_y))
            # Barcode digits
            fs_dig = get_font(max(5, int(5 * dpi / 72)), bold=False)
            draw.text((mg + full_w // 2 - len(digits) * 3, ean_y + ean_h + 1), digits, fill="black", font=fs_dig)
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
