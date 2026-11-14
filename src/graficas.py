"""
Genera las gráficas del README (docs/img/) a partir de los resultados reales.

  - comparacion.png : log loss en datos de prueba, de la base más simple al modelo final
  - calibracion.png : ¿las probabilidades del modelo se cumplen en la realidad?
  - pesos.png       : importancia de cada variable en la regresión logística

Uso:
    python src/graficas.py
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

import caracteristicas as car  # noqa: E402
import config  # noqa: E402
from elo import log_loss  # noqa: E402
from modelo import cargar  # noqa: E402

IMG = config.RAIZ / "docs" / "img"
IMG.mkdir(parents=True, exist_ok=True)

AZUL, GRIS, VERDE, TEXTO, SUAVE = "#2f6fdb", "#9aa1ad", "#1f9d61", "#1d2433", "#6b7280"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": "#d5d9e0",
    "axes.labelcolor": TEXTO, "xtick.color": SUAVE, "ytick.color": SUAVE,
    "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150,
})

NOMBRES = {
    "ELO_DIF": "Diferencia de Elo", "DIF_NET": "Net rating (temporada)", "DIF_NET10": "Net rating (últimos 10)",
    "DIF_BAJAS": "Bajas por lesión", "L_B2B": "Local en back-to-back", "V_B2B": "Visita en back-to-back",
    "DIF_DESCANSO": "Diferencia de descanso", "L_3EN4": "Local: 3 juegos en 4 noches",
    "V_3EN4": "Visita: 3 juegos en 4 noches", "SEDE_NEUTRAL": "Sede neutral",
}


def entrenar(datos, columnas, entren, prueba):
    m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    m.fit(datos.loc[entren, columnas], datos.loc[entren, "GANO_LOCAL"])
    return m, m.predict_proba(datos.loc[prueba, columnas])[:, 1]


def main():
    d = cargar()
    y_all = d["GANO_LOCAL"].to_numpy()
    entren = (d["TEMPORADA"].isin(["2023-24", "2024-25"]) & (d["FECHA"] >= "2023-12-01")).to_numpy()
    prueba = d["TEMPORADA"].isin(["2025-26", "2026-27"]).to_numpy()
    y = y_all[prueba]
    tasa_local = y_all[d["TEMPORADA"].eq("2024-25").to_numpy()].mean()

    sin_bajas = [c for c in car.COLUMNAS_MODELO if c != "DIF_BAJAS"]
    _, p_sin = entrenar(d, sin_bajas, entren, prueba)
    modelo, p_final = entrenar(d, car.COLUMNAS_MODELO, entren, prueba)
    p_elo = d.loc[prueba, "PROB_ELO_LOCAL"].to_numpy()

    # ---------- 1) Comparación ----------
    filas = [
        ("Moneda al aire", log_loss(y, np.full(len(y), 0.5)), GRIS),
        ("Siempre el local", log_loss(y, np.full(len(y), tasa_local)), GRIS),
        ("Elo", log_loss(y, p_elo), AZUL),
        ("+ descanso y forma", log_loss(y, p_sin), AZUL),
        ("+ lesiones (final)", log_loss(y, p_final), VERDE),
    ]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    nombres, vals, colores = zip(*filas)
    barras = ax.barh(nombres[::-1], vals[::-1], color=colores[::-1], height=0.6)
    for b, v in zip(barras, vals[::-1]):
        ax.text(v + 0.002, b.get_y() + b.get_height() / 2, f"{v:.4f}", va="center", color=TEXTO, fontsize=10)
    ax.set_xlim(0.55, 0.71)
    ax.set_xlabel("Log loss en datos de prueba (menor = mejor)")
    ax.set_title(f"Cada mejora, medida en {prueba.sum():,} partidos nunca vistos", loc="left", color=TEXTO, fontsize=12)
    ax.tick_params(axis="y", length=0)
    fig.tight_layout()
    fig.savefig(IMG / "comparacion.png")
    plt.close(fig)

    # ---------- 2) Calibración ----------
    fig, ax = plt.subplots(figsize=(5.4, 5.0))
    ax.plot([0, 1], [0, 1], ls="--", color=GRIS, lw=1, label="Calibración perfecta")
    bins = np.linspace(0, 1, 11)
    for p, nombre, color in ((p_elo, "Elo", GRIS), (p_final, "Modelo final", AZUL)):
        idx = np.digitize(p, bins) - 1
        xs, ys, ns = [], [], []
        for k in range(10):
            mask = idx == k
            if mask.sum() >= 15:
                xs.append(p[mask].mean()); ys.append(y[mask].mean()); ns.append(mask.sum())
        ax.plot(xs, ys, marker="o", color=color, lw=2 if color == AZUL else 1.4,
                ms=6 if color == AZUL else 4, label=nombre)
    ax.set_xlabel("Probabilidad que dio el modelo")
    ax.set_ylabel("Frecuencia real de victoria")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_xticks(np.linspace(0, 1, 6)); ax.set_xticklabels([f"{int(t*100)}%" for t in np.linspace(0, 1, 6)])
    ax.set_yticks(np.linspace(0, 1, 6)); ax.set_yticklabels([f"{int(t*100)}%" for t in np.linspace(0, 1, 6)])
    ax.set_title("Calibración: cuando dice 70%, ¿gana el 70%?", loc="left", color=TEXTO, fontsize=12)
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(IMG / "calibracion.png")
    plt.close(fig)

    # ---------- 3) Pesos ----------
    coef = pd.Series(modelo[-1].coef_[0], index=car.COLUMNAS_MODELO)
    coef = coef.reindex(coef.abs().sort_values().index)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.barh([NOMBRES.get(c, c) for c in coef.index], coef.values,
            color=[AZUL if v > 0 else "#d9534f" for v in coef.values], height=0.6)
    ax.axvline(0, color="#d5d9e0", lw=1)
    ax.set_xlabel("Coeficiente estandarizado (+ favorece al local)")
    ax.set_title("¿Qué pesa más al predecir un partido?", loc="left", color=TEXTO, fontsize=12)
    ax.tick_params(axis="y", length=0)
    fig.tight_layout()
    fig.savefig(IMG / "pesos.png")
    plt.close(fig)

    print(f"Gráficas guardadas en {IMG}")
    for n, v, _ in filas:
        print(f"  {n:22s} {v:.4f}")


if __name__ == "__main__":
    main()
