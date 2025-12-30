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
        columns = [
            "Data", "Ora", "Partita", "Fiducia", "Affidabilità", 
            "1X2", "U/O 2.5", "G/NG", "SGF", "SGC", "SGO", 
            "Top 6 RE Finali", "Top 3 RE 1°T", "Match_ID", "Stato"
        ]
        df = pd.DataFrame(columns=columns)
        df.to_csv(FILE_DB_PRONOSTICI, index=False)

inizializza_db()

def salva_completo_in_locale(match, fiducia, affidabilita, p1x2, uo, gng, sgf, sgc, sgo, re_fin, re_pt, match_id=None):
    try:
        fuso_ita = pytz.timezone('Europe/Rome')
        adesso = datetime.now(fuso_ita)
        
        nuova_riga = {
            "Data": adesso.strftime("%d/%m/%Y"),
            "Ora": adesso.strftime("%H:%M"),
            "Partita": match,
            "Fiducia": f"{fiducia}%",
            "Affidabilità": f"{affidabilita}%",
            "1X2": p1x2,
            "U/O 2.5": uo,
            "G/NG": gng,
            "SGF": sgf,
            "SGC": sgc,
            "SGO": sgo,
            "Top 6 RE Finali": re_fin,
            "Top 3 RE 1°T": re_pt,
            "Match_ID": match_id if match_id and str(match_id) != "nan" else "N/A",
            "Stato": "In attesa" # Cambiare in "Vincente" per attivare il verde
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

# --- 3. LOGICA COLORAZIONE ---
def colora_vincenti(val):
    color = 'background-color: #d4edda; color: #155724' if val == "Vincente" else ''
    return color

# --- 4. BANNER ---
if os.path.exists("banner.png"):
    st.image("banner.png", use_container_width=True)
else:
    st.markdown("<h1 style='text-align: center;'>⚽ Delphi Predictor Pro</h1>", unsafe_allow_html=True)

# --- 5. TABS ---
tab1, tab2 = st.tabs(["🎯 Analisi Match", "📜 Cronologia e Statistiche"])

with tab1:
    search_query = st.text_input("Cerca Squadra (es: Lazio):", placeholder="Inserisci nome...")
    
    if st.button("Analizza Match", type="primary"):
        if not os.path.exists(FILE_DB_CALCIO):
            st.error("⚠️ Database non trovato.")
        else:
            df = pd.read_csv(FILE_DB_CALCIO)
            match_found = df[df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED']) & 
                            (df['HomeTeam'].str.contains(search_query, case=False, na=False) | 
                             df['AwayTeam'].str.contains(search_query, case=False, na=False))]
            
            if not match_found.empty:
                st.session_state['current_match'] = match_found.iloc[0].to_dict()
            else:
                st.session_state['current_match'] = None
                st.warning("Nessun match trovato.")

    if 'current_match' in st.session_state and st.session_state['current_match'] is not None:
        m = st.session_state['current_match']
        casa = str(m['HomeTeam'])
        fuori = str(m['AwayTeam'])
        mid = m.get('ID', "N/A")
        
        st.markdown(f"<h2 style='text-align: center;'>🏟️ {casa} vs {fuori}</h2>", unsafe_allow_html=True)

        c_btn1, c_btn2 = st.columns(2)
        fid_val, aff_val = 85, 92
        c_btn1.markdown(f"<div style='background-color: #2e7d32; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold; border: 1px solid white;'>🎯 FIDUCIA: {fid_val}%</div>", unsafe_allow_html=True)
        c_btn2.markdown(f"<div style='background-color: #1565c0; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold; border: 1px solid white;'>📊 AFFIDABILITÀ: {aff_val}%</div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # --- PREPARAZIONE DATI PULITI PER CRONOLOGIA (SENZA %) ---
        p1, pX, p2 = 0.45, 0.28, 0.27
        txt_1x2_cron = "1" # Solo il primo
        
        st.subheader("📊 Esito Finale 1X2")
        c1, cx, c2 = st.columns(3)
        c1.info(f"**1**: {p1:.1%}\nQ: {stima_quota(p1)}")
        cx.info(f"**X**: {pX:.1%}\nQ: {stima_quota(pX)}")
        c2.info(f"**2**: {p2:.1%}\nQ: {stima_quota(p2)}")

        p_ov25, p_un25, p_gol, p_nogol = 0.54, 0.46, 0.61, 0.39
        txt_uo_cron = "OVER 2.5" if p_ov25 > p_un25 else "UNDER 2.5"
        txt_gng_cron = "GOL" if p_gol > p_nogol else "NO GOL"

        st.subheader("⚽ Goal & Somma Goal")
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

        txt_sgf_cron = "3, 2, 4" # Tutti e tre
        txt_sgc_cron = "2, 1"    # Primi due
        txt_sgo_cron = "1, 0"    # Primi due

        st.subheader("🎯 Somma Goal Per Squadra")
        col_sgf, col_sgc, col_sgo = st.columns(3)
        with col_sgf:
            st.write("**SGF (Top 3)**")
            st.code(f"3 G: 21% Q:{stima_quota(0.21)}\n2 G: 18% Q:{stima_quota(0.18)}\n4 G: 12% Q:{stima_quota(0.12)}")
        with col_sgc:
            st.write(f"**SGC**")
            st.code(f"2 G: 31% Q:{stima_quota(0.31)}\n1 G: 28% Q:{stima_quota(0.28)}")
        with col_sgo:
            st.write(f"**SGO**")
            st.code(f"1 G: 35% Q:{stima_quota(0.35)}\n0 G: 22% Q:{stima_quota(0.22)}")

        txt_re_fin_cron = "1-1, 2-1, 1-0, 2-0, 1-2, 0-0" # Tutti e 6
        txt_re_pt_cron = "0-0, 1-0, 0-1"                # Primi 3

        st.subheader("🔢 Risultati Esatti")
        col_re_f, col_re_p = st.columns(2)
        with col_re_f:
            st.write("**Top 6 Finali**")
            st.code(f"1-1: 14% Q:7.14 | 2-1: 11% Q:9.09\n1-0: 10% Q:10.0 | 2-0: 09% Q:11.11\n1-2: 07% Q:14.29 | 0-0: 06% Q:16.67")
        with col_re_p:
            st.write("**Top 3 1° Tempo**")
            st.code(f"0-0: 32% Q:3.12\n1-0: 18% Q:5.56\n0-1: 15% Q:6.67")

        st.markdown("---")
        
        if st.button("💾 Salva in Cronologia"):
            success = salva_completo_in_locale(
                f"{casa} vs {fuori}", fid_val, aff_val, 
                txt_1x2_cron, txt_uo_cron, txt_gng_cron, 
                txt_sgf_cron, txt_sgc_cron, txt_sgo_cron, 
                txt_re_fin_cron, txt_re_pt_cron, match_id=mid
            )
            if success:
                st.success("✅ Salvato senza percentuali!")
                time.sleep(1)
                st.rerun()

with tab2:
    st.subheader("📊 Archivio Pronostici")
    if os.path.exists(FILE_DB_PRONOSTICI):
        df_cronologia = pd.read_csv(FILE_DB_PRONOSTICI)
        if not df_cronologia.empty:
            # Applica lo stile verde se lo Stato è 'Vincente'
            styled_df = df_cronologia.iloc[::-1].style.applymap(colora_vincenti, subset=['Stato'])
            st.dataframe(styled_df, use_container_width=True)
            
            st.markdown("---")
            if st.button("🗑️ Svuota Tutto", type="secondary"):
                st.session_state['confirm_delete'] = True
            
            if st.session_state.get('confirm_delete'):
                st.warning("⚠️ Confermi la cancellazione?")
                cy, cn = st.columns(2)
                if cy.button("✅ SÌ", type="primary"):
                    os.remove(FILE_DB_PRONOSTICI)
                    st.session_state['confirm_delete'] = False
                    st.rerun()
                if cn.button("❌ NO"):
                    st.session_state['confirm_delete'] = False
                    st.rerun()
        else:
            st.info("Cronologia vuota.")
