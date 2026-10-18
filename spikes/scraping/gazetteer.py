"""Toronto relevance matcher for social posts.

Strong terms are specific enough to mark a post as Toronto-related on their own.
Weak terms (street names, generic neighbourhood names) only count when two distinct
ones appear together, or alongside a strong term. Spike version: curated lists; the
production version adds all 158 official neighbourhoods and GTFS stop names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

STRONG_TERMS = [
    "toronto", "torontonian", "torontonians", "the 6ix", "6ix", "ttc", "topoli",
    "city of toronto", "olivia chow", "scarborough", "etobicoke", "north york", "east york",
    "yorkville", "leslieville", "parkdale", "roncesvalles", "kensington market",
    "liberty village", "cabbagetown", "the danforth", "distillery district", "harbourfront",
    "cn tower", "rogers centre", "scotiabank arena", "nathan phillips square",
    "yonge-dundas square", "yonge dundas square", "dundas square", "sankofa square",
    "eaton centre", "union station", "trinity bellwoods", "st lawrence market",
    "st. lawrence market", "exhibition place", "ontario place", "toronto island",
    "toronto islands", "bloor west village", "queen west", "king west", "ossington",
    "spadina", "yonge street", "yonge st", "bloor street", "bloor st", "gardiner expressway",
    "don valley parkway", "dvp", "presto card", "union pearson", "eglinton crosstown",
    "crosstown lrt", "finch west lrt", "regent park", "moss park", "corktown", "the annex",
    "high park", "christie pits", "dufferin grove", "riverdale park", "the beaches",
    "humber bay", "mimico", "weston", "rexdale", "thorncliffe", "flemingdon", "jane and finch",
    "malvern", "agincourt", "kennedy station", "kipling station", "finch station",
    "path network", "toronto reference library", "metro hall", "queen's park",
]

WEAK_TERMS = [
    "yonge", "bloor", "queen st", "queen street", "king st", "king street", "dundas",
    "college st", "college street", "danforth", "gerrard", "jarvis", "sherbourne", "bathurst",
    "dufferin", "lansdowne", "parliament st", "front st", "front street", "adelaide",
    "richmond st", "wellington st", "harbord", "eglinton", "sheppard", "finch", "steeles",
    "lawrence ave", "kennedy rd", "markham rd", "chinatown", "koreatown", "little italy",
    "little portugal", "greektown", "riverdale", "the junction", "the beach", "gta",
    "ontario", "streetcar", "gardiner", "metrolinx", "go train", "pearson", "don valley",
    "lake ontario", "humber", "rouge", "subway",
]

SUBWAY_STATIONS = [
    "finch", "north york centre", "sheppard-yonge", "york mills", "lawrence", "eglinton",
    "davisville", "st clair", "summerhill", "rosedale", "bloor-yonge", "wellesley", "college",
    "dundas", "queen", "king", "union", "st andrew", "osgoode", "st patrick", "queen's park",
    "museum", "st george", "spadina", "dupont", "st clair west", "cedarvale", "eglinton west",
    "glencairn", "lawrence west", "yorkdale", "wilson", "sheppard west", "downsview park",
    "finch west", "york university", "pioneer village", "highway 407",
    "vaughan metropolitan centre", "kipling", "islington", "royal york", "old mill", "jane",
    "runnymede", "high park", "keele", "dundas west", "lansdowne", "dufferin", "ossington",
    "christie", "bathurst", "bay", "sherbourne", "castle frank", "broadview", "chester", "pape",
    "donlands", "greenwood", "coxwell", "woodbine", "main street", "victoria park", "warden",
    "kennedy", "bayview", "bessarion", "leslie", "don mills",
]


def _alternation(terms: list[str]) -> str:
    # Longest first so "queen west" wins over "queen".
    return "|".join(re.escape(t) for t in sorted(set(terms), key=len, reverse=True))


_STRONG_RE = re.compile(rf"(?<![\w#])#?(?:{_alternation(STRONG_TERMS)})(?!\w)", re.IGNORECASE)
_WEAK_RE = re.compile(rf"(?<![\w#])#?(?:{_alternation(WEAK_TERMS)})(?!\w)", re.IGNORECASE)
_STATION_RE = re.compile(
    rf"(?<!\w)(?:{_alternation(SUBWAY_STATIONS)})\s+(?:station|stn)\b", re.IGNORECASE
)
# Hashtags such as #toronto, #torontolife, #torontostreets
_TAG_RE = re.compile(r"#(?:toronto\w*|the6ix|6ix|ttc\w*|topoli|streetsoftoronto)\b", re.IGNORECASE)


# Region-level words that never count toward the two-weak-terms rule on their own.
REGIONAL = {"ontario", "gta", "lake ontario", "subway", "streetcar", "go train", "metrolinx", "pearson"}
# Other cities whose streets share Toronto names (King St, Dundas St ...).
_OTHER_CITY_RE = re.compile(
    r"(?<!\w)(?:london|hamilton|ottawa|kitchener|waterloo|guelph|oshawa|barrie|kingston|"
    r"mississauga|brampton|montreal|vancouver|new york|nyc|melbourne|sydney)(?!\w)",
    re.IGNORECASE,
)


@dataclass
class Match:
    strong: list[str]
    weak: list[str]
    other_city: bool = False

    @property
    def relevant(self) -> bool:
        if self.strong:
            return True
        local_weak = set(self.weak) - REGIONAL
        return len(local_weak) >= 2 and not self.other_city

    @property
    def prefilter(self) -> bool:
        """Broad net used at capture time; relevance is decided later."""
        return bool(self.strong) or bool(self.weak)


def match(text: str) -> Match:
    if not text:
        return Match([], [])
    strong = [m.group(0).lower().lstrip("#") for m in _STRONG_RE.finditer(text)]
    strong += [m.group(0).lower() for m in _STATION_RE.finditer(text)]
    strong += [m.group(0).lower() for m in _TAG_RE.finditer(text)]
    weak = [m.group(0).lower().lstrip("#") for m in _WEAK_RE.finditer(text)]
    return Match(strong, weak, bool(_OTHER_CITY_RE.search(text)))


COMPLAINT_TERMS = [
    "pothole", "potholes", "flooding", "flooded", "flood", "graffiti", "out of service",
    "out of order", "elevator", "escalator", "broken", "smashed", "vandalized", "vandalised",
    "garbage", "trash", "litter", "dumping", "dumped", "overflowing", "fallen tree",
    "downed tree", "streetlight", "street light", "sidewalk", "crack", "cracked", "311",
    "hazard", "dangerous", "unsafe", "construction", "blocked", "closed", "leak", "leaking",
    "water main", "sinkhole", "snow", "ice", "unplowed", "not plowed", "shelter", "bus shelter",
]
_COMPLAINT_RE = re.compile(rf"(?<!\w)(?:{_alternation(COMPLAINT_TERMS)})(?!\w)", re.IGNORECASE)


def complaint_terms(text: str) -> list[str]:
    return [m.group(0).lower() for m in _COMPLAINT_RE.finditer(text or "")]


if __name__ == "__main__":
    samples = [
        "Huge pothole on Queen St at Spadina again",
        "Lovely sunset over Lake Ontario from Mimico",
        "Bloor-Yonge station elevator out of service #TTC",
        "King st and Dundas in London Ontario",
        "My cat is so cute",
    ]
    for s in samples:
        m = match(s)
        print(f"{m.relevant!s:5} strong={m.strong} weak={m.weak} complaints={complaint_terms(s)} :: {s}")
