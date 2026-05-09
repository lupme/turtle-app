import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup

# --- [1] 시스템 설정 및 CSS ---
st.set_page_config(page_title="거북이 함대 기동 본부 V26", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f1f5f9; }
    h1, h2, h3, p, span, div { font-family: 'Urbanist', 'Noto Sans KR', sans-serif; }
    .hq-title { font-size: 1.4rem; color: #4682B4; font-weight: 800; letter-spacing: 1px; padding-top: 10px; margin-bottom: 20px; }
    
    .index-container { display: flex; justify-content: space-between; background: #0f172a; padding: 15px 20px; border-radius: 12px; border: 1px solid #1e293b; margin-bottom: 20px; }
    .index-item { display: flex; flex-direction: column; align-items: center; width: 24%; }
    .index-name { font-size: 0.85rem; color: #6C7A89; font-weight: 700; margin-bottom: 4px; }
    .index-val { font-size: 1.15rem; font-weight: 800; color: #f8fafc; }
    .index-diff { font-size: 0.85rem; font-weight: 600; }
    
    .list-header { color: #6C7A89; font-size: 0.85rem; font-weight: 600; padding: 0 20px 10px 20px; border-bottom: 1px solid #1e293b; margin-bottom: 10px; }
    .row-layout { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: 10px; }
    .col-name { width: 28%; display: flex; align-items: center; gap: 8px; overflow: hidden; }
    .col-price { width: 24%; text-align: right; font-size: 1.05rem; font-weight: 800; color: #f8fafc; }
    .col-diff { width: 28%; text-align: right; font-size: 0.9rem; font-weight: 700; }
    .col-yield { width: 20%; text-align: right; font-size: 1.05rem; font-weight: 800; }
    
    details.premium-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 12px; margin-bottom: 10px; transition: all 0.2s; }
    details.premium-card:hover { border-color: #4682B4; }
    details.premium-card summary { display: flex; align-items: center; padding: 16px 20px; cursor: pointer; list-style: none; }
    details.premium-card summary::-webkit-details-marker { display: none; }
    
    .status-dot { min-width: 8px; height: 8px; border-radius: 50%; }
    .dot-red { background-color: #ef4444; box-shadow: 0 0 8px rgba(239, 68, 68, 0.6); }
    .dot-blue { background-color: #3b82f6; box-shadow: 0 0 8px rgba(59, 130, 246, 0.6); }
    .dot-gray { background-color: #6C7A89; }
    .stock-name { font-size: 1.05rem; font-weight: 700; color: #f8fafc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .text-red { color: #ef4444; } .text-blue { color: #3b82f6; } .text-gray { color: #6C7A89; }
    
    .card-body { background-color: #020617; padding: 20px; border-top: 1px solid #1e293b; border-radius: 0 0 12px 12px; }
    .metric-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
    .metric-box { display: flex; flex-direction: column; }
    .metric-label { font-size: 0.8rem; font-weight: 600; color: #6C7A89; margin-bottom: 4px; text-transform: uppercase; }
    .metric-value { font-size: 1.1rem; font-weight: 700; color: #f1f5f9; }
    .metric-highlight { color: #4682B4; font-weight: 800; font-size: 1.1rem; }
    
    .pos-badge { padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.85rem; margin-bottom: 16px; display: inline-block; border: 1px solid; }
    .pos-head { background-color: rgba(239, 68, 68, 0.1); color: #ef4444; border-color: rgba(239, 68, 68, 0.3); }
    .pos-waist { background-color: rgba(245, 158, 11, 0.1); color: #f59e0b; border-color: rgba(245, 158, 11, 0.3); }
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

def safe_update(sheet, row, col_name, val, idmap):
    """에러 방지용 안전 주입 엔진"""
    if col_name in idmap:
        sheet.update_cell(row, idmap[col_name], val)

@st.cache_data(ttl=120)
def get_market_indices():
    indices = {"KOSPI": ("-", "-", "text-gray"), "KOSDAQ": ("-", "-", "text-gray"), "DOW": ("-", "-", "text-gray"), "NASDAQ": ("-", "-", "text-gray")}
    try:
        url_main = "https://finance.naver.com/"
        res_main = requests.get(url_main, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        soup_main = BeautifulSoup(res_main.text, 'html.parser')
        
        for code, cls in [("KOSPI", ".kospi_area"), ("KOSDAQ", ".kosdaq_area")]:
            box = soup_main.select_one(cls)
            if box:
                val, diff, rate = box.select_one(".num").text, box.select_one(".num2").text, box.select_one(".num3").text
                b_txt = box.select_one(".blind").text
                cl = "text-red" if "상승" in b_txt else "text-blue" if "하락" in b_txt else "text-gray"
                sign = "▲" if "상승" in b_txt else "▼" if "하락" in b_txt else ""
                indices[code] = (val, f"{sign}{diff} ({rate})", cl)
                
        for code, sym in [("DOW", "DJI@DJI"), ("NASDAQ", "NAS@IXIC")]:
            res_w = requests.get(f"https://finance.naver.com/world/sise.naver?symbol={sym}", headers={'User-Agent': 'Mozilla/5.0'}, timeout=2)
            s_w = BeautifulSoup(res_w.text, 'html.parser')
            em = s_w.select_one("p.no_today em")
            if em:
                val = em.text.strip()
                diff_area = s_w.select_one("p.no_exday")
                if diff_area:
                    ems = diff_area.find_all("em")
                    if len(ems) >= 2:
                        d_v, r_v = ems[0].text.strip(), ems[1].text.strip()
                        s_t = diff_area.select_one("span.blind").text
                        cl = "text-red" if "상승" in s_t else "text-blue" if "하락" in s_t else "text-gray"
                        sign = "▲" if "상승" in s_t else "▼" if "하락" in s_t else ""
                        indices[code] = (val, f"{sign}{d_v} ({r_v})", cl)
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
    full_df.columns = full_df.columns.str.strip()
    
    essential_cols = ['계좌번호', '계좌유형', '종목명', '종목코드', '잔고수량', '매수단가', '현재가2', '수익률2', '매수금액', '평가금액', '평가손익', '전일종가', '52주최고', '52주최저']
    for col in essential_cols:
        if col not in full_df.columns: full_df[col] = 0
            
    df = full_df.copy()
    for col in essential_cols:
        if col not in ['계좌번호', '계좌유형', '종목명', '종목코드']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', '').str.replace('%', ''), errors='coerce').fillna(0)

    # 쓰레기 데이터 정리
    invalid_keywords = '합계|총계|총액|평가금|총자산'
    df = df[df['종목명'].astype(str).str.strip() != '']
    df = df[~df['종목명'].astype(str).str.contains(invalid_keywords, na=False)]
    
    # [V26.0 IRP 무결성 필터] 수량이 없어도 평가금액이 있거나 이름이 특수자산이면 합산
    is_special_asset = df['종목명'].astype(str).str.contains('현금|예수금|단기|연금|펀드', na=False)
    has_qty = df['잔고수량'] > 0
    has_value = df['평가금액'] > 0
    df = df[is_special_asset | has_qty | has_value]
    
    return sheet, df, full_df

def get_position_text(now, low, high):
    if high == 0 or low == 0 or high <= low or now == 0: return "데이터 수집중", "pos-unknown"
    pos = (now - low) / (high - low) * 100
    if pos >= 85: return f"머리 (고점 {pos:.0f}%)", "pos-head"
    if pos >= 35: return f"허리 (평균 시세 {pos:.0f}%)", "pos-waist"
    return f"발바닥 (바닥권 {pos:.0f}%)", "pos-feet"

# --- [3] 관제 화면 기동 ---
try:
    sheet, df, full_df = load_data()
    indices = get_market_indices()
    
    c_title, c_space, c_filter = st.columns([4, 1, 3])
    with c_title: st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V26</div>', unsafe_allow_html=True)
    with c_filter:
        acc_types = ["함대 전체"] + list(df['계좌유형'].unique())
        selected_type = st.selectbox("필터", acc_types, label_visibility="collapsed")
        
    if indices:
        idx_html = '<div class="index-container">'
        for name in ["KOSPI", "KOSDAQ", "DOW", "NASDAQ"]:
            val, diff, cl = indices.get(name, ("-", "-", "text-gray"))
            idx_html += f'<div class="index-item"><span class="index-name">{name}</span><span class="index-val {cl}">{val}</span><span class="index-diff {cl}">{diff}</span></div>'
        idx_html += '</div>'
        st.markdown(idx_html, unsafe_allow_html=True)

    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()

    total_eval = display_df['평가금액'].sum()
    total_cash = display_df[display_df['종목명'].astype(str).str.contains('현금|예수금', na=False)]['평가금액'].sum()
    
    daily_delta = 0
    for _, row in display_df.iterrows():
        # 현금성 자산이 아닌 '주식'만 전일비 변동 계산
        if not any(x in str(row['종목명']) for x in ["현금", "예수금", "단기", "연금"]):
            now_p, prev_p = row['현재가2'], row['전일종가']
            if prev_p > 0 and now_p > 0: daily_delta += (now_p - prev_p) * row['잔고수량']
    
    kc1, kc2, kc3 = st.columns(3)
    kc1.metric("총 함대 자산", f"{total_eval:,.0f}원")
    kc2.metric("전일 대비 증감", f"{daily_delta:,.0f}원", delta=f"{daily_delta:,.0f}")
    kc3.metric("기동 대기 예수금", f"{total_cash:,.0f}원")
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        target_val = st.number_input("함대 목표 자산 (원)", value=830000000, step=10000000)
        t_rate = (total_eval/target_val*100) if target_val > 0 else 0
        st.markdown(f"<div style='color:#4682B4; font-size:1.2rem; font-weight:800; margin-top:-10px; margin-bottom:20px;'>목표 달성률: {t_rate:.1f}%</div>", unsafe_allow_html=True)
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
            
        qty = st.number_input("수량", min_value=0, value=None, step=1)
        price = st.number_input("현재가/단가", min_value=0, value=None, step=100)
        
        if st.button("명령 확정 (Sync)"):
            client = get_gspread_client() 
            sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0").get_worksheet(0)
            idx_map = {col.strip(): i+1 for i, col in enumerate(full_df.columns)}
            qv, pv = (qty if qty else 0), (price if price else 0)
            
            if "신규" in mode and s_name:
                nr = len(full_df) + 2
                safe_update(sheet, nr, '계좌번호', sel_acc, idx_map)
                at = full_df[full_df['계좌번호'].astype(str).str.strip() == sel_acc]['계좌유형'].iloc[0] if not full_df[full_df['계좌번호'].astype(str).str.strip() == sel_acc].empty else "수동"
                safe_update(sheet, nr, '계좌유형', at, idx_map)
                safe_update(sheet, nr, '종목명', s_name, idx_map)
                safe_update(sheet, nr, '잔고수량', int(qv), idx_map)
                safe_update(sheet, nr, '매수단가', int(pv), idx_map)
                
                # 수식 주입 로직 에러 방어 적용
                q_l, b_l = col_letter(idx_map.get('잔고수량', 0)), col_letter(idx_map.get('매수단가', 0))
                c_l = col_letter(idx_map.get('현재가2', idx_map.get('현재가1', 0)))
                ba_l = col_letter(idx_map.get('매수금액', 0))
                ea_l = col_letter(idx_map.get('평가금액', 0))
                p_l = col_letter(idx_map.get('평가손익', 0))
                y_idx = idx_map.get('수익률2', 0)
                y_l = col_letter(y_idx) if y_idx else ""

                if ba_l and q_l and b_l: sheet.update_cell(nr, idx_map['매수금액'], f"={q_l}{nr}*{b_l}{nr}")
                if ea_l and q_l and c_l: sheet.update_cell(nr, idx_map['평가금액'], f"={q_l}{nr}*{c_l}{nr}")
                if p_l and ea_l and ba_l: sheet.update_cell(nr, idx_map['평가손익'], f"={ea_l}{nr}-{ba_l}{nr}")
                if y_l and p_l and ba_l: sheet.update_cell(nr, y_idx, f"=IFERROR({p_l}{nr}/{ba_l}{nr}, 0)")
                
                if s_code:
                    c = str(s_code).strip().zfill(6)
                    safe_update(sheet, nr, '종목코드', c, idx_map)
                    safe_update(sheet, nr, '현재가2', f'=GOOGLEFINANCE("KRX:{c}", "price")', idx_map)
                    safe_update(sheet, nr, '전일종가', f'=GOOGLEFINANCE("KRX:{c}", "price") - GOOGLEFINANCE("KRX:{c}", "change")', idx_map)
                    safe_update(sheet, nr, '52주최고', f'=GOOGLEFINANCE("KRX:{c}", "high52")', idx_map)
                    safe_update(sheet, nr, '52주최저', f'=GOOGLEFINANCE("KRX:{c}", "low52")', idx_map)
                else: 
                    safe_update(sheet, nr, '현재가2', int(pv), idx_map)
            
            elif s_name != "없음":
                t_indices = full_df[(full_df['계좌번호'].astype(str).str.strip() == sel_acc) & (full_df['종목명'] == s_name)].index
                if len(t_indices) > 0:
                    ti = t_indices[0]
                    if "수정" in mode:
                        safe_update(sheet, ti+2, '잔고수량', int(qv), idx_map)
                        safe_update(sheet, ti+2, '매수단가', int(pv), idx_map)
                    else:
                        oq, oa = full_df.at[ti, '잔고수량'], full_df.at[ti, '매수단가']
                        nq = oq + qv if action == "매수" else max(0, oq - qv)
                        na = ((oq * oa) + (qv * pv)) / nq if action == "매수" and nq > 0 else oa
                        safe_update(sheet, ti+2, '잔고수량', int(nq), idx_map)
                        safe_update(sheet, ti+2, '매수단가', int(na), idx_map)
            
            st.cache_data.clear()
            st.rerun()

    if not display_df.empty:
        st.markdown('<div class="list-header"><div class="row-layout"><div class="col-name">종목명</div><div class="col-price">현재가</div><div class="col-diff">당일비(%)</div><div class="col-yield">누적수익률</div></div></div>', unsafe_allow_html=True)
        display_df = display_df.sort_values(by='수익률2', ascending=False)
        html_cards = ""
        for _, row in display_df.iterrows():
            is_special = any(x in str(row['종목명']) for x in ["현금", "예수금", "단기", "연금"]) or (row['잔고수량'] == 0 and row['평가금액'] > 0)
            
            if is_special:
                html_cards += f'<details class="premium-card"><summary><div class="row-layout"><div class="col-name"><div class="status-dot dot-gray"></div><span class="stock-name text-gray">{row["종목명"]}</span></div><div class="col-price">{row["평가금액"]:,.0f}원</div><div class="col-diff text-gray">-</div><div class="col-yield text-gray">-</div></div></summary></details>'
            else:
                yield_v, now_p, prev_p = row['수익률2'], row['현재가2'], row['전일종가']
                diff = now_p - prev_p if prev_p > 0 else 0
                rate = (diff / prev_p * 100) if prev_p > 0 else 0
                cl = "text-red" if diff > 0 else "text-blue" if diff < 0 else "text-gray"
                dt = "dot-red" if diff > 0 else "dot-blue" if diff < 0 else "dot-gray"
                ds = f"{'▲' if diff>0 else '▼' if diff<0 else ''}{abs(diff):,.0f} ({rate:.2f}%)" if diff != 0 else "-"
                txt, pos_cl = get_position_text(now_p, row['52주최저'], row['52주최고'])
                
                html_cards += f"""
                <details class="premium-card">
                    <summary><div class="row-layout"><div class="col-name"><div class="status-dot {dt}"></div><span class="stock-name">{row["종목명"]}</span></div><div class="col-price {cl}">{now_p:,.0f}</div><div class="col-diff {cl}">{ds}</div><div class="col-yield {cl}">{yield_v*100:.2f}%</div></div></summary>
                    <div class="card-body"><div class="pos-badge {pos_cl}">📍 시세위치: {txt}</div><div class="metric-grid">
                        <div class="metric-box"><div class="metric-label">평가 금액</div><div class="metric-highlight">{row['평가금액']:,.0f}원</div></div>
                        <div class="metric-box"><div class="metric-label">매수 총액</div><div class="metric-value">{row['매수금액']:,.0f}원</div></div>
                        <div class="metric-box"><div class="metric-label">보유 수량</div><div class="metric-value">{row['잔고수량']:,.0f}주</div></div>
                        <div class="metric-box"><div class="metric-label">평균 단가</div><div class="metric-value">{row['매수단가']:,.0f}원</div></div>
                        <div class="metric-box"><div class="metric-label">52주 최고</div><div class="metric-value">{row['52주최고']:,.0f}원</div></div>
                        <div class="metric-box"><div class="metric-label">52주 최저</div><div class="metric-value">{row['52주최저']:,.0f}원</div></div>
                    </div></div>
                </details>"""
        st.markdown(html_cards, unsafe_allow_html=True)
except Exception as e: st.error(f"함대 기동 중지: {e}")
