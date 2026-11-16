"""
Valor esperado (EV) y monto sugerido para los partidos próximos.

TRES MERCADOS
  - Ganador (moneyline): probabilidad del modelo de ganador (modelo.py).
  - Spread (hándicap):   margen esperado ~ Normal(μ, σ)   (puntos.py)
  - Total (over/under):  total esperado  ~ Normal(μ, σ)   (puntos.py)

Para cada lado de cada mercado:
  1. Probabilidad del modelo.
  2. Probabilidad "justa" del mercado = Pinnacle sin su margen.
  3. Mejor oferta entre todas las casas. En spreads/totales cada casa puede tener
     una línea distinta (−5.5 aquí, −6 allá): evaluamos TODAS y elegimos la de
     mayor EV ("line shopping").
  4. EV = P(ganar)·(momio_decimal − 1) − P(perder)    (los empates/push devuelven la apuesta)
  5. Monto con Kelly fraccional y tope por apuesta.

FILTROS DE SEGURIDAD:
  - Ganador: valor si EV ≥ UMBRAL_EV; sospechosa si el modelo difiere del
    mercado por más de DIF_SOSPECHOSA (en probabilidad).
  - Spreads/totales: valor si EV ≥ UMBRAL_EV_PUNTOS (más exigente, porque el
    modelo de puntos es menos preciso que las líneas); sospechosa si la
    proyección difiere de la línea de Pinnacle por más de DIF_SOSPECHOSA_SPREAD
    o DIF_SOSPECHOSA_TOTAL puntos, o si el ganador de ese partido ya es sospechoso.

TODO se registra como apuesta SIMULADA en datos/apuestas_simuladas.csv.

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
import puntos
from predecir_hoy import prob_implicita


def a_decimal(momio_americano: float) -> float:
    m = float(momio_americano)
    return 1 + (m / 100 if m > 0 else 100 / -m)


def kelly(prob: float, decimal: float, prob_perder: float | None = None) -> float:
    """Fracción del bankroll según Kelly completo (negativa = no apostar). Con push: prob_perder < 1 − prob."""
    q = 1 - prob if prob_perder is None else prob_perder
    return (prob * (decimal - 1) - q) / (decimal - 1)


def partidos_proximos(momios: pd.DataFrame, mercado: str | None = "h2h") -> pd.DataFrame:
    """Momios del último snapshot para partidos que no han empezado. mercado=None -> todos."""
    ahora = pd.Timestamp.now(tz="UTC")
    ultima = momios["CAPTURADO_UTC"].max()
    m = momios[momios["CAPTURADO_UTC"] == ultima].copy()
    if mercado:
        m = m[m["MERCADO"] == mercado]
    m["INICIO"] = pd.to_datetime(m["INICIO_UTC"], utc=True)
    return m[m["INICIO"] > ahora]


def features_futuros(eventos: pd.DataFrame) -> pd.DataFrame:
    """Variables del modelo para partidos futuros (índice = EVENTO_ID)."""
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
    return car.construir(todo).set_index("GAME_ID").loc[futuros["GAME_ID"]]


def probabilidades_modelo(eventos: pd.DataFrame, feats: pd.DataFrame | None = None) -> pd.Series:
    """Probabilidad de que gane el local, por EVENTO_ID."""
    feats = features_futuros(eventos) if feats is None else feats
    paquete = joblib.load(config.PROCESADOS / "modelo.joblib")
    p = paquete["modelo"].predict_proba(feats[paquete["columnas"]])[:, 1]
    return pd.Series(p, index=feats.index.to_numpy())


def proyeccion_puntos(feats: pd.DataFrame) -> pd.DataFrame:
    """Margen esperado del local, total esperado y sus σ, por EVENTO_ID."""
    paq = joblib.load(config.PROCESADOS / "modelo_puntos.joblib")
    mu_m, mu_t = puntos.predecir(paq, feats)
    return pd.DataFrame({"MU_MARGEN": mu_m, "MU_TOTAL": mu_t,
                         "SIGMA_MARGEN": paq["margen"]["sigma"], "SIGMA_TOTAL": paq["total"]["sigma"]},
                        index=feats.index.to_numpy())


def _estado(p_modelo: float, p_justa: float, ev: float) -> str:
    if np.isfinite(p_justa) and abs(p_modelo - p_justa) > config.DIF_SOSPECHOSA:
        return "SOSPECHOSA"
    return "VALOR" if ev >= config.UMBRAL_EV else "-"


def _monto(p_gana: float, p_pierde: float, decimal: float, estado: str) -> float:
    if estado != "VALOR":
        return 0
    f = kelly(p_gana, decimal, p_pierde)
    return round(config.BANKROLL * min(max(f, 0) * config.KELLY_FRACCION, config.TOPE_APUESTA), 0)


def fmt_linea(x: float) -> str:
    return f"{x:+g}"


def analizar_ganador(m: pd.DataFrame, eventos: pd.DataFrame, p_local: pd.Series) -> list:
    filas = []
    for ev in eventos.itertuples(index=False):
        g = m[(m["EVENTO_ID"] == ev.EVENTO_ID) & (m["MERCADO"] == "h2h")]
        if g.empty:
            continue
        pin = g[g["CASA"] == "pinnacle"].set_index("EQUIPO")["MOMIO"]
        justa = None
        if len(pin) == 2:
            impl = pin.apply(prob_implicita)
            justa = impl / impl.sum()
        for equipo, es_local in ((ev.LOCAL, True), (ev.VISITA, False)):
            p = float(p_local[ev.EVENTO_ID] if es_local else 1 - p_local[ev.EVENTO_ID])
            lado = g[g["EQUIPO"] == equipo]
            mejor = lado.loc[lado["DECIMAL"].idxmax()]
            ev_ = p * mejor["DECIMAL"] - 1
            pj = float(justa[equipo]) if justa is not None else np.nan
            estado = _estado(p, pj, ev_)
            filas.append({
                "EVENTO_ID": ev.EVENTO_ID, "INICIO": ev.INICIO, "PARTIDO": f"{ev.VISITA} @ {ev.LOCAL}",
                "MERCADO": "h2h", "LADO": equipo, "LINEA": np.nan, "APUESTA": equipo,
                "MODELO_%": round(100 * p, 1), "MERCADO_%": round(100 * pj, 1),
                "MEJOR_MOMIO": int(mejor["MOMIO"]), "CASA": mejor["CASA"],
                "EV_%": round(100 * ev_, 1), "MONTO": _monto(p, 1 - p, mejor["DECIMAL"], estado), "ESTADO": estado,
            })
    return filas


def analizar_puntos(m: pd.DataFrame, eventos: pd.DataFrame, proy: pd.DataFrame,
                    sospechosos: set | None = None) -> list:
    """Spreads y totales: evalúa todas las ofertas (casa, línea, momio) de cada lado."""
    sospechosos = sospechosos or set()
    filas = []
    for ev in eventos.itertuples(index=False):
        pr = proy.loc[ev.EVENTO_ID]
        dif_pts = {"spreads": abs(pr["MU_MARGEN"] + pr["PIN_SPREAD_LOCAL"]),   # margen esperado vs. −línea
                   "totals": abs(pr["MU_TOTAL"] - pr["PIN_TOTAL"])}
        tope_pts = {"spreads": config.DIF_SOSPECHOSA_SPREAD, "totals": config.DIF_SOSPECHOSA_TOTAL}
        args = (pr["MU_MARGEN"], pr["MU_TOTAL"], pr["SIGMA_MARGEN"], pr["SIGMA_TOTAL"])
        for mercado, lados in (("spreads", ("L", "V")), ("totals", ("Over", "Under"))):
            g = m[(m["EVENTO_ID"] == ev.EVENTO_ID) & (m["MERCADO"] == mercado)].dropna(subset=["LINEA"]).copy()
            if g.empty:
                continue
            if mercado == "spreads":
                g["LADO"] = np.where(g["RESULTADO"].map(config.abreviatura) == ev.LOCAL, "L", "V")
            else:
                g["LADO"] = g["RESULTADO"]

            # Probabilidad justa de Pinnacle en SU línea
            pin = g[g["CASA"] == "pinnacle"]
            justa = {}
            if len(pin) == 2:
                impl = pin.set_index("LADO")["MOMIO"].apply(prob_implicita)
                justa = (impl / impl.sum()).to_dict()
                linea_pin = pin.set_index("LADO")["LINEA"].to_dict()

            for lado in lados:
                ofertas = g[g["LADO"] == lado]
                if ofertas.empty:
                    continue
                probs = [puntos.probs_apuesta(mercado, lado, float(o.LINEA), *args) for o in ofertas.itertuples()]
                evs = [pg * (o.DECIMAL - 1) - pp for (pg, _, pp), o in zip(probs, ofertas.itertuples())]
                k = int(np.argmax(evs))
                mejor = ofertas.iloc[k]
                p_gana, p_push, p_pierde = probs[k]

                # Comparación justa con el mercado: modelo en la línea de Pinnacle (sin contar push)
                pj = justa.get(lado, np.nan)
                if np.isfinite(pj):
                    gp, _, lp = puntos.probs_apuesta(mercado, lado, float(linea_pin[lado]), *args)
                    p_cmp = gp / (gp + lp)
                else:
                    p_cmp = p_gana / (p_gana + p_pierde)
                if (dif_pts[mercado] > tope_pts[mercado]
                        or (mercado == "spreads" and ev.EVENTO_ID in sospechosos)):
                    estado = "SOSPECHOSA"
                else:
                    estado = "VALOR" if evs[k] >= config.UMBRAL_EV_PUNTOS else "-"

                equipo = ev.LOCAL if lado == "L" else ev.VISITA if lado == "V" else None
                texto = f"{equipo} {fmt_linea(mejor['LINEA'])}" if equipo else f"{lado} {mejor['LINEA']:g}"
                filas.append({
                    "EVENTO_ID": ev.EVENTO_ID, "INICIO": ev.INICIO, "PARTIDO": f"{ev.VISITA} @ {ev.LOCAL}",
                    "MERCADO": mercado, "LADO": lado, "LINEA": float(mejor["LINEA"]), "APUESTA": texto,
                    "MODELO_%": round(100 * p_cmp, 1), "MERCADO_%": round(100 * pj, 1),
                    "MEJOR_MOMIO": int(mejor["MOMIO"]), "CASA": mejor["CASA"],
                    "EV_%": round(100 * evs[k], 1), "MONTO": _monto(p_gana, p_pierde, mejor["DECIMAL"], estado),
                    "ESTADO": estado,
                })
    return filas


def linea_pinnacle(m: pd.DataFrame, evento: str, mercado: str, local: str | None = None) -> float:
    """Línea de Pinnacle: hándicap del local (spreads) o total (totals)."""
    g = m[(m["EVENTO_ID"] == evento) & (m["MERCADO"] == mercado) & (m["CASA"] == "pinnacle")]
    if mercado == "spreads":
        g = g[g["EQUIPO"] == local]
    return float(g["LINEA"].iloc[0]) if len(g) else np.nan


def analizar() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Devuelve (tabla de apuestas, eventos, proyección de puntos). Lo usan main() y exportar_web."""
    momios = pd.read_csv(config.MOMIOS / "momios_historico.csv")
    m = partidos_proximos(momios, mercado=None)
    if m.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    m = m[~m["CASA"].isin(config.CASAS_EXCLUIDAS) & m["MERCADO"].isin(["h2h", "spreads", "totals"])].copy()
    m["DECIMAL"] = m["MOMIO"].apply(a_decimal)
    m["EQUIPO"] = m["RESULTADO"].map(lambda r: config.EQUIPOS.get(str(r).strip()))  # None en totales

    eventos = m.drop_duplicates("EVENTO_ID")[["EVENTO_ID", "INICIO", "LOCAL", "VISITA"]].reset_index(drop=True)
    feats = features_futuros(eventos)
    p_local = probabilidades_modelo(eventos, feats)
    proy = proyeccion_puntos(feats)

    # Líneas de Pinnacle (para registrar el pronóstico vs. el mercado)
    proy["PIN_SPREAD_LOCAL"] = [linea_pinnacle(m, e, "spreads", loc)
                                for e, loc in zip(eventos["EVENTO_ID"], eventos["LOCAL"])]
    proy["PIN_TOTAL"] = [linea_pinnacle(m, e, "totals") for e in eventos["EVENTO_ID"]]
    proy["PROB_LOCAL"] = p_local

    ganador = analizar_ganador(m, eventos, p_local)
    sospechosos = {f["EVENTO_ID"] for f in ganador if f["ESTADO"] == "SOSPECHOSA"}
    filas = ganador + analizar_puntos(m, eventos, proy, sospechosos)
    tabla = pd.DataFrame(filas)
    tabla["INICIO (CDMX)"] = tabla["INICIO"].dt.tz_convert("America/Mexico_City").dt.strftime("%d/%m %H:%M")
    orden_mercado = {"h2h": 0, "spreads": 1, "totals": 2}
    tabla = tabla.sort_values(["INICIO", "PARTIDO", "MERCADO"], key=lambda s: s.map(orden_mercado)
                              if s.name == "MERCADO" else s).reset_index(drop=True)
    return tabla, eventos, proy


def registrar(tabla: pd.DataFrame, eventos: pd.DataFrame, proy: pd.DataFrame) -> int:
    ahora = datetime.now(timezone.utc).isoformat(timespec="minutes")

    # 1) Predicciones de ganador (todas, no solo apuestas)
    h2h = tabla[(tabla["MERCADO"] == "h2h")].merge(eventos[["EVENTO_ID", "LOCAL"]], on="EVENTO_ID")
    h2h = h2h[h2h["APUESTA"] == h2h["LOCAL"]]
    pred = pd.DataFrame({
        "REGISTRADA_UTC": ahora, "EVENTO_ID": h2h["EVENTO_ID"],
        "INICIO_UTC": h2h["INICIO"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "PARTIDO": h2h["PARTIDO"],
        "PROB_MODELO_LOCAL": (h2h["MODELO_%"] / 100).round(4),
        "PROB_MERCADO_LOCAL": (h2h["MERCADO_%"] / 100).round(4),
    })
    ruta = config.DATOS / "predicciones.csv"
    pred.to_csv(ruta, mode="a", header=not ruta.exists(), index=False)

    # 2) Predicciones de puntos vs. líneas de Pinnacle
    ev = eventos.set_index("EVENTO_ID")
    pp = pd.DataFrame({
        "REGISTRADA_UTC": ahora, "EVENTO_ID": proy.index,
        "INICIO_UTC": ev.loc[proy.index, "INICIO"].dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy(),
        "PARTIDO": (ev.loc[proy.index, "VISITA"] + " @ " + ev.loc[proy.index, "LOCAL"]).to_numpy(),
        "MU_MARGEN": proy["MU_MARGEN"].round(2).to_numpy(), "MU_TOTAL": proy["MU_TOTAL"].round(2).to_numpy(),
        "PIN_SPREAD_LOCAL": proy["PIN_SPREAD_LOCAL"].to_numpy(), "PIN_TOTAL": proy["PIN_TOTAL"].to_numpy(),
    })
    ruta = config.DATOS / "predicciones_puntos.csv"
    pp.to_csv(ruta, mode="a", header=not ruta.exists(), index=False)

    # 3) Apuestas simuladas (sin duplicar un mismo lado de un mismo mercado)
    nuevas = tabla[tabla["ESTADO"] == "VALOR"].drop(columns="INICIO").copy()
    if nuevas.empty:
        return 0
    nuevas.insert(0, "REGISTRADA_UTC", ahora)
    reg = config.DATOS / "apuestas_simuladas.csv"
    if reg.exists():
        previas = pd.read_csv(reg)
        if "MERCADO" not in previas:
            previas["MERCADO"] = "h2h"
        if "LADO" not in previas:
            previas["LADO"] = previas["APUESTA"]
        previas["MERCADO"] = previas["MERCADO"].fillna("h2h")
        previas["LADO"] = previas["LADO"].fillna(previas["APUESTA"])
        clave = set(zip(previas["EVENTO_ID"], previas["MERCADO"], previas["LADO"]))
        nuevas = nuevas[[(e, mk, l) not in clave
                         for e, mk, l in zip(nuevas["EVENTO_ID"], nuevas["MERCADO"], nuevas["LADO"])]]
        todo = pd.concat([previas, nuevas], ignore_index=True)  # reescribe: permite columnas nuevas
    else:
        todo = nuevas
    todo.to_csv(reg, index=False)
    return len(nuevas)


def registrar_parlay(tabla: pd.DataFrame) -> bool:
    """
    Registra como máximo UN parlay simulado por día (hora CDMX): las PARLAY_PATAS
    apuestas con más ganancia esperada, de partidos distintos. La probabilidad de cada
    pata se deduce de su EV (p = (1+EV)/decimal), así el parlay es consistente con ellas.
    """
    import json
    valor = tabla[tabla["ESTADO"] == "VALOR"].copy()
    if valor.empty:
        return False
    valor["DECIMAL"] = valor["MEJOR_MOMIO"].apply(a_decimal)
    valor["P_PATA"] = (1 + valor["EV_%"] / 100) / valor["DECIMAL"]
    valor = valor[valor["P_PATA"] >= config.PARLAY_PROB_MIN_PATA]
    valor = valor.sort_values("EV_%", ascending=False).drop_duplicates("EVENTO_ID")
    n = config.PARLAY_PATAS
    if len(valor) < n:
        return False
    patas = valor.head(n)
    dec = float(np.prod(patas["DECIMAL"]))
    p = float(np.prod((1 + patas["EV_%"] / 100) / patas["DECIMAL"]))
    ev = p * dec - 1
    if ev < config.UMBRAL_EV_PARLAY:
        return False
    hoy = pd.Timestamp.now(tz="America/Mexico_City").strftime("%Y-%m-%d")
    reg = config.DATOS / "parlays_simulados.csv"
    previos = pd.read_csv(reg) if reg.exists() else pd.DataFrame(columns=["DIA"])
    if hoy in set(previos["DIA"].astype(str)):
        return False
    k = (p * (dec - 1) - (1 - p)) / (dec - 1)
    monto = round(config.BANKROLL * min(max(k, 0) * config.KELLY_FRACCION, config.TOPE_APUESTA / 2), 0)
    if monto <= 0:
        return False
    lista = [{"EVENTO_ID": r["EVENTO_ID"], "PARTIDO": r["PARTIDO"], "MERCADO": r["MERCADO"], "LADO": r["LADO"],
              "LINEA": None if pd.isna(r["LINEA"]) else float(r["LINEA"]), "APUESTA": r["APUESTA"],
              "MOMIO": int(r["MEJOR_MOMIO"]), "INICIO (CDMX)": str(r.get("INICIO (CDMX)", ""))}
             for _, r in patas.iterrows()]
    fila = pd.DataFrame([{
        "DIA": hoy, "REGISTRADA_UTC": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "PATAS": json.dumps(lista, ensure_ascii=False), "N": n, "DECIMAL": round(dec, 4),
        "PROB_%": round(100 * p, 1), "EV_%": round(100 * ev, 1), "MONTO": monto,
        "INICIO (CDMX)": min(str(d["INICIO (CDMX)"]) for d in lista),
    }])
    pd.concat([previos, fila], ignore_index=True).to_csv(reg, index=False)
    return True


def main():
    tabla, eventos, proy = analizar()
    if tabla.empty:
        print("No hay partidos próximos en el último snapshot. Corre primero: python src/descargar_momios.py")
        return

    print(f"Bankroll de práctica: ${config.BANKROLL:,.0f} · Kelly {config.KELLY_FRACCION:.0%} · "
          f"tope {config.TOPE_APUESTA:.0%} · umbral EV {config.UMBRAL_EV:.0%}\n")
    print("Proyección del modelo:")
    for e in eventos.itertuples(index=False):
        pr = proy.loc[e.EVENTO_ID]
        fav, marg = (e.LOCAL, pr["MU_MARGEN"]) if pr["MU_MARGEN"] >= 0 else (e.VISITA, -pr["MU_MARGEN"])
        print(f"  {e.VISITA} @ {e.LOCAL}: {fav} por {marg:.1f} (Pinnacle: {e.LOCAL} {fmt_linea(pr['PIN_SPREAD_LOCAL'])})"
              f" · total {pr['MU_TOTAL']:.1f} (Pinnacle: {pr['PIN_TOTAL']:g})")

    cols = ["INICIO (CDMX)", "PARTIDO", "MERCADO", "APUESTA", "MODELO_%", "MERCADO_%",
            "MEJOR_MOMIO", "CASA", "EV_%", "MONTO", "ESTADO"]
    print()
    print(tabla[cols].to_string(index=False))

    n = registrar(tabla, eventos, proy)
    if n:
        print(f"\n{n} apuesta(s) SIMULADA(s) nuevas registradas en apuestas_simuladas.csv")
    else:
        print("\nNinguna apuesta nueva pasa los filtros. (Es normal: la mayoría de los días no hay valor.)")
    if registrar_parlay(tabla):
        print(f"Parlay simulado de {config.PARLAY_PATAS} registrado en parlays_simulados.csv")
    sosp = (tabla["ESTADO"] == "SOSPECHOSA").sum()
    if sosp:
        print(f"{sosp} lado(s) SOSPECHOSOS: el modelo difiere >{config.DIF_SOSPECHOSA:.0%} del mercado.")


if __name__ == "__main__":
    main()
