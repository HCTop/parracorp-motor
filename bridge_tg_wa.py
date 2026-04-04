#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bridge_tg_wa.py - Bridge Telegram -> WhatsApp

Lee mensajes del bot de Telegram en un grupo y los reenvia a WhatsApp.
Usa Telethon (Telegram) + Selenium (WhatsApp Web con sesion persistente).

REQUISITOS:
  pip install telethon selenium webdriver-manager

PRIMERA VEZ:
  - Te pedira login de Telegram (codigo SMS)
  - Abrira Chrome con WhatsApp Web -> escanea QR
  - Las siguientes veces NO pide nada (sesion guardada)

USO:
  python bridge_tg_wa.py
"""
import os
import re
import sys
import time
import asyncio
import threading

# ============================================================================
# CONFIGURACION
# ============================================================================

TG_API_ID = 38455110
TG_API_HASH = "77df11e964ec7b98ed5c796cc68dc937"
TG_CHAT_ID = -5157330346  # Grupo "ToroWS by ParraCorp"

# Nombre EXACTO del grupo de WhatsApp (tal cual aparece en tu WhatsApp)
WA_GROUP_NAME = "ToroWS by ParraCorp"

# ============================================================================

_wa_driver = None
_wa_ready = False


def clean_html(text):
    """Limpia tags HTML del mensaje de Telegram."""
    return re.sub(r'<[^>]+>', '', text).strip()


# === WHATSAPP WEB VIA SELENIUM =============================================

def init_whatsapp():
    """Abre Chrome con WhatsApp Web. QR solo la primera vez."""
    global _wa_driver, _wa_ready

    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # Instalar ChromeDriver automaticamente
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
    except Exception:
        service = Service()  # Usar chromedriver del PATH

    opts = Options()
    # Sesion persistente - NO pide QR cada vez
    session_dir = os.path.join(os.path.expanduser("~"), ".parracorp_wa_chrome")
    opts.add_argument(f"--user-data-dir={session_dir}")
    opts.add_argument("--profile-directory=Default")
    # Evitar deteccion de automatizacion
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    print("[WA] Abriendo Chrome con WhatsApp Web...")
    _wa_driver = webdriver.Chrome(service=service, options=opts)
    _wa_driver.get("https://web.whatsapp.com")

    print("[WA] Esperando a que cargue WhatsApp Web...")
    print("[WA] (Si es la primera vez, escanea el QR con tu telefono)")
    print("[WA] (Abre WhatsApp > Menu > Dispositivos vinculados > Vincular)")
    print()

    # Esperar hasta que WhatsApp Web este listo (max 2 minutos para QR)
    try:
        WebDriverWait(_wa_driver, 120).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '#side'))
        )
    except Exception:
        print("[WA] Timeout esperando WhatsApp Web. Reintentando...")
        _wa_driver.refresh()
        WebDriverWait(_wa_driver, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '#side'))
        )

    _wa_ready = True
    print("[WA] WhatsApp Web LISTO!")
    print()


def send_whatsapp(message):
    """Envia mensaje al grupo de WhatsApp."""
    global _wa_driver, _wa_ready

    if not _wa_ready or not _wa_driver:
        print("[WA] No inicializado")
        return False

    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    try:
        # 1. Buscar el grupo
        search_box = WebDriverWait(_wa_driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, '[contenteditable="true"][data-tab="3"]')
            )
        )
        search_box.click()
        time.sleep(0.3)

        # Limpiar busqueda anterior
        search_box.send_keys(Keys.CONTROL, "a")
        search_box.send_keys(Keys.DELETE)
        time.sleep(0.2)

        # Escribir nombre del grupo
        search_box.send_keys(WA_GROUP_NAME)
        time.sleep(1.5)

        # 2. Click en el grupo encontrado
        try:
            group = WebDriverWait(_wa_driver, 5).until(
                EC.presence_of_element_located(
                    (By.XPATH, f'//span[@title="{WA_GROUP_NAME}"]')
                )
            )
            group.click()
        except Exception:
            # Intentar con titulo parcial
            group = WebDriverWait(_wa_driver, 5).until(
                EC.presence_of_element_located(
                    (By.XPATH, f'//span[contains(@title,"{WA_GROUP_NAME}")]')
                )
            )
            group.click()
        time.sleep(0.5)

        # 3. Encontrar caja de mensaje
        msg_box = WebDriverWait(_wa_driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, '[contenteditable="true"][data-tab="10"]')
            )
        )
        msg_box.click()
        time.sleep(0.2)

        # 4. Escribir mensaje linea por linea
        lines = message.split('\n')
        for i, line in enumerate(lines):
            if line.strip():
                msg_box.send_keys(line)
            if i < len(lines) - 1:
                msg_box.send_keys(Keys.SHIFT, Keys.ENTER)

        time.sleep(0.2)

        # 5. Enviar
        msg_box.send_keys(Keys.ENTER)
        print(f"[WA] Mensaje enviado al grupo '{WA_GROUP_NAME}'")

        # Limpiar busqueda (volver al estado inicial)
        time.sleep(0.5)
        try:
            search_box2 = _wa_driver.find_element(
                By.CSS_SELECTOR, '[contenteditable="true"][data-tab="3"]'
            )
            search_box2.click()
            search_box2.send_keys(Keys.ESCAPE)
        except Exception:
            pass

        return True

    except Exception as e:
        print(f"[WA] Error enviando: {e}")
        # Intentar recuperar
        try:
            _wa_driver.find_element(By.CSS_SELECTOR, 'body').send_keys(Keys.ESCAPE)
        except Exception:
            pass
        return False


# === TELETHON (TELEGRAM) ===================================================

async def main():
    from telethon import TelegramClient, events

    if not WA_GROUP_NAME:
        print("=" * 50)
        print("  ERROR: Falta configurar WA_GROUP_NAME")
        print("  Abre bridge_tg_wa.py y pon el nombre")
        print("  exacto de tu grupo de WhatsApp")
        print("=" * 50)
        return

    # Iniciar WhatsApp primero
    print("[BRIDGE] Iniciando WhatsApp Web...")
    init_whatsapp()

    # Conectar a Telegram
    session_file = os.path.join(os.path.expanduser("~"), ".parracorp_tg_bridge")
    client = TelegramClient(session_file, TG_API_ID, TG_API_HASH)

    print("[TG] Conectando a Telegram...")
    print("[TG] (La primera vez pedira tu numero y codigo SMS)")
    print()
    await client.start()

    me = await client.get_me()
    print(f"[TG] Conectado como: {me.first_name} (@{me.username})")

    # Obtener entidad del grupo
    try:
        entity = await client.get_entity(TG_CHAT_ID)
        print(f"[TG] Escuchando grupo: {entity.title}")
    except Exception as e:
        print(f"[TG] Error obteniendo grupo: {e}")
        print(f"[TG] Usando chat_id directo: {TG_CHAT_ID}")
        entity = TG_CHAT_ID

    print()
    print("=" * 50)
    print("  BRIDGE ACTIVO")
    print(f"  Telegram: ToroWS by ParraCorp")
    print(f"  WhatsApp: {WA_GROUP_NAME}")
    print(f"  Ctrl+C para detener")
    print("=" * 50)
    print()

    @client.on(events.NewMessage(chats=TG_CHAT_ID))
    async def handler(event):
        """Recibe mensaje de Telegram y lo reenvia a WhatsApp."""
        text = event.message.message or ""
        if not text:
            return

        # Limpiar HTML tags
        clean = clean_html(text)
        if not clean:
            return

        # Mostrar preview
        preview = clean[:80].replace('\n', ' ')
        print(f"[TG->WA] {preview}...")

        # Enviar a WhatsApp en thread separado (selenium no es async)
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, send_whatsapp, clean)
        if success:
            print(f"[OK] Reenviado a WhatsApp")
        else:
            print(f"[FAIL] No se pudo reenviar")

    await client.run_until_disconnected()


if __name__ == "__main__":
    print()
    print("=" * 50)
    print("  ParraCorp Bridge: Telegram -> WhatsApp")
    print("=" * 50)
    print()

    # Verificar dependencias
    ok = True
    try:
        import telethon
        print("[OK] telethon")
    except ImportError:
        print("[X] telethon - pip install telethon")
        ok = False

    try:
        from selenium import webdriver
        print("[OK] selenium")
    except ImportError:
        print("[X] selenium - pip install selenium")
        ok = False

    try:
        from webdriver_manager.chrome import ChromeDriverManager
        print("[OK] webdriver-manager")
    except ImportError:
        print("[!] webdriver-manager - pip install webdriver-manager (recomendado)")

    print()

    if not ok:
        print("Instala las dependencias: pip install telethon selenium webdriver-manager")
        sys.exit(1)

    if not WA_GROUP_NAME:
        print("FALTA CONFIGURAR:")
        print("  Abre bridge_tg_wa.py y edita la variable WA_GROUP_NAME")
        print("  con el nombre EXACTO de tu grupo de WhatsApp")
        print()
        name = input("  O escribe el nombre del grupo aqui: ").strip()
        if name:
            WA_GROUP_NAME = name
        else:
            sys.exit(1)

    asyncio.run(main())
