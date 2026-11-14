"""
FASE 4 · Liquidar apuestas simuladas y medir si el modelo le gana al mercado.

Qué hace:
  1. Baja los resultados de los últimos 3 días (The Odds API, endpoint /scores,
     2 créditos por llamada) y los guarda en datos/resultados.csv para no repetir.
  2. Liquida cada apuesta simulada: GANADA / PERDIDA y su ganancia.
  3. Calcula el CLV (Closing Line Value): ¿el momio que tomamos era mejor que la
     probabilidad justa de CIERRE de Pinnacle? Es el mejor indicador de habilidad:
     el ROI tarda cientos de apuestas en dejar de ser ruido; el CLV, muchas menos.
  4. Compara el modelo contra el mercado en TODOS los partidos predichos
     (Brier para ganador; error en puntos para spreads y totales).

Spreads y totales: el push (empate exacto con la línea) devuelve la apuesta.
Su CLV se mide en PUNTOS: si tomaste +5.5 y Pinnacle cerró en +4, ganaste
1.5 puntos de línea (CLV +1.5). Cada punto en la NBA vale aprox. 3% de probabilidad.

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


def lineas_cierre(momios: pd.DataFrame) -> pd.DataFrame:
    """
    Línea de cierre de cada partido que ya empezó: hándicap del LOCAL y total.
    Prioriza Pinnacle; si no está, usa la mediana de todas las casas.
    """
    m = momios[momios["MERCADO"].isin(["spreads", "totals"])].dropna(subset=["LINEA"]).copy()
    inicio = pd.to_datetime(m["INICIO_UTC"], utc=True)
    m = m[(pd.to_datetime(m["CAPTURADO_UTC"], utc=True) < inicio) & (inicio < pd.Timestamp.now(tz="UTC"))]
    if m.empty:
        return pd.DataFrame(columns=["CIERRE_SPREAD_LOCAL", "CIERRE_TOTAL"])
    m = m[m["CAPTURADO_UTC"] == m.groupby("EVENTO_ID")["CAPTURADO_UTC"].transform("max")]
    sp = m[(m["MERCADO"] == "spreads") & (m["RESULTADO"].map(lambda r: config.EQUIPOS.get(str(r).strip())) == m["LOCAL"])]
    tt = m[(m["MERCADO"] == "totals") & (m["RESULTADO"] == "Over")]

    def elegir(df):
        pin = df[df["CASA"] == "pinnacle"].groupby("EVENTO_ID")["LINEA"].first()
        return pin.combine_first(df.groupby("EVENTO_ID")["LINEA"].median())

    return pd.DataFrame({"CIERRE_SPREAD_LOCAL": elegir(sp), "CIERRE_TOTAL": elegir(tt)})


def liquidar_fila(r, res) -> str:
    """GANADA / PERDIDA / PUSH / PENDIENTE para una apuesta de cualquier mercado."""
    if r.EVENTO_ID not in res.index:
        return "PENDIENTE"
    x = res.loc[r.EVENTO_ID]
    if r.MERCADO == "h2h":
        return "GANADA" if x["GANADOR"] == r.LADO else "PERDIDA"
    margen = x["PTS_LOCAL"] - x["PTS_VISITA"]
    total = x["PTS_LOCAL"] + x["PTS_VISITA"]
    if r.MERCADO == "spreads":
        neto = (margen if r.LADO == "L" else -margen) + r.LINEA
    else:
        neto = (total - r.LINEA) if r.LADO == "Over" else (r.LINEA - total)
    return "GANADA" if neto > 0 else "PUSH" if neto == 0 else "PERDIDA"


def a_decimal(momio: float) -> float:
    return 1 + (momio / 100 if momio > 0 else 100 / -momio)


# ---------------- Reporte ----------------
def main():
    ruta_ap = config.DATOS / "apuestas_simuladas.csv"
    ruta_pred = config.DATOS / "predicciones.csv"
    ruta_pp = config.DATOS / "predicciones_puntos.csv"
    apuestas = pd.read_csv(ruta_ap) if ruta_ap.exists() else pd.DataFrame()
    pred = pd.read_csv(ruta_pred) if ruta_pred.exists() else pd.DataFrame()
    pred_pts = pd.read_csv(ruta_pp) if ruta_pp.exists() else pd.DataFrame()
    if apuestas.empty and pred.empty:
        print("Todavía no hay apuestas ni predicciones. Corre primero: python src/valor.py")
        return

    # Pedimos resultados solo de partidos registrados que empezaron hace 3+ horas
    # (ya terminaron) y de hace menos de 3 días (lo que cubre la API).
    ids = set(apuestas.get("EVENTO_ID", [])) | set(pred.get("EVENTO_ID", [])) | set(pred_pts.get("EVENTO_ID", []))
    momios_ini = pd.read_csv(config.MOMIOS / "momios_historico.csv", usecols=["EVENTO_ID", "INICIO_UTC"])
    inicio = momios_ini.drop_duplicates("EVENTO_ID").set_index("EVENTO_ID")["INICIO_UTC"]
    inicio = pd.to_datetime(inicio, utc=True)
    ahora = pd.Timestamp.now(tz="UTC")
    terminados = set(inicio[(inicio < ahora - pd.Timedelta(hours=3)) & (inicio > ahora - pd.Timedelta(days=3))].index)
    resultados = actualizar_resultados(ids & terminados)
    res = resultados.set_index("EVENTO_ID") if not resultados.empty else pd.DataFrame(
        columns=["GANADOR", "PTS_LOCAL", "PTS_VISITA"])
    ganador = res["GANADOR"]

    momios = pd.read_csv(config.MOMIOS / "momios_historico.csv")
    cierre = probabilidades_cierre(momios)
    lc = lineas_cierre(momios)
    p_cierre = cierre.set_index(["EVENTO_ID", "EQUIPO"])["PROB_CIERRE"]

    # ===== 1) Apuestas simuladas =====
    if not apuestas.empty:
        a = apuestas.copy()
        for col, default in (("MERCADO", "h2h"), ("LADO", None), ("LINEA", np.nan)):
            if col not in a:
                a[col] = default
        a["MERCADO"] = a["MERCADO"].fillna("h2h")
        a["LADO"] = a["LADO"].fillna(a["APUESTA"])
        a["DECIMAL"] = a["MEJOR_MOMIO"].apply(a_decimal)
        a["RESULTADO"] = [liquidar_fila(r, res) for r in a.itertuples()]
        a["GANANCIA"] = np.select([a["RESULTADO"] == "GANADA", a["RESULTADO"] == "PERDIDA"],
                                  [a["MONTO"] * (a["DECIMAL"] - 1), -a["MONTO"]], 0.0).round(2)

        # CLV ganador (%): valor de nuestro momio con la probabilidad justa de cierre
        es_h2h = a["MERCADO"] == "h2h"
        prob_c = [p_cierre.get((e, t), np.nan) for e, t in zip(a["EVENTO_ID"], a["LADO"])]
        a["CLV_%"] = np.where(es_h2h, (100 * (a["DECIMAL"] * np.array(prob_c, dtype=float) - 1)).round(1), np.nan)

        # CLV spreads/totales (puntos): nuestra línea vs. la de cierre
        def clv_pts(r):
            if r.EVENTO_ID not in lc.index or r.MERCADO == "h2h":
                return np.nan
            c = lc.loc[r.EVENTO_ID]
            if r.MERCADO == "spreads":
                cierre_lado = c["CIERRE_SPREAD_LOCAL"] if r.LADO == "L" else -c["CIERRE_SPREAD_LOCAL"]
                return r.LINEA - cierre_lado
            return (c["CIERRE_TOTAL"] - r.LINEA) if r.LADO == "Over" else (r.LINEA - c["CIERRE_TOTAL"])
        a["CLV_PTS"] = [clv_pts(r) for r in a.itertuples()]
        a.to_csv(config.DATOS / "reporte_apuestas.csv", index=False)

        liq = a[~a["RESULTADO"].isin(["PENDIENTE"])]
        print("\n=== APUESTAS SIMULADAS ===")
        print(f"Registradas: {len(a)} · liquidadas: {len(liq)} · pendientes: {(a['RESULTADO'] == 'PENDIENTE').sum()}")
        if not liq.empty:
            arriesgado = liq.loc[liq["RESULTADO"] != "PUSH", "MONTO"].sum()
            ganancia = liq["GANANCIA"].sum()
            print(f"Ganadas: {(liq['RESULTADO'] == 'GANADA').sum()} · Perdidas: {(liq['RESULTADO'] == 'PERDIDA').sum()}"
                  f" · Push: {(liq['RESULTADO'] == 'PUSH').sum()}")
            if arriesgado:
                print(f"Arriesgado: ${arriesgado:,.0f} · Ganancia: ${ganancia:,.0f} · ROI: {100 * ganancia / arriesgado:.1f}%")
            print(f"Bankroll simulado: ${config.BANKROLL + ganancia:,.0f} (inicial ${config.BANKROLL:,.0f})")
            print("\nPor mercado:")
            nombres = {"h2h": "Ganador", "spreads": "Spread", "totals": "Total"}
            for mk, g in liq.groupby("MERCADO"):
                arr = g.loc[g["RESULTADO"] != "PUSH", "MONTO"].sum()
                roi = f"{100 * g['GANANCIA'].sum() / arr:+.1f}%" if arr else "–"
                print(f"  {nombres.get(mk, mk):8s} {len(g):3d} apuestas · ganancia ${g['GANANCIA'].sum():,.0f} · ROI {roi}")
        clv1 = a["CLV_%"].dropna()
        if len(clv1):
            print(f"CLV ganador: {clv1.mean():+.1f}% · le ganamos al cierre en {100 * (clv1 > 0).mean():.0f}%")
        clv2 = a["CLV_PTS"].dropna()
        if len(clv2):
            print(f"CLV spreads/totales: {clv2.mean():+.2f} pts · le ganamos al cierre en {100 * (clv2 > 0).mean():.0f}%")
        print("\nÚltimas apuestas:")
        cols = ["INICIO (CDMX)", "PARTIDO", "APUESTA", "MEJOR_MOMIO", "MONTO", "RESULTADO", "GANANCIA", "CLV_%", "CLV_PTS"]
        print(a[cols].tail(12).to_string(index=False))

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

    # ===== 3) Puntos: modelo vs. líneas del mercado =====
    if not pred_pts.empty and not res.empty:
        q = pred_pts[pd.to_datetime(pred_pts["REGISTRADA_UTC"], utc=True)
                     < pd.to_datetime(pred_pts["INICIO_UTC"], utc=True)]
        q = q.sort_values("REGISTRADA_UTC").groupby("EVENTO_ID").last()
        q = q[q.index.isin(res.index)]
        if len(q):
            r = res.loc[q.index]
            margen = (r["PTS_LOCAL"] - r["PTS_VISITA"]).to_numpy(dtype=float)
            total = (r["PTS_LOCAL"] + r["PTS_VISITA"]).to_numpy(dtype=float)
            c = lc.reindex(q.index)
            err = lambda a, b: float(np.sqrt(np.nanmean((np.asarray(a, dtype=float) - b) ** 2)))  # noqa: E731
            print(f"\n=== PUNTOS: MODELO vs. MERCADO ({len(q)} partidos) ===  (error típico en puntos, menor = mejor)")
            print(f"  Margen · modelo {err(q['MU_MARGEN'], margen):5.2f} · Pinnacle al predecir "
                  f"{err(-q['PIN_SPREAD_LOCAL'], margen):5.2f} · al cierre {err(-c['CIERRE_SPREAD_LOCAL'], margen):5.2f}")
            print(f"  Total  · modelo {err(q['MU_TOTAL'], total):5.2f} · Pinnacle al predecir "
                  f"{err(q['PIN_TOTAL'], total):5.2f} · al cierre {err(c['CIERRE_TOTAL'], total):5.2f}")

    print(
        "\nCómo leerlo:\n"
        "  - CLV positivo y constante = señal real de ventaja (aunque el ROI vaya mal por mala suerte).\n"
        "  - Con menos de ~300 apuestas, el ROI es casi puro ruido. No saques conclusiones antes.\n"
        "  - Si el Brier del modelo NO baja del Brier del mercado, el modelo todavía no le gana a las casas."
    )


if __name__ == "__main__":
    main()
