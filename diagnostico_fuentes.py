"""
Diagnóstico de fuentes para el scraping de casas en Gustavo A. Madero.
    pip install requests beautifulsoup4
    python diagnostico_fuentes.py

Genera la carpeta ./muestras con el HTML de cada portal y un resumen en
consola. Sube el resumen (y los .html si pesan poco) para escribir los
scrapers con selectores reales.
"""
import os
import re
import time
import random
import requests
from bs4 import BeautifulSoup

# Cambia a True si el portal responde 403 con el UA académico.
USAR_UA_NAVEGADOR = False

UA_ACADEMICO = "AcademicResearchBot/1.0 (proyecto escolar de mineria de datos)"
UA_NAVEGADOR = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": UA_NAVEGADOR if USAR_UA_NAVEGADOR else UA_ACADEMICO,
    "Accept-Language": "es-MX,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}

FUENTES = {
    "mercadolibre": "https://inmuebles.mercadolibre.com.mx/casas/venta/distrito-federal/gustavo-a-madero/",
    "mercadolibre_p2": "https://inmuebles.mercadolibre.com.mx/casas/venta/distrito-federal/gustavo-a-madero/_Desde_49",
    "trovit": "https://casas.trovit.com.mx/gustavo-madero-casa",
    "century21": "https://century21mexico.com/casas-en-venta-en-mexico-ciudad-de-mexico-gustavo-a-madero",
    "casasyterrenos": "https://www.casasyterrenos.com/ciudad-de-mexico/gustavo-a-madero/casas/venta",
    "lamudi": "https://www.lamudi.com.mx/distrito-federal/gustavo-a-madero/casa/for-sale/",
    "propiedades": "https://propiedades.com/gustavo-a-madero/casas-venta",
}

# Marcadores que nos dicen dónde viven los datos en cada página.
MARCADORES = [
    "__PRELOADED_STATE__",
    "__NEXT_DATA__",
    "__INITIAL_STATE__",
    "application/ld+json",
]

os.makedirs("muestras", exist_ok=True)

for nombre, url in FUENTES.items():
    print(f"\n=== {nombre} ===\n{url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except Exception as e:
        print("  ERROR de conexión:", e)
        continue

    html = r.text
    print(f"  status: {r.status_code} | bytes: {len(html):,}")

    with open(f"muestras/{nombre}.html", "w", encoding="utf-8") as f:
        f.write(html)

    if r.status_code != 200:
        print("  -> bloqueado o no disponible")
    else:
        soup = BeautifulSoup(html, "html.parser")
        print("  <title>:", soup.title.string.strip() if soup.title and soup.title.string else None)
        print("  marcadores JSON:", [m for m in MARCADORES if m in html] or "ninguno")
        # Conteo de precios con formato $ 1,234,567 como señal rápida de que hay anuncios
        precios = re.findall(r"\$\s?\d{1,3}(?:,\d{3}){1,3}", html)
        print("  ocurrencias de precio en el HTML:", len(precios), precios[:3])

    time.sleep(random.uniform(1.5, 3.5))

print("\nListo. Revisa la carpeta ./muestras y comparte este resumen.")