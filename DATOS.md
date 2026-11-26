# Datos de faccion.json

Qué saca el escucha de EDDN (y de EDSM y tick.edcd.io), qué guarda en `faccion.json` y quién lo usa.
**Si se añade un campo nuevo al escucha, se apunta aquí.**

`faccion.json` está en [cdsn-datos](https://github.com/ortemedder/cdsn-datos) (se sube cada 15 min si cambia, en JSON compacto desde la v11.3) y en la red de casa en `http://IP:8090/faccion.json`.
Lo leen: radar-cdsn (ESP32), cdsn-web, panel-elite y escucha-s3.

Horas: siempre en **segundos UTC** (epoch). Influencias: en **%** (0–100, con 2 decimales). Días: `AAAA-MM-DD` en UTC.

---

## 1. De dónde salen los datos

| Fuente | Mensajes | Qué se saca |
|---|---|---|
| **EDDN** journal `FSDJump`, `Location`, `CarrierJump` | Cada vez que un piloto llega a un sistema | Facciones (influencia, estados, gobierno, alianza), **conflictos** (tipo, estado, días ganados, lo que hay en juego), facción que controla, coordenadas, población, economía, seguridad, Powerplay, guerra thargoide |
| EDDN journal `Docked` (y `Location` atracado) | Al atracar | Estación: dueño, tipo, distancia, plataformas, estado, MarketID |
| EDDN `commodity`, `shipyard`, `outfitting` | Al abrir el mercado / astillero / equipamiento | Mejores ventas, precios disparados, chollos, naves, número de módulos |
| EDDN `dockinggranted`, `dockingdenied` | Al pedir atraque | Atraques concedidos y denegados (y por qué) |
| EDDN `fsssignaldiscovered` | Al escanear el sistema | Zonas de conflicto y portanaves |
| EDDN `navroute` | Al trazar una ruta | Rutas que pasan por nuestros sistemas |
| EDDN `codexentry` | Descubrimientos | Códice a menos de 20 al |
| EDDN `approachsettlement` | Al acercarse a un asentamiento (Odyssey) | Asentamientos de nuestros sistemas y su dueño (v11) |
| Cabecera de EDDN (`uploaderID`) | Todos | **Visitas**: pilotos distintos por día (id anónimo, no se sabe quién es) |
| **EDSM** (cada 6 h) | API | Facciones de los sistemas sin datos de EDDN (**sin conflictos**) y coordenadas |
| **tick.edcd.io** (cada 30 min) | API | Hora del último tick de la galaxia |
| **edgalaxydata.space** (jueves a las 7:10 UTC y a mano, v12.3) | Archivo diario de EDDN | Relleno de visitas, mapa de horas e influencia de los días en que el escucha estuvo caído (`relleno_eddn.py`) |

Lo que **no** da EDDN: quién es cada piloto, el arquitecto de un sistema ni el avance de las obras (Spansh tampoco tiene el arquitecto; se ve en Inara), qué misiones hace, en qué día va un conflicto (lo cuenta el escucha) ni el resultado de cada día (lo deduce el escucha).

---

## 2. Raíz de faccion.json

| Campo | Qué es | Desde |
|---|---|---|
| `ver` | Versión del escucha | v7 |
| `faccion` | Nombre de la facción (Caballeros de Sion) | v1 |
| `t` | Hora a la que se guardó el archivo | v1 |
| `sistemas` | Un objeto por sistema (ver punto 3) | v1 |
| `eddn` | `ok` conectado, `ultimo` último dato nuestro, `msgs` mensajes, `mios` datos útiles, `descartados` sospechosos, `malos` ilegibles | v1 |
| `tick_global` | Último tick de la galaxia (tick.edcd.io) | v4 |
| `zona` | Powerplay de sistemas a menos de 20 al: `pos`, `pot`, `est`, `prog`, `pots`, `t` | v3 |
| `thargoides` | Sistemas a menos de 20 al con thargoides: estado, progreso, puertos, `junto`, `ly` | v7 |
| `expansion` | Candidatos para expandirse (sin CDSN, menos de 7 facciones): `ly`, `junto`, `nfac`, `pob`, `ctrl_n` | v8 |
| `codice` | Últimas 30 entradas del códice cerca | v8 |
| `ataques.act` | Posibles ataques en curso: `ini`, `v` pilotos, `m` media, `antes`/`min`/`inf` influencia, `quien` (v10) | v9 |
| `ataques.hist` | Últimos 30 posibles ataques terminados: lo de arriba + `fin`, `dif`, `res` (recuperada/perdida) | v9 |
| **`conflictos_hist`** | **Últimos 50 conflictos terminados** (ver punto 4) | **v10** |
| `rivales` | Facciones vigiladas (ver punto 5) | v10 |
| `relleno` | Último relleno con el archivo de EDDN: `t`, `motivo` (semanal / a mano), `dias`, `visitas`, `horas`, `influencia` (mejorados), `min`, `error` | v11.4 |
| **`noticias`** | **Los 300 últimos avisos (los mismos de Discord), para La Crónica de Sion de la web:** `[hora, texto, sección, urgente 0/1, sistema]` y, si la noticia tiene varias líneas (resumen diario), un 6.º campo con el resto. Secciones: cronica, conflictos, expansion (lo nuestro y 🛬 facciones que llegan a nuestros sistemas), vecindario (🛸 expansiones de otras facciones, solo en la web, v11.8), obras, estaciones, poblacion, actividad, thargoides, resumen, escucha, otras | **v11.6 / v11.8** |
| **`fija`**, **`hemeroteca`** | Noticia fija que escribe el almirante en `noticia_fija.txt` (cdsn-datos): `fija` = `{n: [[titular, texto]...], desde}`; `hemeroteca` = las 100 últimas que se quitaron o cambiaron: `{tit, txt, desde, hasta}`, la más nueva primero | **v11.7** |
| `vec_av` | **v11.8: expansiones de otras facciones ya publicadas en La Crónica, una por facción:** `{"Facción": {ini, ult, orig: [sistemas donde se vio], obj: {sistema nuestro: al}}}`. Se borra al ver la facción sin expansión (noticia "terminó su expansión") o tras 10 días sin noticias | **v11.8** |
| `resumen_ayer` | v11.8: controlados y sistemas del último resumen diario, para el "desde ayer" | **v11.8** |
| `vecinos` | **Expansiones y retiradas de otras facciones** en nuestros sistemas y a menos de 30 al (ver punto 7) | **v11** |

---

## 3. Cada sistema (`sistemas["Nombre"]`)

### Influencia y estados
| Campo | Qué es |
|---|---|
| `sys`, `t`, `src` | Nombre, hora del dato y fuente (EDDN o EDSM) |
| `inf` | Influencia de CDSN |
| `prev`, `prev_t` | Influencia anterior (la última distinta) y su hora |
| `hinf` | Histórico: `[hora, influencia]`, últimos **60** cambios (v11.3; antes 14) |
| `ctrl`, `ctrl_n` | Si CDSN controla el sistema y quién lo controla |
| `estado`, `activos`, `pendientes`, `recuperando` | Estados de CDSN (en inglés: War, Election, Expansion, Retreat...) |
| `segunda`, `segunda_inf` | Segunda facción e influencia |
| `todas` | Todas las facciones: `n` nombre, `inf`, `gov`, `alg`, `act`, `pend`, `jug` (de jugadores), `fel` felicidad 1–5 (v11) |
| `fel` | Felicidad de CDSN en el sistema: 1 eufórica, 2 contenta, 3 descontenta, 4 infeliz, 5 desesperada (v11) |
| `rach`, `rivales` | Ticks seguidos que sube cada facción; las que llevan 2 o más (`racha`, `inf`, `dif`) |
| `fuera` | CDSN ya no está en el sistema |

### Conflictos (`conflictos`, lista)
| Campo | Qué es | Desde |
|---|---|---|
| `tipo` | `war`, `civilwar` o `election` | v1 |
| `estado` | `pending` (empieza en el próximo tick) o `active` | v1 |
| `contra` | Facción rival | v1 |
| `ganados`, `perdidos` | Días ganados por CDSN y por el rival (gana quien llegue a 4) | v1 |
| `en_juego`, `en_juego_rival` | Lo que perdemos si perdemos / lo que ganamos si ganamos (estación o activo) | v10 |
| `dia` | Día que se está jugando (1–7) | v10 |
| `dia_exacto` | `true` si el escucha lo vio empezar; `false` si es un mínimo estimado | v10 |
| `desde` | Hora en que empezó (o en que se descubrió) | v10 |
| `fase` | `pendiente`, `defensa`, `a_un_dia`, `victoria`, `disputado`, `igualado`, `decisivo`, `derrota`, `sin_remedio` | v10 |
| `juego` | Qué se juega hoy: "GANAR = victoria · PERDER = empate" | v10 |
| `res`, `res_desde` | Resultado de cada día: `G` ganado, `P` perdido, `=` sin resultado, `?` sin datos; `res_desde` = día del primero | v10 |

Reglas de las fases (las mismas en el escucha, el radar y la web; 7 días como mucho; si nadie llega a 4, gana quien tenga más):
- `victoria`: el rival ya no puede alcanzarnos. `sin_remedio`: nosotros ya no podemos alcanzarle.
- `decisivo`: el rival tiene 3 días, o es el día 7 y la diferencia es de 1 o menos.
- `a_un_dia`: tenemos 3 y el rival 1 o menos. `defensa`: vamos ganando. `derrota`: vamos perdiendo.
- `disputado`: 0-0 en los días 1–3. `igualado`: cualquier otro empate.

`cseg` es el seguimiento interno de cada conflicto (lo usa solo el escucha para contar días).

### Ataques y rivales
| Campo | Qué es | Desde |
|---|---|---|
| `sube_cuando_baja` | Última vez que bajamos 1 punto o más: `n` facción que más subió, `d` cuánto, `baja` cuánto bajamos, `t` | v10 |

### Tick
| Campo | Qué es |
|---|---|
| `tick_ult`, `tick_marg` | Último tick visto y su margen (± min) |
| `tick_prox`, `tick_disp`, `tick_n` | Próximo tick previsto, variación (± min) y ticks aprendidos |
| `tk` | Datos internos del cálculo del tick |

### Actividad
| Campo | Qué es |
|---|---|
| `trafico` | Pilotos distintos por día (`AAAA-MM-DD`: número), **60 días** (v11.3; 31 en la v10, antes 9). Los ids anónimos de los pilotos solo se guardan 9 días, en `trafico.json` de la Orange Pi (no se sube) |
| `saltos` | Saltos que llegan por hora (últimas 48 h) |
| `hdia` | Saltos por día y hora UTC: `AAAA-MM-DD` → 24 números, **28 días** (v11; 14 hasta la v11.3) para el mapa de horas |
| `rutas` | Rutas que pasan por el sistema, por día (8 días) |
| `zc` | Zonas de conflicto vistas en 24 h: `n`, `i` intensidad (Low/Med/High), `t` |
| `pn` | Portanaves vistos en 7 días: matrícula → `n` nombre, `t` visto, `d` desde cuándo |
| `thargoid` | Guerra thargoide en el sistema: estado, progreso, puertos... |

### Sistema y Powerplay
| Campo | Qué es |
|---|---|
| `pos` | Coordenadas `[x, y, z]` |
| `sis` | `pob` población, `eco`/`eco2` economía, `seg` seguridad, `gov` gobierno, `alg` alianza |
| `hsis` | Cambios de población y seguridad: `[hora, pob, seg]`, los 10 últimos (v11) |
| `pp` | `pot` potencia, `est` estado, `prog` progreso, `ref` refuerzo, `soc` socavamiento, `pots` presentes |

### Asentamientos (`asent["Nombre"]`, v11)
| Campo | Qué es |
|---|---|
| `f`, `cuerpo`, `mid`, `eco`, `t` | Dueño, cuerpo, MarketID, economía, hora (los 40 más recientes) |

### Estaciones (`estaciones["Nombre"]`)
| Campo | Qué es |
|---|---|
| `f`, `tipo`, `estado`, `ls`, `pads`, `mid`, `t` | Dueño, tipo, estado (Damaged, UnderRepairs, UnderAttack...), distancia (ls), plataformas, MarketID, hora |
| `estado_t`, `serv`, `eco` | Desde cuándo tiene ese estado, número de servicios y economía (v11) |
| `obra` | Solo en las obras (*Construction Site*, dueño Brewer Corporation): nombre de la estación que se está construyendo. Cuando alguien atraca en la estación terminada, la obra se borra (v11.1) |
| `atq`, `neg` | Atraques por día (`ok`/`no`) y motivos de denegación |
| `mer` | Mercado: `vende` mejores ventas, `alta` precios disparados, `barato` chollos |
| `naves`, `mods` | Naves del astillero y número de módulos |

---

## 4. Historial de conflictos (`conflictos_hist`, v10)
Uno por conflicto terminado, el más reciente primero (50 como mucho):
`sys`, `contra`, `tipo`, `ini`, `fin`, `dias`, `dia_exacto`, `g`, `p` (marcador antes del último día),
`res` (`ganado`, `perdido`, `empate` o `desconocido` si iba 3-3 o era el día 7 empatado), `res_dias`, `res_desde`,
`en_juego`, `en_juego_rival`, `ctrl` (si lo controlábamos), `inf_antes`, `inf_despues`.

## 5. Rivales vigilados (`rivales`, v10)
`rivales["Facción"]`: `veces` (cuántas veces nos ha hecho daño), `sis` (sistemas, 10 como mucho), `motivo`
(`conflicto` y/o `sube cuando bajamos`), `ini`, `ult`. Se borran tras 60 días sin noticias.
Si un rival vigilado sube 2 puntos o más en **otro** sistema nuestro, aviso a Discord (uno al día por sistema).

## 6. Avisos a Discord
Facción nueva en un sistema · ya no está · ventaja baja · conflicto que empieza ✉/⚔ · **resultado de cada día del conflicto** (v10) ·
**fases DÍA DECISIVO, SISTEMA EN DERROTA, sin remedio, A UN DÍA DE GANAR y VICTORIA SEGURA** (v10) · conflicto terminado ·
retirada / expansión / guerra / elecciones · rival que sube 3 ticks · **rival vigilado que sube en otro sistema** (v10) ·
estación ganada o perdida · **estación dañada / bajo ataque y su vuelta a la normalidad** (v11) · **asentamiento ganado o perdido** (v11) · **obra nueva y obra terminada** (v11.1) · **expansión de otra facción que puede llegar a nuestros sistemas** (v11) · **otra facción en retirada en un sistema nuestro** (v11) · **felicidad de CDSN que baja a descontenta o peor** (v11) · **cambio de seguridad y de población (5 % o más)** (v11) · pico de saltos · thargoides · dato sospechoso · POSIBLE ATAQUE (no salta si hay conflicto, v10) y su final · resumen diario a las 21:00.

## 7. Vecinos: expansiones y retiradas (`vecinos`, v11)
`vecinos["Sistema"]`: sistemas (nuestros o a menos de `vecinos_ly` = 30 al) donde **otra** facción está en expansión o retirada.
`pos`, `ly` y `junto` (nuestro sistema más cercano), `propio` (es nuestro), `nfac`, `t`,
`exp`: `[{n, inf, est: "pend"/"act", obj: [[sistema nuestro, ly], ...]}]` (`obj` = nuestros sistemas a menos de `expansion_ly` (20 al), con menos de 7 facciones y sin esa facción: adonde puede llegar),
`ret`: `[{n, inf, est}]`. Se borran tras 10 días sin noticias.

## 8. Ideas para más adelante (datos que EDDN manda y no guardamos)
- Cuerpos escaneados (`Scan`, `FSSAllBodiesFound`) en nuestros sistemas.

## historial.json (v12.5)

Archivo aparte en cdsn-datos (no va en faccion.json, para no engordarlo ni cargar al radar). Guarda 60 días.

| Campo | Qué es |
|---|---|
| `rivales` | `{sistema: {facción: [[hora, %], ...]}}`: influencia de cada facción que no es CDSN, un punto cada vez que cambia (más el valor de antes de los 60 días, para que la gráfica empiece bien) |
| `zonas` | `{sistema: {"aaaa-mm-dd": ["High", "Med", "Low"]}}`: niveles de zona de conflicto vistos cada día |
| `portanaves` | `{sistema: {"XXX-XXX": {"n": nombre, "d": primera vez, "u": última vez}}}`: portanaves que han pasado por el sistema |
| `t` | hora en que se generó |
