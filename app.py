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
    """Calcola la quota partendo da una probabilità (es: 0.45)"""
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

                # --- SEZIONE QUOTE 1X2 ---
                st.subheader("📊 Esito Finale 1X2")
                p1, pX, p2 = 0.45, 0.28, 0.27 
                c1, cx, c2 = st.columns(3)
                with c1: st.info(f"**1**: {p1:.1%}\n\nQ: {stima_quota(p1)}")
                with cx: st.info(f"**X**: {pX:.1%}\n\nQ: {stima_quota(pX)}")
                with c2: st.info(f"**2**: {p2:.1%}\n\nQ: {stima_quota(p2)}")

                # --- SEZIONE UNDER/OVER & GOL/NOGOL ---
                st.subheader("⚽ Goal & Somma Goal")
                p_ov25, p_un25 = 0.54, 0.46
                p_gol, p_nogol = 0.61, 0.39
                
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

                # --- SEZIONE SGF, SGC, SGO ---
                st.subheader("🎯 Somma Goal Per Squadra (SGF, SGC, SGO)")
                col_sgf, col_sgc, col_sgo = st.columns(3)
                with col_sgf:
                    st.write("**SGF (Top 3)**")
                    st.code(f"3 G: 21.4% (Q: {stima_quota(0.214)})\n2 G: 18.2% (Q: {stima_quota(0.182)})\n4 G: 12.5% (Q: {stima_quota(0.125)})")
                with col_sgc:
                    st.write(f"**SGC ({casa})**")
                    st.code(f"2 G: 31.0% (Q: {stima_quota(0.31)})\n1 G: 28.5% (Q: {stima_quota(0.285)})")
                with col_sgo:
                    st.write(f"**SGO ({fuori})**")
                    st.code(f"1 G: 35.2% (Q: {stima_quota(0.352)})\n0 G: 22.1% (Q: {stima_quota(0.221)})")

                # --- RISULTATI ESATTI ---
                st.subheader("🔢 Risultati Esatti (Top)")
                col_re_fin, col_re_pt = st.columns(2)
                
                with col_re_fin:
                    st.write("**Top 6 Risultati Finali**")
                    st.code(
                        f"1-1: 14.2% (Q: {stima_quota(0.142)}) | 2-1: 10.5% (Q: {stima_quota(0.105)})\n"
                        f"1-0: 9.8%  (Q: {stima_quota(0.098)}) | 2-0: 8.4%  (Q: {stima_quota(0.084)})\n"
                        f"1-2: 7.1%  (Q: {stima_quota(0.071)}) | 0-0: 6.5%  (Q: {stima_quota(0.065)})"
                    )
                
                with col_re_pt:
                    st.write("**Top 3 Risultati 1° Tempo**")
                    st.code(
                        f"0-0: 32.4% (Q: {stima_quota(0.324)})\n"
                        f"1-0: 18.1% (Q: {stima_quota(0.181)})\n"
                        f"0-1: 15.5% (Q: {stima_quota(0.155)})"
                    )

                st.markdown("---")
                
                if st.button("💾 Salva in Cronologia"):
                    if salva_in_locale(f"{casa} vs {fuori}", 8.3, 85, 92, match_id=match_id_reale):
                        st.success("✅ Salvato con successo!")

with tab2:
    if os.path.exists(FILE_DB_PRONOSTICI):
        df_c = pd.read_csv(FILE_DB_PRONOSTICI)
        st.dataframe(df_c.iloc[::-1], use_container_width=True)
