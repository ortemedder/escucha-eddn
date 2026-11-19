# escucha-eddn

Escucha de EDDN para un Linux (Orange Pi): sigue en directo el estado de la facción
**Caballeros de Sion (CDSN)** en todos sus sistemas y lo publica en
[cdsn-datos](https://github.com/ortemedder/cdsn-datos) (`faccion.json`), de donde lo leen
el [panel-elite](https://github.com/ortemedder/panel-elite), el [radar-cdsn](https://github.com/ortemedder/radar-cdsn),
la [cdsn-web](https://github.com/ortemedder/cdsn-web) y el [escucha-s3](https://github.com/ortemedder/escucha-s3).

## Qué hace
- **EDDN en directo** (`tcp://eddn.edcd.io:9500`, solo galaxia actual): influencia, estados, conflictos,
  facciones, Powerplay, población… de cada sistema donde está la facción.
- **EDSM** cada 6 h para los sistemas de los que no llega nada.
- **Visitas**: pilotos distintos por día en cada sistema; **zonas de conflicto** y **portanaves** vistos.
- **Tick de cada sistema**: lo detecta cuando cambia la influencia y cruza las ventanas de varios días
  para prever el siguiente (`tick_ult`, `tick_prox`, `tick_disp`). Además, el **tick global** de
  [tick.edcd.io](https://tick.edcd.io) como respaldo (`tick_global`).
- **Histórico de influencia** (`hinf`, últimos 14 cambios).
- **Filtro de datos sospechosos**: descarta datos de EDDN sin sentido y espera confirmación de otro piloto en saltos grandes.
- **Guerra thargoide**: en tus sistemas (campo `thargoid` de cada sistema) y en los de menos de 20 al
  (`thargoides`: estado, progreso, puertos, tiempo restante y sistema propio más cercano). Aviso por Discord al cambiar.
- **Más datos (v8)**: rivales que suben varios ticks seguidos (`rivales`), estaciones con dueño, plataformas,
  mercado, astillero y atraques concedidos/denegados (`estaciones`), saltos por hora (`saltos`), rutas que pasan
  por tus sistemas (`rutas`), candidatos para expandirse (`expansion`), códice cercano (`codice`) y desde
  cuándo está cada portanaves (`d`). Avisos por Discord: rival que sube 3 ticks, estación ganada/perdida y pico de saltos.
- **Versión** visible al arrancar y en `faccion.json` (`ver`).
- **GitHub**: sube `faccion.json` a cdsn-datos cada 15 min si ha cambiado.
- **Discord** (opcional): avisos de sistemas nuevos, conflictos, retiradas, expansiones, ventaja baja,
  y resumen diario a las 21:00.
- **Red local**: `http://IP:8090/faccion.json`.

## Instalación
```bash
sudo apt install python3-zmq          # o: pip install pyzmq
mkdir -p /root/elite/escucha-eddn && cd /root/elite/escucha-eddn
# copiar aquí escucha_faccion.py
cp config.json.ejemplo config.json    # opcional: cambiar facción, puerto, horas...
echo "TOKEN_DE_GITHUB" > github_token.txt            # permiso de escritura en cdsn-datos
echo "URL_DEL_WEBHOOK" > discord_webhook.txt         # opcional
cp escucha-eddn.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now escucha-eddn
journalctl -u escucha-eddn -f
```
`github_token.txt` y `discord_webhook.txt` son claves: **no se suben nunca** (están en `.gitignore`).

## Comandos útiles
```bash
journalctl -u escucha-eddn -f                      # ver lo que hace
journalctl -u escucha-eddn --since today | grep TICK
journalctl -u escucha-eddn --since today | grep -i discord
systemctl restart escucha-eddn
```

## Versiones
- v1: EDDN + EDSM, servidor local.
- v2: subida a GitHub (cdsn-datos).
- v3: visitas, zonas de conflicto, portanaves y Powerplay de alrededor.
- Discord: avisos y resumen diario.
- v4: tick de cada sistema (ventanas cruzadas entre días) y tick global de tick.edcd.io.
- v5: histórico de influencia (`hinf`).
- v6: filtro de datos sospechosos de EDDN.
- v7: versión visible (`ver`) y guerra thargoide (`thargoid`, `thargoides`) con avisos a Discord.
- v8: rivales, estaciones, mercado, atraques, saltos por hora, rutas, candidatos de expansión y códice.
- v9: posibles ataques: si un sistema tiene pico de visitas (hoy o ayer ≥ 5 pilotos y ≥ 3 veces la media de 7 días) y la influencia baja ≥ 1 punto, avisa por Discord; al terminar avisa si la influencia se recuperó y lo guarda en `ataques.hist` (los 30 últimos) de faccion.json. El tráfico guarda ahora 9 días.

- v10: conflictos día a día: día del conflicto (1–7), fase (DEFENSA EN CURSO, DISPUTADO, DÍA DECISIVO, SISTEMA EN DERROTA...), qué se juega hoy, resultado de cada día y lo que hay en juego; historial de conflictos (`conflictos_hist`); quién sube cuando bajamos (`sube_cuando_baja`) y rivales vigilados (`rivales`); avisos de todo eso por Discord. Con un conflicto activo, las visitas ya no lanzan POSIBLE ATAQUE. EDSM ya no borra los conflictos que vio EDDN.

Todos los campos de `faccion.json` están explicados en [DATOS.md](DATOS.md).

Creado por CMDR ORTEM ED DER (ortemedder@gmail.com) con Claude.
