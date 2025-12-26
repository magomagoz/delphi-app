import streamlit as st
import pandas as pd
import math
import requests
import os
import time
from datetime import datetime

# --- CONFIGURAZIONE E LOGICA (Invariate) ---
API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'
FILE_DB = 'database_pro_2025.csv'

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

# --- FUNZIONE AGGIORNAMENTO API (Invariata) ---
def aggiorna_con_api():
    headers = {'X-Auth-Token': API_TOKEN}
    leagues = {'WC': 'World Cup', 'SA':'Serie A', 'PL':'Premier League', 'PD':'La Liga', 'BL1':'Bundesliga', 'FL1':'Ligue 1', 'CL':'Champions League'}
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
    except Exception as e: st.error(f"Errore: {e}")

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
    giocate = df[df['Status'] == 'FINISHED'].copy()
    arbitro = m.get('Referee', 'N.D.')
    molt_arbitro = analizza_severita_arbitro(giocate, arbitro)
    avg_g = max(1.1, giocate['FTHG'].mean())

    def get_stats(team):
        t = giocate[(giocate['HomeTeam'] == team) | (giocate['AwayTeam'] == team)].tail(15)
        if t.empty: return 1.4, 1.4
        att = t.apply(lambda r: float(r['FTHG']) if r['HomeTeam']==team else float(r['FTAG']), axis=1).mean()
        dif = t.apply(lambda r: float(r['FTAG']) if r['HomeTeam']==team else float(r['FTHG']), axis=1).mean()
        return att, dif

    att_h, dif_h = get_stats(casa); att_a, dif_a = get_stats(fuori)
    exp_h = (att_h * dif_a / avg_g) * (2 - molt_arbitro)
    exp_a = (att_a * dif_h / avg_g) * (2 - molt_arbitro)

    # Poisson
    p1, px, p2, total_p = 0, 0, 0, 0
    p_u25, p_gol = 0, 0
    sgf, sgc, sgo = {i:0 for i in range(6)}, {i:0 for i in range(6)}, {i:0 for i in range(6)}
    
    for i in range(7):
        for j in range(7):
            prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
            total_p += prob
            if i > j: p1 += prob
            elif i == j: px += prob
            else: p2 += prob
            if (i+j) < 2.5: p_u25 += prob
            if i > 0 and j > 0: p_gol += prob
            sgf[min(i+j, 5)] += prob
            sgc[min(i, 5)] += prob
            sgo[min(j, 5)] += prob

    top_sgf = sorted(sgf.items(), key=lambda x: x[1], reverse=True)[:3]
    top_sgc = sorted(sgc.items(), key=lambda x: x[1], reverse=True)[:2]
    top_sgo = sorted(sgo.items(), key=lambda x: x[1], reverse=True)[:2]

    # --- UI ---
    st.header(f"🏟️ {casa} vs {fuori}")
    st.info(f"👮 **Arbitro:** {arbitro} | 📈 **Impatto:** {molt_arbitro}x")

    st.subheader("⚽ Analisi Somme Gol")
    c_sgf, c_sgc, c_sgo = st.columns(3)

    with c_sgf:
        st.write("**Top 3 SGF**")
        for i, (k, v) in enumerate(top_sgf):
            q = stima_quota(v/total_p)
            label = f"{'🎯' if i==0 else '💎'} {k if k<5 else '>4'} G: {q:.2f}"
            if q >= 3.0:
                st.success(label)
            else:
                st.info(label)

    with c_sgc:
        st.write("**Top 2 SGC**")
        for k, v in top_sgc:
            q = stima_quota(v/total_p)
            label = f"💎 {k} G: {q:.2f}"
            if q >= 3.0: st.success(label)
            else: st.info(label)

    with c_sgo:
        st.write("**Top 2 SGO**")
        for k, v in top_sgo:
            q = stima_quota(v/total_p)
            label = f"💎 {k} G: {q:.2f}"
            if q >= 3.0: st.success(label)
            else: st.info(label)

    st.divider()
    st.subheader("🏁 Mercati Classici")
    cuo, cgng = st.columns(2)
    with cuo:
        qu, qo = stima_quota(p_u25), stima_quota(1-p_u25)
        if qu >= 3.0: st.success(f"💎 U2.5: {qu:.2f}")
        else: st.info(f"U2.5: {qu:.2f}")
        if qo >= 3.0: st.success(f"💎 O2.5: {qo:.2f}")
        else: st.info(f"O2.5: {qo:.2f}")
    with cgng:
        qg, qng = stima_quota(p_gol), stima_quota(1-p_gol)
        if qg >= 3.0: st.success(f"💎 GOL: {qg:.2f}")
        else: st.info(f"GOL: {qg:.2f}")
        if qng >= 3.0: st.success(f"💎 NOGOL: {qng:.2f}")
        else: st.info(f"NOGOL: {qng:.2f}")

# --- MAIN ---
st.set_page_config(page_title="Delphi Pro", layout="wide")
st.title("🏆 Delphi Predictor Pro Max")
t1, t2 = st.tabs(["🎯 Analisi", "⚙️ Gestione"])

with t1:
    search = st.text_input("Squadra:")
    if st.button("Analizza Match", type="primary"):
        if search: calcola_pronostico_streamlit(search)

with t2:
    if os.path.exists(FILE_DB):
        st.write(f"📂 Ultimo DB: {datetime.fromtimestamp(os.path.getmtime(FILE_DB)).strftime('%d/%m/%Y %H:%M')}")
    if st.button("🌐 Aggiorna Database"): aggiorna_con_api()
