import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup

# --- [1] 시스템 설정 및 CSS (모바일 최적화 규격 엄수) ---
st.set_page_config(page_title="거북이 함대 기동 본부 V37", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f1f5f9; }
    h1, h2, h3, p, span, div { font-family: 'Urbanist', 'Noto Sans KR', sans-serif; }
    .hq-title { font-size: 1.4rem; color: #4682B4; font-weight: 800; letter-spacing: 1px; padding-top: 10px; margin-bottom: 20px; }
    
    .index-container { display: flex; justify-content: space-between; background: #0f172a; padding: 15px 20px; border-radius: 12px; border: 1px solid #1e293b; margin-bottom: 20px; }
    .index-item { display: flex; flex-direction: column; align-items: center; width: 24%; }
    .index-name { font-size: 0.85rem; color: rgb(108,122,137); font-weight: 700; margin-bottom: 4px; }
    .index-val { font-size: 1.15rem; font-weight: 800; color: #f8fafc; }
    .index-diff { font-size: 0.85rem; font-weight: 600; }
    
    .list-header { color: rgb(108,122,137); font-size: 0.85rem; font-weight: 600; padding: 0 16px 8px 16px; border-bottom: 1px solid #1e293b; margin-bottom: 10px; display: flex; justify-content: space-between; gap: 8px; }
    .header-col { width: 28%; text-align: left; }
    .header-price { width: 20%; text-align: right; }
    .header-diff { width: 28%; text-align: right; }
    .header-yield { width: 24%; text-align: right; }

    details.premium-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 12px; margin-bottom: 10px; transition: all 0.2s; }
    details.premium-card:hover { border-color: rgb(70,130,180); }
    details.premium-card summary { padding: 16px 16px; cursor: pointer; list-style: none; }
    details.premium-card summary::-webkit-details-marker { display: none; }
    
    .card-header-flex { display: flex; justify-content: space-between; align-items: center; width: 100%; gap: 8px;}
    .card-left { display: flex; align-items: center; gap: 8px; width: 45%; }
    .card-right { display: flex; flex-direction: column; align-items: flex-end; width: 55%; text-align: right; }
    .card-price { font-size: 1.1rem; font-weight: 800; letter-spacing: -0.5px; }
    .card-sub { font-size: 0.85rem; font-weight: 600; margin-top: 3px; }
    
    .status-dot { min-width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .dot-red { background-color: #ef4444; box-shadow: 0 0 8px rgba(239, 68, 68, 0.6); }
    .dot-blue { background-color: #3b82f6; box-shadow: 0 0 8px rgba(59, 130, 246, 0.6); }
    .dot-gray { background-color: rgb(108,122,137); }
    
    .stock-name { font-size: 1.05rem; font-weight: 700; color: #f8fafc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .text-red { color: #ef4444; } .text-blue { color: #3b82f6; } .text-gray { color: rgb(108,122,137); }
    
    .card-body { background-color: #020617; padding: 16px; border-top: 1px solid #1e293b; border-radius: 0 0 12px 12px; }
    .metric-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
    .metric-box { display: flex; flex-direction: column; }
    .metric-label { font-size: 0.75rem; font-weight: 600; color: rgb(108,122,137); margin-bottom: 2px; }
    .metric-value { font-size: 1rem; font-weight: 700; color: #f1f5f9; }
    .metric-highlight { color: rgb(70,130,180); font-weight: 800; font-size: 1rem; }
    
    .pos-badge { padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.8rem; margin-bottom: 12px; display: inline-block; border: 1px solid; }
    .pos-head { background-color: rgba(239, 68, 68, 0.1); color: #ef4444; border-color: rgba(239, 68, 68, 0.3); }
    .pos-waist { background-color: rgba(245, 158, 11, 0.1); color: #f59e0b; border-color: rgba(245, 158, 11, 0.3); }
    .pos-feet { background-color: rgba(16, 185, 129, 0.1); color: #10b981; border-color: rgba(16, 185, 129, 0.3); }
    
    [data-testid="stMetricValue"] { color: rgb(70,130,180) !important; font-size: 1.8rem !important; font-weight: 800 !important; }
    
    @media (max-width: 768px) {
        .index-container { flex-wrap: wrap; padding: 10px; }
        .index-item { width: 48%; margin-bottom: 10px; }
        .hq-title { font-size: 1.2rem; }
        .stock-name { font-size: 0.95rem; }
        .card-price { font-size: 1.05rem; }
        .card-sub { font-size: 0.8rem; }
        [data-testid="stMetricValue"] { font-size: 1.3rem !important; }
        [data-testid="stMetricDelta"] { font-size: 0.9rem !important; }
    }
    </style>
    """, unsafe_allow_html=True)

# --- [2] 네이버 금융 라이브 스캐너 (캐싱 적용으로 속도 향상) ---
@st.cache_data(ttl=120) # 2분 동안 캐싱
def get_naver_stock_info(code):
    if pd.isna(code) or str(code).strip() in ["", "0"]: return 0, 0, 0, 0
    clean_code = str(int(float(code))).zfill(6) if str(code).replace('.','').isdigit() else str(code).strip()
    
    try:
        url = f"https://finance.naver.com/item/main.naver?code={clean_code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        now_p_tag = soup.select_one(".no_today .blind")
        now_p = int(now_p_tag.text.replace(',', '')) if now_p_tag else 0
        
        prev_p_tag = soup.select_one("td.first .blind")
        prev_p = int(prev_p_tag.text.replace(',', '')) if prev_p_tag else 0
        
        # 52주 데이터 스캔
        high52, low52 = 0, 0
        table = soup.select("table.no_info tr")
        for tr in table:
            if "52주" in tr.text:
                tds = tr.select("td em")
                if len(tds) >= 2:
                    high52 = int(tds[0].text.replace(',', ''))
                    low52 = int(tds[1].text.replace(',', ''))
                break
                
        return now_p, prev_p, high52, low52
    except:
        return 0, 0, 0, 0

@st.cache_data(ttl=120) # 2분 동안 캐싱
def get_market_indices():
    indices = {"KOSPI": ("-", "-", "text-gray"), "KOSDAQ": ("-", "-", "text-gray"), "DOW": ("-", "-", "text-gray"), "NASDAQ": ("-", "-", "text-gray")}
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get("https://finance.naver.com/", headers=headers, timeout=3)
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

# --- [3] 데이터베이스 로드 ---
@st.cache_data(ttl=60) # 1분 동안 캐싱
def load_data():
    client = get_gspread_client()
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0").get_worksheet(0)
    full_df = pd.DataFrame(sheet.get_all_records())
    full_df.columns = full_df.columns.str.strip()
    
    essential_cols = ['계좌번호', '계좌유형', '종목명', '종목코드', '잔고수량', '매수단가', '매수금액', '평가금액']
    for col in essential_cols:
        if col not in full_df.columns: full_df[col] = 0
            
    df = full_df.copy()
    for col in essential_cols:
        if col not in ['계좌번호', '계좌유형', '종목명', '종목코드']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', '').str.replace('%', ''), errors='coerce').fillna(0)

    # 찌꺼기 행 제거
    df = df[df['종목명'].astype(str).str.strip() != '']
    df = df[~df['종목명'].astype(str).str.contains('합계|총계|총액|총자산', na=False)]
    
    is_special = df['종목명'].astype(str).str.contains('현금|예수금|단기|연금|펀드', na=False)
    df = df[is_special | (df['잔고수량'] > 0) | (df['매수금액'] > 0) | (df['평가금액'] > 0)]
    
    return sheet, df, full_df

def get_position_text(now, low, high):
    if high == 0 or low == 0 or high <= low or now == 0: return "데이터 수집중", "pos-unknown"
    pos = (now - low) / (high - low) * 100
    if pos >= 85: return f"머리 (고점 {pos:.0f}%)", "pos-head"
    if pos >= 35: return f"허리 (평균 시세 {pos:.0f}%)", "pos-waist"
    return f"발바닥 (바닥권 {pos:.0f}%)", "pos-feet"

# --- [4] 관제소 기동 ---
try:
    sheet, df, full_df = load_data()
    indices = get_market_indices()
    
    c_title, c_space, c_filter = st.columns([4, 1, 3])
    with c_title: st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V37 (OPTIMIZED LIVE)</div>', unsafe_allow_html=True)
    with c_filter:
        acc_types = ["함대 전체"] + list(df['계좌유형'].unique())
        selected_type = st.selectbox("필터", acc_types, label_visibility="collapsed")
        
    if indices:
        idx_html = '<div class="index-container">'
        for name in ["KOSPI", "KOSDAQ"]:
            val, diff, cl = indices.get(name, ("-", "-", "text-gray"))
            idx_html += f'<div class="index-item"><span class="index-name">{name}</span><span class="index-val {cl}">{val}</span><span class="index-diff {cl}">{diff}</span></div>'
        idx_html += '</div>'
        st.markdown(idx_html, unsafe_allow_html=True)

    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()

    # --- 🚨 [핵심] 파이썬 독자 연산 엔진 기동 ---
    live_data = []
    total_eval = 0
    total_invest = 0
    total_profit = 0
    daily_delta = 0
    total_cash = 0

    for _, row in display_df.iterrows():
        is_special = any(x in str(row['종목명']) for x in ["현금", "예수금", "단기", "연금", "펀드"]) or (row['잔고수량'] == 0 and row['매수금액'] > 0)
        
        data = row.to_dict()
        
        if is_special:
            e_amt = row['평가금액']
            i_amt = row['매수금액']
            profit = e_amt - i_amt
            yld = (profit / i_amt * 100) if i_amt > 0 else 0
            
            total_eval += e_amt
            total_invest += i_amt
            total_profit += profit
            if any(x in str(row['종목명']) for x in ["현금", "예수금"]): total_cash += e_amt
                
            data.update({'live_eval': e_amt, 'live_inv': i_amt, 'live_prof': profit, 'live_yield': yld, 'now_p': 0, 'diff': 0, 'rate': 0, 'high': 0, 'low': 0})
        
        else:
            # 네이버 금융에서 실시간 가격 수집 (캐싱 적용)
            now_p, prev_p, high52, low52 = get_naver_stock_info(row['종목코드'])
            
            # (보험) 네이버 일시적 오류 시 엑셀 원본 단가로 방어
            if now_p == 0: now_p = row['매수단가'] 
            
            e_amt = now_p * row['잔고수량']
            i_amt = row['매수단가'] * row['잔고수량'] if row['매수금액'] == 0 else row['매수금액']
            profit = e_amt - i_amt
            yld = (profit / i_amt * 100) if i_amt > 0 else 0
            
            total_eval += e_amt
            total_invest += i_amt
            total_profit += profit
            
            diff = now_p - prev_p if prev_p > 0 else 0
            rate = (diff / prev_p * 100) if prev_p > 0 else 0
            if prev_p > 0 and now_p > 0 and row['잔고수량'] > 0: 
                daily_delta += diff * row['잔고수량']
                
            data.update({'live_eval': e_amt, 'live_inv': i_amt, 'live_prof': profit, 'live_yield': yld, 'now_p': now_p, 'diff': diff, 'rate': rate, 'high': high52, 'low': low52})

        live_data.append(data)
        
    total_roi = (total_profit / total_invest * 100) if total_invest > 0 else 0
    
    # 4대 지표 출력
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

    if live_data:
        cards_df = pd.DataFrame(live_data).sort_values(by='live_yield', ascending=False)
        html_cards = ""
        
        # 디자인 복원: V32의 Premium Card 레이아웃 적용
        # 헤더 섹션
        st.markdown("""
            <div class="list-header">
                <div class="header-col">종목명</div>
                <div class="header-price">현재가</div>
                <div class="header-diff">당일비(%)</div>
                <div class="header-yield">수익률</div>
            </div>
        """, unsafe_allow_html=True)
        
        for _, row in cards_df.iterrows():
            is_special = any(x in str(row['종목명']) for x in ["현금", "예수금", "단기", "연금", "펀드"]) or (row['잔고수량'] == 0 and row['매수금액'] > 0)
            
            if is_special:
                y_str = f"{row['live_yield']:,.2f}%" if row['live_yield'] != 0 else "-"
                # 모바일 2단 정렬 (특수 자산)
                html_cards += f"""
                <details class="premium-card">
                    <summary>
                        <div class="card-header-flex">
                            <div class="card-left">
                                <div class="status-dot dot-gray"></div>
                                <span class="stock-name text-gray">{row["종목명"]}</span>
                            </div>
                            <div class="card-right">
                                <div class="card-price text-gray">{row["live_eval"]:,.0f}원</div>
                                <div class="card-sub text-gray">수익률: {y_str}</div>
                            </div>
                        </div>
                    </summary>
                    <div class="card-body"><div class="metric-grid">
                        <div class="metric-box"><div class="metric-label">평가 금액</div><div class="metric-highlight">{row['live_eval']:,.0f}원</div></div>
                        <div class="metric-box"><div class="metric-label">투입 원금</div><div class="metric-value">{row['live_inv']:,.0f}원</div></div>
                        <div class="metric-box"><div class="metric-label">누적 손익</div><div class="metric-value">{row['live_prof']:,.0f}원</div></div>
                    </div></div>
                </details>"""
            else:
                y_val, now_p, diff, rate = row['live_yield'], row['now_p'], row['diff'], row['rate']
                cl = "text-red" if y_val > 0 else "text-blue" if y_val < 0 else "text-gray"
                dt = "dot-red" if y_val > 0 else "dot-blue" if y_val < 0 else "dot-gray"
                diff_color = "text-red" if diff > 0 else "text-blue" if diff < 0 else "text-gray"
                ds = f"<span class='{diff_color}'>{'▲' if diff>0 else '▼' if diff<0 else ''}{abs(diff):,.0f} ({rate:.2f}%)</span>" if diff != 0 else "-"
                txt, pos_cl = get_position_text(now_p, row['low'], row['high'])
                
                # 모바일 2단 정렬 (일반 주식)
                html_cards += f"""
                <details class="premium-card">
                    <summary>
                        <div class="card-header-flex">
                            <div class="card-left">
                                <div class="status-dot {dt}"></div>
                                <span class="stock-name">{row["종목명"]}</span>
                            </div>
                            <div class="card-right">
                                <div class="card-price {cl}">{now_p:,.0f}원</div>
                                <div class="card-sub {cl}">{ds} &nbsp;│&nbsp; <span style="font-weight:800;">{y_val:.2f}%</span></div>
                            </div>
                        </div>
                    </summary>
                    <div class="card-body">
                        <div class="pos-badge {pos_cl}">📍 시세위치: {txt}</div>
                        <div class="metric-grid">
                            <div class="metric-box"><div class="metric-label">평가 금액</div><div class="metric-highlight">{row['live_eval']:,.0f}원</div></div>
                            <div class="metric-box"><div class="metric-label">매수 총액</div><div class="metric-value">{row['live_inv']:,.0f}원</div></div>
                            <div class="metric-box"><div class="metric-label">누적 손익</div><div class="metric-value {cl}">{row['live_prof']:,.0f}원</div></div>
                            <div class="metric-box"><div class="metric-label">평균 단가 / 수량</div><div class="metric-value">{row['매수단가']:,.0f}원 <span class='text-gray'>({row['잔고수량']:,.0f}주)</span></div></div>
                            <div class="metric-box"><div class="metric-label">52주 최고</div><div class="metric-value">{row['high']:,.0f}원</div></div>
                            <div class="metric-box"><div class="metric-label">52주 최저</div><div class="metric-value">{row['low']:,.0f}원</div></div>
                        </div>
                    </div>
                </details>"""
        st.markdown(html_cards, unsafe_allow_html=True)
except Exception as e: st.error(f"함대 기동 중지: {e}")
