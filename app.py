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
    columns = [
        "Data", "Ora", "Partita", "Fiducia", "Affidabilità", 
        "1X2", "U/O 2.5", "G/NG", "SGF", "SGC", "SGO", 
        "Top 6 RE Finali", "Top 3 RE 1°T", "Fatica", "Match_ID", "Risultato_Reale", "PT_Reale"
    ]
    if not os.path.exists(FILE_DB_PRONOSTICI):
        # Crea un file nuovo con le colonne se non esiste
        df = pd.DataFrame(columns=columns)
        df.to_csv(FILE_DB_PRONOSTICI, index=False)
    else:
        # Se esiste, controlliamo che non sia vuoto o corrotto
        try:
            df_esistente = pd.read_csv(FILE_DB_PRONOSTICI)
            # Aggiunge colonne mancanti se hai aggiornato il codice ma il file è vecchio
            for col in columns:
                if col not in df_esistente.columns:
                    df_esistente[col] = "N/D"
            df_esistente.to_csv(FILE_DB_PRONOSTICI, index=False)
        except:
            # Se il file è illeggibile, lo resetta
            pd.DataFrame(columns=columns).to_csv(FILE_DB_PRONOSTICI, index=False)

# *** FIX CRUCIALE: ESEGUIAMO LA FUNZIONE ALL'AVVIO ***
inizializza_db()

def salva_completo_in_locale(data_dict):
    try:
        df = pd.read_csv(FILE_DB_PRONOSTICI)
        # Creiamo la riga prendendo i valori dal dizionario
        # Usiamo data_dict.get(chiave, "N/D") per evitare errori se una chiave manca
        nuova_riga = {col: data_dict.get(col, "N/D") for col in df.columns}
        
        df = pd.concat([df, pd.DataFrame([nuova_riga])], ignore_index=True)
        df.to_csv(FILE_DB_PRONOSTICI, index=False)
        return True
    except Exception as e:
        st.error(f"Errore critico salvataggio: {e}")
        return False

def calcola_trend_forma(df_giocate, squadra):
    # Filtra le ultime 4 partite della squadra
    ultime = df_giocate[(df_giocate['HomeTeam'] == squadra) | (df_giocate['AwayTeam'] == squadra)].tail(4)
    if ultime.empty:
        return "N.D.", 1.0
    
    punti = 0
    stringa_trend = []
    for _, r in ultime.iterrows():
        # Determina se la squadra giocava in casa o fuori
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
    
    # Calcola un moltiplicatore (Media 1.0)
    # 12 punti (4 vittorie) = 1.2x attacco / 0.8x difesa
    # 0 punti (4 sconfitte) = 0.8x attacco / 1.2x difesa
    moltiplicatore = round(0.8 + (punti / 12) * 0.4, 2)
    return "".join(stringa_trend), moltiplicatore

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
                        m['score']['halfTime']['home'], m['score']['halfTime']['away'], 
                        ref, m['id']
                    ])
                    
            time.sleep(1) 
            progress_bar.progress((i + 1) / len(competitions))

        # Salviamo con la colonna ID e le nuove colonne HT
        df_new = pd.DataFrame(rows, columns=[
            'League', 'Date', 'HomeTeam', 'AwayTeam', 'Status', 
            'FTHG', 'FTAG', 'HTHG', 'HTAG', 'Referee', 'ID'
        ])
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

def controlla_fatica(df, squadra, data_match_str):
    try:
        # Convertiamo la data del match corrente (formato DD/MM/YYYY)
        data_m = pd.to_datetime(data_match_str, dayfirst=True).normalize()
        
        # Filtriamo i match conclusi della squadra (Home o Away)
        storico = df[(df['Status'] == 'FINISHED') & 
                    ((df['HomeTeam'] == squadra) | (df['AwayTeam'] == squadra))].copy()
        
        if storico.empty:
            return False
            
        # Normalizziamo le date del database per il confronto
        storico['Date_dt'] = pd.to_datetime(storico['Date'], utc=True).dt.tz_localize(None).dt.normalize()
        
        # Troviamo la data dell'ultimo match disputato PRIMA di oggi
        ultima_partita = storico[storico['Date_dt'] < data_m]['Date_dt'].max()
        
        if pd.notnull(ultima_partita):
            giorni_riposo = (data_m - ultima_partita).days
            # --- LIMITE IMPOSTATO A 3 GIORNI ---
            return giorni_riposo <= 3
    except Exception as e:
        print(f"Errore controllo fatica: {e}")
    return False

def calcola_late_goal_index(casa, fuori):
    # Placeholder per logica late goal
    val = (len(str(casa)) + len(str(fuori))) % 10
    return round(val * 0.10 + 0.5, 2)

def analizza_distribuzione_tempi(df_giocate, squadra):
    # Chiama la funzione pericolosità che abbiamo scritto sopra
    p1, p2 = analizza_pericolosita_tempi(df_giocate, squadra)
    return p1, p2

def analizza_h2h(df_giocate, casa, fuori):
    # Filtriamo tutti i precedenti tra le due squadre (sia a campi invertiti che non)
    storico = df_giocate[
        ((df_giocate['HomeTeam'] == casa) & (df_giocate['AwayTeam'] == fuori)) |
        ((df_giocate['HomeTeam'] == fuori) & (df_giocate['AwayTeam'] == casa))
    ].tail(5) # Consideriamo gli ultimi 5 scontri diretti
    
    if storico.empty:
        return 1.0, 1.0, "Nessun precedente recente"
    
    punti_casa = 0
    gol_casa = 0
    gol_fuori = 0
    
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
            
    # Calcolo moltiplicatori basati sul dominio storico
    # Se la squadra in casa ha vinto spesso, riceve un bonus (max 1.10)
    # Se ha sempre perso, riceve un malus (min 0.90)
    win_rate = punti_casa / (len(storico) * 3)
    bonus_h2h_casa = round(0.9 + (win_rate * 0.2), 2)
    bonus_h2h_fuori = round(2.0 - bonus_h2h_casa, 2)
    
    testo_h2h = f"Ultimi {len(storico)} match: {punti_casa} pt fatti dal team casa"
    return bonus_h2h_casa, bonus_h2h_fuori, testo_h2h

def get_stats(team, is_home_side, df_giocate):
    # Filtriamo le ultime 15 partite totali della squadra
    t = df_giocate[(df_giocate['HomeTeam'] == team) | (df_giocate['AwayTeam'] == team)].tail(15)
    if t.empty: return 1.2, 1.2
        
    # Filtriamo per condizione (Casa o Fuori)
    stats_condizione = t[t['HomeTeam'] == team] if is_home_side else t[t['AwayTeam'] == team]
            
    if not stats_condizione.empty:
        if is_home_side:
            gf = stats_condizione['FTHG'].mean()
            gs = stats_condizione['FTAG'].mean()
        else:
            gf = stats_condizione['FTAG'].mean()
            gs = stats_condizione['FTHG'].mean()
    else:
        # Fallback: media totale delle ultime 15
        gf = t.apply(lambda r: r['FTHG'] if r['HomeTeam']==team else r['FTAG'], axis=1).mean()
        gs = t.apply(lambda r: r['FTAG'] if r['HomeTeam']==team else r['FTHG'], axis=1).mean()
            
    return max(0.5, gf), max(0.5, gs)

def analizza_pericolosita_tempi(df_giocate, squadra):
    # Analizziamo gli ultimi 15 match per avere un campione più ampio
    ultime = df_giocate[(df_giocate['HomeTeam'] == squadra) | (df_giocate['AwayTeam'] == squadra)].tail(15)
    
    gol_fatti_1t = 0
    gol_fatti_2t = 0
    match_validi = 0
    
    for _, r in ultime.iterrows():
        is_home = r['HomeTeam'] == squadra
        f_tot = r['FTHG'] if is_home else r['FTAG']
        
        # Cerchiamo i gol del primo tempo nelle colonne HTHG/HTAG
        # Se non esistono o sono NaN, saltiamo il calcolo per questo match
        h_1t = r.get('HTHG') if is_home else r.get('HTAG')
        
        if pd.notnull(h_1t):
            gol_fatti_1t += h_1t
            gol_fatti_2t += (f_tot - h_1t)
            match_validi += 1
            
    if match_validi == 0:
        return 50.0, 50.0  # Fallback se mancano i dati storici parziali
    
    tot = gol_fatti_1t + gol_fatti_2t
    if tot == 0: return 50.0, 50.0
    
    perc_1t = round((gol_fatti_1t / tot * 100), 1)
    perc_2t = round((gol_fatti_2t / tot * 100), 1)
    
    return perc_1t, perc_2t

def esegui_analisi(nome_input, pen_h=1.0, pen_a=1.0, is_big_match=False): # Aggiunto parametro
    if not os.path.exists(FILE_DB_CALCIO):
        st.error("Database Calcio mancante. Aggiorna il DB"); return None

    df = pd.read_csv(FILE_DB_CALCIO)
    # Forza il formato datetime con UTC per combaciare con 'today'
    df['Date'] = pd.to_datetime(df['Date'], utc=True) 

# Invece di: today = pd.to_datetime(date.today())
# Usa questa versione che rende 'today' compatibile con le date dell'API:
    today = pd.Timestamp.now(tz='UTC').normalize()

    future_matches = df[
        (df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED'])) & 
        (df['HomeTeam'].str.contains(nome_input, case=False, na=False) | 
         df['AwayTeam'].str.contains(nome_input, case=False, na=False)) &
        (df['Date'] >= today)
    ].sort_values(by='Date')
    
    if future_matches.empty:
        st.warning(f"Nessun match futuro trovato per '{nome_input}'."); return None

    m = future_matches.iloc[0]
    casa, fuori = m['HomeTeam'], m['AwayTeam']
    match_id = m.get('ID', 'N/A')

    # Traduzione Lega
    codice_lega = m['League']
    nome_lega = LEAGUE_MAP.get(codice_lega, codice_lega)

    giocate = df[df['Status'] == 'FINISHED'].copy()
    arbitro = str(m.get('Referee', 'N.D.'))
    molt_arbitro = analizza_severita_arbitro(giocate, arbitro)
    avg_g = max(1.1, pd.to_numeric(giocate['FTHG'], errors='coerce').mean())
    
    # Passiamo 'giocate' come terzo argomento
    att_h, dif_h = get_stats(casa, True, giocate)
    att_a, dif_a = get_stats(fuori, False, giocate)
    
    trend_h, molt_forma_h = calcola_trend_forma(giocate, casa)
    trend_a, molt_forma_a = calcola_trend_forma(giocate, fuori)

    # Calcolo H2H
    m_h2h_h, m_h2h_a, testo_h2h = analizza_h2h(giocate, casa, fuori)
    
    # Applichiamo tutto: Forma, Arbitro, Assenze e ora H2H
    exp_h = (att_h * dif_a / avg_g) * molt_forma_h * (2 - molt_arbitro) * pen_h * m_h2h_h
    exp_a = (att_a * dif_h / avg_g) * molt_forma_a * (2 - molt_arbitro) * pen_a * m_h2h_a

    # AGGIUNGI QUESTO BLOCCO:
    if is_big_match:
        exp_h *= 0.88 # Riduzione del 12%
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
    re_1t, total_p_1t = [], 0
    for i in range(4):
        for j in range(4):
            pb = poisson_probability(i, eh1) * poisson_probability(j, ea1)
            total_p_1t += pb
            re_1t.append({'s': f"{i}-{j}", 'p': pb})
   
    p1, px, p2 = p1/tot, px/tot, p2/tot
    pu, pg = pu/tot, pg/tot
    res_1x2 = "1" if p1 > px and p1 > p2 else ("X" if px > p1 and px > p2 else "2")
    res_uo = "OVER 2.5" if (1-pu) > 0.5 else "UNDER 2.5"
    res_gng = "GOL" if pg > 0.5 else "NO GOL"

    # --- FUNZIONI DI FORMATTAZIONE CON QUOTE ---
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

    # Generazione stringhe corrette
    top_sgf_final = formatta_somma_con_quote(sgf, 5, 3)
    top_sgc_final = formatta_somma_con_quote(sgc, 3, 2)
    top_sgo_final = formatta_somma_con_quote(sgo, 3, 2)
    top_re_final = formatta_re_con_quote(re_fin, 6)
    top_re1t_final = formatta_re_con_quote(re_1t, 3)

    # Calcolo distribuzione gol per tempo (Assicurati che la funzione sopra sia presente)
    dist_1t_h, dist_2t_h = analizza_distribuzione_tempi(giocate, casa)
    dist_1t_a, dist_2t_a = analizza_distribuzione_tempi(giocate, fuori)

    # Calcoliamo la probabilità di quale tempo avrà più gol
    prob_1t_piu_gol = (dist_1t_h + dist_1t_a) / 2
    prob_2t_piu_gol = (dist_2t_h + dist_2t_a) / 2
    tempo_top = "2° Tempo" if prob_2t_piu_gol > prob_1t_piu_gol else "1° Tempo"
    
    # --- FIX DEFINITIVO ORARIO ---
    try:
        # L'API restituisce 2025-05-20T18:30:00Z. 
        # Forziamo il parsing includendo l'informazione UTC
        dt_event = pd.to_datetime(m['Date'], utc=True)
        
        # Convertiamo nel fuso orario di Roma (gestisce automaticamente ora legale/solare)
        fuso_roma = pytz.timezone('Europe/Rome')
        dt_event_ita = dt_event.astimezone(fuso_roma)
    except Exception as e:
        # In caso di errore estremo, mettiamo un orario neutro ma visibile
        dt_event_ita = datetime.now(pytz.timezone('Europe/Rome'))
    
    # Prepariamo le stringhe per il dizionario
    data_finale = dt_event_ita.strftime("%d/%m/%Y")
    ora_finale = dt_event_ita.strftime("%H:%M")

    return {
        "Data": data_finale, 
        "Ora": ora_finale,
        "League": nome_lega, #m['League'],
        "Partita": f"{casa} vs {fuori}",
        "Fiducia": f"{int(max(p1,px,p2)*100)}%", 
        "Affidabilità": f"{85 + int(molt_arbitro*2)}%",
        "Trend_Casa": trend_h,
        "Trend_Fuori": trend_a,
        "Forma_H": molt_forma_h,
        "Forma_A": molt_forma_a,
        "1X2": res_1x2, "U/O 2.5": res_uo, "G/NG": res_gng,
        "SGF": top_sgf_final, "SGC": top_sgc_final, "SGO": top_sgo_final,
        "Top 6 RE Finali": top_re_final, 
        "Top 3 RE 1°T": top_re1t_final,
        #"Fatica": data_dict.get ("Fatica"),
        "Match_ID": match_id, "Risultato_Reale": "N/D", "PT_Reale": "N/D",
        "p1": p1, "px": px, "p2": p2, "pu": pu, "pg": pg,
        "h2h_info": testo_h2h,
        "m_h2h_h": m_h2h_h,
        "m_h2h_a": m_h2h_a,
        "dist_1t_h": dist_1t_h,
        "dist_2t_h": dist_2t_h,
        "dist_1t_a": dist_1t_a,
        "dist_2t_a": dist_2t_a,
        "tempo_top": tempo_top,
        "casa_nome": casa,   # Aggiungiamo questi per comodità
        "fuori_nome": fuori,
        "lg": calcola_late_goal_index(casa, fuori),
        "is_big_match": is_big_match,
        "arbitro": arbitro, 
        "molt_arbitro": molt_arbitro
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
tab1, tab2, tab3 = st.tabs(["🎯 **Analisi**", "⚙️ **Database**", "📜 **Cronologia**"])

with tab1:
    sq = st.text_input("🔍 Inserisci Squadra:")

    # Inizializziamo gli stati se non esistono
    if 'dati_acquisiti' not in st.session_state:
        st.session_state['dati_acquisiti'] = False
    if 'squadra_precedente' not in st.session_state:
        st.session_state['squadra_precedente'] = ""

    # Reset se l'utente cambia squadra nel box
    if sq != st.session_state['squadra_precedente']:
        st.session_state['dati_acquisiti'] = False
        st.session_state['pronostico_corrente'] = None
        st.session_state['squadra_precedente'] = sq

    # --- STEP 1: ACQUISIZIONE ---
    if sq and not st.session_state['dati_acquisiti']:
        if st.button("📊 Acquisisci Dati", type="secondary", use_container_width=True):
            risultati_temp = esegui_analisi(sq)
            if risultati_temp:
                st.session_state['dati_temp'] = risultati_temp
                st.session_state['dati_acquisiti'] = True
                st.rerun()
            else:
                st.error("Squadra non trovata nel database.")

    # --- STEP 2: RICERCA NEWS E GENERAZIONE ---
    if st.session_state['dati_acquisiti']:
        d_temp = st.session_state['dati_temp']
        
        # Link Google News con data precisa
        data_match = d_temp['Data']
        search_query = f"**Formazione {sq} nella partita del {data_match}**"
        google_news_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}&tbm=nws"
        
        st.success(f"✅ Dati acquisiti per {d_temp['Partita']}")
        st.markdown(f"👉 [**Controlla Formazione e Assenti per il {data_match}**]({google_news_url})")
        
        st.divider()
        st.info("Regola la potenza offensiva se mancano giocatori chiave")
        
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            pen_h = st.select_slider(f"Potenza Attacco Casa", 
                                     options=[0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0], value=1.0)
        with col_p2:
            pen_a = st.select_slider(f"Potenza Attacco Fuori", 
                                     options=[0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0], value=1.0)        
            is_big_match = st.toggle("🔥 Filtro Big Match / Derby")

        # Pulsante finale per il pronostico
        if st.button("🎯 Genera Pronostico", type="primary", use_container_width=True):
            # Eseguiamo l'analisi finale con le penali scelte
            risultati = esegui_analisi(sq, pen_h, pen_a, is_big_match)
            st.session_state['pronostico_corrente'] = risultati
        else:
            st.session_state['pronostico_corrente'] = None

    if 'pronostico_corrente' in st.session_state and st.session_state['pronostico_corrente']:
        d = st.session_state['pronostico_corrente']
        df_per_fatica = pd.read_csv(FILE_DB_CALCIO) # Carichiamo il DB qui per usarlo sotto
        casa_nome, fuori_nome = d['Partita'].split(" vs ")

        # --- UI TESTATA ---
        st.header(f"🏟️ **{d['Partita']}**")
        st.subheader(f"🏆 Lega: {d.get('League', 'N.D.')}")
        st.subheader(f"📅 Data: {d['Data']} ore {d['Ora']}")

        if d.get('is_big_match'):
            st.warning("🛡️ **Filtro Big Match Attivo**: Le probabilità Over/Under sono state ricalcolate per una partita tattica.")

        # --- 2. ORA PUOI USARE casa_nome E fuori_nome PER LA FORMA ---
        c_trend1, c_trend2 = st.columns(2)
        with c_trend1:
            st.markdown(f"**Forma {casa_nome}:** {d['Trend_Casa']}")
            st.caption(f"Incidenza stats: {d['Forma_H']}x")
        with c_trend2:
            st.markdown(f"**Forma {fuori_nome}:** {d['Trend_Fuori']}")
            st.caption(f"Incidenza stats: {d['Forma_A']}x")
        st.write("---")
        
        # --- SEZIONE WARNING FATICA ---
        df_calcio = pd.read_csv(FILE_DB_CALCIO)
        casa_nome, fuori_nome = d['Partita'].split(" vs ")
        
        fatica_casa = controlla_fatica(df_calcio, casa_nome, d['Data'])
        fatica_fuori = controlla_fatica(df_calcio, fuori_nome, d['Data'])
        
        if fatica_casa or fatica_fuori:
            with st.container():
                st.markdown("🏃‍♂️ **Allerta Stanchezza**")
                c_fat1, c_fat2 = st.columns(2)
                with c_fat1:
                    if fatica_casa:
                        st.error(f"⚠️ **{casa_nome}: ha giocato meno di 72 ore fa!**")
                with c_fat2:
                    if fatica_fuori:
                        st.error(f"⚠️ **{fuori_nome}**: ha giocato meno di 72 ore fa!**")
            st.divider()

        c_inf1, c_inf2 = st.columns(2)

        with c_inf1:
            st.info(f"👮 **Arbitro**: {d.get('arbitro', 'N.D.')}  |  **Impatto**: {d.get('molt_arbitro', 1.0)}x")
            casa_nome = d['Partita'].split(" vs ")[0]
            fuori_nome = d['Partita'].split(" vs ")[1]
            #if controlla_fatica(df_per_fatica, casa_nome, d['Data']) or controlla_fatica(df_per_fatica, fuori_nome, d['Data']):
                #st.warning("⚠️ **Possibile stanchezza: una delle squadre ha giocato meno di 3 giorni fa!**")

        with c_inf2:
            st.info(f"⏳ **Gol nel finale: {d['lg']:.2f}**")
            if d['lg'] > 1.2: 
                st.error("🔥🔥🔥 **POSSIBILE GOL NEL FINALE (80+ MINUTO)**")

        # --- SEZIONE H2H ---
        #st.divider()
        #st.subheader("⚔️ Scontri Diretti (H2H)")

        # Usiamo .get() per evitare il KeyError se la chiave manca
        #st.write(f"📊 {d.get('h2h_info', 'Dati H2H non disponibili')}")

        # --- SEZIONE FASCE ORARIE ---
        #st.divider()
        #st.subheader("⏰ Analisi Momento Gol (Ultime 10)")
        
        #c_time1, c_time2 = st.columns(2)
        #p1_h, p2_h = analizza_pericolosita_tempi(df_calcio, casa_nome)
        #p1_a, p2_a = analizza_pericolosita_tempi(df_calcio, fuori_nome)

        #if p1_h == 50.0 and p2_h == 50.0:
            #st.caption("⚠️ Dati parziali insufficienti nel DB per un'analisi accurata dei tempi.")
        #else:
            # Mostra i tuoi metric/progress bar qui
            #st.write(f"Distribuzione Gol {casa_nome}: {p1_h}% (1°T) / {p2_h}% (2°T)")

        #with c_time1:
            #st.write(f"**{casa_nome}**")
            #st.metric("Gol 1° Tempo", f"{p1_h}%")
            #st.metric("Gol 2° Tempo", f"{p2_h}%", delta=f"{p2_h-p1_h}%" if p2_h > p1_h else None)
            #if p2_h > 65: st.warning("⚠️ Squadra da 'Second Time Goal'")

        #with c_time2:
            #st.write(f"**{fuori_nome}**")
            #st.metric("Gol 1° Tempo", f"{p1_a}%")
            #st.metric("Gol 2° Tempo", f"{p2_a}%", delta=f"{p2_a-p1_a}%" if p2_a > p1_a else None)
            #if p1_a > 60: st.info("⚡ Partenza Sprint garantita")
        
        # --- SEZIONE DISTRIBUZIONE TEMPI ---
        st.divider()
        st.subheader("⏱️ Analisi Tempi (Distribuzione Gol)")
        ct1, ct2 = st.columns(2)
        
        with ct1:
            st.write(f"**{casa_nome}**")
            # Usiamo i dati estratti dal dizionario 'd'
            st.progress(d['dist_1t_h'] / 100, text=f"1° Tempo: {d['dist_1t_h']}%")
            st.progress(d['dist_2t_h'] / 100, text=f"2° Tempo: {d['dist_2t_h']}%")
            
        with ct2:
            st.write(f"**{fuori_nome}**")
            st.progress(d['dist_1t_a'] / 100, text=f"1° Tempo: {d['dist_1t_a']}%")
            st.progress(d['dist_2t_a'] / 100, text=f"2° Tempo: {d['dist_2t_a']}%")

        st.info(f"💡 **Tendenza**: Il tempo con più gol previsto è il **{d['tempo_top']}**")
        
        # --- ESITO FINALE 1X2 ---
        st.divider()
        st.subheader("🏁 Esito Finale 1X2")
        c1, cx, c2 = st.columns(3)
        
        with c1:
            st.success(f" 1: \n 📈 Prob: {d['p1']:.1%}\n 💰 Quota: {stima_quota(d['p1'])}")
        with cx:
            st.success(f" X: \n 📈 Prob: {d['px']:.1%}\n 💰 Quota: {stima_quota(d['px'])}")
        with c2:
            st.success(f" 2: \n 📈 Prob: {d['p2']:.1%}\n 💰 Quota: {stima_quota(d['p2'])}")

        # --- MERCATI ACCESSORI ---
        st.divider()
        st.subheader("📊 Under/Over 2,5 & Gol/NoGol")
        col_uo, col_gng = st.columns(2)
        
        with col_uo:
            # Calcolo probabilità e quota per l'Over partendo dall'Under
            p_over = 1 - d['pu']
            st.warning(f"\n**UNDER 2,5:** 📈 Prob: {d['pu']:.1%} (💰 Quota: {stima_quota(d['pu'])})\n\n**OVER 2,5:** 📈 Prob {p_over:.1%} (💰 Quota: {stima_quota(p_over)})")
            
        with col_gng:
            # Calcolo probabilità e quota per il No Gol partendo dal Gol
            p_nogol = 1 - d['pg']
            st.warning(f"\n**GOL:** 📈 Prob: {d['pg']:.1%} (💰 Quota: {stima_quota(d['pg'])})\n\n**NOGOL:** 📈 Prob: {p_nogol:.1%} (💰 Quota: {stima_quota(p_nogol)})")

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
        st.subheader("🎯 Risultati Esatti Probabili")
        cfe1, cfe2 = st.columns(2)

        with cfe1:
            st.success(f"🏁 **Top 6 RE Finali**\n\n{d['Top 6 RE Finali']}")
            
        with cfe2:
            st.info(f"⏱️ **Top 3 RE 1° Tempo**\n\n{d['Top 3 RE 1°T']}")

        # --- TASTO SALVATAGGIO AGGIORNATO ---
        if st.button("💾 Salva in Cronologia", use_container_width=True):
            import re
            dati_puliti = d.copy()

            # Calcolo nota fatica
            nota_fatica = "Nessuna"
            if fatica_casa and fatica_fuori: nota_fatica = "Entrambe"
            elif fatica_casa: nota_fatica = f"Solo {casa_nome}"
            elif fatica_fuori: nota_fatica = f"Solo {fuori_nome}"
            
            # INSERIMENTO CRUCIALE: aggiungiamo la fatica al dizionario prima di pulire
            dati_puliti["Fatica"] = nota_fatica

            # Pulizia quote dai testi (per non sporcare il database)
            campi_con_quote = ["SGF", "SGC", "SGO", "Top 6 RE Finali", "Top 3 RE 1°T"]
            for campo in campi_con_quote:
                if campo in dati_puliti:
                    testo_pulito = re.sub(r'\s\(Q:\s\d+\.\d+\)', '', str(dati_puliti[campo]))
                    dati_puliti[campo] = testo_pulito

            # Specifichiamo quali campi NON vogliamo nel CSV (quelli tecnici/probabilità)
            escludi = ['p1', 'px', 'p2', 'pu', 'pg', 'lg', 'arbitro', 'molt_arbitro', 
                       'dist_1t_h', 'dist_2t_h', 'dist_1t_a', 'dist_2t_a', 'tempo_top', 
                       'casa_nome', 'fuori_nome', 'h2h_info', 'm_h2h_h', 'm_h2h_a', 'is_big_match']
            
            dati_per_csv = {k: v for k, v in dati_puliti.items() if k not in escludi}

            # Chiamata alla funzione di salvataggio
            if salva_completo_in_locale(dati_per_csv):
                st.success("✅ Salvato con successo!")
                time.sleep(0.5)
                st.rerun()

with tab2:
    st.info("⚠️ Aggiornerai Premier, Championship, Primera, Serie A, Liga, Ligue 1, Bundesliga, Eredivisie, Brasileirao Betano, UEFA e FIFA")
    if st.button("🌐 Aggiorna Database"):
        with st.spinner("Aggiornamento database in corso..."):
            aggiorna_database_calcio()

with tab3:
    st.header("📜 Cronologia Pronostici")
    
    if os.path.exists(FILE_DB_PRONOSTICI):
        # 1. CARICAMENTO E PULIZIA AUTOMATICA DUPLICATI
        df_cronologia = pd.read_csv(FILE_DB_PRONOSTICI)

        if not df_cronologia.empty:
            # Rimuove righe identiche (stessa Partita e stessa Data)
            initial_count = len(df_cronologia)
            df_cronologia = df_cronologia.drop_duplicates(subset=['Data', 'Partita'], keep='last')

            # Se sono stati rimossi duplicati, salva subito il file pulito
            if len(df_cronologia) < initial_count:
                df_cronologia.to_csv(FILE_DB_PRONOSTICI, index=False)
                st.toast(f"Pulizia completata: rimossi {initial_count - len(df_cronologia)} duplicati.")

            # --- SEZIONE EXPORT ---
            col_ex1, col_ex2 = st.columns([1, 4])
            with col_ex1:
                # CORRETTO: Usiamo df_cronologia
                csv_data = df_cronologia.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Scarica Excel (CSV)", 
                    data=csv_data, 
                    file_name=f"pronostici_{date.today()}.csv", 
                    mime='text/csv'
                )
            
            # 2. FILTRO PER GIORNATA SPECIFICA
            date_disponibili = sorted(df_cronologia['Data'].unique(), reverse=True)
            date_disponibili.insert(0, "Tutte")
            
            data_scelta = st.selectbox("📅 Filtra per data:", date_disponibili)
            
            if data_scelta != "Tutte":
                df_da_mostrare = df_cronologia[df_cronologia['Data'] == data_scelta]
            else:
                df_da_mostrare = df_cronologia

            # 3. PULSANTE AGGIORNAMENTO RISULTATI
            if st.button("🔄 Aggiorna Risultati Reali"):
                with st.spinner("Controllo risultati in corso..."):
                    aggiorna_risultati_pronostici()
                    st.rerun()

            # 4. VISUALIZZAZIONE TABELLA FILTRATA
            st.dataframe(
                df_da_mostrare.style.apply(highlight_winners, axis=1),
                use_container_width=True,
                hide_index=True
            )

            # --- TASTO CANCELLA CRONOLOGIA ---
            st.divider()
            if st.button("🗑️ Elimina Cronologia...", type="secondary"):
                st.session_state['conferma_delete'] = True

            if st.session_state.get('conferma_delete', False):
                st.error("🚨 **ATTENZIONE: AZIONE IRREVERSIBILE**")
                st.write("Sei sicuro di voler cancellare TUTTA la cronologia?")
                
                c_del1, c_del2 = st.columns(2)
                with c_del1:
                    if st.button("SÌ, CANCELLA", type="primary", use_container_width=True):
                        columns = ["Data", "Ora", "Partita", "Fiducia", "Affidabilità", "1X2", "U/O 2.5", "G/NG", "SGF", "SGC", "SGO", "Top 6 RE Finali", "Top 3 RE 1°T", "Fatica", "Match_ID", "Risultato_Reale", "PT_Reale"]
                        pd.DataFrame(columns=columns).to_csv(FILE_DB_PRONOSTICI, index=False)
                        st.session_state['conferma_delete'] = False
                        st.rerun()
                with c_del2:
                    if st.button("ANNULLA", use_container_width=True):
                        st.session_state['conferma_delete'] = False
                        st.rerun()
        else:
            st.info("La cronologia è vuota.")
    else:
        st.warning("Database non trovato.")
