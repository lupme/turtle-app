import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- [1] 보안 및 시스템 설정 ---
st.set_page_config(page_title="거북이-퀀터멘털 관제소", layout="wide")

@st.cache_resource
def get_gspread_client():
    key_dict = json.loads(st.secrets["google_credentials"])
    creds = Credentials.from_service_account_info(key_dict, 
        scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
    return gspread.authorize(creds)

def load_data():
    client = get_gspread_client()
    sheet_url = "https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0"
    doc = client.open_by_url(sheet_url)
    sheet = doc.get_worksheet(0)
    return sheet, pd.DataFrame(sheet.get_all_records())

# --- [2] 핵심 로직: 평단 및 수량 자동 계산 ---
def calculate_new_avg(old_qty, old_avg, change_qty, price, action):
    if action == "매수":
        new_qty = old_qty + change_qty
        new_avg = ((old_qty * old_avg) + (change_qty * price)) / new_qty if new_qty > 0 else 0
    else: # 매도
        new_qty = max(0, old_qty - change_qty)
        new_avg = old_avg # 매도는 평단에 영향을 주지 않음
    return new_qty, new_avg

# --- [3] 메인 관제 화면 ---
try:
    sheet, df = load_data()
    st.title("🐢 거북이-퀀터멘털 실시간 관제 시스템")

    # [좌측 사이드바: 매매 및 입력 관제]
    with st.sidebar:
        st.header("⚙️ 실시간 매매 입력")
        target_acc = st.selectbox("계좌 선택", df['계좌번호'].unique())
        
        mode = st.radio("작업 선택", ["기존 종목 업데이트", "신규 종목 추가"])
        
        if mode == "기존 종목 업데이트":
            acc_stocks = df[df['계좌번호'] == target_acc]['종목명'].tolist()
            target_stock = st.selectbox("종목 선택", acc_stocks)
            action = st.selectbox("구분", ["매수", "매도"])
            qty_change = st.number_input("수량(주)", min_value=1, step=1)
            exec_price = st.number_input("실행 단가(원)", min_value=0, step=100)
            
            if st.button("🚀 데이터 무결성 반영"):
                # 계산 및 업데이트 로직 실행
                idx = df[(df['계좌번호'] == target_acc) & (df['종목명'] == target_stock)].index[0]
                old_qty = df.at[idx, '잔고수량']
                old_avg = df.at[idx, '매수단가']
                
                new_qty, new_avg = calculate_new_avg(old_qty, old_avg, qty_change, exec_price, action)
                
                # 구글 시트 업데이트 (gspread 사용)
                row_idx = idx + 2 # 헤더 포함 인덱스 보정
                sheet.update_cell(row_idx, df.columns.get_loc('잔고수량')+1, int(new_qty))
                sheet.update_cell(row_idx, df.columns.get_loc('매수단가')+1, int(new_avg))
                st.success(f"{target_stock} 업데이트 완료!")
                st.rerun()

    # [중앙 대시보드: 계좌별 분리 디자인]
    accounts = df['계좌번호'].unique()
    tabs = st.tabs([f"📂 {acc}" for acc in accounts] + ["🌍 전체 통합"])

    for i, acc in enumerate(accounts):
        with tabs[i]:
            acc_df = df[df['계좌번호'] == acc]
            
            # 디자인 수칙 적용 (Steel Blue / Slate Gray)
            def style_df(v):
                if isinstance(v, (int, float)) and v > 0: return 'color: #7086B4; font-weight: bold;' # Steel Blue
                return 'color: #6C7A89;' # Slate Gray

            st.dataframe(acc_df.style.map(style_df), use_container_width=True)

    # [하단: 데이터 무결성 범례]
    st.divider()
    st.markdown("### 📋 분석 범례 (Legend)")
    st.info("🟦 **Steel Blue**: 개선 후/수익 데이터 | ⬜ **Slate Gray**: 개선 전/기준 데이터")
    st.warning("**가중 평균 공식**: $\sum (수익률 \\times 비중)$ 로 실시간 감시 중")

except Exception as e:
    st.error(f"⚠️ 관제소 기동 실패: {e}")
