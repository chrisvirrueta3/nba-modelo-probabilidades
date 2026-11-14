"""
VALOR DE JUGADORES · +/− ajustado (APM) con base de Game Score.

IDEA
  El margen de cada partido se explica por quién estuvo en cancha y cuánto:
     margen = ventaja_local + Σ (min_i/48)·β_i  (local)  − Σ (min_j/48)·β_j  (visita)
  β_i = puntos por 48 minutos que el jugador i suma (o resta) a su equipo,
  YA DESCONTANDO a sus compañeros y rivales. Mide también defensa e intangibles,
  que el Game Score no ve.

  Con pocos datos esta regresión es muy ruidosa, así que:
    1. Una primera regresión Ridge da un β "crudo".
    2. Ajustamos una recta  β ≈ a + b·(Game Score por 36 min)  → la "base".
    3. Una segunda Ridge estima cuánto se desvía cada jugador de su base.
       Jugadores con pocos minutos se quedan cerca de su base (la Ridge los encoge).

  Valor final del jugador = base(G36) + desviación.
  Impacto de su ausencia (en puntos de margen) = (valor − reemplazo) × minutos/48
  donde "reemplazo" es el valor típico de un jugador de banca.

SIN FUGA DE INFORMACIÓN
  Para los partidos de la temporada S se usan valores ajustados SOLO con temporadas
  anteriores a S. (2023-24 no tiene temporada previa: solo usa la base de Game Score.)

Uso:
    python src/apm.py
Salidas:
    datos/procesados/bajas_apm_historicas.csv  (GAME_ID, EQUIPO, BAJAS_APM)
    datos/procesados/apm_actual.json           (para lesiones.py)
"""
import json

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold

import config
from bajas import cargar_jugadores

ALFAS = [3, 10, 30, 100, 300]
MIN_BANCA = 12  # jugadores con menos minutos por partido = nivel de reemplazo


def _diseno(j: pd.DataFrame, p: pd.DataFrame):
    """Matriz (partidos × jugadores) con ±minutos/48, más columna de localía."""
    d = j.merge(p[["GAME_ID", "LOCAL", "SEDE_NEUTRAL"]], on="GAME_ID")
    d["SIGNO"] = np.where(d["TEAM_ABBREVIATION"] == d["LOCAL"], 1.0, -1.0)
    juegos = p["GAME_ID"].to_numpy()
    fila = pd.Series(np.arange(len(juegos)), index=juegos)
    jugadores = np.sort(d["PLAYER_ID"].unique())
    col = pd.Series(np.arange(len(jugadores)), index=jugadores)
    X = sparse.csr_matrix((d["SIGNO"] * d["MIN"] / 48, (fila[d["GAME_ID"]].to_numpy(), col[d["PLAYER_ID"]].to_numpy())),
                          shape=(len(juegos), len(jugadores)))
    hca = sparse.csr_matrix((1 - p["SEDE_NEUTRAL"].to_numpy(dtype=float))[:, None] * 10)  # ×10: casi sin penalizar
    return sparse.hstack([X, hca]).tocsr(), p["MARGEN"].to_numpy(dtype=float), jugadores


def _mejor_alfa(X, y) -> float:
    errores = []
    for a in ALFAS:
        e = []
        for tr, te in KFold(5, shuffle=True, random_state=0).split(y):
            m = Ridge(alpha=a, fit_intercept=False).fit(X[tr], y[tr])
            e.append(np.mean((y[te] - m.predict(X[te])) ** 2))
        errores.append(np.mean(e))
    return ALFAS[int(np.argmin(errores))]


def ajustar(j: pd.DataFrame, p: pd.DataFrame) -> dict:
    """Ajusta base + desviación con los partidos dados. Devuelve parámetros y valores."""
    X, y, jugadores = _diseno(j, p)

    # 1) β crudo
    a1 = _mejor_alfa(X, y)
    beta0 = Ridge(alpha=a1, fit_intercept=False).fit(X, y).coef_[:-1]

    # 2) Base: β ≈ a + b·G36, ponderando por minutos
    tot = j.groupby("PLAYER_ID").agg(MIN=("MIN", "sum"), GMSC=("GMSC", "sum")).reindex(jugadores)
    g36 = (36 * tot["GMSC"] / tot["MIN"].clip(lower=1)).to_numpy()
    w = tot["MIN"].to_numpy()
    A = np.column_stack([np.ones_like(g36), g36])
    a, b = np.linalg.lstsq(A * np.sqrt(w)[:, None], beta0 * np.sqrt(w), rcond=None)[0]
    base = a + b * g36

    # 3) Desviación respecto a la base
    y_res = y - X[:, :-1] @ base
    a2 = _mejor_alfa(X, y_res)
    dev = Ridge(alpha=a2, fit_intercept=False).fit(X, y_res).coef_[:-1]
    beta = base + dev

    # Nivel de reemplazo: jugadores de banca (pocos minutos por partido)
    juegos_jug = j.groupby("PLAYER_ID")["GAME_ID"].nunique().reindex(jugadores)
    mpg = tot["MIN"].to_numpy() / juegos_jug.to_numpy()
    banca = mpg < MIN_BANCA
    reemplazo = float(np.average(beta[banca], weights=w[banca])) if banca.any() else float(np.min(beta))

    return {"a": float(a), "b": float(b), "reemplazo": reemplazo, "alfas": [a1, a2],
            "desviacion": dict(zip(map(int, jugadores), map(float, dev))),
            "beta": dict(zip(map(int, jugadores), map(float, beta)))}


def valor(params: dict, player_id: int, g36: float) -> float:
    """Valor (pts/48) = base(G36) + desviación del jugador (0 si no estaba en el ajuste)."""
    return params["a"] + params["b"] * g36 + params["desviacion"].get(int(player_id), 0.0)


def impacto(params: dict, player_id: int, g36: float, min_prom: float) -> float:
    """Puntos de margen que pierde el equipo si el jugador no juega."""
    return (valor(params, player_id, g36) - params["reemplazo"]) * min_prom / 48


def main():
    j = cargar_jugadores()
    p = pd.read_csv(config.PROCESADOS / "partidos.csv", dtype={"GAME_ID": str})
    if "SEDE_NEUTRAL" not in p:
        p["SEDE_NEUTRAL"] = 0
    det = pd.read_csv(config.PROCESADOS / "bajas_detalle.csv", dtype={"GAME_ID": str})
    temporadas = sorted(p["TEMPORADA"].unique())

    # Ajuste por temporada usando SOLO temporadas anteriores
    ajustes = {}
    for i, t in enumerate(temporadas):
        previas = temporadas[:i] or [t]  # la primera temporada solo usa la base (sin desviaciones)
        jj, pp = j[j["TEMPORADA"].isin(previas)], p[p["TEMPORADA"].isin(previas)]
        prm = ajustar(jj, pp)
        if i == 0:
            prm["desviacion"] = {}
        ajustes[t] = prm
        print(f"{t}: ajustado con {', '.join(previas)} · base β = {prm['a']:+.2f} + {prm['b']:.3f}·G36 · "
              f"reemplazo {prm['reemplazo']:+.2f} · alfas {prm['alfas']}")

    det["IMPACTO"] = [impacto(ajustes[r.TEMPORADA], r.PLAYER_ID, r.G36, r.MIN_PROM) for r in det.itertuples()]
    hist = det.groupby(["GAME_ID", "EQUIPO"])["IMPACTO"].sum().rename("BAJAS_APM").round(3).reset_index()
    hist.to_csv(config.PROCESADOS / "bajas_apm_historicas.csv", index=False)

    # Ajuste con TODO para predecir partidos futuros
    actual = ajustar(j, p)
    nombres = j.drop_duplicates("PLAYER_ID", keep="last").set_index("PLAYER_ID")["PLAYER_NAME"]
    top = sorted(actual["beta"].items(), key=lambda kv: -kv[1])
    mins = j.groupby("PLAYER_ID")["MIN"].sum()
    top = [(pid, b) for pid, b in top if mins.get(pid, 0) > 3000][:10]
    (config.PROCESADOS / "apm_actual.json").write_text(json.dumps(actual))

    print(f"\nBajas con APM: {len(hist)} registros equipo-partido.")
    print("Top 10 jugadores por valor (APM, ≥3,000 minutos):")
    for pid, b in top:
        print(f"  {nombres.get(pid, pid):28s} {b:+.1f} pts/48")


if __name__ == "__main__":
    main()
