# Guía de uso diario

Proyecto por fases: **Datos** → Modelo base → Momios/EV → Backtesting → Bankroll → Interfaz.

## Fase 1 · Datos (esta entrega)

### 1. Instalar (una sola vez)
```bash
cd nba-apuestas
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Descargar partidos (2023-24 a la actual)
```bash
python src/descargar_partidos.py
python src/limpiar_partidos.py
```
Resultado: `datos/procesados/partidos.csv`, con una fila por partido.
Para actualizar después solo la temporada en curso: `python src/descargar_partidos.py --actual`

> Si stats.nba.com tarda o te da error de timeout, vuelve a correrlo. A veces bloquea redes de
> oficinas/escuelas o VPNs; desde el internet de casa suele funcionar.

### 3. Empezar a guardar momios (hazlo hoy)
1. Saca tu clave gratis en https://the-odds-api.com
2. Copia `.env.example` como `.env` y pega tu clave.
3. Corre `python src/descargar_momios.py` **dos veces al día** (mañana y justo antes de los partidos).
   El de la noche te da la línea de cierre, que vamos a usar para medir el CLV.

## Fase 2 · Elo  ·  Fase 3 · Modelo y valor

```
..\.venv\Scripts\python src\elo.py           (recalcula ratings; correr tras actualizar partidos)
..\.venv\Scripts\python src\modelo.py        (reentrena el modelo)
..\.venv\Scripts\python src\puntos.py        (modelo de spreads y totales)
..\.venv\Scripts\python src\predecir_hoy.py  (Elo vs. mercado)
..\.venv\Scripts\python src\valor.py         (EV, monto sugerido y registro de apuestas simuladas)
```

### Rutina diaria: doble clic en `rutina.bat`
Hace todo lo de abajo en orden y al final sube los datos a GitHub: la página se actualiza sola.

Si prefieres hacerlo a mano:
1. `python src\descargar_partidos.py --actual`, `python src\limpiar_partidos.py`,
   `python src\descargar_jugadores.py --actual` y `python src\bajas.py`
2. `python src\elo.py`, `python src\modelo.py` y `python src\puntos.py`
3. `python src\descargar_momios.py` y `python src\valor.py`
4. Antes de los partidos, otra vez `python src\descargar_momios.py` (línea de cierre)
5. Al día siguiente: `python src\liquidar.py` (resultados, ROI, CLV y modelo vs. mercado)

Parámetros de apuesta (bankroll, Kelly, umbral EV) en `src\config.py`.
Todo es SIMULADO: se registra en `datos\apuestas_simuladas.csv`.

## Página web
Página: https://chrisvirrueta3.github.io/nba-modelo-probabilidades

Se actualiza sola: al final de `rutina.bat` los datos se suben a GitHub y una
GitHub Action publica la carpeta `web` en GitHub Pages (gratis, sin límite).

Primera vez: doble clic en `configurar_github.bat` para conectar la carpeta con
GitHub. Si se abre una ventana para iniciar sesión en GitHub, acéptala.

## Estructura
```
src/config.py              temporadas, rutas, equipos
src/descargar_partidos.py  baja resultados de nba_api
src/limpiar_partidos.py    1 fila por partido + validaciones
src/descargar_momios.py    guarda snapshots de momios
src/elo.py                 modelo Elo + validación
src/caracteristicas.py     descanso, B2B, net rating
src/modelo.py              regresión logística vs. boosting
src/descargar_jugadores.py estadísticas por jugador (nba_api)
src/bajas.py               valor de cada jugador y bajas históricas
src/lesiones.py            reporte de lesiones de ESPN -> bajas esperadas
src/valor.py               EV, Kelly y paper trading
src/liquidar.py            resultados, ROI, CLV
src/exportar_web.py        genera web/datos.json
web/                       página (index.html + datos.json)
datos/                     (no se sube a GitHub)
```
