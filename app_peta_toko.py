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
from branca.element import Element, MacroElement
from folium.plugins import Fullscreen, MarkerCluster
from streamlit_folium import st_folium
from jinja2 import Template
from export_peta import AREAS, KEC2AREA, create_screenshot_archive

st.set_page_config(page_title="Peta Toko Motorola", page_icon="📍", layout="wide")
DEFAULT_FILE = "Daftar_Toko_Motorola_Fixed.xlsx"
GOOGLE_BLUE = "#1a73e8"
NEARBY_STORE_DISTANCE_M = 300
NEARBY_MARKER_COLORS = [
    "#d93025", "#188038", "#f29900", "#8430ce", "#00838f", "#c2185b",
    "#1a73e8", "#7b5e00", "#5f6368", "#b3145a", "#137333", "#e37400",
]

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
           f'<circle cx="15" cy="15" r="8" fill="#fff"/>'
           f'<path d="m9.3 13.5 1.4-3h8.6l1.4 3v1.1c0 .8-.6 1.4-1.4 1.4-.6 0-1-.3-1.3-.8-.3.5-.8.8-1.4.8s-1.1-.3-1.4-.8c-.3.5-.8.8-1.4.8s-1.1-.3-1.4-.8c-.3.5-.7.8-1.3.8-.8 0-1.4-.6-1.4-1.4zM10.7 16.5h8.6v3.8h-8.6zM12.2 17.2h2v3.1h-2z" fill="{color}"/></svg>')
    return folium.DivIcon(html=svg, icon_size=(w, h), icon_anchor=(w / 2, h))


def nearby_marker_colors(df, selected=None):
    positions = {}
    for index, row in df[["Latitude", "Longitude"]].iterrows():
        if pd.notna(row["Latitude"]) and pd.notna(row["Longitude"]):
            positions[index] = (math.radians(row["Latitude"]), row["Longitude"])

    indexes = list(positions)
    neighbors = {index: set() for index in indexes}
    for i, index in enumerate(indexes):
        lat1, lon1 = positions[index]
        for other in indexes[i + 1:]:
            lat2, lon2 = positions[other]
            mean_lat = (lat1 + lat2) / 2
            distance = 6_371_000 * math.hypot(
                lat2 - lat1,
                math.radians(lon2 - lon1) * math.cos(mean_lat),
            )
            if distance <= NEARBY_STORE_DISTANCE_M:
                neighbors[index].add(other)
                neighbors[other].add(index)

    nearby = [index for index, adjacent in neighbors.items() if adjacent]
    order = sorted(
        nearby,
        key=lambda index: (index != selected, -len(neighbors[index]), str(index)),
    )
    colors = {}
    for index in order:
        used = {colors[other] for other in neighbors[index] if other in colors}
        colors[index] = next(
            (color for color in NEARBY_MARKER_COLORS if color not in used),
            NEARBY_MARKER_COLORS[len(colors) % len(NEARBY_MARKER_COLORS)],
        )
    return colors


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
        return list(points), [], []
    coordinates = ";".join(f"{lon},{lat}" for lat, lon in points)
    response = requests.get(
        OSRM_URL + coordinates,
        params={"overview": "full", "geometries": "geojson", "steps": "true"},
        timeout=20,
    )
    response.raise_for_status()
    routes = response.json().get("routes", [])
    if not routes:
        raise ValueError("Layanan rute tidak mengembalikan jalur.")
    route = routes[0]
    legs = route.get("legs", [])
    if len(legs) != len(points) - 1:
        raise ValueError("Data jarak antar toko tidak lengkap dari layanan rute.")
    distances_km = [leg["distance"] / 1000 for leg in legs]
    segment_midpoints = []
    for i, leg in enumerate(legs):
        midpoint_distance = leg["distance"] / 2
        walked_distance = 0
        midpoint = None
        for step in leg.get("steps", []):
            step_distance = step.get("distance", 0)
            coordinates = step.get("geometry", {}).get("coordinates", [])
            if step_distance <= 0 or not coordinates:
                continue
            if walked_distance + step_distance >= midpoint_distance:
                fraction = (midpoint_distance - walked_distance) / step_distance
                midpoint = midpoint_on_geometry(coordinates, fraction)
                break
            walked_distance += step_distance
        if midpoint is None:
            midpoint = (
                (points[i][0] + points[i + 1][0]) / 2,
                (points[i][1] + points[i + 1][1]) / 2,
            )
        segment_midpoints.append(midpoint)
    return (
        [(lat, lon) for lon, lat in route["geometry"]["coordinates"]],
        distances_km,
        segment_midpoints,
    )


def midpoint_on_geometry(coordinates, fraction):
    path = [(float(lon), float(lat)) for lon, lat in coordinates]
    if len(path) < 2:
        lon, lat = path[0]
        return lat, lon

    def segment_length(a, b):
        lat1, lat2 = math.radians(a[1]), math.radians(b[1])
        dlat = lat2 - lat1
        dlon = math.radians(b[0] - a[0])
        h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 12_742_000 * math.asin(min(1, math.sqrt(h)))

    lengths = [segment_length(a, b) for a, b in zip(path, path[1:])]
    target = sum(lengths) * fraction
    travelled = 0
    for a, b, length in zip(path, path[1:], lengths):
        if travelled + length >= target and length:
            part = (target - travelled) / length
            return a[1] + (b[1] - a[1]) * part, a[0] + (b[0] - a[0]) * part
        travelled += length
    lon, lat = path[-1]
    return lat, lon


def distance_label(distance_km):
    if distance_km is None:
        return "Titik awal"
    if not math.isfinite(distance_km):
        return "Jarak tidak tersedia"
    return f"{distance_km:.1f} km"


def add_label_collision_layout(m, label_pairs):
    m.get_root().header.add_child(Element("""
    <style>
      .store-name-icon { background: transparent; border: 0; }
      .store-name-label {
        position: absolute;
        left: 0;
        top: 0;
        display: inline-block;
        width: max-content;
        max-width: 164px;
        background: rgba(255, 255, 255, .96);
        border: 1px solid #1a73e8;
        border-radius: 4px;
        box-shadow: 0 1px 4px rgba(0, 0, 0, .25);
        box-sizing: border-box;
        color: #202124;
        font: 600 11px/1.2 Arial, sans-serif;
        overflow-wrap: anywhere;
        padding: 4px 7px;
      }
      @media (max-width: 600px) {
        .store-name-label {
          font-size: 10px;
          max-width: 124px;
          padding: 3px 5px;
        }
      }
      .route-distance-tooltip {
        background: transparent;
        border: 0;
        box-shadow: none;
        padding: 0;
      }
      .route-distance-tooltip:before { display: none; }
      .route-distance-label {
        background: rgba(255, 255, 255, .96);
        border: 2px solid var(--route-color);
        border-radius: 999px;
        box-shadow: 0 1px 5px rgba(0, 0, 0, .3);
        color: #202124;
        font: 700 12px Arial, sans-serif;
        padding: 4px 8px;
        white-space: nowrap;
      }
    </style>
    """))
    marker_names = ",".join(marker.get_name() for marker, _ in label_pairs)
    label_names = ",".join(label.get_name() for _, label in label_pairs)
    script = f"""
    (function() {{
      const map = {m.get_name()};
      const markers = [{marker_names}];
      const labels = [{label_names}];
      function arrangeLabels() {{
        const zoom = map.getZoom();
        const size = map.getSize();
        const narrow = size.x < 600;
        const occupied = [];
        markers.forEach(function(marker, index) {{
          const label = labels[index];
          const icon = label.getElement();
          const element = icon && icon.querySelector(".store-name-label");
          if (!element) return;
          if (zoom < 9) {{
            icon.style.visibility = "hidden";
            return;
          }}
          icon.style.visibility = "visible";
          const rect = element.getBoundingClientRect();
          const width = rect.width;
          const height = rect.height;
          const markerPoint = map.latLngToContainerPoint(marker.getLatLng());
          let selected = null;
          let selectedBox = null;
          const gap = narrow ? 12 : 16;
          const verticalAdjustments = [0];
          const sides = index % 2 ? ["right", "left"] : ["left", "right"];
          for (const side of sides) {{
            for (const verticalAdjustment of verticalAdjustments) {{
              const left = side === "left" ? markerPoint.x - width - gap : markerPoint.x + gap;
              const top = markerPoint.y - height / 2 + verticalAdjustment;
              const box = {{
                left: left - 3, right: left + width + 3,
                top: top - 3, bottom: top + height + 3
              }};
              const overlaps = occupied.some(function(other) {{
                return box.left < other.right && box.right > other.left &&
                       box.top < other.bottom && box.bottom > other.top;
              }});
              const insideViewport = left >= 2 && left + width <= size.x - 2 &&
                top >= 2 && top + height <= size.y - 2;
              if (!overlaps && insideViewport) {{
                selected = [left, top];
                selectedBox = box;
                break;
              }}
            }}
            if (selected) break;
          }}
          if (!selected) {{
            icon.style.visibility = "hidden";
            return;
          }}
          occupied.push(selectedBox);
          const labelPoint = map.containerPointToLatLng(L.point(selected[0], selected[1]));
          label.setLatLng(labelPoint);
        }});
      }}
      map.whenReady(function() {{
        arrangeLabels();
        map.on("zoomend moveend resize", arrangeLabels);
        setTimeout(arrangeLabels, 100);
      }});
    }})();
    """
    label_layout = MacroElement()
    label_layout._template = Template(
        "{% macro script(this, kwargs) %}" + script + "{% endmacro %}"
    )
    m.add_child(label_layout, name="store_label_layout")


def add_route_distance_label(route_layer, point, distance_km, area_color, from_name, to_name):
    label = folium.Marker(
        point,
        icon=folium.DivIcon(icon_size=(1, 1), icon_anchor=(0, 0), html=""),
        tooltip=folium.Tooltip(
            f'<span class="route-distance-label" style="--route-color:{area_color}">'
            f'{distance_km:.1f} km</span>',
            permanent=True,
            direction="center",
            class_name="route-distance-tooltip",
        ),
        popup=folium.Popup(
            f"<b>{html.escape(from_name)} → {html.escape(to_name)}</b>"
            f"<br>Jarak berkendara: {distance_km:.1f} km",
            max_width=260,
        ),
        interactive=True,
    ).add_to(route_layer)
    return label


def build_map(df, sel, warna_area, cluster):
    m = folium.Map(tiles=None, control_scale=True, zoom_control=True)
    distance_from_previous = {index: None for index in df.index}
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
    label_pairs = []
    label_group = folium.FeatureGroup(name="Nama toko").add_to(m)
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
        if len(ordered):
            distance_from_previous[ordered.index[0]] = None
        for index in ordered.index[1:]:
            distance_from_previous[index] = float("nan")
        if len(ordered) > 1:
            points = tuple(
                (float(row.Latitude), float(row.Longitude))
                for row in ordered.itertuples()
            )
            try:
                route, distances_km, segment_midpoints = driving_route(points)
                for index, distance_km in zip(ordered.index[1:], distances_km):
                    distance_from_previous[index] = distance_km
                route_layer = folium.FeatureGroup(name=f"Jalur {kd} · {area_name}").add_to(m)
                folium.PolyLine(
                    route, color=area_color, weight=4, opacity=0.8,
                    tooltip=(
                        f"Jalur kunjungan · {kd} {area_name} · "
                        f"{sum(distances_km):.1f} km"
                    ),
                ).add_to(route_layer)
                for i, (distance_km, midpoint) in enumerate(
                    zip(distances_km, segment_midpoints)
                ):
                    distance_marker = add_route_distance_label(
                        route_layer,
                        midpoint,
                        distance_km,
                        area_color,
                        str(ordered.iloc[i]["Nama Toko"]),
                        str(ordered.iloc[i + 1]["Nama Toko"]),
                    )

            except (requests.RequestException, ValueError, KeyError) as exc:
                st.sidebar.warning(f"Jalur {kd} tidak tersedia: {exc}")

    nearby_colors = nearby_marker_colors(df, sel)
    for r in df.itertuples():
        warna = nearby_colors.get(r.Index, r.Warna if warna_area else GOOGLE_BLUE)
        besar = r.Index == sel
        if besar:
            warna = "#d93025"
        nama_toko = html.escape(str(r._1))
        alamat = html.escape(str(r.Alamat))
        jarak = distance_from_previous.get(r.Index)
        jarak_html = f"<br>Jarak dari toko sebelumnya: {distance_label(jarak)}"
        popup = (f"<b>{nama_toko}</b><br>{r.Kecamatan} · {r.Area}{jarak_html}"
                 f"<br><small>{alamat}</small><br>"
                 f"<a href='{r.Navigasi}' target='_blank'>Rute di Google Maps</a>")
        marker = folium.Marker(
            (r.Latitude, r.Longitude),
            icon=pin("#d93025" if besar else warna, 1.3 if besar else 1.0),
            popup=folium.Popup(popup, max_width=280),
        ).add_to(layer)
        label = folium.Marker(
            (r.Latitude, r.Longitude),
            icon=folium.DivIcon(
                html=f'<div class="store-name-label">{nama_toko}</div>',
                icon_size=(176, 54),
                icon_anchor=(0, 0),
                class_name="store-name-icon",
            ),
            interactive=False,
            keyboard=False,
            z_index_offset=1000,
        ).add_to(label_group)
        label_pairs.append((marker, label))
    m.store_distances = distance_from_previous
    add_label_collision_layout(m, label_pairs)
    folium.LayerControl(collapsed=True).add_to(m)
    if sel is not None and sel in df.index:
        m.location = [df.Latitude[sel], df.Longitude[sel]]
        m.options["zoom"] = 16
    elif len(df):
        m.fit_bounds([[df.Latitude.min(), df.Longitude.min()], [df.Latitude.max(), df.Longitude.max()]], padding=(40, 40))
    return m


# ---------------- UI ----------------
st.markdown("""
<style>
  .block-container { padding-top: 1.4rem; padding-bottom: 1.5rem; }
  [data-testid="stMetric"] { padding: .35rem .55rem; }
  [data-testid="stMetricLabel"] { font-size: .8rem; }
  [data-testid="stMetricValue"] { font-size: 1.25rem; }
  @media (max-width: 640px) {
    .block-container { padding: .8rem .65rem 1rem; }
    h1 { font-size: 1.45rem !important; }
    h2 { font-size: 1.15rem !important; }
    [data-testid="stHorizontalBlock"] { gap: .35rem; }
    [data-testid="stMetric"] { padding: .15rem .25rem; }
    [data-testid="stMetricLabel"] { font-size: .68rem; }
    [data-testid="stMetricValue"] { font-size: 1rem; }
    iframe[title="streamlit_folium.st_folium"] { height: 58vh !important; min-height: 360px !important; }
    [data-testid="stDataFrame"] { font-size: .8rem; }
  }
</style>
""", unsafe_allow_html=True)
st.title("📍 Peta Toko Motorola")

st.sidebar.header("📍 Peta Toko Motorola")
up = st.sidebar.file_uploader("Upload Excel (opsional)", type=["xlsx"])
src = up if up else (DEFAULT_FILE if os.path.exists(DEFAULT_FILE) else None)
if src is None:
    st.info(f"Taruh **{DEFAULT_FILE}** di folder yang sama dengan aplikasi ini, atau upload lewat sidebar.")
    st.stop()
data = load(src)

with st.expander("🖼️ Screenshot detail per area dan sektor", expanded=False):
    st.caption(
        "Buat peta PNG untuk setiap area dan kecamatan, lengkap dengan nomor toko, "
        "nama, rute jalan, dan jarak berkendara antar toko."
    )
    if st.button("Buat screenshot peta", use_container_width=True):
        try:
            with st.spinner("Menyusun screenshot peta, rute, dan jarak..."):
                screenshot_zip, screenshot_count = create_screenshot_archive(data)
            st.session_state["screenshot_zip"] = screenshot_zip
            st.session_state["screenshot_count"] = screenshot_count
        except (requests.RequestException, ValueError, KeyError) as exc:
            st.error(f"Screenshot peta gagal dibuat: {exc}")
    if "screenshot_zip" in st.session_state:
        st.download_button(
            f"⬇️ Download {st.session_state['screenshot_count']} screenshot (ZIP)",
            data=st.session_state["screenshot_zip"],
            file_name="screenshots_area_dan_sektor.zip",
            mime="application/zip",
            use_container_width=True,
        )

area_pilih = st.sidebar.multiselect("Filter area", [f"{k} · {v[0]}" for k, v in AREAS.items()],
                                    default=[f"{k} · {v[0]}" for k, v in AREAS.items()])
cari = st.sidebar.text_input("Cari toko / kecamatan")
warna_area = st.sidebar.toggle(
    "Warna pin per area",
    value=False,
    help="Toko yang berdekatan selalu dibedakan warnanya; opsi ini mengatur warna toko lainnya.",
)
cluster = st.sidebar.toggle("Gabungkan pin berdekatan", value=False)
st.sidebar.caption(
    "Toko dalam jarak 300 m dibedakan dengan warna pin dan ikon toko. Lingkaran menandai sektor; "
    "jalur mengikuti urutan kunjungan. Nama toko muncul saat zoom dan label menghindari tumpang tindih."
)

kode = [a.split(" · ")[0] for a in area_pilih]
df = data[data["Kode Area"].isin(kode)]
if cari:
    c = cari.lower()
    df = df[df["Nama Toko"].str.lower().str.contains(c) | df["Kecamatan"].str.lower().str.contains(c)]

if "sel" not in st.session_state:
    st.session_state.sel = None
if st.session_state.sel not in df.index:
    st.session_state.sel = None

st.caption(f"{len(df)} toko · {df['Kode Area'].nunique()} sektor · {df['Kecamatan'].nunique()} kecamatan")
map_object = build_map(df, st.session_state.sel, warna_area, cluster)
st_folium(map_object, height=560,
          use_container_width=True, returned_objects=[])

with st.expander(f"Daftar toko ({len(df)})", expanded=False):
    if not df.empty:
        pilihan = [None] + list(df.index)
        selected = st.selectbox(
            "Pilih toko untuk fokus di peta",
            options=pilihan,
            index=pilihan.index(st.session_state.sel) if st.session_state.sel in pilihan else 0,
            format_func=lambda idx: "Semua toko" if idx is None else (
                f"{df.at[idx, 'Nama Toko']} · {df.at[idx, 'Kode Area']} · "
                f"{distance_label(map_object.store_distances[idx])}"
            ),
            label_visibility="collapsed",
        )
        if selected != st.session_state.sel:
            st.session_state.sel = selected
            st.rerun()
        tabel = df[["Nama Toko", "Kode Area", "Kecamatan"]].copy()
        tabel["Jarak dari toko sebelumnya"] = [
            distance_label(map_object.store_distances[idx])
            for idx in tabel.index
        ]
        st.dataframe(
            tabel.reset_index(drop=True), width="stretch", height=min(280, 38 + len(tabel) * 34),
            row_height=30, hide_index=True,
        )
        lengkap = df[["Nama Toko", "Kecamatan", "Kode Area", "Area", "Alamat",
                      "Latitude", "Longitude", "Navigasi"]]
        st.download_button(
            "⬇️ Download daftar toko (CSV)",
            data=lengkap.drop(columns="Navigasi").to_csv(index=False).encode("utf-8-sig"),
            file_name="daftar_toko_per_area.csv", mime="text/csv",
            use_container_width=True,
        )
    else:
        st.info("Tidak ada toko untuk filter yang dipilih.")