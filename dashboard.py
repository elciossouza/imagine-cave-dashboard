import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import gspread
from google.oauth2.service_account import Credentials
import numpy as np
import re
import logging

# ─────────────────────────────────────────────
# SEGURANÇA — logging server-side apenas
# ─────────────────────────────────────────────
logging.basicConfig(level=logging.ERROR, format="%(asctime)s [%(levelname)s] %(message)s")
_logger = logging.getLogger(__name__)

def _sanitize_error(err: Exception) -> str:
    raw = str(err)
    try:
        _sid = st.secrets.get("spreadsheet", {}).get("id", "")
        if _sid:
            raw = raw.replace(_sid, "***")
    except Exception:
        pass
    patterns = [
        (r"https?://[^\s]+", "[URL ocultada]"),
        (r"[a-zA-Z0-9_-]{20,}", "***"),
        (r"[\w.+-]+@[\w-]+\.[\w.]+", "[email ocultado]"),
    ]
    for pattern, replacement in patterns:
        raw = re.sub(pattern, replacement, raw)
    return raw

# ─────────────────────────────────────────────
# CONFIGURAÇÃO DA PÁGINA
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Imagine Cave | Dashboard",
    page_icon="🪩",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<meta name="referrer" content="no-referrer">
<meta http-equiv="X-Frame-Options" content="DENY">
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# MAPEAMENTO DE COLUNAS (nomes exatos da planilha)
# ─────────────────────────────────────────────
C = {
    "mes":     "Mes",
    "canal":   "Canal",
    "tipo":    "Tipo",
    "leads":   "Leads",
    "vendas":  "Vendas",
    "receita": "Receita_USD",
    "invest":  "Investimento_USD",
    "cpl":     "Custo_por_lead_CPL",
    "cpv":     "Custo_por_venda_CPV",
    "conv":    "Conversao_Leads_Vendas",
    "ticket":  "Ticket_medio",
    "roas":    "ROAS",
}

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Inter:wght@300;400;500&display=swap');
:root {
    --primary: #E040FB;
    --primary-dark: #AB00D6;
    --accent: #FF4081;
    --accent2: #7C4DFF;
    --bg-dark: #0A0010;
    --bg-card: #120020;
    --text-main: #F3E5F5;
    --text-muted: #9E7BB5;
    --border: rgba(224,64,251,0.18);
    --red: #FF4081;
    --green: #69FF47;
}
html, body, [class*="css"] { font-family: 'Inter', sans-serif; background-color: var(--bg-dark); color: var(--text-main); }
.stApp { background: radial-gradient(ellipse at top, #1a0030 0%, #0A0010 50%, #000510 100%); }
.dashboard-header { padding: 1.5rem 0 2rem 0; border-bottom: 1px solid var(--border); margin-bottom: 2rem; }
.brand-name { font-family: 'Rajdhani', sans-serif; font-size: 2.2rem; font-weight: 700; background: linear-gradient(90deg, #E040FB, #FF4081, #7C4DFF); -webkit-background-clip: text; -webkit-text-fill-color: transparent; letter-spacing: 2px; text-transform: uppercase; }
.brand-sub { font-size: 0.75rem; color: var(--text-muted); font-weight: 300; letter-spacing: 3px; text-transform: uppercase; margin-top: 2px; }
.kpi-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 1.4rem 1.6rem; position: relative; overflow: hidden; }
.kpi-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, #E040FB, #FF4081, #7C4DFF); border-radius: 16px 16px 0 0; }
.kpi-card::after { content: ''; position: absolute; top: -40px; right: -40px; width: 100px; height: 100px; background: radial-gradient(circle, rgba(224,64,251,0.08) 0%, transparent 70%); border-radius: 50%; }
.kpi-label { font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1.5px; font-weight: 500; margin-bottom: 0.5rem; }
.kpi-value { font-family: 'Rajdhani', sans-serif; font-size: 2rem; font-weight: 700; color: var(--text-main); line-height: 1; margin-bottom: 0.5rem; }
.kpi-delta { font-size: 0.78rem; font-weight: 500; }
.delta-up { color: var(--green); } .delta-down { color: var(--red); }
.insight-box { background: linear-gradient(135deg, rgba(224,64,251,0.07), rgba(124,77,255,0.05)); border: 1px solid rgba(224,64,251,0.2); border-left: 4px solid var(--primary); border-radius: 12px; padding: 1rem 1.4rem; margin: 1rem 0; font-size: 0.88rem; color: var(--text-muted); }
.insight-box strong { color: var(--primary); }
.section-title { font-family: 'Rajdhani', sans-serif; font-size: 1.2rem; font-weight: 700; color: var(--text-main); margin: 2rem 0 1rem 0; display: flex; align-items: center; gap: 10px; letter-spacing: 1px; text-transform: uppercase; }
.section-title::after { content: ''; flex: 1; height: 1px; background: var(--border); }
.stTabs [data-baseweb="tab-list"] { background: var(--bg-card); border-radius: 12px; padding: 4px; gap: 4px; border: 1px solid var(--border); }
.stTabs [data-baseweb="tab"] { font-family: 'Rajdhani', sans-serif; font-weight: 600; font-size: 0.9rem; color: var(--text-muted); border-radius: 8px; padding: 0.5rem 1.2rem; letter-spacing: 0.5px; }
.stTabs [aria-selected="true"] { background: linear-gradient(135deg, #E040FB, #7C4DFF) !important; color: white !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# TEMA PLOTLY
# ─────────────────────────────────────────────
PLOT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter", color="#9E7BB5"),
    xaxis=dict(gridcolor="rgba(224,64,251,0.08)", zerolinecolor="rgba(224,64,251,0.08)"),
    yaxis=dict(gridcolor="rgba(224,64,251,0.08)", zerolinecolor="rgba(224,64,251,0.08)"),
    margin=dict(l=10, r=10, t=40, b=10),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#9E7BB5")),
)
COLORS = ["#E040FB", "#FF4081", "#7C4DFF", "#69FF47", "#FF6D00", "#40C4FF", "#FFD740"]

# ─────────────────────────────────────────────
# GOOGLE SHEETS
# ─────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

@st.cache_data(ttl=300)
def load_sheet(sheet_name: str) -> pd.DataFrame:
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
        client = gspread.authorize(creds)
        sh = client.open_by_key(st.secrets["spreadsheet"]["id"])
        data = sh.worksheet(sheet_name).get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        _logger.error("Falha ao carregar '%s': %s", sheet_name, e)
        st.error(f"⚠️ Não foi possível carregar os dados ({sheet_name}).\n\n_Detalhe: {_sanitize_error(e)}_")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_vendas() -> pd.DataFrame:
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
        client = gspread.authorize(creds)
        sh = client.open_by_key(st.secrets["spreadsheet2"]["id"])
        ws = sh.get_worksheet(0)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        _logger.error("Falha ao carregar planilha de vendas: %s", e)
        st.error(f"⚠️ Não foi possível carregar os dados de vendas.\n\n_Detalhe: {_sanitize_error(e)}_")
        return pd.DataFrame()

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(
        s.astype(str).str.replace("$","",regex=False).str.replace("R$","",regex=False)
         .str.replace(".","",regex=False).str.replace(",",".",regex=False)
         .str.replace("%","",regex=False).str.strip(),
        errors="coerce").fillna(0)

def fmt_usd(v): return f"$ {v:,.2f}"
def fmt_pct(v): return f"{v:.1f}%"
def fmt_int(v): return f"{int(v):,}".replace(",", ".")
def fmt_x(v):   return f"{v:.2f}x"

def delta_html(cur, prv, inverse=False):
    if prv == 0: return ""
    diff = ((cur - prv) / abs(prv)) * 100
    up = (diff >= 0) if not inverse else (diff < 0)
    css = "delta-up" if up else "delta-down"
    arrow = "▲" if diff >= 0 else "▼"
    return f'<span class="kpi-delta {css}">{arrow} {abs(diff):.1f}% vs mês anterior</span>'

def kpi_card(label, value, delta="", icon=""):
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">{icon} {label}</div>'
                f'<div class="kpi-value">{value}</div>{delta}</div>', unsafe_allow_html=True)

def prep(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    if df.empty: return df
    for col in cols:
        if col in df.columns:
            df[col] = safe_num(df[col])
    return df

def calc_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula CPL, CPA, ROAS, Conversão e Ticket a partir das colunas base."""
    if df.empty: return df
    leads  = df[C["leads"]].where(df[C["leads"]]  > 0) if C["leads"]  in df.columns else pd.Series(np.nan, index=df.index)
    vendas = df[C["vendas"]].where(df[C["vendas"]] > 0) if C["vendas"] in df.columns else pd.Series(np.nan, index=df.index)
    rec    = df[C["receita"]] if C["receita"] in df.columns else pd.Series(0, index=df.index)
    inv    = df[C["invest"]].where(df[C["invest"]]  > 0) if C["invest"]  in df.columns else pd.Series(np.nan, index=df.index)
    df[C["cpl"]]    = (inv    / leads).fillna(0)
    df[C["cpv"]]    = (inv    / vendas).fillna(0)
    df[C["roas"]]   = (rec    / inv).fillna(0)
    df[C["conv"]]   = (df[C["vendas"]] / leads * 100).fillna(0) if C["vendas"] in df.columns else 0
    df[C["ticket"]] = (rec    / vendas).fillna(0)
    return df

def filt(df, month):
    if df.empty or not month or C["mes"] not in df.columns: return df
    return df[df[C["mes"]] == month]

def prev(df, month):
    if df.empty or not month or C["mes"] not in df.columns: return pd.DataFrame()
    months = df[C["mes"]].dropna().unique().tolist()
    if month not in months: return pd.DataFrame()
    idx = months.index(month)
    if idx == 0: return pd.DataFrame()
    return df[df[C["mes"]] == months[idx - 1]]

def agg(df, col):
    if df.empty or col not in df.columns: return 0
    return df[col].sum()

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown("""
<div class="dashboard-header">
    <div class="brand-name">🪩 Imagine Cave</div>
    <div class="brand-sub">Dashboard de Performance · Punta Cana · República Dominicana</div>
</div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CARREGAMENTO E PRÉ-PROCESSAMENTO
# ─────────────────────────────────────────────
with st.spinner("Carregando dados..."):
    df_canais   = load_sheet("Base_Canais")
    df_total    = load_sheet("Resumo_Total")
    df_pago     = load_sheet("Resumo_Midia_Paga")
    df_organico = load_sheet("Resumo_Organico")
    df_vendas   = load_vendas()

COLS_BASE    = [C["leads"], C["vendas"], C["receita"], C["invest"]]
COLS_RESUMO  = [C["leads"], C["vendas"], C["receita"], C["invest"],
                C["cpl"], C["cpv"], C["conv"], C["ticket"], C["roas"]]

df_canais   = calc_derived(prep(df_canais,   COLS_BASE))
df_total    = prep(df_total,    COLS_RESUMO)
df_pago     = prep(df_pago,     COLS_RESUMO)
df_organico = prep(df_organico, COLS_RESUMO)

if df_canais.empty and df_total.empty:
    st.warning("⚠️ Nenhum dado encontrado. Verifique as credenciais e o ID da planilha.")
    st.stop()

# ── Fallback: calcula resumos a partir de Base_Canais se abas estiverem vazias ──
if df_total.empty and not df_canais.empty:
    df_total = df_canais.groupby(C["mes"]).agg({
        C["leads"]: "sum", C["vendas"]: "sum",
        C["receita"]: "sum", C["invest"]: "sum",
    }).reset_index()
    for d in [df_total]:
        d[C["cpl"]]    = (d[C["invest"]] / d[C["leads"]].replace(0, float("nan"))).fillna(0)
        d[C["cpv"]]    = (d[C["invest"]] / d[C["vendas"]].replace(0, float("nan"))).fillna(0)
        d[C["roas"]]   = (d[C["receita"]] / d[C["invest"]].replace(0, float("nan"))).fillna(0)
        d[C["conv"]]   = (d[C["vendas"]] / d[C["leads"]].replace(0, float("nan")) * 100).fillna(0)
        d[C["ticket"]] = (d[C["receita"]] / d[C["vendas"]].replace(0, float("nan"))).fillna(0)

if df_pago.empty and not df_canais.empty:
    _pago = df_canais[df_canais[C["tipo"]].str.lower().str.contains("pago|paid|paga", na=False)]
    df_pago = _pago.groupby(C["mes"]).agg({
        C["leads"]: "sum", C["vendas"]: "sum",
        C["receita"]: "sum", C["invest"]: "sum",
    }).reset_index()
    df_pago[C["cpl"]]    = (df_pago[C["invest"]] / df_pago[C["leads"]].replace(0, float("nan"))).fillna(0)
    df_pago[C["cpv"]]    = (df_pago[C["invest"]] / df_pago[C["vendas"]].replace(0, float("nan"))).fillna(0)
    df_pago[C["roas"]]   = (df_pago[C["receita"]] / df_pago[C["invest"]].replace(0, float("nan"))).fillna(0)
    df_pago[C["conv"]]   = (df_pago[C["vendas"]] / df_pago[C["leads"]].replace(0, float("nan")) * 100).fillna(0)
    df_pago[C["ticket"]] = (df_pago[C["receita"]] / df_pago[C["vendas"]].replace(0, float("nan"))).fillna(0)

if df_organico.empty and not df_canais.empty:
    _org = df_canais[~df_canais[C["tipo"]].str.lower().str.contains("pago|paid|paga", na=False)]
    df_organico = _org.groupby(C["mes"]).agg({
        C["leads"]: "sum", C["vendas"]: "sum",
        C["receita"]: "sum", C["invest"]: "sum",
    }).reset_index()
    df_organico[C["cpl"]]    = (df_organico[C["invest"]] / df_organico[C["leads"]].replace(0, float("nan"))).fillna(0)
    df_organico[C["cpv"]]    = (df_organico[C["invest"]] / df_organico[C["vendas"]].replace(0, float("nan"))).fillna(0)
    df_organico[C["roas"]]   = (df_organico[C["receita"]] / df_organico[C["invest"]].replace(0, float("nan"))).fillna(0)
    df_organico[C["conv"]]   = (df_organico[C["vendas"]] / df_organico[C["leads"]].replace(0, float("nan")) * 100).fillna(0)
    df_organico[C["ticket"]] = (df_organico[C["receita"]] / df_organico[C["vendas"]].replace(0, float("nan"))).fillna(0)

# ── Seletor de mês ──
src_months = df_total if not df_total.empty else df_canais
all_months_raw = src_months[C["mes"]].dropna().unique().tolist() if C["mes"] in src_months.columns else []

MESES_PT = {
    "01": "Janeiro", "02": "Fevereiro", "03": "Março",
    "04": "Abril",   "05": "Maio",      "06": "Junho",
    "07": "Julho",   "08": "Agosto",    "09": "Setembro",
    "10": "Outubro", "11": "Novembro",  "12": "Dezembro",
}

def fmt_mes(val: str) -> str:
    """Converte '01/01/2026' ou '2026-01-01' em 'Janeiro/2026'."""
    val = str(val).strip()
    try:
        if "/" in val:
            parts = val.split("/")
            if len(parts) == 2:
                # formato M/AA ex: 1/26
                mes, ano = parts[0].zfill(2), "20" + parts[1].strip()
                return f"{MESES_PT.get(mes, mes)}/{ano}"
            if len(parts) == 3:
                # formato DD/MM/YYYY
                mes, ano = parts[1].zfill(2), parts[2]
                return f"{MESES_PT.get(mes, mes)}/{ano}"
        if "-" in val:
            parts = val.split("-")
            if len(parts) == 3:
                mes, ano = parts[1].zfill(2), parts[0]
                return f"{MESES_PT.get(mes, mes)}/{ano}"
    except Exception:
        pass
    return val

# Dicionário: nome legível → valor raw para filtro
month_labels = {fmt_mes(m): m for m in all_months_raw}
month_options = list(month_labels.keys())  # ex: ["Janeiro/2026", "Fevereiro/2026"]

col_f1, col_f2 = st.columns([4, 1])
with col_f1:
    mes_label = st.selectbox("📅 Selecionar Mês", options=month_options,
                             index=len(month_options) - 1 if month_options else 0)
with col_f2:
    if st.button("🔄 Atualizar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# Valor real para filtrar o DataFrame
mes_sel = month_labels.get(mes_label, mes_label)

st.markdown("---")

# Dados filtrados
df_c_mes  = filt(df_canais,   mes_sel)
df_c_prv  = prev(df_canais,   mes_sel)
df_t_mes  = filt(df_total,    mes_sel)
df_t_prv  = prev(df_total,    mes_sel)
df_p_mes  = filt(df_pago,     mes_sel)
df_o_mes  = filt(df_organico, mes_sel)

# ── Pré-processa df_vendas (usado em múltiplas abas) ──
if not df_vendas.empty:
    def _parse_data(s):
        s = str(s).strip()
        if "T" in s and s.endswith("Z"):
            try:
                return pd.to_datetime(s, format="%Y-%m-%dT%H:%M:%S.%fZ")
            except Exception:
                try:
                    return pd.to_datetime(s, utc=True).tz_localize(None)
                except Exception:
                    pass
        if "/" in s:
            try:
                return pd.to_datetime(s, dayfirst=True, errors="coerce")
            except Exception:
                pass
        return pd.NaT

    CV_DATA = "Data/hora da compra"
    CV_VALOR = "Valor total pago"
    CV_TAXAS = "Taxas"
    CV_QTD = "Qtd de ingressos"
    CV_REEMBOLSO = "Valor reembolsado"

    for col in [CV_VALOR, CV_TAXAS, CV_QTD, CV_REEMBOLSO]:
        if col in df_vendas.columns:
            df_vendas[col] = safe_num(df_vendas[col])

    if CV_DATA in df_vendas.columns:
        df_vendas["_data_parsed"] = df_vendas[CV_DATA].apply(_parse_data)
        df_vendas["_mes"] = df_vendas["_data_parsed"].dt.to_period("M").astype(str)

# ─────────────────────────────────────────────
# ABAS
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📊  Visão Geral", "🎯  Análise por Canal", "💡  Pago vs Orgânico", "🎟️  Ingressos & Vendas"])

# ════════════════════════════════════════════
# ABA 1 — VISÃO GERAL
# ════════════════════════════════════════════
with tab1:
    # Usa Resumo_Total como fonte primária (já consolidado)
    src, src_prv = (df_t_mes, df_t_prv) if not df_t_mes.empty else (df_c_mes, df_c_prv)

    # Receita real: busca da planilha de ingressos filtrada pelo mês selecionado
    if not df_vendas.empty and "_mes" in df_vendas.columns:
        def _mes_to_period(v):
            try:
                parts = str(v).split("/")
                if len(parts) == 2:
                    return f"20{parts[1].strip()}-{parts[0].zfill(2)}"
            except Exception:
                pass
            return str(v)
        _periodo_sel = _mes_to_period(mes_sel)
        _df_v_mes = df_vendas[df_vendas["_mes"] == _periodo_sel]
        receita = _df_v_mes["Valor total pago"].sum() if not _df_v_mes.empty else 0
    else:
        receita = agg(src, C["receita"])
    leads   = agg(src,     C["leads"])
    # Vendas reais = número de compras na planilha de ingressos
    if not df_vendas.empty and "_mes" in df_vendas.columns:
        def _mes_to_period_vg(v):
            try:
                parts = str(v).split("/")
                if len(parts) == 2:
                    return f"20{parts[1].strip()}-{parts[0].zfill(2)}"
            except Exception:
                pass
            return str(v)
        _p = _mes_to_period_vg(mes_sel)
        vendas = len(df_vendas[df_vendas["_mes"] == _p])
    else:
        vendas  = agg(src, C["vendas"])
    invest  = agg(src,     C["invest"])
    # ROAS real = receita ingressos / investimento
    _invest_roas = agg(src, C["invest"])
    roas = receita / _invest_roas if _invest_roas > 0 else 0
    conv    = agg(src,     C["conv"])
    r_prv   = agg(src_prv, C["receita"])
    l_prv   = agg(src_prv, C["leads"])
    v_prv   = agg(src_prv, C["vendas"])
    i_prv   = agg(src_prv, C["invest"])
    roas_prv= agg(src_prv, C["roas"])
    conv_prv= agg(src_prv, C["conv"])

    # KPIs
    st.markdown('<div class="section-title">🏆 KPIs do Mês</div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1: kpi_card("Receita Total",   fmt_usd(receita), delta_html(receita, r_prv),           "💰")
    with c2: kpi_card("Leads Gerados",   fmt_int(leads),   delta_html(leads,   l_prv),           "🎯")
    with c3: kpi_card("Vendas Fechadas", fmt_int(vendas),  delta_html(vendas,  v_prv),           "🤝")
    with c4: kpi_card("Conversão",       fmt_pct(conv),    delta_html(conv,    conv_prv),        "📈")
    with c5: kpi_card("Investimento",    fmt_usd(invest),  delta_html(invest,  i_prv, inverse=True), "💸")
    with c6: kpi_card("ROAS",            fmt_x(roas),      delta_html(roas,    roas_prv),        "🚀")

    # Cresceu ou caiu
    if r_prv > 0:
        var = ((receita - r_prv) / r_prv) * 100
        if var >= 0:
            st.success(f"📈 Crescemos **{var:.1f}%** vs mês anterior  ({fmt_usd(r_prv)} → {fmt_usd(receita)})")
        else:
            st.error(f"📉 Caímos **{abs(var):.1f}%** vs mês anterior  ({fmt_usd(r_prv)} → {fmt_usd(receita)})")

    # Insight
    canal_top = ""
    if not df_c_mes.empty and C["canal"] in df_c_mes.columns and C["receita"] in df_c_mes.columns:
        canal_top = df_c_mes.groupby(C["canal"])[C["receita"]].sum().idxmax()
    txt = f"Este mês: <strong>{fmt_usd(receita)}</strong> em receita"
    if r_prv > 0:
        diff = ((receita - r_prv) / r_prv) * 100
        txt += f" ({'+' if diff>=0 else ''}{diff:.1f}% vs anterior)"
    if canal_top:
        txt += f". Canal líder: <strong>{canal_top}</strong>."
    st.markdown(f'<div class="insight-box">💡 {txt}</div>', unsafe_allow_html=True)

    # Evolução histórica
    if not df_total.empty and C["mes"] in df_total.columns:
        st.markdown('<div class="section-title">📅 Evolução Histórica</div>', unsafe_allow_html=True)
        ht1, ht2, ht3 = st.tabs(["Receita & Investimento", "Leads & Vendas", "ROAS & Conversão"])

        with ht1:
            fig = go.Figure()
            MESES_L = {"01":"Jan","02":"Fev","03":"Mar","04":"Abr","05":"Mai","06":"Jun",
                       "07":"Jul","08":"Ago","09":"Set","10":"Out","11":"Nov","12":"Dez"}
            def _period_label(p):
                # Converte "2026-02" → "Fev/2026"
                try:
                    pt = str(p).split("-")
                    return f"{MESES_L.get(pt[1], pt[1])}/{pt[0]}"
                except Exception:
                    return str(p)
            def _raw_to_period(v):
                # Converte "1/26" → "2026-01" para depois virar label
                try:
                    parts = str(v).split("/")
                    if len(parts) == 2:
                        return f"20{parts[1].strip()}-{parts[0].zfill(2)}"
                except Exception:
                    pass
                return str(v)

            # Receita real vem da planilha de ingressos
            if not df_vendas.empty and "_mes" in df_vendas.columns:
                df_rec_mes = df_vendas.groupby("_mes")["Valor total pago"].sum().reset_index()
                df_rec_mes.columns = ["Periodo", "Receita"]
                df_rec_mes = df_rec_mes.sort_values("Periodo")  # ordena como string "2026-01" < "2026-02"
                df_rec_mes["Label"] = df_rec_mes["Periodo"].apply(_period_label)
                fig.add_trace(go.Bar(x=df_rec_mes["Label"], y=df_rec_mes["Receita"],
                                     name="Receita USD (Ingressos)", marker_color=COLORS[0], opacity=0.9))

            # Investimento vem da Base_Canais — normaliza para mesmo label
            if C["invest"] in df_total.columns:
                df_inv = df_total[[C["mes"], C["invest"]]].copy()
                df_inv["Periodo"] = df_inv[C["mes"]].apply(_raw_to_period)
                df_inv = df_inv.sort_values("Periodo")
                df_inv["Label"] = df_inv["Periodo"].apply(_period_label)
                fig.add_trace(go.Scatter(x=df_inv["Label"], y=df_inv[C["invest"]],
                                         name="Investimento USD", mode="lines+markers",
                                         line=dict(color=COLORS[2], width=2.5, dash="dot"), marker=dict(size=6)))

            # Ordena labels cronologicamente
            all_periods = sorted(set(
                list(df_rec_mes["Periodo"].tolist() if not df_vendas.empty and "_mes" in df_vendas.columns else []) +
                list(df_inv["Periodo"].tolist() if C["invest"] in df_total.columns else [])
            ))
            sorted_labels = [_period_label(p) for p in all_periods]
            layout_ht1 = dict(PLOT_LAYOUT)
            layout_ht1["xaxis"] = dict(type="category", categoryorder="array",
                                       categoryarray=sorted_labels,
                                       gridcolor="rgba(224,64,251,0.08)")
            layout_ht1["title"] = "Receita (Ingressos) vs Investimento (USD)"
            layout_ht1["height"] = 340
            fig.update_layout(**layout_ht1)
            st.plotly_chart(fig, use_container_width=True)

        with ht2:
            fig2 = go.Figure()
            if C["leads"] in df_total.columns:
                fig2.add_trace(go.Bar(x=df_total[C["mes"]], y=df_total[C["leads"]],
                                      name="Leads", marker_color=COLORS[1], opacity=0.9))
            if C["vendas"] in df_total.columns:
                fig2.add_trace(go.Scatter(x=df_total[C["mes"]], y=df_total[C["vendas"]],
                                          name="Vendas", mode="lines+markers",
                                          line=dict(color=COLORS[0], width=2.5), marker=dict(size=7)))
            fig2.update_layout(**PLOT_LAYOUT, title="Leads vs Vendas", height=340)
            st.plotly_chart(fig2, use_container_width=True)

        with ht3:
            fig3 = make_subplots(specs=[[{"secondary_y": True}]])
            if C["roas"] in df_total.columns:
                fig3.add_trace(go.Scatter(x=df_total[C["mes"]], y=df_total[C["roas"]],
                                          name="ROAS", mode="lines+markers",
                                          line=dict(color=COLORS[0], width=2.5), marker=dict(size=7)), secondary_y=False)
            if C["conv"] in df_total.columns:
                fig3.add_trace(go.Scatter(x=df_total[C["mes"]], y=df_total[C["conv"]],
                                          name="Conversão %", mode="lines+markers",
                                          line=dict(color=COLORS[1], width=2.5, dash="dash"), marker=dict(size=7)), secondary_y=True)
            fig3.update_layout(**PLOT_LAYOUT, title="ROAS & Conversão mês a mês", height=340)
            st.plotly_chart(fig3, use_container_width=True)

    # Gráficos por canal
    if not df_c_mes.empty and C["canal"] in df_c_mes.columns:
        st.markdown('<div class="section-title">📊 Distribuição por Canal</div>', unsafe_allow_html=True)
        g1, g2 = st.columns(2)
        with g1:
            df_r = df_c_mes.groupby(C["canal"])[C["receita"]].sum().reset_index().sort_values(C["receita"], ascending=False)
            fig_b = px.bar(df_r, x=C["receita"], y=C["canal"], orientation="h",
                           color=C["canal"], color_discrete_sequence=COLORS, title="Receita por Canal (USD)")
            fig_b.update_layout(**PLOT_LAYOUT, showlegend=False, height=320)
            st.plotly_chart(fig_b, use_container_width=True)
        with g2:
            df_l = df_c_mes.groupby(C["canal"])[C["leads"]].sum().reset_index().sort_values(C["leads"], ascending=False)
            fig_l = px.bar(df_l, x=C["leads"], y=C["canal"], orientation="h",
                           color=C["canal"], color_discrete_sequence=COLORS, title="Leads por Canal")
            fig_l.update_layout(**PLOT_LAYOUT, showlegend=False, height=320)
            st.plotly_chart(fig_l, use_container_width=True)

        if C["tipo"] in df_c_mes.columns:
            df_tipo = df_c_mes.groupby(C["tipo"])[C["receita"]].sum().reset_index()
            fig_p = px.pie(df_tipo, names=C["tipo"], values=C["receita"],
                           color_discrete_sequence=COLORS, title="Receita: Pago vs Orgânico", hole=0.5)
            fig_p.update_traces(textinfo="percent+label")
            fig_p.update_layout(**PLOT_LAYOUT, height=320)
            st.plotly_chart(fig_p, use_container_width=True)


# ════════════════════════════════════════════
# ABA 2 — ANÁLISE POR CANAL
# ════════════════════════════════════════════
with tab2:
    if df_c_mes.empty or C["canal"] not in df_c_mes.columns:
        st.info("Sem dados de canais para o período selecionado.")
    else:
        st.markdown('<div class="section-title">📋 Tabela Estratégica por Canal</div>', unsafe_allow_html=True)

        agg_map = {col: "sum" for col in COLS_BASE if col in df_c_mes.columns}
        df_tab = df_c_mes.groupby(C["canal"]).agg(agg_map).reset_index()
        df_tab = calc_derived(df_tab)

        # Display formatado
        col_map = {
            C["canal"]:   "Canal",
            C["leads"]:   "Leads",
            C["vendas"]:  "Vendas",
            C["conv"]:    "Conversão %",
            C["receita"]: "Receita (USD)",
            C["invest"]:  "Investimento (USD)",
            C["cpl"]:     "CPL",
            C["cpv"]:     "CPA",
            C["roas"]:    "ROAS",
            C["ticket"]:  "Ticket Médio",
        }
        cols_exist = [c for c in col_map if c in df_tab.columns]
        df_disp = df_tab[cols_exist].rename(columns=col_map).copy()

        for col in ["Receita (USD)", "Investimento (USD)", "CPL", "CPA", "Ticket Médio"]:
            if col in df_disp.columns:
                df_disp[col] = df_disp[col].apply(fmt_usd)
        if "Conversão %" in df_disp.columns:
            df_disp["Conversão %"] = df_disp["Conversão %"].apply(fmt_pct)
        if "ROAS" in df_disp.columns:
            df_disp["ROAS"] = df_disp["ROAS"].apply(fmt_x)

        st.dataframe(df_disp, use_container_width=True, hide_index=True)

        # Insights
        insights = []
        if C["roas"]   in df_tab.columns and df_tab[C["roas"]].sum()   > 0:
            insights.append(f"🏆 Melhor ROAS: <strong>{df_tab.loc[df_tab[C['roas']].idxmax(),   C['canal']]}</strong>")
        if C["cpl"]    in df_tab.columns and df_tab[C["cpl"]].sum()    > 0:
            insights.append(f"💰 Menor CPL: <strong>{df_tab.loc[df_tab[C['cpl']].idxmin(),    C['canal']]}</strong>")
        if C["cpv"]    in df_tab.columns and df_tab[C["cpv"]].sum()    > 0:
            insights.append(f"🎯 Menor CPA: <strong>{df_tab.loc[df_tab[C['cpv']].idxmin(),    C['canal']]}</strong>")
        if C["conv"]   in df_tab.columns and df_tab[C["conv"]].sum()   > 0:
            insights.append(f"📈 Maior Conversão: <strong>{df_tab.loc[df_tab[C['conv']].idxmax(),  C['canal']]}</strong>")
        if C["ticket"] in df_tab.columns and df_tab[C["ticket"]].sum() > 0:
            insights.append(f"💎 Maior Ticket: <strong>{df_tab.loc[df_tab[C['ticket']].idxmax(), C['canal']]}</strong>")
        if insights:
            st.markdown(f'<div class="insight-box">{"  ·  ".join(insights)}</div>', unsafe_allow_html=True)

        # Gráficos
        st.markdown('<div class="section-title">📈 Comparativos por Canal</div>', unsafe_allow_html=True)
        gc1, gc2 = st.columns(2)
        with gc1:
            if C["roas"] in df_tab.columns:
                # Maior ROAS no topo → ascending=False (plotly renderiza de baixo pra cima)
                fig_r = px.bar(df_tab.sort_values(C["roas"], ascending=False),
                               x=C["roas"], y=C["canal"], orientation="h",
                               color=C["canal"], color_discrete_sequence=COLORS, title="ROAS por Canal")
                fig_r.update_layout(**PLOT_LAYOUT, showlegend=False, height=300)
                st.plotly_chart(fig_r, use_container_width=True)
            if C["cpv"] in df_tab.columns:
                # Menor CPA no topo (melhor) → ascending=False
                fig_cpa = px.bar(df_tab.sort_values(C["cpv"], ascending=False),
                                 x=C["cpv"], y=C["canal"], orientation="h",
                                 color=C["canal"], color_discrete_sequence=COLORS, title="CPA por Canal (menor = melhor)")
                fig_cpa.update_layout(**PLOT_LAYOUT, showlegend=False, height=300)
                st.plotly_chart(fig_cpa, use_container_width=True)
        with gc2:
            if C["cpl"] in df_tab.columns:
                # Menor CPL no topo (melhor) → ascending=False
                fig_cpl = px.bar(df_tab.sort_values(C["cpl"], ascending=False),
                                 x=C["cpl"], y=C["canal"], orientation="h",
                                 color=C["canal"], color_discrete_sequence=COLORS, title="CPL por Canal (menor = melhor)")
                fig_cpl.update_layout(**PLOT_LAYOUT, showlegend=False, height=300)
                st.plotly_chart(fig_cpl, use_container_width=True)
            if C["conv"] in df_tab.columns:
                # Maior conversão no topo → ascending=False
                fig_conv = px.bar(df_tab.sort_values(C["conv"], ascending=False),
                                  x=C["conv"], y=C["canal"], orientation="h",
                                  color=C["canal"], color_discrete_sequence=COLORS, title="Conversão % por Canal")
                fig_conv.update_layout(**PLOT_LAYOUT, showlegend=False, height=300)
                st.plotly_chart(fig_conv, use_container_width=True)

        # Investimento vs Receita
        st.markdown('<div class="section-title">💸 Investimento → Receita por Canal</div>', unsafe_allow_html=True)
        df_iv = df_tab.melt(id_vars=C["canal"], value_vars=[c for c in [C["receita"], C["invest"]] if c in df_tab.columns],
                            var_name="Métrica", value_name="Valor")
        df_iv["Métrica"] = df_iv["Métrica"].map({C["receita"]: "Receita USD", C["invest"]: "Investimento USD"})
        fig_iv = px.bar(df_iv, x=C["canal"], y="Valor", color="Métrica", barmode="group",
                        color_discrete_sequence=[COLORS[0], COLORS[2]], title="Investimento vs Receita por Canal")
        fig_iv.update_layout(**PLOT_LAYOUT, height=360)
        st.plotly_chart(fig_iv, use_container_width=True)


# ════════════════════════════════════════════
# ABA 3 — PAGO VS ORGÂNICO
# ════════════════════════════════════════════
with tab3:
    rec_p  = agg(df_p_mes, C["receita"])
    rec_o  = agg(df_o_mes, C["receita"])
    lead_p = agg(df_p_mes, C["leads"])
    lead_o = agg(df_o_mes, C["leads"])
    inv_p  = agg(df_p_mes, C["invest"])
    roas_p = agg(df_p_mes, C["roas"])
    roas_o = agg(df_o_mes, C["roas"])
    cpl_p  = agg(df_p_mes, C["cpl"])

    rec_tot  = rec_p  + rec_o
    lead_tot = lead_p + lead_o

    pct_rp = rec_p  / rec_tot  * 100 if rec_tot  else 0
    pct_ro = rec_o  / rec_tot  * 100 if rec_tot  else 0
    pct_lp = lead_p / lead_tot * 100 if lead_tot else 0
    pct_lo = lead_o / lead_tot * 100 if lead_tot else 0

    st.markdown('<div class="section-title">📊 Participação no Mês</div>', unsafe_allow_html=True)
    pk1, pk2, pk3, pk4 = st.columns(4)
    with pk1: kpi_card("% Receita Pago",     fmt_pct(pct_rp), "", "💰")
    with pk2: kpi_card("% Receita Orgânico", fmt_pct(pct_ro), "", "🌱")
    with pk3: kpi_card("% Leads Pago",       fmt_pct(pct_lp), "", "🎯")
    with pk4: kpi_card("% Leads Orgânico",   fmt_pct(pct_lo), "", "🌿")

    # Insight dependência
    if pct_rp > 70:
        dep = f"⚠️ Negócio <strong>muito dependente de mídia paga</strong> ({pct_rp:.0f}%). Se desligar anúncios, restariam apenas <strong>{fmt_usd(rec_o)}</strong> em receita orgânica."
    elif pct_rp > 50:
        dep = f"📌 Pago domina com <strong>{pct_rp:.0f}%</strong>. Orgânico sustenta <strong>{fmt_usd(rec_o)}</strong>. Atenção à dependência crescente."
    else:
        dep = f"✅ Ótimo equilíbrio! Orgânico representa <strong>{pct_ro:.0f}%</strong>. Negócio tem base sólida sem anúncios."
    st.markdown(f'<div class="insight-box">{dep}</div>', unsafe_allow_html=True)

    # Pizzas
    pg1, pg2 = st.columns(2)
    with pg1:
        if rec_tot > 0:
            fig_pr = px.pie(values=[rec_p, rec_o], names=["Pago", "Orgânico"],
                            title="Receita: Pago vs Orgânico",
                            color_discrete_sequence=[COLORS[0], COLORS[1]], hole=0.55)
            fig_pr.update_traces(textinfo="percent+label")
            fig_pr.update_layout(**PLOT_LAYOUT, height=320)
            st.plotly_chart(fig_pr, use_container_width=True)
    with pg2:
        if lead_tot > 0:
            fig_pl = px.pie(values=[lead_p, lead_o], names=["Pago", "Orgânico"],
                            title="Leads: Pago vs Orgânico",
                            color_discrete_sequence=[COLORS[2], COLORS[3]], hole=0.55)
            fig_pl.update_traces(textinfo="percent+label")
            fig_pl.update_layout(**PLOT_LAYOUT, height=320)
            st.plotly_chart(fig_pl, use_container_width=True)

    # Evolução mensal
    st.markdown('<div class="section-title">📅 Evolução Mensal</div>', unsafe_allow_html=True)
    if not df_pago.empty and not df_organico.empty and C["mes"] in df_pago.columns:
        fig_evo = go.Figure()
        if C["receita"] in df_pago.columns:
            fig_evo.add_trace(go.Scatter(x=df_pago[C["mes"]], y=df_pago[C["receita"]],
                                         name="Receita Pago", line=dict(color=COLORS[0], width=2.5),
                                         mode="lines+markers", fill="tozeroy",
                                         fillcolor="rgba(0,201,167,0.08)", marker=dict(size=7)))
        if C["receita"] in df_organico.columns:
            fig_evo.add_trace(go.Scatter(x=df_organico[C["mes"]], y=df_organico[C["receita"]],
                                         name="Receita Orgânico", line=dict(color=COLORS[1], width=2.5),
                                         mode="lines+markers", fill="tozeroy",
                                         fillcolor="rgba(255,209,102,0.08)", marker=dict(size=7)))
        if C["invest"] in df_pago.columns:
            fig_evo.add_trace(go.Scatter(x=df_pago[C["mes"]], y=df_pago[C["invest"]],
                                         name="Investimento Pago", line=dict(color=COLORS[2], width=2, dash="dot"),
                                         mode="lines+markers", marker=dict(size=6, symbol="diamond")))
        fig_evo.update_layout(**PLOT_LAYOUT, title="Receita Pago vs Orgânico vs Investimento (USD)", height=400)
        st.plotly_chart(fig_evo, use_container_width=True)

    # ROAS evolução
    if not df_pago.empty and not df_organico.empty and C["roas"] in df_pago.columns:
        st.markdown('<div class="section-title">🚀 ROAS: Pago vs Orgânico</div>', unsafe_allow_html=True)
        fig_revo = go.Figure()
        fig_revo.add_trace(go.Scatter(x=df_pago[C["mes"]], y=df_pago[C["roas"]],
                                      name="ROAS Pago", line=dict(color=COLORS[0], width=2.5),
                                      mode="lines+markers", marker=dict(size=8)))
        if C["roas"] in df_organico.columns:
            fig_revo.add_trace(go.Scatter(x=df_organico[C["mes"]], y=df_organico[C["roas"]],
                                          name="ROAS Orgânico", line=dict(color=COLORS[1], width=2.5, dash="dash"),
                                          mode="lines+markers", marker=dict(size=8)))
        fig_revo.update_layout(**PLOT_LAYOUT, title="Evolução do ROAS mês a mês", height=320)
        st.plotly_chart(fig_revo, use_container_width=True)

    # CAC pago
    if not df_pago.empty and C["cpl"] in df_pago.columns and C["mes"] in df_pago.columns:
        st.markdown('<div class="section-title">💸 CAC Pago ao Longo do Tempo</div>', unsafe_allow_html=True)
        fig_cac = px.line(df_pago, x=C["mes"], y=C["cpl"], markers=True,
                          title="CAC Pago (CPL) mês a mês", color_discrete_sequence=[COLORS[2]])
        fig_cac.update_traces(line_width=2.5, marker_size=8)
        fig_cac.update_layout(**PLOT_LAYOUT, height=300)
        st.plotly_chart(fig_cac, use_container_width=True)

        vals = df_pago[C["cpl"]].dropna().values
        if len(vals) >= 2:
            trend = "aumentando 📈 — custo crescente" if vals[-1] > vals[-2] else "diminuindo ✅ — eficiência melhorando"
            st.markdown(f'<div class="insight-box">CAC pago está <strong>{trend}</strong>. Último valor: <strong>{fmt_usd(vals[-1])}</strong></div>',
                        unsafe_allow_html=True)


# ════════════════════════════════════════════
# ABA 4 — INGRESSOS & VENDAS
# ════════════════════════════════════════════
with tab4:
    if df_vendas.empty:
        st.info("Sem dados de vendas disponíveis.")
    else:
        CV = {
            "data":      "Data/hora da compra",
            "genero":    "Gênero",
            "valor":     "Valor total pago",
            "taxas":     "Taxas",
            "qtd":       "Qtd de ingressos",
            "tipo":      "Tipo",
            "tipo_ing":  "Tipo de ingresso",
            "metodo":    "Método de pagamento",
            "pais":      "País do comprador",
            "reembolso": "Valor reembolsado",
        }

        # Filtra pelo mês selecionado
        def _mes_to_period_tab4(v):
            try:
                parts = str(v).split("/")
                if len(parts) == 2:
                    return f"20{parts[1].strip()}-{parts[0].zfill(2)}"
            except Exception:
                pass
            return str(v)
        _periodo_tab4 = _mes_to_period_tab4(mes_sel)
        if not df_vendas.empty and "_mes" in df_vendas.columns:
            df_v = df_vendas[df_vendas["_mes"] == _periodo_tab4].copy()
        else:
            df_v = df_vendas.copy()

        def parse_data(s):
            s = str(s).strip()
            # Formato ISO: 2026-02-20T18:35:46.000Z
            if "T" in s and s.endswith("Z"):
                try:
                    return pd.to_datetime(s, format="%Y-%m-%dT%H:%M:%S.%fZ")
                except Exception:
                    try:
                        return pd.to_datetime(s, utc=True).tz_localize(None)
                    except Exception:
                        pass
            # Formato BR: 11/03/2026 15:53:05 ou 11/03/2026
            if "/" in s:
                try:
                    return pd.to_datetime(s, dayfirst=True, errors="coerce")
                except Exception:
                    pass
            return pd.NaT

        # _mes já calculado no pré-processamento global

        st.markdown('<div class="section-title">🎟️ KPIs de Ingressos</div>', unsafe_allow_html=True)
        receita_v   = df_v[CV["valor"]].sum()      if CV["valor"]     in df_v.columns else 0
        taxas_v     = df_v[CV["taxas"]].sum()      if CV["taxas"]     in df_v.columns else 0
        qtd_v       = df_v[CV["qtd"]].sum()        if CV["qtd"]       in df_v.columns else 0
        reembolso_v = df_v[CV["reembolso"]].sum()  if CV["reembolso"] in df_v.columns else 0
        n_compras   = len(df_v)
        ticket_v    = receita_v / n_compras if n_compras > 0 else 0
        media_ing   = qtd_v / n_compras if n_compras > 0 else 0

        k1,k2,k3,k4,k5,k6 = st.columns(6)
        with k1: kpi_card("Receita Total",      fmt_usd(receita_v),   "", "💰")
        with k2: kpi_card("Ingressos Vendidos", fmt_int(qtd_v),       "", "🎟️")
        with k3: kpi_card("Ticket Médio",       fmt_usd(ticket_v),    "", "💳")
        with k4: kpi_card("Média Ing./Compra",  f"{media_ing:.1f}",   "", "👥")
        with k5: kpi_card("Total em Taxas",     fmt_usd(taxas_v),     "", "📋")
        with k6: kpi_card("Reembolsos",         fmt_usd(reembolso_v), "", "↩️")

        st.markdown("---")
        st.markdown('<div class="section-title">👥 Perfil do Comprador</div>', unsafe_allow_html=True)
        col_a, col_b = st.columns(2)

        with col_a:
            if CV["genero"] in df_v.columns:
                df_gen = df_v.groupby(CV["genero"])[CV["valor"]].sum().reset_index()
                df_gen.columns = ["Gênero", "Receita"]
                fig_gen = px.pie(df_gen, names="Gênero", values="Receita", title="Receita por Gênero",
                                 color_discrete_sequence=COLORS, hole=0.5)
                fig_gen.update_traces(textinfo="percent+label")
                fig_gen.update_layout(**PLOT_LAYOUT, height=320)
                st.plotly_chart(fig_gen, use_container_width=True)

        with col_b:
            if CV["tipo"] in df_v.columns:
                df_tipo = df_v.groupby(CV["tipo"])[CV["qtd"]].sum().reset_index()
                df_tipo.columns = ["Tipo", "Qtd"]
                fig_tipo = px.pie(df_tipo, names="Tipo", values="Qtd", title="Ingressos por Tipo",
                                  color_discrete_sequence=COLORS, hole=0.5)
                fig_tipo.update_traces(textinfo="percent+label")
                fig_tipo.update_layout(**PLOT_LAYOUT, height=320)
                st.plotly_chart(fig_tipo, use_container_width=True)

        col_c, col_d = st.columns(2)
        with col_c:
            if CV["tipo_ing"] in df_v.columns:
                df_ti = df_v.groupby(CV["tipo_ing"])[CV["qtd"]].sum().reset_index()
                df_ti.columns = ["Tipo de Ingresso", "Qtd"]
                df_ti = df_ti.sort_values("Qtd", ascending=False)
                fig_ti = px.bar(df_ti, x="Qtd", y="Tipo de Ingresso", orientation="h",
                                color="Tipo de Ingresso", color_discrete_sequence=COLORS,
                                title="Quantidade por Tipo de Ingresso")
                fig_ti.update_layout(**PLOT_LAYOUT, showlegend=False, height=320)
                st.plotly_chart(fig_ti, use_container_width=True)

        with col_d:
            if CV["metodo"] in df_v.columns:
                df_met = df_v.groupby(CV["metodo"])[CV["valor"]].sum().reset_index()
                df_met.columns = ["Método", "Receita"]
                fig_met = px.pie(df_met, names="Método", values="Receita",
                                 title="Receita por Método de Pagamento",
                                 color_discrete_sequence=COLORS, hole=0.5)
                fig_met.update_traces(textinfo="percent+label")
                fig_met.update_layout(**PLOT_LAYOUT, height=320)
                st.plotly_chart(fig_met, use_container_width=True)

        st.markdown('<div class="section-title">🌍 Origem dos Compradores</div>', unsafe_allow_html=True)
        col_e, col_f = st.columns(2)
        with col_e:
            if CV["pais"] in df_v.columns:
                df_pais = df_v.groupby(CV["pais"])[CV["qtd"]].sum().reset_index()
                df_pais.columns = ["País", "Qtd"]
                df_pais = df_pais.sort_values("Qtd", ascending=False)
                fig_pais = px.bar(df_pais, x="Qtd", y="País", orientation="h",
                                  color="País", color_discrete_sequence=COLORS,
                                  title="Ingressos por País")
                fig_pais.update_layout(**PLOT_LAYOUT, showlegend=False, height=360)
                st.plotly_chart(fig_pais, use_container_width=True)

        with col_f:
            if CV["pais"] in df_v.columns:
                df_pais_r = df_v.groupby(CV["pais"])[CV["valor"]].sum().reset_index()
                df_pais_r.columns = ["País", "Receita"]
                fig_pais_r = px.pie(df_pais_r, names="País", values="Receita",
                                    title="Participação de Receita por País",
                                    color_discrete_sequence=COLORS, hole=0.5)
                fig_pais_r.update_traces(textinfo="percent+label")
                fig_pais_r.update_layout(**PLOT_LAYOUT, height=360)
                st.plotly_chart(fig_pais_r, use_container_width=True)

        st.markdown('<div class="section-title">📅 Vendas por Mês</div>', unsafe_allow_html=True)
        if "_mes" in df_v.columns:
            df_mes_v = df_v.groupby("_mes").agg(
                Receita=(CV["valor"], "sum"),
                Ingressos=(CV["qtd"], "sum"),
            ).reset_index().rename(columns={"_mes": "Mês"})
            # Converte período para nome legível ex: "2026-02" → "Fev/2026"
            MESES_LABEL = {"01":"Jan","02":"Fev","03":"Mar","04":"Abr","05":"Mai","06":"Jun",
                           "07":"Jul","08":"Ago","09":"Set","10":"Out","11":"Nov","12":"Dez"}
            def mes_label(p):
                try:
                    partes = str(p).split("-")
                    return f"{MESES_LABEL.get(partes[1], partes[1])}/{partes[0]}"
                except Exception:
                    return str(p)
            df_mes_v["Mês_Label"] = df_mes_v["Mês"].apply(mes_label)
            df_mes_v = df_mes_v.sort_values("Mês")

            fig_mv = go.Figure()
            fig_mv.add_trace(go.Bar(x=df_mes_v["Mês_Label"], y=df_mes_v["Receita"],
                                    name="Receita", marker_color=COLORS[0], opacity=0.9))
            fig_mv.add_trace(go.Scatter(x=df_mes_v["Mês_Label"], y=df_mes_v["Ingressos"],
                                        name="Ingressos", mode="lines+markers",
                                        line=dict(color=COLORS[1], width=2.5),
                                        marker=dict(size=7), yaxis="y2"))
            layout_mv = dict(PLOT_LAYOUT)
            layout_mv["xaxis"] = dict(type="category", gridcolor="rgba(224,64,251,0.08)")
            layout_mv["yaxis2"] = dict(overlaying="y", side="right", gridcolor="rgba(0,0,0,0)", color="#9E7BB5")
            layout_mv["title"] = "Receita e Ingressos por Mês"
            layout_mv["height"] = 360
            fig_mv.update_layout(**layout_mv)
            st.plotly_chart(fig_mv, use_container_width=True)

        st.markdown('<div class="section-title">🔀 Cruzamento: Marketing × Vendas</div>', unsafe_allow_html=True)
        invest_total = agg(df_total, C["invest"]) if not df_total.empty else agg(df_pago, C["invest"])
        leads_total  = agg(df_total, C["leads"])  if not df_total.empty else 0
        roas_real    = receita_v / invest_total if invest_total > 0 else 0
        cpv_real     = invest_total / n_compras  if n_compras   > 0 else 0
        cpl_real     = invest_total / leads_total if leads_total > 0 else 0

        cx1,cx2,cx3,cx4 = st.columns(4)
        with cx1: kpi_card("Investimento Total", fmt_usd(invest_total), "", "💸")
        with cx2: kpi_card("ROAS Real",          fmt_x(roas_real),      "", "🚀")
        with cx3: kpi_card("Custo por Venda",    fmt_usd(cpv_real),     "", "🎯")
        with cx4: kpi_card("Custo por Lead",     fmt_usd(cpl_real),     "", "📊")

        st.markdown(
            f'<div class="insight-box">🔀 Para cada <strong>{fmt_usd(1)}</strong> investido, a Imagine Cave gerou ' +
            f'<strong>{fmt_usd(roas_real)}</strong> em receita (ROAS real). ' +
            f'Custo por venda: <strong>{fmt_usd(cpv_real)}</strong> · Custo por lead: <strong>{fmt_usd(cpl_real)}</strong>.</div>',
            unsafe_allow_html=True
        )

# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style="text-align:center; color: #4a3060; font-size: 0.75rem; padding: 1rem 0;">
    🪩 Imagine Cave · Dashboard de Marketing Digital ·
    Dados atualizados automaticamente · Powered by Élcio Souza
</div>""", unsafe_allow_html=True)
