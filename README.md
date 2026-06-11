# Smart Campus Attendance Analytics

Project UAS Teknologi Big Data untuk NIM akhir genap: pipeline Attendance Data -> Spark Analytics -> Parquet Storage -> AI Prediction -> Streamlit.

## Struktur

```text
.
|-- app.py
|-- generate_and_process.py
|-- requirements.txt
`-- output/
    |-- attendance_total/
    |-- attendance_time/
    `-- ml_attendance/
```

## Cara Menjalankan

Jalankan dari WSL Ubuntu pada folder project:

```bash
cd /home/mkaspulanwar/uas-tbg-230104040212
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python generate_and_process.py
streamlit run app.py
```

Dashboard akan tersedia di:

```text
http://localhost:8501
```

## Validasi Output

- Spark berhasil dijalankan melalui `generate_and_process.py`.
- File Parquet dibuat pada absolute path folder `output/attendance_total`, `output/attendance_time`, dan `output/ml_attendance`.
- Dashboard Streamlit membaca Parquet secara langsung.
- Grafik dibuat menggunakan Plotly.
- Prediksi menggunakan Linear Regression dari PySpark ML.
- Sidebar filter gedung tersedia pada dashboard.

## Analisis Singkat

Data simulasi dibuat selama 12 jam dari pukul 06:00 sampai 18:00 untuk tiga gedung: Fakultas Sains dan Teknologi, Perpustakaan, dan Auditorium. Jam perkuliahan utama dimulai pukul 09:00. Pola data dibuat realistis: fakultas ramai menjelang kelas dan pergantian aktivitas, perpustakaan meningkat setelah kelas berjalan, sedangkan auditorium memiliki lonjakan saat ada kegiatan. Gedung dan jam dengan total attendance tertinggi dapat diprioritaskan untuk pengaturan akses, keamanan, dan fasilitas saat jam sibuk.
