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
    """Load Cyrillic font at size_px pixels."""
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


def _lh(draw, font):
    """Line height."""
    bbox = draw.textbbox((0, 0), "Ag", font=font)
    return bbox[3] - bbox[1]


def _wrap_text(text, font, max_w, draw):
    """Wrap text, break long words character-by-character if needed."""
    if not text:
        return []
    words = str(text).split()
    lines = []
    cur = ""
    
    for word in words:
        # Try adding word with space
        test = (cur + " " + word).strip()
        test_w = draw.textbbox((0, 0), test, font=font)[2]
        
        if test_w <= max_w:
            cur = test
        else:
            # Word doesn't fit
            if cur:
                lines.append(cur)
                cur = ""
            
            # Check if word itself is too long
            word_w = draw.textbbox((0, 0), word, font=font)[2]
            if word_w <= max_w:
                cur = word
            else:
                # Break word character by character
                for char in word:
                    test_char = cur + char
                    if draw.textbbox((0, 0), test_char, font=font)[2] <= max_w:
                        cur = test_char
                    else:
                        if cur:
                            lines.append(cur)
                        cur = char
    
    if cur:
        lines.append(cur)
    
    return lines if lines else [str(text)]


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
    VERTICAL LAYOUT:
      TOP: DataMatrix (centered, ~50% height)
      BOTTOM: Name, Article, Supplier, KIZ text, EAN-13 barcode
    """
    w_mm, h_mm = LABEL_FORMATS.get(label_format, (58, 40))
    w_px = int(w_mm * dpi / 25.4)
    h_px = int(h_mm * dpi / 25.4)

    img = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w_px - 1, h_px - 1], outline="black", width=1)

    mg = max(4, int(1.0 * dpi / 25.4))  # ~1mm margin

    # --- DataMatrix ZONE (TOP, centered horizontally) ---
    # Use ~45% of height for DataMatrix
    dm_zone_h = int(h_px * 0.45)
    dm_size = min(dm_zone_h - mg, w_px - mg * 2)
    dm_size = max(dm_size, 20)
    
    dm_img = generate_datamatrix(kiz, size=max(2, dm_size // 22))
    dm_img = dm_img.resize((dm_size, dm_size), Image.NEAREST)
    dm_x = (w_px - dm_size) // 2  # center horizontally
    dm_y = mg
    img.paste(dm_img, (dm_x, dm_y))

    # --- TEXT ZONE (BOTTOM) ---
    text_y_start = dm_y + dm_size + mg
    text_w = w_px - mg * 2
    
    # Check if EAN-13 needed
    digits = "".join(filter(str.isdigit, str(barcode_val or "")))
    has_ean = len(digits) >= 8
    ean_h = int(h_px * 0.20) if has_ean else 0
    ean_text_h = 8 if has_ean else 0
    
    avail_text_h = h_px - text_y_start - mg - ean_h - ean_text_h

    # Prepare text fields
    kiz_short = kiz[:18] + ".." + kiz[-6:] if len(kiz) > 26 else kiz
    
    # Auto-shrink fonts from 11px down to 6px
    chosen = None
    for fsize in range(11, 5, -1):
        fn = get_font(fsize, bold=True)
        fb = get_font(max(fsize - 1, 5), bold=False)
        fs = get_font(max(fsize - 2, 5), bold=False)
        
        lh_n = _lh(draw, fn) + 1
        lh_b = _lh(draw, fb) + 1
        lh_s = _lh(draw, fs) + 1
        
        ln_name = _wrap_text(name[:50] if name else "", fn, text_w, draw)[:2]
        ln_art = [f"Арт: {article[:25]}"] if article else []
        ln_sup = [f"Пост: {supplier[:25]}"] if supplier else []
        ln_kiz = _wrap_text(kiz_short, fs, text_w, draw)[:2]
        
        total_h = (
            len(ln_name) * lh_n + (2 if ln_name else 0) +
            len(ln_art) * lh_b + (1 if ln_art else 0) +
            len(ln_sup) * lh_s + (1 if ln_sup else 0) +
            len(ln_kiz) * lh_s
        )
        
        if total_h <= avail_text_h:
            chosen = (fn, fb, fs, lh_n, lh_b, lh_s, ln_name, ln_art, ln_sup, ln_kiz)
            break
    
    # Fallback smallest
    if not chosen:
        fsize = 6
        fn = get_font(fsize, bold=True)
        fb = get_font(5, bold=False)
        fs = get_font(5, bold=False)
        lh_n = _lh(draw, fn) + 1
        lh_b = _lh(draw, fb) + 1
        lh_s = _lh(draw, fs) + 1
        ln_name = _wrap_text(name[:50] if name else "", fn, text_w, draw)[:2]
        ln_art = [f"Арт: {article[:25]}"] if article else []
        ln_sup = [f"Пост: {supplier[:25]}"] if supplier else []
        ln_kiz = _wrap_text(kiz_short, fs, text_w, draw)[:2]
        chosen = (fn, fb, fs, lh_n, lh_b, lh_s, ln_name, ln_art, ln_sup, ln_kiz)
    
    fn, fb, fs, lh_n, lh_b, lh_s, ln_name, ln_art, ln_sup, ln_kiz = chosen

    # Draw text from top to bottom
    y = text_y_start
    tx = mg
    
    for line in ln_name:
        draw.text((tx, y), line, fill="#000000", font=fn)
        y += lh_n
    if ln_name:
        y += 2
    
    for line in ln_art:
        draw.text((tx, y), line, fill="#222222", font=fb)
        y += lh_b
    if ln_art:
        y += 1
    
    for line in ln_sup:
        draw.text((tx, y), line, fill="#444444", font=fs)
        y += lh_s
    if ln_sup:
        y += 1
    
    for line in ln_kiz:
        draw.text((tx, y), line, fill="#666666", font=fs)
        y += lh_s

    # EAN-13 at bottom
    if has_ean:
        try:
            ean_img = generate_ean13(barcode_val)
            ean_w = w_px - mg * 2
            ean_img = ean_img.resize((ean_w, ean_h), Image.LANCZOS)
            ean_y = h_px - ean_h - ean_text_h - mg
            img.paste(ean_img, (mg, ean_y))
            fs_d = get_font(6, bold=False)
            draw.text((mg + ean_w // 2 - len(digits) * 3, ean_y + ean_h + 1), digits, fill="black", font=fs_d)
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
