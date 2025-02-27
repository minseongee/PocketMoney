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
    
    # asset_status 테이블 생성
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS asset_status (
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        btc_balance REAL,
        krw_balance REAL,
        current_btc_price REAL
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
    page_title="BTC Trading Bot Dashboard",
    page_icon="📈",
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
    /* 마크다운 헤더 스타일 */
    .markdown-header {
        background-color: #1e293b;
        color: #ffffff !important;
        padding: 10px 15px;
        border-radius: 10px;
        margin: 15px 0;
        font-weight: bold;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #ffffff !important;
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
        btc_balance = float(upbit.get_balance("BTC"))  # btc 보유량
        krw_balance = float(upbit.get_balance("KRW"))  # 원화 잔고
        current_price = float(pyupbit.get_current_price("KRW-btc"))  # 현재 btc 가격
        
        btc_value = btc_balance * current_price
        total_value = btc_value + krw_balance
        
        # 데이터베이스에 현재 상태 저장
        conn = get_database_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO asset_status (btc_balance, krw_balance, current_btc_price)
            VALUES (?, ?, ?)
        """, (btc_balance, krw_balance, current_price))
        conn.commit()
        conn.close()
        
        return {
            'btc_balance': btc_balance,
            'krw_balance': krw_balance,
            'current_price': current_price,
            'btc_value': btc_value,
            'total_value': total_value
        }
    except Exception as e:
        st.error(f"자산 정보 로드 중 오류: {e}")
        # 오류 발생 시 데이터베이스의 최신 데이터 반환
        try:
            conn = get_database_connection()
            query = """
            SELECT 
                btc_balance,
                krw_balance,
                current_btc_price
            FROM asset_status
            ORDER BY timestamp DESC
            LIMIT 1
            """
            df = pd.read_sql_query(query, conn)
            if not df.empty:
                btc_balance = float(df['btc_balance'].iloc[0])
                krw_balance = float(df['krw_balance'].iloc[0])
                current_price = float(df['current_btc_price'].iloc[0])
                btc_value = btc_balance * current_price
                total_value = btc_value + krw_balance
                
                return {
                    'btc_balance': btc_balance,
                    'krw_balance': krw_balance,
                    'current_price': current_price,
                    'btc_value': btc_value,
                    'total_value': total_value
                }
        except Exception as db_error:
            st.error(f"백업 데이터 로드 중 오류: {db_error}")
        return None
    finally:
        try:
            conn.close()
        except:
            pass

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

# 수정된 수익률 계산 및 추세 데이터 로드 함수
@st.cache_data(ttl=300)
def load_profit_data(_days=7, initial_investment=5300000):  # 초기 투자금액 파라미터 추가
    try:
        conn = get_database_connection()
        # 시간별 자산 상태 조회
        query = f"""
        SELECT 
            timestamp,
            btc_balance * current_btc_price + krw_balance as total_value
        FROM asset_status
        WHERE timestamp >= datetime('now', '-{_days} days')
        ORDER BY timestamp ASC
        """
        df = pd.read_sql_query(query, conn)
        
        if df.empty:
            return None, None
            
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # 최소 2개 이상의 데이터 포인트가 필요
        if len(df) >= 2:
            final_value = df['total_value'].iloc[-1]
            
            # 초기 투자금액 기준 수익률 계산
            df['profit_rate'] = ((df['total_value'] - initial_investment) / initial_investment) * 100
            
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
        st.error(f"수익률 데이터 로드 중 오류 발생: {e}")
        return None, None
    finally:
        conn.close()

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
    st.title("📊 BTC Trading Bot Dashboard")

    # 사이드바 설정
    st.sidebar.title("대시보드 설정")
    days = st.sidebar.slider("데이터 조회 기간 (일)", 1, 30, 7)
    update_interval = st.sidebar.number_input("자동 새로고침 간격 (초)", 
                                            min_value=5, value=300)

    # 데이터 로드
    gpt_df = load_gpt_advice(_days=days)
    trade_df = load_trade_history(_days=days)
    current_assets = load_current_assets()
    profit_info, profit_df = load_profit_data(_days=days)

    # 자산 현황 섹션
    st.markdown("### 💰 현재 자산 현황")
    if current_assets:
        cols = st.columns(6)
        with cols[0]:
            st.markdown(f"""
            <div class="metric-card">
                <p class="big-font">btc 가격</p>
                <p class="medium-font">{format(int(current_assets['current_price']), ',')}원</p>
            </div>
            """, unsafe_allow_html=True)
        
        with cols[1]:
            st.markdown(f"""
            <div class="metric-card">
                <p class="big-font">btc 보유량</p>
                <p class="medium-font">{current_assets['btc_balance']:.8f} btc</p>
            </div>
            """, unsafe_allow_html=True)
        
        with cols[2]:
            st.markdown(f"""
            <div class="metric-card">
                <p class="big-font">보유 btc 가치</p>
                <p class="medium-font">{format(int(current_assets['btc_value']), ',')}원</p>
            </div>
            """, unsafe_allow_html=True)
        
        with cols[3]:
            st.markdown(f"""
            <div class="metric-card">
                <p class="big-font">KRW 잔고</p>
                <p class="medium-font">{format(int(current_assets['krw_balance']), ',')}원</p>
            </div>
            """, unsafe_allow_html=True)
        
        with cols[4]:
            st.markdown(f"""
            <div class="metric-card">
                <p class="big-font">총 자산</p>
                <p class="medium-font">{format(int(current_assets['total_value']), ',')}원</p>
            </div>
            """, unsafe_allow_html=True)
            
        with cols[5]:
            if profit_info:
                profit_color = "color: #22c55e;" if profit_info['profit_rate'] >= 0 else "color: #ef4444;"
                period_text = f"{profit_info['start_date'].strftime('%m/%d')} ~ {profit_info['end_date'].strftime('%m/%d')}"
                initial_investment_text = f"{format(int(profit_info['initial_investment']), ',')}원"
                st.markdown(f"""
                <div class="metric-card">
                    <p class="big-font">초기투자금 기준 수익률</p>
                    <p class="medium-font" style="{profit_color}">{profit_info['profit_rate']:.2f}%</p>
                    <p class="medium-font" style="font-size:14px !important;">초기투자금: {initial_investment_text}</p>
                    <p class="medium-font" style="font-size:14px !important;">{period_text}</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="metric-card">
                    <p class="big-font">초기투자금 기준 수익률</p>
                    <p class="medium-font">데이터 부족</p>
                    <p class="medium-font" style="font-size:14px !important;">최소 2개 이상의 데이터 필요</p>
                </div>
                """, unsafe_allow_html=True)

    else:
        st.info("자산 정보를 불러올 수 없습니다.")

    # 수익률 추세 그래프
    if profit_df is not None and not profit_df.empty:
        st.markdown("### 📈 초기투자금 기준 수익률 추세")
        
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=profit_df['timestamp'],
            y=profit_df['total_value'],
            mode='lines+markers',
            name='총 자산가치',
            line=dict(
                color='#22c55e' if profit_info['profit_rate'] >= 0 else '#ef4444',
                width=2
            ),
            hovertemplate='시간: %{x}<br>자산가치: %{y:,.0f}원<extra></extra>'
        ))
        
        fig.add_hline(
            y=profit_info['initial_investment'],
            line_dash="dash",
            line_color="gray",
            annotation_text="초기 투자금액",
            annotation_position="bottom right"
        )
        
        fig.add_trace(go.Scatter(
            x=profit_df['timestamp'],
            y=profit_df['profit_rate'],
            mode='lines',
            name='수익률',
            line=dict(color='#3b82f6', width=1, dash='dot'),
            yaxis='y2',
            hovertemplate='시간: %{x}<br>수익률: %{y:.2f}%<extra></extra>'
        ))
        
        fig.update_layout(
            title=f'{days}일간 자산가치 및 수익률 변화',
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

if __name__ == "__main__":
    main()
