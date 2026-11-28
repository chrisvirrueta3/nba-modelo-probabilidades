# NBA Apuestas · Modelo de probabilidades

Proyecto por fases: **Datos** → Modelo base → Momios/EV → Backtesting → Bankroll → Interfaz.

## Fase 1 · Datos (esta entrega)

### 1\. Instalar (una sola vez)

```bash
cd nba-apuestas
python -m venv .venv
# Windows:
.venv\\\\Scripts\\\\activate
# Mac/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

### 2\. Descargar partidos (2023-24 a la actual)

```bash
python src/descargar\\\_partidos.py
python src/limpiar\\\_partidos.py
```

Resultado: `datos/procesados/partidos.csv`, con una fila por partido.
Para actualizar después solo la temporada en curso: `python src/descargar\\\_partidos.py --actual`

> Si stats.nba.com tarda o te da error de timeout, vuelve a correrlo. A veces bloquea redes de
> oficinas/escuelas o VPNs; desde el internet de casa suele funcionar.

### 3\. Empezar a guardar momios (hazlo hoy)

1. Saca tu clave gratis en https://the-odds-api.com
2. Copia `.env.example` como `.env` y pega tu clave.
3. Corre `python src/descargar\\\_momios.py` **dos veces al día** (mañana y justo antes de los partidos).
El de la noche te da la línea de cierre, que vamos a usar para medir el CLV.

## Estructura

```
src/config.py              temporadas, rutas, equipos
src/descargar\\\_partidos.py  baja resultados de nba\\\_api
src/limpiar\\\_partidos.py    1 fila por partido + validaciones
src/descargar\\\_momios.py    guarda snapshots de momios
datos/                     (no se sube a GitHub)
```

