"""
Control de créditos de The Odds API (plan gratis: 500 al mes).

Cada llamada guarda en datos/momios/creditos.json cuántos créditos quedan.
- Los momios (6 créditos) se dejan de bajar cuando quedan menos de RESERVA_CREDITOS:
  esa reserva queda para los resultados, que son los que liquidan las apuestas.
- Los resultados (2 créditos) se siguen bajando hasta que se acaben.
La página muestra cuántos quedan y para cuántos días alcanzan.
"""
import json
from datetime import datetime, timezone

import config

RUTA = config.MOMIOS / "creditos.json"


def leer() -> dict | None:
    try:
        return json.loads(RUTA.read_text())
    except (OSError, ValueError):
        return None


def guardar(headers) -> None:
    rest, usados = headers.get("x-requests-remaining"), headers.get("x-requests-used")
    if rest is None:
        return
    datos = {"restantes": int(float(rest)), "usados": int(float(usados or 0)),
             "fecha": datetime.now(timezone.utc).isoformat(timespec="minutes")}
    RUTA.write_text(json.dumps(datos))


def alcanza(costo: int, reserva: int = 0) -> bool:
    """¿Quedan créditos para gastar `costo` sin bajar de `reserva`? Sin dato, se asume que sí."""
    d = leer()
    return d is None or d["restantes"] - costo >= reserva
