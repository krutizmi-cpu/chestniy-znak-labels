def validate_kiz(kiz: str) -> dict:
    """
    Валидация кода маркировки (КИЗ) Честного знака.
    Возвращает словарь с результатами проверки.
    """
    kiz = kiz.strip()

    result = {
        "raw": kiz,
        "is_valid": False,
        "has_gtin": False,
        "has_serial": False,
        "has_crypto_tail": False,
        "gtin": None,
        "serial": None,
        "warning": None,
        "error": None,
        "length": len(kiz),
    }

    if not kiz:
        result["error"] = "Пустой КИЗ"
        return result

    # Проверка GTIN (начинается с 01 + 14 цифр)
    if kiz.startswith("01") and len(kiz) >= 16:
        gtin = kiz[2:16]
        if gtin.isdigit():
            result["has_gtin"] = True
            result["gtin"] = gtin

    # Проверка серийного номера (блок 21)
    if len(kiz) > 16:
        result["has_serial"] = True
        try:
            if "\x1d" in kiz:
                parts = kiz.split("\x1d")
                for p in parts:
                    if p.startswith("21"):
                        result["serial"] = p[2:]
            else:
                result["serial"] = kiz[18:]
        except Exception:
            pass

    # Проверка криптохвоста (блок 92)
    result["has_crypto_tail"] = "92" in kiz and len(kiz) > 50

    # Итоговая валидность
    result["is_valid"] = result["has_gtin"]

    # Предупреждения
    if result["is_valid"] and not result["has_crypto_tail"]:
        result["warning"] = (
            "Криптохвост (блок 92) отсутствует. "
            "Код подходит для печати и внутреннего учёта, "
            "но верификация через приложение Честный знак может не пройти. "
            "Для полной верификации скачайте полный КИЗ из ЛК Честного знака."
        )

    if not result["is_valid"]:
        result["error"] = "КИЗ не соответствует формату Честного знака (не найден GTIN)"

    return result


def validate_batch(kiz_list: list) -> list:
    """Валидация списка КИЗ"""
    return [validate_kiz(k) for k in kiz_list]


def clean_kiz(kiz: str) -> str:
    """Очистка КИЗ от лишних пробелов и переносов"""
    return kiz.strip().replace("\n", "").replace("\r", "")
