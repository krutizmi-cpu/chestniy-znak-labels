import streamlit as st
import pandas as pd
import io
from modules.validator import validate_kiz, clean_kiz
from modules.excel_handler import create_template, read_excel, df_to_excel_bytes
from modules.label_builder import build_label_image, build_pdf, build_pdf_a4, LABEL_FORMATS

st.set_page_config(
    page_title="Генератор этикеток Честный Знак",
    page_icon="🏷️",
    layout="wide"
)

# Стилизация
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #0066CC; color: white; }
    .stDownloadButton>button { width: 100%; border-radius: 5px; height: 3em; }
    .css-1n76uvr { border: 1px solid #ddd; padding: 20px; border-radius: 10px; background: white; }
    </style>
""", unsafe_allow_html=True)

st.title("🏷️ Генератор этикеток Честный Знак")
st.caption("Сервис для создания DataMatrix этикеток из кодов маркировки (КИЗ)")

# Sidebar
with st.sidebar:
    st.header("Настройки")
    label_format = st.selectbox("Формат этикетки", list(LABEL_FORMATS.keys()))
    print_type = st.radio("Тип выгрузки PDF", ["По одной этикетке на страницу", "Сетка на листе A4"])
    
    st.divider()
    st.subheader("Шаблон для Excel")
    template_data = create_template()
    st.download_button(
        label="📥 Скачать шаблон Excel",
        data=template_data,
        file_name="template_markirovka.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Main Tabs
tab1, tab2 = st.tabs(["📊 Массовая загрузка (Excel)", "✍️ Одиночный ввод"])

with tab1:
    uploaded_file = st.file_uploader("Загрузите Excel файл с кодами", type=["xlsx", "xls"])
    
    if uploaded_file:
        try:
            df = read_excel(uploaded_file)
            st.success(f"Загружено кодов: {len(df)}")
            
            # Проверка кодов
            df['check'] = df['kiz'].apply(lambda x: validate_kiz(clean_kiz(x)))
            df['is_valid'] = df['check'].apply(lambda x: x['is_valid'])
            
            invalid_count = len(df[~df['is_valid']])
            if invalid_count > 0:
                st.warning(f"Найдено некорректных кодов: {invalid_count}")
            
            with st.expander("Предпросмотр данных"):
                st.dataframe(df[['kiz', 'article', 'name', 'supplier', 'barcode_val', 'is_valid']], use_container_width=True)

            # Генерация
            if st.button("🚀 Сгенерировать PDF для всех"):
                labels_data = df.to_dict('records')
                
                with st.spinner("Создаём PDF..."):
                    if print_type == "По одной этикетке на страницу":
                        pdf_bytes = build_pdf(labels_data, label_format=label_format)
                    else:
                        pdf_bytes = build_pdf_a4(labels_data, label_format=label_format)
                
                st.download_button(
                    label="💾 Скачать готовый PDF",
                    data=pdf_bytes,
                    file_name=f"labels_{label_format.replace(' ', '_')}.pdf",
                    mime="application/pdf"
                )
                
                # Excel выгрузка результата
                res_xlsx = df_to_excel_bytes(df.drop(columns=['check']))
                st.download_button(
                    label="📈 Скачать отчет Excel",
                    data=res_xlsx,
                    file_name="result_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        except Exception as e:
            st.error(f"Ошибка при обработке файла: {e}")

with tab2:
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Данные товара")
        single_kiz = st.text_input("Код маркировки (КИЗ) *", placeholder="01...21...")
        single_art = st.text_input("Артикул")
        single_name = st.text_input("Название")
        single_supp = st.text_input("Поставщик")
        single_bc = st.text_input("Штрихкод (EAN-13)")
        
        if single_kiz:
            v_res = validate_kiz(clean_kiz(single_kiz))
            if not v_res['is_valid']:
                st.error(v_res['error'])
            elif v_res['warning']:
                st.warning(v_res['warning'])
            else:
                st.success("Код корректен")
    
    with col2:
        st.subheader("Предпросмотр")
        if single_kiz:
            try:
                img = build_label_image(
                    kiz=single_kiz,
                    label_format=label_format,
                    article=single_art,
                    name=single_name,
                    supplier=single_supp,
                    barcode_val=single_bc
                )
                st.image(img, caption="Так будет выглядеть этикетка", use_container_width=True)
                
                # Скачивание одной штуки
                single_pdf = build_pdf([{"kiz": single_kiz, "article": single_art, "name": single_name, "supplier": single_supp, "barcode_val": single_bc}], label_format=label_format)
                st.download_button("💾 Скачать одну этикетку (PDF)", single_pdf, "single_label.pdf", "application/pdf")
            except Exception as e:
                st.error(f"Ошибка генерации: {e}")
        else:
            st.info("Введите КИЗ слева, чтобы увидеть результат")

st.divider()
st.markdown("По правилам Честного знака: если марка повреждена, допускается повторная печать того же КИЗ, если он активен в системе.")
