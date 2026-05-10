import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json, requests, time, re
from bs4 import BeautifulSoup
import quant_analyzer

# --- [1] V49.2 정통 규격 CSS ---
st.set_page_config(page_title="거북이 함대 기동 본부 V49.2", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    h1, h2, h3, p, span, div { font-family: 'Urbanist', 'Noto Sans KR', sans-serif; }
    .hq-title { font-size: 1.3rem; color: rgb(70,130,180); font-weight: 800; padding-top: 5px; margin-bottom: 15px; }
    .index-container { display: flex; flex-wrap: wrap; justify-content: space-between; background: #0f172a; padding: 10px 15px; border-radius: 10px; border: 1px solid #1e293b; margin-bottom: 15px; }
    .index-item { display: flex; flex-direction: column; align-items: center; width: 24%; }
    .index-name { font-size: 0.75rem; color: rgb(108,122,137); font-weight: 700; }
    .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }
    .kpi-box { display: flex; flex-direction: column; }
    .kpi-label { font-size: 0.8rem; color: rgb(108,122,137); font-weight: 700; }
    .kpi-val { font-size: 1.5rem; font-weight: 800; letter-spacing: -0.5px; }
    .text-blue { color: rgb(70,130,180) !important; }
    .text-red { color: #ef4444 !important; }
    .text-gray { color: rgb(108,122,137) !important; }
    .text-white { color: #ffffff !important; }
    details.premium-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 10px; margin-bottom: 8px; }
    summary { padding: 14px 16px; cursor: pointer; list-style: none; }
    .card-header-flex { display: flex; justify-content: space-between; align-items: center; width: 100%; gap: 10px; }
    .card-left { display: flex; align-items: center; gap: 8px; width: 35%; overflow: hidden; }
    .card-right { display: flex; justify-content: space-between; align-items: center; width: 65%; }
    @media (max-width: 768px) {
        .kpi-grid { grid-template-columns: repeat(2, 1fr); }
        .card-header-flex { flex-direction: column; }
    }
    </style>
    """, unsafe_allow_html=True)

# --- [2] 데이터 처리 ---
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
        if col not in ['계좌번호', '계좌유형', '종목명', '종목코드']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', '').str.replace('%', ''), errors='coerce').fillna(0)
    return sheet, df[df['종목명'].astype(str).str.strip() != ''], full_df

@st.cache_data(ttl=120)
def get_market_indices():
    indices = {"KOSPI": ("-", "-", "text-gray"), "KOSDAQ": ("-", "-", "text-gray"), "NASDAQ": ("-", "-", "text-gray"), "S&P 500": ("-", "-", "text-gray"), "DOW": ("-", "-", "text-gray"), "VIX": ("-", "-", "text-gray"), "USD/KRW": ("-", "-", "text-gray")}
    try:
        res_main = requests.get("https://finance.naver.com/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        soup_main = BeautifulSoup(res_main.text, 'html.parser')
        for code, cls in [("KOSPI", ".kospi_area"), ("KOSDAQ", ".kosdaq_area")]:
            box = soup_main.select_one(cls)
            if box:
                val, diff, rate = box.select_one(".num").text, box.select_one(".num2").text, box.select_one(".num3").text
                bt = box.select_one(".blind").text
                cl = "text-red" if "상승" in bt else "text-blue" if "하락" in bt else "text-gray"
                indices[code] = (val, f"{'▲' if '상승' in bt else '▼' if '하락' in bt else ''}{diff} ({rate})", cl)
        for code, sym in [("NASDAQ", "NAS@IXIC"), ("S&P 500", "SPI@SPX"), ("DOW", "DJI@DJI"), ("VIX", "VIX@VIX")]:
            res_w = requests.get(f"https://finance.naver.com/world/sise.naver?symbol={sym}", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
            sw = BeautifulSoup(res_w.text, 'html.parser')
            em = sw.select_one("p.no_today em")
            if em:
                val = em.text.strip()
                diff_area = sw.select_one("p.no_exday")
                if diff_area:
                    ems = diff_area.find_all("em")
                    dv, rv = ems[0].text.strip(), ems[1].text.strip()
                    stt = diff_area.select_one("span.blind").text if diff_area.select_one("span.blind") else ""
                    cl = "text-red" if "상승" in stt else "text-blue" if "하락" in stt else "text-gray"
                    indices[code] = (val, f"{'▲' if '상승' in stt else '▼' if '하락' in stt else ''}{dv} ({rv})", cl)
        res_ex = requests.get("https://finance.naver.com/marketindex/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        sx = BeautifulSoup(res_ex.text, 'html.parser')
        ex_box = sx.select_one("#exchangeList > li.on > a.head.usd")
        if ex_box:
            val, diff, blind = ex_box.select_one(".value").text, ex_box.select_one(".change").text, ex_box.select_one(".blind").text
            indices["USD/KRW"] = (val, diff, "text-red" if "상승" in blind else "text-blue")
    except: pass
    return indices

# --- [3] 메인 기동 ---
try:
    sheet, df, full_df = load_data()
    indices = get_market_indices()
    
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V49.2</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        sort_option = st.radio("📊 정렬 기준", ["수익률 순", "당일 등락 순", "종목명 순"], horizontal=True)
        st.divider()
        acc_filter = st.selectbox("🗂️ 계좌 필터", ["함대 전체"] + list(df['계좌유형'].unique()))
        if st.button("🔄 데이터 동기화 (Sync)"):
            st.cache_data.clear()
            st.rerun()

    # 지수 렌더링
    if indices:
        idx_html = '<div class="index-container">'
        for name in ["KOSPI", "KOSDAQ", "NASDAQ", "S&P 500"]:
            v, d, c = indices.get(name, ("-", "-", "text-gray"))
            idx_html += f'<div class="index-item"><span class="index-name">{name}</span><span class="index-val {c}">{v}</span><span class="index-diff {c}">{d}</span></div>'
        idx_html += '</div>'
        st.markdown(idx_html, unsafe_allow_html=True)
        with st.expander("🌍 거시경제 및 보조 지표 (DOW, VIX, 환율)"):
            macro_html = '<div class="index-container" style="background:transparent; border:none; margin:0; padding:0;">'
            for name in ["DOW", "VIX", "USD/KRW"]:
                v, d, c = indices.get(name, ("-", "-", "text-gray"))
                macro_html += f'<div class="index-item" style="width:32%;"><span class="index-name">{name}</span><span class="index-val {c}">{v}</span><span class="index-diff {c}">{d}</span></div>'
            macro_html += '</div>'
            st.markdown(macro_html, unsafe_allow_html=True)

    # 필터 및 데이터 정산
    display_df = df[df['계좌유형'] == acc_filter].copy() if acc_filter != "함대 전체" else df.copy()
    total_eval = display_df['평가금액'].sum()
    total_profit = display_df['평가손익'].sum()
    total_roi = (total_profit / display_df['매수금액'].sum() * 100) if display_df['매수금액'].sum() > 0 else 0
    daily_delta = 0
    for _, r in display_df.iterrows():
        if r.get('전일종가', 0) > 0: daily_delta += (r['현재가2'] - r['전일종가']) * r['잔고수량']
    total_cash = display_df[display_df['종목명'].str.contains('현금|예수금', na=False)]['평가금액'].sum()

    # KPI 렌더링 (사령관님 지정 색상 엄수)
    kpi_html = f"""<div class="kpi-grid">
        <div class="kpi-box"><span class="kpi-label">총 함대 자산</span><span class="kpi-val text-white">{total_eval:,.0f}원</span></div>
        <div class="kpi-box"><span class="kpi-label">총 누적 손익</span><span class="kpi-val {'text-red' if total_profit>0 else 'text-blue'}">{total_profit:,.0f}원 ({total_roi:.2f}%)</span></div>
        <div class="kpi-box"><span class="kpi-label">전일 대비 증감</span><span class="kpi-val {'text-red' if daily_delta>0 else 'text-blue'}">{daily_delta:,.0f}원</span></div>
        <div class="kpi-box"><span class="kpi-label">기동 대기 예수금</span><span class="kpi-val text-blue">{total_cash:,.0f}원</span></div>
    </div>"""
    st.markdown(kpi_html, unsafe_allow_html=True)

    # 정렬 및 카드 출력
    yc = '수익률2' if '수익률2' in display_df.columns else '수익률'
    display_df['gap'] = display_df.apply(lambda r: ((r['현재가2']-r['전일종가'])/r['전일종가']*100) if r.get('전일종가',0)>0 else 0, axis=1)
    if sort_option == "수익률 순": display_df = display_df.sort_values(yc, ascending=False)
    elif sort_option == "당일 등락 순": display_df = display_df.sort_values('gap', ascending=False)
    else: display_df = display_df.sort_values('종목명')

    html_cards = ""
    for _, row in display_df.iterrows():
        now_p = row.get('현재가2', row.get('매수단가', 0))
        y_v = row.get(yc, 0)
        tcr = quant_analyzer.get_tcr_score(str(row.get('종목코드', '')), now_p)
        cl = "text-red" if y_v > 0 else "text-blue" if y_v < 0 else "text-gray"
        
        html_cards += f"""
        <details class="premium-card">
            <summary><div class="card-header-flex">
                <span class="stock-name" style="font-weight:700;">{row['종목명']}</span>
                <div class="card-right">
                    <span class="val-num {cl}">{now_p:,.0f}원 ({y_v*100:.2f}%)</span>
                </div>
            </div></summary>
            <div class="card-body" style="background:#020617; padding:15px; border-top:1px solid #1e293b;">
                <div style="color:rgb(70,130,180); font-weight:700;">평가금액: {row['평가금액']:,.0f}원</div>
                <div style="color:{tcr['color']};">🔥 확신율: {tcr['score']}% ({tcr['status']})</div>
            </div>
        </details>""", unsafe_allow_html=True)
        
    st.markdown(html_cards, unsafe_allow_html=True)
    st.markdown(quant_analyzer.get_analysis_legend(), unsafe_allow_html=True)

except Exception as e: st.error(f"원복 실패: {e}")
