import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json, requests, time
from bs4 import BeautifulSoup
import quant_analyzer
import altair as alt

# --- 최상단 설정 ---
st.set_page_config(page_title="거북이 함대 기동 본부 V0.8", layout="wide", initial_sidebar_state="expanded")

# Secrets 키 자동 로드 (보안 유지)
auto_api_key = st.secrets.get("gemini_api_key", "")

# --- V0.4.1 프리미엄 디자인 CSS 완벽 복원 ---
st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    .hq-title { font-size: 1.3rem; color: #4682B4; font-weight: 800; letter-spacing: 1px; margin-bottom: 15px; }
    .index-container { display: flex; flex-wrap: wrap; justify-content: space-between; background: #0f172a; padding: 10px 15px; border-radius: 10px; border: 1px solid #1e293b; margin-bottom: 15px; }
    .index-item { display: flex; flex-direction: column; align-items: center; width: 24%; }
    .index-name { font-size: 0.75rem; color: #6c7a89; font-weight: 700; }
    .index-val { font-size: 1rem; font-weight: 800; }
    .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }
    .kpi-box { background: #0f172a; padding: 12px; border-radius: 10px; border: 1px solid #1e293b; text-align: left; }
    .kpi-label { font-size: 0.75rem; color: #6c7a89; font-weight: 700; margin-bottom: 4px; display: block; }
    .kpi-val { font-size: 1.3rem; font-weight: 800; letter-spacing: -0.5px; }
    
    /* 종목 카드 시인성 극대화 */
    details.premium-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 8px; margin-bottom: 6px; }
    summary { padding: 12px 16px; cursor: pointer; list-style: none; }
    .card-header-flex { display: flex; justify-content: space-between; align-items: center; width: 100%; }
    .stock-name { font-size: 0.95rem; font-weight: 700; color: #ffffff; }
    .val-box { text-align: right; }
    .val-num { font-size: 1rem; font-weight: 800; color: #4682B4; }
    .profit-tag { font-size: 0.8rem; font-weight: 700; margin-left: 8px; }
    
    .text-red { color: #ef4444 !important; }
    .text-blue { color: #4682B4 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 데이터 로드 (배열 방식 우선) ---
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
        if col not in ['계좌번호', '계좌유형', '종목명', '종목코드']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', '').str.replace('%', ''), errors='coerce').fillna(0)
    df = df[df['종목명'].astype(str).str.strip() != '']
    return sheet, df, full_df

def get_safe_val(r, cols):
    for c in cols:
        v = r.get(c, 0)
        if v != 0 and pd.notna(v): return v
    return 0

# --- AI 브리핑 통신망 (V0.6.2 규격 이식) ---
def generate_ai_briefing(api_key, portfolio_df, tcr_results, user_context):
    pf_summary = [f"- {r['종목명']}: 수익률 {r.get('안전_수익률',0)*100:.1f}%, TCR {tcr_results.get(str(r['종목코드']),{}).get('score',0)}%" for _, r in portfolio_df.iterrows() if "현금" not in str(r['종목명'])]
    prompt = f"참모 브리핑. [지시]: {user_context}\n[현황]: {chr(10).join(pf_summary)}\n🌍요약, 🎯진단, 🔥매매지시(단호하게)"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key.strip()}"
    try:
        res = requests.post(url, headers={'Content-Type': 'application/json'}, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
        return res.json()['candidates'][0]['content']['parts'][0]['text'] if res.status_code == 200 else "🚨 통신 지연 중..."
    except: return "🚨 통신망 확인 요망"

# --- 메인 로직 ---
try:
    sheet, df, full_df = load_data()
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V0.8 [RESTORED]</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        if st.button("🔄 실시간 시세 수동 업데이트"): st.cache_data.clear(); st.rerun()
        st.divider()
        mode = st.radio("작전 모드", ["함대 관측", "종목 완전 삭제", "신규 종목 추가"])
        if mode == "종목 완전 삭제":
            del_target = st.selectbox("삭제 종목", df['종목명'].tolist())
            if st.button("❌ 격멸"):
                idx = full_df[full_df['종목명'] == del_target].index[0] + 2
                sheet.delete_rows(int(idx)); st.success("삭제 완료"); time.sleep(1); st.rerun()

    # 데이터 전처리
    display_df = df.copy()
    display_df['안전_수익률'] = display_df.apply(lambda r: get_safe_val(r, ['수익률2', '수익률']), axis=1)
    stock_fetch_list = [(str(row.get('종목코드', '')), get_safe_val(row, ['현재가2', '현재가', '기준가'])) for _, row in display_df.iterrows() if str(row.get('종목코드', '')) and "현금" not in str(row['종목명'])]
    
    with st.spinner("🚀 TCR 엔진 가동 중..."):
        tcr_results = quant_analyzer.get_tcr_scores_batch(stock_fetch_list, {"flow": 0.4, "trend": 0.4, "vcp": 0.2})

    tab1, tab2, tab3 = st.tabs(["🚀 기동 관제실", "🔬 심층 분석실", "🤖 AI 브리핑"])

    with tab1:
        total_eval = display_df['평가금액'].sum()
        total_profit = display_df['평가손익'].sum()
        roi = (total_profit / (total_eval - total_profit) * 100) if (total_eval - total_profit) > 0 else 0
        
        st.markdown(f"""<div class="kpi-grid">
            <div class="kpi-box"><span class="kpi-label">총 함대 자산</span><span class="kpi-val">{total_eval:,.0f}</span></div>
            <div class="kpi-box"><span class="kpi-label">누적 손익</span><span class="kpi-val {'text-red' if total_profit>0 else 'text-blue'}">{total_profit:,.0f}</span></div>
            <div class="kpi-box"><span class="kpi-label">누적 수익률</span><span class="kpi-val {'text-red' if roi>0 else 'text-blue'}">{roi:.2f}%</span></div>
            <div class="kpi-box"><span class="kpi-label">기동 상태</span><span class="kpi-val text-blue">정상</span></div>
        </div>""", unsafe_allow_html=True)

        for _, row in display_df.sort_values(by='안전_수익률', ascending=False).iterrows():
            now_p = get_safe_val(row, ['현재가2', '현재가', '기준가'])
            tcr = tcr_results.get(str(row.get('종목코드', '')), {"score": 0, "status": "관측중", "color": "#6c7a89"})
            is_up = row['안전_수익률'] >= 0
            
            st.markdown(f"""
            <details class="premium-card">
                <summary><div class="card-header-flex">
                    <span class="stock-name">{row['종목명']}</span>
                    <div class="val-box">
                        <span class="val-num">{now_p:,.0f}</span>
                        <span class="profit-tag {'text-red' if is_up else 'text-blue'}">{row['안전_수익률']*100:+.2f}%</span>
                    </div>
                </div></summary>
                <div style="padding:12px; border-top:1px solid #1e293b; font-size:0.85rem;">
                    🔥 AI 확신율(TCR): <span style="color:{tcr['color']}; font-weight:800;">{tcr['score']}% ({tcr['status']})</span><br>
                    평가손익: {row['평가손익']:,.0f}원 / 보유수량: {row.get('잔고수량',0)}주
                </div>
            </details>""", unsafe_allow_html=True)

    with tab2:
        st.subheader("📊 전술 사분면 (V0.4 복원)")
        plot_df = display_df[~display_df['종목명'].astype(str).str.contains('현금|예수금')].copy()
        plot_df['TCR점수'] = plot_df['종목코드'].astype(str).apply(lambda c: tcr_results.get(c, {}).get('score', 0))
        plot_df['표시수익률'] = plot_df['안전_수익률'] * 100
        chart = alt.Chart(plot_df).mark_circle(size=150).encode(
            x=alt.X('TCR점수:Q', title='TCR'), y=alt.Y('표시수익률:Q', title='수익률(%)'),
            color=alt.Color('TCR점수:Q', scale=alt.Scale(scheme='redblue')), tooltip=['종목명', 'TCR점수', '표시수익률']
        ).properties(height=450, background='transparent').interactive()
        st.altair_chart(chart, use_container_width=True)

    with tab3:
        st.subheader("🤖 제미나이 전술 참모")
        user_context = st.text_area("📡 특별 지시", placeholder="예: 오늘 미국 지표 발표 대응 전략은?")
        if st.button("🔥 작전 지시서 생성"):
            if not auto_api_key: st.error("Secrets에 키를 등록하십시오.")
            else:
                with st.spinner("🧠 퀀터멘털 데이터 종합 분석 중..."):
                    report = generate_ai_briefing(auto_api_key, display_df, tcr_results, user_context)
                    st.markdown(f"<div style='background:#0f172a; padding:20px; border-radius:10px; border-left:4px solid #4682B4;'>{report.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)

except Exception as e: st.error(f"기동 실패: {e}")
