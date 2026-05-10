import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json, requests, time
from bs4 import BeautifulSoup
import quant_analyzer
import altair as alt

# --- 오리지널 설정 ---
st.set_page_config(page_title="거북이 함대 기동 본부 V0.4.1", layout="wide", initial_sidebar_state="expanded")

# --- V0.4.1 오리지널 프리미엄 디자인 CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    h1, h2, h3, p, span, div { font-family: 'Urbanist', 'Noto Sans KR', sans-serif; }
    
    /* 최상단 지수 보드 */
    .index-container { display: flex; flex-wrap: wrap; justify-content: space-between; background: #0f172a; padding: 10px 15px; border-radius: 10px; border: 1px solid #1e293b; margin-bottom: 20px; }
    .index-item { display: flex; flex-direction: column; align-items: center; width: 24%; border-right: 1px solid #1e293b; }
    .index-item:last-child { border-right: none; }
    .index-name { font-size: 0.7rem; color: #6c7a89; font-weight: 700; margin-bottom: 2px; }
    .index-val { font-size: 1.1rem; font-weight: 800; color: #ffffff; }
    .index-diff { font-size: 0.75rem; font-weight: 600; }
    
    /* KPI 그리드 */
    .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 25px; }
    .kpi-box { display: flex; flex-direction: column; background: #0f172a; padding: 15px; border-radius: 10px; border: 1px solid #1e293b; }
    .kpi-label { font-size: 0.75rem; color: #6c7a89; font-weight: 700; margin-bottom: 6px; }
    .kpi-val { font-size: 1.6rem; font-weight: 800; letter-spacing: -0.5px; }
    .kpi-sub { font-size: 0.8rem; font-weight: 700; margin-top: 4px; }
    
    /* 종목 리스트 카드 */
    details.premium-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 10px; margin-bottom: 10px; transition: all 0.2s; }
    details.premium-card summary { padding: 18px 20px; cursor: pointer; list-style: none; }
    .card-header-flex { display: flex; justify-content: space-between; align-items: flex-start; width: 100%; }
    .stock-info { display: flex; flex-direction: column; }
    .stock-name-box { display: flex; align-items: center; gap: 8px; }
    .status-dot-mini { width: 6px; height: 6px; border-radius: 50%; background-color: #ef4444; }
    .stock-name { font-size: 1rem; font-weight: 700; color: #ffffff; }
    
    .price-roi-box { display: flex; gap: 40px; text-align: right; }
    .val-group { display: flex; flex-direction: column; }
    .val-label-mini { font-size: 0.65rem; color: #6c7a89; font-weight: 700; margin-bottom: 2px; }
    .val-data { font-size: 1.1rem; font-weight: 800; }
    
    .card-body-inner { padding: 0 20px 20px 20px; font-size: 0.85rem; border-top: 1px solid #1e293b; padding-top: 15px; margin-top: 5px; }
    .tcr-line { font-size: 0.9rem; margin-bottom: 5px; }
    .tcr-val { font-weight: 800; color: #4682B4; }
    
    .text-blue { color: #4682B4 !important; }
    .text-red { color: #ef4444 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 오리지널 데이터 엔진 ---
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
    df = df[~df['종목명'].astype(str).str.contains('합계|총계|총액|총자산', na=False)]
    return sheet, df, full_df

@st.cache_data(ttl=120)
def get_market_indices():
    indices = {"KOSPI": ("-", "-", "text-gray"), "KOSDAQ": ("-", "-", "text-gray"), "NASDAQ": ("-", "-", "text-gray"), "S&P 500": ("-", "-", "text-gray")}
    try:
        res = requests.get("https://finance.naver.com/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        for name, selector in [("KOSPI", ".kospi_area"), ("KOSDAQ", ".kosdaq_area")]:
            box = soup.select_one(selector)
            if box:
                val, diff, rate = box.select_one(".num").text, box.select_one(".num2").text, box.select_one(".num3").text
                bt = box.select_one(".blind").text
                indices[name] = (val, f"{'▲' if '상승' in bt else '▼' if '하락' in bt else ''}{diff} ({rate})", "text-red" if "상승" in bt else "text-blue")
    except: pass
    return indices

def get_safe_val(r, cols):
    for c in cols:
        v = r.get(c, 0)
        if v != 0 and pd.notna(v): return v
    return 0

# --- 기동 ---
try:
    sheet, df, full_df = load_data()
    indices = get_market_indices()
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V0.4.1</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        if st.button("🔄 실시간 시세 수동 업데이트"): st.cache_data.clear(); st.rerun()
        st.divider()
        st.subheader("📊 정렬")
        sort_option = st.radio("기준 선택", ["수익률 순", "당일 등락 순", "종목명 순"], horizontal=True, label_visibility="collapsed")
        st.divider()
        st.subheader("📂 계좌 필터")
        selected_type = st.selectbox("계좌 선택", ["함대 전체"] + list(df['계좌유형'].unique()), label_visibility="collapsed")
        st.divider()
        st.subheader("📡 작전 모드")
        mode = st.radio("모드 선택", ["함대 관측", "데이터 강제 수정", "신규 종목 추가", "종목 완전 삭제"], label_visibility="collapsed")
        st.divider()
        st.subheader("💳 대상 계좌")
        acc_opts = [f"{r['계좌유형']} [{r['계좌번호']}]" for _, r in full_df[['계좌유형', '계좌번호']].drop_duplicates().iterrows() if str(r['계좌번호']).strip() != '']
        sel_acc = st.selectbox("계좌 선택", acc_opts, label_visibility="collapsed")

    # 데이터 전처리
    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()
    display_df['안전_수익률'] = display_df.apply(lambda r: get_safe_val(r, ['수익률2', '수익률']), axis=1)
    stock_fetch_list = [(str(row.get('종목코드', '')), get_safe_val(row, ['현재가2', '현재가', '기준가'])) for _, row in display_df.iterrows() if str(row.get('종목코드', '')) and "현금" not in str(row['종목명'])]
    
    with st.spinner("🚀 오리지널 TCR 엔진 가동..."):
        tcr_results = quant_analyzer.get_tcr_scores_batch(stock_fetch_list, {"flow": 0.4, "trend": 0.4, "vcp": 0.2})

    tab1, tab2 = st.tabs(["🚀 기동 관제실 (Dashboard)", "🔬 심층 분석실 (Deep Analysis)"])

    with tab1:
        # 시장 지수 보드
        idx_html = '<div class="index-container">'
        for name in ["KOSPI", "KOSDAQ", "NASDAQ", "S&P 500"]:
            val, diff, cl = indices.get(name, ("-", "-", "text-gray"))
            idx_html += f'<div class="index-item"><span class="index-name">{name}</span><span class="index-val {cl}">{val}</span><span class="index-diff {cl}">{diff}</span></div>'
        idx_html += '</div>'
        st.markdown(idx_html, unsafe_allow_html=True)
            
        total_eval = display_df['평가금액'].sum()
        total_profit = display_df['평가손익'].sum()
        total_cash = display_df[display_df['종목명'].astype(str).str.contains('현금|예수금')]['평가금액'].sum()

        # KPI 그리드
        st.markdown(f"""<div class="kpi-grid">
            <div class="kpi-box"><span class="kpi-label">총 함대 자산</span><span class="kpi-val text-white">{total_eval:,.0f}원</span></div>
            <div class="kpi-box"><span class="kpi-label">총 누적 손익</span><span class="kpi-val {'text-red' if total_profit>0 else 'text-blue'}">{total_profit:,.0f}원</span><span class="kpi-sub {'text-red' if total_profit>0 else 'text-blue'}">({(total_profit/(total_eval-total_profit)*100):.2f}%)</span></div>
            <div class="kpi-box"><span class="kpi-label">기동 대기 예수금</span><span class="kpi-val text-blue">{total_cash:,.0f}원</span></div>
            <div class="kpi-box"><span class="kpi-label">기동 상태</span><span class="kpi-val text-white">정상</span></div>
        </div>""", unsafe_allow_html=True)

        is_cash = display_df['종목명'].astype(str).str.contains('현금|예수금', na=False)
        df_stock = display_df[~is_cash].sort_values(by='안전_수익률', ascending=False)
        
        for _, row in df_stock.iterrows():
            now_p = get_safe_val(row, ['현재가2', '현재가', '기준가'])
            tcr = tcr_results.get(str(row.get('종목코드', '')), {"score": 0, "status": "관측중", "color": "#6c7a89"})
            is_up = row['안전_수익률'] > 0
            
            st.markdown(f"""
            <details class="premium-card">
                <summary><div class="card-header-flex">
                    <div class="stock-info">
                        <div class="stock-name-box"><div class="status-dot-mini" style="background-color: {'#ef4444' if is_up else '#4682B4'}"></div><span class="stock-name">{row['종목명']}</span></div>
                    </div>
                    <div class="price-roi-box">
                        <div class="val-group"><span class="val-label-mini">현재가</span><span class="val-data {'text-red' if is_up else 'text-blue'}">{now_p:,.0f}</span></div>
                        <div class="val-group"><span class="val-label-mini">수익률</span><span class="val-data {'text-red' if is_up else 'text-blue'}">{row['안전_수익률']*100:+.2f}%</span></div>
                    </div>
                </div></summary>
                <div class="card-body-inner">
                    <div class="tcr-line">🔥 AI 확신율(TCR): <span style="color:{tcr['color']}; font-weight:800;">{tcr['score']}% ({tcr['status']})</span></div>
                    <div class="meta-line">평가금액: {row['평가금액']:,.0f}원 / 평가손익: <span class="{'text-red' if is_up else 'text-blue'}">{row['평가손익']:,.0f}원</span> / 보유수량: {row.get('잔고수량',0)}주</div>
                </div>
            </details>""", unsafe_allow_html=True)

    with tab2:
        st.subheader("📊 전술 사분면 ( Deep Analysis )")
        plot_df = df_stock.copy()
        plot_df['TCR점수'] = plot_df['종목코드'].astype(str).apply(lambda c: tcr_results.get(c, {}).get('score', 0))
        plot_df['표시수익률'] = plot_df['안전_수익률'] * 100
        chart = alt.Chart(plot_df).mark_circle(size=150).encode(
            x=alt.X('TCR점수:Q', scale=alt.Scale(domain=[0, 100]), title='AI 확신율 (TCR)'),
            y=alt.Y('표시수익률:Q', title='내 계좌 수익률 (%)'),
            color=alt.Color('TCR점수:Q', scale=alt.Scale(scheme='redblue', domain=[0, 100]), legend=None),
            tooltip=['종목명', 'TCR점수', '표시수익률', '평가금액']
        ).properties(height=500).interactive()
        st.altair_chart(chart, use_container_width=True)

except Exception as e: st.error(f"함대 기동 중지: {e}")
