"""
FASE 2: Modelo Elo para la NBA.

IDEA
  Cada equipo tiene una calificación (empiezan en 1500). Antes de cada partido,
  la diferencia de calificaciones (+ ventaja de local) se convierte en una
  probabilidad de ganar. Después del partido, el ganador "le quita" puntos al
  perdedor: más puntos si la victoria fue inesperada o por mucho margen.

  Probabilidad local = 1 / (1 + 10^(-(Elo_local + VENTAJA_LOCAL - Elo_visita) / 400))

  Clave contra el "data leakage": la probabilidad de cada partido se calcula
  ANTES de actualizar con su resultado. Nunca usamos el futuro para predecir.

CÓMO VALIDAMOS (sin hacer trampa)
  - 2023-24: calentamiento (los ratings arrancan en 1500 y necesitan tiempo).
  - 2024-25: AJUSTE. Probamos combinaciones de parámetros y elegimos la mejor.
  - 2025-26 + 2026-27: PRUEBA. Datos que el ajuste nunca vio. Este es el número honesto.

Uso:
    python src/elo.py
Salidas:
    datos/procesados/partidos_elo.csv   (probabilidad pre-partido de cada juego)
    datos/procesados/ratings_actuales.csv
"""
import itertools
import math

import numpy as np
import pandas as pd

import config

ELO_INICIAL = 1500
MEDIA_REVERSION = 1505


def prob_elo(diferencia: float) -> float:
    """Diferencia de Elo (ya con ventaja de local) -> probabilidad de ganar."""
    return 1.0 / (1.0 + 10 ** (-diferencia / 400))


def multiplicador_margen(margen: int, dif_elo_ganador: float) -> float:
    """
    Una paliza mueve más el rating que un triunfo por 1 punto, pero con
    rendimientos decrecientes. El denominador frena a los favoritos que ganan
    por mucho (evita que los ratings se inflen). Fórmula estilo FiveThirtyEight.
    """
    return ((abs(margen) + 3) ** 0.8) / (7.5 + 0.006 * dif_elo_ganador)


def correr_elo(partidos: pd.DataFrame, k: float, ventaja_local: float, reversion: float):
    """
    Recorre los partidos en orden cronológico.
    Devuelve (probabilidades pre-partido, elo_local_pre, elo_visita_pre, ratings finales).
    """
    ratings: dict[str, float] = {}
    temporada_previa = None
    probs, elo_l, elo_v = [], [], []

    for p in partidos.itertuples(index=False):
        # Entre temporadas, todos regresan un poco hacia el promedio
        # (cambian plantillas, entrenadores, lesiones...).
        if temporada_previa is not None and p.TEMPORADA != temporada_previa:
            ratings = {eq: r * (1 - reversion) + MEDIA_REVERSION * reversion for eq, r in ratings.items()}
        temporada_previa = p.TEMPORADA

        rl = ratings.get(p.LOCAL, ELO_INICIAL)
        rv = ratings.get(p.VISITA, ELO_INICIAL)
        hca = 0 if p.SEDE_NEUTRAL else ventaja_local
        prob = prob_elo(rl + hca - rv)

        probs.append(prob)
        elo_l.append(rl)
        elo_v.append(rv)

        # Actualización con el resultado real
        resultado = p.GANO_LOCAL
        dif_ganador = (rl + hca - rv) if resultado == 1 else (rv - rl - hca)
        cambio = k * multiplicador_margen(p.MARGEN, dif_ganador) * (resultado - prob)
        ratings[p.LOCAL] = rl + cambio
        ratings[p.VISITA] = rv - cambio

    return np.array(probs), np.array(elo_l), np.array(elo_v), ratings


# ---------------- Métricas ----------------
def brier(y, p):
    """Error cuadrático de la probabilidad. Menor = mejor. 0.25 = lanzar moneda."""
    return float(np.mean((p - y) ** 2))


def log_loss(y, p):
    """Castiga mucho estar muy seguro y equivocarse. Menor = mejor. 0.693 = moneda."""
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def acierto(y, p):
    return float(np.mean((p > 0.5) == (y == 1)))


def evaluar(y, p, nombre):
    return {"modelo": nombre, "partidos": len(y), "acierto_%": round(100 * acierto(y, p), 1),
            "brier": round(brier(y, p), 4), "log_loss": round(log_loss(y, p), 4)}


def tabla_calibracion(y, p, bins=10):
    """¿Cuando el modelo dice 70%, el equipo gana ~70% de las veces?"""
    df = pd.DataFrame({"y": y, "p": p})
    df["rango"] = pd.cut(df["p"], bins=np.linspace(0, 1, bins + 1))
    t = df.groupby("rango", observed=True).agg(partidos=("y", "size"), prob_modelo=("p", "mean"), real=("y", "mean"))
    t["prob_modelo"] = (100 * t["prob_modelo"]).round(1)
    t["real"] = (100 * t["real"]).round(1)
    return t[t["partidos"] >= 15]


def main():
    partidos = pd.read_csv(config.PROCESADOS / "partidos.csv", parse_dates=["FECHA"], dtype={"GAME_ID": str})
    partidos = partidos.sort_values(["FECHA", "GAME_ID"]).reset_index(drop=True)
    if "SEDE_NEUTRAL" not in partidos.columns:
        partidos["SEDE_NEUTRAL"] = 0
    y = partidos["GANO_LOCAL"].to_numpy()

    ajuste = (partidos["TEMPORADA"] == "2024-25").to_numpy()
    prueba = partidos["TEMPORADA"].isin(["2025-26", "2026-27"]).to_numpy()

    # 1) Búsqueda de parámetros SOLO con la temporada de ajuste
    print("Buscando los mejores parámetros (solo con 2024-25)...")
    mejores = None
    for k, hca, rev in itertools.product([10, 15, 20, 25, 30], [20, 30, 40, 50, 60, 70, 90], [0.25, 0.4, 0.55]):
        p, *_ = correr_elo(partidos, k, hca, rev)
        ll = log_loss(y[ajuste], p[ajuste])
        if mejores is None or ll < mejores[0]:
            mejores = (ll, k, hca, rev)
    _, K, HCA, REV = mejores
    print(f"  Mejor: K={K}, ventaja local={HCA} pts Elo, reversión entre temporadas={REV:.0%}")

    # 2) Evaluación honesta en la temporada de prueba
    p, elo_l, elo_v, ratings = correr_elo(partidos, K, HCA, REV)
    tasa_local = y[ajuste].mean()  # lo que sabríamos ANTES de la prueba
    base = np.where(partidos["SEDE_NEUTRAL"].to_numpy() == 1, 0.5, tasa_local)

    print("\n=== Resultados en datos de PRUEBA (2025-26 y 2026-27, nunca vistos en el ajuste) ===")
    res = pd.DataFrame([
        evaluar(y[prueba], np.full(prueba.sum(), 0.5), "Moneda al aire (50%)"),
        evaluar(y[prueba], base[prueba], f"Siempre el local ({tasa_local:.1%})"),
        evaluar(y[prueba], p[prueba], "Elo"),
    ])
    print(res.to_string(index=False))

    print("\nCalibración del Elo en prueba (¿sus porcentajes son reales?):")
    print(tabla_calibracion(y[prueba], p[prueba]).to_string())

    # 3) Guardar
    partidos["ELO_LOCAL_PRE"] = elo_l.round(1)
    partidos["ELO_VISITA_PRE"] = elo_v.round(1)
    partidos["PROB_ELO_LOCAL"] = p.round(4)
    # Aprox.: ~28 puntos de Elo = 1 punto de margen en la NBA
    hca_vec = np.where(partidos["SEDE_NEUTRAL"] == 1, 0, HCA)
    partidos["SPREAD_ELO_LOCAL"] = (-(elo_l + hca_vec - elo_v) / 28).round(1)
    partidos.to_csv(config.PROCESADOS / "partidos_elo.csv", index=False)

    tabla = (pd.DataFrame(ratings.items(), columns=["EQUIPO", "ELO"])
             .sort_values("ELO", ascending=False).reset_index(drop=True))
    tabla["ELO"] = tabla["ELO"].round(0).astype(int)
    tabla.index += 1
    tabla.to_csv(config.PROCESADOS / "ratings_actuales.csv", index_label="RANK")
    pd.Series({"K": K, "HCA": HCA, "REV": REV}).to_json(config.PROCESADOS / "elo_parametros.json")

    print("\nRatings actuales (top 10 y últimos 5):")
    print(pd.concat([tabla.head(10), tabla.tail(5)]).to_string())
    print("\nGuardado en datos/procesados/. Siguiente: python src/predecir_hoy.py")


if __name__ == "__main__":
    main()
