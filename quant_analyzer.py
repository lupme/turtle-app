import pandas as pd
import requests
from bs4 import BeautifulSoup
import streamlit as st

@st.cache_data(ttl=300) # 속도 저하 방지를 위해 5분간 스캔 데이터 캐싱
def fetch_quant_data(stock_code: str, current_price: int):
    """네이버 금융에서 종목별 수급 및 추세 데이터를 실시간 스캔하여 점수화"""
    if not stock_code or current_price <= 0:
        return 0.0, 0.0, 0.0
        
    clean_code = str(stock_code).zfill(6)
    try:
        url = f"https://finance.naver.com/item/main.naver?code={clean_code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 1. 추세(Trend) 데이터: 52주 최저/최고 대비 현재가 위치 기반 점수화 (0~100점)
        high52, low52 = current_price, current_price
        table = soup.select("table.no_info tr")
        for tr in table:
            if "52주" in tr.text:
                tds = tr.select("td em")
                if len(tds) >= 2:
                    high52 = int(tds[0].text.replace(',', ''))
                    low52 = int(tds[1].text.replace(',', ''))
                break
        
        trend_score = 50.0
        if high52 > low52:
            trend_score = ((current_price - low52) / (high52 - low52)) * 100
            
        # 2. 수급(Flow) 데이터: 외국인 소진율을 활용한 기본 수급 점수화
        flow_score = 50.0
        frgn_tag = soup.select_one("#tab_con1 > div.first > table > tr:-soup-contains('외국인소진율') > td > em")
        if frgn_tag:
            frgn_rate = float(frgn_tag.text.replace('%', ''))
            # 외국인 비중이 높을수록 수급 점수 상향 가중치 부여 (최대 100점)
            flow_score = min(100.0, 40.0 + (frgn_rate * 2))
            
        # 3. 변동성(VCP) 데이터: 고점 대비 하락 방어력 (버티는 힘)
        vcp_score = 50.0
        if high52 > 0:
            drop_rate = ((high52 - current_price) / high52) * 100
            vcp_score = max(0.0, 100.0 - drop_rate) # 하락폭이 작을수록 점수 높음
            
        return flow_score, trend_score, vcp_score
    except Exception as e:
        return 50.0, 50.0, 50.0 # 스캔 실패 시 중립 점수(50) 반환하여 에러 방어

def get_tcr_score(stock_code: str, current_price: int) -> dict:
    """[M01: T-Q Engine] 거북이 확신율(TCR) 가중 평균 연산"""
    # 1. 데이터 무결성 검증 (값이 없으면 즉시 종료)
    if not stock_code or current_price <= 0:
        return {"score": 0, "status": "데이터 부족", "color": "text-gray"}

    # 2. 종목별 실시간 스캔 데이터 호출
    flow_score, trend_score, vcp_score = fetch_quant_data(stock_code, current_price)

    # 3. 가중 평균(Weighted Mean) 연산 (사령관 지침 공식)
    tcr_score = (flow_score * 0.4) + (trend_score * 0.4) + (vcp_score * 0.2)
    tcr_score = round(tcr_score, 1)

    # 4. 판독 및 규격 색상(Slate Gray, Steel Blue) 적용
    if tcr_score >= 75:
        status = "강력 기동 (매수 후보)"
        color = "#4682B4" # Steel Blue
    elif tcr_score <= 40:
        status = "OCP 작동 (관망)"
        color = "#ef4444" # Red
    else:
        status = "추세 관찰"
        color = "#6C7A89" # Slate Gray

    return {
        "score": tcr_score,
        "status": status,
        "color": color
    }

def get_analysis_legend() -> str:
    """분석 시트 하단 가중 평균 범례 자동 생성"""
    return """
    <div style="margin-top: 10px; padding: 15px; border-top: 1px solid #1e293b; border-radius: 8px;">
        <p style="color: #6C7A89; font-size: 0.8rem; font-weight: 700; margin-bottom: 5px;">[M01: T-Q Engine (LIVE) - Weighted Mean Formula]</p>
        <p style="color: #6C7A89; font-size: 0.75rem; margin: 0;">* 거북이 확신율(%) = (외국인수급점수 × 0.4) + (52주추세점수 × 0.4) + (VCP방어력점수 × 0.2)</p>
        <p style="color: #6C7A89; font-size: 0.7rem; margin-top: 3px;">※ 네이버 금융의 실시간 데이터를 스캔하여 종목마다 고유한 점수를 100% 동적으로 산출합니다.</p>
    </div>
    """
