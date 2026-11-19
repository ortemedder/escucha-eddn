#!/usr/bin/env python3
# Escucha de EDDN para el Panel Elite: guarda el estado de una faccion en todos sus sistemas
# y lo ofrece en la red de casa en http://<IP>:8090/faccion.json
# - EDDN en directo (solo galaxia actual, no Legacy)
# - EDSM cada 6 h para los sistemas de los que no llega nada
# Configuracion: config.json junto a este archivo.
VERSION = "v10"                  # v10: dia y fase de cada conflicto, resultado diario, en juego, historial de conflictos,
                                 #      quien sube cuando bajamos, vigilancia de rivales y avisos de conflicto a Discord
                                 # v9: posibles ataques por pico de visitas (aviso por Discord e historial)
                                 # v8: rivales, estaciones, mercado, atraques, saltos, rutas, expansion y codice
import base64, calendar, hashlib, json, math, os, threading, time, urllib.error, urllib.request, urllib.parse, zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = {"faccion": "Caballeros de Sion", "puerto": 8090, "edsm_horas": 6, "github": "ortemedder/cdsn-datos",
       "github_min": 15, "resumen_hora": 21, "expansion_ly": 20}
try:
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        CFG.update(json.load(f))
except (OSError, ValueError):
    pass
FAC = CFG["faccion"]
DATA_FILE = os.path.join(HERE, "faccion.json")
SYS_FILE = os.path.join(HERE, "sistemas.txt")
lock = threading.Lock()
DB = {"ver": VERSION, "faccion": FAC, "sistemas": {}, "eddn": {"ok": False, "ultimo": 0, "msgs": 0, "mios": 0}, "t": 0}
dirty = [False]

def log(*a):
    print(time.strftime("%d/%m %H:%M:%S"), *a, flush=True)

def load():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            j = json.load(f)
        if j.get("faccion") == FAC:
            DB["sistemas"] = j.get("sistemas") or {}
            if j.get("tick_global"): DB["tick_global"] = j["tick_global"]
            if j.get("thargoides"): DB["thargoides"] = j["thargoides"]
            for k_ in ("expansion", "codice", "ataques", "conflictos_hist", "rivales"):   # v8 / v9 / v10
                if j.get(k_): DB[k_] = j[k_]
    except (OSError, ValueError):
        pass
    try:
        with open(SYS_FILE, encoding="utf-8") as f:
            for l in f:
                n = l.strip()
                if n and not n.startswith("#") and n not in DB["sistemas"]:
                    DB["sistemas"][n] = {"sys": n, "t": 0}
    except OSError:
        pass

def save():
    with lock:
        DB["t"] = time.time()
        txt = json.dumps(DB, ensure_ascii=False, separators=(",", ":"))
        dirty[0] = False
    with open(DATA_FILE + ".tmp", "w", encoding="utf-8") as f:
        f.write(txt)
    os.replace(DATA_FILE + ".tmp", DATA_FILE)

def iso2epoch(s):
    try:
        return calendar.timegm(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return 0

def update(sysname, t, facs, ctrl_name, src, conflicts=(), extra=None):
    """facs: lista de dicts con Name, Influence (0..1), FactionState, ActiveStates... (formato journal)."""
    facs = sorted(facs, key=lambda x: -(x.get("Influence") or 0))
    me = next((x for x in facs if x.get("Name") == FAC), None)
    with lock:
        old = DB["sistemas"].get(sysname)
        if old and old.get("t", 0) >= t:                 # ya tengo un dato igual o mas nuevo:
            fill = {}                                    # solo se completa lo que le falte (datos de la v1)
            if old.get("todas") is None and me:
                fill["todas"] = [{"n": x.get("Name"), "inf": round((x.get("Influence") or 0) * 100, 2), "gov": x.get("Government") or "",
                                  "alg": x.get("Allegiance") or "", "act": [y.get("State") for y in x.get("ActiveStates") or [] if y.get("State")],
                                  "pend": [y.get("State") for y in x.get("PendingStates") or [] if y.get("State")],
                                  "jug": x.get("isPlayer")} for x in facs if (x.get("Influence") or 0) > 0]
                fill["ctrl_n"] = ctrl_name or ""
            for k_ in ("pos", "sis", "pp"):
                if not old.get(k_) and (extra or {}).get(k_):
                    fill[k_] = extra[k_]
            if fill:
                old.update(fill); dirty[0] = True
            return False
        if not me:
            if old and old.get("inf") is not None:
                DB["sistemas"][sysname] = {"sys": sysname, "t": t, "src": src, "fuera": True, "inf": 0}
                dirty[0] = True
                log("¡", FAC, "ya no está en", sysname, "!")
                discord(f"⚠️ **{FAC}** ya no está en **{sysname}**")
            return False
        inf = round((me.get("Influence") or 0) * 100, 2)
        sec = next((x for x in facs if x.get("Name") != FAC), {})
        st = lambda k: [x.get("State") for x in me.get(k) or [] if x.get("State")]
        con = [{"tipo": c.get("WarType"), "estado": c.get("Status"),
                "contra": (c["Faction2"] if c["Faction1"].get("Name") == FAC else c["Faction1"]).get("Name"),
                "ganados": (c["Faction1"] if c["Faction1"].get("Name") == FAC else c["Faction2"]).get("WonDays"),
                "perdidos": (c["Faction2"] if c["Faction1"].get("Name") == FAC else c["Faction1"]).get("WonDays"),
                "en_juego": (c["Faction1"] if c["Faction1"].get("Name") == FAC else c["Faction2"]).get("Stake") or "",      # v10: lo que perdemos si perdemos
                "en_juego_rival": (c["Faction2"] if c["Faction1"].get("Name") == FAC else c["Faction1"]).get("Stake") or ""}   # v10: lo que ganamos si ganamos
               for c in conflicts or [] if FAC in ((c.get("Faction1") or {}).get("Name"), (c.get("Faction2") or {}).get("Name"))]
        if src != "EDDN" and (old or {}).get("conflictos"):
            con = old["conflictos"]                      # v10: EDSM no trae conflictos; se conservan los de EDDN
        new = {"sys": sysname, "t": t, "src": src, "inf": inf, "ctrl": ctrl_name == FAC,
               "estado": me.get("FactionState") or "None", "activos": st("ActiveStates"), "pendientes": st("PendingStates"),
               "recuperando": st("RecoveringStates"), "segunda": sec.get("Name") or "",
               "segunda_inf": round((sec.get("Influence") or 0) * 100, 2), "conflictos": con,
               "todas": [{"n": x.get("Name"), "inf": round((x.get("Influence") or 0) * 100, 2), "gov": x.get("Government") or "",
                          "alg": x.get("Allegiance") or "", "act": [y.get("State") for y in x.get("ActiveStates") or [] if y.get("State")],
                          "pend": [y.get("State") for y in x.get("PendingStates") or [] if y.get("State")],
                          "jug": x.get("isPlayer")} for x in facs if (x.get("Influence") or 0) > 0],
               "ctrl_n": ctrl_name or ""}
        for k_ in ("pos", "sis", "pp"):                  # lo que no traiga este dato se conserva del anterior
            v_ = (extra or {}).get(k_) or (old or {}).get(k_)
            if v_:
                new[k_] = v_
        for k_ in ("trafico", "zc", "pn", "tk", "thargoid", "saltos", "rutas", "estaciones", "cseg", "sube_cuando_baja"):  # actividad: siempre se conserva
            if (old or {}).get(k_):
                new[k_] = old[k_]
        if old and old.get("inf") is not None and abs(old["inf"] - inf) >= 0.01:
            new["prev"], new["prev_t"] = old["inf"], old.get("t")
        elif old:
            new["prev"], new["prev_t"] = old.get("prev"), old.get("prev_t")
        # historico de influencia (v5): un punto cada vez que cambia, los ultimos 14
        h = [list(x) for x in (old or {}).get("hinf") or []]
        if not h and old and old.get("inf") is not None:
            if old.get("prev") is not None and old.get("prev_t"):
                h.append([int(old["prev_t"]), old["prev"]])
            h.append([int(old.get("t") or t), old["inf"]])
        if not h or abs(h[-1][1] - inf) >= 0.01:
            h.append([int(t), inf])
        new["hinf"] = h[-14:]
        # rivales (v8): ticks seguidos que sube cada faccion del sistema
        rach = dict((old or {}).get("rach") or {})
        o_inf = {x.get("n"): x.get("inf") or 0 for x in (old or {}).get("todas") or []}
        if o_inf and any(abs(o_inf.get(x["n"], -1) - x["inf"]) >= 0.01 for x in new["todas"]):
            for x in new["todas"]:
                d_ = x["inf"] - o_inf.get(x["n"], x["inf"])
                rach[x["n"]] = rach.get(x["n"], 0) + 1 if d_ >= 0.1 else 0 if d_ <= -0.1 else rach.get(x["n"], 0)
        nombres = {x["n"] for x in new["todas"]}
        new["rach"] = {k: v for k, v in rach.items() if k in nombres}
        new["rivales"] = sorted([{"n": x["n"], "racha": new["rach"][x["n"]], "inf": x["inf"], "dif": round(x["inf"] - inf, 2)}
                                 for x in new["todas"] if x["n"] != FAC and new["rach"].get(x["n"], 0) >= 2], key=lambda r_: -r_["racha"])
        tick_track(sysname, new, src, t)
        msgs = conf_track(sysname, old, new, t, src)    # v10: dia, fase y resultado de cada conflicto
        msgs += quien_sube(sysname, old, new, o_inf, t, src)   # v10: quien sube cuando bajamos y rivales vigilados
        DB["sistemas"][sysname] = new
        dirty[0] = True
    for m_ in msgs:
        log(m_.replace("**", "")); discord(m_)
    avisos(sysname, old, new)
    return True


# ---------- tick de cada sistema (v4) ----------
# El BGS solo cambia la influencia en el tick. Si entre dos datos de EDDN cambian las influencias
# del sistema, el tick fue entre el ultimo dato igual ("igual") y el primero distinto (t).
# Se guardan las horas de los ultimos ticks bien acotados (ventana <= 6 h) y se calcula la hora habitual.
TICK_VENTANA = 6 * 3600          # ventanas cortas: cuentan como tick "bien acotado"
TICK_VENTANA_MAX = 20 * 3600     # ventanas de hasta 20 h: se cruzan entre dias para estrechar la hora

def _firma(todas):
    txt = ";".join(f"{x.get('n')}:{(x.get('inf') or 0):.1f}" for x in sorted(todas or [], key=lambda x: x.get("n") or ""))
    return hashlib.md5(txt.encode("utf-8")).hexdigest()[:8]

def _prevision(tk):
    """Cruza las ventanas de los ultimos dias (hora del dia) y se queda con el tramo en el que coinciden mas."""
    vent = tk.get("vent") or []
    if not vent:
        return None, None
    cuenta = [0.0] * 1440                                 # minutos del dia (UTC); las ventanas cortas pesan mas
    for a, b in vent:
        m0, largo = int(a % 86400) // 60, max(1, int(b - a) // 60)
        for k in range(min(largo, 1440)):
            cuenta[(m0 + k) % 1440] += 60.0 / largo
    top = max(cuenta)
    mejor, ini, run = (0, 0), None, 0                     # tramo mas largo con el maximo (circular)
    for k in range(2880):
        if cuenta[k % 1440] >= top - 1e-9:
            if ini is None: ini = k
            run = k - ini + 1
            if run > mejor[0] and run <= 1440: mejor = (run, ini)
        else:
            ini = None
    run, ini = mejor
    tod = ((ini + run / 2) % 1440) * 60                    # centro del tramo, en segundos UTC
    disp = int(run / 2)                                    # +- minutos
    base = (tk.get("ult") or vent[-1][1]) + 6 * 3600       # el siguiente, despues del ultimo visto
    nxt = (base // 86400) * 86400 + tod
    while nxt < base:
        nxt += 86400
    return int(nxt), disp

def tick_track(sysname, new, src, t):
    tk = dict(new.get("tk") or {})
    if src == "EDDN":                                     # EDSM no vale: su hora es la del ultimo informe
        firma = _firma(new.get("todas"))
        if tk.get("firma") and tk["firma"] != firma and tk.get("igual"):
            desde = tk["igual"]; ventana = t - desde
            tk["ult"], tk["desde"] = t, desde
            if ventana <= TICK_VENTANA_MAX:                # ventana para cruzar con otros dias
                vent = [v for v in tk.get("vent") or [] if t - v[1] < 14 * 86400]
                vent.append([int(desde), int(t)])
                tk["vent"] = vent[-7:]
            if ventana <= TICK_VENTANA:
                est = int(desde + ventana / 2)
                hist = [h for h in tk.get("hist") or [] if t - h < 14 * 86400]
                if not hist or est - hist[-1] > 12 * 3600:      # un tick por dia como mucho
                    hist.append(est)
                tk["hist"], tk["est"] = hist[-7:], est
            else:
                tk["est"] = None
            log(f"TICK {sysname}: entre {time.strftime('%d/%m %H:%M', time.localtime(desde))} y {time.strftime('%H:%M', time.localtime(t))}")
        tk["firma"], tk["igual"] = firma, t
    new["tk"] = tk
    # datos para los paneles: ultimo tick, margen (min) y proximo previsto
    if tk.get("ult"):
        new["tick_ult"] = tk.get("est") or tk["ult"]
        new["tick_marg"] = int((tk["ult"] - tk["desde"]) / 120) if tk.get("desde") else None
    prox, disp = _prevision(tk)
    if prox:
        new["tick_prox"], new["tick_disp"], new["tick_n"] = prox, disp, len(tk.get("hist") or [])

def _a_epoch(v):
    """La API puede dar texto ISO, un numero o un objeto: se acepta cualquiera."""
    if isinstance(v, dict):
        for k in ("lastGalaxyTick", "tick", "timestamp", "time", "date"):
            if v.get(k):
                return _a_epoch(v[k])
        return 0
    if isinstance(v, (int, float)):
        return int(v / 1000 if v > 1e12 else v)
    if isinstance(v, str):
        v = v.strip().strip('"')
        return int(float(v)) if v.replace(".", "").isdigit() else iso2epoch(v.replace(" ", "T"))
    return 0

def tick_global_loop():                                  # tick de la galaxia (comunidad EDCD), de respaldo
    time.sleep(5)
    log("Tick global: consultando tick.edcd.io")
    while True:
        try:
            req = urllib.request.Request("https://tick.edcd.io/api/tick", headers={"User-Agent": "PanelEliteRPi-escucha/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                crudo = r.read().decode()
            try:
                tg = _a_epoch(json.loads(crudo))
            except ValueError:
                tg = _a_epoch(crudo)
            if not tg:
                log("Tick global: respuesta no reconocida:", crudo[:120])
            elif tg != DB.get("tick_global"):
                with lock:
                    DB["tick_global"] = tg; dirty[0] = True
                log("Tick global:", time.strftime("%d/%m %H:%M", time.localtime(tg)))
                conf_tick(tg)                            # v10: pasa un dia en los conflictos activos
        except Exception as e:
            log("Tick global:", e)
        time.sleep(1800)

# ---------- avisos a Discord (opcional: discord_webhook.txt junto a este archivo) ----------
ES = {"Expansion": "Expansión", "War": "Guerra", "CivilWar": "Guerra civil", "Election": "Elecciones", "Retreat": "Retirada",
      "Boom": "Auge", "Bust": "Crisis", "Famine": "Hambruna", "Outbreak": "Epidemia", "Lockdown": "Confinamiento",
      "CivilUnrest": "Disturbios", "PirateAttack": "Ataque pirata", "Drought": "Sequía", "Blight": "Plaga",
      "InfrastructureFailure": "Fallo de infraestructura", "NaturalDisaster": "Desastre natural", "TerroristAttack": "Atentado",
      "CivilLiberty": "Libertad civil", "Investment": "Inversión", "PublicHoliday": "Festividad"}
DQ = []

DQL = threading.Lock()                           # cerrojo propio de la cola de Discord

def discord(txt):
    with DQL:
        DQ.append([txt, time.time(), 0])                 # texto, cuando se creo, cuando reintentar

def _dq_send(url, txt):
    """0 = enviado, segundos = reintentar tras esos segundos, -1 = no reintentar"""
    req = urllib.request.Request(url, data=json.dumps({"content": txt[:1900]}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "PanelEliteRPi-escucha/1.1"})
    try:
        urllib.request.urlopen(req, timeout=15).read()
        return 0
    except urllib.error.HTTPError as e:
        if e.code == 429:                                # Discord pide esperar
            try:
                w = float(json.loads(e.read().decode() or "{}").get("retry_after") or 0)
            except Exception:
                w = 0
            w = w or float(e.headers.get("Retry-After") or 5)
            log(f"Discord: limitado, espero {w:.0f} s")
            return max(1, w)
        if e.code in (401, 403, 404):
            log(f"Discord: el webhook no vale (HTTP {e.code}); revisa discord_webhook.txt")
            return -1
        log("Discord:", e)
        return 60
    except Exception as e:
        log("Discord:", e)
        return 60

def discord_loop():
    f = os.path.join(HERE, "discord_webhook.txt")
    while True:
        time.sleep(3)
        with DQL:
            if not DQ:
                continue
            for i, x in enumerate(DQ):                   # avisos antiguos en formato texto
                if isinstance(x, str):
                    DQ[i] = [x, time.time(), 0]
            now = time.time()
            DQ[:] = [x for x in DQ if now - x[1] < 3600 or log("Discord: aviso descartado tras 1 h sin poder enviarlo")]
            if not DQ or DQ[0][2] > now:
                continue
            item = DQ[0]
        try:
            url = open(f).read().strip()
        except OSError:
            url = ""
        if not url:
            with DQL:
                DQ.clear()                               # sin webhook: no se manda nada
            continue
        r = _dq_send(url, item[0])
        with DQL:
            if r == 0 or r < 0:
                if item in DQ:
                    DQ.remove(item)
                if r == 0:
                    log("Discord: enviado ·", item[0].split("\n")[0][:60])
            else:
                item[2] = time.time() + r                # el resto espera detras, en orden

def avisos(sysname, old, new):
    if not old or old.get("inf") is None or old.get("t", 0) == 0:
        if old is None and new.get("src") == "EDDN":
            discord(f"🆕 **{FAC}** aparece en **{sysname}** ({new['inf']:.1f} %)")
        return
    gap_o = old["inf"] - (old.get("segunda_inf") or 0)
    gap_n = new["inf"] - (new.get("segunda_inf") or 0)
    if new.get("ctrl") and gap_n < 5 <= gap_o:
        discord(f"🔻 **{sysname}**: ventaja de solo {gap_n:.1f} puntos sobre {new.get('segunda')}".replace(".", ","))
    if old.get("conflictos") and not new.get("conflictos"):
        c = old["conflictos"][0]
        g_, p_ = c.get("ganados") or 0, c.get("perdidos") or 0
        discord(f"🏁 **{sysname}**: terminó el conflicto contra **{c.get('contra')}** ({g_}-{p_} días, {'GANADO' if g_ > p_ else 'PERDIDO' if p_ > g_ else 'empate'})")
    if new.get("conflictos") and not old.get("conflictos"):
        c = new["conflictos"][0]
        tipo = {"war": "Guerra", "civilwar": "Guerra civil", "election": "Elecciones"}.get((c.get("tipo") or "").lower(), "Conflicto")
        discord(f"{'✉️' if (c.get('tipo') or '').lower() == 'election' else '⚔️'} **{sysname}**: {tipo} contra **{c.get('contra')}**")
    for r_ in new.get("rivales") or []:                  # v8: rival que sube 3 ticks seguidos
        if r_["racha"] == 3 and (old.get("rach") or {}).get(r_["n"], 0) == 2 and r_["dif"] > -15:
            discord(f"⬆️ **{sysname}**: **{r_['n']}** lleva 3 ticks seguidos subiendo ({r_['inf']:.1f} %, {r_['dif']:+.1f} sobre nosotros)".replace(".", ","))
    for k, lab in (("pendientes", "pendiente"), ("activos", "activo")):
        for st_ in set(new.get(k) or []) - set(old.get(k) or []):
            if st_ in ("Retreat", "Expansion", "War", "CivilWar", "Election"):
                discord(f"{'🚨' if st_ == 'Retreat' else '📣'} **{sysname}**: {ES.get(st_, st_)} {lab}")

def resumen():
    with lock:
        S = [v for v in DB["sistemas"].values() if v.get("inf") and not v.get("fuera")]
    S.sort(key=lambda v: (not v.get("ctrl"), -(v.get("inf") or 0)))
    L = [f"📊 **{FAC}** · {sum(1 for v in S if v.get('ctrl'))} controlados · {len(S)} sistemas"]
    for v in S:
        gap = v["inf"] - (v.get("segunda_inf") or 0)
        tr = v["inf"] - v["prev"] if v.get("prev") is not None else 0
        est = ", ".join([ES.get(x, x) for x in v.get("activos") or []] + [ES.get(y, y) + " (pend.)" for y in v.get("pendientes") or []]
                        + (["👾 " + TG_ES.get(v["thargoid"].get("estado"), v["thargoid"].get("estado"))] if (v.get("thargoid") or {}).get("estado") else []))
        L.append((f"{'🏰' if v.get('ctrl') else '·'} {v['sys']}: {v['inf']:.1f} % ({'+' if gap >= 0 else ''}{gap:.1f})"
                  + (f" {'▲' if tr > 0 else '▼'}{abs(tr):.1f}" if abs(tr) >= 0.1 else "")).replace(".", ",") + (f" · {est}" if est else ""))
    discord("\n".join(L))

def resumen_loop():
    hecho = None
    while True:
        time.sleep(60)
        lt = time.localtime()
        if lt.tm_hour == CFG["resumen_hora"] and hecho != lt.tm_yday:
            hecho = lt.tm_yday
            resumen()

# ---------- subida a GitHub (todos los paneles leen de ahi) ----------
def gh_loop():
    tf = os.path.join(HERE, "github_token.txt")
    last_h, last_t = None, 0
    api = f"https://api.github.com/repos/{CFG['github']}/contents/faccion.json"
    time.sleep(60)
    while True:
        try:
            token = open(tf).read().strip()
        except OSError:
            token = ""
        if token:
            with lock:
                h = hashlib.md5((json.dumps(DB["sistemas"], sort_keys=True) + str(DB.get("tick_global")) + json.dumps(DB.get("thargoides"), sort_keys=True)
                                 + json.dumps(DB.get("expansion"), sort_keys=True) + json.dumps(DB.get("codice"), sort_keys=True)
                                 + json.dumps(DB.get("ataques"), sort_keys=True) + json.dumps(DB.get("conflictos_hist"), sort_keys=True)
                                 + json.dumps(DB.get("rivales"), sort_keys=True)).encode()).hexdigest()
                body = json.dumps(DB, ensure_ascii=False, indent=1)
            if h != last_h or time.time() - last_t > 6 * 3600:
                hdr = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                       "User-Agent": "PanelEliteRPi-escucha/1.0", "X-GitHub-Api-Version": "2022-11-28"}
                try:
                    sha = None
                    try:
                        with urllib.request.urlopen(urllib.request.Request(api, headers=hdr), timeout=20) as r:
                            sha = json.loads(r.read().decode()).get("sha")
                    except urllib.error.HTTPError as e:
                        if e.code != 404:
                            raise
                    put = {"message": "Datos " + time.strftime("%d/%m/%Y %H:%M"),
                           "content": base64.b64encode(body.encode("utf-8")).decode()}
                    if sha:
                        put["sha"] = sha
                    req = urllib.request.Request(api, data=json.dumps(put).encode(), headers=hdr, method="PUT")
                    urllib.request.urlopen(req, timeout=30).read()
                    last_h, last_t = h, time.time()
                    log("GitHub: faccion.json subido")
                except Exception as e:
                    log("GitHub:", e)
        time.sleep(CFG["github_min"] * 60)


# ---------- actividad (v3): trafico, zonas de conflicto, portanaves y Powerplay de alrededor ----------
import math, re as _re
FAC_B = FAC.encode("utf-8")
NAMES = {"b": [], "t": 0}
TRAF_FILE = os.path.join(HERE, "trafico.json")
try:
    with open(TRAF_FILE, encoding="utf-8") as _f:
        TRAF = {k: {d: set(v) for d, v in dd.items()} for k, dd in json.load(_f).items()}
except (OSError, ValueError):
    TRAF = {}
CALLSIGN = _re.compile(r"\b([A-Z0-9]{3}-[A-Z0-9]{3})\b")
ZONA_LY = 20.0

def mis_sistemas():
    if time.time() - NAMES["t"] > 60:
        with lock:
            NAMES["b"] = [(n.encode("utf-8"), n) for n, v in DB["sistemas"].items() if not v.get("fuera")]
            NAMES["tg"] = [n.encode("utf-8") for n in DB.get("thargoides") or {}]
            NAMES["mid"] = {e.get("mid"): (n, en) for n, v in DB["sistemas"].items() if not v.get("fuera")
                            for en, e in (v.get("estaciones") or {}).items() if e.get("mid")}
        NAMES["t"] = time.time()
    return NAMES["b"]

def cerca(pos):
    if not pos:
        return False
    with lock:
        P_ = [v.get("pos") for v in DB["sistemas"].values() if v.get("pos") and not v.get("fuera")]
    return any(math.dist(pos, q) <= ZONA_LY for q in P_ if None not in q)

def traf_save():
    try:
        with open(TRAF_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump({k: {d: sorted(v) for d, v in dd.items()} for k, dd in TRAF.items()}, f)
        os.replace(TRAF_FILE + ".tmp", TRAF_FILE)
    except OSError as e:
        log("trafico:", e)

# ---------- guerra thargoide (v7) ----------
# Los FSDJump/Location/CarrierJump traen "ThargoidWar" si el sistema esta en guerra con los thargoides.
# Sistemas propios: campo "thargoid" en el sistema. Sistemas a menos de 20 al: DB["thargoides"].
TG_ES = {"Thargoid_Probing": "Alerta", "Thargoid_Harvest": "Invasión", "Thargoid_Controlled": "Controlado",
         "Thargoid_Stronghold": "Fortaleza titán", "Thargoid_Recovery": "Recuperación"}

def _tg_dato(tw, t):
    return {"estado": tw.get("CurrentState") or "", "exito": tw.get("NextStateSuccess") or "",
            "fallo": tw.get("NextStateFailure") or "", "logrado": bool(tw.get("SuccessStateReached")),
            "prog": round((tw.get("WarProgress") or 0) * 100, 1), "puertos": tw.get("RemainingPorts"),
            "quedan": tw.get("EstimatedRemainingTime") or "", "t": t}

def _mas_cerca(pos):
    """(distancia, sistema propio mas cercano) o None"""
    with lock:
        P_ = [(n, v["pos"]) for n, v in DB["sistemas"].items() if v.get("pos") and not v.get("fuera") and None not in v["pos"]]
    return min(((math.dist(pos, q), n) for n, q in P_), default=None)

def thargoides(sname, m, mine, t):
    tw = m.get("ThargoidWar") or {}
    est = tw.get("CurrentState") or ""
    pos = m.get("StarPos")
    lab = TG_ES.get(est, est)
    extra = f" · progreso {tw.get('WarProgress', 0) * 100:.0f} %".replace(".", ",") if est and tw.get("WarProgress") is not None else ""
    aviso = None
    if mine and not mine.get("fuera"):
        with lock:
            o = mine.get("thargoid") or {}
            if o.get("t", 0) > t:
                return                                   # dato mas viejo que el que tengo
            old = o.get("estado") or ""
            if est:
                mine["thargoid"] = _tg_dato(tw, t); dirty[0] = True
            elif o:
                mine.pop("thargoid", None); dirty[0] = True
        if est != old:
            aviso = f"👾 **{sname}**: " + (f"thargoides · {lab}{extra}" if est else "ya no hay thargoides")
    elif sname and pos and None not in pos:
        with lock:
            z = DB.setdefault("thargoides", {})
            o = z.get(sname) or {}
        if o.get("t", 0) > t:
            return
        if not est:
            if o:
                with lock:
                    z.pop(sname, None); dirty[0] = True
                NAMES["t"] = 0
                aviso = f"👾 **{sname}** (a {o.get('ly')} al de {o.get('junto')}): ya no hay thargoides"
        else:
            mc = _mas_cerca(pos)
            if not mc or mc[0] > ZONA_LY:
                return
            with lock:
                z[sname] = dict(_tg_dato(tw, t), pos=pos, junto=mc[1], ly=round(mc[0], 1)); dirty[0] = True
            if not o:
                NAMES["t"] = 0
            if est != (o.get("estado") or ""):
                aviso = f"👾 Thargoides a {mc[0]:.0f} al de **{mc[1]}**: {lab} en **{sname}**{extra}"
    if aviso:
        log(aviso.replace("**", ""))
        discord(aviso)

# ---------- filtro de datos sospechosos (v6) ----------
# Cualquiera puede mandar mensajes a EDDN. Antes de aceptar un dato se comprueba que tenga sentido;
# si es raro se descarta, y si es un salto grande de influencia se espera a que otro piloto lo confirme.
SALTO_MAX = 20.0                 # puntos de influencia de CDSN entre dos datos de menos de 48 h
SOSP = {}                        # sistema -> {"firma", "uid", "t"} dato raro esperando confirmacion
_avisado = {}                    # sistema -> hora del ultimo aviso (uno cada 6 h como mucho)

def aviso_sosp(sname, motivo):
    with lock:
        DB["eddn"]["descartados"] = DB["eddn"].get("descartados", 0) + 1
    log(f"Dato sospechoso en {sname}: {motivo}")
    if time.time() - _avisado.get(sname, 0) > 6 * 3600:
        _avisado[sname] = time.time()
        discord(f"🛡️ **{sname}**: dato de EDDN descartado por sospechoso ({motivo})")

def sospechoso(sname, m, hdr, t, mine):
    """Devuelve el motivo si el dato no es fiable, o None si se puede usar."""
    if t > time.time() + 600:
        return "fecha en el futuro"
    facs = m.get("Factions") or []
    infs = [x.get("Influence") for x in facs]
    if any(not isinstance(v, (int, float)) or v < 0 or v > 1 for v in infs):
        return "influencias fuera de rango"
    if facs and not 0.97 <= sum(infs) <= 1.03:
        return f"las influencias suman {sum(infs) * 100:.0f} %"
    if len({x.get("Name") for x in facs}) != len(facs):
        return "facciones repetidas"
    if not mine or mine.get("fuera"):
        return None
    pos, p0 = m.get("StarPos"), mine.get("pos")
    if pos and p0 and max(abs(a - b) for a, b in zip(pos, p0)) > 1:
        return "el sistema ha cambiado de coordenadas"
    me = next((x for x in facs if x.get("Name") == FAC), None)
    if me is None or mine.get("inf") is None:
        return None
    salto = abs(me["Influence"] * 100 - mine["inf"])
    if salto < SALTO_MAX or t - (mine.get("t") or 0) > 48 * 3600:
        return None
    # salto grande: hace falta que otro piloto mande lo mismo
    firma = _firma([{"n": x.get("Name"), "inf": round((x.get("Influence") or 0) * 100, 2)} for x in facs])
    uid = str(hdr.get("uploaderID") or "")[:12]
    p = SOSP.get(sname)
    if p and p["firma"] == firma and p["uid"] != uid and t - p["t"] < 48 * 3600:
        SOSP.pop(sname, None)
        log(f"{sname}: salto de {salto:.1f} puntos confirmado por otro piloto")
        return None
    if not p or p["firma"] != firma:
        SOSP[sname] = {"firma": firma, "uid": uid, "t": t}
        return f"salto de {salto:.1f} puntos de influencia, esperando a que otro piloto lo confirme"
    return "pendiente de confirmar"

# ---------- mas datos de EDDN (v8) ----------
# Campos nuevos (solo se añaden): en cada sistema "rach"/"rivales", "saltos", "rutas", "estaciones";
# en la raiz "expansion" y "codice"; en cada portanaves "d" (desde cuando esta).
_pico = {}                       # sistema -> hora del ultimo aviso de pico de saltos

def _dia(t):
    return time.strftime("%Y-%m-%d", time.gmtime(t))

def saltos(sname, mine, t):
    """Saltos (FSDJump) que llegan al sistema, por hora UTC; avisa si hay un pico."""
    h = int(t // 3600 * 3600)
    with lock:
        s = {int(k): v for k, v in (mine.get("saltos") or {}).items()}
        s[h] = s.get(h, 0) + 1
        s = dict(sorted(s.items())[-48:])
        mine["saltos"] = {str(k): v for k, v in s.items()}; dirty[0] = True
    cur = s.get(h, 0)
    media = sum(s.get(h - 3600 * k, 0) for k in range(1, 25)) / 24
    if cur == max(10, math.ceil(3 * media)) and time.time() - t < 7200 and time.time() - _pico.get(sname, 0) > 6 * 3600:
        _pico[sname] = time.time()
        discord(f"📈 **{sname}**: {cur} saltos esta hora (lo normal son {media:.0f})")

def rutas(m, t):
    """Rutas trazadas (NavRoute) que pasan por tus sistemas, por dia."""
    vistos = set()
    with lock:
        for k, p in enumerate(m.get("Route") or []):
            n = p.get("StarSystem"); mine = DB["sistemas"].get(n)
            if k == 0 or n in vistos or not mine or mine.get("fuera"):
                continue
            vistos.add(n)
            r_ = dict(mine.get("rutas") or {}); r_[_dia(t)] = r_.get(_dia(t), 0) + 1
            mine["rutas"] = dict(sorted(r_.items())[-8:]); dirty[0] = True

def _es_portanaves(nm, tipo=""):
    return tipo == "FleetCarrier" or bool(CALLSIGN.fullmatch(nm or ""))

def estacion(sname, m, mine, t):
    """Docked / Location atracado: dueño, tipo, distancia, plataformas y estado de la estacion."""
    nm = m.get("StationName")
    if not nm or _es_portanaves(nm, m.get("StationType") or ""):
        return
    f = (m.get("StationFaction") or {}).get("Name") or ""
    with lock:
        E = mine.setdefault("estaciones", {})
        o = E.get(nm) or {}
        if o.get("t", 0) > t:
            return
        e = dict(o)
        e.update({"f": f or o.get("f") or "", "tipo": m.get("StationType") or o.get("tipo") or "", "t": t,
                  "estado": m.get("StationState") or ""})
        if m.get("DistFromStarLS") is not None: e["ls"] = round(m["DistFromStarLS"])
        if m.get("LandingPads"): e["pads"] = m["LandingPads"]
        if m.get("MarketID"): e["mid"] = m["MarketID"]
        E[nm] = e; dirty[0] = True
    if e.get("mid") and not o.get("mid"):
        NAMES["t"] = 0
    of = o.get("f")
    if of and f and of != f and FAC in (of, f):
        txt = (f"🏳️ **{sname}**: **{FAC}** gana la estación **{nm}** (antes de {of})" if f == FAC
               else f"🏴 **{sname}**: **{FAC}** pierde la estación **{nm}** (ahora es de {f})")
        log(txt.replace("**", "")); discord(txt)

def atraque(m, sch, t):
    """Atraques concedidos y denegados por dia en tus estaciones (se buscan por MarketID)."""
    mis_sistemas()
    ref = (NAMES.get("mid") or {}).get(m.get("MarketID"))
    if not ref:
        return
    sname, nm = ref
    with lock:
        e = ((DB["sistemas"].get(sname) or {}).get("estaciones") or {}).get(nm)
        if e is None:
            return
        a = dict(e.get("atq") or {}); d = dict(a.get(_dia(t)) or {"ok": 0, "no": 0})
        if "/dockinggranted/" in sch:
            d["ok"] += 1
        else:
            d["no"] += 1
            neg = dict(e.get("neg") or {}); r_ = m.get("Reason") or "?"; neg[r_] = neg.get(r_, 0) + 1; e["neg"] = neg
        a[_dia(t)] = d
        e["atq"] = dict(sorted(a.items())[-8:]); dirty[0] = True

def mercado(m, mine, t, sch):
    """Mercado (mejores ventas, precios disparados, chollos), naves del astillero y n.º de modulos."""
    nm = m.get("stationName")
    if not nm or _es_portanaves(nm):
        return
    with lock:
        e = mine.setdefault("estaciones", {}).setdefault(nm, {"t": 0})
        if m.get("marketId") and not e.get("mid"):
            e["mid"] = m["marketId"]; NAMES["t"] = 0
        if "/commodity/" in sch:
            if (e.get("mer") or {}).get("t", 0) > t:
                return
            C = [c for c in m.get("commodities") or [] if c.get("name")]
            dem = [c for c in C if (c.get("demand") or 0) > 0 and c.get("sellPrice")]
            alta = [c for c in dem if c.get("meanPrice") and c["sellPrice"] >= 1.3 * c["meanPrice"]]
            bar = [c for c in C if (c.get("stock") or 0) > 0 and c.get("buyPrice") and c.get("meanPrice") and c["buyPrice"] <= 0.7 * c["meanPrice"]]
            e["mer"] = {"t": t, "n": len(C),
                        "vende": [{"n": c["name"], "p": c["sellPrice"], "d": c.get("demand")} for c in sorted(dem, key=lambda c: -c["sellPrice"])[:5]],
                        "alta": [{"n": c["name"], "p": c["sellPrice"], "m": c["meanPrice"]} for c in sorted(alta, key=lambda c: -c["sellPrice"] / c["meanPrice"])[:5]],
                        "barato": [{"n": c["name"], "p": c["buyPrice"], "m": c["meanPrice"], "s": c.get("stock")} for c in sorted(bar, key=lambda c: c["buyPrice"] / c["meanPrice"])[:5]]}
        elif "/shipyard/" in sch:
            e["naves"], e["naves_t"] = sorted(m.get("ships") or []), t
        elif "/outfitting/" in sch:
            e["mods"], e["mods_t"] = len(m.get("modules") or []), t
        dirty[0] = True

def expansion(sname, m, t):
    """Sistemas habitados cerca de los tuyos, sin CDSN y con menos de 7 facciones."""
    pos, facs = m.get("StarPos"), m.get("Factions") or []
    if not sname or not pos or None in pos:
        return
    mc = _mas_cerca(pos)
    if not mc or mc[0] > CFG["expansion_ly"]:
        return
    with lock:
        z = DB.setdefault("expansion", {})
        o = z.get(sname) or {}
        if o.get("t", 0) > t:
            return
        if len(facs) >= 7 or any(x.get("Name") == FAC for x in facs) or not m.get("Population"):
            if z.pop(sname, None):
                dirty[0] = True
            return
        z[sname] = {"pos": pos, "ly": round(mc[0], 1), "junto": mc[1], "nfac": len(facs), "pob": m.get("Population"),
                    "ctrl_n": (m.get("SystemFaction") or {}).get("Name") or "", "t": t}
        dirty[0] = True

def _cx(s):
    s = _re.sub(r"^\$Codex_(Ent_|Category_|SubCategory_)?", "", s or "")
    return _re.sub(r"(_Name)?;$", "", s).replace("_", " ").strip()

def codice(m, t):
    """Entradas del codice a menos de 20 al de tus sistemas (las 30 ultimas)."""
    pos, sysn = m.get("StarPos"), m.get("System")
    if not pos or not sysn or None in pos:
        return
    mc = _mas_cerca(pos)
    if not mc or mc[0] > ZONA_LY:
        return
    n = _cx(m.get("Name"))
    with lock:
        L = [x for x in DB.get("codice") or [] if not (x.get("sys") == sysn and x.get("n") == n)]
        L.append({"sys": sysn, "n": n, "cat": _cx(m.get("Category")), "sub": _cx(m.get("SubCategory")),
                  "cuerpo": m.get("BodyName") or "", "junto": mc[1], "ly": round(mc[0], 1), "t": t})
        DB["codice"] = sorted(L, key=lambda x: -(x.get("t") or 0))[:30]; dirty[0] = True

def process(pkt):
    hit = next((n for b_, n in mis_sistemas() if b_ in pkt), None)
    pp_ = b'"ControllingPower"' in pkt or b'"Powers"' in pkt
    tg_ = b'"ThargoidWar"' in pkt or any(b_ in pkt for b_ in NAMES.get("tg") or [])
    otros_ = b'"Factions"' in pkt or b"/codexentry/" in pkt or b"/docking" in pkt      # v8
    if not hit and FAC_B not in pkt and not pp_ and not tg_ and not otros_:
        return                                           # rapido: no es de ningun sistema que interese
    d = json.loads(pkt)
    sch = d.get("$schemaRef", "")
    hdr = d.get("header") or {}
    gv = hdr.get("gameversion") or ""
    if gv.startswith("3.") or "legacy" in gv.lower() or "/test" in sch:
        return                                           # galaxia antigua (Horizons 3.8) o pruebas
    m = d.get("message") or {}
    sname = m.get("StarSystem") or m.get("systemName")
    t = iso2epoch(m.get("timestamp")) or int(time.time())
    if "/dockinggranted/" in sch or "/dockingdenied/" in sch:   # v8: atraques en tus estaciones
        atraque(m, sch, t); return
    if "/codexentry/" in sch:                             # v8: descubrimientos del codice cerca
        codice(m, t); return
    if "/navroute/" in sch:                               # v8: rutas que pasan por tus sistemas
        if hit: rutas(m, t)
        return
    with lock:
        mine = DB["sistemas"].get(sname) if sname else None
    # trafico: comandantes distintos por dia (id anonimo de EDDN)
    if mine and not mine.get("fuera") and hdr.get("uploaderID"):
        day = time.strftime("%Y-%m-%d", time.gmtime(t))
        dd = TRAF.setdefault(sname, {})
        ids = dd.setdefault(day, set())
        uid = str(hdr["uploaderID"])[:12]
        if uid not in ids:
            ids.add(uid)
            for old_ in sorted(dd)[:-9]:                 # 9 dias: hoy, ayer y 7 para la media del pico
                dd.pop(old_, None)
            with lock:                                   # v10: los numeros se guardan 31 dias (los ids solo 9)
                tr_ = dict(mine.get("trafico") or {})
                tr_.update({k: len(v) for k, v in dd.items()})
                mine["trafico"] = dict(sorted(tr_.items())[-31:])
                dirty[0] = True
    # senales: zonas de conflicto y portanaves
    if mine and "/fsssignaldiscovered/" in sch:
        for sg in m.get("signals") or []:
            nm = sg.get("SignalName") or ""
            ts = iso2epoch(sg.get("timestamp")) or t
            with lock:
                if "Warzone_PointRace" in nm:
                    lv = "High" if "High" in nm else "Med" if "Med" in nm else "Low"
                    zc = {z["n"]: z for z in mine.get("zc") or [] if time.time() - z["t"] < 86400}
                    zc[nm] = {"n": nm, "i": lv, "t": ts}
                    mine["zc"] = sorted(zc.values(), key=lambda z: -z["t"])[:8]
                    dirty[0] = True
                elif sg.get("SignalType") == "FleetCarrier" or (sg.get("IsStation") and CALLSIGN.search(nm)):
                    cs = CALLSIGN.search(nm)
                    if cs:
                        pn = {k: v for k, v in (mine.get("pn") or {}).items() if time.time() - v["t"] < 7 * 86400}
                        pn[cs.group(1)] = {"n": nm.replace(cs.group(1), "").strip(), "t": ts,
                                           "d": (pn.get(cs.group(1)) or {}).get("d") or ts}   # v8: desde cuando esta
                        mine["pn"] = pn
                        dirty[0] = True
        return
    vivo = mine and not mine.get("fuera")
    if vivo and any(x in sch for x in ("/commodity/", "/shipyard/", "/outfitting/")):
        mercado(m, mine, t, sch); return                  # v8: mercado, astillero y equipamiento
    if "/journal/" in sch and m.get("event") == "Docked":
        if vivo: estacion(sname, m, mine, t)              # v8: dueño y datos de la estacion
        return
    if "/journal/" not in sch or m.get("event") not in ("FSDJump", "Location", "CarrierJump"):
        return
    if vivo and m.get("event") == "Location" and m.get("Docked"):
        estacion(sname, m, mine, t)
    if vivo and m.get("event") == "FSDJump":
        saltos(sname, mine, t)                            # v8: saltos por hora
    if not vivo and m.get("Factions") and FAC_B not in pkt:
        expansion(sname, m, t)                            # v8: candidatos para expandirse
    thargoides(sname, m, mine, t)                         # guerra thargoide (v7)
    # Powerplay de los sistemas a menos de 20 al de los tuyos
    if (m.get("ControllingPower") or m.get("Powers")) and cerca(m.get("StarPos")):
        with lock:
            DB.setdefault("zona", {})[sname] = {"pos": m.get("StarPos"), "pot": m.get("ControllingPower"), "est": m.get("PowerplayState"),
                                                 "prog": m.get("PowerplayStateControlProgress"), "pots": m.get("Powers") or [], "t": t}
            dirty[0] = True
    if FAC_B not in pkt or not m.get("Factions"):
        return
    motivo = sospechoso(sname, m, hdr, t, mine)
    if motivo:
        if motivo != "pendiente de confirmar":
            aviso_sosp(sname, motivo)
        return
    ex = {"pos": m.get("StarPos"),
          "sis": {"pob": m.get("Population"), "eco": m.get("SystemEconomy"), "eco2": m.get("SystemSecondEconomy"),
                  "seg": m.get("SystemSecurity"), "gov": m.get("SystemGovernment"), "alg": m.get("SystemAllegiance")},
          "pp": {"pot": m.get("ControllingPower"), "est": m.get("PowerplayState"), "prog": m.get("PowerplayStateControlProgress"),
                 "ref": m.get("PowerplayStateReinforcement"), "soc": m.get("PowerplayStateUndermining"),
                 "pots": m.get("Powers") or []}}
    if update(sname, t, m["Factions"], (m.get("SystemFaction") or {}).get("Name"), "EDDN", m.get("Conflicts"), ex):
        DB["eddn"]["mios"] += 1; DB["eddn"]["ultimo"] = time.time()
        s_ = DB["sistemas"][sname]
        log(f"EDDN {sname}: {s_['inf']:.1f}% {'(controla)' if s_['ctrl'] else ''} {' '.join(s_['activos'] + s_['pendientes'])}")

# ---------- EDDN ----------
def eddn_loop():
    import zmq
    ctx = zmq.Context()
    while True:
        sub = ctx.socket(zmq.SUB)
        sub.setsockopt(zmq.SUBSCRIBE, b"")
        sub.setsockopt(zmq.RCVTIMEO, 600000)             # 10 min sin nada: se reconecta
        sub.connect("tcp://eddn.edcd.io:9500")
        log("EDDN conectado")
        DB["eddn"]["ok"] = True
        try:
            while True:
                raw = sub.recv()
                DB["eddn"]["msgs"] += 1
                try:
                    process(zlib.decompress(raw))
                except Exception as e:                   # un mensaje raro no corta la escucha
                    DB["eddn"]["malos"] = DB["eddn"].get("malos", 0) + 1
                    if DB["eddn"]["malos"] % 100 == 1:
                        log("EDDN mensaje:", e)
        except Exception as e:
            log("EDDN:", e)
        DB["eddn"]["ok"] = False
        try:
            sub.close(0)
        except Exception:
            pass
        time.sleep(30)

# ---------- EDSM (rellena huecos) ----------
def edsm_one(name):
    url = "https://www.edsm.net/api-system-v1/factions?" + urllib.parse.urlencode({"systemName": name})
    req = urllib.request.Request(url, headers={"User-Agent": "PanelEliteRPi-escucha/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.loads(r.read().decode() or "{}")
    fs = j.get("factions") or []
    if not fs:
        return
    t = max(f.get("lastUpdate") or 0 for f in fs)
    conv = lambda L: [{"State": x.get("state")} for x in L or []]
    facs = [{"Name": f.get("name"), "Influence": f.get("influence") or 0, "FactionState": f.get("state"),
             "Government": f.get("government"), "Allegiance": f.get("allegiance"), "isPlayer": f.get("isPlayer"),
             "ActiveStates": conv(f.get("activeStates")), "PendingStates": conv(f.get("pendingStates")),
             "RecoveringStates": conv(f.get("recoveringStates"))} for f in fs]
    ex = None
    if not (DB["sistemas"].get(name) or {}).get("pos"):    # coordenadas y datos del sistema, una sola vez
        try:
            u2 = "https://www.edsm.net/api-v1/system?" + urllib.parse.urlencode(
                {"systemName": name, "showCoordinates": 1, "showInformation": 1})
            with urllib.request.urlopen(urllib.request.Request(u2, headers={"User-Agent": "PanelEliteRPi-escucha/1.0"}), timeout=20) as r:
                j2 = json.loads(r.read().decode() or "{}")
            c, inf_ = j2.get("coords") or {}, j2.get("information") or {}
            ex = {"pos": [c.get("x"), c.get("y"), c.get("z")] if c else None,
                  "sis": {"pob": inf_.get("population"), "eco": inf_.get("economy"), "eco2": inf_.get("secondEconomy"),
                          "seg": inf_.get("security"), "gov": inf_.get("government"), "alg": inf_.get("allegiance")} if inf_ else None}
        except Exception as e:
            log("EDSM sistema", name, e)
    if update(name, t, facs, (j.get("controllingFaction") or {}).get("name"), "EDSM", (), ex):
        log(f"EDSM {name}: actualizado")

def edsm_loop():
    time.sleep(20)
    while True:
        for name in list(DB["sistemas"]):
            v_ = DB["sistemas"][name]
            if time.time() - (v_.get("t") or 0) > 3 * 3600 or v_.get("todas") is None or not v_.get("pos"):
                try:
                    edsm_one(name)
                except Exception as e:
                    log("EDSM", name, e)
                time.sleep(3)                            # sin prisa: EDSM pide no saturar
        time.sleep(CFG["edsm_horas"] * 3600)

# ---------- servidor para el panel ----------
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] not in ("/", "/faccion.json"):
            self.send_error(404); return
        with lock:
            body = json.dumps(DB, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass

# ---------- v9: posibles ataques (mismas reglas que la web y el radar) ----------
# Pico de visitas: hoy o ayer al menos 5 pilotos y el triple de la media de los 7 dias anteriores.
# Si ademas nuestra influencia baja 1 punto o mas desde ayer: POSIBLE ATAQUE.
# DB["ataques"] = {"act": {sistema: {...}}, "hist": [ataques terminados, el mas reciente primero]}
def _pico_vis(v):
    tr = v.get("trafico") or {}
    d = lambda n: tr.get(time.strftime("%Y-%m-%d", time.gmtime(time.time() - n * 86400)), 0)
    for k in (0, 1):
        m = sum(d(i) for i in range(k + 1, k + 8)) / 7
        if d(k) >= 5 and d(k) >= 3 * max(m, 1):
            return d(k), m, "ayer" if k else "hoy"
    return None

def revisa_ataques():
    c1 = lambda x: f"{x:.1f}".replace(".", ",")
    msgs, now = [], time.time()
    with lock:
        A = DB.setdefault("ataques", {"act": {}, "hist": []})
        act, hist = A.setdefault("act", {}), A.setdefault("hist", [])
        vistos = set()
        for n, v in DB["sistemas"].items():
            if v.get("fuera") or v.get("inf") is None:
                continue
            p = _pico_vis(v)
            baja = v["prev"] - v["inf"] if v.get("prev") is not None else 0
            if p and baja >= 1 and not [c for c in v.get("conflictos") or [] if c.get("estado") in ("active", "pending")]:   # v10: con conflicto manda el marcador
                vistos.add(n)
                a = act.get(n)
                if not a:                                # ataque nuevo
                    act[n] = {"ini": int(now), "v": p[0], "m": round(p[1], 1), "dia": p[2], "antes": v["prev"],
                              "min": v["inf"], "inf": v["inf"], "ctrl": bool(v.get("ctrl"))}
                    q_ = v.get("sube_cuando_baja") or {}
                    if q_.get("n") and now - (q_.get("t") or 0) < 2 * 86400:
                        act[n]["quien"] = q_["n"]
                    msgs.append(f"🚨 **POSIBLE ATAQUE** en **{n}**: {p[0]} pilotos {p[2]} (media {c1(p[1])}) "
                                f"y la influencia baja {c1(baja)} puntos ({c1(v['inf'])} %)"
                                + (f" · sube **{q_['n']}** (+{c1(q_['d'])})" if act[n].get("quien") else ""))
                else:
                    a["v"] = max(a["v"], p[0]); a["inf"] = v["inf"]; a["min"] = min(a["min"], v["inf"])
        for n in [n for n in act if n not in vistos]:    # ya no hay pico o ya no baja: termina
            a = act.pop(n); v = DB["sistemas"].get(n) or {}
            fin = v.get("inf", a["inf"])
            dif = fin - a["antes"]
            res = "recuperada" if dif >= -0.5 else "perdida"
            hist.insert(0, {"sys": n, "ini": a["ini"], "fin": int(now), "v": a["v"], "m": a["m"], "antes": a["antes"],
                            "min": a["min"], "inf": fin, "dif": round(dif, 1), "res": res, "ctrl": a.get("ctrl", False),
                            "quien": a.get("quien") or ""})
            msgs.append(f"{'✅' if res == 'recuperada' else '📉'} Fin del posible ataque en **{n}**: influencia {c1(a['antes'])} → {c1(fin)} % "
                        f"({'+' if dif >= 0 else ''}{c1(dif)}), {'recuperada' if res == 'recuperada' else 'no se ha recuperado'}")
        del hist[30:]                                     # los 30 ultimos
        if msgs:
            dirty[0] = True
    for m_ in msgs:
        log(m_.replace("**", "")); discord(m_)

# ---------- v10: conflictos dia a dia ----------
# EDDN solo da los dias GANADOS de cada faccion (WonDays). El dia del conflicto (1..7) lo cuenta el escucha:
# - si lo vio pendiente y luego activo: dia exacto (empieza en 1 y suma 1 en cada tick global)
# - si lo descubre ya activo: dia minimo = ganados + perdidos + 1 ("dia_exacto": false)
# El resultado de cada dia (G ganado, P perdido, = sin resultado, ? sin datos) se mira con el primer dato despues del tick.
# Gana quien llegue a 4 dias; si nadie llega en 7 dias, gana quien tenga mas (igual = empate).
DIAS_CONF = 7
FASE_TXT = {"pendiente": "PENDIENTE", "victoria": "VICTORIA SEGURA", "sin_remedio": "SISTEMA EN DERROTA (sin remedio)",
            "decisivo": "DÍA DECISIVO", "a_un_dia": "A UN DÍA DE GANAR", "defensa": "DEFENSA EN CURSO",
            "derrota": "SISTEMA EN DERROTA", "disputado": "DISPUTADO", "igualado": "DISPUTADO (igualado)"}
FASE_AVISA = ("decisivo", "derrota", "sin_remedio", "a_un_dia", "victoria")   # avisos a Discord al entrar en estas fases

def final_conf(g, p, dia):
    """Como acabaria el conflicto con g-p al terminar el dia 'dia': victoria, derrota, empate o sigue."""
    if g >= 4: return "victoria"
    if p >= 4: return "derrota"
    if dia >= DIAS_CONF: return "victoria" if g > p else "derrota" if p > g else "empate"
    return "sigue"

def fase_conf(g, p, dia):
    """Fase para los avisos (mismas reglas que el radar y la web). dia = el que se esta jugando (1..7)."""
    quedan = DIAS_CONF + 1 - dia                          # dias que quedan, contando el de hoy
    if p + quedan < g: return "victoria"
    if g + quedan < p: return "sin_remedio"
    if p == 3 or (dia >= DIAS_CONF and abs(g - p) <= 1): return "decisivo"
    if g == 3 and p <= 1: return "a_un_dia"
    if g > p: return "defensa"
    if g < p: return "derrota"
    return "disputado" if g == 0 and dia <= 3 else "igualado"

def juego_conf(g, p, dia):
    """Que se juega hoy: 'GANAR = victoria · PERDER = empate' (solo lo que cambia el final)."""
    r = lambda x: {"victoria": "victoria", "derrota": "derrota", "empate": "empate", "sigue": "sigue"}[x]
    a, b, c = final_conf(g + 1, p, dia), final_conf(g, p + 1, dia), final_conf(g, p, dia)
    return f"GANAR = {r(a)} · PERDER = {r(b)}" + (f" · SIN RESULTADO = {r(c)}" if dia >= DIAS_CONF else "")

def conf_track(sysname, old, new, t, src):
    """Se llama con el cerrojo cogido. Rellena dia/fase/resultados en new['conflictos'] y devuelve avisos."""
    msgs, seg = [], {k: dict(v) for k, v in ((old or {}).get("cseg") or {}).items()}
    hoy = []
    for c in new.get("conflictos") or []:
        r_ = c.get("contra") or "?"; hoy.append(r_)
        s_ = seg.setdefault(r_, {"tipo": c.get("tipo"), "ini": None, "pend": None, "exacto": False, "dia": 0,
                                 "res": [], "ref": [0, 0], "tick": None, "eval": None, "fase": None})
        g, p = c.get("ganados") or 0, c.get("perdidos") or 0
        if src == "EDDN" and c.get("estado") == "pending":
            s_["pend"] = s_.get("pend") or int(t)
        elif src == "EDDN" and c.get("estado") == "active":
            if not s_.get("ini"):                         # empieza (o lo descubrimos ya empezado)
                s_["ini"], s_["exacto"] = int(t), bool(s_.get("pend"))
                s_["dia"] = 1 if s_["exacto"] else min(DIAS_CONF, g + p + 1)
                s_["ref"], s_["tick"], s_["res0"] = [g, p], DB.get("tick_global"), s_["dia"]
                if r_ not in (DB.get("rivales") or {}) or "conflicto" not in DB["rivales"][r_].get("motivo", ""):
                    vigila(r_, sysname, t, "conflicto")
            elif s_.get("eval") and t > s_["eval"]:       # primer dato despues del tick: resultado del dia anterior
                dg, dp = g - s_["ref"][0], p - s_["ref"][1]
                res = "G" if dg > 0 and dp <= 0 else "P" if dp > 0 and dg <= 0 else "=" if not dg and not dp else "?"
                s_["res"] = (s_.get("res") or []) + [res]; s_["ref"], s_["eval"] = [g, p], None
                tipo = {"war": "Guerra", "civilwar": "Guerra civil", "election": "Elecciones"}.get((c.get("tipo") or "").lower(), "Conflicto")
                lab = {"G": "✅ ganado", "P": "❌ perdido", "=": "➖ sin resultado", "?": "❔ no se sabe"}[res]
                msgs.append(f"{'✉️' if (c.get('tipo') or '') == 'election' else '⚔️'} **{sysname}**: {tipo} contra **{r_}** · "
                            f"día {s_['dia'] - 1}/{DIAS_CONF} {lab} · van {g}-{p}")
        s_.update({"tipo": c.get("tipo"), "g": g, "p": p, "mio": c.get("en_juego") or "", "suyo": c.get("en_juego_rival") or ""})
        if c.get("estado") == "active" and s_.get("ini"):
            fase = fase_conf(g, p, s_["dia"])
            c.update({"dia": s_["dia"], "dia_exacto": s_["exacto"], "desde": s_["ini"], "fase": fase,
                      "juego": juego_conf(g, p, s_["dia"]), "res": s_.get("res") or [], "res_desde": s_.get("res0") or 1})
            if fase != s_.get("fase") and fase in FASE_AVISA:
                txt = c["juego"] if fase == "decisivo" else ""
                msgs.append(f"{'🚨' if fase in ('decisivo', 'derrota', 'sin_remedio') else '🟢'} **{sysname}**: **{FASE_TXT[fase]}** contra **{r_}** · "
                            f"día {s_['dia']}/{DIAS_CONF}{'' if s_['exacto'] else ' (aprox.)'} · {g}-{p}"
                            + (f" · {txt}" if txt else "") + (f" · en juego: {s_['mio']}" if s_["mio"] and fase != "victoria" else ""))
            s_["fase"] = fase
        elif c.get("estado") == "pending":
            c.update({"fase": "pendiente", "desde": s_.get("pend")})
            s_["fase"] = "pendiente"
    if src == "EDDN":
        for r_ in [r_ for r_ in seg if r_ not in hoy]:   # conflicto terminado (o pendiente que no llego a empezar)
            s_ = seg.pop(r_)
            if not s_.get("ini"):
                continue
            g, p = s_.get("g") or 0, s_.get("p") or 0
            res = "ganado" if g > p else "perdido" if p > g else "desconocido" if g == 3 or (s_.get("dia") or 0) >= DIAS_CONF else "empate"
            H = DB.setdefault("conflictos_hist", [])
            H.insert(0, {"sys": sysname, "contra": r_, "tipo": s_.get("tipo"), "ini": s_["ini"], "fin": int(t), "dias": s_.get("dia"),
                         "dia_exacto": s_.get("exacto"), "g": g, "p": p, "res": res, "res_dias": s_.get("res") or [],
                         "res_desde": s_.get("res0") or 1, "en_juego": s_.get("mio") or "", "en_juego_rival": s_.get("suyo") or "",
                         "ctrl": bool((old or {}).get("ctrl")), "inf_antes": (old or {}).get("inf"), "inf_despues": new.get("inf")})
            del H[50:]                                    # los 50 ultimos
    new["cseg"] = seg
    return msgs

def conf_tick(tg):
    """Tick global nuevo: los conflictos activos pasan al dia siguiente."""
    with lock:
        for n, v in DB["sistemas"].items():
            seg = v.get("cseg") or {}
            for r_, s_ in seg.items():
                if not s_.get("ini") or s_.get("tick") == tg:
                    continue
                if tg <= s_["ini"] - 6 * 3600 or (s_.get("tick") and tg < s_["tick"]):
                    continue                              # tick viejo
                if tg < s_["ini"]:                        # es el tick que lo empezo (llego tarde a tick.edcd.io)
                    s_["tick"] = tg; continue
                if s_.get("eval"):                        # un dia entero sin datos
                    s_["res"] = (s_.get("res") or []) + ["?"]
                s_["eval"], s_["tick"] = tg, tg
                s_["dia"] = min(DIAS_CONF, (s_.get("dia") or 1) + 1)
                for c in v.get("conflictos") or []:      # el panel ve el dia nuevo enseguida
                    if c.get("contra") == r_ and c.get("estado") == "active":
                        g, p = c.get("ganados") or 0, c.get("perdidos") or 0
                        c.update({"dia": s_["dia"], "fase": fase_conf(g, p, s_["dia"]), "juego": juego_conf(g, p, s_["dia"])})
                dirty[0] = True

# ---------- v10: quien sube cuando bajamos y vigilancia de rivales ----------
# Cuando nuestra influencia baja 1 punto o mas, se apunta la faccion que mas sube en ese sistema (sube_cuando_baja)
# y se anade a DB["rivales"]. Si un rival vigilado sube 2 puntos o mas en OTRO de nuestros sistemas, aviso a Discord.
_vig_avisado = {}                # (rival, sistema) -> hora del ultimo aviso

def vigila(n, sysname, t, motivo):
    R = DB.setdefault("rivales", {})
    r_ = R.setdefault(n, {"veces": 0, "sis": [], "motivo": "", "ini": int(t)})
    r_["veces"] += 1; r_["ult"] = int(t)
    if sysname not in r_["sis"]:
        r_["sis"] = (r_["sis"] + [sysname])[-10:]
    if motivo not in r_["motivo"]:
        r_["motivo"] = (r_["motivo"] + ", " + motivo).strip(", ")

def quien_sube(sysname, old, new, o_inf, t, src):
    """Se llama con el cerrojo cogido. Devuelve avisos."""
    msgs = []
    if src != "EDDN" or not o_inf or not old or old.get("inf") is None:
        return msgs
    dif = {x["n"]: x["inf"] - o_inf[x["n"]] for x in new.get("todas") or [] if x["n"] != FAC and x["n"] in o_inf}
    if old["inf"] - new["inf"] >= 1 and dif:
        n, d = max(dif.items(), key=lambda kv: kv[1])
        if d >= 0.5:
            new["sube_cuando_baja"] = {"n": n, "d": round(d, 2), "baja": round(old["inf"] - new["inf"], 2), "t": int(t)}
            vigila(n, sysname, t, "sube cuando bajamos")
    R = DB.get("rivales") or {}
    for n, d in dif.items():
        r_ = R.get(n)
        if not r_ or d < 2 or sysname in r_.get("sis", []) or time.time() - _vig_avisado.get((n, sysname), 0) < 86400:
            continue
        _vig_avisado[(n, sysname)] = time.time()
        inf_r = next((x["inf"] for x in new["todas"] if x["n"] == n), 0)
        msgs.append(f"🕵️ **{n}** (vigilada: {r_.get('motivo')} en {', '.join(r_.get('sis', [])[:3])}) sube {d:+.1f} en **{sysname}** "
                    f"({inf_r:.1f} %, nosotros {new['inf']:.1f} %)".replace(".", ","))
    return msgs

def saver_loop():
    n_ = 0
    while True:
        time.sleep(10)
        n_ += 1
        if n_ % 30 == 0:                                 # cada 5 min
            traf_save()
            try:
                revisa_ataques()
            except Exception as e:                       # nunca debe tumbar el guardado
                log("ataques:", e)
            with lock:
                z_ = DB.get("zona") or {}
                for k in [k for k, v in z_.items() if time.time() - (v.get("t") or 0) > 7 * 86400]:
                    z_.pop(k, None)
                tz_ = DB.get("thargoides") or {}                 # thargoides de alrededor sin noticias en 7 dias
                for k in [k for k, v in tz_.items() if time.time() - (v.get("t") or 0) > 7 * 86400]:
                    tz_.pop(k, None)
                rv_ = DB.get("rivales") or {}                    # v10: rivales sin noticias en 60 dias
                for k in [k for k, v in rv_.items() if time.time() - (v.get("ult") or 0) > 60 * 86400]:
                    rv_.pop(k, None)
                ez_ = DB.get("expansion") or {}                  # v8: candidatos sin noticias en 14 dias
                for k in [k for k, v in ez_.items() if time.time() - (v.get("t") or 0) > 14 * 86400]:
                    ez_.pop(k, None)
        if dirty[0]:
            try:
                save()
            except OSError as e:
                log("guardar:", e)

if __name__ == "__main__":
    load()
    log(f"Escucha EDDN {VERSION} · escuchando a '{FAC}' · {len(DB['sistemas'])} sistemas conocidos · puerto {CFG['puerto']}")
    for fn in (eddn_loop, edsm_loop, saver_loop, gh_loop, discord_loop, resumen_loop, tick_global_loop):
        threading.Thread(target=fn, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", CFG["puerto"]), H).serve_forever()
