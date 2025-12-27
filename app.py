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

# --- ANALISI ---
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

    # Poisson Finale
    p_u25, p_gol, total_p = 0, 0, 0
    sgf, sgc, sgo = {i:0 for i in range(6)}, {i:0 for i in range(6)}, {i:0 for i in range(6)}
    re_finali = []
    
    for i in range(7):
        for j in range(7):
            prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
            total_p += prob
            if (i+j) < 2.5: p_u25 += prob
            if i > 0 and j > 0: p_gol += prob
            sgf[min(i+j, 5)] += prob
            sgc[min(i, 5)] += prob
            sgo[min(j, 5)] += prob
            re_finali.append({'s': f"{i}-{j}", 'p': prob})

    # Poisson 1° Tempo (Stima ~42% exp goals)
    exp_h_1t, exp_a_1t = exp_h * 0.42, exp_a * 0.42
    re_1t, total_p_1t = [], 0
    for i in range(4):
        for j in range(4):
            prob_1t = poisson_probability(i, exp_h_1t) * poisson_probability(j, exp_a_1t)
            total_p_1t += prob_1t
            re_1t.append({'s': f"{i}-{j}", 'p': prob_1t})

    # --- UI ---
    st.header(f"🏟️ {casa} vs {fuori}")
    st.caption(f"🏆 {m['League']} | 📅 {m['Date']}")
    
    c1, c2 = st.columns(2)
    with c1:
        st.info(f"👮 Arbitro: {arbitro} ({molt_arbitro}x)")
    with c2:
        lg_idx = calcola_late_goal_index(casa, fuori)
        st.metric("⏳ Late Goal Index", f"{lg_idx}")
        if lg_idx > 1.2: st.error("🔥 ALTA PROBABILITÀ LATE GOAL")

    # MERCATI PRINCIPALI CON PERCENTUALI
    st.divider()
    st.subheader("🏁 Mercati Under/Over & Gol/NoGol")
    cm1, cm2 = st.columns(2)
    with cm1:
        perc_u25 = (p_u25/total_p)
        st.write(f"**U2.5:** {perc_u25:.1%} (Q: {stima_quota(perc_u25)})")
        st.write(f"**O2.5:** {(1-perc_u25):.1%} (Q: {stima_quota(1-perc_u25)})")
    with cm2:
        perc_gol = (p_gol/total_p)
        st.write(f"**GOL:** {perc_gol:.1%} (Q: {stima_quota(perc_gol)})")
        st.write(f"**NOGOL:** {(1-perc_gol):.1%} (Q: {stima_quota(1-perc_gol)})")

    # SOMME GOL CON PERCENTUALI
    st.divider()
    st.subheader("⚽ Somme Gol Finale")
    cs1, cs2, cs3 = st.columns(3)
    tops = [sorted(sgf.items(), key=lambda x:x[1], reverse=True)[:3], 
            sorted(sgc.items(), key=lambda x:x[1], reverse=True)[:2], 
            sorted(sgo.items(), key=lambda x:x[1], reverse=True)[:2]]
    
    for idx, col in enumerate([cs1, cs2, cs3]):
        labels = ["Totale", "Casa", "Ospite"]
        with col:
            st.write(f"**Top {labels[idx]}**")
            for k, v in tops[idx]:
                p = v/total_p
                st.code(f"{k} Gol: {p:.1%} (Q: {stima_quota(p)})")

    # RISULTATI ESATTI
    st.divider()
    st.subheader("🎯 Risultati Esatti (Finale & 1° Tempo)")
    cre1, cre2 = st.columns([2, 1])
    with cre1:
        st.write("**Top 6 Finale**")
        for r in sorted(re_finali, key=lambda x: x['p'], reverse=True)[:6]:
            p = r['p']/total_p
            st.success(f"{r['s']} ➡️ {p:.1%} (Quota: {stima_quota(p)})")
    with cre2:
        st.write("**Top 3 1° Tempo**")
        for r in sorted(re_1t, key=lambda x: x['p'], reverse=True)[:3]:
            p = r['p']/total_p_1t
            st.info(f"{r['s']} ➡️ {p:.1%} (Quota: {stima_quota(p)})")

# --- APP ---
st.set_page_config(page_title="Delphi Pro", layout="wide")
t1, t2 = st.tabs(["🎯 Analisi", "⚙️ Database"])
with t1:
    sq = st.text_input("Squadra:")
    if st.button("Analizza"): calcola_pronostico_streamlit(sq)
with t2:
    if st.button("Aggiorna DB"): aggiorna_con_api()
