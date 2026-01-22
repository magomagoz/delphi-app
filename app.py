import streamlit as st
import pandas as pd
import math
import requests
import os
import time
import re
from datetime import datetime, date
import pytz
from fpdf import FPDF

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Delphi Predictor Pro", layout="wide") 

LEAGUE_MAP = {
    'SA': 'Serie A', 'PL': 'Premier League', 'ELC': 'Championship',
    'PD': 'La Liga', 'BL1': 'Bundesliga', 'FL1': 'Ligue 1',
    'CL': 'UEFA Champions League', 'PPL': 'Primeira Liga', 'DED': 'Eredivisie',
    'BSA': 'Serie A Brasile', 'EC': 'UEFA Nations League', 'WC': 'FIFA World Cup'
}

# --- 1.1. BANNER ---
if os.path.exists("banner.png"):
    st.image("banner.png", use_container_width=True)
else:
    st.markdown("<h1 style='text-align: center;'>⚽ Delphi Predictor Pro</h1>", unsafe_allow_html=True)

API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'
FILE_DB_CALCIO = 'database_pro_2025.csv'
FILE_DB_PRONOSTICI = 'database_pronostici.csv'

# --- 2. FUNZIONI LOGICHE DI VERIFICA ---
def genera_pdf_pronostico(partita, lega, data, consiglio, quote):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    
    # Intestazione
    pdf.cell(190, 10, "DELPHI PREDICTOR - REPORT", ln=True, align='C')
    pdf.ln(10)
    
    # Dettagli Match
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(190, 10, f"Match: {partita}", ln=True)
    pdf.set_font("Arial", '', 11)
    pdf.cell(190, 10, f"Campionato: {lega} | Data: {data}", ln=True)
    pdf.ln(5)
    
    # Pronostico
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(190, 10, f"CONSIGLIO PRINCIPALE: {consiglio}", ln=True, fill=True)
    pdf.ln(5)
    
    # Quote
    pdf.cell(190, 10, f"Dettaglio Quote: {quote}", ln=True)
    
    return pdf.output(dest='S').encode('latin-1')

def check_1x2(pred, home, away):
    if home > away: d = "1"
    elif away > home: d = "2"
    else: d = "X"
    return str(pred).strip() == d

def check_uo(pred, home, away):
    total = home + away
    d = "OVER 2.5" if total > 2.5 else "UNDER 2.5"
    return str(pred).strip().upper() == d

def check_gng(pred, home, away):
    d = "GOL" if home > 0 and away > 0 else "NOGOL"
    return str(pred).strip().upper() == d

def check_in_list(pred_string, value_to_find):
    preds = [p.strip() for p in str(pred_string).split(",")]
    return str(value_to_find).strip() in [p.strip() for p in preds]

# --- 3. FUNZIONI DATABASE (CORRETTE) ---
def get_db_columns():
    return [
        "Data", "Ora", "League", "Partita", "Fiducia", "Affidabilità", 
        "1X2", "U/O 2.5", "G/NG", "SGF", "SGC", "SGO", 
        "Top 6 RE Finali", "Top 3 RE 1°T", "Top 3 HT/FT", "Fatica", "Match_ID", "Risultato_Reale", "PT_Reale"
    ]

def inizializza_db():
    columns = get_db_columns()
    if not os.path.exists(FILE_DB_PRONOSTICI):
        df = pd.DataFrame(columns=columns)
        df.to_csv(FILE_DB_PRONOSTICI, index=False)
    else:
        # Se esiste, controlla che le colonne siano giuste
        try:
            df = pd.read_csv(FILE_DB_PRONOSTICI)
            mancanti = [c for c in columns if c not in df.columns]
            if mancanti:
                for c in mancanti:
                    df[c] = "N/D"
                df.to_csv(FILE_DB_PRONOSTICI, index=False)
        except:
            # Se è corrotto, lo ricrea
            df = pd.DataFrame(columns=columns)
            df.to_csv(FILE_DB_PRONOSTICI, index=False)

# ESEGUIAMO SUBITO L'INIZIALIZZAZIONE
inizializza_db()

def crea_backup_automatico():
    if not os.path.exists("backups"):
        os.makedirs("backups")
    
    if os.path.exists(FILE_DB_PRONOSTICI):
        # Controlliamo che il file non sia vuoto (almeno più di 100 byte per sicurezza)
        if os.path.getsize(FILE_DB_PRONOSTICI) < 50: 
            return # Evitiamo di backuppare un file vuoto o solo intestazioni

        data_oggi = datetime.now().strftime("%Y-%m-%d")
        nome_backup = f"backups/pronostici_backup_{data_oggi}.csv"
        
        # Facciamo il backup solo se non esiste già per oggi
        if not os.path.exists(nome_backup):
            try:
                df_backup = pd.read_csv(FILE_DB_PRONOSTICI)
                df_backup.to_csv(nome_backup, index=False)
                
                # Pulizia: tieni solo gli ultimi 10 backup
                files = [os.path.join("backups", f) for f in os.listdir("backups") if f.endswith(".csv")]
                files.sort(key=os.path.getmtime) # Ordina dal più vecchio
                while len(files) > 10:
                    os.remove(files.pop(0))
            except Exception as e:
                print(f"Errore backup: {e}")

def ripristina_ultimo_backup():
    if not os.path.exists("backups"):
        return False, "Cartella backup non trovata."
    
    # Prende i file e li ordina per DATA DI MODIFICA (il più recente per ultimo)
    files = [os.path.join("backups", f) for f in os.listdir("backups") if f.startswith("pronostici_backup")]
    files.sort(key=os.path.getmtime) 
    
    if not files:
        return False, "Nessun file di backup disponibile."
    
    ultimo_file = files[-1] # Il più recente effettivamente scritto su disco
    try:
        df_backup = pd.read_csv(ultimo_file)
        if df_backup.empty:
            return False, "L'ultimo backup trovato è vuoto!"
            
        df_backup.to_csv(FILE_DB_PRONOSTICI, index=False)
        return True, f"Ripristinato backup del: {datetime.fromtimestamp(os.path.getmtime(ultimo_file)).strftime('%d/%m/%Y %H:%M')}"
    except Exception as e:
        return False, f"Errore durante il ripristino: {e}"

def salva_completo_in_locale(d_dict):
    try:
        columns = get_db_columns()
        df_old = pd.read_csv(FILE_DB_PRONOSTICI) if os.path.exists(FILE_DB_PRONOSTICI) else pd.DataFrame(columns=columns)
        
        dati_puliti = d_dict.copy()
        # Aggiungi 'Top 3 HT/FT' alla lista dei campi da pulire dalle quote
        campi_da_pulire = ["SGF", "SGC", "SGO", "Top 6 RE Finali", "Top 3 RE 1°T", "Top 3 HT/FT"]
        for campo in campi_da_pulire:
            if campo in dati_puliti:
                # Questa regex rimuove tutto ciò che somiglia a (Q: 1.23)
                dati_puliti[campo] = re.sub(r'\s\(Q:\s\d+\.\d+\)', '', str(dati_puliti[campo]))

        nuova_riga = {col: dati_puliti.get(col, "N/D") for col in columns}
        df_updated = pd.concat([df_old, pd.DataFrame([nuova_riga])], ignore_index=True)
        df_updated.to_csv(FILE_DB_PRONOSTICI, index=False)
        return True
    except Exception as e:
        st.error(f"❌ Errore salvataggio: {e}")
        return False

def calcola_trend_forma(df_giocate, squadra):
    ultime = df_giocate[(df_giocate['HomeTeam'] == squadra) | (df_giocate['AwayTeam'] == squadra)].tail(4)
    if ultime.empty:
        return "N.D.", 1.0
    
    punti = 0
    stringa_trend = []
    for _, r in ultime.iterrows():
        is_home = r['HomeTeam'] == squadra
        goal_fatti = r['FTHG'] if is_home else r['FTAG']
        goal_subiti = r['FTAG'] if is_home else r['FTHG']
        
        if goal_fatti > goal_subiti:
            punti += 3
            stringa_trend.append("🟢")
        elif goal_fatti == goal_subiti:
            punti += 1
            stringa_trend.append("🟡")
        else:
            stringa_trend.append("🔴")
    
    moltiplicatore = round(0.8 + (punti / 12) * 0.4, 2)
    return "".join(stringa_trend), moltiplicatore

# --- 4. FUNZIONI AGGIORNAMENTO API ---
# --- SOSTITUISCI INTERA FUNZIONE aggiorna_database_calcio ---
def aggiorna_database_calcio():
    headers = {'X-Auth-Token': API_TOKEN}
    competitions = ['SA', 'PL', 'ELC', 'PD', 'BL1', 'FL1', 'CL', 'PPL', 'DED', 'BSA', 'EC', 'WC'] 
    
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
                    # --- MODIFICA: RECUPERO CREST (LOGHI) ---
                    home_crest = m['homeTeam'].get('crest', '')
                    away_crest = m['awayTeam'].get('crest', '')
                    
                    ref = m['referees'][0]['name'] if m.get('referees') else 'N.D.'
                    rows.append([
                        comp, m['utcDate'], home, away, m['status'], 
                        m['score']['fullTime']['home'], m['score']['fullTime']['away'], 
                        m['score']['halfTime']['home'], m['score']['halfTime']['away'], 
                        ref, m['id'], home_crest, away_crest # Aggiunti qui
                    ])
            time.sleep(1) 
            progress_bar.progress((i + 1) / len(competitions))

        # --- MODIFICA: AGGIUNTE COLONNE 'HomeCrest' E 'AwayCrest' ---
        df_new = pd.DataFrame(rows, columns=[
            'League', 'Date', 'HomeTeam', 'AwayTeam', 'Status', 
            'FTHG', 'FTAG', 'HTHG', 'HTAG', 'Referee', 'ID', 'HomeCrest', 'AwayCrest'
        ])
        df_new.to_csv(FILE_DB_CALCIO, index=False)
        status_text.empty()
        st.success("✅ Database Calcio aggiornato con successo! Loghi acquisiti.")
    except Exception as e:
        st.error(f"Errore aggiornamento dati: {e}")

def aggiorna_risultati_pronostici():
    if not os.path.exists(FILE_DB_PRONOSTICI): return
    df = pd.read_csv(FILE_DB_PRONOSTICI)
    headers = {'X-Auth-Token': API_TOKEN}
    
    changes = 0
    progress_bar = st.progress(0)
    
    for i, row in df.iterrows():
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

def controlla_fatica(df, squadra, data_match_str):
    try:
        data_m = pd.to_datetime(data_match_str, dayfirst=True).normalize()
        storico = df[(df['Status'] == 'FINISHED') & 
                    ((df['HomeTeam'] == squadra) | (df['AwayTeam'] == squadra))].copy()
        
        if storico.empty: return False
        storico['Date_dt'] = pd.to_datetime(storico['Date'], utc=True).dt.tz_localize(None).dt.normalize()
        ultima_partita = storico[storico['Date_dt'] < data_m]['Date_dt'].max()
        
        if pd.notnull(ultima_partita):
            giorni_riposo = (data_m - ultima_partita).days
            return giorni_riposo <= 3
    except Exception as e:
        print(f"Errore controllo fatica: {e}")
    return False

def calcola_late_goal_index(casa, fuori):
    val = (len(str(casa)) + len(str(fuori))) % 10
    return round(val * 0.10 + 0.5, 2)

def analizza_distribuzione_tempi(df_giocate, squadra):
    p1, p2 = analizza_pericolosita_tempi(df_giocate, squadra)
    return p1, p2

def analizza_h2h(df_giocate, casa, fuori):
    storico = df_giocate[
        ((df_giocate['HomeTeam'] == casa) & (df_giocate['AwayTeam'] == fuori)) |
        ((df_giocate['HomeTeam'] == fuori) & (df_giocate['AwayTeam'] == casa))
    ].tail(5)
    
    if storico.empty: return 1.0, 1.0, "Nessun precedente recente"
    
    punti_casa = 0
    gol_casa, gol_fuori = 0, 0
    
    for _, r in storico.iterrows():
        if r['HomeTeam'] == casa:
            gol_casa += r['FTHG']
            gol_fuori += r['FTAG']
            if r['FTHG'] > r['FTAG']: punti_casa += 3
            elif r['FTHG'] == r['FTAG']: punti_casa += 1
        else:
            gol_casa += r['FTAG']
            gol_fuori += r['FTHG']
            if r['FTAG'] > r['FTHG']: punti_casa += 3
            elif r['FTAG'] == r['FTHG']: punti_casa += 1
            
    win_rate = punti_casa / (len(storico) * 3)
    bonus_h2h_casa = round(0.9 + (win_rate * 0.2), 2)
    bonus_h2h_fuori = round(2.0 - bonus_h2h_casa, 2)
    
    testo_h2h = f"Ultimi {len(storico)} match: {punti_casa} pt fatti dal team casa"
    return bonus_h2h_casa, bonus_h2h_fuori, testo_h2h

def get_stats(team, is_home_side, df_giocate):
    t = df_giocate[(df_giocate['HomeTeam'] == team) | (df_giocate['AwayTeam'] == team)].tail(15)
    if t.empty: return 1.2, 1.2
    stats_condizione = t[t['HomeTeam'] == team] if is_home_side else t[t['AwayTeam'] == team]
            
    if not stats_condizione.empty:
        if is_home_side:
            gf = stats_condizione['FTHG'].mean()
            gs = stats_condizione['FTAG'].mean()
        else:
            gf = stats_condizione['FTAG'].mean()
            gs = stats_condizione['FTHG'].mean()
    else:
        gf = t.apply(lambda r: r['FTHG'] if r['HomeTeam']==team else r['FTAG'], axis=1).mean()
        gs = t.apply(lambda r: r['FTAG'] if r['HomeTeam']==team else r['FTHG'], axis=1).mean()
    return max(0.5, gf), max(0.5, gs)

def analizza_pericolosita_tempi(df_giocate, squadra):
    ultime = df_giocate[(df_giocate['HomeTeam'] == squadra) | (df_giocate['AwayTeam'] == squadra)].tail(15)
    gol_fatti_1t, gol_fatti_2t, match_validi = 0, 0, 0
    
    for _, r in ultime.iterrows():
        is_home = r['HomeTeam'] == squadra
        f_tot = r['FTHG'] if is_home else r['FTAG']
        h_1t = r.get('HTHG') if is_home else r.get('HTAG')
        
        if pd.notnull(h_1t):
            gol_fatti_1t += h_1t
            gol_fatti_2t += (f_tot - h_1t)
            match_validi += 1
            
    if match_validi == 0: return 50.0, 50.0
    tot = gol_fatti_1t + gol_fatti_2t
    if tot == 0: return 50.0, 50.0
    perc_1t = round((gol_fatti_1t / tot * 100), 1)
    perc_2t = round((gol_fatti_2t / tot * 100), 1)
    return perc_1t, perc_2t

def analizza_performance_campionato(camp_filtro):
    if not os.path.exists(FILE_DB_PRONOSTICI):
        st.warning("Cronologia pronostici non trovata.")
        return

    try:
        df_cron = pd.read_csv(FILE_DB_PRONOSTICI)
        # Filtriamo solo i match con risultati reali completi
        df_v = df_cron[(df_cron['Risultato_Reale'] != "N/D") & (df_cron['PT_Reale'] != "N/D")].copy()
        
        if camp_filtro != 'TUTTI':
            df_v = df_v[df_v['League'] == camp_filtro]

        if df_v.empty:
            st.info(f"Nessun match con dati completi trovato per {camp_filtro}.")
            return

        if 'League' not in df_cron.columns:
            st.error("Il database non contiene la colonna 'League'. Prova a fare una nuova analisi per rigenerare il file correttamente.")
            return

        # Assicuriamoci che esistano tutte le colonne necessarie
        colonne_necessarie = ['Risultato_Reale', 'PT_Reale', '1X2', 'U/O 2.5', 'G/NG', 'SGF', 'SGC', 'SGO']
        for col in colonne_necessarie:
            if col not in df_cron.columns:
                df_cron[col] = "N/D" # Crea colonna vuota se manca

        # Filtro match completati
        df_v = df_cron[(df_cron['Risultato_Reale'] != "N/D") & (df_cron['PT_Reale'] != "N/D")].copy()
        
        if camp_filtro != 'TUTTI':
            df_v = df_v[df_v['League'] == camp_filtro]

        if df_v.empty:
            st.info(f"Nessun match con dati reali trovato per {camp_filtro}.")
            return
        
        match_contati = len(df_v)

        st.success(f"Analisi completata su {match_contati} match per {camp_filtro}")
        
        # Dizionario per accumulare i successi [Vinti, Totali]
        stats = {k: [0, 0] for k in ['1X2', 'U/O 2.5', 'G/NG', 'SGF', 'SGC (Casa)', 'SGO (Ospite)', 'RE Finali', 'RE 1°T', 'HT/FT']}

        for _, row in df_v.iterrows():
            try:
                h, a = map(int, str(row['Risultato_Reale']).split('-'))

                ph, pa = map(int, str(row['PT_Reale']).split('-'))

                # Calcolo segni reali per verifica
                real_1t = "1" if ph > pa else ("2" if pa > ph else "X")
                real_ft = "1" if h > a else ("2" if a > h else "X")
                real_htft = f"{real_1t}-{real_ft}"

                # 1. Mercati Standard
                stats['1X2'][1] += 1
                if check_1x2(row['1X2'], h, a): stats['1X2'][0] += 1
                
                stats['U/O 2.5'][1] += 1
                if check_uo(row['U/O 2.5'], h, a): stats['U/O 2.5'][0] += 1
                
                stats['G/NG'][1] += 1
                if check_gng(row['G/NG'], h, a): stats['G/NG'][0] += 1

                # 2. Somma Gol (SGF, SGC, SGO)
                stats['SGF'][1] += 1
                if check_in_list(row['SGF'], h+a): stats['SGF'][0] += 1

                stats['SGC (Casa)'][1] += 1
                if check_in_list(row['SGC'], h): stats['SGC (Casa)'][0] += 1

                stats['SGO (Ospite)'][1] += 1
                if check_in_list(row['SGO'], a): stats['SGO (Ospite)'][0] += 1

                # 3. Verifica RE Finali
                stats['RE Finali'][1] += 1
                if check_in_list(row['Top 6 RE Finali'], row['Risultato_Reale']): stats['RE Finali'][0] += 1

                # 4. Mercati Avanzati (RE 1°T e HT/FT)
                stats['RE 1°T'][1] += 1
                if check_in_list(row['Top 3 RE 1°T'], f"{ph}-{pa}"): stats['RE 1°T'][0] += 1

                stats['HT/FT'][1] += 1
                if check_in_list(row['Top 3 HT/FT'], real_htft): stats['HT/FT'][0] += 1
                
            except Exception as e:
                continue
        
        # --- INTERFACCIA GRAFICA ---
        st.subheader(f"📊 Precisione modello: {camp_filtro}")
        
        # Visualizzazione a griglia (2 righe da 4 colonne)
        keys = list(stats.keys())
        for i in range(0, len(keys), 4):
            cols = st.columns(4)
            for j in range(4):
                if i + j < len(keys):
                    market = keys[i+j]
                    v = stats[market]
                    if v[1] > 0:
                        wr = v[0] / v[1]
                        is_gold = wr >= 0.75
                        with cols[j]:
                            st.metric(market, f"{wr:.1%}", f"{v[0]}/{v[1]}", delta_color="normal" if not is_gold else "inverse")
                            if is_gold: st.markdown("🏆 **SOGLIA GOLD**")

        # Grafico comparativo
        st.divider()
        st.write("### 📈 Precisione per tipo di Pronostico")
        chart_data = pd.DataFrame({
            'Mercato': stats.keys(),
            'Win Rate': [v[0]/v[1] if v[1]>0 else 0 for v in stats.values()]
        })
        st.bar_chart(chart_data.set_index('Mercato'))

    except Exception as e:
        st.error(f"Errore analisi: {e}")

def analizza_performance_squadra_gold(squadra_target):
    if not os.path.exists(FILE_DB_PRONOSTICI):
        st.warning("Cronologia pronostici non trovata.")
        return

    try:
        df_cron = pd.read_csv(FILE_DB_PRONOSTICI)
        
        # Filtro: Cerchiamo la squadra sia come Casa che come Ospite nella colonna 'Partita'
        # Assumiamo che la colonna Partita sia "SquadraA vs SquadraB"
        df_v = df_cron[
            (df_cron['Risultato_Reale'] != "N/D") & 
            (df_cron['PT_Reale'] != "N/D") & 
            (df_cron['Partita'].str.contains(squadra_target, case=False, na=False))
        ].copy()

        if df_v.empty:
            st.info(f"Nessun match terminato trovato per **{squadra_target}**.")
            return

        match_contati = len(df_v)
        st.markdown(f"### 📊 Report: **{squadra_target}** ({match_contati} match)")
        
        # Dizionario statistiche (Identico a quello delle Leghe)
        stats = {k: [0, 0] for k in ['1X2', 'U/O 2.5', 'G/NG', 'SGF', 'SGC (Casa)', 'SGO (Ospite)', 'RE Finali', 'RE 1°T', 'HT/FT']}

        for _, row in df_v.iterrows():
            try:
                # Parsing risultati
                h, a = map(int, str(row['Risultato_Reale']).split('-'))
                ph, pa = map(int, str(row['PT_Reale']).split('-'))
                
                real_1t = "1" if ph > pa else ("2" if pa > ph else "X")
                real_ft = "1" if h > a else ("2" if a > h else "X")
                real_htft = f"{real_1t}-{real_ft}"

                # --- CALCOLO WIN RATE (STESSA LOGICA LEGHE) ---
                stats['1X2'][1] += 1
                if check_1x2(row['1X2'], h, a): stats['1X2'][0] += 1
                
                stats['U/O 2.5'][1] += 1
                if check_uo(row['U/O 2.5'], h, a): stats['U/O 2.5'][0] += 1
                
                stats['G/NG'][1] += 1
                if check_gng(row['G/NG'], h, a): stats['G/NG'][0] += 1

                stats['SGF'][1] += 1
                if check_in_list(row['SGF'], h+a): stats['SGF'][0] += 1

                stats['SGC (Casa)'][1] += 1
                if check_in_list(row['SGC'], h): stats['SGC (Casa)'][0] += 1

                stats['SGO (Ospite)'][1] += 1
                if check_in_list(row['SGO'], a): stats['SGO (Ospite)'][0] += 1

                stats['RE Finali'][1] += 1
                if check_in_list(row['Top 6 RE Finali'], row['Risultato_Reale']): stats['RE Finali'][0] += 1

                stats['RE 1°T'][1] += 1
                if check_in_list(row['Top 3 RE 1°T'], f"{ph}-{pa}"): stats['RE 1°T'][0] += 1

                stats['HT/FT'][1] += 1
                if check_in_list(row['Top 3 HT/FT'], real_htft): stats['HT/FT'][0] += 1
                
            except Exception as e:
                continue
        
        # --- VISUALIZZAZIONE GRIGLIA ---
        keys = list(stats.keys())
        for i in range(0, len(keys), 3): # 3 colonne per riga per le squadre
            cols = st.columns(3)
            for j in range(3):
                if i + j < len(keys):
                    market = keys[i+j]
                    v = stats[market]
                    if v[1] > 0:
                        wr = v[0] / v[1]
                        # Soglia Gold: 75% o più
                        is_gold = wr >= 0.75
                        with cols[j]:
                            st.metric(
                                label=market, 
                                value=f"{wr:.1%}", 
                                delta=f"{v[0]}/{v[1]} presi",
                                delta_color="normal" if not is_gold else "off" # Trucco per evidenziare
                            )
                            if is_gold: 
                                st.markdown("🏆 **GOLD**")
                            else:
                                st.markdown("➖") # Spaziatura
        
        # Grafico
        st.write("#### 📈 Precisione per Lega")
        chart_data = pd.DataFrame({
            'Mercato': stats.keys(),
            'Win Rate': [v[0]/v[1] if v[1]>0 else 0 for v in stats.values()]
        })
        st.bar_chart(chart_data.set_index('Mercato'), color="#FFD700") # Colore Oro

    except Exception as e:
        st.error(f"Errore analisi squadra: {e}")

def esegui_analisi(nome_input, pen_h=1.0, pen_a=1.0, is_big_match=False):
    if not os.path.exists(FILE_DB_CALCIO):
        st.error("Database Calcio mancante. Aggiorna il DB"); return None

    df = pd.read_csv(FILE_DB_CALCIO)
    df['Date'] = pd.to_datetime(df['Date'], utc=True) 
    today = pd.Timestamp.now(tz='UTC').normalize()

    future_matches = df[
        (df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED'])) & 
        (df['HomeTeam'].str.contains(nome_input, case=False, na=False) | 
         df['AwayTeam'].str.contains(nome_input, case=False, na=False)) &
        (df['Date'] >= today)
    ].sort_values(by='Date')
    
    if future_matches.empty:
        st.warning(f"Nessun prossimo match trovato per '{nome_input}'."); return None

    m = future_matches.iloc[0]

    # Convertiamo la data da UTC a Fuso Orario Roma
    dt_utc = m['Date']
    dt_event_ita = dt_utc.tz_convert('Europe/Rome')
    
    casa, fuori = m['HomeTeam'], m['AwayTeam']
    match_id = m.get('ID', 'N/A')
    codice_lega = m['League']
    nome_lega = LEAGUE_MAP.get(codice_lega, codice_lega)

    giocate = df[df['Status'] == 'FINISHED'].copy()
    arbitro = str(m.get('Referee', 'N.D.'))
    molt_arbitro = analizza_severita_arbitro(giocate, arbitro)
    avg_g = max(1.1, pd.to_numeric(giocate['FTHG'], errors='coerce').mean())
    
    att_h, dif_h = get_stats(casa, True, giocate)
    att_a, dif_a = get_stats(fuori, False, giocate)
    trend_h, molt_forma_h = calcola_trend_forma(giocate, casa)
    trend_a, molt_forma_a = calcola_trend_forma(giocate, fuori)

    m_h2h_h, m_h2h_a, testo_h2h = analizza_h2h(giocate, casa, fuori)
    
    exp_h = (att_h * dif_a / avg_g) * molt_forma_h * (2 - molt_arbitro) * pen_h * m_h2h_h
    exp_a = (att_a * dif_h / avg_g) * molt_forma_a * (2 - molt_arbitro) * pen_a * m_h2h_a

    if is_big_match:
        exp_h *= 0.88
        exp_a *= 0.88

    p1, px, p2, pu, pg, tot = 0,0,0,0,0,0
    sgf, sgc, sgo = {i:0 for i in range(12)}, {i:0 for i in range(6)}, {i:0 for i in range(6)}
    re_fin = []
    
    for i in range(6):
        for j in range(6):
            prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
            tot += prob
            if i>j: p1+=prob
            elif i==j: px+=prob
            else: p2+=prob
            if i+j < 2.5: pu+=prob
            if i>0 and j>0: pg+=prob
            sgf[i+j] += prob
            sgc[i] += prob
            sgo[j] += prob
            re_fin.append({'s': f"{i}-{j}", 'p': prob})
            
    # --- CALCOLO HT/FT (LOGICA CORRETTA) ---
    eh1, ea1 = exp_h * 0.42, exp_a * 0.42
    prob_1t = {'1': 0, 'X': 0, '2': 0}
    re_1t = []
    
    # Calcolo probabilità primo tempo
    for i in range(4):
        for j in range(4):
            pb = poisson_probability(i, eh1) * poisson_probability(j, ea1)
            re_1t.append({'s': f"{i}-{j}", 'p': pb})
            sign = "1" if i > j else ("2" if j > i else "X")
            prob_1t[sign] += pb

    # Probabilità Finale (già calcolate prima nel tuo codice)
    prob_ft = {'1': p1, 'X': px, '2': p2}
    
    # Inizializziamo pf_final_dict (FONDAMENTALE PER EVITARE L'ERRORE UnboundLocalError)
    pf_final_dict = {}
    for s1 in ['1', 'X', '2']:
        for s2 in ['1', 'X', '2']:
            comb = f"{s1}-{s2}"
            # Peso statistico per rendere il calcolo realistico
            weight = 0.6 if s1 == s2 else (0.3 if s1 == 'X' else 0.1)
            pf_final_dict[comb] = (prob_1t[s1] * prob_ft[s2]) * weight

    # Normalizzazione
    total_pf = sum(pf_final_dict.values())
    if total_pf > 0:
        for k in pf_final_dict: pf_final_dict[k] /= total_pf

    # Generazione stringa TOP 3 HT/FT
    # Ordiniamo e prendiamo i primi 3. Gestiamo il caso in cui il dizionario sia vuoto.
    items_htft = sorted(pf_final_dict.items(), key=lambda x: x[1], reverse=True)[:3]
    top_pf_string = ", ".join([f"{k} (Q: {stima_quota(v):.2f})" for k, v in items_htft])
    
    # 1. Calcolo stringhe pronostici 1X2, U/O, G/NG
    if p1 >= px and p1 >= p2: d_1x2 = "1"
    elif p2 >= p1 and p2 >= px: d_1x2 = "2"
    else: d_1x2 = "X"
    
    d_uo = "UNDER 2.5" if pu >= 0.5 else "OVER 2.5"
    d_gng = "GOL" if pg >= 0.5 else "NOGOL"

    # 2. Calcolo statistiche tempi (dist_1t_h, ecc.)
    dist_1t_h, dist_2t_h = analizza_pericolosita_tempi(giocate, casa)
    dist_1t_a, dist_2t_a = analizza_pericolosita_tempi(giocate, fuori)
    
    avg_1t = (dist_1t_h + dist_1t_a) / 2
    avg_2t = (dist_2t_h + dist_2t_a) / 2
    tempo_top = "1° Tempo" if avg_1t > avg_2t else "2° Tempo"

    # 3. Controllo sicurezza data
    if 'dt_event_ita' not in locals():
        # Se per qualche motivo dt_event_ita non è definita sopra, la ricalcoliamo
        dt_event_ita = m['Date'].tz_convert('Europe/Rome')

    # Funzioni di formattazione interne
    def formatta_somma_con_quote(diz, limite, top_n):
        items = sorted(diz.items(), key=lambda x: x[1], reverse=True)[:top_n]
        return ", ".join([f"{str(k) if k < limite else '>'+str(limite-1)} (Q: {stima_quota(v):.2f})" for k, v in items])

    def formatta_re_con_quote(lista, top_n):
        items = sorted(lista, key=lambda x: x['p'], reverse=True)[:top_n]
        return ", ".join([f"{v['s']} (Q: {stima_quota(v['p']):.2f})" for v in items])

    # --- RECUPERO LOGHI DAL DATAFRAME ---
    # m è la riga del match trovata nel database
    logo_casa = m.get('HomeCrest') if 'HomeCrest' in m else None
    logo_fuori = m.get('AwayCrest') if 'AwayCrest' in m else None
    
    # --- RETURN FINALE COMPLETO ---
    return {
        "Data": dt_event_ita.strftime("%d/%m/%Y"), 
        "Ora": dt_event_ita.strftime("%H:%M"),
        "League": nome_lega,
        "Partita": f"{casa} vs {fuori}",
        "Fiducia": f"{int(max(p1,px,p2)*100)}%", 
        "Affidabilità": f"{85 + int(molt_arbitro*2)}%",
        "1X2": d_1x2, "U/O 2.5": d_uo, "G/NG": d_gng,
        "SGF": formatta_somma_con_quote(sgf, 5, 3), 
        "SGC": formatta_somma_con_quote(sgc, 3, 2), 
        "SGO": formatta_somma_con_quote(sgo, 3, 2),
        "Top 6 RE Finali": formatta_re_con_quote(re_fin, 6), 
        "Top 3 RE 1°T": formatta_re_con_quote(re_1t, 3),
        "Top 3 HT/FT": top_pf_string,
        "Match_ID": match_id, "Risultato_Reale": "N/D", "PT_Reale": "N/D",
        "p1": p1, "px": px, "p2": p2, "pu": pu, "pg": pg,
        "dist_1t_h": dist_1t_h, "dist_2t_h": dist_2t_h,
        "dist_1t_a": dist_1t_a, "dist_2t_a": dist_2t_a, "tempo_top": tempo_top,
        "casa_nome": casa, "fuori_nome": fuori, "lg": calcola_late_goal_index(casa, fuori),
        "arbitro": arbitro, "molt_arbitro": molt_arbitro,
        "Trend_Casa": trend_h, "Trend_Fuori": trend_a,
        "Forma_H": molt_forma_h, "Forma_A": molt_forma_a,
        "is_big_match": is_big_match, # Aggiunto per evitare errori nel frontend
        "logo_casa": logo_casa,  # <--- NUOVO
        "logo_fuori": logo_fuori # <--- NUOVO
    }
    
def highlight_winners(row):
    # Creiamo una lista di stili vuoti lunga quanto la riga
    colors = [''] * len(row)
    
    # Se non c'è il risultato reale, non coloriamo nulla
    if row.get('Risultato_Reale') == "N/D" or pd.isna(row.get('Risultato_Reale')):
        return colors
    
    try:
        # 1. Recupero dati reali
        h, a = map(int, str(row['Risultato_Reale']).split('-'))
        ph, pa = map(int, str(row['PT_Reale']).split('-'))
        
        real_1t_sign = "1" if ph > pa else ("2" if pa > ph else "X")
        real_ft_sign = "1" if h > a else ("2" if a > h else "X")
        real_htft = f"{real_1t_sign}-{real_ft_sign}"
        
        green = 'background-color: #d4edda; color: #155724; font-weight: bold'

        # 2. Mappatura colonne per nome (evita errori di indice)
        # Cerchiamo la posizione della colonna nella riga corrente
        cols_list = list(row.index)

        checks = [
            ('1X2', lambda: check_1x2(row['1X2'], h, a)),
            ('U/O 2.5', lambda: check_uo(row['U/O 2.5'], h, a)),
            ('G/NG', lambda: check_gng(row['G/NG'], h, a)),
            ('SGF', lambda: check_in_list(row['SGF'], h+a)),
            ('SGC', lambda: check_in_list(row['SGC'], h)),
            ('SGO', lambda: check_in_list(row['SGO'], a)),
            ('Top 6 RE Finali', lambda: check_in_list(row['Top 6 RE Finali'], row['Risultato_Reale'])),
            ('Top 3 RE 1°T', lambda: check_in_list(row['Top 3 RE 1°T'], row['PT_Reale'])),
            ('Top 3 HT/FT', lambda: check_in_list(row['Top 3 HT/FT'], real_htft))
        ]

        for col_name, condition_func in checks:
            if col_name in cols_list and condition_func():
                colors[cols_list.index(col_name)] = green

    except Exception as e:
        pass # In caso di errore nel parsing (es. dati sporchi), non colora
        
    return colors

# --- 7. MAIN ---
tab1, tab2, tab3, tab4 = st.tabs(["🎯 **Analisi**", "⚙️ **Database**", "📜 **Cronologia**", "📊 **Statistiche**"])


with tab1:
    sq = st.text_input("🔍 Inserisci Squadra")

    if 'dati_acquisiti' not in st.session_state: st.session_state['dati_acquisiti'] = False
    if 'squadra_precedente' not in st.session_state: st.session_state['squadra_precedente'] = ""

    if sq != st.session_state['squadra_precedente']:
        st.session_state['dati_acquisiti'] = False
        st.session_state['pronostico_corrente'] = None
        st.session_state['squadra_precedente'] = sq

    if sq and not st.session_state.get('dati_acquisiti', False):
        if st.button("📊 Acquisisci dati della partita", use_container_width=True):
            d_temp = esegui_analisi(sq)
            if d_temp:
                st.session_state['dati_temp'] = d_temp
                st.session_state['dati_acquisiti'] = True
                st.rerun()
            else:
                st.error("Squadra non trovata.")

    # Il controllo 'if' previene il KeyError
    if st.session_state.get('dati_acquisiti'):
        d = st.session_state['dati_temp']
        d_temp = d # Definiamo d_temp per compatibilità con le righe successive
        st.success(f"✅ Dati acquisiti per {d['Partita']}")
        
        search_query = f"**Formazione {sq} nella partita del {d_temp['Data']}**"
        google_news_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}&tbm=nws"
        
        st.markdown(f"👉 [**Controlla Formazione e Assenti per il {d_temp['Data']}**]({google_news_url})")

        st.divider()
        st.info("Regola la potenza offensiva se mancano giocatori chiave")
        
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            pen_h = st.select_slider(f"**Potenza Attacco Casa**", options=[0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0], value=1.0)
        with col_p2:
            pen_a = st.select_slider(f"**Potenza Attacco Fuori**", options=[0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0], value=1.0)        
            
            is_big_match = st.toggle("🔥 Filtro Big Match / Derby")

        if st.button("🎯 Genera Pronostico", type="primary", use_container_width=True):
            risultati = esegui_analisi(sq, pen_h, pen_a, is_big_match)
            st.session_state['pronostico_corrente'] = risultati
            st.rerun()

        if st.session_state.get('pronostico_corrente'):
            d = st.session_state['pronostico_corrente']
            df_calcio = pd.read_csv(FILE_DB_CALCIO)
            casa_nome, fuori_nome = d['casa_nome'], d['fuori_nome']

            # Creazione di 3 colonne con proporzioni diverse per centrare bene il testo
            # [1, 3, 1] significa che la colonna centrale è 3 volte più grande delle laterali
            col1, col2, col3 = st.columns([1, 3, 1])
            
            with col1:
                # Logo Squadra Casa
                if d.get('logo_casa') and str(d['logo_casa']) != 'nan':
                    st.image(d['logo_casa'], width=80)
            
            with col2:
                # Nome Partita centrato
                st.header(f"**{d['Partita']}**")
                
            with col3:
                # Logo Squadra Fuori
                if d.get('logo_fuori') and str(d['logo_fuori']) != 'nan':
                    st.image(d['logo_fuori'], width=60)

            #st.header(f"🏟️ **{d['Partita']}**")
            #st.subheader(f"🏆 Lega: {d.get('League', 'N.D.')}")
            #st.subheader(f"📅 Data: {d['Data']} ore {d['Ora']}")
        
            if d.get('is_big_match'): st.warning("🛡️ **Filtro Big Match Attivo**: probabile partita molto tattica")

            c_trend1, c_trend2 = st.columns(2)
            with c_trend1:
                st.markdown(f"**Forma {casa_nome}:** {d['Trend_Casa']}")
                st.caption(f"Incidenza: {d['Forma_H']}x")
            with c_trend2:
                st.markdown(f"**Forma {fuori_nome}:** {d['Trend_Fuori']}")
                st.caption(f"Incidenza: {d['Forma_A']}x")
            
            fatica_casa = controlla_fatica(df_calcio, casa_nome, d['Data'])
            fatica_fuori = controlla_fatica(df_calcio, fuori_nome, d['Data'])
            
            if fatica_casa or fatica_fuori:
                st.markdown("---")
                st.markdown("🏃‍♂️ **Allerta Stanchezza**")
                c_fat1, c_fat2 = st.columns(2)
                with c_fat1:
                    if fatica_casa: st.error(f"⚠️ **{casa_nome} ha giocato meno di 72h fa!**")
                with c_fat2:
                    if fatica_fuori: st.error(f"⚠️ **{fuori_nome} ha giocato meno di 72h fa!**")

            st.divider()
            c_inf1, c_inf2 = st.columns(2)
            with c_inf1: st.info(f"👮 **Arbitro**: {d.get('arbitro', 'N.D.')}  |  **Impatto**: {d.get('molt_arbitro', 1.0)}x")
            casa_nome = d['Partita'].split(" vs ")[0]
            fuori_nome = d['Partita'].split(" vs ")[1]

            with c_inf2: st.info(f"⏳ **Gol nel finale: {d['lg']:.2f}**")
            if d['lg'] > 1.2: 
                st.error("🔥🔥🔥 **POSSIBILE GOL NEL FINALE (80+ MINUTO)**")
            
            st.divider()
            st.subheader("⏱️ Analisi Tempi (Distribuzione Gol)")
            ct1, ct2 = st.columns(2)
            with ct1:
                st.write(f"**{casa_nome}**")
                st.progress(d['dist_1t_h'] / 100, text=f"1° Tempo: {d['dist_1t_h']}%")
                st.progress(d['dist_2t_h'] / 100, text=f"2° Tempo: {d['dist_2t_h']}%")
            with ct2:
                st.write(f"**{fuori_nome}**")
                st.progress(d['dist_1t_a'] / 100, text=f"1° Tempo: {d['dist_1t_a']}%")
                st.progress(d['dist_2t_a'] / 100, text=f"2° Tempo: {d['dist_2t_a']}%")

            st.info(f"💡 **Tendenza**: Il tempo con più gol è il **{d['tempo_top']}**")

            st.divider()
            st.subheader("🏁 Esito Finale 1X2")
            c1, cx, c2 = st.columns(3)
            with c1: st.success(f"**Esito 1:** \n 📈 Prob: {d['p1']:.1%}\n 💰 Quota: {stima_quota(d['p1'])}")
            with cx: st.success(f"**Esito X:** \n 📈 Prob: {d['px']:.1%}\n 💰 Quota: {stima_quota(d['px'])}")
            with c2: st.success(f"**Esito 2:** \n 📈 Prob: {d['p2']:.1%}\n 💰 Quota: {stima_quota(d['p2'])}")

            st.divider()
            st.subheader("⚔️ Under/Over 2,5 & Gol/NoGol")
            col_uo, col_gng = st.columns(2)
            p_over = 1 - d['pu']
            p_nogol = 1 - d['pg']
            with col_uo: st.warning(f"**UNDER 2.5:** {d['pu']:.1%} (Q:{stima_quota(d['pu'])})\n\n**OVER 2.5:** {p_over:.1%} (Q:{stima_quota(p_over)})")
            with col_gng: st.warning(f"**GOL:** {d['pg']:.1%} (Q:{stima_quota(d['pg'])})\n\n**NOGOL:** {p_nogol:.1%} (Q:{stima_quota(p_nogol)})")

            # --- RISULTATI E SOMME GOL CON QUOTE ---
            st.divider()
            st.subheader("⚽ Analisi Somma Gol")
            cr1, cr2 = st.columns(2)
            with cr1:
                # Mostra i Top 3 esiti del match con le relative quote
                st.error(f"🎯 **Somma Gol Finale (Top 3)**\n\n{d['SGF']}")           
            with cr2:
                # Mostra i Top 2 esiti per squadra con le relative quote
                st.error(f"🏠 **Somma Gol Casa:** {d['SGC']}\n\n🚀 **Somma Gol Ospite:** {d['SGO']}")

            # --- RISULTATI ESATTI ---
            st.divider()
            st.subheader("🎯 Risultati Esatti")
            cfe1, cfe2 = st.columns(2)
            with cfe1:
                st.success(f"🏁 **Top 6 Risultati Esatti Finali**\n\n{d['Top 6 RE Finali']}")
            with cfe2:
                st.info(f"⏱️ **Top 3 Risultati Esatti 1° Tempo**\n\n{d['Top 3 RE 1°T']}")

            # --- LOGICA SALVATAGGIO ROBUSTA ---
            if st.button("💾 Salva in Cronologia", use_container_width=True):
                # Calcola la fatica prima di salvare
                df_c = pd.read_csv(FILE_DB_CALCIO)
                f_h = controlla_fatica(df_c, d['casa_nome'], d['Data'])
                f_a = controlla_fatica(df_c, d['fuori_nome'], d['Data'])
                d['Fatica'] = "SÌ" if (f_h or f_a) else "NO"
                
                if salva_completo_in_locale(d):
                    st.toast("Salvato con successo!", icon="✅")
                    time.sleep(1)
                    st.rerun()

with tab2:
    st.info(f"⏰  Aggiorna Serie A, Premier League, Championship, Liga, Bundesliga, Ligue 1, Primeira Liga, Eredivisie, Brasileirao Betano, UEFA e FIFA")

    if st.button("🌐 Aggiorna tutti i Dati"):
        with st.spinner("Aggiornamento database in corso..."):
            aggiorna_database_calcio()

with tab3:
    st.header("📜 Cronologia")
    
    mostra_tabella = False
    df_cronologia = pd.DataFrame()

    # 1. CARICAMENTO DATI ATTUALI
    if os.path.exists(FILE_DB_PRONOSTICI):
        try:
            df_cronologia = pd.read_csv(FILE_DB_PRONOSTICI)
            if not df_cronologia.empty:
                mostra_tabella = True
                df_cronologia = df_cronologia.drop_duplicates(subset=['Data', 'Partita'], keep='last')
        except:
            st.error("Il file della cronologia sembra corrotto.")

    # 2. BOTTONE SCARICA (SALVA SU ICLOUD/TELEFONO)
    if mostra_tabella:
        # Generiamo il CSV
        csv_data = df_cronologia.to_csv(index=False).encode('utf-8')
        
        col_down, col_msg = st.columns([1, 2])
        with col_down:
            st.download_button(
                label="📥 Salva Pronostici",
                data=csv_data,
                file_name=f"pronostici_backup_{date.today()}.csv",
                mime='text/csv',
                use_container_width=True,
                help="Salva questo file su 'File' o iCloud Drive per non perderlo"
            )
        with col_msg:
            st.caption("💡 Su iPhone/iPad: dopo il download scegli **'Salva su File'** per metterlo su iCloud.")

        # Filtri e Tabella
        st.divider()
        date_disponibili = sorted(df_cronologia['Data'].unique(), reverse=True)
        date_disponibili.insert(0, "Tutte")
        
        col_filt, col_agg = st.columns([3, 1])
        with col_filt:
            data_scelta = st.selectbox("📅 Filtra per data:", date_disponibili)
        with col_agg:
            st.write("")
            st.write("")
            if st.button("🔄 Verifica i pronostici", use_container_width=True):
                with st.spinner("Aggiornamento..."):
                    aggiorna_risultati_pronostici()
                    st.rerun()

        df_da_mostrare = df_cronologia if data_scelta == "Tutte" else df_cronologia[df_cronologia['Data'] == data_scelta]
        st.dataframe(df_da_mostrare.style.apply(highlight_winners, axis=1), use_container_width=True, hide_index=True)
    
    else:
        st.info("📭 Nessun dato in cronologia.")

    # 3. AREA DI RIPRISTINO (FUNZIONA CON ICLOUD)
    st.divider()
    st.subheader("☁️ Ripristina Backup")
    
    with st.expander("Carica un file CSV precedente (da iCloud o Locale)"):
        uploaded_file = st.file_uploader("Trascina qui il file o clicca per cercare", type=["csv"])
        
        if uploaded_file is not None:
            try:
                # Legge il file caricato
                df_uploaded = pd.read_csv(uploaded_file)
                
                # Controllo base validità
                if 'Partita' in df_uploaded.columns and '1X2' in df_uploaded.columns:
                    # Pulsante conferma
                    if st.button("🔥 Conferma e Sovrascrivi Cronologia attuale"):
                        df_uploaded.to_csv(FILE_DB_PRONOSTICI, index=False)
                        st.success("✅ Database ripristinato con successo!")
                        time.sleep(1.5)
                        st.rerun()
                else:
                    st.error("Il file caricato non sembra un backup valido di Delphi.")
            except Exception as e:
                st.error(f"Errore nel caricamento: {e}")

    # Tasto Cancellazione (sempre utile averlo nascosto)
    with st.expander("🗑️ Zona Pericolo: Cancella tutto"):
        st.warning("Vuoi cancellare tutta la cronologia attuale?")
        if st.button("🔥 Cancella definitivamente"):
            if os.path.exists(FILE_DB_PRONOSTICI):
                os.remove(FILE_DB_PRONOSTICI)
                st.rerun()

with tab4:
    st.header("📊 Performance Delphi")
    
    # --- SEZIONE 1: ANALISI CAMPIONATO ---
    st.subheader("🌍 Analisi per Campionato")
    opzioni_camp = ['TUTTI', 'Serie A', 'Premier League', 'Championship', 'La Liga', 'Bundesliga', 'Ligue 1', 'Primeira Liga', 'Eredivisie', 'Champions League', 'Nations League', 'Brasileirao Betano']
    scelta_camp = st.selectbox("Seleziona Campionato:", opzioni_camp, index=0)
    
    if st.button("Analizza Campionato", type="primary"):
        analizza_performance_campionato(scelta_camp)
    
    st.markdown("---")
    
    # --- SEZIONE 2: ANALISI SQUADRA (GOLD STYLE) ---
    st.subheader("🛡️ Analisi per Squadra")
    
    if os.path.exists(FILE_DB_PRONOSTICI):
        try:
            df_cron = pd.read_csv(FILE_DB_PRONOSTICI)
            
            # Estraiamo la lista pulita di tutte le squadre presenti nel DB
            tutte_squadre = set()
            for partita in df_cron['Partita'].dropna():
                if ' vs ' in str(partita):
                    teams = str(partita).split(' vs ')
                    tutte_squadre.update([t.strip() for t in teams])
            
            lista_squadre = sorted(list(tutte_squadre))
            
            if lista_squadre:
                scelta_sq = st.selectbox("Seleziona la Squadra:", lista_squadre)
                
                if st.button(f"Analizza precisione {scelta_sq}"):
                    analizza_performance_squadra_gold(scelta_sq)
            else:
                st.info("Nessuna squadra trovata nel database.")
                
        except Exception as e:
            st.error("Errore lettura database per elenco squadre.")
    else:
        st.warning("Database non ancora creato.")
