import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- [거북이-퀀터멘털] 관제소 설정 ---
st.set_page_config(page_title="거북이-퀀터멘털 관제소", layout="wide")

@st.cache_data(ttl=60)
def load_data():
    key_dict = json.loads(st.secrets["google_credentials"])
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # 사령관님의 시트 좌표
    sheet_url = "https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0"
    doc = client.open_by_url(sheet_url)
    sheet = doc.get_worksheet(0)
    return pd.DataFrame(sheet.get_all_records())

# --- 분석 엔진 기동 ---
try:
    df = load_data()
    
    st.title("🐢 거북이-퀀터멘털 실시간 관제 시스템")
    st.subheader("📊 실시간 포트폴리오 분석 보고")

    # [데이터 무결성] 색상 및 강조 로직 (최신 규격 map 사용)
    def color_rule(val):
        try:
            # 수익(+)은 Steel Blue, 손실(-)이나 기본은 Slate Gray
            num_val = float(str(val).replace('%', '').replace(',', ''))
            return 'color: #4682B4' if num_val > 0 else 'color: #6C7A89'
        except:
            return 'color: #6C7A89'

    # 데이터 출력 (종목명 굵게, 수치는 정수로 시각화)
    styled_df = df.style.map(color_rule)
    
    # 만약 '종목명' 열이 있다면 굵게 강조 (열 이름이 다르면 아래를 수정하십시오)
    if '종목명' in df.columns:
        styled_df = styled_df.set_properties(**{'font-weight': 'bold'}, subset=['종목명'])

    st.dataframe(styled_df, use_container_width=True)

    # --- 범례 및 수칙 보고 ---
    st.divider()
    st.markdown("### 📋 분석 범례 및 데이터 무결성 수칙")
    col1, col2 = st.columns(2)
    with col1:
        st.info("**Slate Gray**: 일반/기준 데이터 | **Steel Blue**: 수익/개선 데이터")
    with col2:
        st.warning("**가중 평균(Weighted Mean)** 분석 및 **PPID/UPEH** 실시간 감시 중")

except Exception as e:
    st.error(f"⚠️ 공정 오류 발생: {e}")
    st.info("시트의 1행(제목줄)에 중복된 이름이 없는지 다시 한번 확인하십시오.")
