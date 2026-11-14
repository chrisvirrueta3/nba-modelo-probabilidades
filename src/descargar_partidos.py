"""
FASE 1 · Paso 1: descargar resultados históricos de la NBA.

Usa nba_api (gratis, datos oficiales de stats.nba.com). Descarga el
"game log" por equipo de cada temporada: una fila por equipo por partido,
con puntos, tiros, rebotes, pérdidas, etc.

Uso:
    python src/descargar_partidos.py              # todas las temporadas de config
    python src/descargar_partidos.py --actual     # solo la temporada en curso (para actualizar)
"""
import argparse
import time

import pandas as pd
from nba_api.stats.endpoints import leaguegamelog

import config

INTENTOS = 4  # stats.nba.com a veces tarda o corta la conexión


def descargar_temporada(temporada: str, tipo: str = "Regular Season") -> pd.DataFrame:
    """Descarga el game log de una temporada, con reintentos."""
    for intento in range(1, INTENTOS + 1):
        try:
            respuesta = leaguegamelog.LeagueGameLog(
                season=temporada,
                season_type_all_star=tipo,
                player_or_team_abbreviation="T",  # T = equipos
                timeout=60,
            )
            df = respuesta.get_data_frames()[0]
            df["TEMPORADA"] = temporada
            df["TIPO"] = tipo
            return df
        except Exception as e:  # noqa: BLE001
            espera = 5 * intento
            print(f"  intento {intento}/{INTENTOS} falló ({e.__class__.__name__}). Reintento en {espera}s...")
            time.sleep(espera)
    raise RuntimeError(f"No se pudo descargar {temporada} ({tipo}). Prueba más tarde o con otra red.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--actual", action="store_true", help="solo la temporada en curso")
    parser.add_argument("--playoffs", action="store_true", help="incluir playoffs")
    args = parser.parse_args()

    temporadas = [config.TEMPORADA_ACTUAL] if args.actual else config.TEMPORADAS
    tipos = ["Regular Season"] + (["Playoffs"] if args.playoffs else [])

    for temporada in temporadas:
        for tipo in tipos:
            print(f"Descargando {temporada} · {tipo}...")
            df = descargar_temporada(temporada, tipo)
            if df.empty:
                print("  (sin partidos todavía)")
                continue
            sufijo = "rs" if tipo == "Regular Season" else "po"
            ruta = config.CRUDOS / f"gamelog_{temporada}_{sufijo}.csv"
            df.to_csv(ruta, index=False)
            print(f"  {len(df)} filas -> {ruta.name}")
            time.sleep(config.PAUSA_SEGUNDOS)

    print("\nListo. Ahora corre: python src/limpiar_partidos.py")


if __name__ == "__main__":
    main()
