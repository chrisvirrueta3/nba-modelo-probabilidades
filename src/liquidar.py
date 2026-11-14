"""
FASE 4 · Liquidar apuestas simuladas y medir si el modelo le gana al mercado.

Qué hace:
  1. Baja los resultados de los últimos 3 días (The Odds API, endpoint /scores,
     2 créditos por llamada) y los guarda en datos/resultados.csv para no repetir.
  2. Liquida cada apuesta simulada: GANADA / PERDIDA y su ganancia.
  3. Calcula el CLV (Closing Line Value): ¿el momio que tomamos era mejor que la
     probabilidad justa de CIERRE de Pinnacle? Es el mejor indicador de habilidad:
     el ROI tarda cientos de apuestas en dejar de ser ruido; el CLV, muchas menos.
  4. Compara el modelo contra el mercado en TODOS los partidos predichos (Brier).

Uso:
    python src/liquidar.py
Salida:
    datos/reporte_apuestas.csv  (cada apuesta con su resultado y CLV)
"""
import os

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

import config
from predecir_hoy import prob_implicita

URL_SCORES = f"https://api.the-odds-api.com/v4/sports/{config.DEPORTE_ODDS}/scores"


# ---------------- Resultados ----------------
def bajar_resultados(api_key: str) -> pd.DataFrame:
    r = requests.get(URL_SCORES, params={"apiKey": api_key, "daysFrom": 3, "dateFormat": "iso"}, timeout=30)
    r.raise_for_status()
    filas = []
    for ev in r.json():
        if not ev.get("completed") or not ev.get("scores"):
            continue
        pts = {config.abreviatura(s["name"]): int(s["score"]) for s in ev["scores"]}
        local, visita = config.abreviatura(ev["home_team"]), config.abreviatura(ev["away_team"])
        filas.append({"EVENTO_ID": ev["id"], "LOCAL": local, "VISITA": visita,
                      "PTS_LOCAL": pts[local], "PTS_VISITA": pts[visita],
                      "GANADOR": local if pts[local] > pts[visita] else visita})
    print(f"Resultados descargados: {len(filas)} partidos terminados · "
          f"créditos restantes: {r.headers.get('x-requests-remaining')}")
    return pd.DataFrame(filas)


def actualizar_resultados(pendientes: set) -> pd.DataFrame:
    ruta = config.DATOS / "resultados.csv"
    previos = pd.read_csv(ruta) if ruta.exists() else pd.DataFrame(columns=["EVENTO_ID"])
    faltan = pendientes - set(previos["EVENTO_ID"])
    if faltan:
        load_dotenv(config.RAIZ / ".env")
        nuevos = bajar_resultados(os.environ["ODDS_API_KEY"])
        nuevos = nuevos[~nuevos["EVENTO_ID"].isin(previos["EVENTO_ID"])]
        previos = pd.concat([previos, nuevos], ignore_index=True)
        previos.to_csv(ruta, index=False)
    return previos


# ---------------- Línea de cierre ----------------
def probabilidades_cierre(momios: pd.DataFrame) -> pd.DataFrame:
    """
    Para cada partido: probabilidad justa (sin margen) de cada equipo en el
    último snapshot ANTES del inicio. Prioriza Pinnacle; si no está, usa la
    mediana de todas las casas.
    """
    m = momios[momios["MERCADO"] == "h2h"].copy()
    m = m[~m["CASA"].isin(config.CASAS_EXCLUIDAS)]
    inicio = pd.to_datetime(m["INICIO_UTC"], utc=True)
    # Solo partidos que ya empezaron (antes de eso, la "línea de cierre" aún no existe)
    m = m[(pd.to_datetime(m["CAPTURADO_UTC"], utc=True) < inicio) & (inicio < pd.Timestamp.now(tz="UTC"))]
    ultimo = m.groupby("EVENTO_ID")["CAPTURADO_UTC"].transform("max")
    m = m[m["CAPTURADO_UTC"] == ultimo].copy()

    m["EQUIPO"] = m["RESULTADO"].map(config.abreviatura)
    m["IMPL"] = m["MOMIO"].apply(prob_implicita)
    m["JUSTA"] = m["IMPL"] / m.groupby(["EVENTO_ID", "CASA"])["IMPL"].transform("sum")

    pin = m[m["CASA"] == "pinnacle"].groupby(["EVENTO_ID", "EQUIPO"])["JUSTA"].first()
    mediana = m.groupby(["EVENTO_ID", "EQUIPO"])["JUSTA"].median()
    cierre = pin.combine_first(mediana).rename("PROB_CIERRE").reset_index()
    cierre["CIERRE_UTC"] = cierre["EVENTO_ID"].map(m.groupby("EVENTO_ID")["CAPTURADO_UTC"].first())
    return cierre


def a_decimal(momio: float) -> float:
    return 1 + (momio / 100 if momio > 0 else 100 / -momio)


# ---------------- Reporte ----------------
def main():
    ruta_ap = config.DATOS / "apuestas_simuladas.csv"
    ruta_pred = config.DATOS / "predicciones.csv"
    apuestas = pd.read_csv(ruta_ap) if ruta_ap.exists() else pd.DataFrame()
    pred = pd.read_csv(ruta_pred) if ruta_pred.exists() else pd.DataFrame()
    if apuestas.empty and pred.empty:
        print("Todavía no hay apuestas ni predicciones. Corre primero: python src/valor.py")
        return

    # Pedimos resultados solo de partidos registrados que empezaron hace 3+ horas
    # (ya terminaron) y de hace menos de 3 días (lo que cubre la API).
    ids = set(apuestas.get("EVENTO_ID", [])) | set(pred.get("EVENTO_ID", []))
    momios_ini = pd.read_csv(config.MOMIOS / "momios_historico.csv", usecols=["EVENTO_ID", "INICIO_UTC"])
    inicio = momios_ini.drop_duplicates("EVENTO_ID").set_index("EVENTO_ID")["INICIO_UTC"]
    inicio = pd.to_datetime(inicio, utc=True)
    ahora = pd.Timestamp.now(tz="UTC")
    terminados = set(inicio[(inicio < ahora - pd.Timedelta(hours=3)) & (inicio > ahora - pd.Timedelta(days=3))].index)
    resultados = actualizar_resultados(ids & terminados)
    ganador = resultados.set_index("EVENTO_ID")["GANADOR"] if not resultados.empty else pd.Series(dtype=str)

    cierre = probabilidades_cierre(pd.read_csv(config.MOMIOS / "momios_historico.csv"))
    p_cierre = cierre.set_index(["EVENTO_ID", "EQUIPO"])["PROB_CIERRE"]

    # ===== 1) Apuestas simuladas =====
    if not apuestas.empty:
        a = apuestas.copy()
        a["DECIMAL"] = a["MEJOR_MOMIO"].apply(a_decimal)
        a["GANADOR"] = a["EVENTO_ID"].map(ganador)
        a["RESULTADO"] = np.where(a["GANADOR"].isna(), "PENDIENTE",
                                  np.where(a["GANADOR"] == a["APUESTA"], "GANADA", "PERDIDA"))
        a["GANANCIA"] = np.select([a["RESULTADO"] == "GANADA", a["RESULTADO"] == "PERDIDA"],
                                  [a["MONTO"] * (a["DECIMAL"] - 1), -a["MONTO"]], 0.0).round(2)
        a["PROB_CIERRE"] = [p_cierre.get((e, t), np.nan) for e, t in zip(a["EVENTO_ID"], a["APUESTA"])]
        # CLV: valor de nuestro momio medido con la probabilidad justa de cierre
        a["CLV_%"] = (100 * (a["DECIMAL"] * a["PROB_CIERRE"] - 1)).round(1)
        a.to_csv(config.DATOS / "reporte_apuestas.csv", index=False)

        liq = a[a["RESULTADO"] != "PENDIENTE"]
        print("\n=== APUESTAS SIMULADAS ===")
        print(f"Registradas: {len(a)} · liquidadas: {len(liq)} · pendientes: {(a['RESULTADO'] == 'PENDIENTE').sum()}")
        if not liq.empty:
            arriesgado = liq["MONTO"].sum()
            ganancia = liq["GANANCIA"].sum()
            print(f"Ganadas: {(liq['RESULTADO'] == 'GANADA').sum()} · Perdidas: {(liq['RESULTADO'] == 'PERDIDA').sum()}")
            print(f"Arriesgado: ${arriesgado:,.0f} · Ganancia: ${ganancia:,.0f} · "
                  f"ROI: {100 * ganancia / arriesgado:.1f}%")
            print(f"Bankroll simulado: ${config.BANKROLL + ganancia:,.0f} (inicial ${config.BANKROLL:,.0f})")
        con_clv = a.dropna(subset=["CLV_%"])
        if not con_clv.empty:
            print(f"CLV promedio: {con_clv['CLV_%'].mean():+.1f}% · "
                  f"le ganamos al cierre en {100 * (con_clv['CLV_%'] > 0).mean():.0f}% de las apuestas")
        print("\nÚltimas apuestas:")
        cols = ["INICIO (CDMX)", "PARTIDO", "APUESTA", "MEJOR_MOMIO", "MONTO", "RESULTADO", "GANANCIA", "CLV_%"]
        print(a[cols].tail(10).to_string(index=False))

    # ===== 2) Modelo vs. mercado en todos los partidos =====
    if not pred.empty:
        p = pred.copy()
        p = p[pd.to_datetime(p["REGISTRADA_UTC"], utc=True) < pd.to_datetime(p["INICIO_UTC"], utc=True)]
        p = p.sort_values("REGISTRADA_UTC").groupby("EVENTO_ID").last().reset_index()
        p["GANADOR"] = p["EVENTO_ID"].map(ganador)
        p = p.dropna(subset=["GANADOR", "PROB_MERCADO_LOCAL"])
        if not p.empty:
            local = p["PARTIDO"].str.split(" @ ").str[1]
            y = (p["GANADOR"] == local).astype(int).to_numpy()
            p["PROB_CIERRE_LOCAL"] = [p_cierre.get((e, l), np.nan) for e, l in zip(p["EVENTO_ID"], local)]
            brier = lambda col: float(np.nanmean((p[col].to_numpy() - y) ** 2))  # noqa: E731
            print(f"\n=== MODELO vs. MERCADO ({len(p)} partidos terminados) ===  (Brier: menor = mejor)")
            print(f"  Modelo:                   {brier('PROB_MODELO_LOCAL'):.4f}")
            print(f"  Mercado al predecir:      {brier('PROB_MERCADO_LOCAL'):.4f}")
            print(f"  Mercado al cierre:        {brier('PROB_CIERRE_LOCAL'):.4f}")

    print(
        "\nCómo leerlo:\n"
        "  - CLV positivo y constante = señal real de ventaja (aunque el ROI vaya mal por mala suerte).\n"
        "  - Con menos de ~300 apuestas, el ROI es casi puro ruido. No saques conclusiones antes.\n"
        "  - Si el Brier del modelo NO baja del Brier del mercado, el modelo todavía no le gana a las casas."
    )


if __name__ == "__main__":
    main()
