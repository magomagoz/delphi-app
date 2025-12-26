import streamlit as st
import pandas as pd
import math
import requests
import os
import re
import time
import dialogs
from datetime import datetime

API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'
FILE_DB = 'database_pro_2025.csv'
FILE_REPORT = 'Report_Simulazioni.txt'

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

def aggiorna_con_api():
    headers = {'X-Auth-Token': API_TOKEN}
    leagues = {
    'WC': 'FIFA World Cup',
    'SA':'Serie A',
    'PL':'Premier League', 'ELC':'Championship', 
    'PD':'La Liga',
    'BL1':'Bundesliga', 
    'FL1':'Ligue 1', 
    'DED':'Eredivisie', 'BSA': 'Campeonato Brasileiro',
    'PPL':'Primeira Liga',
    'CL':'Champions League', 'EC':'Conference League'}
    progress_bar = st.progress(0)
    status_text = st.empty
    
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

def analizza_late_goal(df, team):
    partite = df[((df['HomeTeam'] == team) | (df['AwayTeam'] == team)) & (df['Status'] == 'FINISHED')].tail(8)
    if partite.empty: return 0
    score = 0
    for _, r in partite.iterrows():
        gol = r['FTHG'] if r['HomeTeam'] == team else r['FTAG']
        if gol >= 2: score += 12.5 
    return score

def analizza_zona_cesarini(df, team):
    partite = df[((df['HomeTeam'] == team) | (df['AwayTeam'] == team)) & (df['Status'] == 'FINISHED')].tail(10)
    if partite.empty: return 0
    gol_secondo_tempo = 0
    for _, row in partite.iterrows():
        fthg, ftag = row['FTHG'], row['FTAG']
        if (row['HomeTeam'] == team and fthg > 1) or (row['AwayTeam'] == team and ftag > 1):
            gol_secondo_tempo += 1
    return (gol_secondo_tempo / len(partite)) * 100

def calcola_pronostico_streamlit(nome_input):
    if not os.path(FILE_DB):
   			st.error("Database non trovato. Aggiorna i dati.")
   			return

        df = pd.read_csv(FILE_DB)
        df['FTHG'] = pd.to_numeric(df['FTHG'], errors='coerce').fillna(0)
        df['FTAG'] = pd.to_numeric(df['FTAG'], errors='coerce').fillna(0)
        
        match = df[df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED']) & 
                   (df['HomeTeam'].str.contains(nome_input, case=False, na=False) | 
                    df['AwayTeam'].str.contains(nome_input, case=False, na=False))]
        
        if match.empty: 
            st.warning(f"Prossimo match non trovato per '{nome_input}'"); return None
            return
            
        m = match.iloc[0]; 
        casa, fuori = m['HomeTeam'], m['AwayTeam']
        
        q_bk = [float(m['Odd_1'] or 1.0), float(m['Odd_X'] or 1.0), float(m['Odd_2'] or 1.0)]
        
        giocate = df[df['Status'] == 'FINISHED'].copy()
        avg_g = max(1.1, giocate['FTHG'].mean())
        
        arbitro = m.get('Referee', 'N.D.')
        molt_arbitro = analizza_severita_arbitro(giocate, arbitro)

        def get_fatica(team, data_match):
            last = giocate[(giocate['HomeTeam'] == team) | (giocate['AwayTeam'] == team)].tail(1)
            if not last.empty:
                diff = (pd.to_datetime(data_match) - pd.to_datetime(last.iloc[0]['Date'])).days
                return 0.88 if diff < 4 else 1.0
            return 1.0

        fat_h = get_fatica(casa, m['Date']); fat_a = get_fatica(fuori, m['Date'])

        def get_stats(team):
            t = giocate[(giocate['HomeTeam'] == team) | (giocate['AwayTeam'] == team)].tail(15)
            count = len(t)
            if t.empty: return 1.4, 1.4, 0
            att = t.apply(lambda r: float(r['FTHG']) if r['HomeTeam']==team else float(r['FTAG']), axis=1).mean()
            dif = t.apply(lambda r: float(r['FTAG']) if r['HomeTeam']==team else float(r['FTHG']), axis=1).mean()
            return att, dif, len(t)

        att_h, dif_h, count_h = get_stats(casa)
        att_a, dif_a, count_a = get_stats(fuori)
        exp_h = (att_h * dif_a / avg_g) * fat_h * (2 - molt_arbitro)
        exp_a = (att_a * dif_h / avg_g) * fat_a * (2 - molt_arbitro)
        exp_h_1t, exp_a_1t = exp_h * 0.45, exp_a * 0.45

        total_p, p1, px, p2, p_over25, p_goal = 0, 0, 0, 0, 0, 0
        p1_1t, px_1t, p2_1t, total_p_1t = 0, 0, 0, 0
        sgc, sgo, sgf = {i:0 for i in range(6)}, {i:0 for i in range(6)}, {i:0 for i in range(6)}
        ris_esatti, re_1t = [], []
                
        # Loop Poisson per Finale e 1° Tempo
        for i in range(7):
            for j in range(7):
                prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
                total_p += prob
                if i > j: p1 += prob
                elif i == j: px += prob
                else: p2 += prob
                if (i+j) > 2.5: p_over25 += prob
                if i > 0 and j > 0: p_goal += prob
                if (i+j) < 5: sgf[i+j] += prob
                else: sgf[5] += prob
                if i < 5: sgc[i] += prob
                else: sgc[5] += prob
                if j < 5: sgo[j] += prob
                else: sgo[5] += prob
                ris_esatti.append({'s': f"{i}-{j}", 'p': prob})
                
                # Sotto-loop 1° Tempo (max 3 gol)
                if i < 4 and j < 4:
                    prob_1t = poisson_probability(i, exp_h_1t) * poisson_probability(j, exp_a_1t)
                    total_p_1t += prob_1t
                    if i > j: p1_1t += prob_1t
                    elif i == j: px_1t += prob_1t
                    else: p2_1t += prob_1t
                    re_1t.append({'s': f"{i}-{j}", 'p': prob_1t})
                    

        top_re = sorted(ris_esatti, key=lambda x: x['p'], reverse=True)[:6]
        top_re_1t = sorted(re_1t, key=lambda x: x['p'], reverse=True)[:3]
        top_sgc = sorted(sgc.items(), key=lambda x: x[1], reverse=True)[:2]
        top_sgo = sorted(sgo.items(), key=lambda x: x[1], reverse=True)[:2]
        top_sgf = sorted(sgf.items(), key=lambda x: x[1], reverse=True)[:3]

        # Calcolo indici Zona Cesarini
        zc_h = analizza_zona_cesarini(giocate, casa)
        zc_a = analizza_zona_cesarini(giocate, fuori)
        
        avviso_late_goal = ""
        if zc_h > 60 or zc_a > 60:
            avviso_late_goal = "⚠️ ATTENZIONE: Alta probabilità di GOL nel finale (80'+)!\n"
            
                    # --- OUTPUT STREAMLIT ---
    st.header(f"{casa} vs {fuori}")
    st.info(f"\n"
            f"🏆 {m['League']} - 📅 {m['Date']}\n"
            f"👮 Arbitro: {arbitro} (Severità: {molt_arbitro})\n"
            f"🏃 Fatica: Casa ({fat_h:.2f}) - Ospite ({fat_a:.2f})\n"
            f"🔥 Indice Late Goal: {max(zc_h, zc_a):.0f}%\n"
            f"{avviso_late_goal}"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚽️ PRONOSTICO FINALE 1X2 :\n")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Vittoria Casa (1)", f"{(p1/total_p):.1%}", f"Quota: {stima_quota(p1/total_p)}")
    c2.metric("Pareggio (X)", f"{(px/total_p):.1%}", f"Quota: {stima_quota(px/total_p)}")
    c3.metric("Vittoria Ospite (2)", f"{(p2/total_p):.1%}", f"Quota: {stima_quota(p2/total_p)}")

    d1, d2, d3 = st.columns(3)
    d1.metric("Vittoria Casa 1° Tempo (1)", f"{probs_1t[0]:.1%}", f"Quota: {stima_quota(probs_1t:.1%)}")
    d2.metric("Pareggio 1° Tempo (X)", f"{probs_xt[0]:.1%}", f"Quota: {stima_quota(probs_x:.1%)}")
    d3.metric("Vittoria Ospite 1° Tempo (2)", f"{probs_2t[0]:.1%}", f"Quota: {stima_quota(probs_2t:.1%)}")
    
    e1, e2, e3 = st.columns(3)
    e1.metric("Primo risultato esatto 1° Tempo", f"{re_1t[0]:.1%}", f"Quota: {stima_quota(re_1t[0]:.1%)}")
    e2.metric("Secondo risultato esatto 1° Tempo", f"{re_1t[0]:.1%}", f"Quota: {stima_quota(re_1t[0]:.1%)}")
    e3.metric("Terzo risultato esatto 1° Tempo", f"{re_1t[0]:.1%}", f"Quota: {stima_quota(re_1t[0]:.1%)}")

    f1, f2 = st.columns(2)
    f1.metric("UNDER 2,5", f"{po25:.1%}", f"Quota: {stima_quota(po25[0]:.2f)}")
    f2.metric("OVER 2,5", f"{1-po25:.1%}", f"Quota: {stima_quota(po25[0]:.2f)}")
    
    g1, g2 = st.columns(2)
    g1.metric("GOL", f"{pg:.1%}", f"Quota: {stima_quota(pg[0]:.2f)}")
    g2.metric("NOGOL", f"{1-pg:.1%}", f"Quota: {stima_quota(pg[0]:.2f)}")

    h1, h2, h3 = st.columns(3)
    h1.metric("Primo risultato esatto", f"{v/total_p:.1%}", f"Quota: {stima_quota(po25[0]:.2f)}")
    h2.metric("Secondo risultato esatto", f"{v/total_p:.2%}", f"Quota: {stima_quota(po25[0]:.2f)}")
    h2.metric("Terzo risultato esatto", f"{v/total_p:.3%}", f"Quota: {stima_quota(po25[0]:.2f)}")
    
    # Salva in cronologia
    report_text = f"Predizione 1X2: {p1/total_p:.1%} - {px/total_p:.1%} - {p2/total_p:.1%}"
    salva_report_permanente(report_text, f"{casa} vs {fuori}")


        
        def get_force_and_n(team):
            t_games = giocate[(giocate['HomeTeam'] == team) | (giocate['AwayTeam'] == team)].tail(5)
            n = len(t_games)
            if n == 0: return m_hg_lega, m_ag_lega, 0
            weights = range(1, n + 1)
            sum_w = sum(weights)
            att = sum((row['FTHG'] if row['HomeTeam'] == team else row['FTAG']) * weights[i] for i, (_, row) in enumerate(t_games.iterrows())) / sum_w
            dif = sum((row['FTAG'] if row['HomeTeam'] == team else row['FTHG']) * weights[i] for i, (_, row) in enumerate(t_games.iterrows())) / sum_w
            return att, dif, n

        att_h, dif_h, n_h = get_force_and_n(casa)
        att_a, dif_a, n_a = get_force_and_n(fuori)

        min_p = min(n_h, n_a)
        aff_msg = "🔴 AFFIDABILITÀ DEI DATI: CRITICA" if min_p < 3 else "🟡 AFFIDABILITÀ DEI DATI: MEDIA" if min_p < 5 else "🟢 AFFIDABILITÀ DEI DATI: ALTA"
        
        exp_h = max(0.01, (att_h / m_hg_lega) * (dif_a / m_ag_lega) * m_hg_lega)
        exp_a = max(0.01, (att_a / m_ag_lega) * (dif_h / m_hg_lega) * m_ag_lega)

        p1, px, p2, p_under25, p_goal = 0, 0, 0, 0, 0
        risultati_tutti = []
        somma_gol = {0:0, 1:0, 2:0, 3:0, 4:0, ">4":0}
        sg_casa = {0:0, 1:0, 2:0, ">2":0}
        sg_ospite = {0:0, 1:0, 2:0, ">2":0}

#----INTERFACCIA STREAMLIT -------


st.set_page_config(page_title="Delphi Predictor Pro", page_icon="🏆")
st.title("🏆 DELPHI PREDICTOR PRO MAX 🏆")

tab1, tab2, tab3 = st.tabs(["🎯 Pronostico", "📊 Statistiche", "⚙️ Gestione"])

with tab1:
    search = st.text_input("Inserisci squadra:", placeholder="Es: Inter, Man City...")
    if st.button("🔍 Analizza la prossima partita"):
        calcola_pronostico_streamlit(search)

with tab2:
    st.subheader("Performance Modello")
    if os.path.exists(FILE_REPORT):
        with open(FILE_REPORT, 'r') as f:
            st.text_area("Cronologia:", f.read(), height=300)
    else:
        st.write("Cronologia vuota.")

with tab3:
    st.subheader("Manutenzione del Sistema")
    if st.button("🌐 Aggiorna Database"):
        aggiorna_con_api()
    
    if st.button("🗑️ Svuota Cronologia"):
        if os.path.exists(FILE_REPORT):
            os.remove(FILE_REPORT)
            st.success("Cronologia cancellata!")

    st.subheader("Elimina duplicati")
    if st.button("🧹 Elimina duplicati"):
        aggiorna_con_api()
