#!/usr/bin/env python3
"""
Genera las capas del mapa de cargadores compatibles con Tesla Model 3 (CCS2 / Tipo 2).

Fuentes:
  - DGT (datos del Ministerio): todos los puntos de recarga de acceso público, DATEX II XML.
  - OpenStreetMap (Overpass): restaurantes/cafeterías y hoteles/hostales cerca de cada cargador.

Salida (carpeta site/data):
  rapidos.geojson      emplazamientos con al menos un conector CCS2
  lentos.geojson       emplazamientos con Tipo 2 y sin CCS2
  comida.geojson       compatibles con restaurante/cafetería a <= RADIO_COMIDA m
  dormir.geojson       compatibles con hotel/hostal a <= RADIO_HOTEL m
  resumen.json         fecha y recuentos

Solo usa la librería estándar de Python.
"""
import json
import math
import os
import sys
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone

DGT_URL = "https://infocar.dgt.es/datex2/v3/miterd/EnergyInfrastructureTablePublication/electrolineras.xml"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
RADIO_COMIDA = 250   # metros
RADIO_HOTEL = 600    # metros
UA = "cargadores-mapa (github.com/Manujzesc/cargadores-mapa)"

# Tipos de servicio DATEX II declarados por el operador
SERV_COMIDA = {"restaurant", "cafe", "bar", "fastfood", "fastFood", "foodshop"}
SERV_HOTEL = {"hotel", "motel", "hostel", "hotelOrMotel"}


def local(tag):
    return tag.rsplit("}", 1)[-1]


def children(el, name):
    return [c for c in el if local(c.tag) == name]


def child(el, name):
    for c in el:
        if local(c.tag) == name:
            return c
    return None


def path(el, *names):
    cur = el
    for n in names:
        if cur is None:
            return None
        cur = child(cur, n)
    return cur


def text_of(el):
    """Texto de un nodo; para textos multilingües DATEX II (values/value) devuelve el primero."""
    if el is None:
        return ""
    for d in el.iter():
        if local(d.tag) == "value" and d.text and d.text.strip():
            return d.text.strip()
    return (el.text or "").strip()


def num(s):
    try:
        return float(str(s).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def connector_kind(ctype):
    t = (ctype or "").lower()
    if t in ("iec62196t2combo",) or ("t2" in t and "combo" in t):
        return "CCS2"
    if t == "iec62196t2":
        return "Tipo 2"
    return None


def parse_site(site):
    sid = text_of(child(site, "id")) or site.get("id") or ""
    coords = path(site, "locationReference", "coordinatesForDisplay")
    if coords is None:
        # algunos ficheros lo anidan distinto: busca en cualquier nivel
        for d in site.iter():
            if local(d.tag) == "coordinatesForDisplay":
                coords = d
                break
    if coords is None:
        return None
    lat = num(text_of(child(coords, "latitude")))
    lon = num(text_of(child(coords, "longitude")))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    name = text_of(child(site, "name")) or "Punto de recarga"
    operator = text_of(path(site, "operator", "name"))
    schedule = text_of(path(site, "operatingHours", "label"))

    # dirección: líneas tipo "Municipio: X"
    addr, muni, prov = "", "", ""
    for d in site.iter():
        if local(d.tag) == "addressLine":
            t = text_of(d)
            low = t.lower()
            if low.startswith("municipio"):
                muni = t.split(":", 1)[-1].strip()
            elif low.startswith("provincia"):
                prov = t.split(":", 1)[-1].strip()
            elif low.startswith("direcci"):
                addr = t.split(":", 1)[-1].strip()
            elif t and not low.startswith("comunidad"):
                addr = addr or t

    services = set()
    for f in children(site, "supplementalFacility"):
        s = text_of(child(f, "serviceFacilityType"))
        if s:
            services.add(s)

    conns = Counter()
    for station in children(site, "energyInfrastructureStation"):
        for rp in children(station, "refillPoint"):
            for c in children(rp, "connector"):
                kind = connector_kind(text_of(child(c, "connectorType")))
                if not kind:
                    continue
                p = num(text_of(child(c, "maxPowerAtSocket")))
                kw = None
                if p is not None:
                    kw = p / 1000 if p >= 1000 else p
                    kw = int(round(kw))
                conns[(kind, kw)] += 1

    if not conns:
        return None

    has_ccs = any(k == "CCS2" for k, _ in conns)
    max_kw = max((kw or 0) for _, kw in conns)
    parts = []
    for (kind, kw), n in sorted(conns.items(), key=lambda x: (x[0][0] != "CCS2", -(x[0][1] or 0))):
        parts.append(f"{n}× {kind}" + (f" {kw} kW" if kw else ""))

    return {
        "id": sid,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "nombre": name,
        "operador": operator,
        "direccion": ", ".join(x for x in (addr, muni, prov) if x),
        "horario": schedule,
        "conectores": " · ".join(parts),
        "kw_max": max_kw,
        "ccs2": has_ccs,
        "serv_comida": bool({s for s in services} & SERV_COMIDA),
        "serv_hotel": bool({s for s in services} & SERV_HOTEL),
    }


def download(url, dest, timeout=300, data=None, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            return True
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  intento {i + 1} fallido ({url}): {e}", file=sys.stderr)
            time.sleep(10 * (i + 1))
    print(f"::warning::ERROR descargando {url}: {last}")
    return False


def load_sites(xml_path):
    sites, seen = [], set()
    total = 0
    for _, el in ET.iterparse(xml_path, events=("end",)):
        if local(el.tag) != "energyInfrastructureSite":
            continue
        total += 1
        try:
            s = parse_site(el)
        except Exception as e:  # noqa: BLE001
            print(f"  site ignorado: {e}", file=sys.stderr)
            s = None
        el.clear()
        if not s:
            continue
        key = s["id"] or f'{s["lat"]},{s["lon"]}'
        if key in seen:
            continue
        seen.add(key)
        sites.append(s)
    print(f"::notice::DGT: {total} emplazamientos en el fichero, {len(sites)} compatibles (CCS2/Tipo 2)")
    return sites, total


OVERPASS_QUERY = """
[out:json][timeout:900];
area["ISO3166-1"="ES"][admin_level=2]->.es;
(
  nwr["amenity"~"^(restaurant|cafe|fast_food|bar)$"](area.es);
  nwr["tourism"~"^(hotel|hostel|motel|guest_house|apartment)$"](area.es);
);
out center tags qt;
"""


def load_pois(work):
    dest = os.path.join(work, "osm.json")
    data = urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode()
    for url in OVERPASS_URLS:
        print(f"OSM: consultando {url}")
        if download(url, dest, timeout=1200, data=data, tries=2):
            try:
                with open(dest, encoding="utf-8") as f:
                    els = json.load(f).get("elements", [])
                if els:
                    break
            except Exception as e:  # noqa: BLE001
                print(f"  respuesta no válida: {e}", file=sys.stderr)
    else:
        print("OSM: sin datos, las capas de comida/dormir solo usarán lo declarado por el operador")
        return [], []

    comida, dormir = [], []
    for e in els:
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lon = e.get("lon") or (e.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        tags = e.get("tags", {})
        nm = tags.get("name") or ""
        if tags.get("amenity") in ("restaurant", "cafe", "fast_food", "bar"):
            comida.append((lat, lon, nm, tags["amenity"]))
        elif tags.get("tourism"):
            dormir.append((lat, lon, nm, tags["tourism"]))
    print(f"OSM: {len(comida)} sitios de comida, {len(dormir)} alojamientos")
    return comida, dormir


TIPO_ES = {
    "restaurant": "restaurante", "cafe": "cafetería", "fast_food": "comida rápida", "bar": "bar",
    "hotel": "hotel", "hostel": "albergue", "motel": "motel", "guest_house": "hostal",
    "apartment": "apartamentos",
}


class Grid:
    def __init__(self, pts, cell=0.01):
        self.cell = cell
        self.g = defaultdict(list)
        for p in pts:
            self.g[(int(p[0] // cell), int(p[1] // cell))].append(p)

    def near(self, lat, lon, radius_m, limit=3):
        cl = int(lat // self.cell)
        co = int(lon // self.cell)
        r = int(radius_m / 1000 / (111 * self.cell)) + 1
        out = []
        coslat = math.cos(math.radians(lat))
        for i in range(cl - r, cl + r + 1):
            for j in range(co - r - 1, co + r + 2):
                for p in self.g.get((i, j), ()):
                    dy = (p[0] - lat) * 111320
                    dx = (p[1] - lon) * 111320 * coslat
                    d = math.hypot(dx, dy)
                    if d <= radius_m:
                        out.append((d, p))
        out.sort(key=lambda x: x[0])
        # prioriza los que tienen nombre
        out.sort(key=lambda x: (x[1][2] == "", x[0]))
        return [
            f'{p[2] or TIPO_ES.get(p[3], p[3]).capitalize()} ({TIPO_ES.get(p[3], p[3])}, {int(round(d, -1))} m)'
            for d, p in out[:limit]
        ], len(out)


def feature(s, extra=None):
    props = {k: v for k, v in s.items() if k not in ("lat", "lon") and v not in ("", None)}
    if extra:
        props.update(extra)
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]}, "properties": props}


def write_geojson(path_, feats):
    with open(path_, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f, ensure_ascii=False, separators=(",", ":"))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "site/data"
    work = os.environ.get("WORK_DIR", "work")
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)

    xml_path = os.environ.get("DGT_XML") or os.path.join(work, "electrolineras.xml")
    if not os.environ.get("DGT_XML"):
        print("DGT: descargando…")
        if not download(DGT_URL, xml_path, timeout=600):
            sys.exit(1)
    sites, total = load_sites(xml_path)
    if len(sites) < 100 and not os.environ.get("ALLOW_SMALL"):
        size = os.path.getsize(xml_path)
        with open(xml_path, "rb") as f:
            head = f.read(600).decode("utf-8", "replace").replace("\n", " ")
        print(f"::error::Solo {len(sites)} emplazamientos (fichero {size} bytes). Inicio: {head}")
        sys.exit(1)

    if os.environ.get("SKIP_OSM"):
        comida, dormir = [], []
    else:
        comida, dormir = load_pois(work)
    gc, gd = Grid(comida), Grid(dormir)

    rapidos, lentos, f_comida, f_dormir = [], [], [], []
    for s in sites:
        cerca_c, n_c = gc.near(s["lat"], s["lon"], RADIO_COMIDA)
        cerca_d, n_d = gd.near(s["lat"], s["lon"], RADIO_HOTEL)
        extra = {}
        if cerca_c:
            extra["comida"] = cerca_c
            extra["n_comida"] = n_c
        if cerca_d:
            extra["dormir"] = cerca_d
            extra["n_dormir"] = n_d
        f = feature(s, extra)
        (rapidos if s["ccs2"] else lentos).append(f)
        if cerca_c or s["serv_comida"]:
            f_comida.append(f)
        if cerca_d or s["serv_hotel"]:
            f_dormir.append(f)

    write_geojson(os.path.join(out, "rapidos.geojson"), rapidos)
    write_geojson(os.path.join(out, "lentos.geojson"), lentos)
    write_geojson(os.path.join(out, "comida.geojson"), f_comida)
    write_geojson(os.path.join(out, "dormir.geojson"), f_dormir)
    resumen = {
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "emplazamientos_dgt": total,
        "rapidos": len(rapidos),
        "lentos": len(lentos),
        "comida": len(f_comida),
        "dormir": len(f_dormir),
        "osm": bool(comida or dormir),
    }
    with open(os.path.join(out, "resumen.json"), "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=1)
    print("::notice::" + json.dumps(resumen, ensure_ascii=False))


if __name__ == "__main__":
    main()
