import requests
import os

def invia_messaggio_telegram(testo):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": testo, "parse_mode": "HTML"})

# Qui inserisci il caricamento del CSV e l'avvio della scansione...
# invia_messaggio_telegram("🔥 Segnali Gold di oggi:\n- Juventus vs Napoli...")
