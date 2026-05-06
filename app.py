import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- [거북이-퀀터멘털] 시스템 설정 ---
st.set_page_config(page_title="거북이-퀀터멘털 관제소", layout="wide")

@st.cache_data(ttl=60)
def load_data():
    key_dict = json.loads(st.secrets["google_credentials"])
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # 사령관님의 주소 (이미 설정된 주소를 그대로 사용하십시오)
    sheet_url = "https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0"
    doc = client.open_by_url(sheet_url)
    sheet = doc.get_worksheet(0)
    return pd.DataFrame(sheet.get_all_records())

# --- 분석 로직 가동 ---
try:
    df = load_data()
    
    st.title("🐢 거북이-퀀터멘털 실시간 관제 시스템")
    
    # 1. 데이터 무결성: 핵심 지표 강조 및 색상 적용
    def highlight_data(val):
        # 개선 후(수익 등)는 Steel Blue, 기본은 Slate Gray
        color = '#4682B4' if str(val).startswith('+') else '#6C7A89'
        return f'color: {color}'

    # 2. 데이터 시각화 (사령관님 지침 준수)
    st.subheader("📊 실시간 포트폴리오 분석 보고")
    
    # 열 이름이 시트와 정확히 일치해야 합니다. (현재가, 수익률 등)
    # 데이터프레임 스타일링
    st.dataframe(df.style.format(precision=0)
                 .set_properties(**{'font-weight': 'bold'}, subset=['종목명']) # 종목명 강조
                 .applymap(highlight_data))

    # 3. 데이터 무결성 및 분석 수칙 범례 (Legend) 자동 생성
    st.divider()
    st.markdown("### 📋 분석 범례 및 데이터 무결성 수칙")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**[데이터 규격]**")
        st.write("- **Slate Gray (108,122,137)**: 일반/개선 전 데이터")
        st.write("- **Steel Blue (70,130,180)**: 핵심/개선 후 데이터")
    with col2:
        st.write("**[분석 공식]**")
        st.write("- **가중 평균(Weighted Mean)**: $\sum (수익률 \\times 비중)$")
        st.write("- **핵심 관리**: **PPID**, **UPEH** 지표 상시 모니터링 중")

except Exception as e:
    st.error(f"❌ 시스템 통신 오류: {e}")
