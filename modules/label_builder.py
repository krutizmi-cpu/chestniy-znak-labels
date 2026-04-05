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
    brand: str = "",
    size_value: str = "",
    color: str = "",
    composition: str = "",
    manufacturer: str = "",
    country: str = "",
    care: str = "",
    supplier: str = "",
    barcode_val: str = "",
    dpi: int = 203,
) -> Image.Image:
    """
    Balanced label layout.

    For compact formats like 58x40 we use a split layout:
    - left: name/article/supplier
    - right: DataMatrix
    - bottom: short KIZ + EAN13

    For larger formats we keep a spacious vertical layout.
    """
    w_mm, h_mm = LABEL_FORMATS.get(label_format, (58, 40))
    w_px = int(w_mm * dpi / 25.4)
    h_px = int(h_mm * dpi / 25.4)

    img = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w_px - 1, h_px - 1], outline="black", width=1)

    mg = max(4, int(0.8 * dpi / 25.4))
    content_w = w_px - mg * 2
    content_h = h_px - mg * 2

    compact_layout = (w_mm <= 60 and h_mm <= 45)

    fs_name = max(7, int(7 * dpi / 72))
    fs_body = max(5, int(5.5 * dpi / 72))
    fs_small = max(4, int(4 * dpi / 72))
    fs_digits = max(4, int(4 * dpi / 72))

    font_name = get_font(fs_name, bold=False)
    font_body = get_font(fs_body, bold=False)
    font_small = get_font(fs_small, bold=False)
    font_digits = get_font(fs_digits, bold=False)

    if compact_layout:
        gap = max(6, int(1.0 * dpi / 25.4))
        dm_size = min(max(int(content_h * 0.40), 70), int(content_w * 0.34))
        dm_size = max(dm_size, 62)

        left_w = content_w - dm_size - gap
        top_y = mg
        left_x = mg
        right_x = mg + left_w + gap

        y = top_y
        if name:
            name_lines = _wrap_text(name, font_name, left_w, draw, max_lines=2)
            for line in name_lines:
                draw.text((left_x, y), line, fill="#000000", font=font_name)
                _, lh = _text_size(draw, line, font_name)
                y += lh + 1
            y += 2

        if article:
            art_text = f"Арт: {article}"
            for line in _wrap_text(art_text, font_body, left_w, draw, max_lines=1):
                draw.text((left_x, y), line, fill="#222222", font=font_body)
                _, lh = _text_size(draw, line, font_body)
                y += lh + 1
            y += 1

        meta_parts = []
        if size_value:
            meta_parts.append(f"Размер: {size_value}")
        if color:
            meta_parts.append(f"Цвет: {color}")
        if composition:
            meta_parts.append(f"Состав: {composition}")
        if country:
            meta_parts.append(f"Страна: {country}")
        if care:
            meta_parts.append(f"Уход: {care}")
        for meta in meta_parts[:5]:
            for line in _wrap_text(meta, font_body, left_w, draw, max_lines=1):
                draw.text((left_x, y), line, fill="#444444", font=font_body)
                _, lh = _text_size(draw, line, font_body)
                y += lh + 1
        maker = manufacturer or supplier
        if maker:
            for line in _wrap_text(maker, font_small, left_w, draw, max_lines=1):
                draw.text((left_x, y), line, fill="#666666", font=font_small)
                _, lh = _text_size(draw, line, font_small)
                y += lh + 1

        dm_module = max(2, dm_size // 22)
        dm_img = generate_datamatrix(kiz, size=dm_module)
        dm_img = dm_img.resize((dm_size, dm_size), Image.NEAREST)
        img.paste(dm_img, (right_x, top_y))

        # short honest sign code directly under DataMatrix
        caption_y = top_y + dm_size + 2
        caption = "КИЗ"
        cap_w, cap_h = _text_size(draw, caption, font_small)
        draw.text((right_x + max(0, (dm_size - cap_w) // 2), caption_y), caption, fill="#444444", font=font_small)

        # Bottom zone: barcode on left, service block on right
        bottom_y = mg + int(content_h * 0.66)
        barcode_zone_w = int(content_w * 0.62)
        right_zone_x = mg + barcode_zone_w + gap
        right_zone_w = content_w - barcode_zone_w - gap

        digits = "".join(filter(str.isdigit, str(barcode_val or "")))
        if len(digits) >= 8:
            try:
                ean_img = generate_ean13(barcode_val)
                ean_h = min(max(int(content_h * 0.16), 24), 30)
                ean_img = ean_img.resize((barcode_zone_w, ean_h), Image.LANCZOS)
                img.paste(ean_img, (mg, bottom_y))
                draw.rectangle([mg-1, bottom_y-1, mg + barcode_zone_w + 1, bottom_y + ean_h + 14], outline="#000000", width=1)
                txt_w, txt_h = _text_size(draw, digits, font_digits)
                draw.text((mg + (barcode_zone_w - txt_w) // 2, bottom_y + ean_h + 1), digits, fill="black", font=font_digits)
            except Exception:
                pass

        service_lines = ["ЧЕСТНЫЙ", "ЗНАК", "EAC"]
        ky = bottom_y + 2
        for line in service_lines:
            txt_w, txt_h = _text_size(draw, line, font_small)
            draw.text((right_zone_x + max(0, (right_zone_w - txt_w)//2), ky), line, fill="#555555", font=font_small)
            ky += txt_h + 1
        return img

    # spacious vertical layout for larger labels
    y = mg
    if name:
        name_lines = _wrap_text(name, font_name, content_w, draw, max_lines=2)
        for line in name_lines:
            draw.text((mg, y), line, fill="#000000", font=font_name)
            _, lh = _text_size(draw, line, font_name)
            y += lh + 1
        y += 2

    if article:
        art_text = f"Арт: {article}"
        for line in _wrap_text(art_text, font_body, content_w, draw, max_lines=1):
            draw.text((mg, y), line, fill="#222222", font=font_body)
            _, lh = _text_size(draw, line, font_body)
            y += lh + 1
        y += 1

    if supplier:
        for line in _wrap_text(supplier, font_body, content_w, draw, max_lines=2):
            draw.text((mg, y), line, fill="#444444", font=font_body)
            _, lh = _text_size(draw, line, font_body)
            y += lh + 1
        y += 2

    dm_size = min(int(content_w * 0.5), 80)
    dm_size = max(dm_size, 40)
    dm_module = max(2, dm_size // 22)
    dm_img = generate_datamatrix(kiz, size=dm_module)
    dm_img = dm_img.resize((dm_size, dm_size), Image.NEAREST)
    dm_x = mg + (content_w - dm_size) // 2
    img.paste(dm_img, (dm_x, y))
    y += dm_size + 3

    kiz_short = kiz[:18] + ".." + kiz[-6:] if len(kiz) > 26 else kiz
    for line in _wrap_text(kiz_short, font_small, content_w, draw, max_lines=2):
        draw.text((mg, y), line, fill="#666666", font=font_small)
        _, lh = _text_size(draw, line, font_small)
        y += lh + 1
    y += 2

    digits = "".join(filter(str.isdigit, str(barcode_val or "")))
    if len(digits) >= 8:
        try:
            ean_img = generate_ean13(barcode_val)
            ean_h = min(int(h_px * 0.18), 35)
            ean_img = ean_img.resize((content_w, ean_h), Image.LANCZOS)
            img.paste(ean_img, (mg, y))
            y += ean_h + 2
            txt_w, _ = _text_size(draw, digits, font_digits)
            draw.text((mg + (content_w - txt_w) // 2, y), digits, fill="black", font=font_digits)
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
            brand=str(item.get("brand", "") or ""),
            size_value=str(item.get("size", "") or ""),
            color=str(item.get("color", "") or ""),
            composition=str(item.get("composition", "") or ""),
            manufacturer=str(item.get("manufacturer", "") or ""),
            country=str(item.get("country", "") or ""),
            care=str(item.get("care", "") or ""),
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
