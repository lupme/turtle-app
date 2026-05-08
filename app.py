import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- [1] 모바일 극강 최적화 UI (V8.3 - 현금 연동) ---
st.set_page_config(page_title="거북이 함대 기동 본부 V8.3", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f1f5f9; }
    h1, h2, h3 { font-family: 'Urbanist', 'Noto Sans KR', sans-serif !important; }
    .streamlit-expanderHeader { 
        background-color: #0f172a !important; 
        border-radius: 8px !important; 
        border: 1px solid #1e293b !important;
        padding: 10px 15px !important;
        font-size: 1.05rem !important;
        font-weight: 700 !important;
        color: #f8fafc !important;
    }
    [data-testid="stExpanderDetails"] { background-color: #020617; border-radius: 0 0 8px 8px; border: 1px solid #1e293b; border-top: none; padding: 15px !important; }
    [data-testid="stMetricValue"] { color: #4682B4 !important; font-size: 1.6rem !important; font-weight: 800 !important; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def get_gspread_client():
    key_info = json.loads(st.secrets["google_credentials"])
    if "private_key" in key_info:
        key_info["private_key"] = key_info["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(key_info, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
    return gspread.authorize(creds)

@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    sheet_url = "https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0"
    doc = client.open_by_url(sheet_url)
    sheet = doc.get_worksheet(0)
    full_df = pd.DataFrame(sheet.get_all_records())
    
    essential_cols = ['계좌번호', '계좌유형', '종목명', '잔고수량', '매수단가', '현재가2', '현재가1', '수익률', '수익률1', '평가금액', '매수금액', '평가손익', '전일종가']
    df = full_df[[c for c in essential_cols if c in full_df.columns]].copy()
    
    for col in essential_cols:
        if col not in df.columns:
            df[col] = 0
        elif col not in ['계좌번호', '계좌유형', '종목명', '수익률', '수익률1']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', ''), errors='coerce').fillna(0)
            
    target_yield = '수익률' if '수익률' in full_df.columns else '수익률1' if '수익률1' in full_df.columns else None
    df['수익률_숫자'] = pd.to_numeric(df[target_yield].astype(str).str.replace('%', '').str.replace(',', ''), errors='coerce').fillna(0) if target_yield else 0.0
        
    return sheet, df, full_df

# --- [2] 관제 화면 기동 ---
try:
    sheet, df, full_df = load_data()
    
    st.markdown('<div style="color:#4682B4; font-weight:800; font-size:1.2rem; margin-bottom:10px; letter-spacing:1px;">🐢 TURTLE HQ V8.3</div>', unsafe_allow_html=True)
    
    acc_types = ["함대 전체"] + list(df['계좌유형'].unique())
    selected_type = st.selectbox("📂 섹터 필터", acc_types, label_visibility="collapsed")
    
    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()
    
    # --- [핵심] 자산 및 현금 분리 연산 ---
    total_eval = display_df['평가금액'].sum()
    cash_mask = display_df['종목명'].astype(str).str.contains('현금')
    total_cash = display_df[cash_mask]['평가금액'].sum() # 현금만 추출하여 합산
    
    # 수익률 기준 정렬 (현금은 리스트 하단으로 내리거나 제외할 수 있으나 정렬 유지)
    display_df = display_df.sort_values(by='수익률_숫자', ascending=False)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("총 함대 자산", f"{total_eval:,.0f}원")
    c2.metric("기동 대기 현금", f"{total_cash:,.0f}원")
    c3.metric("고지(8.3억) 달성률", f"{(total_eval/830000000*100):.1f}%")

    st.divider()

    if display_df.empty:
        st.info("데이터가 없습니다.")
    else:
        for _, row in display_df.iterrows():
            if "현금" in str(row['종목명']): continue # 현금은 위에서 보여주므로 리스트에서는 숨김 처리
            
            yield_val = row.get('수익률_숫자', 0)
            ball = "🔴" if yield_val > 0 else "🔵" if yield_val < 0 else "🔘"
            now_price = row['현재가2'] if row['현재가2'] != 0 else row['현재가1']
            
            if row['전일종가'] > 0:
                change_amt = now_price - row['전일종가']
                change_sign = "▲" if change_amt > 0 else "▼" if change_amt < 0 else "-"
                price_display = f"{now_price:,.0f} ({change_sign}{abs(change_amt):,.0f})"
            else:
                price_display = f"{now_price:,.0f}"
                
            title = f"{ball} {row['종목명']} │ {price_display} │ {yield_val:.2f}%"
            
            with st.expander(title):
                weight = (row['평가금액'] / total_eval * 100) if total_eval > 0 else 0
                st.markdown(f"<span style='color:#6C7A89; font-size:0.85rem;'>계좌: {row['계좌유형']} | 자산 비중: <strong style='color:#4682B4;'>{weight:.1f}%</strong></span>", unsafe_allow_html=True)
                
                sc1, sc2 = st.columns(2)
                with sc1:
                    st.write(f"📊 **평가액:** {row['평가금액']:,.0f}원")
                    st.write(f"💰 **투입금:** {row['매수금액']:,.0f}원")
                with sc2:
                    st.write(f"🎯 **평단가:** {row['매수단가']:,.0f}원")
                    st.write(f"📦 **수량:** {row['잔고수량']:,.0f}주")

    # --- [3] 사이드바 폼 ---
    with st.sidebar:
        st.header("🛠️ 작전 통제")
        mode = st.radio("모드", ["기존 매매", "데이터 수정", "신규 추가"])
        with st.form("command_form"):
            acc_opts = [f"{r['계좌유형']} [{r['계좌번호']}]" for _, r in full_df[['계좌유형', '계좌번호']].drop_duplicates().iterrows()]
            sel_acc_str = st.selectbox("타격 계좌", acc_opts)
            sel_acc = sel_acc_str.split('[')[-1].replace(']', '')
            
            if "신규" not in mode:
                s_list = full_df[full_df['계좌번호'].astype(str) == sel_acc]['종목명'].tolist()
                s_name = st.selectbox("종목 선택", s_list if s_list else ["없음"])
                action = st.radio("구분", ["매수", "매도"], horizontal=True) if "매매" in mode else None
            else:
                s_name = st.text_input("종목명/코드")
                s_code = st.text_input("종목번호(선택)")
                
            qty = st.number_input("수량", min_value=0, step=1)
            price = st.number_input("단가", min_value=0, step=100)
            
            if st.form_submit_button("시트 동기화"):
                idx_map = {col: i+1 for i, col in enumerate(full_df.columns)}
                if "수정" in mode:
                    t_idx = full_df[(full_df['계좌번호'].astype(str) == sel_acc) & (full_df['종목명'] == s_name)].index[0]
                    if '잔고수량' in idx_map: sheet.update_cell(t_idx+2, idx_map['잔고수량'], int(qty))
                    if '매수단가' in idx_map: sheet.update_cell(t_idx+2, idx_map['매수단가'], int(price))
                elif "매매" in mode:
                    t_idx = full_df[(full_df['계좌번호'].astype(str) == sel_acc) & (full_df['종목명'] == s_name)].index[0]
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
                        acc_type = full_df[full_df['계좌번호'].astype(str) == sel_acc]['계좌유형'].iloc[0] if not full_df[full_df['계좌번호'].astype(str) == sel_acc].empty else "수동"
                        if '계좌유형' in idx_map: sheet.update_cell(new_row, idx_map['계좌유형'], acc_type)
                        if '종목명' in idx_map: sheet.update_cell(new_row, idx_map['종목명'], s_name)
                        if s_code and '종목코드' in idx_map: sheet.update_cell(new_row, idx_map['종목코드'], str(s_code))
                        if '잔고수량' in idx_map: sheet.update_cell(new_row, idx_map['잔고수량'], int(qty))
                        if '매수단가' in idx_map: sheet.update_cell(new_row, idx_map['매수단가'], int(price))
                st.cache_data.clear()
                st.rerun()

except Exception as e:
    st.error(f"함대 기동 중지: {e}")
