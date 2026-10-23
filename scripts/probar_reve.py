#!/usr/bin/env python3
"""Prueba de la API de Reve: UNA sola petición. Nunca imprime la clave."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www.mapareve.es/api/external/v1"
key = os.environ.get("REVE_API_KEY", "").strip()
if not key:
    print("::error::No existe el secreto REVE_API_KEY (o está vacío)")
    raise SystemExit(1)
import hashlib
print(f"::notice::Secreto REVE_API_KEY encontrado ({len(key)} caracteres) · huella {hashlib.sha256(key.encode()).hexdigest()[:12]}")
if os.environ.get("SOLO_HUELLA"):
    raise SystemExit(0)

params = {"page": 1, "limit": 100}
url = f"{BASE}/locations?{urllib.parse.urlencode(params)}"
req = urllib.request.Request(url, headers={
    "x-api-key": key,
    "Accept": "application/json",
    "User-Agent": "cargadores-mapa (github.com/Manujzesc/Cargadores-mapa)",
})
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        status, headers, body = r.status, dict(r.headers), r.read()
except urllib.error.HTTPError as e:
    status, headers, body = e.code, dict(e.headers), e.read()
except Exception as e:  # noqa: BLE001
    print(f"::error::No se pudo conectar: {e}")
    raise SystemExit(1)

interesting = {k: v for k, v in headers.items()
               if any(s in k.lower() for s in ("total", "page", "limit", "rate", "retry", "link"))}
print(f"::notice::HTTP {status} · {len(body)} bytes · cabeceras: {json.dumps(interesting)[:700]}")

try:
    data = json.loads(body)
except Exception:  # noqa: BLE001
    print(f"::error::Respuesta no JSON: {body[:500]!r}")
    raise SystemExit(1)

items = data
if isinstance(data, dict):
    print(f"::notice::Claves de la respuesta: {list(data.keys())[:20]}")
    for k in ("data", "items", "results", "locations"):
        if isinstance(data.get(k), list):
            items = data[k]
            break
if isinstance(items, list):
    print(f"::notice::Elementos recibidos con limit=100: {len(items)}")
    if items:
        first = items[0]
        print(f"::notice::Campos de un emplazamiento: {list(first.keys())[:40] if isinstance(first, dict) else type(first)}")
        print(f"::notice::Ejemplo: {json.dumps(first, ensure_ascii=False)[:900]}")
else:
    print(f"::notice::Respuesta: {json.dumps(data, ensure_ascii=False)[:900]}")

if status != 200:
    raise SystemExit(1)
