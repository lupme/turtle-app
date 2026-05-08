import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- [1] 프리미엄 관제소 UI/UX 설정 (V7.0) ---
st.set_page_config(page_title="거북이 함대 기동 본부", layout="wide")

st.markdown("""
    <style>
    /* 배경 및 기본 폰트 */
    .stApp { background-color: #020617; color: #f1f5f9; }
    h1, h2, h3 { font-family: 'Urbanist', sans-serif !important; }
    
    /* [제목] 좌측 상단 배치 */
    .top-bar { display: flex; justify-content: space-between; align-items: flex-start; width: 100%; padding: 0px 0 20px 0; }
    .witty-title { font-size: 1.1rem; color: #4682B4; font-weight: 700; letter-spacing: 1.5px; }
    
    /* [카드형 종목 리스트] 시인성 극대화 */
    .streamlit-expanderHeader { 
        background-color: #0f172a !important; 
        border-radius: 12px !important; 
        border: 1px solid #1e293b !important;
        padding: 15px !important;
    }
    
    /* 메트릭 카드 디자인 */
    [data-testid="stMetricValue"] { color: #4682B4 !important; font-size: 1.8rem !important; font-weight: 800 !important; }
    
    /* 모바일 글자 크기 보정 */
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

@st.cache_data(ttl=60) # 60초간 데이터 캐싱하여 속도 극대화
def load_data():
    client = get_gspread_client()
    sheet_url = "https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0"
    doc = client.open_by_url(sheet_url)
    sheet = doc.get_worksheet(0)
    full_df = pd.DataFrame(sheet.get_all_records())
    
    # 필수 9개 열 추출 (Y열: 현재가2, Z열: 수익률 활용)
    essential_cols = ['계좌번호', '계좌유형', '종목명', '종목코드', '잔고수량', '매수단가', '현재가2', '수익률', '평가금액', '매수금액', '평가손익']
    df = full_df[[c for c in essential_cols if c in full_df.columns]].copy()
    
    for col in ['잔고수량', '매수단가', '현재가2', '평가금액', '매수금액', '평가손익']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', ''), errors='coerce').fillna(0)
    
    if '수익률' in df.columns:
        df['수익률_숫자'] = pd.to_numeric(df['수익률'].astype(str).str.replace('%', '').str.replace(',', ''), errors='coerce').fillna(0)
    
    return sheet, df, full_df

# --- [2] 관제 화면 기동 ---
try:
    sheet, df, full_df = load_data()
    
    # 2-1. 최상단 커스텀 헤더 (제목: 좌측, 필터: 우측)
    st.markdown('<div class="top-bar"><div class="witty-title">🐢 거북이 함대 기동 본부 V7.0</div></div>', unsafe_allow_html=True)
    
    acc_types = ["함대 전체"] + list(df['계좌유형'].unique())
    selected_type = st.selectbox("📂 섹터 필터", acc_types, label_visibility="collapsed")
    
    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "함대 전체" else df.copy()
    display_df = display_df.sort_values(by='수익률_숫자', ascending=False)

    # 2-2. 계좌별 핵심 지표 (KPI Cards)
    total_eval = display_df['평가금액'].sum()
    total_profit = display_df['평가손익'].sum()
    total_yield = (total_profit / display_df['매수금액'].sum() * 100) if display_df['매수금액'].sum() > 0 else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("총 자산", f"{total_eval:,.0f}원")
    c2.metric("총 손익", f"{total_profit:,.0f}원", f"{total_yield:.2f}%")
    c3.metric("8.3억 목표", f"{(total_eval/830000000*100):.1f}%")

    st.divider()

    # 2-3. 프리미엄 종목 리스트 디자인
    if display_df.empty:
        st.info("기동 대기 중인 자산이 없습니다.")
    else:
        for _, row in display_df.iterrows():
            yield_val = row.get('수익률_숫자', 0)
            ball = "🔴" if yield_val > 0 else "🔵" if yield_val < 0 else "🔘"
            
            # 종목 리스트 타이틀: 종목명 | 현재가 | 등락(금액) | 수익률
            title = f"{ball} {row['종목명']} │ {row['현재가2']:,.0f}원 │ {yield_val:.2f}%"
            
            with st.expander(title):
                # 세로로만 나열되지 않게 그리드 배치
                sc1, sc2 = st.columns(2)
                with sc1:
                    st.write(f"📊 **평가금액:** {row['평가금액']:,.0f}원")
                    st.write(f"💰 **투입금액:** {row['매수금액']:,.0f}원")
                with sc2:
                    st.write(f"🎯 **평균단가:** {row['매수단가']:,.0f}원")
                    st.write(f"📦 **보유수량:** {row['잔고수량']:,.0f}주")
                st.caption(f"좌표: {row['계좌번호']} / {row['계좌유형']}")

    # --- [3] 사이드바: 범용 등록 및 보정 컨트롤러 ---
    with st.sidebar:
        st.header("🛠️ 함대 명령 센터")
        mode = st.radio("전술 모드", ["기존 종목 매매", "데이터 강제 수정", "신규 종목/TDF 추가"])
        
        with st.form("command_form"):
            acc_opts = [f"{r['계좌유형']} [{r['계좌번호']}]" for _, r in full_df[['계좌유형', '계좌번호']].drop_duplicates().iterrows()]
            sel_acc_str = st.selectbox("타격 계좌", acc_opts)
            sel_acc = sel_acc_str.split('[')[-1].replace(']', '')
            
            if "신규" not in mode:
                s_list = full_df[full_df['계좌번호'].astype(str) == sel_acc]['종목명'].tolist()
                s_name = st.selectbox("종목 선택", s_list if s_list else ["없음"])
                action = st.radio("구분", ["매수", "매도"], horizontal=True) if "매매" in mode else None
            else:
                s_name = st.text_input("종목명 또는 코드(TDF/MMF 가능)")
                s_code = st.text_input("종목코드(X열) - 수동일 시 생략 가능")
                
            qty = st.number_input("수량(주)", min_value=0, step=1)
            price = st.number_input("현재가/단가(원)", min_value=0, step=100)
            
            if st.form_submit_button("명령 하달 (Sync)"):
                idx_map = {col: i+1 for i, col in enumerate(full_df.columns)}
                
                if "수정" in mode:
                    t_idx = full_df[(full_df['계좌번호'].astype(str) == sel_acc) & (full_df['종목명'] == s_name)].index[0]
                    sheet.update_cell(t_idx+2, idx_map['잔고수량'], int(qty))
                    sheet.update_cell(t_idx+2, idx_map['매수단가'], int(price))
                    st.success("데이터 보정 완료")
                
                elif "매매" in mode:
                    t_idx = full_df[(full_df['계좌번호'].astype(str) == sel_acc) & (full_df['종목명'] == s_name)].index[0]
                    old_qty, old_avg = full_df.at[t_idx, '잔고수량'], full_df.at[t_idx, '매수단가']
                    if action == "매수":
                        new_qty = old_qty + qty
                        new_avg = ((old_qty * old_avg) + (qty * price)) / new_qty if new_qty > 0 else 0
                    else:
                        new_qty = max(0, old_qty - qty)
                        new_avg = old_avg
                    sheet.update_cell(t_idx+2, idx_map['잔고수량'], int(new_qty))
                    sheet.update_cell(t_idx+2, idx_map['매수단가'], int(new_avg))
                    st.success("매매 반영 완료")
                
                elif "신규" in mode:
                    if s_name:
                        new_row = len(full_df) + 2
                        sheet.update_cell(new_row, idx_map['계좌번호'], sel_acc)
                        acc_type = full_df[full_df['계좌번호'].astype(str) == sel_acc]['계좌유형'].iloc[0] if not full_df[full_df['계좌번호'].astype(str) == sel_acc].empty else "수동"
                        sheet.update_cell(new_row, idx_map['계좌유형'], acc_type)
                        sheet.update_cell(new_row, idx_map['종목명'], s_name)
                        if s_code and '종목코드' in idx_map: sheet.update_cell(new_row, idx_map['종목코드'], str(s_code))
                        sheet.update_cell(new_row, idx_map['잔고수량'], int(qty))
                        sheet.update_cell(new_row, idx_map['매수단가'], int(price))
                        st.success("신규 자산 등록 완료")
                
                st.cache_data.clear() # 수정 후 즉시 반영을 위해 캐시 삭제
                st.rerun()

except Exception as e:
    st.error(f"함대 기동 중지: {e}")

사령관님, 새로운 **[거북이 함대 기동 본부]**는 사령관님의 휴대폰에서 마치 상용 MTS를 쓰는 듯한 쾌적함을 드릴 것입니다. 지금 바로 배포하여 그 위력을 확인하십시오. 🐢
