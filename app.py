import streamlit as st
import pandas as pd
import pydeck as pdk
import asyncio
import time
import sqlite3
import json
from datetime import datetime
import database as db

# Eigene Module
from api_client import OpenSkyClient
from physics import get_noise_radius
from database import init_db, process_noise_tracking, get_recent_history

# --- INITIALISIERUNG ---
init_db()

def load_credentials():
    try:
        if "clientId" in st.secrets:
            return st.secrets["clientId"], st.secrets["clientSecret"]
    except Exception:
        pass

    try:
        with open("credentials.json", "r") as f:
            creds = json.load(f)
        return creds["clientId"], creds["clientSecret"]
    except FileNotFoundError:
        st.error("Fehler: 'credentials.json' nicht gefunden!")
        return None, None

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

@st.cache_resource
def load_aircraft_models():
    try:
        with open("aircraft_cache.json", "r") as f:
            return json.load(f)
    except Exception as e:
        return {}

# --- KONFIGURATION ---
LIMIT_LAERM = 55
LIMIT_UNGESUND = 65
GERMANY_CENTER = {"lat": 51.16, "lon": 10.45}

st.set_page_config(page_title="Fluglärm-Monitor Deutschland", layout="wide")

# --- SIDEBAR ---
st.sidebar.header("🛠️ Monitoring & Filter")
live_updates = st.sidebar.toggle("Live-Updates (15s)", value=True)
sidebar_progress_placeholder = st.sidebar.empty()

st.sidebar.divider()
show_heatmap = st.sidebar.checkbox("🔥 Lärm-Hotspots (Heatmap)", value=False)
show_live_traffic = st.sidebar.checkbox("✈️ Aktuellen Flugverkehr anzeigen", value=True)

with st.sidebar:
    with st.expander("ℹ️ Wie werden Lärmzonen berechnet?"):
        st.markdown("""
        **Farblegende:**
        * 🔴 **Extrem (75+ dB)** | 🟠 **Hoch (65-75 dB)**
        * 🟡 **Mittel (55-65 dB)** | 🔵 **Gering (<55 dB)**
        """)

    st.divider()
    # Check Verbindung & History-Status
    if db.get_connection() is not None:
        st.success("✅ Verbunden mit Supabase Cloud")
        history_raw = db.get_recent_history(limit=1)
        # Fix: Prüfung für Liste (Supabase) oder DataFrame (SQLite)
        if history_raw and len(history_raw) > 0:
            last_entry = history_raw[0] if isinstance(history_raw, list) else history_raw.iloc[0]
            st.caption(f"Letzter Sync: {last_entry.get('end_time') if isinstance(last_entry, dict) else last_entry['end_time']}")
    else:
        st.warning("🏠 Modus: Lokale Datenbank (SQLite)")

# --- MAIN UI ---
st.title(f"✈️ Live-Monitor: Deutschland")

with st.spinner('Lade Flugdaten...'):
    flights = get_flight_data()

df = pd.DataFrame(flights) if flights else pd.DataFrame()
model_db = load_aircraft_models()

if not df.empty:
    df['model'] = df['icao24'].apply(lambda x: model_db.get(x.lower(), "Unknown") if x else "Unknown")
    df['noise_radius'] = df.apply(lambda r: get_noise_radius(r['alt'], LIMIT_LAERM, r['model']), axis=1).fillna(0)
    df['critical_radius'] = df.apply(lambda r: get_noise_radius(r['alt'], LIMIT_UNGESUND, r['model']), axis=1).fillna(0)
    # Globales Speichern (unabhängig von der Anzeige)
    process_noise_tracking(df, "Deutschland", LIMIT_LAERM)

# --- LAYER VORBEREITUNG ---
layers = []

if show_heatmap:
    try:
        hist_data_raw = db.get_recent_history(limit=1000)
        if hist_data_raw:
            hist_data = pd.DataFrame(hist_data_raw)
            hist_data['intensity'] = (12000 - hist_data['min_alt']).clip(lower=0)
            layers.append(pdk.Layer(
                "HeatmapLayer", hist_data, get_position=['start_lon', 'start_lat'],
                get_weight='intensity', radius_pixels=40, intensity=1, threshold=0.1
            ))
    except Exception as e:
        st.sidebar.error(f"Heatmap-Fehler: {e}")

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
st.pydeck_chart(pdk.Deck(
    layers=layers,
    initial_view_state=pdk.ViewState(latitude=GERMANY_CENTER["lat"], longitude=GERMANY_CENTER["lon"], zoom=6),
    tooltip={"html": "<b>Flug:</b> {callsign}<br/><b>Modell:</b> {model}<br/><b>Höhe:</b> {alt}m"} if show_live_traffic else None,
    map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
))

# --- TABELLEN ---
if not df.empty:
    st.subheader("Aktuelle Flüge (gefiltert)")
    st.dataframe(df[['callsign', 'model', 'alt', 'noise_radius']].sort_values("noise_radius", ascending=False),
                 hide_index=True, width='stretch')

st.divider()
if st.checkbox("📊 Letzte Lärm-Ereignisse (Historie)"):
    hist_raw = db.get_recent_history(limit=15)
    if hist_raw:
        hist_df = pd.DataFrame(hist_raw)
        hist_df['Zeit von'] = pd.to_datetime(hist_df['start_time']).dt.strftime('%H:%M:%S')
        hist_df['bis'] = pd.to_datetime(hist_df['end_time']).dt.strftime('%H:%M:%S')
        display_df = hist_df.rename(columns={'callsign': 'Flugnummer', 'model': 'Modell'})
        st.dataframe(display_df[['Flugnummer', 'Modell', 'Zeit von', 'bis', 'duration_sec', 'min_alt']],
                     hide_index=True, width='stretch')

# --- REFRESH ---
if live_updates:
    for i in range(15, 0, -1):
        sidebar_progress_placeholder.progress(int((i / 15) * 100), text=f"Update in {i}s")
        time.sleep(1)
    st.rerun()