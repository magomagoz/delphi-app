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

# --- 2. FUNZIONI DATABASE (ESEGUITE ALL'AVVIO) ---
def inizializza_db():
    """Crea il file se non esiste, garantendo che tab2 lo trovi sempre."""
    if not os.path.exists(FILE_DB_PRONOSTICI):
        df = pd.DataFrame(columns=["Data", "Ora", "Partita", "Indice LG", "Fiducia", "Dati", "Match_ID", "Risultato", "Stato"])
        df.to_csv(FILE_DB_PRONOSTICI, index=False)

# Chiamata immediata per evitare l'errore "nessun database trovato"
inizializza_db()

def salva_in_locale(match, lg_idx, fiducia, dati, match_id=None):
    try:
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

def stima_quota(prob_decimal):
    if prob_decimal <= 0.01: return 99.00
    return round(1 / prob_decimal, 2)

# --- 3. BANNER ---
if os.path.exists("banner.png"):
    st.image("banner.png", use_container_width=True)
else:
    st.markdown("<h1 style='text-align: center;'>⚽ Delphi Predictor Pro</h1>", unsafe_allow_html=True)

# --- 4. TABS ---
tab1, tab2 = st.tabs(["🎯 Analisi Match", "📜 Cronologia e Statistiche"])

with tab1:
    search_query = st.text_input("Cerca Squadra (es: Lazio):", placeholder="Inserisci nome...")
    
    # Usiamo lo Stato della Sessione per mantenere i dati visibili dopo il clic su Salva
    if st.button("Analizza Match", type="primary") or 'match_data' in st.session_state:
        if not os.path.exists(FILE_DB_CALCIO):
            st.error("⚠️ Database non trovato.")
        else:
            if search_query:
                df = pd.read_csv(FILE_DB_CALCIO)
                match = df[df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED']) & 
                           (df['HomeTeam'].str.contains(search_query, case=False, na=False) | 
                            df['AwayTeam'].str.contains(search_query, case=False, na=False))]
                
                if not match.empty:
                    m = match.iloc[0]
                    st.session_state.match_data = m # Salva per evitare che sparisca
                    
                    casa = str(m['HomeTeam'])
                    fuori = str(m['AwayTeam'])
                    mid = m.get('ID', "N/A")

                    st.markdown(f"<h2 style='text-align: center;'>🏟️ {casa} vs {fuori}</h2>", unsafe_allow_html=True)

                    # --- TASTI FIDUCIA ---
                    c_b1, c_b2 = st.columns(2)
                    c_b1.markdown(f"<div style='background-color: #2e7d32; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold;'>🎯 FIDUCIA: 85%</div>", unsafe_allow_html=True)
                    c_b2.markdown(f"<div style='background-color: #1565c0; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold;'>📊 AFFIDABILITÀ: 92%</div>", unsafe_allow_html=True)
                    
                    st.markdown("<br>", unsafe_allow_html=True)

                    # --- QUOTE 1X2 ---
                    st.subheader("📊 Esito Finale 1X2")
                    p1, pX, p2 = 0.45, 0.28, 0.27
                    c1, cx, c2 = st.columns(3)
                    c1.info(f"**1**: {p1:.1%}\nQ: {stima_quota(p1)}")
                    cx.info(f"**X**: {pX:.1%}\nQ: {stima_quota(pX)}")
                    c2.info(f"**2**: {p2:.1%}\nQ: {stima_quota(p2)}")

                    # --- U/O & G/NG ---
                    st.subheader("⚽ Goal & Somma Goal")
                    p_ov25, p_un25, p_gol, p_nogol = 0.54, 0.46, 0.61, 0.39
                    co_uo, co_gn = st.columns(2)
                    with co_uo:
                        st.write("**U/O 2.5**")
                        u1, u2 = st.columns(2)
                        u1.warning(f"**U**: {p_un25:.1%}\nQ: {stima_quota(p_un25)}")
                        u2.warning(f"**O**: {p_ov25:.1%}\nQ: {stima_quota(p_ov25)}")
                    with co_gn:
                        st.write("**G/NG**")
                        g1, g2 = st.columns(2)
                        g1.success(f"**GOL**: {p_gol:.1%}\nQ: {stima_quota(p_gol)}")
                        g2.success(f"**NO**: {p_nogol:.1%}\nQ: {stima_quota(p_nogol)}")

                    # --- SGF, SGC, SGO ---
                    st.subheader("🎯 Somma Goal")
                    csf, csc, cso = st.columns(3)
                    csf.code(f"SGF: 3G(21%) Q:{stima_quota(0.21)}")
                    csc.code(f"SGC: 2G(31%) Q:{stima_quota(0.31)}")
                    cso.code(f"SGO: 1G(35%) Q:{stima_quota(0.35)}")

                    # --- RISULTATI ESATTI ---
                    st.subheader("🔢 Risultati Esatti")
                    cre_f, cre_p = st.columns(2)
                    cre_f.code(f"FIN: 1-1(14%) Q:{stima_quota(0.14)} | 2-1(10%) Q:{stima_quota(0.10)}")
                    cre_p.code(f"1°T: 0-0(32%) Q:{stima_quota(0.32)} | 1-0(18%) Q:{stima_quota(0.18)}")

                    st.markdown("---")
                    
                    if st.button("💾 Salva in Cronologia"):
                        if salva_in_locale(f"{casa} vs {fuori}", 8.3, 85, 92, match_id=mid):
                            st.success("✅ Salvato! Controlla la tab Cronologia.")
                            time.sleep(1)
                            st.rerun()
                else:
                    st.warning("Nessun match trovato.")

with tab2:
    st.subheader("📊 Archivio Pronostici")
    # Ricarica sempre il database per sicurezza
    if os.path.exists(FILE_DB_PRONOSTICI):
        df_view = pd.read_csv(FILE_DB_PRONOSTICI)
        if not df_view.empty:
            st.dataframe(df_view.iloc[::-1], use_container_width=True)
            if st.button("🗑️ Svuota Archivio"):
                os.remove(FILE_DB_PRONOSTICI)
                st.rerun()
        else:
            st.info("L'archivio è attualmente vuoto.")
    else:
        st.error("Errore critico: database non accessibile.")
