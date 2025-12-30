import pandas as pd
import math
import requests
import os
import time
from datetime import datetime
import streamlit as st
import pytz 

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Delphi Predictor Pro", layout="centered")

API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'

# File 1: Database scaricato dall'API per i calcoli (Calendario + Storico)
FILE_DB_CALCIO = 'database_pro_2025.csv'
# File 2: Il tuo database personale dei pronostici salvati
FILE_DB_PRONOSTICI = 'database_pronostici.csv'

# --- 2. FUNZIONI GESTIONE DATABASE PRONOSTICI (LOCALE) ---
def inizializza_db_pronostici():
    if not os.path.exists(FILE_DB_PRONOSTICI):
        df = pd.DataFrame(columns=["Data", "Ora", "Partita", "Indice LG", "Fiducia", "Dati", "Match_ID", "Risultato", "Stato"])
        df.to_csv(FILE_DB_PRONOSTICI, index=False)

def salva_in_locale(match, lg_idx, fiducia, dati, match_id=None):
    try:
        inizializza_db_pronostici()
        fuso_ita = pytz.timezone('Europe/Rome')
        adesso = datetime.now(fuso_ita)
        
        nuova_riga = {
            "Data": adesso.strftime("%d/%m/%Y"),
            "Ora": adesso.strftime("%H:%M"),
            "Partita": match,
            "Indice LG": lg_idx,
            "Fiducia": f"{fiducia}", # Salviamo come stringa o numero
            "Dati": f"{dati}",
            "Match_ID": match_id if match_id else "N/A",
            "Risultato": "In attesa",
            "Stato": "Da verificare"
        }
        
        df = pd.read_csv(FILE_DB_PRONOSTICI)
        df = pd.concat([df, pd.DataFrame([nuova_riga])], ignore_index=True)
        df.to_csv(FILE_DB_PRONOSTICI, index=False)
        return True
    except Exception as e:
        st.error(f"Errore tecnico salvataggio: {e}")
        return False

def recupera_risultato_match(match_id):
    if not match_id or str(match_id) in ["None", "N/A", "nan"]:
        return None, None
    
    url = f"https://api.football-data.org/v4/matches/{int(float(match_id))}"
    headers = {"X-Auth-Token": API_TOKEN}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200: return None, None
        
        data = response.json()
        if data.get('status') == 'FINISHED':
            home = data['score']['fullTime']['home']
            away = data['score']['fullTime']['away']
            if home > away: esito = "1"
            elif home < away: esito = "2"
            else: esito = "X"
            return f"{home}-{away}", esito
        return None, None
    except Exception:
        return None, None

def aggiorna_statistiche_locali():
    if not os.path.exists(FILE_DB_PRONOSTICI):
        return
    
    df = pd.read_csv(FILE_DB_PRONOSTICI)
    # Filtriamo i match "Da verificare" con un ID valido
    mask = (df['Stato'] == 'Da verificare') & (df['Match_ID'].notnull()) & (df['Match_ID'].astype(str) != 'N/A')
    
    if not df[mask].empty:
        aggiornati = 0
        progress = st.progress(0)
        totale = len(df[mask])
        
        for i, (idx, row) in enumerate(df[mask].iterrows()):
            risultato_string, esito_reale = recupera_risultato_match(row['Match_ID'])
            if risultato_string:
                df.at[idx, 'Risultato'] = risultato_string
                df.at[idx, 'Stato'] = "Verificato"
                aggiornati += 1
            time.sleep(0.5) # Rispetto limiti API
            progress.progress((i + 1) / totale)
        
        if aggiornati > 0:
            df.to_csv(FILE_DB_PRONOSTICI, index=False)
            st.success(f"✅ Aggiornati {aggiornati} risultati!")
            time.sleep(1)
            st.rerun()
        else:
            st.info("Nessun match terminato trovato tra quelli in attesa.")
    else:
        st.info("Tutti i pronostici sono già verificati.")

# --- 3. FUNZIONI MATEMATICHE & UTILITÀ ---
def poisson_probability(k, exp):
    if exp <= 0: return 0
    return (exp**k * math.exp(-exp)) / math.factorial(k)

def stima_quota(prob):
    if prob <= 0.001: return 99.00
    return round(1 / prob, 2)

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

# --- 4. FUNZIONE SCARICO DATI (CORRETTA CON ID) ---
def aggiorna_con_api():
    headers = {'X-Auth-Token': API_TOKEN}
    leagues = {'WC': 'FIFA World Cup', 'SA':'Serie A', 'PL':'Premier League', 'ELC': 'Championship', 'PD':'La Liga', 'BL1':'Bundesliga', 'FL1':'Ligue 1', 'DED': 'Eredivisie',  'CL':'UEFA Champions League', 'EC': 'UEFA Europa League', 'PPL': 'Primeira Liga', 'BSA': 'Campeonato Brasileiro'}
    
    st.info("Inizio download dati e calendario...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    rows = []
    try:
        for i, (code, name) in enumerate(leagues.items()):
            status_text.text(f"📥 Scaricando: {name}...")
            r = requests.get(f"https://api.football-data.org/v4/competitions/{code}/matches", headers=headers, timeout=10)
            if r.status_code == 200:
                for m in r.json().get('matches', []):
                    home = m['homeTeam']['shortName'] or m['homeTeam']['name']
                    away = m['awayTeam']['shortName'] or m['awayTeam']['name']
                    ref = m['referees'][0].get('name', 'N.D.') if m.get('referees') else 'N.D.'
                    # SALVIAMO L'ID QUI
                    match_id = m['id'] 
                    rows.append([match_id, name, m['utcDate'][:10], home, away, m['status'], m['score']['fullTime']['home'], m['score']['fullTime']['away'], ref])
            time.sleep(1.2)
            progress_bar.progress((i + 1) / len(leagues))
        
        # Aggiunta colonna ID al CSV principale
        pd.DataFrame(rows, columns=['ID', 'League', 'Date', 'HomeTeam', 'AwayTeam', 'Status', 'FTHG', 'FTAG', 'Referee']).to_csv(FILE_DB_CALCIO, index=False)
        status_text.text("✅ Database aggiornato con successo!")
        st.success("Tutti i dati sono pronti.")
    except Exception as e: 
        st.error(f"Errore download API: {e}")

# --- 5. LOGICA DI ANALISI ---
def calcola_pronostico_streamlit(nome_input):
    if not os.path.exists(FILE_DB_CALCIO):
        st.error("⚠️ Database non trovato. Vai su 'Gestione' e clicca 'Aggiorna Database'."); return
    
    df = pd.read_csv(FILE_DB_CALCIO)
    df['FTHG'] = pd.to_numeric(df['FTHG'], errors='coerce').fillna(0)
    df['FTAG'] = pd.to_numeric(df['FTAG'], errors='coerce').fillna(0)
    
    # Ricerca Match
    match = df[df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED']) & 
               (df['HomeTeam'].str.contains(nome_input, case=False, na=False) | 
                df['AwayTeam'].str.contains(nome_input, case=False, na=False))]
    
    if match.empty:
        st.warning(f"Nessun match futuro trovato per '{nome_input}'"); return

    m = match.iloc[0]
    match_id_reale = m['ID'] # Recuperiamo l'ID salvato
    casa, fuori = m['HomeTeam'], m['AwayTeam']
    
    # Calcoli Statistici
    giocate = df[df['Status'] == 'FINISHED'].copy()
    arbitro = m.get('Referee', 'N.D.')
    molt_arbitro = analizza_severita_arbitro(giocate, arbitro)
    
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

    # Poisson & Probabilità
    p_u25, p_gol, total_p = 0, 0, 0
    sgf = {i:0 for i in range(6)}
    re_finali = []
    
    for i in range(7):
        for j in range(7):
            prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
            total_p += prob
            if (i+j) < 2.5: p_u25 += prob
            if i > 0 and j > 0: p_gol += prob
            sgf[min(i+j, 5)] += prob
            re_finali.append({'s': f"{i}-{j}", 'p': prob})

    # Visualizzazione UI
    st.header(f"🏟️ {casa} vs {fuori}")
    st.caption(f"ID Match: {match_id_reale} | Data: {m['Date']}")
    
    lg_idx = calcola_late_goal_index(casa, fuori)
    fiducia_calc = 85 # Qui potresti mettere un tuo calcolo dinamico
    dati_calc = 90
    
    col_fid, col_aff = st.columns(2)
    with col_fid:
        st.success(f"🎯 Fiducia: {fiducia_calc}%")
    with col_aff:
        st.info(f"📊 Dati: {dati_calc}%")

    st.divider()
    
    # --- PULSANTE SALVATAGGIO ---
    # Qui integriamo il salvataggio con l'ID corretto
    if st.button("💾 Salva Pronostico nel Database"):
        match_fullname = f"{casa} vs {fuori}"
        # Chiamata alla funzione di salvataggio unificata
        esito = salva_in_locale(match_fullname, lg_idx, fiducia_calc, dati_calc, match_id=match_id_reale)
        if esito:
            st.success("✅ Pronostico salvato e pronto per la verifica!")
    
    # Resto delle statistiche visuali...
    c1, c2 = st.columns(2)
    with c1:
        st.write("Top Risultati Esatti")
        for r in sorted(re_finali, key=lambda x: x['p'], reverse=True)[:3]:
            st.write(f"**{r['s']}** ({r['p']/total_p:.1%})")
            
    with c2:
         st.write("Quote Stimate")
         st.write(f"Gol: {stima_quota(p_gol/total_p)}")
         st.write(f"Over 2.5: {stima_quota(1-(p_u25/total_p))}")

# --- 6. INTERFACCIA PRINCIPALE ---
st.image("banner.png") if os.path.exists("banner.png") else st.write("## Delphi Predictor Pro")

tab_analisi, tab_cronologia, tab_gestione = st.tabs(["🎯 Analisi", "📊 Cronologia & Verifica", "⚙️ Gestione"])

with tab_analisi:
    search_query = st.text_input("Inserisci nome squadra (es. Inter, Milan):")
    if st.button("Analizza Match", type="primary"):
        if search_query: 
            calcola_pronostico_streamlit(search_query)
        else:
            st.warning("Scrivi il nome di una squadra.")

with tab_cronologia:
    st.subheader("I tuoi Pronostici")
    if st.button("🔄 Aggiorna Risultati dai Match Finiti"):
        aggiorna_statistiche_locali()
        
    if os.path.exists(FILE_DB_PRONOSTICI):
        df_crono = pd.read_csv(FILE_DB_PRONOSTICI)
        if not df_crono.empty:
            # Mostra prima i più recenti
            st.dataframe(df_crono.iloc[::-1], use_container_width=True)
            
            # Download CSV
            csv = df_crono.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Scarica Excel/CSV", csv, "miei_pronostici.csv", "text/csv")
        else:
            st.info("Nessun pronostico salvato ancora.")
    else:
        st.info("Database vuoto.")

with tab_gestione:
    st.write("Usa questo tasto per scaricare il calendario aggiornato e i risultati storici per i calcoli.")
    if st.button("🌐 Aggiorna Database Calcio (API)"):
        aggiorna_con_api()
