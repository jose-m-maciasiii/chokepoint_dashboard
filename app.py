from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from maplibre import Map, MapOptions
from maplibre.controls import NavigationControl
from maplibre.streamlit import st_maplibre


APP_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
DATA_DIR = APP_DIR / "data"


@st.cache_data
def load_geojson(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def feature_collection_subset(geojson: dict, predicate) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            feature for feature in geojson["features"] if predicate(feature)
        ],
    }


def attach_summary_properties(geojson: dict, summary_df: pd.DataFrame) -> dict:
    summary_lookup = (
        summary_df.fillna("")
        .assign(
            countries_500km=lambda df: df["countries_500km"].astype(str).str.replace("|", ", ", regex=False),
            countries_1000km=lambda df: df["countries_1000km"].astype(str).str.replace("|", ", ", regex=False),
            closest_distance_km=lambda df: df["closest_distance_km"].map(
                lambda x: round(float(x), 1) if x != "" else ""
            ),
        )
        .set_index("portid")
        .to_dict(orient="index")
    )

    enriched_features = []
    for feature in geojson["features"]:
        props = feature["properties"].copy()
        props.update(summary_lookup.get(props.get("portid"), {}))
        enriched_features.append(
            {
                "type": feature["type"],
                "geometry": feature["geometry"],
                "properties": props,
            }
        )

    return {"type": "FeatureCollection", "features": enriched_features}


def map_center(points_geojson: dict, selected_port: str) -> tuple[float, float, float]:
    features = points_geojson["features"]
    if selected_port != "All chokepoints":
        features = [
            feature
            for feature in features
            if feature["properties"].get("portname") == selected_port
        ]

    if not features:
        return (20.0, 15.0, 1.3)

    lons = [feature["geometry"]["coordinates"][0] for feature in features]
    lats = [feature["geometry"]["coordinates"][1] for feature in features]
    zoom = 2.0 if selected_port == "All chokepoints" else 4.0
    return (sum(lons) / len(lons), sum(lats) / len(lats), zoom)


def build_layers(
    countries_geojson: dict,
    selected_countries_geojson: dict,
    selected_buffers_geojson: dict,
    selected_points_geojson: dict,
    distance_option: int,
) -> list[dict]:
    if distance_option == 500:
        country_fill = [211, 84, 0, 160]
        buffer_color = [211, 84, 0]
    else:
        country_fill = [0, 119, 182, 160]
        buffer_color = [0, 119, 182]

    return [
        {
            "@@type": "GeoJsonLayer",
            "id": "countries-background",
            "data": countries_geojson,
            "stroked": True,
            "filled": True,
            "getFillColor": [235, 238, 241, 80],
            "getLineColor": [180, 180, 180],
            "lineWidthMinPixels": 0.5,
            "pickable": False,
            "autoHighlight": False,
        },
        {
            "@@type": "GeoJsonLayer",
            "id": f"buffers-{distance_option}km",
            "data": selected_buffers_geojson,
            "stroked": True,
            "filled": True,
            "getFillColor": buffer_color + [35],
            "getLineColor": buffer_color,
            "lineWidthMinPixels": 1.2,
            "pickable": True,
            "autoHighlight": True,
        },
        {
            "@@type": "GeoJsonLayer",
            "id": f"countries-highlight-{distance_option}km",
            "data": selected_countries_geojson,
            "stroked": True,
            "filled": True,
            "getFillColor": country_fill,
            "getLineColor": [255, 255, 255],
            "lineWidthMinPixels": 1,
            "pickable": False,
            "autoHighlight": False,
        },
        {
            "@@type": "GeoJsonLayer",
            "id": "chokepoints",
            "data": selected_points_geojson,
            "pointType": "circle",
            "filled": True,
            "stroked": True,
            "getFillColor": [8, 48, 107, 220],
            "getLineColor": [255, 255, 255, 220],
            "getPointRadius": 30000,
            "pointRadiusMinPixels": 5,
            "pickable": True,
            "autoHighlight": True,
        },
    ]


def get_maptiler_key() -> str | None:
    if "MAPTILER_KEY" in st.secrets:
        return st.secrets["MAPTILER_KEY"]
    return os.environ.get("MAPTILER_KEY")


def get_basemap_style() -> tuple[str, str]:
    maptiler_key = get_maptiler_key()
    if maptiler_key:
        return (
            f"https://api.maptiler.com/maps/basic-v2/style.json?key={maptiler_key}",
            "MapTiler basic-v2",
        )
    return (
        "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        "Carto Positron fallback",
    )


st.set_page_config(page_title="Chokepoint Dashboard", layout="wide")

st.title("Chokepoint Buffer Dashboard")
st.caption(
    "Countries of interest intersecting 500 km and 1000 km buffers around chokepoints."
)

summary = load_csv(DATA_DIR / "chokepoint_country_summary.csv")
proximity = load_csv(DATA_DIR / "chokepoint_country_proximity.csv")
chokepoints_geojson = load_geojson(DATA_DIR / "chokepoints.geojson")
countries_geojson = load_geojson(DATA_DIR / "countries_of_interest.geojson")
buffers_500_geojson = load_geojson(DATA_DIR / "buffers_500km.geojson")
buffers_1000_geojson = load_geojson(DATA_DIR / "buffers_1000km.geojson")

query_distance = st.query_params.get("distance", "500")
query_port = st.query_params.get("port", "All chokepoints")

port_options = ["All chokepoints"] + sorted(summary["portname"].dropna().unique().tolist())
if query_port not in port_options:
    query_port = "All chokepoints"

top_cols = st.columns([1, 2.4])

control_card = top_cols[0].container(border=True, height="stretch")
map_card = top_cols[1].container(border=True)
basemap_style, basemap_label = get_basemap_style()

with control_card:
    st.subheader("Controls")
    selected_port = st.selectbox(
        "Chokepoint",
        options=port_options,
        index=port_options.index(query_port),
    )
    distance_option = st.pills(
        "Buffer distance",
        options=[500, 1000],
        default=int(query_distance) if query_distance in {"500", "1000"} else 500,
    )
    st.caption(f"Basemap: {basemap_label}")

st.query_params["distance"] = str(distance_option)
if selected_port == "All chokepoints":
    st.query_params.pop("port", None)
else:
    st.query_params["port"] = selected_port

if distance_option == 500:
    within_column = "within_500km"
    count_column = "n_countries_500km"
    list_column = "countries_500km"
    buffer_geojson = buffers_500_geojson
    accent_label = "500 km"
else:
    within_column = "within_1000km"
    count_column = "n_countries_1000km"
    list_column = "countries_1000km"
    buffer_geojson = buffers_1000_geojson
    accent_label = "1000 km"

if selected_port == "All chokepoints":
    proximity_view = proximity.copy()
    summary_view = summary.copy()
    port_ids = set(summary_view["portid"].dropna().tolist())
else:
    proximity_view = proximity.loc[proximity["portname"] == selected_port].copy()
    summary_view = summary.loc[summary["portname"] == selected_port].copy()
    port_ids = set(summary_view["portid"].dropna().tolist())

highlight_iso3 = set(
    proximity_view.loc[proximity_view[within_column] == True, "iso3"].dropna().tolist()
)

selected_countries_geojson = feature_collection_subset(
    countries_geojson,
    lambda feature: feature["properties"].get("iso3") in highlight_iso3,
)

selected_buffers_geojson = feature_collection_subset(
    buffer_geojson,
    lambda feature: feature["properties"].get("portid") in port_ids,
)

selected_points_geojson = feature_collection_subset(
    chokepoints_geojson,
    lambda feature: (
        True
        if selected_port == "All chokepoints"
        else feature["properties"].get("portid") in port_ids
    ),
)

selected_buffers_geojson = attach_summary_properties(selected_buffers_geojson, summary)
selected_points_geojson = attach_summary_properties(selected_points_geojson, summary)

center_lon, center_lat, zoom = map_center(chokepoints_geojson, selected_port)

map_options = MapOptions(
    style=basemap_style,
    center=(center_lon, center_lat),
    zoom=zoom,
    pitch=0,
    hash=True,
)

map_object = Map(map_options)
map_object.add_control(NavigationControl())
map_object.add_deck_layers(
    build_layers(
        countries_geojson=countries_geojson,
        selected_countries_geojson=selected_countries_geojson,
        selected_buffers_geojson=selected_buffers_geojson,
        selected_points_geojson=selected_points_geojson,
        distance_option=distance_option,
    ),
    tooltip="""
    <b>{{ properties.portname }}</b><br/>
    Port ID: {{ properties.portid }}
    <hr/>
    <b>500 km count:</b> {{ properties.n_countries_500km }}<br/>
    <b>500 km countries:</b> {{ properties.countries_500km }}<br/>
    <b>1000 km count:</b> {{ properties.n_countries_1000km }}<br/>
    <b>1000 km countries:</b> {{ properties.countries_1000km }}<br/>
    <b>Closest country:</b> {{ properties.closest_country }}<br/>
    <b>Closest distance (km):</b> {{ properties.closest_distance_km }}
    """,
)

with control_card:
    st.write("")
    if selected_port == "All chokepoints":
        metric_cols = st.columns(2)
        metric_cols[0].metric("Chokepoints", int(summary_view["portid"].nunique()))
        metric_cols[1].metric(
            f"Mean countries within {distance_option} km",
            round(float(summary_view[count_column].mean()), 1),
        )
        st.metric(
            "Mean closest distance (km)",
            round(float(summary_view["closest_distance_km"].mean()), 1),
        )
    elif not summary_view.empty:
        row = summary_view.iloc[0]
        metric_cols = st.columns(2)
        metric_cols[0].metric(f"Countries within {distance_option} km", int(row[count_column]))
        metric_cols[1].metric("Closest country", row["closest_country"])
        st.metric("Closest distance (km)", round(float(row["closest_distance_km"]), 1))
        st.write("Countries in buffer")
        st.write(row[list_column] if pd.notna(row[list_column]) else "None")

with map_card:
    st.subheader("Map")
    st_maplibre(map_object, height=700)
    st.write(f"Highlighted countries: within `{accent_label}` of the selected chokepoint set.")
    st.write("Blue points are chokepoint locations. Buffer polygons are shown as transparent overlays.")

st.subheader("Chokepoint Table")
if selected_port == "All chokepoints":
    st.dataframe(
        summary_view[
            [
                "portname",
                "n_countries_500km",
                "n_countries_1000km",
                "closest_country",
                "closest_distance_km",
            ]
        ].sort_values("portname"),
        width="stretch",
    )
else:
    st.dataframe(
        proximity_view[
            [
                "country_std",
                "iso3",
                "distance_km",
                "within_500km",
                "within_1000km",
            ]
        ].sort_values("distance_km"),
        width="stretch",
    )
