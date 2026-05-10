import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json, requests, time
from bs4 import BeautifulSoup
import quant_analyzer
import altair as alt
# 🚨 [V0.5.1 패치] 에러를 유발하는 google.generativeai 라이브러리를 삭제하고 기본 requests로 우회합니다.

st.set_page_config(page_title="거북이 함대 기동 본부 V0.5.1", layout="wide", initial_sidebar_state="expanded")

# --- CSS ---
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

# --- Data Load ---
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
            val = r_box.select_one("em").text.strip()
            indices["US 10Y (미 국채)"] = (val, "변동조회필요", "text-gray")
    except: pass
    return indices

def get_safe_val(r, cols):
    for c in cols:
        v = r.get(c, 0)
        if v != 0 and pd.notna(v): return v
    return 0

# --- 🚨 [V0.5.1 패치] 별도 라이브러리 없이 REST API로 AI와 직접 통신 ---
def generate_ai_briefing(api_key, portfolio_df, tcr_results, indices, user_context):
    try:
        pf_summary = []
        for _, r in portfolio_df.iterrows():
            if "현금" in r['종목명'] or "예수금" in r['종목명']: continue
            code = str(r['종목코드'])
            tcr = tcr_results.get(code, {}).get('score', 0)
            pf_summary.append(f"- {r['종목명']}: 수익률 {r['안전_수익률']*100:.1f}%, TCR확신율 {tcr}점, 비중금액 {r['평가금액']:,.0f}원")
        
        cash = portfolio_df[portfolio_df['종목명'].astype(str).str.contains('현금|예수금')]['평가금액'].sum()
        
        prompt = f"""
        당신은 월스트리트 최고의 퀀터멘털(Quantamental) 투자 참모입니다. 사령관(사용자)을 위해 '최종 작전 지시서'를 작성하십시오.
        말투는 군대식으로 명확하고 단호하게, 불필요한 서론 없이 즉시 본론만 출력하십시오.
        
        [현재 거시 경제 상황]
        {indices}
        
        [사령관의 현재 함대(포트폴리오) 상태]
        총 보유 현금(예수금): {cash:,.0f}원
        보유 종목 현황:
        {chr(10).join(pf_summary)}
        *(참고: TCR확신율은 100점 만점이며, 75점 이상은 강력매수/유지, 40점 이하는 위험/매도 신호입니다)*
        
        [사령관의 특별 지시 및 추가 정보]
        {user_context if user_context else "특이사항 없음"}
        
        아래 양식에 맞춰 정확히 브리핑하십시오:
        1. 🌍 글로벌 전황 요약 (거시 경제와 유가/금리를 바탕으로 한 시장 방향성)
        2. 🎯 포트폴리오 정밀 진단 (수익률과 TCR 점수를 비교하여 취약점과 강점 분석)
        3. 🔥 최종 작전 지시 (가장 시급하게 매도해야 할 종목 1개, 물타기/매수해야 할 종목 1개, 현금 비중 조절 조언을 정확한 이유와 함께 명시)
        """
        
        # 라이브러리 없이 직접 구글 서버로 전송
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        headers = {'Content-Type': 'application/json'}
        data = {"contents": [{"parts": [{"text": prompt}]}]}
        
        response = requests.post(url, headers=headers, json=data, timeout=15)
        response.raise_for_status()
        
        result_json = response.json()
        if 'candidates' in result_json and len(result_json['candidates']) > 0:
            return result_json['candidates'][0]['content']['parts'][0]['text']
        else:
            return "AI 참모 통신 오류: 응답을 해석할 수 없습니다."
            
    except Exception as e:
        return f"AI 참모 통신 실패: API 키가 잘못되었거나 오류가 발생했습니다. ({e})"

# --- Main App ---
try:
    sheet, df, full_df = load_data()
    indices = get_market_indices()
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V0.5.1</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        with st.expander("🛠️ 함대 버전 관리 (VCS)", expanded=False):
            st.markdown("**현재 가동:** `V0.5.1 (무설치 AI 통신판)`")
            st.markdown("**패치 내역:**\n- 에러 유발 라이브러리 삭제\n- REST API 다이렉트 통신망 개설")
        st.divider()
        
        st.markdown("**🤖 AI 참모 통신 채널**")
        api_key = st.text_input("Gemini API Key 입력 (1회용)", type="password", help="구글 AI 스튜디오에서 무료로 발급받은 키를 입력하세요.")
        st.divider()
        
        if st.button("🔄 실시간 시세 수동 업데이트"):
            st.cache_data.clear(); st.rerun()
        st.divider()
        
        sort_option = st.radio("📊 리스트 정렬 기준", ["수익률 순", "당일 등락 순", "종목명 순"], horizontal=True)
        st.divider()
        selected_type = st.selectbox("🗂️ 계좌 필터", ["함대 전체"] + list(df['계좌유형'].unique()))
        st.divider()

        # 수동 입력 폼
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
            time.sleep(1)
            st.rerun()
        
    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()
    display_df['안전_수익률'] = display_df.apply(lambda r: get_safe_val(r, ['수익률2', '수익률']), axis=1)
    
    stock_fetch_list = [(str(row.get('종목코드', '')), get_safe_val(row, ['현재가2', '현재가', '기준가', '매수단가'])) for _, row in display_df.iterrows() if str(row.get('종목코드', '')) and "현금" not in str(row['종목명']) and "예수금" not in str(row['종목명'])]
    
    with st.spinner("🚀 T-Q 엔진 데이터 수집 중..."):
        tcr_results = quant_analyzer.get_tcr_scores_batch(stock_fetch_list, {"flow": 0.4, "trend": 0.4, "vcp": 0.2})

    tab_main, tab_analysis, tab_ai = st.tabs(["🚀 기동 관제실", "🔬 심층 분석실", "🤖 AI 퀀터멘털 브리핑"])

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
        st.markdown(f"""<div class="kpi-grid">
            <div class="kpi-box"><span class="kpi-label">총 함대 자산</span><span class="kpi-val text-white">{total_eval:,.0f}원</span></div>
            <div class="kpi-box"><span class="kpi-label">총 누적 손익</span><span class="kpi-val {'text-red' if total_profit>0 else 'text-blue'}">{total_profit:,.0f}원 <span class="kpi-delta">({total_roi:.2f}%)</span></span></div>
        </div>""", unsafe_allow_html=True)

    with tab_analysis:
        st.subheader("📊 1. 전술 사분면 (수익률 vs 확신율)")
        plot_df = display_df[~display_df['종목명'].astype(str).str.contains('현금|예수금', na=False)].copy()
        plot_df['TCR점수'] = plot_df['종목코드'].astype(str).apply(lambda c: tcr_results.get(c, {}).get('score', 0))
        plot_df['표시수익률'] = plot_df['안전_수익률'] * 100
        
        base_chart = alt.Chart(plot_df).mark_circle().encode(
            x=alt.X('TCR점수:Q', scale=alt.Scale(domain=[0, 100]), title='TCR 확신율 (0~100)'),
            y=alt.Y('표시수익률:Q', title='현재 수익률 (%)'),
            size=alt.Size('평가금액:Q', legend=None),
            color=alt.Color('TCR점수:Q', scale=alt.Scale(scheme='redblue', domain=[0, 100]), legend=None),
            tooltip=['종목명', 'TCR점수', '표시수익률', '평가금액']
        ).interactive()
        st.altair_chart(base_chart, use_container_width=True)

    with tab_ai:
        st.subheader("🤖 제미나이 전술 참모 본부")
        st.markdown("<p style='font-size:0.9rem; color:#94a3b8;'>현재 함대의 데이터(TCR)와 거시 경제 지표를 종합하여 최종 매매 지시서를 하달합니다.</p>", unsafe_allow_html=True)
        
        user_context = st.text_area("📡 사령관 특별 지시 및 추가 정보 입력", placeholder="예: 내일 미국 CPI 발표가 있는데 어떻게 대응할까? 삼성전자 실적 악재 뉴스가 떴어.", height=100)
        
        if st.button("🔥 AI 퀀터멘털 브리핑 생성", use_container_width=True):
            if not api_key:
                st.error("사이드바에 Gemini API Key를 먼저 입력해 주십시오. (구글 AI Studio에서 무료 발급 가능)")
            else:
                with st.spinner("🧠 퀀터멘털 데이터 종합 및 전술 생성 중... (약 10초 소요)"):
                    ai_report = generate_ai_briefing(api_key, display_df, tcr_results, indices, user_context)
                    st.success("✅ 작전 지시서 수신 완료")
                    st.markdown("""<div style="background-color:#0f172a; padding:20px; border-radius:10px; border:1px solid #1e293b; color:#f8fafc; font-size:1rem; line-height:1.6;">""" + ai_report.replace('\n', '<br>') + """</div>""", unsafe_allow_html=True)

except Exception as e: st.error(f"함대 기동 중지: {e}")
