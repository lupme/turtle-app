import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json, requests, time, re
from bs4 import BeautifulSoup
import quant_analyzer

st.set_page_config(page_title="거북이 함대 기동 본부 V49.2", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    h1, h2, h3, p, span, div { font-family: 'Urbanist', 'Noto Sans KR', sans-serif; }
    .hq-title { font-size: 1.3rem; color: rgb(70,130,180); font-weight: 800; padding-top: 5px; margin-bottom: 15px; }
    .index-container { display: flex; flex-wrap: wrap; justify-content: space-between; background: #0f172a; padding: 10px 15px; border-radius: 10px; border: 1px solid #1e293b; margin-bottom: 15px; }
    .index-item { display: flex; flex-direction: column; align-items: center; width: 14%; margin-bottom: 5px; }
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
    @media (max-width: 768px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } .card-header-flex { flex-direction: column; } .index-item { width: 30%; } }
    </style>
    """, unsafe_allow_html=True)

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
    for col in df.columns:
        if col not in ['계좌번호', '계좌유형', '종목명', '종목코드', '상품', '구분']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', '').str.replace('%', ''), errors='coerce').fillna(0)
    return sheet, df[df['종목명'].astype(str).str.strip() != ''], full_df

def get_market_indices():
    indices = {"KOSPI": ("-", "-", "text-gray"), "KOSDAQ": ("-", "-", "text-gray"), "NASDAQ": ("-", "-", "text-gray"), "S&P 500": ("-", "-", "text-gray"), "DOW": ("-", "-", "text-gray"), "VIX": ("-", "-", "text-gray"), "USD/KRW": ("-", "-", "text-gray")}
    try:
        # 국내 지수 및 환율 수집
        res_main = requests.get("https://finance.naver.com/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        soup_main = BeautifulSoup(res_main.text, 'html.parser')
        for code, cls in [("KOSPI", ".kospi_area"), ("KOSDAQ", ".kosdaq_area")]:
            box = soup_main.select_one(cls)
            if box:
                val, diff, rate = box.select_one(".num").text, box.select_one(".num2").text, box.select_one(".num3").text
                bt = box.select_one(".blind").text
                indices[code] = (val, f"{'▲' if '상승' in bt else '▼' if '하락' in bt else ''}{diff} ({rate})", "text-red" if "상승" in bt else "text-blue")
        
        ex_box = soup_main.select_one("#exchangeList > li.on > a.head.usd")
        if ex_box:
            indices["USD/KRW"] = (ex_box.select_one(".value").text, ex_box.select_one(".change").text, "text-red" if "상승" in ex_box.select_one(".blind").text else "text-blue")

        # 해외 지수 수집 (누락되었던 로직 복원)
        world_symbols = {"NASDAQ": "NAS@IXIC", "S&P 500": "SPI@SPX", "DOW": "DJI@DJI", "VIX": "SPI@SPVXSP"}
        for key, sym in world_symbols.items():
            try:
                w_url = f"https://finance.naver.com/world/sise.naver?symbol={sym}"
                w_res = requests.get(w_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
                w_soup = BeautifulSoup(w_res.text, 'html.parser')
                val = w_soup.select_one(".no_today .blind").text
                ex_el = w_soup.select_one(".no_exday")
                diff = ex_el.select(".blind")[0].text
                rate = ex_el.select(".blind")[1].text
                is_up = "상승" in ex_el.text or "+" in str(ex_el)
                sign = "▲" if is_up else "▼"
                color = "text-red" if is_up else "text-blue"
                indices[key] = (val, f"{sign}{diff} ({rate}%)", color)
            except:
                pass
    except: pass
    return indices

def get_safe_val(r, cols):
    for c in cols:
        v = r.get(c, 0)
        if v != 0 and pd.notna(v): return v
    return 0

try:
    sheet, df, full_df = load_data()
    indices = get_market_indices()
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V49.2</div>', unsafe_allow_html=True)
    
    # 지수 패널 UI 렌더링
    idx_html = '<div class="index-container">'
    for k, v in indices.items():
        idx_html += f'<div class="index-item"><span class="kpi-label" style="margin-bottom:2px;">{k}</span><span class="{v[2]}" style="font-size:1.1rem; font-weight:800;">{v[0]}</span><span style="font-size:0.75rem; color:#94a3b8;">{v[1]}</span></div>'
    idx_html += '</div>'
    st.markdown(idx_html, unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        
        with st.expander("🛠️ 함대 버전 관리 (VCS)", expanded=True):
            st.markdown("**현재 가동:** `V49.2 (정통 베이스라인)`")
            st.markdown("**직전 안정:** `-`")
            st.markdown("**패치 내역:**")
            st.markdown("- 원본 100% 복원\n- 나스닥/S&P 등 해외지수 크롤링 로직 추가")
            
        st.divider()
        sort_option = st.radio("📊 정렬 기준", ["수익률 순", "당일 등락 순", "종목명 순"], horizontal=True)
        acc_filter = st.selectbox("🗂️ 계좌 필터", ["함대 전체"] + list(df['계좌유형'].unique()))
        st.divider()
        if st.button("🚀 데이터 동기화 (Sync)"):
            st.cache_data.clear()
            st.rerun()

    display_df = df[df['계좌유형'] == acc_filter].copy() if acc_filter != "함대 전체" else df.copy()
    
    total_eval = display_df['평가금액'].sum()
    total_profit = display_df['평가손익'].sum()
    daily_delta = sum((get_safe_val(r,['현재가2','현재가','기준가','매수단가']) - get_safe_val(r,['전일종가2','전일종가'])) * r.get('잔고수량',0) for _,r in display_df.iterrows() if get_safe_val(r,['전일종가2','전일종가']) > 0)
    total_cash = display_df[display_df['종목명'].str.contains('현금|예수금', na=False)]['평가금액'].sum()

    kpi_html = f"""<div class="kpi-grid">
        <div class="kpi-box"><span class="kpi-label">총 함대 자산</span><span class="kpi-val text-white">{total_eval:,.0f}원</span></div>
        <div class="kpi-box"><span class="kpi-label">총 누적 손익</span><span class="kpi-val {'text-red' if total_profit>0 else 'text-blue'}">{total_profit:,.0f}원</span></div>
        <div class="kpi-box"><span class="kpi-label">전일 대비 증감</span><span class="kpi-val {'text-red' if daily_delta>0 else 'text-blue'}">{daily_delta:,.0f}원</span></div>
        <div class="kpi-box"><span class="kpi-label">기동 대기 예수금</span><span class="kpi-val text-blue">{total_cash:,.0f}원</span></div>
    </div>"""
    st.markdown(kpi_html, unsafe_allow_html=True)

    display_df['temp_yield'] = display_df.apply(lambda r: get_safe_val(r, ['수익률2', '수익률']), axis=1)
    if sort_option == "수익률 순": display_df = display_df.sort_values('temp_yield', ascending=False)
    elif sort_option == "종목명 순": display_df = display_df.sort_values('종목명')

    for _, row in display_df.iterrows():
        now_p = get_safe_val(row, ['현재가2', '현재가', '기준가', '매수단가'])
        tcr = quant_analyzer.get_tcr_score(str(row.get('종목코드', '')), now_p)
        st.markdown(f"""<details class="premium-card"><summary><div class="card-header-flex">
            <span style="font-weight:700;">{row['종목명']}</span>
            <span class="val-num">{now_p:,.0f}원</span></div></summary>
            <div style="padding:15px; background:#020617; border-top:1px solid #1e293b;">
            <p>평가금액: {row['평가금액']:,.0f}원 / 수익률: {row['temp_yield']*100 if -1<row['temp_yield']<1 else row['temp_yield']:.2f}%</p>
            <p style="color:{tcr['color']};">🔥 확신율: {tcr['score']}% ({tcr['status']})</p></div></details>""", unsafe_allow_html=True)
            
    st.markdown(quant_analyzer.get_analysis_legend(), unsafe_allow_html=True)
    
except Exception as e: st.error(f"기동 실패: {e}")
