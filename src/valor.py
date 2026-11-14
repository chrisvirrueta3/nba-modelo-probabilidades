"""
FASE 3 · Valor esperado (EV) y monto sugerido para los partidos próximos.

Para cada equipo de cada partido:
  1. Probabilidad del modelo (Elo + descanso + forma).
  2. Probabilidad "justa" del mercado = Pinnacle sin su margen.
  3. Mejor momio disponible entre las casas (line shopping).
  4. EV = prob_modelo × momio_decimal − 1   (ganancia esperada por cada $1)
  5. Monto con Kelly fraccional y tope por apuesta.

FILTROS DE SEGURIDAD (para no engañarnos):
  - Solo se marca si EV ≥ UMBRAL_EV.
  - Si el modelo difiere del mercado por más de DIF_SOSPECHOSA, se marca como
    SOSPECHOSA y NO se recomienda: casi siempre es una lesión/baja que el modelo no ve.

TODO se registra como apuesta SIMULADA (paper trading) en datos/apuestas_simuladas.csv.
Nada de dinero real hasta que el registro demuestre ventaja (fase 4).

Uso:
    python src/descargar_momios.py   (primero, para tener momios frescos)
    python src/valor.py
"""
import json
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

import caracteristicas as car
import config
from predecir_hoy import prob_implicita


def a_decimal(momio_americano: float) -> float:
    m = float(momio_americano)
    return 1 + (m / 100 if m > 0 else 100 / -m)


def kelly(prob: float, decimal: float) -> float:
    """Fracción del bankroll según Kelly completo (puede ser negativa = no apostar)."""
    return (prob * decimal - 1) / (decimal - 1)


def partidos_proximos(momios: pd.DataFrame) -> pd.DataFrame:
    ahora = pd.Timestamp.now(tz="UTC")
    ultima = momios["CAPTURADO_UTC"].max()
    m = momios[(momios["CAPTURADO_UTC"] == ultima) & (momios["MERCADO"] == "h2h")].copy()
    m["INICIO"] = pd.to_datetime(m["INICIO_UTC"], utc=True)
    m = m[m["INICIO"] > ahora]
    return m


def probabilidades_modelo(eventos: pd.DataFrame) -> pd.Series:
    """Calcula la probabilidad del local para cada evento con el modelo guardado."""
    hist = pd.read_csv(config.PROCESADOS / "partidos_elo.csv", parse_dates=["FECHA"], dtype={"GAME_ID": str})
    hca = json.loads((config.PROCESADOS / "elo_parametros.json").read_text())["HCA"]
    hist["ELO_DIF"] = (hist["ELO_LOCAL_PRE"] + np.where(hist["SEDE_NEUTRAL"] == 1, 0, hca)
                       - hist["ELO_VISITA_PRE"]) / 100
    ratings = pd.read_csv(config.PROCESADOS / "ratings_actuales.csv").set_index("EQUIPO")["ELO"]

    futuros = pd.DataFrame({
        "GAME_ID": eventos["EVENTO_ID"],
        # La NBA fecha sus partidos con la hora del Este de EE.UU.
        "FECHA": eventos["INICIO"].dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize(),
        "TEMPORADA": config.TEMPORADA_ACTUAL,
        "LOCAL": eventos["LOCAL"], "VISITA": eventos["VISITA"], "SEDE_NEUTRAL": 0,
    })
    futuros["ELO_DIF"] = (futuros["LOCAL"].map(ratings) + hca - futuros["VISITA"].map(ratings)) / 100

    # Bajas esperadas según el reporte de lesiones de hoy
    try:
        import lesiones
        por_equipo, _ = lesiones.bajas_esperadas()
    except Exception as e:  # noqa: BLE001
        print(f"  Aviso: no se pudo leer el reporte de lesiones ({e}). Bajas = 0.")
        por_equipo = pd.Series(dtype=float)
    futuros["L_BAJAS"] = futuros["LOCAL"].map(por_equipo).fillna(0.0)
    futuros["V_BAJAS"] = futuros["VISITA"].map(por_equipo).fillna(0.0)
    hist = car.agregar_bajas_historicas(hist)

    todo = pd.concat([hist, futuros], ignore_index=True)
    feats = car.construir(todo).set_index("GAME_ID").loc[futuros["GAME_ID"]]

    paquete = joblib.load(config.PROCESADOS / "modelo.joblib")
    p = paquete["modelo"].predict_proba(feats[paquete["columnas"]])[:, 1]
    return pd.Series(p, index=futuros["GAME_ID"].to_numpy())


def main():
    momios = pd.read_csv(config.MOMIOS / "momios_historico.csv")
    m = partidos_proximos(momios)
    if m.empty:
        print("No hay partidos próximos en el último snapshot. Corre primero: python src/descargar_momios.py")
        return

    m = m[~m["CASA"].isin(config.CASAS_EXCLUIDAS)]
    m["EQUIPO"] = m["RESULTADO"].map(config.abreviatura)
    m["DECIMAL"] = m["MOMIO"].apply(a_decimal)

    eventos = m.drop_duplicates("EVENTO_ID")[["EVENTO_ID", "INICIO", "LOCAL", "VISITA"]].reset_index(drop=True)
    p_local = probabilidades_modelo(eventos)

    filas = []
    for ev in eventos.itertuples(index=False):
        g = m[m["EVENTO_ID"] == ev.EVENTO_ID]
        pin = g[g["CASA"] == "pinnacle"].set_index("EQUIPO")["MOMIO"]
        if len(pin) == 2:
            impl = pin.apply(prob_implicita)
            justa = impl / impl.sum()
        else:
            justa = None

        for equipo, rival, es_local in ((ev.LOCAL, ev.VISITA, True), (ev.VISITA, ev.LOCAL, False)):
            p = p_local[ev.EVENTO_ID] if es_local else 1 - p_local[ev.EVENTO_ID]
            lado = g[g["EQUIPO"] == equipo]
            mejor = lado.loc[lado["DECIMAL"].idxmax()]
            ev_mejor = p * mejor["DECIMAL"] - 1
            p_justa = float(justa[equipo]) if justa is not None else np.nan
            f = kelly(p, mejor["DECIMAL"])
            monto = config.BANKROLL * min(max(f, 0) * config.KELLY_FRACCION, config.TOPE_APUESTA)

            if np.isfinite(p_justa) and abs(p - p_justa) > config.DIF_SOSPECHOSA:
                estado = "SOSPECHOSA"
            elif ev_mejor >= config.UMBRAL_EV:
                estado = "VALOR"
            else:
                estado = "-"

            filas.append({
                "EVENTO_ID": ev.EVENTO_ID,
                "INICIO (CDMX)": ev.INICIO.tz_convert("America/Mexico_City").strftime("%d/%m %H:%M"),
                "PARTIDO": f"{ev.VISITA} @ {ev.LOCAL}",
                "APUESTA": equipo,
                "MODELO_%": round(100 * p, 1),
                "MERCADO_%": round(100 * p_justa, 1),
                "MEJOR_MOMIO": int(mejor["MOMIO"]),
                "CASA": mejor["CASA"],
                "EV_%": round(100 * ev_mejor, 1),
                "MONTO": round(monto, 0) if estado == "VALOR" else 0,
                "ESTADO": estado,
            })

    tabla = pd.DataFrame(filas).sort_values(["INICIO (CDMX)", "PARTIDO"])
    vista = tabla.drop(columns="EVENTO_ID")
    print(f"Bankroll de práctica: ${config.BANKROLL:,.0f} · Kelly {config.KELLY_FRACCION:.0%} · "
          f"tope {config.TOPE_APUESTA:.0%} · umbral EV {config.UMBRAL_EV:.0%}\n")
    print(vista.to_string(index=False))

    # Registro de TODAS las predicciones (no solo apuestas): sirve para comparar
    # modelo vs. mercado con muchos más partidos. Si corres el script varias veces,
    # liquidar.py usa la última predicción hecha antes del partido.
    locales = tabla.merge(eventos[["EVENTO_ID", "LOCAL", "INICIO"]], on="EVENTO_ID")
    locales = locales[locales["APUESTA"] == locales["LOCAL"]]
    pred = pd.DataFrame({
        "REGISTRADA_UTC": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "EVENTO_ID": locales["EVENTO_ID"],
        "INICIO_UTC": locales["INICIO"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "PARTIDO": locales["PARTIDO"],
        "PROB_MODELO_LOCAL": (locales["MODELO_%"] / 100).round(4),
        "PROB_MERCADO_LOCAL": (locales["MERCADO_%"] / 100).round(4),
    })
    ruta_pred = config.DATOS / "predicciones.csv"
    pred.to_csv(ruta_pred, mode="a", header=not ruta_pred.exists(), index=False)

    # Registro de paper trading (sin duplicar si corres el script varias veces)
    nuevas = tabla[tabla["ESTADO"] == "VALOR"].copy()
    registro = config.DATOS / "apuestas_simuladas.csv"
    if not nuevas.empty:
        nuevas.insert(0, "REGISTRADA_UTC", datetime.now(timezone.utc).isoformat(timespec="minutes"))
        if registro.exists():
            previas = pd.read_csv(registro)
            clave = set(zip(previas["EVENTO_ID"], previas["APUESTA"]))
            nuevas = nuevas[[(e, a) not in clave for e, a in zip(nuevas["EVENTO_ID"], nuevas["APUESTA"])]]
        nuevas.to_csv(registro, mode="a", header=not registro.exists(), index=False)
        print(f"\n{len(nuevas)} apuesta(s) SIMULADA(s) nuevas registradas en {registro.name}")
    else:
        print("\nNinguna apuesta pasa los filtros hoy. (Es normal: la mayoría de los días no hay valor.)")

    sosp = (tabla["ESTADO"] == "SOSPECHOSA").sum()
    if sosp:
        print(f"{sosp} lado(s) SOSPECHOSOS: el modelo difiere >{config.DIF_SOSPECHOSA:.0%} del mercado. "
              "Revisa lesiones antes de creerle al modelo.")


if __name__ == "__main__":
    main()
