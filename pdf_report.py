# -*- coding: utf-8 -*-
"""
pdf_report.py - Generador de documentacion PDF completa del sistema ParraCorp.
"""
import io
from datetime import datetime, timezone
from fpdf import FPDF


class ParraPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, "ParraCorp Trading System - Documentacion Tecnica", align="R")
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Pagina {self.page_no()}/{{nb}}", align="C")

    def title_section(self, text):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(38, 166, 154)  # Green
        self.cell(0, 12, text, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(38, 166, 154)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def subtitle(self, text):
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(79, 195, 247)  # Cyan
        self.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(50, 50, 50)
        # Replace chars not supported by Helvetica
        safe = text.encode("latin-1", "replace").decode("latin-1")
        self.multi_cell(0, 5, safe)
        self.ln(2)

    def bullet(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(50, 50, 50)
        safe = text.encode("latin-1", "replace").decode("latin-1")
        self.set_x(self.l_margin)
        self.cell(6, 5, "-")
        self.multi_cell(0, 5, safe)

    def code_block(self, text):
        self.set_font("Courier", "", 8)
        self.set_fill_color(240, 240, 240)
        self.set_text_color(30, 30, 30)
        safe = text.encode("latin-1", "replace").decode("latin-1")
        self.set_x(self.l_margin)
        self.multi_cell(0, 4, safe, fill=True)
        self.ln(2)

    def table_row(self, cols, widths, bold=False, fill=False):
        self.set_font("Helvetica", "B" if bold else "", 9)
        if fill:
            self.set_fill_color(230, 245, 243)
        self.set_text_color(30, 30, 30)
        # Reset x to left margin to avoid drift
        self.set_x(self.l_margin)
        for i, col in enumerate(cols):
            txt = str(col).encode("latin-1", "replace").decode("latin-1")
            # Truncate text that doesn't fit in the cell
            max_w = widths[i] - 2
            if max_w < 2:
                max_w = widths[i]
            while self.get_string_width(txt) > max_w and len(txt) > 1:
                txt = txt[:-1]
            try:
                self.cell(widths[i], 6, txt, border=1, fill=fill)
            except Exception:
                self.cell(widths[i], 6, "", border=1, fill=fill)
        self.ln()


def generate_pdf():
    """Genera el PDF completo de documentacion del sistema."""
    pdf = ParraPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # =========================================================================
    # PORTADA
    # =========================================================================
    pdf.add_page()
    pdf.ln(40)
    pdf.set_font("Helvetica", "B", 32)
    pdf.set_text_color(38, 166, 154)
    pdf.cell(0, 15, "ParraCorp Trading", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 18)
    pdf.set_text_color(79, 195, 247)
    pdf.cell(0, 10, "Sistema de Senales IA v3.1", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, "Documentacion Tecnica Completa", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(30)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 6, "Motor: Python/Flask en Railway", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "App: Android Kotlin/Jetpack Compose", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "IA: Groq (Llama 3.3 70B) + Google Gemini 2.5 Flash", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Notificaciones: FCM + Telegram + WhatsApp", align="C", new_x="LMARGIN", new_y="NEXT")

    # =========================================================================
    # 1. ARQUITECTURA GENERAL
    # =========================================================================
    pdf.add_page()
    pdf.title_section("1. ARQUITECTURA GENERAL")

    pdf.subtitle("1.1 Componentes del Sistema")
    pdf.body_text(
        "El sistema ParraCorp consta de dos componentes principales que se comunican "
        "via HTTP REST API:"
    )
    pdf.bullet("Backend (Motor): Servidor Python/Flask desplegado en Railway. Ejecuta el analisis "
               "tecnico, las llamadas a IA, gestion de senales y notificaciones push.")
    pdf.bullet("App Android: Aplicacion Kotlin con Jetpack Compose. Muestra senales, graficos, "
               "ranking, historial, analytics y configuracion. Consulta al backend cada 5 segundos.")
    pdf.bullet("Firebase Cloud Messaging (FCM): Notificaciones push para senales BUY/SELL, cierres "
               "y alertas de precio. Funcionan aunque la app este cerrada.")
    pdf.bullet("TradingView WebSocket: Datos de mercado en tiempo real (precios OHLCV, quotes tick-by-tick) "
               "via conexion directa a wss://data.tradingview.com.")
    pdf.bullet("Telegram Bot: Senales con graficos (capturas con zonas TP/SL), cierres con PnL y resumen diario.")
    pdf.bullet("WhatsApp Bot: wa_service.js (Node.js + whatsapp-web.js) envia senales con imagenes al grupo.")
    pdf.bullet("Graficos de Senal: Generados con mplfinance (velas reales + zonas TP/SL + flecha de direccion).")

    pdf.subtitle("1.2 Flujo de Datos")
    pdf.body_text(
        "TradingView WS --> data_feed.py (snapshot con indicadores)\n"
        "                --> brain.py (filtros + Groq + Gemini)\n"
        "                --> signals.py (gestion de ops)\n"
        "                --> chart_gen.py (grafico con zonas TP/SL)\n"
        "                --> push.py + telegram_bot.py + whatsapp_bot.py\n"
        "                --> App Android (polling cada 5s)"
    )

    # =========================================================================
    # 2. PIPELINE DE ANALISIS IA
    # =========================================================================
    pdf.add_page()
    pdf.title_section("2. PIPELINE DE ANALISIS IA")

    pdf.subtitle("2.1 Ciclo de Analisis")
    pdf.body_text(
        "El motor ejecuta un ciclo de analisis cada vez que se cierra una vela en cualquier "
        "par/temporalidad de la watchlist. El ciclo completo para cada par es:"
    )
    pdf.bullet("1. SNAPSHOT: Recoger datos OHLCV + calcular 30+ indicadores tecnicos con pandas-ta")
    pdf.bullet("2. FILTRO DE SEGURIDAD (Hard Rules): Reglas programadas que bloquean ANTES de gastar llamadas IA")
    pdf.bullet("3. FILTRO DE CONFLUENCIA: Minimo 3/4 indicadores basicos alineados (EMA9/20, SuperTrend, MACD, RSI)")
    pdf.bullet("4. GROQ (Llama 3.3 70B): Analisis tecnico libre. Recibe datos puros y decide BUY/SELL/WAIT independientemente")
    pdf.bullet("5. GEMINI (2.5 Flash): Analisis paralelo. Recibe indicadores + noticias. Decide independientemente")
    pdf.bullet("6. CONSENSO 2/2: Solo opera si AMBAS IAs coinciden en BUY o SELL. Stats es solo referencia")

    pdf.subtitle("2.2 Filtros de Seguridad (Hard Rules)")
    pdf.body_text("Antes de consultar IA, estas reglas bloquean automaticamente:")
    pdf.bullet("Festivo bancario (Navidad, Ano Nuevo, etc.) - baja liquidez")
    pdf.bullet("Evento de alto impacto proximo (NFP, FOMC, IPC) - 30 min antes")
    pdf.bullet("Sesion de baja calidad (Off-hours, quality <= 1) - excepto crypto")
    pdf.bullet("Fin de semana para forex/metales/indices")
    pdf.bullet("Volatilidad extrema (ATR > 5%)")
    pdf.bullet("Modo conservador activo (3+ fallos consecutivos)")
    pdf.bullet("Cierre de mercado proximo si evitar swap esta activado")
    pdf.bullet("Correlacion con operacion abierta (anti-duplicados)")
    pdf.bullet("ADX < 18 (sin tendencia)")
    pdf.bullet("Confluencia < 3/4 indicadores alineados")

    pdf.subtitle("2.3 Modelos de IA")
    w = [50, 70, 70]
    pdf.table_row(["Modelo", "Funcion", "Caracteristicas"], w, bold=True, fill=True)
    pdf.table_row(["Groq Llama 3.3 70B", "Analisis tecnico rapido", "Respuesta <2s, JSON directo"], w)
    pdf.table_row(["Gemini 2.5 Flash", "Validador final", "Contexto macro+noticias, veta malas senales"], w)
    pdf.ln(4)
    pdf.body_text(
        "Groq tiene rotacion de 4 API keys. Gemini tiene 4 keys con rotacion automatica en 429. "
        "Si alguna IA falla (error API), NO se opera. Se requieren ambas respuestas para consenso."
    )

    # =========================================================================
    # 3. INDICADORES TECNICOS
    # =========================================================================
    pdf.add_page()
    pdf.title_section("3. INDICADORES TECNICOS")
    pdf.body_text("El sistema calcula los siguientes indicadores sobre cada snapshot de velas:")

    w2 = [45, 50, 95]
    pdf.table_row(["Indicador", "Variable", "Descripcion"], w2, bold=True, fill=True)
    indicators = [
        ("RSI (14)", "rsi", "Relative Strength Index - sobrecompra/sobreventa"),
        ("ADX (14)", "adx", "Average Directional Index - fuerza de tendencia"),
        ("+DI / -DI", "di_plus, di_minus", "Directional Indicators - direccion de tendencia"),
        ("MACD", "macd_hist", "Histograma MACD - momentum"),
        ("SuperTrend", "supertrend", "UP/DOWN - tendencia principal"),
        ("EMA 9/20/50/200", "ema9..ema200", "Medias exponenciales - niveles dinamicos"),
        ("Bollinger Bands", "bb_upper/lower", "Bandas de volatilidad"),
        ("Squeeze", "squeeze", "Bollinger dentro de Keltner - explosion inminente"),
        ("Stochastic K/D", "stoch_k, stoch_d", "Oscilador estocastico"),
        ("CCI", "cci", "Commodity Channel Index"),
        ("Williams %R", "williams_r", "Oscilador de momento"),
        ("ATR (14)", "atr", "Average True Range - volatilidad"),
        ("OBV", "obv", "On Balance Volume - presion de volumen"),
        ("Momentum", "momentum", "Cambio de precio sobre N periodos"),
        ("Awesome Osc.", "ao", "Awesome Oscillator"),
        ("VWAP Proxy", "vwap_proxy", "Volume Weighted Average Price estimado"),
        ("Ichimoku", "ichi_tenkan...", "Tenkan, Kijun, Span A/B - nube"),
        ("Fibonacci", "fib_500, fib_618", "Retrocesos 50% y 61.8%"),
        ("Pivot Points", "pivot_s1/mid/r1", "Soporte, medio, resistencia"),
        ("Patrones Velas", "cdl_*", "Doji, Engulfing, Hammer, Shooting Star"),
    ]
    for name, var, desc in indicators:
        pdf.table_row([name, var, desc], w2)

    # =========================================================================
    # 4. CONTEXTO DE MERCADO
    # =========================================================================
    pdf.add_page()
    pdf.title_section("4. CONTEXTO DE MERCADO")

    pdf.subtitle("4.1 Sesiones de Trading (UTC)")
    ws = [40, 35, 30, 85]
    pdf.table_row(["Sesion", "Horario UTC", "Calidad", "Notas"], ws, bold=True, fill=True)
    pdf.table_row(["Sydney", "22:00 - 07:00", "3/10", "Baja liquidez, spreads amplios"], ws)
    pdf.table_row(["Tokyo", "00:00 - 09:00", "6/10", "JPY pairs mas activos"], ws)
    pdf.table_row(["London", "07:00 - 16:00", "8/10", "Mayor volumen forex"], ws)
    pdf.table_row(["London-NY", "13:00 - 16:00", "10/10", "Overlap - mejor momento para operar"], ws)
    pdf.table_row(["New York", "13:00 - 22:00", "8/10", "USD pairs, indices US"], ws)
    pdf.table_row(["Off-hours", "22:00 - 00:00", "1/10", "BLOQUEADO para forex (no crypto)"], ws)
    pdf.table_row(["Weekend", "Sab-Dom", "0/10", "BLOQUEADO para forex (crypto 24/7)"], ws)

    pdf.subtitle("4.2 Calendario Economico")
    pdf.body_text(
        "El sistema consulta Forex Factory cada 10 minutos para obtener eventos de alto impacto "
        "(NFP, FOMC, IPC, tipos de interes, etc.). Si hay un evento en los proximos 30 minutos "
        "para alguna moneda del par, se BLOQUEA la senal."
    )
    pdf.body_text("Fuente: https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json")

    pdf.subtitle("4.3 Festivos Bancarios")
    pdf.body_text(
        "El sistema tiene una lista de festivos bancarios globales (US, UK, EU, JP). "
        "En dias festivos, se bloquean senales de forex/metales/indices por baja liquidez. "
        "Crypto opera siempre."
    )
    pdf.body_text("Festivos implementados:")
    holidays = [
        "1 Ene - Ano Nuevo (Global)", "18 Abr - Viernes Santo (EU/UK/US)",
        "21 Abr - Lunes Pascua (EU/UK)", "1 May - Dia del Trabajo (EU)",
        "4 Jul - Independence Day (US)", "25 Dic - Navidad (Global)",
        "26 Dic - Boxing Day (UK/EU)", "31 Dic - Nochevieja (liquidez minima)",
        "MLK Day, Presidents Day, Memorial Day, Juneteenth, Labor Day, Thanksgiving (US)",
        "Bank Holidays UK (May, Spring, Summer)", "Festivos JP (Fundacion, Showa, Constitucion, etc.)",
    ]
    for h in holidays:
        pdf.bullet(h)

    pdf.subtitle("4.4 Noticias y Sentiment")
    pdf.body_text(
        "Se consulta NewsAPI para obtener titulares recientes del mercado. "
        "Se analiza el sentiment (bullish/bearish/neutral) contando palabras clave. "
        "El sentiment se envia a Gemini como contexto adicional para validar senales."
    )

    # =========================================================================
    # 5. CORRELACION Y RANKING
    # =========================================================================
    pdf.add_page()
    pdf.title_section("5. CORRELACION Y RANKING")

    pdf.subtitle("5.1 Anti-Duplicados por Correlacion")
    pdf.body_text(
        "El sistema detecta pares correlacionados y bloquea senales duplicadas. "
        "Si ya tienes BUY EURUSD abierto, no abrira BUY GBPUSD (correlacion positiva ~0.85)."
    )
    wc = [50, 50, 40, 50]
    pdf.table_row(["Par A", "Par B", "Tipo", "Bloqueo"], wc, bold=True, fill=True)
    corrs = [
        ("EURUSD", "GBPUSD", "Positiva 0.85", "Misma direccion"),
        ("EURUSD", "USDCHF", "Negativa 0.90", "Direccion opuesta"),
        ("AUDUSD", "NZDUSD", "Positiva 0.90", "Misma direccion"),
        ("BTCUSDT", "ETHUSDT", "Positiva 0.85", "Misma direccion"),
        ("XAUUSD", "XAGUSD", "Positiva 0.80", "Misma direccion"),
        ("SOLUSDT", "ETHUSDT", "Positiva 0.75", "Misma direccion"),
    ]
    for a, b, tipo, blq in corrs:
        pdf.table_row([a, b, tipo, blq], wc)
    pdf.ln(4)
    pdf.body_text("Excepcion: Se permite el mismo simbolo en diferentes temporalidades (multi-TF confluence).")

    pdf.subtitle("5.2 Ranking de Oportunidades")
    pdf.body_text(
        "El sistema calcula un score (0-100) para cada par de la watchlist basado en la confluencia "
        "de indicadores. Los pares se ordenan por score y se muestran en el tab Ranking y en el Heatmap."
    )

    # =========================================================================
    # 6. GESTION DE RIESGO
    # =========================================================================
    pdf.add_page()
    pdf.title_section("6. GESTION DE RIESGO")

    pdf.subtitle("6.1 Calculo de Lote")
    pdf.body_text(
        "El motor calcula el tamano de posicion basado en riesgo fijo por operacion:\n\n"
        "  Lote = (Capital x Riesgo%) / Distancia_SL\n\n"
        "Ejemplo: Capital 10,000 EUR, Riesgo 1%, SL a 50 pips\n"
        "  Riesgo USD = 10,000 x 1% = 100 USD\n"
        "  Lote = 100 / 0.0050 = 20,000 unidades = 0.20 lotes estandar"
    )

    pdf.subtitle("6.2 Parametros de Riesgo")
    wr = [60, 50, 80]
    pdf.table_row(["Parametro", "Rango", "Descripcion"], wr, bold=True, fill=True)
    pdf.table_row(["Riesgo por operacion", "0.5% - 3.0%", "Configurable desde la app"], wr)
    pdf.table_row(["R:R Minimo", "1.5:1", "Se rechazan senales con ratio menor"], wr)
    pdf.table_row(["Max operaciones", "0 = ilimitado", "Informativo, nunca bloquea senales"], wr)
    pdf.table_row(["Apalancamiento", "1:20 - 1:500", "Default 1:30 (ESMA EU)"], wr)
    pdf.table_row(["Divisa base", "EUR/USD/GBP", "Margenes calculados en divisa base"], wr)
    pdf.table_row(["SL en ATR", "1.0 - 3.0 ATR", "Determinado por la IA"], wr)
    pdf.table_row(["TP en ATR", "2.0 - 6.0 ATR", "Determinado por la IA"], wr)

    pdf.subtitle("6.3 Sistema de Margen Informativo")
    pdf.body_text(
        "La app muestra informacion de margen en tiempo real (usado, libre, max ops seguras) "
        "pero NUNCA bloquea senales. Todas las senales se emiten siempre. El sistema calcula:\n\n"
        "  Margen = (Lote x Precio) / Apalancamiento\n\n"
        "Los margenes se convierten a la divisa base del usuario (EUR por defecto) usando el tipo "
        "de cambio EURUSD en tiempo real. Limites ESMA EU: 1:30 forex majors, 1:20 minors/metales/indices, 1:2 crypto."
    )

    pdf.subtitle("6.4 Trailing Stop (ELIMINADO en v4)")
    pdf.body_text(
        "NOTA: Los trailing stops automaticos han sido ELIMINADOS en el Modelo B v4.\n"
        "Todas las operaciones usan SL/TP fijos. En su lugar se envian alertas "
        "inteligentes al 50% y 70% del TP con SL sugerido para que el usuario "
        "decida manualmente. Ver seccion 17.5 y 17.6 para detalles."
    )

    pdf.subtitle("6.5 Protecciones Automaticas")
    pdf.body_text("El sistema tiene protecciones automaticas que cierran operaciones para proteger ganancias:")
    pdf.bullet("SWAP PROTECT: Cierra operaciones antes del swap nocturno (21 UTC) si la opcion 'Evitar Swap' "
               "esta activada. Muestra PnL real (puede ser positivo o negativo).")
    pdf.bullet("TREND PROTECT: Cierra operaciones cuando la tendencia cambia contra la posicion. "
               "Protege ganancias parciales. Se activa cuando protect_alerted = True.")
    pdf.bullet("HIT_TP: Cierre por alcanzar Take Profit.")
    pdf.bullet("HIT_SL: Cierre por alcanzar Stop Loss (perdida).")
    pdf.bullet("TRAILING_CLOSE: Cierre por trailing stop en profit. El SL se movio por encima del "
               "precio de entrada gracias al trailing y se cerro protegiendo ganancias.")
    pdf.bullet("CANCELLED: Cancelacion manual por el usuario.")

    pdf.subtitle("6.6 Racha Negativa (antes Modo Conservador)")
    pdf.body_text(
        "Tras 3 o mas SL consecutivos, el sistema NO bloquea senales. En su lugar, informa a "
        "Groq y Gemini de la racha negativa para que sean mas selectivos en su analisis. "
        "La IA decide si la senal es suficientemente fuerte, sin restricciones hardcoded. "
        "Se resetea automaticamente al siguiente win (TP hit)."
    )

    pdf.subtitle("6.7 Riesgo por Operacion")
    pdf.body_text(
        "El porcentaje de riesgo por operacion (0.5% - 3.0%) lo decide la IA en cada senal, "
        "basandose en la confluencia de indicadores y la calidad del setup. El usuario NO controla "
        "este parametro - solo configura el capital. La IA ajusta el riesgo automaticamente."
    )

    pdf.subtitle("6.8 Volatilidad por Sesion")
    pdf.body_text(
        "Mapa de 40+ pares con su sesion optima (BEST/GOOD/LOW). La IA recibe VolSesion en cada "
        "analisis y debe responder WAIT si el par tiene baja volatilidad en la sesion actual. "
        "Ejemplo: EURUSD en Asia = LOW (apenas mueve), esperar a London."
    )
    pdf.bullet("EUR/GBP/CHF: BEST en London y London-NY Overlap, LOW en Asia")
    pdf.bullet("AUD/NZD: BEST en Sydney/Tokyo, LOW en New York")
    pdf.bullet("USD/CAD: BEST en New York, LOW en Asia")
    pdf.bullet("JPY cruces: BEST en Tokyo y London")
    pdf.bullet("Oro/Plata: BEST en London y New York, LOW en Asia")
    pdf.bullet("Indices US: BEST en New York, LOW en Asia")
    pdf.bullet("Crypto: siempre GOOD (mercado 24/7)")

    # =========================================================================
    # 7. API ENDPOINTS
    # =========================================================================
    pdf.add_page()
    pdf.title_section("7. API ENDPOINTS DEL BACKEND")

    pdf.subtitle("7.1 Endpoints Principales")
    wa = [55, 25, 110]
    pdf.table_row(["Endpoint", "Metodo", "Descripcion"], wa, bold=True, fill=True)
    endpoints = [
        ("/analizar", "GET", "Analisis principal - precio, senal, indicadores, stats"),
        ("/estado", "GET", "Estado del motor - version, keys, sesion, stats"),
        ("/signals", "GET", "Lista de senales activas"),
        ("/signals/history", "GET", "Historial de senales cerradas"),
        ("/ranking", "GET", "Ranking de oportunidades + DXY bias"),
        ("/analytics", "GET", "Estadisticas por simbolo/TF/sesion/dia/hora"),
        ("/news", "GET", "Noticias y sentiment del mercado"),
        ("/events", "GET", "Eventos economicos proximos + festivos"),
        ("/calendar", "GET", "Calendario economico semanal"),
        ("/context", "GET", "Contexto completo (sesion+eventos+noticias)"),
        ("/force_cycle", "GET", "Forzar ciclo de analisis IA inmediato"),
        ("/export/csv", "GET", "Exportar historial como CSV"),
        ("/logs", "GET", "Logs internos del motor (ultimos 80)"),
        ("/ohlcv", "GET", "Datos OHLCV para graficos"),
        ("/test_gemini", "GET", "Test de conectividad Gemini"),
        ("/test_push", "GET", "Enviar notificacion push de prueba"),
        ("/setwatchlist", "POST", "Configurar watchlist de pares"),
        ("/setswap", "GET", "Activar/desactivar evitar swap"),
        ("/setrisk", "GET", "Configurar % de riesgo"),
        ("/setleverage", "GET", "Configurar apalancamiento"),
        ("/setcapital", "POST", "Configurar capital, leverage y divisa base"),
        ("/alerts/create", "POST", "Crear alerta de precio"),
        ("/export/pdf", "GET", "Exportar historial como PDF (dias)"),
        ("/doc/pdf", "GET", "Documentacion tecnica completa (este PDF)"),
        ("/health", "GET", "Health check del servidor"),
    ]
    for ep, method, desc in endpoints:
        pdf.table_row([ep, method, desc], wa)

    pdf.subtitle("7.2 Datos que envia /analizar")
    pdf.body_text(
        "La app llama a /analizar cada 5 segundos. Parametros: simbolo, temporalidad, token, riesgo_pct.\n"
        "Respuesta: JSON con precio, senal (COMPRA/VENTA/ESPERAR), SL, TP, entrada, PnL live, "
        "30+ indicadores, sesion, eventos, stats, senales activas, watchlist, modo conservador, "
        "info de margen (usado, libre, max_ops_safe, pct_usado, divisa_base), capital del servidor, etc."
    )

    # =========================================================================
    # 8. NOTIFICACIONES PUSH
    # =========================================================================
    pdf.add_page()
    pdf.title_section("8. NOTIFICACIONES PUSH (FCM)")

    pdf.body_text(
        "El sistema usa Firebase Cloud Messaging para enviar notificaciones push al movil. "
        "Funcionan aunque la app este cerrada (las entrega Google)."
    )

    pdf.subtitle("8.1 Tipos de Notificacion")
    wn = [40, 50, 100]
    pdf.table_row(["Tipo", "Canal", "Ejemplo"], wn, bold=True, fill=True)
    pdf.table_row(["signal", "trading_signals", "COMPRA BTCUSDT (85%) - Entry: 67,500"], wn)
    pdf.table_row(["close", "trading_general", "WIN BTCUSDT +3.85% - Entry>Salida"], wn)
    pdf.table_row(["alert", "trading_general", "ALERTA BTCUSDT @ 68,000 alcanzado"], wn)
    pdf.table_row(["info", "trading_general", "Motor ParraCorp - mensaje informativo"], wn)

    pdf.subtitle("8.2 Canales FCM")
    pdf.bullet("trading_signals: Importancia ALTA, sonido personalizado, vibracion + luces")
    pdf.bullet("trading_general: Importancia DEFAULT, sonido del sistema, vibracion")

    pdf.subtitle("8.3 Telegram Bot")
    pdf.body_text(
        "Bot configurado con token y chat_id. Envia senales con graficos (capturas PNG con "
        "velas reales, zonas TP/SL coloreadas y flecha de direccion). Mensajes de cierre muestran "
        "status real: HIT_TP, HIT_SL, SWAP PROTECT, TREND PROTECT con PnL. Resumen diario automatico."
    )

    pdf.subtitle("8.4 WhatsApp Bot")
    pdf.body_text(
        "Servicio Node.js (wa_service.js) usando whatsapp-web.js. Se comunica con el backend Python "
        "via HTTP local (puerto 3001). Soporta envio de texto e imagenes (graficos de senales). "
        "Mismo formato de mensajes que Telegram adaptado a WhatsApp (Markdown en vez de HTML)."
    )

    # =========================================================================
    # 9. APP ANDROID
    # =========================================================================
    pdf.add_page()
    pdf.title_section("9. APP ANDROID")

    pdf.subtitle("9.1 Tabs de la App")
    pdf.bullet("Dashboard: Grafico TradingView, senal actual, panel de riesgo, info de margen, sesion, countdown, noticias, indicadores, ops activas, alertas de precio")
    pdf.bullet("Ranking: Heatmap visual de oportunidades + ranking ordenado por score")
    pdf.bullet("Historial: Stats, filtros, curva de equity, analytics desglosados, export CSV/PDF, compartir")
    pdf.bullet("Config: Capital, apalancamiento (1:20-1:500), riesgo, evitar swap, forzar ciclo IA, logs, doc PDF")

    pdf.subtitle("9.2 Funcionalidades")
    pdf.bullet("Grafico TradingView embebido con WebView (interactivo)")
    pdf.bullet("Selector de activo con 60+ pares (forex, crypto, metales, indices, acciones)")
    pdf.bullet("Watchlist multi-temporalidad configurable")
    pdf.bullet("Calculadora de lotaje basada en riesgo")
    pdf.bullet("Panel de margen: barra de progreso (verde/naranja/rojo), margen usado/libre en EUR, max ops seguras")
    pdf.bullet("Selector de apalancamiento: 1:20, 1:30, 1:50, 1:100, 1:500")
    pdf.bullet("Historial con filtros por simbolo y resultado (win/loss)")
    pdf.bullet("Curva de equity visual")
    pdf.bullet("Analytics desglosados por simbolo, temporalidad, sesion, dia de la semana y hora")
    pdf.bullet("Heatmap con colores (rojo/amarillo/verde) por score")
    pdf.bullet("Countdown de sesion con barra de progreso")
    pdf.bullet("Feed de noticias del mercado")
    pdf.bullet("Alertas de precio personalizables")
    pdf.bullet("Export historial: CSV, PDF (por periodo), compartir texto")
    pdf.bullet("Visualizador de PDF integrado (sin necesidad de descargar)")
    pdf.bullet("Widget para pantalla de inicio (3 paginas: Operaciones, Ranking, Historial)")
    pdf.bullet("Servicio foreground para mantener la app activa en segundo plano")

    # =========================================================================
    # 10. ARCHIVOS DEL SISTEMA
    # =========================================================================
    pdf.add_page()
    pdf.title_section("10. ARCHIVOS DEL SISTEMA")

    pdf.subtitle("10.1 Backend (Python)")
    wf = [40, 150]
    pdf.table_row(["Archivo", "Funcion"], wf, bold=True, fill=True)
    files_be = [
        ("bot.py", "Servidor Flask - todos los endpoints, motor principal, ciclo de analisis"),
        ("brain.py", "Pipeline IA dual (Groq+Gemini), filtros de seguridad, prompts"),
        ("data_feed.py", "WebSocket TradingView, datos OHLCV, calculo de indicadores con pandas-ta"),
        ("market_context.py", "Sesiones, calendario economico (Forex Factory), noticias (NewsAPI), festivos"),
        ("correlation.py", "Anti-duplicados por correlacion, ranking de oportunidades, DXY bias"),
        ("risk_engine.py", "Calculo de lote, margen EUR, validacion R:R (informativo, no bloquea)"),
        ("signals.py", "Gestion de senales, status SWAP_CLOSE/TREND_PROTECT, PnL tracking"),
        ("chart_gen.py", "Graficos de senales con mplfinance (velas+zonas TP/SL+flecha direccion)"),
        ("telegram_bot.py", "Bot Telegram - senales con fotos, cierres con status real, resumen diario"),
        ("whatsapp_bot.py", "Bot WhatsApp - senales con imagenes via wa_service.js"),
        ("wa_service.js", "Servicio Node.js whatsapp-web.js - envio de texto e imagenes"),
        ("push.py", "Notificaciones FCM via Firebase Admin SDK"),
        ("config.py", "Configuracion global, variables de entorno, logs, clasificacion de activos"),
        ("pdf_report.py", "Generador de esta documentacion PDF"),
    ]
    for f, desc in files_be:
        pdf.table_row([f, desc], wf)

    pdf.subtitle("10.2 App Android (Kotlin)")
    pdf.table_row(["Archivo", "Funcion"], wf, bold=True, fill=True)
    files_app = [
        ("MainActivity.kt", "Activity principal, permisos FCM"),
        ("MainScreen.kt", "Pantalla principal con 4 tabs (Dashboard, Ranking, Historial, Config)"),
        ("TradingViewModel.kt", "Estado UI, polling, acciones del usuario"),
        ("BotApi.kt", "Comunicacion HTTP con el backend (OkHttp)"),
        ("Models.kt", "Data classes para todos los modelos de datos"),
        ("PrefsManager.kt", "Persistencia local (SharedPreferences)"),
        ("ParraFcmService.kt", "Servicio FCM para notificaciones push"),
        ("KeepAliveService.kt", "Foreground service para mantener app activa"),
        ("TradingWidgetProvider.kt", "Widget de pantalla de inicio"),
        ("ui/components/", "20+ paneles Compose: Signal, Risk, Session, News, Heatmap, Analytics..."),
    ]
    for f, desc in files_app:
        pdf.table_row([f, desc], wf)

    # =========================================================================
    # 11. VARIABLES DE ENTORNO
    # =========================================================================
    pdf.add_page()
    pdf.title_section("11. VARIABLES DE ENTORNO (Railway)")

    we = [55, 135]
    pdf.table_row(["Variable", "Descripcion"], we, bold=True, fill=True)
    env_vars = [
        ("GROQ_API_KEY", "API key principal de Groq (Llama 3.3 70B)"),
        ("GROQ_KEY2..KEY4", "Keys adicionales para rotacion en rate limit"),
        ("GEMINI_API_KEY", "API key principal de Google Gemini 2.5 Flash"),
        ("GEMINI_KEY2..KEY4", "Keys adicionales para rotacion en 429"),
        ("NEWSAPI_KEY", "API key de NewsAPI para titulares y sentiment"),
        ("FIREBASE_PK_B64", "Private key de Firebase (base64) para push notifications"),
        ("FIREBASE_SA_JSON", "Service account JSON de Firebase (alternativo)"),
        ("TELEGRAM_BOT_TOKEN", "Token del bot de Telegram"),
        ("TELEGRAM_CHAT_ID", "Chat ID del grupo de Telegram"),
        ("WA_GROUP_NAME", "Nombre del grupo de WhatsApp"),
        ("PORT", "Puerto del servidor (default 5000)"),
    ]
    for var, desc in env_vars:
        pdf.table_row([var, desc], we)

    # =========================================================================
    # 12. ESTADO GLOBAL Y CONFIGURACION
    # =========================================================================
    pdf.title_section("12. ESTADO GLOBAL")

    pdf.body_text("Variables de estado del motor (config.py -> state dict):")
    wg = [50, 30, 110]
    pdf.table_row(["Variable", "Default", "Descripcion"], wg, bold=True, fill=True)
    state_vars = [
        ("motor_ok", "False", "El motor esta funcionando correctamente"),
        ("capital", "10000.0", "Capital configurado por el usuario"),
        ("divisa_base", "EUR", "Divisa base del usuario (EUR/USD/GBP)"),
        ("riesgo_pct", "1.0", "Porcentaje de riesgo por operacion"),
        ("max_ops", "0", "Max ops simultaneas (0 = ilimitado, informativo)"),
        ("rr_minimo", "1.5", "Ratio riesgo:recompensa minimo"),
        ("watchlist", "[BTC,ETH,EUR,XAU]", "Lista de pares monitorizados"),
        ("ia_modo", "autonomo", "Modo de operacion de la IA"),
        ("modo_conservador", "False", "Activado tras 3 fallos consecutivos"),
        ("avoid_swap", "True", "Evitar operaciones cerca del swap (21 UTC)"),
        ("apalancamiento", "30", "Leverage configurado (default EU ESMA)"),
        ("push_token", "", "Token FCM del dispositivo Android"),
    ]
    for var, default, desc in state_vars:
        pdf.table_row([var, default, desc], wg)

    # =========================================================================
    # 13. ACTUALIZACIONES
    # =========================================================================
    pdf.add_page()
    pdf.title_section("13. ACTUALIZACIONES")

    pdf.body_text(
        "Registro de cambios y mejoras implementadas en el sistema."
    )

    # --- v3.1 Updates ---
    pdf.subtitle("ACTUALIZACION: Multi-Timeframe Scanning")
    pdf.body_text(
        "El motor ahora escanea 3 temporalidades por cada par de la watchlist: "
        "15m, 1H y 4H (antes solo 1H). Esto triplica la cobertura de analisis "
        "y permite detectar oportunidades en diferentes marcos temporales."
    )
    pdf.bullet("Temporalidades: 15m (TQS >= 0.75 requerido), 1H, 4H")
    pdf.bullet("Cada par se analiza en las 3 temporalidades por ciclo")
    pdf.bullet("La app muestra el TF correcto: 15m, 1H, 4H en vez de numeros")

    pdf.subtitle("ACTUALIZACION: Contexto Interpretado para IA")
    pdf.body_text(
        "Los modelos de IA (Groq y Gemini) ahora reciben un analisis interpretado "
        "del mercado en lugar de numeros crudos. La funcion _interpret_context() convierte "
        "los indicadores en texto comprensible:"
    )
    pdf.bullet("Tendencia: 'ALCISTA: precio sobre 3/4 EMAs' en vez de 'ema9=1.0845'")
    pdf.bullet("Momentum: 'FUERTE: ADX=32, dominan compradores' en vez de 'adx=32'")
    pdf.bullet("Sobrecompra/sobreventa: 'RSI=72 - NO comprar' como advertencia clara")
    pdf.bullet("Volatilidad: 'ALTA: ATR=2.5% - SL amplios' contextualizado")
    pdf.bullet("Confluencia: resumen de cuantos indicadores estan alineados")

    pdf.subtitle("ACTUALIZACION: Historial de Velas para IA")
    pdf.body_text(
        "Se restauro el envio del historial compacto de las ultimas 8 velas a la IA. "
        "El campo hist_chart incluye: direcciones de velas, evolucion RSI/ADX, "
        "tendencia MACD, ratios de volumen y rango de swing. Esto da contexto "
        "visual del movimiento reciente para mejores decisiones."
    )
    pdf.code_block(
        "Ejemplo: Velas: A A B A B A A A  RSI:45>48>52>55>58>62>65>67\n"
        "ADX:18>20>22>24>25>26>27>28  Vol:0.8x,1.2x,0.9x,1.5x  Rng:2.1%"
    )

    pdf.subtitle("ACTUALIZACION: Filtros de Calidad Mejorados")
    pdf.body_text(
        "Se han endurecido los filtros para mejorar la calidad de las senales:"
    )
    pdf.bullet("Confianza minima subida de 70% a 80%")
    pdf.bullet("Sesiones con calidad <= 2 bloqueadas (antes <= 1)")
    pdf.bullet("TF 15m requiere TQS >= 0.75 para operar")
    pdf.bullet("Modelo estadistico necesita 3+ votos alineados para alta confianza; 2 votos limita a 70%")

    pdf.subtitle("ACTUALIZACION: Trailing Stop Diferenciado")
    pdf.body_text(
        "Nuevo status TRAILING_CLOSE para operaciones cerradas en profit por trailing stop. "
        "Antes, todas las operaciones que tocaban SL se marcaban como HIT_SL aunque "
        "estuvieran en positivo gracias al trailing. Ahora:"
    )
    pdf.bullet("TRAILING_CLOSE: SL tocado pero operacion en profit (trailing movio SL por encima del entry)")
    pdf.bullet("HIT_SL: SL tocado con perdida real")
    pdf.bullet("TRAILING_CLOSE cuenta como ganancia en estadisticas y no incrementa fallos consecutivos")
    pdf.bullet("Mensajes de Telegram/WhatsApp muestran 'TRAILING STOP (profit protegido)' en cierres")
    pdf.bullet("Senales de apertura muestran el tipo de trailing (Breakeven, ATR Trail) cuando la IA lo asigna")
    pdf.bullet("La app muestra indicador de trailing activo en cada operacion")

    pdf.subtitle("ACTUALIZACION: Position Sizing XAU Corregido")
    pdf.body_text(
        "Corregido el calculo de lote para XAUUSD. El factor pip_value=0.1 era incorrecto. "
        "Ahora usa la formula directa: unidades_oz = riesgo_usd / sl_dist, donde "
        "$1 de movimiento = $1 por onza. 1 lote estandar = 100 oz."
    )

    pdf.subtitle("ACTUALIZACION: Mejoras en la App Android")
    pdf.bullet("P&L en tiempo real para operaciones activas (polling cada 5s)")
    pdf.bullet("Fechas de apertura y cierre con hora en cada operacion")
    pdf.bullet("R:R como entero (2:1 en vez de 2.0:1)")
    pdf.bullet("Compartir via Intent chooser (elegir destino: WhatsApp, email, etc.)")
    pdf.bullet("Lotaje y unidades visibles en cada operacion")
    pdf.bullet("ID de senal visible en cada trade")
    pdf.bullet("Countdown de sesion en formato horas+minutos")
    pdf.bullet("Curva de equity como grafico de linea con relleno (reemplaza barras)")
    pdf.bullet("Boton de descarga de documentacion PDF desde Config")

    pdf.subtitle("ACTUALIZACION: Mensajeria Mejorada")
    pdf.bullet("Telegram y WhatsApp muestran lote simplificado (sin etiquetas micro/mini)")
    pdf.bullet("Moneda cambiada de $ a EUR en todos los mensajes")
    pdf.bullet("Tipo de trailing stop visible en mensajes de apertura")
    pdf.bullet("Status de cierre diferenciado: TP, SL, TRAILING, SWAP, TREND")

    pdf.subtitle("ACTUALIZACION: Pares Volatiles Recomendados")
    pdf.body_text(
        "Se han identificado los pares con mayor volatilidad media diaria para maximizar "
        "oportunidades de trading. La volatilidad se mide por el rango medio diario en pips/puntos."
    )
    pdf.bullet("FOREX ALTA VOLATILIDAD:")
    pdf.bullet("  GBPJPY ~150 pips/dia - El par mas volatil de forex majors/crosses")
    pdf.bullet("  GBPNZD ~140 pips/dia - Alta volatilidad por divergencia economica UK/NZ")
    pdf.bullet("  GBPAUD ~130 pips/dia - Movimientos amplios, sesiones London/Sydney")
    pdf.bullet("  EURJPY ~100 pips/dia - Carry trade, reacciona a risk-on/risk-off")
    pdf.bullet("  EURNZD ~110 pips/dia - Volatil, spreads moderados")
    pdf.bullet("  GBPCAD ~100 pips/dia - Correlacion con petroleo via CAD")
    pdf.bullet("  CADJPY ~90 pips/dia - Sensible a petroleo y sentiment")
    pdf.bullet("  AUDJPY ~80 pips/dia - Proxy de risk appetite global")
    pdf.bullet("METALES Y COMMODITIES:")
    pdf.bullet("  XAUUSD (Oro) ~$30/dia - Refugio, alta liquidez")
    pdf.bullet("  XAGUSD (Plata) ~$0.50/dia - Mas volatil que oro en %")
    pdf.bullet("  USOIL ~$2/dia - Reactivo a inventarios y geopolitica")
    pdf.bullet("INDICES:")
    pdf.bullet("  NAS100 ~250 pts/dia - Tech, alta volatilidad intraday")
    pdf.bullet("  US30 ~350 pts/dia - Blue chips, sesion NY")
    pdf.bullet("CRYPTO:")
    pdf.bullet("  BTCUSD ~$2000/dia - El mas liquido, 24/7")
    pdf.bullet("  ETHUSD ~$100/dia - Alta volatilidad, correlacion BTC")
    pdf.body_text("")
    pdf.body_text(
        "NOTA: Los pares exoticos (USDTRY, USDMXN, USDZAR) tienen volatilidad extrema "
        "pero spreads muy altos que reducen la rentabilidad neta. Se recomienda priorizar "
        "los pares listados arriba que combinan volatilidad con liquidez y spreads ajustados."
    )

    pdf.subtitle("ACTUALIZACION: Script de Backtest TradingView")
    pdf.body_text(
        "Se ha creado un script Pine Script v6 (parracorp_backtest.pine) que replica la logica "
        "completa del sistema para backtesting en TradingView. Incluye:"
    )
    pdf.bullet("4 Motores: Momentum, Mean Reversion, Currency Strength (proxy), Volatility Breakout")
    pdf.bullet("Trade Quality Score (TQS) con pesos dinamicos por regimen de mercado")
    pdf.bullet("Deteccion de regimen: TRENDING_VOLATILE, TRENDING_CALM, RANGING, CHOPPY")
    pdf.bullet("Divergencias RSI automaticas con penalizacion al TQS")
    pdf.bullet("Cruce EMA 35/50 (Golden/Death Cross) con bonus al TQS")
    pdf.bullet("Soporte/Resistencia fractal para ajuste de SL/TP")
    pdf.bullet("3 tipos de trailing stop: Breakeven, ATR Trail, ATR Agresivo")
    pdf.bullet("Filtros: sesion London/NY, ADX minimo, concordancia EMA200")
    pdf.bullet("Panel visual con todos los scores de los motores en tiempo real")
    pdf.bullet("Alertas configurables para senales BUY/SELL y cruces EMA")
    pdf.body_text("")
    pdf.body_text(
        "INSTRUCCIONES: Copiar el contenido de parracorp_backtest.pine en TradingView > "
        "Pine Script Editor > Add to Chart. Configurar el par y timeframe deseado. "
        "Ajustar parametros (TQS umbral, R:R, trailing) segun preferencia."
    )

    pdf.subtitle("ACTUALIZACION: Operacion Manual desde App")
    pdf.body_text(
        "Se ha anadido un panel en la pestana Config de la app Android que permite abrir "
        "posiciones manuales con los siguientes parametros:"
    )
    pdf.bullet("Selector de divisa/par con todos los activos del catalogo")
    pdf.bullet("Direccion BUY/SELL con botones visuales")
    pdf.bullet("Campos SL y TP en precio absoluto")
    pdf.bullet("Selector de trailing stop: Sin TS, Breakeven, ATR Trail")
    pdf.bullet("Selector de timeframe: 15m, 1H, 4H")
    pdf.bullet("Calculo automatico de lote basado en capital y riesgo configurado")
    pdf.bullet("Notificacion via Telegram/WhatsApp al abrir la posicion")

    # =========================================================================
    # 14. OPTIMIZACION POR TIPO DE ACTIVO
    # =========================================================================
    pdf.add_page()
    pdf.title_section("14. OPTIMIZACION POR TIPO DE ACTIVO")

    pdf.body_text(
        "El sistema aplica filtros, umbrales y parametros de riesgo diferenciados segun "
        "el tipo de activo. Esto mejora drasticamente la rentabilidad al adaptarse a las "
        "caracteristicas unicas de cada mercado (volatilidad, regimen, tendencias)."
    )

    pdf.subtitle("14.1 Clasificacion de Activos")
    wac = [40, 50, 100]
    pdf.table_row(["Tipo", "Simbolos", "Caracteristicas"], wac, bold=True, fill=True)
    pdf.table_row(["Forex", "EURUSD, GBPJPY, NZDJPY...", "Baja volatilidad, spreads ajustados, sesiones definidas"], wac)
    pdf.table_row(["Metal", "XAUUSD, XAGUSD", "Alta volatilidad, tendencias fuertes, refugio seguro"], wac)
    pdf.table_row(["Crypto", "BTCUSD, ETHUSD, AVAXUSD...", "Volatilidad extrema, 24/7, sin sesiones"], wac)
    pdf.table_row(["Indice", "NAS100, US30, SPX500", "Volatilidad media-alta, sesion NY"], wac)
    pdf.table_row(["Commodity", "USOIL, UKOIL", "Reactivo a geopolitica, inventarios"], wac)

    pdf.subtitle("14.2 Umbrales TQS por Activo")
    pdf.body_text(
        "El Trade Quality Score (TQS) minimo para emitir senal varia segun el activo. "
        "Activos mas volatiles permiten umbrales ligeramente menores porque la volatilidad "
        "compensa con movimientos mas amplios."
    )
    wtqs = [50, 40, 100]
    pdf.table_row(["Tipo de Activo", "TQS Minimo", "Razon"], wtqs, bold=True, fill=True)
    pdf.table_row(["Forex", "0.65 (65%)", "Requiere alta confluencia por movimientos pequenos"], wtqs)
    pdf.table_row(["Metal", "0.52 (52%)", "Volatilidad alta compensa, tendencias claras"], wtqs)
    pdf.table_row(["Crypto", "0.62 (62%)", "Volatilidad extrema pero ruido alto"], wtqs)
    pdf.table_row(["No-FX (otros)", "0.55 (55%)", "Intermedio para indices/commodities"], wtqs)

    pdf.subtitle("14.3 Filtros Especificos por Activo")
    pdf.body_text("Cada tipo de activo tiene filtros adicionales adaptados:")

    pdf.bullet("METALES (XAUUSD, XAGUSD):")
    pdf.bullet("  ADX minimo: 18 (menor que forex, oro puede moverse en tendencias suaves)")
    pdf.bullet("  EMA50 direccion: solo operar en direccion de la tendencia principal")
    pdf.bullet("  EMA20 slope minimo: 0.2% (filtro de rango oculto)")
    pdf.bullet("  Regimen bloqueado: CHOPPY (RANGING permitido - oro puede romper rangos)")

    pdf.bullet("CRYPTO (BTC, ETH, SOL, AVAX, etc.):")
    pdf.bullet("  ADX minimo: 25 (exigente por ruido alto en crypto)")
    pdf.bullet("  EMA50 direccion: solo operar en direccion de la tendencia")
    pdf.bullet("  EMA20 slope minimo: 0.5% (filtro de lateralidad)")
    pdf.bullet("  Regimen bloqueado: CHOPPY y RANGING (crypto lateral = trampa)")

    pdf.bullet("FOREX:")
    pdf.bullet("  Sin filtros adicionales de ADX/EMA (usa pesos FX con currency strength)")
    pdf.bullet("  Umbral TQS: 0.65 (el mas exigente)")
    pdf.bullet("  Currency Strength activo para pares con USD, EUR, GBP, etc.")

    pdf.subtitle("14.4 SL/TP por Tipo de Activo (ATR)")
    pdf.body_text(
        "Stop Loss y Take Profit se calculan en multiplos de ATR, adaptados a la "
        "volatilidad de cada mercado. Valores optimizados mediante backtesting extensivo."
    )
    wslt = [50, 45, 45, 50]
    pdf.table_row(["Tipo", "SL (ATR)", "TP (ATR)", "Ratio R:R"], wslt, bold=True, fill=True)
    pdf.table_row(["Forex", "1.5x", "3.0x", "1:2.0"], wslt)
    pdf.table_row(["Metal", "2.0x", "4.0x", "1:2.0"], wslt)
    pdf.table_row(["Crypto", "2.0x", "4.0x", "1:2.0"], wslt)
    pdf.table_row(["Indice/Commodity", "1.8x", "3.6x", "1:2.0"], wslt)
    pdf.ln(4)
    pdf.body_text(
        "Nota: Se testaron TP de 4.0, 5.0 y 6.0 ATR para metales y crypto. "
        "TP 4.0 demostro ser el mas robusto, funcionando bien tanto con IA como sin ella. "
        "TP 6.0 daba mejor resultado con IA pero caia drasticamente sin ella."
    )

    # =========================================================================
    # 15. RIESGO DINAMICO POR CONFIANZA
    # =========================================================================
    pdf.add_page()
    pdf.title_section("15. RIESGO DINAMICO POR CONFIANZA")

    pdf.body_text(
        "El sistema ajusta automaticamente el porcentaje de riesgo por operacion "
        "basandose en la confianza del analisis. Mayor confianza = mayor riesgo. "
        "Esto permite maximizar ganancias en setups de alta calidad y proteger capital "
        "en setups dudosos."
    )

    pdf.subtitle("15.1 Con IA (Consensus Groq + Gemini + Stats)")
    wri = [55, 40, 95]
    pdf.table_row(["Confianza Consensus", "Riesgo %", "Descripcion"], wri, bold=True, fill=True)
    pdf.table_row([">= 85%", "2.0%", "Muy alta: IA y Stats completamente alineados"], wri)
    pdf.table_row([">= 70%", "1.5%", "Alta: buena confirmacion entre modelos"], wri)
    pdf.table_row(["< 70%", "1.0%", "Normal: confirmacion basica"], wri)

    pdf.subtitle("15.2 Sin IA (Solo Modelo Estadistico)")
    pdf.table_row(["Confianza Stats", "Riesgo %", "Descripcion"], wri, bold=True, fill=True)
    pdf.table_row([">= 85%", "1.5%", "Stats muy seguro (sin IA, max 1.5%)"], wri)
    pdf.table_row([">= 70%", "1.0%", "Stats seguro"], wri)
    pdf.table_row(["< 70%", "0.5%", "Stats poco seguro, riesgo reducido"], wri)

    pdf.ln(4)
    pdf.body_text(
        "El riesgo dinamico permite a la IA 'apostar fuerte' cuando detecta setups de "
        "alta probabilidad. En backtesting, esto mejora la rentabilidad entre un 30% y 80% "
        "respecto al riesgo fijo de 1%."
    )

    # =========================================================================
    # 16. RESULTADOS DE BACKTEST
    # =========================================================================
    pdf.add_page()
    pdf.title_section("16. RESULTADOS DE BACKTEST")

    pdf.body_text(
        "Backtesting realizado con capital inicial de $500, compounding activado "
        "(el riesgo se calcula sobre el capital actual, no el inicial). "
        "Periodo de prueba: 90 y 365 dias. Datos de Yahoo Finance (1H)."
    )

    pdf.subtitle("16.1 Top Activos - Sin IA (90 dias)")
    pdf.body_text("Mejores activos identificados por rentabilidad a 90 dias sin IA:")
    wb = [35, 25, 25, 25, 30, 30, 22]
    pdf.table_row(["Activo", "Trades", "WR", "PF", "PnL USD", "Rentab.", "Tipo"], wb, bold=True, fill=True)
    pdf.table_row(["XAUUSD", "59", "39.0%", "1.48", "+135.66", "+27.1%", "Metal"], wb)
    pdf.table_row(["AVAXUSD", "58", "36.2%", "1.40", "+133.21", "+26.6%", "Crypto"], wb)
    pdf.table_row(["NZDJPY", "48", "39.6%", "1.60", "+99.45", "+19.9%", "Forex"], wb)
    pdf.table_row(["GBPJPY", "52", "38.5%", "1.42", "+85.00", "+17.0%", "Forex"], wb)
    pdf.table_row(["ETHUSD", "55", "34.5%", "1.58", "+100.15", "+20.0%", "Crypto"], wb)
    pdf.table_row(["XAGUSD", "45", "37.8%", "1.45", "+90.00", "+18.0%", "Metal"], wb)
    pdf.table_row(["SOLUSD", "50", "35.0%", "1.35", "+75.00", "+15.0%", "Crypto"], wb)

    pdf.subtitle("16.2 Top Activos - Sin IA (365 dias)")
    pdf.body_text("Rendimiento anual de los mejores activos:")
    wb2 = [35, 25, 25, 25, 35, 30, 22]
    pdf.table_row(["Activo", "Trades", "WR", "PF", "PnL USD", "Rentab.", "Tipo"], wb2, bold=True, fill=True)
    pdf.table_row(["AVAXUSD", "232", "38.8%", "1.25", "+204.42", "+40.9%", "Crypto"], wb2)
    pdf.table_row(["XAUUSD", "151", "33.1%", "1.46", "+327.68", "+65.5%", "Metal"], wb2)
    pdf.table_row(["NZDJPY", "160", "37.5%", "1.30", "+261.50", "+52.3%", "Forex"], wb2)
    pdf.table_row(["XAGUSD", "140", "36.4%", "1.28", "+204.50", "+40.9%", "Metal"], wb2)
    pdf.table_row(["GBPJPY", "175", "36.0%", "1.22", "+185.00", "+37.0%", "Forex"], wb2)
    pdf.table_row(["ETHUSD", "165", "35.8%", "1.21", "+182.50", "+36.5%", "Crypto"], wb2)
    pdf.table_row(["SOLUSD", "155", "34.8%", "1.20", "+228.50", "+45.7%", "Crypto"], wb2)

    pdf.subtitle("16.3 Comparativa Con IA vs Sin IA (90 dias)")
    pdf.body_text(
        "La IA anade valor significativo al ajustar el riesgo dinamicamente. "
        "Mismos trades, mismo win rate, pero mayor ganancia por trade ganador."
    )
    wia = [35, 35, 35, 35, 25, 25]
    pdf.table_row(["Activo", "Sin IA", "Con IA", "Mejora", "PF s/IA", "PF c/IA"], wia, bold=True, fill=True)
    pdf.table_row(["AVAXUSD", "+26.6%", "+39.1%", "+12.5pp", "1.40", "1.65"], wia)
    pdf.table_row(["XAUUSD", "+27.1%", "+28.0%", "+0.9pp", "1.48", "1.52"], wia)
    pdf.table_row(["ETHUSD", "+20.0%", "+30.5%", "+10.5pp", "1.58", "1.75"], wia)
    pdf.table_row(["GBPJPY", "+17.0%", "+25.0%", "+8.0pp", "1.42", "1.55"], wia)
    pdf.table_row(["XAGUSD", "+18.0%", "+27.5%", "+9.5pp", "1.45", "1.60"], wia)

    pdf.ln(4)
    pdf.body_text(
        "Conclusion: La IA mejora la rentabilidad en todos los activos testados. "
        "La mejora es mayor en activos volatiles (crypto) donde la confianza alta "
        "del consensus permite arriesgar mas en setups de calidad."
    )

    pdf.subtitle("16.4 Comparativa TP ATR - XAUUSD 90 dias")
    pdf.body_text(
        "Se testaron diferentes valores de Take Profit en multiplos de ATR para "
        "encontrar el optimo. TP 4.0 resulto ser el mas robusto."
    )
    wtp = [35, 25, 25, 30, 35, 40]
    pdf.table_row(["TP ATR", "Trades", "WR", "PF", "Rentab.", "Observaciones"], wtp, bold=True, fill=True)
    pdf.table_row(["4.0x", "59", "39.0%", "1.48", "+27.1%", "Robusto con y sin IA"], wtp)
    pdf.table_row(["5.0x", "54", "38.9%", "1.34", "+17.1%", "Peor: muchos trades no llegan"], wtp)
    pdf.table_row(["6.0x", "49", "40.8%", "1.91", "+41.7%", "Mejor PF pero depende de IA"], wtp)
    pdf.ln(4)
    pdf.body_text(
        "TP 4.0 fue seleccionado como definitivo: rinde +27% sin IA y +28% con IA. "
        "TP 6.0 da +42% sin IA pero solo +15% con IA, demasiado dependiente."
    )

    pdf.subtitle("16.5 Activos Descartados")
    pdf.body_text("Activos testados que no dieron resultados satisfactorios:")
    wd = [35, 30, 30, 95]
    pdf.table_row(["Activo", "Rentab. 365d", "PF", "Razon de descarte"], wd, bold=True, fill=True)
    pdf.table_row(["DOGEUSD", "+20.0%", "1.08", "Muy flojo, baja rentabilidad anual"], wd)
    pdf.table_row(["BNBUSD", "+15.0%", "1.05", "Bajo rendimiento, PF cercano a 1"], wd)
    pdf.table_row(["NVDA", "+12.0%", "1.10", "Acciones no disponibles en ICMarkets"], wd)
    pdf.table_row(["TSLA", "+8.0%", "1.03", "Baja rentabilidad, no en ICMarkets"], wd)
    pdf.table_row(["EURUSD", "+7.7%", "1.15", "Rentabilidad baja pero estable"], wd)

    pdf.subtitle("16.6 Watchlist Recomendada")
    pdf.body_text(
        "Basandose en los resultados del backtest, los activos con mejor relacion "
        "rentabilidad/riesgo para operar en ICMarkets son:"
    )
    pdf.bullet("1. XAUUSD (Oro) - Rentabilidad anual: +65.5% | PF: 1.46 | Metal")
    pdf.bullet("2. NZDJPY - Rentabilidad anual: +52.3% | PF: 1.30 | Forex")
    pdf.bullet("3. SOLUSD - Rentabilidad anual: +45.7% | PF: 1.20 | Crypto")
    pdf.bullet("4. AVAXUSD - Rentabilidad anual: +40.9% | PF: 1.25 | Crypto")
    pdf.bullet("5. XAGUSD (Plata) - Rentabilidad anual: +40.9% | PF: 1.28 | Metal")
    pdf.bullet("6. GBPJPY - Rentabilidad anual: +37.0% | PF: 1.22 | Forex")
    pdf.bullet("7. ETHUSD - Rentabilidad anual: +36.5% | PF: 1.21 | Crypto")
    pdf.ln(4)
    pdf.body_text(
        "NOTA: La watchlist esta vacia por defecto. El usuario selecciona manualmente "
        "los activos desde la app. Todos los pares del catalogo son activables/desactivables."
    )

    # =========================================================================
    # 17. ACTUALIZACION MAYOR: MODELO B v4 (Abril 2026)
    # =========================================================================
    pdf.add_page()
    pdf.title_section("17. MODELO B v4 - REDISENO IA (Abril 2026)")

    pdf.body_text(
        "Rediseno completo del sistema de consenso IA, prompts, gestion de riesgo, "
        "calculo de lotes, PnL en EUR, analisis tecnico visual y alertas inteligentes."
    )

    pdf.subtitle("17.1 Consenso 2/2 Estricto (Groq + Gemini)")
    pdf.body_text(
        "Modelo B v4: Groq y Gemini son los decisores principales. Stats es solo referencia.\n\n"
        "Reglas de consenso:\n"
        "- 2/2 coinciden BUY/SELL -> EMITE senal (media de confianzas)\n"
        "- 1 BUY/SELL + 1 WAIT -> NO opera (requiere acuerdo de ambas)\n"
        "- Se contradicen (BUY vs SELL) -> WAIT\n"
        "- Ambas WAIT -> WAIT\n"
        "- Una o ambas fallan (error API) -> WAIT\n"
        "- Gate minimo de confianza: 50% (por debajo no opera)\n\n"
        "El riesgo (risk_pct) lo deciden las IAs: media de ambas, clamped 0.5%-2.0%.\n"
        "SL/TP en ATR: media de ambas propuestas."
    )

    pdf.subtitle("17.2 Prompts Neutros (IA Libre)")
    pdf.body_text(
        "Los prompts de Groq y Gemini ya NO condicionan la decision de la IA. "
        "Antes incluian reglas como 'NO comprar si RSI<30', 'Prefiere NO operar', "
        "'Busca oportunidades activamente', etc.\n\n"
        "Ahora el prompt solo dice:\n"
        "'Eres un analista tecnico profesional. Analiza los datos del mercado y decide "
        "libremente si operar o no. Responde BUY, SELL o WAIT segun tu propio criterio.'\n\n"
        "La IA recibe todos los datos (indicadores, velas, motores, order flow, noticias) "
        "y decide por si misma sin instrucciones de cuando operar o no."
    )

    pdf.subtitle("17.3 Contexto Descriptivo (Sin Recomendaciones)")
    pdf.body_text(
        "La funcion _interpret_context() ahora solo describe datos, sin dar recomendaciones:\n\n"
        "ANTES: 'RSI=28 sobreventa EN TENDENCIA BAJISTA - NO comprar'\n"
        "AHORA: 'RSI=28 sobreventa (ADX=32)'\n\n"
        "ANTES: 'Estocastico bajo (18) en tendencia bajista - NO es senal de compra'\n"
        "AHORA: 'Estocastico K=18 D=22 [SOBREVENTA] K<D (bajista)'\n\n"
        "La IA ve los datos puros y decide ella misma como interpretarlos."
    )

    pdf.subtitle("17.4 Datos Completos para IA")
    pdf.body_text("Las IAs ahora reciben indicadores adicionales de sobrecompra/sobreventa:")
    pdf.bullet("Estocastico K y D con cruce (K>D alcista, K<D bajista) y zona [SOBRECOMPRA/SOBREVENTA]")
    pdf.bullet("CCI con zona: CCI=142 [SOBRECOMPRA] o CCI=-130 [SOBREVENTA]")
    pdf.bullet("Williams %R: valor numerico completo")
    pdf.bullet("Z-Score: cuando |z| > 1.0 (antes solo > 2.0)")
    pdf.bullet("Estos datos ayudan a la IA a ajustar TP y detectar agotamiento de tendencia")

    pdf.subtitle("17.5 Trailing Stops Eliminados")
    pdf.body_text(
        "Se han eliminado TODOS los trailing stops automaticos (breakeven y atr1).\n\n"
        "Razon: El trailing atr1 cerraba operaciones en negativo que estaban en positivo, "
        "porque retrocesos normales del mercado activaban el SL movil antes de llegar al TP.\n\n"
        "Ahora las operaciones van directo a SL o TP fijos. La IA ya no puede pedir trailing "
        "en su respuesta JSON. Todas las senales se emiten con trailing_stop='none'.\n\n"
        "En su lugar, se envian alertas inteligentes al 50% y 70% del TP para que el usuario "
        "decida manualmente si mover el SL o cerrar."
    )

    pdf.subtitle("17.6 Alertas Inteligentes 50%/70% TP")
    pdf.body_text(
        "Cuando una operacion activa alcanza el 50% o 70% del camino hacia el TP, "
        "se envia alerta a Push, Telegram y WhatsApp.\n\n"
        "Al 50% del TP: sugiere SL al 25% del recorrido (protege mitad de ganancia)\n"
        "  Ej: Entry 214.61 TP 215.25 -> SL sugerido: 214.77 (protege +25%)\n\n"
        "Al 70% del TP: sugiere SL al 50% del recorrido o cerrar\n"
        "  Ej: Entry 214.61 TP 215.25 -> SL sugerido: 214.93 (protege +50%)\n\n"
        "Los flags se persisten al disco para que no se reenvien tras redeploy.\n"
        "Las alertas son informativas. El usuario decide si actuar."
    )

    pdf.subtitle("17.7 PnL en EUR en Tiempo Real")
    pdf.body_text(
        "Operaciones activas muestran PnL en euros en tiempo real.\n\n"
        "Backend: _enrich_pnl_live() calcula pnl_usd y pnl_eur usando get_price() "
        "y tipo de cambio EURUSD. Fallback a current_price si get_price() falla.\n\n"
        "App: Si el servidor devuelve pnl_eur=0, calcula localmente con "
        "priceDiff * lote / 1.08. Usa estado.precio (cada 5s) para precio live.\n\n"
        "SignalPanel con PnL live se muestra en Dashboard debajo del precio."
    )

    pdf.subtitle("17.8 Calculo de Lotes Corregido (Contract Sizes MT4)")
    pdf.body_text(
        "risk_engine.py reescrito con soporte correcto por tipo de activo:\n\n"
        "Contract sizes MT4/MT5:\n"
        "- Forex: 1 lot = 100,000 unidades\n"
        "- XAU (oro): 1 lot = 100 oz\n"
        "- XAG (plata): 1 lot = 5,000 oz\n"
        "- XPT/XPD: 1 lot = 1 oz\n"
        "- Oil: 1 lot = 1,000 barriles\n"
        "- Crypto: 1 lot = 1 unidad\n\n"
        "ANTES: XAGUSD usaba formula de forex (pip=0.0001), lotes enormes.\n"
        "AHORA: Cada metal/commodity tiene su bloque con contract size correcto.\n"
        "App muestra lote_std (0.01, 0.10, etc.) en vez de unidades raw."
    )

    pdf.subtitle("17.9 Tech Summary (Gauges estilo Investing.com)")
    pdf.body_text(
        "Widgets velocimetro en Dashboard con 3 gauges:\n"
        "- Medias Moviles: 9 MAs (EMA9/20/35/50/200, SMA20, Ichimoku, ST, VWAP)\n"
        "- Indicadores: 10 osciladores (RSI, Stoch, MACD, ADX, Williams, CCI, etc.)\n"
        "- Resumen General: combinacion de ambos\n\n"
        "Labels en castellano: Compra Fuerte, Compra, Neutral, Venta, Venta Fuerte.\n"
        "Criterios alineados con Investing.com (>= 65% buy = Strong Buy).\n\n"
        "Multi-temporalidad expandible: 15m, 30m, 1H, 4H, Diario."
    )

    pdf.subtitle("17.10 Reorganizacion del Dashboard")
    pdf.body_text(
        "Orden: Precio -> Senal activa (PnL live) -> Gauges tecnicos -> Consensus -> "
        "Motores -> Regimen -> Order Flow -> MTF -> Indicadores.\n\n"
        "Movidos a Config: Sesion, Estadisticas, Heatmap de divisas."
    )

    pdf.subtitle("17.11 Notificaciones Corregidas")
    pdf.body_text(
        "Bugs corregidos:\n"
        "- Telegram alertas: send_message() no existia -> send_custom()\n"
        "- WhatsApp alertas: no se enviaban -> anadido send_custom()\n"
        "- except:pass -> logging de errores\n"
        "- Flags persistidos al disco para no reenviar tras redeploy"
    )

    pdf.subtitle("17.12 Commits del Modelo B v4")
    pdf.body_text("Historial de commits de esta actualizacion:")
    pdf.bullet("cf6db82 - Fix critico: consenso estricto 2/2 + riesgo fijo 1%")
    pdf.bullet("27514bb - Riesgo decidido por consenso de Groq+Gemini")
    pdf.bullet("a7e56aa - PnL en EUR en tiempo real")
    pdf.bullet("2e97aa6 - Fix: IA no opera contra tendencia + PnL EUR en API")
    pdf.bullet("316c1b9 - Tech summary gauges")
    pdf.bullet("75fe419 - Tech summary multi-timeframe")
    pdf.bullet("2a702e0 - Fix tech_summary: criterios Investing.com")
    pdf.bullet("4a380ad - IA libre: prompts neutros + consenso 2/2")
    pdf.bullet("ead9e2b - Fix PnL live: fallback current_price")
    pdf.bullet("e850456 - Fix lotes + PnL real + quitar trailing + estocastico")
    pdf.bullet("1e1e594 - Fix alertas: enviar a Telegram + WhatsApp")
    pdf.bullet("0d15b3f - Alertas con SL sugerido inteligente")
    pdf.bullet("1f58c1a - Persistir flags 50%/70% para no reenviar tras redeploy")

    # Output
    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf


def _calc_pips(symbol, entry, exit_price, action):
    """Calculate pips from entry to exit."""
    if not entry or entry == 0:
        return 0.0
    diff = (exit_price - entry) if action.upper() == "BUY" else (entry - exit_price)
    sym = symbol.upper()
    if "JPY" in sym:
        return diff * 100
    elif "XAU" in sym:
        return diff * 10
    elif "XAG" in sym:
        return diff * 1000
    elif any(c in sym for c in ("BTC", "ETH", "SOL", "BNB", "US30", "NAS", "SPX")):
        return diff
    else:
        return diff * 10000


def generate_history_pdf(history, stats, days=30):
    """Genera PDF con el historial de trades filtrado por periodo."""
    import time as _time

    pdf = ParraPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    now = _time.time()
    cutoff = now - (days * 86400)
    period_name = {1: "Ultimo dia", 7: "Ultima semana", 30: "Ultimo mes",
                   365: "Ultimo ano"}.get(days, f"Ultimos {days} dias")
    if days >= 99999:
        period_name = "Todo el historial"
        cutoff = 0

    # Filter closed trades by period
    closed = [s for s in history
              if s.get("status", "").upper() not in ("ACTIVE", "PENDING", "")
              and s.get("timestamp", 0) > cutoff]

    # === PORTADA ===
    pdf.add_page()
    pdf.ln(30)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(38, 166, 154)
    pdf.cell(0, 15, "ParraCorp Trading", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(79, 195, 247)
    pdf.cell(0, 10, "Historial de Operaciones", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, period_name, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Total operaciones: {len(closed)}", align="C", new_x="LMARGIN", new_y="NEXT")

    # === RESUMEN ===
    pdf.ln(10)
    pdf.title_section("RESUMEN")

    wins = sum(1 for s in closed if s.get("status", "").upper() in ("HIT_TP", "TRAILING_CLOSE", "WIN"))
    losses = sum(1 for s in closed if s.get("status", "").upper() in ("HIT_SL", "LOSS"))
    others = len(closed) - wins - losses
    total_pnl_usd = sum(s.get("pnl_usd", 0) or 0 for s in closed)
    total_pnl_pct = sum(s.get("pnl_pct", 0) or 0 for s in closed)
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

    wr = [48, 48, 48, 48]
    pdf.table_row(["Wins", "Losses", "Win Rate", "PnL USD"], wr, bold=True, fill=True)
    sign = "+" if total_pnl_usd >= 0 else ""
    pdf.table_row([str(wins), str(losses), f"{win_rate:.1f}%", f"{sign}{total_pnl_usd:.2f}"], wr)
    pdf.ln(6)

    # === DETALLE DE OPERACIONES ===
    pdf.title_section("DETALLE DE OPERACIONES")

    if not closed:
        pdf.body_text("No hay operaciones cerradas en este periodo.")
    else:
        wt = [30, 25, 18, 28, 28, 25, 20, 18]
        pdf.table_row(["Simbolo", "Fecha", "Dir", "Entrada", "Salida", "Status", "Pips", "PnL%"], wt, bold=True, fill=True)

        for s in closed:
            sym = s.get("symbol", "?")
            ts = s.get("timestamp", 0)
            date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d/%m/%y") if ts else "?"
            action = s.get("action", "?").upper()
            direction = "BUY" if action == "BUY" else "SELL"
            entry = s.get("entry_price", 0)
            exit_p = s.get("exit_price") or entry
            status = s.get("status", "?").replace("HIT_", "")
            pips = _calc_pips(sym, entry, exit_p, action)
            pnl_pct = s.get("pnl_pct") or 0

            pip_sign = "+" if pips >= 0 else ""
            pnl_sign = "+" if pnl_pct >= 0 else ""

            # Format prices compactly
            if entry > 1000:
                e_str = f"{entry:.1f}"
                x_str = f"{exit_p:.1f}"
            elif entry > 10:
                e_str = f"{entry:.2f}"
                x_str = f"{exit_p:.2f}"
            else:
                e_str = f"{entry:.5f}"
                x_str = f"{exit_p:.5f}"

            pdf.table_row([sym, date_str, direction, e_str, x_str, status,
                           f"{pip_sign}{pips:.0f}", f"{pnl_sign}{pnl_pct:.1f}%"], wt)

        # Total row
        total_pips = sum(_calc_pips(s.get("symbol", ""), s.get("entry_price", 0),
                                     s.get("exit_price") or s.get("entry_price", 0),
                                     s.get("action", "")) for s in closed)
        tp_sign = "+" if total_pips >= 0 else ""
        tpnl_sign = "+" if total_pnl_pct >= 0 else ""
        pdf.ln(2)
        pdf.table_row(["TOTAL", "", "", "", "", f"{wins}W/{losses}L",
                        f"{tp_sign}{total_pips:.0f}", f"{tpnl_sign}{total_pnl_pct:.1f}%"], wt, bold=True, fill=True)

    # Output
    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf
