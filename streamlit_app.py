import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
from zoneinfo import ZoneInfo
import pyupbit
import os
from dotenv import load_dotenv

# 데이터베이스 연결
def get_database_connection():
    return sqlite3.connect('trading_log.db')

def initialize_database():
    conn = get_database_connection()
    cursor = conn.cursor()
    
    # asset_status 테이블 생성 (XRP 포함)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS asset_status (
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        btc_balance REAL,
        xrp_balance REAL,
        krw_balance REAL,
        current_btc_price REAL,
        current_xrp_price REAL
    )
    """)
    
    # trade_log 테이블 생성
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trade_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_type TEXT,
        amount REAL,
        price REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        confidence_score INTEGER,
        reasoning TEXT,
        rsi REAL,
        volatility REAL,
        strategy_type TEXT
    )
    """)
    
    # gpt_advice_log 테이블 생성
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gpt_advice_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        trade_recommendation TEXT,
        investment_percentage INTEGER,
        confidence_score INTEGER,
        reasoning TEXT,
        market_state TEXT
    )
    """)
    
    conn.commit()
    conn.close()

# 앱 시작 시 데이터베이스 초기화
initialize_database()

# .env 파일 로드
load_dotenv()

# Upbit API 키 설정
ACCESS_KEY = os.getenv('UPBIT_ACCESS_KEY')
SECRET_KEY = os.getenv('UPBIT_SECRET_KEY')

# Upbit 객체 초기화
upbit = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)

# 페이지 기본 설정
st.set_page_config(
    page_title="Crypto Trading Dashboard",
    page_icon="📊",
    layout="wide"
)

# 스타일 설정
st.markdown("""
    <style>
    .big-font {
        font-size:24px !important;
        font-weight: bold;
    }
    .medium-font {
        font-size:18px !important;
    }
    .metric-card {
        background-color: #1e293b;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        color: #ffffff;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .metric-card .big-font {
        color: #ffffff;
        margin-bottom: 10px;
    }
    .metric-card .medium-font {
        color: #94a3b8;
    }
    </style>
    """, unsafe_allow_html=True)


# 데이터베이스 초기화 함수
def initialize_database():
    conn = get_database_connection()
    cursor = conn.cursor()
    
    # asset_status 테이블 생성
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS asset_status (
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        btc_balance REAL,
        krw_balance REAL,
        current_btc_price REAL
    )
    """)
    
    conn.commit()
    conn.close()

# 자산 정보 로드 함수
@st.cache_data(ttl=300)
def load_current_assets():
    try:
        # Upbit API를 통해 실제 데이터 가져오기
        btc_balance = float(upbit.get_balance("BTC"))
        xrp_balance = float(upbit.get_balance("XRP"))
        krw_balance = float(upbit.get_balance("KRW"))
        
        current_btc_price = float(pyupbit.get_current_price("KRW-BTC"))
        current_xrp_price = float(pyupbit.get_current_price("KRW-XRP"))
        
        btc_value = btc_balance * current_btc_price
        xrp_value = xrp_balance * current_xrp_price
        total_value = btc_value + xrp_value + krw_balance
        
        # 데이터베이스에 현재 상태 저장
        conn = get_database_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO asset_status (btc_balance, xrp_balance, krw_balance, current_btc_price, current_xrp_price)
            VALUES (?, ?, ?, ?, ?)
        """, (btc_balance, xrp_balance, krw_balance, current_btc_price, current_xrp_price))
        conn.commit()
        conn.close()
        
        return {
            'btc_balance': btc_balance,
            'xrp_balance': xrp_balance,
            'krw_balance': krw_balance,
            'current_btc_price': current_btc_price,
            'current_xrp_price': current_xrp_price,
            'btc_value': btc_value,
            'xrp_value': xrp_value,
            'total_value': total_value
        }
    except Exception as e:
        st.error(f"자산 정보 로드 중 오류: {e}")
        return None

# 기존 데이터 로드 함수들...
@st.cache_data(ttl=300)
def load_gpt_advice(_days=7):
    try:
        conn = get_database_connection()
        query = f"""
        SELECT 
            timestamp,
            trade_recommendation,
            investment_percentage,
            confidence_score,
            reasoning,
            market_state
        FROM gpt_advice_log
        WHERE timestamp > datetime('now', '-{_days} days')
        ORDER BY timestamp DESC
        """
        df = pd.read_sql_query(query, conn)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    except Exception as e:
        st.error(f"GPT 자문 데이터 로드 중 오류: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

@st.cache_data(ttl=300)
def load_trade_history(_days=7):
    try:
        conn = get_database_connection()
        query = f"""
        SELECT 
            id,
            trade_type,
            amount,
            price,
            timestamp,
            confidence_score,
            reasoning,
            rsi,
            volatility,
            strategy_type
        FROM trade_log
        WHERE timestamp > datetime('now', '-{_days} days')
        ORDER BY timestamp DESC
        """
        df = pd.read_sql_query(query, conn)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # 매도 거래의 경우 amount를 원화 가치로 변환
        df['krw_value'] = df.apply(lambda row: 
            row['amount'] * row['price'] if row['trade_type'] == 'sell' 
            else row['amount'], axis=1)
        
        return df
    except Exception as e:
        st.error(f"거래 데이터 로드 중 오류: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

# 수익률 데이터 로드 함수
@st.cache_data(ttl=300)
def load_profit_data(_days=7, initial_investment=5300000):
    try:
        conn = get_database_connection()
        query = f"""
        SELECT 
            timestamp,
            btc_balance * current_btc_price as btc_value,
            xrp_balance * current_xrp_price as xrp_value,
            krw_balance,
            btc_balance * current_btc_price + xrp_balance * current_xrp_price + krw_balance as total_value
        FROM asset_status
        WHERE timestamp >= datetime('now', '-{_days} days')
        ORDER BY timestamp ASC
        """
        df = pd.read_sql_query(query, conn)
        
        if df.empty:
            return None, None
            
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # 수익률 계산
        if len(df) >= 2:
            df['profit_rate'] = ((df['total_value'] - initial_investment) / initial_investment) * 100
            final_value = df['total_value'].iloc[-1]
            
            profit_info = {
                'initial_investment': initial_investment,
                'final_value': final_value,
                'profit_rate': ((final_value - initial_investment) / initial_investment) * 100,
                'start_date': df['timestamp'].iloc[0],
                'end_date': df['timestamp'].iloc[-1]
            }
            
            return profit_info, df
        return None, None
    except Exception as e:
        st.error(f"수익률 데이터 로드 중 오류: {e}")
        return None, None

# 거래 현황 표시 함수
def display_trade_status(trade_df):
    if not trade_df.empty:
        recent_trade = trade_df.iloc[0]
        amount_display = format(int(recent_trade['krw_value']), ',')
        
        st.markdown(f"""
        <div class="metric-card">
            <p class="big-font">최근 거래</p>
            <p class="medium-font">유형: {recent_trade['trade_type']}</p>
            <p class="medium-font">금액: {amount_display}원</p>
            <p class="medium-font">가격: {format(int(recent_trade['price']), ',')}원</p>
        </div>
        """, unsafe_allow_html=True)

        # 거래량 추세 그래프
        fig = px.bar(trade_df, 
                   x='timestamp', 
                   y='krw_value',  # amount 대신 krw_value 사용
                   color='trade_type',
                   title='거래량 추세 (원화 기준)')
        fig.update_layout(yaxis_title='거래금액 (원)')
        st.plotly_chart(fig, use_container_width=True)

        # RSI vs 거래 타입 산점도
        fig = px.scatter(trade_df,
                       x='timestamp',
                       y='rsi',
                       color='trade_type',
                       size='krw_value',  # 거래 규모를 점 크기로 표시
                       title='RSI vs 거래 타입')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("거래 데이터가 없습니다.")

# 상세 데이터 테이블 표시 함수
def display_detailed_tables(gpt_df, trade_df):
    st.markdown("### 📝 상세 데이터")
    tab1, tab2 = st.tabs(["GPT 자문 기록", "거래 기록"])
    
    with tab1:
        if not gpt_df.empty:
            # GPT 자문 기록은 원본 그대로 표시
            st.dataframe(gpt_df)
        else:
            st.info("GPT 자문 기록이 없습니다.")

    with tab2:
        if not trade_df.empty:
            # 거래 기록에서 표시할 컬럼 선택 및 이름 변경
            display_df = trade_df.copy()
            display_df['거래금액(원)'] = display_df['krw_value'].map('{:,.0f}'.format)
            display_df['거래가격(원)'] = display_df['price'].map('{:,.0f}'.format)
            
            # 컬럼 순서 및 이름 정리
            columns_to_display = {
                'timestamp': '거래시각',
                'trade_type': '거래유형',
                '거래금액(원)': '거래금액(원)',
                '거래가격(원)': '거래가격(원)',
                'confidence_score': '신뢰도',
                'reasoning': '거래이유',
                'rsi': 'RSI',
                'volatility': '변동성',
                'strategy_type': '전략유형'
            }
            
            display_df = display_df.rename(columns=columns_to_display)
            display_df = display_df[columns_to_display.values()]
            
            st.dataframe(display_df, hide_index=True)
        else:
            st.info("거래 기록이 없습니다.")

def main():
    st.title("📊 Crypto Trading Dashboard")

    # 사이드바 설정
    st.sidebar.title("대시보드 설정")
    days = st.sidebar.slider("데이터 조회 기간 (일)", 1, 30, 7)
    update_interval = st.sidebar.number_input("자동 새로고침 간격 (초)", min_value=5, value=300)

    # 데이터 로드
    current_assets = load_current_assets()
    profit_info, profit_df = load_profit_data(_days=days)
    gpt_df = load_gpt_advice(_days=days)  # Load GPT advice data
    trade_df = load_trade_history(_days=days)  # Load trade history data

    # 자산 현황 섹션
    st.markdown("### 💰 현재 자산 현황")
    if current_assets:
        cols = st.columns(8)
        
        # BTC 정보
        with cols[0]:
            st.markdown(f"""
            <div class="metric-card">
                <p class="big-font">BTC 가격</p>
                <p class="medium-font">{format(int(current_assets['current_btc_price']), ',')}원</p>
            </div>
            """, unsafe_allow_html=True)
        
        with cols[1]:
            st.markdown(f"""
            <div class="metric-card">
                <p class="big-font">BTC 보유량</p>
                <p class="medium-font">{current_assets['btc_balance']:.8f} BTC</p>
            </div>
            """, unsafe_allow_html=True)
        
        with cols[2]:
            st.markdown(f"""
            <div class="metric-card">
                <p class="big-font">BTC 가치</p>
                <p class="medium-font">{format(int(current_assets['btc_value']), ',')}원</p>
            </div>
            """, unsafe_allow_html=True)
        
        # XRP 정보
        with cols[3]:
            st.markdown(f"""
            <div class="metric-card">
                <p class="big-font">XRP 가격</p>
                <p class="medium-font">{format(current_assets['current_xrp_price'], '.2f')}원</p>
            </div>
            """, unsafe_allow_html=True)
        
        with cols[4]:
            st.markdown(f"""
            <div class="metric-card">
                <p class="big-font">XRP 보유량</p>
                <p class="medium-font">{current_assets['xrp_balance']:.2f} XRP</p>
            </div>
            """, unsafe_allow_html=True)
        
        with cols[5]:
            st.markdown(f"""
            <div class="metric-card">
                <p class="big-font">XRP 가치</p>
                <p class="medium-font">{format(int(current_assets['xrp_value']), ',')}원</p>
            </div>
            """, unsafe_allow_html=True)
        
        # 종합 정보
        with cols[6]:
            st.markdown(f"""
            <div class="metric-card">
                <p class="big-font">KRW 잔고</p>
                <p class="medium-font">{format(int(current_assets['krw_balance']), ',')}원</p>
            </div>
            """, unsafe_allow_html=True)
        
        with cols[7]:
            if profit_info:
                profit_color = "color: #22c55e;" if profit_info['profit_rate'] >= 0 else "color: #ef4444;"
                st.markdown(f"""
                <div class="metric-card">
                    <p class="big-font">총 수익률</p>
                    <p class="medium-font" style="{profit_color}">{profit_info['profit_rate']:.2f}%</p>
                    <p class="medium-font">총 자산: {format(int(current_assets['total_value']), ',')}원</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="metric-card">
                    <p class="big-font">총 자산</p>
                    <p class="medium-font">{format(int(current_assets['total_value']), ',')}원</p>
                </div>
                """, unsafe_allow_html=True)

    # 자산 추이 그래프
    if profit_df is not None and not profit_df.empty:
        st.markdown("### 📈 자산 구성 및 수익률 추이")
        
        fig = go.Figure()
        
        # 자산별 영역 그래프
        fig.add_trace(go.Scatter(
            x=profit_df['timestamp'],
            y=profit_df['btc_value'],
            name='BTC 가치',
            stackgroup='assets',
            fillcolor='rgba(255, 99, 132, 0.4)',
            line=dict(color='rgba(255, 99, 132, 0.8)'),
            hovertemplate='%{x}<br>BTC: %{y:,.0f}원<extra></extra>'
        ))
        
        fig.add_trace(go.Scatter(
            x=profit_df['timestamp'],
            y=profit_df['xrp_value'],
            name='XRP 가치',
            stackgroup='assets',
            fillcolor='rgba(54, 162, 235, 0.4)',
            line=dict(color='rgba(54, 162, 235, 0.8)'),
            hovertemplate='%{x}<br>XRP: %{y:,.0f}원<extra></extra>'
        ))
        
        fig.add_trace(go.Scatter(
            x=profit_df['timestamp'],
            y=profit_df['krw_balance'],
            name='KRW 잔고',
            stackgroup='assets',
            fillcolor='rgba(75, 192, 192, 0.4)',
            line=dict(color='rgba(75, 192, 192, 0.8)'),
            hovertemplate='%{x}<br>KRW: %{y:,.0f}원<extra></extra>'
        ))
        
        # 초기 투자금액 라인
        fig.add_hline(
            y=profit_info['initial_investment'],
            line_dash="dash",
            line_color="gray",
            annotation_text="초기 투자금액",
            annotation_position="bottom right"
        )
        
        # 수익률 라인
        fig.add_trace(go.Scatter(
            x=profit_df['timestamp'],
            y=profit_df['profit_rate'],
            name='수익률',
            yaxis='y2',
            line=dict(color='#3b82f6', width=2),
            hovertemplate='%{x}<br>수익률: %{y:.2f}%<extra></extra>'
        ))
        
        fig.update_layout(
            title=f'{days}일간 자산 구성 및 수익률 변화',
            xaxis_title='시간',
            yaxis_title='자산가치 (원)',
            yaxis2=dict(
                title='수익률 (%)',
                overlaying='y',
                side='right',
                showgrid=False
            ),
            hovermode='x unified',
            showlegend=True,
            plot_bgcolor='rgba(0,0,0,0)',
            yaxis=dict(
                gridcolor='rgba(128,128,128,0.1)',
                zerolinecolor='rgba(128,128,128,0.2)'
            ),
            xaxis=dict(
                gridcolor='rgba(128,128,128,0.1)',
                zerolinecolor='rgba(128,128,128,0.2)'
            )
        )
        
        st.plotly_chart(fig, use_container_width=True)

        # 자산 구성 비율 파이 차트
        latest_data = profit_df.iloc[-1]
        pie_data = {
            'asset': ['BTC', 'XRP', 'KRW'],
            'value': [latest_data['btc_value'], latest_data['xrp_value'], latest_data['krw_balance']]
        }
        pie_df = pd.DataFrame(pie_data)
        
        fig_pie = px.pie(
            pie_df, 
            values='value', 
            names='asset',
            title='현재 자산 구성 비율',
            color_discrete_sequence=['rgba(255, 99, 132, 0.8)', 'rgba(54, 162, 235, 0.8)', 'rgba(75, 192, 192, 0.8)']
        )
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        
        st.plotly_chart(fig_pie, use_container_width=True)

    # 메인 대시보드
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🤖 GPT 자문 현황")
        if not gpt_df.empty:
            # 최근 GPT 자문 통계
            recent_advice = gpt_df.iloc[0]
            st.markdown(f"""
            <div class="metric-card">
                <p class="big-font">최근 자문</p>
                <p class="medium-font">추천: {recent_advice['trade_recommendation']}</p>
                <p class="medium-font">신뢰도: {recent_advice['confidence_score']}%</p>
                <p class="medium-font">투자 비율: {recent_advice['investment_percentage']}%</p>
            </div>
            """, unsafe_allow_html=True)

            # GPT 자문 추세 그래프
            fig = px.line(gpt_df, 
                        x='timestamp', 
                        y='confidence_score',
                        title='GPT 자문 신뢰도 추세')
            st.plotly_chart(fig, use_container_width=True)

            # GPT 추천 분포
            recommendation_counts = gpt_df['trade_recommendation'].value_counts()
            fig = px.pie(values=recommendation_counts.values,
                       names=recommendation_counts.index,
                       title='GPT 추천 분포')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("GPT 자문 데이터가 없습니다.")

    with col2:
        st.markdown("### 📈 거래 현황")
        display_trade_status(trade_df)

    # 상세 데이터 테이블 표시
    display_detailed_tables(gpt_df, trade_df)

    # 자동 새로고침 설정
    if st.sidebar.button('수동 새로고침'):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.markdown(f"다음 자동 새로고침까지: {update_interval}초")
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 대시보드 정보")
    st.sidebar.markdown(f"마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 푸터에 저작권 정보와 GitHub 링크 추가
    st.markdown("---")
    footer_cols = st.columns([3, 1])
    
    with footer_cols[0]:
        st.markdown("### © 2025 Mytheong(김민성). All Rights Reserved.")
        st.markdown("BTC Trading Bot Dashboard - 암호화폐 자동 거래 대시보드")
    
    with footer_cols[1]:
        github_url = "https://github.com/minseongee/PocketMoney/tree/main"
        st.markdown(f"""
        <a href="{github_url}" target="_blank">
            <button style="
                background-color: #24292e;
                color: white;
                padding: 12px 20px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 16px;
                display: inline-flex;
                align-items: center;
                margin-top: 20px;
                width: 100%;
                justify-content: center;
            ">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="white" style="margin-right: 8px;">
                    <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                </svg>
                GitHub 코드 보기
            </button>
        </a>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
