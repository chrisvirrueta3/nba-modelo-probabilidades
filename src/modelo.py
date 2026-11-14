"""
FASE 3 · Modelo mejorado: Elo + descanso + forma + net rating + bajas.

Compara dos modelos contra el Elo solo:
  - Regresión logística: simple, interpretable (vemos cuánto pesa cada variable).
  - Gradient Boosting: más flexible, pero con pocos datos se sobreajusta fácil.

Validación igual que antes, sin trampa:
  ENTRENAMIENTO: 2023-24 y 2024-25   ·   PRUEBA: 2025-26 y 2026-27

Uso:
    python src/modelo.py
Salida:
    datos/procesados/modelo.joblib  (el modelo elegido, para valor.py)
"""
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import caracteristicas as car
import config
from elo import evaluar, tabla_calibracion


def cargar() -> pd.DataFrame:
    p = pd.read_csv(config.PROCESADOS / "partidos_elo.csv", parse_dates=["FECHA"], dtype={"GAME_ID": str})
    hca = json.loads((config.PROCESADOS / "elo_parametros.json").read_text())["HCA"]
    p["ELO_DIF"] = (p["ELO_LOCAL_PRE"] + np.where(p["SEDE_NEUTRAL"] == 1, 0, hca) - p["ELO_VISITA_PRE"]) / 100
    p = car.agregar_bajas_historicas(p)
    return car.construir(p)


def main():
    datos = cargar()
    X, y = datos[car.COLUMNAS_MODELO], datos["GANO_LOCAL"].to_numpy()
    entren = datos["TEMPORADA"].isin(["2023-24", "2024-25"]).to_numpy()
    prueba = datos["TEMPORADA"].isin(["2025-26", "2026-27"]).to_numpy()
    # Las primeras semanas de 2023-24 tienen Elo "frío" (todos en 1500): las quitamos del entrenamiento
    calentando = (datos["FECHA"] < "2023-12-01").to_numpy()
    entren &= ~calentando

    modelos = {
        "Regresión logística": make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000)),
        "Gradient Boosting": HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                                            l2_regularization=1.0, random_state=42),
    }

    resultados = [evaluar(y[prueba], datos.loc[prueba, "PROB_ELO_LOCAL"].to_numpy(), "Elo solo (fase 2)")]
    probs = {}
    for nombre, m in modelos.items():
        m.fit(X[entren], y[entren])
        probs[nombre] = m.predict_proba(X[prueba])[:, 1]
        resultados.append(evaluar(y[prueba], probs[nombre], nombre))

    tabla = pd.DataFrame(resultados)
    print(f"Entrenamiento: {entren.sum()} partidos · Prueba: {prueba.sum()} partidos\n")
    print("=== Resultados en PRUEBA (menor log_loss = mejor) ===")
    print(tabla.to_string(index=False))

    ganador = min(modelos, key=lambda n: tabla.set_index("modelo").loc[n, "log_loss"])
    print(f"\nModelo elegido: {ganador}")

    lr = modelos["Regresión logística"][-1]
    pesos = pd.Series(lr.coef_[0], index=car.COLUMNAS_MODELO).sort_values(key=abs, ascending=False)
    print("\nPeso de cada variable (regresión logística, estandarizado; + favorece al local):")
    print(pesos.round(3).to_string())

    print(f"\nCalibración de {ganador} en prueba:")
    print(tabla_calibracion(y[prueba], probs[ganador]).to_string())

    # Reentrenamos el elegido con TODO lo disponible para predecir partidos futuros
    final = modelos[ganador]
    todo = ~calentando
    final.fit(X[todo], y[todo])
    joblib.dump({"modelo": final, "columnas": car.COLUMNAS_MODELO, "nombre": ganador},
                config.PROCESADOS / "modelo.joblib")
    print("\nGuardado: datos/procesados/modelo.joblib · Siguiente: python src/valor.py")


if __name__ == "__main__":
    main()
