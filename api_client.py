import httpx
import time
import json
import os


class OpenSkyClient:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expires = 0

        # Lade den Cache, den wir mit dem Filter-Skript erstellt haben
        self.aircraft_cache = self._load_cache()
        if self.aircraft_cache:
            print(f"✅ Cache geladen: {len(self.aircraft_cache)} Flugzeuge bekannt.")
        else:
            print("⚠️ Kein Cache gefunden. Modelle werden auf 'DEFAULT' gesetzt.")

    def _load_cache(self):
        """Lädt die handliche JSON-Datei mit Modellen."""
        if os.path.exists("aircraft_cache.json"):
            with open("aircraft_cache.json", "r") as f:
                return json.load(f)
        return {}

    async def get_access_token(self):
        if self.token and time.time() < self.token_expires - 60:
            return self.token
        url = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
        data = {"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret}
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=data)
            if response.status_code == 200:
                res_data = response.json()
                self.token = res_data["access_token"]
                self.token_expires = time.time() + res_data["expires_in"]
                return self.token
        return None

    async def fetch_full_data(self, bbox):
        token = await self.get_access_token()
        if not token: return []

        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://opensky-network.org/api/states/all?lamin={bbox[0]}&lomin={bbox[1]}&lamax={bbox[2]}&lomax={bbox[3]}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                states = response.json().get("states", [])
                processed_data = []
                for s in states:
                    icao24 = s[0].lower()  # OpenSky nutzt oft Kleinbuchstaben im Cache

                    # Hier holen wir das Modell aus dem Cache
                    # WICHTIG: Wenn nicht gefunden, nutzen wir "A320" als sinnvollen Standard für Lärm
                    model = self.aircraft_cache.get(icao24, "A320")

                    processed_data.append({
                        "icao24": icao24,
                        "callsign": s[1].strip() if s[1] else "Unknown",
                        "lat": s[6],
                        "lon": s[5],
                        "alt": s[7] if s[7] else 0,
                        "model": model
                    })
                return processed_data
            return []