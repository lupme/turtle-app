import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import time

# [핵심] 분석국 모듈 유지
import quant_analyzer

# --- [1] 시스템 설정 및 CSS (V47 규격 유지) ---
st.set_page_config(page_title="거북이 함대 기동 본부 V48", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    h1, h2, h3, p, span, div { font-family: 'Urbanist', 'Noto Sans KR', sans-serif; }
    .hq-title { font-size: 1.3rem; color: rgb(70,130,180); font-weight: 800; letter-spacing: 1px; padding-top: 5px; margin-bottom: 15px; }
    
    .index-container { display: flex; flex-wrap: wrap; justify-content: space-between; background: #0f172a; padding: 10px 15px; border-radius: 10px; border: 1px solid #1e293b; margin-bottom: 15px; gap: 8px 0; }
    .index-item { display: flex; flex-direction: column; align-items: center; width: 24%; }
    .index-name { font-size: 0.75rem; color: rgb(108,122,137); font-weight: 700; margin-bottom: 2px; }
    .index-val { font-size: 1.05rem; font-weight: 800; color: #ffffff; }
    .index-diff { font-size: 0.75rem; font-weight: 600; }
    
    .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }
    .kpi-box { display: flex; flex-direction: column; }
    .kpi-label { font-size: 0.8rem; color: rgb(108,122,137); font-weight: 700; margin-bottom: 4px; }
    .kpi-val { font-size: 1.5rem; font-weight: 800; color: #ffffff; letter-spacing: -0.5px; }
    .kpi-delta { font-size: 0.85rem; font-weight: 700; margin-left: 6px; }

    details.premium-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 10px; margin-bottom: 8px; }
    details.premium-card summary { padding: 14px 16px; cursor: pointer; list-style: none; }
    
    .card-header-flex { display: flex; justify-content: space-between; align-items: center; width: 100%; gap: 10px; }
    .card-left { display: flex; align-items: center; gap: 8px; width: 35%; overflow: hidden; }
    .card-right { display: flex; justify-content: space-between; align-items: center; width: 65%; }
    
    .status-dot { min-width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .dot-red { background-color: #ef4444; } .dot-blue { background-color: rgb(70,130,180); } .dot-gray { background-color: rgb(108,122,137); }
    .stock-name { font-size: 1rem; font-weight: 700; color: #ffffff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    
    .val-box { display: flex; flex-direction: column; align-items: center; width: 33%; text-align: center; }
    .val-label { font-size: 0.65rem; font-weight: 600; color: rgb(108,122,137); margin-bottom: 2px; }
    .val-num { font-size: 1rem; font-weight: 800; }
    
    .text-red { color: #ef4444; } .text-blue { color: rgb(70,130,180); } .text-gray { color: rgb(108,122,137); } .text-white { color: #ffffff; }
    
    .card-body { background-color: #020617; padding: 16px; border-top: 1px solid #1e293b; border-radius: 0 0 10px 10px; }
    .metric-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
    .metric-box { display: flex; flex-direction: column; }
    .metric-label { font-size: 0.75rem; font-weight: 600; color: rgb(108,122,137); margin-bottom: 2px; }
    .metric-value { font-size: 1.05rem; font-weight: 700; color: #ffffff; }
    .metric-highlight { color: rgb(70,130,180); font-weight: 800; font-size: 1.1rem; }
    
    @media (max-width: 768px) {
        .kpi-grid { grid-template-columns: repeat(2, 1fr); }
        .card-header-flex { flex-direction: column; align-items: stretch; }
        .card-left { width: 100%; border-bottom: 1px dashed rgba(30,41,59, 0.7); padding-bottom: 8px; }
        .card-right { width: 100%; }
        .val-box { width: 32%; }
    }
    </style>
    """, unsafe_allow_html=True)

# --- [2] 데이터 처리 함수 ---
def safe_update(sheet, row, col_name, val, idmap):
    if col_name in idmap and idmap[col_name] > 0:
        sheet.update_cell(row, idmap[col_name], val)

@st.cache_data(ttl=120)
def get_market_indices():
    indices = {"KOSPI": ("-", "-", "text-gray"), "KOSDAQ": ("-", "-", "text-gray"), "NASDAQ": ("-", "-", "text-gray"), "S&P 500": ("-", "-", "text-gray"), "DOW": ("-", "-", "text-gray"), "VIX": ("-", "-", "text-gray"), "USD/KRW": ("-", "-", "text-gray")}
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res_main = requests.get("https://finance.naver.com/", headers=headers, timeout=3)
        soup_main = BeautifulSoup(res_main.text, 'html.parser')
        for code, cls in [("KOSPI", ".kospi_area"), ("KOSDAQ", ".kosdaq_area")]:
            box = soup_main.select_one(cls)
            if box:
                val, diff, rate = box.select_one(".num").text, box.select_one(".num2").text, box.select_one(".num3").text
                b_txt = box.select_one(".blind").text
                cl = "text-red" if "상승" in b_txt else "text-blue" if "하락" in b_txt else "text-gray"
                sign = "▲" if "상승" in b_txt else "▼" if "하락" in b_txt else ""
                indices[code] = (val, f"{sign}{diff} ({rate})", cl)
        # (기타 지수 생략 - V47과 동일)
    except: pass
    return indices

def get_gspread_client():
    key_info = json.loads(st.secrets["google_credentials"])
    if "private_key" in key_info:
        key_info["private_key"] = key_info["private_key"].replace("\\n", "\n")
    return gspread.authorize(Credentials.from_service_account_info(key_info, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']))

@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0").get_worksheet(0)
    full_df = pd.DataFrame(sheet.get_all_records())
    df = full_df.copy()
    for col in df.columns:
        if col not in ['계좌번호', '계좌유형', '종목명', '종목코드', '상품', '구분']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', '').str.replace('%', ''), errors='coerce').fillna(0)
    df = df[df['종목명'].astype(str).str.strip() != '']
    df = df[~df['종목명'].astype(str).str.contains('합계|총계|총액|총자산', na=False)]
    return sheet, df, full_df

# --- [3] 관제 화면 기동 ---
try:
    sheet, df, full_df = load_data()
    indices = get_market_indices()
    
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V48.0</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        # 🚨 [신규] 정렬 기준 선택 기능
        st.subheader("📊 리스트 정렬 기준")
        sort_option = st.radio("기준 선택", ["수익률 순", "당일 등락 순", "종목명 순"], horizontal=True)
        st.divider()
        # (기존 작전 모드 등 유지...)
        mode = st.radio("작전 모드", ["기존 종목 매매", "데이터 강제 수정", "신규 종목 추가", "종목 완전 삭제"])
        # ... (중략 - 기존 사이드바 로직 동일)

    # 지수 및 KPI 렌더링 (V47 동일)
    # ...

    display_df = df.copy() # 필터 로직 생략

    # 🚨 [핵심] 정렬을 위한 데이터 전처리
    yield_col = '수익률2' if '수익률2' in display_df.columns else '수익률'
    display_df['당일등락율'] = display_df.apply(lambda row: ((row['현재가2'] - row['전일종가']) / row['전일종가'] * 100) if row.get('전일종가', 0) > 0 else 0, axis=1)

    # 🚨 [핵심] 사용자 선택에 따른 정렬 실행
    if sort_option == "수익률 순":
        display_df = display_df.sort_values(by=yield_col, ascending=False)
    elif sort_option == "당일 등락 순":
        display_df = display_df.sort_values(by='당일등락율', ascending=False)
    else:
        display_df = display_df.sort_values(by='종목명')

    # 리스트 렌더링
    html_cards = ""
    for _, row in display_df.iterrows():
        # (종목 카드 생성 로직 - V47과 동일하게 유지하되, 정렬된 순서대로 출력)
        # ... (이하 생략)
        
    st.markdown(html_cards, unsafe_allow_html=True)
    st.markdown(quant_analyzer.get_analysis_legend(), unsafe_allow_html=True)

except Exception as e: st.error(f"함대 기동 중지: {e}")
