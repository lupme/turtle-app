import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup

# --- [1] 시스템 설정 및 CSS (V24 오리지널 + 규격 색상 복원) ---
st.set_page_config(page_title="거북이 함대 기동 본부 V41", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    /* 전체 배경 및 폰트 */
    .stApp { background-color: #020617; color: #f1f5f9; }
    h1, h2, h3, p, span, div { font-family: 'Urbanist', 'Noto Sans KR', sans-serif; }
    
    /* 타이틀 (Steel Blue 적용) */
    .hq-title { font-size: 1.4rem; color: rgb(70,130,180); font-weight: 800; letter-spacing: 1px; padding-top: 10px; margin-bottom: 20px; }
    
    /* 상단 지수 전광판 */
    .index-container { display: flex; justify-content: space-between; background: #0f172a; padding: 15px 20px; border-radius: 12px; border: 1px solid #1e293b; margin-bottom: 20px; }
    .index-item { display: flex; flex-direction: column; align-items: center; width: 24%; }
    .index-name { font-size: 0.85rem; color: rgb(108,122,137); font-weight: 700; margin-bottom: 4px; }
    .index-val { font-size: 1.15rem; font-weight: 800; color: #f8fafc; }
    .index-diff { font-size: 0.85rem; font-weight: 600; }
    
    /* [핵심] V24 1줄 정렬 리스트 헤더 및 행 레이아웃 복원 */
    .list-header { color: rgb(108,122,137); font-size: 0.85rem; font-weight: 600; padding: 0 16px 10px 16px; border-bottom: 1px solid #1e293b; margin-bottom: 10px; }
    .row-layout { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: 8px; }
    
    /* 비율 기반 정밀 폭 분할 (모바일 깨짐 방지) */
    .col-name { width: 30%; display: flex; align-items: center; gap: 6px; overflow: hidden; }
    .col-price { width: 24%; text-align: right; font-size: 1.05rem; font-weight: 800; color: #f8fafc; }
    .col-diff { width: 26%; text-align: right; font-size: 0.9rem; font-weight: 700; }
    .col-yield { width: 20%; text-align: right; font-size: 1.05rem; font-weight: 800; }
    
    /* 프리미엄 카드 디자인 */
    details.premium-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 12px; margin-bottom: 10px; transition: all 0.2s; }
    details.premium-card:hover { border-color: rgb(70,130,180); }
    details.premium-card summary { display: flex; align-items: center; padding: 16px 16px; cursor: pointer; list-style: none; }
    details.premium-card summary::-webkit-details-marker { display: none; }
    
    /* 상태 도트 및 텍스트 색상 (Slate Gray / Steel Blue 엄수) */
    .status-dot { min-width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .dot-red { background-color: #ef4444; box-shadow: 0 0 8px rgba(239, 68, 68, 0.6); }
    .dot-blue { background-color: rgb(70,130,180); box-shadow: 0 0 8px rgba(70, 130, 180, 0.6); }
    .dot-gray { background-color: rgb(108,122,137); }
    
    .stock-name { font-size: 1.05rem; font-weight: 700; color: #f8fafc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .text-red { color: #ef4444; } .text-blue { color: rgb(70,130,180); } .text-gray { color: rgb(108,122,137); }
    
    /* 카드 확장 시 내부 상세 지표 */
    .card-body { background-color: #020617; padding: 20px; border-top: 1px solid #1e293b; border-radius: 0 0 12px 12px; }
    .metric-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
    .metric-box { display: flex; flex-direction: column; }
    .metric-label { font-size: 0.8rem; font-weight: 600; color: rgb(108,122,137); margin-bottom: 4px; }
    .metric-value { font-size: 1.1rem; font-weight: 700; color: #f1f5f9; }
    .metric-highlight { color: rgb(70,130,180); font-weight: 800; font-size: 1.1rem; }
    
    .pos-badge { padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.85rem; margin-bottom: 16px; display: inline-block; border: 1px solid; }
    .pos-head { background-color: rgba(239, 68, 68, 0.1); color: #ef4444; border-color: rgba(239, 68, 68, 0.3); }
    .pos-waist { background-color: rgba(245, 158, 11, 0.1); color: #f59e0b; border-color: rgba(245, 158, 11, 0.3); }
    .pos-feet { background-color: rgba(16, 185, 129, 0.1); color: #10b981; border-color: rgba(16, 185, 129, 0.3); }
    
    /* 메트릭 폰트 색상 강제 지정 */
    [data-testid="stMetricValue"] { color: rgb(70,130,180) !important; font-size: 1.8rem !important; font-weight: 800 !important; }
    
    /* 모바일 반응형 폰트 축소 (레이아웃은 1줄 유지) */
    @media (max-width: 768px) {
        .col-price { font-size: 0.95rem; }
        .col-diff { font-size: 0.8rem; }
        .col-yield { font-size: 0.95rem; }
        .stock-name { font-size: 0.95rem; }
        .list-header { font-size: 0.75rem; }
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=120)
def get_market_indices():
    indices = {"KOSPI": ("-", "-", "text-gray"), "KOSDAQ": ("-", "-", "text-gray"), "DOW": ("-", "-", "text-gray"), "NASDAQ": ("-", "-", "text-gray")}
    try:
        res = requests.get("https://finance.naver.com/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        for code, cls in [("KOSPI", ".kospi_area"), ("KOSDAQ", ".kosdaq_area")]:
            box = soup.select_one(cls)
            if box:
                val, diff, rate = box.select_one(".num").text, box.select_one(".num2").text, box.select_one(".num3").text
                b_txt = box.select_one(".blind").text
                cl = "text-red" if "상승" in b_txt else "text-blue" if "하락" in b_txt else "text-gray"
                sign = "▲" if "상승" in b_txt else "▼" if "하락" in b_txt else ""
                indices[code] = (val, f"{sign}{diff} ({rate})", cl)
    except: pass
    return indices

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
    
    # 🚨 무결성 필터: 시트 내의 모든 에러 텍스트(#N/A 등)를 0으로 강제 변환
    df = full_df.copy()
    for col in df.columns:
        if col not in ['계좌번호', '계좌유형', '종목명', '종목코드', '상품', '구분']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', '').str.replace('%', ''), errors='coerce').fillna(0)
            
    df = df[df['종목명'].astype(str).str.strip() != '']
    df = df[~df['종목명'].astype(str).str.contains('합계|총계|총액|총자산', na=False)]
    return sheet, df, full_df

def get_position_text(now, low, high):
    if high == 0 or low == 0 or high <= low or now == 0: return "지표 부족", "pos-unknown"
    pos = (now - low) / (high - low) * 100
    if pos >= 85: return f"머리 (고점 {pos:.0f}%)", "pos-head"
    if pos >= 35: return f"허리 (평균 시세 {pos:.0f}%)", "pos-waist"
    return f"발바닥 (바닥권 {pos:.0f}%)", "pos-feet"

# --- [3] 관제 화면 기동 ---
try:
    sheet, df, full_df = load_data()
    indices = get_market_indices()
    
    c_title, c_space, c_filter = st.columns([4, 1, 3])
    with c_title: st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V41</div>', unsafe_allow_html=True)
    with c_filter:
        acc_types = ["함대 전체"] + list(df['계좌유형'].unique())
        selected_type = st.selectbox("계좌 필터", acc_types, label_visibility="collapsed")
        
    if indices:
        idx_html = '<div class="index-container">'
        for name in ["KOSPI", "KOSDAQ"]:
            val, diff, cl = indices.get(name, ("-", "-", "text-gray"))
            idx_html += f'<div class="index-item"><span class="index-name">{name}</span><span class="index-val {cl}">{val}</span><span class="index-diff {cl}">{diff}</span></div>'
        idx_html += '</div>'
        st.markdown(idx_html, unsafe_allow_html=True)

    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()

    # KPI 합산 (구글 시트의 연산값을 100% 신뢰하여 추출)
    total_eval = display_df['평가금액'].sum() if '평가금액' in display_df else 0
    total_invest = display_df['매수금액'].sum() if '매수금액' in display_df else 0
    total_profit = display_df['평가손익'].sum() if '평가손익' in display_df else 0
    total_roi = (total_profit / total_invest * 100) if total_invest > 0 else 0
    total_cash = display_df[display_df['종목명'].astype(str).str.contains('현금|예수금', na=False)]['평가금액'].sum() if '평가금액' in display_df else 0
    
    # 전일비 정산 (안전 연산)
    daily_delta = 0
    if '전일종가' in display_df.columns and '현재가2' in display_df.columns and '잔고수량' in display_df.columns:
        for _, row in display_df.iterrows():
            if not any(x in str(row.get('종목명','')) for x in ["현금", "예수금", "단기", "연금"]):
                diff = row['현재가2'] - row['전일종가']
                if row['전일종가'] > 0 and row['현재가2'] > 0:
                    daily_delta += diff * row['잔고수량']
    
    kc1, kc2, kc3, kc4 = st.columns(4)
    kc1.metric("총 함대 자산", f"{total_eval:,.0f}원")
    kc2.metric("총 누적 손익", f"{total_profit:,.0f}원", delta=f"{total_roi:,.2f}%")
    kc3.metric("전일 대비 증감", f"{daily_delta:,.0f}원", delta=f"{daily_delta:,.0f}")
    kc4.metric("기동 대기 예수금", f"{total_cash:,.0f}원")
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        target_val = st.number_input("함대 목표 자산 (원)", value=830000000, step=10000000)
        t_rate = (total_eval/target_val*100) if target_val > 0 else 0
        st.markdown(f"<div style='color:rgb(70,130,180); font-size:1.2rem; font-weight:800; margin-top:-10px; margin-bottom:20px;'>목표 달성률: {t_rate:.1f}%</div>", unsafe_allow_html=True)

    if not display_df.empty:
        # 정렬 기준: 수익률2 (존재 시)
        yield_col = '수익률2' if '수익률2' in display_df.columns else '수익률'
        if yield_col in display_df.columns:
            display_df = display_df.sort_values(by=yield_col, ascending=False)
            
        st.markdown("""
        <div class="row-layout list-header">
            <div class="col-name">종목명</div>
            <div class="col-price">현재가</div>
            <div class="col-diff">당일비(%)</div>
            <div class="col-yield">수익률</div>
        </div>
        """, unsafe_allow_html=True)
        
        html_cards = ""
        for _, row in display_df.iterrows():
            is_special = any(x in str(row.get('종목명','')) for x in ["현금", "예수금", "단기", "연금"]) or (row.get('잔고수량',0) == 0 and row.get('매수금액',0) > 0)
            
            y_val = row.get(yield_col, 0)
            now_p = row.get('현재가2', row.get('현재가', row.get('매수단가', 0)))
            prev_p = row.get('전일종가', 0)
            high52 = row.get('52주최고', 0)
            low52 = row.get('52주최저', 0)
            
            diff = now_p - prev_p if prev_p > 0 else 0
            rate = (diff / prev_p * 100) if prev_p > 0 else 0
            
            if is_special:
                y_str = f"{y_val*100:,.2f}%" if y_val != 0 else "-"
                html_cards += f"""
                <details class="premium-card">
                    <summary>
                        <div class="row-layout">
                            <div class="col-name"><div class="status-dot dot-gray"></div><span class="stock-name text-gray">{row.get("종목명","")}</span></div>
                            <div class="col-price text-gray">{row.get("평가금액",0):,.0f}원</div>
                            <div class="col-diff text-gray">-</div>
                            <div class="col-yield text-gray">{y_str}</div>
                        </div>
                    </summary>
                    <div class="card-body"><div class="metric-grid">
                        <div class="metric-box"><div class="metric-label">평가 금액</div><div class="metric-highlight">{row.get('평가금액',0):,.0f}원</div></div>
                        <div class="metric-box"><div class="metric-label">투입 원금</div><div class="metric-value">{row.get('매수금액',0):,.0f}원</div></div>
                        <div class="metric-box"><div class="metric-label">누적 손익</div><div class="metric-value">{row.get('평가손익',0):,.0f}원</div></div>
                    </div></div>
                </details>"""
            else:
                # 일반 주식 UI (Steel Blue & Slate Gray 엄수)
                cl = "text-red" if y_val > 0 else "text-blue" if y_val < 0 else "text-gray"
                dt = "dot-red" if y_val > 0 else "dot-blue" if y_val < 0 else "dot-gray"
                diff_color = "text-red" if diff > 0 else "text-blue" if diff < 0 else "text-gray"
                ds = f"<span class='{diff_color}'>{'▲' if diff>0 else '▼' if diff<0 else ''}{abs(diff):,.0f} ({rate:.2f}%)</span>" if diff != 0 else "-"
                txt, pos_cl = get_position_text(now_p, low52, high52)
                
                # y_val이 이미 백분율 값일 경우와 소수점일 경우를 자동 분기
                y_display = y_val * 100 if -1 < y_val < 1 else y_val
                
                html_cards += f"""
                <details class="premium-card">
                    <summary>
                        <div class="row-layout">
                            <div class="col-name"><div class="status-dot {dt}"></div><span class="stock-name">{row.get("종목명","")}</span></div>
                            <div class="col-price {cl}">{now_p:,.0f}</div>
                            <div class="col-diff">{ds}</div>
                            <div class="col-yield {cl}">{y_display:.2f}%</div>
                        </div>
                    </summary>
                    <div class="card-body">
                        <div class="pos-badge {pos_cl}">📍 시세위치: {txt}</div>
                        <div class="metric-grid">
                            <div class="metric-box"><div class="metric-label">평가 금액</div><div class="metric-highlight">{row.get('평가금액',0):,.0f}원</div></div>
                            <div class="metric-box"><div class="metric-label">매수 총액</div><div class="metric-value">{row.get('매수금액',0):,.0f}원</div></div>
                            <div class="metric-box"><div class="metric-label">누적 손익</div><div class="metric-value {cl}">{row.get('평가손익',0):,.0f}원</div></div>
                            <div class="metric-box"><div class="metric-label">평균 단가 / 수량</div><div class="metric-value">{row.get('매수단가',0):,.0f}원 <span class='text-gray'>({row.get('잔고수량',0):,.0f}주)</span></div></div>
                            <div class="metric-box"><div class="metric-label">52주 최고</div><div class="metric-value">{high52:,.0f}원</div></div>
                            <div class="metric-box"><div class="metric-label">52주 최저</div><div class="metric-value">{low52:,.0f}원</div></div>
                        </div>
                    </div>
                </details>"""
        st.markdown(html_cards, unsafe_allow_html=True)
except Exception as e: st.error(f"함대 기동 중지: {e}")
