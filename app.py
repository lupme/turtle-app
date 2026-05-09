import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import time

# --- [1] 시스템 설정 및 CSS (시인성 및 라벨 디자인 강화) ---
st.set_page_config(page_title="거북이 함대 기동 본부 V43", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    h1, h2, h3, p, span, div { font-family: 'Urbanist', 'Noto Sans KR', sans-serif; }
    .hq-title { font-size: 1.4rem; color: rgb(70,130,180); font-weight: 800; letter-spacing: 1px; padding-top: 10px; margin-bottom: 20px; }
    
    /* 카드 디자인 */
    details.premium-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 12px; margin-bottom: 10px; }
    details.premium-card summary { padding: 16px; cursor: pointer; list-style: none; }
    details.premium-card summary::-webkit-details-marker { display: none; }
    
    /* 레이아웃 구조 */
    .card-header-flex { display: flex; justify-content: space-between; align-items: center; width: 100%; gap: 10px; }
    .card-left { width: 30%; min-width: 130px; }
    .card-right { display: flex; justify-content: space-between; align-items: center; width: 70%; }
    
    .stock-name { font-size: 1.05rem; font-weight: 700; color: #ffffff; display: block; margin-bottom: 2px; }
    .stock-code { font-size: 0.75rem; color: rgb(108,122,137); font-weight: 600; }
    
    /* 숫자 데이터 및 라벨(Tag) 디자인 */
    .data-box { display: flex; flex-direction: column; align-items: flex-end; width: 32%; }
    .data-label { font-size: 0.65rem; font-weight: 700; color: rgb(108,122,137); margin-bottom: 2px; text-transform: uppercase; }
    .data-value { font-size: 1.05rem; font-weight: 800; letter-spacing: -0.3px; }

    .text-red { color: #ef4444; } 
    .text-blue { color: rgb(70,130,180); } 
    .text-gray { color: rgb(108,122,137); }
    .text-white { color: #ffffff; }

    /* 모바일 환경 최적화 */
    @media (max-width: 768px) {
        .card-header-flex { flex-direction: column; align-items: flex-start; }
        .card-left { width: 100%; border-bottom: 1px solid #1e293b; padding-bottom: 8px; margin-bottom: 6px; }
        .card-right { width: 100%; }
        .data-box { align-items: flex-start; }
        .data-label { font-size: 0.6rem; }
        .data-value { font-size: 0.95rem; }
    }
    
    [data-testid="stMetricValue"] { color: #ffffff !important; font-size: 1.6rem !important; font-weight: 800 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- [2] 데이터 로드 및 무결성 필터 ---
def get_gspread_client():
    key_info = json.loads(st.secrets["google_credentials"])
    if "private_key" in key_info:
        key_info["private_key"] = key_info["private_key"].replace("\\n", "\n")
    return gspread.authorize(Credentials.from_service_account_info(key_info, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']))

@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0").get_worksheet(0)
    full_df = pd.DataFrame(sheet.get_all_records())
    
    df = full_df.copy()
    for col in df.columns:
        if col not in ['계좌번호', '계좌유형', '종목명', '종목코드']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', '').str.replace('%', ''), errors='coerce').fillna(0)
            
    # 합계 행 제외, 데이터 있는 행만 추출
    df = df[df['종목명'].astype(str).str.strip() != '']
    df = df[~df['종목명'].astype(str).str.contains('합계|총계|총액|총자산', na=False)]
    return sheet, df, full_df

# --- [3] 관제 화면 기동 ---
try:
    sheet, df, full_df = load_data()
    
    st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V43</div>', unsafe_allow_html=True)
    
    acc_types = ["함대 전체"] + list(df['계좌유형'].unique())
    selected_type = st.selectbox("필터", acc_types, label_visibility="collapsed")
    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()

    # 🚨 [무결성 합산 로직] 조회 여부와 관계없이 시트의 모든 자산(TDF 포함) 합산
    total_eval = display_df['평가금액'].sum()
    total_invest = display_df['매수금액'].sum()
    total_profit = display_df['평가손익'].sum()
    total_roi = (total_profit / total_invest * 100) if total_invest > 0 else 0
    total_cash = display_df[display_df['종목명'].astype(str).str.contains('현금|예수금', na=False)]['평가금액'].sum()
    
    # 전일비 정산
    daily_delta = 0
    if '전일종가' in display_df.columns and '현재가2' in display_df.columns:
        for _, row in display_df.iterrows():
            # 조회 가능한 주식만 전일비 계산
            if row['현재가2'] > 0 and row['전일종가'] > 0:
                daily_delta += (row['현재가2'] - row['전일종가']) * row['잔고수량']
    
    kc1, kc2, kc3, kc4 = st.columns(4)
    kc1.metric("총 함대 자산", f"{total_eval:,.0f}원")
    kc2.metric("총 누적 손익", f"{total_profit:,.0f}원", delta=f"{total_roi:,.2f}%")
    kc3.metric("전일 대비 증감", f"{daily_delta:,.0f}원", delta=f"{daily_delta:,.0f}")
    kc4.metric("기동 대기 예수금", f"{total_cash:,.0f}원")
    
    if not display_df.empty:
        # 수익률 기준 정렬
        yield_col = '수익률2' if '수익률2' in display_df.columns else '수익률'
        display_df = display_df.sort_values(by=yield_col, ascending=False)
        
        html_cards = ""
        for _, row in display_df.iterrows():
            # TDF, 펀드, 현금 등은 특수 자산으로 처리
            is_special = any(x in str(row['종목명']) for x in ["현금", "예수금", "단기", "연금", "TDF", "펀드"])
            y_val = row.get(yield_col, 0)
            now_p = row.get('현재가2', row.get('현재가', 0))
            prev_p = row.get('전일종가', 0)
            
            # 수익률 디스플레이 값 조정
            y_display = y_val * 100 if -1 < y_val < 1 else y_val
            cl = "text-red" if y_val > 0 else "text-blue" if y_val < 0 else "text-gray"
            
            # 당일비 계산
            diff = now_p - prev_p if prev_p > 0 else 0
            rate = (diff / prev_p * 100) if prev_p > 0 else 0
            diff_cl = "text-red" if diff > 0 else "text-blue" if diff < 0 else "text-gray"
            ds = f"{'▲' if diff>0 else '▼' if diff<0 else ''}{abs(diff):,.0f}({rate:.1f}%)" if diff != 0 else "-"

            html_cards += f"""
            <details class="premium-card">
                <summary>
                    <div class="card-header-flex">
                        <div class="card-left">
                            <span class="stock-name">{row['종목명']}</span>
                            <span class="stock-code">{row.get('종목코드', '')}</span>
                        </div>
                        <div class="card-right">
                            <div class="data-box">
                                <span class="data-label">현재가</span>
                                <span class="data-value">{now_p:,.0f if now_p > 0 else row.get('매수단가', 0):,.0f}</span>
                            </div>
                            <div class="data-box">
                                <span class="data-label">당일비</span>
                                <span class="data-value {diff_cl}">{ds}</span>
                            </div>
                            <div class="data-box">
                                <span class="data-label">수익률</span>
                                <span class="data-value {cl}">{y_display:.2f}%</span>
                            </div>
                        </div>
                    </div>
                </summary>
                <div class="card-body">
                    <div class="metric-grid">
                        <div class="metric-box"><div class="metric-label">평가 금액</div><div class="metric-highlight">{row['평가금액']:,.0f}원</div></div>
                        <div class="metric-box"><div class="metric-label">매수 금액</div><div class="metric-value">{row['매수금액']:,.0f}원</div></div>
                        <div class="metric-box"><div class="metric-label">평가 손익</div><div class="metric-value {cl}">{row['평가손익']:,.0f}원</div></div>
                        <div class="metric-box"><div class="metric-label">보유 수량</div><div class="metric-value">{row['잔고수량']:,.0f}주</div></div>
                    </div>
                </div>
            </details>"""
        st.markdown(html_cards, unsafe_allow_html=True)

except Exception as e: st.error(f"함대 기동 중지: {e}")
