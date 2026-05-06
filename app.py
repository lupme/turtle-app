import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- [1] 보안 및 환경 설정 ---
st.set_page_config(page_title="거북이-퀀터멘털 관제소", layout="wide")

@st.cache_data(ttl=60)
def load_data():
    key_dict = json.loads(st.secrets["google_credentials"])
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    sheet_url = "https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0"
    doc = client.open_by_url(sheet_url)
    sheet = doc.get_worksheet(0)
    return pd.DataFrame(sheet.get_all_records())

# --- [2] 디자인 및 데이터 무결성 수칙 (보정됨) ---
def apply_commander_style(df):
    def color_rule(val):
        try:
            # 숫자형 변환 시 발생할 수 있는 오류 원천 차단
            str_val = str(val).replace('%', '').replace(',', '').replace('+', '').strip()
            num_val = float(str_val) if str_val else 0.0
            return 'color: #4682B4; font-weight: bold;' if num_val > 0 else 'color: #6C7A89;'
        except:
            return 'color: #6C7A89;'

    styled = df.style.map(color_rule)
    bold_cols = [c for c in ['종목명', 'PPID', 'UPEH', '계좌번호'] if c in df.columns]
    if bold_cols:
        styled = styled.set_properties(**{'font-weight': 'black'}, subset=bold_cols)
    return styled

# --- [3] 메인 관제소 기동 ---
try:
    df = load_data()
    st.title("🐢 거북이-퀀터멘털 실시간 관제 시스템")
    
    # 3-1. 총 자산 요약 (에러 방지형 계산)
    if '평가금액' in df.columns:
        total_eval = pd.to_numeric(df['평가금액'], errors='coerce').sum()
        st.metric("📊 총 평가 자산", f"{total_eval:,.0f} KRW")

    # 3-2. [핵심] 계좌별 분리 탭 디자인
    if '계좌번호' in df.columns and not df['계좌번호'].empty:
        # 계좌번호가 섞여 있어도 깨끗하게 분류
        accounts = [str(acc) for acc in df['계좌번호'].unique() if str(acc).strip()]
        tabs = st.tabs([f"📂 {acc}" for acc in accounts] + ["🌍 전체 통합"])

        for i, acc in enumerate(accounts):
            with tabs[i]:
                acc_df = df[df['계좌번호'].astype(str) == acc]
                st.dataframe(apply_commander_style(acc_df), use_container_width=True)
        
        with tabs[-1]:
            st.dataframe(apply_commander_style(df), use_container_width=True)
    else:
        st.dataframe(apply_commander_style(df), use_container_width=True)

    # --- [4] 하단 범례 고정 ---
    st.divider()
    st.markdown("### 📋 분석 범례 및 운영 지침")
    st.info("🟦 Steel Blue: 수익/핵심 지표 | ⬜ Slate Gray: 기본/이전 데이터 | 🔄 60초 자동 동기화")

except Exception as e:
    st.error(f"⚠️ 시스템 통신 오류: {e}")
