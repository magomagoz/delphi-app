import streamlit as st
import pandas as pd
import math
import requests
import os
import time
from datetime import datetime
import pytz
from streamlit_gsheets import GSheetsConnection

# 1. FUNZIONI MATEMATICHE (Sempre in alto)
def poisson_probability(k, exp):
    if exp <= 0: return 0
    return (exp**k * math.exp(-exp)) / math.factorial(k)

def stima_quota(prob):
    if prob <= 0.001: return 99.00
    return round(1 / prob, 2)

# 2. CONNESSIONE GOOGLE SHEETS
try:
    secrets_dict = st.secrets["connections"]["gsheets"]
    conn = st.connection("gsheets", type=GSheetsConnection, **secrets_dict)
except Exception as e:
    st.error("Errore configurazione Secrets/Google Sheets")

# 3. ALTRE FUNZIONI DI LOGICA
def analizza_severita_arbitro(df, nome_arbitro):
    if not nome_arbitro or nome_arbitro == 'N.D.' or df.empty: return 1.0
    partite_arbitro = df[df['Referee'].astype(str).str.contains(str(nome_arbitro), na=False, case=False)]
    if len(partite_arbitro) < 2: return 1.0
    media_gol_arbitro = (partite_arbitro['FTHG'] + partite_arbitro['FTAG']).mean()
    media_gol_totale = (df['FTHG'] + df['FTAG']).mean()
    return round(max(0.8, min(1.3, media_gol_totale / media_gol_arbitro)), 2)

def calcola_late_goal_index(casa, fuori):
    val = (len(casa) + len(fuori)) % 15
    return round(val * 0.12, 2)

def salva_in_cronologia(match, lg_idx, fiducia, dati):
    try:
        existing_data = conn.read(worksheet="Foglio1", ttl=5)
        nuova_riga = pd.DataFrame([{
            "Data": datetime.now().strftime("%d/%m/%Y"),
            "Ora": datetime.now().strftime("%H:%M"),
            "Partita": match,
            "Indice LG": lg_idx,
            "Fiducia": fiducia,
            "Dati": dati
        }])
        updated_df = pd.concat([existing_data, nuova_riga], ignore_index=True)
        conn.update(worksheet="Foglio1", data=updated_df)
        st.success("✅ Salvato in cronologia!")
    except:
        st.warning("Impossibile salvare su Google Sheets")

# 4. ANALISI PRINCIPALE
def calcola_pronostico_streamlit(nome_input):
    FILE_DB = 'database_pro_2025.csv'
    if not os.path.exists(FILE_DB):
        st.error("Database non trovato."); return
    
    df = pd.read_csv(FILE_DB)
    match = df[df['Status'].isin(['TIMED', 'SCHEDULED', 'LIVE', 'IN_PLAY']) & 
               (df['HomeTeam'].str.contains(nome_input, case=False, na=False) | 
                df['AwayTeam'].str.contains(nome_input, case=False, na=False))]
    
    if match.empty:
        st.warning(f"Nessun match trovato per '{nome_input}'"); return

    m = match.iloc[0]
    casa, fuori = m['HomeTeam'], m['AwayTeam']
    giocate = df[df['Status'] == 'FINISHED'].copy()
    arbitro = m.get('Referee', 'N.D.')
    molt_arbitro = analizza_severita_arbitro(giocate, arbitro)
    
    # Poisson Stats
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

    # UI RENDERING - BADGES DINAMICI
    st.header(f"🏟️ {casa} vs {fuori}")
    
    fiducia_val = 85 # Qui puoi mettere la tua logica di calcolo
    affidabilita_val = 90
    
    col_fid, col_aff = st.columns(2)
    with col_fid:
        st.markdown(f"""<div style="background-color: #1E7E34; color: white; padding: 10px; border-radius: 10px; text-align: center;">
        <p style="margin:0; font-size: 12px; opacity: 0.8;">🎯 FIDUCIA</p>
        <p style="margin:0; font-size: 20px; font-weight: bold;">{fiducia_val}%</p></div>""", unsafe_allow_html=True)
    with col_aff:
        st.markdown(f"""<div style="background-color: #1C3D5A; color: white; padding: 10px; border-radius: 10px; text-align: center;">
        <p style="margin:0; font-size: 12px; opacity: 0.8;">📊 DATI</p>
        <p style="margin:0; font-size: 20px; font-weight: bold;">{affidabilita_val}%</p></div>""", unsafe_allow_html=True)

    # --- CALCOLO 1X2 ---
    st.divider()
    p_1, p_x, p_2, total_p = 0, 0, 0, 0
    for i in range(7):
        for j in range(7):
            prob = poisson_probability(i, exp_h) * poisson_probability(j, exp_a)
            total_p += prob
            if i > j: p_1 += prob
            elif i == j: p_x += prob
            else: p_2 += prob

    c1, cx, c2 = st.columns(3)
    with c1: st.info(f"1: {p_1/total_p:.1%}")
    with cx: st.info(f"X: {p_x/total_p:.1%}")
    with c2: st.info(f"2: {p_2/total_p:.1%}")

    # SALVATAGGIO AUTOMATICO
    salva_in_cronologia(f"{casa}-{fuori}", calcola_late_goal_index(casa, fuori), fiducia_val, affidabilita_val)

# 5. INTERFACCIA MAIN
st.image("banner.png")
tab_analisi, tab_gestione = st.tabs(["🎯 Analisi", "⚙️ Gestione"])

with tab_analisi:
    search_query = st.text_input("Squadra:")
    if st.button("Analizza"):
        if search_query: calcola_pronostico_streamlit(search_query)
    
    st.divider()
    if st.checkbox("Mostra Cronologia"):
        st.dataframe(conn.read(worksheet="Foglio1").tail(10))

with tab_gestione:
    if st.button("Aggiorna Database"):
        # Qui va la tua funzione aggiorna_con_api()
        st.write("Funzione aggiornamento...")
