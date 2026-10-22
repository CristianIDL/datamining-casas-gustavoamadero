"""
Limpieza del dataset de casas en venta - Gustavo A. Madero (CDMX)
Entrada : data/dataset_raw.csv   (salida de scraper_gam.py)
Salida  : data/dataset_clean.csv

Cada paso imprime cuantas filas quedan, para documentarlo en el reporte (CRISP-DM: Data Preparation).
"""
import re
import unicodedata

import numpy as np
import pandas as pd

RAW = "data/dataset_raw.csv"
OUT = "data/dataset_clean.csv"
# si un anuncio esta en varias fuentes, se conserva el de la fuente con mas campos
PRIORIDAD = {"century21": 0, "casasyterrenos": 1, "mercadolibre": 2, "trovit": 3}
CLAVE_DUP = ["precio", "m2_construccion", "recamaras", "banos"]

# umbrales de cordura (justificar en el reporte)
PRECIO_MIN, PRECIO_MAX = 1_000_000, 60_000_000
M2_MIN, M2_MAX = 30, 2_000
PRECIO_M2_MIN, PRECIO_M2_MAX = 6_000, 150_000  # MXN por m2 construido
REC_MAX = 12

# alias frecuentes en titulos de Trovit (norm -> norm del catalogo)
ALIAS = {"linda vista": "lindavista", "7 maravillas": "siete maravillas"}


def norm(s):
    """Minusculas, sin acentos ni signos: para comparar nombres de colonias."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def paso(df, mascara, nombre):
    """Conserva las filas donde mascara es True e informa cuantas se quitaron."""
    out = df[mascara]
    print(f"  {nombre:52s} -{len(df) - len(out):5d} -> {len(out):5d}")
    return out


df = pd.read_csv(RAW)
print(f"Crudo: {len(df)} filas")
print("Filtros:")

# --- 1) Contaminacion por texto (solo titulo: el 'texto' suele mencionar renta/terreno sin serlo)
t = df.titulo.fillna("").map(norm)
es_renta = t.str.contains(r"\b(?:renta|rento|alquiler)\b") & ~t.str.contains(r"\bventa\b")
es_terreno = t.str.contains(r"\b(?:terreno|lote|predio)\b") & ~t.str.contains(r"\bcasa\b")
otra_zona = t.str.contains(
    r"edomex|estado de mexico|ecatepec|nezahualcoyotl|naucalpan|tlalnepantla|coacalco|tultitlan|atizapan|pachuca")
# remates / recuperacion bancaria: precios que no reflejan el mercado. Codigos tipo 'F-532', 'FG-964'
es_remate = (t.str.contains(r"\b(?:remate|remato|recuperacion|adjudicad[ao]s?|bancari[ao])\b")
             | t.str.contains(r"\b(?:f|fg) \d{2,5}\b"))
df = paso(df, ~es_renta, "rentas")
t = df.titulo.fillna("").map(norm)  # recalcular tras filtrar
df = paso(df, ~(es_terreno.reindex(df.index)), "terrenos etiquetados como casa")
df = paso(df, ~(otra_zona.reindex(df.index)), "fuera de GAM (por titulo)")
df = paso(df, ~(es_remate.reindex(df.index)), "remates / recuperacion bancaria")

# --- 2) Rangos de cordura
df = df.assign(precio_m2=df.precio / df.m2_construccion)
df = paso(df, df.precio.between(PRECIO_MIN, PRECIO_MAX), f"precio fuera de [{PRECIO_MIN:,}, {PRECIO_MAX:,}]")
df = paso(df, df.m2_construccion.between(M2_MIN, M2_MAX), "m2_construccion nulo o fuera de rango")
df = paso(df, df.precio_m2.between(PRECIO_M2_MIN, PRECIO_M2_MAX), "precio por m2 inverosimil")
df = paso(df, df.recamaras.between(1, REC_MAX), "recamaras nulas o fuera de rango")
df = paso(df, df.banos.notna() & (df.banos >= 1), "banos nulos o < 1")

# --- 3) Deduplicacion global (Trovit agrega anuncios de ML/C21 y ML repite anuncios con distinto id)
df = df.assign(_p=df.fuente.map(PRIORIDAD)).sort_values("_p", kind="stable")
df = paso(df, ~df.duplicated(CLAVE_DUP, keep="first"), "duplicados (precio, m2, recamaras, banos)")
df = df.drop(columns="_p")

# --- 4) Colonia: catalogo desde fuentes que la traen; se rescata en Trovit desde titulo y texto
ref = df[(df.fuente != "trovit") & df.colonia.notna()]
nombre = ref.groupby(ref.colonia.map(norm)).colonia.agg(lambda s: s.mode().iat[0]).to_dict()
claves = sorted((c for c in nombre if len(c) >= 5), key=len, reverse=True)  # mas largas primero
patrones = [(re.compile(rf"(?<![a-z0-9]){re.escape(c)}(?![a-z0-9])"), c) for c in claves]


def buscar(txt):
    x = norm(txt)
    for a, b in ALIAS.items():
        x = x.replace(a, b)
    for p, c in patrones:
        if p.search(x):
            return nombre[c]
    return None


falta = df.colonia.isna()
df.loc[falta, "colonia"] = df.loc[falta, "titulo"].map(buscar)
falta = df.colonia.isna()
df.loc[falta, "colonia"] = df.loc[falta, "texto"].map(buscar)
# unificar escritura ('LINDAVISTA NORTE' vs 'Lindavista Norte')
df["colonia"] = df.colonia.map(lambda c: nombre.get(norm(c), c) if pd.notna(c) else c)
df = paso(df, df.colonia.notna(), "sin colonia (no se pudo rescatar)")

# --- 5) Medios banos: 3.5 -> banos=3, medios_banos=1
b = df.banos
df["medios_banos"] = ((b % 1) >= 0.5).astype(int)
df["banos"] = np.floor(b).astype(int)

# --- 6) Salida (cp se descarta: casi todo nulo y redundante con colonia; texto ya no se usa)
cols = ["fuente", "id", "url", "titulo", "precio", "colonia", "m2_construccion", "m2_terreno",
        "recamaras", "banos", "medios_banos", "estacionamientos", "lat", "lon", "precio_m2",
        "fecha_recoleccion"]
df = df[cols].reset_index(drop=True)
df.to_csv(OUT, index=False, encoding="utf-8-sig")

print(f"\n== Limpio: {len(df)} filas -> {OUT}")
print("\nFilas por fuente:")
print(df.groupby("fuente").size().to_string())
print("\nPrecio y precio/m2 por fuente (MXN):")
print(df.groupby("fuente")[["precio", "precio_m2"]].median().round(0).to_string())
print("\nNulos (%) por columna:")
print((df.isna().mean() * 100).round(0).to_string())
print(f"\nColonias distintas: {df.colonia.nunique()} | con < 5 casas: "
      f"{(df.colonia.value_counts() < 5).sum()}")