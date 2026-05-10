import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json, requests, time
from bs4 import BeautifulSoup
import quant_analyzer
import altair as alt

st.set_page_config(page_title="거북이 함대 기동 본부 V0.6.2", layout="wide", initial_sidebar_state="expanded")

# --- 🚨 [V0.6.2 패치] Secrets에서 키 자동 로드 로직 추가 ---
# Secrets에 gemini_api_key가 등록되어 있으면 자동으로 가져옵니다.
if "gemini_api_key" in st.secrets:
    auto_api_key = st.secrets["gemini_api_key"]
else:
    auto_api_key = ""

# --- CSS (원본 스타일 유지) ---
st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    h1, h2, h3, p, span, div { font-family: 'Urbanist', 'Noto Sans KR', sans-serif; }
    .hq-title { font-size: 1.3rem; color: rgb(70,130,180); font-weight: 800; padding-top: 5px; margin-bottom: 15px; }
    .index-container { display: flex; flex-wrap: wrap; justify-content: space-between; background: #0f172a; padding: 10px 15px; border-radius: 10px; border: 1px solid #1e293b; margin-bottom: 15px; gap: 8px 0; }
    .index-item { display: flex; flex-direction: column; align-items: center; width: 24%; }
    .index-name { font-size: 0.75rem; color: rgb(108,122,137); font-weight: 700; margin-bottom: 2px; }
    .index-val { font-size: 1.05rem; font-weight: 800; color: #ffffff; }
    .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }
    .kpi-box { display: flex; flex-direction: column; }
    .kpi-label { font-size: 0.8rem; color: rgb(108,122,137); font-weight: 700; margin-bottom: 4px; }
    .kpi-val { font-size: 1.5rem; font-weight: 800; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: 700; background-color: #0f172a; border: 1px solid #1e293b; color: #f8fafc; height: 45px; }
    .stButton>button:hover { border-color: rgb(70,130,180); color: rgb(70,130,180); }
    </style>
    """, unsafe_allow_html=True)

# --- Data Load & Helper Functions ---
def get_gspread_client():
    key_info = json.loads(st.secrets["google_credentials"])
    if "private_key" in key_info: key_info["private_key"] = key_info["private_key"].replace("\\n", "\n")
    return gspread.authorize(Credentials.from_service_account_info(key_info, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']))

@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0").get_worksheet(0)
    full_df = pd.DataFrame(sheet.get_all_records())
    df = full_df.copy()
    if '계좌유형' in df.columns: df['계좌유형'] = df['계좌유형'].astype(str).str.strip()
    for col in df.columns:
        if col not in ['계좌번호', '계좌유형', '종목명', '종목코드', '상품', '구분']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', '').str.replace('%', ''), errors='coerce').fillna(0)
    df = df[df['종목명'].astype(str).str.strip() != '']
    return sheet, df, full_df

def get_safe_val(r, cols):
    for c in cols:
        v = r.get(c, 0)
        if v != 0 and pd.notna(v): return v
    return 0

# --- 🚨 [V0.6.2 패치] 통신 엔진 전면 재설계 (다중 버전 정밀 타격) ---
def generate_ai_briefing(api_key, portfolio_df, tcr_results, user_context):
    clean_key = api_key.strip()
    pf_summary = [f"- {r['종목명']}: 수익률 {r['안전_수익률']*100:.1f}%, TCR {tcr_results.get(str(r['종목코드']),{}).get('score',0)}%" for _, r in portfolio_df.iterrows() if "현금" not in str(r['종목명'])]
    
    prompt = f"참모 브리핑 요망.\n[현황]: {chr(10).join(pf_summary)}\n[지시]: {user_context}\n🌍글로벌요약, 🎯포트진단, 🔥작전지시"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    # 시도할 최신 주소들 (순서대로 타격)
    endpoints = [
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
        "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent",
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
    ]
    
    for url in endpoints:
        try:
            res = requests.post(f"{url}?key={clean_key}", headers=headers, json=payload, timeout=60)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text']
        except: continue
            
    return "🚨 통신망 전면 두절. API 키가 유효한지, 혹은 구글 서버 점검 중인지 확인이 필요합니다."

# --- Main App ---
try:
    sheet, df, full_df = load_data()
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V0.6.2</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        # 🚨 Secrets에 키가 있으면 자동으로 채워지도록 설정
        api_key = st.text_input("Gemini API Key", value=auto_api_key, type="password")
        if st.button("🔄 시세 업데이트"): st.cache_data.clear(); st.rerun()
        selected_type = st.selectbox("🗂️ 계좌 필터", ["함대 전체"] + list(df['계좌유형'].unique()))
        
    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()
    display_df['안전_수익률'] = display_df.apply(lambda r: get_safe_val(r, ['수익률2', '수익률']), axis=1)
    stock_fetch_list = [(str(row.get('종목코드', '')), get_safe_val(row, ['현재가2', '현재가', '기준가', '매수단가'])) for _, row in display_df.iterrows() if str(row.get('종목코드', '')) and "현금" not in str(row['종목명'])]
    
    with st.spinner("🚀 분석 중..."):
        tcr_results = quant_analyzer.get_tcr_scores_batch(stock_fetch_list, {"flow": 0.4, "trend": 0.4, "vcp": 0.2})

    tab_main, tab_ai = st.tabs(["🚀 관제실", "🤖 AI 브리핑"])

    with tab_main:
        total_eval = display_df['평가금액'].sum()
        total_profit = display_df['평가손익'].sum()
        st.markdown(f"""<div class="kpi-grid">
            <div class="kpi-box"><span class="kpi-label">총 자산</span><span class="kpi-val">{total_eval:,.0f}원</span></div>
            <div class="kpi-box"><span class="kpi-label">누적 손익</span><span class="kpi-val {'text-red' if total_profit>0 else 'text-blue'}">{total_profit:,.0f}원</span></div>
        </div>""", unsafe_allow_html=True)

        for _, row in display_df.sort_values(by='안전_수익률', ascending=False).iterrows():
            now_p = get_safe_val(row, ['현재가2', '현재가', '기준가', '매수단가'])
            st.markdown(f"""<details class="premium-card"><summary><div class="card-header-flex">
                <span class="stock-name">{row['종목명']}</span><span class="val-num">{now_p:,.0f}원</span></div></summary>
                <div style="padding:10px;">수익률: {row['안전_수익률']*100:.2f}%</div></details>""", unsafe_allow_html=True)

    with tab_ai:
        st.subheader("🤖 제미나이 전술 참모")
        user_context = st.text_area("사령관 특별 지시", placeholder="추가 정보를 입력하세요.")
        if st.button("🔥 작전 지시서 생성", use_container_width=True):
            if not api_key: st.error("API Key가 없습니다!")
            else:
                with st.spinner("🧠 최신 통신 규격으로 분석 중..."):
                    report = generate_ai_briefing(api_key, display_df, tcr_results, user_context)
                    st.markdown(f"<div style='background:#0f172a; padding:20px; border-radius:10px; border:1px solid #1e293b;'>{report.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)

except Exception as e: st.error(f"기동 실패: {e}")
