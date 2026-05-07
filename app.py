import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup

# --- [1] 전술적 UI/UX 설정 ---
st.set_page_config(page_title="스마트 퀀터멘털 관제 시스템 V4.1", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    h1, h2, h3 { color: #f8fafc !important; font-weight: 700 !important; }
    .streamlit-expanderHeader { font-size: 1.2rem !important; font-weight: bold !important; background-color: #0f172a; }
    [data-testid="stMetricValue"] { color: #4682B4 !important; font-weight: 800 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- [2] 네이버 실시간 스캐너 (방어 로직 추가) ---
def get_realtime_naver_price(ticker):
    """네이버 증권 스캔 (실패 시 0 반환)"""
    if pd.isna(ticker) or str(ticker).strip() == "": 
        return 0, "0", "0%"
    
    # 숫자형일 경우 6자리 문자로 변환 (예: 5930 -> 005930)
    clean_ticker = str(int(float(ticker))).zfill(6) if str(ticker).replace('.','').isdigit() else str(ticker).strip()
    
    url = f"https://finance.naver.com/item/main.naver?code={clean_ticker}"
    try:
        # 봇 차단 우회를 위한 강력한 User-Agent
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        price_tag = soup.select_one(".no_today .blind")
        now_price = int(price_tag.text.replace(',', '')) if price_tag else 0
        
        diff_tag = soup.select_one(".no_exday .blind")
        rate_tag = soup.select_one(".no_exday .n_set_u .blind") or soup.select_one(".no_exday .n_set_d .blind")
        
        price_diff = diff_tag.text.strip() if diff_tag else "0"
        price_rate = rate_tag.text.strip() if rate_tag else "0%"
        
        return now_price, price_diff, price_rate
    except:
        return 0, "0", "0%"

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
    # 현재가1, 현재가2 모두 가져와서 예비 전력으로 확보
    essential_cols = ['계좌번호', '계좌유형', '종목명', '종목코드', '잔고수량', '매수단가', '현재가1', '현재가2', '매수금액']
    df = full_df[[c for c in essential_cols if c in full_df.columns]].copy()
    
    numeric_cols = ['잔고수량', '매수단가', '현재가1', '현재가2', '매수금액']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', ''), errors='coerce').fillna(0)
            
    return sheet, df, full_df

# --- [3] 메인 대시보드 기동 ---
try:
    sheet, df, full_df = load_data()
    
    col_title, col_filter = st.columns([2, 1])
    with col_title:
        st.title("💡 스마트 퀀터멘털 실시간 관제 시스템")
    with col_filter:
        account_types = ["전체 보기"] + list(df['계좌유형'].unique())
        selected_type = st.selectbox("📂 계좌유형 선택", account_types)

    st.divider()

    if selected_type != "전체 보기":
        display_df = df[df['계좌유형'] == selected_type].copy()
    else:
        display_df = df.copy()

    # 데이터 정제 및 하이브리드 엔진 가동
    processed_data = []
    for i, row in display_df.iterrows():
        if "현금" in str(row['종목명']): continue
        
        # 1. 실시간 스캔 시도
        now_p, p_diff, p_rate = get_realtime_naver_price(row.get('종목코드', ''))
        is_realtime = True
        
        # 2. 이중 안전장치 (Fail-safe): 0원일 경우 시트의 '현재가2' 또는 '현재가1'로 방어
        if now_p == 0:
            now_p = row.get('현재가2', row.get('현재가1', 0))
            p_diff, p_rate = "-", "-"
            is_realtime = False # 실시간 실패 마킹
            
        # 데이터 무결성 연산
        buy_price = row['매수단가']
        qty = row['잔고수량']
        real_eval = now_p * qty
        real_yield = ((now_p - buy_price) / buy_price * 100) if buy_price > 0 else 0
        
        processed_data.append({
            **row,
            '적용현재가': now_p,
            '등락폭': p_diff,
            '등락률': p_rate,
            '최종수익률': real_yield,
            '최종평가액': real_eval,
            '실시간여부': is_realtime
        })
    
    # 3. 수익률 내림차순 정렬 (나래비)
    final_df = pd.DataFrame(processed_data)
    if not final_df.empty:
        final_df = final_df.sort_values(by='최종수익률', ascending=False)

        for _, item in final_df.iterrows():
            ball = "🔴" if item['최종수익률'] > 0 else "🔵" if item['최종수익률'] < 0 else "⚪"
            alert_mark = "" if item['실시간여부'] else "⚠️(시트값)"
            
            title = f"{ball} {item['종목명']} | 시세: {item['적용현재가']:,.0f}원 ({item['등락률']}) | 수익률: {item['최종수익률']:.2f}% {alert_mark}"
            
            with st.expander(title):
                c1, c2, c3, c4 = st.columns(4)
                profit_loss = item['최종평가액'] - item['매수금액']
                c1.metric("최종 평가액", f"{item['최종평가액']:,.0f}원", f"{profit_loss:,.0f}원")
                c2.metric("투입 자본", f"{item['매수금액']:,.0f}원")
                c3.metric("평균 매수단가", f"{item['매수단가']:,.0f}원")
                c4.metric("보유 수량", f"{item['잔고수량']:,.0f}주", delta_color="off")
    else:
        st.info("데이터가 없습니다.")

    # --- [4] 전술 매매 컨트롤러 ---
    with st.sidebar:
        st.header("🛒 전술 매매 컨트롤러")
        mode = st.radio("작업 선택", ["기존 종목 매매", "데이터 강제 보정", "신규 종목 추가"])
        
        with st.form("trade_form"):
            acc_list = [str(a) for a in full_df['계좌번호'].unique()]
            sel_acc = st.selectbox("계좌번호", acc_list)
            
            if mode != "신규 종목 추가":
                s_list = full_df[full_df['계좌번호'].astype(str) == sel_acc]['종목명'].tolist()
                sel_stock = st.selectbox("종목 선택", s_list if s_list else ["없음"])
                action = st.radio("구분", ["매수", "매도"], horizontal=True) if mode == "기존 종목 매매" else None
            else:
                sel_stock = st.text_input("신규 종목명")
                sel_code = st.text_input("종목코드(6자리) - 필수")
                
            qty = st.number_input("수량(주)", min_value=0, step=1)
            price = st.number_input("단가(원)", min_value=0, step=100)
            
            if st.form_submit_button("시트 데이터 확정"):
                idx_map = {col: i+1 for i, col in enumerate(full_df.columns)}
                
                if mode == "데이터 강제 보정":
                    t_idx = full_df[(full_df['계좌번호'].astype(str) == sel_acc) & (full_df['종목명'] == sel_stock)].index[0]
                    sheet.update_cell(t_idx+2, idx_map['잔고수량'], int(qty))
                    sheet.update_cell(t_idx+2, idx_map['매수단가'], int(price))
                    st.success(f"✅ {sel_stock} 보정 완료!")
                
                elif mode == "기존 종목 매매":
                    t_idx = full_df[(full_df['계좌번호'].astype(str) == sel_acc) & (full_df['종목명'] == sel_stock)].index[0]
                    old_qty = full_df.at[t_idx, '잔고수량']
                    old_avg = full_df.at[t_idx, '매수단가']
                    
                    if action == "매수":
                        new_qty = old_qty + qty
                        new_avg = ((old_qty * old_avg) + (qty * price)) / new_qty if new_qty > 0 else 0
                    else:
                        new_qty = max(0, old_qty - qty)
                        new_avg = old_avg

                    sheet.update_cell(t_idx+2, idx_map['잔고수량'], int(new_qty))
                    sheet.update_cell(t_idx+2, idx_map['매수단가'], int(new_avg))
                    st.success(f"✅ {sel_stock} 매매 반영 완료!")
                    
                elif mode == "신규 종목 추가":
                    if sel_stock and sel_code:
                        new_row = len(full_df) + 2
                        sheet.update_cell(new_row, idx_map['계좌번호'], sel_acc)
                        acc_type = full_df[full_df['계좌번호'].astype(str) == sel_acc]['계좌유형'].iloc[0] if not full_df[full_df['계좌번호'].astype(str) == sel_acc].empty else "일반"
                        sheet.update_cell(new_row, idx_map['계좌유형'], acc_type)
                        sheet.update_cell(new_row, idx_map['종목명'], sel_stock)
                        
                        if '종목코드' in idx_map:
                            sheet.update_cell(new_row, idx_map['종목코드'], str(sel_code))
                            
                        sheet.update_cell(new_row, idx_map['잔고수량'], int(qty))
                        sheet.update_cell(new_row, idx_map['매수단가'], int(price))
                        st.success(f"✅ 신규 종목 추가 완료!")
                    else:
                        st.error("종목명과 종목코드(6자리)를 모두 입력하십시오.")
                st.rerun()

except Exception as e:
    st.error(f"시스템 중단 오류: {e}")
