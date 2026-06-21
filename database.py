import sqlite3
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

# Falls wir online sind, brauchen wir diesen Connector
try:
    from st_supabase_connection import SupabaseConnection
except ImportError:
    SupabaseConnection = None


def get_connection():
    try:
        # Wir holen uns die Werte manuell aus den Secrets
        url = st.secrets["connections"]["supabase"]["url"]
        key = st.secrets["connections"]["supabase"]["key"]

        # Wir übergeben die URL und den Key direkt an die Verbindung
        return st.connection(
            "supabase",
            type=SupabaseConnection,
            url=url,
            key=key
        )
    except Exception as e:
        # Wenn die Secrets lokal fehlen, nutzen wir SQLite
        return None


def init_db():
    """Initialisiert die lokale SQLite DB (nur für lokale Nutzung)."""
    conn = sqlite3.connect("noise_history.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS active_flights
                 (callsign TEXT PRIMARY KEY, start_time TEXT, model TEXT, 
                  max_db REAL, min_alt REAL, region TEXT,
                  start_lat REAL, start_lon REAL)''')

    c.execute('''CREATE TABLE IF NOT EXISTS noise_history
                 (callsign TEXT, model TEXT, region TEXT, 
                  start_time TEXT, end_time TEXT, duration_sec REAL, 
                  min_alt REAL, 
                  start_lat REAL, start_lon REAL, 
                  end_lat REAL, end_lon REAL)''')
    conn.commit()
    conn.close()


def process_noise_tracking(df, region_name, current_db_threshold):
    supabase = get_connection()

    # ✅ Verwende UTC-Zeit mit timezone
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()

    # Filtere Flugzeuge, die Lärm verursachen
    current_noisy_flights = df[
        (df['noise_radius'] > 0) &
        (df['callsign'].notnull()) &
        (df['alt'] > 50)
        ].copy()
    current_callsigns = set(current_noisy_flights['callsign'].tolist())

    if supabase:
        # --- CLOUD LOGIK (Supabase + Session State) ---
        if 'active_flights' not in st.session_state:
            st.session_state.active_flights = {}

        # 1. Neue Flüge erfassen
        for _, row in current_noisy_flights.iterrows():
            cs = row['callsign']
            if cs not in st.session_state.active_flights:
                st.session_state.active_flights[cs] = {
                    "callsign": cs,
                    "start_time": now_str,  # ISO-String für Session-State
                    "model": row['model'],
                    "min_alt": row['alt'],
                    "region": region_name,
                    "start_lat": row['lat'],
                    "start_lon": row['lon']
                }

        # 2. Beendete Flüge finden und in Historie speichern
        finished_callsigns = []
        for cs, data in st.session_state.active_flights.items():
            if cs not in current_callsigns:
                start_dt = datetime.fromisoformat(data['start_time'])
                duration = (now - start_dt).total_seconds()

                if duration > 5:
                    last_row = df[df['callsign'] == cs]
                    e_lat = last_row['lat'].values[0] if not last_row.empty else data['start_lat']
                    e_lon = last_row['lon'].values[0] if not last_row.empty else data['start_lon']

                    # ✅ Korrigierte history_data mit ISO-Strings für Supabase
                    history_data = {
                        "callsign": cs,
                        "model": data['model'],
                        "region": region_name,
                        "start_time": start_dt.isoformat(),  # ISO-String
                        "end_time": now.isoformat(),  # ISO-String
                        "duration_sec": duration,
                        "min_alt": data['min_alt'],
                        "start_lat": data['start_lat'],
                        "start_lon": data['start_lon'],
                        "end_lat": e_lat,
                        "end_lon": e_lon
                    }
                    try:
                        supabase.table("noise_history").insert(history_data).execute()
                    except Exception as e:
                        st.error(f"Supabase Error: {e}")

                finished_callsigns.append(cs)

        for cs in finished_callsigns:
            del st.session_state.active_flights[cs]

    else:
        # --- LOKALE LOGIK (SQLite) ---
        conn = sqlite3.connect("noise_history.db")
        c = conn.cursor()

        # 1. Neue Events
        c.execute("SELECT callsign FROM active_flights")
        already_active = {row[0] for row in c.fetchall()}

        for _, row in current_noisy_flights.iterrows():
            if row['callsign'] not in already_active:
                try:
                    c.execute("INSERT INTO active_flights VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                              (row['callsign'], now_str, row['model'], current_db_threshold,
                               row['alt'], region_name, row['lat'], row['lon']))
                except sqlite3.IntegrityError:
                    pass

        # 2. Beendete Events
        c.execute("SELECT callsign, start_time, model, min_alt, start_lat, start_lon FROM active_flights")
        active_in_db = c.fetchall()

        for callsign, start_time, model, min_alt, s_lat, s_lon in active_in_db:
            if callsign not in current_callsigns:
                start_dt = datetime.fromisoformat(start_time)
                duration = (now - start_dt).total_seconds()

                if duration > 5:
                    last_row = df[df['callsign'] == callsign]
                    e_lat = last_row['lat'].values[0] if not last_row.empty else s_lat
                    e_lon = last_row['lon'].values[0] if not last_row.empty else s_lon

                    c.execute("INSERT INTO noise_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                              (callsign, model, region_name, start_time, now_str, duration,
                               min_alt, s_lat, s_lon, e_lat, e_lon))

                c.execute("DELETE FROM active_flights WHERE callsign = ?", (callsign,))

        conn.commit()
        conn.close()


def get_recent_history(limit=50):
    """Holt die letzten Einträge aus der Historie - mit Timeout und Fehlerbehandlung"""
    conn = get_connection()

    if conn:
        try:
            # 🔥 Timeout auf 10 Sekunden erhöhen
            return conn.table("noise_history").select("*").order("end_time", desc=True).limit(limit).execute().data
        except Exception as e:
            # Bei Netzwerkfehlern auf SQLite umschalten
            st.warning(f"⚠️ Supabase nicht erreichbar, verwende lokale Datenbank: {str(e)[:100]}")
            return _get_local_history(limit)
    else:
        return _get_local_history(limit)


def _get_local_history(limit=50):
    """Interne Funktion für lokale SQLite-Abfrage"""
    try:
        conn = sqlite3.connect("noise_history.db")
        query = f"SELECT * FROM noise_history ORDER BY end_time DESC LIMIT {limit}"
        df_hist = pd.read_sql_query(query, conn)
        conn.close()
        return df_hist
    except Exception as e:
        st.error(f"Fehler beim Laden der lokalen Historie: {e}")
        return pd.DataFrame()  # Leeres DataFrame zurückgeben