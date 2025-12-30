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

# --- 3. LOGICA DI CALCOLO ---

def poisson_probability(k, exp):
    if exp <= 0: return 0
    return (exp**k * math.exp(-exp)) / math.factorial(k)

def stima_quota(prob):
    if prob <= 0.01: return 99.00
    return round(1 / prob, 2)

# --- 4. INTERFACCIA PRINCIPALE ---

if os.path.exists("banner.png"):
    st.image("banner.png", use_container_width=True)
else:
    st.markdown("<h1 style='text-align: center;'>⚽ Delphi Predictor Pro</h1>", unsafe_allow_bit=True)

tab1, tab2 = st.tabs(["🎯 Analisi Match", "📜 Cronologia e Statistiche"])

with tab1:
    search_query = st.text_input("Cerca Squadra (es: Lazio):", placeholder="Inserisci nome...")
    
    if st.button("Analizza Match", type="primary"):
        if not os.path.exists(FILE_DB_CALCIO):
            st.error("⚠️ Database non trovato. Scarica i dati nella sezione Gestione.")
        else:
            df = pd.read_csv(FILE_DB_CALCIO)
            # Filtro per match futuri/attivi
            match = df[df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED']) & 
                       (df['HomeTeam'].str.contains(search_query, case=False, na=False) | 
                        df['AwayTeam'].str.contains(search_query, case=False, na=False))]
            
            if match.empty:
                st.warning(f"Nessun match imminente per '{search_query}'.")
            else:
                m = match.iloc[0]
                match_id_reale = m.get('ID', "N/A")
                casa = m['HomeTeam']
                fuori = m['AwayTeam']
                
                st.markdown(f"<h2 style='text-align: center;'>🏟️ {casa} vs {fuori}</h2>", unsafe_allow_bit=True)

                # --- DUE BOTTONI AFFIANCATI PER FIDUCIA E AFFIDABILITÀ ---
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    st.markdown("""
                        <div style='background-color: #2e7d32; color: white; padding: 10px; border-radius: 10px; text-align: center; font-weight: bold; border: 1px solid white;'>
                            🎯 FIDUCIA: 85%
                        </div>
                    """, unsafe_allow_bit=True)
                with col_btn2:
                    st.markdown("""
                        <div style='background-color: #1565c0; color: white; padding: 10px; border-radius: 10px; text-align: center; font-weight: bold; border: 1px solid white;'>
                            📊 DATI ANALIZZATI: 92%
                        </div>
                    """, unsafe_allow_bit=True)

                st.markdown("<br>", unsafe_allow_bit=True)

                # --- BOX QUOTE ---
                # Esempio di percentuali calcolate
                p1, pX, p2 = 0.121, 0.298, 0.581
                
                c1, cx, c2 = st.columns(3)
                c1.info(f"**1**: {p1:.1%}\n\nQ: {stima_quota(p1)}")
                cx.info(f"**X**: {pX:.1%}\n\nQ: {stima_quota(pX)}")
                c2.info(f"**2**: {p2:.1%}\n\nQ: {stima_quota(p2)}")

                st.markdown("---")
                
                # Tasto Salvataggio
                if st.button("💾 Salva Pronostico"):
                    if salva_in_locale(f"{casa} vs {fuori}", 8.3, 85, 92, match_id=match_id_reale):
                        st.success("✅ Pronostico archiviato localmente!")

with tab2:
    st.subheader("Archivio Personale")
    if os.path.exists(FILE_DB_PRONOSTICI):
        df_crono = pd.read_csv(FILE_DB_PRONOSTICI)
        if not df_crono.empty:
            st.dataframe(df_crono.iloc[::-1], use_container_width=True)
        else:
            st.info("L'archivio è vuoto.")
    else:
        st.info("Cronologia non ancora creata.")
