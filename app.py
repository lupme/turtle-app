import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup

# --- [1] 프리미엄 관제소 V17.0 (계좌 연동 및 수식 주입 강화) ---
st.set_page_config(page_title="거북이 함대 기동 본부 V17.0", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f1f5f9; }
    h1, h2, h3, p, span, div { font-family: 'Urbanist', 'Noto Sans KR', sans-serif; }
    .hq-title { font-size: 1.2rem; color: #4682B4; font-weight: 800; letter-spacing: 1px; padding-top: 10px; }
    
    [data-testid="stExpander"] {
        background-color: #0f172a !important;
        border: 1px solid #1e293b !important;
        border-left: 4px solid #4682B4 !important;
        border-radius: 8px !important; margin-bottom: 12px !important;
    }
    [data-testid="stExpander"] summary { padding: 1rem !important; list-style-type: none !important; }
    [data-testid="stExpander"] summary p { font-size: 1.1rem !important; font-weight: 700 !important; color: #f8fafc !important; }
    [data-testid="stExpanderDetails"] { background-color: #020617 !important; padding: 1.5rem !important; border-top: 1px solid #1e293b !important; }

    .metric-box { margin-bottom: 15px; }
    .metric-label { color: #64748b; font-size: 0.8rem; font-weight: 600; margin-bottom: 4px; text-transform: uppercase; }
    .metric-value { color: #f8fafc; font-size: 1.15rem; font-weight: 700; }
    .metric-value-blue { color: #4682B4; font-size: 1.15rem; font-weight: 800; }
    .metric-value-gray { color: #94a3b8; font-size: 1rem; font-weight: 500; }

    .pos-badge { padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.85rem; margin-bottom: 15px; display: inline-block; }
    .pos-head { background-color: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; }
    .pos-shoulder { background-color: rgba(248, 113, 113, 0.2); color: #f87171; border: 1px solid #f87171; }
    .pos-waist { background-color: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid #f59e0b; }
    .pos-knee { background-color: rgba(52, 211, 153, 0.2); color: #34d399; border: 1px solid #34d399; }
    .pos-feet { background-color: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981; }
    </style>
    """, unsafe_allow_html=True)

# 시트 열 번호를 알파벳(A, B, C...)으로 변환
def col_letter(n):
    string = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string

def fetch_emergency_price(ticker):
    if pd.isna(ticker) or str(ticker).strip() in ["", "0"]: return 0
    clean_ticker = str(int(float(ticker))).zfill(6) if str(ticker).replace('.','').isdigit() else str(ticker).strip()
    try:
        url = f"https://finance.naver.com/item/main.naver?code={clean_ticker}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=2)
        soup = BeautifulSoup(res.text, 'html.parser')
        price_tag = soup.select_one(".no_today .blind")
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
    sheet_url = "https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0"
    doc = client.open_by_url(sheet_url)
    sheet = doc.get_worksheet(0)
    full_df = pd.DataFrame(sheet.get_all_records())
    
    essential_cols = ['계좌번호', '계좌유형', '종목명', '종목코드', '잔고수량', '매수단가', '현재가2', '현재가1', '수익률', '수익률1', '평가금액', '매수금액', '평가손익', '전일종가', '52주최고', '52주최저']
    df = full_df[[c for c in essential_cols if c in full_df.columns]].copy()
    
    for col in essential_cols:
        if col not in df.columns: df[col] = 0
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
    with c_title: st.markdown('<div class="hq-title">🐢 TURTLE COMMAND HQ V17</div>', unsafe_allow_html=True)
    with c_filter:
        acc_types = ["함대 전체"] + list(df['계좌유형'].unique())
        selected_type = st.selectbox("필터", acc_types, label_visibility="collapsed")
    
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
    
    kc1, kc2, kc3 = st.columns(3)
    kc1.metric("총 함대 자산", f"{total_eval:,.0f}원")
    kc2.metric("기동 대기 예수금", f"{total_cash:,.0f}원")
    
    with st.sidebar:
        st.header("🎯 전략 사령부")
        target_val = st.number_input("함대 목표 자산 (원)", value=830000000, step=10000000)
        kc3.metric("목표 달성률", f"{(total_eval/target_val*100):.1f}%")
        st.divider()
        mode = st.radio("작전 모드", ["기존 종목 매매", "데이터 강제 수정", "신규 종목 추가"])
        
        # [실시간 연동을 위해 폼을 제거]
        acc_opts = [f"{r['계좌유형']} [{r['계좌번호']}]" for _, r in full_df[['계좌유형', '계좌번호']].drop_duplicates().iterrows() if str(r['계좌번호']).strip() != '']
        sel_acc_str = st.selectbox("작전 계좌 선택", acc_opts)
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
                
                # 수식 자동 주입 엔진 가동
                q_l, b_l, c_l = col_letter(idx_map['잔고수량']), col_letter(idx_map['매수단가']), col_letter(idx_map.get('현재가2', idx_map['현재가1']))
                ba_l, ea_l, p_l = col_letter(idx_map['매수금액']), col_letter(idx_map['평가금액']), col_letter(idx_map['평가손익'])
                y_idx = idx_map.get('수익률', idx_map.get('수익률1'))
                y_l = col_letter(y_idx) if y_idx else None

                sheet.update_cell(nr, idx_map['매수금액'], f"={q_l}{nr}*{b_l}{nr}")
                sheet.update_cell(nr, idx_map['평가금액'], f"={q_l}{nr}*{c_l}{nr}")
                sheet.update_cell(nr, idx_map['평가손익'], f"={ea_l}{nr}-{ba_l}{nr}")
                if y_l: sheet.update_cell(nr, y_idx, f"=IFERROR({p_l}{nr}/{ba_l}{nr}, 0)")
                
                if s_code:
                    c = str(s_code).strip().zfill(6)
                    sheet.update_cell(nr, idx_map['종목코드'], c)
                    for k in ['현재가2', '현재가1']:
                        if k in idx_map: sheet.update_cell(nr, idx_map[k], f'=GOOGLEFINANCE("KRX:{c}", "price")')
                else: # 수동 자산일 경우 입력단가를 시세로 고정
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

    if not final_df.empty:
        for _, row in final_df.iterrows():
            is_c = any(x in str(row['종목명']) for x in ["현금", "예수금"])
            t = f"💵 {row['종목명']} │ {row['보정평가액']:,.0f}원" if is_c else f"📂 {row['종목명']} │ {row['보정가']:,.0f}원 │ {row['보정수익률']:.2f}%"
            with st.expander(t):
                if not is_c:
                    txt, cl = get_position_text(row['보정가'], row['52주최저'], row['52주최고'])
                    st.markdown(f'<div class="pos-badge {cl}">시세위치: {txt}</div>', unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"<div class='metric-label'>평가 금액</div><div class='metric-value-blue'>{row['보정평가액']:,.0f}원</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='metric-label'>투입 원금</div><div class='metric-value'>{row['매수금액']:,.0f}원</div>", unsafe_allow_html=True)
                with c2:
                    st.markdown(f"<div class='metric-label'>평균 단가</div><div class='metric-value'>{row['매수단가']:,.0f}원</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='metric-label'>52주 최고/최저</div><div class='metric-value'>{row['52주최고']:,.0f} / {row['52주최저']:,.0f}</div>", unsafe_allow_html=True)

except Exception as e: st.error(f"함대 기동 중지: {e}")
