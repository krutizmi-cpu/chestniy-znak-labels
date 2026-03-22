import io
import base64
from PIL import Image

try:
    import treepoem
    TREEPOEM_AVAILABLE = True
except ImportError:
    TREEPOEM_AVAILABLE = False


def generate_datamatrix(kiz: str, size: int = 10) -> Image.Image:
    kiz = kiz.strip()
    if TREEPOEM_AVAILABLE:
        try:
            barcode = treepoem.generate_barcode(barcode_type="datamatrix", data=kiz)
            img = barcode.convert("RGB")
            w, h = img.size
            scale = max(1, size // 3)
            return img.resize((w * scale, h * scale), Image.NEAREST)
        except Exception as e:
            print(f"treepoem error: {e}")
    return _qr_fallback(kiz, size)


def generate_ean13(barcode_val: str) -> Image.Image:
    try:
        import barcode
        from barcode.writer import ImageWriter
        digits = "".join(filter(str.isdigit, str(barcode_val)))
        if len(digits) < 12:
            digits = digits.zfill(12)
        digits = digits[:13]
        EAN = barcode.get_barcode_class('ean13')
        ean = EAN(digits, writer=ImageWriter())
        img = ean.render(writer_options={
            "module_height": 12.0,
            "module_width": 0.35,
            "quiet_zone": 2.0,
            "write_text": False,
            "dpi": 203,
        })
        return img.convert("RGB")
    except Exception as e:
        print(f"EAN-13 error: {e}")
        return Image.new("RGB", (200, 80), "white")


def _qr_fallback(kiz: str, size: int = 10) -> Image.Image:
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=size, border=1)
        qr.add_data(kiz)
        qr.make(fit=True)
        return qr.make_image().convert("RGB")
    except Exception:
        return Image.new("RGB", (size * 20, size * 20), "white")


def image_to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def image_to_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
