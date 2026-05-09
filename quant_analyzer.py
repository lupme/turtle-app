import pandas as pd

def get_tcr_score(stock_code: str, current_price: int) -> dict:
    """
    [M01: T-Q Engine] 거북이 확신율(TCR) 분석 로직
    """
    # 1. 데이터 무결성 검증 (값이 없으면 즉시 종료)
    if not stock_code or current_price <= 0:
        return {"score": 0, "status": "데이터 부족", "color": "text-gray"}

    # 2. 임시 데이터 생성 (추후 실제 네이버 수급/차트 데이터 연동 예정)
    # 현재는 모듈이 잘 작동하는지 테스트하기 위한 임의의 점수입니다.
    flow_score = 85.0   # 수급(외국인/기관) 점수
    trend_score = 80.0  # 추세(이동평균선) 점수
    vcp_score = 70.0    # 변동성 수축 점수

    # 3. 가중 평균(Weighted Mean) 연산
    tcr_score = (flow_score * 0.4) + (trend_score * 0.4) + (vcp_score * 0.2)
    tcr_score = round(tcr_score, 1)

    # 4. 판독 및 규격 색상(Slate Gray, Steel Blue) 적용
    if tcr_score >= 80:
        status = "강력 기동 (매수 후보)"
        color = "#4682B4" # Steel Blue
    elif tcr_score <= 30:
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
        <p style="color: #6C7A89; font-size: 0.8rem; font-weight: 700; margin-bottom: 5px;">[M01: T-Q Engine 범례 - Weighted Mean Formula]</p>
        <p style="color: #6C7A89; font-size: 0.75rem; margin: 0;">* 거북이 확신율(%) = (수급 × 0.4) + (추세 × 0.4) + (VCP 변동성 × 0.2)</p>
    </div>
    """
