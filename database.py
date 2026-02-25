import sqlite3
from datetime import datetime
import pandas as pd


def init_db():
    conn = sqlite3.connect("noise_history.db")
    c = conn.cursor()
    # Zwischenspeicher: Merkt sich, wo der Lärm BEGANN
    c.execute('''CREATE TABLE IF NOT EXISTS active_flights
                 (callsign TEXT PRIMARY KEY, start_time TEXT, model TEXT, 
                  max_db REAL, min_alt REAL, region TEXT,
                  start_lat REAL, start_lon REAL)''')

    # Historie: Speichert Start- UND Endpunkt
    c.execute('''CREATE TABLE IF NOT EXISTS noise_history
                 (callsign TEXT, model TEXT, region TEXT, 
                  start_time TEXT, end_time TEXT, duration_sec REAL, 
                  min_alt REAL, 
                  start_lat REAL, start_lon REAL, 
                  end_lat REAL, end_lon REAL)''')
    conn.commit()
    conn.close()


def process_noise_tracking(df, region_name, current_db_threshold):
    conn = sqlite3.connect("noise_history.db")
    c = conn.cursor()
    now = datetime.now()
    now_str = now.isoformat()

    current_noisy_flights = df[
        (df['noise_radius'] > 0) &
        (df['callsign'].notnull()) &
        (df['alt']>50)].copy()
    current_callsigns = set(current_noisy_flights['callsign'].tolist())

    # 1. NEUE LÄRM-EVENTS STARTEN (Inkl. Start-Position)
    c.execute("SELECT callsign FROM active_flights WHERE region = ?", (region_name,))
    already_active = {row[0] for row in c.fetchall()}

    for _, row in current_noisy_flights.iterrows():
        if row['callsign'] not in already_active:
            try:
                # Wir speichern hier die aktuellen Koordinaten als Startpunkt
                c.execute("INSERT INTO active_flights VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                          (row['callsign'], now_str, row['model'], current_db_threshold,
                           row['alt'], region_name, row['lat'], row['lon']))
            except sqlite3.IntegrityError:
                pass

    # 2. BEENDETE LÄRM-EVENTS (Inkl. End-Position)
    c.execute("SELECT callsign, start_time, model, min_alt, start_lat, start_lon FROM active_flights WHERE region = ?", (region_name,))
    active_in_db = c.fetchall()

    for callsign, start_time, model, min_alt, s_lat, s_lon in active_in_db:
        if callsign not in current_callsigns:
            start_dt = datetime.fromisoformat(start_time)
            duration = (now - start_dt).total_seconds()

            if duration > 5:
                # Wir holen die LETZTE bekannte Position aus dem DF für den Endpunkt
                # Falls der Flieger schon ganz weg ist, nehmen wir die Startposition (Sicherheitshalber)
                last_row = df[df['callsign'] == callsign]
                e_lat = last_row['lat'].values[0] if not last_row.empty else s_lat
                e_lon = last_row['lon'].values[0] if not last_row.empty else s_lon

                c.execute("INSERT INTO noise_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (callsign, model, region_name, start_time, now_str, duration,
                           min_alt, s_lat, s_lon, e_lat, e_lon))

            c.execute("DELETE FROM active_flights WHERE callsign = ?", (callsign,))

    conn.commit()
    conn.close()


def get_recent_history(limit=5):
    """Holt die erweiterten Lärmereignisse für die Anzeige."""
    conn = sqlite3.connect("noise_history.db")
    # Wir holen jetzt mehr Spalten aus der DB
    query = f"""
        SELECT callsign, model, start_time, end_time, duration_sec, min_alt 
        FROM noise_history 
        ORDER BY end_time DESC LIMIT {limit}
    """
    df_hist = pd.read_sql_query(query, conn)
    conn.close()
    return df_hist