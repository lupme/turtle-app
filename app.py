import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup

# --- [1] 프리미엄 관제소 V16.0 ---
st.set_page_config(page_title="거북이 함대 기동 본부 V16.0", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f1f5f9; }
    h1, h2, h3, p, span, div { font-family: 'Urbanist', 'Noto Sans KR', sans-serif; }
    
    .hq-title { font-size: 1.2rem; color: #4682B4; font-weight: 800; letter-spacing: 1px; margin-bottom: 0; padding-top: 10px; }
    
    [data-testid="stExpander"] {
        background-color: #0f172a !important;
        border: 1px solid #1e293b !important;
        border-left: 4px solid #4682B4 !important;
        border-radius: 8px !important;
        margin-bottom: 12px !important;
    }
    
    [data-testid="stExpander"] summary svg { display: none !important; }
    [data-testid="stExpander"] summary { padding: 1rem !important; list-style-type: none !important; }
    [data-testid="stExpander"] summary p { font-size: 1.1rem !important; font-weight: 700 !important; color: #f8fafc !important; }
    [data-testid="stExpanderDetails"] { background-color: #020617 !important; padding: 1.5rem !important; border-top: 1px solid #1e293b !important; }

    .metric-box { margin-bottom: 15px; }
    .metric-label { color: #64748b; font-size: 0.8rem; font-weight: 600; margin-bottom: 4px; text-transform: uppercase; }
    .metric-value { color: #f8fafc; font-size: 1.15rem; font-weight: 700; }
    .metric-value-blue { color: #4682B4; font-size: 1.15rem; font-weight: 800; }
    .metric-value-gray { color: #94a3b8; font-size: 1rem; font-weight: 500; }

    .pos-badge { padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.85rem; margin-bottom: 15px; display: inline-block; }
    .pos-head { background-color: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid #ef4444; }
    .pos-shoulder { background-color: rgba(248, 113, 113, 0.15); color: #f87171; border: 1px solid #f87171; }
    .pos-waist { background-color: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid #f59e0b; }
    .pos-knee { background-color: rgba(52, 211, 153, 0.15); color: #34d399; border: 1px solid #34d399; }
    .pos-feet { background-color: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid #10b981; }
    .pos-unknown { background-color: rgba(71, 85, 105, 0.15); color: #94a3b8; border: 1px solid #64748b; }
    
    [data-testid="stMetricValue"] { color: #4682B4 !important; font-size: 1.6rem !important; font-weight: 800 !important; }
    </style>
    """, unsafe_allow_html=True)

def col_letter(n):
    string = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string

def fetch_emergency_price(ticker):
    if pd.isna(ticker) or str(ticker).strip() == "" or str(ticker).strip() == "0": return 0
    clean_ticker = str(int(float(ticker))).zfill(6) if str(ticker).replace('.','').isdigit() else str(ticker).strip()
    try:
        url = f"https://finance.naver.com/item/main.naver?code={clean_ticker}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=2)
        soup = BeautifulSoup(res.text, 'html.parser')
        price_tag = soup.select_one(".no_today .blind")
        return int(price_tag.text.replace(',', '')) if price_tag else 0
    except:
        return 0

@st.cache_resource
def get_gspread_client():
    key_info = json.loads(st.secrets["google_credentials"])
    if "private_key" in key_info:
        key_info["private_key"] = key_info["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(key_info, 
        scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
    return gspread.authorize(creds)

@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    sheet_url = "https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0"
    doc = client.open_by_url(sheet_url)
    sheet = doc.get_worksheet(0)
    full_df = pd.DataFrame(sheet.get_all_records())
    
    essential_cols = ['계좌번호', '계좌유형', '종목명', '종목코드', '잔고수량', '매수단가', '현재가2', '현재가1', '수익률', '수익률1', '평가금액', '매수금액', '평가손익', '전일종가', '52주최고', '52주최저']
    df = full_df[[c for c in essential_cols if c in full_df.columns]].copy()
    
    for col in essential_cols:
        if col not in df.columns:
            df[col] = 0
        elif col not in ['계좌번호', '계좌유형', '종목명', '종목코드', '수익률', '수익률1']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', ''), errors='coerce').fillna(0)
    
    target_yield = '수익률' if '수익률' in full_df.columns else '수익률1' if '수익률1' in full_df.columns else None
    df['수익률_숫자'] = pd.to_numeric(df[target_yield].astype(str).str.replace('%', '').str.replace(',', ''), errors='coerce').fillna(0) if target_yield else 0.0
        
    df = df[~df['종목명'].astype(str).str.contains('합계|총계|총액', na=False)]
    df = df[df['종목명'].astype(str).str.strip() != '']
        
    return sheet, df, full_df

def get_position_text(now, low, high):
    if high == 0 or low == 0 or high <= low or now == 0: return "지표 부족", "pos-unknown"
    pos = (now - low) / (high - low) * 100
    if pos >= 85: return f"머리 ({pos:.0f}%↑)", "pos-head"
    if pos >= 65: return f"어깨 ({pos:.0f}%)", "pos-shoulder"
    if pos >= 35: return f"허리 ({pos:.0f}%)", "pos-waist"
    if pos >= 15: return f"무릎 ({pos:.0f}%)", "pos-knee"
    return f"발바닥 ({pos:.0f}%↓)", "pos-feet"

# --- [3] 관제 화면 기동 ---
try:
    sheet, df, full_df = load_data()
    
    c_title, c_space, c_filter = st.columns([4, 1, 3])
    with c_title:
        st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ</div>', unsafe_allow_html=True)
    with c_filter:
        acc_types = ["함대 전체"] + list(df['계좌유형'].unique())
        selected_type = st.selectbox("필터", acc_types, label_visibility="collapsed")
    
    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()

    processed_data = []
    for _, row in display_df.iterrows():
        now_price = row['현재가2'] if row['현재가2'] != 0 else row['현재가1']
        
        if now_price == 0 and not ("현금" in str(row['종목명']) or "예수금" in str(row['종목명'])):
            now_price = fetch_emergency_price(row.get('종목코드', ''))
            
        real_yield = ((now_price - row['매수단가']) / row['매수단가'] * 100) if row['매수단가'] > 0 else 0
        real_eval = now_price * row['잔고수량']
        
        row_dict = row.to_dict()
        row_dict['보정현재가'] = now_price
        row_dict['보정수익률'] = real_yield
        row_dict['보정평가금액'] = real_eval
        processed_data.append(row_dict)

    final_df = pd.DataFrame(processed_data).sort_values(by='보정수익률', ascending=False) if processed_data else pd.DataFrame()

    total_eval = final_df['보정평가금액'].sum() if not final_df.empty else 0
    total_prev = (final_df['전일종가'] * final_df['잔고수량']).sum() if not final_df.empty else 0
    daily_delta = total_eval - total_prev if total_prev > 0 else 0
    total_cash = final_df[final_df['종목명'].astype(str).str.contains('현금|예수금', na=False)]['보정평가금액'].sum() if not final_df.empty else 0
    
    kc1, kc2, kc3, kc4 = st.columns(4)
    kc1.metric("총 함대 자산", f"{total_eval:,.0f}원")
    if total_prev > 0: kc2.metric("전일 대비 증감", f"{daily_delta:,.0f}원", delta=f"{daily_delta:,.0f}")
    else: kc2.metric("전일 대비 증감", "지표 없음", delta=None)
    kc3.metric("기동 대기 예수금", f"{total_cash:,.0f}원")
    
    target_input = 830000000

    if final_df.empty:
        st.info("기동 대기 중인 자산이 없습니다.")
    else:
        for _, row in final_df.iterrows():
            is_cash = "현금" in str(row['종목명']) or "예수금" in str(row['종목명'])
            
            yield_val = row['보정수익률']
            now_price = row['보정현재가']
            prev_price = row['전일종가']
            
            daily_diff = now_price - prev_price if prev_price > 0 else 0
            diff_str = f"(▲{daily_diff:,.0f})" if daily_diff > 0 else f"(▼{abs(daily_diff):,.0f})" if daily_diff < 0 else ""
            
            if is_cash:
                title = f"💵 {row['종목명']} │ {row['보정평가금액']:,.0f}원"
            else:
                mark = "🔴" if yield_val > 0 else "🔵" if yield_val < 0 else "🔘"
                title = f"📂 {mark} {row['종목명']} │ {now_price:,.0f}원 {diff_str} │ {yield_val:.2f}%"
            
            with st.expander(title):
                if not is_cash:
                    pos_text, pos_class = get_position_text(now_price, row['52주최저'], row['52주최고'])
                    st.markdown(f'<div class="pos-badge {pos_class}">📍 시세위치: {pos_text}</div>', unsafe_allow_html=True)
                
                # 52주 최저가를 포함하여 사령관님이 직접 위치 계산을 검증할 수 있도록 개선
                html_content = f"""
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div class="metric-box"><div class="metric-label">평가 금액</div><div class="metric-value-blue">{row['보정평가금액']:,.0f}원</div></div>
                    <div class="metric-box"><div class="metric-label">현재 시세</div><div class="metric-value">{now_price:,.0f}원</div></div>
                    <div class="metric-box"><div class="metric-label">투입 원금</div><div class="metric-value">{row['매수금액']:,.0f}원</div></div>
                    <div class="metric-box"><div class="metric-label">평균 단가</div><div class="metric-value">{row['매수단가']:,.0f}원</div></div>
                    <div class="metric-box"><div class="metric-label">보유 수량</div><div class="metric-value">{row['잔고수량']:,.0f}주</div></div>
                    <div class="metric-box"><div class="metric-label">52주 최고/최저가</div><div class="metric-value">{row['52주최고']:,.0f}원 <span class="metric-value-gray">/ {row['52주최저']:,.0f}원</span></div></div>
                </div>
                """
                st.markdown(html_content, unsafe_allow_html=True)

    # --- [4] 사이드바 로직 ---
    with st.sidebar:
        st.header("🎯 함대 전략 설정")
        target_val = st.number_input("함대 목표 자산 (원)", value=830000000, step=10000000)
        kc4.metric("목표 달성률", f"{(total_eval/target_val*100):.1f}%")
        
        st.divider()
        st.header("🛠️ 작전 명령")
        mode = st.radio("전술 모드", ["기존 종목 매매", "데이터 강제 수정", "신규 종목 추가"])
        
        acc_opts = [f"{r['계좌유형']} [{r['계좌번호']}]" for _, r in full_df[['계좌
