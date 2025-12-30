import streamlit as st
import pandas as pd
import os
from datetime import datetime
import pytz

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Delphi Predictor Pro", layout="centered")

API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'
#FILE_DB = 'database_pro_2025.csv'

# Nome del file database locale
DB_FILE = "database_pronostici.csv"

def aggiorna_statistiche_locali():
    if not os.path.exists(DB_FILE):
        return
    
    df = pd.read_csv(DB_FILE)
    # Filtriamo solo quelli da verificare e che hanno un Match_ID valido
    mask = (df['Stato'] == 'Da verificare') & (df['Match_ID'] != 'N/A')
    
    if not df[mask].empty:
        for idx, row in df[mask].iterrows():
            risultato_string, esito_reale = recupera_risultato_match(row['Match_ID'])
            
            if risultato_string:
                df.at[idx, 'Risultato'] = risultato_string
                # Verifichiamo se l'indice LG (il tuo pronostico) era corretto
                # Qui aggiungi la tua logica: es. se Indice LG > 7.0 e esito è '2'...
                df.at[idx, 'Stato'] = "Verificato"
        
        df.to_csv(DB_FILE, index=False)
        st.success("Statistiche aggiornate correttamente!")


# --- FUNZIONI DATABASE ---
def inizializza_db():
    if not os.path.exists(DB_FILE):
        df = pd.DataFrame(columns=["Data", "Ora", "Partita", "Indice LG", "Fiducia", "Dati", "Match_ID", "Risultato", "Stato"])
        df.to_csv(DB_FILE, index=False)

def salva_in_locale(match, lg_idx, fiducia, dati, match_id=None): # <--- Aggiungi =None
    try:
        # Se il file non esiste, lo crea con le nuove colonne
        if not os.path.exists(DB_FILE):
            df = pd.DataFrame(columns=["Data", "Ora", "Partita", "Indice LG", "Fiducia", "Dati", "Match_ID", "Risultato", "Stato"])
            df.to_csv(DB_FILE, index=False)
        
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

# Inizializza il file all'avvio
inizializza_db()

def aggiorna_statistiche_locali():
    if not os.path.exists(DB_FILE):
        return
    
    df = pd.read_csv(DB_FILE)
    # Filtriamo solo quelli da verificare e che hanno un Match_ID valido
    mask = (df['Stato'] == 'Da verificare') & (df['Match_ID'] != 'N/A')
    
    if not df[mask].empty:
        for idx, row in df[mask].iterrows():
            risultato_string, esito_reale = recupera_risultato_match(row['Match_ID'])
            
            if risultato_string:
                df.at[idx, 'Risultato'] = risultato_string
                # Verifichiamo se l'indice LG (il tuo pronostico) era corretto
                # Qui aggiungi la tua logica: es. se Indice LG > 7.0 e esito è '2'...
                df.at[idx, 'Stato'] = "Verificato"
        
        df.to_csv(DB_FILE, index=False)
        st.success("Statistiche aggiornate correttamente!")



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

if st.button("🔄 Aggiorna Risultati e Statistiche"):
    with st.spinner("Controllo risultati su Football-Data.org..."):
        aggiorna_statistiche_locali()
        st.rerun() # Ricarica l'app per mostrare i dati nuovi
