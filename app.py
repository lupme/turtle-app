import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import concurrent.futures

# --- [1] 모바일 반응형 UI/UX (CSS 최적화) ---
st.set_page_config(page_title="스마트 퀀터멘털 관제 시스템", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    h1, h2, h3 { color: #f8fafc !important; font-weight: 700 !important; word-break: keep-all !important; }
    .streamlit-expanderHeader { font-size: 1.1rem !important; font-weight: bold !important; background-color: #0f172a; }
    [data-testid="stMetricValue"] { color: #4682B4 !important; font-weight: 800 !important; }
    
    /* 모바일 환경 강제 최적화 (768px 이하 화면) */
    @media (max-width: 768px) {
        h1 { font-size: 24px !important; }
        .streamlit-expanderHeader { font-size: 0.95rem !important; }
        [data-testid="stMetricValue"] { font-size: 20px !important; }
        [data-testid="stMetricDelta"] { font-size: 14px !important; }
    }
    </style>
    """, unsafe_allow_html=True)

# --- [2] 0.5초 컷: 병렬 스캐닝 엔진 (Multi-threading) ---
def fetch_single_price(ticker):
    """단일 종목 네이버 시세 스캔 (타임아웃 2초 제한)"""
    if pd.isna(ticker) or str(ticker).strip() == "": return ticker, 0, "0%"
    clean_ticker = str(int(float(ticker))).zfill(6) if str(ticker).replace('.','').isdigit() else str(ticker).strip()
    url = f"https://finance.naver.com/item/main.naver?code={clean_ticker}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=2)
        soup = BeautifulSoup(res.text, 'html.parser')
        price_tag = soup.select_one(".no_today .blind")
        now_price = int(price_tag.text.replace(',', '')) if price_tag else 0
        rate_tag = soup.select_one(".no_exday .n_set_u .blind") or soup.select_one(".no_exday .n_set_d .blind")
        price_rate = rate_tag.text.strip() if rate_tag else "0%"
        return ticker, now_price, price_rate
    except:
        return ticker, 0, "0%"

def get_all_prices_parallel(tickers):
    """여러 종목을 동시에 타격하여 속도를 10배 이상 끌어올림"""
    results = {}
    unique_tickers = list(set([t for t in tickers if pd.notna(t) and str(t).strip() != ""]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(fetch_single_price, t) for t in unique_tickers]
        for future in concurrent.futures.as_completed(futures):
            t, p, r = future.result()
            results[t] = (p, r)
    return results

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
        st.title("💡 스마트 퀀터멘털 실시간 관제")
    with col_filter:
        account_types = ["전체 보기"] + list(df['계좌유형'].unique())
        selected_type = st.selectbox("📂 계좌유형 선택", account_types)

    st.divider()

    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "전체 보기" else df.copy()

    # 병렬 스캐닝 일괄 실행 (속도 최적화 핵심)
    all_tickers = display_df['종목코드'].tolist()
    live_prices = get_all_prices_parallel(all_tickers)

    processed_data = []
    for i, row in display_df.iterrows():
        if "현금" in str(row['종목명']): continue
        
        ticker = row.get('종목코드', '')
        now_p, p_rate = live_prices.get(ticker, (0, "0%"))
        is_realtime = True
        
        # 0.5초 타임아웃 방어 (시트 데이터로 즉각 대체)
        if now_p == 0:
            now_p = row.get('현재가2', row.get('현재가1', 0))
            p_rate = "-"
            is_realtime = False
            
        buy_price = row['매수단가']
        qty = row['잔고수량']
        real_eval = now_p * qty
        real_yield = ((now_p - buy_price) / buy_price * 100) if buy_price > 0 else 0
        
        processed_data.append({
            **row, '적용현재가': now_p, '등락률': p_rate, '최종수익률': real_yield, '최종평가액': real_eval, '실시간여부': is_realtime
        })
    
    final_df = pd.DataFrame(processed_data)
    if not final_df.empty:
        final_df = final_df.sort_values(by='최종수익률', ascending=False)
        for _, item in final_df.iterrows():
            ball = "🔴" if item['최종수익률'] > 0 else "🔵" if item['최종수익률'] < 0 else "⚪"
            alert_mark = "" if item['실시간여부'] else "⚠️"
            title = f"{ball} {item['종목명']} | {item['적용현재가']:,.0f}원 ({item['등락률']}) | {item['최종수익률']:.2f}% {alert_mark}"
            
            with st.expander(title):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("최종 평가액", f"{item['최종평가액']:,.0f}원", f"{item['최종평가액'] - item['매수금액']:,.0f}원")
                c2.metric("투입 자본", f"{item['매수금액']:,.0f}원")
                c3.metric("평균 매수단가", f"{item['매수단가']:,.0f}원")
                c4.metric("보유 수량", f"{item['잔고수량']:,.0f}주", delta_color="off")
    else:
        st.info("데이터가 없습니다.")

    # --- [4] 사이드바: 계좌유형 기반 컨트롤러 ---
    with st.sidebar:
        st.header("🛒 전술 매매 컨트롤러")
        mode = st.radio("작업 선택", ["기존 종목 매매", "데이터 강제 보정", "신규 종목 추가"])
        
        with st.form("trade_form"):
            # UI는 계좌유형을 보여주되, 뒤에서는 정확한 계좌번호를 잡도록 설계
            acc_options = []
            for _, r in full_df[['계좌유형', '계좌번호']].drop_duplicates().iterrows():
                acc_options.append(f"{r['계좌유형']} [{r['계좌번호']}]")
            
            sel_acc_str = st.selectbox("계좌유형(계좌번호) 선택", acc_options)
            sel_acc = sel_acc_str.split('[')[-1].replace(']', '')
            
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
                st.rerun()

except Exception as e:
    st.error(f"시스템 중단 오류: {e}")
