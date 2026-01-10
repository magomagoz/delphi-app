import streamlit as st
import pandas as pd
import math
import requests
import os
import time
import re
from datetime import datetime, date
import pytz

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Delphi Predictor Pro", layout="wide") 

LEAGUE_MAP = {
    'SA': 'Serie A', 'PL': 'Premier League', 'ELC': 'Championship',
    'PD': 'La Liga', 'BL1': 'Bundesliga', 'FL1': 'Ligue 1',
    'CL': 'UEFA Champions League', 'PPL': 'Primeira Liga', 'DED': 'Eredivisie',
    'BSA': 'Serie A Brasile', 'EC': 'UEFA Europa League', 'WC': 'FIFA World Cup'
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
def check_1x2(pred, home, away):
    if home > away: res = "1"
    elif away > home: res = "2"
    else: d = "X"
    return str(pred).strip() == res

def check_uo(pred, home, away):
    total = home + away
    valore_reale = "OVER 2.5" if total > 2.5 else "UNDER 2.5"
    return str(pred).strip().upper() == valore_reale

def check_gng(pred, home, away):
    valore_reale = "GOL" if home > 0 and away > 0 else "NOGOL"
    return str(pred).strip().upper() == valore_reale

def check_in_list(pred_string, value_to_find):
    preds = [p.strip() for p in str(pred_string).split(",")]
    return str(value_to_find).strip() in [p.strip() for p in preds]

# --- 3. FUNZIONI DATABASE (CORRETTE) ---
def get_db_columns():
    return [
        "Data", "Ora", "Partita", "Fiducia", "Affidabilità", 
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
    # Crea la cartella backup se non esiste
    if not os.path.exists("backups"):
        os.makedirs("backups")
    
    # Se il file pronostici esiste, fanne una copia
    if os.path.exists(FILE_DB_PRONOSTICI):
        data_oggi = datetime.now().strftime("%Y-%m-%d")
        nome_backup = f"backups/pronostici_backup_{data_oggi}.csv"
        
        # Crea il backup solo se non è già stato fatto oggi (per non rallentare l'app)
        if not os.path.exists(nome_backup):
            try:
                df_backup = pd.read_csv(FILE_DB_PRONOSTICI)
                df_backup.to_csv(nome_backup, index=False)
                # Opzionale: tieni solo gli ultimi 7 backup per non occupare troppo spazio
                files_backup = sorted([f for f in os.listdir("backups") if f.startswith("pronostici_backup")])
                if len(files_backup) > 7:
                    os.remove(os.path.join("backups", files_backup[0]))
            except Exception as e:
                print(f"Errore backup: {e}")

# Esegui il backup all'avvio
crea_backup_automatico()

def ripristina_ultimo_backup():
    if not os.path.exists("backups"):
        return False, "Cartella backup non trovata."
    
    # Prende la lista dei backup ordinata per data
    files = sorted([f for f in os.listdir("backups") if f.startswith("pronostici_backup")])
    if not files:
        return False, "Nessun file di backup disponibile."
    
    ultimo_file = os.path.join("backups", files[-1])
    try:
        df_backup = pd.read_csv(ultimo_file)
        df_backup.to_csv(FILE_DB_PRONOSTICI, index=False)
        return True, f"Ripristinato backup del: {files[-1].replace('pronostici_backup_', '').replace('.csv', '')}"
    except Exception as e:
        return False, f"Errore durante il ripristino: {e}"

def salva_completo_in_locale(d_dict):
    try:
        columns = get_db_columns()
        df_old = pd.read_csv(FILE_DB_PRONOSTICI) if os.path.exists(FILE_DB_PRONOSTICI) else pd.DataFrame(columns=columns)
        
        # Pulizia: rimuove "(Q: 1.50)" per non rompere i confronti futuri
        dati_puliti = d_dict.copy()
        for campo in ["SGF", "SGC", "SGO", "Top 6 RE Finali", "Top 3 RE 1°T", "Top 3 HT/FT"]:
            if campo in dati_puliti:
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
def aggiorna_database_calcio():
    headers = {'X-Auth-Token': API_TOKEN}
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
                    rows.append([
                        comp, m['utcDate'], home, away, m['status'], 
                        m['score']['fullTime']['home'], m['score']['fullTime']['away'], 
                        m['score']['halfTime']['home'], m['score']['halfTime']['away'], 
                        ref, m['id']
                    ])
            time.sleep(1) 
            progress_bar.progress((i + 1) / len(competitions))

        df_new = pd.DataFrame(rows, columns=[
            'League', 'Date', 'HomeTeam', 'AwayTeam', 'Status', 
            'FTHG', 'FTAG', 'HTHG', 'HTAG', 'Referee', 'ID'
        ])
        df_new.to_csv(FILE_DB_CALCIO, index=False)
        status_text.empty()
        st.success("✅ Database Calcio aggiornato con successo!")
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
            
    eh1, ea1 = exp_h*0.42, exp_a*0.42
    re_1t,total_p_1t = [], 0
    for i in range(4):
        for j in range(4):
            pb = poisson_probability(i, eh1) * poisson_probability(j, ea1)
            total_p_1t += pb
            re_1t.append({'s': f"{i}-{j}", 'p': pb})
   
    p1, px, p2 = p1/tot, px/tot, p2/tot
    pu, pg = pu/tot, pg/tot
    d_1x2 = "1" if p1 > px and p1 > p2 else ("X" if px > p1 and px > p2 else "2")
    d_uo = "OVER 2.5" if (1-pu) > 0.5 else "UNDER 2.5"
    d_gng = "GOL" if pg > 0.5 else "NOGOL"

    # --- Estrazione Top 3 Parziale/Finale per visualizzazione ---
    top_pf_final = ", ".join([
        f"{k} (Q: {stima_quota(v):.2f})" 
        for k, v in sorted(pf_final.items(), key=lambda x: x[1], reverse=True)[:3]
    ])
        
    def formatta_somma_con_quote(diz, limite, top_n):
        items = sorted(diz.items(), key=lambda x: x[1], reverse=True)[:top_n]
        ris = []
        for k, v in items:
            label = f">{limite-1}" if k >= limite else str(k)
            ris.append(f"{label} (Q: {stima_quota(v):.2f})")
        return ", ".join(ris)

    def formatta_re_con_quote(lista, top_n):
        items = sorted(lista, key=lambda x: x['p'], reverse=True)[:top_n]
        return ", ".join([f"{v['s']} (Q: {stima_quota(v['p']):.2f})" for v in items])

    top_sgf_final = formatta_somma_con_quote(sgf, 5, 3)
    top_sgc_final = formatta_somma_con_quote(sgc, 3, 2)
    top_sgo_final = formatta_somma_con_quote(sgo, 3, 2)
    top_re_final = formatta_re_con_quote(re_fin, 6)
    top_re1t_final = formatta_re_con_quote(re_1t, 3)

    dist_1t_h, dist_2t_h = analizza_distribuzione_tempi(giocate, casa)
    dist_1t_a, dist_2t_a = analizza_distribuzione_tempi(giocate, fuori)
    
    prob_1t_piu_gol = (dist_1t_h + dist_1t_a) / 2
    prob_2t_piu_gol = (dist_2t_h + dist_2t_a) / 2
    tempo_top = "2° Tempo" if prob_2t_piu_gol > prob_1t_piu_gol else "1° Tempo"
    
    try:
        dt_event = pd.to_datetime(m['Date'], utc=True)
        fuso_roma = pytz.timezone('Europe/Rome')
        dt_event_ita = dt_event.astimezone(fuso_roma)
    except:
        dt_event_ita = datetime.now(pytz.timezone('Europe/Rome'))    

    # --- CALCOLO 9 ESITI PARZIALE/FINALE ---
    pf_probs = {}
    segni = ['1', 'X', '2']
    p1t_1 = sum(v['p'] for v in re_1t if int(v['s'].split('-')[0]) > int(v['s'].split('-')[1]))
    p1t_x = sum(v['p'] for v in re_1t if int(v['s'].split('-')[0]) == int(v['s'].split('-')[1]))
    p1t_2 = sum(v['p'] for v in re_1t if int(v['s'].split('-')[0]) < int(v['s'].split('-')[1]))

    for s1 in segni:
        for s2 in segni:
            p1t = p1t_1 if s1=='1' else (p1t_x if s1=='X' else p1t_2)
            pfin = p1 if s2=='1' else (px if s2=='X' else p2)
            corr = 1.25 if s1 == s2 else 0.85 # Correzione statistica
            pf_probs[f"{s1}-{s2}"] = (p1t * pfin * corr)

    # Normalizzazione
    total_pf = sum(pf_probs.values())
    pf_final = {k: v/total_pf for k, v in pf_probs.items()}
    
    return {
        "Data": dt_event_ita.strftime("%d/%m/%Y"), 
        "Ora": dt_event_ita.strftime("%H:%M"),
        "League": nome_lega,
        "Partita": f"{casa} vs {fuori}",
        "Fiducia": f"{int(max(p1,px,p2)*100)}%", 
        "Affidabilità": f"{85 + int(molt_arbitro*2)}%",
        "Trend_Casa": trend_h, "Trend_Fuori": trend_a,
        "Forma_H": molt_forma_h, "Forma_A": molt_forma_a,
        "1X2": d_1x2, "U/O 2.5": d_uo, "G/NG": d_gng,
        "SGF": top_sgf_final, "SGC": top_sgc_final, "SGO": top_sgo_final,
        "Top 6 RE Finali": top_re_final, "Top 3 RE 1°T": top_re1t_final,
        "Top 3 RE HT/FT": top_pf_final, # Questa è la chiave che mancava e causava il KeyError
        "pf_grid": pf_final,
        "Fatica": "N/D",
        "Match_ID": match_id, "Risultato_Reale": "N/D", "PT_Reale": "N/D",
        "p1": p1, "px": px, "p2": p2, "pu": pu, "pg": pg,
        "h2h_info": testo_h2h, 
        "m_h2h_h": m_h2h_h, "m_h2h_a": m_h2h_a,
        "dist_1t_h": dist_1t_h, "dist_2t_h": dist_2t_h,
        "dist_1t_a": dist_1t_a, "dist_2t_a": dist_2t_a, "tempo_top": tempo_top,
        "casa_nome": casa, "fuori_nome": fuori, "lg": calcola_late_goal_index(casa, fuori),
        "is_big_match": is_big_match, "arbitro": arbitro, "molt_arbitro": molt_arbitro,
    }

def highlight_winners(row):
    colors = [''] * len(row)
    if row['Risultato_Reale'] == "N/D": return colors
    try:
        h, a = map(int, row['Risultato_Reale'].split('-'))
        ph, pa = map(int, row['PT_Reale'].split('-'))
    except: return colors

    green = 'background-color: #d4edda; color: #155724; font-weight: bold'
    if check_1x2(row['1X2'], h, a): colors[5] = green
    if check_uo(row['U/O 2.5'], h, a): colors[6] = green
    if check_gng(row['G/NG'], h, a): colors[7] = green
    if check_in_list(row['SGF'], h+a): colors[8] = green
    if check_in_list(row['SGC'], h): colors[9] = green
    if check_in_list(row['SGO'], a): colors[10] = green
    if check_in_list(row['Top 6 RE Finali'], row['Risultato_Reale']): colors[11] = green
    if check_in_list(row['Top 3 RE 1°T'], row['PT_Reale']): colors[12] = green
    if check_in_list(row['Top 3 RE HT/FT'], row['HTFT']): colors[13] = green
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
        d_acq = st.session_state['dati_temp']
        #d_temp = d # Definiamo d_temp per compatibilità con le righe successive
        st.success(f"✅ Dati acquisiti per {d_acq['Partita']}")
        
        search_query = f"**Formazione {sq} nella partita del {d_acq['Data']}**"
        google_news_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}&tbm=nws"
        
        st.markdown(f"👉 [**Controlla Formazione e Assenti per il {d_acq['Data']}**]({google_news_url})")

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

            st.header(f"🏟️ **{d['Partita']}**")
            st.subheader(f"🏆 Lega: {d.get('League', 'N.D.')}", "📅 Data: {d['Data']} ore {d['Ora']}")
        
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

            st.divider() 
            st.info(f"🏆 **Top 3 Risultati 1°Tempo/Finale**\n\n{d['Top 3 RE HT/FT']}")

            st.divider()
            st.subheader("⏱️ Griglia Completa Parziale/Finale (9 Esiti)")
            
            grid_data = d.get('pf_grid', {})
            if grid_data:
                pf_list = [{"Combinazione": esito, "Probabilità": f"{prob:.1%}", "Quota": f"{stima_quota(prob):.2f}"} 
                           for esito, prob in grid_data.items()]
                df_pf = pd.DataFrame(pf_list)
                
                c_pf1, c_pf2, c_pf3 = st.columns(3)
                with c_pf1: st.table(df_pf.iloc[0:3])
                with c_pf2: st.table(df_pf.iloc[3:6])
                with c_pf3: st.table(df_pf.iloc[6:9])
            
            st.divider()
            # --- LOGICA SALVATAGGIO ROBUSTA (Sempre dentro l'if del pronostico) ---
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
    st.info("⏰ Aggiorna Serie A, Premier League, Championship, Liga, Bundesliga, Ligue 1, Primeira Liga, Eredivisie, Brasileirao Betano, UEFA e FIFA")

    if st.button("🌐 Aggiorna Database"):
        with st.spinner("Aggiornamento database in corso..."):
            aggiorna_database_calcio()

with tab3:
    st.header("📜 Cronologia")
    
    if os.path.exists(FILE_DB_PRONOSTICI):
        df_cronologia = pd.read_csv(FILE_DB_PRONOSTICI)

        if not df_cronologia.empty:
            df_cronologia = df_cronologia.drop_duplicates(subset=['Data', 'Partita'], keep='last')
            
            col_ex1, col_ex2 = st.columns([1, 4])
            with col_ex1:
                csv_data = df_cronologia.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Scarica file CSV", csv_data, f"pronostici_{date.today()}.csv", 'text/csv')
            
            date_disponibili = sorted(df_cronologia['Data'].unique(), reverse=True)
            date_disponibili.insert(0, "Tutte")
            data_scelta = st.selectbox("📅 Filtra per data:", date_disponibili)
            
            df_da_mostrare = df_cronologia if data_scelta == "Tutte" else df_cronologia[df_cronologia['Data'] == data_scelta]

            if st.button("🔄 Aggiorna Risultati Reali"):
                with st.spinner("Controllo risultati in corso..."):
                    aggiorna_risultati_pronostici()
                    st.rerun()

            st.dataframe(df_da_mostrare.style.apply(highlight_winners, axis=1), use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("🛠️ Gestione Dati ed Emergenze")
            
            col_back, col_del = st.columns(2)
            
            with col_back:
                with st.popover("⏪ Ripristino Backup", use_container_width=True):
                    st.info("Questa azione sovrascriverà la cronologia attuale con l'ultimo backup giornaliero salvato.")
                    if st.button("Conferma Ripristino", type="secondary", use_container_width=True):
                        successo, messaggio = ripristina_ultimo_backup()
                        if successo:
                            st.success(messaggio)
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error(messaggio)

            with col_del:
                with st.popover("🗑️ Elimina Cronologia", use_container_width=True):
                    st.warning("⚠️ Sei sicuro? Cancellerai tutti i pronostici salvati.")
                    if st.button("Sì, cancella tutto", type="primary", use_container_width=True):
                        try:
                            os.remove(FILE_DB_PRONOSTICI)
                            st.success("Cronologia eliminata!")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore: {e}")
        else:
            st.info("La cronologia è vuota.")
    else:
        st.warning("Nessun pronostico salvato finora.")

with tab4:
    st.header("📊 Performance Delphi")
    if os.path.exists(FILE_DB_PRONOSTICI):
        df_stat = pd.read_csv(FILE_DB_PRONOSTICI)
        df_v = df_stat[df_stat['Risultato_Reale'] != "N/D"].copy()
        
        if not df_v.empty:
            def verifica(r):
                try:
                    h, a = map(int, str(r['Risultato_Reale']).split('-'))
                    return check_1x2(r['1X2'], h, a)
                except: return False
            
            df_v['Vinto'] = df_v.apply(verifica, axis=1)
            win_rate = df_v['Vinto'].mean()
            
            c1, c2 = st.columns(2)
            c1.metric("Win Rate 1X2", f"{win_rate:.1%}")
            c2.metric("Match Totali", len(df_v))
            
            st.subheader("Ultime 10 Giocate Verificate")
            st.dataframe(df_v[['Partita', '1X2', 'Risultato_Reale', 'Vinto']].tail(10), use_container_width=True)
        else:
            st.info("Aggiorna i risultati reali nella Cronologia per generare le statistiche.")
    else:
        st.warning("Database pronostici non trovato.")
