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
import datetime

# ─────────────────────────────────────────────
# SEGURANÇA
# ─────────────────────────────────────────────
logging.basicConfig(level=logging.ERROR, format="%(asctime)s [%(levelname)s] %(message)s")
_logger = logging.getLogger(__name__)

_SENSITIVE_PATTERNS = [
    (r"https?://[^\s\"']+", "[URL_OCULTA]"),
    (r"[a-zA-Z0-9_\-]{30,}", "[TOKEN_OCULTO]"),
    (r"[\w.+\-]+@[\w\-]+\.[\w.]+", "[EMAIL_OCULTO]"),
    (r"\b\d{10,}\b", "[ID_OCULTO]"),
    (r"act_\d+", "[AD_ACCOUNT_OCULTO]"),
]

def _sanitize(text: str) -> str:
    raw = str(text)
    try:
        for key in ["spreadsheet", "spreadsheet2"]:
            sid = st.secrets.get(key, {}).get("id", "")
            if sid and len(sid) > 5:
                raw = raw.replace(sid, "[SHEET_ID_OCULTO]")
    except Exception:
        pass
    try:
        for section in ["google_ads", "meta_ads", "gcp_service_account"]:
            section_data = st.secrets.get(section, {})
            if hasattr(section_data, 'to_dict'):
                section_data = section_data.to_dict()
            if isinstance(section_data, dict):
                for v in section_data.values():
                    if isinstance(v, str) and len(v) > 8:
                        raw = raw.replace(v, "[SECRET_OCULTO]")
    except Exception:
        pass
    for pattern, replacement in _SENSITIVE_PATTERNS:
        raw = re.sub(pattern, replacement, raw)
    return raw

def _log_error(context: str, err: Exception):
    _logger.error("[%s] %s", context, _sanitize(str(err)))

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
<meta http-equiv="X-Content-Type-Options" content="nosniff">
<meta http-equiv="Permissions-Policy" content="geolocation=(), microphone=(), camera=()">
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# MAPEAMENTO DE COLUNAS
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
    --primary: #E040FB; --primary-dark: #AB00D6;
    --accent: #FF4081;  --accent2: #7C4DFF;
    --bg-dark: #0A0010; --bg-card: #120020;
    --text-main: #F3E5F5; --text-muted: #9E7BB5;
    --border: rgba(224,64,251,0.18);
    --red: #FF4081; --green: #69FF47;
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
.ads-invest-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 1.2rem 1.4rem; margin-bottom: 0.8rem; }
.ads-invest-google { border-left: 4px solid #4285F4; }
.ads-invest-meta   { border-left: 4px solid #0866FF; }
.ads-invest-total  { border-left: 4px solid var(--primary); }
.ads-platform-label { font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 4px; }
.ads-platform-value { font-family: 'Rajdhani', sans-serif; font-size: 1.6rem; font-weight: 700; color: var(--text-main); }
.badge { display: inline-block; font-size: 0.6rem; padding: 2px 8px; border-radius: 20px; font-weight: 700; letter-spacing: 0.5px; margin-left: 6px; vertical-align: middle; }
.badge-api    { background: rgba(105,255,71,0.12); color: #69FF47; border: 1px solid rgba(105,255,71,0.3); }
.badge-manual { background: rgba(255,209,71,0.12); color: #FFD147; border: 1px solid rgba(255,209,71,0.3); }
</style>
""", unsafe_allow_html=True)

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
        creds  = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
        client = gspread.authorize(creds)
        sh     = client.open_by_key(st.secrets["spreadsheet"]["id"])
        data   = sh.worksheet(sheet_name).get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        _log_error(f"load_sheet:{sheet_name}", e)
        st.error(f"⚠️ Não foi possível carregar os dados ({sheet_name}).")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_vendas() -> pd.DataFrame:
    try:
        creds  = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
        client = gspread.authorize(creds)
        sh     = client.open_by_key(st.secrets["spreadsheet2"]["id"])
        data   = sh.get_worksheet(0).get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        _log_error("load_vendas", e)
        st.error("⚠️ Não foi possível carregar os dados de vendas.")
        return pd.DataFrame()

# ─────────────────────────────────────────────
# CONVERSÃO DE MÊS → DATAS
# Suporta: "1/26", "01/26", "3/26", "2/26"
# ─────────────────────────────────────────────
def _month_date_range(mes_raw: str):
    """
    Converte o formato da planilha (ex: "3/26") para (start_date, end_date).
    Retorna strings no formato YYYY-MM-DD para uso nas APIs.
    """
    try:
        val   = str(mes_raw).strip()
        parts = val.split("/")

        if len(parts) == 2:
            mes = int(parts[0])           # ex: 3
            ano = int("20" + parts[1])    # ex: "26" → 2026
        elif len(parts) == 3:
            # formato DD/MM/YYYY
            mes = int(parts[1])
            ano = int(parts[2])
        else:
            return None, None

        if mes < 1 or mes > 12:
            return None, None

        start = datetime.date(ano, mes, 1)
        # Último dia do mês
        if mes == 12:
            end = datetime.date(ano + 1, 1, 1) - datetime.timedelta(days=1)
        else:
            end = datetime.date(ano, mes + 1, 1) - datetime.timedelta(days=1)

        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    except Exception as e:
        _log_error("month_date_range", e)
        return None, None

# ─────────────────────────────────────────────
# GOOGLE ADS API — Extrai investimento real
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def load_google_ads_spend(mes_raw: str) -> float:
    """
    Busca o total gasto no Google Ads para o mês selecionado.
    Retorna float em USD. Retorna 0.0 em caso de erro.
    """
    try:
        from google.ads.googleads.client import GoogleAdsClient

        start, end = _month_date_range(mes_raw)
        if not start:
            return 0.0

        cfg = {
            "developer_token":   st.secrets["google_ads"]["developer_token"],
            "client_id":         st.secrets["google_ads"]["client_id"],
            "client_secret":     st.secrets["google_ads"]["client_secret"],
            "refresh_token":     st.secrets["google_ads"]["refresh_token"],
            "login_customer_id": str(st.secrets["google_ads"]["login_customer_id"]),
            "use_proto_plus":    True,
        }
        client   = GoogleAdsClient.load_from_dict(cfg)
        service  = client.get_service("GoogleAdsService")
        cust_id  = str(st.secrets["google_ads"]["customer_id"]).replace("-", "")

        query = f"""
            SELECT metrics.cost_micros
            FROM campaign
            WHERE segments.date BETWEEN '{start}' AND '{end}'
            AND campaign.status != 'REMOVED'
        """
        response = service.search(customer_id=cust_id, query=query)
        total    = sum(row.metrics.cost_micros for row in response) / 1_000_000
        return round(total, 2)

    except Exception as e:
        _log_error("google_ads_spend", e)
        return 0.0

# ─────────────────────────────────────────────
# META ADS API — Extrai investimento real
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def load_meta_spend(mes_raw: str) -> float:
    """
    Busca o total gasto no Meta Ads para o mês selecionado.
    Retorna float em USD. Retorna 0.0 em caso de erro.
    """
    try:
        from facebook_business.api import FacebookAdsApi
        from facebook_business.adobjects.adaccount import AdAccount

        start, end = _month_date_range(mes_raw)
        if not start:
            return 0.0

        FacebookAdsApi.init(access_token=st.secrets["meta_ads"]["access_token"])
        account  = AdAccount(st.secrets["meta_ads"]["ad_account_id"])
        insights = account.get_insights(params={
            "time_range": {"since": start, "until": end},
            "level":      "account",
            "fields":     ["spend"],
        })
        total = sum(float(i["spend"]) for i in insights if "spend" in i)
        return round(total, 2)

    except Exception as e:
        _log_error("meta_spend", e)
        return 0.0

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
    up   = (diff >= 0) if not inverse else (diff < 0)
    css  = "delta-up" if up else "delta-down"
    arr  = "▲" if diff >= 0 else "▼"
    return f'<span class="kpi-delta {css}">{arr} {abs(diff):.1f}% vs mês anterior</span>'

def kpi_card(label, value, delta="", icon=""):
    st.markdown(
        f'<div class="kpi-card"><div class="kpi-label">{icon} {label}</div>'
        f'<div class="kpi-value">{value}</div>{delta}</div>',
        unsafe_allow_html=True
    )

def prep(df, cols):
    if df.empty: return df
    for col in cols:
        if col in df.columns:
            df[col] = safe_num(df[col])
    return df

def calc_derived(df):
    if df.empty: return df
    leads  = df[C["leads"]].where(df[C["leads"]]  > 0) if C["leads"]  in df.columns else pd.Series(np.nan, index=df.index)
    vendas = df[C["vendas"]].where(df[C["vendas"]] > 0) if C["vendas"] in df.columns else pd.Series(np.nan, index=df.index)
    rec    = df[C["receita"]] if C["receita"] in df.columns else pd.Series(0, index=df.index)
    inv    = df[C["invest"]].where(df[C["invest"]] > 0)  if C["invest"] in df.columns else pd.Series(np.nan, index=df.index)
    df[C["cpl"]]    = (inv / leads).fillna(0)
    df[C["cpv"]]    = (inv / vendas).fillna(0)
    df[C["roas"]]   = (rec / inv).fillna(0)
    df[C["conv"]]   = (df[C["vendas"]] / leads * 100).fillna(0) if C["vendas"] in df.columns else 0
    df[C["ticket"]] = (rec / vendas).fillna(0)
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

def badge(ok: bool) -> str:
    if ok:
        return '<span class="badge badge-api">API</span>'
    return '<span class="badge badge-manual">Planilha</span>'

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown("""
<div class="dashboard-header">
    <div class="brand-name">🪩 Imagine Cave</div>
    <div class="brand-sub">Dashboard de Performance · Punta Cana · República Dominicana</div>
</div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CARREGAMENTO DE DADOS
# ─────────────────────────────────────────────
with st.spinner("Carregando dados..."):
    df_canais   = load_sheet("Base_Canais")
    df_total    = load_sheet("Resumo_Total")
    df_pago     = load_sheet("Resumo_Midia_Paga")
    df_organico = load_sheet("Resumo_Organico")
    df_vendas   = load_vendas()

COLS_BASE   = [C["leads"], C["vendas"], C["receita"], C["invest"]]
COLS_RESUMO = [C["leads"], C["vendas"], C["receita"], C["invest"],
               C["cpl"], C["cpv"], C["conv"], C["ticket"], C["roas"]]

df_canais   = calc_derived(prep(df_canais,   COLS_BASE))
df_total    = prep(df_total,    COLS_RESUMO)
df_pago     = prep(df_pago,     COLS_RESUMO)
df_organico = prep(df_organico, COLS_RESUMO)

if df_canais.empty and df_total.empty:
    st.warning("⚠️ Nenhum dado encontrado.")
    st.stop()

# Fallbacks
if df_total.empty and not df_canais.empty:
    df_total = df_canais.groupby(C["mes"]).agg({c:"sum" for c in COLS_BASE if c in df_canais.columns}).reset_index()
    for d in [df_total]:
        d[C["cpl"]]    = (d[C["invest"]] / d[C["leads"]].replace(0, float("nan"))).fillna(0)
        d[C["cpv"]]    = (d[C["invest"]] / d[C["vendas"]].replace(0, float("nan"))).fillna(0)
        d[C["roas"]]   = (d[C["receita"]] / d[C["invest"]].replace(0, float("nan"))).fillna(0)
        d[C["conv"]]   = (d[C["vendas"]] / d[C["leads"]].replace(0, float("nan")) * 100).fillna(0)
        d[C["ticket"]] = (d[C["receita"]] / d[C["vendas"]].replace(0, float("nan"))).fillna(0)

if df_pago.empty and not df_canais.empty:
    _pago = df_canais[df_canais[C["tipo"]].str.lower().str.contains("pago|paid|paga", na=False)]
    df_pago = _pago.groupby(C["mes"]).agg({c:"sum" for c in COLS_BASE if c in _pago.columns}).reset_index()
    df_pago[C["cpl"]]    = (df_pago[C["invest"]] / df_pago[C["leads"]].replace(0, float("nan"))).fillna(0)
    df_pago[C["cpv"]]    = (df_pago[C["invest"]] / df_pago[C["vendas"]].replace(0, float("nan"))).fillna(0)
    df_pago[C["roas"]]   = (df_pago[C["receita"]] / df_pago[C["invest"]].replace(0, float("nan"))).fillna(0)
    df_pago[C["conv"]]   = (df_pago[C["vendas"]] / df_pago[C["leads"]].replace(0, float("nan")) * 100).fillna(0)
    df_pago[C["ticket"]] = (df_pago[C["receita"]] / df_pago[C["vendas"]].replace(0, float("nan"))).fillna(0)

if df_organico.empty and not df_canais.empty:
    _org = df_canais[~df_canais[C["tipo"]].str.lower().str.contains("pago|paid|paga", na=False)]
    df_organico = _org.groupby(C["mes"]).agg({c:"sum" for c in COLS_BASE if c in _org.columns}).reset_index()
    df_organico[C["cpl"]]    = (df_organico[C["invest"]] / df_organico[C["leads"]].replace(0, float("nan"))).fillna(0)
    df_organico[C["cpv"]]    = (df_organico[C["invest"]] / df_organico[C["vendas"]].replace(0, float("nan"))).fillna(0)
    df_organico[C["roas"]]   = (df_organico[C["receita"]] / df_organico[C["invest"]].replace(0, float("nan"))).fillna(0)
    df_organico[C["conv"]]   = (df_organico[C["vendas"]] / df_organico[C["leads"]].replace(0, float("nan")) * 100).fillna(0)
    df_organico[C["ticket"]] = (df_organico[C["receita"]] / df_organico[C["vendas"]].replace(0, float("nan"))).fillna(0)

# ── Seletor de mês ──
MESES_PT = {"01":"Janeiro","02":"Fevereiro","03":"Março","04":"Abril","05":"Maio","06":"Junho",
            "07":"Julho","08":"Agosto","09":"Setembro","10":"Outubro","11":"Novembro","12":"Dezembro"}

def fmt_mes(val: str) -> str:
    """Converte '1/26' → 'Janeiro/2026'"""
    val = str(val).strip()
    try:
        parts = val.split("/")
        if len(parts) == 2:
            mes = parts[0].zfill(2)   # "1" → "01"
            ano = "20" + parts[1]     # "26" → "2026"
            return f"{MESES_PT.get(mes, mes)}/{ano}"
        if len(parts) == 3:
            mes = parts[1].zfill(2)
            ano = parts[2]
            return f"{MESES_PT.get(mes, mes)}/{ano}"
    except Exception:
        pass
    return val

src_months    = df_total if not df_total.empty else df_canais
all_months    = src_months[C["mes"]].dropna().unique().tolist() if C["mes"] in src_months.columns else []
month_labels  = {fmt_mes(m): m for m in all_months}
month_options = list(month_labels.keys())

col_f1, col_f2 = st.columns([4, 1])
with col_f1:
    mes_label = st.selectbox("📅 Selecionar Mês", options=month_options,
                             index=len(month_options)-1 if month_options else 0)
with col_f2:
    if st.button("🔄 Atualizar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

mes_sel = month_labels.get(mes_label, mes_label)   # ex: "3/26"
st.markdown("---")

# ── Pré-processa vendas ──
CV_DATA, CV_VALOR, CV_TAXAS = "Data/hora da compra", "Valor total pago", "Taxas"
CV_QTD,  CV_REEMBOLSO       = "Qtd de ingressos",    "Valor reembolsado"

if not df_vendas.empty:
    def _parse_data(s):
        s = str(s).strip()
        if "T" in s and s.endswith("Z"):
            try: return pd.to_datetime(s, format="%Y-%m-%dT%H:%M:%S.%fZ")
            except Exception:
                try: return pd.to_datetime(s, utc=True).tz_localize(None)
                except Exception: pass
        if "/" in s:
            try: return pd.to_datetime(s, dayfirst=True, errors="coerce")
            except Exception: pass
        return pd.NaT
    for col in [CV_VALOR, CV_TAXAS, CV_QTD, CV_REEMBOLSO]:
        if col in df_vendas.columns:
            df_vendas[col] = safe_num(df_vendas[col])
    if CV_DATA in df_vendas.columns:
        df_vendas["_data_parsed"] = df_vendas[CV_DATA].apply(_parse_data)
        df_vendas["_mes"]         = df_vendas["_data_parsed"].dt.to_period("M").astype(str)

# ── Dados filtrados ──
df_c_mes = filt(df_canais,   mes_sel); df_c_prv = prev(df_canais,   mes_sel)
df_t_mes = filt(df_total,    mes_sel); df_t_prv = prev(df_total,    mes_sel)
df_p_mes = filt(df_pago,     mes_sel)
df_o_mes = filt(df_organico, mes_sel)

# Converter mes_sel para período do pandas (ex: "3/26" → "2026-03")
def _mes_to_period(v: str) -> str:
    try:
        p = str(v).strip().split("/")
        if len(p) == 2:
            return f"20{p[1]}-{p[0].zfill(2)}"
    except Exception:
        pass
    return str(v)

_periodo_sel = _mes_to_period(mes_sel)  # ex: "2026-03"

# ─────────────────────────────────────────────
# EXTRAÇÃO DO INVESTIMENTO DAS APIs
# Google Ads + Meta Ads → valor real do mês
# ─────────────────────────────────────────────
with st.spinner("🔄 Buscando investimento do Google Ads e Meta Ads..."):
    _invest_google = load_google_ads_spend(mes_sel)   # ex: 1250.00
    _invest_meta   = load_meta_spend(mes_sel)          # ex: 890.50
    _invest_api    = round(_invest_google + _invest_meta, 2)
    _fonte_api     = _invest_api > 0                   # True = veio das APIs

# BLOCO DE DEBUG — remover após resolver

# Fallback: se APIs não retornaram, usa soma da planilha
_invest_planilha = agg(df_t_mes, C["invest"]) if not df_t_mes.empty else agg(df_c_mes, C["invest"])
_invest_final    = _invest_api if _fonte_api else _invest_planilha

# ─────────────────────────────────────────────
# ABAS
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊  Visão Geral",
    "💸  Investimento Ads",
    "🎯  Análise por Canal",
    "💡  Pago vs Orgânico",
    "🎟️  Ingressos & Vendas",
])

# ════════════════════════════════════════════
# ABA 1 — VISÃO GERAL
# ════════════════════════════════════════════
with tab1:
    src, src_prv = (df_t_mes, df_t_prv) if not df_t_mes.empty else (df_c_mes, df_c_prv)

    # Receita e vendas reais da planilha de ingressos
    if not df_vendas.empty and "_mes" in df_vendas.columns:
        _df_v_sel = df_vendas[df_vendas["_mes"] == _periodo_sel]
        receita   = _df_v_sel[CV_VALOR].sum() if not _df_v_sel.empty else 0
        vendas    = len(_df_v_sel)
    else:
        receita = agg(src, C["receita"])
        vendas  = agg(src, C["vendas"])

    leads   = agg(src, C["leads"])
    invest  = _invest_final                              # ← VALOR REAL DAS APIs
    roas    = receita / invest if invest > 0 else 0
    conv    = agg(src, C["conv"])
    r_prv   = agg(src_prv, C["receita"]); l_prv   = agg(src_prv, C["leads"])
    v_prv   = agg(src_prv, C["vendas"]);  i_prv   = agg(src_prv, C["invest"])
    roas_prv= agg(src_prv, C["roas"]);    conv_prv= agg(src_prv, C["conv"])

    st.markdown('<div class="section-title">🏆 KPIs do Mês</div>', unsafe_allow_html=True)
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    with c1: kpi_card("Receita Total",   fmt_usd(receita), delta_html(receita, r_prv),               "💰")
    with c2: kpi_card("Leads Gerados",   fmt_int(leads),   delta_html(leads,   l_prv),               "🎯")
    with c3: kpi_card("Vendas Fechadas", fmt_int(vendas),  delta_html(vendas,  v_prv),               "🤝")
    with c4: kpi_card("Conversão",       fmt_pct(conv),    delta_html(conv,    conv_prv),            "📈")
    with c5: kpi_card("Investimento",    fmt_usd(invest),  delta_html(invest,  i_prv, inverse=True), "💸")
    with c6: kpi_card("ROAS",            fmt_x(roas),      delta_html(roas,    roas_prv),            "🚀")

    # Linha de fonte do investimento — corrigida com unsafe_allow_html=True
    _badge_html = "🟢 API" if _fonte_api else "🟡 Planilha"
    st.caption(f"Investimento via: {_badge_html}  |  🔵 Google Ads: {fmt_usd(_invest_google)}  ·  🔷 Meta Ads: {fmt_usd(_invest_meta)}")
    if r_prv > 0:
        var = ((receita - r_prv) / r_prv) * 100
        if var >= 0: st.success(f"📈 Crescemos **{var:.1f}%** vs mês anterior ({fmt_usd(r_prv)} → {fmt_usd(receita)})")
        else:        st.error(  f"📉 Caímos **{abs(var):.1f}%** vs mês anterior ({fmt_usd(r_prv)} → {fmt_usd(receita)})")

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

    if not df_total.empty and C["mes"] in df_total.columns:
        st.markdown('<div class="section-title">📅 Evolução Histórica</div>', unsafe_allow_html=True)
        ht1, ht2, ht3 = st.tabs(["Receita & Investimento", "Leads & Vendas", "ROAS & Conversão"])
        MESES_L = {"01":"Jan","02":"Fev","03":"Mar","04":"Abr","05":"Mai","06":"Jun",
                   "07":"Jul","08":"Ago","09":"Set","10":"Out","11":"Nov","12":"Dez"}
        def _pl(p):
            try:
                pt = str(p).split("-"); return f"{MESES_L.get(pt[1],pt[1])}/{pt[0]}"
            except Exception: return str(p)
        def _r2p(v):
            try:
                p = str(v).strip().split("/")
                if len(p) == 2: return f"20{p[1]}-{p[0].zfill(2)}"
            except Exception: pass
            return str(v)

        with ht1:
            fig = go.Figure()
            if not df_vendas.empty and "_mes" in df_vendas.columns:
                df_rec = df_vendas.groupby("_mes")[CV_VALOR].sum().reset_index()
                df_rec.columns = ["Periodo","Receita"]
                df_rec = df_rec.sort_values("Periodo")
                df_rec["Label"] = df_rec["Periodo"].apply(_pl)
                fig.add_trace(go.Bar(x=df_rec["Label"], y=df_rec["Receita"],
                                     name="Receita USD", marker_color=COLORS[0], opacity=0.9))
            if C["invest"] in df_total.columns:
                df_inv = df_total[[C["mes"],C["invest"]]].copy()
                df_inv["Periodo"] = df_inv[C["mes"]].apply(_r2p)
                df_inv = df_inv.sort_values("Periodo")
                df_inv["Label"] = df_inv["Periodo"].apply(_pl)
                fig.add_trace(go.Scatter(x=df_inv["Label"], y=df_inv[C["invest"]],
                                         name="Investimento USD", mode="lines+markers",
                                         line=dict(color=COLORS[2], width=2.5, dash="dot"), marker=dict(size=6)))
            all_p = sorted(set(
                list(df_rec["Periodo"].tolist() if not df_vendas.empty and "_mes" in df_vendas.columns else []) +
                list(df_inv["Periodo"].tolist()  if C["invest"] in df_total.columns else [])
            ))
            lyt = dict(PLOT_LAYOUT)
            lyt["xaxis"]  = dict(type="category", categoryorder="array",
                                 categoryarray=[_pl(p) for p in all_p],
                                 gridcolor="rgba(224,64,251,0.08)")
            lyt["title"]  = "Receita vs Investimento (USD)"
            lyt["height"] = 340
            fig.update_layout(**lyt)
            st.plotly_chart(fig, use_container_width=True)

        with ht2:
            fig2 = go.Figure()
            if C["leads"]  in df_total.columns:
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


# ════════════════════════════════════════════
# ABA 2 — 💸 INVESTIMENTO ADS
# ════════════════════════════════════════════
with tab2:
    st.markdown('<div class="section-title">💸 Investimento em Anúncios</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f'<div class="ads-invest-card ads-invest-google">'
            f'<div class="ads-platform-label">🔵 Google Ads {badge(_invest_google > 0)}</div>'
            f'<div class="ads-platform-value">{fmt_usd(_invest_google)}</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    with c2:
        st.markdown(
            f'<div class="ads-invest-card ads-invest-meta">'
            f'<div class="ads-platform-label">🔷 Meta Ads {badge(_invest_meta > 0)}</div>'
            f'<div class="ads-platform-value">{fmt_usd(_invest_meta)}</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    with c3:
        st.markdown(
            f'<div class="ads-invest-card ads-invest-total">'
            f'<div class="ads-platform-label">📊 Total Investido {badge(_fonte_api)}</div>'
            f'<div class="ads-platform-value">{fmt_usd(_invest_final)}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    # Métricas de eficiência calculadas com investimento real
    if not df_vendas.empty and "_mes" in df_vendas.columns:
        _rec_m = df_vendas[df_vendas["_mes"] == _periodo_sel][CV_VALOR].sum()
    else:
        _rec_m = agg(df_t_mes, C["receita"])

    _leads_m = agg(df_t_mes, C["leads"])
    _roas_r  = _rec_m        / _invest_final if _invest_final > 0 else 0
    _cpl_r   = _invest_final / _leads_m      if _leads_m      > 0 else 0
    _ret_liq = _rec_m        - _invest_final

    st.markdown('<div class="section-title">📈 Métricas de Eficiência</div>', unsafe_allow_html=True)
    m1,m2,m3,m4 = st.columns(4)
    with m1: kpi_card("ROAS Real",        fmt_x(_roas_r),   "", "🚀")
    with m2: kpi_card("Receita no Mês",   fmt_usd(_rec_m),  "", "💰")
    with m3: kpi_card("Custo por Lead",   fmt_usd(_cpl_r),  "", "🎯")
    with m4: kpi_card("Retorno Líquido",  fmt_usd(_ret_liq),"", "📊")

    if _invest_google > 0 or _invest_meta > 0:
        st.markdown('<div class="section-title">🥧 Distribuição do Investimento</div>', unsafe_allow_html=True)
        d1, d2 = st.columns(2)
        with d1:
            fig_dist = px.pie(
                values=[_invest_google, _invest_meta],
                names=["Google Ads", "Meta Ads"],
                title="Google Ads vs Meta Ads",
                color_discrete_sequence=["#4285F4", "#0866FF"],
                hole=0.55
            )
            fig_dist.update_traces(textinfo="percent+label")
            fig_dist.update_layout(**PLOT_LAYOUT, height=320)
            st.plotly_chart(fig_dist, use_container_width=True)
        with d2:
            _pg = (_invest_google / _invest_api * 100) if _invest_api > 0 else 0
            _pm = (_invest_meta   / _invest_api * 100) if _invest_api > 0 else 0
            st.markdown(
                f'<div class="insight-box">'
                f'💡 Neste mês:<br><br>'
                f'🔵 <strong>Google Ads</strong>: <strong>{_pg:.1f}%</strong> do total ({fmt_usd(_invest_google)})<br>'
                f'🔷 <strong>Meta Ads</strong>: <strong>{_pm:.1f}%</strong> do total ({fmt_usd(_invest_meta)})<br><br>'
                f'Para cada <strong>{fmt_usd(1)}</strong> investido → '
                f'<strong>{fmt_usd(_roas_r)}</strong> em receita de ingressos (ROAS Real).'
                f'</div>',
                unsafe_allow_html=True
            )

    if not _fonte_api:
        st.warning("⚠️ APIs sem dados para este período. Usando valores da planilha como fallback.")


# ════════════════════════════════════════════
# ABA 3 — ANÁLISE POR CANAL
# ════════════════════════════════════════════
with tab3:
    if df_c_mes.empty or C["canal"] not in df_c_mes.columns:
        st.info("Sem dados de canais para o período selecionado.")
    else:
        st.markdown('<div class="section-title">📋 Tabela Estratégica por Canal</div>', unsafe_allow_html=True)
        df_tab = calc_derived(df_c_mes.groupby(C["canal"]).agg(
            {c:"sum" for c in COLS_BASE if c in df_c_mes.columns}
        ).reset_index())

        col_map = {
            C["canal"]:"Canal", C["leads"]:"Leads", C["vendas"]:"Vendas",
            C["conv"]:"Conversão %", C["receita"]:"Receita (USD)", C["invest"]:"Investimento (USD)",
            C["cpl"]:"CPL", C["cpv"]:"CPA", C["roas"]:"ROAS", C["ticket"]:"Ticket Médio",
        }
        df_disp = df_tab[[c for c in col_map if c in df_tab.columns]].rename(columns=col_map).copy()
        for col in ["Receita (USD)","Investimento (USD)","CPL","CPA","Ticket Médio"]:
            if col in df_disp.columns: df_disp[col] = df_disp[col].apply(fmt_usd)
        if "Conversão %" in df_disp.columns: df_disp["Conversão %"] = df_disp["Conversão %"].apply(fmt_pct)
        if "ROAS"        in df_disp.columns: df_disp["ROAS"]        = df_disp["ROAS"].apply(fmt_x)
        st.dataframe(df_disp, use_container_width=True, hide_index=True)

        ins = []
        if C["roas"] in df_tab.columns and df_tab[C["roas"]].sum() > 0:
            ins.append(f"🏆 Melhor ROAS: <strong>{df_tab.loc[df_tab[C['roas']].idxmax(), C['canal']]}</strong>")
        if C["cpl"]  in df_tab.columns and df_tab[C["cpl"]].sum()  > 0:
            ins.append(f"💰 Menor CPL: <strong>{df_tab.loc[df_tab[C['cpl']].idxmin(), C['canal']]}</strong>")
        if C["conv"] in df_tab.columns and df_tab[C["conv"]].sum() > 0:
            ins.append(f"📈 Maior Conversão: <strong>{df_tab.loc[df_tab[C['conv']].idxmax(), C['canal']]}</strong>")
        if ins:
            st.markdown(f'<div class="insight-box">{"  ·  ".join(ins)}</div>', unsafe_allow_html=True)

        st.markdown('<div class="section-title">📈 Comparativos por Canal</div>', unsafe_allow_html=True)
        gc1, gc2 = st.columns(2)
        with gc1:
            if C["roas"] in df_tab.columns:
                fig_r = px.bar(df_tab.sort_values(C["roas"], ascending=False),
                               x=C["roas"], y=C["canal"], orientation="h",
                               color=C["canal"], color_discrete_sequence=COLORS, title="ROAS por Canal")
                fig_r.update_layout(**PLOT_LAYOUT, showlegend=False, height=300)
                st.plotly_chart(fig_r, use_container_width=True)
            if C["cpv"] in df_tab.columns:
                fig_cpa = px.bar(df_tab.sort_values(C["cpv"], ascending=False),
                                 x=C["cpv"], y=C["canal"], orientation="h",
                                 color=C["canal"], color_discrete_sequence=COLORS, title="CPA por Canal")
                fig_cpa.update_layout(**PLOT_LAYOUT, showlegend=False, height=300)
                st.plotly_chart(fig_cpa, use_container_width=True)
        with gc2:
            if C["cpl"] in df_tab.columns:
                fig_cpl = px.bar(df_tab.sort_values(C["cpl"], ascending=False),
                                 x=C["cpl"], y=C["canal"], orientation="h",
                                 color=C["canal"], color_discrete_sequence=COLORS, title="CPL por Canal")
                fig_cpl.update_layout(**PLOT_LAYOUT, showlegend=False, height=300)
                st.plotly_chart(fig_cpl, use_container_width=True)
            if C["conv"] in df_tab.columns:
                fig_conv = px.bar(df_tab.sort_values(C["conv"], ascending=False),
                                  x=C["conv"], y=C["canal"], orientation="h",
                                  color=C["canal"], color_discrete_sequence=COLORS, title="Conversão % por Canal")
                fig_conv.update_layout(**PLOT_LAYOUT, showlegend=False, height=300)
                st.plotly_chart(fig_conv, use_container_width=True)


# ════════════════════════════════════════════
# ABA 4 — PAGO VS ORGÂNICO
# ════════════════════════════════════════════
with tab4:
    rec_p  = agg(df_p_mes, C["receita"]); rec_o  = agg(df_o_mes, C["receita"])
    lead_p = agg(df_p_mes, C["leads"]);   lead_o = agg(df_o_mes, C["leads"])
    rec_tot  = rec_p + rec_o; lead_tot = lead_p + lead_o
    pct_rp = rec_p  / rec_tot  * 100 if rec_tot  else 0
    pct_ro = rec_o  / rec_tot  * 100 if rec_tot  else 0
    pct_lp = lead_p / lead_tot * 100 if lead_tot else 0
    pct_lo = lead_o / lead_tot * 100 if lead_tot else 0

    st.markdown('<div class="section-title">📊 Participação no Mês</div>', unsafe_allow_html=True)
    pk1,pk2,pk3,pk4 = st.columns(4)
    with pk1: kpi_card("% Receita Pago",     fmt_pct(pct_rp), "", "💰")
    with pk2: kpi_card("% Receita Orgânico", fmt_pct(pct_ro), "", "🌱")
    with pk3: kpi_card("% Leads Pago",       fmt_pct(pct_lp), "", "🎯")
    with pk4: kpi_card("% Leads Orgânico",   fmt_pct(pct_lo), "", "🌿")

    if   pct_rp > 70: dep = f"⚠️ Negócio <strong>muito dependente de mídia paga</strong> ({pct_rp:.0f}%). Orgânico = <strong>{fmt_usd(rec_o)}</strong>."
    elif pct_rp > 50: dep = f"📌 Pago domina com <strong>{pct_rp:.0f}%</strong>. Orgânico sustenta <strong>{fmt_usd(rec_o)}</strong>."
    else:             dep = f"✅ Ótimo equilíbrio! Orgânico = <strong>{pct_ro:.0f}%</strong>."
    st.markdown(f'<div class="insight-box">{dep}</div>', unsafe_allow_html=True)

    pg1, pg2 = st.columns(2)
    with pg1:
        if rec_tot > 0:
            fig_pr = px.pie(values=[rec_p, rec_o], names=["Pago","Orgânico"],
                            title="Receita: Pago vs Orgânico",
                            color_discrete_sequence=[COLORS[0], COLORS[1]], hole=0.55)
            fig_pr.update_traces(textinfo="percent+label")
            fig_pr.update_layout(**PLOT_LAYOUT, height=320)
            st.plotly_chart(fig_pr, use_container_width=True)
    with pg2:
        if lead_tot > 0:
            fig_pl = px.pie(values=[lead_p, lead_o], names=["Pago","Orgânico"],
                            title="Leads: Pago vs Orgânico",
                            color_discrete_sequence=[COLORS[2], COLORS[3]], hole=0.55)
            fig_pl.update_traces(textinfo="percent+label")
            fig_pl.update_layout(**PLOT_LAYOUT, height=320)
            st.plotly_chart(fig_pl, use_container_width=True)

    if not df_pago.empty and C["mes"] in df_pago.columns:
        st.markdown('<div class="section-title">📅 Evolução Mensal</div>', unsafe_allow_html=True)
        fig_evo = go.Figure()
        if C["receita"] in df_pago.columns:
            fig_evo.add_trace(go.Scatter(x=df_pago[C["mes"]], y=df_pago[C["receita"]],
                                         name="Receita Pago", line=dict(color=COLORS[0], width=2.5),
                                         mode="lines+markers", fill="tozeroy",
                                         fillcolor="rgba(224,64,251,0.08)", marker=dict(size=7)))
        if not df_organico.empty and C["receita"] in df_organico.columns:
            fig_evo.add_trace(go.Scatter(x=df_organico[C["mes"]], y=df_organico[C["receita"]],
                                         name="Receita Orgânico", line=dict(color=COLORS[1], width=2.5),
                                         mode="lines+markers", fill="tozeroy",
                                         fillcolor="rgba(255,64,129,0.08)", marker=dict(size=7)))
        if C["invest"] in df_pago.columns:
            fig_evo.add_trace(go.Scatter(x=df_pago[C["mes"]], y=df_pago[C["invest"]],
                                         name="Investimento Pago", line=dict(color=COLORS[2], width=2, dash="dot"),
                                         mode="lines+markers", marker=dict(size=6, symbol="diamond")))
        fig_evo.update_layout(**PLOT_LAYOUT, title="Receita Pago vs Orgânico vs Investimento", height=400)
        st.plotly_chart(fig_evo, use_container_width=True)


# ════════════════════════════════════════════
# ABA 5 — INGRESSOS & VENDAS
# ════════════════════════════════════════════
with tab5:
    if df_vendas.empty:
        st.info("Sem dados de vendas disponíveis.")
    else:
        CV = {
            "data":"Data/hora da compra","genero":"Gênero","valor":"Valor total pago",
            "taxas":"Taxas","qtd":"Qtd de ingressos","tipo":"Tipo",
            "tipo_ing":"Tipo de ingresso","metodo":"Método de pagamento",
            "pais":"País do comprador","reembolso":"Valor reembolsado",
        }
        df_v = df_vendas[df_vendas["_mes"] == _periodo_sel].copy() if "_mes" in df_vendas.columns else df_vendas.copy()

        st.markdown('<div class="section-title">🎟️ KPIs de Ingressos</div>', unsafe_allow_html=True)
        receita_v   = df_v[CV["valor"]].sum()     if CV["valor"]     in df_v.columns else 0
        taxas_v     = df_v[CV["taxas"]].sum()     if CV["taxas"]     in df_v.columns else 0
        qtd_v       = df_v[CV["qtd"]].sum()       if CV["qtd"]       in df_v.columns else 0
        reembolso_v = df_v[CV["reembolso"]].sum() if CV["reembolso"] in df_v.columns else 0
        n_compras   = len(df_v)
        ticket_v    = receita_v / n_compras if n_compras > 0 else 0
        media_ing   = qtd_v     / n_compras if n_compras > 0 else 0

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
                df_gen.columns = ["Gênero","Receita"]
                fig_gen = px.pie(df_gen, names="Gênero", values="Receita", title="Receita por Gênero",
                                 color_discrete_sequence=COLORS, hole=0.5)
                fig_gen.update_traces(textinfo="percent+label")
                fig_gen.update_layout(**PLOT_LAYOUT, height=320)
                st.plotly_chart(fig_gen, use_container_width=True)
        with col_b:
            if CV["tipo"] in df_v.columns:
                df_tipo = df_v.groupby(CV["tipo"])[CV["qtd"]].sum().reset_index()
                df_tipo.columns = ["Tipo","Qtd"]
                fig_tipo = px.pie(df_tipo, names="Tipo", values="Qtd", title="Ingressos por Tipo",
                                  color_discrete_sequence=COLORS, hole=0.5)
                fig_tipo.update_traces(textinfo="percent+label")
                fig_tipo.update_layout(**PLOT_LAYOUT, height=320)
                st.plotly_chart(fig_tipo, use_container_width=True)

        col_c, col_d = st.columns(2)
        with col_c:
            if CV["tipo_ing"] in df_v.columns:
                df_ti = df_v.groupby(CV["tipo_ing"])[CV["qtd"]].sum().reset_index()
                df_ti.columns = ["Tipo de Ingresso","Qtd"]
                df_ti = df_ti.sort_values("Qtd", ascending=False)
                fig_ti = px.bar(df_ti, x="Qtd", y="Tipo de Ingresso", orientation="h",
                                color="Tipo de Ingresso", color_discrete_sequence=COLORS,
                                title="Quantidade por Tipo de Ingresso")
                fig_ti.update_layout(**PLOT_LAYOUT, showlegend=False, height=320)
                st.plotly_chart(fig_ti, use_container_width=True)
        with col_d:
            if CV["metodo"] in df_v.columns:
                df_met = df_v.groupby(CV["metodo"])[CV["valor"]].sum().reset_index()
                df_met.columns = ["Método","Receita"]
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
                df_pais.columns = ["País","Qtd"]
                df_pais = df_pais.sort_values("Qtd", ascending=False)
                fig_pais = px.bar(df_pais, x="Qtd", y="País", orientation="h",
                                  color="País", color_discrete_sequence=COLORS, title="Ingressos por País")
                fig_pais.update_layout(**PLOT_LAYOUT, showlegend=False, height=360)
                st.plotly_chart(fig_pais, use_container_width=True)
        with col_f:
            if CV["pais"] in df_v.columns:
                df_pais_r = df_v.groupby(CV["pais"])[CV["valor"]].sum().reset_index()
                df_pais_r.columns = ["País","Receita"]
                fig_pais_r = px.pie(df_pais_r, names="País", values="Receita",
                                    title="Participação de Receita por País",
                                    color_discrete_sequence=COLORS, hole=0.5)
                fig_pais_r.update_traces(textinfo="percent+label")
                fig_pais_r.update_layout(**PLOT_LAYOUT, height=360)
                st.plotly_chart(fig_pais_r, use_container_width=True)

        st.markdown('<div class="section-title">📅 Vendas por Mês</div>', unsafe_allow_html=True)
        if "_mes" in df_vendas.columns:
            df_mes_v = df_vendas.groupby("_mes").agg(
                Receita=(CV["valor"],"sum"), Ingressos=(CV["qtd"],"sum")
            ).reset_index().rename(columns={"_mes":"Mês"})
            ML = {"01":"Jan","02":"Fev","03":"Mar","04":"Abr","05":"Mai","06":"Jun",
                  "07":"Jul","08":"Ago","09":"Set","10":"Out","11":"Nov","12":"Dez"}
            def _ml(p):
                try: pt = str(p).split("-"); return f"{ML.get(pt[1],pt[1])}/{pt[0]}"
                except Exception: return str(p)
            df_mes_v["Mês_Label"] = df_mes_v["Mês"].apply(_ml)
            df_mes_v = df_mes_v.sort_values("Mês")
            fig_mv = go.Figure()
            fig_mv.add_trace(go.Bar(x=df_mes_v["Mês_Label"], y=df_mes_v["Receita"],
                                    name="Receita", marker_color=COLORS[0], opacity=0.9))
            fig_mv.add_trace(go.Scatter(x=df_mes_v["Mês_Label"], y=df_mes_v["Ingressos"],
                                        name="Ingressos", mode="lines+markers",
                                        line=dict(color=COLORS[1], width=2.5),
                                        marker=dict(size=7), yaxis="y2"))
            lyt_mv = dict(PLOT_LAYOUT)
            lyt_mv["xaxis"]  = dict(type="category", gridcolor="rgba(224,64,251,0.08)")
            lyt_mv["yaxis2"] = dict(overlaying="y", side="right", gridcolor="rgba(0,0,0,0)", color="#9E7BB5")
            lyt_mv["title"]  = "Receita e Ingressos por Mês"
            lyt_mv["height"] = 360
            fig_mv.update_layout(**lyt_mv)
            st.plotly_chart(fig_mv, use_container_width=True)

        st.markdown('<div class="section-title">🔀 Cruzamento: Marketing × Vendas</div>', unsafe_allow_html=True)
        _leads_cx = agg(df_t_mes, C["leads"])
        _roas_cx  = receita_v    / _invest_final if _invest_final > 0 else 0
        _cpv_cx   = _invest_final / n_compras    if n_compras     > 0 else 0
        _cpl_cx   = _invest_final / _leads_cx    if _leads_cx     > 0 else 0

        cx1,cx2,cx3,cx4 = st.columns(4)
        with cx1: kpi_card("Investimento Total", fmt_usd(_invest_final), "", "💸")
        with cx2: kpi_card("ROAS Real",          fmt_x(_roas_cx),        "", "🚀")
        with cx3: kpi_card("Custo por Venda",    fmt_usd(_cpv_cx),       "", "🎯")
        with cx4: kpi_card("Custo por Lead",     fmt_usd(_cpl_cx),       "", "📊")

        st.markdown(
            f'<div class="insight-box">🔀 Para cada <strong>{fmt_usd(1)}</strong> investido, a Imagine Cave gerou '
            f'<strong>{fmt_usd(_roas_cx)}</strong> em receita (ROAS real). '
            f'Custo por venda: <strong>{fmt_usd(_cpv_cx)}</strong> · Custo por lead: <strong>{fmt_usd(_cpl_cx)}</strong>.</div>',
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
