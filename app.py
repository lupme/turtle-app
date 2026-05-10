import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json, requests, time, re
from bs4 import BeautifulSoup
import quant_analyzer

# 앱 설정 및 스타일 (임포트 직후 실행)
st.set_page_config(page_title="거북이 함대 기동 본부 V49.3", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    h1, h2, h3, p, span, div { font-family: 'Urbanist', 'Noto Sans KR', sans-serif; }
    .hq-title { font-size: 1.3rem; color: rgb(70,130,180); font-weight: 800; padding-top: 5px; margin-bottom: 15px; }
    .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }
    .kpi-box { display: flex; flex-direction: column; }
    .kpi-label { font-size: 0.8rem; color: rgb(108,122,137); font-weight: 700; }
    .kpi-val { font-size: 1.5rem; font-weight: 800; letter-spacing: -0.5px; }
    .text-blue { color: rgb(70,130,180) !important; }
    .text-red { color: #ef4444 !important; }
    .text-white { color: #ffffff !important; }
    details.premium-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 10px; margin-bottom: 8px; }
    summary { padding: 14px 16px; cursor: pointer; list-style: none; }
    .card-header-flex { display: flex; justify-content: space-between; align-items: center; width: 100%; gap: 10px; }
    </style>
    """, unsafe_allow_html=True)

def get_gspread_client():
    key_info = json.loads(st.secrets["google_credentials"])
    if "private_key" in key_info: key_info["private_key"] = key_info["private_key"].replace("\\n", "\n")
    return gspread.authorize(Credentials.from_service_account_info(key_info, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']))

@st.cache_data(ttl=60)
def load_all_data():
    client = get_gspread_client()
    # 사령관님의 구글 시트 URL
    doc = client.open_by_url("https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0")
    
    # 1. 자산 데이터 로드
    main_sheet = doc.get_worksheet(0)
    full_df = pd.DataFrame(main_sheet.get_all_records())
    df = full_df.copy()
    for col in df.columns:
        if col not in ['계좌번호', '계좌유형', '종목명', '종목코드', '상품', '구분']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', '').str.replace('%', ''), errors='coerce').fillna(0)
    
    # 2. Control_Room 가중치 로드
    weights = {"flow": 0.4, "trend": 0.4, "vcp": 0.2} # 기본값
    try:
        # 시트 이름이 'CONTROL' 혹은 'Control_Room'인지 확인 필요
        ctrl_sheet = doc.worksheet("Control_Room")
        ctrl_df = pd.DataFrame(ctrl_sheet.get_all_records())
        if not ctrl_df.empty:
            weights["flow"] = float(ctrl_df.iloc[0].get('수급가중치', 0.4))
            weights["trend"] = float(ctrl_df.iloc[0].get('추세가중치', 0.4))
            weights["vcp"] = float(ctrl_df.iloc[0].get('VCP가중치', 0.2))
    except Exception as e:
        st.sidebar.warning(f"Control_Room 로드 실패 (기본값 가동): {e}")
        
    return main_sheet, df[df['종목명'].astype(str).str.strip() != ''], weights

def get_market_indices():
    indices = {"KOSPI": ("-", "-", "text-gray"), "USD/KRW": ("-", "-", "text-gray")}
    try:
        res_main = requests.get("https://finance.naver.com/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        soup = BeautifulSoup(res_main.text, 'html.parser')
        box = soup.select_one(".kospi_area")
        if box:
            indices["KOSPI"] = (box.select_one(".num").text, f"{box.select_one('.num2').text} ({box.select_one('.num3').text})", "text-red" if "상승" in box.select_one(".blind").text else "text-blue")
    except: pass
    return indices

def get_safe_val(r, cols):
    for c in cols:
        v = r.get(c, 0)
        if v != 0 and pd.notna(v): return v
    return 0

# 메인 실행부
try:
    sheet, df, current_weights = load_all_data()
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V49.3</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        st.write(f"현재 가중치: 수급({current_weights['flow']}), 추세({current_weights['trend']}), VCP({current_weights['vcp']})")
        if st.button("🚀 데이터 동기화 (Sync)"):
            st.cache_data.clear()
            st.rerun()

    # KPI 계산
    total_eval = df['평가금액'].sum()
    total_profit = df['평가손익'].sum()
    daily_delta = sum((get_safe_val(r,['현재가2','현재가','기준가','매수단가']) - get_safe_val(r,['전일종가2','전일종가'])) * r.get('잔고수량',0) for _,r in df.iterrows() if get_safe_val(r,['전일종가2','전일종가']) > 0)
    total_cash = df[df['종목명'].str.contains('현금|예수금', na=False)]['평가금액'].sum()

    st.markdown(f"""<div class="kpi-grid">
        <div class="kpi-box"><span class="kpi-label">총 함대 자산</span><span class="kpi-val text-white">{total_eval:,.0f}원</span></div>
        <div class="kpi-box"><span class="kpi-label">총 누적 손익</span><span class="kpi-val {'text-red' if total_profit>0 else 'text-blue'}">{total_profit:,.0f}원</span></div>
        <div class="kpi-box"><span class="kpi-label">전일 대비 증감</span><span class="kpi-val {'text-red' if daily_delta>0 else 'text-blue'}">{daily_delta:,.0f}원</span></div>
        <div class="kpi-box"><span class="kpi-label">기동 대기 예수금</span><span class="kpi-val text-blue">{total_cash:,.0f}원</span></div>
    </div>""", unsafe_allow_html=True)

    # 종목 리스트 출력
    for _, row in df.iterrows():
        now_p = get_safe_val(row, ['현재가2', '현재가', '기준가', '매수단가'])
        tcr = quant_analyzer.get_tcr_score(str(row.get('종목코드', '')), now_p, weights=current_weights)
        yld = get_safe_val(row, ['수익률2', '수익률'])
        
        st.markdown(f"""<details class="premium-card"><summary><div class="card-header-flex">
            <span style="font-weight:700;">{row['종목명']}</span>
            <span class="val-num">{now_p:,.0f}원</span></div></summary>
            <div style="padding:15px; background:#020617; border-top:1px solid #1e293b;">
            <p>수익률: {yld*100 if -1<yld<1 else yld:.2f}%</p>
            <p style="color:{tcr['color']};">🔥 확신율: {tcr['score']}% ({tcr['status']})</p></div></details>""", unsafe_allow_html=True)
    
    st.markdown(quant_analyzer.get_analysis_legend(current_weights), unsafe_allow_html=True)

except Exception as e:
    st.error(f"함대 기동 오류 발생: {e}")
