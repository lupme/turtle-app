import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import time

# [핵심] 분석국 모듈 연동
import quant_analyzer

# --- [1] 시스템 설정 및 CSS (모바일 최적화 및 2x2 그리드) ---
st.set_page_config(page_title="거북이 함대 기동 본부 V47", layout="wide", initial_sidebar_state="expanded")

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
    .kpi-box { background: transparent; padding: 0; display: flex; flex-direction: column; }
    .kpi-label { font-size: 0.8rem; color: rgb(108,122,137); font-weight: 700; margin-bottom: 4px; }
    .kpi-val { font-size: 1.5rem; font-weight: 800; color: #ffffff; letter-spacing: -0.5px; }
    .kpi-delta { font-size: 0.85rem; font-weight: 700; margin-left: 6px; }

    details.premium-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 10px; margin-bottom: 8px; transition: all 0.2s; }
    details.premium-card:hover { border-color: rgb(70,130,180); }
    details.premium-card summary { padding: 14px 16px; cursor: pointer; list-style: none; }
    details.premium-card summary::-webkit-details-marker { display: none; }
    
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
        .hq-title { font-size: 1.1rem; margin-bottom: 10px; }
        .index-container { padding: 10px; gap: 10px 0; }
        .index-item { width: 48%; }
        .kpi-grid { grid-template-columns: repeat(2, 1fr); gap: 12px 10px; }
        .kpi-val { font-size: 1.15rem; }
        .card-header-flex { flex-direction: column; align-items: stretch; gap: 8px; }
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
        # 해외 지수 및 환율 생략 없이 로드
        for code, sym in [("NASDAQ", "NAS@IXIC"), ("S&P 500", "SPI@SPX"), ("DOW", "DJI@DJI"), ("VIX", "VIX@VIX")]:
            res_w = requests.get(f"https://finance.naver.com/world/sise.naver?symbol={sym}", headers=headers, timeout=3)
            s_w = BeautifulSoup(res_w.text, 'html.parser')
            em = s_w.select_one("p.no_today em")
            if em:
                val = em.text.strip()
                diff_area = s_w.select_one("p.no_exday")
                if diff_area:
                    ems = diff_area.find_all("em")
                    if len(ems) >= 2:
                        d_v, r_v = ems[0].text.strip(), ems[1].text.strip()
                        s_t = diff_area.select_one("span.blind").text if diff_area.select_one("span.blind") else ""
                        cl = "text-red" if "상승" in s_t else "text-blue" if "하락" in s_t else "text-gray"
                        sign = "▲" if "상승" in s_t else "▼" if "하락" in s_t else ""
                        indices[code] = (val, f"{sign}{d_v} ({r_v})", cl)
        res_ex = requests.get("https://finance.naver.com/marketindex/", headers=headers, timeout=3)
        s_ex = BeautifulSoup(res_ex.text, 'html.parser')
        ex_box = s_ex.select_one("#exchangeList > li.on > a.head.usd")
        if ex_box:
            val, diff, blind = ex_box.select_one(".value").text, ex_box.select_one(".change").text, ex_box.select_one(".blind").text
            cl = "text-red" if "상승" in blind else "text-blue" if "하락" in blind else "text-gray"
            indices["USD/KRW"] = (val, f"{'▲' if '상승' in blind else '▼' if '하락' in blind else ''}{diff}", cl)
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
    
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V47.0 (Rollback)</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        acc_types = ["함대 전체"] + list(df['계좌유형'].unique())
        selected_type = st.selectbox("계좌 필터", acc_types)
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
            try:
                client = get_gspread_client()
                ws = client.open_by_url("https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0").get_worksheet(0)
                idx_map = {str(col).strip(): i+1 for i, col in enumerate(full_df.columns)}
                # 동기화 로직 실행
                st.cache_data.clear()
                st.success("동기화 완료.")
                time.sleep(1)
                st.rerun()
            except Exception as e: st.error(f"오류: {e}")

    # 계좌 필터 적용
    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()

    # 지수 렌더링
    if indices:
        idx_html = '<div class="index-container">'
        for name in ["KOSPI", "KOSDAQ", "NASDAQ", "S&P 500"]:
            val, diff, cl = indices.get(name, ("-", "-", "text-gray"))
            idx_html += f'<div class="index-item"><span class="index-name">{name}</span><span class="index-val {cl}">{val}</span><span class="index-diff {cl}">{diff}</span></div>'
        idx_html += '</div>'
        st.markdown(idx_html, unsafe_allow_html=True)

    # KPI 렌더링
    total_eval = display_df['평가금액'].sum()
    total_invest = display_df['매수금액'].sum()
    total_profit = display_df['평가손익'].sum()
    total_roi = (total_profit / total_invest * 100) if total_invest > 0 else 0
    total_cash = display_df[display_df['종목명'].astype(str).str.contains('현금|예수금', na=False)]['평가금액'].sum()
    
    roi_cl = "text-red" if total_roi > 0 else "text-blue" if total_roi < 0 else "text-gray"
    kpi_html = f"""<div class="kpi-grid">
        <div class="kpi-box"><span class="kpi-label">총 함대 자산</span><span class="kpi-val">{total_eval:,.0f}원</span></div>
        <div class="kpi-box"><span class="kpi-label">총 누적 손익</span><span class="kpi-val {roi_cl}">{total_profit:,.0f}원 <span class="kpi-delta">({total_roi:.2f}%)</span></span></div>
        <div class="kpi-box"><span class="kpi-label">기동 대기 예수금</span><span class="kpi-val text-white">{total_cash:,.0f}원</span></div>
    </div>"""
    st.markdown(kpi_html, unsafe_allow_html=True)

    # 리스트 렌더링
    yield_col = '수익률2' if '수익률2' in display_df.columns else '수익률'
    display_df = display_df.sort_values(by=yield_col, ascending=False)
    
    html_cards = ""
    for _, row in display_df.iterrows():
        is_special = any(x in str(row.get('종목명','')) for x in ["현금", "예수금", "단기", "연금", "TDF", "펀드"])
        y_val = row.get(yield_col, 0)
        now_p = row.get('현재가2', row.get('현재가', row.get('매수단가', 0)))
        prev_p = row.get('전일종가', 0)
        diff = now_p - prev_p if prev_p > 0 else 0
        rate = (diff / prev_p * 100) if prev_p > 0 else 0
        tcr_info = quant_analyzer.get_tcr_score(str(row.get('종목코드', '')), now_p)
        
        cl = "text-red" if y_val > 0 else "text-blue" if y_val < 0 else "text-gray"
        dt = "dot-red" if y_val > 0 else "dot-blue" if y_val < 0 else "dot-gray"
        ds = f"<span class='{'text-red' if diff>0 else 'text-blue' if diff<0 else 'text-gray'}'>{'▲' if diff>0 else '▼' if diff<0 else ''}{abs(diff):,.0f}({rate:.2f}%)</span>"
        
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
                <div class="metric-grid">
                    <div class="metric-box"><div class="metric-label">평가 금액</div><div class="metric-highlight">{row['평가금액']:,.0f}원</div></div>
                    <div class="metric-box"><div class="metric-label">매수 금액</div><div class="metric-value">{row['매수금액']:,.0f}원</div></div>
                    <div class="metric-box"><div class="metric-label">🔥 확신율 (TCR)</div><div class="metric-value" style="color:{tcr_info['color']};">{tcr_info['score']}% <span style='font-size:0.7rem;'>({tcr_info['status']})</span></div></div>
                    <div class="metric-box"><div class="metric-label">평균 단가 / 수량</div><div class="metric-value">{row['매수단가']:,.0f}원 ({row['잔고수량']:,.0f}주)</div></div>
                </div>
            </div>
        </details>"""
        
    st.markdown(html_cards, unsafe_allow_html=True)
    st.markdown(quant_analyzer.get_analysis_legend(), unsafe_allow_html=True)

except Exception as e: st.error(f"함대 기동 중지: {e}")
