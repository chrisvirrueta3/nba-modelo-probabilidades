"""
FASE 5 · Exportar los datos para la página web.

Junta en un solo archivo web/datos.json:
  - Partidos próximos con probabilidades, EV y estado (de valor.py)
  - Ratings Elo actuales
  - Historial de apuestas simuladas con resultado y CLV (de liquidar.py)
  - Resumen: ROI, bankroll, CLV promedio, modelo vs. mercado

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


def proximos() -> list:
    momios = pd.read_csv(config.MOMIOS / "momios_historico.csv")
    m = valor.partidos_proximos(momios)
    if m.empty:
        return []
    m = m[~m["CASA"].isin(config.CASAS_EXCLUIDAS)].copy()
    m["EQUIPO"] = m["RESULTADO"].map(config.abreviatura)
    m["DECIMAL"] = m["MOMIO"].apply(valor.a_decimal)
    eventos = m.drop_duplicates("EVENTO_ID")[["EVENTO_ID", "INICIO", "LOCAL", "VISITA"]].reset_index(drop=True)
    p_local = valor.probabilidades_modelo(eventos)
    try:
        import lesiones
        _, det = lesiones.bajas_esperadas()
    except Exception:  # noqa: BLE001
        det = pd.DataFrame(columns=["EQUIPO", "JUGADOR", "ESTADO", "PROB_JUGAR", "VALOR"])

    salida = []
    for ev in eventos.sort_values("INICIO").itertuples(index=False):
        g = m[m["EVENTO_ID"] == ev.EVENTO_ID]
        pin = g[g["CASA"] == "pinnacle"].set_index("EQUIPO")["MOMIO"]
        justa = None
        if len(pin) == 2:
            impl = pin.apply(valor.prob_implicita)
            justa = impl / impl.sum()
        lados = []
        for equipo, es_local in ((ev.VISITA, False), (ev.LOCAL, True)):
            p = float(p_local[ev.EVENTO_ID] if es_local else 1 - p_local[ev.EVENTO_ID])
            lado = g[g["EQUIPO"] == equipo]
            mejor = lado.loc[lado["DECIMAL"].idxmax()]
            ev_pct = p * mejor["DECIMAL"] - 1
            pj = float(justa[equipo]) if justa is not None else None
            f = valor.kelly(p, mejor["DECIMAL"])
            if pj is not None and abs(p - pj) > config.DIF_SOSPECHOSA:
                estado = "sospechosa"
            elif ev_pct >= config.UMBRAL_EV:
                estado = "valor"
            else:
                estado = "nada"
            monto = config.BANKROLL * min(max(f, 0) * config.KELLY_FRACCION, config.TOPE_APUESTA)
            lados.append({
                "equipo": equipo, "local": es_local,
                "modelo": round(100 * p, 1), "mercado": round(100 * pj, 1) if pj is not None else None,
                "momio": int(mejor["MOMIO"]), "casa": mejor["CASA"],
                "pinnacle": int(pin[equipo]) if equipo in pin else None,
                "ev": round(100 * ev_pct, 1), "estado": estado,
                "monto": round(monto) if estado == "valor" else 0,
                "bajas": [{"jugador": b.JUGADOR, "prob": int(round(100 * b.PROB_JUGAR)), "valor": float(b.VALOR)}
                          for b in det[det["EQUIPO"] == equipo].itertuples() if b.PROB_JUGAR < 1],
            })
        salida.append({"id": ev.EVENTO_ID, "inicio": ev.INICIO.isoformat(), "lados": lados})
    return salida


def historial():
    ruta = config.DATOS / "reporte_apuestas.csv"
    if not ruta.exists():
        ruta = config.DATOS / "apuestas_simuladas.csv"
        if not ruta.exists():
            return [], {}
    a = pd.read_csv(ruta)
    for col, default in (("RESULTADO", "PENDIENTE"), ("GANANCIA", 0.0), ("CLV_%", np.nan)):
        if col not in a:
            a[col] = default
    liq = a[a["RESULTADO"] != "PENDIENTE"]
    clv = a["CLV_%"].dropna()
    arriesgado = float(liq["MONTO"].sum())
    ganancia = float(liq["GANANCIA"].sum())
    resumen = {
        "apuestas": int(len(a)), "liquidadas": int(len(liq)),
        "ganadas": int((liq["RESULTADO"] == "GANADA").sum()),
        "perdidas": int((liq["RESULTADO"] == "PERDIDA").sum()),
        "arriesgado": round(arriesgado, 2), "ganancia": round(ganancia, 2),
        "roi": round(100 * ganancia / arriesgado, 1) if arriesgado else None,
        "bankroll": round(config.BANKROLL + ganancia, 2), "bankroll_inicial": config.BANKROLL,
        "clv_promedio": round(float(clv.mean()), 1) if len(clv) else None,
        "clv_positivo": round(100 * float((clv > 0).mean())) if len(clv) else None,
    }
    cols = {"INICIO (CDMX)": "fecha", "PARTIDO": "partido", "APUESTA": "apuesta", "MEJOR_MOMIO": "momio",
            "CASA": "casa", "MONTO": "monto", "EV_%": "ev", "RESULTADO": "resultado",
            "GANANCIA": "ganancia", "CLV_%": "clv"}
    h = a[[c for c in cols if c in a]].rename(columns=cols).iloc[::-1]
    return limpio(h), resumen


def main():
    ratings = pd.read_csv(config.PROCESADOS / "ratings_actuales.csv")
    params = json.loads((config.PROCESADOS / "elo_parametros.json").read_text())
    hist, resumen = historial()
    datos = {
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "config": {"bankroll": config.BANKROLL, "kelly": config.KELLY_FRACCION, "tope": config.TOPE_APUESTA,
                   "umbral_ev": config.UMBRAL_EV, "dif_sospechosa": config.DIF_SOSPECHOSA, "hca": params["HCA"]},
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
