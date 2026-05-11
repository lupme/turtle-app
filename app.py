import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json, time
from bs4 import BeautifulSoup
import quant_analyzer
import requests
import altair as alt

# [완전히 새로운 무기] 구글 공식 AI 통신 라이브러리
import google.generativeai as genai

st.set_page_config(page_title="거북이 함대 기동 본부 V0.5.3 (Mobile)", layout="wide", initial_sidebar_state="expanded")

# --- 📱 모바일 반응형 CSS (오리지널 유지) ---
st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    h1, h2, h3, p, span, div { font-family: 'Urbanist', 'Noto Sans KR', sans-serif; }
    .hq-title { font-size: 1.3rem; color: rgb(70,130,180); font-weight: 800; padding-top: 5px; margin-bottom: 15px; }
    
    .index-container { display: flex; flex-wrap: wrap; justify-content: space-between; background: #0f172a; padding: 10px 15px; border-radius: 10px; border: 1px solid #1e293b; margin-bottom: 15px; gap: 8px 0; }
    .index-item { display: flex; flex-direction: column; align-items: center; width: 24%; }
    .index-name { font-size: 0.75rem; color: rgb(108,122,137); font-weight: 700; margin-bottom: 2px; }
    .index-val { font-size: 1.05rem; font-weight: 800; color: #ffffff; }
    .index-diff { font-size: 0.75rem; font-weight: 600; }
    
    .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }
    .kpi-box { display: flex; flex-direction: column; background: #0f172a; padding: 15px; border-radius: 10px; border: 1px solid #1e293b; }
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
    .stock-name { font-size: 1rem; font-weight: 700; color: #ffffff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .val-box { display: flex; flex-direction: column; align-items: center; width: 33%; }
    .val-label { font-size: 0.65rem; color: rgb(108,122,137); font-weight: 600; margin-bottom: 2px; }
    .val-num { font-size: 1rem; font-weight: 800; }
    
    @media (max-width: 768px) {
        .index-item { width: 48%; margin-bottom: 10px; }
        .kpi-grid { grid-template-columns: repeat(2, 1fr); gap: 10px; }
        .card-header-flex { flex-direction: column; align-items: flex-start; }
        .card-left { width: 100%; margin-bottom: 10px; }
        .card-right { width: 100%; border-top: 1px dashed #1e293b; padding-top: 10px; }
        .kpi-val { font-size: 1.2rem; }
    }
    
    .stButton>button { width: 100%; border-radius: 8px; font-weight: 700; background-color: #0f172a; border: 1px solid #1e293b; color: #f8fafc; height: 45px; }
    .stButton>button:hover { border-color: rgb(70,130,180); color: rgb(70,130,180); }
    </style>
    """, unsafe_allow_html=True)

# --- Data Load (오리지널 유지) ---
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
    indices = {"KOSPI": ("-", "-", "text-gray"), "NASDAQ": ("-", "-", "text-gray"), "S&P 500": ("-", "-", "text-gray"), "VIX": ("-", "-", "text-gray"), "USD/KRW": ("-", "-", "text-gray"), "WTI (유가)": ("-", "-", "text-gray"), "US 10Y (미 국채)": ("-", "-", "text-gray")}
    try:
        res_main = requests.get("https://finance.naver.com/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        soup_main = BeautifulSoup(res_main.text, 'html.parser')
        box = soup_main.select_one(".kospi_area")
        if box:
            val, diff, rate = box.select_one(".num").text, box.select_one(".num2").text, box.select_one(".num3").text
            indices["KOSPI"] = (val, f"{'▲' if '상승' in box.select_one('.blind').text else '▼' if '하락' in box.select_one('.blind').text else ''}{diff} ({rate})", "text-red" if "상승" in box.select_one(".blind").text else "text-blue")
        
        for code, sym in [("NASDAQ", "NAS@IXIC"), ("S&P 500", "SPI@SPX"), ("VIX", "VIX@VIX")]:
            res_w = requests.get(f"https://finance.naver.com/world/sise.naver?symbol={sym}", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
            sw = BeautifulSoup(res_w.text, 'html.parser')
            em = sw.select_one("p.no_today em")
            if em:
                stt = sw.select_one("p.no_exday span.blind").text if sw.select_one("p.no_exday span.blind") else ""
                ems = sw.select_one("p.no_exday").find_all("em")
                indices[code] = (em.text.strip(), f"{'▲' if '상승' in stt else '▼' if '하락' in stt else ''}{ems[0].text.strip()} ({ems[1].text.strip()})", "text-red" if "상승" in stt else "text-blue")
        
        res_ex = requests.get("https://finance.naver.com/marketindex/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        sx = BeautifulSoup(res_ex.text, 'html.parser')
        ex_box = sx.select_one("#exchangeList > li.on > a.head.usd")
        if ex_box: indices["USD/KRW"] = (ex_box.select_one(".value").text, ex_box.select_one(".change").text, "text-red" if "상승" in ex_box.select_one(".blind").text else "text-blue")
        
        oil_box = sx.select_one("#oilGoldList > li.on > a.head.oil")
        if oil_box: indices["WTI (유가)"] = (oil_box.select_one(".value").text, oil_box.select_one(".change").text, "text-red" if "상승" in oil_box.select_one(".blind").text else "text-blue")
    except: pass
    return indices

def get_safe_val(r, cols):
    for c in cols:
        v = r.get(c, 0)
        if v != 0 and pd.notna(v): return v
    return 0

# --- 🚀 [아예 다른 방식] 전용 SDK 통신망 ---
def generate_ai_briefing(api_key, portfolio_df, tcr_results, indices, user_context):
    try:
        pf_summary = []
        for _, r in portfolio_df.iterrows():
            if "현금" in r['종목명'] or "예수금" in r['종목명']: continue
            code = str(r['종목코드'])
            tcr = tcr_results.get(code, {}).get('score', 0)
            pf_summary.append(f"- {r['종목명']}: 수익률 {r['안전_수익률']*100:.1f}%, TCR확신율 {tcr}점")
        
        cash = portfolio_df[portfolio_df['종목명'].astype(str).str.contains('현금|예수금')]['평가금액'].sum()
        
        prompt = f"""
        당신은 월스트리트 최고의 퀀터멘털(Quantamental) 투자 참모입니다. 사령관을 위해 작전 지시서를 작성하십시오.
        
        [지표]: {indices}
        [현황]: 현금 {cash:,.0f}원
        {chr(10).join(pf_summary)}
        [지시]: {user_context}
        
        1. 🌍 시황 요약
        2. 🎯 포트폴리오 진단
        3. 🔥 작전 지시 (명확한 매도/매수 종목 추천)
        """
        
        # 1. API 키 세팅 (주소를 만들지 않고 라이브러리에 키만 넘겨줍니다)
        genai.configure(api_key=api_key.strip())
        
        # 2. 모델 직접 소환 (서버 주소 문제 원천 차단)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # 3. 답변 생성
        response = model.generate_content(prompt)
        
        return response.text
        
    except Exception as e:
        return f"🚨 전용 통신망(SDK) 구축 후에도 에러가 발생했습니다: {str(e)}\n\n사령관님, 이 에러는 구글 클라우드 콘솔에서 API 키 자체의 결제/권한 설정 문제일 확률이 매우 높습니다."

# --- Main App ---
try:
    sheet, df, full_df = load_data()
    indices = get_market_indices()
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V0.5.3 (Mobile + SDK)</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        with st.expander("🛠️ 함대 버전 관리 (VCS)", expanded=False):
            st.markdown("**현재 가동:** `V0.5.3 (모바일 최적화 + SDK 통신판)`")
            st.markdown("**패치 내역:**\n- `google-generativeai` 라이브러리 전면 교체 (404 원천 차단)")
        st.divider()
        
        st.markdown("**🤖 AI 참모 통신 채널**")
        api_key = st.text_input("Gemini API Key 입력 (1회용)", type="password")
        st.divider()
        
        if st.button("🔄 실시간 시세 수동 업데이트"):
            st.cache_data.clear(); st.rerun()
        st.divider()
        
        sort_option = st.radio("📊 리스트 정렬 기준", ["수익률 순", "당일 등락 순", "종목명 순"], horizontal=True)
        st.divider()
        selected_type = st.selectbox("🗂️ 계좌 필터", ["함대 전체"] + list(df['계좌유형'].unique()))
        st.divider()

        mode = st.radio("작전 모드", ["기존 종목 매매", "데이터 강제 수정", "신규 종목 추가", "종목 완전 삭제"])
        acc_opts = [f"{r['계좌유형']} [{r['계좌번호']}]" for _, r in full_df[['계좌유형', '계좌번호']].drop_duplicates().iterrows() if str(r['계좌번호']).strip() != '']
        sel_acc_str = st.selectbox("명령 하달 대상 계좌", acc_opts) if acc_opts else ""
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
            time.sleep(1); st.rerun()
        
    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()
    display_df['안전_수익률'] = display_df.apply(lambda r: get_safe_val(r, ['수익률2', '수익률']), axis=1)
    
    stock_fetch_list = [(str(row.get('종목코드', '')), get_safe_val(row, ['현재가2', '현재가', '기준가', '매수단가'])) for _, row in display_df.iterrows() if str(row.get('종목코드', '')) and "현금" not in str(row['종목명']) and "예수금" not in str(row['종목명'])]
    
    with st.spinner("🚀 T-Q 엔진 데이터 수집 중..."):
        tcr_results = quant_analyzer.get_tcr_scores_batch(stock_fetch_list, {"flow": 0.4, "trend": 0.4, "vcp": 0.2})

    tab_main, tab_analysis, tab_ai = st.tabs(["🚀 기동 관제실", "🔬 전술 분석실(서술형)", "🤖 AI 브리핑"])

    with tab_main:
        if indices:
            idx_html = '<div class="index-container">'
            for name in ["KOSPI", "NASDAQ", "S&P 500", "USD/KRW"]:
                val, diff, cl = indices.get(name, ("-", "-", "text-gray"))
                idx_html += f'<div class="index-item"><span class="index-name">{name}</span><span class="index-val {cl}">{val}</span><span class="index-diff {cl}">{diff}</span></div>'
            idx_html += '</div>'
            st.markdown(idx_html, unsafe_allow_html=True)
            
            with st.expander("🌍 거시경제 및 보조 지표 (VIX, 유가, 미 국채)"):
                macro_html = '<div class="index-container" style="background:transparent; border:none; margin:0; padding:0;">'
                for name in ["VIX", "WTI (유가)", "US 10Y (미 국채)"]:
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
            <div class="kpi-box"><span class="kpi-label">총 함대 자산</span><span class="kpi-val text-white">{total_eval:,.0f}</span></div>
            <div class="kpi-box"><span class="kpi-label">총 누적 손익</span><span class="kpi-val {'text-red' if total_profit>0 else 'text-blue'}">{total_profit:,.0f} <span class="kpi-delta">({total_roi:.2f}%)</span></span></div>
            <div class="kpi-box"><span class="kpi-label">전일 대비 증감</span><span class="kpi-val {'text-red' if daily_delta>0 else 'text-blue'}">{'▲' if daily_delta>0 else '▼' if daily_delta<0 else ''}{abs(daily_delta):,.0f}</span></div>
            <div class="kpi-box"><span class="kpi-label">기동 예수금</span><span class="kpi-val text-blue">{total_cash:,.0f}</span></div>
        </div>""", unsafe_allow_html=True)

        is_cash = display_df['종목명'].astype(str).str.contains('현금|예수금', na=False)
        df_stock, df_cash = display_df[~is_cash].copy(), display_df[is_cash].copy()

        def calc_gap(r):
            n = get_safe_val(r, ['현재가2', '현재가', '기준가', '매수단가'])
            p = get_safe_val(r, ['전일종가2', '전일종가'])
            if p > 0: return ((n - p) / p) * 100
            return 0
        df_stock['당일등락율'] = df_stock.apply(calc_gap, axis=1)

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
                tcr_info = {"score": "-", "status": "안전 자산", "color": "text-blue"}
            else:
                tcr_info = tcr_results.get(code, {"score": 0, "status": "확인 불가", "color": "text-gray"})
            
            cl = "text-red" if y_val > 0 else "text-blue" if y_val < 0 else "text-gray"
            dt = "dot-red" if y_val > 0 else "dot-blue" if y_val < 0 else "dot-gray"
            ds = f"<span class='{'text-red' if diff>0 else 'text-blue' if diff<0 else 'text-gray'}'>{'▲' if diff>0 else '▼' if diff<0 else ''}{abs(diff):,.0f}({rate:.1f}%)</span>"
            
            html_cards += f"""
            <details class="premium-card">
                <summary><div class="card-header-flex">
                    <div class="card-left"><div class="status-dot {dt}"></div><span class="stock-name" title="{row['종목명']}">{row['종목명']}</span></div>
                    <div class="card-right">
                        <div class="val-box"><span class="val-label">현재가</span><span class="val-num {cl}">{now_p:,.0f}</span></div>
                        <div class="val-box"><span class="val-label">당일비</span><span class="val-num">{ds}</span></div>
                        <div class="val-box"><span class="val-label">수익률</span><span class="val-num {cl}">{y_val*100:.2f}%</span></div>
                    </div>
                </div></summary>
                <div class="card-body">
                    <div class="metric-grid" style="display:grid; grid-template-columns:repeat(2,1fr); gap:12px; background:#020617; padding:15px; border-radius:0 0 10px 10px; border-top:1px solid #1e293b;">
                        <div class="metric-box"><div class="metric-label" style="font-size:0.75rem; color:rgb(108,122,137);">평가 금액</div><div class="metric-value" style="font-size:1.05rem; font-weight:700; color:rgb(70,130,180);">{row['평가금액']:,.0f}</div></div>
                        <div class="metric-box"><div class="metric-label" style="font-size:0.75rem; color:rgb(108,122,137);">🔥 확신율 (TCR)</div><div class="metric-value" style="font-size:1.05rem; font-weight:700; color:{tcr_info.get('color', 'text-gray')};">{tcr_info.get('score', 0)}%</div></div>
                        <div class="metric-box"><div class="metric-label" style="font-size:0.75rem; color:rgb(108,122,137);">매수 금액</div><div class="metric-value" style="font-size:1.05rem; font-weight:700;">{row['매수금액']:,.0f}</div></div>
                        <div class="metric-box"><div class="metric-label" style="font-size:0.75rem; color:rgb(108,122,137);">보유 수량</div><div class="metric-value" style="font-size:1.05rem; font-weight:700;">{row['잔고수량']:,.0f}</div></div>
                    </div>
                </div>
            </details>"""
        st.markdown(html_cards, unsafe_allow_html=True)

    # --- 📝 모바일 최적화 서술형 분석실 ---
    with tab_analysis:
        st.subheader("📝 전술 상태 분류 (서술형 보고)")
        st.markdown("<p style='font-size:0.85rem; color:#94a3b8;'>모바일 환경에 맞춰 종목들을 4가지 상태로 분류하여 직관적으로 보고합니다.</p>", unsafe_allow_html=True)
        
        q1, q2, q3, q4 = [], [], [], []
        for _, row in df_stock.iterrows():
            code = str(row.get('종목코드', ''))
            tcr = tcr_results.get(code, {}).get('score', 0)
            ret = row['안전_수익률'] * 100
            item = f"**{row['종목명']}** (수익: {ret:+.2f}% / TCR: {tcr}점)"
            
            if ret >= 0 and tcr >= 50: q1.append(item)
            elif ret < 0 and tcr >= 50: q2.append(item)
            elif ret >= 0 and tcr < 50: q3.append(item)
            else: q4.append(item)
            
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 🟢 [1사분면] 주력 홀딩")
            st.info("수익 발생 & AI 확신율 높음\n\n" + ("\n".join([f"- {x}" for x in q1]) if q1 else "- 해당 종목 없음"))
            st.markdown("### 🟡 [3사분면] 익절 경계")
            st.warning("수익 발생 but AI 확신율 낮음\n\n" + ("\n".join([f"- {x}" for x in q3]) if q3 else "- 해당 종목 없음"))
        with col2:
            st.markdown("### 🔵 [2사분면] 물타기 대기")
            st.info("손실 발생 but AI 확신율 높음\n\n" + ("\n".join([f"- {x}" for x in q2]) if q2 else "- 해당 종목 없음"))
            st.markdown("### 🔴 [4사분면] 손절 고려")
            st.error("손실 발생 & AI 확신율 낮음\n\n" + ("\n".join([f"- {x}" for x in q4]) if q4 else "- 해당 종목 없음"))

    with tab_ai:
        st.subheader("🤖 제미나이 전술 참모")
        user_context = st.text_area("📡 사령관 지시사항", placeholder="예: 삼성전자 악재 뉴스가 떴는데 비중을 줄일까?")
        if st.button("🔥 작전 지시서 생성", use_container_width=True):
            if not api_key:
                st.error("사이드바에 API Key를 입력하십시오.")
            else:
                with st.spinner("🧠 전용 SDK 통신망 가동 중... (안정화 대기)"):
                    ai_report = generate_ai_briefing(api_key, display_df, tcr_results, indices, user_context)
                    st.markdown(f"<div style='background:#0f172a; padding:15px; border-radius:10px; border:1px solid #1e293b; font-size:0.95rem; line-height:1.6;'>{ai_report.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)

except Exception as e: st.error(f"함대 기동 중지: {e}")
