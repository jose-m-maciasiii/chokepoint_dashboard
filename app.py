from __future__ import annotations

import json
import os
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium


APP_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
DATA_DIR = APP_DIR / "data"

CSIS_COLORS = {
    "blue": "#0054a4",
    "cyan": "#3DD5ff",
    "green": "#44C07B",
    "red": "#E53E3A",
    "yellow": "#FFC728",
    "purple": "#7D4391",
    "taupe": "#8B7B5A",
}


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
            countries_500km=lambda df: df["countries_500km"]
            .astype(str)
            .str.replace("|", ", ", regex=False),
            countries_1000km=lambda df: df["countries_1000km"]
            .astype(str)
            .str.replace("|", ", ", regex=False),
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
        return (15.0, 20.0, 2.0)

    lons = [feature["geometry"]["coordinates"][0] for feature in features]
    lats = [feature["geometry"]["coordinates"][1] for feature in features]
    zoom = 2.0 if selected_port == "All chokepoints" else 4.0
    return (sum(lats) / len(lats), sum(lons) / len(lons), zoom)


def basemap_config() -> tuple[str | None, str]:
    return (
        "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        "CartoDB DarkMatter",
    )


def summary_html(props: dict) -> str:
    return f"""
    <b>{props.get('portname', '')}</b><br/>
    Port ID: {props.get('portid', '')}<hr/>
    <b>500 km count:</b> {props.get('n_countries_500km', '')}<br/>
    <b>500 km countries:</b> {props.get('countries_500km', '')}<br/>
    <b>1000 km count:</b> {props.get('n_countries_1000km', '')}<br/>
    <b>1000 km countries:</b> {props.get('countries_1000km', '')}<br/>
    <b>Closest country:</b> {props.get('closest_country', '')}<br/>
    <b>Closest distance (km):</b> {props.get('closest_distance_km', '')}
    """


def build_map(
    maritime_routes_geojson: dict,
    selected_countries_geojson: dict,
    selected_buffers_geojson: dict,
    selected_points_geojson: dict,
    selected_port: str,
    distance_option: int,
) -> folium.Map:
    center_lat, center_lon, zoom = map_center(selected_points_geojson, selected_port)
    tile_url, _ = basemap_config()
    highlight_fill = CSIS_COLORS["blue"]
    point_fill = CSIS_COLORS["yellow"]
    buffer_fill = CSIS_COLORS["red"]

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom,
        tiles=None,
        control_scale=True,
    )

    if tile_url:
        folium.TileLayer(
            tiles=tile_url,
            attr=(
                '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors '
                '&copy; <a href="https://carto.com/attributions">CARTO</a>'
            ),
            subdomains="abcd",
            max_zoom=20,
            name=basemap_config()[1],
            overlay=False,
            control=False,
        ).add_to(m)

    folium.GeoJson(
        maritime_routes_geojson,
        name="Maritime routes",
        style_function=lambda _: {
            "color": CSIS_COLORS["cyan"],
            "weight": 0.9,
            "opacity": 0.35,
        },
        smooth_factor=1.0,
    ).add_to(m)

    folium.GeoJson(
        selected_countries_geojson,
        name=f"Countries within {distance_option} km",
        style_function=lambda _: {
            "fillColor": highlight_fill,
            "color": CSIS_COLORS["cyan"],
            "weight": 1,
            "fillOpacity": 0.38,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["country_std", "iso3"],
            aliases=["Country", "ISO3"],
            sticky=False,
        ),
    ).add_to(m)

    folium.GeoJson(
        selected_buffers_geojson,
        name=f"Buffers {distance_option} km",
        style_function=lambda _: {
            "fillColor": buffer_fill,
            "color": buffer_fill,
            "weight": 2.5,
            "fillOpacity": 0.08,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=[
                "portname",
                "n_countries_500km",
                "countries_500km",
                "n_countries_1000km",
                "countries_1000km",
                "closest_country",
                "closest_distance_km",
            ],
            aliases=[
                "Chokepoint",
                "500 km count",
                "500 km countries",
                "1000 km count",
                "1000 km countries",
                "Closest country",
                "Closest distance (km)",
            ],
            sticky=True,
            labels=True,
        ),
    ).add_to(m)

    point_group = folium.FeatureGroup(name="Chokepoints")
    for feature in selected_points_geojson["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        props = feature["properties"]
        folium.CircleMarker(
            location=[lat, lon],
            radius=6,
            color=CSIS_COLORS["blue"],
            weight=2,
            fill=True,
            fill_color=point_fill,
            fill_opacity=0.95,
            tooltip=folium.Tooltip(summary_html(props), sticky=True),
            popup=folium.Popup(summary_html(props), max_width=450),
        ).add_to(point_group)
    point_group.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m


st.set_page_config(page_title="Chokepoint Dashboard", layout="wide")

st.title("Global Chokepoint Analyzer")
st.caption(
    "The global economy relies on freedom of navigation and a rules-based order for economic prosperity. In an age of strategic competition, rivals of the United States have signaled their intent to compete for influence at these intersections. That places the U.S. and its allies and partners under greater pressure to study these regions more closely. This tool was designed by the CSIS Futures Lab at the direction of Romina Bandura from the CSIS Project on Prosperity and Development."
)

summary = load_csv(DATA_DIR / "chokepoint_country_summary.csv")
proximity = load_csv(DATA_DIR / "chokepoint_country_proximity.csv")
chokepoints_geojson = load_geojson(DATA_DIR / "chokepoints.geojson")
countries_geojson = load_geojson(DATA_DIR / "countries_of_interest.geojson")
maritime_routes_geojson = load_geojson(DATA_DIR / "simple_maritime_routes.geojson")
buffers_500_geojson = load_geojson(DATA_DIR / "buffers_500km.geojson")
buffers_1000_geojson = load_geojson(DATA_DIR / "buffers_1000km.geojson")

query_distance = st.query_params.get("distance", "500")
query_port = st.query_params.get("port", "All chokepoints")

port_options = ["All chokepoints"] + sorted(summary["portname"].dropna().unique().tolist())
if query_port not in port_options:
    query_port = "All chokepoints"

top_cols = st.columns([0.85, 2.75])
control_card = top_cols[0].container(border=True, height="stretch")
map_card = top_cols[1].container(border=True)
_, basemap_label = basemap_config()

with control_card:
    st.subheader("Select A Chokepoint")
    selected_port = st.selectbox(
        "Chokepoint",
        options=port_options,
        index=port_options.index(query_port),
    )
    distance_option = st.pills(
        "Distance from Chokepoint Center",
        options=[500, 1000],
        default=int(query_distance) if query_distance in {"500", "1000"} else 500,
    )


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

dashboard_map = build_map(
    maritime_routes_geojson=maritime_routes_geojson,
    selected_countries_geojson=selected_countries_geojson,
    selected_buffers_geojson=selected_buffers_geojson,
    selected_points_geojson=selected_points_geojson,
    selected_port=selected_port,
    distance_option=distance_option,
)

with control_card:
    st.write("")
    st.write(f"Highlighted countries: within `{accent_label}` of the selected chokepoint set.")
    st.write("Yellow points mark chokepoint locations. Red buffer polygons are shown as transparent overlays.")
    st.write("Light blue maritime routes show major shipping lanes, with emphasis on where traffic converges near chokepoints.")
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
        st.write("Countries in range")
        st.write(row[list_column] if pd.notna(row[list_column]) else "None")

with map_card:
    # st.subheader("Map")
    st_folium(
        dashboard_map,
        height=700,
        width=None,
        use_container_width=True,
        returned_objects=[],
    )

table_card = st.container(border=True)
with table_card:
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
