"""
Configuración central del proyecto.
Todo lo que quieras cambiar (temporadas, rutas, casas de apuestas) se cambia aquí.
"""
from pathlib import Path

# ---------- Rutas ----------
RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"
CRUDOS = DATOS / "crudos"          # tal cual llegan de la API
PROCESADOS = DATOS / "procesados"  # limpios, listos para el modelo
MOMIOS = DATOS / "momios"          # snapshots de momios

for carpeta in (CRUDOS, PROCESADOS, MOMIOS):
    carpeta.mkdir(parents=True, exist_ok=True)

# ---------- Temporadas ----------
# 3 temporadas completas + la actual (2026-27, en curso).
TEMPORADAS = ["2023-24", "2024-25", "2025-26", "2026-27"]
TEMPORADA_ACTUAL = "2026-27"

# Pausa entre llamadas a stats.nba.com (si vas muy rápido te bloquean).
PAUSA_SEGUNDOS = 1.5

# ---------- Momios (The Odds API) ----------
DEPORTE_ODDS = "basketball_nba"
# "us" = casas de EE.UU. (DraftKings, FanDuel...), "eu" incluye Pinnacle,
# la casa más "afilada": su línea es la mejor referencia de probabilidad justa.
REGIONES_ODDS = "us,eu"
MERCADOS_ODDS = "h2h,spreads,totals"   # moneyline, spread, totales

# ---------- Equipos ----------
# Nombre completo -> abreviatura. Las fuentes escriben distinto algunos nombres
# (ej. "LA Clippers" vs "Los Angeles Clippers"), por eso hay alias.
EQUIPOS = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "LA Clippers": "LAC", "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM", "Miami Heat": "MIA", "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP", "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR", "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}


def abreviatura(nombre: str) -> str:
    """Devuelve la abreviatura de un equipo o lanza error si no se reconoce."""
    try:
        return EQUIPOS[nombre.strip()]
    except KeyError:
        raise ValueError(f"Equipo no reconocido: '{nombre}'. Agrégalo a EQUIPOS en config.py")

# ---------- Apuestas (fase 3) ----------
BANKROLL = 1000            # bankroll de PRÁCTICA (simulado), en pesos
KELLY_FRACCION = 0.25      # 1/4 de Kelly: menos varianza que Kelly completo
TOPE_APUESTA = 0.02        # nunca más del 2% del bankroll en una apuesta
UMBRAL_EV = 0.03           # solo marcar apuestas con EV >= 3%
DIF_SOSPECHOSA = 0.10      # si el modelo difiere >10 pts del mercado, desconfiar
# Bolsas de apuestas: su momio no incluye la comisión, así que lo excluimos
CASAS_EXCLUIDAS = ["betfair_ex_eu", "betfair_ex_uk", "betfair_ex_au", "matchbook"]

# ---------- Spreads y totales ----------
# El modelo de puntos es menos preciso que las líneas del mercado, así que
# exigimos más ventaja y desconfiamos antes que en el mercado de ganador.
UMBRAL_EV_PUNTOS = 0.05         # EV mínimo para marcar valor en spreads/totales
RESERVA_CREDITOS = 30           # con menos créditos ya no se bajan momios (se guardan para los resultados)
MARGEN_JUSTO = 0.02             # 'precio justo': Draftea debe pagar al menos 2% más que el precio sin comisión de Pinnacle
PESO_MODELO = 0.5               # la probabilidad para apostar mezcla 50% modelo + 50% Pinnacle (el mercado es muy preciso)
MOMIO_TIPICO = True             # simular con el momio típico (mediana de las casas), no con el mejor: más realista para Draftea
MOMIO_MAX_GANADOR = 300         # en "ganador" no se apuestan no favoritos que paguen más de +300 (ahí el modelo falla más)
PARLAYS_ACTIVOS = False         # parlays simulados en pausa (los errores se multiplican; iban 0 de 4)
UMBRAL_EV_PARLAY = 0.10         # EV mínimo de un parlay simulado (los errores del modelo se multiplican)
PARLAY_PATAS = 2                # patas del parlay simulado diario (partidos distintos)
PARLAY_PROB_MIN_PATA = 0.40     # en parlays solo patas con 40%+ de probabilidad (nada de lotería)
DIF_SOSPECHOSA_SPREAD = 3.0     # puntos de diferencia vs. la línea de Pinnacle
DIF_SOSPECHOSA_TOTAL = 5.0
