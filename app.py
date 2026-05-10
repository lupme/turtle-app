import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json, requests, time
from bs4 import BeautifulSoup
import quant_analyzer
import altair as alt

# --- 기본 설정 및 디자인 원복 ---
st.set_page_config(page_title="거북이 함대 기동 본부 V0.6.5", layout="wide", initial_sidebar_state="expanded")

# Secrets 키 로드
auto_api_key = st.secrets.get("gemini_api_key", "")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700;900&display=swap');
    .stApp { background-color: #020617; color: #f8fafc; }
    h1, h2, h3, p, span, div, summary { font-family: 'Noto Sans KR', sans-serif; }
    
    /* 헤더 디자인 */
    .hq-title { font-size: 1.5rem; color: #4682B4; font-weight: 900; padding: 15px 0; border-bottom: 2px solid #1e293b; margin-bottom: 20px; text-align: center; }
    
    /* KPI 카드 */
    .kpi-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 20px; }
    .kpi-box { background: #0f172a; padding: 15px; border-radius: 12px; border: 1px solid #1e293b; text-align: center; }
    .kpi-label { font-size: 0.85rem; color: #6c7a89; font-weight: 700; margin-bottom: 5px; display: block; }
    .kpi-val { font-size: 1.4rem; font-weight: 900; letter-spacing: -0.5px; }
    
    /* 모바일 최적화 종목 카드 */
    details.premium-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 12px; margin-bottom: 10px; overflow: hidden; }
    summary { padding: 16px; cursor: pointer; list-style: none; }
    .card-header { display: flex; flex-direction: column; gap: 5px; }
    .stock-title { font-size: 1.1rem; font-weight: 800; color: #ffffff; }
    .price-row { display: flex; justify-content: space-between; align-items: center; }
    .current-price { font-size: 1.2rem; font-weight: 900; color: #4682B4; }
    .profit-tag { font-size: 0.9rem; font-weight: 700; padding: 2px 8px; border-radius: 5px; }
    
    /* 텍스트 색상 */
    .text-blue { color: #4682B4; }
    .text-red { color: #ef4444; }
    .text-gray { color: #6c7a89; }
    
    /* 버튼 스타일 */
    .stButton>button { width: 100%; border-radius: 10px; font-weight: 700; height: 50px; background-color: #1e293b; border: 1px solid #334155; color: #f8fafc; }
    .stButton>button:hover { border-color: #4682B4; color: #4682B4; }
    </style>
    """, unsafe_allow_html=True)

# --- 데이터 로드 및 처리 ---
def get_gspread_client():
    key_info = json.loads(st.secrets["google_credentials"])
    if "private_key" in key_info: key_info["private_key"] = key_info["private_key"].replace("\\n", "\n")
    return gspread.authorize(Credentials.from_service_account_info(key_info, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']))

@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0").get_worksheet(0)
    df = pd.DataFrame(sheet.get_all_records())
    df = df[df['종목명'].astype(str).str.strip() != ''].copy()
    for col in ['평가금액', '평가손익', '수익률', '현재가', '매수단가']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', '').str.replace('%', ''), errors='coerce').fillna(0)
    return sheet, df

def get_safe_val(r, cols):
    for c in cols:
        v = r.get(c, 0)
        if v != 0 and pd.notna(v): return v
    return 0

# --- 통신 모듈 (안정화 버전) ---
def generate_ai_briefing(api_key, portfolio_df, tcr_results, user_context):
    clean_key = api_key.strip()
    pf_summary = [f"- {r['종목명']}: 수익률 {r['수익률']*100:.1f}%, TCR {tcr_results.get(str(r['종목코드']),{}).get('score',0)}%" for _, r in portfolio_df.iterrows() if "현금" not in str(r['종목명'])]
    prompt = f"사령관 지시: {user_context}\n\n포트폴리오 요약:\n{chr(10).join(pf_summary)}\n\n위 데이터를 기반으로 전략 브리핑을 실시하라. (글로벌 시황, 종목 진단, 작전 지시 포함)"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={clean_key}"
    try:
        res = requests.post(url, headers={'Content-Type': 'application/json'}, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
        return res.json()['candidates'][0]['content']['parts'][0]['text'] if res.status_code == 200 else f"통신 실패 (코드: {res.status_code})"
    except: return "통신망 연결 확인 요망"

# --- 메인 기동 ---
try:
    sheet, df = load_data()
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V0.6.5</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        api_key = st.text_input("Gemini API Key (Secrets 연동됨)", value=auto_api_key, type="password")
        if st.button("🔄 시세 업데이트"): st.cache_data.clear(); st.rerun()
        
        st.divider()
        st.subheader("🗑️ 함대 정비")
        delete_target = st.selectbox("삭제할 종목 선택", ["선택 안 함"] + df['종목명'].tolist())
        if st.button("❌ 종목 삭제 실행") and delete_target != "선택 안 함":
            # 시트에서 해당 행 삭제 로직 (실제 운영 시 주의)
            target_idx = df[df['종목명'] == delete_target].index[0] + 2 
            sheet.delete_rows(target_idx)
            st.success(f"{delete_target} 삭제 완료! 시세 업데이트를 눌러주세요.")

    # KPI 섹션
    total_eval = df['평가금액'].sum()
    total_profit = df['평가손익'].sum()
    st.markdown(f"""<div class="kpi-grid">
        <div class="kpi-box"><span class="kpi-label">총 자산</span><span class="kpi-val">{total_eval:,.0f}</span></div>
        <div class="kpi-box"><span class="kpi-label">누적 손익</span><span class="kpi-val {'text-red' if total_profit>0 else 'text-blue'}">{total_profit:,.0f}</span></div>
    </div>""", unsafe_allow_html=True)

    tab_main, tab_ai = st.tabs(["🚀 관제실", "🤖 AI 브리핑"])

    with tab_main:
        # 모바일 시인성 최적화 리스트
        for _, row in df.sort_values(by='수익률', ascending=False).iterrows():
            is_profit = row['수익률'] >= 0
            color_class = "text-red" if is_profit else "text-blue"
            
            st.markdown(f"""
            <details class="premium-card">
                <summary>
                    <div class="card-header">
                        <div class="stock-title">{row['종목명']}</div>
                        <div class="price-row">
                            <span class="current-price">{row['현재가']:,.0f}원</span>
                            <span class="profit-tag {color_class}" style="background: {'#fee2e2' if is_profit else '#e0f2fe'}">
                                {row['수익률']*100:+.2f}%
                            </span>
                        </div>
                    </div>
                </summary>
                <div style="padding:15px; border-top:1px solid #1e293b; font-size:0.9rem;">
                    평가금액: {row['평가금액']:,.0f}원<br>
                    평가손익: <span class="{color_class}">{row['평가손익']:,.0f}원</span><br>
                    매수단가: {row['매수단가']:,.0f}원
                </div>
            </details>
            """, unsafe_allow_html=True)

    with tab_ai:
        st.subheader("🤖 제미나이 전술 참모")
        user_context = st.text_area("사령관 특별 지시", placeholder="예: 오늘 삼성전자 흐름에 맞춰서 포트 재조정 제안해줘.")
        if st.button("🔥 작전 지시서 생성"):
            if not api_key: st.error("API Key가 없습니다. Secrets를 확인하거나 직접 입력하세요.")
            else:
                with st.spinner("🧠 데이터 분석 및 전략 수립 중..."):
                    # TCR은 임시로 0 처리 (필요 시 로직 추가)
                    report = generate_ai_briefing(api_key, df, {}, user_context)
                    st.markdown(f"<div style='background:#0f172a; padding:20px; border-radius:12px; border:1px solid #4682B4; line-height:1.6;'>{report.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)

except Exception as e:
    st.error(f"함대 기동 중 오류 발생: {e}")
