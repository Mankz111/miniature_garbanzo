import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
from sqlalchemy import text

# 1. Proteção de Acesso
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    st.title("Acesso Restrito")
    password = st.text_input("Palavra-passe", type="password")
    if st.button("Entrar"):
        if password == st.secrets["auth"]["password"]:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Palavra-passe incorreta")
    return False

if not check_password():
    st.stop()

# 2. Ligação ao Neon (PostgreSQL)
conn = st.connection("postgresql", type="sql")

def create_tables():
    with conn.session as s:
        # Tabela de Musculação
        s.execute(text('''
            CREATE TABLE IF NOT EXISTS lifts (
                id SERIAL PRIMARY KEY,
                data DATE,
                exercicio TEXT,
                peso REAL,
                series INTEGER,
                reps INTEGER,
                rpe INTEGER
            )
        '''))
        # Tabela de Nomes
        s.execute(text('''
            CREATE TABLE IF NOT EXISTS nomes_exercicios (
                id SERIAL PRIMARY KEY,
                nome TEXT UNIQUE
            )
        '''))
        # Tabela de Corrida
        s.execute(text('''
            CREATE TABLE IF NOT EXISTS corridas_intervaladas (
                id SERIAL PRIMARY KEY,
                data DATE,
                series INTEGER,
                tempo_corrida_seg INTEGER,
                velocidade_kmh REAL,
                distancia_estimada_m REAL,
                descanso_seg INTEGER,
                rpe INTEGER
            )
        '''))
        s.commit()

create_tables()

def get_exercicios():
    # Busca nomes na tabela de definições e nomes já usados
    nomes_fixos = conn.query("SELECT nome FROM nomes_exercicios", ttl=0)
    lista_fixos = nomes_fixos["nome"].tolist() if not nomes_fixos.empty else []
    
    nomes_treinados = conn.query("SELECT DISTINCT exercicio FROM lifts WHERE peso > 0", ttl=0)
    lista_treinados = nomes_treinados["exercicio"].tolist() if not nomes_treinados.empty else []
    
    exercicios_base = ["Bench Press", "Squat", "Deadlift"]
    todos = list(set(exercicios_base + lista_fixos + lista_treinados))
    todos.sort()
    return todos

# 3. Interface Principal
st.title("Tracker de Treino: Força e Corrida")

tab_forca, tab_corrida, tab_consistencia = st.tabs(["Musculação", "Corrida Intervalada", "Consistência"])

# --- SECÇÃO DE MUSCULAÇÃO ---
with tab_forca:
    with st.expander("Gerir Lista de Exercícios"):
        novo_ex_nome = st.text_input("Novo nome de exercício")
        if st.button("Adicionar à Lista"):
            if novo_ex_nome.strip():
                try:
                    with conn.session as s:
                        s.execute(text("INSERT INTO nomes_exercicios (nome) VALUES (:nome)"), 
                                 {"nome": novo_ex_nome.strip()})
                        s.commit()
                    st.success(f"'{novo_ex_nome}' adicionado.")
                    st.rerun()
                except:
                    st.info("Esse exercício já existe na lista.")

    st.divider()
    st.header("Registar Novo Treino")
    ex_list = get_exercicios()
    
    with st.form("form_forca", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            d_forca = st.date_input("Data", date.today(), key="d_f")
            ex_sel = st.selectbox("Exercício", ex_list)
            peso = st.number_input("Peso (kg)", min_value=0.0, step=0.5)
        with col2:
            s_f = st.number_input("Séries", min_value=1, value=3)
            r_f = st.number_input("Repetições", min_value=1, value=10)
            rpe_f = st.slider("RPE (1-10)", 1, 10, 8, key="rpe_f_new")
        
        if st.form_submit_button("Guardar Treino"):
            if ex_sel:
                with conn.session as s:
                    s.execute(text("""
                        INSERT INTO lifts (data, exercicio, peso, series, reps, rpe) 
                        VALUES (:d, :e, :p, :s, :r, :rpe)
                    """), {"d": d_forca, "e": ex_sel, "p": peso, "s": s_f, "r": r_f, "rpe": rpe_f})
                    s.commit()
                st.success("Treino guardado")
                st.rerun()

    st.divider()
    df_l = conn.query("SELECT * FROM lifts WHERE peso > 0", ttl=0)
    
    if not df_l.empty:
        df_l['data'] = pd.to_datetime(df_l['data'])
        df_l['volume'] = df_l['peso'] * df_l['series'] * df_l['reps']
        vol_total = df_l[df_l['data'].dt.year == date.today().year]['volume'].sum()
        st.metric(f"Total Levantado ({date.today().year})", f"{vol_total/1000:.2f} Ton" if vol_total > 1000 else f"{vol_total} kg")
        
        fig_l = px.line(df_l.sort_values('data'), x='data', y='peso', color='exercicio', markers=True)
        st.plotly_chart(fig_l, use_container_width=True)
        
        st.subheader("Histórico")
        st.dataframe(df_l[['id', 'data', 'exercicio', 'peso', 'series', 'reps', 'rpe', 'volume']].sort_values('data', ascending=False), 
                     use_container_width=True, hide_index=True)

        with st.expander("Remover Registo de Força"):
            id_remover = st.number_input("ID do treino a remover", min_value=0, step=1, key="del_f")
            if st.button("Confirmar Eliminação", type="primary"):
                with conn.session as s:
                    s.execute(text("DELETE FROM lifts WHERE id = :id"), {"id": id_remover})
                    s.commit()
                st.rerun()

# --- SECÇÃO DE CORRIDA ---
with tab_corrida:
    st.header("Registar Treino (Tempo e Velocidade)")
    with st.form("form_corrida", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            d_c = st.date_input("Data", date.today(), key="d_c")
            n_s = st.number_input("Número de Séries", min_value=1, value=5)
            cm, cs = st.columns(2)
            min_c = cm.number_input("Minutos", 0, 59, 1)
            seg_c = cs.number_input("Segundos", 0, 59, 30)
        with c2:
            vel = st.number_input("Velocidade (km/h)", 1.0, 25.0, 10.5, step=0.1)
            desc = st.number_input("Descanso (segundos)", 0, 600, 30)
            rpe_c = st.slider("RPE", 1, 10, 8, key="rpe_c")
            
        t_seg = (min_c * 60) + seg_c
        dist_m = (vel / 3.6) * t_seg
        pace_dec = 60 / vel
        st.info(f"Cada série percorre {dist_m:.0f} metros (Pace: {int(pace_dec)}:{int((pace_dec%1)*60):02d} min/km)")

        if st.form_submit_button("Guardar Treino"):
            with conn.session as s:
                s.execute(text("""
                    INSERT INTO corridas_intervaladas 
                    (data, series, tempo_corrida_seg, velocidade_kmh, distancia_estimada_m, descanso_seg, rpe) 
                    VALUES (:d, :s, :t, :v, :dist, :desc, :rpe)
                """), {"d": d_c, "s": n_s, "t": t_seg, "v": vel, "dist": dist_m, "desc": desc, "rpe": rpe_c})
                s.commit()
            st.success("Corrida guardada")
            st.rerun()

    st.divider()
    df_r = conn.query("SELECT * FROM corridas_intervaladas", ttl=0)
    if not df_r.empty:
        df_r['data'] = pd.to_datetime(df_r['data'])
        df_r['dist_total_km'] = (df_r['series'] * df_r['distancia_estimada_m']) / 1000
        st.metric(f"Distância Total ({date.today().year})", f"{df_r[df_r['data'].dt.year == date.today().year]['dist_total_km'].sum():.2f} km")
        fig_r = px.line(df_r.sort_values('data'), x='data', y='velocidade_kmh', markers=True)
        st.plotly_chart(fig_r, use_container_width=True)
        df_r['Tempo/Série'] = df_r['tempo_corrida_seg'].apply(lambda x: f"{int(x//60)}:{int(x%60):02d}")
        st.dataframe(df_r[['id', 'data', 'series', 'Tempo/Série', 'velocidade_kmh', 'descanso_seg', 'rpe']], use_container_width=True, hide_index=True)

        with st.expander("Remover Registo de Corrida"):
            id_c_rem = st.number_input("ID da corrida a remover", min_value=0, step=1, key="del_c")
            if st.button("Eliminar Corrida", type="primary"):
                with conn.session as s:
                    s.execute(text("DELETE FROM corridas_intervaladas WHERE id = :id"), {"id": id_c_rem})
                    s.commit()
                st.rerun()

# --- SECÇÃO DE CONSISTÊNCIA ---
with tab_consistencia:
    with tab_consistencia:
    st.header("Consistência de Treino")
    # REMOVIDO o text() - Passamos apenas a string
    q = "SELECT data FROM lifts WHERE peso > 0 UNION SELECT data FROM corridas_intervaladas"
    df_d = conn.query(q, ttl=0)
    
    if not df_d.empty:
        df_d['data'] = pd.to_datetime(df_d['data'])
        df_d['treinou'] = 1
        ano = date.today().year
        df_cal = pd.DataFrame({"data": pd.date_range(date(ano, 1, 1), date(ano, 12, 31))})
        df_cal = pd.merge(df_cal, df_d, on='data', how='left').fillna(0)
        
        fig_cal = go.Figure(data=go.Heatmap(
            z=df_cal['treinou'], x=df_cal['data'].dt.isocalendar().week, y=df_cal['data'].dt.dayofweek,
            colorscale=[[0, '#ebedf0'], [1, '#216e39']], showscale=False, xgap=4, ygap=4,
            hovertext=df_cal['data'].dt.strftime('%d %b (%a)'), hoverinfo="text"
        ))
        fig_cal.update_layout(
            height=280, margin=dict(t=40, b=10, l=40, r=10),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            yaxis=dict(tickvals=[0,1,2,3,4,5,6], ticktext=['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'], 
                       autorange='reversed', fixedrange=True, showgrid=False, zeroline=False, scaleanchor="x", scaleratio=1),
            xaxis=dict(tickvals=[1,5,9,14,18,22,27,31,36,40,44,48], 
                       ticktext=['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'],
                       range=[1, 53], fixedrange=True, showgrid=False, zeroline=False, side='top')
        )
        st.plotly_chart(fig_cal, use_container_width=True, config={'displayModeBar': False})
    else:
        st.info("Ainda não existem treinos registados.")
