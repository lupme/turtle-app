# app.py 내 load_data 함수 수정
@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    doc = client.open_by_url("https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0")
    
    # 메인 자산 시트 (기존)
    sheet = doc.get_worksheet(0)
    full_df = pd.DataFrame(sheet.get_all_records())
    df = full_df.copy()
    for col in df.columns:
        if col not in ['계좌번호', '계좌유형', '종목명', '종목코드', '상품', '구분']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', '').str.replace('%', ''), errors='coerce').fillna(0)
    
    # Control_Room 가중치 시트 읽기 (새로 추가)
    # 가심비/수급/추세/VCP 등 설정값이 있는 시트라고 가정합니다.
    try:
        ctrl_sheet = doc.worksheet("Control_Room")
        ctrl_data = ctrl_sheet.get_all_records()[0] # 첫 줄에 가중치가 있다고 가정
        weights = {
            "flow": float(ctrl_data.get('수급가중치', 0.4)),
            "trend": float(ctrl_data.get('추세가중치', 0.4)),
            "vcp": float(ctrl_data.get('VCP가중치', 0.2))
        }
    except:
        weights = {"flow": 0.4, "trend": 0.4, "vcp": 0.2} # 실패 시 기본값
        
    return sheet, df[df['종목명'].astype(str).str.strip() != ''], full_df, weights

# 메인 루프에서 사용 시:
sheet, df, full_df, current_weights = load_data()

# 리스트 출력부 수정:
tcr = quant_analyzer.get_tcr_score(str(row.get('종목코드', '')), now_p, weights=current_weights)
