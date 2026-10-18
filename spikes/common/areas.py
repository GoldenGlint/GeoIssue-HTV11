"""Study areas for the geolocation spike (west, south, east, north)."""

AREAS = {
    # About 1.2 km x 1.05 km around Queen/King x Spadina/Bathurst.
    "A_downtown": (-79.4050, 43.6430, -79.3900, 43.6525),
    # About 0.56 km x 0.56 km around UTSC, 1265 Military Trail (the hackathon venue; confirm).
    "B_venue": (-79.1905, 43.7810, -79.1835, 43.7860),
}

# Distractor areas: embedded only, so retrieval is tested against a city-sized haystack.
# Liberty Village is deliberately close to A and architecturally similar (hard negatives).
DISTRACTORS = {
    "D_liberty_village": (-79.4260, 43.6355, -79.4140, 43.6420),
    "D_yonge_eglinton": (-79.4030, 43.7030, -79.3930, 43.7100),
    "D_danforth_pape": (-79.3500, 43.6765, -79.3390, 43.6825),
}


def center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    w, s, e, n = bbox
    return (s + n) / 2, (w + e) / 2


def contains(bbox: tuple[float, float, float, float], lat: float, lon: float) -> bool:
    w, s, e, n = bbox
    return s <= lat <= n and w <= lon <= e
