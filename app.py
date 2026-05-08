import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- [1] 프리미엄 관제소 V8.1 설정 (방어력 강화) ---
st.set_page_config(page_title="거북이 함대 기동 본부 V8.1", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f1f5f9; }
    h1, h2, h3 { font-family: 'Urbanist', sans-serif !important; }
    .top-bar { display: flex; justify-content: space-between; align-items: flex-start; width: 100%; padding-bottom: 20px; }
    .witty-title { font-size: 1.1rem; color: #4682B4; font-weight: 700; letter-spacing: 1.5px; }
    .streamlit-expanderHeader { 
        background-color: #0f172a !important; 
        border-radius: 12px !important; 
        border: 1px solid #1e293b !important;
        padding: 15px !important;
    }
    /* 신체 부위 지표 스타일 */
    .pos-badge { padding: 4px 10px; border-radius: 4px; font-weight: 800; font-size: 0.8rem; margin-right: 10px; }
    .pos-head { background-color: #ef4444; color: white; }
    .pos-shoulder { background-color: #f87171; color: white; }
    .pos-waist { background-color: #f59e0b; color: white; }
    .pos-knee { background-color: #34d399; color: white; }
    .pos-feet { background-color: #10b981; color: white; }
    .pos-unknown { background-color: #475569; color: white; }
    
    [data-testid="stMetricValue"] { color: #4682B4 !important; font-size: 1.8rem !important; font-weight: 800 !important; }
    @media (max-width: 768px) {
        .witty-title { font-size: 0.9rem; }
        [data-testid="stMetricValue"] { font-size: 1.4rem !important; }
    }
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
    
    # [핵심 방어 로직] 필요한 열이 시트에 없어도 시스템이 멈추지 않도록 0으로 자동 생성
    essential_cols = ['계좌번호', '계좌유형', '종목명', '잔고수량', '매수단가', '현재가2', '현재가1', '수익률', '수익률1', '평가금액', '매수금액', '평가손익', '전일종가', '52주최고', '52주최저']
    
    df = full_df[[c for c in essential_cols if c in full_df.columns]].copy()
    
    for col in essential_cols:
        if col not in df.columns:
            df[col] = 0 # 시트에 없는 열은 0으로 방어 처리
        elif col not in ['계좌번호', '계좌유형', '종목명', '수익률', '수익률1']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', ''), errors='coerce').fillna(0)
    
    # 수익률 열 이름이 '수익률'이든 '수익률1'이든 유연하게 감지
    target_yield = '수익률' if '수익률' in full_df.columns else '수익률1' if '수익률1' in full_df.columns else None
    
    if target_yield:
        df['수익률_숫자'] = pd.to_numeric(df[target_yield].astype(str).str.replace('%', '').str.replace(',', ''), errors='coerce').fillna(0)
    else:
        df['수익률_숫자'] = 0.0 # 둘 다 없어도 에러 방지
        
    return sheet, df, full_df

# --- [2] 시장 위치 판독 로직 ---
def get_position_text(now, low, high):
    if high == 0 or low == 0 or high == low or now == 0: 
        return "데이터 필요", "pos-unknown"
    pos = (now - low) / (high - low) * 100
    if pos >= 85: return "머리 (85% 이상)", "pos-head"
    if pos >= 65: return "어깨 (과열 진입)", "pos-shoulder"
    if pos >= 35: return "허리 (평균 시세)", "pos-waist"
    if pos >= 15: return "무릎 (저점 접근)", "pos-knee"
    return "발바닥 (극저점)", "pos-feet"

# --- [3] 관제 화면 기동 ---
try:
    sheet, df, full_df = load_data()
    
    # 사이드바: 목표 금액 설정 (가변형)
    with st.sidebar:
        st.header("🎯 함대 전략 설정")
        target_input = st.number_input("함대 목표 자산 (원)", value=830000000, step=10000000)
        st.divider()
        mode = st.radio("전술 모드", ["기존 종목 매매", "데이터 강제 수정", "신규 종목 추가"])

    st.markdown('<div class="top-bar"><div class="witty-title">🐢 TURTLE COMMAND HQ V8.1</div></div>', unsafe_allow_html=True)
    
    acc_types = ["함대 전체"] + list(df['계좌유형'].unique())
    selected_type = st.selectbox("📂 섹터 필터", acc_types, label_visibility="collapsed")
    
    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()
    display_df = display_df.sort_values(by='수익률_숫자', ascending=False)

    # 계좌별 지표 계산
    total_eval = display_df['평가금액'].sum()
    total_prev = (display_df['전일종가'] * display_df['잔고수량']).sum()
    daily_delta = total_eval - total_prev if total_prev > 0 else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("총 함대 자산", f"{total_eval:,.0f}원")
    
    if total_prev > 0:
        c2.metric("전일 대비 증감", f"{daily_delta:,.0f}원", delta=f"{daily_delta:,.0f}")
    else:
        c2.metric("전일 대비 증감", "지표 설정 필요", delta=None)
        
    c3.metric("전략 고지 달성률", f"{(total_eval/target_input*100):.1f}%")

    st.divider()

    # 리스트 디자인 (시장 위치 지표 포함)
    if display_df.empty:
        st.info("기동 대기 중인 자산이 없습니다.")
    else:
        for _, row in display_df.iterrows():
            if "현금" in str(row['종목명']): continue
            
            yield_val = row.get('수익률_숫자', 0)
            ball = "🔴" if yield_val > 0 else "🔵" if yield_val < 0 else "🔘"
            
            now_price = row['현재가2'] if row['현재가2'] != 0 else row['현재가1']
            
            # 위치 판독
            pos_text, pos_class = get_position_text(now_price, row['52주최저'], row['52주최고'])
            
            title = f"{ball} {row['종목명']} │ {now_price:,.0f}원 │ {yield_val:.2f}%"
            
            with st.expander(title):
                st.markdown(f'<span class="pos-badge {pos_class}">시장위치: {pos_text}</span>', unsafe_allow_html=True)
                sc1, sc2 = st.columns(2)
                with sc1:
                    st.write(f"📊 **평가금액:** {row['평가금액']:,.0f}원")
                    st.write(f"💰 **투입금액:** {row['매수금액']:,.0f}원")
                with sc2:
                    st.write(f"🎯 **평균단가:** {row['매수단가']:,.0f}원")
                    if row['52주최고'] > 0:
                        st.write(f"📈 **52주 최고:** {row['52주최고']:,.0f}원")
                    else:
                        st.write("📈 **52주 지표:** 구글 시트 추가 필요")
                st.caption(f"좌표: {row['계좌번호']} / {row['계좌유형']}")

    # --- [4] 사이드바 폼 로직 ---
    with st.sidebar:
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
            price = st.number_input("현재가/단가", min_value=0, step=100)
            
            if st.form_submit_button("명령 하달 (Sync)"):
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
