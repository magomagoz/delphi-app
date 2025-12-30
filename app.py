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
            "Top 6 RE Finali", "Top 3 RE 1°T", "Risultato Reale", "Stato"
        ]
        df = pd.DataFrame(columns=columns)
        df.to_csv(FILE_DB_PRONOSTICI, index=False)

inizializza_db()

def salva_completo_in_locale(match, fid, aff, p1x2, uo, gng, sgf, sgc, sgo, re_fin, re_pt, match_id=None):
    try:
        fuso_ita = pytz.timezone('Europe/Rome')
        adesso = datetime.now(fuso_ita)
        
        nuova_riga = {
            "Data": adesso.strftime("%d/%m/%Y"),
            "Ora": adesso.strftime("%H:%M"),
            "Partita": match,
            "Fiducia": f"{fid}%",
            "Affidabilità": f"{aff}%",
            "1X2": p1x2,
            "U/O 2.5": uo,
            "G/NG": gng,
            "SGF": sgf,
            "SGC": sgc,
            "SGO": sgo,
            "Top 6 RE Finali": re_fin,
            "Top 3 RE 1°T": re_pt,
            "Risultato Reale": "N/D", # Campo per il controllo futuro
            "Stato": "In attesa"
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

# --- 3. LOGICA DI COLORAZIONE ---
def colora_vincenti(val):
    """Colora di verde se lo stato è 'Vincente'"""
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
        casa, fuori, mid = str(m['HomeTeam']), str(m['AwayTeam']), m.get('ID', "N/A")
        
        st.markdown(f"<h2 style='text-align: center;'>🏟️ {casa} vs {fuori}</h2>", unsafe_allow_html=True)

        # UI Tasti
        c_fid, c_aff = st.columns(2)
        fid_v, aff_v = 85, 92
        c_fid.markdown(f"<div style='background-color:#2e7d32;color:white;padding:10px;border-radius:10px;text-align:center;'>🎯 FIDUCIA: {fid_v}%</div>", unsafe_allow_html=True)
        c_aff.markdown(f"<div style='background-color:#1565c0;color:white;padding:10px;border-radius:10px;text-align:center;'>📊 AFFIDABILITÀ: {aff_v}%</div>", unsafe_allow_html=True)

        # Estrazione Valori per Cronologia (Solo i richiesti)
        p1, pX, p2 = 0.45, 0.28, 0.27
        res_1x2 = "1" # Il primo (più probabile)
        
        st.subheader("📊 Esito Finale 1X2")
        c1, cx, c2 = st.columns(3)
        c1.info(f"**1**: {p1:.1%}\nQ: {stima_quota(p1)}")
        cx.info(f"**X**: {pX:.1%}\nQ: {stima_quota(pX)}")
        c2.info(f"**2**: {p2:.1%}\nQ: {stima_quota(p2)}")

        p_ov, p_un, p_gol, p_nogol = 0.54, 0.46, 0.61, 0.39
        res_uo = "OVER 2.5" if p_ov > p_un else "UNDER 2.5"
        res_gng = "GOL" if p_gol > p_nogol else "NO GOL"

        st.subheader("⚽ Goal & Somma Goal")
        col_uo, col_gn = st.columns(2)
        with col_uo:
            st.write("**U/O 2.5**")
            u1, u2 = st.columns(2)
            u1.warning(f"**U**: {p_un:.1%}\nQ:{stima_quota(p_un)}")
            u2.warning(f"**O**: {p_ov:.1%}\nQ:{stima_quota(p_ov)}")
        with col_gn:
            st.write("**G/NG**")
            g1, g2 = st.columns(2)
            g1.success(f"**GOL**: {p_gol:.1%}\nQ:{stima_quota(p_gol)}")
            g2.success(f"**NO**: {p_nogol:.1%}\nQ:{stima_quota(p_nogol)}")

        res_sgf = "3, 2, 4" # Tutti e tre
        res_sgc = "2, 1"    # Primi due
        res_sgo = "1, 0"    # Primi due

        st.subheader("🎯 Somma Goal")
        csf, csc, cso = st.columns(3)
        csf.code(f"SGF: 3G, 2G, 4G")
        csc.code(f"SGC: 2G, 1G")
        cso.code(f"SGO: 1G, 0G")

        res_re_fin = "1-1, 2-1, 1-0, 2-0, 1-2, 0-0" # Tutti e 6
        res_re_pt = "0-0, 1-0, 0-1"                # Primi 3

        st.subheader("🔢 Risultati Esatti")
        cref, crept = st.columns(2)
        cref.code(f"FIN: {res_re_fin}")
        crept.code(f"1°T: {res_re_pt}")

        st.markdown("---")
        if st.button("💾 Salva in Cronologia"):
            if salva_completo_in_locale(f"{casa}-{fuori}", fid_v, aff_v, res_1x2, res_uo, res_gng, res_sgf, res_sgc, res_sgo, res_re_fin, res_re_pt, mid):
                st.success("✅ Salvato!")
                time.sleep(0.5)
                st.rerun()

with tab2:
    st.subheader("📊 Registro Analisi")
    if os.path.exists(FILE_DB_PRONOSTICI):
        df_cron = pd.read_csv(FILE_DB_PRONOSTICI)
        if not df_cron.empty:
            # Applichiamo lo stile: se lo 'Stato' è 'Vincente', colora la riga
            styler = df_cron.iloc[::-1].style.applymap(colora_vincenti, subset=['Stato'])
            st.dataframe(styler, use_container_width=True)
            
            st.markdown("---")
            if st.button("🗑️ Svuota Tutto"):
                st.session_state['confirm_del'] = True
            
            if st.session_state.get('confirm_del'):
                st.warning("⚠️ Cancellare tutta la cronologia?")
                cy, cn = st.columns(2)
                if cy.button("✅ SÌ"):
                    os.remove(FILE_DB_PRONOSTICI)
                    st.session_state['confirm_del'] = False
                    st.rerun()
                if cn.button("❌ NO"):
                    st.session_state['confirm_del'] = False
                    st.rerun()
        else:
            st.info("Cronologia vuota.")
