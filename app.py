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

# --- 1.1. BANNER ---
if os.path.exists("banner.png"):
    st.image("banner.png", use_container_width=True)
else:
    st.markdown("<h1 style='text-align: center;'>⚽ Delphi Predictor Pro</h1>", unsafe_allow_html=True)

API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'
FILE_DB_CALCIO = 'database_pro_2025.csv'
FILE_DB_PRONOSTICI = 'database_pronostici.csv'

# --- 2. FUNZIONI LOGICHE DI VERIFICA (CASELLE VERDI) ---
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

def salva_completo_in_locale(data_dict):
    try:
        df = pd.read_csv(FILE_DB_PRONOSTICI)
        # Creiamo un DataFrame da una singola riga (il dizionario)
        nuova_riga = pd.DataFrame([data_dict])
        df = pd.concat([df, nuova_riga], ignore_index=True)
        df.to_csv(FILE_DB_PRONOSTICI, index=False)
        return True
    except Exception as e:
        st.error(f"Errore salvataggio: {e}")
        return False

# --- 4. FUNZIONI AGGIORNAMENTO API ---
def aggiorna_database_calcio():
    headers = {'X-Auth-Token': API_TOKEN}
    # Aggiungi qui altre leghe se vuoi (es. 'FL1' per Francia, 'BL1' per Germania)
    competitions = ['SA', 'PL', 'ELC', 'PD', 'BL1', 'FL1', 'CL', 'PPL', 'DED', 'EC', 'WC', 'BSA'] 
    
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
                    # IMPORTANTE: Salviamo l'ID
                    rows.append([
                        comp, m['utcDate'], home, away, m['status'], 
                        m['score']['fullTime']['home'], m['score']['fullTime']['away'], 
                        ref, m['id']
                    ])
            time.sleep(1) 
            progress_bar.progress((i + 1) / len(competitions))
        
        # Salviamo con la colonna ID
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
        # Aggiorna solo se manca il risultato e c'è un ID valido
        if row['Risultato_Reale'] == "N/D" and str(row['Match_ID']) not in ["N/A", "nan"]:
            try:
                match_id = int(float(row['Match_ID']))
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
                time.sleep(1)
            except Exception as e:
                print(f"Errore check match {row['Match_ID']}: {e}")
        progress_bar.progress((i + 1) / len(df))
    
    if changes > 0:
        df.to_csv(FILE_DB_PRONOSTICI, index=False)
        st.success(f"Aggiornati {changes} risultati!")
    else:
        st.info("Nessun nuovo risultato trovato.")

# --- 5. LOGICA MATEMATICA E ANALISI ---
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
        media_tot = (df['FTHG'] + df['FTAG']).mean()
        media_arb = (partite['FTHG'] + partite['FTAG']).mean()
        if pd.isna(media_arb) or pd.isna(media_tot): return 1.0
        return round(max(0.8, min(1.3, media_tot / media_arb)), 2)
    except: return 1.0

def controlla_fatica(df, squadra, data_match):
    try:
        data_m = pd.to_datetime(data_match).tz_localize(None)
        storico = df[(df['Status'] == 'FINISHED') & 
                    ((df['HomeTeam'] == squadra) | (df['AwayTeam'] == squadra))].copy()
        if storico.empty:
            return False
        storico['Date'] = pd.to_datetime(storico['Date']).dt.tz_localize(None)
        ultima_partita = storico[storico['Date'] < data_m]['Date'].max()
        if pd.notnull(ultima_partita):
            return (data_m - ultima_partita).days <= 4
    except:
        pass
    return False

def calcola_late_goal_index(casa, fuori):
    # Placeholder per logica late goal
    val = (len(str(casa)) + len(str(fuori))) % 10
    return round(val * 0.10 + 0.5, 2)

def esegui_analisi(nome_input):
    # Controlla DB
    if not os.path.exists(FILE_DB_CALCIO):
        st.error("Database Calcio mancante. Aggiorna il DB"); return None
    
    df = pd.read_csv(FILE_DB_CALCIO)
    df['Date'] = pd.to_datetime(df['Date'])
    today = pd.to_datetime(date.today())
    
    # Filtra Match
    future_matches = df[
        (df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED'])) & 
        (df['HomeTeam'].str.contains(nome_input, case=False, na=False) | 
         df['AwayTeam'].str.contains(nome_input, case=False, na=False)) &
        (df['Date'] >= today)
    ].sort_values(by='Date')
    
    if future_matches.empty:
        st.warning(f"Nessun match futuro trovato per '{nome_input}'."); return None

    m = future_matches.iloc[0]
    
    # Dati match
    casa, fuori = m['HomeTeam'], m['AwayTeam']
    match_id = m.get('ID', 'N/A') # Usa .get per evitare crash
    data_match = m['Date'].strftime('%d/%m/%Y')
    
    # Stats Arbitro e Team
    giocate = df[df['Status'] == 'FINISHED'].copy()
    arbitro = str(m.get('Referee', 'N.D.'))
    molt_arbitro = analizza_severita_arbitro(giocate, arbitro)
    avg_g = max(1.1, pd.to_numeric(giocate['FTHG'], errors='coerce').mean())
    
    def get_stats(team):
        t = giocate[(giocate['HomeTeam'] == team) | (giocate['AwayTeam'] == team)].tail(15)
        if t.empty: return 1.2, 1.2
        gf = t.apply(lambda r: r['FTHG'] if r['HomeTeam']==team else r['FTAG'], axis=1).mean()
        gs = t.apply(lambda r: r['FTAG'] if r['HomeTeam']==team else r['FTHG'], axis=1).mean()
        return max(0.5, gf), max(0.5, gs)

    att_h, dif_h = get_stats(casa)
    att_a, dif_a = get_stats(fuori)
    
    exp_h = (att_h * dif_a / avg_g) * (2 - molt_arbitro)
    exp_a = (att_a * dif_h / avg_g) * (2 - molt_arbitro)
    
    # Poisson finale
    p1, px, p2, pu, pg, tot = 0,0,0,0,0,0
    sgf, sgc, sgo = {i:0 for i in range(6)}, {i:0 for i in range(6)}, {i:0 for i in range(6)}
    re_fin, re_1t = [], []
    
    for i in range(6):
        for j in range(6):
            prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
            tot += prob
            
            #Pronostico 1X2
            if i>j: p1+=prob
            elif i==j: px+=prob
            else: p2+=prob

            #Pronostico U/O 2,5 e G/NG
            if i+j < 2.5: pu+=prob
            if i>0 and j>0: pg+=prob

            #Pronostico Somma Gol
            sgf[min(i+j, 5)] += prob
            sgc[min(i, 5)] += prob
            sgo[min(j, 5)] += prob
            re_fin.append({'s': f"{i}-{j}", 'p': prob})
            
    # Poisson 1T
    eh1, ea1 = exp_h*0.42, exp_a*0.42
    re_1t, total_p_1t = [], 0
    for i in range(4):
        for j in range(4):
            pb = poisson_probability(i, eh1) * poisson_probability(j, ea1)
            total_p_1t += pb
            re_1t.append({'s': f"{i}-{j}", 'p': pb})
   
    # Preparazione Dati per Session State
    p1, px, p2 = p1/tot, px/tot, p2/tot
    pu, pg = pu/tot, pg/tot
    
    # Logica scelta pronostico
    res_1x2 = "1" if p1 > px and p1 > p2 else ("X" if px > p1 and px > p2 else "2")
    res_uo = "OVER 2.5" if (1-pu) > 0.5 else "UNDER 2.5"
    res_gng = "GOL" if pg > 0.5 else "NO GOL"
    
    # Stringhe per DB
    top_re = ", ".join([x['s'] for x in sorted(re_fin, key=lambda x:x['p'], reverse=True)[:6]])
    top_re1t = ", ".join([x['s'] for x in sorted(re_1t, key=lambda x:x['p'], reverse=True)[:3]])
    top_sgf = ", ".join(map(str, [k for k,v in sorted(sgf.items(), key=lambda x:x[1], reverse=True)[:3]]))
    top_sgc = ", ".join(map(str, [k for k,v in sorted(sgc.items(), key=lambda x:x[1], reverse=True)[:2]]))
    top_sgo = ", ".join(map(str, [k for k,v in sorted(sgo.items(), key=lambda x:x[1], reverse=True)[:2]]))
    
    fuso_ita = pytz.timezone('Europe/Rome')
    adesso = datetime.now(fuso_ita)
        # --- CALCOLO DATA E ORA REALE DELL'EVENTO ---
    # Convertiamo la stringa del DB in oggetto data
    dt_event = pd.to_datetime(m['Date'])
    
    # Se la data non ha fuso orario (è UTC grezzo), glielo assegniamo e convertiamo a Roma
    if dt_event.tzinfo is None:
        dt_event = dt_event.tz_localize('UTC')
    
    dt_event_ita = dt_event.astimezone(pytz.timezone('Europe/Rome'))

    return {
        # Usiamo dt_event_ita invece di 'adesso'
        "Data": dt_event_ita.strftime("%d/%m/%Y"), 
        "Ora": dt_event_ita.strftime("%H:%M"),
        "League": m['League']
        "Partita": f"{casa} vs {fuori}",
        "Fiducia": f"{int(max(p1,px,p2)*100)}%", 
        "Affidabilità": f"{85 + int(molt_arbitro*2)}%",
        "1X2": res_1x2, "U/O 2.5": res_uo, "G/NG": res_gng,
        "SGF": top_sgf, "SGC": top_sgc, "SGO": top_sgo,
        "Top 6 RE Finali": top_re, "Top 3 RE 1°T": top_re1t,
        "Match_ID": match_id,
        "Risultato_Reale": "N/D", "PT_Reale": "N/D",
        # Dati extra per visualizzazione
        "p1": p1, "px": px, "p2": p2, "lg": calcola_late_goal_index(casa, fuori),
        "arbitro": arbitro, "molt_arbitro": molt_arbitro
    }

# --- 6. LOGICA DI COLORAZIONE TABELLA ---
def highlight_winners(row):
    colors = [''] * len(row)
    if row['Risultato_Reale'] == "N/D": return colors
    try:
        h, a = map(int, row['Risultato_Reale'].split('-'))
        ph, pa = map(int, row['PT_Reale'].split('-'))
    except: return colors

    green = 'background-color: #d4edda; color: #155724; font-weight: bold'
    
    # Indici colonne: 5=1X2, 6=UO, 7=GNG, 8=SGF, 9=SGC, 10=SGO, 11=RE_F, 12=RE_P
    if check_1x2(row['1X2'], h, a): colors[5] = green
    if check_uo(row['U/O 2.5'], h, a): colors[6] = green
    if check_gng(row['G/NG'], h, a): colors[7] = green
    if check_in_list(row['SGF'], h+a): colors[8] = green
    if check_in_list(row['SGC'], h): colors[9] = green
    if check_in_list(row['SGO'], a): colors[10] = green
    if check_in_list(row['Top 6 RE Finali'], row['Risultato_Reale']): colors[11] = green
    if check_in_list(row['Top 3 RE 1°T'], row['PT_Reale']): colors[12] = green
    return colors

# --- 7. MAIN ---
tab1, tab2, tab3 = st.tabs(["🎯 Analisi", "⚙️ Database", "📜 Cronologia"])

with tab1:
    sq = st.text_input("Inserisci Squadra:")
    
    if st.button("Pronostici Match", type="primary"):
        if sq:
            risultati = esegui_analisi(sq)
            if risultati:
                st.session_state['pronostico_corrente'] = risultati
            else:
                st.session_state['pronostico_corrente'] = None

    if 'pronostico_corrente' in st.session_state and st.session_state['pronostico_corrente']:
        d = st.session_state['pronostico_corrente']
        df_per_fatica = pd.read_csv(FILE_DB_CALCIO) # Carichiamo il DB qui per usarlo sotto

        # --- UI TESTATA ---
        st.header(f"🏟️ {d['Partita']}")
        st.subheader(f"🏆 {d.get('League', 'N.D.')} | 📅 Data: {d['Data']} ore {d['Ora']}")

        # TUTTO IL CODICE SUCCESSIVO (c_inf1, c_inf2, st.divider, ecc.) 
        # DEVE ESSERE ALLINEATO QUI (indentato di 8 spazi o 2 tab)

c_inf1, c_inf2 = st.columns(2)

with c_inf1:
    st.info(f"👮 Arbitro: {d['nome_arbitro']}  |  Severità: {d['molt_arbitro']}x")
    casa_nome = d['Partita'].split(" vs ")[0]
    fuori_nome = d['Partita'].split(" vs ")[1]
    if controlla_fatica(df_per_fatica, casa_nome, d['Data']) or \
    controlla_fatica(df_per_fatica, fuori_nome, d['Data']):
        st.warning("⚠️ Possibile stanchezza: una delle squadre ha giocato meno di 4 giorni fa.")

with c_inf2:
    st.info(f"⏳ Late Goal Index: {d['lg']:.2f}")
    if d['lg'] > 1.2: 
        st.error("🔥 ALTA PROBABILITÀ DI GOL NEL FNALE (80+ MINUTO)")

        # --- ESITO FINALE 1X2 ---
        st.divider()
        st.subheader("🏁 Esito Finale 1X2")
        c1, cx, c2 = st.columns(3)
        with c1:
            st.metric("1 (Casa)", f"{d['p1']:.1%}", f"Quota: {stima_quota(d['p1'])}")
        with cx:
            st.metric("X (Pareggio)", f"{d['px']:.1%}", f"Quota: {stima_quota(d['px'])}")
        with c2:
            st.metric("2 (Ospite)", f"{d['p2']:.1%}", f"Quota: {stima_quota(d['p2'])}")

        # --- MERCATI ACCESSORI ---
        st.divider()
        col_uo, col_gng = st.columns(2)
        with col_uo:
            st.write(f"**U/O 2.5:** {d['U/O 2.5']}")
        with col_gng:
            st.write(f"**GOL/NOGOL:** {d['G/NG']}")

        # --- RISULTATI E SOMME ---
        st.divider()
        cr1, cr2 = st.columns(2)
        with cr1:
            st.success(f"🎯 **Top Risultati Finali:** {d['Top 6 RE Finali']}")
            st.success(f"⚽ **Somma Gol Totale:** {d['SGF']}")
        with cr2:
            st.info(f"⏱️ **Top Risultati 1° Tempo:** {d['Top 3 RE 1°T']}")
            st.info(f"🏠 **Somma Gol Casa:** {d['SGC']} | 🚀 **Ospite:** {d['SGO']}")

        # --- TASTO SALVATAGGIO ---
        st.write("---")
        if st.button("💾 Salva in Cronologia"):
            # Rimuoviamo le chiavi extra non necessarie per il CSV
            dati_per_csv = {k: v for k, v in d.items() if k not in ['p1', 'px', 'p2', 'lg', 'arbitro', 'molt_arbitro']}
            if salva_completo_in_locale(dati_per_csv):
                st.success("✅ Pronostico Salvato in Cronologia!")
