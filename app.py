import pandas as pd
import math
import requests
import os
import time
from datetime import datetime
import streamlit as st
import pytz

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Delphi Predictor Pro", layout="wide")

API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'
FILE_DB_CALCIO = 'database_pro_2025.csv'
FILE_DB_PRONOSTICI = 'database_pronostici.csv'

# --- 2. FUNZIONI DATABASE ---

def inizializza_db():
    if not os.path.exists(FILE_DB_PRONOSTICI):
        df = pd.DataFrame(columns=["Data", "Ora", "Partita", "Indice LG", "Fiducia", "Dati", "Match_ID", "Risultato", "Stato"])
        df.to_csv(FILE_DB_PRONOSTICI, index=False)

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
            "Match_ID": match_id if match_id and str(match_id) != "nan" else "N/A",
            "Risultato": "In attesa",
            "Stato": "Da verificare"
        }
        df = pd.read_csv(FILE_DB_PRONOSTICI)
        df = pd.concat([df, pd.DataFrame([nuova_riga])], ignore_index=True)
        df.to_csv(FILE_DB_PRONOSTICI, index=False)
        return True
    except Exception as e:
        st.error(f"Errore salvataggio: {e}")
        return False

# --- 3. LOGICA DI CALCOLO (POISSON) ---

def poisson_probability(k, exp):
    if exp <= 0: return 0
    return (exp**k * math.exp(-exp)) / math.factorial(k)

def stima_quota(prob):
    if prob <= 0.05: return 20.0 # Quota massima di sicurezza
    return round(1 / prob, 2)

# --- 4. INTERFACCIA ---

if os.path.exists("banner.png"):
    st.image("banner.png", use_container_width=True)
else:
    st.title("⚽ Delphi Predictor Pro")

tab1, tab2 = st.tabs(["🎯 Analisi Match", "📜 Cronologia e Statistiche"])

with tab1:
    search_query = st.text_input("Cerca Squadra (es: Lazio):", placeholder="Inserisci il nome...")
    
    if st.button("Analizza Match", type="primary"):
        if not os.path.exists(FILE_DB_CALCIO):
            st.error("⚠️ Database calcio non trovato. Scarica i dati nella tab Gestione.")
        else:
            df = pd.read_csv(FILE_DB_CALCIO)
            # Filtro match futuri
            match = df[df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED']) & 
                       (df['HomeTeam'].str.contains(search_query, case=False, na=False) | 
                        df['AwayTeam'].str.contains(search_query, case=False, na=False))]
            
            if match.empty:
                st.warning(f"Nessun match imminente trovato per '{search_query}'.")
            else:
                m = match.iloc[0]
                # RISOLUZIONE KEYERROR ID: se la colonna non esiste, mette N/A
                match_id_reale = m.get('ID', "N/A")
                casa = m['HomeTeam']
                fuori = m['AwayTeam']
                
                # --- LOGICA PRONOSTICO (Esempio Calcolato) ---
                # Qui usiamo dei valori simulati basati su Poisson per mostrare i box
                prob_1 = 0.58  # 58%
                prob_X = 0.29  # 29%
                prob_2 = 0.13  # 13%
                
                st.subheader(f"🏟️ {casa} vs {fuori}")
                
                col_fid, col_dat = st.columns(2)
                col_fid.metric("🎯 FIDUCIA", "85%")
                col_dat.metric("📊 DATI ANALIZZATI", "92%")

                st.markdown("---")
                
                # Visualizzazione Box Quote (Simile al tuo screenshot)
                c1, cx, c2 = st.columns(3)
                with c1:
                    st.info(f"**1**: {prob_1:.1%}\n\nQ: {stima_quota(prob_1)}")
                with cx:
                    st.info(f"**X**: {prob_X:.1%}\n\nQ: {stima_quota(prob_X)}")
                with c2:
                    st.info(f"**2**: {prob_2:.1%}\n\nQ: {stima_quota(prob_2)}")

                st.markdown("---")
                
                # Tasto Salvataggio
                if st.button("💾 Salva in Cronologia"):
                    if salva_in_locale(f"{casa} vs {fuori}", 8.3, 85, 92, match_id=match_id_reale):
                        st.success("✅ Salvato correttamente!")

with tab2:
    st.subheader("Archivio Pronostici")
    if os.path.exists(FILE_DB_PRONOSTICI):
        df_crono = pd.read_csv(FILE_DB_PRONOSTICI)
        if not df_crono.empty:
            st.dataframe(df_crono.iloc[::-1], use_container_width=True)
            csv = df_crono.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Scarica CSV", csv, "cronologia.csv", "text/csv")
        else:
            st.info("Nessun pronostico in archivio.")
    else:
        st.info("Cronologia al momento non disponibile.")
