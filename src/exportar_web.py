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
                "ev": _num(r["EV_%"]), "estado": {"VALOR": "valor", "SOSPECHOSA": "sospechosa"}.get(r["ESTADO"], "nada"),
                "monto": int(r["MONTO"]),
                "bajas": [{"jugador": b.JUGADOR, "prob": int(round(100 * b.PROB_JUGAR)), "valor": float(b.VALOR)}
                          for b in det[det["EQUIPO"] == equipo].itertuples() if b.PROB_JUGAR < 1],
            })
        puntos_ = [{
            "mercado": r["MERCADO"], "lado": r["LADO"], "texto": r["APUESTA"],
            "modelo": _num(r["MODELO_%"]), "mercado_pct": _num(r["MERCADO_%"]),
            "momio": int(r["MEJOR_MOMIO"]), "casa": r["CASA"], "ev": _num(r["EV_%"]),
            "estado": {"VALOR": "valor", "SOSPECHOSA": "sospechosa"}.get(r["ESTADO"], "nada"),
            "monto": int(r["MONTO"]),
        } for _, r in t[t["MERCADO"].isin(["spreads", "totals"])]
            .sort_values("LADO", key=lambda s: s.map({"V": 0, "L": 1, "Over": 2, "Under": 3})).iterrows()]

        salida.append({
            "id": ev.EVENTO_ID, "inicio": ev.INICIO.isoformat(), "local": ev.LOCAL, "visita": ev.VISITA,
            "lados": lados, "puntos": puntos_,
            "proyeccion": {"margen_local": _num(pr["MU_MARGEN"]), "total": _num(pr["MU_TOTAL"]),
                           "pin_spread_local": _num(pr["PIN_SPREAD_LOCAL"]), "pin_total": _num(pr["PIN_TOTAL"])},
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
    cols = {"INICIO (CDMX)": "fecha", "PARTIDO": "partido", "MERCADO": "mercado", "APUESTA": "apuesta",
            "MEJOR_MOMIO": "momio", "CASA": "casa", "MONTO": "monto", "EV_%": "ev", "RESULTADO": "resultado",
            "GANANCIA": "ganancia", "CLV": "clv"}
    h = a[[c for c in cols if c in a]].rename(columns=cols).iloc[::-1]
    return limpio(h), resumen


def main():
    ratings = pd.read_csv(config.PROCESADOS / "ratings_actuales.csv")
    params = json.loads((config.PROCESADOS / "elo_parametros.json").read_text())
    hist, resumen = historial()
    datos = {
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "config": {"bankroll": config.BANKROLL, "kelly": config.KELLY_FRACCION, "tope": config.TOPE_APUESTA,
                   "umbral_ev": config.UMBRAL_EV, "umbral_ev_puntos": config.UMBRAL_EV_PUNTOS,
                   "dif_sospechosa": config.DIF_SOSPECHOSA, "hca": params["HCA"]},
        "proximos": proximos(),
        "ratings": limpio(ratings.rename(columns={"RANK": "rank", "EQUIPO": "equipo", "ELO": "elo"})),
        "historial": hist,
        "resumen": resumen,
    }
    (WEB / "datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"web/datos.json listo: {len(datos['proximos'])} partidos próximos, "
          f"{len(hist)} apuestas en historial.")


if __name__ == "__main__":
    main()
