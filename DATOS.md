# Datos de faccion.json

Qué saca el escucha de EDDN (y de EDSM y tick.edcd.io), qué guarda en `faccion.json` y quién lo usa.
**Si se añade un campo nuevo al escucha, se apunta aquí.**

`faccion.json` está en [cdsn-datos](https://github.com/ortemedder/cdsn-datos) (se sube cada 15 min si cambia) y en la red de casa en `http://IP:8090/faccion.json`.
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
| Cabecera de EDDN (`uploaderID`) | Todos | **Visitas**: pilotos distintos por día (id anónimo, no se sabe quién es) |
| **EDSM** (cada 6 h) | API | Facciones de los sistemas sin datos de EDDN (**sin conflictos**) y coordenadas |
| **tick.edcd.io** (cada 30 min) | API | Hora del último tick de la galaxia |

Lo que **no** da EDDN: quién es cada piloto, qué misiones hace, en qué día va un conflicto (lo cuenta el escucha) ni el resultado de cada día (lo deduce el escucha).

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
| **`rivales`** | **Facciones vigiladas** (ver punto 5) | **v10** |

---

## 3. Cada sistema (`sistemas["Nombre"]`)

### Influencia y estados
| Campo | Qué es |
|---|---|
| `sys`, `t`, `src` | Nombre, hora del dato y fuente (EDDN o EDSM) |
| `inf` | Influencia de CDSN |
| `prev`, `prev_t` | Influencia anterior (la última distinta) y su hora |
| `hinf` | Histórico: `[hora, influencia]`, últimos 14 cambios |
| `ctrl`, `ctrl_n` | Si CDSN controla el sistema y quién lo controla |
| `estado`, `activos`, `pendientes`, `recuperando` | Estados de CDSN (en inglés: War, Election, Expansion, Retreat...) |
| `segunda`, `segunda_inf` | Segunda facción e influencia |
| `todas` | Todas las facciones: `n` nombre, `inf`, `gov`, `alg`, `act`, `pend`, `jug` (de jugadores) |
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
| `trafico` | Pilotos distintos por día (`AAAA-MM-DD`: número), 9 días |
| `saltos` | Saltos que llegan por hora (últimas 48 h) |
| `rutas` | Rutas que pasan por el sistema, por día (8 días) |
| `zc` | Zonas de conflicto vistas en 24 h: `n`, `i` intensidad (Low/Med/High), `t` |
| `pn` | Portanaves vistos en 7 días: matrícula → `n` nombre, `t` visto, `d` desde cuándo |
| `thargoid` | Guerra thargoide en el sistema: estado, progreso, puertos... |

### Sistema y Powerplay
| Campo | Qué es |
|---|---|
| `pos` | Coordenadas `[x, y, z]` |
| `sis` | `pob` población, `eco`/`eco2` economía, `seg` seguridad, `gov` gobierno, `alg` alianza |
| `pp` | `pot` potencia, `est` estado, `prog` progreso, `ref` refuerzo, `soc` socavamiento, `pots` presentes |

### Estaciones (`estaciones["Nombre"]`)
| Campo | Qué es |
|---|---|
| `f`, `tipo`, `estado`, `ls`, `pads`, `mid`, `t` | Dueño, tipo, estado, distancia (ls), plataformas, MarketID, hora |
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
estación ganada o perdida · pico de saltos · thargoides · dato sospechoso · POSIBLE ATAQUE (no salta si hay conflicto, v10) y su final · resumen diario a las 21:00.

## 7. Ideas para más adelante (datos que EDDN manda y no guardamos)
- `Happiness` de cada facción (felicidad).
- Asentamientos (`ApproachSettlement`) y sus dueños en Odyssey.
- Cuerpos escaneados (`Scan`, `FSSAllBodiesFound`) en nuestros sistemas.
