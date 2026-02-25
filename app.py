import streamlit as st
import pandas as pd
import pydeck as pdk
import asyncio
import time
import sqlite3
import json
from datetime import datetime

# Eigene Module
from api_client import OpenSkyClient
from physics import get_noise_radius
from database import init_db, process_noise_tracking, get_recent_history

# --- INITIALISIERUNG ---
init_db()

def load_credentials():
    with open("credentials.json", "r") as f:
        creds = json.load(f)
    return creds["clientId"], creds["clientSecret"]

@st.cache_resource
def get_client():
    c_id, c_secret = load_credentials()
    return OpenSkyClient(c_id, c_secret)

@st.cache_data(ttl=15)
def get_flight_data():
    client = get_client()
    bbox = ["47.2", "5.8", "55.1", "15.1"]
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(client.fetch_full_data(bbox))

# --- KONFIGURATION ---
LIMIT_LAERM = 55
LIMIT_UNGESUND = 65
GERMANY_CENTER = {"lat": 51.16, "lon": 10.45}

st.set_page_config(page_title="Fluglärm-Monitor Deutschland", layout="wide")

# --- SIDEBAR ---
st.sidebar.header("🛠️ Monitoring & Filter")
live_updates = st.sidebar.toggle("Live-Updates (15s)", value=True)
# Hier definieren wir den Platzhalter SOFORT, damit er immer existiert
sidebar_progress_placeholder = st.sidebar.empty()

st.sidebar.divider()
show_heatmap = st.sidebar.checkbox("🔥 Lärm-Hotspots (Heatmap)", value=False)
show_live_traffic = st.sidebar.checkbox("✈️ Aktuellen Flugverkehr anzeigen", value=True)

st.sidebar.subheader("🚫 Einzelne Flugnummern filtern")
exclude_callsigns = st.sidebar.text_input("Flugnummern (z.B. DLH123, EWG456)")
exclude_list = [x.strip().upper() for x in exclude_callsigns.split(",") if x.strip()]

# --- MAIN UI ---
st.title(f"✈️ Live-Monitor: Deutschland")

with st.spinner('Lade Flugdaten...'):
    flights = get_flight_data()

df = pd.DataFrame(flights) if flights else pd.DataFrame()

# --- DATEN-VERARBEITUNG ---
if not df.empty:
    df = df[df['alt'] > 100].copy()
    if exclude_list and not df.empty:
        df = df[~df['callsign'].str.upper().isin(exclude_list)]

# Spalten-Garantie gegen KeyErrors
if 'noise_radius' not in df.columns: df['noise_radius'] = 0.0
if 'critical_radius' not in df.columns: df['critical_radius'] = 0.0

if not df.empty:
    df['noise_radius'] = df.apply(lambda r: get_noise_radius(r['alt'], LIMIT_LAERM, r['model']), axis=1).fillna(0)
    df['critical_radius'] = df.apply(lambda r: get_noise_radius(r['alt'], LIMIT_UNGESUND, r['model']), axis=1).fillna(0)
    process_noise_tracking(df, "Deutschland", LIMIT_LAERM)

# --- LAYER VORBEREITUNG ---
layers = []

if show_heatmap:
    try:
        conn = sqlite3.connect("noise_history.db")
        hist_data = pd.read_sql_query("SELECT start_lat, start_lon, min_alt FROM noise_history", conn)
        conn.close()
        if not hist_data.empty:
            hist_data['intensity'] = (12000 - hist_data['min_alt']).clip(lower=0)
            layers.append(pdk.Layer(
                "HeatmapLayer", hist_data, get_position=['start_lon', 'start_lat'],
                get_weight='intensity', radius_pixels=40, intensity=1, threshold=0.1
            ))
    except: pass

if show_live_traffic and not df.empty:
    layers.extend([
        pdk.Layer("ScatterplotLayer", df[df['noise_radius'] > 0], get_position=["lon", "lat"],
                  get_radius="noise_radius", get_fill_color=[255, 255, 0, 40]),
        pdk.Layer("ScatterplotLayer", df[df['critical_radius'] > 0], get_position=["lon", "lat"],
                  get_radius="critical_radius", get_fill_color=[255, 0, 0, 80]),
        pdk.Layer("ScatterplotLayer", df, get_position=["lon", "lat"], get_radius=400,
                  get_fill_color="critical_radius > 0 ? [255, 0, 0, 255] : [0, 155, 255, 255]", pickable=True)
    ])

# --- KARTE ---
# Wir nutzen einen stabilen Dark-Mode Style von CartoDB (funktioniert ohne Mapbox-Token)
dark_style = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
light_style = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json'

# Wenn Heatmap an, dann IMMER Darkmode, sonst nach Wahl (hier jetzt Standard Dark)
map_style = dark_style if show_heatmap else dark_style

st.pydeck_chart(pdk.Deck(
    layers=layers,
    initial_view_state=pdk.ViewState(
        latitude=GERMANY_CENTER["lat"],
        longitude=GERMANY_CENTER["lon"],
        zoom=6,
        pitch=0
    ),
    tooltip={"html": "<b>Flug:</b> {callsign}<br/><b>Modell:</b> {model}<br/><b>Höhe:</b> {alt}m"} if show_live_traffic else None,
    map_style=map_style
))

# --- TABELLEN ---
if not df.empty:
    st.subheader("Aktuelle Flüge (gefiltert)")
    st.dataframe(df[['callsign', 'model', 'alt', 'noise_radius']].sort_values("noise_radius", ascending=False),
                 hide_index=True, width='stretch')

st.divider()
if st.checkbox("📊 Letzte Lärm-Ereignisse (Historie)"):
    hist_df = get_recent_history(limit=15)
    if not hist_df.empty:
        hist_df['Zeit von'] = pd.to_datetime(hist_df['start_time']).dt.strftime('%H:%M:%S')
        hist_df['bis'] = pd.to_datetime(hist_df['end_time']).dt.strftime('%H:%M:%S')
        hist_df['Dauer (Sek)'] = hist_df['duration_sec'].round(0).astype(int)
        hist_df['Min. Höhe (m)'] = hist_df['min_alt'].round(0).astype(int)
        display_df = hist_df.rename(columns={'callsign': 'Flugnummer', 'model': 'Modell'})
        st.dataframe(display_df[['Flugnummer', 'Modell', 'Zeit von', 'bis', 'Dauer (Sek)', 'Min. Höhe (m)']],
                     hide_index=True, width='stretch')

# --- REFRESH ---
if live_updates:
    for i in range(15, 0, -1):
        sidebar_progress_placeholder.progress(int((i / 15) * 100), text=f"Update in {i}s")
        time.sleep(1)
    st.rerun()
else:
    sidebar_progress_placeholder.info("Updates pausiert.")