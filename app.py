import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

st.title("🛡️ 시스템 연결 진단 모드")

try:
    # [1] Secrets 로드 확인
    st.write("1. Secrets 로드 중...")
    key_info = json.loads(st.secrets["google_credentials"])
    st.success("Secrets 로드 완료!")

    # [2] 구글 시트 연결 확인
    st.write("2. 구글 시트 연결 시도...")
    creds = Credentials.from_service_account_info(key_info, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
    client = gspread.authorize(creds)
    
    # 사령관님의 시트 URL 직접 입력
    sheet_url = "https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0"
    sheet = client.open_by_url(sheet_url).get_worksheet(0)
    data = pd.DataFrame(sheet.get_all_records())
    
    st.success(f"시트 연결 성공! 데이터 {len(data)}건 발견.")
    st.write("--- 데이터 샘플 ---")
    st.dataframe(data.head()) # 데이터가 화면에 보이면 성공!

except Exception as e:
    st.error(f"❌ 진단 실패: {e}")
    st.info("이 에러 메시지를 저에게 알려주시면 즉시 해결책을 찾겠습니다.")
