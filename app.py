import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- [1] 엘리트 커맨드 프리미엄 UI/UX (V8.5) ---
st.set_page_config(page_title="거북이 함대 기동 본부 V8.5", layout="wide")

# 사령관님 지정 색상 규격: Steel Blue(#4682B4), Slate Gray(#6C7A89)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;700&family=Noto+Sans+KR:wght@300;400;700&display=swap');
    
    .stApp { background-color: #020617; color: #f1f5f9; font-family: 'Noto Sans KR', sans-serif; }
    
    /* 상단 콤팩트 헤더 레이아웃 */
    .top-command-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 5px 0 15px 0;
    }
    .witty-title { font-family: 'Poppins'; font-size: 0.9rem; color: #4682B4; font-weight: 700; letter-spacing: 1.5px; }
    
    /* [프리미엄 카드] 상용 어플 스타일 리스트 */
    .asset-card {
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 15px;
        margin-bottom: 10px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .card-left { display: flex; align-items: center; gap: 12px; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; }
    .dot-profit { background-color: #4682B4; box-shadow: 0 0 10px #4682B4; } /* Steel Blue */
    .dot-loss { background-color: #6C7A89; } /* Slate Gray */
    
    .stock-name { font-size: 1.05rem; font-weight: 700; color: #f8fafc; }
    .stock-price { font-size: 0.8rem; color: #94a3b8; }
    
    .card-right { text-align: right; }
    .roi-text { font-family: 'Poppins'; font-size: 1.15rem; font-weight: 700; }
    .roi-up { color: #4682B4; } /* 수익 시 Steel Blue */
    .roi-down { color: #6C7A89; } /* 손실 시 Slate Gray */
    
    /* 확장 세부 분석 그리드 */
    .detail-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        background: #020617;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #1e293b;
    }
    .detail-item { font-size: 0.85rem; color: #94a3b8; }
    .detail-value { font-weight: 700; color: #4682B4; float: right; }
    
    /* 메트릭 섹션 */
    [data-testid="stMetricValue"] { color: #4682B4 !important; font-size: 1.6rem !important; font-weight: 800 !important; }
    
    /* 모바일 가독성 강제 보정 */
    @media (max-width: 768px) {
        .witty-title { font-size: 0.8rem; }
        .stock-name { font-size: 0.95rem; }
        .roi-text { font-size: 1rem; }
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

@st.cache_data(ttl=60) # 초고속 기동을 위한 60초 캐싱
def load_data():
    client = get_gspread_client()
    sheet_url = "https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0"
    doc = client.open_by_url(sheet_url)
    sheet = doc.get_worksheet(0)
    full_df = pd.DataFrame(sheet.get_all_records())
    
    # 분석 필수 열 (전일종가 등 지표 포함)
    essential_cols = ['계좌번호', '계좌유형', '종목명', '잔고수량', '매수단가', '현재가2', '현재가1', '수익률', '수익률1', '평가금액', '매수금액', '평가손익', '전일종가']
    df = full_df[[c for c in essential_cols if c in full_df.columns]].copy()
    
    for col in essential_cols:
        if col not in df.columns: df[col] = 0
        elif col not in ['계좌번호', '계좌유형', '종목명', '수익률', '수익률1']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', ''), errors='coerce').fillna(0)
    
    target_yield = '수익률' if '수익률' in full_df.columns else '수익률1' if '수익률1' in full_df.columns else None
    df['수익률_숫자'] = pd.to_numeric(df[target_yield].astype(str).str.replace('%', '').str.replace(',', ''), errors='coerce').fillna(0) if target_yield else 0.0
    return sheet, df, full_df

# --- [2] 관제 화면 기동 ---
try:
    sheet, df, full_df = load_data()
    
    # 상단 전략 바 (Compact Title & Filter)
    st.markdown('<div class="top-command-bar"><div class="witty-title">FLEET HQ │ ELITE RECON</div></div>', unsafe_allow_html=True)
    
    acc_types = ["전체 함대"] + list(df['계좌유형'].unique())
    selected_type = st.selectbox("", acc_types, label_visibility="collapsed")
    
    display_df = df[df['계좌유형'] == selected_type].copy() if selected_type != "전체 함대" else df.copy()
    display_df = display_df.sort_values(by='수익률_숫자', ascending=False)

    # 지휘관 요약 지표
    total_eval = display_df['평가금액'].sum()
    total_cash = display_df[display_df['종목명'].str.contains('현금', na=False)]['평가금액'].sum()
    
    k1, k2 = st.columns(2)
    k1.metric("총 자산 평가", f"{total_eval:,.0f}원")
    k2.metric("기동 대기 현금", f"{total_cash:,.0f}원")
    
    st.divider()

    # 엘리트 종목 리스트 (Premium Card UI)
    if display_df.empty:
        st.info("No Tactical Data Available.")
    else:
        for _, row in display_df.iterrows():
            if "현금" in str(row['종목명']): continue
            
            yield_val = row.get('수익률_숫자', 0)
            dot_class = "dot-profit" if yield_val > 0 else "dot-loss"
            roi_class = "roi-up" if yield_val > 0 else "roi-down"
            
            # 시세 정보 하이브리드 로드
            now_price = row['현재가2'] if row['현재가2'] != 0 else row['현재가1']
            price_txt = f"{now_price:,.0f}원" if now_price > 0 else "데이터 스캔 중..."
            
            # 카드 렌더링
            st.markdown(f"""
                <div class="asset-card">
                    <div class="card-left">
                        <div class="status-dot {dot_class}"></div>
                        <div>
                            <div class="stock-name">{row['종목명']}</div>
                            <div class="stock-price">{price_txt}</div>
                        </div>
                    </div>
                    <div class="card-right">
                        <div class="roi-text {roi_class}">{yield_val:.2f}%</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # 상세 분석 아코디언
            with st.expander(f"{row['종목명']} 전략적 세부 지표"):
                weight = (row['평가금액'] / total_eval * 100) if total_eval > 0 else 0
                st.markdown(f"""
                <div class="detail-grid">
                    <div class="detail-item">포트폴리오 비중 <span class="detail-value">{weight:.1f}%</span></div>
                    <div class="detail-item">평가 금액 <span class="detail-value">{row['평가금액']:,.0f}원</span></div>
                    <div class="detail-item">매수 총액 <span class="detail-value">{row['매수금액']:,.0f}원</span></div>
                    <div class="detail-item">가중 평균 단가 <span class="detail-value">{row['매수단가']:,.0f}원</span></div>
                    <div class="detail-item">보유 수량 <span class="detail-value">{row['잔고수량']:,.0f}주</span></div>
                    <div class="detail-item">섹터 분류 <span class="detail-value">{row['계좌유형']}</span></div>
                </div>
                """, unsafe_allow_html=True)

    # --- [3] 사이드바: 통합 전략 컨트롤러 ---
    with st.sidebar:
        st.header("🛠️ 전략 사령부")
        mode = st.radio("전술", ["기존 종목 매매", "데이터 강제 수정", "신규 종목 추가"])
        
        with st.form("elite_command_form"):
            # 버그 수정: 계좌번호 매칭 시 공백 및 형식 엄격화
            acc_opts = [f"{r['계좌유형']} [{r['계좌번호']}]" for _, r in full_df[['계좌유형', '계좌번호']].drop_duplicates().iterrows()]
            sel_acc_str = st.selectbox("타격 계좌", acc_opts)
            sel_acc = sel_acc_str.split('[')[-1].replace(']', '').strip()
            
            if mode != "신규 종목 추가":
                s_list = full_df[full_df['계좌번호'].astype(str).str.strip() == sel_acc]['종목명'].tolist()
                s_name = st.selectbox("종목 선택", s_list if s_list else ["데이터 없음"])
            else:
                s_name = st.text_input("신규 종목명/번호")
                s_code = st.text_input("종목코드(필수X)")

            qty = st.number_input("거래 수량", min_value=0)
            price = st.number_input("거래 단가", min_value=0)
            
            if st.form_submit_button("명령 확정 및 동기화"):
                idx_map = {col: i+1 for i, col in enumerate(full_df.columns)}
                
                # 시트 좌표 추적 로직 (무결성 보장)
                if mode == "데이터 강제 수정":
                    t_idx = full_df[(full_df['계좌번호'].astype(str).str.strip() == sel_acc) & (full_df['종목명'] == s_name)].index[0]
                    sheet.update_cell(t_idx+2, idx_map['잔고수량'], int(qty))
                    sheet.update_cell(t_idx+2, idx_map['매수단가'], int(price))
                elif mode == "기존 종목 매매":
                    t_idx = full_df[(full_df['계좌번호'].astype(str).str.strip() == sel_acc) & (full_df['종목명'] == s_name)].index[0]
                    old_qty, old_avg = full_df.at[t_idx, '잔고수량'], full_df.at[t_idx, '매수단가']
                    new_qty = old_qty + qty if qty > 0 else old_qty
                    new_avg = ((old_qty * old_avg) + (qty * price)) / new_qty if new_qty > 0 else old_avg
                    sheet.update_cell(t_idx+2, idx_map['잔고수량'], int(new_qty))
                    sheet.update_cell(t_idx+2, idx_map['매수단가'], int(new_avg))
                elif mode == "신규 종목 추가":
                    if s_name:
                        nr = len(full_df) + 2
                        sheet.update_cell(nr, idx_map['계좌번호'], sel_acc)
                        acc_type = full_df[full_df['계좌번호'].astype(str).str.strip() == sel_acc]['계좌유형'].iloc[0] if not full_df[full_df['계좌번호'].astype(str).str.strip() == sel_acc].empty else "수동"
                        sheet.update_cell(nr, idx_map['계좌유형'], acc_type)
                        sheet.update_cell(nr, idx_map['종목명'], s_name)
                        if s_code and '종목코드' in idx_map: sheet.update_cell(nr, idx_map['종목코드'], str(s_code))
                        sheet.update_cell(nr, idx_map['잔고수량'], int(qty))
                        sheet.update_cell(nr, idx_map['매수단가'], int(price))
                
                st.cache_data.clear() # 수정 즉시 반영을 위한 기억 소거
                st.rerun()

except Exception as e:
    st.error(f"함대 기동 중단: {e}")
