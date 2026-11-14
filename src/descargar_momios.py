"""
FASE 1 · Paso 3: guardar momios actuales (The Odds API).

POR QUÉ EMPEZAR YA: los momios históricos cuestan dinero. Si guardas una
"foto" de los momios cada día desde hoy, en unas semanas tendrás tus propios
datos gratis, incluida la línea de cierre (CLV), que es la métrica que dice si
el modelo de verdad le gana al mercado.

Plan gratuito: 500 créditos/mes. Cada llamada cuesta (mercados × regiones)
= 3 × 2 = 6 créditos -> unas 80 llamadas al mes (2 al día de sobra).

Configuración: crea un archivo .env en la raíz del proyecto con
    ODDS_API_KEY=tu_clave
(la clave se saca gratis en https://the-odds-api.com)

Uso:
    python src/descargar_momios.py
    python src/descargar_momios.py --si-viejo 180   # solo si el último snapshot tiene más de 180 min
"""
import argparse
import json
import os
from datetime import datetime, timezone

import pandas as pd
import requests
from dotenv import load_dotenv

import config

URL = f"https://api.the-odds-api.com/v4/sports/{config.DEPORTE_ODDS}/odds"


def pedir_momios(api_key: str) -> tuple[list, dict]:
    params = {
        "apiKey": api_key,
        "regions": config.REGIONES_ODDS,
        "markets": config.MERCADOS_ODDS,
        "oddsFormat": "american",
        "dateFormat": "iso",
    }
    r = requests.get(URL, params=params, timeout=30)
    if r.status_code == 401:
        raise SystemExit("Clave inválida. Revisa ODDS_API_KEY en tu archivo .env")
    if r.status_code == 429:
        raise SystemExit("Se acabaron los créditos del mes (o vas muy rápido).")
    r.raise_for_status()
    creditos = {
        "usados": r.headers.get("x-requests-used"),
        "restantes": r.headers.get("x-requests-remaining"),
    }
    return r.json(), creditos


def aplanar(eventos: list, capturado: str) -> pd.DataFrame:
    """Convierte el JSON anidado en una tabla: una fila por casa/mercado/resultado."""
    filas = []
    for ev in eventos:
        local, visita = ev["home_team"], ev["away_team"]
        for casa in ev.get("bookmakers", []):
            for mercado in casa.get("markets", []):
                for res in mercado.get("outcomes", []):
                    filas.append({
                        "CAPTURADO_UTC": capturado,
                        "EVENTO_ID": ev["id"],
                        "INICIO_UTC": ev["commence_time"],
                        "LOCAL": config.abreviatura(local),
                        "VISITA": config.abreviatura(visita),
                        "CASA": casa["key"],
                        "MERCADO": mercado["key"],            # h2h / spreads / totals
                        "RESULTADO": res["name"],             # equipo, "Over" o "Under"
                        "LINEA": res.get("point"),            # spread o total (vacío en h2h)
                        "MOMIO": res["price"],                # formato americano
                    })
    return pd.DataFrame(filas)


def snapshot_reciente(minutos: int) -> bool:
    """True si ya hay momios capturados hace menos de `minutos` (para ahorrar créditos)."""
    historico = config.MOMIOS / "momios_historico.csv"
    if not historico.exists():
        return False
    ultima = pd.read_csv(historico, usecols=["CAPTURADO_UTC"])["CAPTURADO_UTC"].max()
    edad = datetime.now(timezone.utc) - pd.to_datetime(ultima, utc=True)
    return edad.total_seconds() < minutos * 60


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--si-viejo", type=int, default=0, metavar="MIN")
    args = parser.parse_args()
    if args.si_viejo and snapshot_reciente(args.si_viejo):
        print(f"Momios de hace menos de {args.si_viejo} min: no se descargan (ahorro de créditos).")
        return

    load_dotenv(config.RAIZ / ".env")
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        raise SystemExit("Falta ODDS_API_KEY. Crea el archivo .env (ver instrucciones arriba).")

    ahora = datetime.now(timezone.utc)
    sello = ahora.strftime("%Y%m%d_%H%M")
    eventos, creditos = pedir_momios(api_key)

    # 1) Guardamos el JSON crudo, por si después queremos otra cosa de él
    (config.MOMIOS / f"snapshot_{sello}.json").write_text(json.dumps(eventos, indent=1))

    # 2) Y lo agregamos a una tabla histórica acumulada
    df = aplanar(eventos, ahora.isoformat())
    historico = config.MOMIOS / "momios_historico.csv"
    df.to_csv(historico, mode="a", header=not historico.exists(), index=False)

    print(f"{len(eventos)} partidos, {len(df)} momios guardados.")
    print(f"Créditos usados: {creditos['usados']} · restantes: {creditos['restantes']}")


if __name__ == "__main__":
    main()
