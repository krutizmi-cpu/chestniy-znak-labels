import io
import base64
from PIL import Image

try:
    import treepoem
    TREEPOEM_AVAILABLE = True
except ImportError:
    TREEPOEM_AVAILABLE = False


def generate_datamatrix(kiz: str, size: int = 10) -> Image.Image:
    """
    Генерация DataMatrix из КИЗ.
    size — масштаб (размер модуля в пикселях).
    """
    kiz = kiz.strip()

    if TREEPOEM_AVAILABLE:
        try:
            barcode = treepoem.generate_barcode(
                barcode_type="datamatrix",
                data=kiz,
            )
            img = barcode.convert("RGB")
            w, h = img.size
            scale = max(1, size // 3)
            img = img.resize((w * scale, h * scale), Image.NEAREST)
            return img
        except Exception as e:
            print(f"treepoem error: {e}")

    # Fallback — QR код если treepoem недоступен
    return _qr_fallback(kiz, size)


def _qr_fallback(kiz: str, size: int = 10) -> Image.Image:
    """Fallback: QR код если DataMatrix недоступен"""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=size,
            border=1,
        )
        qr.add_data(kiz)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        return img.convert("RGB")
    except Exception:
        img = Image.new("RGB", (size * 20, size * 20), "white")
        return img


def image_to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    """PIL Image → bytes"""
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def image_to_base64(img: Image.Image) -> str:
    """PIL Image → base64"""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
