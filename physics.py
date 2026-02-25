import math

# Mapping von ICAO-Typecodes auf geschätzte Schalleistungspegel (Lw)
# Das ist eine Vereinfachung, aber viel besser als ein Einheitswert!
NOISE_LOOKUP = {
    "A388": 155,  # Airbus A380
    "A359": 145,  # Airbus A350-900
    "A320": 140,  # Airbus A320
    "A321": 141,
    "B744": 152,  # Boeing 747-400
    "B738": 140,  # Boeing 737-800
    "B77W": 148,  # Boeing 777-300ER
    "C172": 115,  # Cessna 172 (sehr leise)
    "E190": 138,  # Embraer 190
    "MD11": 150,  # MD-11 (bekannt als laut)
}


def get_base_noise(typecode):
    """Gibt den Lärmwert basierend auf dem Typ-Code zurück."""
    if not typecode:
        return 140  # Default-Wert

    # 1. Direkter Treffer
    if typecode in NOISE_LOOKUP:
        return NOISE_LOOKUP[typecode]

    # 2. Heuristik: Grobe Kategorien (Startet der Code mit...)
    if typecode.startswith("A3"): return 142  # Meist Airbus Jets
    if typecode.startswith("B7"): return 143  # Meist Boeing Jets
    if typecode.startswith("C"):  return 120  # Meist kleinere Propellermaschinen

    return 140  # Standardwert für Unbekannte


def calculate_db(alt_m, dist_ground_m, typecode="DEFAULT"):
    if alt_m <= 0: return 0

    base_noise = get_base_noise(typecode)
    direct_dist = math.sqrt(dist_ground_m ** 2 + alt_m ** 2)

    noise = base_noise - 20 * math.log10(max(1, direct_dist)) - 11
    return max(0, noise)


def get_noise_radius(alt_m, target_db, model_code="DEFAULT"):
    if alt_m < 100:
        return 0

    base_noise = get_base_noise(model_code)
    try:
        total_dist = 10 ** ((base_noise - target_db - 11) / 20)

        if total_dist <= alt_m:
            return 0

        radius = math.sqrt(total_dist ** 2 - alt_m ** 2)

        # --- NEU: LIMITIERUNG ---
        # Ein Radius von mehr als 5km (5000m) ist unrealistisch für 55dB
        # wegen atmosphärischer Dämpfung.
        return min(radius, 5000)

    except:
        return 0