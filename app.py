import streamlit as st
import pandas as pd
import math
import requests
import os
import re
import time
from datetime import datetime

# --- CONFIGURAZIONE ---
API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'
FILE_DB = 'database_pro_2025.csv'
FILE_REPORT = 'Report_Simulazioni.txt'

# --- LOGICA MATEMATICA ---

def stima_quota(prob):
    if prob <= 0.001: return 99.00
    return round(1 / prob, 2)

def poisson_probability(actual, average):
    if average <= 0: average = 0.01
    return (math.pow(average, actual) * math.exp(-average)) / math.factorial(actual)

def analizza_severita_arbitro(df, nome_arbitro):
    if nome_arbitro == 'N.D.' or df.empty: return 1.0
    partite_arbitro = df[(df['Referee'] == nome_arbitro) & (df['Status'] == 'FINISHED')]
    if len(partite_arbitro) < 3: return 1.0
    media_gol_arbitro = (partite_arbitro['FTHG'] + partite_arbitro['FTAG']).mean()
    media_gol_totale = (df['FTHG'] + df['FTAG']).mean()
    return round(max(0.8, min(1.3, media_gol_totale / media_gol_arbitro)), 2)

# --- FUNZIONI DI AZIONE ---

def aggiorna_con_api():
    headers = {'X-Auth-Token': API_TOKEN}
    leagues = {
        'WC': 'FIFA World Cup', 'SA':'Serie A', 'PL':'Premier League', 
        'ELC':'Championship', 'PD':'La Liga', 'BL1':'Bundesliga', 
        'FL1':'Ligue 1', 'DED':'Eredivisie', 'BSA': 'Campeonato Brasileiro',
        'PPL':'Primeira Liga', 'CL':'Champions League', 'EC':'Conference League'
    }
    progress_bar = st.progress(0)
    try:
        rows = []
        for i, (code, name) in enumerate(leagues.items()):
            r = requests.get(f"https://api.football-data.org/v4/competitions/{code}/matches", headers=headers, timeout=10)
            if r.status_code == 200:
                for m in r.json().get('matches', []):
                    home = m['homeTeam']['shortName'] or m['homeTeam']['name']
                    away = m['awayTeam']['shortName'] or m['awayTeam']['name']
                    ref = m['referees'][0].get('name', 'N.D.') if m.get('referees') else 'N.D.'
                    rows.append([name, m['utcDate'][:10], home, away, m['status'], m['score']['fullTime']['home'], m['score']['fullTime']['away'], ref, m.get('odds', {}).get('homeWin', 1.0), m.get('odds', {}).get('draw', 1.0), m.get('odds', {}).get('awayWin', 1.0)])
                time.sleep(1.2)
            progress_bar.progress((i + 1) / len(leagues))
        pd.DataFrame(rows, columns=['League', 'Date', 'HomeTeam', 'AwayTeam', 'Status', 'FTHG', 'FTAG', 'Referee', 'Odd_1', 'Odd_X', 'Odd_2']).to_csv(FILE_DB, index=False)
        st.success("Database Aggiornato!")
    except Exception as e: st.error(f"Errore API: {e}")

def calcola_pronostico_streamlit(nome_input):
    if not os.path.exists(FILE_DB):
        st.error("Database non trovato. Vai in 'Gestione' e aggiorna i dati."); return
    
    df = pd.read_csv(FILE_DB)
    df['FTHG'] = pd.to_numeric(df['FTHG'], errors='coerce').fillna(0)
    df['FTAG'] = pd.to_numeric(df['FTAG'], errors='coerce').fillna(0)
    
    match = df[df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED']) & 
               (df['HomeTeam'].str.contains(nome_input, case=False, na=False) | 
                df['AwayTeam'].str.contains(nome_input, case=False, na=False))]
    
    if match.empty:
        st.warning(f"Nessun match imminente per '{nome_input}'"); return

    m = match.iloc[0]; casa, fuori = m['HomeTeam'], m['AwayTeam']
    giocate = df[df['Status'] == 'FINISHED'].copy()
    avg_g = max(1.1, giocate['FTHG'].mean())
    arbitro = m.get('Referee', 'N.D.')
    molt_arbitro = analizza_severita_arbitro(giocate, arbitro)

    def get_stats(team):
        t = giocate[(giocate['HomeTeam'] == team) | (giocate['AwayTeam'] == team)].tail(15)
        if t.empty: return 1.4, 1.4
        att = t.apply(lambda r: float(r['FTHG']) if r['HomeTeam']==team else float(r['FTAG']), axis=1).mean()
        dif = t.apply(lambda r: float(r['FTAG']) if r['HomeTeam']==team else float(r['FTHG']), axis=1).mean()
        return att, dif

    att_h, dif_h = get_stats(casa); att_a, dif_a = get_stats(fuori)
    exp_h = (att_h * dif_a / avg_g) * (2 - molt_arbitro)
    exp_a = (att_a * dif_h / avg_g) * (2 - molt_arbitro)

    # --- POISSON FINALE ---
    p1, px, p2, total_p = 0, 0, 0, 0
    sgf, sgc, sgo = {i:0 for i in range(6)}, {i:0 for i in range(6)}, {i:0 for i in range(6)}
    re_finali = []
    
    for i in range(7):
        for j in range(7):
            prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
            total_p += prob
            if i > j: p1 += prob
            elif i == j: px += prob
            else: p2 += prob
            if (i+j) < 5: sgf[i+j] += prob
            else: sgf[5] += prob
            if i < 5: sgc[i] += prob
            else: sgc[5] += prob
            if j < 5: sgo[j] += prob
            else: sgo[5] += prob
            re_finali.append({'s': f"{i}-{j}", 'p': prob})

    # --- POISSON 1° TEMPO ---
    exp_h_1t, exp_a_1t = exp_h * 0.45, exp_a * 0.45
    re_1t, total_p_1t = [], 0
    for i in range(4):
        for j in range(4):
            prob_1t = poisson_probability(i, exp_h_1t) * poisson_probability(j, exp_a_1t)
            total_p_1t += prob_1t
            re_1t.append({'s': f"{i}-{j}", 'p': prob_1t})

    top_re_1t = sorted(re_1t, key=lambda x: x['p'], reverse=True)[:3]
    top_sgf = sorted(sgf.items(), key=lambda x: x[1], reverse=True)[:3]
    top_sgc = sorted(sgc.items(), key=lambda x: x[1], reverse=True)[:2]
    top_sgo = sorted(sgo.items(), key=lambda x: x[1], reverse=True)[:2]
    top_re = sorted(re_finali, key=lambda x: x['p'], reverse=True)[:6]

    # --- VISUALIZZAZIONE ---
    st.header(f"🏟️ {casa} vs {fuori}")
    st.caption(f"🏆 {m['League']} | 📅 {m['Date']} | 👮 Arbitro: {arbitro}")

    st.subheader("📊 Probabilità 1X2 Finale")
    prob_df = pd.DataFrame({
        'Segno': ['1', 'X', '2'],
        'Probabilità': [f"{p1/total_p:.1%}", f"{px/total_p:.1%}", f"{p2/total_p:.1%}"],
        'Quota': [stima_quota(p1/total_p), stima_quota(px/total_p), stima_quota(p2/total_p)]
    })
    st.table(prob_df)

    st.subheader("⏱️ Top 3 RE 1° Tempo")
    c1t = st.columns(3)
    for idx, r in enumerate(top_re_1t):
        q = stima_quota(r['p']/total_p_1t)
        if q >= 3.0:
            c1t[idx].success(f"**{r['s']}**\n\nQ: {q:.2f} 🔥")
        else:
            c1t[idx].info(f"**{r['s']}**\n\nQ: {q:.2f}")

    st.divider()
    st.subheader("⚽ Analisi Somme Gol")
    csgf, csgc, csgo = st.columns(3)
    with csgf:
        st.write("**Top 3 SGF**")
        for k, v in top_sgf:
            q = stima_quota(v/total_p)
            label = f"{k if k<5 else '>4'} G: {q:.2f}"
            if q >= 3.0: st.success(f"💎 {label}")
            else: st.write(label)
    with csgc:
        st.write("**Top 2 SGC**")
        for k, v in top_sgc:
            q = stima_quota(v/total_p)
            label = f"{k} G: {q:.2f}"
            if q >= 3.0: st.success(f"💎 {label}")
            else: st.write(label)
    with csgo:
        st.write("**Top 2 SGO**")
        for k, v in top_sgo:
            q = stima_quota(v/total_p)
            label = f"{k} G: {q:.2f}"
            if q >= 3.0: st.success(f"💎 {label}")
            else: st.write(label)

    st.divider()
    st.subheader("🎯 Top 6 Risultati Esatti Finale")
    re_cols = st.columns(3)
    for idx, r in enumerate(top_re):
        q = stima_quota(r['p']/total_p)
        with re_cols[idx % 3]:
            if q >= 3.0: st.success(f"**{r['s']}**\n\nQ: {q:.2f} 🔥")
            else: st.code(f"{r['s']} | Q: {q:.2f}")

# --- INTERFACCIA PRINCIPALE ---
st.set_page_config(page_title="Delphi Pro", layout="wide")
st.title("🏆 Delphi Predictor Pro 🏆")

tab1, tab2 = st.tabs(["🎯 Analisi Match", "⚙️ Gestione"])

with tab1:
    search = st.text_input("Inserisci nome squadra (es: Milan, Real, Arsenal):")
    if st.button("Analizza Match", type="primary"):
        if search:
            calcola_pronostico_streamlit(search)
        else:
            st.warning("Inserisci il nome di una squadra!")

with tab2:
    st.subheader("Configurazione Sistema")
    if st.button("🌐 Aggiorna Database API"):
        aggiorna_con_api()
    
    if st.button("🗑️ Svuota Cronologia"):
        if os.path.exists(FILE_REPORT):
            os.remove(FILE_REPORT)
            st.success("Cronologia eliminata.")
