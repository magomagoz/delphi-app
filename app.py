import pandas as pd
import math
import requests
import os
import time
from datetime import datetime
import streamlit as st
import pytz

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Delphi Predictor Pro", layout="centered")

API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'
FILE_DB_CALCIO = 'database_pro_2025.csv'
FILE_DB_PRONOSTICI = 'database_pronostici.csv'

# --- 2. FUNZIONI DATABASE (Indispensabili all'inizio) ---

def inizializza_db_pronostici():
    """Inizializza il file dei pronostici se non esiste."""
    if not os.path.exists(FILE_DB_PRONOSTICI):
        df = pd.DataFrame(columns=["Data", "Ora", "Partita", "Indice LG", "Fiducia", "Dati", "Match_ID", "Risultato", "Stato"])
        df.to_csv(FILE_DB_PRONOSTICI, index=False)

def salva_in_locale(match, lg_idx, fiducia, dati, match_id=None):
    """Salva il pronostico nel database locale."""
    try:
        inizializza_db_pronostici()
        fuso_ita = pytz.timezone('Europe/Rome')
        adesso = datetime.now(fuso_ita)
        
        nuova_riga = {
            "Data": adesso.strftime("%d/%m/%Y"),
            "Ora": adesso.strftime("%H:%M"),
            "Partita": match,
            "Indice LG": lg_idx,
            "Fiducia": f"{fiducia}%",
            "Dati": f"{dati}%",
            "Match_ID": match_id if match_id and str(match_id) != "nan" else "N/A",
            "Risultato": "In attesa",
            "Stato": "Da verificare"
        }
        
        df = pd.read_csv(FILE_DB_PRONOSTICI)
        df = pd.concat([df, pd.DataFrame([nuova_riga])], ignore_index=True)
        df.to_csv(FILE_DB_PRONOSTICI, index=False)
        return True
    except Exception as e:
        st.error(f"Errore tecnico salvataggio: {e}")
        return False

def recupera_risultato_match(match_id):
    """Recupera il risultato finale tramite API."""
    if not match_id or str(match_id) in ["None", "N/A", "nan"]:
        return None, None
    url = f"https://api.football-data.org/v4/matches/{match_id}"
    headers = {"X-Auth-Token": API_TOKEN}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'FINISHED':
                home = data['score']['fullTime']['home']
                away = data['score']['fullTime']['away']
                esito = "1" if home > away else ("2" if home < away else "X")
                return f"{home}-{away}", esito
        return None, None
    except:
        return None, None

def aggiorna_statistiche_locali():
    """Controlla i match in sospeso e aggiorna i risultati."""
    if not os.path.exists(FILE_DB_PRONOSTICI):
        st.warning("Nessun pronostico salvato.")
        return
    df = pd.read_csv(FILE_DB_PRONOSTICI)
    mask = (df['Stato'] == 'Da verificare') & (df['Match_ID'].notnull()) & (df['Match_ID'].astype(str) != 'N/A')
    
    if not df[mask].empty:
        aggiornati = 0
        for idx, row in df[mask].iterrows():
            res, esito = recupera_risultato_match(row['Match_ID'])
            if res:
                df.at[idx, 'Risultato'] = res
                df.at[idx, 'Stato'] = "Verificato"
                aggiornati += 1
        df.to_csv(FILE_DB_PRONOSTICI, index=False)
        st.success(f"Aggiornamento completato: {aggiornati} match verificati.")
        st.rerun()
    else:
        st.info("Tutti i match sono già aggiornati.")

# --- 3. LOGICA MATEMATICA ---

def poisson_probability(k, exp):
    if exp <= 0: return 0
    return (exp**k * math.exp(-exp)) / math.factorial(k)

def stima_quota(prob):
    if prob <= 0.001: return 99.00
    return round(1 / prob, 2)

# --- 4. INTERFACCIA (CORREZIONE BANNER) ---

if os.path.exists("banner.png"):
    st.image("banner.png")
else:
    st.markdown("## ⚽ Delphi Predictor Pro")

# --- 5. ANALISI E SALVATAGGIO ---

def calcola_pronostico_streamlit(nome_input):
    if not os.path.exists(FILE_DB_CALCIO):
        st.error("Esegui l'aggiornamento del database nella tab 'Gestione'."); return
    
    df = pd.read_csv(FILE_DB_CALCIO)
    # Cerca match futuri
    match = df[df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED']) & 
               (df['HomeTeam'].str.contains(nome_input, case=False, na=False) | 
                df['AwayTeam'].str.contains(nome_input, case=False, na=False))]
    
    if match.empty:
        st.warning(f"Nessun match futuro trovato per '{nome_input}'"); return

    m = match.iloc[0]
    # Risoluzione KeyError: usa .get() per sicurezza
    match_id_reale = m.get('ID', "N/A")
    
    st.header(f"🏟️ {m['HomeTeam']} vs {m['AwayTeam']}")
    
    # Valori di esempio (qui inseriresti la tua logica Poisson reale)
    lg_idx = 8.3 
    fiducia = 85
    dati = 92

    st.divider()
    
    # Pulsante di salvataggio unificato
    if st.button("💾 Salva in Cronologia"):
        match_name = f"{m['HomeTeam']} vs {m['AwayTeam']}"
        if salva_in_locale(match_name, lg_idx, fiducia, dati, match_id=match_id_reale):
            st.success("✅ Pronostico salvato con successo!")

# --- 6. NAVIGAZIONE ---

tab1, tab2 = st.tabs(["🎯 Analisi Match", "📜 Cronologia e Statistiche"])

with tab1:
    squadra_cercata = st.text_input("Cerca Squadra (es: Lazio):")
    if st.button("Analizza Match", type="primary"):
        if squadra_cercata:
            calcola_pronostico_streamlit(squadra_cercata)

with tab2:
    st.subheader("Archivio Pronostici")
    if st.button("🔄 Verifica Risultati (Aggiorna Stato)"):
        aggiorna_statistiche_locali()
        
    if os.path.exists(FILE_DB_PRONOSTICI):
        df_visualizza = pd.read_csv(FILE_DB_PRONOSTICI)
        st.dataframe(df_visualizza.iloc[::-1], use_container_width=True)
    else:
        st.info("La cronologia è al momento vuota.")
