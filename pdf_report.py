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
    pdf.bullet("4. GROQ (Llama 3.3 70B): Analisis tecnico rapido. Recibe todos los indicadores y responde BUY/SELL/WAIT con confianza 0-100")
    pdf.bullet("5. GEMINI (2.5 Flash): Validador final. Puede confirmar o vetar la senal de Groq. Recibe indicadores + noticias + contexto macro")
    pdf.bullet("6. EMISION: Si ambas IA confirman, se crea la senal con entry/SL/TP y se envia push notification")

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
        "Si Gemini no responde, Groq puede operar solo si confianza >= 80% y las noticias no contradicen."
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

    pdf.subtitle("6.4 Trailing Stop")
    pdf.body_text(
        "La IA decide si aplicar trailing stop en cada senal segun el momentum y ADX:\n"
        "- none: Sin trailing stop (por defecto, solo si la IA no lo indica)\n"
        "- breakeven: Mover SL a precio de entrada cuando avanza >= 50% hacia TP\n"
        "- atr1: Trailing ATR - SL sigue al precio a distancia de 1 ATR\n"
        "- atr2: Trailing agresivo, mover SL cada +0.5 ATR\n\n"
        "IMPORTANTE: No todas las operaciones tienen trailing stop. Solo se activa cuando "
        "la IA lo recomienda explicitamente en el campo trailing_stop de su respuesta JSON."
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
    pdf.body(
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
    pdf.body("")
    pdf.body(
        "NOTA: Los pares exoticos (USDTRY, USDMXN, USDZAR) tienen volatilidad extrema "
        "pero spreads muy altos que reducen la rentabilidad neta. Se recomienda priorizar "
        "los pares listados arriba que combinan volatilidad con liquidez y spreads ajustados."
    )

    pdf.subtitle("ACTUALIZACION: Script de Backtest TradingView")
    pdf.body(
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
    pdf.body("")
    pdf.body(
        "INSTRUCCIONES: Copiar el contenido de parracorp_backtest.pine en TradingView > "
        "Pine Script Editor > Add to Chart. Configurar el par y timeframe deseado. "
        "Ajustar parametros (TQS umbral, R:R, trailing) segun preferencia."
    )

    pdf.subtitle("ACTUALIZACION: Operacion Manual desde App")
    pdf.body(
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
