import pandas as pd

df = pd.read_csv("data/dataset_raw.csv")
clave = ["precio", "m2_construccion", "recamaras", "banos"]

print("Nulos (%) por fuente:")
print(df.groupby("fuente")[["colonia", "m2_construccion", "m2_terreno",
                            "recamaras", "banos", "precio"]]
        .apply(lambda g: (g.isna().mean() * 100).round(0)))

print("\nDuplicados internos por fuente (misma clave):")
for f, g in df.groupby("fuente"):
    print(f"  {f:15s} {g.duplicated(clave).sum()} de {len(g)}")

# prioridad: fuentes con más campos primero
orden = {"century21": 0, "casasyterrenos": 1, "mercadolibre": 2, "trovit": 3}
d = df.assign(p=df.fuente.map(orden)).sort_values("p")
unicos = d.drop_duplicates(clave, keep="first")
print(f"\nTras dedup global: {len(unicos)} de {len(df)}")
print(unicos.groupby("fuente").size())
print("\nPrecio por fuente:")
print(unicos.groupby("fuente").precio.describe().round(0))