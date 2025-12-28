import streamlit as st
import pandas as pd
import math
import requests
import os
import time
from datetime import datetime

st.image("banner1.png")

# 4. Titolo
# st.title("Delphi Predictor")

# --- IL RESTO DEL TUO CODICE ---🔮

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

# --- FUNZIONE DI ANALISI PRINCIPALE ---
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
    
    # Calcolo medie Poisson
    avg_g = max(1.1, giocate['FTHG'].mean())
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

    # Poisson 1° Tempo
    exp_h_1t, exp_a_1t = exp_h * 0.42, exp_a * 0.42
    re_1t, total_p_1t = [], 0
    for i in range(4):
        for j in range(4):
            prob_1t = poisson_probability(i, exp_h_1t) * poisson_probability(j, exp_a_1t)
            total_p_1t += prob_1t
            re_1t.append({'s': f"{i}-{j}", 'p': prob_1t})

    # --- UI RENDERING ---
    st.header(f"🏟️ {casa} vs {fuori}")
    st.info(f"🏆 **Lega**: {m['League']} | 📅 **Data**: {m['Date']}")
    st.info(f"👮 **Arbitro:** {arbitro} | 📈 **Impatto:** {molt_arbitro}x")
    f_h, f_a = controlla_fatica(df, casa, m['Date']), controlla_fatica(df, fuori, m['Date'])
    if f_h or f_a:
        st.warning(f"⚠️ **Fatica Coppa:** {'Casa' if f_h else ''} {'&' if f_h and f_a else ''} {'Fuori' if f_a else ''}")

    # 1. Calcolo del valore
    lg_idx = calcola_late_goal_index(casa, fuori)
    
    # 2. Definiamo il colore in base al valore
    # Se l'indice è > 1.2 diventa rosso (#FF4B4B), altrimenti resta blu (#007BFF)
    badge_color = "#FF4B4B" if lg_idx > 1.2 else "#007BFF"
    
    st.write("⏳ **Indice Late Goal**")
    
    # 3. Visualizzazione del "Pulsante" dinamico
    st.markdown(f"""
        <div style="
            background-color: {badge_color};
            color: white;
            padding: 10px 20px;
            text-align: center;
            border-radius: 10px;
            font-size: 26px;
            font-weight: bold;
            box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.1);
            margin-bottom: 10px;
        ">
            {lg_idx}
        </div>
    """, unsafe_allow_html=True)
    
    # 4. Messaggio di avviso extra (solo se alto)
    if lg_idx > 1.2: 
        st.warning(f"🔥 **POTENZIALE LATE GOAL RILEVATO**")
    
    
    # --- ESITO FINALE 1X2 (BLU) ---
    st.divider()
    st.subheader("🏁 Esito Finale 1X2")
    c1, cx, c2 = st.columns(3)
    
    # Calcolo probabilità dai risultati di Poisson
    p_1, p_x, p_2 = 0, 0, 0
    for i in range(7):
        for j in range(7):
            prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
            if i > j: p_1 += prob
            elif i == j: p_x += prob
            else: p_2 += prob

    with c1:
        prob1 = p_1/total_p
        st.info(f"1:📈 {prob1:.1%} 💰 Q: {stima_quota(prob1)}")
    with cx:
        probx = p_x/total_p
        st.info(f"X:📈 {probx:.1%} 💰 Q: {stima_quota(probx)}")
    with c2:
        prob2 = p_2/total_p
        st.info(f"2:📈 {prob2:.1%} 💰 Q: {stima_quota(prob2)}")
        
    # --- MERCATI CLASSICI (BLU) ---
    st.divider()
    st.subheader("🥅 Under/Over 2,5 & Gol/NoGol")
    cuo, cgng = st.columns(2)
    with cuo:
        pu, po = p_u25/total_p, 1-(p_u25/total_p)
        st.info(f"UNDER 2.5:📈 {pu:.1%} 💰 Quota: {stima_quota(pu)}")
        st.info(f"OVER 2.5:📈 {po:.1%} 💰 Quota: {stima_quota(po)}")
    with cgng:
        pg, png = p_gol/total_p, 1-(p_gol/total_p)
        st.info(f"GOL:📈 {pg:.1%} 💰 Quota: {stima_quota(pg)}")
        st.info(f"NOGOL:📈 {png:.1%} 💰 Quota: {stima_quota(png)}")

    # --- SOMME GOL (VERDI) ---
    st.divider()
    st.subheader("⚽ Analisi Somme Gol")
    c_sgf, c_sgc, c_sgo = st.columns(3)
    with c_sgf:
        st.write("**Top 3 Somma Gol Finale**")
        for k, v in sorted(sgf.items(), key=lambda x: x[1], reverse=True)[:3]:
            p = v/total_p
            st.success(f"**{k if k<5 else '>4'}** GOL:📈 {p:.1%} 💰 Q: {stima_quota(p)}")
    with c_sgc:
        st.write("**Top 2 Somma Gol Casa**")
        for k, v in sorted(sgc.items(), key=lambda x: x[1], reverse=True)[:2]:
            p = v/total_p
            st.success(f"**{k if k<2 else '>2'}** GOL:📈 {p:.1%} 💰 Q: {stima_quota(p)}")
    with c_sgo:
        st.write("**Top 2 Somma Gol Ospite**")
        for k, v in sorted(sgo.items(), key=lambda x: x[1], reverse=True)[:2]:
            p = v/total_p
            st.success(f"**{k if k<2 else '>2'}** GOL:📈 {p:.1%} 💰 Q: {stima_quota(p)}")

    # --- RISULTATI ESATTI (VERDI E BLU) ---
    st.divider()
    st.subheader("🎯 Top Risultati Esatti")
    cre1, cre2 = st.columns([2, 1])
    with cre1:
        st.write("**Top 6 Risultati Esatti Finali**")
        for r in sorted(re_finali, key=lambda x: x['p'], reverse=True)[:6]:
            p = r['p']/total_p
            st.success(f"**{r['s']}**: 📈 {p:.1%} 💰Q: {stima_quota(p)}")
    with cre2:
        st.write("**Top 3 Risultati Esatti 1° Tempo**")
        for r in sorted(re_1t, key=lambda x: x['p'], reverse=True)[:3]:
            p = r['p']/total_p_1t
            st.info(f"**{r['s']}**: 📈 {p:.1%} 💰Q: {stima_quota(p)}")

# --- MAIN APP ---
# st.set_page_config(page_title="Delphi Pro", layout="wide")
# st.title("Delphi Predictor")
tab_analisi, tab_gestione = st.tabs(["🎯 Analisi Match", "⚙️ Gestione"])

with tab_analisi:
    search_query = st.text_input("Inserisci nome squadra:")
    if st.button("Analizza Match", type="primary"):
        if search_query: calcola_pronostico_streamlit(search_query)

with tab_gestione:
    if st.button("🌐 Aggiorna Database"): aggiorna_con_api()
