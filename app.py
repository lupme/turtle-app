import requests
from bs4 import BeautifulSoup
import streamlit as st
import re
from concurrent.futures import ThreadPoolExecutor

# 세션을 미리 생성하여 연결 속도 최적화
session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0'})

def fetch_data(stock_code, price):
    """실시간 데이터 수집 일꾼"""
    if not stock_code or price <= 0: return None
    try:
        url = f"https://finance.naver.com/item/main.naver?code={str(stock_code).zfill(6)}"
        res = session.get(url, timeout=2)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 데이터 추출 (최대한 가볍게)
        h52, l52, f_rt = price, price, 0.0
        info = soup.select_one(".no_info")
        if info:
            ems = info.select("tr:-soup-contains('52주') em")
            if len(ems) >= 2:
                h52 = int(re.sub(r'[^0-9]', '', ems[0].text))
                l52 = int(re.sub(r'[^0-9]', '', ems[1].text))
        
        # 수급/추세/VCP 계산
        t_sc = ((price - l52) / (h52 - l52)) * 100 if h52 > l52 else 50.0
        v_sc = max(0.0, 100.0 - (((h52 - price) / h52) * 100)) if h52 > 0 else 50.0
        
        score = round((t_sc * 0.5) + (v_sc * 0.5), 1) # 속도를 위해 수급 제외/추세&방어 집중
        color = "#4682B4" if score >= 70 else "#6C7A89"
        
        return {"code": stock_code, "score": score, "color": color}
    except:
        return {"code": stock_code, "score": 0, "color": "#6C7A89"}

@st.cache_data(ttl=120)
def get_all_tcr(stocks_list):
    """병렬 기동: 10개 종목을 동시에 처리"""
    with ThreadPoolExecutor(max_workers=10) as exe:
        results = list(exe.map(lambda x: fetch_data(x[0], x[1]), stocks_list))
    return {r['code']: r for r in results if r}

def get_analysis_legend():
    return """<div style="margin-top:10px; padding:10px; border-top:1px solid #1e293b; color:#6C7A89; font-size:0.75rem;">
        [M01: 초고속 병렬 엔진 V54 가동 중]</div>"""
