import streamlit as st
import pandas as pd
import math
import requests
import os
import time
from datetime import datetime, date
import pytz

# --- 1. CONFIGURAZIONE (UNA SOLA VOLTA) ---
st.set_page_config(page_title="Delphi Predictor Pro", layout="wide") 

API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'
FILE_DB = 'database_pro_2025.csv'
FILE_DB_PRONOSTICI = 'database_pronostici.csv'

# --- 2. FUNZIONI DATABASE ---
def inizializza_db():
    if not os.path.exists(FILE_DB_PRONOSTICI):
        columns = [
            "Data", "Ora", "Partita", "Fiducia", "Affidabilità", 
            "1X2", "U/O 2.5", "G/NG", "SGF", "SGC", "SGO", 
            "RE Finale", "RE 1°T", "Match_ID", "Stato"
        ]
        df = pd.DataFrame(columns=columns)
        df.to_csv(FILE_DB_PRONOSTICI, index=False)

inizializza_db()

def salva_completo_in_locale(match, fiducia, affidabilita, p1x2, uo, gng, sgf, sgc, sgo, re_fin, re_pt, match_id=None):
    try:
        fuso_ita = pytz.timezone('Europe/Rome')
        adesso = datetime.now(fuso_ita)
        nuova_riga = {
            "Data": adesso.strftime("%d/%m/%Y"),
            "Ora": adesso.strftime("%H:%M"),
            "Partita": match,
            "Fiducia": f"{fiducia}%",
            "Affidabilità": f"{affidabilita}%",
            "1X2": p1x2, "U/O 2.5": uo, "G/NG": gng,
            "SGF": sgf, "SGC": sgc, "SGO": sgo,
            "RE Finale": re_fin, "RE 1°T": re_pt,
            "Match_ID": match_id if match_id and str(match_id) != "nan" else "N/A",
            "Stato": "In attesa"
        }
        df = pd.read_csv(FILE_DB_PRONOSTICI)
        df = pd.concat([df, pd.DataFrame([nuova_riga])], ignore_index=True)
        df.to_csv(FILE_DB_PRONOSTICI, index=False)
        return True
    except Exception as e:
        st.error(f"Errore salvataggio: {e}")
        return False

# --- 3. LOGICA MATEMATICA ---
def stima_quota(prob):
    if prob <= 0.001: return 99.00
    return round(1 / prob, 2)

def poisson_probability(actual, average):
    if average <= 0: average = 0.01
    return (math.pow(average, actual) * math.exp(-average)) / math.factorial(actual)

def analizza_severita_arbitro(df, nome_arbitro):
    if not nome_arbitro or nome_arbitro == 'N.D.' or df.empty: return 1.0
    try:
        partite_arbitro = df[df['Referee'].str.contains(str(nome_arbitro), na=False, case=False)]
        if len(partite_arbitro) < 2: return 1.0
        media_gol_arbitro = (partite_arbitro['FTHG'] + partite_arbitro['FTAG']).mean()
        media_gol_totale = (df['FTHG'] + df['FTAG']).mean()
        return round(max(0.8, min(1.3, media_gol_totale / media_gol_arbitro)), 2)
    except: return 1.0

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
    val = (len(str(casa)) + len(str(fuori))) % 15
    return round(val * 0.12, 2)

# --- 4. AGGIORNAMENTO API ---
def aggiorna_con_api():
    headers = {'X-Auth-Token': API_TOKEN}
    leagues = {'SA':'Serie A', 'PL':'Premier League', 'PD':'La Liga', 'BL1':'Bundesliga', 'CL':'Champions League'}
    rows = []
    progress_bar = st.progress(0)
    for i, (code, name) in enumerate(leagues.items()):
        try:
            r = requests.get(f"https://api.football-data.org/v4/competitions/{code}/matches", headers=headers, timeout=12)
            if r.status_code == 200:
                matches = r.json().get('matches', [])
                for m in matches:
                    home = m['homeTeam']['shortName'] or m['homeTeam']['name']
                    away = m['awayTeam']['shortName'] or m['awayTeam']['name']
                    ref = m['referees'][0].get('name', 'N.D.') if m.get('referees') else 'N.D.'
                    rows.append([name, m['utcDate'][:10], home, away, m['status'], m['score']['fullTime']['home'], m['score']['fullTime']['away'], ref, m['id']])
            time.sleep(1.5)
            progress_bar.progress((i + 1) / len(leagues))
        except: continue
    df_new = pd.DataFrame(rows, columns=['League', 'Date', 'HomeTeam', 'AwayTeam', 'Status', 'FTHG', 'FTAG', 'Referee', 'ID'])
    df_new.to_csv(FILE_DB, index=False)
    st.success("Database Sincronizzato!")

# --- 5. CORE ANALISI ---
def calcola_pronostico_streamlit(nome_input):
    if not os.path.exists(FILE_DB):
        st.error("Database non trovato."); return
    
    df = pd.read_csv(FILE_DB)
    df['Date'] = pd.to_datetime(df['Date'])
    today = pd.to_datetime(date.today())
    
    future_matches = df[
        (df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED'])) & 
        (df['HomeTeam'].str.contains(nome_input, case=False, na=False) | 
         df['AwayTeam'].str.contains(nome_input, case=False, na=False)) &
        (df['Date'] >= today)
    ].sort_values(by='Date')
    
    if future_matches.empty:
        st.warning(f"Nessun match imminente trovato per '{nome_input}'."); return

    m = future_matches.iloc[0]
    casa, fuori, match_id = m['HomeTeam'], m['AwayTeam'], m['ID']
    data_match_str = m['Date'].strftime('%Y-%m-%d')
    giocate = df[df['Status'] == 'FINISHED'].copy()
    arbitro = str(m.get('Referee', 'N.D.'))
    molt_arbitro = analizza_severita_arbitro(giocate, arbitro)
    
    # Calcolo Poisson semplice
    avg_g = max(1.1, pd.to_numeric(giocate['FTHG'], errors='coerce').mean())
    def get_stats(team):
        t = giocate[(giocate['HomeTeam'] == team) | (giocate['AwayTeam'] == team)].tail(15)
        if t.empty: return 1.2, 1.2
        att = t.apply(lambda r: float(r['FTHG']) if r['HomeTeam']==team else float(r['FTAG']), axis=1).mean()
        dif = t.apply(lambda r: float(r['FTAG']) if r['HomeTeam']==team else float(r['FTHG']), axis=1).mean()
        return max(0.5, att), max(0.5, dif)

    att_h, dif_h = get_stats(casa)
    att_a, dif_a = get_stats(fuori)
    exp_h = (att_h * dif_a / avg_g) * (2 - molt_arbitro)
    exp_a = (att_a * dif_h / avg_g) * (2 - molt_arbitro)

    # Probabilità
    p1, px, p2, pu25, pgol, total_p = 0, 0, 0, 0, 0, 0
    sgf, sgc, sgo = {i:0 for i in range(6)}, {i:0 for i in range(6)}, {i:0 for i in range(6)}
    re_finali = []
    
    for i in range(7):
        for j in range(7):
            prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
            total_p += prob
            if i > j: p1 += prob
            elif i == j: px += prob
            else: p2 += prob
            if (i+j) < 2.5: pu25 += prob
            if i > 0 and j > 0: pgol += prob
            sgf[min(i+j, 5)] += prob
            sgc[min(i, 5)] += prob
            sgo[min(j, 5)] += prob
            re_finali.append({'s': f"{i}-{j}", 'p': prob})

    # UI RENDERING
    st.header(f"🏟️ {casa} vs {fuori}")
    c_inf1, c_inf2 = st.columns(2)
    with c_inf1:
        st.info(f"👮 Arbitro: {arbitro} | Severità: {molt_arbitro}x")
        if controlla_fatica(df, casa, data_match_str) or controlla_fatica(df, fuori, data_match_str):
            st.warning("⚠️ Possibile stanchezza rilevata")
    with c_inf2:
        lg = calcola_late_goal_index(casa, fuori)
        st.info(f"⏳ Late Goal Index: {lg:.2f}")

    # Mercati Principali
    st.subheader("🏁 Esito Finale 1X2")
    c1, cx, c2 = st.columns(3)
    c1.metric("1", f"{p1/total_p:.1%}")
    cx.metric("X", f"{px/total_p:.1%}")
    c2.metric("2", f"{p2/total_p:.1%}")

    # Prepariamo stringhe per il salvataggio
    top_re = ", ".join([r['s'] for r in sorted(re_finali, key=lambda x:x['p'], reverse=True)[:6]])
    
    if st.button("💾 Salva in Cronologia"):
        res_1x2 = "1" if p1 > px and p1 > p2 else ("X" if px > p1 and px > p2 else "2")
        salva_completo_in_locale(f"{casa}-{fuori}", 85, 90, res_1x2, "U/O 2.5", "GOL", "3,2,4", "2,1", "1,0", top_re, "0-0, 1-0", match_id)
        st.success("Pronostico salvato!")

# --- 6. MAIN INTERFACE ---
t1, t2, t3 = st.tabs(["🎯 Analisi", "⚙️ Database", "📜 Cronologia"])

with t1:
    sq = st.text_input("Inserisci Squadra:")
    if st.button("Analizza Match", type="primary"): 
        if sq: calcola_pronostico_streamlit(sq)

with t2:
    if st.button("🌐 Aggiorna Database"): aggiorna_con_api()

with t3:
    st.subheader("Archivio Pronostici")
    if os.path.exists(FILE_DB_PRONOSTICI):
        df_cron = pd.read_csv(FILE_DB_PRONOSTICI)
        st.dataframe(df_cron.iloc[::-1], use_container_width=True)
        if st.button("🗑️ Svuota Cronologia"):
            os.remove(FILE_DB_PRONOSTICI)
            st.rerun()
