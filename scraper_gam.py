"""
Scraper de casas en venta - Gustavo A. Madero (CDMX)
Fuentes: Mercado Libre, Trovit, Century 21, Casas y Terrenos

Uso (LOCAL, no Colab):
    pip install requests beautifulsoup4 pandas
    python scraper_gam.py                 # scrapea todo y genera data/dataset_raw.csv
    python scraper_gam.py --offline muestras   # prueba los parsers con los HTML guardados

Buenas practicas: pausa aleatoria 1.5-3.5 s, solo paginas publicas de listados,
sin datos de contacto (no se guardan telefonos/correos/nombres de agentes).
"""
import argparse
import json
import os
import random
import re
import sys
import time
from datetime import date

import pandas as pd
import requests
from bs4 import BeautifulSoup

OUT_DIR = "data"
FECHA = date.today().isoformat()
HEADERS = {
    "User-Agent": "AcademicResearchBot/1.0 (proyecto escolar de mineria de datos)",
    "Accept-Language": "es-MX,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}
COLUMNAS = [
    "fuente", "id", "url", "titulo", "tipo", "precio", "colonia", "cp",
    "m2_construccion", "m2_terreno", "recamaras", "banos", "estacionamientos",
    "lat", "lon", "texto", "fecha_recoleccion",
]
sess = requests.Session()
sess.headers.update(HEADERS)


# ----------------------------------------------------------------- utilidades
def get_html(url, intentos=2):
    """Descarga decodificando SIEMPRE en UTF-8 (evita 'MÃ©xico')."""
    for i in range(intentos):
        try:
            r = sess.get(url, timeout=25)
            if r.status_code == 200:
                return r.content.decode("utf-8", errors="replace")
            print(f"   ! {r.status_code} en {url}")
            if r.status_code in (403, 429):
                time.sleep(10)
        except requests.RequestException as e:
            print(f"   ! error {e.__class__.__name__} en {url}")
        time.sleep(2)
    return None


def pausa():
    time.sleep(random.uniform(1.5, 3.5))


def num(txt):
    """'1,005 m²' -> 1005.0 ; '3.5' -> 3.5 ; None si no hay numero."""
    if txt is None:
        return None
    m = re.search(r"\d[\d,]*\.?\d*", str(txt))
    return float(m.group(0).replace(",", "")) if m else None


def fila(**kw):
    d = {c: None for c in COLUMNAS}
    d.update(kw)
    d["fecha_recoleccion"] = FECHA
    return d


def limpiar_texto(t):
    """Quita telefonos y correos del texto libre (proteccion de PII)."""
    if not t:
        return t
    t = re.sub(r"[\w\.-]+@[\w\.-]+", "[correo]", t)
    t = re.sub(r"\+?\d[\d\s\-\(\)]{8,}\d", "[tel]", t)
    return re.sub(r"\s+", " ", t).strip()


# ------------------------------------------------------------ MERCADO LIBRE
ML_BASE = "https://inmuebles.mercadolibre.com.mx/casas/venta/distrito-federal/gustavo-a-madero/"


def parse_ml(html):
    soup = BeautifulSoup(html, "html.parser")
    filas = []
    for it in soup.select("li.ui-search-layout__item"):
        a = it.select_one("a.poly-component__title")
        if not a:
            continue
        href = a["href"].split("#")[0]
        m = re.search(r"MLM-?(\d+)", href)
        head = it.select_one(".poly-component__headline")
        if head and "casa" not in head.get_text().lower():
            continue
        sym = it.select_one(".andes-money-amount__currency-symbol")
        precio = it.select_one(".andes-money-amount__fraction")
        if not precio or (sym and "MXN" not in sym.get_text()):
            continue  # solo precios en MXN
        attrs = [x.get_text(" ", strip=True) for x in it.select(".poly-attributes_list__item")]
        rec = ban = const = terr = None
        for t in attrs:
            tl = t.lower()
            if "rec" in tl:
                rec = num(t)
            elif "baño" in tl:
                ban = num(t)
            elif "construid" in tl:
                const = num(t)
            elif "terreno" in tl or "totales" in tl:
                terr = num(t)
        loc = it.select_one(".poly-component__location")
        loc = loc.get_text(" ", strip=True) if loc else ""
        partes = [p.strip() for p in loc.split(",")]
        colonia = None
        for i, p in enumerate(partes):
            if "Gustavo A. Madero" in p and i > 0:
                colonia = partes[i - 1]
                break
        cp = re.search(r"\b(0\d{4})\b", loc)
        filas.append(fila(
            fuente="mercadolibre", id=m.group(1) if m else href, url=href,
            titulo=a.get_text(strip=True), tipo="Casa", precio=num(precio.get_text()),
            colonia=colonia, cp=cp.group(1) if cp else None,
            m2_construccion=const, m2_terreno=terr, recamaras=rec, banos=ban,
        ))
    return filas, soup


def ml_page_url(u, off):
    head, _, rest = u.partition("gustavo-a-madero/")
    rest = rest.split("#")[0].lstrip("_")
    return f"{head}gustavo-a-madero/_Desde_{off}" + (f"_{rest}" if rest else "_NoIndex_True")


def scrape_ml(max_req=70):
    print("\n[Mercado Libre]")
    vistos, todas, req = set(), [], 0
    html = get_html(ML_BASE)
    if not html:
        return []
    filas, soup = parse_ml(html)
    total = re.search(r"(\d+)\s+Casas", soup.title.string if soup.title else "")
    total = int(total.group(1)) if total else 250
    print(f" total anunciado: {total}")

    # variantes: base, ordenamientos y filtros (facetas) tomados de la propia pagina
    variantes = [ML_BASE]
    variantes += [ML_BASE + s + "_NoIndex_True" for s in ("_OrderId_PRICE", "_OrderId_PRICE*DESC")]
    for a in soup.find_all("a", href=True):
        h = a["href"].split("#")[0]
        if h.startswith(ML_BASE + "_") and "NoIndex_True" in h and h not in variantes:
            variantes.append(h)
    print(f" variantes de URL a probar: {len(variantes)}")

    for v in variantes:
        if len(vistos) >= total * 0.97 or req >= max_req:
            break
        off = 1
        while req < max_req:
            url = v if off == 1 else ml_page_url(v, off)
            h = html if (url == ML_BASE and req == 0) else get_html(url)
            req += 1
            if not h:
                break
            fs, _ = parse_ml(h)
            nuevas = [f for f in fs if f["id"] not in vistos]
            for f in nuevas:
                vistos.add(f["id"])
                todas.append(f)
            print(f"  {url[-70:]:70s} -> {len(fs)} items, {len(nuevas)} nuevos | acumulado {len(vistos)}")
            if len(fs) < 48 or not nuevas:
                break  # fin de variante (o paginacion ignorada)
            off += 48
            pausa()
        pausa()
    return todas


# ------------------------------------------------------------------- TROVIT
TROVIT_BASE = "https://casas.trovit.com.mx/gustavo-madero-casa"


def parse_trovit(html):
    soup = BeautifulSoup(html, "html.parser")
    filas = []
    for art in soup.select("article.snippet-listing"):
        a = art.select_one("a.js-listing")
        tipo = art.select_one(".address_property-type b")
        if not a or (tipo and tipo.get_text(strip=True).lower() != "casa"):
            continue
        precio = art.select_one(".price__actual")
        if not precio:
            continue
        rec = ban = m2 = None
        for li in art.select(".snippet-listing-content-header-icons li"):
            img = li.select_one("img")
            alt = (img.get("alt") or "").lower() if img else ""
            p = li.select_one("p")
            if not p:
                continue
            valor = num(p.find(string=True))
            if "rec" in alt:
                rec = valor
            elif "ba" in alt and "os" in alt:
                ban = valor
            elif re.search(r"m.{0,2}[²2]", p.get_text()):  # tolera 'm²' o 'mÂ²'
                m2 = valor
        desc = art.select_one(".snippet-listing-content-header-description p")
        url = a["href"].split("?")[0]
        filas.append(fila(
            fuente="trovit", id=art.get("data-retis-id") or url, url=url,
            titulo=a.get("title"), tipo="Casa", precio=num(precio.get_text()),
            m2_construccion=m2,  # Trovit no distingue construccion/terreno: se documenta
            recamaras=rec, banos=ban,
            texto=limpiar_texto(desc.get_text(" ", strip=True) if desc else None),
        ))
    return filas, soup


def scrape_trovit(max_pages=60):
    print("\n[Trovit]")
    vistos, todas = set(), []
    for n in range(1, max_pages + 1):
        url = TROVIT_BASE if n == 1 else f"{TROVIT_BASE}/{n}"
        h = get_html(url)
        if not h:
            break
        fs, _ = parse_trovit(h)
        nuevas = [f for f in fs if f["id"] not in vistos]
        for f in nuevas:
            vistos.add(f["id"])
            todas.append(f)
        print(f"  pag {n:2d}: {len(fs)} casas, {len(nuevas)} nuevas | acumulado {len(vistos)}")
        if not nuevas:
            break
        pausa()
    return todas


# --------------------------------------------------------------- CENTURY 21
C21_BASE = "https://century21mexico.com/casas-en-venta-en-mexico-ciudad-de-mexico-gustavo-a-madero"


def parse_c21(html):
    soup = BeautifulSoup(html, "html.parser")
    filas = []
    for card in soup.select(".property-card"):
        a = card.select_one("a.block.p-4")
        if not a:
            continue
        titulo = a.select_one("h3").get_text(strip=True)
        if re.search(r"departamento|terreno|local|oficina|bodega", titulo, re.I) and not re.search(r"casa", titulo, re.I):
            continue
        texto = a.get_text(" | ", strip=True)
        precio = re.search(r"\$\s?([\d,]+)\s*MXN", texto)
        if not precio:
            continue
        ubic = a.select_one("p.mt-1.text-xs")
        ubic = ubic.get_text(" ", strip=True) if ubic else ""
        colonia = ubic.split(",")[0].strip() if ubic else None
        rec = re.search(r"(\d+)\s*rec", texto)
        ban = re.search(r"([\d\.]+)\s*ba", texto)
        const = re.search(r"([\d,\.]+)\s*m²\s*const", texto)
        terr = re.search(r"([\d,\.]+)\s*m²\s*terr", texto)
        # el ultimo numero suelto de la tarjeta corresponde a estacionamientos
        park = re.search(r"\|\s*(\d+)\s*$", texto)
        href = a["href"]
        filas.append(fila(
            fuente="century21", id=href.rsplit("/", 1)[-1], url="https://century21mexico.com" + href,
            titulo=titulo, tipo="Casa", precio=num(precio.group(1)), colonia=colonia,
            m2_construccion=num(const.group(1)) if const else None,
            m2_terreno=num(terr.group(1)) if terr else None,
            recamaras=num(rec.group(1)) if rec else None,
            banos=num(ban.group(1)) if ban else None,
            estacionamientos=num(park.group(1)) if park else None,
        ))
    return filas, soup


def scrape_c21(max_pages=8):
    print("\n[Century 21]")
    vistos, todas = set(), []
    for n in range(1, max_pages + 1):
        url = C21_BASE if n == 1 else f"{C21_BASE}?page={n}"
        h = get_html(url)
        if not h:
            break
        fs, _ = parse_c21(h)
        nuevas = [f for f in fs if f["id"] not in vistos]
        for f in nuevas:
            vistos.add(f["id"])
            todas.append(f)
        print(f"  pag {n}: {len(fs)} casas, {len(nuevas)} nuevas | acumulado {len(vistos)}")
        if not nuevas:
            break
        pausa()
    return todas


# -------------------------------------------------------- CASAS Y TERRENOS
CYT_URL = "https://www.casasyterrenos.com/ciudad-de-mexico/gustavo-a-madero/casas/venta"


def parse_cyt(html):
    """Los datos viajan en el payload RSC de Next.js (self.__next_f.push)."""
    soup = BeautifulSoup(html, "html.parser")
    trozos = []
    for sc in soup.find_all("script"):
        s = (sc.string or "").strip()
        m = re.match(r'self\.__next_f\.push\(\[1,(".*")\]\)\s*;?$', s, re.S)
        if not m:
            continue
        try:
            trozos.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            continue
    full = "".join(trozos)
    i = full.find('"properties":[')
    if i < 0:
        return [], soup
    arr, _ = json.JSONDecoder().raw_decode(full[i + len('"properties":'):])
    filas = []
    for p in arr:
        if "Madero" not in (p.get("municipality") or "") or not p.get("isSale") or p.get("type") != "Casa":
            continue
        geo = p.get("_geo") or {}
        filas.append(fila(
            fuente="casasyterrenos", id=str(p["id"]),
            url="https://www.casasyterrenos.com" + (p.get("canonical") or ""),
            titulo=p.get("name"), tipo="Casa", precio=num(p.get("priceSale")),
            colonia=(p.get("neighborhood") or "").title(),
            m2_construccion=p.get("construction"), m2_terreno=p.get("surface"),
            recamaras=p.get("rooms"), banos=p.get("bathrooms"),
            estacionamientos=p.get("parkingLots"),
            lat=float(geo["lat"]) if geo.get("lat") else None,
            lon=float(geo["lng"]) if geo.get("lng") else None,
        ))  # NO se guarda 'broker' (datos de contacto)
    return filas, soup


def scrape_cyt():
    print("\n[Casas y Terrenos]")
    h = get_html(CYT_URL)
    fs = parse_cyt(h)[0] if h else []
    print(f"  {len(fs)} casas de GAM en la pagina inicial")
    return fs


# --------------------------------------------------------------------- MAIN
def guardar(nombre, filas):
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.DataFrame(filas, columns=COLUMNAS)
    df.to_csv(f"{OUT_DIR}/raw_{nombre}.csv", index=False, encoding="utf-8-sig")
    print(f"  -> data/raw_{nombre}.csv ({len(df)} filas)")
    return df


def modo_offline(carpeta):
    pruebas = {
        "mercadolibre.html": parse_ml, "trovit.html": parse_trovit,
        "century21.html": parse_c21, "casasyterrenos.html": parse_cyt,
    }
    for archivo, fn in pruebas.items():
        with open(os.path.join(carpeta, archivo), encoding="utf-8") as f:
            fs, _ = fn(f.read())
        df = pd.DataFrame(fs, columns=COLUMNAS)
        print(f"\n== {archivo}: {len(df)} filas")
        print(df.drop(columns=["url", "id", "texto", "fecha_recoleccion", "titulo"]).head(4).to_string())
        print("nulos por columna:\n", df.isna().sum()[df.isna().sum() > 0].to_dict())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", help="carpeta con HTML guardados para probar parsers")
    args = ap.parse_args()
    if args.offline:
        modo_offline(args.offline)
        sys.exit()

    dfs = []
    for nombre, fn in [("century21", scrape_c21), ("casasyterrenos", scrape_cyt),
                       ("mercadolibre", scrape_ml), ("trovit", scrape_trovit)]:
        try:
            dfs.append(guardar(nombre, fn()))
        except Exception as e:  # una fuente caida no debe tirar las demas
            print(f"!! {nombre} fallo: {e}")
    raw = pd.concat(dfs, ignore_index=True)
    raw.to_csv(f"{OUT_DIR}/dataset_raw.csv", index=False, encoding="utf-8-sig")
    print("\n===== RESUMEN =====")
    print(raw.groupby("fuente").size())
    print("TOTAL filas:", len(raw))