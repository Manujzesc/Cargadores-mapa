# Cargadores Model 3

Mapa de puntos de recarga públicos de España compatibles con Tesla Model 3, actualizado cada lunes.

**Mapa:** https://manujzesc.github.io/Cargadores-mapa/

## Capas

- **Rápidos CCS2**: emplazamientos con al menos un conector CCS2.
- **Lentos Tipo 2**: emplazamientos con Tipo 2 y sin CCS2.
- **☕ Comer**: compatibles con restaurante, cafetería o bar a ≤250 m (OpenStreetMap) o declarado por el operador.
- **🛏️ Dormir**: compatibles con hotel u hostal a ≤600 m (OpenStreetMap) o declarado por el operador.

Cada punto tiene un botón para abrirlo en Google Maps y, desde ahí, compartirlo con la app de Tesla.

## Cómo funciona

`.github/workflows/actualizar.yml` se ejecuta cada lunes a las 10:00 (hora de España en invierno), un solo intento: `scripts/build.py` descarga el fichero
público de la DGT (datos del Ministerio) y los sitios de OpenStreetMap, genera los GeoJSON en
`site/data/` y publica `site/` en GitHub Pages.

Para lanzarlo a mano: pestaña **Actions → Actualizar mapa → Run workflow**.

Datos: DGT / MITECO (información pública) y © colaboradores de OpenStreetMap (ODbL).
