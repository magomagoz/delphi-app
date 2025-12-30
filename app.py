import pandas as pd
import math
import requests
import os
import time
from datetime import datetime
import streamlit as st
import pytz

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Delphi Predictor Pro", layout="wide") # Layout wide per il banner grande

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

def stima_quota(prob):
    if prob <= 0.01: return 99.00
    return round(1 / prob, 2)

# --- 3. BANNER A TUTTO SCHERMO ---
if os.path.exists("banner.png"):
    st.image("banner.png", use_container_width=True)
else:
    st.markdown("<h1 style='text-align: center;'>⚽ Delphi Predictor Pro</h1>", unsafe_allow_bit=True)

# --- 4. TABS ---
tab1, tab2 = st.tabs(["🎯 Analisi Match", "📜 Cronologia e Statistiche"])

with tab1:
    search_query = st.text_input("Cerca Squadra (es: Lazio):", placeholder="Inserisci nome...")
    
    if st.button("Analizza Match", type="primary"):
        if not os.path.exists(FILE_DB_CALCIO):
            st.error("⚠️ Database non trovato. Scarica i dati nella sezione Gestione.")
        else:
            df = pd.read_csv(FILE_DB_CALCIO)
            # Filtro match
            match = df[df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED']) & 
                       (df['HomeTeam'].str.contains(search_query, case=False, na=False) | 
                        df['AwayTeam'].str.contains(search_query, case=False, na=False))]
            
            if match.empty:
                st.warning(f"Nessun match imminente per '{search_query}'.")
            else:
                m = match.iloc[0]
                match_id_reale = m.get('ID', "N/A")
                casa = str(m['HomeTeam'])
                fuori = str(m['AwayTeam'])
                
                # Titolo Match centrato
                st.markdown(f"<h2 style='text-align: center;'>🏟️ {casa} vs {fuori}</h2>", unsafe_allow_bit=True)

                # --- I DUE TASTI AFFIANCATI (FIDUCIA E AFFIDABILITÀ) ---
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    st.markdown(f"""
                        <div style='background-color: #2e7d32; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold; border: 1px solid #ffffff;'>
                            🎯 FIDUCIA: 85%
                        </div>
                    """, unsafe_allow_bit=True)
                with col_btn2:
                    st.markdown(f"""
                        <div style='background-color: #1565c0; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold; border: 1px solid #ffffff;'>
                            📊 DATI: 92%
                        </div>
                    """, unsafe_allow_bit=True)

                st.markdown("<br>", unsafe_allow_bit=True)

                # --- BOX QUOTE (1-X-2) ---
                p1, pX, p2 = 0.121, 0.298, 0.581 # Dati simulati per l'esempio grafico
                
                c1, cx, c2 = st.columns(3)
                with c1:
                    st.info(f"**1**: {p1:.1%}\n\nQ: {stima_quota(p1)}")
                with cx:
                    st.info(f"**X**: {pX:.1%}\n\nQ: {stima_quota(pX)}")
                with c2:
                    st.info(f"**2**: {p2:.1%}\n\nQ: {stima_quota(p2)}")

                st.markdown("---")
                
                # Tasto Salvataggio
                if st.button("💾 Salva in Cronologia"):
                    nome_completo = f"{casa} vs {fuori}"
                    if salva_in_locale(nome_completo, 8.3, 85, 92, match_id=match_id_reale):
                        st.success("✅ Salvato con successo!")

with tab2:
    st.subheader("Archivio Pronostici")
    if os.path.exists(FILE_DB_PRONOSTICI):
        df_crono = pd.read_csv(FILE_DB_PRONOSTICI)
        if not df_crono.empty:
            st.dataframe(df_crono.iloc[::-1], use_container_width=True)
        else:
            st.info("Cronologia vuota.")
    else:
        st.info("Nessun dato salvato.")
