import re
import unicodedata

import pandas as pd


def norm(s):
    """Minúsculas, sin acentos ni signos, para comparar nombres de colonias."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


df = pd.read_csv("data/dataset_raw.csv")
tv = df[df.fuente == "trovit"].copy().reset_index(drop=True)

# --- 1) Catálogo de colonias a partir de las fuentes que sí las traen
ref = df[(df.fuente != "trovit") & df.colonia.notna()]
nombre = ref.groupby(ref.colonia.map(norm)).colonia.agg(lambda s: s.mode().iat[0]).to_dict()
# más largas primero: "lindavista norte" debe ganar sobre "lindavista"
claves = sorted((c for c in nombre if len(c) >= 5), key=len, reverse=True)
patrones = [(re.compile(rf"(?<![a-z0-9]){re.escape(c)}(?![a-z0-9])"), c) for c in claves]
print(f"Colonias en el catálogo: {len(claves)}")


def buscar(txt):
    t = norm(txt)
    for p, c in patrones:
        if p.search(t):
            return nombre[c]
    return None


tv["colonia_rescatada"] = tv.titulo.map(buscar)
sin = tv.colonia_rescatada.isna()
tv.loc[sin, "colonia_rescatada"] = tv.loc[sin, "texto"].map(buscar)
print(f"\nColonia rescatada: {tv.colonia_rescatada.notna().sum()} de {len(tv)}")

# --- 2) Contaminación: renta, terrenos, otras zonas
t_all = (tv.titulo.fillna("") + " " + tv.texto.fillna("")).map(norm)
t_tit = tv.titulo.fillna("").map(norm)
tv["es_renta"] = t_all.str.contains(r"\b(renta|rento|alquiler|se renta)\b")
tv["es_terreno"] = t_tit.str.contains(r"\b(terreno|lote|predio)\b") & ~t_tit.str.contains(r"\bcasa\b")
tv["otra_zona"] = t_tit.str.contains(
    r"edomex|estado de mexico|ecatepec|nezahualcoyotl|naucalpan|tlalnepantla|coacalco|tultitlan|hidalgo|pachuca")
print("\nBanderas (número de filas):")
print(tv[["es_renta", "es_terreno", "otra_zona"]].sum().to_string())

# --- 3) ¿Se degrada con la página? (el CSV conserva el orden de paginación)
tv["bloque"] = (tv.index // 150) + 1
print("\nMediana de precio y % con colonia por bloque de 150 filas (≈5 páginas):")
print(tv.groupby("bloque").agg(n=("precio", "size"),
                               mediana=("precio", "median"),
                               pct_colonia=("colonia_rescatada", lambda s: round(s.notna().mean() * 100))
                               ).to_string())

# --- 4) Distribución de precios y muestras
bins = [0, 5e5, 1.5e6, 3e6, 1e9]
print("\nPrecio Trovit por rango:")
print(pd.cut(tv.precio, bins).value_counts().sort_index().to_string())

pd.set_option("display.width", 200, "display.max_colwidth", 60)
print("\nMuestra de precios < $1,500,000:")
print(tv[tv.precio < 1.5e6][["titulo", "precio", "m2_construccion", "es_renta"]].sample(15, random_state=1).to_string())

print("\nTítulos sin colonia (para revisar alias):")
print(tv[tv.colonia_rescatada.isna()].titulo.sample(15, random_state=1).to_string())

# --- 5) Cuántos Trovit sobreviven con filtros razonables
ok = tv[~tv.es_renta & ~tv.es_terreno & ~tv.otra_zona
        & (tv.precio >= 1_000_000) & tv.colonia_rescatada.notna()]
clave = ["precio", "m2_construccion", "recamaras", "banos"]
print(f"\nTrovit tras filtros: {len(ok)} | únicos: {len(ok.drop_duplicates(clave))}")