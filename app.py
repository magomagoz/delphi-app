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
            "Fiducia nel pronostico": f"{fiducia}%",
            "Affidabilità dei dati": f"{affidabilita}%",
            "1X2": p1x2,
            "U/O 2.5": uo,
            "G/NG": gng,
            "SGF": sgf,
            "SGC": sgc,
            "SGO": sgo,
            "Top 6 Risultati Esatti Finali": re_fin,
            "Top 3 Risultati Esatti 1°T": re_pt,
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
tab1, tab2 = st.tabs(["🎯 Analisi del Match", "📜 Cronologia e Statistiche"])

with tab1:
    search_query = st.text_input("Cerca Squadra:", placeholder="Inserisci nome...")
    
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

# ==========================================
# 2. FUNZIONI CORE (MATEMATICA E LOGICA)
# ==========================================
def poisson_probability(k, exp):
    """Calcola la probabilità di Poisson per k eventi con media exp."""
    if exp <= 0: return 0
    return (exp**k * math.exp(-exp)) / math.factorial(k)

def stima_quota(prob):
    """Converte probabilità in quota decimale."""
    if prob <= 0.001: return 99.00
    return round(1 / prob, 2)

def analizza_severita_arbitro(df, nome_arbitro):
    if not nome_arbitro or nome_arbitro == 'N.D.' or df.empty: return 1.0
    partite_arbitro = df[df['Referee'].astype(str).str.contains(str(nome_arbitro), na=False, case=False)]
    if len(partite_arbitro) < 2: return 1.0
    media_gol_arbitro = (partite_arbitro['FTHG'] + partite_arbitro['FTAG']).mean()
    media_gol_totale = (df['FTHG'] + df['FTAG']).mean()
    return round(max(0.8, min(1.3, media_gol_totale / media_gol_arbitro)), 2)

def calcola_late_goal_index(casa, fuori):
    val = (len(casa) + len(fuori)) % 15
    return round(val * 0.12, 2)
                  
        if st.button("💾 Salva in Cronologia"):
            success = salva_completo_in_locale(
                f"{casa} vs {fuori}", fid_val, aff_val, 
                txt_1x2_cron, txt_uo_cron, txt_gng_cron, 
                txt_sgf_cron, txt_sgc_cron, txt_sgo_cron, 
                txt_re_fin_cron, txt_re_pt_cron, match_id=mid
            )
            if success:
                st.success("✅ Salvato in Cronbologia!")
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

# ==========================================
# 4. LOGICA DI ANALISI API E MATCH
# ==========================================
def aggiorna_con_api():
    headers = {'X-Auth-Token': API_TOKEN}
    leagues = {'SA':'Serie A', 'PL':'Premier League', 'PD':'La Liga', 'BL1':'Bundesliga', 'CL':'Champions League'}
    st.info("Aggiornamento database in corso...")
    rows = []
    for code, name in leagues.items():
        r = requests.get(f"https://api.football-data.org/v4/competitions/{code}/matches", headers=headers)
        if r.status_code == 200:
            for m in r.json().get('matches', []):
                home = m['homeTeam']['shortName'] or m['homeTeam']['name']
                away = m['awayTeam']['shortName'] or m['awayTeam']['name']
                ref = m['referees'][0].get('name', 'N.D.') if m.get('referees') else 'N.D.'
                rows.append([name, m['utcDate'], home, away, m['status'], m['score']['fullTime']['home'], m['score']['fullTime']['away'], ref])
    pd.DataFrame(rows, columns=['League', 'Date', 'HomeTeam', 'AwayTeam', 'Status', 'FTHG', 'FTAG', 'Referee']).to_csv(FILE_DB, index=False)
    st.success("Database pronto!")

def calcola_pronostico_streamlit(nome_input):
    if not os.path.exists(FILE_DB):
        st.error("Aggiorna il database nella sezione Gestione."); return
    
    df = pd.read_csv(FILE_DB)
    match = df[df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY']) & 
               (df['HomeTeam'].str.contains(nome_input, case=False, na=False) | 
                df['AwayTeam'].str.contains(nome_input, case=False, na=False))]
    
    if match.empty:
        st.warning("Nessun match imminente trovato."); return

    m = match.iloc[0]
    casa, fuori = m['HomeTeam'], m['AwayTeam']
    giocate = df[df['Status'] == 'FINISHED'].copy()
    
    # Calcolo Medie
    arbitro = m.get('Referee', 'N.D.')
    molt_arbitro = analizza_severita_arbitro(giocate, arbitro)
    avg_g = max(1.1, giocate['FTHG'].mean() if not giocate.empty else 1.3)
    
    def get_stats(team):
        t = giocate[(giocate['HomeTeam'] == team) | (giocate['AwayTeam'] == team)].tail(10)
        if t.empty: return 1.3, 1.3
        att = t.apply(lambda r: float(r['FTHG']) if r['HomeTeam']==team else float(r['FTAG']), axis=1).mean()
        dif = t.apply(lambda r: float(r['FTAG']) if r['HomeTeam']==team else float(r['FTHG']), axis=1).mean()
        return att, dif

    att_h, dif_h = get_stats(casa)
    att_a, dif_a = get_stats(fuori)
    exp_h = (att_h * dif_a / avg_g) * (2 - molt_arbitro)
    exp_a = (att_a * dif_h / avg_g) * (2 - molt_arbitro)

    # --- UI RENDERING ---
    st.markdown(f"### 🏟️ {casa} vs {fuori}")
    
    # Badge Dinamici
    fiducia_val = 82 
    affidabilita_val = 88
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""<div style="background-color: #1E7E34; color: white; padding: 10px; border-radius: 10px; text-align: center;">
        <p style="margin:0; font-size: 11px; opacity: 0.8;">🎯 FIDUCIA</p>
        <p style="margin:0; font-size: 22px; font-weight: bold;">{fiducia_val}%</p></div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div style="background-color: #1C3D5A; color: white; padding: 10px; border-radius: 10px; text-align: center;">
        <p style="margin:0; font-size: 11px; opacity: 0.8;">📊 DATI</p>
        <p style="margin:0; font-size: 22px; font-weight: bold;">{affidabilita_val}%</p></div>""", unsafe_allow_html=True)

    # --- ESITO 1X2 ---
    st.divider()
    p_1, p_x, p_2, total_p = 0, 0, 0, 0
    for i in range(6):
        for j in range(6):
            prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
            total_p += prob
            if i > j: p_1 += prob
            elif i == j: p_x += prob
            else: p_2 += prob

    c1, cx, c2 = st.columns(3)
    c1.metric("1", f"{p_1/total_p:.1%}", f"Q: {stima_quota(p_1/total_p)}")
    cx.metric("X", f"{p_x/total_p:.1%}", f"Q: {stima_quota(p_x/total_p)}")
    c2.metric("2", f"{p_2/total_p:.1%}", f"Q: {stima_quota(p_2/total_p)}")

    # Salvataggio in background
    salva_in_cronologia(f"{casa}-{fuori}", calcola_late_goal_index(casa, fuori), fiducia_val, affidabilita_val)

# ==========================================
# 5. MAIN INTERFACE
# ==========================================
st.image("banner.png")

tab1, tab2 = st.tabs(["🎯 Analisi Pro", "⚙️ Gestione"])

with tab1:
    search = st.text_input("Cerca squadra (es. Milan, Real, Arsenal):")
    if st.button("CALCOLA PRONOSTICO", type="primary"):
        if search: calcola_pronostico_streamlit(search)
    
    st.divider()
    mostra_cronologia_bella()

with tab2:
    if st.button("🌐 AGGIORNA DATABASE"):
        aggiorna_con_api()

