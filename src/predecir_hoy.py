"""
FASE 2 (vista previa de la fase 3): probabilidades del Elo para los partidos
próximos vs. lo que dice el mercado (Pinnacle, sin su margen).

Necesita haber corrido antes:
    python src/elo.py
    python src/descargar_momios.py

Uso:
    python src/predecir_hoy.py
"""
import json

import pandas as pd

import config
from elo import prob_elo


def prob_implicita(momio_americano: float) -> float:
    """Momio americano -> probabilidad implícita (todavía con el margen de la casa)."""
    m = float(momio_americano)
    return 100 / (m + 100) if m > 0 else -m / (-m + 100)


def main():
    ratings = pd.read_csv(config.PROCESADOS / "ratings_actuales.csv").set_index("EQUIPO")["ELO"]
    params = json.loads((config.PROCESADOS / "elo_parametros.json").read_text())
    hca = params["HCA"]

    momios = pd.read_csv(config.MOMIOS / "momios_historico.csv")
    ultima = momios["CAPTURADO_UTC"].max()
    m = momios[(momios["CAPTURADO_UTC"] == ultima) & (momios["MERCADO"] == "h2h")].copy()
    m["PROB_IMPL"] = m["MOMIO"].apply(prob_implicita)
    m["ES_LOCAL"] = m["RESULTADO"].map(config.abreviatura) == m["LOCAL"]

    filas = []
    for (evento, local, visita, inicio), g in m.groupby(["EVENTO_ID", "LOCAL", "VISITA", "INICIO_UTC"]):
        p_elo = prob_elo(ratings[local] + hca - ratings[visita])

        fila = {"PARTIDO": f"{visita} @ {local}",
                "INICIO (CDMX)": pd.to_datetime(inicio).tz_convert("America/Mexico_City").strftime("%d/%m %H:%M"),
                "ELO_LOCAL_%": round(100 * p_elo, 1)}

        pin = g[g["CASA"] == "pinnacle"]
        if len(pin) == 2:
            pl = pin.loc[pin["ES_LOCAL"], "PROB_IMPL"].iloc[0]
            pv = pin.loc[~pin["ES_LOCAL"], "PROB_IMPL"].iloc[0]
            justa = pl / (pl + pv)  # quitamos el margen (vig) normalizando a 100%
            fila["PINNACLE_JUSTA_%"] = round(100 * justa, 1)
            fila["MARGEN_CASA_%"] = round(100 * (pl + pv - 1), 1)
            fila["DIFERENCIA_pts"] = round(100 * (p_elo - justa), 1)
        filas.append(fila)

    tabla = pd.DataFrame(filas).sort_values("INICIO (CDMX)")
    print(f"Momios capturados: {ultima[:16].replace('T', ' ')} UTC\n")
    print(tabla.to_string(index=False))
    print(
        "\nCómo leerlo: DIFERENCIA = Elo − mercado (probabilidad del LOCAL).\n"
        "OJO: el Elo todavía NO sabe de lesiones, descanso ni back-to-backs, y el mercado sí.\n"
        "Una diferencia grande aquí casi siempre significa que el MERCADO sabe algo que el Elo no.\n"
        "Esto NO es una recomendación de apuesta; eso llega en la fase 3, con backtesting."
    )


if __name__ == "__main__":
    main()
