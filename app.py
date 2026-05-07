import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import time

# --- [1] 전술적 UI/UX 설정 ---
st.set_page_config(page_title="스마트 주식 관제 시스템 V4.0", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    .streamlit-expanderHeader { font-size: 1.2rem !important; font-weight: bold !important; background-color: #0f172a; }
    [data-testid="stMetricValue"] { color: #4682B4 !important; font-weight: 800 !important; }
    .status-ball { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- [2] 실시간 네이버 시세 스캐너 엔진 ---
def get_realtime_naver_price(ticker):
    """네이버 증권에서 실시간 현재가 및 등락 정보를 스캔합니다."""
    if not ticker or len(str(ticker)) < 5: return 0, 0, "0%"
    
    url = f"https://finance.naver.com/item/main.naver?code={str(ticker).zfill(6)}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 현재가 추출
        price_tag = soup.select_one(".no_today .blind")
        now_price = int(price_tag.text.replace(',', '')) if price_tag else 0
        
        # 전일대비 및 등락률 추출
        diff_tag = soup.select_one(".no_exday .blind")
        rate_tag = soup.select_one(".no_exday .n_set_u .blind") # 상승 기준 예시
        if not rate_tag: rate_tag = soup.select_one(".no_exday .n_set_d .blind") # 하락 기준
        
        price_diff = diff_tag.text.strip() if diff_tag else "0"
        price_rate = rate_tag.text.strip() if rate_tag else "0%"
        
        return now_price, price_diff, price_rate
    except:
        return 0, 0, "0%"

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
    # 사령관님 지정 열(X, Y, Z) 포함 필수 데이터 추출
    essential_cols = ['계좌번호', '계좌유형', '종목명', '종목코드', '잔고수량', '매수단가', '현재가2', '수익률', '평가금액', '매수금액']
    df = full_df[[c for c in essential_cols if c in full_df.columns]].copy()
    
    numeric_cols = ['잔고수량', '매수단가', '현재가2', '평가금액', '매수금액']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', ''), errors='coerce').fillna(0)
            
    return sheet, df, full_df

# --- [3] 메인 기동 로직 ---
try:
    sheet, df, full_df = load_data()
    
    st.title("💡 스마트 퀀터멘털 실시간 관제 시스템")
    
    # 계좌유형 필터
    account_types = ["전체 보기"] + list(df['계좌유형'].unique())
    selected_type = st.sidebar.selectbox("📂 계좌유형 필터", account_types)
    
    if selected_type != "전체 보기":
        display_df = df[df['계좌유형'] == selected_type].copy()
    else:
        display_df = df.copy()

    # 실시간 시세 오버레이 (나래비 정렬 및 공 표시)
    st.subheader(f"📊 {selected_type} 실시간 전략 현황")
    
    processed_data = []
    for i, row in display_df.iterrows():
        if not row['종목코드']: continue
        
        # 실시간 스캔 실행
        now_p, p_diff, p_rate = get_realtime_naver_price(row['종목코드'])
        
        # 수익률 재계산 (실시간 무결성 보장)
        real_yield = ((now_p - row['매수단가']) / row['매수단가'] * 100) if row['매수단가'] > 0 else 0
        real_eval = now_p * row['잔고수량']
        
        processed_data.append({
            **row,
            '실시간현재가': now_p,
            '등락률': p_rate,
            '실시간수익률': real_yield,
            '실시간평가액': real_eval
        })
    
    # 수익률 기준 나래비(정렬)
    final_df = pd.DataFrame(processed_data).sort_values(by='실시간수익률', ascending=False)

    for _, item in final_df.iterrows():
        ball = "🔴" if item['실시간수익률'] > 0 else "🔵" if item['실시간수익률'] < 0 else "⚪"
        title = f"{ball} {item['종목명']} | {item['실시간현재가']:,.0f}원 ({item['등락률']}) | 수익률: {item['실시간수익률']:.2f}%"
        
        with st.expander(title):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("실시간 평가액", f"{item['실시간평가액']:,.0f}원")
            c2.metric("투입 자본", f"{item['매수금액']:,.0f}원")
            c3.metric("평균 단가", f"{item['매수단가']:,.0f}원")
            c4.metric("보유 수량", f"{item['잔고수량']:,.0f}주")

    # --- [4] 사이드바: 매매 및 데이터 보정 ---
    with st.sidebar:
        st.divider()
        mode = st.radio("전술 선택", ["기존 종목 매매", "데이터 오차 보정", "신규 종목 추가"])
        
        with st.form("action_form"):
            sel_acc = st.selectbox("계좌번호", list(full_df['계좌번호'].unique()))
            if mode != "신규 종목 추가":
                s_list = full_df[full_df['계좌번호'] == sel_acc]['종목명'].tolist()
                s_name = st.selectbox("종목 선택", s_list)
            else:
                s_name = st.text_input("신규 종목명")
                s_code = st.text_input("종목코드(6자리)")

            input_qty = st.number_input("수량", min_value=0)
            input_price = st.number_input("단가", min_value=0)
            
            if st.form_submit_button("시트 데이터 확정"):
                # 좌표 계산 (X=종목코드, Y=현재가2, Z=수익률)
                # 시트의 절대 위치를 찾아 정확히 타격합니다.
                idx_map = {col: i+1 for i, col in enumerate(full_df.columns)}
                
                if mode == "데이터 오차 보정":
                    t_idx = full_df[(full_df['계좌번호'] == sel_acc) & (full_df['종목명'] == s_name)].index[0]
                    sheet.update_cell(t_idx+2, idx_map['잔고수량'], int(input_qty))
                    sheet.update_cell(t_idx+2, idx_map['매수단가'], int(input_price))
                    st.success("보정 완료")
                
                # 추가 로직 생략 (동일 구조)
                st.rerun()

except Exception as e:
    st.error(f"관리자 보고: 시스템 가동 중단 - {e}")
