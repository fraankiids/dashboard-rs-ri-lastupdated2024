"""
Dashboard Rumah Sakit Indonesia
================================
Dashboard interaktif berbasis Streamlit untuk data rumah sakit se-Indonesia.

Fitur:
- Peta choropleth nasional (klik provinsi -> filter otomatis ke provinsi itu)
- Kartu KPI (total RS, total tempat tidur, total tenaga kerja, dst)
- Rekap RS per Kelas / per Kepemilikan / per Jenis (donut & bar chart)
- Daftar rumah sakit dengan filter & pencarian
- Klik satu baris RS pada tabel -> profil lengkap RS tersebut

Jalankan dengan:
    streamlit run app.py

Data: Hospital_Indonesia_datasets.csv harus berada di folder yang sama dengan file ini.
"""

import copy
import json

import folium
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from branca.colormap import linear
from streamlit_folium import st_folium

# --------------------------------------------------------------------------------
# KONFIGURASI HALAMAN
# --------------------------------------------------------------------------------
st.set_page_config(
    page_title="Dashboard Rumah Sakit Indonesia",
    page_icon="🏥",
    layout="wide",
)

DATA_PATH = "Hospital_Indonesia_datasets.csv"

# GeoJSON batas provinsi (38 provinsi, sudah termasuk pemekaran Papua)
GEOJSON_URL = (
    "https://raw.githubusercontent.com/denyherianto/"
    "indonesia-geojson-topojson-maps-with-38-provinces/main/"
    "GeoJSON/indonesia-38-provinces.geojson"
)

# Nama provinsi di dataset kadang beda penulisan dengan nama provinsi di GeoJSON.
# key = nama di data CSV, value = nama di GeoJSON
DATA_TO_GEO_NAME = {
    "Yogyakarta": "Daerah Istimewa Yogyakarta",
}
GEO_TO_DATA_NAME = {v: k for k, v in DATA_TO_GEO_NAME.items()}

KELAS_VALID = {"A", "B", "C", "D", "D PRATAMA"}
KEPEMILIKAN_VALID = {
    "SWASTA/LAINNYA", "Pemkab", "Perusahaan", "Organisasi Sosial", "Pemprop",
    "Pemkot", "Organisasi Islam", "TNI AD", "Perorangan", "POLRI",
    "Organisasi Katholik", "Kementerian Lain", "Kemkes", "BUMN",
    "Organisasi Protestan", "TNI AL", "TNI AU", "Organisasi Hindu",
    "Organisasi Budha",
}


# --------------------------------------------------------------------------------
# LOAD & BERSIHKAN DATA
# --------------------------------------------------------------------------------
@st.cache_data(show_spinner="Memuat data rumah sakit...")
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";")

    # rapikan spasi berlebih di kolom teks
    text_cols = df.select_dtypes(include=["object", "str"]).columns
    for c in text_cols:
        df[c] = df[c].astype(str).str.strip()

    # beberapa baris sumber punya nilai yang meleset dari kategori resmi
    # (kesalahan input pada data mentah) -> kelompokkan sebagai "Lainnya/Tidak Diketahui"
    df["kelas"] = df["kelas"].where(df["kelas"].isin(KELAS_VALID), "Lainnya/Tidak Diketahui")
    df["kepemilikan"] = df["kepemilikan"].where(
        df["kepemilikan"].isin(KEPEMILIKAN_VALID), "Lainnya/Tidak Diketahui"
    )
    df["jenis"] = df["jenis"].where(
        df["jenis"].str.startswith("Rumah Sakit", na=False), "Lainnya/Tidak Diketahui"
    )

    for c in ["total_tempat_tidur", "total_layanan", "total_tenaga_kerja"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    df["propinsi_geo"] = df["propinsi"].replace(DATA_TO_GEO_NAME)
    return df


@st.cache_data(show_spinner="Memuat batas wilayah provinsi...")
def load_geojson(url: str):
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


df_all = load_data(DATA_PATH)
geojson_data = load_geojson(GEOJSON_URL)


# --------------------------------------------------------------------------------
# STATE
# --------------------------------------------------------------------------------
if "selected_province" not in st.session_state:
    st.session_state.selected_province = None
if "selected_hospital_id" not in st.session_state:
    st.session_state.selected_hospital_id = None


def reset_province():
    st.session_state.selected_province = None
    st.session_state.selected_hospital_id = None


def select_hospital(hid):
    st.session_state.selected_hospital_id = hid


# --------------------------------------------------------------------------------
# HEADER
# --------------------------------------------------------------------------------
st.title("🏥 Dashboard Rumah Sakit Indonesia")
st.caption(
    "Data profil rumah sakit se-Indonesia. Klik area provinsi pada peta untuk fokus ke "
    "data provinsi tersebut, lalu klik salah satu baris pada tabel untuk melihat profil "
    "lengkap rumah sakit."
)

# --------------------------------------------------------------------------------
# SCOPE (nasional atau 1 provinsi) berdasarkan klik peta
# --------------------------------------------------------------------------------
scope = st.session_state.selected_province
df_scope = df_all if scope is None else df_all[df_all["propinsi"] == scope]

top_l, top_r = st.columns([5, 1])
with top_l:
    if scope:
        st.markdown(f"### 📍 Menampilkan data provinsi: **{scope}**")
    else:
        st.markdown("### 🇮🇩 Menampilkan data: **Nasional**")
with top_r:
    if scope:
        st.button("⟲ Reset ke Nasional", on_click=reset_province, width="stretch")

# --------------------------------------------------------------------------------
# KPI CARDS
# --------------------------------------------------------------------------------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Rumah Sakit", f"{len(df_scope):,}".replace(",", "."))
k2.metric("Total Tempat Tidur", f"{df_scope['total_tempat_tidur'].sum():,}".replace(",", "."))
k3.metric("Total Tenaga Kerja", f"{df_scope['total_tenaga_kerja'].sum():,}".replace(",", "."))
pemilik_top = (
    df_scope["kepemilikan"].mode().iloc[0] if len(df_scope) else "-"
)
k4.metric("Kepemilikan Terbanyak", pemilik_top)

st.divider()

# --------------------------------------------------------------------------------
# PETA (kiri) + DONUT KELAS (kanan)
# --------------------------------------------------------------------------------
col_map, col_donut = st.columns([2, 1])

with col_map:
    st.subheader("Peta Sebaran Rumah Sakit")
    metric_label = st.selectbox(
        "Tampilan peta berdasarkan:",
        ["Jumlah RS", "Total Tempat Tidur", "Total Tenaga Kerja"],
        key="map_metric",
    )
    metric_col = {
        "Jumlah RS": None,  # None -> pakai count
        "Total Tempat Tidur": "total_tempat_tidur",
        "Total Tenaga Kerja": "total_tenaga_kerja",
    }[metric_label]

    if metric_col is None:
        prov_values = df_all.groupby("propinsi_geo").size()
    else:
        prov_values = df_all.groupby("propinsi_geo")[metric_col].sum()

    if geojson_data is not None:
        vmin, vmax = float(prov_values.min()), float(prov_values.max())
        colormap = linear.YlOrRd_09.scale(vmin, vmax if vmax > vmin else vmin + 1)
        colormap.caption = metric_label

        geo = copy.deepcopy(geojson_data)
        for feat in geo["features"]:
            prov_geo_name = feat["properties"].get("PROVINSI", "")
            val = prov_values.get(prov_geo_name, 0)
            feat["properties"]["nilai"] = int(val)
            feat["properties"]["label_nilai"] = f"{int(val):,}".replace(",", ".")

        def style_function(feature):
            prov_geo_name = feature["properties"].get("PROVINSI", "")
            data_name = GEO_TO_DATA_NAME.get(prov_geo_name, prov_geo_name)
            is_selected = scope is not None and data_name == scope
            val = feature["properties"]["nilai"]
            return {
                "fillColor": colormap(val),
                "color": "#1f2937" if is_selected else "#4b5563",
                "weight": 3 if is_selected else 1,
                "fillOpacity": 0.9 if is_selected else 0.7,
            }

        def highlight_function(_feature):
            return {"weight": 3, "color": "#111827", "fillOpacity": 0.9}

        m = folium.Map(location=[-2.3, 118.0], zoom_start=4.4, tiles="OpenStreetMap")
        gj = folium.GeoJson(
            geo,
            style_function=style_function,
            highlight_function=highlight_function,
            tooltip=folium.GeoJsonTooltip(
                fields=["PROVINSI", "label_nilai"],
                aliases=["Provinsi:", f"{metric_label}:"],
                sticky=True,
            ),
        )
        gj.add_to(m)
        colormap.add_to(m)

        map_event = st_folium(
            m,
            width=None,
            height=520,
            returned_objects=["last_active_drawing"],
            key="rs_map",
        )

        clicked = map_event.get("last_active_drawing") if map_event else None
        if clicked:
            clicked_geo_name = clicked["properties"].get("PROVINSI")
            clicked_data_name = GEO_TO_DATA_NAME.get(clicked_geo_name, clicked_geo_name)
            if clicked_data_name and clicked_data_name != st.session_state.selected_province:
                st.session_state.selected_province = clicked_data_name
                st.session_state.selected_hospital_id = None
                st.rerun()

        st.caption("💡 Klik salah satu provinsi pada peta untuk memfilter seluruh dashboard.")
    else:
        st.warning(
            "Peta tidak dapat dimuat (tidak ada koneksi internet ke sumber GeoJSON). "
            "Menampilkan alternatif berupa grafik batang per provinsi."
        )
        fallback = prov_values.sort_values(ascending=False).reset_index()
        fallback.columns = ["Provinsi", metric_label]
        fig_fb = px.bar(fallback, x=metric_label, y="Provinsi", orientation="h", height=520)
        fig_fb.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_fb, width="stretch")

with col_donut:
    st.subheader("Rekap RS per Kelas")
    kelas_count = df_scope["kelas"].value_counts().reset_index()
    kelas_count.columns = ["Kelas", "Jumlah"]
    if len(kelas_count):
        fig_kelas = px.pie(kelas_count, names="Kelas", values="Jumlah", hole=0.55)
        fig_kelas.update_layout(
            annotations=[dict(text=f"{len(df_scope):,}".replace(",", ".") + "<br>Total RS",
                               x=0.5, y=0.5, font_size=16, showarrow=False)],
            showlegend=True,
            height=460,
        )
        st.plotly_chart(fig_kelas, width="stretch")
    else:
        st.info("Tidak ada data untuk ditampilkan.")

st.divider()

# --------------------------------------------------------------------------------
# BAR CHART: KEPEMILIKAN & JENIS
# --------------------------------------------------------------------------------
col_pemilik, col_jenis = st.columns(2)

with col_pemilik:
    st.subheader("Rekap RS per Kepemilikan")
    pemilik_count = (
        df_scope["kepemilikan"].value_counts().reset_index().head(12)
    )
    pemilik_count.columns = ["Kepemilikan", "Jumlah"]
    if len(pemilik_count):
        fig_p = px.bar(
            pemilik_count.sort_values("Jumlah"),
            x="Jumlah", y="Kepemilikan", orientation="h", height=420,
            text="Jumlah",
        )
        fig_p.update_traces(textposition="outside")
        st.plotly_chart(fig_p, width="stretch")
    else:
        st.info("Tidak ada data untuk ditampilkan.")

with col_jenis:
    st.subheader("Rekap RS per Jenis")
    jenis_count = df_scope["jenis"].value_counts().reset_index().head(12)
    jenis_count.columns = ["Jenis", "Jumlah"]
    if len(jenis_count):
        fig_j = px.bar(
            jenis_count.sort_values("Jumlah"),
            x="Jumlah", y="Jenis", orientation="h", height=420,
            text="Jumlah",
        )
        fig_j.update_traces(textposition="outside")
        st.plotly_chart(fig_j, width="stretch")
    else:
        st.info("Tidak ada data untuk ditampilkan.")

st.divider()

# --------------------------------------------------------------------------------
# DAFTAR RUMAH SAKIT (filter + tabel + klik baris untuk detail)
# --------------------------------------------------------------------------------
st.subheader(f"📋 Daftar Rumah Sakit ({'Nasional' if not scope else scope})")

f1, f2, f3, f4 = st.columns([1, 1, 1, 2])
with f1:
    f_kelas = st.multiselect("Filter kelas", sorted(df_scope["kelas"].unique()))
with f2:
    f_jenis = st.multiselect("Filter jenis", sorted(df_scope["jenis"].unique()))
with f3:
    f_pemilik = st.multiselect("Filter kepemilikan", sorted(df_scope["kepemilikan"].unique()))
with f4:
    q = st.text_input("Cari nama RS / kabupaten-kota", "")

df_table = df_scope.copy()
if f_kelas:
    df_table = df_table[df_table["kelas"].isin(f_kelas)]
if f_jenis:
    df_table = df_table[df_table["jenis"].isin(f_jenis)]
if f_pemilik:
    df_table = df_table[df_table["kepemilikan"].isin(f_pemilik)]
if q:
    ql = q.lower()
    df_table = df_table[
        df_table["nama"].str.lower().str.contains(ql)
        | df_table["kab"].str.lower().str.contains(ql)
    ]

display_cols = {
    "nama": "Nama RS",
    "kab": "Kab/Kota",
    "kelas": "Kelas",
    "jenis": "Jenis",
    "kepemilikan": "Kepemilikan",
    "total_tempat_tidur": "Tempat Tidur",
    "total_tenaga_kerja": "Tenaga Kerja",
}
df_display = df_table[list(display_cols.keys())].rename(columns=display_cols).reset_index(drop=True)

st.caption(f"Menampilkan {len(df_display):,} rumah sakit. Klik salah satu baris untuk melihat profil lengkapnya."
           .replace(",", "."))

try:
    # Fitur klik-baris membutuhkan streamlit >= 1.35
    event = st.dataframe(
        df_display,
        width="stretch",
        hide_index=True,
        height=380,
        on_select="rerun",
        selection_mode="single-row",
        key="rs_table",
    )
    if event and event.selection and event.selection.rows:
        row_pos = event.selection.rows[0]
        chosen_id = df_table.iloc[row_pos]["id"]
        if chosen_id != st.session_state.selected_hospital_id:
            st.session_state.selected_hospital_id = chosen_id
            st.rerun()
except TypeError:
    # fallback untuk versi streamlit lama tanpa dukungan on_select
    st.dataframe(df_display, width="stretch", hide_index=True, height=380)
    st.info("Update Streamlit ke versi >= 1.35 agar bisa klik baris langsung. "
            "Sementara itu, pilih RS secara manual di bawah ini:")

st.markdown("**Atau cari & pilih RS secara manual:**")
if len(df_table):
    options = df_table.set_index("id")["nama"].to_dict()
    default_idx = 0
    ids_list = list(options.keys())
    if st.session_state.selected_hospital_id in ids_list:
        default_idx = ids_list.index(st.session_state.selected_hospital_id)
    picked = st.selectbox(
        "Pilih rumah sakit",
        options=ids_list,
        format_func=lambda i: options[i],
        index=default_idx,
        label_visibility="collapsed",
    )
    if picked != st.session_state.selected_hospital_id:
        st.session_state.selected_hospital_id = picked

st.divider()

# --------------------------------------------------------------------------------
# PROFIL RUMAH SAKIT TERPILIH
# --------------------------------------------------------------------------------
st.subheader("🏨 Profil Rumah Sakit")

sel_id = st.session_state.selected_hospital_id
if sel_id is not None and (df_all["id"] == sel_id).any():
    rs = df_all[df_all["id"] == sel_id].iloc[0]

    prof_l, prof_r = st.columns([1, 2])
    with prof_l:
        st.markdown(f"### {rs['nama']}")
        st.markdown(f"**Alamat:** {rs['alamat']}")
        st.markdown(f"**Kab/Kota:** {rs['kab']}, {rs['propinsi']}")
        st.markdown(f"**Jenis:** {rs['jenis']}")
        st.markdown(f"**Kelas:** {rs['kelas']}")
        st.markdown(f"**Kepemilikan:** {rs['kepemilikan']}")
        st.markdown(f"**Status BLU:** {rs['status_blu']}")

    with prof_r:
        m1, m2, m3 = st.columns(3)
        m1.metric("Tempat Tidur", f"{int(rs['total_tempat_tidur']):,}".replace(",", "."))
        m2.metric("Layanan", f"{int(rs['total_layanan']):,}".replace(",", "."))
        m3.metric("Tenaga Kerja", f"{int(rs['total_tenaga_kerja']):,}".replace(",", "."))
        st.caption(
            "Catatan: dataset ini hanya memuat angka total per rumah sakit "
            "(bukan rincian per kelas kamar / jenis layanan / jenis tenaga kerja). "
            "Jika kamu punya data rinciannya, tab tambahan bisa ditambahkan di sini."
        )
else:
    st.info("Pilih salah satu rumah sakit di atas untuk melihat profil lengkapnya.")
