import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json, requests, time
from bs4 import BeautifulSoup
import quant_analyzer
import streamlit as st # 로컬 테스트용 secrets 호출

print("🚀 [TURTLE-QUANTAMENTAL V1.5] 무인 정찰 엔진 가동 시작...")

# 1. 구글 시트 인증 (기존 로직 동일)
def get_gspread_client():
    key_info = json.loads(st.secrets["google_credentials"])
    if "private_key" in key_info: 
        key_info["private_key"] = key_info["private_key"].replace("\\n", "\n")
    return gspread.authorize(Credentials.from_service_account_info(key_info, scopes=[
        'https://www.googleapis.com/auth/spreadsheets', 
        'https://www.googleapis.com/auth/drive'
    ]))

# 2. 거시 지표 수집 (완벽히 작동하던 오리지널 로직)
def get_market_indices():
    print("📡 거시 경제 지표 정찰 중...")
    indices = {"KOSPI": ("-", "-"), "NASDAQ": ("-", "-"), "S&P 500": ("-", "-"), "VIX": ("-", "-"), "USD/KRW": ("-", "-"), "WTI": ("-", "-"), "US10Y": ("-", "-")}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    try:
        res = requests.get("https://finance.naver.com/", headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        box = soup.select_one(".kospi_area")
        if box:
            indices["KOSPI"] = (box.select_one(".num").text, box.select_one('.num2').text)
            
        for code, sym in [("NASDAQ", "NAS@IXIC"), ("S&P 500", "SPI@SPX"), ("VIX", "VIX@VIX")]:
            res = requests.get(f"https://finance.naver.com/world/sise.naver?symbol={sym}", headers=headers, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            em = soup.select_one("p.no_today em")
            if em:
                ems = soup.select_one("p.no_exday").find_all("em")
                indices[code] = (em.text.strip(), ems[0].text.strip())
                
        res = requests.get("https://finance.naver.com/marketindex/", headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        usd = soup.select_one("a.head.usd")
        if usd: indices["USD/KRW"] = (usd.select_one(".value").text, usd.select_one('.change').text)
        oil = soup.select_one("a.head.oil")
        if oil: indices["WTI"] = (oil.select_one(".value").text, oil.select_one('.change').text)
        
        res = requests.get("https://finance.naver.com/marketindex/worldInterestQuote.naver?marketindexCd=IR_TNX", headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        em = soup.select_one(".no_today em")
        if em: indices["US10Y"] = (em.text.strip(), "-")
    except Exception as e:
        print(f"⚠️ 거시 지표 수집 오류: {e}")
    return indices

def get_safe_val(r, cols):
    for c in cols:
        v = r.get(c, 0)
        if v != 0 and pd.notna(v): return v
    return 0

def run_engine():
    try:
        client = get_gspread_client()
        sheet_url = "https://docs.google.com/spreadsheets/d/1SLobWRlOvwyj8zwp6O3SHU5rX4aJsVxknrCR6qd6U0k/edit#gid=0"
        
        # 원본 데이터 읽기 (첫 번째 탭)
        print("📥 원본 포트폴리오 데이터 다운로드 중...")
        raw_sheet = client.open_by_url(sheet_url).get_worksheet(0)
        df = pd.DataFrame(raw_sheet.get_all_records())
        
        # 데이터 정제 (비대면 계좌 제외 등)
        if '계좌유형' in df.columns: 
            df['계좌유형'] = df['계좌유형'].astype(str).str.strip()
            df = df[df['계좌유형'] != '종합(비대면)']
            
        for col in df.columns:
            if col not in ['계좌번호', '계좌유형', '종목명', '종목코드', '상품', '구분']:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('원', '').str.replace('%', ''), errors='coerce').fillna(0)
                
        df = df[df['종목명'].astype(str).str.strip() != '']
        df = df[~df['종목명'].astype(str).str.contains('합계|총계|총액|총자산', na=False)]
        
        # 수익률 및 필요 데이터 사전 연산
        df['안전_수익률'] = df.apply(lambda r: get_safe_val(r, ['수익률2', '수익률']), axis=1)
        
        # TCR 연산
        print("🧠 퀀트 엔진: TCR 점수 연산 중...")
        stock_list = [(str(row.get('종목코드', '')), get_safe_val(row, ['현재가2', '현재가', '기준가', '매수단가'])) for _, row in df.iterrows() if "현금" not in str(row['종목명']) and "예수금" not in str(row['종목명'])]
        tcr_results = quant_analyzer.get_tcr_scores_batch(stock_list, {"flow": 0.4, "trend": 0.4, "vcp": 0.2})
        df['TCR점수'] = df['종목코드'].astype(str).apply(lambda c: tcr_results.get(c, {}).get('score', 0))
        
        # 거시 지표 수집
        macro_data = get_market_indices()
        
        # --- 결과물 DB 저장 ---
        print("💾 연산 결과 [TQ_DB] 탭에 덮어쓰기 기록 중...")
        db_sheet = client.open_by_url(sheet_url).worksheet("TQ_DB")
        db_sheet.clear()
        
        # 1행에 거시 지표 기록 (JSON 형태 문자열로 저장)
        db_sheet.update('A1', [[json.dumps(macro_data, ensure_ascii=False)]])
        
        # 3행부터 정제된 데이터프레임 기록
        db_sheet.update('A3', [df.columns.values.tolist()] + df.values.tolist())
        
        print("✅ [성공] 엔진 1회전 완료. 데이터가 구글 시트에 업데이트되었습니다.")

    except Exception as e:
        print(f"🚨 [치명적 오류] 엔진 가동 실패: {e}")

if __name__ == "__main__":
    run_engine()
