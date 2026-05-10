import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json, requests, time, re
from bs4 import BeautifulSoup
import quant_analyzer

# --- [1] V49.1 정통 규격 CSS ---
st.set_page_config(page_title="거북이 함대 기동 본부 V49.1", layout="wide", initial_sidebar_state="expanded")

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
    .kpi-val { font-size: 1.5rem; font-weight: 800; letter-spacing: -0.5px; }
    .kpi-delta { font-size: 0.85rem; font-weight: 700; margin-left: 6px; }
    .text-blue { color: rgb(70,130,180) !important; }
    .text-red { color: #ef4444 !important; }
    .text-gray { color: rgb(108,122,137) !important; }
    .text-white { color: #ffffff !important; }
    details.premium-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 10px; margin-bottom: 8px; transition: all 0.2s; }
    details.premium-card:hover { border-color: rgb(70,130,180); }
    details.premium-card summary { padding: 14px 16px; cursor: pointer; list-style: none; }
    details.premium-card summary::-webkit-details-marker { display: none; }
    .card-header-flex { display: flex; justify-content: space-between; align-items: center; width: 100%; gap: 10px; }
    .card-left { display: flex; align-items: center; gap: 8px; width: 35%; overflow: hidden; }
    .card-right { display: flex; justify-content: space-between; align-items: center; width: 65%; }
    .status-dot { min-width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .dot-red { background-color: #ef4444; } .dot-blue { background-color: rgb(70,130,180); } .dot-gray { background-color: rgb(108,122,137); }
    .stock-name { font-size: 1rem; font-weight: 700; color: #ffffff; }
    .val-box { display: flex; flex-direction: column; align-items: center; width: 33%; }
    .val-label { font-size: 0.65rem; color: rgb(108,122,137); font-weight: 600; margin-bottom: 2px; }
    .val-num { font-size: 1rem; font-weight: 800; }
    @media (max-width: 768px) {
        .kpi-grid { grid-template-columns: repeat(2, 1fr); }
        .kpi-val { font-size: 1.15rem; }
        .card-header-flex { flex-direction: column; align-items: stretch; }
        .card-left { width: 100%; border-bottom: 1px dashed rgba(108,122,137, 0.4); padding-bottom: 8px; }
        .card-right { width: 100%; }
        .val-box { width: 32%; }
    }
    </style>
    """, unsafe_allow_html=True)

# --- [2] 데이터 로드 ---
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
    df = df[df['종목명'].astype(str).str.strip() != '']
    df = df[~df['종목명'].astype(str).str.contains('합계|총계|총액|총자산', na=False)]
    return sheet, df, full_df

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
    
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V49.1</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        
        sort_option = st.radio("📊 리스트 정렬 기준", ["수익률 순", "당일 등락 순", "종목명 순"], horizontal=True)
        st.divider()
        
        acc_types = ["함대 전체"] + list(df['계좌유형'].unique())
        selected_type = st.selectbox("🗂️ 계좌 필터", acc_types)
        st.divider()
        
        mode = st.radio("작전 모드", ["기존 종목 매매", "데이터 강제 수정", "신규 종목 추가", "종목 완전 삭제"])
        acc_opts = [f"{r['계좌유형']} [{r['계좌번호']}]" for _, r in full_df[['계좌유형', '계좌번호']].drop_duplicates().iterrows() if str(r['계좌번호']).strip() != '']
        sel_acc_str = st.selectbox("작전 계좌 선택", acc_opts) if acc_opts else ""
        sel_acc = sel_acc_str.split('[')[-1].replace(']', '').strip() if sel_acc_str else ""
        
        if "신규" not in mode:
            s_list = [s for s in full_df[full_df['계좌번호'].astype(str).str.strip() == sel_acc]['종목명'].dropna().tolist() if str(s).strip() != '']
            s_name = st.selectbox("작전 종목 선택", s_list if s_list else ["없음"])
            if "매매" in mode: action = st.radio("구분", ["매수", "매도"], horizontal=True)
        else:
            s_name, s_code = st.text_input("신규 종목명"), st.text_input("종목코드 (6자리)")
            
        if "삭제" not in mode:
            qty, price = st.number_input("수량", min_value=0, value=None, step=1), st.number_input("현재가/단가", min_value=0, value=None, step=100)
        
        if st.button("명령 확정 (Sync)"):
            st.cache_data.clear()
            st.success("동기화 완료.")
            time.sleep(1)
            st.rerun()

    # 지수 렌더링
    if indices:
        idx_html = '<div class="index-container">'
        for name in ["KOSPI", "KOSDAQ", "NASDAQ", "S&P 500"]:
            val, diff, cl = indices.get(name, ("-", "-", "text-gray"))
            idx_html += f'<div class="index-item"><span class="index-name">{name}</span><span class="index-val {cl}">{val}</span><span class="index-diff {cl}">{diff}</span></div>'
        idx_html += '</div>'
        st.markdown(idx_html, unsafe_allow_html=True)
        
        with st.expander("🌍 거시경제 및 보조 지표 (DOW, VIX, 환율)"):
            macro_html = '<div class="index-container" style="background:transparent; border:none; margin:0; padding:0;">'
            for name in ["DOW", "VIX", "USD/KRW"]:
                val, diff, cl = indices.get(name, ("-", "-", "text-gray"))
                macro_html += f'<div class="index-item" style="width:32%;"><span class="index-name">{name}</span><span class="index-val {cl}">{val}</span><span class="index-diff {cl}">{diff}</span></div>'
            macro_html += '</div>'
            st.markdown(macro_html, unsafe_allow_html=True)

    # 🚨 [중요] 비어있는 값을 0으로 오해하지 않도록 안전한 데이터 파싱 함수 추가
    def get_safe_val(r, cols):
        for c in cols:
            v = r.get(c, 0)
            if v != 0 and pd.notna(v): return v
        return 0

    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()

    total_eval = display_df['평가금액'].sum()
    total_profit = display_df['평가손익'].sum()
    total_roi = (total_profit / display_df['매수금액'].sum() * 100) if display_df['매수금액'].sum() > 0 else 0
    daily_delta = 0
    
    for _, r in display_df.iterrows():
        p_now = get_safe_val(r, ['현재가2', '현재가', '기준가', '매수단가'])
        p_prev = get_safe_val(r, ['전일종가2', '전일종가'])
        if p_prev > 0:
            daily_delta += (p_now - p_prev) * r.get('잔고수량', 0)
            
    total_cash = display_df[display_df['종목명'].astype(str).str.contains('현금|예수금', na=False)]['평가금액'].sum()

    kpi_html = f"""<div class="kpi-grid">
        <div class="kpi-box"><span class="kpi-label">총 함대 자산</span><span class="kpi-val text-white">{total_eval:,.0f}원</span></div>
        <div class="kpi-box"><span class="kpi-label">총 누적 손익</span><span class="kpi-val {'text-red' if total_profit>0 else 'text-blue'}">{total_profit:,.0f}원 <span class="kpi-delta">({total_roi:.2f}%)</span></span></div>
        <div class="kpi-box"><span class="kpi-label">전일 대비 증감</span><span class="kpi-val {'text-red' if daily_delta>0 else 'text-blue'}">{'▲' if daily_delta>0 else '▼' if daily_delta<0 else ''}{abs(daily_delta):,.0f}원</span></div>
        <div class="kpi-box"><span class="kpi-label">기동 대기 예수금</span><span class="kpi-val text-blue">{total_cash:,.0f}원</span></div>
    </div>"""
    st.markdown(kpi_html, unsafe_allow_html=True)

    # 🚨 정렬을 위한 안전한 등락률 계산 적용
    def calc_gap(r):
        n = get_safe_val(r, ['현재가2', '현재가', '기준가', '매수단가'])
        p = get_safe_val(r, ['전일종가2', '전일종가'])
        if p > 0: return ((n - p) / p) * 100
        return 0

    display_df['안전_수익률'] = display_df.apply(lambda r: get_safe_val(r, ['수익률2', '수익률']), axis=1)
    display_df['당일등락율'] = display_df.apply(calc_gap, axis=1)

    if sort_option == "수익률 순": display_df = display_df.sort_values(by='안전_수익률', ascending=False)
    elif sort_option == "당일 등락 순": display_df = display_df.sort_values(by='당일등락율', ascending=False)
    else: display_df = display_df.sort_values(by='종목명')

    html_cards = ""
    for _, row in display_df.iterrows():
        # 🚨 TDF 및 HTS 오차(현재가2/전일종가2) 완벽 반영
        now_p = get_safe_val(row, ['현재가2', '현재가', '기준가', '매수단가'])
        prev_p = get_safe_val(row, ['전일종가2', '전일종가'])
        y_val = row['안전_수익률']
        
        diff = now_p - prev_p if prev_p > 0 else 0
        rate = (diff / prev_p * 100) if prev_p > 0 else 0
        tcr_info = quant_analyzer.get_tcr_score(str(row.get('종목코드', '')), now_p)
        
        cl = "text-red" if y_val > 0 else "text-blue" if y_val < 0 else "text-gray"
        dt = "dot-red" if y_val > 0 else "dot-blue" if y_val < 0 else "dot-gray"
        ds = f"<span class='{'text-red' if diff>0 else 'text-blue' if diff<0 else 'text-gray'}'>{'▲' if diff>0 else '▼' if diff<0 else ''}{abs(diff):,.0f}({rate:.1f}%)</span>"
        
        html_cards += f"""
        <details class="premium-card">
            <summary><div class="card-header-flex">
                <div class="card-left"><div class="status-dot {dt}"></div><span class="stock-name">{row['종목명']}</span></div>
                <div class="card-right">
                    <div class="val-box"><span class="val-label">현재가</span><span class="val-num {cl}">{now_p:,.0f}</span></div>
                    <div class="val-box"><span class="val-label">당일비</span><span class="val-num">{ds}</span></div>
                    <div class="val-box"><span class="val-label">수익률</span><span class="val-num {cl}">{y_val*100 if -1<y_val<1 else y_val:.2f}%</span></div>
                </div>
            </div></summary>
            <div class="card-body">
                <div class="metric-grid" style="display:grid; grid-template-columns:repeat(2,1fr); gap:12px; background:#020617; padding:15px; border-radius:0 0 10px 10px; border-top:1px solid #1e293b;">
                    <div class="metric-box"><div class="metric-label" style="font-size:0.75rem; color:rgb(108,122,137);">평가 금액</div><div class="metric-value" style="font-size:1.05rem; font-weight:700; color:rgb(70,130,180);">{row['평가금액']:,.0f}원</div></div>
                    <div class="metric-box"><div class="metric-label" style="font-size:0.75rem; color:rgb(108,122,137);">🔥 확신율 (TCR)</div><div class="metric-value" style="font-size:1.05rem; font-weight:700; color:{tcr_info['color']};">{tcr_info['score']}% <span style='font-size:0.7rem;'>({tcr_info['status']})</span></div></div>
                    <div class="metric-box"><div class="metric-label" style="font-size:0.75rem; color:rgb(108,122,137);">매수 금액</div><div class="metric-value" style="font-size:1.05rem; font-weight:700;">{row['매수금액']:,.0f}원</div></div>
                    <div class="metric-box"><div class="metric-label" style="font-size:0.75rem; color:rgb(108,122,137);">보유 수량</div><div class="metric-value" style="font-size:1.05rem; font-weight:700;">{row['잔고수량']:,.0f}주</div></div>
                </div>
            </div>
        </details>"""
        
    st.markdown(html_cards, unsafe_allow_html=True)
    st.markdown(quant_analyzer.get_analysis_legend(), unsafe_allow_html=True)

except Exception as e: st.error(f"함대 기동 중지: {e}")
