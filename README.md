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

## Relleno con el archivo de EDDN (una sola vez)
EDDN no guarda nada, pero [edgalaxydata.space](https://edgalaxydata.space/EDDN) archiva todos sus mensajes por días.
`relleno_eddn.py` saca de ahí las **visitas** (60 días), el **mapa de horas** (28 días) y el **histórico de influencia**
de nuestros sistemas y los mezcla en `faccion.json` sin borrar nada (en cada día se queda con el número más alto).
```bash
python relleno_eddn.py descargar            # en el PC (tarda: baja varios GB); si se corta, se relanza y sigue
# copiar relleno.json a /root/elite/escucha-eddn de la Orange Pi, y allí:
systemctl stop escucha-eddn
python3 relleno_eddn.py mezclar relleno.json faccion.json     # deja copia en faccion.json.antes_relleno
systemctl start escucha-eddn
```
Opciones: `--dias 30` (menos días), `--atraques` (cuenta también los atraques como visitas; mucha más descarga).

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

- v10: conflictos día a día: día del conflicto (1–7), fase (DEFENSA EN CURSO, DISPUTADO, DÍA DECISIVO, SISTEMA EN DERROTA...), qué se juega hoy, resultado de cada día y lo que hay en juego; historial de conflictos (`conflictos_hist`); quién sube cuando bajamos (`sube_cuando_baja`) y rivales vigilados (`rivales`); avisos de todo eso por Discord. Con un conflicto activo, las visitas ya no lanzan POSIBLE ATAQUE. EDSM ya no borra los conflictos que vio EDDN. Las visitas (`trafico`) se guardan 31 días.
- v11: expansiones y retiradas de otras facciones en nuestros sistemas y a menos de 30 al (`vecinos`), con aviso si una expansión puede llegar a uno nuestro; felicidad de cada facción (`fel`); estado de las estaciones (dañada, bajo ataque...); cambios de población y seguridad (`hsis`); saltos por día y hora (`hdia`, 14 días) para el mapa de horas; asentamientos de Odyssey (`asent`). Todo con avisos a Discord.
- v11.1: obras (*Construction Site*) en nuestros sistemas: campo `obra` en la estación y avisos de obra nueva y obra terminada.
- v11.2: si CDSN sale con 0 % de influencia (EDSM la sigue listando), cuenta como que ya no está en el sistema.
- v11.3: `faccion.json` se sube compacto (sin espacios, un 35 % menos); histórico de influencia de 60 cambios, mapa de horas de 28 días y visitas de 60 días.
- v11.4: relleno automático cada 15 días (a las 4:00) con el archivo de EDDN: tapa los huecos de los cortes sin parar el escucha y avisa por Discord. Necesita `relleno_eddn.py` en la misma carpeta. Se cambia con `relleno_dias` y `relleno_hora` en config.json (`relleno_dias: 0` lo apaga).
- v11.5: el relleno pasa a ser **semanal, los viernes a las 7:00**, con los últimos 8 días (`relleno_dia` 0 lunes … 6 domingo, -1 nunca; `relleno_hora`; `relleno_atras`). **A mano:** `touch /root/elite/escucha-eddn/relleno_ya` (o `echo 30 > relleno_ya` para 30 días) y en menos de un minuto empieza; al acabar avisa por Discord.
- v11.6: cada aviso de Discord se guarda también en `noticias` (los 300 últimos, con hora, sección, si es urgente y sistema) para La Crónica de Sion de la web. Se guarda aunque no haya webhook de Discord.
- v11.7: cada 15 min mira `noticia_fija.txt` de cdsn-datos (la noticia fija que se escribe a mano); al cambiarla o quitarla, la anterior pasa a la `hemeroteca` con sus fechas, y avisa por Discord de cada noticia fija nueva.

Todos los campos de `faccion.json` están explicados en [DATOS.md](DATOS.md).

Creado por CMDR ORTEM ED DER (ortemedder@gmail.com) con Claude.
- v12.3: el relleno semanal pasa a los **jueves a las 7:10 UTC** (8:10 en España en invierno, 9:10 en verano), durante el mantenimiento de los servidores (`relleno_dia: 3`, `relleno_hora: 7`, `relleno_min: 10`, `relleno_utc: true`; con `relleno_utc: false` la hora es la de la Orange Pi).
- v12.4: el relleno lee también los **atraques** (Docked), así cuenta pilotos que no saltan al sistema y las visitas se parecen más a las del escucha en vivo. Tarda más (más o menos el doble). Se quita con `"relleno_atraques": false` en `config.json`.
