"""
FASE 1 · Paso 2: convertir el game log en UNA fila por partido.

El game log trae dos filas por partido (una por equipo). El modelo necesita
una sola fila: local vs. visitante, con las estadísticas de ambos lado a lado.

Cómo sabemos quién es local:
    MATCHUP = "BOS vs. NYK"  -> BOS es local
    MATCHUP = "BOS @ NYK"    -> BOS es visitante

Salida: datos/procesados/partidos.csv
"""
import pandas as pd

import config

# Estadísticas que conservamos de cada equipo (sirven para calcular ratings en la fase 2)
STATS = ["PTS", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA",
         "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF"]


def cargar_crudos() -> pd.DataFrame:
    archivos = sorted(config.CRUDOS.glob("gamelog_*.csv"))
    if not archivos:
        raise FileNotFoundError("No hay datos crudos. Corre primero: python src/descargar_partidos.py")
    return pd.concat([pd.read_csv(a, dtype={"GAME_ID": str}) for a in archivos], ignore_index=True)


def a_una_fila_por_partido(log: pd.DataFrame) -> pd.DataFrame:
    log = log.copy()
    # Partidos en curso: stats.nba.com a veces los publica antes de terminar
    # (p. ej. 71-71 al final del 3er cuarto). Un partido completo suma al menos
    # 240 minutos por equipo; si alguno trae menos, se descarta por ahora.
    en_curso = log.groupby("GAME_ID")["MIN"].transform("min") < 240
    if en_curso.any():
        print(f"  {log.loc[en_curso, 'GAME_ID'].nunique()} partidos en curso se omitieron (aún no terminan).")
        log = log[~en_curso]
    log["ES_LOCAL"] = log["MATCHUP"].str.contains(" vs. ", regex=False)

    # Partidos en sede neutral (México, Europa, semis de la NBA Cup en Las Vegas):
    # los dos equipos aparecen con "@". Elegimos un "local nominal" (el primero en
    # orden alfabético) y los marcamos con SEDE_NEUTRAL=1 para que el modelo
    # no les dé ventaja de localía.
    sin_local = log.groupby("GAME_ID")["ES_LOCAL"].transform("sum") == 0
    log["SEDE_NEUTRAL"] = sin_local.astype(int)
    primero = log[sin_local].groupby("GAME_ID")["TEAM_ABBREVIATION"].transform("min")
    log.loc[sin_local, "ES_LOCAL"] = log.loc[sin_local, "TEAM_ABBREVIATION"] == primero
    if sin_local.any():
        print(f"  {log.loc[sin_local, 'GAME_ID'].nunique()} partidos en sede neutral (marcados con SEDE_NEUTRAL=1).")

    columnas = ["GAME_ID", "GAME_DATE", "TEMPORADA", "TIPO", "SEDE_NEUTRAL", "TEAM_ABBREVIATION", "MIN"] + STATS
    local = log[log["ES_LOCAL"]][columnas]
    visita = log[~log["ES_LOCAL"]][["GAME_ID", "TEAM_ABBREVIATION"] + STATS]

    local = local.rename(columns={"TEAM_ABBREVIATION": "LOCAL", **{s: f"L_{s}" for s in STATS}})
    visita = visita.rename(columns={"TEAM_ABBREVIATION": "VISITA", **{s: f"V_{s}" for s in STATS}})

    partidos = local.merge(visita, on="GAME_ID", how="inner")
    perdidos = set(log["GAME_ID"]) - set(partidos["GAME_ID"])
    if perdidos:
        print(f"  Aviso: {len(perdidos)} partidos incompletos se omitieron: {sorted(perdidos)[:5]}")

    partidos["FECHA"] = pd.to_datetime(partidos.pop("GAME_DATE"))
    partidos["MARGEN"] = partidos["L_PTS"] - partidos["V_PTS"]           # >0 ganó el local
    empatados = partidos["MARGEN"] == 0                                   # en tiempo extra todavía
    if empatados.any():
        print(f"  {empatados.sum()} partidos empatados (en curso) se omitieron.")
        partidos = partidos[~empatados].copy()
    partidos["TOTAL"] = partidos["L_PTS"] + partidos["V_PTS"]
    partidos["GANO_LOCAL"] = (partidos["MARGEN"] > 0).astype(int)
    partidos["TIEMPO_EXTRA"] = (partidos["MIN"] > 240).astype(int)        # 240 min = partido normal por equipo
    partidos = partidos.drop(columns="MIN")

    orden = ["GAME_ID", "FECHA", "TEMPORADA", "TIPO", "LOCAL", "VISITA",
             "SEDE_NEUTRAL", "L_PTS", "V_PTS", "MARGEN", "TOTAL", "GANO_LOCAL", "TIEMPO_EXTRA"]
    resto = [c for c in partidos.columns if c not in orden]
    return partidos[orden + resto].sort_values(["FECHA", "GAME_ID"]).reset_index(drop=True)


def validar(partidos: pd.DataFrame) -> None:
    """Revisiones básicas: si algo sale raro, mejor enterarse ahora que en el modelo."""
    assert partidos["GAME_ID"].is_unique, "Hay partidos duplicados"
    assert (partidos["MARGEN"] != 0).all(), "Hay empates (imposible en la NBA): revisar datos"
    assert (partidos["LOCAL"] != partidos["VISITA"]).all(), "Un equipo jugando contra sí mismo"

    print("\nResumen por temporada:")
    resumen = partidos.groupby(["TEMPORADA", "TIPO"]).agg(
        partidos=("GAME_ID", "count"),
        pct_gana_local=("GANO_LOCAL", "mean"),
        total_promedio=("TOTAL", "mean"),
    )
    resumen["pct_gana_local"] = (resumen["pct_gana_local"] * 100).round(1)
    resumen["total_promedio"] = resumen["total_promedio"].round(1)
    print(resumen.to_string())
    print("\n(Una temporada regular completa tiene 1,230 partidos; el local suele ganar ~54-58%.)")


def main():
    log = cargar_crudos()
    partidos = a_una_fila_por_partido(log)
    validar(partidos)
    ruta = config.PROCESADOS / "partidos.csv"
    partidos.to_csv(ruta, index=False)
    print(f"\nGuardado: {ruta}  ({len(partidos)} partidos)")


if __name__ == "__main__":
    main()
