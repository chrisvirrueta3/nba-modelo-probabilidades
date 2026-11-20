"""
Revisión de lesiones antes de los partidos.

La corre Windows cada 30 minutos por la tarde (ver programar_rutina.ps1).
Toma las apuestas que "convienen" en web/datos.json (la última corrida de rutina.bat)
de los partidos que empiezan en las próximas 2.5 horas, vuelve a calcular el modelo con
el reporte de lesiones MÁS RECIENTE de ESPN (usa los momios ya guardados: no gasta créditos)
y, si una apuesta ya no conviene, manda un aviso al teléfono: "Cancela ...".

Cada apuesta se avisa una sola vez (datos/avisos_cancelados.json).
El detalle queda en datos/revision_lesiones.log.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

import config

LOG = config.DATOS / "revision_lesiones.log"


def log(msg: str) -> None:
    linea = f"{datetime.now().strftime('%Y-%m-%d %H:%M')}  {msg}"
    print(linea)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


def picks_por_revisar(d: dict, horas: float = 2.5) -> list:
    ahora = datetime.now(timezone.utc)
    salida = []
    for p in d.get("proximos", []):
        inicio = datetime.fromisoformat(p["inicio"])
        if not (ahora < inicio <= ahora + timedelta(hours=horas)):
            continue
        for l in p["lados"]:
            if l["estado"] == "valor":
                salida.append({"clave": f"{p['id']}-h2h-{l['equipo']}", "evento": p["id"], "mercado": "h2h",
                               "lado": l["equipo"], "texto": f"Ganan {l['equipo']}", "partido": f"{p['visita']} @ {p['local']}",
                               "inicio": inicio, "prob": l.get("prob") or l["modelo"]})
        for x in p.get("puntos", []):
            if x["estado"] == "valor":
                texto = x["texto"].replace("Over", "Más de").replace("Under", "Menos de").replace("-", "−")
                salida.append({"clave": f"{p['id']}-{x['mercado']}-{x['lado']}", "evento": p["id"], "mercado": x["mercado"],
                               "lado": x["lado"], "texto": texto, "partido": f"{p['visita']} @ {p['local']}",
                               "inicio": inicio, "prob": x.get("prob") or x.get("modelo")})
    return salida


def main():
    d = json.loads((config.RAIZ / "web" / "datos.json").read_text(encoding="utf-8"))
    picks = picks_por_revisar(d)
    if not picks:
        return  # nada que revisar (no se escribe al log para no llenarlo)
    ruta = config.DATOS / "avisos_cancelados.json"
    avisados = set(json.loads(ruta.read_text())) if ruta.exists() else set()
    picks = [x for x in picks if x["clave"] not in avisados]
    if not picks:
        return

    import valor  # se importa aquí: carga los modelos solo cuando hace falta
    tabla, _, _ = valor.analizar()
    cancelar = []
    for x in picks:
        t = tabla[(tabla["EVENTO_ID"] == x["evento"]) & (tabla["MERCADO"] == x["mercado"]) & (tabla["LADO"] == x["lado"])]
        if t.empty:
            continue
        fila = t.iloc[0]
        if fila["ESTADO"] != "VALOR":
            ahora = fila.get("PROB_%", fila["MODELO_%"])
            motivo = {"SOSPECHOSA": "el modelo y las casas ya están muy lejos",
                      "SIN_REFERENCIA": "ya no hay momios de Pinnacle para revisar"}.get(fila["ESTADO"], "ya no tiene ventaja")
            cancelar.append((x, ahora, motivo))
            log(f"CANCELAR {x['texto']} ({x['partido']}): antes {x['prob']}%, ahora {ahora}% · {motivo}")
        else:
            log(f"sigue conviniendo: {x['texto']} ({x['partido']})")

    if not cancelar:
        return
    load_dotenv(config.RAIZ / ".env")
    tema = os.environ.get("NTFY_TOPIC", "").strip()
    if tema:
        cuerpo = "\n".join(
            f"• {x['texto']} ({x['partido']}, {x['inicio'].astimezone(timezone(timedelta(hours=-6))).strftime('%H:%M')}): "
            f"antes {x['prob']:.0f}%, ahora {ahora:.0f}% · {motivo}"
            for x, ahora, motivo in cancelar)
        cuerpo += "\nCambió el reporte de lesiones. Si no la has apostado, ya no la apuestes."
        requests.post(f"https://ntfy.sh/{tema}", data=cuerpo.encode("utf-8"), timeout=20, headers={
            "Title": f"NBA: cancela {len(cancelar)} apuesta{'s' if len(cancelar) > 1 else ''}",
            "Tags": "warning,basketball", "Priority": "high",
            "Click": "https://chrisvirrueta3.github.io/nba-modelo-probabilidades/"})
    ruta.write_text(json.dumps(sorted(avisados | {x["clave"] for x, _, _ in cancelar})))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # corre en segundo plano: que el error quede en el log
        log(f"ERROR: {e!r}")
        sys.exit(1)
