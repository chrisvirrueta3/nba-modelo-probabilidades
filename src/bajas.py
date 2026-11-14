"""
LESIONES · Paso 2: medir cuánto le falta a cada equipo en cada partido.

1. Valor de cada jugador = promedio de su "Game Score" (Hollinger) en sus
   últimos 15 partidos. Es una medida simple de cuánto produce por partido:
     GmSc = PTS + 0.4·FGM − 0.7·FGA − 0.4·(FTA−FTM) + 0.7·OREB + 0.3·DREB
            + STL + 0.7·AST + 0.7·BLK − 0.4·PF − TOV
   (Estrella ≈ 18-25 · titular ≈ 10-14 · banca ≈ 3-7)

2. Rotación de un equipo antes de un partido = jugadores que jugaron al menos
   5 de los últimos 10 partidos del equipo (y que no fueron traspasados).

3. BAJAS de un equipo en un partido = suma del valor de los jugadores de su
   rotación que NO jugaron ese partido.

Nota honesta: en el histórico sabemos quién NO jugó al final (incluye bajas de
último minuto). Para partidos futuros usamos el reporte de lesiones, que es
incierto ("en duda"). Por eso el efecto real será un poco menor que en el backtest.

Uso:
    python src/bajas.py
Salidas:
    datos/procesados/bajas_historicas.csv   (GAME_ID, EQUIPO, BAJAS, FUERA)
    datos/procesados/rotaciones_actuales.csv (valor actual de cada jugador de rotación)
"""
import re
import unicodedata

import pandas as pd

import config

VENTANA_VALOR = 15
VENTANA_ROTACION = 10
MIN_JUEGOS_ROTACION = 5


def normalizar_nombre(nombre: str) -> str:
    """'Luka Dončić Jr.' -> 'lukadoncic'  (para empatar nombres entre ESPN y la NBA)."""
    s = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", s)
    return re.sub(r"[^a-z]", "", s)


def cargar_jugadores() -> pd.DataFrame:
    archivos = sorted(config.CRUDOS.glob("jugadores_*.csv"))
    if not archivos:
        raise FileNotFoundError("Faltan datos de jugadores. Corre: python src/descargar_jugadores.py")
    j = pd.concat([pd.read_csv(a, dtype={"GAME_ID": str}) for a in archivos], ignore_index=True)
    j["FECHA"] = pd.to_datetime(j["GAME_DATE"])
    j["GMSC"] = (j["PTS"] + 0.4 * j["FGM"] - 0.7 * j["FGA"] - 0.4 * (j["FTA"] - j["FTM"])
                 + 0.7 * j["OREB"] + 0.3 * j["DREB"] + j["STL"] + 0.7 * j["AST"]
                 + 0.7 * j["BLK"] - 0.4 * j["PF"] - j["TOV"])
    j = j.sort_values(["PLAYER_ID", "FECHA", "GAME_ID"]).reset_index(drop=True)
    # Valor del jugador DESPUÉS de cada partido (incluyéndolo). Para un partido que
    # se perdió, usamos el valor de su último partido jugado -> no hay fuga de futuro.
    j["VALOR"] = (j.groupby(["PLAYER_ID", "TEMPORADA"])["GMSC"]
                   .transform(lambda s: s.rolling(VENTANA_VALOR, min_periods=1).mean()))
    j["MIN_PROM"] = (j.groupby(["PLAYER_ID", "TEMPORADA"])["MIN"]
                      .transform(lambda s: s.rolling(VENTANA_VALOR, min_periods=1).mean()))
    # Producción por 36 minutos (para el +/− ajustado de apm.py)
    g = j.groupby(["PLAYER_ID", "TEMPORADA"])
    gmsc_sum = g["GMSC"].transform(lambda s: s.rolling(VENTANA_VALOR, min_periods=1).sum())
    min_sum = g["MIN"].transform(lambda s: s.rolling(VENTANA_VALOR, min_periods=1).sum())
    j["G36"] = 36 * gmsc_sum / min_sum.clip(lower=1)
    return j


def _rotacion(j_eq: pd.DataFrame, juegos: list, i: int, ultimo_equipo: dict, equipo: str, fecha) -> pd.DataFrame:
    """Jugadores de rotación del equipo antes del partido i, con su valor más reciente."""
    previos = juegos[max(0, i - VENTANA_ROTACION):i]
    if not previos:
        return j_eq.iloc[0:0]
    reciente = j_eq[j_eq["GAME_ID"].isin(previos)]
    conteo = reciente.groupby("PLAYER_ID").size()
    ids = conteo[conteo >= min(MIN_JUEGOS_ROTACION, len(previos) // 2 + 1)].index
    rot = reciente[reciente["PLAYER_ID"].isin(ids)].groupby("PLAYER_ID").last()
    # Fuera los traspasados: su partido más reciente (antes de esta fecha) fue con otro equipo
    rot = rot[[ultimo_equipo(pid, fecha) == equipo for pid in rot.index]]
    return rot


def calcular() -> tuple[pd.DataFrame, pd.DataFrame]:
    j = cargar_jugadores()

    # Para detectar traspasos: historial (fecha, equipo) por jugador
    hist_eq = {pid: (g["FECHA"].to_numpy(), g["TEAM_ABBREVIATION"].to_numpy())
               for pid, g in j.groupby("PLAYER_ID")}

    def ultimo_equipo(pid, fecha):
        fechas, equipos = hist_eq[pid]
        k = fechas.searchsorted(pd.Timestamp(fecha).to_datetime64(), side="left") - 1
        return equipos[k] if k >= 0 else None

    filas, rot_actual, detalle = [], [], []
    for (equipo, temporada), j_eq in j.groupby(["TEAM_ABBREVIATION", "TEMPORADA"]):
        juegos_df = j_eq.drop_duplicates("GAME_ID").sort_values(["FECHA", "GAME_ID"])
        juegos = juegos_df["GAME_ID"].tolist()
        fechas = juegos_df["FECHA"].tolist()
        for i, (gid, fecha) in enumerate(zip(juegos, fechas)):
            rot = _rotacion(j_eq, juegos, i, ultimo_equipo, equipo, fecha)
            jugaron = set(j_eq.loc[j_eq["GAME_ID"] == gid, "PLAYER_ID"])
            fuera = rot[~rot.index.isin(jugaron)]
            filas.append({"GAME_ID": gid, "EQUIPO": equipo,
                          "BAJAS": round(float(fuera["VALOR"].clip(lower=0).sum()), 2),
                          "FUERA": ", ".join(fuera["PLAYER_NAME"].tolist())})
            for pid, r in fuera.iterrows():
                detalle.append({"GAME_ID": gid, "EQUIPO": equipo, "TEMPORADA": temporada, "PLAYER_ID": pid,
                                "VALOR": round(float(r["VALOR"]), 2), "MIN_PROM": round(float(r["MIN_PROM"]), 1),
                                "G36": round(float(r["G36"]), 2)})

        if temporada == config.TEMPORADA_ACTUAL:
            fin = pd.Timestamp.now() + pd.Timedelta(days=1)
            rot = _rotacion(j_eq, juegos, len(juegos), ultimo_equipo, equipo, fin)
            for pid, r in rot.iterrows():
                rot_actual.append({"EQUIPO": equipo, "PLAYER_ID": pid, "JUGADOR": r["PLAYER_NAME"],
                                   "NOMBRE_NORM": normalizar_nombre(r["PLAYER_NAME"]),
                                   "VALOR": round(float(r["VALOR"]), 2), "MIN_PROM": round(float(r["MIN_PROM"]), 1),
                                   "G36": round(float(r["G36"]), 2)})

    pd.DataFrame(detalle).to_csv(config.PROCESADOS / "bajas_detalle.csv", index=False)
    return pd.DataFrame(filas), pd.DataFrame(rot_actual)


def main():
    bajas, rot = calcular()
    bajas.to_csv(config.PROCESADOS / "bajas_historicas.csv", index=False)
    rot.sort_values(["EQUIPO", "VALOR"], ascending=[True, False]).to_csv(
        config.PROCESADOS / "rotaciones_actuales.csv", index=False)
    print(f"Bajas históricas: {len(bajas)} registros equipo-partido "
          f"({(bajas['BAJAS'] > 0).mean():.0%} con al menos una baja de rotación).")
    print(f"Rotaciones actuales: {len(rot)} jugadores en {rot['EQUIPO'].nunique()} equipos.")
    print("\nPartidos con más valor ausente:")
    print(bajas.sort_values("BAJAS", ascending=False).head(5).to_string(index=False))


if __name__ == "__main__":
    main()
