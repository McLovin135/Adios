import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import re
from collections import Counter
import io
import textwrap

st.set_page_config(page_title="Encuesta Redes - Visualizador", layout="wide")
st.title("Encuesta uso de redes sociales — Cargar archivo (Forms)")

def can_read_excel():
    try:
        import openpyxl
        return True
    except Exception:
        return False

def read_table(uploaded):
    name = getattr(uploaded, "name", "")
    if name.lower().endswith((".xls", ".xlsx")):
        if not can_read_excel():
            raise RuntimeError("Para leer .xlsx instala openpyxl en el venv: pip install openpyxl")
        return pd.read_excel(uploaded, engine="openpyxl")
    else:
        return pd.read_csv(uploaded)

def parse_redes_rank(s):
    if pd.isna(s): return []
    return [x.strip() for x in str(s).split(';') if x.strip()]

def parse_tipo_uso(s):
    if pd.isna(s): return []
    return [x.strip().lower() for x in str(s).replace(';',',').split(',') if x.strip()]

def parse_hours_text(txt):
    if pd.isna(txt): return None
    s = str(txt).lower()
    m = re.search(r'(\d+(\.\d+)?)', s)
    if not m:
        return None
    val = float(m.group(1))
    if 'semana' in s or '/sem' in s:
        return val/7.0
    if 'mes' in s or '/mes' in s:
        return val/30.0
    return val

def auto_map_columns(cols):
    cols_lower = [c.lower() for c in cols]
    def find_any(keywords):
        for i,c in enumerate(cols_lower):
            for kw in keywords:
                if kw in c:
                    return cols[i]
        return None
    mapping = {}
    mapping['facultad'] = find_any(['facultad','¿a qué facultad','faculty','carrera'])
    redes = None
    for i,c in enumerate(cols_lower):
        if ('redes' in c or 'red social' in c or 'qué redes' in c or 'qué redes sociales' in c) and ('ia' not in c and 'intelig' not in c):
            redes = cols[i]; break
    if not redes:
        redes = find_any(['red','plataforma','plataform','social'])
    mapping['redes_rank'] = redes
    mapping['horas_dia'] = find_any(['horas/dia','horas_dia','hours per day','horas por dia'])
    mapping['horas_semana'] = find_any(['horas/semana','horas_semana','hours per week','semana'])
    mapping['horas_mes'] = find_any(['horas/mes','horas_mes','hours per month','mes'])
    mapping['tipo_uso'] = find_any(['tipo uso','propósito','proposito','para','uso'])
    puntos = [c for c in cols if c.strip().lower().startswith('puntos') or c.strip().lower().startswith('puntos:')]
    ia = None
    impacto = None
    for p in puntos:
        pl = p.lower()
        if 'ia' in pl or 'inteligencia' in pl:
            ia = p
        if 'emocion' in pl or 'impact' in pl or 'afect' in pl:
            impacto = p
    if not ia:
        ia = find_any(['ia','inteligencia','ai'])
    if not impacto:
        impacto = find_any(['impact','emocion','emocional','afecto'])
    mapping['ia_uso'] = ia
    mapping['impacto_emocional'] = impacto
    return mapping

def build_normalized(df_raw, mapping):
    df = df_raw.copy()
    df_norm = pd.DataFrame()
    if mapping.get('facultad'):
        df_norm['facultad'] = df[mapping['facultad']].astype(str)
    else:
        df_norm['facultad'] = 'Sin especificar'
    df_norm['redes_rank'] = df[mapping['redes_rank']] if mapping.get('redes_rank') else ""
    df_norm['redes_parsed'] = df_norm['redes_rank'].apply(parse_redes_rank)
    df_norm['tipo_uso'] = df[mapping['tipo_uso']] if mapping.get('tipo_uso') else ""
    df_norm['tipo_parsed'] = df_norm['tipo_uso'].apply(parse_tipo_uso)
    if mapping.get('ia_uso'):
        df_norm['ia_uso'] = pd.to_numeric(df[mapping['ia_uso']], errors='coerce')
    else:
        df_norm['ia_uso'] = pd.NA
    if mapping.get('impacto_emocional'):
        df_norm['impacto_emocional'] = pd.to_numeric(df[mapping['impacto_emocional']], errors='coerce')
    else:
        df_norm['impacto_emocional'] = pd.NA
    def hours_from_row(row):
        for ckey in ['horas_dia','horas_semana','horas_mes']:
            colname = mapping.get(ckey)
            if colname and colname in row and not pd.isna(row[colname]):
                try:
                    val = float(row[colname])
                    if ckey=='horas_dia':
                        return val
                    if ckey=='horas_semana':
                        return val/7.0
                    if ckey=='horas_mes':
                        return val/30.0
                except:
                    parsed = parse_hours_text(row[colname]); 
                    if parsed is not None: return parsed
        for c in row.index:
            if 'hora' in c.lower() or 'tiempo' in c.lower() or 'promedio' in c.lower():
                parsed = parse_hours_text(row[c])
                if parsed is not None: return parsed
        return np.nan
    df_norm['horas_dia_norm'] = df.apply(hours_from_row, axis=1)
    df_out = pd.concat([df.reset_index(drop=True), df_norm.reset_index(drop=True)], axis=1)
    return df_out

def compute_aggregates(std_df):
    agg = {}
    redes_all = []
    redes_first = []
    for r in std_df['redes_parsed']:
        redes_all.extend(r)
        if r:
            redes_first.append(r[0])
    agg['redes_all_counts'] = dict(Counter(redes_all))
    agg['redes_first_counts'] = dict(Counter(redes_first))
    agg['hours_by_faculty'] = std_df.groupby(std_df['facultad'].fillna('Sin especificar'))['horas_dia_norm'].mean().fillna(0).to_dict()
    tipos = []
    for t in std_df['tipo_parsed']:
        tipos.extend(t)
    agg['tipo_uso_counts'] = dict(Counter(tipos))
    agg['ia_by_faculty'] = std_df.groupby(std_df['facultad'].fillna('Sin especificar'))['ia_uso'].mean().fillna(0).to_dict()
    agg['impacto_by_faculty'] = std_df.groupby(std_df['facultad'].fillna('Sin especificar'))['impacto_emocional'].mean().fillna(0).to_dict()
    return agg

uploaded = st.file_uploader("Sube archivo (CSV / Excel exportado desde Google Forms)", type=["csv","txt","xlsx","xls"])
if uploaded is None:
    st.stop()

try:
    df_raw = read_table(uploaded)
except RuntimeError as e:
    st.error(str(e))
    st.info("Instala openpyxl en tu venv: `pip install openpyxl`")
    st.stop()
except Exception as e:
    st.error(f"Error leyendo archivo: {e}")
    st.stop()

mapping = auto_map_columns(list(df_raw.columns))
std_df = build_normalized(df_raw, mapping)

st.sidebar.header("Filtros y opciones de gráfica")
facultades_fijas = ['Todos', 'Facultad de Sistemas', 'Facultad de Arquitectura', 'Facultad de Ingeniería', 'Facultad de Artes', 'Facultad de Música', 'No pertenezco a ninguna facultad', 'Otra']
fac_filter = st.sidebar.selectbox("Filtrar por facultad:", facultades_fijas)

redes_fijas = ['Todas', 'Facebook', 'Instagram', 'TikTok', 'X (Twitter)', 'YouTube', 'WhatsApp']
red_filter = st.sidebar.selectbox("Filtrar por red social (elige una):", redes_fijas)

chart_type = st.sidebar.selectbox("Tipo de gráfica:", ["Barras", "Pastel (pie)", "Líneas", "Dispersión", "Radar"])

df_filtered = std_df.copy()
if fac_filter != 'Todos':
    df_filtered = df_filtered[df_filtered['facultad'] == fac_filter]
if red_filter != 'Todas':
    df_filtered = df_filtered[df_filtered['redes_parsed'].apply(lambda lst: red_filter in lst)]

agg = compute_aggregates(df_filtered)

st.header("Resumen rápido")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Respuestas mostradas", len(df_filtered))
    st.write("Top redes (menciones totales)")
    if agg['redes_all_counts']:
        st.table(pd.Series(agg['redes_all_counts']).sort_values(ascending=False).head(8))
    else:
        st.write("Sin datos de redes")
with col2:
    st.write("Horas promedio (por facultad)")
    st.table(pd.Series(agg['hours_by_faculty']).sort_values(ascending=False))
with col3:
    st.write("Tipo de uso (top)")
    st.table(pd.Series(agg['tipo_uso_counts']).sort_values(ascending=False))

def plot_radar(ax, values, labels, title="", max_labels=8, wrap_width=20, show_yticks=True):
    if len(values) == 0:
        ax.text(0.5, 0.5, "No hay datos", horizontalalignment='center', verticalalignment='center')
        return
    labels = list(labels)[:max_labels]
    values = np.array(list(values)[:max_labels], dtype=float)
    labels_wrapped = [textwrap.fill(str(l), wrap_width) for l in labels]
    N = len(values)
    angles = np.linspace(0, 2*np.pi, N, endpoint=False).tolist()
    values = np.concatenate((values, [values[0]]))
    angles = np.concatenate((angles, [angles[0]]))
    ax.clear()
    ax.plot(angles, values, marker='o', linewidth=2)
    ax.fill(angles, values, alpha=0.25)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels_wrapped, fontsize=9)
    ax.tick_params(axis='x', pad=12)
    ax.set_rlabel_position(30)
    maxv = max(values) if max(values) > 0 else 1
    ax.set_ylim(0, maxv * 1.1)
    if show_yticks:
        ax.set_yticks(np.linspace(0, maxv, num=4))
        ax.set_yticklabels([f"{x:.2f}" for x in np.linspace(0, maxv, num=4)], fontsize=8)
    else:
        ax.set_yticklabels([])
    ax.set_title(title, y=1.08, fontsize=12)

if chart_type == "Radar":
    radar_choice = st.sidebar.selectbox("Serie para radar:", [
        "Frecuencia de redes (menciones totales)",
        "Preferencia: primer lugar",
        "Horas promedio por facultad",
        "Uso IA por facultad",
        "Impacto emocional por facultad",
        "Propósito principal (tipo de uso)"
    ])
    fig, ax = plt.subplots(figsize=(9,7), subplot_kw={'polar': True})
    if radar_choice == "Frecuencia de redes (menciones totales)":
        s = pd.Series(agg['redes_all_counts']).sort_values(ascending=False)
        plot_radar(ax, s.values, s.index, title="Frecuencia de redes (top)", max_labels=8, wrap_width=18)
    elif radar_choice == "Preferencia: primer lugar":
        s = pd.Series(agg['redes_first_counts']).sort_values(ascending=False)
        plot_radar(ax, s.values, s.index, title="Preferencia (primer lugar) - top", max_labels=8, wrap_width=18)
    elif radar_choice == "Horas promedio por facultad":
        s = pd.Series(agg['hours_by_faculty']).sort_values(ascending=False)
        plot_radar(ax, s.values, s.index, title="Horas promedio por facultad", max_labels=8, wrap_width=18)
    elif radar_choice == "Uso IA por facultad":
        s = pd.Series(agg['ia_by_faculty']).sort_values(ascending=False)
        plot_radar(ax, s.values, s.index, title="Uso IA por facultad (promedio)", max_labels=8, wrap_width=18)
    elif radar_choice == "Impacto emocional por facultad":
        s = pd.Series(agg['impacto_by_faculty']).sort_values(ascending=False)
        plot_radar(ax, s.values, s.index, title="Impacto emocional (promedio)", max_labels=8, wrap_width=18)
    else:
        s = pd.Series(agg['tipo_uso_counts']).sort_values(ascending=False)
        plot_radar(ax, s.values, s.index, title="Propósito principal (top)", max_labels=8, wrap_width=18)
else:
    s = pd.Series(agg['redes_all_counts']).sort_values(ascending=True)
    if s.size == 0:
        fig, ax = plt.subplots(figsize=(10,5))
        ax.text(0.5, 0.5, "No hay datos", horizontalalignment='center', verticalalignment='center')
    else:
        fig, ax = plt.subplots(figsize=(10,5))
        if chart_type == "Líneas":
            s.plot(ax=ax, marker='o')
            ax.set_xlabel("Redes"); ax.set_ylabel("Menciones")
            ax.set_title("Frecuencia de uso por red")
        elif chart_type == "Pastel (pie)":
            top = s.sort_values(ascending=False).head(8)
            ax.pie(top.values, labels=top.index, autopct='%1.1f%%', startangle=90)
            ax.axis('equal')
            ax.set_title("Frecuencia de uso por red (top)")
        elif chart_type == "Dispersión":
            numeric_cols = [c for c in std_df.columns if pd.api.types.is_numeric_dtype(std_df[c])]
            prefer_x = None; prefer_y = None
            lower_cols = [c.lower() for c in std_df.columns]
            for cand in ['seguidores','followers','ventas','sales']:
                if cand in lower_cols and prefer_x is None:
                    prefer_x = std_df.columns[lower_cols.index(cand)]
                elif cand in lower_cols and prefer_y is None:
                    prefer_y = std_df.columns[lower_cols.index(cand)]
            if not (prefer_x and prefer_y):
                if len(numeric_cols) >= 2:
                    prefer_x, prefer_y = numeric_cols[0], numeric_cols[1]
            if prefer_x and prefer_y:
                ax.scatter(std_df[prefer_x].fillna(0), std_df[prefer_y].fillna(0))
                ax.set_xlabel(prefer_x); ax.set_ylabel(prefer_y); ax.set_title(f"Dispersión: {prefer_x} vs {prefer_y}")
            else:
                fig, ax = plt.subplots(figsize=(10,5))
                ax.text(0.2, 0.5, "No hay datos numéricos para dispersión", fontsize=12)
        else:
            s.plot.barh(ax=ax)
            ax.set_xlabel("Menciones totales")
            ax.set_title("Frecuencia de uso por red")

plt.tight_layout()
st.pyplot(fig)

buf = io.BytesIO()
fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
buf.seek(0)
st.download_button("Descargar gráfica (PNG)", data=buf, file_name="grafica.png", mime="image/png")

buf2 = io.BytesIO()
fig.savefig(buf2, format='svg', bbox_inches='tight')
buf2.seek(0)
st.download_button("Descargar gráfica (SVG)", data=buf2, file_name="grafica.svg", mime="image/svg+xml")

st.header("Exportar")
aggs_df = pd.DataFrame({
    "facultad": list(agg['hours_by_faculty'].keys()),
    "horas_prom": list(agg['hours_by_faculty'].values()),
}).set_index("facultad")
ia_df = pd.Series(agg['ia_by_faculty'], name='ia_prom')
impacto_df = pd.Series(agg['impacto_by_faculty'], name='impacto_prom')
export_df = pd.concat([aggs_df, ia_df, impacto_df], axis=1).fillna(0).reset_index().rename(columns={'index':'facultad'})

st.download_button("Descargar agregados (CSV)", data=export_df.to_csv(index=False).encode('utf-8'), file_name="agregados_facultad.csv", mime="text/csv")
st.download_button("Descargar respuestas normalizadas (CSV)", data=std_df.to_csv(index=False).encode('utf-8'), file_name="respuestas_normalizadas.csv", mime="text/csv")

st.info("Filtros: usa el selector de facultad o de red para ver datos separados (p. ej. Facebook).")
