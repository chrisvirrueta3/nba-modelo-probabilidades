"""
LESIONES · Paso 3: reporte de lesiones de HOY (ESPN, gratis) -> bajas esperadas.

Para cada jugador lesionado de la rotación estimamos la probabilidad de que juegue:
  Fuera / suspendido ............ 0%
  "doubtful" (duda seria) ....... 20%
  "questionable" (en duda) ...... 50%
  "probable" .................... 85%
  Day-to-day sin más detalle .... 60%

BAJAS ESPERADAS = suma de VALOR × (1 − prob_jugar)

Uso:
    python src/lesiones.py      (muestra las bajas esperadas por equipo)
"""
import re

import pandas as pd
import requests

import config
from bajas import normalizar_nombre

URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"


def prob_jugar(estado: str, comentario: str) -> float:
    e, c = (estado or "").lower(), (comentario or "").lower()
    if e in ("out", "suspension") or re.search(r"ruled out|will not play|won't play|will miss|out for", c):
        return 0.0
    if re.search(r"will play|available|cleared|will start|expected to play", c):
        return 1.0
    if "doubtful" in c:
        return 0.2
    if "questionable" in c or "game-time" in c:
        return 0.5
    if "probable" in c:
        return 0.85
    return 0.6


def reporte() -> pd.DataFrame:
    """Una fila por jugador lesionado: equipo, jugador, estado, prob. de jugar."""
    d = requests.get(URL, timeout=30).json()
    filas = []
    for t in d.get("injuries", []):
        try:
            equipo = config.abreviatura(t["displayName"])
        except ValueError:
            continue
        for i in t.get("injuries", []):
            nombre = i["athlete"]["displayName"]
            filas.append({"EQUIPO": equipo, "JUGADOR_ESPN": nombre, "NOMBRE_NORM": normalizar_nombre(nombre),
                          "ESTADO": i.get("status"), "COMENTARIO": i.get("shortComment", ""),
                          "PROB_JUGAR": prob_jugar(i.get("status"), i.get("shortComment", ""))})
    return pd.DataFrame(filas)


def bajas_esperadas() -> tuple[pd.Series, pd.DataFrame]:
    """
    Devuelve (bajas esperadas por equipo, detalle de lesionados de la rotación).
    Solo cuentan jugadores de la rotación actual: los que llevan mucho tiempo fuera
    ya están reflejados en el rendimiento reciente del equipo (Elo, net rating).
    """
    rot = pd.read_csv(config.PROCESADOS / "rotaciones_actuales.csv")
    les = reporte()
    if les.empty:
        return pd.Series(dtype=float), les
    det = les.merge(rot[["EQUIPO", "NOMBRE_NORM", "JUGADOR", "VALOR", "MIN_PROM"]],
                    on=["EQUIPO", "NOMBRE_NORM"], how="inner")
    det["BAJA_ESPERADA"] = (det["VALOR"].clip(lower=0) * (1 - det["PROB_JUGAR"])).round(2)
    por_equipo = det.groupby("EQUIPO")["BAJA_ESPERADA"].sum()
    return por_equipo, det.sort_values(["EQUIPO", "VALOR"], ascending=[True, False])


def main():
    por_equipo, det = bajas_esperadas()
    if det.empty:
        print("No hay lesionados de rotación en el reporte.")
        return
    print("Lesionados de rotación (valor = Game Score promedio):\n")
    print(det[["EQUIPO", "JUGADOR", "VALOR", "ESTADO", "PROB_JUGAR", "BAJA_ESPERADA"]].to_string(index=False))
    print("\nBajas esperadas por equipo:")
    print(por_equipo.sort_values(ascending=False).round(1).to_string())


if __name__ == "__main__":
    main()
