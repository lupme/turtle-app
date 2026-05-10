import pandas as pd
import requests
from bs4 import BeautifulSoup
import streamlit as st
import re

@st.cache_data(ttl=300)
def fetch_quant_data(stock_code: str, current_price: int):
    if not stock_code or current_price <= 0:
        return 50.0, 50.0, 50.0
        
    clean_code = str(stock_code).zfill(6)
    try:
        url = f"https://finance.naver.com/item/main.naver?code={clean_code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
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
        
        frgn_rate = 0.0
        th_tags = soup.find_all('th')
        for th in th_tags:
            if "외국인소진율" in th.text:
                td = th.find_next_sibling('td')
                if td and td.find('em'):
                    frgn_rate = float(re.sub(r'[^0-9.]', '', td.find('em').text))
                break

        trend_score = ((current_price - low52) / (high52 - low52)) * 100 if high52 > low52 else 50.0
        flow_score = min(100.0, 40.0 + (frgn_rate * 1.5))
        vcp_score = max(0.0, 100.0 - (((high52 - current_price) / high52) * 100)) if high52 > 0 else 50.0
            
        return round(flow_score, 1), round(trend_score, 1), round(vcp_score, 1)
    except:
        return 50.0, 50.0, 50.0

def get_tcr_score(stock_code: str, current_price: int) -> dict:
    if not stock_code or current_price <= 0:
        return {"score": 0, "status": "데이터 부족", "color": "text-gray"}

    f_s, t_s, v_s = fetch_quant_data(stock_code, current_price)
    tcr_score = round((f_s * 0.4) + (t_s * 0.4) + (v_s * 0.2), 1)
    detail = f"수급:{f_s:.0f} 추세:{t_s:.0f} VCP:{v_s:.0f}"

    if tcr_score >= 75: col, stt = "#4682B4", f"강력 기동 [{detail}]"
    elif tcr_score <= 40: col, stt = "#ef4444", f"OCP 작동 [{detail}]"
    else: col, stt = "#6C7A89", f"추세 관찰 [{detail}]"

    return {"score": tcr_score, "status": stt, "color": col}

def get_analysis_legend() -> str:
    return """<div style="margin-top: 10px; padding: 15px; border-top: 1px solid #1e293b; border-radius: 8px;">
        <p style="color: #6C7A89; font-size: 0.8rem; font-weight: 700; margin-bottom: 5px;">[M01: T-Q Engine Baseline V47.0]</p>
        <p style="color: #6C7A89; font-size: 0.75rem; margin: 0;">* 외국인수급(40%) + 52주추세(40%) + VCP방어력(20%)</p></div>"""
