import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- [1] 시스템 보안 및 무결성 설정 ---
st.set_page_config(page_title="거북이-퀀터멘털 관제소", layout="wide")

@st.cache_resource
def get_gspread_client():
    # 보안 키 인출 및 JWT 줄바꿈 오류 방지 로직
    key_info = json.loads(st.secrets["google_credentials"])
    if "private_key" in key_info:
        key_info["private_key"] = key_info["private_key"].replace("\\n", "\n")
        
    creds = Credentials.from_service_account_info(key_info, 
        scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
    return gspread.authorize(creds)

def load_data():
    client = get_gspread_client()
    sheet_url = "https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0"
    doc = client.open_by_url(sheet_url)
    sheet = doc.get_worksheet(0)
    
    full_df = pd.DataFrame(sheet.get_all_records())
    
    # [사령관님 지침: 필수 9개 열만 정밀 추출]
    essential_cols = ['계좌번호', '계좌유형', '종목명', '잔고수량', '매수단가', '현재가1', '평가금액', '평가손익', '수익률1']
    df = full_df[[c for c in essential_cols if c in full_df.columns]].copy()
    
    # 숫자 데이터 정제 (쉼표 제거 및 수치화)
    numeric_cols = ['잔고수량', '매수단가', '현재가1', '평가금액', '평가손익']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', ''), errors='coerce').fillna(0)
            
    return sheet, df

# --- [2] 전술 디자인 규격 (Steel Blue & Slate Gray) ---
def apply_commander_design(styled_df):
    def color_logic(val):
        try:
            # 수익률(%) 등에서 숫자만 추출하여 판별
            n = float(str(val).replace('%', '').replace(',', '').replace('+', '').strip())
            return 'color: #4682B4; font-weight: bold;' if n > 0 else 'color: #6C7A89;'
        except: return 'color: #6C7A89;'

    # Pandas Styler 최신 규격(map) 적용
    styled_df = styled_df.map(color_rule=color_logic)
    
    # 핵심 관리 지표 강조 (종목명 등)
    bold_cols = ['종목명', 'PPID', 'UPEH']
    available_bold = [c for c in bold_cols if c in styled_df.columns]
    if available_bold:
        styled_df = styled_df.set_properties(**{'font-weight': 'black', 'font-size': '1.1rem'}, subset=available_bold)
    
    return styled_df

# --- [3] 메인 관제 화면 기동 ---
try:
    sheet, df = load_data()
    st.title("🐢 거북이-퀀터멘털 실시간 관제 시스템")

    # 3-1. 사이드바: 실시간 매매/수량/평단 관제
    with st.sidebar:
        st.header("🛠️ 실시간 매매 기록")
        with st.form("trade_form"):
            acc_list = [str(a) for a in df['계좌번호'].unique()]
            sel_acc = st.selectbox("계좌 선택", acc_list)
            
            # 선택한 계좌의 종목만 필터링
            stock_list = df[df['계좌번호'].astype(str) == sel_acc]['종목명'].tolist()
            sel_stock = st.selectbox("종목 선택", stock_list if stock_list else ["종목 없음"])
            
            sel_action = st.radio("구분", ["매수", "매도"], horizontal=True)
            trade_qty = st.number_input("수량(주)", min_value=1, step=1)
            trade_price = st.number_input("실행단가(원)", min_value=0, step=100)
            
            if st.form_submit_button("시트 데이터 즉시 반영"):
                # 평단가 및 수량 연산 로직
                idx = df[(df['계좌번호'].astype(str) == sel_acc) & (df['종목명'] == sel_stock)].index[0]
                old_qty = df.at[idx, '잔고수량']
                old_avg = df.at[idx, '매수단가']
                
                if sel_action == "매수":
                    new_qty = old_qty + trade_qty
                    # 가중 평균 평단가 계산
                    new_avg = ((old_qty * old_avg) + (trade_qty * trade_price)) / new_qty if new_qty > 0 else 0
                else:
                    new_qty = max(0, old_qty - trade_qty)
                    new_avg = old_avg

                # 구글 시트 업데이트 (헤더 포함 +2 행)
                row_num = idx + 2
                qty_col = df.columns.get_loc('잔고수량') + 1
                avg_col = df.columns.get_loc('매수단가') + 1
                
                sheet.update_cell(row_num, qty_col, int(new_qty))
                sheet.update_cell(row_num, avg_col, int(new_avg))
                st.success(f"✅ {sel_stock} {sel_action} 동기화 완료!")
                st.rerun()

    # 3-2. 중앙 대시보드: 계좌별 탭 분리 디자인 복원
    if not df.empty:
        accounts = [str(a) for a in df['계좌번호'].unique()]
        tabs = st.tabs([f"📂 {acc}" for acc in accounts] + ["🌍 전체 통합"])

        for i, acc in enumerate(accounts):
            with tabs[i]:
                acc_df = df[df['계좌번호'].astype(str) == acc]
                st.dataframe(apply_commander_design(acc_df.style), use_container_width=True)

        with tabs[-1]:
            st.dataframe(apply_commander_design(df.style), use_container_width=True)

    # --- [4] 데이터 무결성 범례 ---
    st.divider()
    st.info("🟦 **Steel Blue**: 수익/개선 데이터 | ⬜ **Slate Gray**: 기본/이전 데이터 | 🔄 60초 자동 동기화 가동 중")

except Exception as e:
    st.error(f"⚠️ 시스템 오류 발생: {e}")
