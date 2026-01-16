import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from dataclasses import dataclass
from datetime import date
from dateutil.relativedelta import relativedelta

# =============================
# 기본 설정
# =============================
st.set_page_config(page_title="ELS 백테스트 시뮬레이터", layout="wide")
st.title("ELS 백테스트 시뮬레이터")

# 세션 상태 초기화
if 'backtest_result' not in st.session_state:
    st.session_state.backtest_result = None

# 캐시 클리어 버튼
if st.sidebar.button("🔄 캐시 초기화"):
    st.cache_data.clear()
    st.session_state.backtest_result = None
    st.sidebar.success("성공! 데이터가 초기화되었습니다!")
    st.rerun()

TRADING_DAYS_PER_YEAR = 252

# =============================
# 유틸리티 함수
# =============================
def snap_next_trading_day(index: pd.DatetimeIndex, target: pd.Timestamp):
    """
    target 이상의 첫 거래일 반환 (익영업일 원칙)
    ELS 평가일이 휴일이면 다음 영업일로 연기되는 실무 관행 반영
    """
    if not isinstance(target, pd.Timestamp):
        target = pd.Timestamp(target)
    pos = index.searchsorted(target, side="left")
    if pos >= len(index):
        return None
    return index[pos]

# =============================
# 다크모드 가독성용 CSS
# =============================
st.markdown(
    """
    <style>
    /* ... (기존 폰트, 카드 스타일 등은 유지) ... */
    
    @import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.8/dist/web/static/pretendard.css");
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; }
    [data-testid="stHeaderActionElements"] { display: none !important; }

    /* 메인 타이틀 */
    h1 {
        background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800 !important;
        margin-bottom: 0px !important;
    }

    /* 카드 스타일 */
    .card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
    }
    .card h3 {
        margin: 0 0 12px 0;
        font-size: 18px;
        font-weight: 700;
        color: #f0f0f0;
        border-bottom: 1px solid rgba(255,255,255,0.1);
        padding-bottom: 8px;
    }

    /* ★ [수정됨] 요약 박스 (Summary) - 시원시원한 리스트형 ★ */
    .summary {
        background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(79,172,254,0.05) 100%);
        border: 1px solid rgba(79, 172, 254, 0.3);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 20px;
    }
    
    /* 한 줄에 하나씩 (Flex + Bottom Border) */
    .summary-row {
        display: flex;
        justify-content: space-between; /* 양끝 정렬 */
        align-items: center;
        padding: 10px 0; /* 위아래 여백 */
        border-bottom: 1px solid rgba(255,255,255,0.1); /* 구분선 */
    }
    .summary-row:last-child { border-bottom: none; } /* 마지막 줄은 선 없음 */

    /* 라벨 (왼쪽) */
    .summary-label { 
        color: #ccc; 
        font-size: 15px; 
        font-weight: 500;
    }
    
    /* 값 (오른쪽) - 크고 진하게 */
    .summary-val { 
        color: #fff; 
        font-size: 17px; 
        font-weight: 700; 
        text-align: right;
    }

    /* 통계 박스 등 나머지 스타일 유지... */
    .stat-container { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 15px; }
    .stat-box { flex: 1; min-width: 140px; background: rgba(255, 255, 255, 0.05); border-radius: 12px; padding: 15px; text-align: center; border: 1px solid rgba(255,255,255,0.05); }
    .stat-title { font-size: 13px; color: #aaa; margin-bottom: 5px; }
    .stat-value { font-size: 24px; font-weight: 800; color: #4facfe; }
    .stat-sub { font-size: 12px; color: #888; }
    
    /* 기존 테이블 스타일 등... */
    .dist-table { width: 100%; font-size: 14px; text-align: center; border-collapse: collapse; margin-top: 5px; }
    .dist-table td { padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.05); border-right: 1px solid rgba(255,255,255,0.05); }
    .dist-table td:last-child { border-right: none; }
    .dist-header { color: #aaa; font-size: 12px; }
    .dist-val { font-weight: bold; color: #eee; }
    
    div[role="checkbox"] + label { line-height: 1.4; }
    .smalllabel { font-size: 13px; color: #aaa; }
    pre { display: none !important; }
    
    .debug-highlight {
        background: rgba(255, 165, 0, 0.1);
        border-left: 4px solid #ff9f43;
        padding: 12px 16px;
        border-radius: 4px;
        margin: 15px 0;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# =============================
# 기초자산
# =============================
ASSETS = [
    {"name": "S&P500", "ticker": "^GSPC"},
    {"name": "HSCEI", "ticker": "^HSCE"},
    {"name": "HSI", "ticker": "^HSI"},
    {"name": "EURO50", "ticker": "^STOXX50E"},
    {"name": "NIKKEI225", "ticker": "^N225"},
    {"name": "KOSPI", "ticker": "^KS11"},
    {"name": "NASDAQ100", "ticker": "^NDX"},
    {"name": "TSLA", "ticker": "TSLA"},
    {"name": "AMD", "ticker": "AMD"},
    {"name": "NVDA", "ticker": "NVDA"},
    {"name": "PLTR", "ticker": "PLTR"},
    {"name": "MU", "ticker": "MU"},
    {"name": "GOOGL", "ticker": "GOOGL"},
    {"name": "MSFT", "ticker": "MSFT"},
    {"name": "AAPL", "ticker": "AAPL"},
    {"name": "META", "ticker": "META"},
]

# =============================
# ELS 구조
# =============================
@dataclass
class StepDownELS:
    maturity_months: int
    obs_interval_months: int
    early_levels: list
    coupon_annual: float
    knock_in: float

# =============================
# 데이터
# =============================

@st.cache_data(show_spinner=False, ttl=3600)
def download_prices(tickers, start, end):
    try:
        # 1. auto_adjust=False로 설정 (Raw 데이터 확보)
        df = yf.download(tickers, start=start, end=end, auto_adjust=False, progress=False, threads=False)
        
        # 2. 'Adj Close'만 추출 (수정주가 사용)
        if isinstance(df.columns, pd.MultiIndex):
            # 최신 yfinance: (Price, Ticker) 구조
            if "Adj Close" in df.columns.get_level_values(0):
                df = df["Adj Close"]
            elif "Close" in df.columns.get_level_values(0):
                df = df["Close"]
        else:
            # 구버전 또는 단일 티커
            if "Adj Close" in df.columns:
                df = df["Adj Close"]
            elif "Close" in df.columns:
                df = df["Close"]
        
        # 3. Series -> DataFrame 변환
        if isinstance(df, pd.Series):
            df = df.to_frame()
            # 단일 티커일 경우 컬럼명 지정
            if isinstance(tickers, str):
                df.columns = [tickers]
            elif isinstance(tickers, list) and len(tickers) == 1:
                df.columns = tickers

        # 4. [핵심] 컬럼 순서를 요청한 'tickers' 리스트 순서대로 강제 정렬
        # (yfinance는 알파벳순으로 주지만, 우리는 선택한 순서가 필요함)
        if isinstance(tickers, list) and len(tickers) > 1:
            # 데이터에 있는 티커만 추려서 정렬 (없는 티커 에러 방지)
            available_tickers = [t for t in tickers if t in df.columns]
            df = df[available_tickers]

        # 5. 데이터 정리
        df = df.ffill().dropna()
        
        if df.empty:
            return None
            
        return df

    except Exception as e:
        st.error(f"데이터 다운로드 실패: {str(e)}")
        return None
        
# ==========================================
# [추가] 마켓 모니터용 도우미 함수들
# ==========================================
def get_default_ki(ticker):
    """지수(^로 시작)는 40%, 개별종목은 20% 기본값 반환"""
    if ticker.startswith("^"): 
        return 40
    else:
        return 20

def render_mini_chart(series, color_code):
    """미니 차트 그리기"""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=series.index, y=series.values,
        mode='lines', line=dict(color=color_code, width=2), hoverinfo='y'
    ))
    fig.update_layout(
        showlegend=False, margin=dict(l=0, r=0, t=0, b=0), height=50,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(visible=False), yaxis=dict(visible=False)
    )
    return fig
        
# =============================
# 캘린더 기반 관측일 계산
# =============================
def get_observation_dates(start_date, maturity_months, obs_interval_months):
    """캘린더 기반으로 정확한 관측일 계산"""
    obs_dates = []
    n_obs = maturity_months // obs_interval_months
    
    # start_date가 Timestamp가 아니면 변환
    if not isinstance(start_date, pd.Timestamp):
        start_date = pd.Timestamp(start_date)
    
    for i in range(1, n_obs + 1):
        obs_date = start_date + relativedelta(months=i * obs_interval_months)
        # Timestamp로 변환
        obs_date = pd.Timestamp(obs_date)
        obs_dates.append(obs_date)
    
    return obs_dates

# =============================
# 시뮬레이션 (KI 버그 수정)
# =============================
def simulate_els(price_window, els, start_date, return_detail=False):
    """
    ELS 시뮬레이션 (조기상환 케이스도 KI 여부를 올바르게 기록)
    
    return_detail=True면 일별 경로 데이터도 반환
    """
    norm = price_window / price_window.iloc[0]
    
    # 단일 자산이면 DataFrame으로 변환
    if isinstance(norm, pd.Series):
        norm = norm.to_frame()
    
    # worst-of 경로 (일자별, 종가 기준)
    worst_series = norm.min(axis=1)
    
    # early_levels 길이 검증
    n_obs = els.maturity_months // els.obs_interval_months
    if len(els.early_levels) != n_obs:
        raise ValueError(
            f"조기상환 레벨 개수({len(els.early_levels)})가 "
            f"관측 횟수({n_obs})와 일치하지 않습니다."
        )
    
    # 관측일 계산 (캘린더 기반)
    obs_dates = get_observation_dates(start_date, els.maturity_months, els.obs_interval_months)
    
    # 조기상환 체크
    for i, (obs_date, lvl) in enumerate(zip(obs_dates, els.early_levels)):
        # 관측일을 실제 거래일로 스냅 (익영업일 원칙)
        obs_eval = snap_next_trading_day(norm.index, obs_date)
        
        if obs_eval is None:
            # 관측일이 데이터 범위를 벗어남
            break
        
        # 관측일까지의 KI 발생 여부 체크 (중요!)
        ki_up_to_obs = bool((worst_series.loc[:obs_eval] < els.knock_in).any())
        
        # 관측일의 worst 성과
        obs_worst = float(worst_series.loc[obs_eval])
        
        if obs_worst >= float(lvl):
            # 조기상환 성공
            holding_days = (obs_eval - start_date).days
            holding_years = holding_days / 365.25
            payoff = 1.0 + els.coupon_annual * holding_years
            
            if return_detail:
                detail = {
                    "dates": worst_series.index.tolist(),
                    "worst_path": worst_series.values.tolist(),
                    "asset_paths": norm.to_dict('list'),  # 개별 자산 경로 추가
                    "asset_names": norm.columns.tolist(),  # 자산 이름
                    "ki_level": els.knock_in,
                    "ki_touched": ki_up_to_obs,
                    "ki_touch_date": worst_series[worst_series < els.knock_in].index[0] if ki_up_to_obs else None,
                    "redemption_date": obs_eval,
                    "redemption_step": i + 1
                }
                return payoff - 1.0, ki_up_to_obs, i + 1, detail
            
            return payoff - 1.0, ki_up_to_obs, i + 1
    
    # 만기까지 도달 - KI 체크
    ki_occurred = bool((worst_series < els.knock_in).any())
    final_worst = float(worst_series.iloc[-1])
    
    if ki_occurred:
        # 낙인 찍힘 → 손실 확정
        payoff = final_worst
    else:
        # 낙인 안 찍힘 → 원금 + 만기 쿠폰
        maturity_years = els.maturity_months / 12.0
        payoff = 1.0 + els.coupon_annual * maturity_years
    
    if return_detail:
        detail = {
            "dates": worst_series.index.tolist(),
            "worst_path": worst_series.values.tolist(),
            "asset_paths": norm.to_dict('list'),  # 개별 자산 경로 추가
            "asset_names": norm.columns.tolist(),  # 자산 이름
            "ki_level": els.knock_in,
            "ki_touched": ki_occurred,
            "ki_touch_date": worst_series[worst_series < els.knock_in].index[0] if ki_occurred else None,
            "redemption_date": worst_series.index[-1],
            "redemption_step": None
        }
        return payoff - 1.0, ki_occurred, None, detail
    
    return payoff - 1.0, ki_occurred, None

def render_compact_stats(df, els):
    """HTML 기반의 콤팩트한 통계 대시보드 출력"""
    N = len(df)
    win = (df["return"] >= 0).mean() * 100
    avg_return = df["return"].mean() * 100
    median_return = df["return"].median() * 100
    std = df["return"].std() * 100
    
    ki_n = int(df["ki"].sum())
    loss_n = int((df["return"] < 0).sum())
    min_return = df["return"].min() * 100
    min_date = df.loc[df["return"].idxmin(), "start_date"].strftime("%Y-%m-%d")
    
    # 1. 상단 주요 지표 (4개 카드)
    st.markdown(f"""
    <div class="stat-container">
        <div class="stat-box">
            <div class="stat-title">상환 성공률</div>
            <div class="stat-value" style="color: {'#00ff88' if win==100 else '#ff4b4b'}">{win:.1f}%</div>
            <div class="stat-sub">총 {N}건</div>
        </div>
        <div class="stat-box">
            <div class="stat-title">평균 수익률</div>
            <div class="stat-value">{avg_return:.2f}%</div>
            <div class="stat-sub">중위: {median_return:.2f}%</div>
        </div>
        <div class="stat-box">
            <div class="stat-title">낙인(KI) 발생</div>
            <div class="stat-value" style="color: {'#ff4b4b' if ki_n > 0 else '#888'}">{ki_n}건</div>
            <div class="stat-sub">({ki_n/N*100:.1f}%)</div>
        </div>
        <div class="stat-box">
            <div class="stat-title">최악의 수익률</div>
            <div class="stat-value" style="color: {'#ff4b4b' if min_return < 0 else '#ddd'}">{min_return:.2f}%</div>
            <div class="stat-sub">{min_date}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 2. 상환 차수 분포 (가로형 테이블)
    # 데이터를 가로로 배치하여 공간 절약
    cols = []
    vals = []
    
    # 조기상환
    for i in range(1, len(els.early_levels) + 1):
        c = int((df["step"] == i).sum())
        if c > 0: # 0건인 차수는 숨겨서 공간 절약 (원하면 주석 해제)
            cols.append(f"{i}차")
            vals.append(f"{c}<br><span style='font-size:10px; color:#888'>({c/N*100:.1f}%)</span>")
    
    # 만기 상환
    maturity_n = int(df["step"].isna().sum())
    if maturity_n > 0:
        cols.append("만기")
        vals.append(f"{maturity_n}<br><span style='font-size:10px; color:#888'>({maturity_n/N*100:.1f}%)</span>")
        
    # 테이블 HTML 생성
    header_html = "".join([f"<td><div class='dist-header'>{c}</div></td>" for c in cols])
    body_html = "".join([f"<td><div class='dist-val'>{v}</div></td>" for v in vals])
    
    st.markdown(f"""
    <div style="background: rgba(255,255,255,0.03); border-radius: 8px; padding: 10px;">
        <div style="font-size: 13px; font-weight: bold; margin-bottom: 5px; color: #ddd;">📊 상환 차수 분포</div>
        <table class="dist-table">
            <tr>{header_html}</tr>
            <tr>{body_html}</tr>
        </table>
    </div>
    """, unsafe_allow_html=True)

def run_backtest(prices, els, show_progress=False):
    """백테스트 실행 (캘린더 기반, 익영업일 원칙)"""
    rows = []
    
    # 전체 케이스 수 계산 (progress bar용)
    total_cases = 0
    for start_date in prices.index:
        maturity_date = pd.Timestamp(start_date + relativedelta(months=els.maturity_months))
        mat_eval = snap_next_trading_day(prices.index, maturity_date)
        if mat_eval is None:
            break
        total_cases += 1
    
    # Progress bar
    if show_progress:
        progress_bar = st.progress(0)
        progress_text = st.empty()
    
    # 백테스트 실행
    case_idx = 0
    for start_date in prices.index:
        # 만기일 계산 (캘린더 기반)
        maturity_date = pd.Timestamp(start_date + relativedelta(months=els.maturity_months))
        
        # 만기일을 실제 거래일로 스냅 (익영업일 원칙)
        mat_eval = snap_next_trading_day(prices.index, maturity_date)
        
        if mat_eval is None:
            # 만기일이 데이터 범위를 벗어남
            break
        
        if mat_eval < start_date:
            # 논리적 오류 (발생 가능성 낮음)
            continue
        
        # 해당 기간 데이터 추출 (정확하게 스냅된 만기일까지)
        try:
            window = prices.loc[start_date:mat_eval]
        except Exception:
            continue
        
        if len(window) < 10:  # 최소 데이터 체크
            continue
        
        try:
            r, ki, step = simulate_els(window, els, start_date)
            
            rows.append({
                "start_date": start_date,
                "return": r, 
                "ki": ki, 
                "step": step,
                "year": start_date.year
            })
            
            # Progress 업데이트
            case_idx += 1
            if show_progress and case_idx % 10 == 0:  # 10건마다 업데이트
                progress = case_idx / total_cases
                progress_bar.progress(progress)
                progress_text.text(f"백테스트 진행 중... {case_idx}/{total_cases} ({progress*100:.1f}%)")
                
        except Exception:
            # 개별 케이스 오류는 조용히 스킵
            continue
    
    # Progress bar 정리
    if show_progress:
        progress_bar.progress(1.0)
        progress_text.text(f"백테스트 완료! 총 {len(rows)}개 케이스 분석")
        import time
        time.sleep(0.5)
        progress_bar.empty()
        progress_text.empty()
    
    if len(rows) == 0:
        return None
    
    return pd.DataFrame(rows)

# =============================
# 리포트 생성
# =============================
def build_report(df, els):
    N = len(df)
    win = (df["return"] >= 0).mean() * 100
    avg_return = df["return"].mean() * 100
    median_return = df["return"].median() * 100
    
    ki_n = int(df["ki"].sum())
    loss_n = int((df["return"] < 0).sum())
    ki_recovery = int(((df["ki"]) & (df["return"] >= 0)).sum())
    
    # 리스크 지표
    std = df["return"].std() * 100
    min_return = df["return"].min() * 100
    min_return_date = df.loc[df["return"].idxmin(), "start_date"]
    loss_10pct = int((df["return"] < -0.1).sum())
    loss_20pct = int((df["return"] < -0.2).sum())
    
    lines = [
        f"■ 통계 분석 결과 (총 {N}건)",
        f"  • 상환 성공률   : {win:6.2f} %",
        f"  • 평균 수익률   : {avg_return:6.2f} %",
        f"  • 중위 수익률   : {median_return:6.2f} %",
        f"  • 변동성        : {std:6.2f} %",
        "",
        "[ 리스크 지표 ]",
        f"  • 최소 수익률   : {min_return:6.2f} %",
        f"    └ 발생일      : {min_return_date.date()}",
        f"  • 10% 이상 손실 : {loss_10pct:4d} ({loss_10pct/N*100:4.1f}%)",
        f"  • 20% 이상 손실 : {loss_20pct:4d} ({loss_20pct/N*100:4.1f}%)",
        "",
        "[ 낙인(KI) 발생 현황 ]",
        f"  • 낙인 발생     : {ki_n:4d} ({ki_n/N*100:4.1f}%)",
        f"  • 원금 손실 확정 : {loss_n:4d} ({loss_n/N*100:4.1f}%)",
        f"  • 낙인 후 회복   : {ki_recovery:4d} ({ki_recovery/N*100:4.1f}%)",
        "",
        "[ 상환 차수 분포 ]"
    ]
    
    for i in range(1, len(els.early_levels) + 1):
        c = int((df["step"] == i).sum())
        lines.append(f"  • {i}차 조기상환 : {c:4d} ({c/N*100:4.1f}%)")
    
    maturity = int(df["step"].isna().sum())
    lines.append(f"  • 만기상환     : {maturity:4d} ({maturity/N*100:4.1f}%)")
    
    return "\n".join(lines)

def build_yearly_report(df):
    """연도별 성과 분석"""
    yearly = df.groupby("year").agg({
        "return": ["mean", "median", "std", "count"],
        "ki": "sum"
    }).round(4)
    
    yearly.columns = ["평균 수익률", "중위 수익률", "변동성", "샘플 수", "낙인 발생"]
    yearly["평균 수익률"] = (yearly["평균 수익률"] * 100).round(2)
    yearly["중위 수익률"] = (yearly["중위 수익률"] * 100).round(2)
    yearly["변동성"] = (yearly["변동성"] * 100).round(2)
    yearly["상환 성공률(%)"] = df.groupby("year").apply(lambda x: (x["return"] >= 0).mean() * 100).round(2)
    
    return yearly

# =============================
# 시각화
# =============================
def plot_return_distribution(df):
    """수익률 분포 히스토그램"""
    fig = go.Figure()
    
    returns_pct = df["return"] * 100
    
    fig.add_trace(go.Histogram(
        x=returns_pct,
        nbinsx=50,
        name="Return Distribution",
        marker_color="rgba(99, 110, 250, 0.7)",
        hovertemplate="Return: %{x:.2f}%<br>Count: %{y}<extra></extra>"
    ))
    
    avg = returns_pct.mean()
    fig.add_vline(x=avg, line_dash="dash", line_color="red", 
                  annotation_text=f"평균: {avg:.2f}%", annotation_position="top")
    
    fig.add_vline(x=0, line_dash="dot", line_color="white", 
                  annotation_text="손익분기", annotation_position="bottom")
    
    fig.update_layout(
        title="수익률 분포",
        xaxis_title="수익률 (%)",
        yaxis_title="빈도",
        showlegend=False,
        height=400,
        template="plotly_dark"
    )
    
    return fig

def plot_yearly_performance(df):
    """연도별 성과"""
    yearly_avg = df.groupby("year")["return"].mean() * 100
    yearly_win = df.groupby("year").apply(lambda x: (x["return"] >= 0).mean() * 100)
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=yearly_avg.index,
        y=yearly_avg.values,
        name="평균 수익률",
        marker_color="rgba(99, 110, 250, 0.8)",
        yaxis="y1",
        hovertemplate="연도: %{x}<br>평균 수익률: %{y:.2f}%<extra></extra>"
    ))
    
    fig.add_trace(go.Scatter(
        x=yearly_win.index,
        y=yearly_win.values,
        name="상환 성공률",
        mode="lines+markers",
        marker=dict(size=8, color="orange"),
        line=dict(width=2, color="orange"),
        yaxis="y2",
        hovertemplate="연도: %{x}<br>상환 성공률: %{y:.1f}%<extra></extra>"
    ))
    
    fig.update_layout(
        title="연도별 성과",
        xaxis_title="연도",
        yaxis=dict(title="평균 수익률 (%)", side="left"),
        yaxis2=dict(title="상환 성공률 (%)", side="right", overlaying="y", range=[0, 100]),
        height=400,
        template="plotly_dark",
        hovermode="x unified"
    )
    
    return fig

def plot_step_distribution(df, els):
    """조기상환 차수 분포"""
    step_counts = []
    labels = []
    
    for i in range(1, len(els.early_levels) + 1):
        count = (df["step"] == i).sum()
        step_counts.append(count)
        labels.append(f"{i}차")
    
    maturity_count = df["step"].isna().sum()
    step_counts.append(maturity_count)
    labels.append("만기")
    
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=step_counts,
        hole=0.4,
        marker=dict(colors=px.colors.qualitative.Set3),
        textinfo='label+percent',
        hovertemplate="<b>%{label}</b><br>횟수: %{value}<br>비율: %{percent}<extra></extra>"
    )])
    
    fig.update_layout(
        title="조기상환 차수 분포",
        height=400,
        template="plotly_dark"
    )
    
    return fig

def plot_single_case_path(detail, start_date):
    """
    [수정] 낙인 여부와 상관없이 'Worst-of' 라인을 항상 그려서
    만기 시점의 진짜 수익률 위치를 시각적으로 확인하도록 개선
    """
    fig = go.Figure()
    
    dates = detail["dates"]
    worst_path = [x * 100 for x in detail["worst_path"]] # 이것이 실제 평가 기준선
    ki_level = detail["ki_level"] * 100
    
    asset_paths = detail.get("asset_paths", {})
    
    # 1. 개별 자산들 흐리게 그리기 (배경)
    colors = ['#FFA07A', '#98FB98', '#87CEFA'] # 연한 색상들
    for i, (name, path) in enumerate(asset_paths.items()):
        path_pct = [x * 100 for x in path]
        fig.add_trace(go.Scatter(
            x=dates, y=path_pct,
            mode='lines',
            name=name,
            line=dict(width=1, dash='dot'), # 점선으로 얇게
            opacity=0.7
        ))

    # 2. Worst-of 라인 (진한 파란색) - 이것이 진짜 내 돈의 운명
    fig.add_trace(go.Scatter(
        x=dates, y=worst_path,
        mode='lines',
        name='Worst-of (평가 기준)',
        line=dict(color='white', width=3), # 흰색 굵은 실선 (다크모드용)
        hovertemplate="<b>Worst-of</b><br>날짜: %{x}<br>성과: %{y:.2f}%<extra></extra>"
    ))
    
    # 3. 낙인 배리어
    fig.add_hline(
        y=ki_level, line_dash="dash", line_color="red", line_width=2,
        annotation_text=f"낙인 {ki_level:.0f}%", annotation_position="right"
    )
    
    # 4. 원금 기준선
    fig.add_hline(y=100, line_color="gray", line_width=1)
    
    # 5. 낙인 발생 지점 (X 표시)
    if detail["ki_touched"] and detail["ki_touch_date"]:
        ki_date = detail["ki_touch_date"]
        try:
            ki_idx = dates.index(ki_date)
            ki_val = worst_path[ki_idx]
            fig.add_trace(go.Scatter(
                x=[ki_date], y=[ki_val],
                mode='markers',
                name='낙인 발생',
                marker=dict(color='red', size=12, symbol='x-open', line=dict(width=3)),
            ))
        except: pass
        
    # 6. 상환 지점 (별표)
    redemption_date = detail["redemption_date"]
    try:
        redemption_idx = dates.index(redemption_date)
        redemption_val = worst_path[redemption_idx]
        
        # 만기 시점의 Worst 값이 낙인 배리어보다 높은지 낮은지 확인
        is_happy_ending = (redemption_val >= ki_level) if detail["ki_touched"] else True
        # ※ 주의: 낙인을 이미 터치했다면, 만기 때 조기상환 배리어(보통 70~80)를 넘어야 함.
        # 시각적 편의를 위해 수익(+)이면 초록, 손실(-)이면 빨강으로 표시
        final_return = redemption_val - 100
        marker_color = '#00ff00' if final_return >= 0 else '#ff0000'
        
        fig.add_trace(go.Scatter(
            x=[redemption_date], y=[redemption_val],
            mode='markers+text',
            name='최종 상환',
            text=[f"{redemption_val:.1f}%"],
            textposition="top center",
            marker=dict(color=marker_color, size=15, symbol='star'),
        ))
    except: pass

    fig.update_layout(
        title=f"케이스 상세: {start_date.date()} 발행 (Worst-of 기준)",
        xaxis_title="날짜", yaxis_title="성과 (%)",
        height=500, template="plotly_dark", hovermode="x unified"
    )
    
    return fig

# =============================
# UI
# =============================
left, right = st.columns([1.1, 1.9], gap="large")

LEVEL_OPTIONS = [100, 95, 90, 85, 80, 75, 70, 65, 60, 50]

with left:
    # Underlying card
    st.markdown('<div class="card"><h3>① 기초자산 선택 (최대 3개)</h3>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    selected = []
    half = (len(ASSETS) + 1) // 2
    
    # 선택 개수 체크를 위한 임시 카운터
    temp_selected = []
    for i, a in enumerate(ASSETS):
        col = c1 if i < half else c2
        # 이미 3개 선택되었으면 비활성화
        is_disabled = len(temp_selected) >= 3 and a not in temp_selected
        if col.checkbox(a["name"], key=a["ticker"], disabled=is_disabled):
            temp_selected.append(a)
    
    selected = temp_selected
    if len(selected) > 3:
        st.error("기초자산은 최대 3개까지 선택 가능합니다.")
    st.markdown("</div>", unsafe_allow_html=True)

    # Structure card
    st.markdown('<div class="card"><h3>② 상품 구조 및 상환 조건</h3>', unsafe_allow_html=True)

    r1c1, r1c2 = st.columns(2)
    maturity = r1c1.number_input("만기 (개월)", min_value=6, max_value=60, value=36, step=1)
    obs = r1c2.number_input("평가 주기 (개월)", min_value=1, max_value=12, value=6, step=1, help="조기상환 평가 간격 (보통 6개월)")

    n_steps = maturity // obs
    if n_steps <= 0:
        n_steps = 1

    st.caption("차수별 상환 기준을 설정합니다 (중복 가능)")

    # 단계별 selectbox
    step_cols = st.columns(min(6, n_steps))
    early_levels = []
    default_levels = [95, 90, 85, 80, 75, 70]
    for i in range(n_steps):
        col = step_cols[i % len(step_cols)]
        col.markdown(f'<div class="smalllabel">{i+1}차</div>', unsafe_allow_html=True)
        
        default_val = default_levels[i] if i < len(default_levels) else default_levels[-1]
        default_idx = LEVEL_OPTIONS.index(default_val) if default_val in LEVEL_OPTIONS else 0
        
        lvl = col.selectbox(
            label="",
            options=LEVEL_OPTIONS,
            index=default_idx,
            key=f"step_lvl_{i}"
        )
        early_levels.append(lvl / 100.0)

    r2c1, r2c2 = st.columns(2)
    coupon = r2c1.number_input(
        "제시 수익률 (연 %)",
        min_value=0.0,
        max_value=30.0,
        value=8.0,
        step=0.1,
        format="%.1f",
        help="조기상환 시 지급되는 연간 수익률"
    )
    ki = r2c2.number_input(
        "낙인 배리어 (KI, %)", 
        min_value=1, 
        max_value=99, 
        value=40, 
        step=1,
        help="원금손실 기준선 - 이 수준 아래로 떨어지면 낙인 발생"
    )

    lookback = st.slider("과거 데이터 분석 기간 (년)", 3, 25, 15)

    st.markdown("</div>", unsafe_allow_html=True)

    run = st.button(
        "백테스트 실행하기",
        type="primary",
        use_container_width=True,
        disabled=(len(selected) == 0)
    )

with right:
    # Compact Summary card
    tab1, tab2 = st.tabs(["📊 백테스트 분석", "🌍 마켓 모니터 (New)"])

    with tab1:
        if selected:
            underlying_txt = " / ".join(a["name"] for a in selected)
            steps_txt = "-".join(str(int(x * 100)) for x in early_levels)
            
            st.markdown(f"""
            <div class="summary">
                <div style="font-size:15px; font-weight:700; margin-bottom:8px; color:#e0e0e0;">⚙️ 설정 요약</div>
                <div class="summary-row">
                    <div><span class="summary-label">기초자산:</span><span class="summary-val">{underlying_txt}</span></div>
                    <div><span class="summary-label">수익률:</span><span class="summary-val" style="color:#4facfe">{coupon:.1f}%</span></div>
                </div>
                <div class="summary-row">
                    <div><span class="summary-label">구조:</span><span class="summary-val">{maturity}M / {obs}M ({n_steps}회)</span></div>
                    <div><span class="summary-label">낙인:</span><span class="summary-val" style="color:#ff6b6b">{ki}%</span></div>
                </div>
                <div style="margin-top:4px; font-size:13px; color:#aaa;">
                    <span class="summary-label">상환조건:</span> {steps_txt}
                </div>
            </div>
            """, unsafe_allow_html=True)
    
        if run:
            tickers = [a["ticker"] for a in selected]
            names = [a["name"] for a in selected]
    
            end = date.today()
            start = date(end.year - lookback, end.month, end.day)
    
            with st.spinner("Downloading data..."):
                prices = download_prices(tickers, start, end)
                
            if prices is None or prices.empty:
                st.error("데이터를 가져올 수 없습니다. 티커를 확인하거나 기간을 조정해주세요.")
            else:
                prices.columns = names
    
                els = StepDownELS(
                    maturity_months=maturity,
                    obs_interval_months=obs,
                    early_levels=early_levels,
                    coupon_annual=coupon / 100.0,
                    knock_in=ki / 100.0
                )
    
                with st.spinner("Running backtest..."):
                    try:
                        df = run_backtest(prices, els, show_progress=True)
                    except Exception as e:
                        st.error(f"백테스트 실행 중 오류: {str(e)}")
                        import traceback
                        st.code(traceback.format_exc())
                        df = None
                
                if df is not None and not df.empty:
                    # Session State에 저장
                    st.session_state.backtest_result = {
                        'df': df,
                        'prices': prices,
                        'els': els,
                        'maturity': maturity,
                        'start': start,
                        'end': end
                    }
        
        # Session State에서 결과 불러오기
        if st.session_state.backtest_result is not None:
            result = st.session_state.backtest_result
            df = result['df']
            prices = result['prices']
            els = result['els']
            maturity = result['maturity']
            start = result.get('start')
            end = result.get('end')
            
            if df is not None and not df.empty:
                    # 데이터 확인 expander - 탭과 무관하게 항상 표시
                    with st.expander("📊 다운로드된 데이터 확인", expanded=False):
                        if start and end:
                            st.write(f"**요청 기간**: {start} ~ {end}")
                        st.write(f"**실제 기간**: {prices.index[0].date()} ~ {prices.index[-1].date()}")
                        st.write(f"**총 거래일**: {len(prices)}일")
                        
                        # 실제 가격 차트만 표시 (비율 기준 Y축 분리)
                        fig = go.Figure()
                        
                        # 가격 범위 계산
                        price_ranges = {}
                        for col in prices.columns:
                            avg_price = prices[col].mean()
                            price_ranges[col] = avg_price
                        
                        # 최대/최소 가격
                        max_price = max(price_ranges.values())
                        min_price = min(price_ranges.values())
                        ratio = max_price / min_price if min_price > 0 else 1
                        
                        # 비율이 3배 이상 차이나면 Y축 분리
                        if ratio > 3.0 and len(prices.columns) > 1:
                            # 중간값 기준으로 분리
                            threshold = (max_price + min_price) / 2
                            
                            y1_cols = [col for col, price in price_ranges.items() if price >= threshold]
                            y2_cols = [col for col, price in price_ranges.items() if price < threshold]
                            
                            # Y1 축 데이터 (고가)
                            for col in y1_cols:
                                fig.add_trace(go.Scatter(
                                    x=prices.index,
                                    y=prices[col],
                                    mode='lines',
                                    name=f"{col} (좌)",
                                    yaxis='y1',
                                    hovertemplate=f"{col}<br>날짜: %{{x}}<br>가격: %{{y:,.2f}}<extra></extra>"
                                ))
                            
                            # Y2 축 데이터 (저가)
                            for col in y2_cols:
                                fig.add_trace(go.Scatter(
                                    x=prices.index,
                                    y=prices[col],
                                    mode='lines',
                                    name=f"{col} (우)",
                                    yaxis='y2',
                                    line=dict(dash='dot'),
                                    hovertemplate=f"{col}<br>날짜: %{{x}}<br>가격: %{{y:,.2f}}<extra></extra>"
                                ))
                            
                            fig.update_layout(
                                title="기초자산 가격",
                                xaxis_title="날짜",
                                yaxis=dict(
                                    title=f"가격",
                                    side="left"
                                ),
                                yaxis2=dict(
                                    title=f"가격",
                                    side="right",
                                    overlaying="y"
                                ),
                                height=400,
                                template="plotly_dark",
                                hovermode="x unified",
                                legend=dict(
                                    orientation="h",
                                    yanchor="bottom",
                                    y=1.02,
                                    xanchor="right",
                                    x=1
                                )
                            )
                        else:
                            # 비슷한 가격대 - Y축 1개만 사용
                            for col in prices.columns:
                                fig.add_trace(go.Scatter(
                                    x=prices.index,
                                    y=prices[col],
                                    mode='lines',
                                    name=col,
                                    hovertemplate=f"{col}<br>날짜: %{{x}}<br>가격: %{{y:,.2f}}<extra></extra>"
                                ))
                            
                            fig.update_layout(
                                title="기초자산 가격",
                                xaxis_title="날짜",
                                yaxis_title="가격",
                                height=400,
                                template="plotly_dark",
                                hovermode="x unified"
                            )
                        
                        st.plotly_chart(fig, use_container_width=True)
                        
                        # 통계 테이블
                        stats = pd.DataFrame({
                            "시작가": prices.iloc[0],
                            "종가": prices.iloc[-1],
                            "최고가": prices.max(),
                            "최저가": prices.min(),
                            "수익률(%)": ((prices.iloc[-1] / prices.iloc[0] - 1) * 100).round(2)
                        })
                        st.dataframe(stats)
                    
                    # 통계 리포트
                    render_compact_stats(df, els)
                    
                    # 차트들 - on_change로 탭 위치 저장
                    selected_tab = st.radio(
                        "분석 항목 선택",
                        options=["📊 수익률 분포", "📈 연도별 성과", "🥧 상환 차수", "📋 연도별 테이블", "🔍 케이스 분석"],
                        horizontal=True,
                        key="selected_tab_radio",
                        label_visibility="collapsed"
                    )
                    
                    if selected_tab == "📊 수익률 분포":
                        st.plotly_chart(plot_return_distribution(df), use_container_width=True)
                    
                    elif selected_tab == "📈 연도별 성과":
                        st.plotly_chart(plot_yearly_performance(df), use_container_width=True)
                    
                    elif selected_tab == "🥧 상환 차수":
                        st.plotly_chart(plot_step_distribution(df, els), use_container_width=True)
                    
                    elif selected_tab == "📋 연도별 테이블":
                        yearly_report = build_yearly_report(df)
                        st.dataframe(yearly_report, use_container_width=True)
                    
                    elif selected_tab == "🔍 케이스 분석":
                        st.markdown("### 🔍 특정 발행일 케이스 분석")
                        st.markdown('<div class="debug-highlight">', unsafe_allow_html=True)
                        st.caption("특정 날짜에 발행된 ELS의 전체 경로를 분석합니다. 낙인 터치 시점, 조기상환/만기상환 여부 등을 확인할 수 있습니다.")
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # 빠른 선택 옵션
                        col1, col2 = st.columns([1, 1])
                        
                        with col1:
                            quick_select = st.selectbox(
                                "빠른 선택",
                                options=["첫 번째 날짜", "최대 손실 케이스", "최초 KI 케이스", "직접 입력"],
                                index=0,
                                key="quick_select_case"
                            )
                        
                        # 빠른 선택에 따라 날짜 결정
                        if quick_select == "첫 번째 날짜":
                            selected_date = df["start_date"].iloc[0]
                        elif quick_select == "최대 손실 케이스" and len(df[df["return"] < 0]) > 0:
                            worst_case = df.loc[df["return"].idxmin()]
                            selected_date = worst_case["start_date"]
                        elif quick_select == "최초 KI 케이스" and len(df[df["ki"]]) > 0:
                            selected_date = df[df["ki"]]["start_date"].iloc[0]
                        else:  # 직접 입력
                            with col2:
                                # 연-월-일 분리 입력
                                date_col1, date_col2, date_col3 = st.columns(3)
                                
                                # 사용 가능한 연도 범위
                                min_year = df["start_date"].min().year
                                max_year = df["start_date"].max().year
                                
                                year = date_col1.number_input(
                                    "연도",
                                    min_value=min_year,
                                    max_value=max_year,
                                    value=2021,
                                    step=1,
                                    key="input_year"
                                )
                                
                                month = date_col2.number_input(
                                    "월",
                                    min_value=1,
                                    max_value=12,
                                    value=2,
                                    step=1,
                                    key="input_month"
                                )
                                
                                day = date_col3.number_input(
                                    "일",
                                    min_value=1,
                                    max_value=31,
                                    value=1,
                                    step=1,
                                    key="input_day"
                                )
                                
                                try:
                                    selected_date = pd.Timestamp(year=year, month=month, day=day)
                                except:
                                    st.error("유효하지 않은 날짜입니다.")
                                    selected_date = df["start_date"].iloc[0]
                        
                        # 선택된 날짜 표시
                        st.info(f"📅 선택된 발행일: **{selected_date.date()}**")
                        
                        # 선택된 날짜로 시뮬레이션
                        # 발행일을 실제 거래일로 스냅
                        start_eval = snap_next_trading_day(prices.index, selected_date)
                        
                        if start_eval is None:
                            st.warning(f"선택한 날짜({selected_date.date()}) 이후에 거래일이 없습니다.")
                        else:
                            if start_eval != selected_date:
                                st.caption(f"💡 {selected_date.date()}는 거래일이 아니므로 다음 거래일({start_eval.date()})로 분석합니다.")
                            
                            maturity_date = pd.Timestamp(start_eval + relativedelta(months=maturity))
                            mat_eval = snap_next_trading_day(prices.index, maturity_date)
                            
                            if mat_eval is None:
                                st.warning(f"만기일({maturity_date.date()})이 데이터 범위를 벗어납니다.")
                            else:
                                try:
                                    window = prices.loc[start_eval:mat_eval]
                                    
                                    r, ki, step, detail = simulate_els(window, els, start_eval, return_detail=True)
                                    
                                    # 결과 요약
                                    st.markdown("#### 📋 케이스 요약")
                                    col1, col2, col3, col4 = st.columns(4)
                                    
                                    col1.metric("수익률", f"{r*100:+.2f}%")
                                    col2.metric("낙인 터치", "예" if ki else "아니오", delta="Recovery" if (ki and r >= 0) else None)
                                    col3.metric("상환 방식", f"{step}차 조기" if step else "만기")
                                    col4.metric("상환일", str(detail["redemption_date"].date()))
                                    
                                    if detail["ki_touched"]:
                                        st.warning(f"⚠️ 낙인 터치: {detail['ki_touch_date'].date()} (최저 {min(detail['worst_path'])*100:.2f}%)")
                                    
                                    # 경로 차트
                                    st.plotly_chart(plot_single_case_path(detail, start_eval), use_container_width=True)
                                except Exception as e:
                                    st.error(f"시뮬레이션 오류: {str(e)}")
                                    import traceback
                                    st.code(traceback.format_exc())
            else:
                st.error("백테스트 결과가 없습니다.")
        else:
    
            st.info("왼쪽에서 조건을 설정하고 실행하세요.")
    
    with tab2:
        st.markdown("### 🌍 글로벌 마켓 상세 모니터 (KI 시뮬레이션)")
        st.caption("실시간 시세를 조회하고, 내가 설정한 낙인(KI) 가격을 계산합니다.")

        # 새로고침 버튼
        if st.button("🔄 최신 데이터 불러오기", type="primary", key="refresh_market"):
            monitor_tickers = [a["ticker"] for a in ASSETS]
            m_start = date.today() - relativedelta(days=400)
            m_end = date.today()
            
            with st.spinner("시장 데이터 분석 중..."):
                # threads=False 옵션은 download_prices 함수 안에 이미 적용되어 있어야 합니다.
                m_df = download_prices(monitor_tickers, m_start, m_end)
                
            if m_df is not None:
                m_df = m_df.ffill()
                
                # 4열 그리드 배치
                cols = st.columns(4)
                
                for idx, asset in enumerate(ASSETS):
                    ticker = asset["ticker"]
                    name = asset["name"]
                    
                    if ticker in m_df.columns:
                        series = m_df[ticker].dropna()
                        if len(series) < 2: continue
                        
                        # 데이터 계산
                        last_price = series.iloc[-1]
                        prev_price = series.iloc[-2]
                        chg_pct = (last_price - prev_price) / prev_price * 100
                        
                        high_52 = series.max()
                        low_52 = series.min()
                        pos = (last_price - low_52) / (high_52 - low_52) * 100
                        
                        # 색상
                        chart_color = "#00ff88" if chg_pct >= 0 else "#ff4b4b"
                        arrow = "▲" if chg_pct >= 0 else "▼"
                        color_cls = "up" if chg_pct >= 0 else "down"
                        
                        # 카드 그리기
                        with cols[idx % 4]:
                            st.markdown(f"""
                            <div class="metric-card" style="margin-bottom:5px;">
                                <div style="font-size:14px; font-weight:bold; color:#ddd;">{name}</div>
                                <div style="font-size:11px; color:#888;">{ticker}</div>
                                <div style="margin: 8px 0;">
                                    <span style="font-size:22px; font-weight:bold; color:#fff;">{last_price:,.2f}</span>
                                    <span class="{color_cls}" style="font-size:13px; font-weight:bold; margin-left:5px;">{arrow} {chg_pct:.2f}%</span>
                                </div>
                                <div style="width:100%; height:4px; background:#333; margin-top:5px;">
                                    <div style="width:{pos}%; height:100%; background:linear-gradient(90deg, #4facfe, #00f2fe);"></div>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # [핵심] 낙인 입력 및 계산 로직
                            default_ki = get_default_ki(ticker) # 지수 40, 종목 20 자동 선택
                            
                            c_input, c_val = st.columns([1, 1.3])
                            with c_input:
                                user_ki = st.number_input("낙인(%)", value=default_ki, step=5, key=f"ki_{ticker}", label_visibility="collapsed")
                            with c_val:
                                ki_price = last_price * (user_ki / 100.0)
                                st.markdown(f"<div style='text-align:right; color:#ff6b6b; font-weight:bold; font-size:15px; padding-top:5px;'>KI: {ki_price:,.0f}</div>", unsafe_allow_html=True)

                            # 미니 차트
                            mini_data = series.iloc[-120:]
                            fig = render_mini_chart(mini_data, chart_color)
                            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                            st.markdown("---")
            else:
                st.error("데이터 로딩 실패")
        else:
            st.info("버튼을 눌러 데이터를 조회하세요.")

