import io
import pandas as pd

# Колонки шаблона
TEMPLATE_COLUMNS = {
    "kiz": "Код маркировки (КИЗ) *",
    "article": "Артикул",
    "name": "Название товара",
    "supplier": "Поставщик",
    "barcode_val": "Штрихкод",
}


def create_template() -> bytes:
    """
    Создаёт Excel-шаблон для загрузки КИЗ.
    Возвращает bytes файла xlsx.
    """
    sample_data = [
        {
            TEMPLATE_COLUMNS["kiz"]: "010468009156625621ebxoQTHDf+mf)",
            TEMPLATE_COLUMNS["article"]: "ART-001",
            TEMPLATE_COLUMNS["name"]: "Велосипед STELS Avangard 300",
            TEMPLATE_COLUMNS["supplier"]: "ООО Тест",
            TEMPLATE_COLUMNS["barcode_val"]: "4680091566256",
        },
        {
            TEMPLATE_COLUMNS["kiz"]: "",
            TEMPLATE_COLUMNS["article"]: "",
            TEMPLATE_COLUMNS["name"]: "",
            TEMPLATE_COLUMNS["supplier"]: "",
            TEMPLATE_COLUMNS["barcode_val"]: "",
        },
    ]

    df = pd.DataFrame(sample_data)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Этикетки")
        workbook = writer.book
        worksheet = writer.sheets["Этикетки"]

        # Стили
        header_format = workbook.add_format({
            "bold": True,
            "bg_color": "#0066CC",
            "font_color": "#FFFFFF",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
        })
        required_format = workbook.add_format({
            "bold": True,
            "bg_color": "#FFE699",
            "border": 1,
        })
        optional_format = workbook.add_format({
            "bg_color": "#EBF3FF",
            "border": 1,
        })

        # Ширина столбцов
        col_widths = [50, 15, 40, 30, 20]
        for col_idx, (col_name, width) in enumerate(zip(df.columns, col_widths)):
            worksheet.set_column(col_idx, col_idx, width)
            worksheet.write(0, col_idx, col_name, header_format)

        # Строка высоты
        worksheet.set_row(0, 30)

        # Пример данных
        worksheet.write(1, 0, sample_data[0][TEMPLATE_COLUMNS["kiz"]], required_format)
        for col_idx in range(1, 5):
            vals = list(sample_data[0].values())
            worksheet.write(1, col_idx, vals[col_idx], optional_format)

        # Примечание
        note_format = workbook.add_format({"italic": True, "font_color": "#888888"})
        worksheet.write(3, 0, "Примечание: * - обязательное поле. Остальные поля - опциональны.", note_format)

    return buf.getvalue()


def read_excel(file) -> pd.DataFrame:
    """
    Читает Excel-файл с КИЗ и возвращает DataFrame.
    Поддерживает шаблон и произвольный формат.
    """
    df = pd.read_excel(file)

    # Маппинг колонок на внутренние ключи
    col_mapping = {v: k for k, v in TEMPLATE_COLUMNS.items()}

    # Также сопоставляем по английским названиям
    alt_mapping = {
        "kiz": "kiz",
        "article": "article",
        "name": "name",
        "supplier": "supplier",
        "barcode": "barcode_val",
        "barcode_val": "barcode_val",
    }

    # Нормализуем названия колонок
    rename = {}
    for col in df.columns:
        col_lower = str(col).strip().lower()
        if col in col_mapping:
            rename[col] = col_mapping[col]
        elif col_lower in alt_mapping:
            rename[col] = alt_mapping[col_lower]
        elif "код марк" in col_lower or "kiz" in col_lower or "КИЗ" in col:
            rename[col] = "kiz"
        elif "арт" in col_lower:
            rename[col] = "article"
        elif "наз" in col_lower:
            rename[col] = "name"
        elif "пост" in col_lower:
            rename[col] = "supplier"
        elif "штрих" in col_lower or "barcode" in col_lower:
            rename[col] = "barcode_val"

    df = df.rename(columns=rename)

    # Обязательные поля
    if "kiz" not in df.columns:
        raise ValueError("Не найден столбец с кодом маркировки. "
                        "Проверьте формат файла и названия столбцов.")

    # Добавляем опциональные колонки если отсутствуют
    for col in ["article", "name", "supplier", "barcode_val"]:
        if col not in df.columns:
            df[col] = ""

    # Удаляем пустые строки
    df = df[df["kiz"].notna() & (df["kiz"].astype(str).str.strip() != "")]
    df = df.reset_index(drop=True)

    return df


def df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Выгрузка DataFrame в Excel bytes"""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Результат")
        workbook = writer.book
        worksheet = writer.sheets["Результат"]
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#0066CC", "font_color": "#FFF", "border": 1})
        for col_idx, col_name in enumerate(df.columns):
            worksheet.write(0, col_idx, col_name, header_fmt)
            worksheet.set_column(col_idx, col_idx, 20)
    return buf.getvalue()
