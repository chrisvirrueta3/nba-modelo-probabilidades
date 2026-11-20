"""
Resumen semanal al teléfono (ntfy). Lo corre Windows los domingos (ver programar_rutina.ps1).
Lee web/datos.json (la última corrida de rutina.bat): no gasta créditos.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

import config


def main():
    load_dotenv(config.RAIZ / ".env")
    tema = os.environ.get("NTFY_TOPIC", "").strip()
    if not tema:
        print("NTFY_TOPIC no está en .env")
        return
    d = json.loads((config.RAIZ / "web" / "datos.json").read_text(encoding="utf-8"))
    desde = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    semana = [h for h in d.get("historial", []) if str(h.get("registrada") or "") >= desde
              and h.get("resultado") not in (None, "PENDIENTE")]
    gan = sum(h.get("ganancia") or 0 for h in semana)
    ok = sum(h.get("resultado") == "GANADA" for h in semana)
    clv = [h["clv"] for h in semana if h.get("clv") is not None]
    r = d.get("resumen", {})
    c = d.get("comparacion") or {}
    lineas = [
        f"Semana: {ok} de {len(semana)} apuestas ganadas · {'+' if gan >= 0 else '−'}${abs(gan):,.0f}" if semana
        else "Semana: no hubo apuestas liquidadas (normal: casi nunca hay valor con momios típicos).",
    ]
    if clv:
        lineas.append(f"Le ganamos al cierre en {sum(v > 0 for v in clv)} de {len(clv)}.")
    if r:
        lineas.append(f"Dinero de práctica: ${r.get('bankroll', 0):,.0f} (empezó en ${r.get('bankroll_inicial', 1000):,.0f}).")
    if c.get("partidos"):
        quien = "va mejor el modelo" if c["brier_modelo"] < c["brier_mercado"] else "van mejor las casas"
        lineas.append(f"Modelo vs. casas ({c['partidos']} partidos): {quien}"
                      + (" (todavía pocos partidos)." if c["partidos"] < 100 else "."))
    cr = d.get("creditos")
    if cr:
        lineas.append(f"Créditos de momios: {cr['restantes']}.")
    requests.post(f"https://ntfy.sh/{tema}", data="\n".join(lineas).encode("utf-8"), timeout=20, headers={
        "Title": "NBA: resumen de la semana", "Tags": "bar_chart",
        "Click": "https://chrisvirrueta3.github.io/nba-modelo-probabilidades/"})
    print("Resumen enviado.")


if __name__ == "__main__":
    main()
