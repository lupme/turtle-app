import streamlit as st
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

# 1. 환경 설정
load_dotenv()
st.set_page_config(page_title="Nova-Realtime Watcher", layout="wide")

# 2. 종목명 -> 티커 매핑 사전 (사령관님 맞춤형)
TICKER_MAP = {
    '삼성전자': '005930.KS',
    'SK하이닉스': '000660.KS',
    'LS': '006260.KS',
    'SKC': '011790.KS'
}

st.title("🐢 거북이-퀀터멘털 실시간 관제 시스템 (HTS 연동)")

# 3. 엑셀 파일 로드
try:
    df = pd.read_excel("종목.xlsx")
    
    # 필요한 열만 추출 및 이름 통일
    portfolio = df[['종목명', '잔고수량', '매수단가']].copy()
    portfolio['Ticker'] = portfolio['종목명'].map(TICKER_MAP)
    
    # 매핑되지 않은 종목 제외 (또는 수동 추가 가능)
    portfolio = portfolio.dropna(subset=['Ticker'])

    # 4. 실시간 주가 수집
    tickers = portfolio['Ticker'].tolist()
    live_data = yf.download(tickers, period="1d")['Close'].iloc[-1]

    # 5. 수익성 분석 계산
    portfolio['현재가'] = portfolio['Ticker'].map(live_data)
    portfolio['수익률(%)'] = ((portfolio['현재가'] - portfolio['매수단가']) / portfolio['매수단가'] * 100).round(2)
    portfolio['평가금액'] = portfolio['현재가'] * portfolio['잔고수량']

    # 6. 대시보드 출력
    total_val = portfolio['평가금액'].sum()
    st.metric("총 자산 평가액", f"{total_val:,.0f} 원", delta=f"{portfolio['수익률(%)'].mean():.2f}%")
    
    st.dataframe(portfolio.style.format({
        '현재가': '{:,.0f}',
        '매수단가': '{:,.0f}',
        '평가금액': '{:,.0f}',
        '수익률(%)': '{:+.2f}%'
    }), use_container_width=True)

except Exception as e:
    st.error(f"공정 오류 발생: {e}")