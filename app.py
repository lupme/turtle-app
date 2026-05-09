import requests
from bs4 import BeautifulSoup
import streamlit as st
import re

def get_tcr_score(stock_code, current_price):
    """네이버 금융 크롤링 - 실패해도 절대 앱을 멈추지 않음"""
    if not stock_code or current_price <= 0:
        return {"score": 0, "status": "코드/가격 오류", "color": "#6C7A89"}
    
    try:
        clean_code = str(stock_code).zfill(6)
        url = f"https://finance.naver.com/item/main.naver?code={clean_code}"
        # 타임아웃을 짧게 설정하여 앱 지연 방지
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=2.5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 데이터 파싱 (최소한의 필수 데이터만)
        high52, low52 = current_price, current_price
        info = soup.select_one(".no_info")
        if info:
            ems = info.select("tr:-soup-contains('52주') em")
            if len(ems) >= 2:
                high52 = int(re.sub(r'[^0-9]', '', ems[0].text))
                low52 = int(re.sub(r'[^0-9]', '', ems[1].text))
        
        # 확신율 산출 로직 (추세+방어 중심)
        t_score = ((current_price - low52) / (high52 - low52)) * 100 if high52 > low52 else 50.0
        v_score = max(0.0, 100.0 - (((high52 - current_price) / high52) * 100)) if high52 > 0 else 50.0
        
        final_score = round((t_score * 0.5) + (v_score * 0.5), 1)
        color = "#4682B4" if final_score >= 75 else "#6C7A89"
        
        return {"score": final_score, "status": "관측 완료", "color": color}
    except:
        # 실패 시 빈 데이터 반환 (화면 백화 방지)
        return {"score": "-", "status": "데이터 호출 지연", "color": "#6C7A89"}

def get_analysis_legend():
    return """<div style="margin-top:10px; padding:10px; border-top:1px solid #1e293b; color:#6C7A89; font-size:0.75rem;">
        [M01: T-Q 안정화 엔진 V55 가동 중]</div>"""
