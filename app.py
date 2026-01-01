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

LEAGUE_MAP = {
    'SA': 'Serie A', 'PL': 'Premier League', 'ELC': 'Championship',
    'PD': 'La Liga', 'BL1': 'Bundesliga', 'FL1': 'Ligue 1',
    'CL': 'UEFA Champions League', 'PPL': 'Primeira Liga', 'DED': 'Eredivisie',
    'BSA': 'Serie A Brasile', 'EC': 'UEFA Europa League', 'WC': 'FIFA World Cup'
}

if os.path.exists("banner.png"):
    st.image("banner.png", use_container_width=True)
else:
    st.markdown("<h1 style='text-align: center;'>⚽ Delphi Predictor Pro</h1>", unsafe_allow_html=True)

API_TOKEN = 'c7a609a0580f4200add2751d787b3c68'
FILE_DB_CALCIO = 'database_pro_2025.csv'
FILE_DB_PRONOSTICI = 'database_pronostici.csv'

# --- 2. FUNZIONI LOGICHE ---
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

def inizializza_db():
    if not os.path.exists(FILE_DB_PRONOSTICI):
        columns = ["Data", "Ora", "Partita", "Fiducia", "Affidabilità", "1X2", "U/O 2.5", "G/NG", "SGF", "SGC", "SGO", "Top 6 RE Finali", "Top 3 RE 1°T", "Fatica", "Match_ID", "Risultato_Reale", "PT_Reale"]
        pd.DataFrame(columns=columns).to_csv(FILE_DB_PRONOSTICI, index=False)

inizializza_db()

def salva_completo_in_locale(data_dict):
    try:
        df = pd.read_csv(FILE_DB_PRONOSTICI)
        nuova_riga = {col: data_dict.get(col, "N/D") for col in df.columns}
        df = pd.concat([df, pd.DataFrame([nuova_riga])], ignore_index=True)
        df.to_csv(FILE_DB_PRONOSTICI, index=False)
        return True
    except Exception as e:
        st.error(f"Errore salvataggio: {e}")
        return False

def calcola_trend_forma(df_giocate, squadra):
    ultime = df_giocate[(df_giocate['HomeTeam'] == squadra) | (df_giocate['AwayTeam'] == squadra)].tail(4)
    if ultime.empty: return "N.D.", 1.0
    punti = 0
    trend = []
    for _, r in ultime.iterrows():
        is_home = r['HomeTeam'] == squadra
        fatti = r['FTHG'] if is_home else r['FTAG']
        subiti = r['FTAG'] if is_home else r['FTHG']
        if fatti > subiti: punti += 3; trend.append("🟢")
        elif fatti == subiti: punti += 1; trend.append("🟡")
        else: trend.append("🔴")
    moltiplicatore = round(0.8 + (punti / 12) * 0.4, 2)
    return "".join(trend), moltiplicatore

def analizza_severita_arbitro(df, nome_arbitro):
    if not nome_arbitro or nome_arbitro == 'N.D.' or df.empty: return 1.0
    try:
        partite = df[df['Referee'].str.contains(str(nome_arbitro), na=False, case=False)]
        if len(partite) < 3: return 1.0
        media_tot = (df['FTHG'] + df['FTAG']).mean()
        media_arb = (partite['FTHG'] + partite['FTAG']).mean()
        return round(max(0.8, min(1.3, media_tot / media_arb)), 2)
    except: return 1.0

def controlla_fatica(df, squadra, data_match_str):
    try:
        data_m = pd.to_datetime(data_match_str, dayfirst=True).normalize()
        storico = df[(df['Status'] == 'FINISHED') & ((df['HomeTeam'] == squadra) | (df['AwayTeam'] == squadra))].copy()
        if storico.empty: return False
        storico['Date_dt'] = pd.to_datetime(storico['Date'], utc=True).dt.tz_localize(None).dt.normalize()
        ultima_partita = storico[storico['Date_dt'] < data_m]['Date_dt'].max()
        if pd.notnull(ultima_partita):
            return (data_m - ultima_partita).days <= 3
    except: pass
    return False

def stima_quota(prob):
    return round(1 / prob, 2) if prob > 0.001 else 99.00

def poisson_probability(actual, average):
    average = max(0.01, average)
    return (math.pow(average, actual) * math.exp(-average)) / math.factorial(actual)

# --- 5. LOGICA ANALISI ---
def esegui_analisi(nome_input):
    if not os.path.exists(FILE_DB_CALCIO): return None
    df = pd.read_csv(FILE_DB_CALCIO)
    df['Date'] = pd.to_datetime(df['Date'], utc=True)
    today = pd.Timestamp.now(tz='UTC').normalize()

    future = df[(df['Status'] != 'FINISHED') & (df['HomeTeam'].str.contains(nome_input, case=False) | df['AwayTeam'].str.contains(nome_input, case=False)) & (df['Date'] >= today)].sort_values('Date')
    if future.empty: return None

    m = future.iloc[0]
    casa, fuori = m['HomeTeam'], m['AwayTeam']
    giocate = df[df['Status'] == 'FINISHED'].copy()
    avg_g = max(1.1, pd.to_numeric(giocate['FTHG'], errors='coerce').mean())
    molt_arbitro = analizza_severita_arbitro(giocate, str(m.get('Referee', 'N.D.')))

    def get_stats_specifiche(team, is_home):
        t = giocate[(giocate['HomeTeam'] == team) | (giocate['AwayTeam'] == team)].tail(15)
        if t.empty: return 1.2, 1.2
        s = t[t['HomeTeam'] == team] if is_home else t[t['AwayTeam'] == team]
        if not s.empty:
            gf = s['FTHG'].mean() if is_home else s['FTAG'].mean()
            gs = s['FTAG'].mean() if is_home else s['FTHG'].mean()
        else:
            gf = t.apply(lambda r: r['FTHG'] if r['HomeTeam']==team else r['FTAG'], axis=1).mean()
            gs = t.apply(lambda r: r['FTAG'] if r['HomeTeam']==team else r['FTHG'], axis=1).mean()
        return max(0.4, gf), max(0.4, gs)

    att_h, dif_h = get_stats_specifiche(casa, True)
    att_a, dif_a = get_stats_specifiche(fuori, False)
    trend_h, molt_h = calcola_trend_forma(giocate, casa)
    trend_a, molt_a = calcola_trend_forma(giocate, fuori)

    exp_h = (att_h * dif_a / avg_g) * molt_h * (2 - molt_arbitro)
    exp_a = (att_a * dif_h / avg_g) * molt_a * (2 - molt_arbitro)

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
            sgf[i+j] += prob; sgc[i] += prob; sgo[j] += prob
            re_fin.append({'s': f"{i}-{j}", 'p': prob})

    p1, px, p2, pu, pg = p1/tot, px/tot, p2/tot, pu/tot, pg/tot
    
    dt_ita = pd.to_datetime(m['Date'], utc=True).astimezone(pytz.timezone('Europe/Rome'))

    return {
        "Data": dt_ita.strftime("%d/%m/%Y"), "Ora": dt_ita.strftime("%H:%M"),
        "League": LEAGUE_MAP.get(m['League'], m['League']), "Partita": f"{casa} vs {fuori}",
        "Fiducia": f"{int(max(p1,px,p2)*100)}%", "Affidabilità": f"{85 + int(molt_arbitro*2)}%",
        "1X2": "1" if p1>px and p1>p2 else ("X" if px>p1 and px>p2 else "2"),
        "U/O 2.5": "OVER 2.5" if (1-pu)>0.5 else "UNDER 2.5", "G/NG": "GOL" if pg>0.5 else "NO GOL",
        "Trend_Casa": trend_h, "Trend_Fuori": trend_a, "Forma_H": molt_h, "Forma_A": molt_a,
        "SGF": ", ".join([f"{k} (Q: {stima_quota(v):.2f})" for k,v in sorted(sgf.items(), key=lambda x:x[1], reverse=True)[:3]]),
        "SGC": ", ".join([f"{k} (Q: {stima_quota(v):.2f})" for k,v in sorted(sgc.items(), key=lambda x:x[1], reverse=True)[:2]]),
        "SGO": ", ".join([f"{k} (Q: {stima_quota(v):.2f})" for k,v in sorted(sgo.items(), key=lambda x:x[1], reverse=True)[:2]]),
        "Top 6 RE Finali": ", ".join([f"{v['s']} (Q: {stima_quota(v['p']):.2f})" for v in sorted(re_fin, key=lambda x:x['p'], reverse=True)[:6]]),
        "Top 3 RE 1°T": ", ".join([f"{v['s']} (Q: {stima_quota(v['p']):.2f})" for v in sorted([{'s':f"{i}-{j}", 'p':poisson_probability(i,exp_h*0.42)*poisson_probability(j,exp_a*0.42)} for i in range(3) for j in range(3)], key=lambda x:x['p'], reverse=True)[:3]]),
        "Match_ID": m['ID'], "lg": round(((len(casa)+len(fuori))%10)*0.1+0.5, 2), "p1": p1, "px": px, "p2": p2, "pu": pu, "pg": pg, "arbitro": str(m.get('Referee', 'N.D.')), "molt_arbitro": molt_arbitro
    }

# --- 7. UI INTERFACE ---
tab1, tab2, tab3 = st.tabs(["🎯 Analisi", "⚙️ Database", "📜 Cronologia"])

with tab1:
    sq = st.text_input("Inserisci Squadra:")
    if st.button("Pronostici Match", type="primary") and sq:
        st.session_state['pronostico_corrente'] = esegui_analisi(sq)

    if st.session_state.get('pronostico_corrente'):
        d = st.session_state['pronostico_corrente']
        casa_n, fuori_n = d['Partita'].split(" vs ")
        df_c = pd.read_csv(FILE_DB_CALCIO)
        
        st.header(f"🏟️ {d['Partita']}")
        st.subheader(f"🏆 {d['League']} | 📅 {d['Data']} {d['Ora']}")
        
        c_tr1, c_tr2 = st.columns(2)
        with c_tr1: st.markdown(f"**Forma {casa_n}:** {d['Trend_Casa']}"); st.caption(f"Incidenza: {d['Forma_H']}x")
        with c_tr2: st.markdown(f"**Forma {fuori_n}:** {d['Trend_Fuori']}"); st.caption(f"Incidenza: {d['Forma_A']}x")

        f_casa = controlla_fatica(df_c, casa_n, d['Data'])
        f_fuori = controlla_fatica(df_c, fuori_n, d['Data'])
        if f_casa or f_fuori:
            st.error(f"⚠️ **ALLERTA STANCHEZZA**: {'Casa' if f_casa else ''} {'Fuori' if f_fuori else ''} ha giocato meno di 72h fa!")

        st.divider()
        c1, cx, c2 = st.columns(3)
        c1.metric("1 (Casa)", f"{d['p1']:.1%}", f"Q: {stima_quota(d['p1'])}")
        cx.metric("X (Pareggio)", f"{d['px']:.1%}", f"Q: {stima_quota(d['px'])}")
        c2.metric("2 (Ospite)", f"{d['p2']:.1%}", f"Q: {stima_quota(d['p2'])}")

        st.divider()
        col_uo, col_gng = st.columns(2)
        col_uo.warning(f"**U/O 2.5**: Under {d['pu']:.1%} (Q:{stima_quota(d['pu'])}) | Over {1-d['pu']:.1%}")
        col_gng.warning(f"**G/NG**: Gol {d['pg']:.1%} (Q:{stima_quota(d['pg'])}) | NoGol {1-d['pg']:.1%}")

        st.error(f"🎯 **Somma Gol**: {d['SGF']} | 🏠 {d['SGC']} | 🚀 {d['SGO']}")
        st.success(f"🏁 **Risultati Esatti**: {d['Top 6 RE Finali']}")

        if st.button("💾 Salva in Cronologia", use_container_width=True):
            import re
            save_data = d.copy()
            save_data["Fatica"] = "Entrambe" if (f_casa and f_fuori) else (f"Solo {casa_n}" if f_casa else (f"Solo {fuori_n}" if f_fuori else "No"))
            for k in ["SGF", "SGC", "SGO", "Top 6 RE Finali", "Top 3 RE 1°T"]:
                save_data[k] = re.sub(r'\s\(Q:\s\d+\.\d+\)', '', str(save_data[k]))
            if salva_completo_in_locale(save_data):
                st.success("✅ Salvato!"); time.sleep(1); st.rerun()

# (Le parti Database e Cronologia rimangono strutturalmente invariate come nel tuo script originale)
