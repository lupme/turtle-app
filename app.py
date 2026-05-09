import requests
from bs4 import BeautifulSoup
import streamlit as st
import re
from concurrent.futures import ThreadPoolExecutor

def fetch_single_stock(stock_code, current_price):
    """개별 종목 실시간 데이터를 파싱하는 일꾼 함수"""
    if not stock_code or current_price <= 0:
        return None
    try:
        clean_code = str(stock_code).zfill(6)
        url = f"https://finance.naver.com/item/main.naver?code={clean_code}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        high52, low52, frgn_rate = current_price, current_price, 0.0
        info = soup.select_one(".no_info")
        if info:
            for tr in info.find_all("tr"):
                if "52주" in tr.text:
                    ems = tr.find_all("em")
                    if len(ems) >= 2:
                        high52 = int(re.sub(r'[^0-9]', '', ems[0].text))
                        low52 = int(re.sub(r'[^0-9]', '', ems[1].text))
                    break
        th_tags = soup.find_all('th')
        for th in th_tags:
            if "외국인소진율" in th.text:
                td = th.find_next_sibling('td')
                if td and td.find('em'):
                    frgn_rate = float(re.sub(r'[^0-9.]', '', td.find('em').text))
                break
        
        t_score = ((current_price - low52) / (high52 - low52)) * 100 if high52 > low52 else 50.0
        f_score = min(100.0, 40.0 + (frgn_rate * 1.5))
        v_score = max(0.0, 100.0 - (((high52 - current_price) / high52) * 100)) if high52 > 0 else 50.0
        
        score = round((f_score * 0.4) + (t_score * 0.4) + (v_score * 0.2), 1)
        det = f"수급:{f_score:.0f} 추세:{t_score:.0f} VCP:{v_score:.0f}"
        if score >= 75: col, stt = "#4682B4", f"강력 기동 [{det}]"
        elif score <= 40: col, stt = "#ef4444", f"OCP 작동 [{det}]"
        else: col, stt = "#6C7A89", f"추세 관찰 [{det}]"
        
        return {"code": stock_code, "score": score, "status": stt, "color": col}
    except:
        return {"code": stock_code, "score": 0, "status": "데이터 오류", "color": "#6C7A89"}

@st.cache_data(ttl=300)
def get_bulk_tcr_map(stocks_list):
    """전체 종목을 병렬로 긁어온 뒤 딕셔너리로 반환 (속도 혁신)"""
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda x: fetch_single_stock(x[0], x[1]), stocks_list))
    # 종목코드를 키(Key)로 하는 맵 생성하여 데이터 꼬임 방지
    return {res['code']: res for res in results if res is not None}

def get_analysis_legend():
    return """<div style="margin-top:10px; padding:15px; border-top:1px solid #1e293b; border-radius:8px;">
        <p style="color:#6C7A89; font-size:0.8rem; font-weight:700;">[M01: T-Q 병렬 엔진 V53]</p>
        <p style="color:#6C7A89; font-size:0.75rem;">* 실시간 수급(40%) + 추세(40%) + 방어(20%) 가중 평균 / 병렬 기동 방식</p></div>"""
