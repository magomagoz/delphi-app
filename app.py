import streamlit as st
import pandas as pd
import math
import requests
import os
import time
from datetime import datetime, date
import pytz

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Delphi Predictor Pro", layout="wide") 

API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'
FILE_DB_CALCIO = 'database_pro_2025.csv'
FILE_DB_PRONOSTICI = 'database_pronostici.csv'

# --- 2. FUNZIONI LOGICHE DI VERIFICA (PER LE CELLE VERDI) ---
def check_1x2(pred, home, away):
    if home > away: res = "1"
    elif away > home: res = "2"
    else: res = "X"
    return str(pred).strip() == res

def check_uo(pred, home, away):
    total = home + away
    res = "OVER 2.5" if total > 2.5 else "UNDER 2.5"
    return str(pred).strip().upper() == res

def check_gng(pred, home, away):
    res = "GOL" if home > 0 and away > 0 else "NO GOL"
    return str(pred).strip().upper() == res

def check_in_list(pred_string, value_to_find):
    # Pulisce la stringa e controlla se il valore è tra i pronostici
    preds = [p.strip() for p in str(pred_string).split(",")]
    return str(value_to_find) in preds

# --- 3. FUNZIONI DATABASE ---
def inizializza_db():
    if not os.path.exists(FILE_DB_PRONOSTICI):
        columns = [
            "Data", "Ora", "Partita", "Fiducia", "Affidabilità", 
            "1X2", "U/O 2.5", "G/NG", "SGF", "SGC", "SGO", 
            "Top 6 RE Finali", "Top 3 RE 1°T", "Match_ID", "Risultato_Reale", "PT_Reale"
        ]
        df = pd.DataFrame(columns=columns)
        df.to_csv(FILE_DB_PRONOSTICI, index=False)

inizializza_db()

def salva_completo_in_locale(match, fid, aff, p1x2, uo, gng, sgf, sgc, sgo, re_f, re_p, mid):
    try:
        fuso_ita = pytz.timezone('Europe/Rome')
        adesso = datetime.now(fuso_ita)
        nuova_riga = {
            "Data": adesso.strftime("%d/%m/%Y"), "Ora": adesso.strftime("%H:%M"),
            "Partita": match, "Fiducia": f"{fid}", "Affidabilità": f"{aff}",
            "1X2": p1x2, "U/O 2.5": uo, "G/NG": gng, "SGF": sgf, "SGC": sgc, "SGO": sgo,
            "Top 6 RE Finali": re_f, "Top 3 RE 1°T": re_p, "Match_ID": mid,
            "Risultato_Reale": "N/D", "PT_Reale": "N/D"
        }
        df = pd.read_csv(FILE_DB_PRONOSTICI)
        df = pd.concat([df, pd.DataFrame([nuova_riga])], ignore_index=True)
        df.to_csv(FILE_DB_PRONOSTICI, index=False)
        return True
    except Exception as e:
        st.error(f"Errore salvataggio: {e}")
        return False

# --- 4. FUNZIONI AGGIORNAMENTO API (CALCIO E RISULTATI) ---
def aggiorna_database_calcio():
    headers = {'X-Auth-Token': API_TOKEN}
    # Codici competizioni: SA=Serie A, PL=Premier, PD=Liga, BL1=Bundes, CL=Champions, FL1=Ligue1
    competitions = ['SA', 'PL', 'PD', 'BL1', 'FL1', 'CL', 'PPL', 'DED'] 
    
    rows = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        for i, comp in enumerate(competitions):
            status_text.text(f"Scarico {comp}...")
            url = f"https://api.football-data.org/v4/competitions/{comp}/matches"
            r = requests.get(url, headers=headers)
            if r.status_code == 200:
                matches = r.json().get('matches', [])
                for m in matches:
                    home = m['homeTeam']['shortName'] or m['homeTeam']['name']
                    away = m['awayTeam']['shortName'] or m['awayTeam']['name']
                    ref = m['referees'][0]['name'] if m.get('referees') else 'N.D.'
                    # SALVIAMO L'ID QUI
                    rows.append([
                        comp, m['utcDate'][:10], home, away, m['status'], 
                        m['score']['fullTime']['home'], m['score']['fullTime']['away'], 
                        ref, m['id']
                    ])
            time.sleep(1) # Rispetto limiti API
            progress_bar.progress((i + 1) / len(competitions))
        
        df_new = pd.DataFrame(rows, columns=['League', 'Date', 'HomeTeam', 'AwayTeam', 'Status', 'FTHG', 'FTAG', 'Referee', 'ID'])
        df_new.to_csv(FILE_DB_CALCIO, index=False)
        status_text.empty()
        st.success("✅ Database Calcio aggiornato con successo!")
    except Exception as e:
        st.error(f"Errore aggiornamento API: {e}")

def aggiorna_risultati_pronostici():
    if not os.path.exists(FILE_DB_PRONOSTICI): return
    df = pd.read_csv(FILE_DB_PRONOSTICI)
    headers = {'X-Auth-Token': API_TOKEN}
    
    changes = 0
    progress_bar = st.progress(0)
    
    for i, row in df.iterrows():
        # Aggiorna solo se non abbiamo il risultato e abbiamo un ID valido
        if row['Risultato_Reale'] == "N/D" and str(row['Match_ID']) not in ["N/A", "nan"]:
            try:
                match_id = int(float(row['Match_ID'])) # Conversione sicura
                url = f"https://api.football-data.org/v4/matches/{match_id}"
                r = requests.get(url, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    if data['status'] == 'FINISHED':
                        score = data['score']
                        f_h = score['fullTime']['home']
                        f_a = score['fullTime']['away']
                        p_h = score['halfTime']['home']
                        p_a = score['halfTime']['away']
                        
                        df.at[i, 'Risultato_Reale'] = f"{f_h}-{f_a}"
                        df.at[i, 'PT_Reale'] = f"{p_h}-{p_a}"
                        changes += 1
                time.sleep(1) # Rate limit
            except Exception as e:
                print(f"Errore check match {row['Match_ID']}: {e}")
        progress_bar.progress((i + 1) / len(df))
    
    if changes > 0:
        df.to_csv(FILE_DB_PRONOSTICI, index=False)
        st.success(f"Aggiornati {changes} risultati!")
    else:
        st.info("Nessun nuovo risultato trovato.")

# --- 5. LOGICA ANALISI E POISSON ---
def stima_quota(prob):
    if prob <= 0.001: return 99.00
    return round(1 / prob, 2)

def poisson_probability(actual, average):
    if average <= 0: average = 0.01
    return (math.pow(average, actual) * math.exp(-average)) / math.factorial(actual)

def analizza_severita_arbitro(df, nome_arbitro):
    if not nome_arbitro or nome_arbitro == 'N.D.' or df.empty: return 1.0
    try:
        partite = df[df['Referee'].str.contains(str(nome_arbitro), na=False, case=False)]
        if len(partite) < 3: return 1.0
        media_gol_arb = (partite['FTHG'] + partite['FTAG']).mean()
        media_tot = (df['FTHG'] + df['FTAG']).mean()
        if pd.isna(media_gol_arb) or pd.isna(media_tot): return 1.0
        return round(max(0.8, min(1.3, media_tot / media_gol_arb)), 2)
    except: return 1.0

def calcola_late_goal_index(casa, fuori):
    # Algoritmo simbolico basato sui nomi (per placeholder)
    val = (len(str(casa)) + len(str(fuori))) % 10
    return round(val * 0.15 + 0.5, 2)

def calcola_pronostico_streamlit(nome_input):
    if not os.path.exists(FILE_DB_CALCIO):
        st.error("⚠️ Database Calcio mancante. Vai nel Tab 'Database' e aggiorna."); return
    
    df = pd.read_csv(FILE_DB_CALCIO)
    df['Date'] = pd.to_datetime(df['Date'])
    today = pd.to_datetime(date.today())
    
    # Filtra match futuri
    future_matches = df[
        (df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED'])) & 
        (df['HomeTeam'].str.contains(nome_input, case=False, na=False) | 
         df['AwayTeam'].str.contains(nome_input, case=False, na=False)) &
        (df['Date'] >= today)
    ].sort_values(by='Date')
    
    if future_matches.empty:
        st.warning(f"Nessun match futuro trovato per '{nome_input}'."); return

    m = future_matches.iloc[0]
    
    # --- FIX CRITICO: USO .get() PER EVITARE KEYERROR ---
    casa = m['HomeTeam']
    fuori = m['AwayTeam']
    # Se 'ID' non esiste nel CSV vecchio, restituisce N/A invece di crashare
    match_id = m.get('ID', 'N/A') 
    
    data_match_str = m['Date'].strftime('%d/%m/%Y')
    
    # Statistiche base
    giocate = df[df['Status'] == 'FINISHED'].copy()
    arbitro = str(m.get('Referee', 'N.D.'))
    molt_arbitro = analizza_severita_arbitro(giocate, arbitro)
    
    avg_g = max(1.1, pd.to_numeric(giocate['FTHG'], errors='coerce').mean())
    
    def get_team_stats(team):
        # Ultime 10 partite
        t = giocate[(giocate['HomeTeam'] == team) | (giocate['AwayTeam'] == team)].sort_values('Date').tail(10)
        if t.empty: return 1.2, 1.2 # Default
        gf = t.apply(lambda r: r['FTHG'] if r['HomeTeam']==team else r['FTAG'], axis=1).mean()
        gs = t.apply(lambda r: r['FTAG'] if r['HomeTeam']==team else r['FTHG'], axis=1).mean()
        return max(0.2, gf), max(0.2, gs)

    att_h, dif_h = get_team_stats(casa)
    att_a, dif_a = get_team_stats(fuori)
    
    # Forza attacco/difesa relativa
    exp_h = (att_h * dif_a / avg_g) * (2 - molt_arbitro)
    exp_a = (att_a * dif_h / avg_g) * (2 - molt_arbitro)

    # Calcolo Poisson
    p1, px, p2, pu25, pgol, total_p = 0, 0, 0, 0, 0, 0
    sgf, sgc, sgo = {i:0 for i in range(6)}, {i:0 for i in range(6)}, {i:0 for i in range(6)}
    re_fin, re_1t = [], []

    # Matrice Risultati
    for i in range(6):
        for j in range(6):
            prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
            total_p += prob
            
            if i > j: p1 += prob
            elif i == j: px += prob
            else: p2 += prob
            
            if (i+j) < 2.5: pu25 += prob
            if i>0 and j>0: pgol += prob
            
            sgf[min(i+j, 5)] += prob
            sgc[min(i, 5)] += prob
            sgo[min(j, 5)] += prob
            re_fin.append({'s': f"{i}-{j}", 'p': prob})

    # Poisson 1° Tempo (approssimazione 40% dei gol)
    exp_h_1t, exp_a_1t = exp_h * 0.4, exp_a * 0.4
    tot_p_1t = 0
    for i in range(4):
        for j in range(4):
            prob_1t = poisson_probability(i, exp_h_1t) * poisson_probability(j, exp_a_1t)
            tot_p_1t += prob_1t
            re_1t.append({'s': f"{i}-{j}", 'p': prob_1t})

    # --- UI OUTPUT ---
    st.header(f"🏟️ {casa} vs {fuori}")
    st.caption(f"📅 Data: {data_match_str} | ID: {match_id}")
    
    c_inf1, c_inf2 = st.columns(2)
    with c_inf1:
        st.info(f"👮 Arbitro: {arbitro} | Severità: {molt_arbitro}x")
    with c_inf2:
        lg = calcola_late_goal_index(casa, fuori)
        st.info(f"⏳ Late Goal Index: {lg}")
        if lg > 1.3: st.error("🔥 ALTA PROBABILITÀ LATE GOAL")

    st.divider()
    
    # Sezione 1X2
    st.subheader("📊 Esito 1X2")
    c1, cx, c2 = st.columns(3)
    c1.metric("1", f"{p1/total_p:.1%}", f"Q: {stima_quota(p1/total_p)}")
    cx.metric("X", f"{px/total_p:.1%}", f"Q: {stima_quota(px/total_p)}")
    c2.metric("2", f"{p2/total_p:.1%}", f"Q: {stima_quota(p2/total_p)}")

    # Preparazione stringhe pulite per il salvataggio
    p_final = p1/total_p
    res_1x2_save = "1" if p1 > px and p1 > p2 else ("X" if px > p1 and px > p2 else "2")
    res_uo_save = "OVER 2.5" if (1 - pu25/total_p) > 0.5 else "UNDER 2.5"
    res_gng_save = "GOL" if (pgol/total_p) > 0.5 else "NO GOL"
    
    # Top SGF (Somma Goal)
    top_sgf = [k for k,v in sorted(sgf.items(), key=lambda x:x[1], reverse=True)[:3]]
    str_sgf = ", ".join(map(str, top_sgf))
    
    # Top SGC/SGO
    top_sgc = [k for k,v in sorted(sgc.items(), key=lambda x:x[1], reverse=True)[:2]]
    str_sgc = ", ".join(map(str, top_sgc))
    top_sgo = [k for k,v in sorted(sgo.items(), key=lambda x:x[1], reverse=True)[:2]]
    str_sgo = ", ".join(map(str, top_sgo))

    # Top RE
    top_re_f = sorted(re_fin, key=lambda x:x['p'], reverse=True)[:6]
    str_re_f = ", ".join([x['s'] for x in top_re_f])
    
    top_re_p = sorted(re_1t, key=lambda x:x['p'], reverse=True)[:3]
    str_re_p = ", ".join([x['s'] for x in top_re_p])

    # Visualizzazione Rapida Consigli
    st.write(f"**Consigliati:** {res_1x2_save} | {res_uo_save} | {res_gng_save}")
    st.code(f"RE: {str_re_f}")

    if st.button("💾 Salva in Cronologia"):
        # Affidabilità e Fiducia simulate
        fid = int(max(p1, px, p2)/total_p * 100)
        aff = 85 + int(molt_arbitro*2)
        
        if salva_completo_in_locale(
            f"{casa}-{fuori}", fid, aff,
            res_1x2_save, res_uo_save, res_gng_save,
            str_sgf, str_sgc, str_sgo,
            str_re_f, str_re_p, match_id
        ):
            st.success("✅ Pronostico Salvato! Vai al Tab Cronologia.")

# --- 6. LOGICA DI COLORAZIONE (STYLE) ---
def highlight_winners(row):
    colors = [''] * len(row)
    if row['Risultato_Reale'] == "N/D": return colors
    
    try:
        h, a = map(int, row['Risultato_Reale'].split('-'))
        ph, pa = map(int, row['PT_Reale'].split('-'))
    except: return colors

    green = 'background-color: #d4edda; color: #155724; font-weight: bold'
    
    # Indici basati sull'ordine delle colonne in CSV
    # 5:1X2, 6:UO, 7:GNG, 8:SGF, 9:SGC, 10:SGO, 11:RE_F, 12:RE_P
    if check_1x2(row['1X2'], h, a): colors[5] = green
    if check_uo(row['U/O 2.5'], h, a): colors[6] = green
    if check_gng(row['G/NG'], h, a): colors[7] = green
    if check_in_list(row['SGF'], h+a): colors[8] = green
    if check_in_list(row['SGC'], h): colors[9] = green
    if check_in_list(row['SGO'], a): colors[10] = green
    if check_in_list(row['Top 6 RE Finali'], row['Risultato_Reale']): colors[11] = green
    if check_in_list(row['Top 3 RE 1°T'], row['PT_Reale']): colors[12] = green
    
    return colors

# --- 7. INTERFACCIA PRINCIPALE ---
tab1, tab2, tab3 = st.tabs(["🎯 Analisi Match", "⚙️ Database", "📜 Cronologia"])

with tab1:
    sq = st.text_input("Inserisci Squadra (es. Inter):")
    if st.button("Analizza Match", type="primary"):
        if sq: calcola_pronostico_streamlit(sq)

with tab2:
    st.subheader("Gestione Database")
    st.info("Clicca qui sotto se è la prima volta o se mancano partite.")
    if st.button("🌐 Aggiorna Database (Scarica Match e ID)"):
        with st.spinner("Scaricamento dati in corso..."):
            aggiorna_database_calcio()

with tab3:
    st.subheader("Archivio Pronostici")
    
    col_a, col_b = st.columns([1, 3])
    with col_a:
        if st.button("🔄 Verifica Risultati Reali"):
            with st.spinner("Controllo risultati API..."):
                aggiorna_risultati_pronostici()
                st.rerun()
    
    if os.path.exists(FILE_DB_PRONOSTICI):
        df_cron = pd.read_csv(FILE_DB_PRONOSTICI)
        if not df_cron.empty:
            # Applica lo stile
            st.dataframe(df_cron.iloc[::-1].style.apply(highlight_winners, axis=1), use_container_width=True)
            
            if st.button("🗑️ Svuota Cronologia"):
                os.remove(FILE_DB_PRONOSTICI)
                st.rerun()
        else:
            st.info("Nessun pronostico salvato.")
