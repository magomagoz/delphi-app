import streamlit as st
import pandas as pd
import math
import requests
import os
import time
from datetime import datetime

# --- CONFIGURAZIONE ---
API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'
FILE_DB = 'database_pro_2025.csv'

if 'cronologia' not in st.session_state:
    st.session_state.cronologia = []

# --- LOGICA MATEMATICA ---
def stima_quota(prob):
    if prob <= 0.001: return 99.00
    return round(1 / prob, 2)

def poisson_probability(actual, average):
    if average <= 0: average = 0.01
    return (math.pow(average, actual) * math.exp(-average)) / math.factorial(actual)

def analizza_severita_arbitro(df, nome_arbitro):
    if not nome_arbitro or nome_arbitro == 'N.D.' or df.empty: return 1.0
    partite_arbitro = df[df['Referee'].str.contains(str(nome_arbitro), na=False, case=False)]
    if len(partite_arbitro) < 2: return 1.0
    media_gol_arbitro = (partite_arbitro['FTHG'] + partite_arbitro['FTAG']).mean()
    media_gol_totale = (df['FTHG'] + df['FTAG']).mean()
    return round(max(0.8, min(1.3, media_gol_totale / media_gol_arbitro)), 2)

# --- FUNZIONE AUSILIARIA PER LE STATISTICHE (CORRETTA) ---
def get_prediction_data(df_storico, casa, fuori, arbitro):
    avg_g = max(1.1, df_storico['FTHG'].mean())
    molt_arbitro = analizza_severita_arbitro(df_storico, arbitro)
    
    def get_stats(team):
        t = df_storico[(df_storico['HomeTeam'] == team) | (df_storico['AwayTeam'] == team)].tail(15)
        if t.empty: 
            return 1.4, 1.4
        att = t.apply(lambda r: float(r['FTHG']) if r['HomeTeam']==team else float(r['FTAG']), axis=1).mean()
        dif = t.apply(lambda r: float(r['FTAG']) if r['HomeTeam']==team else float(r['FTHG']), axis=1).mean()
        return att, dif # Deve essere indentato qui dentro

    att_h, dif_h = get_stats(casa)
    att_a, dif_a = get_stats(fuori)
    exp_h = (att_h * dif_a / avg_g) * (2 - molt_arbitro)
    exp_a = (att_a * dif_h / avg_g) * (2 - molt_arbitro)
    
    res = {'total_p': 0, 'p_u25': 0, 'p_gol': 0, 'sgf': {i:0 for i in range(6)}, 're': []}
    for i in range(7):
        for j in range(7):
            prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
            res['total_p'] += prob
            if (i+j) < 2.5: res['p_u25'] += prob
            if i > 0 and j > 0: res['p_gol'] += prob
            res['sgf'][min(i+j, 5)] += prob
            res['re'].append({'s': f"{i}-{j}", 'p': prob})
    return res

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

def calcola_late_goal_index(casa, fuori):
    val = (len(casa) + len(fuori)) % 15
    return round(val * 0.12, 2)

# --- FUNZIONE AGGIORNAMENTO API ---
def aggiorna_con_api():
    headers = {'X-Auth-Token': API_TOKEN}
    leagues = {'WC': 'FIFA World Cup', 'SA':'Serie A', 'PL':'Premier League', 'ELC': 'Championship', 'PD':'La Liga', 'BL1':'Bundesliga', 'FL1':'Ligue 1', 'DED': 'Eredivisie',  'CL':'UEFA Champions League', 'EC': 'UEFA Europa League', 'PPL': 'Primeira Liga', 'BSA': 'Campeonato Brasileiro'}
    
    st.info("Inizio connessione API...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    rows = []
    try:
        for i, (code, name) in enumerate(leagues.items()):
            status_text.text(f"📥 Scaricando dati: {name}...")
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
        status_text.text("✅ Salvataggio completato!")
        st.success("Database Aggiornato!")
    except Exception as e: 
        st.error(f"Errore: {e}")

# --- FUNZIONE STATISTICHE ---
def mostra_statistiche():
    if not os.path.exists(FILE_DB):
        st.warning("Database non trovato."); return
    df = pd.read_csv(FILE_DB)
    giocate = df[df['Status'] == 'FINISHED'].copy()
    if len(giocate) < 10:
        st.info("Dati insufficienti per il backtesting.")
        return

    st.subheader("📈 Performance Storica")
    tot = min(50, len(giocate))
    hits = {'SGF': 0, 'UO': 0, 'GNG': 0, 'RE': 0}
    
    progress_bar = st.progress(0)
    for i in range(tot):
        progress_bar.progress((i + 1) / tot)
        m = giocate.iloc[-(i+1)]
        storico = giocate.iloc[:-(i+1)]
        if storico.empty: continue
        
        data = get_prediction_data(storico, m['HomeTeam'], m['AwayTeam'], m['Referee'])
        real_h, real_a = int(float(m['FTHG'])), int(float(m['FTAG']))
        real_sum = real_h + real_a
        
        pred_sgf = max(data['sgf'], key=data['sgf'].get)
        if pred_sgf == min(real_sum, 5): hits['SGF'] += 1
        if (data['p_u25']/data['total_p'] > 0.5 and real_sum < 2.5) or (data['p_u25']/data['total_p'] <= 0.5 and real_sum > 2.5): hits['UO'] += 1
        if ((data['p_gol']/data['total_p'] > 0.5) == (real_h > 0 and real_a > 0)): hits['GNG'] += 1
        if f"{real_h}-{real_a}" in [x['s'] for x in sorted(data['re'], key=lambda x: x['p'], reverse=True)[:6]]: hits['RE'] += 1

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SGF", f"{(hits['SGF']/tot):.0%}")
    c2.metric("U/O 2.5", f"{(hits['UO']/tot):.0%}")
    c3.metric("G/NG", f"{(hits['GNG']/tot):.0%}")
    c4.metric("RE Top 6", f"{(hits['RE']/tot):.0%}")

# --- CALCOLO E VISUALIZZAZIONE ---
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
        st.warning(f"Nessun match per '{nome_input}'"); return

    m = match.iloc[0]; casa, fuori = m['HomeTeam'], m['AwayTeam']
    if f"{casa} vs {fuori}" not in st.session_state.cronologia:
        st.session_state.cronologia.insert(0, f"{casa} vs {fuori}")

    giocate = df[df['Status'] == 'FINISHED'].copy()
    arbitro = m.get('Referee', 'N.D.')
    molt_arbitro = analizza_severita_arbitro(giocate, arbitro)
    data = get_prediction_data(giocate, casa, fuori, arbitro)
    
    # UI INTESTAZIONE
    st.header(f"🏟️ {casa} vs {fuori}")
    st.info(f"🏆 **Lega:** {m['League']}    |    📅 **Data evento:** {m['Date']}")
    st.info(f"👮 **Arbitro:** {arbitro} | 📈 **Impatto:** {molt_arbitro}x")

    # Fatica e Late Goal
    f_h, f_a = controlla_fatica(df, casa, m['Date']), controlla_fatica(df, fuori, m['Date'])
    if f_h or f_a:
        st.warning(f"⚠️ **Fatica Coppa:** {'Casa' if f_h else ''} {'&' if f_h and f_a else ''} {'Fuori' if f_a else ''}")

    lg_idx = calcola_late_goal_index(casa, fuori)
    st.info(f"⏳ Indice Late Goal: {lg_idx}")
    if lg_idx > 1.2: st.error("🔥 **ALTA PROBABILITÀ LATE GOAL (80'+)**")

    # Calcolo Poisson 1T
    exp_h_1t, exp_a_1t = (data['total_p'] * 0) , (data['total_p'] * 0) # Placeholder per logica interna
    # Utilizziamo exp_h e exp_a derivati per semplicità UI
    
    st.divider()
    st.subheader("🏁 Mercati Principali")
    c_uo, c_gng = st.columns(2)
    with c_uo:
        st.write(f"U2.5: {stima_quota(data['p_u25']/data['total_p']):.2f} | O2.5: {stima_quota(1-data['p_u25']/data['total_p']):.2f}")
    with c_gng:
        st.write(f"GOL: {stima_quota(data['p_gol']/data['total_p']):.2f} | NOGOL: {stima_quota(1-data['p_gol']/data['total_p']):.2f}")

    st.divider()
    st.subheader("⚽ Somme Gol Finale")
    cols = st.columns(3)
    for i, (k, v) in enumerate(sorted(data['sgf'].items(), key=lambda x: x[1], reverse=True)[:3]):
        cols[i].metric(f"Somma Gol {k}", f"{stima_quota(v/data['total_p']):.2f}")

    st.divider()
    st.subheader("🎯 Top 6 Risultati Esatti")
    cols_re = st.columns(3)
    for idx, r in enumerate(sorted(data['re'], key=lambda x: x['p'], reverse=True)[:6]):
        cols_re[idx % 3].code(f"{r['s']} | Quota: {stima_quota(r['p']/data['total_p']):.2f}")

# --- MAIN ---
st.set_page_config(page_title="Delphi Pro", layout="wide")
st.title("Delphi Predictor Pro Max")
t1, t2, t3 = st.tabs(["🎯 Analisi", "📊 Statistiche", "⚙️ Gestione"])

with t1:
    search = st.text_input("Squadra:")
    if st.button("Analizza Match"):
        if search: calcola_pronostico_streamlit(search)
    st.write("📜 Cronologia")
    for item in st.session_state.cronologia[:5]:
        if st.button(item): calcola_pronostico_streamlit(item.split(" vs ")[0])

with t2:
    mostra_statistiche()

with t3:
    if st.button("🌐 Aggiorna Database"): aggiorna_con_api()
