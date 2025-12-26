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

# --- FUNZIONI DI CALCOLO ---
def get_prediction_data(df_giocate, casa, fuori, arbitro):
    avg_g = max(1.1, df_giocate['FTHG'].mean())
    molt_arbitro = analizza_severita_arbitro(df_giocate, arbitro)
    
    def get_stats(team):
        t = df_giocate[(df_giocate['HomeTeam'] == team) | (df_giocate['AwayTeam'] == team)].tail(15)
        if t.empty: return 1.4, 1.4
        att = t.apply(lambda r: float(r['FTHG']) if r['HomeTeam']==team else float(r['FTAG']), axis=1).mean()
        dif = t.apply(lambda r: float(r['FTAG']) if r['HomeTeam']==team else float(r['FTHG']), axis=1).mean()
        return att, dif

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

# --- TAB STATISTICHE ---
def mostra_statistiche():
    if not os.path.exists(FILE_DB):
        st.warning("Database non trovato."); return
    df = pd.read_csv(FILE_DB)
    giocate = df[df['Status'] == 'FINISHED'].copy()
    if len(giocate) < 10:
        st.info("Dati insufficienti."); return

    st.subheader("📈 Performance Storica")
    tot = min(50, len(giocate))
    hits = {'SGF': 0, 'UO': 0, 'GNG': 0, 'RE': 0}

    for i in range(tot):
        m = giocate.iloc[-(i+1)]
        storico = giocate.iloc[:-(i+1)]
        if storico.empty: continue
        
        data = get_prediction_data(storico, m['HomeTeam'], m['AwayTeam'], m['Referee'])
        real_h, real_a = int(m['FTHG']), int(m['FTAG'])
        real_sum = real_h + real_a
        
        # SGF
        if max(data['sgf'], key=data['sgf'].get) == min(real_sum, 5): hits['SGF'] += 1
        # U/O
        if (data['p_u25'] > 0.5 and real_sum < 2.5) or (data['p_u25'] <= 0.5 and real_sum > 2.5): hits['UO'] += 1
        # GNG
        if (data['p_gol'] > 0.5 and real_h > 0 and real_a > 0) or (data['p_gol'] <= 0.5 and (real_h == 0 or real_a == 0)): hits['GNG'] += 1
        # RE (Top 6)
        top6_re = [x['s'] for x in sorted(data['re'], key=lambda x: x['p'], reverse=True)[:6]]
        if f"{real_h}-{real_a}" in top6_re: hits['RE'] += 1

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SGF Top 1", f"{(hits['SGF']/tot):.0%}")
    c2.metric("U/O 2.5", f"{(hits['UO']/tot):.0%}")
    c3.metric("GOL/NO GOL", f"{(hits['GNG']/tot):.0%}")
    c4.metric("RE (Top 6)", f"{(hits['RE']/tot):.0%}")

# --- CALCOLO E UI ANALISI ---
def calcola_pronostico_streamlit(nome_input):
    df = pd.read_csv(FILE_DB)
    df['FTHG'] = pd.to_numeric(df['FTHG'], errors='coerce').fillna(0)
    df['FTAG'] = pd.to_numeric(df['FTAG'], errors='coerce').fillna(0)
    
    match = df[df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED']) & 
               (df['HomeTeam'].str.contains(nome_input, case=False, na=False) | 
                df['AwayTeam'].str.contains(nome_input, case=False, na=False))]
    
    if match.empty:
        st.warning("Match non trovato."); return

    m = match.iloc[0]; casa, fuori = m['HomeTeam'], m['AwayTeam']
    entry = f"{casa} vs {fuori}"
    if entry not in st.session_state.cronologia: st.session_state.cronologia.insert(0, entry)

    giocate = df[df['Status'] == 'FINISHED'].copy()
    data = get_prediction_data(giocate, casa, fuori, m.get('Referee', 'N.D.'))
    
    st.header(f"🏟️ {casa} vs {fuori}")
    st.info(f"👮 Arbitro: {m.get('Referee', 'N.D.')}")

    # --- SOMME GOL ---
    st.subheader("⚽ Analisi Somme Gol")
    top_sgf = sorted(data['sgf'].items(), key=lambda x: x[1], reverse=True)[:3]
    cols_sgf = st.columns(3)
    for i, (k, v) in enumerate(top_sgf):
        q = stima_quota(v/data['total_p'])
        label = f"{'🎯' if i==0 else '💎'} {k if k<5 else '>4'} G: {q:.2f}"
        if q >= 3.0: cols_sgf[i].success(label)
        else: cols_sgf[i].info(label)

    # --- CLASSICI ---
    st.divider()
    st.subheader("🏁 Mercati Classici")
    c_uo, c_gng = st.columns(2)
    with c_uo:
        qu, qo = stima_quota(data['p_u25']), stima_quota(1-data['p_u25'])
        st.success(f"💎 U2.5: {qu:.2f}") if qu >= 3.0 else st.info(f"U2.5: {qu:.2f}")
        st.success(f"💎 O2.5: {qo:.2f}") if qo >= 3.0 else st.info(f"O2.5: {qo:.2f}")
    with c_gng:
        qg, qng = stima_quota(data['p_gol']), stima_quota(1-data['p_gol'])
        st.success(f"💎 GOL: {qg:.2f}") if qg >= 3.0 else st.info(f"GOL: {qg:.2f}")
        st.success(f"💎 NOGOL: {qng:.2f}") if qng >= 3.0 else st.info(f"NOGOL: {qng:.2f}")

    # --- RISULTATI ESATTI (6) ---
    st.divider()
    st.subheader("🎯 Top 6 Risultati Esatti Finale")
    top_re = sorted(data['re'], key=lambda x: x['p'], reverse=True)[:6]
    cols_re = st.columns(3)
    for idx, r in enumerate(top_re):
        q = stima_quota(r['p']/data['total_p'])
        with cols_re[idx % 3]:
            if q >= 3.0: st.success(f"**{r['s']}**\n\nQ: {q:.2f} 🔥")
            else: st.code(f"{r['s']} | Q: {q:.2f}")

# --- APP LAYOUT ---
st.set_page_config(page_title="Delphi Pro", layout="wide")
st.title("🏆 Delphi Predictor Pro Max")
t1, t3, t2 = st.tabs(["🎯 Analisi", "📊 Statistiche", "⚙️ Gestione"])

with t1:
    c_in, c_hi = st.columns([2, 1])
    with c_in:
        s = st.text_input("Squadra:")
        if st.button("Analizza", type="primary"): calcola_pronostico_streamlit(s)
    with c_hi:
        st.write("📜 Cronologia")
        for item in st.session_state.cronologia:
            if st.button(item, key=f"h_{item}"): calcola_pronostico_streamlit(item.split(" vs ")[0])
        if st.button("🗑️ Svuota"):
             st.session_state.cronologia = []; st.rerun()

with t3: mostra_statistiche()

with t2:
    if os.path.exists(FILE_DB):
        st.write(f"📂 Ultimo DB: {datetime.fromtimestamp(os.path.getmtime(FILE_DB)).strftime('%H:%M')}")
    if st.button("🌐 Aggiorna"): 
        # Inserire qui la funzione aggiorna_con_api() definita prima
        pass
