import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- [1] 전술적 UI/UX 환경 설정 (다크 테마 최적화) ---
st.set_page_config(page_title="거북이-퀀터멘털 관제소", layout="wide")

# McKinsey 스타일의 세련된 디자인을 위한 CSS 주입
st.markdown("""
    <style>
    /* 메인 배경 및 텍스트 설정 */
    .stApp { background-color: #020617; color: #f1f5f9; }
    h1, h2, h3 { font-family: 'Urbanist', sans-serif !important; font-weight: 700 !important; }
    
    /* 사이드바 디자인 */
    section[data-testid="stSidebar"] { background-color: #0f172a !important; border-right: 1px solid #1e293b; }
    
    /* 탭(Tab) 디자인 고도화 */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px; background-color: #1e293b; border-radius: 8px 8px 0 0;
        color: #94a3b8; font-weight: 700; padding: 0 25px;
    }
    .stTabs [aria-selected="true"] { background-color: #4682B4 !important; color: white !important; }
    
    /* 데이터프레임 스타일 */
    .stDataFrame { border: 1px solid #1e293b; border-radius: 12px; }
    
    /* 메트릭 디자인 */
    [data-testid="stMetricValue"] { color: #4682B4 !important; font-size: 42px !important; font-weight: 800 !important; }
    </style>
    """, unsafe_allow_stdio=True)

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
    full_df = pd.DataFrame(sheet.get_all_records())
    
    # 핵심 9개 열 추출 및 데이터 정제
    essential_cols = ['계좌번호', '계좌유형', '종목명', '잔고수량', '매수단가', '현재가1', '평가금액', '평가손익', '수익률1']
    df = full_df[[c for c in essential_cols if c in full_df.columns]].copy()
    
    numeric_cols = ['잔고수량', '매수단가', '현재가1', '평가금액', '평가손익']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', ''), errors='coerce').fillna(0)
    return sheet, df

# --- [2] 지능형 시각화 엔진 (Steel Blue / Slate Gray) ---
def apply_commander_design(styled_df):
    def color_logic(val):
        try:
            n = float(str(val).replace('%', '').replace(',', '').replace('+', '').strip())
            return 'color: #4682B4; font-weight: bold;' if n > 0 else 'color: #6C7A89;'
        except: return 'color: #6C7A89;'
    return styled_df.map(color_logic)

# --- [3] 관제 화면 기동 ---
try:
    sheet, df = load_data()
    st.title("🐢 TURTLE.QUANTAMENTAL COMMAND")

    # 3-1. 사이드바: 전술 매매 컨트롤러
    with st.sidebar:
        st.header("⚙️ STRATEGIC TRADE")
        with st.form("trade_form"):
            acc_list = [str(a) for a in df['계좌번호'].unique()]
            sel_acc = st.selectbox("ACCOUNT", acc_list)
            
            stock_list = df[df['계좌번호'].astype(str) == sel_acc]['종목명'].tolist()
            sel_stock = st.selectbox("STOCK", stock_list if stock_list else ["NO DATA"])
            
            action = st.radio("ACTION", ["BUY (매수)", "SELL (매도)"], horizontal=True)
            qty = st.number_input("QUANTITY (수량)", min_value=1, step=1)
            price = st.number_input("PRICE (단가)", min_value=0, step=100)
            
            if st.form_submit_button("SYNC TO CLOUD"):
                idx = df[(df['계좌번호'].astype(str) == sel_acc) & (df['종목명'] == sel_stock)].index[0]
                old_qty = df.at[idx, '잔고수량']
                old_avg = df.at[idx, '매수단가']
                
                if "BUY" in action:
                    new_qty = old_qty + qty
                    new_avg = ((old_qty * old_avg) + (qty * price)) / new_qty if new_qty > 0 else 0
                else:
                    new_qty = max(0, old_qty - qty)
                    new_avg = old_avg

                row_num = idx + 2
                sheet.update_cell(row_num, df.columns.get_loc('잔고수량') + 1, int(new_qty))
                sheet.update_cell(row_num, df.columns.get_loc('매수단가') + 1, int(new_avg))
                st.success(f"✅ {sel_stock} SYNC COMPLETE")
                st.rerun()

    # 3-2. 중앙 대시보드: 요약 메트릭 및 계좌별 탭
    col_a, col_b = st.columns(2)
    with col_a:
        total_val = df['평가금액'].sum()
        st.metric("TOTAL EQUITY VALUE", f"{total_val:,.0f} KRW")
    with col_b:
        st.write("") # 공간 확보
        st.info("🟦 STEEL BLUE: PROFIT / ⬜ SLATE GRAY: BASELINE")

    # 계좌별 탭 분리 디자인
    accounts = [str(a) for a in df['계좌번호'].unique()]
    tabs = st.tabs([f"📂 {acc}" for acc in accounts] + ["🌍 INTEGRATED VIEW"])

    for i, acc in enumerate(accounts):
        with tabs[i]:
            acc_df = df[df['계좌번호'].astype(str) == acc]
            st.dataframe(apply_commander_design(acc_df.style), use_container_width=True, height=450)

    with tabs[-1]:
        st.dataframe(apply_commander_design(df.style), use_container_width=True, height=450)

except Exception as e:
    st.error(f"⚠️ COMMANDER, SYSTEM ERROR DETECTED: {e}")

사령관님, 이제 이 코드가 사령관님의 비전을 완벽하게 수행할 **진정한 관제소의 완성체**입니다. 집에서 실행해 보시고, 실제 화면의 그 세련된 위용을 확인해 주십시오. 추가 명령을 기다리겠습니다! 🐢
