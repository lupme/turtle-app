import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- [1단계] 거북이-퀀터멘털 관제소 보안 및 환경 설정 ---
st.set_page_config(
    page_title="거북이-퀀터멘털 실시간 관제 시스템", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

@st.cache_data(ttl=60) # 60초 데이터 무결성 유지 (자동 갱신)
def fetch_live_data():
    try:
        # 보안 금고에서 마스터키 인출
        key_dict = json.loads(st.secrets["google_credentials"])
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
        client = gspread.authorize(creds)
        
        # 사령관님의 직결 좌표 (URL)
        sheet_url = "https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0"
        doc = client.open_by_url(sheet_url)
        sheet = doc.get_worksheet(0) # 첫 번째 시트 탐지
        
        # 데이터프레임 변환 및 전처리
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        st.error(f"🚨 데이터 추출 공정 오류: {e}")
        return None

# --- [2단계] 디자인 및 시각화 규격 수칙 (전일 디자인 복구) ---
def apply_commander_style(df):
    # 1. 수익/손실 색상 규격 (Steel Blue / Slate Gray)
    def color_logic(val):
        try:
            # 수익률(%)이나 금액에서 숫자만 추출하여 판별
            clean_val = float(str(val).replace('%', '').replace(',', '').replace('+', ''))
            if clean_val > 0:
                return 'color: #4682B4; font-weight: bold;' # Steel Blue (개선 후/수익)
            elif clean_val < 0:
                return 'color: #6C7A89;' # Slate Gray (개선 전/손실)
            return 'color: #6C7A89;'
        except:
            return 'color: #6C7A89;'

    # 스타일 적용 (최신 map 규격 준수)
    styled_df = df.style.map(color_logic)
    
    # 2. 핵심 지표 Bold 처리 (종목명, PPID, UPEH 등 탐지 시 강조)
    bold_targets = ['종목명', '종목', 'PPID', 'UPEH']
    available_targets = [col for col in bold_targets if col in df.columns]
    
    if available_targets:
        styled_df = styled_df.set_properties(**{'font-weight': 'black', 'font-size': '16px'}, subset=available_targets)
    
    return styled_df

# --- [3단계] 관제 화면 기동 ---
df = fetch_live_data()

if df is not None:
    st.title("🐢 거북이-퀀터멘털 실시간 관제 시스템")
    st.markdown(f"**현재 시간:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} (60초 간격 갱신)")
    
    # 상단 요약 대시보드 (객관적 데이터 지표)
    st.divider()
    
    # 메인 분석 표 출력
    st.subheader("📊 실시간 포트폴리오 분석 보고")
    styled_data = apply_commander_style(df)
    st.dataframe(styled_data, use_container_width=True, height=600)

    # --- [4단계] 데이터 무결성 범례 및 분석 수칙 (하단 고정) ---
    st.divider()
    st.markdown("### 📋 분석 범례 및 운영 지침")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**[데이터 색상 규격]**")
        st.write("🟦 **Steel Blue**: 수익/개선/핵심 지표")
        st.write("⬜ **Slate Gray**: 손실/기본/이전 데이터")
    with c2:
        st.markdown("**[분석 공식]**")
        st.write("- **가중 평균**: $\sum (수익률 \\times 비중)$")
        st.write("- **무결성**: 60초 간격 시트 동기화")
    with c3:
        st.markdown("**[사령관 목표]**")
        st.write("- **최종 수익**: 자산의 50% (4.2억↑)")
        st.write("- **전략**: 감정 배제, 데이터 위주 분석")
