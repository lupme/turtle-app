import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json, requests, time
from bs4 import BeautifulSoup
import quant_analyzer
import altair as alt

# --- 설정 및 스타일 ---
st.set_page_config(page_title="거북이 함대 기동 본부 V0.7", layout="wide", initial_sidebar_state="expanded")

# Secrets 키 로드
auto_api_key = st.secrets.get("gemini_api_key", "")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    h1, h2, h3, p, span, div { font-family: 'Noto Sans KR', sans-serif; }
    .hq-title { font-size: 1.4rem; color: #4682B4; font-weight: 800; padding: 10px 0; margin-bottom: 15px; }
    .index-container { display: flex; flex-wrap: wrap; justify-content: space-between; background: #0f172a; padding: 10px 15px; border-radius: 10px; border: 1px solid #1e293b; margin-bottom: 15px; }
    .index-item { display: flex; flex-direction: column; align-items: center; width: 24%; }
    .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
    .kpi-box { background: #0f172a; padding: 12px; border-radius: 10px; border: 1px solid #1e293b; text-align: center; }
    .kpi-label { font-size: 0.75rem; color: #6c7a89; font-weight: 700; }
    .kpi-val { font-size: 1.2rem; font-weight: 800; color: #ffffff; }
    details.premium-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 10px; margin-bottom: 8px; }
    .card-header-flex { display: flex; justify-content: space-between; align-items: center; padding: 12px 15px; cursor: pointer; }
    .stock-name { font-size: 1rem; font-weight: 700; color: #ffffff; }
    .val-num { font-size: 1rem; font-weight: 800; color: #4682B4; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: 700; background-color: #1e293b; color: #f8fafc; height: 45px; }
    </style>
    """, unsafe_allow_html=True)

# --- 데이터 엔진 ---
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

def get_safe_val(r, cols):
    for c in cols:
        v = r.get(c, 0)
        if v != 0 and pd.notna(v): return v
    return 0

# --- 통신망 ---
def generate_ai_briefing(api_key, portfolio_df, tcr_results, user_context):
    pf_summary = [f"- {r['종목명']}: 수익률 {r.get('안전_수익률',0)*100:.1f}%, TCR {tcr_results.get(str(r['종목코드']),{}).get('score',0)}%" for _, r in portfolio_df.iterrows() if "현금" not in str(r['종목명'])]
    prompt = f"사령관 특별지시: {user_context}\n[함대현황]: {chr(10).join(pf_summary)}\n🌍글로벌요약, 🎯진단, 🔥작전지시"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key.strip()}"
    try:
        res = requests.post(url, headers={'Content-Type': 'application/json'}, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except: return "🚨 통신망 확인 요망 (Secrets 키 혹은 구글서버 확인)"

# --- 메인 기동 ---
try:
    sheet, df, full_df = load_data()
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V0.7</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        api_key = st.text_input("Gemini API Key", value=auto_api_key, type="password")
        if st.button("🔄 실시간 시세 업데이트"): st.cache_data.clear(); st.rerun()
        
        st.divider()
        mode = st.radio("작전 모드", ["기존 종목 매매", "데이터 강제 수정", "신규 종목 추가", "종목 완전 삭제"])
        acc_opts = [f"{r['계좌유형']} [{r['계좌번호']}]" for _, r in full_df[['계좌유형', '계좌번호']].drop_duplicates().iterrows() if str(r['계좌번호']).strip() != '']
        sel_acc_str = st.selectbox("대상 계좌", acc_opts)
        
        if mode == "종목 완전 삭제":
            del_target = st.selectbox("삭제 종목 선택", df['종목명'].tolist())
            if st.button("❌ 삭제 확정"):
                idx = full_df[full_df['종목명'] == del_target].index[0] + 2
                sheet.delete_rows(int(idx))
                st.success("격멸 완료."); time.sleep(1); st.rerun()
        else:
            st.info("수동 데이터 연동 대기 중...")

    # 데이터 전처리
    display_df = df.copy()
    display_df['안전_수익률'] = display_df.apply(lambda r: get_safe_val(r, ['수익률2', '수익률']), axis=1)
    stock_fetch_list = [(str(row.get('종목코드', '')), get_safe_val(row, ['현재가2', '현재가', '기준가', '매수단가'])) for _, row in display_df.iterrows() if str(row.get('종목코드', '')) and "현금" not in str(row['종목명'])]
    
    with st.spinner("🚀 함대 레이더 가동 중..."):
        tcr_results = quant_analyzer.get_tcr_scores_batch(stock_fetch_list, {"flow": 0.4, "trend": 0.4, "vcp": 0.2})

    # 메인 탭
    tab_main, tab_analysis, tab_ai = st.tabs(["🚀 관제실", "🔬 심층 분석실", "🤖 AI 브리핑"])

    with tab_main:
        total_eval = display_df['평가금액'].sum()
        total_profit = display_df['평가손익'].sum()
        st.markdown(f"""<div class="kpi-grid">
            <div class="kpi-box"><span class="kpi-label">총 자산</span><br><span class="kpi-val">{total_eval:,.0f}원</span></div>
            <div class="kpi-box"><span class="kpi-label">누적 손익</span><br><span class="kpi-val {'text-red' if total_profit>0 else 'text-blue'}">{total_profit:,.0f}원</span></div>
        </div>""", unsafe_allow_html=True)

        for _, row in display_df.sort_values(by='안전_수익률', ascending=False).iterrows():
            now_p = get_safe_val(row, ['현재가2', '현재가', '기준가', '매수단가'])
            tcr = tcr_results.get(str(row.get('종목코드', '')), {"score": 0, "status": "부족", "color": "#6c7a89"})
            st.markdown(f"""<details class="premium-card"><summary><div class="card-header-flex">
                <span class="stock-name">{row['종목명']}</span><span class="val-num">{now_p:,.0f}원</span></div></summary>
                <div style="padding:15px; border-top:1px solid #1e293b; font-size:0.9rem;">
                수익률: {row['안전_수익률']*100:+.2f}% / 🔥확신율: <span style="color:{tcr['color']}">{tcr['score']}% ({tcr['status']})</span></div></details>""", unsafe_allow_html=True)

    with tab_analysis:
        st.subheader("📊 전술 사분면 (수익률 vs 확신율)")
        plot_df = display_df[~display_df['종목명'].astype(str).str.contains('현금|예수금')].copy()
        plot_df['TCR점수'] = plot_df['종목코드'].astype(str).apply(lambda c: tcr_results.get(c, {}).get('score', 0))
        plot_df['표시수익률'] = plot_df['안전_수익률'] * 100
        chart = alt.Chart(plot_df).mark_circle(size=150).encode(
            x=alt.X('TCR점수:Q', title='AI 확신율 (TCR)'), y=alt.Y('표시수익률:Q', title='내 계좌 수익률 (%)'),
            color=alt.Color('TCR점수:Q', scale=alt.Scale(scheme='redblue')), tooltip=['종목명', 'TCR점수', '표시수익률']
        ).properties(height=450).interactive()
        st.altair_chart(chart, use_container_width=True)

    with tab_ai:
        st.subheader("🤖 제미나이 전술 참모")
        user_context = st.text_area("📡 사령관 지시사항", placeholder="예: 오늘 시장 변동성이 큰데 어떤 전략이 좋을까?")
        if st.button("🔥 최종 작전 지시서 생성", use_container_width=True):
            if not api_key: st.error("API Key 미등록됨")
            else:
                with st.spinner("🧠 데이터 종합 분석 중..."):
                    report = generate_ai_briefing(api_key, display_df, tcr_results, user_context)
                    st.markdown(f"<div style='background:#0f172a; padding:20px; border-radius:12px; border:1px solid #4682B4; line-height:1.6;'>{report.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)

except Exception as e: st.error(f"함대 기동 중지: {e}")
