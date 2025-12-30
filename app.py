import streamlit as st
import pandas as pd
import os
from datetime import datetime
import pytz

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Delphi Predictor Pro", layout="centered")

# Nome del file database locale
DB_FILE = "database_pronostici.csv"

# --- FUNZIONI DATABASE ---
def inizializza_db():
    if not os.path.exists(DB_FILE):
        df = pd.DataFrame(columns=["Data", "Ora", "Partita", "Indice LG", "Fiducia", "Dati"])
        df.to_csv(DB_FILE, index=False)

def salva_in_locale(match, lg_idx, fiducia, dati, match_id):
    try:
        df = pd.read_csv(DB_FILE)
        nuova_riga = {
            "Data": datetime.now(pytz.timezone('Europe/Rome')).strftime("%d/%m/%Y"),
            "Ora": datetime.now(pytz.timezone('Europe/Rome')).strftime("%H:%M"),
            "Partita": match,
            "Indice LG": lg_idx,
            "Fiducia": f"{fiducia}%",
            "Dati": f"{dati}%",
            "Match_ID": match_id,  # Salviamo l'ID per il controllo futuro
            "Risultato": "N/A",
            "Stato": "In attesa"
        }
        df = pd.concat([df, pd.DataFrame([nuova_riga])], ignore_index=True)
        df.to_csv(DB_FILE, index=False)
        return True
    except Exception as e:
        st.error(f"Errore: {e}")
        return False

# Inizializza il file all'avvio
inizializza_db()

# --- INTERFACCIA APP ---
st.title("⚽ Delphi Predictor Pro")

# (Inserisci qui la tua logica di calcolo del pronostico esistente)
# Esempio di come chiamare il salvataggio nel tuo tasto "Analizza":
if st.button("Analizza Match"):
    # ... i tuoi calcoli ...
    match_name = "Udinese vs Lazio" # esempio
    successo = salva_in_locale(match_name, 8.3, 85, 92)
    if successo:
        st.success("✅ Pronostico analizzato e salvato localmente!")

# --- SEZIONE CRONOLOGIA ---
st.divider()
st.subheader("📊 Cronologia Pronostici")
try:
    cronologia = pd.read_csv(DB_FILE)
    if not cronologia.empty:
        st.dataframe(cronologia.sort_index(ascending=False))
        
        # Tasto per scaricare i dati (visto che non sono su Google Sheets)
        csv = cronologia.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Scarica Cronologia CSV", csv, "pronostici.csv", "text/csv")
    else:
        st.info("Nessun pronostico in memoria.")
except:
    st.info("Cronologia al momento non disponibile.")
