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

# --- [2] 디자인 및 데이터 무결성 수칙 적용 ---
def apply_commander_style(df):
    def color_rule(val):
        try:
            # 수익률(%) 문자를 숫자로 변환하여 판별
            num_val = float(str(val).replace('%', '').replace(',', '').replace('+', ''))
            return 'color: #4682B4; font-weight: bold;' if num_val > 0 else 'color: #6C7A89;'
        except:
            return 'color: #6C7A89;'

    styled = df.style.map(color_rule)
    # 핵심 데이터 Bold 및 가독성 강화
    bold_cols = [c for c in ['종목명', 'PPID', 'UPEH', '계좌번호'] if c in df.columns]
    if bold_cols:
        styled = styled.set_properties(**{'font-weight': 'black'}, subset=bold_cols)
    return styled

# --- [3] 메인 관제소 기동 ---
try:
    df = load_data()
    st.title("🐢 거북이-퀀터멘털 실시간 관제 시스템")
    
    # 3-1. 최상단 핵심 요약 (전체 자산 등)
    total_eval = df['평가금액'].sum() if '평가금액' in df.columns else 0
    st.metric("📊 총 평가 자산", f"{total_eval:,.0f} KRW")

    # 3-2. [핵심 기능] 계좌별 분리 보기
    if '계좌번호' in df.columns:
        accounts = df['계좌번호'].unique()
        tabs = st.tabs([f"📂 {acc}" for acc in accounts] + ["🌍 전체 통합"])

        # 각 계좌별 탭 구성
        for i, acc in enumerate(accounts):
            with tabs[i]:
                acc_df = df[df['계좌번호'] == acc]
                st.subheader(f"📍 {acc} 계좌 상세 보고")
                st.dataframe(apply_commander_style(acc_df), use_container_width=True)
        
        # 통합 탭
        with tabs[-1]:
            st.subheader("🌍 전체 계좌 통합 현황")
            st.dataframe(apply_commander_style(df), use_container_width=True)
    else:
        st.dataframe(apply_commander_style(df), use_container_width=True)

    # --- [4] 데이터 무결성 및 분석 수칙 범례 (자동 생성) ---
    st.divider()
    st.markdown("### 📋 분석 범례 및 데이터 무결성 수칙")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**[데이터 규격]**")
        st.write("- 🟦 **Steel Blue**: 수익/개선/핵심 지표")
        st.write("- ⬜ **Slate Gray**: 기본/이전 데이터")
    with col2:
        st.markdown("**[운영 지침]**")
        st.write("- **가중 평균(Weighted Mean)** 적용 분석")
        st.write("- **데이터 무결성**: 60초 간격 자동 갱신")

except Exception as e:
    st.error(f"⚠️ 관제 시스템 오류: {e}")
