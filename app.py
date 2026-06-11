from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


BASE_PATH = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_PATH / "output"

ATTENDANCE_TOTAL_PATH = OUTPUT_PATH / "attendance_total"
ATTENDANCE_TIME_PATH = OUTPUT_PATH / "attendance_time"
ML_ATTENDANCE_PATH = OUTPUT_PATH / "ml_attendance"


def load_parquet_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    total_df = pd.read_parquet(ATTENDANCE_TOTAL_PATH)
    time_df = pd.read_parquet(ATTENDANCE_TIME_PATH)
    ml_df = pd.read_parquet(ML_ATTENDANCE_PATH)

    time_df["time_bucket"] = pd.to_datetime(time_df["time_bucket"])
    return total_df, time_df, ml_df


def density_label(value: float) -> str:
    if value >= 120:
        return "Sangat Padat"
    if value >= 75:
        return "Padat"
    if value >= 35:
        return "Sedang"
    return "Sepi"


st.set_page_config(
    page_title="Smart Campus Attendance Analytics",
    page_icon="SC",
    layout="wide",
)

st.title("Smart Campus Attendance Analytics")
st.caption("Attendance Data -> Spark Analytics -> Parquet Storage -> AI Prediction -> Streamlit")
st.sidebar.caption("Observasi simulasi: 06:00-18:00. Jam perkuliahan utama dimulai pukul 09:00.")

try:
    total_df, time_df, ml_df = load_parquet_data()
except FileNotFoundError:
    st.error("Folder Parquet belum ditemukan. Jalankan `python generate_and_process.py` terlebih dahulu.")
    st.stop()

building_options = ["Semua Gedung"] + sorted(time_df["building"].unique().tolist())
selected_building = st.sidebar.selectbox("Filter gedung", building_options)

if selected_building == "Semua Gedung":
    filtered_total_df = total_df.copy()
    filtered_time_df = time_df.copy()
    filtered_ml_df = ml_df.copy()
else:
    filtered_total_df = total_df[total_df["building"] == selected_building]
    filtered_time_df = time_df[time_df["building"] == selected_building]
    filtered_ml_df = ml_df[ml_df["building"] == selected_building]

total_attendance = int(filtered_total_df["total_attendance"].sum())
average_prediction = float(filtered_ml_df["predicted_attendance"].mean())

if selected_building == "Semua Gedung":
    peak_time_df = (
        filtered_time_df.groupby("time_bucket", as_index=False)["attendance_count"].sum()
    )
else:
    peak_time_df = filtered_time_df.copy()

peak_row = peak_time_df.loc[peak_time_df["attendance_count"].idxmax()]
peak_hour = pd.to_datetime(peak_row["time_bucket"]).strftime("%H:%M")

metric_col_1, metric_col_2, metric_col_3 = st.columns(3)
metric_col_1.metric("Total mahasiswa", f"{total_attendance:,}".replace(",", "."))
metric_col_2.metric("Prediksi rata-rata", f"{average_prediction:.0f} mahasiswa")
metric_col_3.metric("Jam tersibuk", peak_hour, density_label(float(peak_row["attendance_count"])))

trend_fig = px.line(
    filtered_time_df,
    x="time_bucket",
    y="attendance_count",
    color="building",
    markers=True,
    title="Tren Kehadiran per 20 Menit",
    labels={
        "time_bucket": "Waktu",
        "attendance_count": "Jumlah Mahasiswa",
        "building": "Gedung",
    },
)
trend_fig.update_layout(hovermode="x unified", legend_title_text="Gedung")
st.plotly_chart(trend_fig, use_container_width=True)

prediction_chart_df = filtered_ml_df.melt(
    id_vars=["building", "hour"],
    value_vars=["attendance_count", "predicted_attendance"],
    var_name="series",
    value_name="value",
)
prediction_chart_df["series"] = prediction_chart_df["series"].replace(
    {
        "attendance_count": "Aktual",
        "predicted_attendance": "Prediksi",
    }
)

prediction_fig = px.bar(
    prediction_chart_df,
    x="hour",
    y="value",
    color="series",
    facet_col="building" if selected_building == "Semua Gedung" else None,
    barmode="group",
    title="Aktual vs Prediksi Kepadatan Kampus Berdasarkan Jam",
    labels={
        "hour": "Jam",
        "value": "Attendance Count per Jam",
        "series": "Data",
        "building": "Gedung",
    },
)
prediction_fig.update_xaxes(dtick=1)
prediction_fig.for_each_annotation(lambda annotation: annotation.update(text=annotation.text.split("=")[-1]))
st.plotly_chart(prediction_fig, use_container_width=True)

table_col_1, table_col_2 = st.columns(2)
with table_col_1:
    st.subheader("Total Mahasiswa per Gedung")
    st.dataframe(filtered_total_df, use_container_width=True, hide_index=True)

with table_col_2:
    st.subheader("Dataset AI dan Hasil Prediksi")
    st.dataframe(filtered_ml_df, use_container_width=True, hide_index=True)

st.subheader("Analisis Jam Sibuk Kampus")
st.write(
    f"Jam tersibuk pada filter saat ini terjadi sekitar pukul {peak_hour} "
    f"dengan kepadatan {density_label(float(peak_row['attendance_count'])).lower()}. "
    "Pola ini merepresentasikan aktivitas kampus dari pagi sampai sore: area fakultas "
    "meningkat menjelang kelas pukul 09:00, perpustakaan cenderung makin ramai setelah "
    "kelas berjalan, dan auditorium mengalami lonjakan ketika ada kegiatan. Informasi ini "
    "dapat dipakai untuk menyiapkan akses masuk, keamanan, dan fasilitas pada rentang waktu paling padat."
)
