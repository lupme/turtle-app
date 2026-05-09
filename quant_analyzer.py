import pandas as pd
import requests
from bs4 import BeautifulSoup
import streamlit as st
import re

@st.cache_data(ttl=300) # 과부하 방지 5분 캐싱
def fetch_quant_data(stock_code: str, current_price: int):
    """정규표현식을 활용한 강력한 네이버 금융 실시간 데이터 파싱"""
    if not stock_code or current_price <= 0:
        return 50.0, 50.0, 50.0
        
    clean_code = str(stock_code).zfill(6)
    try:
        url = f"https://finance.naver.com/item/main.naver?code={clean_code}"
        # 모바일 크롬 브라우저인 것처럼 위장하여 차단 방지
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 1. 52주 최고/최저 확보 (정규표현식으로 숫자만 추출)
        high52, low52 = current_price, current_price
        info_table = soup.select_one(".no_info")
        if info_table:
            for tr in info_table.find_all("tr"):
                if "52주" in tr.text:
                    ems = tr.find_all("em")
                    if len(ems) >= 2:
                        high52 = int(re.sub(r'[^0-9]', '', ems[0].text))
                        low52 = int(re.sub(r'[^0-9]', '', ems[1].text))
                    break
        
        # 2. 외국인 소진율 확보
        frgn_rate = 0.0
        th_tags = soup.find_all('th')
        for th in th_tags:
            if "외국인소진율" in th.text:
                td = th.find_next_sibling('td')
                if td and td.find('em'):
                    frgn_rate = float(re.sub(r'[^0-9.]', '', td.find('em').text))
                break

        # [핵심 로직 연산]
        # 추세 점수: (현재가 - 최저가) / (최고가 - 최저가) * 100
        trend_score = 50.0
        if high52 > low52:
            trend_score = ((current_price - low52) / (high52 - low52)) * 100
            trend_score = min(100.0, max(0.0, trend_score))
            
        # 수급 점수: 외국인 소진율 비중 반영 (소진율이 높을수록 가점)
        flow_score = min(100.0, 40.0 + (frgn_rate * 1.5))
        
        # 변동성(VCP) 점수: 고점 대비 하락률 (적게 빠질수록 고득점)
        vcp_score = 50.0
        if high52 > 0:
            drop_rate = ((high52 - current_price) / high52) * 100
            vcp_score = max(0.0, 100.0 - drop_rate)
            
        return round(flow_score, 1), round(trend_score, 1), round(vcp_score, 1)
    
    except Exception as e:
        # 스캔 실패 시에만 중립값 반환
        return 50.0, 50.0, 50.0

def get_tcr_score(stock_code: str, current_price: int) -> dict:
    """[M01: T-Q Engine] 거북이 확신율(TCR) 가중 평균 연산"""
    if not stock_code or current_price <= 0:
        return {"score": 0, "status": "데이터 부족", "color": "text-gray"}

    flow_score, trend_score, vcp_score = fetch_quant_data(stock_code, current_price)

    tcr_score = (flow_score * 0.4) + (trend_score * 0.4) + (vcp_score * 0.2)
    tcr_score = round(tcr_score, 1)

    # 투명성 확보: 점수 디테일을 status에 강제 포함
    detail_txt = f"수급:{flow_score:.0f} 추세:{trend_score:.0f} VCP:{vcp_score:.0f}"

    if tcr_score >= 75:
        status = f"강력 기동 [{detail_txt}]"
        color = "#4682B4" # Steel Blue
    elif tcr_score <= 40:
        status = f"OCP 작동 [{detail_txt}]"
        color = "#ef4444" # Red
    else:
        status = f"추세 관찰 [{detail_txt}]"
        color = "#6C7A89" # Slate Gray

    return {
        "score": tcr_score,
        "status": status,
        "color": color
    }

def get_analysis_legend() -> str:
    return """
    <div style="margin-top: 10px; padding: 15px; border-top: 1px solid #1e293b; border-radius: 8px;">
        <p style="color: #6C7A89; font-size: 0.8rem; font-weight: 700; margin-bottom: 5px;">[M01: T-Q Engine (LIVE) - Weighted Mean Formula]</p>
        <p style="color: #6C7A89; font-size: 0.75rem; margin: 0;">* 거북이 확신율(%) = (외국인수급 × 0.4) + (52주추세 × 0.4) + (VCP방어력 × 0.2)</p>
        <p style="color: #6C7A89; font-size: 0.7rem; margin-top: 3px;">※ 투명성 확보: 확신율 판독 결과 옆 괄호 안에 각 지표의 획득 점수가 표시됩니다.</p>
    </div>
    """
