import streamlit as st
import pandas as pd
import math
import requests
import os
import time
from datetime import datetime
import pytz
from streamlit_gsheets import GSheetsConnection

# 1. CONFIGURAZIONE E CONNESSIONI
st.set_page_config(page_title="Delphi Predictor Pro", layout="centered")

# Inizializzazione sicura della connessione
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Errore di connessione a Google Sheets: {e}")
    conn = None

API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'
FILE_DB = 'database_pro_2025.csv'

# ==========================================
# 2. FUNZIONI CORE (MATEMATICA E LOGICA)
# ==========================================
def poisson_probability(k, exp):
    """Calcola la probabilità di Poisson"""
    if exp <= 0: exp = 0.01
    return (exp**k * math.exp(-exp)) / math.factorial(k)

def stima_quota(prob):
    """Converte probabilità in quota"""
    if prob <= 0.001: return 99.00
    return round(1 / prob, 2)

def analizza_severita_arbitro(df, nome_arbitro):
    if not nome_arbitro or nome_arbitro == 'N.D.' or df.empty: return 1.0
    partite_arbitro = df[df['Referee'].str.contains(str(nome_arbitro), na=False, case=False)]
    if len(partite_arbitro) < 2: return 1.0
    media_gol_arbitro = (partite_arbitro['FTHG'] + partite_arbitro['FTAG']).mean()
    media_gol_totale = (df['FTHG'] + df['FTAG']).mean()
    return round(max(0.8, min(1.3, media_gol_totale / media_gol_arbitro)), 2)

def calcola_late_goal_index(casa, fuori):
    val = (len(casa) + len(fuori)) % 15
    return round(val * 0.12, 2)

def controlla_fatica(df, squadra, data_match):
    try:
        data_m = pd.to_datetime(data_match)
        storico = df[(df['Status'] == 'FINISHED') & ((df['HomeTeam'] == squadra) | (df['AwayTeam'] == squadra))].copy()
        storico['Date'] = pd.to_datetime(storico['Date'])
        ultima_partita = storico[storico['Date'] < data_m]['Date'].max()
        if pd.notnull(ultima_partita) and (data_m - ultima_partita).days <= 4:
            return True
    except: pass
    return False

# ==========================================
# 3. GESTIONE CRONOLOGIA (GOOGLE SHEETS)
# ==========================================
def salva_in_cronologia(match, lg_idx, fiducia, dati):
    try:
        # Leggiamo i dati esistenti
        existing_data = conn.read(worksheet="Cronologia_Delphi", ttl=0)
        
        # Prepariamo la nuova riga con data e ora italiana
        fuso_ita = pytz.timezone('Europe/Rome')
        adesso = datetime.now(fuso_ita)
        
        nuova_riga = pd.DataFrame([{
            "Data": adesso.strftime("%d/%m/%Y"),
            "Ora": adesso.strftime("%H:%M"),
            "Partita": match,
            "Indice LG": lg_idx,
            "Fiducia": f"{fiducia}%",
            "Dati": f"{dati}%"
        }])
        
        # Uniamo e salviamo
        updated_df = pd.concat([existing_data, nuova_riga], ignore_index=True)
        conn.update(worksheet="Cronologia", data=updated_df)
        st.toast("✅ Pronostico salvato in cronologia!")
    except Exception as e:
        st.sidebar.error(f"Errore salvataggio: {e}")

def mostra_cronologia_bella():
    try:
        df = conn.read(worksheet="Cronologia", ttl=0)
        if df is not None and not df.empty:
            st.subheader("📜 Ultimi Pronostici Salvati")
            # Mostra gli ultimi 10 risultati (dal più recente)
            for i, row in df.tail(10).iloc[::-1].iterrows():
                st.markdown(f"""
                <div style="background-color: #262730; padding: 12px; border-radius: 10px; border-left: 5px solid #1E7E34; margin-bottom: 10px;">
                    <span style="font-size: 11px; color: #888;">{row['Data']} ore {row['Ora']}</span><br>
                    <b style="font-size: 16px;">{row['Partita']}</b><br>
                    <span style="color: #00FF00;">🎯 Fiducia: {row['Fiducia']}</span> | <span style="color: #007BFF;">📊 Dati: {row['Dati']}</span>
                </div>
                """, unsafe_allow_html=True)
    except:
        st.info("Cronologia al momento non disponibile.")

# ==========================================
# 4. LOGICA API E ANALISI
# ==========================================
def aggiorna_con_api():
    headers = {'X-Auth-Token': API_TOKEN}
    leagues = {'WC': 'FIFA World Cup', 'SA':'Serie A', 'PL':'Premier League', 'ELC': 'Championship', 'PD':'La Liga', 'BL1':'Bundesliga', 'FL1':'Ligue 1', 'DED': 'Eredivisie',  'CL':'UEFA Champions League', 'EC': 'UEFA Europa League', 'PPL': 'Primeira Liga', 'BSA': 'Campeonato Brasileiro'}
    
    st.info("Inizio connessione API...")
    progress_bar = st.progress(0)
    rows = []
    try:
        for i, (code, name) in enumerate(leagues.items()):
            r = requests.get(f"https://api.football-data.org/v4/competitions/{code}/matches", headers=headers, timeout=10)
            if r.status_code == 200:
                for m in r.json().get('matches', []):
                    home = m['homeTeam']['shortName'] or m['homeTeam']['name']
                    away = m['awayTeam']['shortName'] or m['awayTeam']['name']
                    ref = m['referees'][0].get('name', 'N.D.') if m.get('referees') else 'N.D.'
                    rows.append([name, m['utcDate'][:10], home, away, m['status'], m['score']['fullTime']['home'], m['score']['fullTime']['away'], ref])
            time.sleep(1.2)
            progress_bar.progress((i + 1) / len(leagues))
        
        pd.DataFrame(rows, columns=['League', 'Date', 'HomeTeam', 'AwayTeam', 'Status', 'FTHG', 'FTAG', 'Referee']).to_csv(FILE_DB, index=False)
        st.success("Database Aggiornato!")
    except Exception as e: 
        st.error(f"Errore API: {e}")

def calcola_pronostico_streamlit(nome_input):
    if not os.path.exists(FILE_DB):
        st.error("Database non trovato."); return
    
    df = pd.read_csv(FILE_DB)
    df['FTHG'] = pd.to_numeric(df['FTHG'], errors='coerce').fillna(0)
    df['FTAG'] = pd.to_numeric(df['FTAG'], errors='coerce').fillna(0)
    
    match = df[df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED']) & 
               (df['HomeTeam'].str.contains(nome_input, case=False, na=False) | 
                df['AwayTeam'].str.contains(nome_input, case=False, na=False))]
    
    if match.empty:
        st.warning(f"Nessun match trovato per '{nome_input}'"); return

    m = match.iloc[0]
    casa, fuori = m['HomeTeam'], m['AwayTeam']
    giocate = df[df['Status'] == 'FINISHED'].copy()
    arbitro = m.get('Referee', 'N.D.')
    molt_arbitro = analizza_severita_arbitro(giocate, arbitro)
    
    # Poisson Medie
    avg_g = max(1.1, giocate['FTHG'].mean() if not giocate.empty else 1.3)
    def get_stats(team):
        t = giocate[(giocate['HomeTeam'] == team) | (giocate['AwayTeam'] == team)].tail(15)
        if t.empty: return 1.4, 1.4
        att = t.apply(lambda r: float(r['FTHG']) if r['HomeTeam']==team else float(r['FTAG']), axis=1).mean()
        dif = t.apply(lambda r: float(r['FTAG']) if r['HomeTeam']==team else float(r['FTHG']), axis=1).mean()
        return att, dif

    att_h, dif_h = get_stats(casa)
    att_a, dif_a = get_stats(fuori)
    exp_h = (att_h * dif_a / avg_g) * (2 - molt_arbitro)
    exp_a = (att_a * dif_h / avg_g) * (2 - molt_arbitro)

    # UI RENDERING
    st.header(f"🏟️ {casa} vs {fuori}")
    
    # Calcolo Fiducia e Dati (Esempio logico)
    fiducia_val = 85
    affidabilita_val = 92
    
    col_fid, col_aff = st.columns(2)
    with col_fid:
        color_fid = "#1E7E34" if fiducia_val >= 80 else "#CC9900"
        st.markdown(f'<div style="background-color: {color_fid}; color: white; padding: 10px; border-radius: 10px; text-align: center;"><b>🎯 FIDUCIA: {fiducia_val}%</b></div>', unsafe_allow_html=True)
    with col_aff:
        st.markdown(f'<div style="background-color: #1C3D5A; color: white; padding: 10px; border-radius: 10px; text-align: center;"><b>📊 DATI: {affidabilita_val}%</b></div>', unsafe_allow_html=True)

    # --- CALCOLO 1X2 ---
    st.divider()
    p_1, p_x, p_2, total_p = 0, 0, 0, 0
    re_finali = []
    for i in range(7):
        for j in range(7):
            prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
            total_p += prob
            if i > j: p_1 += prob
            elif i == j: p_x += prob
            else: p_2 += prob
            re_finali.append({'s': f"{i}-{j}", 'p': prob})

    c1, cx, c2 = st.columns(3)
    c1.info(f"**1**: {p_1/total_p:.1%}\n\nQ: {stima_quota(p_1/total_p)}")
    cx.info(f"**X**: {p_x/total_p:.1%}\n\nQ: {stima_quota(p_x/total_p)}")
    c2.info(f"**2**: {p_2/total_p:.1%}\n\nQ: {stima_quota(p_2/total_p)}")

    # SALVATAGGIO AUTOMATICO IN CRONOLOGIA
    lg_idx = calcola_late_goal_index(casa, fuori)
    salva_in_cronologia(f"{casa}-{fuori}", lg_idx, fiducia_val, affidabilita_val)

# ==========================================
# 5. MAIN APP INTERFACE
# ==========================================
st.image("banner.png")

tab_analisi, tab_gestione = st.tabs(["🎯 **Analisi Match**", "⚙️ **Gestione**"])

with tab_analisi:
    search_query = st.text_input("**Inserisci nome squadra:**")
    if st.button("**Analizza Match**", type="primary"):
        if search_query: 
            calcola_pronostico_streamlit(search_query)
    
    st.divider()
    mostra_cronologia_bella()

with tab_gestione:
    if st.button("🌐 **Aggiorna Database API**"): 
        aggiorna_con_api()
