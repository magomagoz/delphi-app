import pandas as pd
import math
import requests
import os
import time
from datetime import datetime
import streamlit as st
import pytz

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Delphi Predictor Pro", layout="wide") 

API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'
FILE_DB_CALCIO = 'database_pro_2025.csv'
FILE_DB_PRONOSTICI = 'database_pronostici.csv'

# --- 2. FUNZIONI DI VERIFICA LOGICA (PER IL COLORE VERDE) ---
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
    # Pulisce la stringa e controlla se il valore è tra i pronostici (separati da virgola)
    preds = [p.strip() for p in str(pred_string).split(",")]
    return str(value_to_find) in preds

# --- 3. FUNZIONI DATABASE E API ---
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
            "Partita": match, "Fiducia": f"{fid}%", "Affidabilità": f"{aff}%",
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

def aggiorna_risultati_da_api():
    if not os.path.exists(FILE_DB_PRONOSTICI): return
    df = pd.read_csv(FILE_DB_PRONOSTICI)
    headers = {'X-Auth-Token': API_TOKEN}
    
    progress_bar = st.progress(0)
    for i, row in df.iterrows():
        if row['Risultato_Reale'] == "N/D" and str(row['Match_ID']) != "N/A":
            try:
                url = f"https://api.football-data.org/v4/matches/{int(row['Match_ID'])}"
                r = requests.get(url, headers=headers).json()
                if 'score' in r and r['status'] == 'FINISHED':
                    f_h = r['score']['fullTime']['home']
                    f_a = r['score']['fullTime']['away']
                    p_h = r['score']['halfTime']['home']
                    p_a = r['score']['halfTime']['away']
                    df.at[i, 'Risultato_Reale'] = f"{f_h}-{f_a}"
                    df.at[i, 'PT_Reale'] = f"{p_h}-{p_a}"
                time.sleep(1.2) # Delay per limiti API Free
            except: continue
        progress_bar.progress((i + 1) / len(df))
    df.to_csv(FILE_DB_PRONOSTICI, index=False)

# --- 4. LOGICA DI COLORAZIONE CELLA PER CELLA ---
def highlight_winners(row):
    # Array di colori vuoti per la riga
    colors = [''] * len(row)
    if row['Risultato_Reale'] == "N/D": return colors
    
    try:
        # Punteggio Finale
        h, a = map(int, row['Risultato_Reale'].split('-'))
        # Punteggio Primo Tempo
        ph, pa = map(int, row['PT_Reale'].split('-'))
    except: return colors

    green = 'background-color: #d4edda; color: #155724; font-weight: bold'
    
    # Verifica colonne (gli indici devono corrispondere al CSV)
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

def stima_quota(prob_decimal):
    if prob_decimal <= 0.01: return 99.00
    return round(1 / prob_decimal, 2)

# --- 5. INTERFACCIA ---
if os.path.exists("banner.png"):
    st.image("banner.png", use_container_width=True)
else:
    st.markdown("<h1 style='text-align: center;'>⚽ Delphi Predictor Pro</h1>", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["🎯 Analisi Match", "📜 Cronologia e Statistiche"])

with tab1:
    search_query = st.text_input("Cerca Squadra (es: Lazio):", placeholder="Inserisci nome...")
    
    if st.button("Analizza Match", type="primary"):
        if os.path.exists(FILE_DB_CALCIO):
            df_calcio = pd.read_csv(FILE_DB_CALCIO)
            match_found = df_calcio[df_calcio['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY', 'POSTPONED']) & 
                            (df_calcio['HomeTeam'].str.contains(search_query, case=False, na=False) | 
                             df_calcio['AwayTeam'].str.contains(search_query, case=False, na=False))]
            if not match_found.empty:
                st.session_state['current_match'] = match_found.iloc[0].to_dict()
            else:
                st.session_state['current_match'] = None
                st.warning("Nessun match trovato.")

    if 'current_match' in st.session_state and st.session_state['current_match'] is not None:
        m = st.session_state['current_match']
        casa, fuori, mid = str(m['HomeTeam']), str(m['AwayTeam']), m.get('ID', "N/A")
        st.markdown(f"<h2 style='text-align: center;'>🏟️ {casa} vs {fuori}</h2>", unsafe_allow_html=True)

        # UI Visualizzazione (Qui puoi rimettere i tuoi riquadri colorati)
        st.subheader("Pronostici Generati")
        col_1, col_2, col_3 = st.columns(3)
        col_1.metric("1X2 Consigliato", "1")
        col_2.metric("U/O 2.5 Consigliato", "OVER 2.5")
        col_3.metric("G/NG Consigliato", "GOL")

        # Prepariamo i dati PULITI per il DB
        res_1x2 = "1"
        res_uo = "OVER 2.5"
        res_gng = "GOL"
        res_sgf = "3, 2, 4"
        res_sgc = "2, 1"
        res_sgo = "1, 0"
        res_re_f = "1-1, 2-1, 1-0, 2-0, 1-2, 0-0"
        res_re_p = "0-0, 1-0, 0-1"

        if st.button("💾 Salva in Cronologia"):
            if salva_completo_in_locale(f"{casa} vs {fuori}", 85, 92, res_1x2, res_uo, res_gng, res_sgf, res_sgc, res_sgo, res_re_f, res_re_p, mid):
                st.success("✅ Salvato con successo! Vai in Cronologia per verificare.")
                time.sleep(1)
                st.rerun()

with tab2:
    st.subheader("📊 Archivio e Verifica Risultati")
    
    if st.button("🔄 Verifica Risultati Reali (Aggiorna Verde)"):
        with st.spinner("Connessione all'API in corso..."):
            aggiorna_risultati_da_api()
        st.rerun()

    if os.path.exists(FILE_DB_PRONOSTICI):
        df_p = pd.read_csv(FILE_DB_PRONOSTICI)
        if not df_p.empty:
            # Applichiamo la colorazione cella per cella
            styled_df = df_p.iloc[::-1].style.apply(highlight_winners, axis=1)
            st.dataframe(styled_df, use_container_width=True)
            
            if st.button("🗑️ Svuota Tutto"):
                st.session_state['confirm_delete'] = True
            
            if st.session_state.get('confirm_delete'):
                st.warning("Sei sicuro?")
                if st.button("✅ SÌ, CANCELLA"):
                    os.remove(FILE_DB_PRONOSTICI)
                    st.session_state['confirm_delete'] = False
                    st.rerun()
        else:
            st.info("La cronologia è vuota.")
