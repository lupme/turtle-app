import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json, requests, time
from bs4 import BeautifulSoup
import quant_analyzer
import altair as alt # 🚨 Plotly 대신 스트림릿 기본 내장 차트 모듈 사용

st.set_page_config(page_title="거북이 함대 기동 본부 V0.4.1", layout="wide", initial_sidebar_state="expanded")

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
    .stButton>button { width: 100%; border-radius: 8px; font-weight: 700; background-color: #0f172a; border: 1px solid #1e293b; color: #f8fafc; height: 45px; }
    .stButton>button:hover { border-color: rgb(70,130,180); color: rgb(70,130,180); }
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
    if '계좌유형' in df.columns: df['계좌유형'] = df['계좌유형'].astype(str).str.strip()
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
                indices[code] = (val, f"{'▲' if '상승' in bt else '▼' if '하락' in bt else ''}{diff} ({rate})", "text-red" if "상승" in bt else "text-blue" if "하락" in bt else "text-gray")
        for code, sym in [("NASDAQ", "NAS@IXIC"), ("S&P 500", "SPI@SPX"), ("DOW", "DJI@DJI"), ("VIX", "VIX@VIX")]:
            res_w = requests.get(f"https://finance.naver.com/world/sise.naver?symbol={sym}", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
            sw = BeautifulSoup(res_w.text, 'html.parser')
            em = sw.select_one("p.no_today em")
            if em:
                val = em.text.strip()
                diff_area = sw.select_one("p.no_exday")
                if diff_area:
                    ems = diff_area.find_all("em")
                    stt = diff_area.select_one("span.blind").text if diff_area.select_one("span.blind") else ""
                    indices[code] = (val, f"{'▲' if '상승' in stt else '▼' if '하락' in stt else ''}{ems[0].text.strip()} ({ems[1].text.strip()})", "text-red" if "상승" in stt else "text-blue" if "하락" in stt else "text-gray")
        res_ex = requests.get("https://finance.naver.com/marketindex/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        sx = BeautifulSoup(res_ex.text, 'html.parser')
        ex_box = sx.select_one("#exchangeList > li.on > a.head.usd")
        if ex_box:
            val, diff, blind = ex_box.select_one(".value").text, ex_box.select_one(".change").text, ex_box.select_one(".blind").text
            indices["USD/KRW"] = (val, diff, "text-red" if "상승" in blind else "text-blue")
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
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V0.4.1</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        with st.expander("🛠️ 함대 버전 관리 (VCS)", expanded=False):
            st.markdown("**현재 가동:** `V0.4.1 (무설치 분석모듈)`")
            st.markdown("**직전 안정:** `V0.3 (병렬 엔진)`")
            st.markdown("**패치 내역:**")
            st.markdown("- 분석 탭 추가 (수익률 vs 확신율)\n- 가중치 시뮬레이터 구축\n- 스트림릿 클라우드 에러 방지를 위한 내장 차트(Altair) 적용")
        st.divider()
        if st.button("🔄 실시간 시세 수동 업데이트"):
            st.cache_data.clear(); st.rerun()
        st.divider()
        sort_option = st.radio("📊 리스트 정렬 기준", ["수익률 순", "당일 등락 순", "종목명 순"], horizontal=True)
        st.divider()
        selected_type = st.selectbox("🗂️ 계좌 필터", ["함대 전체"] + list(df['계좌유형'].unique()))
        
    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()
    display_df['안전_수익률'] = display_df.apply(lambda r: get_safe_val(r, ['수익률2', '수익률']), axis=1)
    display_df['당일등락율'] = display_df.apply(lambda r: (((get_safe_val(r, ['현재가2', '현재가', '기준가', '매수단가']) - get_safe_val(r, ['전일종가2', '전일종가'])) / get_safe_val(r, ['전일종가2', '전일종가'])) * 100) if get_safe_val(r, ['전일종가2', '전일종가']) > 0 else 0, axis=1)

    default_weights = {"flow": 0.4, "trend": 0.4, "vcp": 0.2}
    stock_fetch_list = [(str(row.get('종목코드', '')), get_safe_val(row, ['현재가2', '현재가', '기준가', '매수단가'])) for _, row in display_df.iterrows() if str(row.get('종목코드', '')) and "현금" not in str(row['종목명']) and "예수금" not in str(row['종목명'])]
    
    with st.spinner("🚀 T-Q 엔진 가동 중..."):
        tcr_results = quant_analyzer.get_tcr_scores_batch(stock_fetch_list, default_weights)

    tab_main, tab_analysis = st.tabs(["🚀 기동 관제실 (Dashboard)", "🔬 심층 분석실 (Deep Analysis)"])

    with tab_main:
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

        total_eval = display_df['평가금액'].sum()
        total_profit = display_df['평가손익'].sum()
        total_roi = (total_profit / display_df['매수금액'].sum() * 100) if display_df['매수금액'].sum() > 0 else 0
        daily_delta = sum((get_safe_val(r,['현재가2','현재가','기준가','매수단가']) - get_safe_val(r,['전일종가2','전일종가'])) * r.get('잔고수량',0) for _,r in display_df.iterrows() if get_safe_val(r,['전일종가2','전일종가']) > 0)
        total_cash = display_df[display_df['종목명'].astype(str).str.contains('현금|예수금', na=False)]['평가금액'].sum()

        st.markdown(f"""<div class="kpi-grid">
            <div class="kpi-box"><span class="kpi-label">총 함대 자산</span><span class="kpi-val text-white">{total_eval:,.0f}원</span></div>
            <div class="kpi-box"><span class="kpi-label">총 누적 손익</span><span class="kpi-val {'text-red' if total_profit>0 else 'text-blue'}">{total_profit:,.0f}원 <span class="kpi-delta">({total_roi:.2f}%)</span></span></div>
            <div class="kpi-box"><span class="kpi-label">전일 대비 증감</span><span class="kpi-val {'text-red' if daily_delta>0 else 'text-blue'}">{'▲' if daily_delta>0 else '▼' if daily_delta<0 else ''}{abs(daily_delta):,.0f}원</span></div>
            <div class="kpi-box"><span class="kpi-label">기동 대기 예수금</span><span class="kpi-val text-blue">{total_cash:,.0f}원</span></div>
        </div>""", unsafe_allow_html=True)

        is_cash = display_df['종목명'].astype(str).str.contains('현금|예수금', na=False)
        df_stock, df_cash = display_df[~is_cash].copy(), display_df[is_cash].copy()

        if sort_option == "수익률 순": df_stock = df_stock.sort_values(by='안전_수익률', ascending=False)
        elif sort_option == "당일 등락 순": df_stock = df_stock.sort_values(by='당일등락율', ascending=False)
        else: df_stock = df_stock.sort_values(by='종목명')
        list_df = pd.concat([df_stock, df_cash])

        html_cards = ""
        for _, row in list_df.iterrows():
            now_p = get_safe_val(row, ['현재가2', '현재가', '기준가', '매수단가'])
            prev_p = get_safe_val(row, ['전일종가2', '전일종가'])
            y_val = row['안전_수익률']
            code = str(row.get('종목코드', ''))
            diff = now_p - prev_p if prev_p > 0 else 0
            rate = (diff / prev_p * 100) if prev_p > 0 else 0
            
            if "현금" in str(row['종목명']) or "예수금" in str(row['종목명']):
                tcr_info = {"score": "-", "status": "안전 자산 대기", "color": "text-blue"}
            else:
                tcr_info = tcr_results.get(code, {"score": 0, "status": "데이터 확인 불가", "color": "text-gray"})
            
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
                        <div class="metric-box"><div class="metric-label" style="font-size:0.75rem; color:rgb(108,122,137);">🔥 확신율 (TCR)</div><div class="metric-value" style="font-size:1.05rem; font-weight:700; color:{tcr_info.get('color', 'text-gray')};">{tcr_info.get('score', 0)}% <span style='font-size:0.7rem;'>({tcr_info.get('status', '')})</span></div></div>
                        <div class="metric-box"><div class="metric-label" style="font-size:0.75rem; color:rgb(108,122,137);">매수 금액</div><div class="metric-value" style="font-size:1.05rem; font-weight:700;">{row['매수금액']:,.0f}원</div></div>
                        <div class="metric-box"><div class="metric-label" style="font-size:0.75rem; color:rgb(108,122,137);">보유 수량</div><div class="metric-value" style="font-size:1.05rem; font-weight:700;">{row['잔고수량']:,.0f}주</div></div>
                    </div>
                </div>
            </details>"""
        st.markdown(html_cards, unsafe_allow_html=True)

    with tab_analysis:
        st.subheader("📊 1. 전술 사분면 (수익률 vs 확신율)")
        st.markdown("<p style='font-size:0.85rem; color:#94a3b8;'>• 마우스를 점 위에 올리면 종목명과 상세 데이터가 보입니다.<br>• 우측 하단(수익↓, 확신↑): <b>비중 확대(물타기) 고려 1순위</b></p>", unsafe_allow_html=True)
        
        plot_df = df_stock.copy()
        plot_df['TCR점수'] = plot_df['종목코드'].astype(str).apply(lambda c: tcr_results.get(c, {}).get('score', 0))
        plot_df['표시수익률'] = plot_df['안전_수익률'] * 100
        
        # 🚨 [V0.4.1 패치] 스트림릿 내장 Altair 차트로 에러 원천 차단
        chart = alt.Chart(plot_df).mark_circle().encode(
            x=alt.X('TCR점수:Q', scale=alt.Scale(domain=[0, 100]), title='TCR 확신율 (0~100)', axis=alt.Axis(gridColor='#1e293b', titleColor='#94a3b8', labelColor='#94a3b8')),
            y=alt.Y('표시수익률:Q', title='현재 수익률 (%)', axis=alt.Axis(gridColor='#1e293b', titleColor='#94a3b8', labelColor='#94a3b8')),
            size=alt.Size('평가금액:Q', legend=None, scale=alt.Scale(range=[50, 500])),
            color=alt.Color('TCR점수:Q', scale=alt.Scale(scheme='redblue', domain=[0, 100]), legend=None),
            tooltip=['종목명', 'TCR점수', '표시수익률', '평가금액']
        ).properties(
            height=450,
            background='#020617'
        ).interactive()

        hline = alt.Chart(pd.DataFrame({'y': [0]})).mark_rule(color='gray', strokeDash=[5, 5]).encode(y='y:Q')
        vline = alt.Chart(pd.DataFrame({'x': [50]})).mark_rule(color='gray', strokeDash=[5, 5]).encode(x='x:Q')

        st.altair_chart(chart + hline + vline, use_container_width=True)

        st.divider()

        st.subheader("🎛️ 2. 워룸 시뮬레이터 (가중치 실시간 조절)")
        st.markdown("<p style='font-size:0.85rem; color:#94a3b8;'>현재 시장 상황에 맞춰 가중치를 변경하면, 포트폴리오 내 최고의 타격 목표(Top 5)가 실시간으로 재계산됩니다.</p>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        with col1: w_flow = st.slider("수급 가중치", 0.0, 1.0, 0.4, 0.1)
        with col2: w_trend = st.slider("추세 가중치", 0.0, 1.0, 0.4, 0.1)
        with col3: w_vcp = st.slider("VCP 가중치", 0.0, 1.0, 0.2, 0.1)
        
        if round(w_flow + w_trend + w_vcp, 1) != 1.0:
            st.warning(f"⚠️ 가중치 합계가 1.0이 아닙니다. (현재: {w_flow + w_trend + w_vcp:.1f})")
        else:
            sim_weights = {"flow": w_flow, "trend": w_trend, "vcp": w_vcp}
            sim_results = quant_analyzer.get_tcr_scores_batch(stock_fetch_list, sim_weights)
            
            sim_df = plot_df.copy()
            sim_df['시뮬레이션_TCR'] = sim_df['종목코드'].astype(str).apply(lambda c: sim_results.get(c, {}).get('score', 0))
            top_5 = sim_df.sort_values(by='시뮬레이션_TCR', ascending=False).head(5)
            
            st.markdown(f"**현재 설정 기준 추천 타격 목표 (Top 5)**")
            for i, (_, r) in enumerate(top_5.iterrows()):
                st.markdown(f"{i+1}. **{r['종목명']}** (예상 확신율: **{r['시뮬레이션_TCR']}점**) / 현재 수익률: {r['표시수익률']:.2f}%")

except Exception as e: st.error(f"함대 기동 중지: {e}")
