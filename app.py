import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json, requests, time
from bs4 import BeautifulSoup
import quant_analyzer
import altair as alt

st.set_page_config(page_title="거북이 함대 기동 본부 V0.5.8", layout="wide", initial_sidebar_state="expanded")

# --- CSS (생략 없이 원본 유지) ---
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
    .kpi-box { display: flex; flex-direction: column; }
    .kpi-label { font-size: 0.8rem; color: rgb(108,122,137); font-weight: 700; margin-bottom: 4px; }
    .kpi-val { font-size: 1.5rem; font-weight: 800; letter-spacing: -0.5px; }
    .text-blue { color: rgb(70,130,180) !important; }
    .text-red { color: #ef4444 !important; }
    .text-gray { color: rgb(108,122,137) !important; }
    .text-white { color: #ffffff !important; }
    details.premium-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 10px; margin-bottom: 8px; transition: all 0.2s; }
    details.premium-card:hover { border-color: rgb(70,130,180); }
    summary { padding: 14px 16px; cursor: pointer; list-style: none; }
    .card-header-flex { display: flex; justify-content: space-between; align-items: center; width: 100%; gap: 10px; }
    .card-left { display: flex; align-items: center; gap: 8px; width: 35%; overflow: hidden; }
    .card-right { display: flex; justify-content: space-between; align-items: center; width: 65%; }
    .status-dot { min-width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .dot-red { background-color: #ef4444; } .dot-blue { background-color: rgb(70,130,180); } .dot-gray { background-color: rgb(108,122,137); }
    .val-box { display: flex; flex-direction: column; align-items: center; width: 33%; }
    .val-num { font-size: 1rem; font-weight: 800; }
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
        
        rate_res = requests.get("https://finance.naver.com/marketindex/worldInterestQuote.naver?marketindexCd=IR_TNX", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        rs = BeautifulSoup(rate_res.text, 'html.parser')
        r_box = rs.select_one(".no_today")
        if r_box and r_box.select_one("em"):
            indices["US 10Y (미 국채)"] = (r_box.select_one("em").text.strip(), "실시간금리", "text-gray")
    except: pass
    return indices

def get_safe_val(r, cols):
    for c in cols:
        v = r.get(c, 0)
        if v != 0 and pd.notna(v): return v
    return 0

# --- 🚨 [V0.5.8 패치] 타임아웃 60초 확장 및 정식 통신망 복구 ---
def generate_ai_briefing(api_key, portfolio_df, tcr_results, indices, user_context):
    try:
        clean_key = api_key.strip()
        pf_summary = []
        for _, r in portfolio_df.iterrows():
            if "현금" in r['종목명'] or "예수금" in r['종목명']: continue
            code = str(r['종목코드'])
            tcr = tcr_results.get(code, {}).get('score', 0)
            pf_summary.append(f"- {r['종목명']}: 수익률 {r['안전_수익률']*100:.1f}%, TCR확신율 {tcr}점")
        
        cash = portfolio_df[portfolio_df['종목명'].astype(str).str.contains('현금|예수금')]['평가금액'].sum()
        
        prompt = f"""당신은 월스트리트 최고의 투자 참모입니다. 말투는 군대식으로 명확하게!
        [시장지표]: {indices}
        [함대현황]: 현금 {cash:,.0f}원 / 종목: {chr(10).join(pf_summary)}
        [특별지시]: {user_context if user_context else "없음"}
        양식: 🌍글로벌요약, 🎯포트폴리오진단, 🔥최종작전지시(매도/매수/비중조절 사유명확히)"""
        
        headers = {'Content-Type': 'application/json'}
        data = {"contents": [{"parts": [{"text": prompt}]}]}
        
        # 정식 V1 주소로 타격하되, 타임아웃을 60초로 대폭 늘림
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={clean_key}"
        response = requests.post(url, headers=headers, json=data, timeout=60)
        
        if response.status_code == 200:
            result_json = response.json()
            return result_json['candidates'][0]['content']['parts'][0]['text']
        else:
            return f"⚠️ 통신 실패 (상태코드 {response.status_code}): {response.text}"
            
    except Exception as e:
        return f"🚨 시스템 에러: {str(e)}"

# --- Main App (Stable V0.5.8) ---
try:
    sheet, df, full_df = load_data()
    indices = get_market_indices()
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V0.5.8</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        with st.expander("🛠️ VCS", expanded=False):
            st.markdown("**V0.5.8 가동**\n- Timeout 60초 확장\n- 정식 Gemini API 경로 복구")
        st.divider()
        st.markdown("**🤖 AI 참모 통신**")
        api_key = st.text_input("Gemini API Key 입력 후 Enter", type="password")
        st.divider()
        if st.button("🔄 시세 업데이트"):
            st.cache_data.clear(); st.rerun()
        st.divider()
        sort_option = st.radio("📊 정렬", ["수익률 순", "당일 등락 순", "종목명 순"], horizontal=True)
        selected_type = st.selectbox("🗂️ 계좌 필터", ["함대 전체"] + list(df['계좌유형'].unique()))
        
    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()
    display_df['안전_수익률'] = display_df.apply(lambda r: get_safe_val(r, ['수익률2', '수익률']), axis=1)
    
    stock_fetch_list = [(str(row.get('종목코드', '')), get_safe_val(row, ['현재가2', '현재가', '기준가', '매수단가'])) for _, row in display_df.iterrows() if str(row.get('종목코드', '')) and "현금" not in str(row['종목명']) and "예수금" not in str(row['종목명'])]
    
    with st.spinner("🚀 데이터 분석 중..."):
        tcr_results = quant_analyzer.get_tcr_scores_batch(stock_fetch_list, {"flow": 0.4, "trend": 0.4, "vcp": 0.2})

    tab_main, tab_analysis, tab_ai = st.tabs(["🚀 관제실", "🔬 분석실", "🤖 AI 브리핑"])

    with tab_main:
        if indices:
            idx_html = '<div class="index-container">'
            for name in ["KOSPI", "NASDAQ", "S&P 500", "USD/KRW"]:
                val, diff, cl = indices.get(name, ("-", "-", "text-gray"))
                idx_html += f'<div class="index-item"><span class="index-name">{name}</span><span class="index-val {cl}">{val}</span><span class="index-diff {cl}">{diff}</span></div>'
            idx_html += '</div>'
            st.markdown(idx_html, unsafe_allow_html=True)
            
        total_eval = display_df['평가금액'].sum()
        total_profit = display_df['평가손익'].sum()
        daily_delta = sum((get_safe_val(r,['현재가2','현재가','기준가','매수단가']) - get_safe_val(r,['전일종가2','전일종가'])) * r.get('잔고수량',0) for _,r in display_df.iterrows() if get_safe_val(r,['전일종가2','전일종가']) > 0)
        st.markdown(f"""<div class="kpi-grid">
            <div class="kpi-box"><span class="kpi-label">총 자산</span><span class="kpi-val text-white">{total_eval:,.0f}원</span></div>
            <div class="kpi-box"><span class="kpi-label">누적 손익</span><span class="kpi-val {'text-red' if total_profit>0 else 'text-blue'}">{total_profit:,.0f}원</span></div>
            <div class="kpi-box"><span class="kpi-label">전일 증감</span><span class="kpi-val {'text-red' if daily_delta>0 else 'text-blue'}">{daily_delta:,.0f}원</span></div>
        </div>""", unsafe_allow_html=True)

        is_cash = display_df['종목명'].astype(str).str.contains('현금|예수금', na=False)
        df_stock, df_cash = display_df[~is_cash].copy(), display_df[is_cash].copy()
        
        if sort_option == "수익률 순": df_stock = df_stock.sort_values(by='안전_수익률', ascending=False)
        else: df_stock = df_stock.sort_values(by='종목명')
        
        for _, row in pd.concat([df_stock, df_cash]).iterrows():
            now_p = get_safe_val(row, ['현재가2', '현재가', '기준가', '매수단가'])
            tcr = tcr_results.get(str(row.get('종목코드', '')), {"score": 0, "status": "데이터부족", "color": "text-gray"})
            st.markdown(f"""<details class="premium-card"><summary><div class="card-header-flex">
                <span class="stock-name">{row['종목명']}</span>
                <span class="val-num">{now_p:,.0f}원</span></div></summary>
                <div style="padding:15px; background:#020617; border-top:1px solid #1e293b;">
                <p>수익률: {row['안전_수익률']*100:.2f}% / TCR: <span style='color:{tcr['color']}'>{tcr['score']}% ({tcr['status']})</span></p></div></details>""", unsafe_allow_html=True)

    with tab_analysis:
        plot_df = df_stock.copy()
        plot_df['TCR점수'] = plot_df['종목코드'].astype(str).apply(lambda c: tcr_results.get(c, {}).get('score', 0))
        plot_df['표시수익률'] = plot_df['안전_수익률'] * 100
        chart = alt.Chart(plot_df).mark_circle(size=100).encode(
            x=alt.X('TCR점수:Q', title='TCR 확신율'), y=alt.Y('표시수익률:Q', title='수익률(%)'),
            color=alt.Color('TCR점수:Q', scale=alt.Scale(scheme='redblue')), tooltip=['종목명', 'TCR점수', '표시수익률']
        ).properties(height=400).interactive()
        st.altair_chart(chart, use_container_width=True)

    with tab_ai:
        st.subheader("🤖 제미나이 전술 참모")
        user_context = st.text_area("사령관 특별 지시", placeholder="분석에 참고할 뉴스를 입력하세요.")
        if st.button("🔥 작전 지시서 생성", use_container_width=True):
            if not api_key: st.error("사이드바에 API Key 입력 후 Enter 필수!")
            else:
                with st.spinner("🧠 퀀터멘털 데이터 분석 중... (최대 1분 소요)"):
                    ai_report = generate_ai_briefing(api_key, display_df, tcr_results, indices, user_context)
                    st.markdown(f"""<div style="background:#0f172a; padding:20px; border-radius:10px; border:1px solid #1e293b;">{ai_report.replace(chr(10), '<br>')}</div>""", unsafe_allow_html=True)

except Exception as e: st.error(f"기동 실패: {e}")
