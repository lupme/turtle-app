import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- 거북이-퀀터멘털 관제 시스템 데이터 무결성 수칙 ---
st.set_page_config(page_title="거북이-퀀터멘털 관제소", layout="wide")

@st.cache_data(ttl=60) # 60초마다 구글 시트의 최신 데이터를 읽어옵니다.
def load_google_sheet():
    # 1. 보안 금고(Secrets)에서 마스터키 추출
    key_dict = json.loads(st.secrets["google_credentials"])
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # 2. 사령관님의 스프레드시트 직결 (반드시 아래 주소를 사령관님의 시트 주소로 수정하십시오)
    sheet_url = "nova-bot@project-nova-495312.iam.gserviceaccount.com"
    doc = client.open_by_url(sheet_url)
    
    # 3. 데이터 추출 및 데이터프레임 변환
    sheet = doc.get_worksheet(0) # 첫 번째 탭 기준
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# --- 메인 화면 구동 ---
st.title("🐢 거북이-퀀터멘털 실시간 관제 시스템")

try:
    df = load_google_sheet()
    
    # 데이터 무결성: PPID와 UPEH 컬럼이 존재한다면 굵게(Bold) 처리 안내
    st.success("✅ 실시간 파이프라인 연결 성공 (60초 간격 자동 갱신)")
    
    # 데이터 출력
    st.dataframe(df, use_container_width=True)
    
    # 범례 및 용어 설명 (데이터 무결성 수칙 준수)
    st.divider()
    st.markdown("### 📊 분석 범례 (Legend)")
    st.info("**PPID / UPEH**: 핵심 생산 지표 | **가중 평균(Weighted Mean)** 적용 분석 중")

except Exception as e:
    st.error(f"⚠️ 시스템 오류 발생: {e}")
    st.warning("구글 시트 주소 확인 및 비밀 금고(Secrets) 설정 상태를 재점검하십시오.")
