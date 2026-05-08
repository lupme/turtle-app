import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- [1] 프리미엄 관제소 V13.0 (시각적 버그 완벽 차단) ---
st.set_page_config(page_title="거북이 함대 기동 본부 V13.0", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f1f5f9; }
    h1, h2, h3, p, span { font-family: 'Urbanist', 'Noto Sans KR', sans-serif !important; }
    
    .hq-title { font-size: 1.2rem; color: #4682B4; font-weight: 800; letter-spacing: 1px; margin-bottom: 0; padding-top: 10px; }
    
    /* 아코디언 디자인 (글자 깨짐 방어) */
    [data-testid="stExpander"] {
        background-color: #0f172a !important;
        border: 1px solid #1e293b !important;
        border-left: 4px solid #4682B4 !important;
        border-radius: 8px !important;
        margin-bottom: 12px !important;
    }
    
    /* 핵심: 스트림릿 기본 화살표 아이콘 완전 삭제 (글자 누수 원흉 제거) */
    [data-testid="stExpander"] summary svg { display: none !important; }
    [data-testid="stExpander"] summary::marker { display: none !important; }
    
    [data-testid="stExpander"] summary { padding: 1rem !important; list-style-type: none !important; }
    [data-testid="stExpander"] summary p { font-size: 1.1rem !important; font-weight: 700 !important; color: #f8fafc !important; margin: 0 !important; }
    [data-testid="stExpanderDetails"] { background-color: #020617 !important; padding: 1.5rem !important; border-top: 1px solid #1e293b !important; }

    .metric-box { margin-bottom: 10px; }
    .metric-label { color: #64748b; font-size: 0.8rem; font-weight: 600; margin-bottom: 2px; text-transform: uppercase; }
    .metric-value { color: #f8fafc; font-size: 1.15rem; font-weight: 700; }
    .metric-value-blue { color: #4682B4; font-size: 1.15rem; font-weight: 800; }

    .pos-badge { padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 0.75rem; margin-bottom: 10px; display: inline-block; }
    .pos-head { background-color: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid #ef4444; }
    .pos-shoulder { background-color: rgba(248, 113, 113, 0.15); color: #f87171; border: 1px solid #f87171; }
    .pos-waist { background-color: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid #f59e0b; }
    .pos-knee { background-color: rgba(52, 211, 153, 0.15); color: #34d399; border: 1px solid #34d399; }
    .pos-feet { background-color: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid #10b981; }
    .pos-unknown { background-color: rgba(71, 85, 105, 0.15); color: #94a3b8; border: 1px solid #64748b; }
    
    [data-testid="stMetricValue"] { color: #4682B4 !important; font-size: 1.6rem !important; font-weight: 800 !important; }
    </style>
    """, unsafe_allow_html=True)

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
    if high == 0 or low == 0 or high <= low or now == 0: return "측정 대기", "pos-unknown"
    pos = (now - low) / (high - low) * 100
    if pos >= 85: return "머리 (85%↑)", "pos-head"
    if pos >= 65: return "어깨 (과열권)", "pos-shoulder"
    if pos >= 35: return "허리 (평균가)", "pos-waist"
    if pos >= 15: return "무릎 (저점권)", "pos-knee"
    return "발바닥 (바닥권)", "pos-feet"

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
    display_df = display_df.sort_values(by='수익률_숫자', ascending=False)

    total_eval = display_df['평가금액'].sum()
    total_prev = (display_df['전일종가'] * display_df['잔고수량']).sum()
    daily_delta = total_eval - total_prev if total_prev > 0 else 0
    total_cash = display_df[display_df['종목명'].astype(str).str.contains('현금|예수금', na=False)]['평가금액'].sum()
    
    kc1, kc2, kc3, kc4 = st.columns(4)
    kc1.metric("총 함대 자산", f"{total_eval:,.0f}원")
    if total_prev > 0: kc2.metric("전일 대비 증감", f"{daily_delta:,.0f}원", delta=f"{daily_delta:,.0f}")
    else: kc2.metric("전일 대비 증감", "지표 없음", delta=None)
    kc3.metric("기동 대기 예수금", f"{total_cash:,.0f}원")
    
    target_input = 830000000

    if display_df.empty:
        st.info("기동 대기 중인 자산이 없습니다.")
    else:
        for _, row in display_df.iterrows():
            is_cash = "현금" in str(row['종목명']) or "예수금" in str(row['종목명'])
            
            yield_val = row.get('수익률_숫자', 0)
            now_price = row['현재가2'] if row['현재가2'] != 0 else row['현재가1']
            prev_price = row['전일종가']
            
            daily_diff = now_price - prev_price if prev_price > 0 else 0
            diff_str = f"(▲{daily_diff:,.0f})" if daily_diff > 0 else f"(▼{abs(daily_diff):,.0f})" if daily_diff < 0 else ""
            
            # 화살표 버그를 막기 위해 구조를 가장 단순화
            if is_cash:
                title = f"💵 {row['종목명']} │ {row['평가금액']:,.0f}원"
            else:
                mark = "🔴" if yield_val > 0 else "🔵" if yield_val < 0 else "🔘"
                title = f"📂 {mark} {row['종목명']} │ {now_price:,.0f}원 {diff_str} │ {yield_val:.2f}%"
            
            with st.expander(title):
                if not is_cash:
                    pos_text, pos_class = get_position_text(now_price, row['52주최저'], row['52주최고'])
                    st.markdown(f'<div class="pos-badge {pos_class}">📍 시세위치: {pos_text}</div>', unsafe_allow_html=True)
                
                html_content = f"""
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                    <div class="metric-box"><div class="metric-label">평가 금액</div><div class="metric-value-blue">{row['평가금액']:,.0f}원</div></div>
                    <div class="metric-box"><div class="metric-label">현재 시세</div><div class="metric-value">{now_price:,.0f}원</div></div>
                    <div class="metric-box"><div class="metric-label">투입 원금</div><div class="metric-value">{row['매수금액']:,.0f}원</div></div>
                    <div class="metric-box"><div class="metric-label">평균 단가</div><div class="metric-value">{row['매수단가']:,.0f}원</div></div>
                    <div class="metric-box"><div class="metric-label">보유 수량</div><div class="metric-value">{row['잔고수량']:,.0f}주</div></div>
                    <div class="metric-box"><div class="metric-label">52주 최고가</div><div class="metric-value">{row['52주최고']:,.0f}원</div></div>
                </div>
                """
                st.markdown(html_content, unsafe_allow_html=True)

    # --- [4] 사이드바 로직 (2단 장전 방식 적용) ---
    with st.sidebar:
        st.header("🎯 함대 전략 설정")
        target_val = st.number_input("함대 목표 자산 (원)", value=830000000, step=10000000)
        kc4.metric("목표 달성률", f"{(total_eval/target_val*100):.1f}%")
        
        st.divider()
        st.header("🛠️ 작전 명령")
        mode = st.radio("전술 모드", ["기존 종목 매매", "데이터 강제 수정", "신규 종목 추가"])
        
        acc_opts = [f"{r['계좌유형']} [{r['계좌번호']}]" for _, r in full_df[['계좌유형', '계좌번호']].drop_duplicates().iterrows() if str(r['계좌번호']).strip() != '']
        sel_acc_str = st.selectbox("작전 계좌 선택", acc_opts) if acc_opts else ""
        sel_acc = sel_acc_str.split('[')[-1].replace(']', '').strip() if sel_acc_str else ""
        
        if "신규" not in mode:
            s_list = full_df[(full_df['계좌번호'].astype(str).str.strip() == sel_acc) & (~full_df['종목명'].astype(str).str.contains('합계|총계', na=False))]['종목명'].dropna().tolist()
            s_list = [s for s in s_list if str(s).strip() != '']
            s_name = st.selectbox("종목 선택", s_list if s_list else ["없음"])
            action = st.radio("구분", ["매수", "매도"], horizontal=True) if "매매" in mode else None
        else:
            s_name = st.text_input("신규 종목명")
            s_code = st.text_input("종목번호(6자리 숫자)")
            st.caption("💡 수동 입력 종목(TDF 등)은 종목번호를 비워두십시오.")
            
        qty = st.number_input("수량", min_value=0, step=1)
        price = st.number_input("현재가/단가", min_value=0, step=100)
        
        if st.button("명령 하달 (Sync)"):
            idx_map = {col: i+1 for i, col in enumerate(full_df.columns)}
            if "수정" in mode and s_name != "없음":
                t_idx = full_df[(full_df['계좌번호'].astype(str).str.strip() == sel_acc) & (full_df['종목명'] == s_name)].index[0]
                if '잔고수량' in idx_map: sheet.update_cell(t_idx+2, idx_map['잔고수량'], int(qty))
                if '매수단가' in idx_map: sheet.update_cell(t_idx+2, idx_map['매수단가'], int(price))
            elif "매매" in mode and s_name != "없음":
                t_idx = full_df[(full_df['계좌번호'].astype(str).str.strip() == sel_acc) & (full_df['종목명'] == s_name)].index[0]
                old_qty, old_avg = full_df.at[t_idx, '잔고수량'], full_df.at[t_idx, '매수단가']
                if action == "매수":
                    new_qty = old_qty + qty
                    new_avg = ((old_qty * old_avg) + (qty * price)) / new_qty if new_qty > 0 else 0
                else:
                    new_qty = max(0, old_qty - qty)
                    new_avg = old_avg
                if '잔고수량' in idx_map: sheet.update_cell(t_idx+2, idx_map['잔고수량'], int(new_qty))
                if '매수단가' in idx_map: sheet.update_cell(t_idx+2, idx_map['매수단가'], int(new_avg))
            elif "신규" in mode:
                if s_name:
                    new_row = len(full_df) + 2
                    if '계좌번호' in idx_map: sheet.update_cell(new_row, idx_map['계좌번호'], sel_acc)
                    acc_type = full_df[full_df['계좌번호'].astype(str).str.strip() == sel_acc]['계좌유형'].iloc[0] if not full_df[full_df['계좌번호'].astype(str).str.strip() == sel_acc].empty else "수동"
                    if '계좌유형' in idx_map: sheet.update_cell(new_row, idx_map['계좌유형'], acc_type)
                    if '종목명' in idx_map: sheet.update_cell(new_row, idx_map['종목명'], s_name)
                    
                    # 1단 장전: 사용자가 입력한 숫자를 먼저 박아서 0원 사태 방어
                    if '잔고수량' in idx_map: sheet.update_cell(new_row, idx_map['잔고수량'], int(qty))
                    if '매수단가' in idx_map: sheet.update_cell(new_row, idx_map['매수단가'], int(price))
                    if '현재가2' in idx_map: sheet.update_cell(new_row, idx_map['현재가2'], int(price))
                    if '현재가1' in idx_map: sheet.update_cell(new_row, idx_map['현재가1'], int(price))
                    
                    # 2단 장전: 종목코드가 있다면 그 위에 수식을 덮어씀 (다음 로딩부터 구글 서버가 계산)
                    if s_code:
                        clean_code = str(s_code).strip().zfill(6)
                        if '종목코드' in idx_map: sheet.update_cell(new_row, idx_map['종목코드'], clean_code)
                        if '현재가2' in idx_map: sheet.update_cell(new_row, idx_map['현재가2'], f'=GOOGLEFINANCE("KRX:{clean_code}", "price")')
                        if '전일종가' in idx_map: sheet.update_cell(new_row, idx_map['전일종가'], f'=GOOGLEFINANCE("KRX:{clean_code}", "price") - GOOGLEFINANCE("KRX:{clean_code}", "change")')
                        if '52주최고' in idx_map: sheet.update_cell(new_row, idx_map['52주최고'], f'=GOOGLEFINANCE("KRX:{clean_code}", "high52")')
                        if '52주최저' in idx_map: sheet.update_cell(new_row, idx_map['52주최저'], f'=GOOGLEFINANCE("KRX:{clean_code}", "low52")')
            st.cache_data.clear()
            st.rerun()

except Exception as e:
    st.error(f"함대 기동 중지: {e}")
