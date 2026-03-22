import io
import os
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from modules.generator import generate_datamatrix, image_to_bytes

# Форматы этикеток (ширина x высота в мм)
LABEL_FORMATS = {
    "58x40 мм (стандарт)": (58, 40),
    "58x60 мм": (58, 60),
    "40x30 мм": (40, 30),
    "60x40 мм": (60, 40),
    "100x50 мм": (100, 50),
    "A6 (105x148 мм)": (105, 148),
    "A4 (210x297 мм)": (210, 297),
}


def get_font(size_pt: int, bold: bool = False):
    """Получить шрифт с fallback на дефолтный"""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans{}.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-{}.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans{}.ttf",
    ]
    suffix = "-Bold" if bold else ""
    for path_tpl in font_paths:
        path = path_tpl.format(suffix if "-" in path_tpl else ("Bold" if bold else ""))
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size_pt)
        except Exception:
            pass
    return ImageFont.load_default()


def build_label_image(
    kiz: str,
    label_format: str = "58x40 мм (стандарт)",
    article: str = "",
    name: str = "",
    supplier: str = "",
    barcode_val: str = "",
    dpi: int = 203,
) -> Image.Image:
    """
    Построение одной этикетки как PIL Image.
    dpi=203 стандарт для термопринтеров.
    """
    w_mm, h_mm = LABEL_FORMATS.get(label_format, (58, 40))
    w_px = int(w_mm * dpi / 25.4)
    h_px = int(h_mm * dpi / 25.4)

    img = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(img)

    # Рамка
    draw.rectangle([1, 1, w_px - 2, h_px - 2], outline="black", width=1)

    margin = max(4, int(2 * dpi / 25.4))

    # DataMatrix - занимает левую часть
    dm_size = min(w_px, h_px) - margin * 2
    if w_mm > h_mm:  # горизонтальная этикетка
        dm_size = h_px - margin * 2
    else:
        dm_size = min(w_px, h_px) // 2

    dm_module = max(2, dm_size // 22)
    dm_img = generate_datamatrix(kiz, size=dm_module)
    dm_img = dm_img.resize((dm_size, dm_size), Image.NEAREST)

    dm_x = margin
    dm_y = (h_px - dm_size) // 2
    img.paste(dm_img, (dm_x, dm_y))

    # Текстовая зона
    text_x = dm_x + dm_size + margin
    text_y = margin
    max_text_w = w_px - text_x - margin

    font_title_size = max(8, int(8 * dpi / 72))
    font_body_size = max(6, int(7 * dpi / 72))
    font_small_size = max(5, int(6 * dpi / 72))

    font_title = get_font(font_title_size, bold=True)
    font_body = get_font(font_body_size)
    font_small = get_font(font_small_size)

    y = text_y
    line_gap = font_title_size + 2

    if name:
        # Обрезаем длинное название
        max_chars = max(10, max_text_w // (font_title_size // 2))
        name_display = name[:max_chars] + "..." if len(name) > max_chars else name
        draw.text((text_x, y), name_display, fill="black", font=font_title)
        y += line_gap + 2

    if article:
        draw.text((text_x, y), f"Арт: {article}", fill="#333333", font=font_body)
        y += line_gap

    if supplier:
        max_chars_s = max(8, max_text_w // (font_body_size // 2))
        supp_d = supplier[:max_chars_s] + "..." if len(supplier) > max_chars_s else supplier
        draw.text((text_x, y), f"Пост: {supp_d}", fill="#333333", font=font_body)
        y += line_gap

    # КИЗ внизу под DataMatrix
    kiz_display = kiz[:22] + "..." if len(kiz) > 22 else kiz
    draw.text(
        (margin, dm_y + dm_size + 2),
        kiz_display,
        fill="#666666",
        font=font_small
    )

    if barcode_val:
        draw.text(
            (text_x, h_px - font_small_size - margin),
            f"ШК: {barcode_val}",
            fill="black",
            font=font_small
        )

    return img


def build_pdf(
    labels_data: list,
    label_format: str = "58x40 мм (стандарт)",
    dpi: int = 203,
) -> bytes:
    """
    Построение PDF с несколькими этикетками.
    labels_data: список словарей {kiz, article, name, supplier, barcode_val}
    Возвращает bytes PDF.
    """
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

        img_bytes = image_to_bytes(img, fmt="PNG")
        img_reader = ImageReader(io.BytesIO(img_bytes))
        c.drawImage(img_reader, 0, 0, w_mm * mm, h_mm * mm)
        c.showPage()

    c.save()
    return buf.getvalue()


def build_pdf_a4(
    labels_data: list,
    label_format: str = "58x40 мм (стандарт)",
    dpi: int = 203,
) -> bytes:
    """
    Построение PDF A4 с несколькими этикетками на листе.
    """
    from reportlab.lib.pagesizes import A4

    w_mm, h_mm = LABEL_FORMATS.get(label_format, (58, 40))
    a4_w, a4_h = A4  # в points

    cols = max(1, int(210 / w_mm))
    rows = max(1, int(297 / h_mm))
    per_page = cols * rows

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    idx = 0
    total = len(labels_data)

    while idx < total:
        page_items = labels_data[idx: idx + per_page]
        idx += per_page

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
            img_bytes = image_to_bytes(img, fmt="PNG")
            img_reader = ImageReader(io.BytesIO(img_bytes))
            c.drawImage(img_reader, x, y, w_mm * mm, h_mm * mm)

        c.showPage()

    c.save()
    return buf.getvalue()
