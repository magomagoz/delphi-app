import streamlit as st
import pandas as pd
import os
import requests
from datetime import datetime
import pytz

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Delphi Predictor Pro", layout="centered")

API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'
DB_FILE = "database_pronostici.csv"

# --- 1. FUNZIONE RECUPERO RISULTATI (Mancava!) ---
def recupera_risultato_match(match_id):
    if not match_id or str(match_id) == "None" or str(match_id) == "N/A":
        return None, None
    
    url = f"https://api.football-data.org/v4/matches/{match_id}"
    headers = {"X-Auth-Token": API_TOKEN}
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        # Verifichiamo se il match è finito
        if data.get('status') == 'FINISHED':
            home = data['score']['fullTime']['home']
            away = data['score']['fullTime']['away']
            if home > away: esito = "1"
            elif home < away: esito = "2"
            else: esito = "X"
            return f"{home}-{away}", esito
        return None, None
    except Exception:
        return None, None

# --- 2. FUNZIONI DATABASE ---
def inizializza_db():
    if not os.path.exists(DB_FILE):
        df = pd.DataFrame(columns=["Data", "Ora", "Partita", "Indice LG", "Fiducia", "Dati", "Match_ID", "Risultato", "Stato"])
        df.to_csv(DB_FILE, index=False)

def salva_in_locale(match, lg_idx, fiducia, dati, match_id=None):
    try:
        inizializza_db()
        fuso_ita = pytz.timezone('Europe/Rome')
        adesso = datetime.now(fuso_ita)
        
        nuova_riga = {
            "Data": adesso.strftime("%d/%m/%Y"),
            "Ora": adesso.strftime("%H:%M"),
            "Partita": match,
            "Indice LG": lg_idx,
            "Fiducia": f"{fiducia}%",
            "Dati": f"{dati}%",
            "Match_ID": match_id if match_id else "N/A",
            "Risultato": "In attesa",
            "Stato": "Da verificare"
        }
        
        df = pd.read_csv(DB_FILE)
        df = pd.concat([df, pd.DataFrame([nuova_riga])], ignore_index=True)
        df.to_csv(DB_FILE, index=False)
        return True
    except Exception as e:
        st.error(f"Errore tecnico salvataggio: {e}")
        return False

def aggiorna_statistiche_locali():
    if not os.path.exists(DB_FILE):
        return
    
    df = pd.read_csv(DB_FILE)
    # Filtriamo i match "Da verificare" con un ID valido
    mask = (df['Stato'] == 'Da verificare') & (df['Match_ID'].notnull()) & (df['Match_ID'] != 'N/A')
    
    if not df[mask].empty:
        aggiornati = 0
        for idx, row in df[mask].iterrows():
            risultato_string, esito_reale = recupera_risultato_match(row['Match_ID'])
            if risultato_string:
                df.at[idx, 'Risultato'] = risultato_string
                df.at[idx, 'Stato'] = "Verificato"
                aggiornati += 1
        
        if aggiornati > 0:
            df.to_csv(DB_FILE, index=False)
            st.success(f"Aggiornati {aggiornati} risultati!")
        else:
            st.info("Nessun match terminato trovato.")

# Inizializza il file all'avvio
inizializza_db()

# --- 3. INTERFACCIA APP ---
st.title("⚽ Delphi Predictor Pro")

# Esempio di logica "Analizza"
if st.button("Analizza Match"):
    # Qui dovresti recuperare il match_id reale dalla tua funzione di ricerca
    # Per ora uso None per testare il salvataggio
    match_name = "Udinese vs Lazio" 
    successo = salva_in_locale(match_name, 8.3, 85, 92, match_id=None)
    if successo:
        st.success("✅ Pronostico salvato localmente!")

# --- SEZIONE CRONOLOGIA ---
st.divider()
st.subheader("📊 Cronologia Pronostici")
try:
    if os.path.exists(DB_FILE):
        cronologia = pd.read_csv(DB_FILE)
        if not cronologia.empty:
            st.dataframe(cronologia.sort_index(ascending=False))
            
            csv = cronologia.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Scarica Cronologia CSV", csv, "pronostici.csv", "text/csv")
            
            if st.button("🔄 Aggiorna Risultati e Statistiche"):
                with st.spinner("Controllo risultati su Football-Data.org..."):
                    aggiorna_statistiche_locali()
                    st.rerun()
        else:
            st.info("Nessun pronostico in memoria.")
except Exception as e:
    st.error(f"Errore caricamento cronologia: {e}")
