"""
Exportar los datos para la página web.

Junta en un solo archivo web/datos.json:
  - Partidos próximos: ganador, spread y total, con probabilidades, EV y estado
    (el mismo análisis de valor.py) + proyección de puntos y lesiones
  - Ratings Elo actuales
  - Historial de apuestas simuladas con resultado y CLV (de liquidar.py)
  - Resumen: ROI, bankroll, CLV promedio

Uso (después de valor.py y liquidar.py):
    python src/exportar_web.py
Luego se publica la carpeta web/ en Netlify.
"""
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import config
import creditos
import valor

WEB = config.RAIZ / "web"
WEB.mkdir(exist_ok=True)


def limpio(df: pd.DataFrame) -> list:
    """DataFrame -> lista de dicts apta para JSON (NaN -> null)."""
    return json.loads(df.replace({np.nan: None}).to_json(orient="records", force_ascii=False))


def _num(x, nd=1):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), nd)


def proximos() -> list:
    tabla, eventos, proy = valor.analizar()
    if tabla.empty:
        return []
    try:
        import lesiones
        _, det = lesiones.bajas_esperadas()
    except Exception:  # noqa: BLE001
        det = pd.DataFrame(columns=["EQUIPO", "JUGADOR", "ESTADO", "PROB_JUGAR", "VALOR"])

    momios = pd.read_csv(config.MOMIOS / "momios_historico.csv")
    h2h = valor.partidos_proximos(momios, "h2h")
    h2h = h2h[h2h["CASA"] == "pinnacle"].assign(EQUIPO=lambda d: d["RESULTADO"].map(config.abreviatura))
    pin_ml = h2h.set_index(["EVENTO_ID", "EQUIPO"])["MOMIO"]

    salida = []
    for ev in eventos.sort_values("INICIO").itertuples(index=False):
        t = tabla[tabla["EVENTO_ID"] == ev.EVENTO_ID]
        pr = proy.loc[ev.EVENTO_ID]
        lados = []
        for equipo, es_local in ((ev.VISITA, False), (ev.LOCAL, True)):
            r = t[(t["MERCADO"] == "h2h") & (t["LADO"] == equipo)]
            if r.empty:
                continue
            r = r.iloc[0]
            lados.append({
                "equipo": equipo, "local": es_local,
                "modelo": _num(r["MODELO_%"]), "mercado": _num(r["MERCADO_%"]),
                "momio": int(r["MEJOR_MOMIO"]), "casa": r["CASA"],
                "pinnacle": int(pin_ml[(ev.EVENTO_ID, equipo)]) if (ev.EVENTO_ID, equipo) in pin_ml else None,
                "ev": _num(r["EV_%"]), "prob": _num(r.get("PROB_%")),
                "estado": {"VALOR": "valor", "SOSPECHOSA": "sospechosa", "SIN_REFERENCIA": "sinref"}.get(r["ESTADO"], "nada"),
                "monto": int(r["MONTO"]),
                "bajas": [{"jugador": b.JUGADOR, "prob": int(round(100 * b.PROB_JUGAR)), "valor": float(b.VALOR)}
                          for b in det[det["EQUIPO"] == equipo].itertuples() if b.PROB_JUGAR < 1],
            })
        puntos_ = [{
            "mercado": r["MERCADO"], "lado": r["LADO"], "texto": r["APUESTA"],
            "modelo": _num(r["MODELO_%"]), "mercado_pct": _num(r["MERCADO_%"]),
            "momio": int(r["MEJOR_MOMIO"]), "casa": r["CASA"], "ev": _num(r["EV_%"]),
            "estado": {"VALOR": "valor", "SOSPECHOSA": "sospechosa", "SIN_REFERENCIA": "sinref"}.get(r["ESTADO"], "nada"),
            "monto": int(r["MONTO"]),
        } for _, r in t[t["MERCADO"].isin(["spreads", "totals"])]
            .sort_values("LADO", key=lambda s: s.map({"V": 0, "L": 1, "Over": 2, "Under": 3})).iterrows()]

        salida.append({
            "id": ev.EVENTO_ID, "inicio": ev.INICIO.isoformat(), "local": ev.LOCAL, "visita": ev.VISITA,
            "lados": lados, "puntos": puntos_,
            "proyeccion": {"margen_local": _num(pr["MU_MARGEN"]), "total": _num(pr["MU_TOTAL"]),
                           "margen_apuesta": _num(pr.get("MU_MARGEN_AP")), "total_apuesta": _num(pr.get("MU_TOTAL_AP")),
                           "pin_spread_local": _num(pr["PIN_SPREAD_LOCAL"]), "pin_total": _num(pr["PIN_TOTAL"]),
                           "sigma_margen": _num(pr.get("SIGMA_MARGEN")), "sigma_total": _num(pr.get("SIGMA_TOTAL"))},
        })
    return salida


def historial():
    ruta = config.DATOS / "reporte_apuestas.csv"
    if not ruta.exists():
        ruta = config.DATOS / "apuestas_simuladas.csv"
        if not ruta.exists():
            return [], {}
    a = pd.read_csv(ruta)
    for col, default in (("RESULTADO", "PENDIENTE"), ("GANANCIA", 0.0), ("CLV_%", np.nan),
                         ("CLV_PTS", np.nan), ("MERCADO", "h2h")):
        if col not in a:
            a[col] = default
    a["MERCADO"] = a["MERCADO"].fillna("h2h")
    liq = a[a["RESULTADO"] != "PENDIENTE"]
    con_dinero = liq[liq["RESULTADO"] != "PUSH"]
    clv = a["CLV_%"].dropna()
    clv_pts = a["CLV_PTS"].dropna()
    arriesgado = float(con_dinero["MONTO"].sum())
    ganancia = float(liq["GANANCIA"].sum())
    resumen = {
        "apuestas": int(len(a)), "liquidadas": int(len(liq)),
        "ganadas": int((liq["RESULTADO"] == "GANADA").sum()),
        "perdidas": int((liq["RESULTADO"] == "PERDIDA").sum()),
        "push": int((liq["RESULTADO"] == "PUSH").sum()),
        "arriesgado": round(arriesgado, 2), "ganancia": round(ganancia, 2),
        "roi": round(100 * ganancia / arriesgado, 1) if arriesgado else None,
        "bankroll": round(config.BANKROLL + ganancia, 2), "bankroll_inicial": config.BANKROLL,
        "clv_promedio": round(float(clv.mean()), 1) if len(clv) else None,
        "clv_positivo": round(100 * float((clv > 0).mean())) if len(clv) else None,
        "clv_pts": round(float(clv_pts.mean()), 2) if len(clv_pts) else None,
    }
    a["CLV"] = np.where(a["MERCADO"] == "h2h", a["CLV_%"], a["CLV_PTS"])
    cols = {"REGISTRADA_UTC": "registrada", "INICIO (CDMX)": "fecha", "PARTIDO": "partido", "MERCADO": "mercado",
            "APUESTA": "apuesta", "MEJOR_MOMIO": "momio", "CASA": "casa", "MONTO": "monto", "EV_%": "ev",
            "RESULTADO": "resultado", "GANANCIA": "ganancia", "CLV": "clv"}
    h = limpio(a[[c for c in cols if c in a]].rename(columns=cols))

    # Parlays simulados (no cuentan para el CLV, sí para el dinero)
    rp = config.DATOS / "reporte_parlays.csv"
    if not rp.exists():
        rp = config.DATOS / "parlays_simulados.csv"
    if rp.exists():
        pr = pd.read_csv(rp)
        for col, default in (("RESULTADO", "PENDIENTE"), ("GANANCIA", 0.0)):
            if col not in pr:
                pr[col] = default
        for _, r in pr.iterrows():
            patas = json.loads(r["PATAS"])
            d = float(r["DECIMAL"])
            h.append({"registrada": r["REGISTRADA_UTC"], "fecha": str(r.get("INICIO (CDMX)") or r["DIA"]),
                      "partido": f"Parlay de {int(r['N'])}", "mercado": "parlay",
                      "apuesta": " + ".join(x["APUESTA"] for x in patas),
                      "patas": [{"mercado": x["MERCADO"], "apuesta": x["APUESTA"], "partido": x["PARTIDO"]} for x in patas],
                      "momio": int(round((d - 1) * 100)) if d >= 2 else int(round(-100 / (d - 1))),
                      "casa": "parlay", "monto": float(r["MONTO"]), "ev": float(r["EV_%"]),
                      "resultado": r["RESULTADO"], "ganancia": float(r["GANANCIA"]), "clv": None})
        liq_p = pr[pr["RESULTADO"] != "PENDIENTE"]
        g_p = float(liq_p["GANANCIA"].sum())
        arr_p = float(liq_p.loc[liq_p["RESULTADO"] != "PUSH", "MONTO"].sum())
        resumen["parlays"] = {"registrados": int(len(pr)), "liquidados": int(len(liq_p)),
                              "ganados": int((liq_p["RESULTADO"] == "GANADA").sum()), "ganancia": round(g_p, 2)}
        resumen["ganancia"] = round(resumen["ganancia"] + g_p, 2)
        resumen["arriesgado"] = round(resumen["arriesgado"] + arr_p, 2)
        resumen["roi"] = round(100 * resumen["ganancia"] / resumen["arriesgado"], 1) if resumen["arriesgado"] else None
        resumen["bankroll"] = round(config.BANKROLL + resumen["ganancia"], 2)
    h.sort(key=lambda x: str(x.get("registrada") or ""), reverse=True)
    return h, resumen


def comparacion_mercado() -> dict | None:
    """
    ¿El modelo le gana a las casas? Compara, en TODOS los partidos ya jugados (no solo en los
    que se apostó), qué tan cerca estuvo cada probabilidad del resultado (Brier: menor = mejor):
    el modelo solo, Pinnacle cuando se hizo la predicción, y Pinnacle al cierre.
    """
    import liquidar
    rp, rr = config.DATOS / "predicciones.csv", config.DATOS / "resultados.csv"
    if not (rp.exists() and rr.exists()):
        return None
    p = pd.read_csv(rp)
    p = p[pd.to_datetime(p["REGISTRADA_UTC"], utc=True) < pd.to_datetime(p["INICIO_UTC"], utc=True)]
    p = p.sort_values("REGISTRADA_UTC").drop_duplicates("EVENTO_ID", keep="last")
    x = p.merge(pd.read_csv(rr), on="EVENTO_ID").dropna(subset=["PROB_MERCADO_LOCAL"])
    if x.empty:
        return None
    x["Y"] = (x["GANADOR"] == x["LOCAL"]).astype(float)
    try:
        pc = liquidar.probabilidades_cierre(pd.read_csv(config.MOMIOS / "momios_historico.csv"))
        x = x.merge(pc.rename(columns={"EQUIPO": "LOCAL", "PROB_CIERRE": "CIERRE"}), on=["EVENTO_ID", "LOCAL"], how="left")
    except Exception:
        x["CIERRE"] = np.nan
    bm = (x["PROB_MODELO_LOCAL"] - x["Y"]) ** 2
    bk = (x["PROB_MERCADO_LOCAL"] - x["Y"]) ** 2
    dif = (bm - bk).to_numpy()
    rng = np.random.default_rng(0)
    prob_mejor = float(np.mean([rng.choice(dif, len(dif)).mean() < 0 for _ in range(2000)])) if len(dif) > 5 else None
    x["DIA"] = pd.to_datetime(x["INICIO_UTC"], utc=True).dt.tz_convert("America/Mexico_City").dt.strftime("%Y-%m-%d")
    x["DIF"] = dif
    por_dia = x.groupby("DIA")["DIF"].agg(["sum", "size"]).cumsum()
    con_cierre = x.dropna(subset=["CIERRE"])
    return {
        "partidos": int(len(x)),
        "brier_modelo": round(float(bm.mean()), 4), "brier_mercado": round(float(bk.mean()), 4),
        "brier_cierre": round(float(((con_cierre["CIERRE"] - con_cierre["Y"]) ** 2).mean()), 4) if len(con_cierre) else None,
        "acierto_modelo": round(100 * float(((x["PROB_MODELO_LOCAL"] > .5) == (x["Y"] == 1)).mean()), 1),
        "acierto_mercado": round(100 * float(((x["PROB_MERCADO_LOCAL"] > .5) == (x["Y"] == 1)).mean()), 1),
        "prob_modelo_mejor": None if prob_mejor is None else round(prob_mejor, 3),
        # diferencia acumulada (modelo − casas) por día: negativa = el modelo va mejor
        "serie": [{"dia": d, "dif": round(float(r["sum"] / r["size"]), 5), "n": int(r["size"])} for d, r in por_dia.iterrows()],
    }


def resultados_y_cierres():
    """Para liquidar en el teléfono las apuestas reales: marcadores finales y momios/líneas de cierre."""
    import liquidar
    res = {}
    ruta = config.DATOS / "resultados.csv"
    if ruta.exists():
        for r in pd.read_csv(ruta).itertuples():
            res[r.EVENTO_ID] = {"local": r.LOCAL, "visita": r.VISITA,
                                "pts_local": int(r.PTS_LOCAL), "pts_visita": int(r.PTS_VISITA)}
    cierres = {}
    try:
        momios = pd.read_csv(config.MOMIOS / "momios_historico.csv")
        pc = liquidar.probabilidades_cierre(momios)
        for r in pc.itertuples():
            cierres.setdefault(r.EVENTO_ID, {"h2h": {}})["h2h"][r.EQUIPO] = round(float(r.PROB_CIERRE), 4)
        lc = liquidar.lineas_cierre(momios)
        for e, r in lc.iterrows():
            c = cierres.setdefault(e, {"h2h": {}})
            c["spread_local"] = _num(r["CIERRE_SPREAD_LOCAL"], 1)
            c["total"] = _num(r["CIERRE_TOTAL"], 1)
    except Exception as e:  # el cierre es un extra: nunca debe romper la página
        print(f"(aviso) no se pudieron calcular los cierres: {e}")
    return res, cierres


def main():
    ratings = pd.read_csv(config.PROCESADOS / "ratings_actuales.csv")
    params = json.loads((config.PROCESADOS / "elo_parametros.json").read_text())
    hist, resumen = historial()
    res, cierres = resultados_y_cierres()
    datos = {
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "config": {"bankroll": config.BANKROLL, "kelly": config.KELLY_FRACCION, "tope": config.TOPE_APUESTA,
                   "umbral_ev": config.UMBRAL_EV, "umbral_ev_puntos": config.UMBRAL_EV_PUNTOS,
                   "dif_sospechosa": config.DIF_SOSPECHOSA, "peso_modelo": config.PESO_MODELO, "parlays": config.PARLAYS_ACTIVOS, "hca": params["HCA"]},
        "proximos": proximos(),
        "ratings": limpio(ratings.rename(columns={"RANK": "rank", "EQUIPO": "equipo", "ELO": "elo"})),
        "historial": hist,
        "resumen": resumen,
        "resultados": res,
        "cierres": cierres,
        "creditos": creditos.leer(),
        "comparacion": comparacion_mercado(),
    }
    (WEB / "datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"web/datos.json listo: {len(datos['proximos'])} partidos próximos, "
          f"{len(hist)} apuestas en historial.")


if __name__ == "__main__":
    main()
