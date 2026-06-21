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

        # Lade den Cache
        self.aircraft_cache = self._load_cache()
        if self.aircraft_cache:
            print(f"✅ Cache geladen: {len(self.aircraft_cache)} Flugzeuge bekannt.")
        else:
            print("⚠️ Kein Cache gefunden. Modelle werden auf 'A320' gesetzt.")

    def _load_cache(self):
        """Lädt die JSON-Datei mit Modellen."""
        if os.path.exists("aircraft_cache.json"):
            try:
                with open("aircraft_cache.json", "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    async def get_access_token(self):
        """Holt OAuth-Token mit Timeout"""
        if self.token and time.time() < self.token_expires - 60:
            return self.token

        url = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
        data = {"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret}

        timeout = httpx.Timeout(15.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(url, data=data)
                if response.status_code == 200:
                    res_data = response.json()
                    self.token = res_data["access_token"]
                    self.token_expires = time.time() + res_data["expires_in"]
                    return self.token
            except Exception as e:
                print(f"⚠️ Token-Fehler: {e}")
                return None
        return None

    async def fetch_full_data(self, bbox):
        """Holt Flugdaten mit erweitertem Timeout und Fehlerbehandlung"""
        token = await self.get_access_token()
        if not token:
            print("⚠️ Kein Token erhalten")
            return []

        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://opensky-network.org/api/states/all?lamin={bbox[0]}&lomin={bbox[1]}&lamax={bbox[2]}&lomax={bbox[3]}"

        # Längerer Timeout für Streamlit Cloud
        timeout = httpx.Timeout(30.0, connect=15.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    states = response.json().get("states", [])
                    processed_data = []
                    for s in states:
                        icao24 = s[0].lower()
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
                else:
                    print(f"⚠️ OpenSky API Fehler: {response.status_code}")
                    return []
            except httpx.TimeoutException:
                print("⚠️ OpenSky API Timeout")
                return []
            except Exception as e:
                print(f"⚠️ OpenSky API Fehler: {e}")
                return []