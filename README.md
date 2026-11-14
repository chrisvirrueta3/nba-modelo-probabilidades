# 🏀 NBA · Modelo de probabilidades

> **EN:** An end-to-end NBA win-probability model. It ingests official box scores, builds an Elo rating system, adds rest, form and injury features, and compares its probabilities against the betting market (Pinnacle's no-vig line) to find positive expected-value spots. Validation is strictly out-of-sample (trained on 2023-25, tested on 1,413 unseen games). Performance is tracked through Closing Line Value and paper trading, and everything is published as a mobile dashboard. Built in Python (pandas, scikit-learn) with a static front end on Netlify.

**Página en vivo:** [nba-modelo-probabilidades.netlify.app](https://nba-modelo-probabilidades.netlify.app)

Proyecto personal de ciencia de datos aplicada a mercados deportivos. La pregunta de fondo es económica: **¿se puede estimar la probabilidad de un partido mejor que un mercado de apuestas?** Si no, ¿qué tan cerca se queda un modelo construido solo con datos públicos?

<p align="center"><img src="docs/img/web.png" width="360" alt="Vista de un partido en la página: probabilidad del modelo vs. mercado, lesiones y valor esperado"></p>

---

## Resultados

Todo se mide en **datos de prueba que el modelo nunca vio**: se entrena con 2023-24 y 2024-25 y se evalúa en 2025-26 y en lo que va de 2026-27 (1,413 partidos).

<p align="center"><img src="docs/img/comparacion.png" width="640" alt="Log loss por modelo"></p>

| Modelo | Acierto | Brier | Log loss |
|---|---|---|---|
| Moneda al aire | — | 0.250 | 0.693 |
| Siempre gana el local | 55.1% | 0.248 | 0.688 |
| Elo | 68.9% | 0.204 | 0.595 |
| Elo + descanso + forma | 68.2% | 0.204 | 0.594 |
| **Modelo final (+ lesiones)** | **68.1%** | **0.201** | **0.587** |

**Hallazgos:**
- **El Elo hace casi todo el trabajo.** Descanso, back-to-backs y forma reciente casi no agregan nada por encima de él.
- **Las lesiones son la mejora más grande.** Agregar el valor de los jugadores que faltan bajó el log loss más que todas las demás variables juntas.
- **Un modelo más complejo no siempre es mejor.** Gradient Boosting salió *peor* que una regresión logística, porque con unos 2,000 partidos de entrenamiento se sobreajusta.
- **El acierto engaña.** El modelo final acierta un poco menos que el Elo, pero sus probabilidades son mejores. Para apostar importa la probabilidad, no el acierto.

<p align="center">
  <img src="docs/img/calibracion.png" width="400" alt="Curva de calibración">
  <img src="docs/img/pesos.png" width="480" alt="Peso de cada variable">
</p>

---

## Metodología

### 1. Datos
- **Resultados y box scores** de cada partido y de cada jugador desde 2023-24, de la API oficial de la NBA (`nba_api`).
- **Momios** de más de 30 casas de apuestas ([The Odds API](https://the-odds-api.com)). Se guarda una "foto" diaria, incluida la línea de cierre.
- **Reporte de lesiones** diario de ESPN.
- Los partidos en sede neutral (Ciudad de México, Europa, NBA Cup) se marcan aparte para no darles ventaja de local.

### 2. Elo
Cada equipo tiene una calificación que se actualiza después de cada partido según el resultado, el margen y la localía (fórmula estilo FiveThirtyEight). Los parámetros (K, ventaja de local y reversión a la media entre temporadas) se ajustan **solo** con 2024-25 y se prueban en temporadas posteriores. La probabilidad de cada partido se calcula *antes* de actualizar con su resultado, así que no hay fuga de información.

### 3. Variables adicionales
| Variable | Idea |
|---|---|
| Net rating (temporada y últimos 10) | Puntos por cada 100 posesiones; se encoge hacia 0 al inicio de la temporada |
| Descanso, back-to-back, 3 juegos en 4 noches | Cansancio |
| **Bajas** | Suma del valor (Game Score promedio) de los jugadores de la rotación que no juegan |

Para partidos futuros, las bajas se calculan con el reporte de lesiones: cada baja se pondera por la probabilidad de que el jugador juegue (fuera = 0%, en duda = 50%…).

### 4. Del modelo a la decisión
1. **Probabilidad justa del mercado:** se toma el momio de Pinnacle y se le quita el margen de la casa.
2. **Valor esperado:** `EV = p_modelo × momio_decimal − 1`, usando el mejor momio disponible.
3. **Filtros:** solo se marca una apuesta con EV ≥ 3%. Si el modelo difiere del mercado por más de 10 puntos, se marca como *sospechosa* y no se apuesta, porque casi siempre significa que el mercado sabe algo que el modelo no.
4. **Monto:** Kelly fraccional (¼) con tope de 2% del bankroll.

### 5. Evaluación en vivo
- **Paper trading:** cada apuesta sugerida se registra y se liquida automáticamente.
- **CLV (Closing Line Value):** compara el momio tomado contra la probabilidad justa de cierre. Es la métrica más confiable de habilidad, porque el ROI necesita cientos de apuestas para dejar de ser ruido.
- **Modelo vs. mercado (Brier):** en *todos* los partidos predichos, no solo en los apostados.

---

## Estructura

```
src/
  config.py              parámetros, rutas y equipos
  descargar_partidos.py  box scores por equipo (nba_api)
  limpiar_partidos.py    1 fila por partido + validaciones
  descargar_jugadores.py box scores por jugador
  bajas.py               valor de cada jugador y bajas históricas
  elo.py                 modelo Elo + búsqueda de parámetros + validación
  caracteristicas.py     variables sin fuga de información
  modelo.py              regresión logística vs. gradient boosting
  descargar_momios.py    snapshots de momios (The Odds API)
  lesiones.py            reporte de ESPN -> bajas esperadas
  valor.py               EV, Kelly y registro de apuestas simuladas
  liquidar.py            resultados, ROI, CLV y modelo vs. mercado
  exportar_web.py        genera web/datos.json
  graficas.py            gráficas de este README
web/                     página estática (HTML/CSS/JS, sin frameworks)
rutina.bat               rutina diaria completa en un doble clic (Windows)
```

## Cómo correrlo

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt

# clave gratuita de https://the-odds-api.com
copy .env.example .env           # y pega tu clave en .env

python src/descargar_partidos.py && python src/limpiar_partidos.py
python src/descargar_jugadores.py && python src/bajas.py
python src/elo.py && python src/modelo.py
python src/descargar_momios.py && python src/valor.py
```

Rutina diaria: `rutina.bat`, o los mismos comandos con `--actual`, y luego `liquidar.py` y `exportar_web.py`. Guía paso a paso en [docs/GUIA.md](docs/GUIA.md).

---

## Limitaciones

- **Lesiones de último minuto:** en el histórico se sabe quién no jugó al final. En vivo, el reporte es incierto, así que el efecto real es menor que en el backtest.
- **Game Score** es una medida simple del valor de un jugador y no captura bien la defensa.
- **Sin momios históricos gratuitos:** la comparación contra el mercado se hace con los momios que el proyecto guarda desde noviembre de 2026.
- **Solo moneyline** por ahora (sin spreads ni totales).

## Aviso

Proyecto educativo y de análisis de datos. **No es una recomendación de apuestas.** Los mercados de apuestas son muy eficientes y la mayoría de los modelos públicos no les gana a largo plazo. Las apuestas que aparecen aquí son simuladas.

---

Hecho por **Christopher Virrueta**, estudiante de Economía en la UMSNH (Morelia, México).
