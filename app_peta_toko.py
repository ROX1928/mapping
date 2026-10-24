"""
Peta + daftar toko Motorola (tampilan ala Google Maps) - Streamlit.

Install : pip install streamlit streamlit-folium folium pandas openpyxl requests
Jalankan: streamlit run app_peta_toko.py
Taruh Daftar_Toko_Motorola_Fixed.xlsx di folder yang sama (atau upload lewat sidebar).

Opsional - peta Google resmi: set environment variable GOOGLE_MAPS_API_KEY
(aktifkan "Map Tiles API" di Google Cloud). Tanpa key, dipakai tile OpenStreetMap.
"""
import os
import urllib.parse
import pandas as pd
import requests
import streamlit as st
import folium
from folium.plugins import Fullscreen, MarkerCluster
from streamlit_folium import st_folium

st.set_page_config(page_title="Peta Toko Motorola", page_icon="📍", layout="wide")
DEFAULT_FILE = "Daftar_Toko_Motorola_Fixed.xlsx"
GOOGLE_BLUE = "#1a73e8"

# kecamatan -> (kode area, nama area, warna)
AREAS = {
    "A1": ("Karawang Kota", "#0b8a7a", ["Karawang Bar."]),
    "A2": ("Karawang Timur", "#e8710a", ["Klari", "Cikampek"]),
    "A3": ("Pantura Cilamaya–Pamanukan", "#8430ce", ["Cilamaya Wetan", "Pamanukan", "Binong"]),
    "A4": ("Purwakarta", "#1a73e8", ["Purwakarta", "Plered"]),
    "A5": ("Subang Kota", "#d93025", ["Subang"]),
}
KEC2AREA = {k: a for a, (_, _, ks) in AREAS.items() for k in ks}


@st.cache_data
def load(src):
    d = pd.read_excel(src)
    d["Kecamatan"] = d["Alamat"].str.extract(r"Kec\. ([^,]+)")
    d["Kode Area"] = d["Kecamatan"].map(KEC2AREA).fillna("-")
    d["Area"] = d["Kode Area"].map(lambda a: AREAS[a][0] if a in AREAS else "Belum diatur")
    d["Warna"] = d["Kode Area"].map(lambda a: AREAS[a][1] if a in AREAS else "#5f6368")
    d["Kecamatan"] = d["Kecamatan"].replace({"Karawang Bar.": "Karawang Barat"})
    d["Navigasi"] = d.apply(lambda r: f"https://www.google.com/maps/dir/?api=1&destination={r.Latitude},{r.Longitude}", axis=1)
    return d.sort_values(["Kode Area", "Nama Toko"]).reset_index(drop=True)


@st.cache_data(ttl=3000)
def google_session(key):
    r = requests.post(f"https://tile.googleapis.com/v1/createSession?key={key}",
                      json={"mapType": "roadmap", "language": "id-ID", "region": "ID"}, timeout=15)
    r.raise_for_status()
    return r.json()["session"]


def google_api_key():
    try:
        return st.secrets.get("GOOGLE_MAPS_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")
    except st.errors.StreamlitSecretNotFoundError:
        return os.getenv("GOOGLE_MAPS_API_KEY")


def pin(color, size=1.0):
    w, h = 30 * size, 40 * size
    svg = (f'<svg width="{w}" height="{h}" viewBox="0 0 30 40" style="filter:drop-shadow(0 2px 2px rgba(0,0,0,.4))">'
           f'<path d="M15 0C6.7 0 0 6.6 0 14.8 0 25 15 40 15 40s15-15 15-25.2C30 6.6 23.3 0 15 0z" fill="{color}"/>'
           f'<circle cx="15" cy="15" r="6" fill="#fff"/></svg>')
    return folium.DivIcon(html=svg, icon_size=(w, h), icon_anchor=(w / 2, h))


def build_map(df, sel, warna_area, cluster):
    m = folium.Map(tiles=None, control_scale=True, zoom_control=True)
    key = google_api_key()
    google_ok = False
    if key:
        try:
            s = google_session(key)
            folium.TileLayer(f"https://tile.googleapis.com/v1/2dtiles/{{z}}/{{x}}/{{y}}?session={s}&key={key}",
                             attr="Map data © Google", name="Google Maps", max_zoom=20).add_to(m)
            google_ok = True
        except Exception as e:
            st.sidebar.warning(f"Google Map Tiles gagal ({str(e)[:60]}), pakai peta CARTO.")
    if not google_ok:
        folium.TileLayer(
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            attr='© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            name="OpenStreetMap",
        ).add_to(m)
    folium.TileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                     attr="Esri", name="Satelit", show=False).add_to(m)
    Fullscreen().add_to(m)
    layer = MarkerCluster().add_to(m) if cluster else m
    for r in df.itertuples():
        warna = r.Warna if warna_area else GOOGLE_BLUE
        besar = r.Index == sel
        popup = (f"<b>{r._1}</b><br>{r.Kecamatan} · {r.Area}<br><small>{r.Alamat}</small><br>"
                 f"<a href='{r.Navigasi}' target='_blank'>Rute di Google Maps</a>")
        folium.Marker((r.Latitude, r.Longitude), icon=pin("#d93025" if besar else warna, 1.3 if besar else 1.0),
                      tooltip=r._1, popup=folium.Popup(popup, max_width=280)).add_to(layer)
    if sel is not None and sel in df.index:
        m.location = [df.Latitude[sel], df.Longitude[sel]]
        m.options["zoom"] = 16
    elif len(df):
        m.fit_bounds([[df.Latitude.min(), df.Longitude.min()], [df.Latitude.max(), df.Longitude.max()]], padding=(40, 40))
    return m


# ---------------- UI ----------------
st.sidebar.header("📍 Peta Toko Motorola")
up = st.sidebar.file_uploader("Upload Excel (opsional)", type=["xlsx"])
src = up if up else (DEFAULT_FILE if os.path.exists(DEFAULT_FILE) else None)
if src is None:
    st.info(f"Taruh **{DEFAULT_FILE}** di folder yang sama dengan aplikasi ini, atau upload lewat sidebar.")
    st.stop()
data = load(src)

area_pilih = st.sidebar.multiselect("Filter area", [f"{k} · {v[0]}" for k, v in AREAS.items()],
                                    default=[f"{k} · {v[0]}" for k, v in AREAS.items()])
cari = st.sidebar.text_input("Cari toko / kecamatan")
warna_area = st.sidebar.toggle("Warna pin per area", value=False, help="Mati = semua pin biru seperti Google Maps")
cluster = st.sidebar.toggle("Gabungkan pin berdekatan", value=False)

kode = [a.split(" · ")[0] for a in area_pilih]
df = data[data["Kode Area"].isin(kode)]
if cari:
    c = cari.lower()
    df = df[df["Nama Toko"].str.lower().str.contains(c) | df["Kecamatan"].str.lower().str.contains(c)]

if "sel" not in st.session_state:
    st.session_state.sel = None
if st.session_state.sel not in df.index:
    st.session_state.sel = None

k1, k2, k3 = st.columns(3)
k1.metric("Jumlah toko", len(df))
k2.metric("Jumlah area", df["Kode Area"].nunique())
k3.metric("Jumlah kecamatan", df["Kecamatan"].nunique())

kiri, kanan = st.columns([2.2, 1])
with kiri:
    st_folium(build_map(df, st.session_state.sel, warna_area, cluster), height=620,
              use_container_width=True, returned_objects=[])
with kanan:
    st.subheader("Daftar toko")
    if st.session_state.sel is not None and st.button("↩︎ Tampilkan semua", use_container_width=True):
        st.session_state.sel = None
        st.rerun()
    box = st.container(height=560)
    with box:
        for kd, g in df.groupby("Kode Area"):
            st.markdown(f"**{kd} · {g['Area'].iloc[0]}** · {len(g)} toko")
            for idx, r in g.iterrows():
                if st.button(f"📍 {r['Nama Toko']}", key=f"b{idx}", use_container_width=True,
                             type="primary" if idx == st.session_state.sel else "secondary"):
                    st.session_state.sel = idx
                    st.rerun()
                st.caption(f"{r['Kecamatan']} · [Navigasi]({r['Navigasi']})")

st.divider()
st.subheader("Tabel lengkap")
tabel = df[["Nama Toko", "Kecamatan", "Kode Area", "Area", "Alamat", "Latitude", "Longitude", "Navigasi"]]
st.dataframe(tabel, use_container_width=True, hide_index=True,
             column_config={"Navigasi": st.column_config.LinkColumn("Navigasi", display_text="Buka"),
                            "Latitude": st.column_config.NumberColumn(format="%.6f"),
                            "Longitude": st.column_config.NumberColumn(format="%.6f")})
st.download_button("⬇️ Download CSV", data=tabel.drop(columns="Navigasi").to_csv(index=False).encode("utf-8-sig"),
                   file_name="daftar_toko_per_area.csv", mime="text/csv")