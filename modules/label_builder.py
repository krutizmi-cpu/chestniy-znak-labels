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
    """Load a Cyrillic-capable font at size_px pixels, fall back to default."""
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
    """Line height for a font."""
    bbox = draw.textbbox((0, 0), "Ag", font=font)
    return bbox[3] - bbox[1]


def _wrap(text, font, max_w, draw, max_lines=None):
    """Wrap text into lines within max_w pixels; optionally cap at max_lines."""
    if not text:
        return []
    words = str(text).split()
    lines, cur = [], ""
    for word in words:
        test = (cur + " " + word).strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    result = lines if lines else [str(text)]
    if max_lines:
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
    Layout:
      LEFT  (40% w): DataMatrix, vertically centered
      RIGHT (60% w): name / article / supplier / KIZ short / EAN-13
    Fonts auto-shrink from 14px down until all text fits.
    """
    w_mm, h_mm = LABEL_FORMATS.get(label_format, (58, 40))
    w_px = int(w_mm * dpi / 25.4)
    h_px = int(h_mm * dpi / 25.4)

    img = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w_px - 1, h_px - 1], outline="black", width=1)

    mg = max(4, int(1.0 * dpi / 25.4))  # ~1 mm margin

    # DataMatrix: square, fills 40% width or full height (whichever smaller)
    dm_max = min(h_px - mg * 2, int(w_px * 0.40) - mg)
    dm_size = max(dm_max, 20)
    dm_img = generate_datamatrix(kiz, size=max(2, dm_size // 22))
    dm_img = dm_img.resize((dm_size, dm_size), Image.NEAREST)
    dm_x, dm_y = mg, (h_px - dm_size) // 2
    img.paste(dm_img, (dm_x, dm_y))

    # Text zone
    tx = dm_x + dm_size + mg
    tw = w_px - tx - mg  # available text width
    if tw < 8:
        return img

    # EAN-13 bottom strip
    digits = "".join(filter(str.isdigit, str(barcode_val or "")))
    has_ean = len(digits) >= 8
    ean_strip_h = int(h_px * 0.28) if has_ean else 0  # barcode image
    ean_num_h = 10 if has_ean else 0                   # digit row
    bottom = ean_strip_h + ean_num_h + mg if has_ean else 0

    avail_h = h_px - mg * 2 - bottom  # height available for text

    # KIZ abbreviation: first 18 + last 6
    kiz_s = kiz[:18] + ".." + kiz[-6:] if len(kiz) > 26 else kiz
    art_s = str(article)[:22] if article else ""
    sup_s = str(supplier)[:22] if supplier else ""
    name_s = str(name)[:40] if name else ""

    # Auto-shrink: try font sizes 14..7 px until text fits
    chosen = None
    for fsize in range(14, 6, -1):
        fn = get_font(fsize, bold=True)         # name
        fb = get_font(max(fsize - 2, 6), bold=False)  # body
        fs = get_font(max(fsize - 3, 5), bold=False)  # small

        lh_n = _lh(draw, fn) + 1
        lh_b = _lh(draw, fb) + 1
        lh_s = _lh(draw, fs) + 1
        gap = 2

        ln_name = _wrap(name_s, fn, tw, draw, max_lines=2)
        ln_art  = _wrap(f"Арт: {art_s}", fb, tw, draw, max_lines=1) if art_s else []
        ln_sup  = _wrap(sup_s, fs, tw, draw, max_lines=1) if sup_s else []
        ln_kiz  = _wrap(kiz_s, fs, tw, draw, max_lines=3)

        total = (
            len(ln_name) * lh_n + (gap if ln_name else 0) +
            len(ln_art)  * lh_b + (gap if ln_art  else 0) +
            len(ln_sup)  * lh_s + (gap if ln_sup  else 0) +
            len(ln_kiz)  * lh_s
        )
        if total <= avail_h:
            chosen = (fn, fb, fs, lh_n, lh_b, lh_s,
                      ln_name, ln_art, ln_sup, ln_kiz, gap)
            break

    # Fallback: smallest size
    if chosen is None:
        fsize = 7
        fn = get_font(fsize, bold=True)
        fb = get_font(max(fsize - 2, 5), bold=False)
        fs = get_font(max(fsize - 3, 4), bold=False)
        lh_n = _lh(draw, fn) + 1
        lh_b = _lh(draw, fb) + 1
        lh_s = _lh(draw, fs) + 1
        gap = 1
        ln_name = _wrap(name_s, fn, tw, draw, max_lines=2)
        ln_art  = _wrap(f"Арт: {art_s}", fb, tw, draw, max_lines=1) if art_s else []
        ln_sup  = _wrap(sup_s, fs, tw, draw, max_lines=1) if sup_s else []
        ln_kiz  = _wrap(kiz_s, fs, tw, draw, max_lines=3)
        chosen = (fn, fb, fs, lh_n, lh_b, lh_s,
                  ln_name, ln_art, ln_sup, ln_kiz, gap)

    fn, fb, fs, lh_n, lh_b, lh_s, ln_name, ln_art, ln_sup, ln_kiz, gap = chosen

    # Draw text, clipping to avail_h
    y = mg
    clip_y = mg + avail_h

    def draw_lines(lines, font, lh, color):
        nonlocal y
        for line in lines:
            if y + lh > clip_y:
                break
            draw.text((tx, y), line, fill=color, font=font)
            y += lh

    draw_lines(ln_name, fn, lh_n, "#000000")
    if ln_name:
        y += gap
    draw_lines(ln_art, fb, lh_b, "#222222")
    if ln_art:
        y += gap
    draw_lines(ln_sup, fs, lh_s, "#444444")
    if ln_sup:
        y += gap
    draw_lines(ln_kiz, fs, lh_s, "#666666")

    # EAN-13 barcode strip at bottom
    if has_ean:
        try:
            ean_img = generate_ean13(barcode_val)
            ean_img = ean_img.resize((tw, ean_strip_h), Image.LANCZOS)
            ey = h_px - ean_strip_h - ean_num_h - mg
            img.paste(ean_img, (tx, ey))
            fs_d = get_font(max(5, int(dpi * 4.5 / 72)), bold=False)
            draw.text((tx, ey + ean_strip_h + 1), digits, fill="black", font=fs_d)
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
