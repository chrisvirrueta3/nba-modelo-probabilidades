"""
SPREADS Y TOTALES · Modelos de puntos.

  - MARGEN = puntos local − puntos visita   (para el spread / hándicap)
    Regresión Ridge con las mismas variables del modelo de ganador.
  - TOTAL  = puntos local + puntos visita   (para el over/under)
    Fórmula directa: ritmo promedio × (ataque de uno vs. defensa del otro).
    Probamos una regresión con más variables y salió PEOR en prueba (19.6 vs
    19.3 de error), así que nos quedamos con la fórmula: más simple y mejor.

Cada una da una predicción (μ) y aprendemos su error típico (σ) en
entrenamiento. Suponemos que el resultado real ~ Normal(μ, σ), lo cual
es una aproximación estándar y razonable en la NBA. Con eso:

  P(local cubre −5.5) = P(margen > 5.5)
  P(over 224.5)       = P(total > 224.5)

Las líneas enteras (ej. −5) pueden empatar ("push", se devuelve la apuesta):
lo manejamos tratando los puntos como números enteros.

Validación igual que el resto: entrenar 2023-25, probar en 2025-26 y 2026-27.
OJO: sin líneas históricas no podemos medir aquí si le ganamos al spread del
mercado; eso lo mide liquidar.py con las líneas que guardamos cada día.

Uso:
    python src/puntos.py
Salida:
    datos/procesados/modelo_puntos.joblib
"""
import math

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import caracteristicas as car
import config
from modelo import cargar

COLS_MARGEN = car.COLUMNAS_MODELO


# ---------------- Probabilidades ----------------
def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def probs_mayor(mu: float, sigma: float, linea: float) -> tuple[float, float, float]:
    """
    Para una variable entera X ~ Normal(mu, sigma) (con corrección de continuidad):
    devuelve (P(X > linea), P(X == linea), P(X < linea)).
    Si la línea es .5 no hay empate posible.
    """
    if float(linea).is_integer():
        gana = 1 - _phi((linea + 0.5 - mu) / sigma)
        pierde = _phi((linea - 0.5 - mu) / sigma)
        return gana, 1 - gana - pierde, pierde
    gana = 1 - _phi((linea - mu) / sigma)
    return gana, 0.0, 1 - gana


def probs_apuesta(mercado: str, lado: str, linea: float, mu_margen: float, mu_total: float,
                  sigma_margen: float, sigma_total: float) -> tuple[float, float, float]:
    """
    (P(ganar), P(push), P(perder)) para una apuesta de spread o total.
      spreads: lado = 'L' o 'V', linea = hándicap de ESE equipo (ej. -5.5 o +5.5)
      totals:  lado = 'Over' o 'Under', linea = total
    """
    if mercado == "spreads":
        if lado == "L":  # local cubre si margen + linea > 0  <=>  margen > -linea
            return probs_mayor(mu_margen, sigma_margen, -linea)
        g, p, l = probs_mayor(mu_margen, sigma_margen, linea)  # visita cubre si margen < linea
        return l, p, g
    if lado == "Over":
        return probs_mayor(mu_total, sigma_total, linea)
    g, p, l = probs_mayor(mu_total, sigma_total, linea)
    return l, p, g


def predecir(paquete: dict, feats: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """(margen esperado del local, total esperado) para cada fila de `feats`."""
    pm = paquete["margen"]
    mu_m = pm["modelo"].predict(feats[pm["columnas"]])
    mu_t = feats["EXP_TOTAL"].to_numpy()
    return mu_m, mu_t


# ---------------- Entrenamiento ----------------
def _ridge():
    return make_pipeline(StandardScaler(), Ridge(alpha=10.0))


def rmse(a, b) -> float:
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def main():
    d = cargar()
    entren = (d["TEMPORADA"].isin(["2023-24", "2024-25"]) & (d["FECHA"] >= "2023-12-01")).to_numpy()
    prueba = d["TEMPORADA"].isin(["2025-26", "2026-27"]).to_numpy()
    todo = (d["FECHA"] >= "2023-12-01").to_numpy()

    resultados, paquete = {}, {}

    # ----- Margen: regresión -----
    X, y = d[COLS_MARGEN], d["MARGEN"].to_numpy()
    m = _ridge().fit(X[entren], y[entren])
    pred = m.predict(X[prueba])
    sigma = float(np.std(y[entren] - m.predict(X[entren]), ddof=len(COLS_MARGEN) + 1))
    resultados["margen"] = {"pred": pred, "y": y[prueba], "sigma": sigma,
                            "dentro": float(np.mean(np.abs(y[prueba] - pred) <= sigma))}
    final = _ridge().fit(X[todo], y[todo])
    paquete["margen"] = {"modelo": final, "columnas": COLS_MARGEN,
                         "sigma": float(np.std(y[todo] - final.predict(X[todo]), ddof=len(COLS_MARGEN) + 1))}

    # ----- Total: fórmula ritmo × eficiencia (sin ajuste) -----
    y = d["TOTAL"].to_numpy()
    e = d["EXP_TOTAL"].to_numpy()
    sigma = float(np.std(y[entren] - e[entren]))
    resultados["total"] = {"pred": e[prueba], "y": y[prueba], "sigma": sigma,
                           "dentro": float(np.mean(np.abs(y[prueba] - e[prueba]) <= sigma))}
    paquete["total"] = {"sigma": float(np.std(y[todo] - e[todo]))}

    ym = resultados["margen"]["y"]
    yt = resultados["total"]["y"]
    elo_spread = -d.loc[prueba, "SPREAD_ELO_LOCAL"].to_numpy()  # margen esperado según Elo
    liga = d.loc[prueba, "LIGA_TOTAL"].to_numpy()
    exp_total = d.loc[prueba, "EXP_TOTAL"].to_numpy()

    print(f"Prueba: {prueba.sum()} partidos (2025-26 y 2026-27)\n")
    print("=== MARGEN (error típico en puntos, menor = mejor) ===")
    print(f"  Siempre 0 (empate)        RMSE {rmse(ym, 0):5.2f}")
    print(f"  Solo Elo                  RMSE {rmse(ym, elo_spread):5.2f}")
    print(f"  Modelo                    RMSE {rmse(ym, resultados['margen']['pred']):5.2f}   "
          f"σ = {resultados['margen']['sigma']:.1f} pts · dentro de ±1σ: {resultados['margen']['dentro']:.0%}")
    print("\n=== TOTAL ===")
    print(f"  Promedio de la liga       RMSE {rmse(yt, liga):5.2f}")
    print(f"  Fórmula ritmo×eficiencia  RMSE {rmse(yt, exp_total):5.2f}")
    print(f"  σ del total = {resultados['total']['sigma']:.1f} pts · dentro de ±1σ: {resultados['total']['dentro']:.0%}")
    print("\n(Como referencia: las líneas de las casas suelen tener RMSE ≈ 12 en margen y ≈ 17-18 en totales.)")

    joblib.dump(paquete, config.PROCESADOS / "modelo_puntos.joblib")
    print("\nGuardado: datos/procesados/modelo_puntos.joblib")


if __name__ == "__main__":
    main()
