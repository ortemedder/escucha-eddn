#!/usr/bin/env python3
# relleno_eddn.py - rellena faccion.json con los datos reales de los ultimos dias, sacados del
# archivo de EDDN de la comunidad (https://edgalaxydata.space/EDDN, un archivo por dia y tipo de mensaje).
# Solo usa la libreria estandar de Python (3.8 o mas nuevo): vale en Windows y en la Orange Pi.
#
# PASO 1 (en el PC, tarda un rato):   python relleno_eddn.py descargar
#     -> crea relleno.json (pequeño) con, para cada sistema de CDSN:
#        visitas por dia (pilotos distintos), saltos por dia y hora, e influencia de CDSN en cada momento.
#     Si se corta, se vuelve a lanzar y sigue por el dia en que iba.
#
# PASO 2 (en la Orange Pi, con el escucha PARADO):   python3 relleno_eddn.py mezclar relleno.json faccion.json
#     -> mezcla sin borrar nada: en cada dia se queda con el numero mas alto, y añade al historico de
#        influencia los cambios anteriores a los que ya tenia. Guarda antes una copia (faccion.json.antes_relleno).
import argparse, bz2, json, os, re, shutil, subprocess, sys, time, urllib.error, urllib.request
from datetime import date, datetime, timedelta, timezone

FAC = "Caballeros de Sion"
DATOS = "https://raw.githubusercontent.com/ortemedder/cdsn-datos/main/faccion.json"
ARCHIVO = "https://edgalaxydata.space/EDDN"
UA = {"User-Agent": "cdsn-relleno/1.0 (escucha-eddn de Caballeros de Sion)"}
TIPOS = ["FSDJump", "Location", "CarrierJump"]          # con --atraques tambien Docked (mas visitas, mas descarga)
SENALES = "FSSSignalDiscovered"                         # v12.5: con --senales, zonas de conflicto y portanaves
NOMBRES = {SENALES: ["FSSSignalDiscovered", "Journal.FSSSignalDiscovered"]}   # nombres posibles del archivo (el primero que exista)
DIAS_HIST = 60                                           # v12.5: historial.json (rivales, zonas, portanaves): 60 dias
RE_CS = re.compile(r"\b([A-Z0-9]{3}-[A-Z0-9]{3})\b")
DIAS_TRAF, DIAS_HDIA, PUNTOS_HINF = 60, 28, 60           # los mismos limites que el escucha v11.3
RE_SIS = re.compile(rb'"StarSystem"\s*:\s*"((?:[^"\\]|\\.)*)"')


def dia(t):
    return time.strftime("%Y-%m-%d", time.gmtime(t))


def epoch(s):
    try:
        return int(datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
    except (TypeError, ValueError):
        return 0


def mb(n):
    return f"{n / 1048576:.0f} MB"


# ---------------------------------------------------------------- PASO 1: descargar
def mis_sistemas(origen):
    if origen and os.path.exists(origen):
        with open(origen, encoding="utf-8") as f:
            j = json.load(f)
    else:
        print("Leyendo la lista de sistemas de CDSN de GitHub...")
        with urllib.request.urlopen(urllib.request.Request(DATOS, headers=UA), timeout=60) as r:
            j = json.loads(r.read().decode("utf-8"))
    return sorted(n for n, v in (j.get("sistemas") or {}).items() if not v.get("fuera"))


def lineas(url):
    """Descarga un .jsonl.bz2 y va dando sus lineas sin guardarlo entero (ni en disco ni en memoria)."""
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        total = int(r.headers.get("Content-Length") or 0)
        dz, resto, leido, t0, aviso = bz2.BZ2Decompressor(), b"", 0, time.time(), 0
        while True:
            trozo = r.read(1 << 20)
            if not trozo:
                break
            leido += len(trozo)
            datos = resto + dz.decompress(trozo)
            *completas, resto = datos.split(b"\n")
            yield from completas
            if dz.eof and dz.unused_data:               # varios bloques bz2 seguidos en el mismo archivo
                d2 = dz.unused_data; dz = bz2.BZ2Decompressor(); resto += dz.decompress(d2)
            if time.time() - aviso > 5:
                aviso = time.time()
                pct = f" ({100 * leido / total:.0f} %)" if total else ""
                print(f"\r      {mb(leido)}{pct} · {leido / max(1, time.time() - t0) / 1048576:.1f} MB/s   ", end="", flush=True)
        if resto.strip():
            yield resto
    print("\r" + " " * 60 + "\r", end="")


def procesa_dia(d, tipos, sistemas, R, base):
    """Lee los mensajes de un dia y apunta lo de nuestros sistemas en R."""
    vistos, faltan = 0, 0
    t_dia = epoch(d + "T12:00:00")
    for tipo in tipos:
      for k_, nom in enumerate(NOMBRES.get(tipo) or ["Journal." + tipo]):
        url = f"{base}/{d[:7]}/{nom}-{d}.jsonl.bz2"
        print(f"   {tipo}: {url}")
        try:
            for ln in lineas(url):
                m = RE_SIS.search(ln)
                if not m:
                    continue
                try:
                    nombre = json.loads(b'"' + m.group(1) + b'"')
                except ValueError:
                    continue
                if nombre not in sistemas:
                    continue
                try:
                    e = json.loads(ln)
                except ValueError:
                    continue
                hdr, msg = e.get("header") or {}, e.get("message") or {}
                gv = hdr.get("gameversion") or ""
                if gv.startswith("3.") or "legacy" in gv.lower() or "/test" in (e.get("$schemaRef") or ""):
                    continue                             # galaxia antigua o pruebas (igual que el escucha)
                t = epoch(msg.get("timestamp")) or epoch(hdr.get("gatewayTimestamp"))
                if not t or abs(t - t_dia) > 36 * 3600:   # fecha basura (reloj mal o journal antiguo)
                    continue
                s = R.setdefault(nombre, {"trafico": {}, "hdia": {}, "inf": []})
                if tipo == SENALES:                      # v12.5: zonas de conflicto y portanaves (como el escucha)
                    for sg in msg.get("signals") or []:
                        nm = sg.get("SignalName") or ""
                        ts = epoch(sg.get("timestamp")) or t
                        if "Warzone_PointRace" in nm:
                            lv = "High" if "High" in nm else "Med" if "Med" in nm else "Low"
                            z = s.setdefault("zonas", {}).setdefault(dia(ts), [])
                            if lv not in z:
                                z.append(lv)
                        elif sg.get("SignalType") == "FleetCarrier" or (sg.get("IsStation") and RE_CS.search(nm)):
                            cs = RE_CS.search(nm)
                            if cs:
                                o = s.setdefault("pn", {}).get(cs.group(1)) or {"n": nm.replace(cs.group(1), "").strip(), "d": ts, "u": ts}
                                o["d"], o["u"] = min(o["d"], ts), max(o["u"], ts)
                                s["pn"][cs.group(1)] = o
                    vistos += 1
                    continue
                dd = dia(t)
                uid = str(hdr.get("uploaderID") or "")[:12]
                if uid:
                    ids = s["trafico"].setdefault(dd, [])
                    if uid not in ids:
                        ids.append(uid)
                if msg.get("event") == "FSDJump":        # saltos por dia y hora (como el mapa de horas)
                    h = s["hdia"].setdefault(dd, [0] * 24)
                    h[time.gmtime(t).tm_hour] += 1
                facs = msg.get("Factions") or []
                infs = [x.get("Influence") for x in facs]
                if facs and all(isinstance(v, (int, float)) for v in infs) and 0.97 <= sum(infs) <= 1.03:
                    me = next((x for x in facs if x.get("Name") == FAC), None)
                    if me is not None:
                        s["inf"].append([t, round(me["Influence"] * 100, 2)])
                        rv = s.setdefault("rivs", {})     # v12.5: influencia de las otras facciones del sistema
                        for x in facs:
                            nx, vx = x.get("Name"), round((x.get("Influence") or 0) * 100, 2)
                            if nx and nx != FAC and vx > 0:
                                pts = rv.setdefault(nx, [])
                                if not pts or pts[-1][1] != vx:
                                    pts.append([t, vx])
                vistos += 1
        except urllib.error.HTTPError as e:
            if k_ + 1 < len(NOMBRES.get(tipo) or [1]):
                continue                                 # v12.5: se prueba el otro nombre
            print(f"      no está ({e.code}); se salta")
            if tipo != SENALES:
                faltan += 1
            break
        except Exception as e:                           # corte de red: se cuenta como no hecho
            print(f"      fallo: {e}")
            return None
        break
    if faltan == len([x for x in tipos if x != SENALES]):
        return -1                                        # el archivo aun no ha publicado ese dia
    return vistos


def descargar(a):
    sistemas = set(mis_sistemas(a.lista))
    print(f"{len(sistemas)} sistemas de CDSN")
    hoy = datetime.now(timezone.utc).date()
    dias = [(hoy - timedelta(days=k)).isoformat() for k in range(a.dias, 0, -1)]   # hasta ayer (hoy aun no esta entero)
    tipos = TIPOS + (["Docked"] if a.atraques else []) + ([SENALES] if a.senales else [])
    R = {"faccion": FAC, "hechos": [], "tipos": tipos, "sistemas": {}}
    if os.path.exists(a.salida) and not a.rehacer:
        with open(a.salida, encoding="utf-8") as f:
            R = json.load(f)
        con = {d for x in R["sistemas"].values() for d in x.get("trafico", {})}   # dias que de verdad trajeron datos
        vacios = [d for d in R["hechos"] if d not in con]
        if vacios:                                       # versiones anteriores daban por hechos los dias aun no publicados
            R["hechos"] = [d for d in R["hechos"] if d in con]
            print(f"{len(vacios)} días sin datos se volverán a intentar: {', '.join(vacios)}")
        print(f"Sigo donde lo dejé: {len(R['hechos'])} días ya hechos")
    t0 = time.time()
    for k, d in enumerate(dias, 1):
        if d in R["hechos"]:
            continue
        print(f"[{k}/{len(dias)}] {d}")
        n = procesa_dia(d, tipos, sistemas, R["sistemas"], a.url.rstrip("/"))
        if n is None:
            print("   se ha cortado: vuelve a lanzar el script y seguirá por este día")
            break
        if n == -1:
            print("   ese día aún no está en el archivo (lo publican con retraso); se intentará la próxima vez")
            continue
        R["hechos"].append(d)
        tmp = a.salida + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(R, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, a.salida)
        print(f"   {n} mensajes de nuestros sistemas · llevas {(time.time() - t0) / 60:.0f} min")
    print(f"\nHecho: {len(R['hechos'])} de {len(dias)} días en {a.salida} ({os.path.getsize(a.salida) // 1024 if os.path.exists(a.salida) else 0} KB).")
    print("Ahora pásalo a la Orange Pi y haz el paso 2 (mezclar).")


# ---------------------------------------------------------------- PASO 2: mezclar
def escucha_en_marcha():
    try:
        return subprocess.run(["systemctl", "is-active", "--quiet", "escucha-eddn"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except OSError:
        return False


def cambios(puntos):
    """De todos los datos de influencia, solo los momentos en que cambia (como el hinf del escucha)."""
    out = []
    for t, v in sorted(puntos):
        if not out or abs(out[-1][1] - v) >= 0.01:
            out.append([int(t), v])
    return out


def juntar_hinf(h, puntos):
    """Junta el historico que habia con los datos del archivo, por orden de hora, y se queda con los cambios.
    El ultimo punto que habia (el valor actual) se respeta siempre."""
    if not puntos:
        return h
    fin = h[-1][0] if h else 10 ** 12
    todo = sorted([list(p) for p in h] + [[int(t), v] for t, v in puntos if t < fin])
    limpio = []
    for p in todo:
        if not limpio or abs(p[1] - limpio[-1][1]) >= 0.01:
            limpio.append(p)
    if h and limpio[-1] != h[-1]:
        limpio.append(list(h[-1]))
    return limpio[-PUNTOS_HINF:]


def juntar_puntos(h, puntos, desde):
    """v12.5: como juntar_hinf, pero se queda con lo de despues de 'desde' (y siempre con el ultimo punto)."""
    nuevo = cambios(puntos)
    if h:                                                # como juntar_hinf, sin cortar a 60 puntos: aqui manda la fecha
        fin = h[-1][0]
        todo = sorted([list(p) for p in h] + [[int(t), v] for t, v in puntos if t < fin])
        nuevo = []
        for p in todo:
            if not nuevo or abs(p[1] - nuevo[-1][1]) >= 0.01:
                nuevo.append(p)
        if nuevo[-1] != list(h[-1]):
            nuevo.append(list(h[-1]))
    viejo = [p for p in nuevo if p[0] < desde]
    nuevo = ([viejo[-1]] if viejo else []) + [p for p in nuevo if p[0] >= desde]   # el valor de hace 60 dias sirve de inicio
    return nuevo


def mezcla_historial(H, R, sistemas_vivos):
    """v12.5: mete en H (historial.json) los rivales, zonas y portanaves del relleno R. Devuelve (puntos, zonas, portanaves) nuevos."""
    desde = int(time.time()) - DIAS_HIST * 86400
    lim = dia(desde)
    nr = nz = npn = 0
    for n, r in (R.get("sistemas") or {}).items():
        if n not in sistemas_vivos:
            continue
        hr = H.setdefault("rivales", {}).setdefault(n, {})
        for f_, pts in (r.get("rivs") or {}).items():
            h = hr.get(f_) or []
            nuevo = juntar_puntos(h, pts, desde)
            if nuevo != h:
                nr += len([p for p in nuevo if p not in h])
                hr[f_] = nuevo
        hz = H.setdefault("zonas", {}).setdefault(n, {})
        for d, lv in (r.get("zonas") or {}).items():
            if d > lim:
                o = hz.get(d) or []
                u = sorted(set(o) | set(lv), key=["High", "Med", "Low"].index)
                if u != o:
                    hz[d] = u; nz += 1
        hp = H.setdefault("portanaves", {}).setdefault(n, {})
        for cs, v in (r.get("pn") or {}).items():
            o = hp.get(cs)
            if not o:
                if v["u"] >= desde:
                    hp[cs] = dict(v); npn += 1
            elif v["d"] < o["d"] or v["u"] > o["u"]:
                o["d"], o["u"] = min(o["d"], v["d"]), max(o["u"], v["u"])
    for k in ("rivales", "zonas", "portanaves"):          # fuera los vacios
        H[k] = {n: v for n, v in (H.get(k) or {}).items() if v}
    return nr, nz, npn


def mezclar(a):
    if escucha_en_marcha() and not a.forzar:
        sys.exit("El escucha está en marcha: páralo antes con  systemctl stop escucha-eddn  (si no, lo machacaría al guardar).")
    with open(a.relleno, encoding="utf-8") as f:
        R = json.load(f)
    with open(a.faccion, encoding="utf-8") as f:
        D = json.load(f)
    shutil.copy2(a.faccion, a.faccion + ".antes_relleno")
    traf_f = os.path.join(os.path.dirname(os.path.abspath(a.faccion)), "trafico.json")
    try:
        with open(traf_f, encoding="utf-8") as f:
            TRAF = json.load(f)
    except (OSError, ValueError):
        TRAF = None
    tot = {"sis": 0, "traf": 0, "hdia": 0, "hinf": 0}
    for n, s in (D.get("sistemas") or {}).items():
        r = (R.get("sistemas") or {}).get(n)
        if not r or s.get("fuera"):
            continue
        tot["sis"] += 1
        # visitas: por cada dia, el numero mas alto (el archivo o lo que ya vio el escucha)
        tr = dict(s.get("trafico") or {})
        for d, ids in r.get("trafico", {}).items():
            if len(ids) > tr.get(d, 0):
                tr[d] = len(ids); tot["traf"] += 1
        lim = (datetime.now(timezone.utc).date() - timedelta(days=DIAS_TRAF)).isoformat()
        s["trafico"] = dict(sorted((k, v) for k, v in tr.items() if k > lim))   # fuera las fechas basura y lo de mas de 60 dias
        # los ids de los ultimos 9 dias tambien van a trafico.json, para que el escucha siga contando bien hoy
        if TRAF is not None:
            dd = TRAF.setdefault(n, {})
            for d in list(dd) + [d for d in r.get("trafico", {}) if d in s["trafico"]]:
                if d in r.get("trafico", {}):
                    dd[d] = sorted(set(dd.get(d) or []) | set(r["trafico"][d]))
            for d in sorted(dd)[:-9]:
                dd.pop(d, None)
        # saltos por dia y hora: el mas alto de cada hora
        hd = {k: list(v) for k, v in (s.get("hdia") or {}).items()}
        for d, h in r.get("hdia", {}).items():
            o = hd.get(d) or [0] * 24
            nuevo = [max(x, y) for x, y in zip(o, h)]
            if nuevo != o:
                hd[d] = nuevo; tot["hdia"] += 1
        lim = (datetime.now(timezone.utc).date() - timedelta(days=DIAS_HDIA)).isoformat()
        s["hdia"] = dict(sorted((k, v) for k, v in hd.items() if k > lim))
        # historico de influencia: se juntan los cambios del archivo con los que ya habia (tambien en los huecos)
        h = [list(x) for x in s.get("hinf") or []]
        nuevo = juntar_hinf(h, r.get("inf", []))
        if nuevo != h:
            tot["hinf"] += len([p for p in nuevo if p not in h])
            s["hinf"] = nuevo
    hist_f = os.path.join(os.path.dirname(os.path.abspath(a.faccion)), "historial.json")   # v12.5
    try:
        with open(hist_f, encoding="utf-8") as f:
            H = json.load(f)
    except (OSError, ValueError):
        H = {}
    vivos = {n for n, s in (D.get("sistemas") or {}).items() if not s.get("fuera")}
    nr, nz, npn = mezcla_historial(H, R, vivos)
    with open(hist_f + ".tmp", "w", encoding="utf-8") as f:
        json.dump(H, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(hist_f + ".tmp", hist_f)
    print(f"Historial: {nr} puntos de rivales, {nz} días con zonas de conflicto, {npn} portanaves.")
    with open(a.faccion + ".tmp", "w", encoding="utf-8") as f:
        json.dump(D, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(a.faccion + ".tmp", a.faccion)
    if TRAF is not None:
        with open(traf_f + ".tmp", "w", encoding="utf-8") as f:
            json.dump(TRAF, f)
        os.replace(traf_f + ".tmp", traf_f)
    print(f"Mezclado en {tot['sis']} sistemas: {tot['traf']} días de visitas mejorados, {tot['hdia']} días del mapa de horas, "
          f"{tot['hinf']} puntos de influencia añadidos.")
    print(f"Copia del archivo anterior: {a.faccion}.antes_relleno")
    print("Ahora arranca el escucha:  systemctl start escucha-eddn")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Relleno de faccion.json con el archivo de EDDN (edgalaxydata.space)")
    sp = p.add_subparsers(dest="modo", required=True)
    d = sp.add_parser("descargar", help="PASO 1 (en el PC): descarga y crea relleno.json")
    d.add_argument("--dias", type=int, default=60, help="días hacia atrás (60 por defecto)")
    d.add_argument("--atraques", action="store_true", help="leer también los atraques (más visitas, mucha más descarga)")
    d.add_argument("--senales", action="store_true", help="leer también las señales: zonas de conflicto y portanaves (v12.5)")
    d.add_argument("--salida", default="relleno.json")
    d.add_argument("--lista", help="faccion.json local para sacar la lista de sistemas (si no, se baja de GitHub)")
    d.add_argument("--url", default=ARCHIVO, help=argparse.SUPPRESS)
    d.add_argument("--rehacer", action="store_true", help="empezar de cero aunque ya haya un relleno.json")
    m = sp.add_parser("mezclar", help="PASO 2 (en la Orange Pi, con el escucha parado)")
    m.add_argument("relleno"); m.add_argument("faccion")
    m.add_argument("--forzar", action="store_true", help=argparse.SUPPRESS)
    a = p.parse_args()
    try:
        descargar(a) if a.modo == "descargar" else mezclar(a)
    except KeyboardInterrupt:
        print("\nParado. Si vuelves a lanzarlo, sigue por donde iba.")
