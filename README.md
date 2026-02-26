# ✈️ Fluglärm-Tracker

Ein Echtzeit-Dashboard zur Überwachung und Dokumentation von Fluglärmereignissen rund um den Flughafen Leipzig/Halle. Die App visualisiert Flugbewegungen und berechnet potenzielle Lärmzonen basierend auf Live-Daten.

## 🚀 Features

* **Live-Tracking:** Echtzeit-Visualisierung von Flugzeugen via OpenSky Network API.
* **Lärm-Simulation:** Dynamische Berechnung von Lärmschutzzonen (dB-Schätzung) basierend auf Flughöhe und Entfernung.
* **Cloud-Historie:** Automatische Speicherung von Lärmereignissen in einer Supabase (PostgreSQL) Datenbank.
* **Automatisches Cleanup:** Rollierender 7-Tage-Speicher sorgt für aktuelle Daten ohne Überlastung.

## 🛠️ Tech Stack

* **Frontend:** [Streamlit](https://streamlit.io)
* **Datenquelle:** [OpenSky Network API](https://opensky-network.org/)
* **Datenbank:** [Supabase](https://supabase.com) (PostgreSQL)
* **Visualisierung:** [Pydeck](https://deck.gl/docs/api-reference/layers/scatterplot-layer)
* **Sprache:** Python 3.x

## 📋 Installation & Lokal ausführen

1.  **Repository klonen:**
    ```bash
    git clone [https://github.com/Big-Eric-Blip/Fluglaerm.git](https://github.com/Big-Eric-Blip/Fluglaerm.git)
    cd Fluglaerm
    ```

2.  **Abhängigkeiten installieren:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Secrets konfigurieren:**
    Erstelle einen Ordner `.streamlit/` und darin eine `secrets.toml` mit deinen Zugangsdaten für OpenSky und Supabase.

4.  **App starten:**
    ```bash
    streamlit run app.py
    ```

## 📈 Lärmberechnung
Die App nutzt das physikalische Abstandsgesetz für Schallwellen. Da der Schalldruck quadratisch zur Entfernung abnimmt, wird aus der vertikalen und horizontalen Distanz zum Messpunkt ein geschätzter Dezibel-Wert ermittelt, um die Belastung in verschiedenen Zonen (Extrem, Hoch, Mittel, Gering) darzustellen.

---
*Hinweis: Dies ist ein privates Projekt zu Bildungszwecken. Die Dezibel-Werte sind mathematische Schätzungen und ersetzen keine geeichten Lärmmessstationen.*
