import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- [1] 시스템 기본 설정 ---
st.set_page_config(page_title="스마트 주식 관제 시스템", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0f172a; color: #f8fafc; }
    h1, h2, h3 { color: #f8fafc !important; font-weight: 700 !important; }
    /* 아코디언(확대) 텍스트 크기 조정 */
    .streamlit-expanderHeader { font-size: 1.2rem !important; font-weight: bold !important; }
    [data-testid="stMetricValue"] { color: #4682B4 !important; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def get_gspread_client():
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
    
    # 사령관님 지침: 스프레드시트 내용 전체가 아닌 필요한 것만 추출
    full_df = pd.DataFrame(sheet.get_all_records())
    essential_cols = ['계좌번호', '계좌유형', '종목명', '잔고수량', '매수단가', '현재가1', '평가금액', '매수금액', '평가손익', '수익률1']
    df = full_df[[c for c in essential_cols if c in full_df.columns]].copy()
    
    # 숫자 데이터 정제
    numeric_cols = ['잔고수량', '매수단가', '현재가1', '평가금액', '매수금액', '평가손익']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', ''), errors='coerce').fillna(0)
            
    # 수익률 숫자 변환 (정렬을 위해)
    if '수익률1' in df.columns:
        df['수익률_숫자'] = pd.to_numeric(df['수익률1'].astype(str).str.replace('%', '').str.replace(',', ''), errors='coerce').fillna(0)
        
    return sheet, df, full_df

# --- [2] 관제 화면 기동 ---
try:
    sheet, df, full_df = load_data()
    
    # 상단 헤더 및 계좌유형 선택기
    col_title, col_filter = st.columns([2, 1])
    with col_title:
        st.title("💡 스마트 주식 관제 시스템")
    with col_filter:
        account_types = ["전체 보기"] + list(df['계좌유형'].unique())
        selected_type = st.selectbox("📂 계좌유형 선택", account_types)

    st.divider()

    # 데이터 필터링 및 수익률 나래비(내림차순 정렬)
    if selected_type != "전체 보기":
        filtered_df = df[df['계좌유형'] == selected_type]
    else:
        filtered_df = df
        
    filtered_df = filtered_df.sort_values(by='수익률_숫자', ascending=False).reset_index()

    # --- [3] 메인 대시보드: 빨간공/파란공 및 종목 확대(Expander) UI ---
    if filtered_df.empty:
        st.info("표시할 종목이 없습니다.")
    else:
        for i, row in filtered_df.iterrows():
            # 종목과 현금 분리 처리
            if "현금" in str(row['종목명']):
                continue
                
            yield_val = row['수익률_숫자']
            
            # 시인성 극대화: 빨간공 / 파란공 / 회색공
            if yield_val > 0:
                ball, sign = "🔴", "+"
            elif yield_val < 0:
                ball, sign = "🔵", ""
            else:
                ball, sign = "⚪", ""
                
            # 타이틀 생성: 🔴 종목명 | 현재가 | 수익률
            expander_title = f"{ball} {row['종목명']} | 시세: {row['현재가1']:,.0f}원 | {sign}{yield_val}%"
            
            # 종목 클릭 시 확대되는 세부 정보
            with st.expander(expander_title):
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("총 평가금액", f"{row['평가금액']:,.0f}원", f"{row['평가손익']:,.0f}원")
                col2.metric("투입(매수)금액", f"{row['매수금액']:,.0f}원")
                col3.metric("평균 매수단가", f"{row['매수단가']:,.0f}원")
                col4.metric("보유 수량", f"{row['잔고수량']:,.0f}주", delta_color="off")
                st.caption(f"계좌 정보: {row['계좌유형']} ({row['계좌번호']})")

    # --- [4] 사이드바: 매수/매도 및 신규 종목 연동 컨트롤러 ---
    with st.sidebar:
        st.header("🛒 전술 매매 컨트롤러")
        trade_mode = st.radio("작업 선택", ["기존 종목 매매", "신규 종목 추가"])
        
        with st.form("trade_form"):
            acc_list = [str(a) for a in df['계좌번호'].unique()]
            sel_acc = st.selectbox("계좌 선택 (계좌번호)", acc_list)
            
            if trade_mode == "기존 종목 매매":
                stock_list = df[df['계좌번호'].astype(str) == sel_acc]['종목명'].tolist()
                sel_stock = st.selectbox("종목 선택", stock_list if stock_list else ["종목 없음"])
                action = st.radio("구분", ["매수", "매도"], horizontal=True)
            else:
                sel_stock = st.text_input("신규 종목명 입력")
                action = "매수" # 신규는 무조건 매수
                
            qty = st.number_input("수량(주)", min_value=1, step=1)
            price = st.number_input("실행단가(원)", min_value=0, step=100)
            
            if st.form_submit_button("시트 데이터 즉시 반영"):
                if trade_mode == "기존 종목 매매":
                    idx = df[(df['계좌번호'].astype(str) == sel_acc) & (df['종목명'] == sel_stock)].index[0]
                    old_qty = df.at[idx, '잔고수량']
                    old_avg = df.at[idx, '매수단가']
                    
                    # 수량 연동 및 평균 단가 가중평균 로직
                    if action == "매수":
                        new_qty = old_qty + qty
                        new_avg = ((old_qty * old_avg) + (qty * price)) / new_qty if new_qty > 0 else 0
                    else:
                        new_qty = max(0, old_qty - qty)
                        new_avg = old_avg

                    row_num = idx + 2
                    sheet.update_cell(row_num, df.columns.get_loc('잔고수량') + 1, int(new_qty))
                    sheet.update_cell(row_num, df.columns.get_loc('매수단가') + 1, int(new_avg))
                    st.success(f"✅ {sel_stock} 동기화 완료!")
                    
                else:
                    # 신규 종목 추가 로직
                    if sel_stock:
                        new_row_idx = len(full_df) + 2
                        # 필수 기본 데이터 채워넣기
                        sheet.update_cell(new_row_idx, full_df.columns.get_loc('계좌번호') + 1, sel_acc)
                        # 계좌 유형 가져오기
                        acc_type = df[df['계좌번호'].astype(str) == sel_acc]['계좌유형'].iloc[0] if not df[df['계좌번호'].astype(str) == sel_acc].empty else "일반"
                        sheet.update_cell(new_row_idx, full_df.columns.get_loc('계좌유형') + 1, acc_type)
                        sheet.update_cell(new_row_idx, full_df.columns.get_loc('종목명') + 1, sel_stock)
                        sheet.update_cell(new_row_idx, full_df.columns.get_loc('잔고수량') + 1, int(qty))
                        sheet.update_cell(new_row_idx, full_df.columns.get_loc('매수단가') + 1, int(price))
                        st.success(f"✅ 신규 종목 [{sel_stock}] 추가 완료!")
                    else:
                        st.error("종목명을 입력하십시오.")
                
                st.rerun()

except Exception as e:
    st.error(f"⚠️ 시스템 오류 발생: {e}")
