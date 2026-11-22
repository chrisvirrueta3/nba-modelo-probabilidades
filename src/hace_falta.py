"""
¿Se perdió una corrida programada? (la usa rutina_auto.bat al prender o desbloquear la computadora)

Horarios: 9:00 y 17:30 (hora de México). Si ya pasó uno de esos horarios hoy y la última
actualización de la página (web/datos.json) es anterior a él, se perdió: sale con código 0
(hay que correr la rutina). Si no se perdió nada, sale con código 1 (no hacer nada).
"""
import json
import sys
from datetime import datetime, timedelta, timezone

import config

MX = timezone(timedelta(hours=-6))   # México ya no cambia de horario
HORARIOS = [(9, 0), (17, 30)]


def ocupado() -> int:
    """0 si otra rutina está corriendo (candado de menos de 40 minutos), 1 si no."""
    candado = config.DATOS / "rutina.lock"
    if candado.exists():
        edad = datetime.now(timezone.utc).timestamp() - candado.stat().st_mtime
        if edad < 40 * 60:
            return 0
    return 1


def main() -> int:
    if "--ocupado" in sys.argv:
        return ocupado()
    ahora = datetime.now(MX)
    try:
        d = json.loads((config.RAIZ / "web" / "datos.json").read_text(encoding="utf-8"))
        ultima = datetime.fromisoformat(d["actualizado"]).astimezone(MX)
    except (OSError, ValueError, KeyError):
        return 0  # sin datos: mejor correr
    pasados = [ahora.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in HORARIOS]
    pasados = [t for t in pasados if t <= ahora]
    if not pasados:
        return 1  # antes de las 9:00: todavía no toca nada
    perdido = max(pasados)
    if ultima < perdido:
        print(f"Se perdió la corrida de las {perdido:%H:%M} (última actualización {ultima:%d/%m %H:%M}): se corre ahora.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
