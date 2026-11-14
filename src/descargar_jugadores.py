"""
LESIONES · Paso 1: descargar estadísticas de cada JUGADOR por partido.

Con esto sabemos quién jugó cada partido y cuánto aporta cada jugador,
para medir qué tanto le pega a un equipo que le falte alguien.

Uso:
    python src/descargar_jugadores.py            # todas las temporadas
    python src/descargar_jugadores.py --actual   # solo la temporada en curso
"""
import argparse
import time

from nba_api.stats.endpoints import leaguegamelog

import config

INTENTOS = 4


def descargar(temporada: str):
    for intento in range(1, INTENTOS + 1):
        try:
            r = leaguegamelog.LeagueGameLog(season=temporada, season_type_all_star="Regular Season",
                                            player_or_team_abbreviation="P", timeout=90)
            df = r.get_data_frames()[0]
            df["TEMPORADA"] = temporada
            return df
        except Exception as e:  # noqa: BLE001
            print(f"  intento {intento}/{INTENTOS} falló ({e.__class__.__name__}). Reintento en {5 * intento}s...")
            time.sleep(5 * intento)
    raise RuntimeError(f"No se pudo descargar {temporada}. Prueba más tarde.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--actual", action="store_true")
    args = parser.parse_args()
    temporadas = [config.TEMPORADA_ACTUAL] if args.actual else config.TEMPORADAS
    for t in temporadas:
        print(f"Descargando jugadores {t}...")
        df = descargar(t)
        ruta = config.CRUDOS / f"jugadores_{t}.csv"
        df.to_csv(ruta, index=False)
        print(f"  {len(df)} filas -> {ruta.name}")
        time.sleep(config.PAUSA_SEGUNDOS)
    print("\nListo.")


if __name__ == "__main__":
    main()
