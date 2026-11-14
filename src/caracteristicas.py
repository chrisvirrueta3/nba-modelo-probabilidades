"""
FASE 3 · Variables ("features") que el Elo no conoce.

Para cada partido calculamos, usando SOLO información anterior a ese partido:
  - Descanso: días desde el último juego de cada equipo (tope 4).
  - Back-to-back (B2B): jugó ayer.
  - 3 en 4: es su 3er partido en 4 noches (cansancio acumulado).
  - Net Rating de la temporada: puntos a favor − en contra por cada 100 posesiones.
    Se "encoge" hacia 0 al inicio de temporada (con 3 partidos no sabemos mucho).
  - Net Rating de los últimos 10 partidos: forma reciente.
  - Diferencia de Elo (con ventaja de local).
  - Ritmo y eficiencia (para spreads y totales): posesiones por partido (PACE),
    puntos anotados por 100 posesiones (ORTG) y recibidos (DRTG), encogidos hacia
    el promedio de la liga al inicio de temporada.
  - Promedio de la liga: puntos totales de los últimos 300 partidos (los totales
    cambian de una temporada a otra).

Posesiones (estimación estándar): FGA − OREB + TOV + 0.44 × FTA
"""
import numpy as np
import pandas as pd

import config

ENCOGIMIENTO = 8  # con n partidos jugados, el net rating pesa n / (n + 8)

COLUMNAS_MODELO = [
    "ELO_DIF", "DIF_NET", "DIF_NET10", "DIF_DESCANSO",
    "L_B2B", "V_B2B", "L_3EN4", "V_3EN4", "SEDE_NEUTRAL", "DIF_BAJAS",
]

VENTANA_LIGA = 300


def agregar_bajas_historicas(p: pd.DataFrame) -> pd.DataFrame:
    """Agrega L_BAJAS y V_BAJAS (valor ausente real de cada equipo en cada partido)."""
    ruta = config.PROCESADOS / "bajas_historicas.csv"
    p = p.drop(columns=[c for c in ("L_BAJAS", "V_BAJAS") if c in p], errors="ignore")
    if not ruta.exists():
        print("  Aviso: no hay bajas_historicas.csv (corre bajas.py). Se usan 0.")
        return p.assign(L_BAJAS=0.0, V_BAJAS=0.0)
    b = pd.read_csv(ruta, dtype={"GAME_ID": str})[["GAME_ID", "EQUIPO", "BAJAS"]]
    p = p.merge(b.rename(columns={"EQUIPO": "LOCAL", "BAJAS": "L_BAJAS"}), on=["GAME_ID", "LOCAL"], how="left")
    p = p.merge(b.rename(columns={"EQUIPO": "VISITA", "BAJAS": "V_BAJAS"}), on=["GAME_ID", "VISITA"], how="left")
    return p.fillna({"L_BAJAS": 0.0, "V_BAJAS": 0.0})


def _tabla_por_equipo(p: pd.DataFrame) -> pd.DataFrame:
    """Una fila por equipo por partido (partidos futuros llevan NaN en resultados)."""
    poss_l = p["L_FGA"] - p["L_OREB"] + p["L_TOV"] + 0.44 * p["L_FTA"]
    poss_v = p["V_FGA"] - p["V_OREB"] + p["V_TOV"] + 0.44 * p["V_FTA"]
    poss = (poss_l + poss_v) / 2
    base = p[["GAME_ID", "FECHA", "TEMPORADA"]]
    local = base.assign(EQUIPO=p["LOCAL"], MARGEN=p["L_PTS"] - p["V_PTS"], PF=p["L_PTS"], PC=p["V_PTS"],
                        POSS=poss, LADO="L")
    visita = base.assign(EQUIPO=p["VISITA"], MARGEN=p["V_PTS"] - p["L_PTS"], PF=p["V_PTS"], PC=p["L_PTS"],
                         POSS=poss, LADO="V")
    return pd.concat([local, visita], ignore_index=True).sort_values(["EQUIPO", "FECHA", "GAME_ID"])


def _liga_por_fecha(p: pd.DataFrame) -> pd.DataFrame:
    """
    Para cada fecha: promedio de la liga en los últimos VENTANA_LIGA partidos
    jugados ANTES de esa fecha (total de puntos, puntos por 100 posesiones, ritmo).
    """
    comp = p.dropna(subset=["L_PTS", "V_PTS"]).sort_values("FECHA")
    poss = ((comp["L_FGA"] - comp["L_OREB"] + comp["L_TOV"] + 0.44 * comp["L_FTA"])
            + (comp["V_FGA"] - comp["V_OREB"] + comp["V_TOV"] + 0.44 * comp["V_FTA"])) / 2
    total = (comp["L_PTS"] + comp["V_PTS"]).to_numpy()
    poss = poss.to_numpy()
    fechas_comp = comp["FECHA"].to_numpy()
    filas = []
    for f in np.sort(p["FECHA"].unique()):
        k = np.searchsorted(fechas_comp, f, side="left")  # partidos estrictamente antes
        ini = max(0, k - VENTANA_LIGA)
        if k - ini < 30:
            filas.append((f, np.nan, np.nan, np.nan))
            continue
        t, ps = total[ini:k], poss[ini:k]
        filas.append((f, t.mean(), 100 * t.sum() / (2 * ps.sum()), ps.mean()))
    liga = pd.DataFrame(filas, columns=["FECHA", "LIGA_TOTAL", "LIGA_RTG", "LIGA_PACE"])
    return liga.bfill()  # las primeras fechas del histórico toman el primer valor disponible


def _calcular(eq: pd.DataFrame, liga: pd.DataFrame | None = None) -> pd.DataFrame:
    g_eq = eq.groupby("EQUIPO", group_keys=False)

    # --- Cansancio ---
    dias = g_eq["FECHA"].diff().dt.days
    eq["DESCANSO"] = (dias - 1).clip(upper=4).fillna(4)
    eq["B2B"] = (eq["DESCANSO"] == 0).astype(int)
    # partidos jugados en los 3 días anteriores
    def previos_3dias(fechas: pd.Series) -> pd.Series:
        f = fechas.to_numpy().astype("datetime64[D]")
        inicio = np.searchsorted(f, f - np.timedelta64(3, "D"), side="left")
        return pd.Series(np.arange(len(f)) - inicio, index=fechas.index)
    eq["3EN4"] = (g_eq["FECHA"].apply(previos_3dias) >= 2).astype(int)

    # --- Rendimiento (solo con partidos ANTERIORES: shift(1)) ---
    g = eq.groupby(["EQUIPO", "TEMPORADA"], group_keys=False)
    marg_acum = g["MARGEN"].transform(lambda s: s.shift(1).cumsum())
    poss_acum = g["POSS"].transform(lambda s: s.shift(1).cumsum())
    n = g.cumcount()
    net = 100 * marg_acum / poss_acum
    eq["NET"] = (net * n / (n + ENCOGIMIENTO)).fillna(0)

    marg10 = g["MARGEN"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).sum())
    poss10 = g["POSS"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).sum())
    eq["NET10"] = (100 * marg10 / poss10).fillna(eq["NET"])

    # --- Ritmo y eficiencia, encogidos hacia el promedio de la liga ---
    if liga is not None:
        eq = eq.merge(liga, on="FECHA", how="left")
        g = eq.groupby(["EQUIPO", "TEMPORADA"], group_keys=False)
        n = g.cumcount()
        pf = g["PF"].transform(lambda s: s.shift(1).cumsum()).fillna(0)
        pc = g["PC"].transform(lambda s: s.shift(1).cumsum()).fillna(0)
        ps = g["POSS"].transform(lambda s: s.shift(1).cumsum()).fillna(0)
        k = ENCOGIMIENTO
        # (puntos reales + k "partidos promedio") / (posesiones reales + k partidos promedio)
        eq["ORTG"] = 100 * (pf + k * eq["LIGA_PACE"] * eq["LIGA_RTG"] / 100) / (ps + k * eq["LIGA_PACE"])
        eq["DRTG"] = 100 * (pc + k * eq["LIGA_PACE"] * eq["LIGA_RTG"] / 100) / (ps + k * eq["LIGA_PACE"])
        eq["PACE"] = (ps + k * eq["LIGA_PACE"]) / (n + k)
    return eq


def construir(partidos: pd.DataFrame) -> pd.DataFrame:
    """
    partidos: debe traer LOCAL, VISITA, FECHA, TEMPORADA, SEDE_NEUTRAL, estadísticas
              y ELO_DIF (diferencia de Elo pre-partido con ventaja de local).
    Devuelve partidos + columnas de COLUMNAS_MODELO.
    """
    liga = _liga_por_fecha(partidos)
    eq = _calcular(_tabla_por_equipo(partidos), liga)
    cols = ["GAME_ID", "DESCANSO", "B2B", "3EN4", "NET", "NET10", "ORTG", "DRTG", "PACE"]
    l = eq[eq["LADO"] == "L"][cols].add_prefix("L_").rename(columns={"L_GAME_ID": "GAME_ID"})
    v = eq[eq["LADO"] == "V"][cols].add_prefix("V_").rename(columns={"V_GAME_ID": "GAME_ID"})
    out = partidos.merge(l, on="GAME_ID").merge(v, on="GAME_ID")

    out["DIF_NET"] = out["L_NET"] - out["V_NET"]
    out["DIF_NET10"] = out["L_NET10"] - out["V_NET10"]
    out["DIF_DESCANSO"] = out["L_DESCANSO"] - out["V_DESCANSO"]
    for c in ("L_BAJAS", "V_BAJAS"):
        if c not in out:
            out[c] = 0.0
    out["DIF_BAJAS"] = out["L_BAJAS"].fillna(0) - out["V_BAJAS"].fillna(0)
    out["SUMA_BAJAS"] = out["L_BAJAS"].fillna(0) + out["V_BAJAS"].fillna(0)

    out = out.drop(columns=[c for c in ("LIGA_TOTAL",) if c in out]).merge(
        liga[["FECHA", "LIGA_TOTAL"]], on="FECHA", how="left")
    # Total esperado "de libro": ritmo promedio × (ataque de uno vs. defensa del otro)
    ritmo = (out["L_PACE"] + out["V_PACE"]) / 2
    out["EXP_TOTAL"] = ritmo * ((out["L_ORTG"] + out["V_DRTG"]) / 2 + (out["V_ORTG"] + out["L_DRTG"]) / 2) / 100
    return out
