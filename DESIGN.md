# DESIGN.md — NBA · Probabilidades

Estilo: app deportiva estándar (referencias de calidad: The Athletic, ESPN, Action Network). Modo Operate, móvil primero.

## Color
Sigue el tema del sistema (claro/oscuro) con tokens en `:root`.
- Claro: fondo `#f4f5f7`, superficie `#ffffff`, texto `#111418`, secundario `#545b68`, acento `#1652f0`.
- Oscuro: fondo `#0e1013`, superficie `#171a1f`, texto `#eef0f3`, secundario `#a6adb9`, acento `#7aa2ff`.
- Semánticos: verde `--pos` = conviene / ganó; rojo `--neg` = perdió / lesión; ámbar `--warn` = sospechosa / alerta.
- Estrategia restringida: neutros + un acento azul. El verde solo marca dinero/valor.

## Tipografía
- Texto: pila del sistema (SF / Segoe / Roboto), 15px, números tabulares.
- Cifras (momios, %, KPIs, Elo, abreviaturas): Barlow Semi Condensed 600–700.

## Componentes
- `.caja`: superficie con borde 1px, radio 14px, sombra suave solo en claro.
- `.eq`: escudo circular con la abreviatura del equipo (sin logos).
- `.precio-btn`: botón tipo casa de apuestas con el momio mínimo (cifra protagonista).
- Tarjeta de partido: encabezado, barra de probabilidad de victoria (favorito en acento), filas tipo marcador desplegables, pronóstico, hándicap y totales.
- `.stats`: tira de 4 KPIs divididos en una sola caja.
- Barra de pestañas inferior sólida; activa en acento con indicador superior.

## Movimiento
Solo una entrada suave al cambiar de pestaña (0.28s, ease-out) y la flecha de los desplegables. Respeta reduced-motion.
