import streamlit as st
import pandas as pd
import math
import requests
import os
import time
from datetime import datetime, date

# --- 1. CONFIGURAZIONE ---
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
            "Top 6 RE Finali", "Top 3 RE 1°T", "Match_ID", "Stato"
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
            "Fiducia nel pronostico": f"{fiducia}%",
            "Affidabilità dei dati": f"{affidabilita}%",
            "1X2": p1x2,
            "U/O 2.5": uo,
            "G/NG": gng,
            "SGF": sgf,
            "SGC": sgc,
            "SGO": sgo,
            "Top 6 Risultati Esatti Finali": re_fin,
            "Top 3 Risultati Esatti 1°T": re_pt,
            "Match_ID": match_id if match_id and str(match_id) != "nan" else "N/A",
            "Stato": "In attesa" # Cambiare in "Vincente" per attivare il verde
        }
        
        df = pd.read_csv(FILE_DB_PRONOSTICI)
        df = pd.concat([df, pd.DataFrame([nuova_riga])], ignore_index=True)
        df.to_csv(FILE_DB_PRONOSTICI, index=False)
        return True
    except Exception as e:
        st.error(f"Errore salvataggio: {e}")
        return False

def stima_quota(prob_decimal):
    if prob_decimal <= 0.01: return 99.00
    return round(1 / prob_decimal, 2)

# --- 3. LOGICA COLORAZIONE ---
def colora_vincenti(val):
    color = 'background-color: #d4edda; color: #155724' if val == "Vincente" else ''
    return color

# --- 4. BANNER ---
if os.path.exists("banner.png"):
    st.image("banner.png", use_container_width=True)
else:
    st.markdown("<h1 style='text-align: center;'>⚽ Delphi Predictor Pro</h1>", unsafe_allow_html=True)


# --- LOGICA MATEMATICA ---
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

# --- AGGIORNAMENTO API ---
def aggiorna_con_api():
    headers = {'X-Auth-Token': API_TOKEN}
    leagues = {
        'WC': 'FIFA World Cup', 'SA':'Serie A', 'PL':'Premier League', 
        'ELC': 'Championship', 'PD':'La Liga', 'BL1':'Bundesliga', 
        'FL1':'Ligue 1', 'DED': 'Eredivisie', 'CL':'UEFA Champions League', 
        'EC': 'UEFA Europa League', 'PPL': 'Primeira Liga', 'BSA': 'Campeonato Brasileiro'
    }
    
    st.info("Inizio connessione API...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    rows = []
    
    try:
        for i, (code, name) in enumerate(leagues.items()):
            status_text.text(f"📥 Scaricando dati: {name}...")
            r = requests.get(f"https://api.football-data.org/v4/competitions/{code}/matches", headers=headers, timeout=12)
            if r.status_code == 200:
                matches = r.json().get('matches', [])
                for m in matches:
                    home = m['homeTeam']['shortName'] or m['homeTeam']['name']
                    away = m['awayTeam']['shortName'] or m['awayTeam']['name']
                    ref = m['referees'][0].get('name', 'N.D.') if m.get('referees') else 'N.D.'
                    rows.append([
                        name, m['utcDate'][:10], home, away, m['status'], 
                        m['score']['fullTime']['home'], m['score']['fullTime']['away'], ref
                    ])
            time.sleep(1.5)
            progress_bar.progress((i + 1) / len(leagues))
        
        df_new = pd.DataFrame(rows, columns=['League', 'Date', 'HomeTeam', 'AwayTeam', 'Status', 'FTHG', 'FTAG', 'Referee'])
        df_new.to_csv(FILE_DB, index=False)
        status_text.text("✅ Database Salvato!")
        st.success("Sincronizzazione completata!")
    except Exception as e: 
        st.error(f"Errore API: {e}")

# --- ANALISI ---
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
    casa, fuori = m['HomeTeam'], m['AwayTeam']
    data_match_str = m['Date'].strftime('%Y-%m-%d')
    
    giocate = df[df['Status'] == 'FINISHED'].copy()
    arbitro = str(m.get('Referee', 'N.D.'))
    molt_arbitro = analizza_severita_arbitro(giocate, arbitro)
    
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

    # Probabilità e Mercati
    p_u25, p_gol, total_p = 0, 0, 0
    p_1, p_x, p_2 = 0, 0, 0
    sgf, sgc, sgo = {i:0 for i in range(6)}, {i:0 for i in range(6)}, {i:0 for i in range(6)}
    re_finali = []
    
    for i in range(7):
        for j in range(7):
            prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
            total_p += prob
            # Esito 1X2
            if i > j: p_1 += prob
            elif i == j: p_x += prob
            else: p_2 += prob
            # Altri mercati
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

    # --- UI ---
    st.header(f"🏟️ {casa} vs {fuori}")
    st.subheader(f"🏆 {m['League']}  |  📅 {data_match_str}")


# --- ASSICURATI CHE QUESTE VARIABILI SIANO CALCOLARE PRIMA ---
# Esempio: 
# arbitro, molt_arbitro = "Orsato", 1.2
# lg = 1.35
# late_goal_val = calcola_late_goal_index(dati...) 

c_inf1, c_inf2 = st.columns(2)

with c_inf1:
    # Mostra l'arbitro e la sua severità
    st.info(f"👮 Arbitro: {arbitro}  |  Severità: {molt_arbitro}x")
    
    # Controlla la fatica (Assicurati che data_match_str sia un oggetto datetime o stringa valida per la funzione)
    fatica_casa = controlla_fatica(df, casa, data_match_str)
    fatica_fuori = controlla_fatica(df, fuori, data_match_str)
    
    if fatica_casa or fatica_fuori:
        st.warning("⚠️ Possibile stanchezza da impegni ravvicinati")

with c_inf2:
    # Qui usiamo una variabile (es. lg) che contiene il valore numerico calcolato
    lg = calcola_late_goal_index(casa, fuori)
    st.info(f"⏳ Late Goal Index - Parametro: {lg:.2f}")
    
    # Alert visivo se l'indice supera la soglia
    if lg > 1.2: 
        st.error("🔥 ALTA PROBABILITÀ LATE GOAL")



    # --- ESITO FINALE 1X2 (BLU) ---
    st.divider()
    st.subheader("🏁 Esito Finale 1X2")
    c1, cx, c2 = st.columns(3)
    with c1:
        prob1 = p_1/total_p
        st.info(f"**1 (Casa):** {prob1:.1%} (Q: {stima_quota(prob1)})")
    with cx:
        probx = p_x/total_p
        st.info(f"**X (Pareggio):** {probx:.1%} (Q: {stima_quota(probx)})")
    with c2:
        prob2 = p_2/total_p
        st.info(f"**2 (Ospite):** {prob2:.1%} (Q: {stima_quota(prob2)})")

    # --- UNDER/OVER & GOL (BLU) ---
    st.divider()
    st.subheader("🏁 Mercati Under/Over & Gol")
    cuo, cgng = st.columns(2)
    with cuo:
        pu = p_u25/total_p
        st.info(f"**U2.5:** {pu:.1%} (Q: {stima_quota(pu)}) | **O2.5:** {(1-pu):.1%} (Q: {stima_quota(1-pu)})")
    with cgng:
        pg = p_gol/total_p
        st.info(f"**GOL:** {pg:.1%} (Q: {stima_quota(pg)}) | **NOGOL:** {(1-pg):.1%} (Q: {stima_quota(1-pg)})")

    # --- SOMME GOL (VERDI) ---
    st.divider()
    st.subheader("⚽ Analisi Somme Gol")
    c_sgf, c_sgc, c_sgo = st.columns(3)
    with c_sgf:
        st.write("**Top 3 Totali**")
        for k, v in sorted(sgf.items(), key=lambda x:x[1], reverse=True)[:3]:
            p = v/total_p
            st.success(f"**{k if k<5 else '>4'} G:** {p:.1%} (Q: {stima_quota(p)})")
    with c_sgc:
        st.write("**Top 2 Casa**")
        for k, v in sorted(sgc.items(), key=lambda x:x[1], reverse=True)[:2]:
            p = v/total_p
            st.success(f"**{k} G:** {p:.1%} (Q: {stima_quota(p)})")
    with c_sgo:
        st.write("**Top 2 Ospite**")
        for k, v in sorted(sgo.items(), key=lambda x:x[1], reverse=True)[:2]:
            p = v/total_p
            st.success(f"**{k} G:** {p:.1%} (Q: {stima_quota(p)})")

    # --- RISULTATI ESATTI (VERDI E BLU) ---
    st.divider()
    st.subheader("🎯 Risultati Esatti")
    cr1, cr2 = st.columns([2, 1])
    with cr1:
        st.write("**Top 6 Finale**")
        for r in sorted(re_finali, key=lambda x:x['p'], reverse=True)[:6]:
            p = r['p']/total_p
            st.success(f"**{r['s']}** ➡️ {p:.1%} (Q: {stima_quota(p)})")
    with cr2:
        st.write("**Top 3 1° Tempo**")
        for r in sorted(re_1t, key=lambda x:x['p'], reverse=True)[:3]:
            p = r['p']/total_p_1t
            st.info(f"**{r['s']}** ➡️ {p:.1%} (Q: {stima_quota(p)})")

# --- MAIN ---
st.set_page_config(page_title="Delphi Pro", layout="wide")
t1, t2, t3 = st.tabs(["🎯 Analisi", "⚙️ Database", "📜 Cronologia"])
with t1:
    sq = st.text_input("Squadra:")
    if st.button("Analizza Match", type="primary"): 
        if sq: calcola_pronostico_streamlit(sq)
with t2:
    if st.button("🌐 Aggiorna Database"): aggiorna_con_api()

with t3:
    if st.button("✅ Verifica pronostici vincenti"): vincente()

    # Salvataggio in background
    salva_in_cronologia(f"{casa}-{fuori}", calcola_late_goal_index(casa, fuori), fiducia_val, affidabilita_val)

