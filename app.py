import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import time

# --- [1] 프리미엄 관제소 V19.0 (MTS UI & 시장 지수) ---
st.set_page_config(page_title="거북이 함대 기동 본부 V19.0", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f1f5f9; }
    h1, h2, h3, p, span, div { font-family: 'Urbanist', 'Noto Sans KR', sans-serif; }
    .hq-title { font-size: 1.4rem; color: #4682B4; font-weight: 800; letter-spacing: 1px; padding-top: 10px; margin-bottom: 20px; }
    
    /* 지수 전광판 스타일 */
    .index-container { display: flex; justify-content: space-between; background: #0f172a; padding: 15px 20px; border-radius: 12px; border: 1px solid #1e293b; margin-bottom: 20px; }
    .index-item { display: flex; flex-direction: column; align-items: center; width: 24%; }
    .index-name { font-size: 0.85rem; color: #94a3b8; font-weight: 700; margin-bottom: 4px; }
    .index-val { font-size: 1.2rem; font-weight: 800; color: #f8fafc; }
    .index-diff { font-size: 0.85rem; font-weight: 600; }
    
    /* MTS 스타일 커스텀 아코디언 */
    details.premium-card {
        background-color: #0f172a; border: 1px solid #1e293b; border-radius: 12px; margin-bottom: 10px; transition: all 0.2s;
    }
    details.premium-card:hover { border-color: #4682B4; box-shadow: 0 4px 12px rgba(70, 130, 180, 0.15); }
    details.premium-card summary {
        display: flex; align-items: center; padding: 16px 20px; cursor: pointer; list-style: none; user-select: none;
    }
    details.premium-card summary::-webkit-details-marker { display: none; }
    
    /* 4열 완벽 정렬 그리드 (MTS 비율) */
    .row-layout { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: 10px; }
    .col-name { width: 35%; display: flex; align-items: center; gap: 10px; overflow: hidden; }
    .col-price { width: 25%; text-align: right; font-size: 1.1rem; font-weight: 800; color: #f8fafc; }
    .col-diff { width: 20%; text-align: right; font-size: 0.95rem; font-weight: 700; }
    .col-yield { width: 20%; text-align: right; font-size: 1.05rem; font-weight: 800; }
    
    .status-dot { min-width: 8px; height: 8px; border-radius: 50%; }
    .dot-red { background-color: #ef4444; box-shadow: 0 0 8px rgba(239, 68, 68, 0.6); }
    .dot-blue { background-color: #3b82f6; box-shadow: 0 0 8px rgba(59, 130, 246, 0.6); }
    .dot-gray { background-color: #94a3b8; }
    .stock-name { font-size: 1.1rem; font-weight: 700; color: #f8fafc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    
    .text-red { color: #ef4444; } .text-blue { color: #3b82f6; } .text-gray { color: #94a3b8; }
    
    .card-body { background-color: #020617; padding: 20px; border-top: 1px solid #1e293b; }
    .metric-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
    .metric-box { display: flex; flex-direction: column; }
    .metric-label { font-size: 0.8rem; font-weight: 600; color: #64748b; margin-bottom: 4px; }
    .metric-value { font-size: 1.1rem; font-weight: 700; color: #f1f5f9; }
    .metric-highlight { color: #4682B4; font-weight: 800; font-size: 1.1rem; }
    
    .pos-badge { padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.85rem; margin-bottom: 16px; display: inline-block; border: 1px solid; }
    .pos-head { background-color: rgba(239, 68, 68, 0.1); color: #ef4444; border-color: rgba(239, 68, 68, 0.3); }
    .pos-shoulder { background-color: rgba(248, 113, 113, 0.1); color: #f87171; border-color: rgba(248, 113, 113, 0.3); }
    .pos-waist { background-color: rgba(245, 158, 11, 0.1); color: #f59e0b; border-color: rgba(245, 158, 11, 0.3); }
    .pos-knee { background-color: rgba(52, 211, 153, 0.1); color: #34d399; border-color: rgba(52, 211, 153, 0.3); }
    .pos-feet { background-color: rgba(16, 185, 129, 0.1); color: #10b981; border-color: rgba(16, 185, 129, 0.3); }
    
    [data-testid="stMetricValue"] { color: #4682B4 !important; font-size: 1.8rem !important; font-weight: 800 !important; }
    </style>
    """, unsafe_allow_html=True)

def col_letter(n):
    string = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string

@st.cache_data(ttl=120)
def get_market_indices():
    """네이버 금융 메인에서 핵심 4대 지수 스캔"""
    try:
        url = "https://finance.naver.com/"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        def parse_idx(box_class):
            box = soup.select_one(f".{box_class}")
            if not box: return "0", "0", "text-gray"
            val = box.select_one(".num").text
            diff = box.select_one(".num2").text
            rate = box.select_one(".num3").text
            blind = box.select_one(".blind")
            if blind and "상승" in blind.text: return val, f"▲{diff} ({rate})", "text-red"
            elif blind and "하락" in blind.text: return val, f"▼{diff} ({rate})", "text-blue"
            return val, f"{diff} ({rate})", "text-gray"
            
        return {
            "KOSPI": parse_idx("kospi_area"), "KOSDAQ": parse_idx("kosdaq_area"),
            "DOW": parse_idx("dow_area"), "NASDAQ": parse_idx("nasdaq_area")
        }
    except: return {}

def fetch_emergency_price(ticker):
    if pd.isna(ticker) or str(ticker).strip() in ["", "0"]: return 0
    clean_ticker = str(int(float(ticker))).zfill(6) if str(ticker).replace('.','').isdigit() else str(ticker).strip()
    try:
        url = f"https://finance.naver.com/item/main.naver?code={clean_ticker}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=2)
        price_tag = BeautifulSoup(res.text, 'html.parser').select_one(".no_today .blind")
        return int(price_tag.text.replace(',', '')) if price_tag else 0
    except: return 0

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
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0").get_worksheet(0)
    full_df = pd.DataFrame(sheet.get_all_records())
    
    essential_cols = ['계좌번호', '계좌유형', '종목명', '종목코드', '잔고수량', '매수단가', '현재가2', '현재가1', '수익률', '수익률1', '평가금액', '매수금액', '평가손익', '전일종가', '52주최고', '52주최저']
    df = full_df[[c for c in essential_cols if c in full_df.columns]].copy()
    
    for col in essential_cols:
        if col not in df.columns: df[col] = 0
        elif col not in ['계좌번호', '계좌유형', '종목명', '종목코드']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', ''), errors='coerce').fillna(0)
            
    # [계산 무결성 100% 필터] 합계 행 제외 및 수량이 0인 찌꺼기 행 완전 삭제
    df = df[~df['종목명'].astype(str).str.contains('합계|총계|총액', na=False)]
    df = df[df['종목명'].astype(str).str.strip() != '']
    df = df[df['잔고수량'] > 0] # 이 한 줄이 모든 계산 뻥튀기를 막습니다.
    
    target_yield = '수익률' if '수익률' in full_df.columns else '수익률1' if '수익률1' in full_df.columns else None
    df['수익률_숫자'] = pd.to_numeric(df[target_yield].astype(str).str.replace('%', '').str.replace(',', ''), errors='coerce').fillna(0) if target_yield else 0.0
    return sheet, df, full_df

def get_position_text(now, low, high):
    if high == 0 or low == 0 or high <= low or now == 0: return "지표 수집중", "pos-unknown"
    pos = (now - low) / (high - low) * 100
    if pos >= 85: return f"머리 (고점 {pos:.0f}%)", "pos-head"
    if pos >= 65: return f"어깨 ({pos:.0f}%)", "pos-shoulder"
    if pos >= 35: return f"허리 ({pos:.0f}%)", "pos-waist"
    if pos >= 15: return f"무릎 ({pos:.0f}%)", "pos-knee"
    return f"발바닥 (저점 {pos:.0f}%)", "pos-feet"

# --- [3] 관제 화면 기동 ---
try:
    sheet, df, full_df = load_data()
    indices = get_market_indices()
    
    # 상단 헤더
    c_title, c_space, c_filter = st.columns([4, 1, 3])
    with c_title: st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V19</div>', unsafe_allow_html=True)
    with c_filter:
        acc_types = ["함대 전체"] + list(df['계좌유형'].unique())
        selected_type = st.selectbox("필터", acc_types, label_visibility="collapsed")
        
    # [신규] 4대 글로벌/국내 지수 전광판 렌더링
    if indices:
        idx_html = '<div class="index-container">'
        for name in ["KOSPI", "KOSDAQ", "DOW", "NASDAQ"]:
            val, diff, cl = indices.get(name, ("0", "0", "text-gray"))
            idx_html += f'<div class="index-item"><span class="index-name">{name}</span><span class="index-val {cl}">{val}</span><span class="index-diff {cl}">{diff}</span></div>'
        idx_html += '</div>'
        st.markdown(idx_html, unsafe_allow_html=True)

    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()

    processed_data = []
    for _, row in display_df.iterrows():
        now_p = row['현재가2'] if row['현재가2'] != 0 else row['현재가1']
        if now_p == 0 and not any(x in str(row['종목명']) for x in ["현금", "예수금"]):
            now_p = fetch_emergency_price(row.get('종목코드', ''))
            
        real_yield = ((now_p - row['매수단가']) / row['매수단가'] * 100) if row['매수단가'] > 0 else 0
        real_eval = now_p * row['잔고수량']
        
        r_dict = row.to_dict()
        r_dict.update({'보정가': now_p, '보정수익률': real_yield, '보정평가액': real_eval})
        processed_data.append(r_dict)

    final_df = pd.DataFrame(processed_data).sort_values(by='보정수익률', ascending=False) if processed_data else pd.DataFrame()
    
    total_eval = final_df['보정평가액'].sum() if not final_df.empty else 0
    total_cash = final_df[final_df['종목명'].astype(str).str.contains('현금|예수금', na=False)]['보정평가액'].sum() if not final_df.empty else 0
    
    # 전일비 계산: 전일종가가 있는 정상 종목만 합산
    valid_prev = final_df[final_df['전일종가'] > 0]
    total_prev = (valid_prev['전일종가'] * valid_prev['잔고수량']).sum() if not valid_prev.empty else 0
    daily_delta = valid_prev['보정평가액'].sum() - total_prev if total_prev > 0 else 0
    
    kc1, kc2, kc3 = st.columns(3)
    kc1.metric("총 함대 자산", f"{total_eval:,.0f}원")
    if total_prev > 0: kc2.metric("전일 대비 증감", f"{daily_delta:,.0f}원", delta=f"{daily_delta:,.0f}")
    else: kc2.metric("전일 대비 증감", "지표 수집중", delta=None)
    kc3.metric("기동 대기 예수금", f"{total_cash:,.0f}원")
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        target_val = st.number_input("함대 목표 자산 (원)", value=830000000, step=10000000)
        st.markdown(f"<div style='color:#4682B4; font-size:1.2rem; font-weight:800; margin-top:-10px; margin-bottom:20px;'>목표 달성률: {(total_eval/target_val*100):.1f}%</div>", unsafe_allow_html=True)
        st.divider()
        mode = st.radio("작전 모드", ["기존 종목 매매", "데이터 강제 수정", "신규 종목 추가"])
        
        acc_opts = [f"{r['계좌유형']} [{r['계좌번호']}]" for _, r in full_df[['계좌유형', '계좌번호']].drop_duplicates().iterrows() if str(r['계좌번호']).strip() != '']
        sel_acc_str = st.selectbox("작전 계좌 선택", acc_opts) if acc_opts else ""
        sel_acc = sel_acc_str.split('[')[-1].replace(']', '').strip() if sel_acc_str else ""
        
        if "신규" not in mode:
            s_list = [s for s in full_df[full_df['계좌번호'].astype(str).str.strip() == sel_acc]['종목명'].dropna().tolist() if str(s).strip() != '']
            s_name = st.selectbox("작전 종목 선택", s_list if s_list else ["없음"])
            action = st.radio("구분", ["매수", "매도"], horizontal=True) if "매매" in mode else None
        else:
            s_name = st.text_input("신규 종목명")
            s_code = st.text_input("종목코드 (숫자 6자리)")
            
        qty = st.number_input("수량", min_value=0, step=1)
        price = st.number_input("현재가/단가", min_value=0, step=100)
        
        if st.button("명령 확정 (Sync)"):
            idx_map = {col.strip(): i+1 for i, col in enumerate(full_df.columns)}
            if "신규" in mode and s_name:
                nr = len(full_df) + 2
                sheet.update_cell(nr, idx_map['계좌번호'], sel_acc)
                at = full_df[full_df['계좌번호'].astype(str).str.strip() == sel_acc]['계좌유형'].iloc[0] if not full_df[full_df['계좌번호'].astype(str).str.strip() == sel_acc].empty else "수동"
                sheet.update_cell(nr, idx_map['계좌유형'], at)
                sheet.update_cell(nr, idx_map['종목명'], s_name)
                sheet.update_cell(nr, idx_map['잔고수량'], int(qty))
                sheet.update_cell(nr, idx_map['매수단가'], int(price))
                
                q_l, b_l, c_l = col_letter(idx_map['잔고수량']), col_letter(idx_map['매수단가']), col_letter(idx_map.get('현재가2', idx_map.get('현재가1', 0)))
                ba_l, ea_l, p_l = col_letter(idx_map.get('매수금액',0)), col_letter(idx_map.get('평가금액',0)), col_letter(idx_map.get('평가손익',0))
                y_idx = idx_map.get('수익률', idx_map.get('수익률1'))
                y_l = col_letter(y_idx) if y_idx else None

                if ba_l: sheet.update_cell(nr, idx_map['매수금액'], f"={q_l}{nr}*{b_l}{nr}")
                if ea_l: sheet.update_cell(nr, idx_map['평가금액'], f"={q_l}{nr}*{c_l}{nr}")
                if p_l: sheet.update_cell(nr, idx_map['평가손익'], f"={ea_l}{nr}-{ba_l}{nr}")
                if y_l: sheet.update_cell(nr, y_idx, f"=IFERROR({p_l}{nr}/{ba_l}{nr}, 0)")
                
                if s_code:
                    c = str(s_code).strip().zfill(6)
                    if '종목코드' in idx_map: sheet.update_cell(nr, idx_map['종목코드'], c)
                    for k in ['현재가2', '현재가1']:
                        if k in idx_map: sheet.update_cell(nr, idx_map[k], f'=GOOGLEFINANCE("KRX:{c}", "price")')
                    if '전일종가' in idx_map: sheet.update_cell(nr, idx_map['전일종가'], f'=GOOGLEFINANCE("KRX:{c}", "price") - GOOGLEFINANCE("KRX:{c}", "change")')
                    if '52주최고' in idx_map: sheet.update_cell(nr, idx_map['52주최고'], f'=GOOGLEFINANCE("KRX:{c}", "high52")')
                    if '52주최저' in idx_map: sheet.update_cell(nr, idx_map['52주최저'], f'=GOOGLEFINANCE("KRX:{c}", "low52")')
                else:
                    for k in ['현재가2', '현재가1']:
                        if k in idx_map: sheet.update_cell(nr, idx_map[k], int(price))
            
            elif s_name != "없음":
                ti = full_df[(full_df['계좌번호'].astype(str).str.strip() == sel_acc) & (full_df['종목명'] == s_name)].index[0]
                if "수정" in mode:
                    sheet.update_cell(ti+2, idx_map['잔고수량'], int(qty))
                    sheet.update_cell(ti+2, idx_map['매수단가'], int(price))
                else:
                    oq, oa = full_df.at[ti, '잔고수량'], full_df.at[ti, '매수단가']
                    nq = oq + qty if action == "매수" else max(0, oq - qty)
                    na = ((oq * oa) + (qty * price)) / nq if action == "매수" and nq > 0 else oa
                    sheet.update_cell(ti+2, idx_map['잔고수량'], int(nq))
                    sheet.update_cell(ti+2, idx_map['매수단가'], int(na))
            
            st.cache_data.clear()
            st.rerun()

    # --- [상용 MTS급 완벽 비율 카드 렌더링] ---
    if not final_df.empty:
        html_cards = ""
        for _, row in final_df.iterrows():
            is_c = any(x in str(row['종목명']) for x in ["현금", "예수금"])
            
            if is_c:
                html_cards += f"""
                <details class="premium-card">
                    <summary>
                        <div class="row-layout">
                            <div class="col-name"><div class="status-dot dot-gray"></div><span class="stock-name" style="color:#94a3b8;">{row['종목명']}</span></div>
                            <div class="col-price">{row['보정평가액']:,.0f}원</div>
                            <div class="col-diff text-gray">-</div>
                            <div class="col-yield text-gray">-</div>
                        </div>
                    </summary>
                </details>
                """
            else:
                yield_v = row['보정수익률']
                now_p = row['보정가']
                prev_p = row['전일종가']
                
                daily_diff = now_p - prev_p if prev_p > 0 else 0
                if daily_diff > 0:
                    diff_str, color_class, dot_class = f"▲{daily_diff:,.0f}", "text-red", "dot-red"
                elif daily_diff < 0:
                    diff_str, color_class, dot_class = f"▼{abs(daily_diff):,.0f}", "text-blue", "dot-blue"
                else:
                    diff_str, color_class, dot_class = "-", "text-gray", "dot-gray"
                    
                txt, cl = get_position_text(now_p, row['52주최저'], row['52주최고'])
                
                # 4열 정렬 UI 적용
                html_cards += f"""
                <details class="premium-card">
                    <summary>
                        <div class="row-layout">
                            <div class="col-name"><div class="status-dot {dot_class}"></div><span class="stock-name">{row['종목명']}</span></div>
                            <div class="col-price {color_class}">{now_p:,.0f}</div>
                            <div class="col-diff {color_class}">{diff_str}</div>
                            <div class="col-yield {color_class}">{yield_v:.2f}%</div>
                        </div>
                    </summary>
                    <div class="card-body">
                        <div class="pos-badge {cl}">📍 시세위치: {txt}</div>
                        <div class="metric-grid">
                            <div class="metric-box"><div class="metric-label">평가 금액</div><div class="metric-highlight">{row['보정평가액']:,.0f}원</div></div>
                            <div class="metric-box"><div class="metric-label">투입 원금</div><div class="metric-value">{row['매수금액']:,.0f}원</div></div>
                            <div class="metric-box"><div class="metric-label">평균 단가</div><div class="metric-value">{row['매수단가']:,.0f}원</div></div>
                            <div class="metric-box"><div class="metric-label">보유 수량</div><div class="metric-value">{row['잔고수량']:,.0f}주</div></div>
                            <div class="metric-box"><div class="metric-label">52주 최고가</div><div class="metric-value">{row['52주최고']:,.0f}원</div></div>
                            <div class="metric-box"><div class="metric-label">52주 최저가</div><div class="metric-value">{row['52주최저']:,.0f}원</div></div>
                        </div>
                    </div>
                </details>
                """
        st.markdown(html_cards, unsafe_allow_html=True)

except Exception as e: st.error(f"함대 기동 중지: {e}")
