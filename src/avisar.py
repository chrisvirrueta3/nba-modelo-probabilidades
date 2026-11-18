"""
Aviso al teléfono cuando hay apuestas que convienen.

Usa ntfy (https://ntfy.sh), una app gratis de notificaciones que no pide cuenta:
instala "ntfy" en el teléfono y suscríbete al tema que está en .env como NTFY_TOPIC.

Lee web/datos.json (lo escribe exportar_web.py) y avisa solo de apuestas NUEVAS
de partidos que no han empezado. Recuerda lo que ya avisó en datos/avisos_enviados.json.

Uso (después de exportar_web.py):
    python src/avisar.py
Si NTFY_TOPIC no está en .env, no hace nada.
"""
import json
import math
import os
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

import config
import puntos



def a_americano(d: float) -> int:
    return math.ceil((d - 1) * 100) if d >= 2 else -math.floor(100 / (d - 1))


def fmt_momio(m: int) -> str:
    return f"+{m}" if m > 0 else f"−{abs(m)}"


def hora(iso: str) -> str:
    import pandas as pd
    return pd.Timestamp(iso).tz_convert("America/Mexico_City").strftime("%H:%M")


def picks(d: dict) -> list:
    ahora = datetime.now(timezone.utc)
    cfg = d["config"]
    salida = []
    for p in d["proximos"]:
        if datetime.fromisoformat(p["inicio"]) <= ahora:
            continue
        for l in p["lados"]:
            if l["estado"] == "valor":
                minimo = a_americano((1 + cfg["umbral_ev"]) / ((l.get("prob") or l["modelo"]) / 100))
                salida.append((f"{p['id']}-h2h-{l['equipo']}", p, f"Ganan {l['equipo']}", minimo, l["monto"]))
        for x in p.get("puntos", []):
            if x["estado"] == "valor" and x.get("modelo"):
                u = cfg.get("umbral_ev_puntos", 0.05)
                pr = p.get("proyeccion") or {}
                try:  # mismo cálculo que la página (considera el empate en líneas exactas)
                    linea = float(x["texto"].split()[-1])
                    g, _, l = puntos.probs_apuesta(x["mercado"], x["lado"], linea, pr.get("margen_apuesta") or pr["margen_local"], pr.get("total_apuesta") or pr["total"],
                                                   pr.get("sigma_margen") or 14.3, pr.get("sigma_total") or 19.3)
                    minimo = a_americano(1 + (u + l) / g)
                except (KeyError, TypeError, ValueError):
                    minimo = a_americano((1 + u) / (x["modelo"] / 100))
                texto = x["texto"].replace("Over", "Más de").replace("Under", "Menos de").replace("-", "−")
                salida.append((f"{p['id']}-{x['mercado']}-{x['lado']}", p, texto, minimo, x["monto"]))
    return salida


def main():
    load_dotenv(config.RAIZ / ".env")
    tema = os.environ.get("NTFY_TOPIC", "").strip()
    if not tema:
        print("Avisos: NTFY_TOPIC no está en .env (se omite).")
        return
    if "--error" in sys.argv:
        requests.post(f"https://ntfy.sh/{tema}", timeout=20, headers={"Title": "NBA: la rutina automatica fallo", "Tags": "warning"},
                      data="La rutina automática no terminó. Corre rutina.bat a mano para ver el error "
                           "(o revisa datos\\ultima_rutina.log).".encode("utf-8"))
        return
    d = json.loads((config.RAIZ / "web" / "datos.json").read_text(encoding="utf-8"))
    ruta = config.DATOS / "avisos_enviados.json"
    enviados = set(json.loads(ruta.read_text())) if ruta.exists() else set()
    nuevos = [x for x in picks(d) if x[0] not in enviados]
    if not nuevos:
        print("Avisos: no hay apuestas nuevas que avisar.")
        return
    lineas = [f"• {texto} ({p['visita']} @ {p['local']}, {hora(p['inicio'])}): Draftea {fmt_momio(m)} o más · ${monto:.0f}"
              for _, p, texto, m, monto in sorted(nuevos, key=lambda x: x[1]["inicio"])]
    cuerpo = "\n".join(lineas[:8]) + ("\n…y más en la página" if len(lineas) > 8 else "")
    url_pagina = "https://chrisvirrueta3.github.io/nba-modelo-probabilidades/"
    r = requests.post(f"https://ntfy.sh/{tema}", data=cuerpo.encode("utf-8"), timeout=20, headers={
        "Title": f"NBA: {len(nuevos)} apuesta{'s' if len(nuevos) != 1 else ''} que conviene{'n' if len(nuevos) != 1 else ''}",
        "Tags": "basketball", "Click": url_pagina})
    r.raise_for_status()
    ruta.write_text(json.dumps(sorted(enviados | {x[0] for x in nuevos})))
    print(f"Avisos: enviado al teléfono ({len(nuevos)} apuestas nuevas).")


if __name__ == "__main__":
    main()
