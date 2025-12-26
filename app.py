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

# Inizializzazione Cronologia nello stato della sessione
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

# --- FUNZIONE AUSILIARIA PER LE STATISTICHE ---
# Questa funzione serve per calcolare le probabilità nel passato per il test statistico
def get_prediction_data(df_storico, casa, fuori, arbitro):
    avg_g = max(1.1, df_storico['FTHG'].mean())
    molt_arbitro = analizza_severita_arbitro(df_storico, arbitro)
    
    def get_stats(team):
        t = df_storico[(df_storico['HomeTeam'] == team) | (df_storico['AwayTeam'] == team)].tail(15)
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

# --- FUNZIONE AGGIORNAMENTO API ---
def aggiorna_con_api():
    headers = {'X-Auth-Token': API_TOKEN}
    leagues = {'SA':'Serie A', 'PL':'Premier League', 'PD':'La Liga', 'BL1':'Bundesliga', 'FL1':'Ligue 1', 'CL':'Champions League'}
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

# --- FUNZIONE STATISTICHE ---
def mostra_statistiche():
    if not os.path.exists(FILE_DB):
        st.warning("Database non trovato."); return
    df = pd.read_csv(FILE_DB)
    giocate = df[df['Status'] == 'FINISHED'].copy()
    
    if len(giocate) < 10:
        st.info("Dati insufficienti per le statistiche (servono almeno 10 match conclusi).")
        return

    st.subheader("📈 Performance Storica (Backtesting)")
    st.caption("Analisi basata sugli ultimi 50 match presenti nel database.")
    
    tot = min(50, len(giocate))
    hits = {'SGF': 0, 'UO': 0, 'GNG': 0, 'RE': 0}
    
    progress_text = "Analisi in corso..."
    my_bar = st.progress(0, text=progress_text)

    for i in range(tot):
        my_bar.progress((i + 1) / tot, text=progress_text)
        # Prende il match e simula di non conoscere il risultato
        m = giocate.iloc[-(i+1)]
        storico = giocate.iloc[:-(i+1)]
        
        if storico.empty: continue
        
        # Calcola previsione
        data = get_prediction_data(storico, m['HomeTeam'], m['AwayTeam'], m['Referee'])
        
        # Dati reali
        real_h = int(float(m['FTHG']))
        real_a = int(float(m['FTAG']))
        real_sum = real_h + real_a
        
        # 1. Verifica SGF (Somma Gol Finale)
        pred_sgf = max(data['sgf'], key=data['sgf'].get)
        if pred_sgf == min(real_sum, 5): hits['SGF'] += 1
        
        # 2. Verifica Under/Over 2.5
        prob_u25 = data['p_u25'] / data['total_p']
        # Se prob U2.5 > 50% e è finito Under, oppure prob U2.5 <= 50% e è finito Over
        if (prob_u25 > 0.5 and real_sum < 2.5) or (prob_u25 <= 0.5 and real_sum > 2.5): 
            hits['UO'] += 1
            
        # 3. Verifica Gol/NoGol
        prob_gol = data['p_gol'] / data['total_p']
        is_gol = (real_h > 0 and real_a > 0)
        if (prob_gol > 0.5 and is_gol) or (prob_gol <= 0.5 and not is_gol):
            hits['GNG'] += 1
            
        # 4. Verifica Top 6 Risultati Esatti
        top6_re = [x['s'] for x in sorted(data['re'], key=lambda x: x['p'], reverse=True)[:6]]
        if f"{real_h}-{real_a}" in top6_re: hits['RE'] += 1

    my_bar.empty()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SGF (Top 1)", f"{(hits['SGF']/tot):.0%}")
    c2.metric("U/O 2.5", f"{(hits['UO']/tot):.0%}")
    c3.metric("GOL/NO GOL", f"{(hits['GNG']/tot):.0%}")
    c4.metric("RE (in Top 6)", f"{(hits['RE']/tot):.0%}")

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
    
    # AGGIUNTA ALLA CRONOLOGIA (Senza duplicati)
    entry = f"{casa} vs {fuori}"
    if entry not in st.session_state.cronologia:
        st.session_state.cronologia.insert(0, entry) # Inserisce in alto

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

    # Poisson & Mercati
    p_u25, p_gol = 0, 0
    total_p = 0
    sgf, sgc, sgo = {i:0 for i in range(6)}, {i:0 for i in range(6)}, {i:0 for i in range(6)}
    re_finali = [] # Lista per i Risultati Esatti
    
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

    top_sgf = sorted(sgf.items(), key=lambda x: x[1], reverse=True)[:3]
    top_sgc = sorted(sgc.items(), key=lambda x: x[1], reverse=True)[:2]
    top_sgo = sorted(sgo.items(), key=lambda x: x[1], reverse=True)[:2]
    # Ordinamento Top 6 Risultati Esatti
    top_re = sorted(re_finali, key=lambda x: x['p'], reverse=True)[:6]

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
            if q >= 3.0: st.success(label)
            else: st.info(label)

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
        
    st.divider()
    st.subheader("🎯 Top 6 Risultati Esatti")
    cols_re = st.columns(3)
    for idx, r in enumerate(top_re):
        q = stima_quota(r['p']/total_p)
        with cols_re[idx % 3]:
            if q >= 3.0: st.success(f"**{r['s']}**\n\nQ: {q:.2f} 🔥")
            else: st.code(f"{r['s']} | Q: {q:.2f}")

# --- MAIN ---
st.set_page_config(page_title="Delphi Pro", layout="wide")
st.title("🏆 Delphi Predictor Pro Max")
# Definizione Tabs (Analisi, Statistiche, Gestione)
t1, t2, t3 = st.tabs(["🎯 Analisi", "📊 Statistiche", "⚙️ Gestione"])

with t1:
    col_input, col_hist = st.columns([2, 1])
    
    with col_input:
        search = st.text_input("Squadra:")
        if st.button("Analizza Match", type="primary"):
            if search: calcola_pronostico_streamlit(search)
    
    with col_hist:
        st.write("📜 **Cronologia**")
        if st.session_state.cronologia:
            for item in st.session_state.cronologia:
                # Se clicchi sulla squadra nella cronologia, la analizza di nuovo
                if st.button(item, key=item):
                    calcola_pronostico_streamlit(item.split(" vs ")[0])
            
            st.divider()
            # CANCELLAZIONE CON WARNING
            if st.button("🗑️ Svuota Cronologia"):
                st.warning("Sei sicuro di voler cancellare tutto?")
                if st.button("Sì, conferma cancellazione"):
                    st.session_state.cronologia = []
                    st.rerun()
        else:
            st.caption("Nessuna ricerca recente.")

with t2:
    mostra_statistiche()

with t3:
    if os.path.exists(FILE_DB):
        st.write(f"📂 Ultimo DB: {datetime.fromtimestamp(os.path.getmtime(FILE_DB)).strftime('%d/%m/%Y %H:%M')}")
    if st.button("🌐 Aggiorna Database"): aggiorna_con_api()
