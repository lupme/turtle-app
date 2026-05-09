import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import time

# --- [1] 시스템 설정 및 CSS ---
st.set_page_config(page_title="거북이 함대 기동 본부 V45", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    h1, h2, h3, p, span, div { font-family: 'Urbanist', 'Noto Sans KR', sans-serif; }
    
    .hq-title { font-size: 1.4rem; color: rgb(70,130,180); font-weight: 800; letter-spacing: 1px; padding-top: 10px; margin-bottom: 20px; }
    
    .index-container { display: flex; justify-content: space-between; background: #0f172a; padding: 15px 20px; border-radius: 12px; border: 1px solid #1e293b; margin-bottom: 20px; }
    .index-item { display: flex; flex-direction: column; align-items: center; width: 24%; }
    .index-name { font-size: 0.85rem; color: rgb(108,122,137); font-weight: 700; margin-bottom: 4px; }
    .index-val { font-size: 1.15rem; font-weight: 800; color: #ffffff; }
    .index-diff { font-size: 0.85rem; font-weight: 600; }
    
    .streamlit-expanderHeader { background-color: #0f172a !important; border: 1px solid #1e293b !important; border-radius: 8px !important; color: rgb(108,122,137) !important; font-weight: 700 !important; }
    div[data-testid="stExpander"] div[role="button"] p { font-weight: 700 !important; color: rgb(108,122,137) !important; }
    
    details.premium-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 12px; margin-bottom: 10px; transition: all 0.2s; }
    details.premium-card:hover { border-color: rgb(70,130,180); }
    details.premium-card summary { padding: 16px; cursor: pointer; list-style: none; }
    details.premium-card summary::-webkit-details-marker { display: none; }
    
    .card-header-flex { display: flex; justify-content: space-between; align-items: center; width: 100%; gap: 10px; }
    .card-left { display: flex; align-items: center; gap: 8px; width: 30%; min-width: 150px; }
    .card-right { display: flex; justify-content: space-between; align-items: center; width: 70%; }
    
    .status-dot { min-width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .dot-red { background-color: #ef4444; } .dot-blue { background-color: rgb(70,130,180); } .dot-gray { background-color: rgb(108,122,137); }
    
    .stock-name { font-size: 1.05rem; font-weight: 700; color: #ffffff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    
    .val-box { display: flex; flex-direction: column; align-items: flex-end; width: 33%; }
    .val-label { font-size: 0.7rem; font-weight: 600; color: rgb(108,122,137); margin-bottom: 2px; }
    .val-num { font-size: 1.05rem; font-weight: 800; }
    
    .text-red { color: #ef4444; } .text-blue { color: rgb(70,130,180); } .text-gray { color: rgb(108,122,137); } .text-white { color: #ffffff; }
    
    .card-body { background-color: #020617; padding: 20px; border-top: 1px solid #1e293b; border-radius: 0 0 12px 12px; }
    .metric-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
    .metric-box { display: flex; flex-direction: column; }
    .metric-label { font-size: 0.8rem; font-weight: 600; color: rgb(108,122,137); margin-bottom: 4px; }
    .metric-value { font-size: 1.1rem; font-weight: 700; color: #ffffff; }
    .metric-highlight { color: rgb(70,130,180); font-weight: 800; font-size: 1.15rem; }
    
    @media (max-width: 768px) {
        .card-header-flex { flex-direction: column; align-items: flex-start; gap: 6px; }
        .card-left { width: 100%; border-bottom: 1px dashed #1e293b; padding-bottom: 8px; margin-bottom: 4px; }
        .stock-name { font-size: 1.15rem; } 
        .card-right { width: 100%; justify-content: space-between; }
        .val-label { font-size: 0.65rem; }
        .val-num { font-size: 0.95rem; }
        
        .index-container { flex-wrap: wrap; padding: 10px; }
        .index-item { width: 48%; margin-bottom: 10px; }
        [data-testid="stMetricValue"] { font-size: 1.4rem !important; }
    }
    
    [data-testid="stMetricValue"] { color: #ffffff !important; font-size: 1.8rem !important; font-weight: 800 !important; }
    [data-testid="stMetricDelta"] { color: rgb(70,130,180) !important; }
    </style>
    """, unsafe_allow_html=True)

# --- [2] 거시 지표 및 데이터베이스 로드 ---
def safe_update(sheet, row, col_name, val, idmap):
    if col_name in idmap and idmap[col_name] > 0:
        sheet.update_cell(row, idmap[col_name], val)

@st.cache_data(ttl=120)
def get_market_indices():
    indices = {
        "KOSPI": ("-", "-", "text-gray"), "KOSDAQ": ("-", "-", "text-gray"),
        "NASDAQ": ("-", "-", "text-gray"), "S&P 500": ("-", "-", "text-gray"),
        "DOW": ("-", "-", "text-gray"), "VIX": ("-", "-", "text-gray"),
        "USD/KRW": ("-", "-", "text-gray")
    }
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res_main = requests.get("https://finance.naver.com/", headers=headers, timeout=3)
        soup_main = BeautifulSoup(res_main.text, 'html.parser')
        for code, cls in [("KOSPI", ".kospi_area"), ("KOSDAQ", ".kosdaq_area")]:
            box = soup_main.select_one(cls)
            if box:
                val, diff, rate = box.select_one(".num").text, box.select_one(".num2").text, box.select_one(".num3").text
                b_txt = box.select_one(".blind").text
                cl = "text-red" if "상승" in b_txt else "text-blue" if "하락" in b_txt else "text-gray"
                sign = "▲" if "상승" in b_txt else "▼" if "하락" in b_txt else ""
                indices[code] = (val, f"{sign}{diff} ({rate})", cl)
                
        for code, sym in [("NASDAQ", "NAS@IXIC"), ("S&P 500", "SPI@SPX"), ("DOW", "DJI@DJI"), ("VIX", "VIX@VIX")]:
            res_w = requests.get(f"https://finance.naver.com/world/sise.naver?symbol={sym}", headers=headers, timeout=3)
            s_w = BeautifulSoup(res_w.text, 'html.parser')
            em = s_w.select_one("p.no_today em")
            if em:
                val = em.text.strip()
                diff_area = s_w.select_one("p.no_exday")
                if diff_area:
                    ems = diff_area.find_all("em")
                    if len(ems) >= 2:
                        d_v, r_v = ems[0].text.strip(), ems[1].text.strip()
                        s_t = diff_area.select_one("span.blind").text if diff_area.select_one("span.blind") else ""
                        cl = "text-red" if "상승" in s_t else "text-blue" if "하락" in s_t else "text-gray"
                        sign = "▲" if "상승" in s_t else "▼" if "하락" in s_t else ""
                        indices[code] = (val, f"{sign}{d_v} ({r_v})", cl)

        res_ex = requests.get("https://finance.naver.com/marketindex/", headers=headers, timeout=3)
        s_ex = BeautifulSoup(res_ex.text, 'html.parser')
        ex_box = s_ex.select_one("#exchangeList > li.on > a.head.usd")
        if ex_box:
            val = ex_box.select_one(".value").text
            diff = ex_box.select_one(".change").text
            blind = ex_box.select_one(".blind").text
            cl = "text-red" if "상승" in blind else "text-blue" if "하락" in blind else "text-gray"
            sign = "▲" if "상승" in blind else "▼" if "하락" in blind else ""
            indices["USD/KRW"] = (val, f"{sign}{diff}", cl)
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
    with c_title: st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V45.0</div>', unsafe_allow_html=True)
    with c_filter:
        acc_types = ["함대 전체"] + list(df['계좌유형'].unique())
        selected_type = st.selectbox("계좌 필터", acc_types, label_visibility="collapsed")
        
    if indices:
        idx_html = '<div class="index-container">'
        for name in ["KOSPI", "KOSDAQ", "NASDAQ", "S&P 500"]:
            val, diff, cl = indices.get(name, ("-", "-", "text-gray"))
            idx_html += f'<div class="index-item"><span class="index-name">{name}</span><span class="index-val {cl}">{val}</span><span class="index-diff {cl}">{diff}</span></div>'
        idx_html += '</div>'
        st.markdown(idx_html, unsafe_allow_html=True)
        
        with st.expander("🌍 거시경제 및 보조 지표 (환율, VIX, DOW)"):
            macro_html = '<div class="index-container" style="margin-bottom: 0px; background: transparent; border: none; padding: 5px;">'
            for name in ["DOW", "VIX", "USD/KRW"]:
                val, diff, cl = indices.get(name, ("-", "-", "text-gray"))
                macro_html += f'<div class="index-item" style="width: 32%;"><span class="index-name">{name}</span><span class="index-val {cl}">{val}</span><span class="index-diff {cl}">{diff}</span></div>'
            macro_html += '</div>'
            st.markdown(macro_html, unsafe_allow_html=True)

    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()

    total_eval = display_df['평가금액'].sum() if '평가금액' in display_df else 0
    total_invest = display_df['매수금액'].sum() if '매수금액' in display_df else 0
    total_profit = display_df['평가손익'].sum() if '평가손익' in display_df else 0
    total_roi = (total_profit / total_invest * 100) if total_invest > 0 else 0
    total_cash = display_df[display_df['종목명'].astype(str).str.contains('현금|예수금', na=False)]['평가금액'].sum() if '평가금액' in display_df else 0
    
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
    
    # 🚨 [V45 업데이트] 전략 사령부: 평가금액 자동 합산 및 종목 삭제 기능 탑재
    with st.sidebar:
        st.header("🎯 전략 사령부")
        target_val = st.number_input("함대 목표 자산 (원)", value=830000000, step=10000000)
        t_rate = (total_eval/target_val*100) if target_val > 0 else 0
        st.markdown(f"<div style='color:rgb(70,130,180); font-size:1.2rem; font-weight:800; margin-top:-10px; margin-bottom:20px;'>목표 달성률: {t_rate:.1f}%</div>", unsafe_allow_html=True)
        st.divider()
        
        mode = st.radio("작전 모드", ["기존 종목 매매", "데이터 강제 수정", "신규 종목 추가", "종목 완전 삭제"])
        acc_opts = [f"{r['계좌유형']} [{r['계좌번호']}]" for _, r in full_df[['계좌유형', '계좌번호']].drop_duplicates().iterrows() if str(r['계좌번호']).strip() != '']
        sel_acc_str = st.selectbox("작전 계좌 선택", acc_opts) if acc_opts else ""
        sel_acc = sel_acc_str.split('[')[-1].replace(']', '').strip() if sel_acc_str else ""
        
        if "신규" not in mode:
            s_list = [s for s in full_df[full_df['계좌번호'].astype(str).str.strip() == sel_acc]['종목명'].dropna().tolist() if str(s).strip() != '']
            s_name = st.selectbox("작전 종목 선택", s_list if s_list else ["없음"])
            if "매매" in mode:
                action = st.radio("구분", ["매수", "매도"], horizontal=True)
        else:
            s_name = st.text_input("신규 종목명")
            s_code = st.text_input("종목코드 (숫자 6자리)")
            
        if "삭제" not in mode:
            qty = st.number_input("수량", min_value=0, value=None, step=1)
            price = st.number_input("현재가/단가", min_value=0, value=None, step=100)
        
        if st.button("명령 확정 (Sync)"):
            try:
                client = get_gspread_client() 
                ws = client.open_by_url("https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0").get_worksheet(0)
                idx_map = {str(col).strip(): i+1 for i, col in enumerate(full_df.columns)}
                
                if "삭제" not in mode:
                    qv = int(qty) if qty else 0
                    pv = int(price) if price else 0
                    total_amount = qv * pv # 평가금액/매수금액 자동 계산
                
                if "신규" in mode and s_name:
                    nr = len(full_df) + 2
                    safe_update(ws, nr, '계좌번호', sel_acc, idx_map)
                    at_series = full_df[full_df['계좌번호'].astype(str).str.strip() == sel_acc]['계좌유형']
                    at = at_series.iloc[0] if not at_series.empty else "수동"
                    safe_update(ws, nr, '계좌유형', at, idx_map)
                    safe_update(ws, nr, '종목명', s_name, idx_map)
                    safe_update(ws, nr, '잔고수량', qv, idx_map)
                    safe_update(ws, nr, '매수단가', pv, idx_map)
                    safe_update(ws, nr, '매수금액', total_amount, idx_map) # 금액 동시 기입
                    safe_update(ws, nr, '평가금액', total_amount, idx_map) # 금액 동시 기입
                    if s_code: safe_update(ws, nr, '종목코드', str(s_code).strip().zfill(6), idx_map)
                
                elif s_name != "없음":
                    t_indices = full_df[(full_df['계좌번호'].astype(str).str.strip() == sel_acc) & (full_df['종목명'] == s_name)].index
                    if len(t_indices) > 0:
                        ti = t_indices[0]
                        row_idx_to_update = ti + 2
                        
                        if "삭제" in mode:
                            ws.delete_rows(row_idx_to_update)
                            st.success(f"[{s_name}] 완전 삭제 완료.")
                        elif "수정" in mode:
                            safe_update(ws, row_idx_to_update, '잔고수량', qv, idx_map)
                            safe_update(ws, row_idx_to_update, '매수단가', pv, idx_map)
                            safe_update(ws, row_idx_to_update, '매수금액', total_amount, idx_map)
                            safe_update(ws, row_idx_to_update, '평가금액', total_amount, idx_map)
                        else: # 기존 매매
                            oq = pd.to_numeric(full_df.at[ti, '잔고수량'], errors='coerce')
                            oa = pd.to_numeric(full_df.at[ti, '매수단가'], errors='coerce')
                            oq = oq if not pd.isna(oq) else 0
                            oa = oa if not pd.isna(oa) else 0
                            
                            nq = oq + qv if action == "매수" else max(0, oq - qv)
                            na = ((oq * oa) + (qv * pv)) / nq if action == "매수" and nq > 0 else oa
                            n_total = int(nq * na)
                            
                            safe_update(ws, row_idx_to_update, '잔고수량', int(nq), idx_map)
                            safe_update(ws, row_idx_to_update, '매수단가', int(na), idx_map)
                            safe_update(ws, row_idx_to_update, '매수금액', n_total, idx_map)
                            if any(x in s_name for x in ["현금", "단기", "예수금", "TDF", "펀드"]):
                                safe_update(ws, row_idx_to_update, '평가금액', n_total, idx_map)
                
                st.cache_data.clear()
                st.success("명령 전송 완료.")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"작전 실패: {e}")

    # 리스트 렌더링
    if not display_df.empty:
        yield_col = '수익률2' if '수익률2' in display_df.columns else '수익률'
        if yield_col in display_df.columns:
            display_df = display_df.sort_values(by=yield_col, ascending=False)
            
        html_cards = ""
        for _, row in display_df.iterrows():
            is_special = any(x in str(row.get('종목명','')) for x in ["현금", "예수금", "단기", "연금", "TDF", "펀드"]) or (row.get('잔고수량',0) == 0 and row.get('매수금액',0) > 0)
            
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
                        <div class="card-header-flex">
                            <div class="card-left"><div class="status-dot dot-gray"></div><span class="stock-name">{row.get("종목명","")}</span></div>
                            <div class="card-right">
                                <div class="val-box"><span class="val-label">평가금액</span><span class="val-num text-gray">{row.get("평가금액",0):,.0f}</span></div>
                                <div class="val-box"><span class="val-label">당일비</span><span class="val-num text-gray">-</span></div>
                                <div class="val-box"><span class="val-label">수익률</span><span class="val-num text-gray">{y_str}</span></div>
                            </div>
                        </div>
                    </summary>
                    <div class="card-body"><div class="metric-grid">
                        <div class="metric-box"><div class="metric-label">평가 금액</div><div class="metric-value">{row.get('평가금액',0):,.0f}원</div></div>
                        <div class="metric-box"><div class="metric-label">투입 원금</div><div class="metric-value">{row.get('매수금액',0):,.0f}원</div></div>
                    </div></div>
                </details>"""
            else:
                cl = "text-red" if y_val > 0 else "text-blue" if y_val < 0 else "text-gray"
                dt = "dot-red" if y_val > 0 else "dot-blue" if y_val < 0 else "dot-gray"
                diff_color = "text-red" if diff > 0 else "text-blue" if diff < 0 else "text-gray"
                ds = f"<span class='{diff_color}'>{'▲' if diff>0 else '▼' if diff<0 else ''}{abs(diff):,.0f} ({rate:.2f}%)</span>" if diff != 0 else "-"
                txt, pos_cl = get_position_text(now_p, low52, high52)
                y_display = y_val * 100 if -1 < y_val < 1 else y_val
                
                html_cards += f"""
                <details class="premium-card">
                    <summary>
                        <div class="card-header-flex">
                            <div class="card-left"><div class="status-dot {dt}"></div><span class="stock-name">{row.get("종목명","")}</span></div>
                            <div class="card-right">
                                <div class="val-box"><span class="val-label">현재가</span><span class="val-num {cl}">{now_p:,.0f}</span></div>
                                <div class="val-box"><span class="val-label">당일비</span><span class="val-num">{ds}</span></div>
                                <div class="val-box"><span class="val-label">수익률</span><span class="val-num {cl}">{y_display:.2f}%</span></div>
                            </div>
                        </div>
                    </summary>
                    <div class="card-body">
                        <div class="pos-badge {pos_cl}">📍 시세위치: {txt}</div>
                        <div class="metric-grid">
                            <div class="metric-box"><div class="metric-label">평가 금액</div><div class="metric-highlight">{row.get('평가금액',0):,.0f}원</div></div>
                            <div class="metric-box"><div class="metric-label">매수 총액</div><div class="metric-value">{row.get('매수금액',0):,.0f}원</div></div>
                            <div class="metric-box"><div class="metric-label">누적 손익</div><div class="metric-value {cl}">{row.get('평가손익',0):,.0f}원</div></div>
                            <div class="metric-box"><div class="metric-label">평균 단가 / 수량</div><div class="metric-value">{row.get('매수단가',0):,.0f}원 <span class='text-gray'>({row.get('잔고수량',0):,.0f}주)</span></div></div>
                        </div>
                    </div>
                </details>"""
        st.markdown(html_cards, unsafe_allow_html=True)
except Exception as e: st.error(f"함대 기동 중지: {e}")
