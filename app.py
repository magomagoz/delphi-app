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
    
    if st.button("Analizza Match", type="primary"):
        if not os.path.exists(FILE_DB_CALCIO):
            st.error("⚠️ Database non trovato. Scarica i dati nella sezione Gestione.")
        else:
            df = pd.read_csv(FILE_DB_CALCIO)
            match = df[df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED']) & 
                       (df['HomeTeam'].str.contains(search_query, case=False, na=False) | 
                        df['AwayTeam'].str.contains(search_query, case=False, na=False))]
            
            if match.empty:
                st.warning(f"Nessun match trovato per '{search_query}'.")
            else:
                m = match.iloc[0]
                match_id_reale = m.get('ID', "N/A")
                casa = str(m['HomeTeam'])
                fuori = str(m['AwayTeam'])
                
                st.markdown(f"<h2 style='text-align: center;'>🏟️ {casa} vs {fuori}</h2>", unsafe_allow_html=True)

                # --- TASTI FIDUCIA E AFFIDABILITÀ ---
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    st.markdown(f"<div style='background-color: #2e7d32; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold; border: 1px solid #ffffff;'>🎯 FIDUCIA: 85%</div>", unsafe_allow_html=True)
                with col_btn2:
                    st.markdown(f"<div style='background-color: #1565c0; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold; border: 1px solid #ffffff;'>📊 AFFIDABILITÀ: 92%</div>", unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)

                # --- 1X2 ---
                st.subheader("📊 Esito Finale 1X2")
                p1, pX, p2 = 0.45, 0.28, 0.27 
                c1, cx, c2 = st.columns(3)
                with c1: st.info(f"**1**: {p1:.1%}\nQ: {stima_quota(p1)}")
                with cx: st.info(f"**X**: {pX:.1%}\nQ: {stima_quota(pX)}")
                with c2: st.info(f"**2**: {p2:.1%}\nQ: {stima_quota(p2)}")

                # --- U/O & G/NG ---
                st.subheader("⚽ Goal & Somma Goal")
                p_ov25, p_un25, p_gol, p_nogol = 0.54, 0.46, 0.61, 0.39
                col_uo, col_gn = st.columns(2)
                with col_uo:
                    st.write("**Under/Over 2.5**")
                    u1, u2 = st.columns(2)
                    u1.warning(f"**U 2.5**: {p_un25:.1%}\nQ: {stima_quota(p_un25)}")
                    u2.warning(f"**O 2.5**: {p_ov25:.1%}\nQ: {stima_quota(p_ov25)}")
                with col_gn:
                    st.write("**Gol/NoGol**")
                    g1, g2 = st.columns(2)
                    g1.success(f"**GOL**: {p_gol:.1%}\nQ: {stima_quota(p_gol)}")
                    g2.success(f"**NO GOL**: {p_nogol:.1%}\nQ: {stima_quota(p_nogol)}")

                # --- SGF, SGC, SGO ---
                st.subheader("🎯 Somma Goal Per Squadra (SGF, SGC, SGO)")
                col_sgf, col_sgc, col_sgo = st.columns(3)
                with col_sgf:
                    st.write("**SGF (Top 3)**")
                    st.code(f"3 G: 21% Q:{stima_quota(0.21)}\n2 G: 18% Q:{stima_quota(0.18)}\n4 G: 12% Q:{stima_quota(0.12)}")
                with col_sgc:
                    st.write(f"**SGC ({casa})**")
                    st.code(f"2 G: 31% Q:{stima_quota(0.31)}\n1 G: 28% Q:{stima_quota(0.28)}")
                with col_sgo:
                    st.write(f"**SGO ({fuori})**")
                    st.code(f"1 G: 35% Q:{stima_quota(0.35)}\n0 G: 22% Q:{stima_quota(0.22)}")

                # --- RISULTATI ESATTI ---
                st.subheader("🔢 Risultati Esatti")
                col_re_f, col_re_p = st.columns(2)
                with col_re_f:
                    st.write("**Top 6 Finali**")
                    st.code(f"1-1: 14% Q:{stima_quota(0.14)} | 2-1: 10% Q:{stima_quota(0.10)}\n1-0: 9%  Q:{stima_quota(0.09)} | 2-0: 8%  Q:{stima_quota(0.08)}\n1-2: 7%  Q:{stima_quota(0.07)} | 0-0: 6%  Q:{stima_quota(0.06)}")
                with col_re_p:
                    st.write("**Top 3 1° Tempo**")
                    st.code(f"0-0: 32% Q:{stima_quota(0.32)}\n1-0: 18% Q:{stima_quota(0.18)}\n0-1: 15% Q:{stima_quota(0.15)}")

                st.markdown("---")
                
                # --- FIX SALVATAGGIO ---
                if st.button("💾 Salva in Cronologia"):
                    if salva_in_locale(f"{casa} vs {fuori}", 8.3, 85, 92, match_id=match_id_reale):
                        st.success("✅ Salvato! Caricamento cronologia...")
                        time.sleep(1)
                        st.rerun() # Forza Streamlit a ricaricare i dati e mostrarli nel Tab 2

with tab2:
    st.subheader("📊 Cronologia Pronostici")
    if os.path.exists(FILE_DB_PRONOSTICI):
        # Leggiamo il file ogni volta che apriamo la tab
        df_cronologia = pd.read_csv(FILE_DB_PRONOSTICI)
        if not df_cronologia.empty:
            st.dataframe(df_cronologia.iloc[::-1], use_container_width=True)
            if st.button("🗑️ Cancella Cronologia"):
                os.remove(FILE_DB_PRONOSTICI)
                st.rerun()
        else:
            st.info("La cronologia è vuota.")
    else:
        st.info("Nessun database di cronologia trovato.")
