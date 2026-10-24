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
import html
import math
import pandas as pd
import requests
import streamlit as st
import folium
from branca.element import Element
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
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/"


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


def carto_api_key():
    try:
        return st.secrets.get("CARTO_API_KEY") or os.getenv("CARTO_API_KEY")
    except st.errors.StreamlitSecretNotFoundError:
        return os.getenv("CARTO_API_KEY")


def pin(color, size=1.0):
    w, h = 30 * size, 40 * size
    svg = (f'<svg width="{w}" height="{h}" viewBox="0 0 30 40" style="filter:drop-shadow(0 2px 2px rgba(0,0,0,.4))">'
           f'<path d="M15 0C6.7 0 0 6.6 0 14.8 0 25 15 40 15 40s15-15 15-25.2C30 6.6 23.3 0 15 0z" fill="{color}"/>'
           f'<circle cx="15" cy="15" r="6" fill="#fff"/></svg>')
    return folium.DivIcon(html=svg, icon_size=(w, h), icon_anchor=(w / 2, h))


def visit_order(group):
    remaining = list(group.index)
    current = min(remaining, key=lambda i: group.at[i, "Longitude"])
    order = [current]
    remaining.remove(current)
    while remaining:
        lat, lon = group.loc[current, ["Latitude", "Longitude"]]
        current = min(
            remaining,
            key=lambda i: math.hypot(
                (group.at[i, "Latitude"] - lat),
                (group.at[i, "Longitude"] - lon) * math.cos(math.radians(lat)),
            ),
        )
        order.append(current)
        remaining.remove(current)
    return group.loc[order]


@st.cache_data(ttl=3600, show_spinner=False)
def driving_route(points):
    if len(points) < 2:
        return list(points)
    coordinates = ";".join(f"{lon},{lat}" for lat, lon in points)
    response = requests.get(
        OSRM_URL + coordinates,
        params={"overview": "full", "geometries": "geojson", "steps": "false"},
        timeout=20,
    )
    response.raise_for_status()
    routes = response.json().get("routes", [])
    if not routes:
        raise ValueError("Layanan rute tidak mengembalikan jalur.")
    return [(lat, lon) for lon, lat in routes[0]["geometry"]["coordinates"]]


def add_label_collision_layout(m, markers):
    marker_names = ",".join(marker.get_name() for marker in markers)
    m.get_root().header.add_child(Element("""
    <style>
      .store-name-label {
        background: rgba(255, 255, 255, .96);
        border: 1px solid #1a73e8;
        border-radius: 4px;
        box-shadow: 0 1px 4px rgba(0, 0, 0, .25);
        color: #202124;
        font: 12px Arial, sans-serif;
        font-weight: 600;
        padding: 3px 6px;
        white-space: nowrap;
      }
      .store-name-label:before { display: none; }
    </style>
    """))
    script = f"""
    (function() {{
      const map = {m.get_name()};
      const markers = [{marker_names}];
      const candidates = [
        [0, -34], [0, 34], [72, 0], [-72, 0],
        [55, -28], [-55, -28], [55, 28], [-55, 28],
        [0, -58], [0, 58], [108, 0], [-108, 0],
        [88, -42], [-88, -42], [88, 42], [-88, 42]
      ];
      function arrangeLabels() {{
        const zoom = map.getZoom();
        const occupied = [];
        markers.forEach(function(marker) {{
          const tooltip = marker.getTooltip();
          const element = tooltip && tooltip.getElement();
          if (!element) return;
          if (zoom < 10) {{
            element.style.visibility = "hidden";
            return;
          }}
          element.style.visibility = "visible";
          const width = element.offsetWidth;
          const height = element.offsetHeight;
          let selected = candidates[0];
          for (const offset of candidates) {{
            const point = map.latLngToLayerPoint(marker.getLatLng()).add(L.point(offset[0], offset[1]));
            const box = {{
              left: point.x - width / 2 - 4,
              right: point.x + width / 2 + 4,
              top: point.y - height / 2 - 3,
              bottom: point.y + height / 2 + 3
            }};
            const overlaps = occupied.some(function(other) {{
              return box.left < other.right && box.right > other.left &&
                     box.top < other.bottom && box.bottom > other.top;
            }});
            if (!overlaps) {{
              selected = offset;
              occupied.push(box);
              break;
            }}
          }}
          tooltip.options.direction = "center";
          tooltip.options.offset = L.point(selected[0], selected[1]);
          tooltip.setLatLng(marker.getLatLng());
        }});
      }}
      map.whenReady(function() {{
        arrangeLabels();
        map.on("zoomend moveend", arrangeLabels);
      }});
    }})();
    """
    m.get_root().script.add_child(Element(script))


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
            st.sidebar.warning(f"Google Map Tiles gagal ({str(e)[:60]}), pakai basemap cadangan.")
    if not google_ok:
        carto_key = carto_api_key()
        if carto_key:
            tile_url = ("https://basemaps.cartocdn.com/rastertiles/voyager/"
                        "{z}/{x}/{y}{r}.png?key=" + urllib.parse.quote(carto_key, safe=""))
            folium.TileLayer(tile_url, attr="© OpenStreetMap © CARTO",
                             name="CARTO Voyager", subdomains="abcd").add_to(m)
        else:
            folium.TileLayer(
                "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                attr='© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                name="OpenStreetMap",
            ).add_to(m)
    folium.TileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                     attr="Esri", name="Satelit", show=False).add_to(m)
    Fullscreen().add_to(m)
    marker_group = folium.FeatureGroup(name="Titik toko").add_to(m)
    layer = MarkerCluster().add_to(marker_group) if cluster else marker_group
    all_markers = []
    for kd, area_group in df.groupby("Kode Area", sort=True):
        if kd not in AREAS or area_group.empty:
            continue
        area_name, area_color, _ = AREAS[kd]
        center = [area_group["Latitude"].mean(), area_group["Longitude"].mean()]
        max_distance = max(
            6371000 * 2 * math.asin(math.sqrt(
                math.sin(math.radians(row.Latitude - center[0]) / 2) ** 2
                + math.cos(math.radians(center[0])) * math.cos(math.radians(row.Latitude))
                * math.sin(math.radians(row.Longitude - center[1]) / 2) ** 2
            ))
            for row in area_group.itertuples()
        )
        area_layer = folium.FeatureGroup(name=f"Sektor {kd} · {area_name}").add_to(m)
        folium.Circle(
            center, radius=max(500, max_distance + 250), color=area_color,
            weight=2, dash_array="8 6", fill=True, fill_opacity=0.07,
            tooltip=f"Sektor {kd} · {area_name}",
        ).add_to(area_layer)

        ordered = visit_order(area_group)
        if len(ordered) > 1:
            points = tuple(
                (float(row.Latitude), float(row.Longitude))
                for row in ordered.itertuples()
            )
            try:
                route = driving_route(points)
                route_layer = folium.FeatureGroup(name=f"Jalur {kd} · {area_name}").add_to(m)
                folium.PolyLine(
                    route, color=area_color, weight=4, opacity=0.8,
                    tooltip=f"Jalur kunjungan · {kd} {area_name}",
                ).add_to(route_layer)
            except (requests.RequestException, ValueError, KeyError) as exc:
                st.sidebar.warning(f"Jalur {kd} tidak tersedia: {exc}")

    for r in df.itertuples():
        warna = r.Warna if warna_area else GOOGLE_BLUE
        besar = r.Index == sel
        nama_toko = html.escape(str(r._1))
        alamat = html.escape(str(r.Alamat))
        popup = (f"<b>{nama_toko}</b><br>{r.Kecamatan} · {r.Area}<br><small>{alamat}</small><br>"
                 f"<a href='{r.Navigasi}' target='_blank'>Rute di Google Maps</a>")
        marker = folium.Marker(
            (r.Latitude, r.Longitude),
            icon=pin("#d93025" if besar else warna, 1.3 if besar else 1.0),
            tooltip=folium.Tooltip(nama_toko, permanent=True, direction="center",
                                   class_name="store-name-label"),
            popup=folium.Popup(popup, max_width=280),
        ).add_to(layer)
        all_markers.append(marker)
    add_label_collision_layout(m, all_markers)
    folium.LayerControl(collapsed=False).add_to(m)
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
st.sidebar.caption("Lingkaran menandai sektor. Jalur mengikuti urutan kunjungan; nama toko muncul saat zoom dan label otomatis menghindari tumpang tindih.")

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