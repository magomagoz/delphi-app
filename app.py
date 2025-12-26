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

# --- LOGICA MATEMATICA E CALCOLO (Invariata) ---

def stima_quota(prob):
    if prob <= 0.001: return 99.00
    return round(1 / prob, 2)

def salva_report_permanente(testo, titolo):
    try:
        timestamp = datetime.now().strftime("%d/%m %H:%M")
        with open(FILE_REPORT, 'a', encoding='utf-8') as f:
            f.write(f"\n[MATCH_START]\nID: {titolo}\n[{timestamp}]\n{testo}\n[MATCH_END]\n")
    except: pass

def poisson_probability(actual, average):
    if average <= 0: average = 0.01
    return (math.pow(average, actual) * math.exp(-average)) / math.factorial(actual)

def analizza_severita_arbitro(df, nome_arbitro):
    if nome_arbitro == 'N.D.' or df.empty: return 1.0
    partite_arbitro = df[(df['Referee'] == nome_arbitro) & (df['Status'] == 'FINISHED')]
    if len(partite_arbitro) < 3: return 1.0
    media_gol_arbitro = (partite_arbitro['FTHG'] + partite_arbitro['FTAG']).mean()
    media_gol_totale = (df['FTHG'] + df['FTAG']).mean()
    rapporto = media_gol_totale / media_gol_arbitro
    return round(max(0.8, min(1.3, rapporto)), 2)

def rimuovi_duplicati_cronologia():
    if not os.path.exists(FILE_REPORT):
        return
    try:
        with open(FILE_REPORT, 'r', encoding='utf-8') as f:
            content = f.read()
        blocks = re.findall(r'\[MATCH_START\].*?\[MATCH_END\]', content, re.DOTALL)
        visti = set()
        unici = []
        for b in reversed(blocks):
            match_id = re.search(r'ID: (.*?)\n', b)
            if match_id:
                id_str = match_id.group(1).strip()
                if id_str not in visti:
                    unici.append(b)
                    visti.add(id_str)
        with open(FILE_REPORT, 'w', encoding='utf-8') as f:
            f.write("\n".join(reversed(unici)))
        st.success(f"Pulizia completata! Rimossi {len(blocks) - len(unici)} duplicati.")
    except Exception as e:
        st.error(f"Errore: {e}")
        
def analizza_zona_cesarini(df, team):
    partite = df[((df['HomeTeam'] == team) | (df['AwayTeam'] == team)) & (df['Status'] == 'FINISHED')].tail(10)
    if partite.empty: return 0
    gol_secondo_tempo = 0
    for _, row in partite.iterrows():
        fthg, ftag = row['FTHG'], row['FTAG']
        if (row['HomeTeam'] == team and fthg > 1) or (row['AwayTeam'] == team and ftag > 1):
            gol_secondo_tempo += 1
    return (gol_secondo_tempo / len(partite)) * 100

# --- FUNZIONI DI AZIONE (Adattate per Streamlit) ---

def aggiorna_con_api():
    headers = {'X-Auth-Token': API_TOKEN}
    leagues = {
        'WC': 'FIFA World Cup', 'SA':'Serie A', 'PL':'Premier League', 
        'ELC':'Championship', 'PD':'La Liga', 'BL1':'Bundesliga', 
        'FL1':'Ligue 1', 'DED':'Eredivisie', 'BSA': 'Campeonato Brasileiro',
        'PPL':'Primeira Liga', 'CL':'Champions League', 'EC':'Conference League'
    }
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        rows = []
        for i, (code, name) in enumerate(leagues.items()):
            status_text.text(f"Sincronizzazione {name}...")
            r = requests.get(f"https://api.football-data.org/v4/competitions/{code}/matches", headers=headers, timeout=10)
            if r.status_code == 200:
                for m in r.json().get('matches', []):
                    home = m['homeTeam']['shortName'] or m['homeTeam']['name']
                    away = m['awayTeam']['shortName'] or m['awayTeam']['name']
                    ref = m['referees'][0].get('name', 'N.D.') if m.get('referees') else 'N.D.'
                    rows.append([name, m['utcDate'][:10], home, away, m['status'], m['score']['fullTime']['home'], m['score']['fullTime']['away'], ref, m.get('odds', {}).get('homeWin', 1.0), m.get('odds', {}).get('draw', 1.0), m.get('odds', {}).get('awayWin', 1.0)])
                time.sleep(1.8)
            progress_bar.progress((i + 1) / len(leagues))
        
        pd.DataFrame(rows, columns=['League', 'Date', 'HomeTeam', 'AwayTeam', 'Status', 'FTHG', 'FTAG', 'Referee', 'Odd_1', 'Odd_X', 'Odd_2']).to_csv(FILE_DB, index=False)
        st.success("Database Aggiornato!")
    except Exception as e: st.error(f"Errore API: {e}")

def calcola_pronostico_streamlit(nome_input):
    if not os.path.exists(FILE_DB):
        st.error("Database non trovato. Aggiorna i dati prima.")
        return
    
    df = pd.read_csv(FILE_DB)
    df['FTHG'] = pd.to_numeric(df['FTHG'], errors='coerce').fillna(0)
    df['FTAG'] = pd.to_numeric(df['FTAG'], errors='coerce').fillna(0)
    
    match = df[df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED']) & 
               (df['HomeTeam'].str.contains(nome_input, case=False, na=False) | 
                df['AwayTeam'].str.contains(nome_input, case=False, na=False))]
    
    if match.empty:
        st.warning(f"Nessun match imminente per '{nome_input}'")
        return

    m = match.iloc[0]
    casa, fuori = m['HomeTeam'], m['AwayTeam']
    giocate = df[df['Status'] == 'FINISHED'].copy()
    avg_g = max(1.1, giocate['FTHG'].mean())
    
    arbitro = m.get('Referee', 'N.D.')
    molt_arbitro = analizza_severita_arbitro(giocate, arbitro)
    
    # --- LOGICA DI CALCOLO POISSON (Sintetizzata per brevità, usa la tua originale) ---
    def get_stats(team):
        t = giocate[(giocate['HomeTeam'] == team) | (giocate['AwayTeam'] == team)].tail(15)
        if t.empty: return 1.4, 1.4, 0
        att = t.apply(lambda r: float(r['FTHG']) if r['HomeTeam']==team else float(r['FTAG']), axis=1).mean()
        dif = t.apply(lambda r: float(r['FTAG']) if r['HomeTeam']==team else float(r['FTHG']), axis=1).mean()
        return att, dif, len(t)

    att_h, dif_h, _ = get_stats(casa)
    att_a, dif_a, _ = get_stats(fuori)
    exp_h = (att_h * dif_a / avg_g) * (2 - molt_arbitro)
    exp_a = (att_a * dif_h / avg_g) * (2 - molt_arbitro)

    p1, px, p2 = 0, 0, 0
    total_p = 0
    for i in range(7):
        for j in range(7):
            prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
            total_p += prob
            if i > j: p1 += prob
            elif i == j: px += prob
            else: p2 += prob
    # --- LOGICA POISSON AGGIORNATA ---
    exp_h_1t, exp_a_1t = exp_h * 0.45, exp_a * 0.45
    re_1t = []
    p1_1t, px_1t, p2_1t, total_p_1t = 0, 0, 0, 0

    for i in range(4): # Max 3 gol per tempo per brevità
        for j in range(4):
            prob_1t = poisson_probability(i, exp_h_1t) * poisson_probability(j, exp_a_1t)
            total_p_1t += prob_1t
            if i > j: p1_1t += prob_1t
            elif i == j: px_1t += prob_1t
            else: p2_1t += prob_1t
            re_1t.append({'s': f"{i}-{j}", 'p': prob_1t})

    top_re_1t = sorted(re_1t, key=lambda x: x['p'], reverse=True)[:3]

    # --- OUTPUT STREAMLIT ---
    st.header(f"🏟️ {casa} vs {fuori}")
    st.caption(f"🏆 {m['League']} | 📅 {m['Date']} | 👮 Arbitro: {arbitro}")

    # --- 1. GRAFICO FINALE ---
    df_pie_finale = pd.DataFrame({
        'Esito': ['1', 'X', '2'],
        'Probabilità': [p1/total_p, px/total_p, p2/total_p]
    })
    fig_finale = px.pie(df_pie_finale, values='Probabilità', names='Esito', 
                         title='Tendenza 1X2 Finale',
                         color_discrete_sequence=['#2ecc71', '#f1c40f', '#e74c3c'], hole=0.4)
    st.plotly_chart(fig_finale, use_container_width=True)

    # --- 2. PRIMO TEMPO (Solo 3 RE) ---
    st.markdown("---")
    st.subheader("⏱️ Top 3 Risultati Esatti 1° Tempo")
    col_1t = st.columns(3)
    for idx, r in enumerate(top_re_1t):
        p_re_1t = r['p']/total_p_1t
        col_1t[idx].metric(f"Esito: {r['s']}", f"{p_re_1t:.1%}", f"Quota: {stima_quota(p_re_1t)}")

    # --- 3. SOMME GOL (SGF, SGC, SGO) ---
    st.markdown("---")
    st.subheader("⚽ Analisi Somme Gol")
    
    c_sgf, c_sgc, c_sgo = st.columns(3)
    
    with c_sgf:
        st.write("**Top 3 Somma Gol (SGF)**")
        for k, v in top_sgf:
            p_k = v/total_p
            st.info(f"**{k if k<5 else '>4'} Gol**: {p_k:.1%} (Q: {stima_quota(p_k)})")
            
    with c_sgc:
        st.write("**Top 2 Gol Casa (SGC)**")
        for k, v in top_sgc:
            p_k = v/total_p
            st.success(f"**{k} Gol**: {p_k:.1%} (Q: {stima_quota(p_k)})")

    with c_sgo:
        st.write("**Top 2 Gol Ospite (SGO)**")
        for k, v in top_sgo:
            p_k = v/total_p
            st.warning(f"**{k} Gol**: {p_k:.1%} (Q: {stima_quota(p_k)})")

    # --- 4. TOP 6 RISULTATI ESATTI FINALI ---
    st.markdown("---")
    st.subheader("🎯 Top 6 Risultati Esatti (RE) Finale")
    
    # Dividiamo i 6 RE in due righe da 3 per leggibilità su mobile
    re_row1 = st.columns(3)
    re_row2 = st.columns(3)
    
    for idx, r in enumerate(top_re):
        p_re = r['p']/total_p
        target_col = re_row1[idx] if idx < 3 else re_row2[idx-3]
        target_col.code(f"{r['s']} \n{p_re:.1%} \nQ: {stima_quota(p_re)}")

    # Sezione Alert (Late Goal)
    if zc_h > 60 or zc_a > 60:
        st.warning(f"⚠️ **ATTENZIONE:** Alta probabilità di GOL nel finale (80'+)! Indice: {max(zc_h, zc_a):.0f}%")
