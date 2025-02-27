import pyupbit
import re
import numpy as np
import pandas as pd
import time
import warnings
import openai
import json
import sqlite3
import gc
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from serpapi import GoogleSearch
import os
from dotenv import load_dotenv

load_dotenv()
warnings.filterwarnings('ignore')

class BTCTradingBot:
    #----------------
    # 1. Initialization and Setup
    #----------------
    def __init__(self, ticker="KRW-BTC", interval="minute240"):
        # 먼저 timezone 설정
        self.timezone = ZoneInfo('Asia/Seoul')

        self.ticker = ticker
        self.interval = interval
        
        self.access_key = os.getenv('UPBIT_ACCESS_KEY')
        self.secret_key = os.getenv('UPBIT_SECRET_KEY')
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.serpapi_key_1 = os.getenv('SERPAPI_KEY_1')
        self.serpapi_key_2 = os.getenv('SERPAPI_KEY_2')
        self.current_serpapi_key = self.serpapi_key_1 

        # 뉴스 검색 키워드 초기화 추가
        self.news_keywords = [
            "BTC Crypto news"
        ]

        self.api_call_counts = {
            self.serpapi_key_1: 0,
            self.serpapi_key_2: 0
        }
        self.last_api_reset = {
            self.serpapi_key_1: datetime.now(self.timezone),
            self.serpapi_key_2: datetime.now(self.timezone)
        }

        self.TRADING_FEE_RATE = 0.0005
        self.MIN_ORDER_AMOUNT = 5000
        
        openai.api_key = self.openai_api_key
        self.upbit = pyupbit.Upbit(self.access_key, self.secret_key)
        self.db_path = 'trading_log.db'
        

        # 뉴스 캐싱 관련 변수
        self.NEWS_UPDATE_INTERVAL = 14400  # 4시간 (초)
        
        # 데이터베이스 생성
        self.create_database()
        
        # 초기 뉴스 로드
        cached_news = self.load_cached_news()
        if cached_news:
            self.cached_news = cached_news
            self.last_news_update = time.time()
        else:
            self.cached_news = self.fetch_BTC_news()
            self.last_news_update = time.time()

        # GPT 자문 관련 변수 초기화
        self.last_gpt_market_state = None
        self.last_gpt_advice = None

        # 역추세 매매를 위한 추가 파라미터
        self.OVERSOLD_RSI = 25  # RSI 과매도 기준
        self.OVERBOUGHT_RSI = 75  # RSI 과매수 기준
        self.BOLLINGER_PERIOD = 20  # 볼린저 밴드 기간
        self.BOLLINGER_STD = 2.2  # 볼린저 밴드 표준편차
        self.MOMENTUM_THRESHOLD = 0.025  # 모멘텀 임계값 (2.5%)

        from threading import Lock
        self.market_data_lock = Lock()

        # 임계값을 설정으로 분리
        self.VOLATILITY_THRESHOLD = 2
        self.CONFIDENCE_THRESHOLD = 60
        self.MIN_TRADE_INTERVAL = 180  # 3분
        self.SLEEP_INTERVAL = 180      # 3분

        # 거래 제한 관련 새로운 변수들
        self.last_gpt_advice = None
        self.last_market_state = None
        self.COOLDOWN_HOURS = 2  # 거래 후 대기 시간 (시간)
        self.MARKET_CHANGE_THRESHOLD = 0.02  # 시장 변화 감지 임계값 (2%)
        
        # DB 커넥션 풀 설정
        self.db_connection = None
        self.init_database_connection()

        # Stoch RSI 크로스 관련 변수 추가
        self.last_stoch_cross_time = None
        self.last_stoch_cross_type = None
        self.STOCH_CROSS_COOLDOWN = 600  # 1시간 쿨다운
        self.STOCH_CROSS_THRESHOLD = 2  # 크로스 발생 후 최소 2% 이상 벌어져야 다음 크로스로 인정

        # KNN 방향 변화 관련 변수 추가
        self.last_knn_change_time = None
        self.last_knn_direction = None
        self.KNN_CHANGE_COOLDOWN = 600  # 1시간 쿨다운
        self.KNN_SIGNAL_MIN_STRENGTH = 0.25  # 최소 신호 강도
        self.KNN_DIRECTION_CHANGE_THRESHOLD = 0.3  # 방향 전환 최소 차이

        # API 키 사용 정보 초기화
        self.init_api_key_usage()

    def get_next_serpapi_key(self):
        """개선된 다음 SerpAPI 키 선택 및 사용량 추적"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            korean_time = datetime.now(self.timezone)
            current_month = korean_time.month
            current_year = korean_time.year
            
            # 월별 리셋 로직
            cursor.execute('''
            UPDATE serpapi_usage 
            SET usage_count = 0, last_reset_month = ?, last_reset_year = ?
            WHERE last_reset_month != ? OR last_reset_year != ?
            ''', (current_month, current_year, current_month, current_year))
            
            # 각 키의 사용량 조회
            cursor.execute('''
            SELECT api_key, usage_count 
            FROM serpapi_usage 
            WHERE usage_count < 95
            ORDER BY usage_count ASC
            ''')
            
            available_keys = cursor.fetchall()
            
            if not available_keys:
                print("모든 API 키의 사용량이 한도에 도달했습니다.")
                return None
            
            selected_key = available_keys[0][0]
            
            # 선택된 키의 사용량 증가
            cursor.execute('''
            UPDATE serpapi_usage 
            SET usage_count = usage_count + 1 
            WHERE api_key = ?
            ''', (selected_key,))
            
            conn.commit()
            conn.close()
            
            print(f"선택된 API 키: {selected_key}")
            return selected_key
            
        except Exception as e:
            print(f"API 키 선택 중 오류: {e}")
            return self.current_serpapi_key

    def init_database_connection(self):
        """데이터베이스 연결 초기화"""
        try:
            self.db_connection = sqlite3.connect(
                self.db_path,
                timeout=30,
                check_same_thread=False
            )
            # WAL 모드 활성화로 성능 향상
            self.db_connection.execute('PRAGMA journal_mode=WAL')
        except Exception as e:
            print(f"데이터베이스 연결 실패: {e}")
            raise

    def create_database(self):
        """데이터베이스 및 테이블 생성 함수 수정"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 기존 코드 유지
            
            # news_cache 테이블 추가
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """)
            
            # trade_log 테이블 추가 (추가적으로 필요할 수 있음)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_type TEXT NOT NULL,
                amount REAL NOT NULL,
                price REAL NOT NULL,
                timestamp TEXT NOT NULL,
                confidence_score INTEGER,
                reasoning TEXT,
                rsi REAL,
                volatility REAL,
                strategy_type TEXT
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS gpt_advice_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                trade_recommendation TEXT NOT NULL,
                investment_percentage INTEGER NOT NULL,
                confidence_score INTEGER NOT NULL,
                reasoning TEXT,
                market_state TEXT
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS serpapi_usage (
                api_key TEXT PRIMARY KEY,
                usage_count INTEGER NOT NULL,
                last_reset_month INTEGER NOT NULL,
                last_reset_year INTEGER NOT NULL
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetch_timestamp TEXT NOT NULL,
                news_content TEXT NOT NULL,
                keywords TEXT NOT NULL
            )
            """)

            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"데이터베이스 생성 중 오류: {e}")
            import traceback
            traceback.print_exc()

    def init_api_key_usage(self):
        """초기 API 키 사용 정보 초기화"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            korean_time = datetime.now(self.timezone)
            
            # 각 API 키에 대한 사용 정보 초기화
            for api_key in [self.serpapi_key_1, self.serpapi_key_2]:
                cursor.execute('''
                INSERT OR REPLACE INTO serpapi_usage 
                (api_key, usage_count, last_reset_month, last_reset_year) 
                VALUES (?, ?, ?, ?)
                ''', (
                    api_key, 
                    0, 
                    korean_time.month, 
                    korean_time.year
                ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"API 키 사용 정보 초기화 중 오류: {e}")
        
    #----------------
    # 2. Data Management
    #----------------
    def get_historical_data(self, count=200):
        """과거 거래 데이터 가져오기 (충분한 데이터 보장)"""
        try:
            # RSI 계산에 필요한 최소 데이터 수 고려
            required_count = max(count, 50)  # RSI 계산을 위해 충분한 데이터 확보
            
            df = pyupbit.get_ohlcv(self.ticker, interval=self.interval, count=required_count)
            if df is None or df.empty:
                raise ValueError("데이터를 가져올 수 없습니다.")
            return df
        except Exception as e:
            print(f"Historical data 조회 중 오류: {e}")
            return None
        
    def get_portfolio_status(self):
        try:
            krw_balance = self.upbit.get_balance("KRW")
            coin_balance = self.upbit.get_balance(self.ticker)
            current_price = pyupbit.get_current_price(self.ticker)
            
            coin_value = coin_balance * current_price if coin_balance and current_price else 0
            total_value = krw_balance + coin_value
            
            avg_buy_price = self.upbit.get_avg_buy_price(self.ticker)
            roi = ((current_price - avg_buy_price) / avg_buy_price * 100) if avg_buy_price and coin_balance else 0
            coin_ratio = (coin_value / total_value * 100) if total_value > 0 else 0
            
            print(f"\n현재 포트폴리오 상태:")
            print(f"KRW 잔고: {krw_balance:.2f}원")
            print(f"BTC 잔고: {coin_balance:.8f}")
            rounded_price = round(current_price / 100) * 100
            print(f"현재 가격: {rounded_price:,.0f}원")
            if avg_buy_price > 0:
                print(f"평균 매수가: {avg_buy_price:.2f}원")
            print(f"코인 가치: {coin_value:.2f}원")
            print(f"총 자산: {total_value:.2f}원")
            print(f"수익률: {roi:.2f}%")
            print(f"코인 비중: {coin_ratio:.2f}%")
            
            return {
                'krw_balance': krw_balance,
                'coin_balance': coin_balance,
                'current_price': current_price,
                'avg_buy_price': avg_buy_price,
                'coin_value': coin_value,
                'total_value': total_value,
                'roi': roi,
                'coin_ratio': coin_ratio
            }
        except Exception as e:
            print(f"포트폴리오 상태 조회 중 오류: {e}")
            return None

    def get_next_news_update_time(self, current_time):
        """정해진 시간 (00, 04, 08, 12, 16, 20)의 다음 업데이트 시간 계산
        
        Args:
            current_time (datetime): 현재 시간
        
        Returns:
            datetime: 다음 업데이트 예정 시간
        """
        fixed_hours = [0, 4, 8, 12, 16, 20]
        current_hour = current_time.hour
        
        # 현재 시간 이후의 다음 고정 시간 찾기
        next_hour = next((h for h in fixed_hours if h > current_hour), fixed_hours[0])
        
        next_update = current_time.replace(
            hour=next_hour,
            minute=0,
            second=0,
            microsecond=0
        )
        
        # 다음 시간이 현재 시간보다 이전이면 다음 날로 설정
        if next_update <= current_time:
            next_update += timedelta(days=1)
        
        return next_update

    def fetch_BTC_news(self, num_articles=5, max_retries=3):
        """개선된 뉴스 수집 함수"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            current_time = datetime.now(self.timezone)
            fixed_hours = [0, 4, 8, 12, 16, 20]
            
            # 마지막으로 저장된 뉴스 조회
            cursor.execute('''
            SELECT news_content, fetch_timestamp 
            FROM news_fetch_log 
            ORDER BY fetch_timestamp DESC 
            LIMIT 1
            ''')
            
            last_news = cursor.fetchone()
            
            if last_news:
                last_fetch_time = datetime.strptime(
                    last_news[1], 
                    '%Y-%m-%d %H:%M:%S'
                ).replace(tzinfo=self.timezone)
                
                # 현재 시간이 정해진 시간이 아닌 경우 캐시된 뉴스 반환
                if current_time.hour not in fixed_hours:
                    print(f"정해진 시간이 아님 - 마지막 업데이트: {last_fetch_time}")
                    return last_news[0]
                
                # 마지막 업데이트가 현재 시간대와 같은 경우 캐시된 뉴스 반환
                if (last_fetch_time.date() == current_time.date() and 
                    last_fetch_time.hour == current_time.hour):
                    print(f"이미 현재 시간대의 뉴스가 있음: {last_fetch_time}")
                    return last_news[0]
            
            # 여기서부터는 새로운 뉴스를 가져오는 로직
            default_keywords = ["BTC cryptocurrency OR BTC"]
            keywords_to_use = getattr(self, 'news_keywords', default_keywords)
            
            # API 키 사용량 확인 및 초기화 로직
            cursor.execute('''
            SELECT api_key, usage_count, last_reset_month, last_reset_year
            FROM serpapi_usage
            WHERE usage_count < 95
            ORDER BY usage_count ASC
            ''')
            
            available_keys = cursor.fetchall()
            
            if not available_keys:
                print("모든 API 키의 사용량이 한도에 도달했습니다.")
                return self._get_cached_news(cursor)
                
            all_news = []
            api_success = False
            retry_count = 0
            
            while not api_success and retry_count < max_retries:
                try:
                    for api_key, current_usage, last_month, last_year in available_keys:
                        # 월간 사용량 초기화 확인
                        if (current_time.month != last_month or 
                            current_time.year != last_year):
                            cursor.execute('''
                            UPDATE serpapi_usage
                            SET usage_count = 0,
                                last_reset_month = ?,
                                last_reset_year = ?
                            WHERE api_key = ?
                            ''', (current_time.month, current_time.year, api_key))
                            conn.commit()
                            current_usage = 0
                        
                        if current_usage >= 95:
                            continue
                            
                        print(f"\nAPI 키 시도: {api_key[:8]}... (현재 사용량: {current_usage})")
                        
                        success_with_current_key = False
                        for keyword in keywords_to_use:
                            try:
                                params = {
                                    "engine": "google_news",
                                    "q": keyword,
                                    "api_key": api_key,
                                    "num": num_articles,
                                    "gl": "us",
                                    "hl": "en",
                                    "time_period": "1h"  # 최근 4시간 뉴스로 제한
                                }
                                
                                search = GoogleSearch(params)
                                results = search.get_dict()
                                
                                if 'error' in results:
                                    print(f"API 오류 ({api_key[:8]}...): {results['error']}")
                                    continue
                                
                                if 'news_results' in results:
                                    news_results = results['news_results']
                                    if news_results:  # 결과가 있는 경우만 처리
                                        news_count = len(news_results)
                                        print(f"뉴스 검색 성공 (키: {api_key[:8]}...): {news_count}개 기사")
                                        all_news.extend(news_results)
                                        success_with_current_key = True
                                        api_success = True
                                        
                                        # 성공한 API 키의 사용량 증가
                                        cursor.execute('''
                                        UPDATE serpapi_usage 
                                        SET usage_count = usage_count + 1 
                                        WHERE api_key = ?
                                        ''', (api_key,))
                                        conn.commit()
                                        break
                                    
                            except Exception as e:
                                print(f"키워드 '{keyword}' 검색 중 오류: {e}")
                                continue
                        
                        if success_with_current_key:
                            break
                            
                    if not api_success:
                        retry_count += 1
                        if retry_count < max_retries:
                            print(f"\n재시도 {retry_count}/{max_retries}...")
                            time.sleep(5)  # 재시도 전 5초 대기
                        
                except Exception as e:
                    print(f"API 호출 중 오류: {e}")
                    retry_count += 1
                    if retry_count < max_retries:
                        time.sleep(5)
                    continue
                    
            if api_success:
                # 뉴스 처리 및 저장
                news_summary = self._process_news(all_news)
                
                try:
                    # 기존 데이터 삭제
                    cursor.execute('DELETE FROM news_fetch_log')
                    
                    # 새로운 뉴스 저장
                    cursor.execute('''
                    INSERT INTO news_fetch_log 
                    (fetch_timestamp, news_content, keywords) 
                    VALUES (?, ?, ?)
                    ''', (
                        current_time.strftime('%Y-%m-%d %H:%M:%S'),
                        news_summary,
                        ','.join(keywords_to_use)
                    ))
                    
                    conn.commit()
                    print(f"\n새로운 뉴스 수집 및 저장 완료 ({len(all_news)}개 기사)")
                    return news_summary
                    
                except sqlite3.Error as e:
                    print(f"데이터베이스 저장 중 오류: {e}")
                    return self._get_cached_news(cursor)
            else:
                print("\n모든 API 키 시도 실패")
                return self._get_cached_news(cursor)
                
        except Exception as e:
            print(f"뉴스 수집 중 오류: {e}")
            import traceback
            traceback.print_exc()
            if 'cursor' in locals():
                return self._get_cached_news(cursor)
            return "뉴스를 가져올 수 없습니다."
            
        finally:
            if 'conn' in locals():
                conn.close()

    def _get_cached_news(self, cursor):
        """캐시된 뉴스 조회"""
        cursor.execute('''
        SELECT news_content, fetch_timestamp 
        FROM news_fetch_log 
        ORDER BY fetch_timestamp DESC 
        LIMIT 1
        ''')
        
        result = cursor.fetchone()
        if result:
            news_content, timestamp = result
            print(f"캐시된 뉴스 반환 (최종 업데이트: {timestamp})")
            return news_content
        return "뉴스를 가져올 수 없습니다."

    def _fetch_news_with_key(self, api_key, num_articles):
        """특정 API 키로 뉴스 수집"""
        news_results = []
        for keyword in self.news_keywords:
            params = {
                "engine": "google_news",
                "q": keyword,
                "api_key": api_key,
                "num": num_articles
            }
            
            search = GoogleSearch(params)
            results = search.get_dict()
            
            if 'news_results' in results:
                news_results.extend(results['news_results'])
            
        return news_results

    def _process_news(self, news_results):
        """뉴스 결과 처리"""
        # 중복 제거
        unique_news = {article.get('title', ''): article for article in news_results}
        sorted_news = sorted(unique_news.values(), key=lambda x: x.get('date', ''), reverse=True)
        
        # 뉴스 요약 생성
        news_summary = ""
        for idx, article in enumerate(sorted_news, 1):
            is_important = any(keyword.lower() in article.get('title', '').lower() 
                             for keyword in ['sec', 'regulation', 'bitcoin'])
            prefix = "🔥 " if is_important else ""
            news_summary += f"{prefix}{idx}. {article.get('title', '')}\n"
            news_summary += f"   {article.get('snippet', '')}\n\n"
        
        return news_summary

    def update_news_cache(self, news_content):
        """개선된 뉴스 캐시 업데이트"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            korean_time = datetime.now(self.timezone)
            
            # 현재 시간이 정해진 시간인 경우에만 업데이트
            if korean_time.hour in [0, 4, 8, 12, 16, 20]:
                cursor.execute('''
                INSERT INTO news_fetch_log 
                (fetch_timestamp, news_content, keywords) 
                VALUES (?, ?, ?)
                ''', (
                    korean_time.strftime('%Y-%m-%d %H:%M:%S'),
                    news_content,
                    ','.join(self.news_keywords)
                ))
                
                print(f"뉴스 캐시 업데이트 완료: {korean_time}")
            else:
                print(f"정해진 시간이 아니므로 뉴스 캐시 업데이트 건너뜀: {korean_time}")
            
            conn.commit()
            
        except sqlite3.Error as e:
            print(f"뉴스 캐시 업데이트 중 SQLite 오류: {e}")
        except Exception as e:
            print(f"뉴스 캐시 업데이트 중 오류: {e}")
        finally:
            if 'conn' in locals():
                conn.close()

    def load_cached_news(self):
        """개선된 캐시된 뉴스 로드"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT news_content, fetch_timestamp 
            FROM news_fetch_log 
            ORDER BY fetch_timestamp DESC 
            LIMIT 1
            ''')
            
            result = cursor.fetchone()
            
            if result:
                cached_news, timestamp_str = result
                print(f"캐시된 뉴스 로드 (최종 업데이트: {timestamp_str})")
                return cached_news
            
            return None
            
        except sqlite3.Error as e:
            print(f"캐시된 뉴스 로드 중 SQLite 오류: {e}")
            return None
        except Exception as e:
            print(f"캐시된 뉴스 로드 중 오류: {e}")
            return None
        finally:
            if 'conn' in locals():
                conn.close()

    def log_trade(self, trade_type, amount, price, confidence_score, reasoning, rsi, volatility, strategy_type):
        """거래 로깅 개선 및 디버깅 기능 추가"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            korean_time = datetime.now(self.timezone)
            timestamp = korean_time.strftime('%Y-%m-%d %H:%M:%S')
            
            # 디버그 출력
            print(f"\n=== 거래 로깅 디버그 ===")
            print(f"시간: {timestamp}")
            print(f"거래 유형: {trade_type}")
            print(f"거래량: {amount}")
            print(f"가격: {price}")
            print(f"신뢰도: {confidence_score}")
            
            cursor.execute('''
            INSERT INTO trade_log 
            (trade_type, amount, price, timestamp, confidence_score, reasoning, rsi, volatility, strategy_type) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                str(trade_type),  # 문자열 타입 보장
                float(amount),    # 실수 타입 보장
                float(price),     # 실수 타입 보장
                timestamp,
                int(confidence_score) if confidence_score else 0,  # NULL 처리
                str(reasoning) if reasoning else '',
                float(rsi) if rsi else 0.0,
                float(volatility) if volatility else 0.0,
                str(strategy_type) if strategy_type else '미정'
            ))
            
            conn.commit()
            
            # 저장 확인
            cursor.execute('''
            SELECT * FROM trade_log WHERE timestamp = ? ORDER BY id DESC LIMIT 1
            ''', (timestamp,))
            
            result = cursor.fetchone()
            if result:
                print("\n✅ 거래 기록 저장 완료:")
                print(f"ID: {result[0]}")
                print(f"저장된 거래 유형: {result[1]}")
                print(f"저장된 거래량: {result[2]}")
            else:
                print("❌ 거래 기록 확인 실패")
                
            return True

        except Exception as e:
            print(f"❌ 거래 로깅 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
            
        finally:
            if 'conn' in locals():
                conn.close()
        
    def get_recent_gpt_advice(self, limit=5):
        """최근 GPT 자문 내역 조회 함수 개선"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT 
                timestamp,
                trade_recommendation,
                investment_percentage,
                confidence_score,
                reasoning,
                market_state
            FROM gpt_advice_log
            ORDER BY timestamp DESC
            LIMIT ?
            ''', (limit,))
            
            results = cursor.fetchall()
            
            # 결과를 딕셔너리 리스트로 변환
            advice_list = []
            for row in results:
                try:
                    market_state = json.loads(row[5]) if row[5] else None
                except json.JSONDecodeError:
                    market_state = None
                
                advice_list.append({
                    'timestamp': row[0],
                    'trade_recommendation': row[1],
                    'investment_percentage': row[2],
                    'confidence_score': row[3],
                    'reasoning': row[4],
                    'market_state': market_state
                })
            
            print(f"\n최근 {len(advice_list)}개의 GPT 자문 기록 조회됨")
            for advice in advice_list:
                print(f"시간: {advice['timestamp']}")
                print(f"추천: {advice['trade_recommendation']}")
                print(f"신뢰도: {advice['confidence_score']}%")
                print("---")
            
            return advice_list
                
        except Exception as e:
            print(f"GPT 자문 내역 조회 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return []
            
        finally:
            if 'conn' in locals():
                conn.close()
    
    def get_recent_trades(self, limit=5):
        """최근 거래 내역 조회 개선"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 컬럼 존재 여부 확인 없이 바로 조회
            cursor.execute('''
            SELECT 
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
            WHERE trade_type != 'hold'
            ORDER BY timestamp DESC
            LIMIT ?
            ''', (limit,))
            
            trades = cursor.fetchall()
            conn.close()
            
            return trades
        except Exception as e:
            print(f"거래 내역 조회 중 오류: {e}")
            return []

    def get_recent_trades_volume(self, hours=24):
        """최근 거래량 집계"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            time_threshold = (datetime.now(self.timezone) - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''
            SELECT trade_type, SUM(amount) as total_amount
            FROM trade_log
            WHERE timestamp > ? AND trade_type IN ('buy', 'sell')
            GROUP BY trade_type
            ''', (time_threshold,))
            
            results = cursor.fetchall()
            trades = {row[0]: row[1] for row in results}
            
            # 총 거래 비율 계산
            portfolio = self.get_portfolio_status()
            total_assets = portfolio['total_value']
            total_traded = sum(trades.values())
            
            return {
                'buy_volume': trades.get('buy', 0),
                'sell_volume': trades.get('sell', 0),
                'total_ratio': total_traded / total_assets if total_assets > 0 else 0
            }
            
        except Exception as e:
            print(f"거래량 집계 중 오류: {e}")
            return {'buy_volume': 0, 'sell_volume': 0, 'total_ratio': 0}
        finally:
            conn.close()

    def get_recent_trading_summary(self, days=7):
        """최근 거래 요약"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            korean_time = datetime.now(self.timezone)
            past_date = (korean_time - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''
            SELECT 
                COUNT(CASE WHEN trade_type = 'buy' THEN 1 END) as buy_count,
                COUNT(CASE WHEN trade_type = 'sell' THEN 1 END) as sell_count,
                AVG(CASE WHEN trade_type != 'hold' THEN confidence_score END) as avg_confidence
            FROM trade_log 
            WHERE timestamp > ? AND trade_type != 'hold'
            ''', (past_date,))
            
            result = cursor.fetchone()
            buy_count, sell_count, avg_confidence = result
            
            return {
                'period_days': days,
                'buy_count': buy_count or 0,
                'sell_count': sell_count or 0,
                'avg_confidence': avg_confidence or 0
            }
        except Exception as e:
            print(f"거래 요약 조회 중 오류: {e}")
            return None
        finally:
            conn.close()

    def get_gpt_advice_history(self, limit=1, formatted=False):
        """GPT 자문 내역을 조회하는 통합 함수
        
        Args:
            limit (int): 조회할 최근 자문 개수 (기본값: 1)
            formatted (bool): 프롬프트용 포맷팅 여부 (기본값: False)
            
        Returns:
            str: 자문 내역 문자열
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 최근 자문 데이터 조회
            cursor.execute('''
            SELECT 
                timestamp,
                trade_recommendation,
                investment_percentage,
                confidence_score,
                reasoning,
                market_state
            FROM gpt_advice_log
            ORDER BY timestamp DESC
            LIMIT ?
            ''', (limit,))
            
            results = cursor.fetchall()
            if not results:
                return "자문 내역이 없습니다."
                
            if formatted:
                # 프롬프트용 포맷
                advice_history = "이전 자문 내역:\n"
                for idx, result in enumerate(results, 1):
                    timestamp_str, recommendation, investment, confidence, reasoning, market_state = result
                    
                    # 한국 시간대로 시간 변환
                    advice_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                    advice_time = advice_time.replace(tzinfo=self.timezone)
                    current_time = datetime.now(self.timezone)
                    minutes_passed = (current_time - advice_time).total_seconds() / 60
                    
                    # 시장 상태 파싱
                    market_status = ""
                    if market_state:
                        try:
                            market_data = json.loads(market_state)
                            market_status = f"""
                            - 당시 시장 상황:
                            * 가격: {market_data.get('price', 'N/A'):,.0f}원
                            * RSI: {market_data.get('rsi', 'N/A'):.1f}
                            * 변동성: {market_data.get('volatility', 'N/A'):.1f}%
                            * EMA: {market_data.get('ema_status', 'N/A')}
                            * 모멘텀: {market_data.get('momentum', 'N/A')*100:.1f}%
                            * 볼린저밴드: {market_data.get('bollinger_position', 'N/A')}
                            """
                        except json.JSONDecodeError:
                            market_status = "  (시장 상태 데이터 없음)"
                    
                    advice_history += f"""
                    {idx}. {int(minutes_passed)}분 전 당신의 자문:
                    - 추천: {recommendation}
                    - 투자비율: {investment}%
                    - 신뢰도: {confidence}%
                    - 근거: {reasoning}
                    {market_status}
                    """
                return advice_history
            else:
                # 일반 포맷
                result = results[0]  # limit=1일 때의 결과
                timestamp_str, recommendation, investment, confidence, reasoning, market_state = result
                
                # 한국 시간대로 시간 변환
                advice_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                advice_time = advice_time.replace(tzinfo=self.timezone)
                current_time = datetime.now(self.timezone)
                minutes_passed = (current_time - advice_time).total_seconds() / 60
                
                # 시장 상태 파싱
                if market_state:
                    try:
                        market_data = json.loads(market_state)
                        market_status = f"""
                        시장 상황:
                        - 가격: {market_data.get('price', 'N/A'):,.0f}원
                        - RSI: {market_data.get('rsi', 'N/A'):.1f}
                        - 변동성: {market_data.get('volatility', 'N/A'):.1f}%
                        - EMA 상태: {market_data.get('ema_status', 'N/A')}
                        - 모멘텀: {market_data.get('momentum', 'N/A')*100:.1f}%
                        - 볼린저밴드: {market_data.get('bollinger_position', 'N/A')}
                        """
                    except json.JSONDecodeError:
                        market_status = "시장 상태 데이터 파싱 실패"
                else:
                    market_status = "시장 상태 정보 없음"
                
                return f"""
                마지막 GPT 자문 (약 {minutes_passed:.0f}분 전):
                - 추천: {recommendation}
                - 투자비율: {investment}%
                - 신뢰도: {confidence}%
                - 근거: {reasoning}
                
                {market_status}
                """
                
        except Exception as e:
            print(f"자문 내역 조회 중 오류: {e}")
            return "자문 내역 조회 실패"
            
        finally:
            if 'conn' in locals():
                conn.close()

    #----------------
    # 3. Technical Analysis
    #----------------
    def calculate_ema_ribbon(self, data, periods=[5, 10, 20, 30, 50]):
        """EMA Ribbon 계산"""
        ema_ribbon = pd.DataFrame()
        for period in periods:
            ema_ribbon[f'EMA_{period}'] = data['close'].ewm(span=period, adjust=False).mean()
        return ema_ribbon

    def calculate_ema_200(self, data):
        """200 기간 EMA 계산"""
        return data['close'].ewm(span=200, adjust=False).mean().iloc[-1]

    def calculate_rsi(self, prices, periods=14):
        """
        Pine Script 스타일의 RSI 계산 함수
        
        Args:
            prices: 가격 데이터 (pandas Series)
            periods: RSI 계산 기간 (기본값: 14)
            
        Returns:
            RSI 값을 담은 pandas Series
        """
        try:
            # 필요한 데이터 포인트 수 확인
            if len(prices) < periods + 1:
                print(f"RSI 계산을 위한 충분한 데이터가 없습니다. (필요: {periods + 1}, 현재: {len(prices)})")
                return pd.Series(50, index=prices.index)  # 기본값 50 반환
                
            # 가격 변화 계산 (Pine Script의 change(close)와 동일)
            changes = prices.diff()
            
            # gains와 losses 분리 (Pine Script 스타일)
            gains = changes.copy()
            losses = changes.copy()
            
            # gain = change >= 0 ? change : 0.0
            gains[gains < 0] = 0.0
            
            # loss = change < 0 ? (-1) * change : 0.0
            losses[losses > 0] = 0.0
            losses = losses.abs()  # (-1) * change 부분
            
            # avgGain = rma(gain, 14) 구현
            # rma(x, n) = (x + ((n-1) * prevRma)) / n
            avg_gains = pd.Series(index=prices.index, dtype=float)
            avg_losses = pd.Series(index=prices.index, dtype=float)
            
            # 첫 번째 평균값 계산
            avg_gains.iloc[periods] = gains.iloc[1:periods + 1].mean()
            avg_losses.iloc[periods] = losses.iloc[1:periods + 1].mean()
            
            # 나머지 기간에 대해 RMA 계산
            for i in range(periods + 1, len(prices)):
                avg_gains.iloc[i] = (gains.iloc[i] + (periods - 1) * avg_gains.iloc[i-1]) / periods
                avg_losses.iloc[i] = (losses.iloc[i] + (periods - 1) * avg_losses.iloc[i-1]) / periods
            
            # rs = avgGain / avgLoss
            rs = avg_gains / avg_losses
            
            # rsi = 100 - (100 / (1 + rs))
            rsi = 100 - (100 / (1 + rs))
            
            # 무한값 및 NaN 처리
            rsi = rsi.replace([np.inf, -np.inf], np.nan)
            rsi = rsi.fillna(50)  # NaN값은 50으로 채움
            
            return rsi.clip(0, 100)  # 0-100 범위로 제한
            
        except Exception as e:
            print(f"RSI 계산 중 오류 발생: {str(e)}")
            return pd.Series(50, index=prices.index)  # 오류 발생 시 기본값 50 반환

    def calculate_cci(self, high, low, close, periods=14):
        """CCI 계산"""
        tp = (high + low + close) / 3
        tp_sma = tp.rolling(window=periods).mean()
        mad = tp.rolling(window=periods).apply(lambda x: np.abs(x - x.mean()).mean())
        cci = (tp - tp_sma) / (0.015 * mad)
        return cci
    
    def calculate_roc(self, close, periods=14):
        """ROC 계산"""
        return close.pct_change(periods=periods) * 100

    def normalize_volume(self, volume, window=14):
        """거래량 정규화"""
        try:
            if len(volume) < window:
                raise ValueError(f"데이터가 부족합니다. 필요: {window}, 실제: {len(volume)}")
                
            rolling_max = volume.rolling(window=window).max()
            rolling_min = volume.rolling(window=window).min()
            
            # 분모가 0이 되는 경우 처리
            denominator = rolling_max - rolling_min
            denominator = denominator.replace(0, 1)  # 0을 1로 대체
            
            normalized = 99 * (volume - rolling_min) / denominator
            
            # NaN 값 처리
            normalized = normalized.fillna(method='ffill').fillna(50)
            
            # 범위를 벗어난 값 클리핑
            normalized = normalized.clip(0, 100)
            
            return normalized

        except Exception as e:
            print(f"거래량 정규화 중 오류 발생: {str(e)}")
            return pd.Series(index=volume.index)  # 빈 시리즈 반환
    
    def calculate_bollinger_bands(self, data):
        """볼린저 밴드 계산"""
        df = data.copy()
        
        # 중심선 (20일 이동평균)
        df['bb_middle'] = df['close'].rolling(window=self.BOLLINGER_PERIOD).mean()
        
        # 표준편차
        bb_std = df['close'].rolling(window=self.BOLLINGER_PERIOD).std()
        
        # 상단/하단 밴드
        df['bb_upper'] = df['bb_middle'] + (bb_std * self.BOLLINGER_STD)
        df['bb_lower'] = df['bb_middle'] - (bb_std * self.BOLLINGER_STD)
        
        return df

    def calculate_momentum(self, data, period=10):
        """모멘텀 지표 계산
        
        Args:
            data (pd.DataFrame): OHLCV 데이터
            period (int): 모멘텀 계산 기간 (기본값: 10)
            
        Returns:
            float: 현재 모멘텀 값 (백분율)
        """
        try:
            if len(data) < period + 1:
                print(f"모멘텀 계산을 위한 충분한 데이터가 없습니다. 필요: {period + 1}, 현재: {len(data)}")
                return 0.0
                
            # 현재 가격과 n기간 전 가격
            current_price = float(data['close'].iloc[-1])
            past_price = float(data['close'].iloc[-period-1])
            
            # 모멘텀 계산 (백분율)
            momentum = ((current_price - past_price) / past_price)
            
            # 디버깅 정보 출력
            print(f"\n모멘텀 계산 디버그:")
            print(f"현재 가격: {current_price:,.0f}")
            print(f"과거 가격({period}기간 전): {past_price:,.0f}")
            print(f"모멘텀: {momentum*100:.2f}%")
            
            return momentum
            
        except Exception as e:
            print(f"모멘텀 계산 중 오류: {e}")
            return 0.0

    def calculate_stoch_rsi(self, data, period=14, smoothK=3, smoothD=3):
        """
        수정된 Stochastic RSI 계산 함수
        
        Args:
            data (pd.Series): 가격 데이터
            period (int): RSI 및 Stoch RSI 계산 기간 (기본값: 14)
            smoothK (int): K 라인 스무딩 기간 (기본값: 3)
            smoothD (int): D 라인 스무딩 기간 (기본값: 3)
            
        Returns:
            tuple: (K 라인, D 라인)
        """
        try:
            # 충분한 데이터가 있는지 확인
            if len(data) < period + smoothK + smoothD:
                print(f"Stoch RSI 계산을 위한 충분한 데이터가 없습니다. 필요: {period + smoothK + smoothD}, 현재: {len(data)}")
                return pd.Series(50, index=data.index), pd.Series(50, index=data.index)

            # 기본 RSI 계산
            rsi = self.calculate_rsi(data)
            
            # Stochastic RSI 계산
            stoch_rsi = pd.DataFrame(index=data.index)
            
            # 각 시점에서 이전 period 기간 동안의 RSI 범위 계산
            for i in range(period, len(rsi)):
                period_rsi = rsi[i-period+1:i+1]
                high = period_rsi.max()
                low = period_rsi.min()
                current = rsi[i]
                
                # 분모가 0인 경우 처리 (RSI 최고값과 최저값이 같은 경우)
                if high == low:
                    stoch_rsi.loc[rsi.index[i], 'K'] = 50  # RSI가 변화없을 때는 중간값 사용
                else:
                    stoch_rsi.loc[rsi.index[i], 'K'] = 100 * (current - low) / (high - low)

            # K% 스무딩
            stoch_rsi['K'] = stoch_rsi['K'].rolling(window=smoothK, min_periods=1).mean()
            
            # D% 계산
            stoch_rsi['D'] = stoch_rsi['K'].rolling(window=smoothD, min_periods=1).mean()
            
            # NaN 값 처리
            stoch_rsi = stoch_rsi.fillna(method='ffill').fillna(50)
            
            # 0-100 범위로 제한
            stoch_rsi = stoch_rsi.clip(0, 100)
            
            # 디버깅 정보 출력
            last_k = stoch_rsi['K'].iloc[-1]
            last_d = stoch_rsi['D'].iloc[-1]
            last_rsi = rsi.iloc[-1]
            print(f"\nStoch RSI 디버그 정보:")
            print(f"기준 RSI: {last_rsi:.2f}")
            last_period_rsi = rsi.tail(period)
            print(f"최근 {period}기간 RSI 범위: {last_period_rsi.min():.2f} - {last_period_rsi.max():.2f}")
            print(f"K값: {last_k:.2f} (최근 {smoothK}기간 평균)")
            print(f"D값: {last_d:.2f} (최근 {smoothD}기간 평균)")
            
            if last_k <= 20:
                print("과매도 구간 (K ≤ 20)")
            elif last_k >= 80:
                print("과매수 구간 (K ≥ 80)")
                
            prev_k = stoch_rsi['K'].iloc[-2]
            prev_d = stoch_rsi['D'].iloc[-2]
            if prev_k < prev_d and last_k > last_d:
                print("K선이 D선을 상향돌파 (매수신호)")
            elif prev_k > prev_d and last_k < last_d:
                print("K선이 D선을 하향돌파 (매도신호)")
            
            return stoch_rsi['K'], stoch_rsi['D']

        except Exception as e:
            print(f"Stoch RSI 계산 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            return pd.Series(50, index=data.index), pd.Series(50, index=data.index)

    def calculate_indicators(self, data):
        """통합 지표 계산 및 분석 결과 포맷팅"""
        try:
            if data is None or len(data) == 0:
                print("데이터가 없거나 비어있습니다.")
                return None
                
            # 데이터 복사 및 유효성 확인
            df = data.copy()
            
            analysis_results = {}

            # 현재 가격 계산
            try:
                current_price = float(df['close'].iloc[-1])
                if pd.isna(current_price):
                    raise ValueError("현재 가격이 NaN입니다")
                analysis_results['current_price'] = current_price
                print(f"\nCurrent Price: {current_price}")
            except Exception as e:
                print(f"현재 가격 추출 중 오류: {e}")
                return None

            # KNN 예측
            try:
                prediction, confidence = self.predict_next_move(df)
                analysis_results['knn_prediction'] = prediction
                analysis_results['knn_signal_strength'] = confidence
                print(f"KNN 예측: {prediction}, 신뢰도: {confidence}")
            except Exception as e:
                print(f"KNN 예측 중 오류: {e}")
                analysis_results['knn_prediction'] = 0
                analysis_results['knn_signal_strength'] = 0

            # RSI 계산 부분 수정
            try:
                close_prices = df['close'].values
                close_series = pd.Series(close_prices)
                rsi = self.calculate_rsi(close_series)
                if rsi is not None and len(rsi) > 0:
                    analysis_results['rsi'] = float(rsi.iloc[-1])
                    
                    # Stoch RSI 계산 추가
                    stoch_k, stoch_d = self.calculate_stoch_rsi(close_series)
                    analysis_results['stoch_rsi_k'] = float(stoch_k.iloc[-1])
                    analysis_results['stoch_rsi_d'] = float(stoch_d.iloc[-1])
                    print(f"RSI: {analysis_results['rsi']}, Stoch RSI K: {analysis_results['stoch_rsi_k']:.1f}, D: {analysis_results['stoch_rsi_d']:.1f}")
                else:
                    analysis_results['rsi'] = 50.0
                    analysis_results['stoch_rsi_k'] = 50.0
                    analysis_results['stoch_rsi_d'] = 50.0
                    print("RSI 계산 실패, 기본값 50.0 사용")
            except Exception as e:
                print(f"RSI 계산 중 오류: {e}")
                analysis_results['rsi'] = 50.0
                analysis_results['stoch_rsi_k'] = 50.0
                analysis_results['stoch_rsi_d'] = 50.0

            # EMA Ribbon 계산
            try:
                ema_ribbon = self.calculate_ema_ribbon(df)
                ema_200 = self.calculate_ema_200(df)
                ema_status = self.analyze_ema_ribbon(ema_ribbon, current_price, ema_200)
                analysis_results['ema_ribbon_status'] = ema_status['status']
                analysis_results['ema_ribbon_status_num'] = ema_status['status_num']
                print(f"EMA Status: {ema_status['status']} (레벨: {ema_status['status_num']})")
            except Exception as e:
                print(f"EMA 계산 중 오류: {e}")
                analysis_results['ema_ribbon_status'] = "중립"
                analysis_results['ema_ribbon_status_num'] = 2  # 중립 상태를 2로 설정

            # 볼린저 밴드 계산
            try:
                bb_df = self.calculate_bollinger_bands(df)
                bb_upper = float(bb_df['bb_upper'].iloc[-1])
                bb_middle = float(bb_df['bb_middle'].iloc[-1])
                bb_lower = float(bb_df['bb_lower'].iloc[-1])
                
                analysis_results['bb_upper'] = bb_upper
                analysis_results['bb_middle'] = bb_middle
                analysis_results['bb_lower'] = bb_lower
                
                # 상단과 중간, 중간과 하단 사이의 간격을 3등분
                upper_third = bb_upper - ((bb_upper - bb_middle) * 0.33)
                lower_third = bb_lower + ((bb_middle - bb_lower) * 0.33)
                
                # 세분화된 위치 판단
                if current_price >= bb_upper:
                    bollinger_position = 5  # extreme_upper
                elif current_price >= upper_third:
                    bollinger_position = 4  # upper_strong
                elif current_price >= bb_middle:
                    bollinger_position = 3  # upper_weak
                elif current_price >= lower_third:
                    bollinger_position = 2  # lower_weak
                elif current_price >= bb_lower:
                    bollinger_position = 1  # lower_strong
                else:
                    bollinger_position = 0  # extreme_lower
                    
                # 숫자를 문자열로 매핑
                position_mapping = {
                    5: 'extreme_upper',
                    4: 'upper_strong',
                    3: 'upper_weak',
                    2: 'lower_weak',
                    1: 'lower_strong',
                    0: 'extreme_lower'
                }
                
                # 추가적인 볼린저 밴드 정보 계산
                band_width = ((bb_upper - bb_lower) / bb_middle) * 100  # 밴드폭
                price_position = ((current_price - bb_lower) / (bb_upper - bb_lower)) * 100  # 상대적 위치
                
                # 숫자와 문자열 모두 저장
                analysis_results['bollinger_position_num'] = bollinger_position
                analysis_results['bollinger_position'] = position_mapping[bollinger_position]
                analysis_results['band_width'] = band_width
                analysis_results['band_position_percentage'] = price_position
                
                print(f"Bollinger Position: {bollinger_position}")
                print(f"Band Width: {band_width:.2f}%")
                print(f"Price Position: {price_position:.2f}%")
                
            except Exception as e:
                print(f"볼린저 밴드 계산 중 오류: {e}")
                analysis_results['bollinger_position'] = 'undefined'
                analysis_results['bb_upper'] = current_price * 1.02
                analysis_results['bb_middle'] = current_price
                analysis_results['bb_lower'] = current_price * 0.98
                analysis_results['band_width'] = 4.0
                analysis_results['band_position_percentage'] = 50.0

            # 모멘텀 계산
            try:
                previous_price = float(df['close'].iloc[-2])
                momentum = (current_price - previous_price) / previous_price
                analysis_results['momentum'] = float(momentum)
                print(f"Momentum: {momentum}")
            except Exception as e:
                print(f"모멘텀 계산 중 오류: {e}")
                analysis_results['momentum'] = 0.0

            # 변동성 계산
            try:
                tr = pd.DataFrame()
                tr['hl'] = df['high'] - df['low']
                tr['hc'] = abs(df['high'] - df['close'].shift())
                tr['lc'] = abs(df['low'] - df['close'].shift())
                tr['tr'] = tr[['hl', 'hc', 'lc']].max(axis=1)
                volatility_ratio = (float(tr['tr'].rolling(window=10).mean().iloc[-1]) / current_price) * 100
                analysis_results['volatility_ratio'] = float(volatility_ratio)
                print(f"Volatility Ratio: {volatility_ratio}")
            except Exception as e:
                print(f"변동성 계산 중 오류: {e}")
                analysis_results['volatility_ratio'] = 0.0

            # 다이버전스 감지
            try:
                divergence = self.detect_divergence(df)
                analysis_results['divergence'] = {
                    'bearish_divergence': bool(divergence['bearish_divergence']),
                    'bullish_divergence': bool(divergence['bullish_divergence'])
                }
                print(f"Divergence: {analysis_results['divergence']}")
            except Exception as e:
                print(f"다이버전스 감지 중 오류: {e}")
                analysis_results['divergence'] = {
                    'bearish_divergence': False,
                    'bullish_divergence': False
                }

            # Counter trend 신호
            try:
                counter_trend_buy = (
                    current_price <= analysis_results['bb_lower'] and
                    analysis_results['rsi'] <= self.OVERSOLD_RSI and
                    analysis_results['momentum'] < -self.MOMENTUM_THRESHOLD and
                    analysis_results['divergence']['bullish_divergence'] and
                    analysis_results['volatility_ratio'] > self.VOLATILITY_THRESHOLD
                )
                
                counter_trend_sell = (
                    current_price >= analysis_results['bb_upper'] and
                    analysis_results['rsi'] >= self.OVERBOUGHT_RSI and
                    analysis_results['momentum'] > self.MOMENTUM_THRESHOLD and
                    analysis_results['divergence']['bearish_divergence'] and
                    analysis_results['volatility_ratio'] > self.VOLATILITY_THRESHOLD
                )
                
                analysis_results['counter_trend_signals'] = {
                    'buy': bool(counter_trend_buy),
                    'sell': bool(counter_trend_sell)
                }
                print(f"Counter Trend Signals - Buy: {counter_trend_buy}, Sell: {counter_trend_sell}")
            except Exception as e:
                print(f"Counter trend 신호 계산 중 오류: {e}")
                analysis_results['counter_trend_signals'] = {
                    'buy': False,
                    'sell': False
                }

            return analysis_results

        except Exception as e:
            print(f"지표 계산 중 오류 발생: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def analyze_ema_ribbon(self, ema_ribbon, current_price, ema_200):
        """개선된 EMA Ribbon 분석"""
        ribbon_values = ema_ribbon.iloc[-1]
        
        # EMA 값들의 기울기 계산 (추세의 강도를 더 정확히 측정)
        ema_slopes = {
            period: (ribbon_values[f'EMA_{period}'] - ema_ribbon[f'EMA_{period}'].iloc[-2]) 
            for period in [5, 10, 30, 50]
        }
        
        short_term_values = [ribbon_values['EMA_5'], ribbon_values['EMA_10']]
        long_term_values = [ribbon_values['EMA_30'], ribbon_values['EMA_50']]
        
        # 추세 강도 계산 개선
        trend_strength = sum(1 for short, long in zip(short_term_values, long_term_values) if short > long)
        slope_strength = sum(1 for slope in ema_slopes.values() if slope > 0)
        
        bullish_trend = current_price > ema_200
        
        # 상태 판단 로직 개선
        if trend_strength >= 2 and slope_strength >= 3 and bullish_trend:
            status_num = 4  # 강한 상승세
        elif trend_strength >= 2 and bullish_trend:
            status_num = 3  # 약한 상승세
        elif trend_strength == 1 or bullish_trend:
            status_num = 2  # 상승 가능성
        elif trend_strength == 0 and slope_strength <= 1:
            status_num = 1  # 약한 하락세
        else:
            status_num = 0  # 강한 하락세
            
        status_mapping = {
            4: '강한 상승세',
            3: '약한 상승세',
            2: '상승 가능성',
            1: '약한 하락세',
            0: '강한 하락세'
        }
        
        return {
            'status': status_mapping[status_num],
            'status_num': status_num
        }

    def detect_divergence(self, data):
        """가격과 기술적 지표 간의 다이버전스 감지"""
        # 데이터 포인트 수 증가 (15개 이상 확보)
        df = data.tail(20).copy()  # 20개로 증가
        
        # 가격 고점/저점
        price_highs = df['high'].rolling(window=3, center=True).max()
        price_lows = df['low'].rolling(window=3, center=True).min()
        
        # RSI 고점/저점
        rsi_values = self.calculate_rsi(df['close'])
        rsi_highs = rsi_values.rolling(window=3, center=True).max()
        rsi_lows = rsi_values.rolling(window=3, center=True).min()
        
        # 베어리시 다이버전스 (가격은 상승, RSI는 하락)
        bearish_div = (price_highs > price_highs.shift(1)) & (rsi_highs < rsi_highs.shift(1))
        
        # 불리시 다이버전스 (가격은 하락, RSI는 상승)
        bullish_div = (price_lows < price_lows.shift(1)) & (rsi_lows > rsi_lows.shift(1))
        
        return {
            'bearish_divergence': bearish_div.iloc[-1],
            'bullish_divergence': bullish_div.iloc[-1]
        }

    #----------------
    # 4. Machine Learning
    #----------------
    def prepare_knn_features(self, data):
        """개선된 KNN 특징 준비 함수
        
        Args:
            data (pd.DataFrame): OHLCV 데이터
            
        Returns:
            features: 준비된 특징 행렬
            labels: 레이블 벡터
        """
        try:
            df = data.copy()
            if df is None or df.empty:
                print("prepare_knn_features: 데이터가 없거나 비어있습니다")
                return None, None

            # 기본 지표 계산
            df['sma_20'] = df['close'].rolling(window=20).mean()
            df['std_20'] = df['close'].rolling(window=20).std()
            df['volume_ma'] = df['volume'].rolling(window=20).mean()
            
            # 볼린저 밴드
            df['bb_middle'] = df['sma_20']
            df['bb_upper'] = df['bb_middle'] + 2 * df['std_20']
            df['bb_lower'] = df['bb_middle'] - 2 * df['std_20']

            # 특징 데이터프레임 생성
            features = pd.DataFrame(index=df.index)

            # 1. 가격 모멘텀 특징들
            features['price_position'] = (df['close'] - df['sma_20']) / df['std_20']
            features['price_momentum'] = df['close'].pct_change(5)
            features['price_trend'] = np.where(df['close'] > df['sma_20'], 1, -1)
            
            # 2. 볼린저 밴드 관련 특징
            features['bb_position'] = (df['close'] - df['bb_middle']) / (df['bb_upper'] - df['bb_lower'])
            features['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
            
            # 3. 거래량 특징들
            features['volume_ratio'] = df['volume'] / df['volume_ma']
            features['volume_trend'] = df['volume'].pct_change(3)
            
            # 4. 변동성 특징
            features['volatility'] = df['close'].pct_change().rolling(window=20).std()
            
            # 5. RSI 추가
            features['rsi'] = self.calculate_rsi(df['close'])
            
            # 6. 이동평균 교차 신호
            ema_5 = df['close'].ewm(span=5, adjust=False).mean()
            ema_20 = df['close'].ewm(span=20, adjust=False).mean()
            features['ema_cross'] = np.where(ema_5 > ema_20, 1, -1)

            # 다음 기간의 수익률 계산 (레이블)
            df['next_return'] = df['close'].shift(-1) / df['close'] - 1
            df['next_direction'] = np.where(df['next_return'] > 0, 1, -1)

            # 특징 정규화 (이진 특징 제외)
            binary_features = ['price_trend', 'ema_cross']
            for col in features.columns:
                if col not in binary_features:
                    features[col] = (features[col] - features[col].mean()) / features[col].std()

            # NaN 제거
            features = features.replace([np.inf, -np.inf], np.nan)
            features = features.fillna(method='ffill').fillna(0)
            
            # 레이블 준비
            labels = df['next_direction'].fillna(0)

            return features.values, labels.values

        except Exception as e:
            print(f"KNN 특징 준비 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return None, None

    def prepare_current_features(self, current_data):
        """현재 시점의 특징 준비 함수
        
        Args:
            current_data (pd.DataFrame): 현재 시점까지의 OHLCV 데이터
            
        Returns:
            현재 시점의 특징 벡터
        """
        try:
            df = current_data.copy()
            
            # 기본 지표 계산
            df['sma_20'] = df['close'].rolling(window=20).mean()
            df['std_20'] = df['close'].rolling(window=20).std()
            df['volume_ma'] = df['volume'].rolling(window=20).mean()
            
            # 볼린저 밴드
            df['bb_middle'] = df['sma_20']
            df['bb_upper'] = df['bb_middle'] + 2 * df['std_20']
            df['bb_lower'] = df['bb_middle'] - 2 * df['std_20']
            
            # EMA 계산
            ema_5 = df['close'].ewm(span=5, adjust=False).mean()
            ema_20 = df['close'].ewm(span=20, adjust=False).mean()

            # 마지막 행 추출
            last_row = df.iloc[-1]
            
            # 현재 특징 벡터 생성
            current_features = np.array([
                (last_row['close'] - last_row['sma_20']) / last_row['std_20'],  # price_position
                df['close'].pct_change(5).iloc[-1],  # price_momentum
                1 if last_row['close'] > last_row['sma_20'] else -1,  # price_trend
                (last_row['close'] - last_row['bb_middle']) / (last_row['bb_upper'] - last_row['bb_lower']),  # bb_position
                (last_row['bb_upper'] - last_row['bb_lower']) / last_row['bb_middle'],  # bb_width
                last_row['volume'] / last_row['volume_ma'],  # volume_ratio
                df['volume'].pct_change(3).iloc[-1],  # volume_trend
                df['close'].pct_change().rolling(window=20).std().iloc[-1],  # volatility
                self.calculate_rsi(df['close']).iloc[-1],  # rsi
                1 if ema_5.iloc[-1] > ema_20.iloc[-1] else -1  # ema_cross
            ]).reshape(1, -1)
            
            # 이진 특징을 제외한 정규화
            binary_indices = [2, 9]  # price_trend와 ema_cross의 인덱스
            for i in range(current_features.shape[1]):
                if i not in binary_indices:
                    mean_val = df[df.columns[i]].mean()
                    std_val = df[df.columns[i]].std()
                    if std_val != 0:
                        current_features[0, i] = (current_features[0, i] - mean_val) / std_val

            return current_features

        except Exception as e:
            print(f"현재 특징 준비 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return None

    def find_k_nearest(self, features, labels, current_point, k=16):
        """개선된 K-최근접 이웃 찾기 함수
        
        Args:
            features: 과거 데이터의 특징 행렬
            labels: 과거 데이터의 레이블
            current_point: 현재 시점의 특징 벡터
            k: 이웃 개수
            
        Returns:
            k_nearest_labels: k개 이웃의 레이블
            k_nearest_distances: k개 이웃까지의 거리
            k_nearest_weights: k개 이웃의 가중치
        """
        try:
            if features is None or len(features) < k:
                print("find_k_nearest: 충분한 데이터가 없습니다")
                return np.array([]), np.array([]), np.array([])

            # 특징별 가중치 정의
            feature_weights = np.array([
                1.2,  # price_position
                1.0,  # price_momentum
                1.5,  # price_trend
                1.3,  # bb_position
                1.0,  # bb_width
                0.8,  # volume_ratio
                0.7,  # volume_trend
                1.1,  # volatility
                1.4,  # rsi
                1.2   # ema_cross
            ])
            
            # 시간 가중치 (최근 데이터에 더 높은 가중치)
            time_weights = np.exp(-np.arange(len(features)) / 100)
            
            # 가중치를 적용한 거리 계산
            weighted_features = features * feature_weights
            weighted_current = current_point * feature_weights
            
            # 거리 계산
            distances = np.zeros(len(features))
            for i in range(len(features)):
                # 유클리디안 거리 계산
                dist = np.sqrt(np.sum((weighted_features[i] - weighted_current) ** 2))
                # 시간 가중치 적용
                distances[i] = dist * (1 / time_weights[i])

            # 거리에 따른 가중치 계산 (지수 감쇠)
            weights = np.exp(-distances)
            weights = weights / np.sum(weights)  # 정규화
            
            # k개의 가장 가까운 이웃 찾기
            k_nearest_indices = np.argsort(distances)[:k]
            k_nearest_labels = labels[k_nearest_indices]
            k_nearest_distances = distances[k_nearest_indices]
            k_nearest_weights = weights[k_nearest_indices]
            
            return k_nearest_labels, k_nearest_distances, k_nearest_weights

        except Exception as e:
            print(f"K-최근접 이웃 찾기 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return np.array([]), np.array([]), np.array([])

    def calculate_adaptive_k(self, data_size, volatility):
        """데이터 크기와 변동성에 따른 적응형 K값 계산"""
        try:
            # 기본 K값 설정
            base_k = 16
            
            # 데이터 크기에 따른 조정
            size_factor = np.clip(data_size / 100, 0.5, 2.0)
            
            # 변동성에 따른 조정 (변동성이 높을수록 더 적은 이웃 사용)
            volatility_factor = np.clip(1 - volatility, 0.5, 1.5)
            
            # 최종 K값 계산
            adjusted_k = int(base_k * size_factor * volatility_factor)
            
            # K값 범위 제한
            final_k = np.clip(adjusted_k, 8, 32)
            
            print(f"적응형 K값 계산:")
            print(f"데이터 크기: {data_size}, 크기 팩터: {size_factor:.2f}")
            print(f"변동성: {volatility:.2f}, 변동성 팩터: {volatility_factor:.2f}")
            print(f"조정된 K값: {final_k}")
            
            return final_k
            
        except Exception as e:
            print(f"적응형 K값 계산 중 오류: {e}")
            return 16  # 오류 발생시 기본값 반환

    def predict_next_move(self, data):
        """개선된 다음 움직임 예측 함수"""
        try:
            # 특징과 레이블 준비
            features, labels = self.prepare_knn_features(data)
            if features is None or labels is None:
                return 0, 0
                    
            # 현재 특징 준비
            current_data = data.tail(50).copy()
            current_features = self.prepare_current_features(current_data)
            if current_features is None:
                return 0, 0
                    
            # 적응형 k값 계산
            k = self.calculate_adaptive_k(
                data_size=len(features),
                volatility=data['close'].pct_change().std()
            )
                    
            # 최근접 이웃 찾기
            k_nearest_labels, distances, weights = self.find_k_nearest(
                features[:-1], 
                labels[:-1], 
                current_features,
                k=k
            )
            
            if len(k_nearest_labels) == 0:
                return 0, 0
            
            # 가중 투표로 예측 (신호 강도 조절)
            weighted_sum = np.sum(k_nearest_labels * weights)
            
            # 신호 강도 조절을 위한 시그모이드 함수 적용 (더 엄격하게)
            signal_strength = 2 / (1 + np.exp(-1.5 * weighted_sum)) - 1  # 기울기 증가로 더 강한 신호 요구
            
            # 더 세분화된 신호 강도 구간 분류 (임계값 상향)
            if abs(signal_strength) < 0.25:  # 중립 구간 확대
                prediction = 0  # 중립
            elif abs(signal_strength) < 0.4:  # 약한 신호 구간 확대
                prediction = np.sign(signal_strength) * 0.25  # 매우 약한 신호
            elif abs(signal_strength) < 0.6:
                prediction = np.sign(signal_strength) * 0.5  # 약한 신호
            elif abs(signal_strength) < 0.8:
                prediction = np.sign(signal_strength) * 0.75  # 중강도 신호
            else:
                prediction = np.sign(signal_strength) * 0.8  # 강한 신호 (최대치 제한)
            
            # 1. 방향 일치도 계산 (35% 비중으로 하향)
            direction_agreement = np.mean(k_nearest_labels == np.sign(prediction))
            strong_signal = np.mean(abs(weighted_sum) > 0.6)  # 강한 신호 기준 상향
            direction_confidence = (direction_agreement * 0.7 + strong_signal * 0.3) * 35
            
            # 2. 거리 기반 신뢰도 (35% 비중)
            closest_neighbors = distances[:int(len(distances) * 0.3)]  # 상위 30%로 축소
            max_distance = np.percentile(distances, 90)  # 90 퍼센타일로 강화
            distance_confidence = (1 - (np.mean(closest_neighbors) / max_distance)) * 35
            
            # 3. 가중치 분포 (15% 비중)
            top_weights = weights[:int(len(weights) * 0.25)]  # 상위 25%로 축소
            weight_concentration = min((np.mean(top_weights) / np.mean(weights)) * 15, 15)
            
            # 4. 신호 강도 기반 신뢰도 (15% 비중)
            signal_base = abs(signal_strength)
            signal_boost = min(np.exp(signal_base) / (np.e * 1.5), 1.0)  # 부스트 감소
            signal_confidence = signal_boost * 15
            
            # 최종 신뢰도 계산 및 스케일링
            base_confidence = (
                direction_confidence +
                distance_confidence +
                weight_concentration +
                signal_confidence
            )
            
            # 초기 신뢰도에 대한 비선형 스케일링 적용 (더 엄격하게)
            scaled_confidence = 25 + (base_confidence * 1.1)  # 기본 스케일 하향
            
            # 변동성 기반 신뢰도 조정 (더 민감하게)
            recent_volatility = data['close'].pct_change().rolling(20).std().iloc[-1]
            volatility_factor = np.clip(1 - (recent_volatility * 5), 0.8, 1.05)  # 변동성 영향 강화
            confidence = scaled_confidence * volatility_factor
            
            # 연속성 보너스 조정 (감소)
            if hasattr(self, 'last_prediction') and self.last_prediction is not None:
                if np.sign(prediction) == np.sign(self.last_prediction):
                    confidence = confidence * 1.05  # 5% 부스트로 감소
            self.last_prediction = prediction
            
            # 신뢰도 범위 제한 (더 엄격하게)
            confidence = np.clip(confidence, 30, 95) 
            
            # 신호 강도에 따른 신뢰도 조정 (더 엄격하게)
            if abs(signal_strength) < 0.3:  # 매우 약한 신호 임계값 상향
                confidence = confidence * 0.65
            elif abs(signal_strength) < 0.45:  # 약한 신호 임계값 상향
                confidence = confidence * 0.8
            elif abs(signal_strength) > 0.7:  # 강한 신호 임계값 상향
                confidence = min(confidence * 1.1, 95)  # 최대 95로 제한
            
            # 디버깅 정보 출력
            print(f"\nKNN 예측 세부 정보:")
            print(f"신호 강도: {signal_strength:.3f}")
            print(f"예측값: {prediction:.3f}")
            print(f"방향 일치도: {direction_confidence:.1f}/35")
            print(f"거리 기반 신뢰도: {distance_confidence:.1f}/35")
            print(f"가중치 분포: {weight_concentration:.1f}/15")
            print(f"신호 강도 신뢰도: {signal_confidence:.1f}/15")
            print(f"기본 신뢰도: {base_confidence:.1f}")
            print(f"스케일링 후 신뢰도: {scaled_confidence:.1f}")
            print(f"변동성 팩터: {volatility_factor:.2f}")
            print(f"최종 신뢰도: {confidence:.1f}%")
            
            return prediction, confidence

        except Exception as e:
            print(f"다음 움직임 예측 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return 0, 0
        
    #----------------
    # 5. Trading Logic
    #----------------
    def generate_trading_signal(self, data, market_changed=False, force_check=False):
            """향상된 트레이딩 신호 생성"""
            default_gpt_advice = {
                'trade_recommendation': '관망',
                'investment_percentage': 0,
                'confidence_score': 0,
                'reasoning': '기본값'
            }
            
            default_response = (False, False, default_gpt_advice, None)

            try:
                if data is None:
                    print("❌ 데이터 없음")
                    return default_response

                current_price = pyupbit.get_current_price(self.ticker)
                if current_price is None:
                    print("❌ 현재 가격 조회 실패")
                    return default_response
                print(f"현재 가격: {current_price:,} KRW")

                try:
                    balance = self.upbit.get_balance("KRW")
                    coin_balance = self.upbit.get_balance(self.ticker)
                    net_balance = balance * (1 - self.TRADING_FEE_RATE)
                    expected_sell_value = coin_balance * current_price * (1 - self.TRADING_FEE_RATE)
                    print(f"KRW 잔고: {balance:,} 원")
                    print(f"BTC 잔고: {coin_balance:.8f}")

                    # 최소 주문금액 체크
                    if net_balance < self.MIN_ORDER_AMOUNT and expected_sell_value < self.MIN_ORDER_AMOUNT:
                        print(f"❌ 최소 주문금액({self.MIN_ORDER_AMOUNT:,}원) 미달")
                        return default_response

                except Exception as e:
                    print(f"❌ 기본 정보 조회 실패: {e}")
                    return default_response

                analysis_results = self.calculate_indicators(data)
                if analysis_results is None:
                    print("❌ 기술적 분석 실패")
                    return default_response

                analysis_results['current_price'] = current_price
                print(f"\n기술적 분석 - RSI: {analysis_results['rsi']:.2f}, 변동성: {analysis_results['volatility_ratio']:.2f}%")

                try:
                    gpt_advice = self.consult_gpt_for_trading(data, analysis_results, market_changed, force_check)
                    if gpt_advice is None:
                        print("❌ GPT 자문 실패")
                        gpt_advice = default_gpt_advice.copy()
                    print(f"\nGPT 자문: {gpt_advice.get('trade_recommendation')}, 신뢰도: {gpt_advice.get('confidence_score')}%")
                except Exception as e:
                    print(f"❌ GPT 자문 처리 실패: {e}")
                    gpt_advice = default_gpt_advice.copy()

                buy_signal = (gpt_advice['trade_recommendation'] == '매수' and net_balance >= self.MIN_ORDER_AMOUNT)
                sell_signal = (gpt_advice['trade_recommendation'] == '매도' and expected_sell_value >= self.MIN_ORDER_AMOUNT)

                print(f"\n최종 신호 - 매수: {buy_signal}, 매도: {sell_signal}")
                if not buy_signal and gpt_advice['trade_recommendation'] == '매수':
                    print(f"매수 신호 무시: 최소 주문금액 미달 (필요: {self.MIN_ORDER_AMOUNT:,}원, 가능: {net_balance:,.0f}원)")
                if not sell_signal and gpt_advice['trade_recommendation'] == '매도':
                    print(f"매도 신호 무시: 최소 주문금액 미달 (필요: {self.MIN_ORDER_AMOUNT:,}원, 가능: {expected_sell_value:,.0f}원)")

                return buy_signal, sell_signal, gpt_advice, analysis_results

            except Exception as e:
                print(f"❌ 거래 신호 생성 중 오류: {e}")
                import traceback
                traceback.print_exc()
                return default_response

    def is_significant_level_change(self, current_level, base_level, indicator_type='ema'):
        """의미있는 레벨 변화인지 확인"""
        # 2단계 이상 차이
        if abs(current_level - base_level) >= 2:
            return True
            
        # 특정 임계값을 넘어가는 경우
        if indicator_type == 'ema':
            significant_boundaries = {
                2: [0, 4],  # 레벨 2에서 0이나 4로 갈 때
                3: [0, 4]   # 레벨 3에서 0이나 4로 갈 때
            }
        else:  # bollinger
            significant_boundaries = {
                2: [0, 4, 5],  # 레벨 2에서 0, 4, 5로 갈 때
                3: [0, 5]      # 레벨 3에서 0이나 5로 갈 때
            }
        
        if base_level in significant_boundaries:
            return current_level in significant_boundaries[base_level]
            
        return False

    def monitor_knn_changes(self, current_knn, last_knn, current_time):
        """KNN 예측 방향 변화 감지 함수"""
        try:
            knn_direction_change = False
            
            # 현재 방향 결정
            if abs(current_knn) < self.KNN_SIGNAL_MIN_STRENGTH:
                current_direction = 'neutral'
            else:
                current_direction = 'up' if current_knn > 0 else 'down'
                
            # 이전 방향 확인
            if self.last_knn_direction is None:
                self.last_knn_direction = current_direction
                return False
                
            # 방향 전환 감지
            if current_direction != self.last_knn_direction and current_direction != 'neutral':
                # 쿨다운 확인
                if (self.last_knn_change_time is None or 
                    current_time - self.last_knn_change_time >= self.KNN_CHANGE_COOLDOWN):
                    
                    # 충분한 강도 차이 확인
                    if abs(current_knn - last_knn) >= self.KNN_DIRECTION_CHANGE_THRESHOLD:
                        knn_direction_change = True
                        self.last_knn_change_time = current_time
                        self.last_knn_direction = current_direction
                        
                        print("\nKNN 예측 방향 변화 감지:")
                        print(f"- 이전 예측: {last_knn:+.2f}")
                        print(f"- 현재 예측: {current_knn:+.2f}")
                        print(f"- 새로운 예측: {current_direction} ")
                        print(f"- 신호 강도 변화: {abs(current_knn - last_knn):.2f}")
                else:
                    cooldown_remaining = (self.KNN_CHANGE_COOLDOWN - 
                                        (current_time - self.last_knn_change_time)) / 60
                    print(f"\nKNN 방향 전환 쿨다운 중... (남은 시간: {cooldown_remaining:.1f}분)")
                    
            return knn_direction_change
            
        except Exception as e:
            print(f"KNN 변화 감지 중 오류: {e}")
            return False

    def monitor_market_conditions(self, data, analysis_results):
        """시장 상황 모니터링 및 유의미한 변화 감지"""
        try:
            # 1. 데이터 유효성 검사
            if data is None or analysis_results is None:
                print("데이터 또는 분석 결과가 없습니다.")
                return True
                    
            if data.empty or 'close' not in data.columns:
                print("가격 데이터가 유효하지 않습니다.")
                return True

            # 2. 필수 키 확인
            required_keys = [
                'rsi', 'volatility_ratio', 'ema_ribbon_status', 
                'ema_ribbon_status_num', 'momentum', 'bollinger_position', 
                'bollinger_position_num', 'stoch_rsi_k', 'stoch_rsi_d',
                'knn_prediction'
            ]
                
            if not all(key in analysis_results for key in required_keys):
                missing_keys = [key for key in required_keys if key not in analysis_results]
                print(f"분석 결과에 필요한 키가 없습니다: {missing_keys}")
                return True

            # 3. 현재 상태 데이터 구성
            try:
                current_state = {
                    'price': float(data['close'].iloc[-1]),
                    'rsi': float(analysis_results['rsi']),
                    'volatility': float(analysis_results['volatility_ratio']),
                    'ema_status': str(analysis_results['ema_ribbon_status']),
                    'ema_ribbon_status_num': int(analysis_results['ema_ribbon_status_num']),
                    'ema_base_num': int(analysis_results['ema_ribbon_status_num']),
                    'momentum': float(analysis_results['momentum']),
                    'bollinger_position': str(analysis_results['bollinger_position']),
                    'bollinger_position_num': int(analysis_results['bollinger_position_num']),
                    'bollinger_base_num': int(analysis_results['bollinger_position_num']),
                    'ema_direction': 'neutral',
                    'bb_direction': 'neutral',
                    'ema_change_start_time': time.time(),
                    'bb_change_start_time': time.time(),
                    'stoch_rsi_k': float(analysis_results['stoch_rsi_k']),
                    'stoch_rsi_d': float(analysis_results['stoch_rsi_d']),
                    'knn_prediction': float(analysis_results['knn_prediction'])
                }
            except (ValueError, TypeError) as e:
                print(f"데이터 변환 중 오류: {e}")
                return True

            # 4. 이전 상태 확인
            if not hasattr(self, 'last_gpt_market_state') or self.last_gpt_market_state is None:
                print("마지막 GPT 자문 시점의 시장 상태 정보 없음")
                return True

            current_time = time.time()

            # 5. Stoch RSI 변화 감지
            last_k = self.last_gpt_market_state.get('stoch_rsi_k', 50)
            last_d = self.last_gpt_market_state.get('stoch_rsi_d', 50)
            current_k = current_state['stoch_rsi_k']
            current_d = current_state['stoch_rsi_d']

            # K와 D의 차이 계산
            current_diff = current_k - current_d
            last_diff = last_k - last_d

            # 크로스 감지 로직
            stoch_cross_up = False
            stoch_cross_down = False
            
            if last_diff < 0 and current_diff > 0:  # 상향돌파 가능성
                if abs(current_diff) >= self.STOCH_CROSS_THRESHOLD:  # 최소 차이 확인
                    if (self.last_stoch_cross_time is None or 
                        current_time - self.last_stoch_cross_time >= self.STOCH_CROSS_COOLDOWN or
                        self.last_stoch_cross_type == 'down'):  # 다른 방향 크로스는 즉시 허용
                        stoch_cross_up = True
                        self.last_stoch_cross_time = current_time
                        self.last_stoch_cross_type = 'up'
                    else:
                        cooldown_remaining = (self.STOCH_CROSS_COOLDOWN - 
                                            (current_time - self.last_stoch_cross_time)) / 60
                        if cooldown_remaining > 0:
                            print(f"Stoch RSI 상향돌파 쿨다운 중... (남은 시간: {cooldown_remaining:.1f}분)")
            
            elif last_diff > 0 and current_diff < 0:  # 하향돌파 가능성
                if abs(current_diff) >= self.STOCH_CROSS_THRESHOLD:  # 최소 차이 확인
                    if (self.last_stoch_cross_time is None or 
                        current_time - self.last_stoch_cross_time >= self.STOCH_CROSS_COOLDOWN or
                        self.last_stoch_cross_type == 'up'):  # 다른 방향 크로스는 즉시 허용
                        stoch_cross_down = True
                        self.last_stoch_cross_time = current_time
                        self.last_stoch_cross_type = 'down'
                    else:
                        cooldown_remaining = (self.STOCH_CROSS_COOLDOWN - 
                                            (current_time - self.last_stoch_cross_time)) / 60
                        if cooldown_remaining > 0:
                            print(f"Stoch RSI 하향돌파 쿨다운 중... (남은 시간: {cooldown_remaining:.1f}분)")

            # 과매수/과매도 구간 진입 감지
            stoch_oversold = current_k <= 20 and last_k > 20
            stoch_overbought = current_k >= 80 and last_k < 80

            significant_stoch_change = (
                stoch_cross_up or 
                stoch_cross_down or 
                stoch_oversold or 
                stoch_overbought or
                abs(current_k - last_k) > 15  # K값이 15 이상 급격히 변화
            )

            # 6. KNN 예측 방향 변화 감지
            last_knn = self.last_gpt_market_state.get('knn_prediction', 0)
            current_knn = current_state['knn_prediction']
            
            knn_direction_change = self.monitor_knn_changes(
                current_knn=current_knn,
                last_knn=last_knn,
                current_time=current_time
            )

            # 7. 기존 지표들의 변화 감지
            price_change = abs(current_state['price'] - self.last_gpt_market_state['price']) / self.last_gpt_market_state['price']
            significant_price_change = price_change > 0.005
            
            rsi_change = abs(current_state['rsi'] - self.last_gpt_market_state['rsi'])
            significant_rsi_change = rsi_change > 5
            
            volatility_change = abs(current_state['volatility'] - self.last_gpt_market_state['volatility'])
            significant_volatility_change = volatility_change > 0.1

            # 8. EMA 변화 감지
            current_ema_num = current_state['ema_ribbon_status_num']
            base_ema_num = self.last_gpt_market_state.get('ema_base_num', current_ema_num)
            last_ema_num = self.last_gpt_market_state.get('ema_ribbon_status_num', current_ema_num)
            
            if current_ema_num > last_ema_num:
                current_ema_direction = 'up'
            elif current_ema_num < last_ema_num:
                current_ema_direction = 'down'
            else:
                current_ema_direction = self.last_gpt_market_state.get('ema_direction', 'neutral')

            last_ema_direction = self.last_gpt_market_state.get('ema_direction', 'neutral')
            last_ema_change_time = self.last_gpt_market_state.get('ema_change_start_time', current_time)

            ema_significant_change = (
                current_ema_direction != last_ema_direction and
                abs(current_ema_num - base_ema_num) >= 2
            )

            # 9. 볼린저 밴드 변화 감지
            current_bb_num = current_state['bollinger_position_num']
            base_bb_num = self.last_gpt_market_state.get('bollinger_base_num', current_bb_num)
            last_bb_num = self.last_gpt_market_state.get('bollinger_position_num', current_bb_num)

            if current_bb_num > last_bb_num:
                current_bb_direction = 'up'
            elif current_bb_num < last_bb_num:
                current_bb_direction = 'down'
            else:
                current_bb_direction = self.last_gpt_market_state.get('bb_direction', 'neutral')

            bb_significant_change = (
                current_bb_direction != self.last_gpt_market_state.get('bb_direction', 'neutral') and
                abs(current_bb_num - base_bb_num) >= 2
            )

            # 10. 모멘텀 방향 변화 감지
            MOMENTUM_THRESHOLD = 0.01
            momentum_direction_change = (
                (current_state['momentum'] > MOMENTUM_THRESHOLD and 
                self.last_gpt_market_state['momentum'] < -MOMENTUM_THRESHOLD) or
                (current_state['momentum'] < -MOMENTUM_THRESHOLD and 
                self.last_gpt_market_state['momentum'] > MOMENTUM_THRESHOLD)
            )

            # 11. 변화 상태 통합 및 출력
            significant_change = (
                significant_price_change or
                significant_rsi_change or
                significant_volatility_change or
                ema_significant_change or
                momentum_direction_change or
                bb_significant_change or
                significant_stoch_change or
                knn_direction_change
            )

            if significant_change:
                print("\n유의미한 변화 감지:")

                # Stoch RSI 변화 출력
                if significant_stoch_change:
                    print("\nStoch RSI 변화:")
                    if stoch_cross_up:
                        print(f"- 골든크로스 발생 (K-D: {current_diff:.1f}%)")
                    if stoch_cross_down:
                        print(f"- 데드크로스 발생 (K-D: {current_diff:.1f}%)")
                    if stoch_oversold:
                        print("- 과매도 구간 진입")
                    if stoch_overbought:
                        print("- 과매수 구간 진입")
                    print(f"- K값 변화: {last_k:.1f} → {current_k:.1f}")
                    print(f"- K-D 차이: {current_diff:.1f}%")

                # KNN 변화 출력
                if knn_direction_change:
                    print("\nKNN 변화:")
                    print(f"- 이전 예측: {last_knn:+.2f}")
                    print(f"- 현재 예측: {current_knn:+.2f}")
                    print(f"- 신호 강도 변화: {abs(current_knn - last_knn):.2f}")

                # 가격 및 기술적 지표 변화 출력
                changes = {
                    '가격 변화': f"{price_change*100:.3f}%" if significant_price_change else None,
                    'RSI 변화': f"{rsi_change:.2f}" if significant_rsi_change else None,
                    '변동성 변화': f"{volatility_change:.3f}" if significant_volatility_change else None,
                    'EMA 상태 변화': "감지됨" if ema_significant_change else None,
                    '모멘텀 방향 변화': "감지됨" if momentum_direction_change else None,
                    '볼린저 밴드 변화': "감지됨" if bb_significant_change else None
                }
                
                for key, value in changes.items():
                    if value:
                        print(f"- {key}: {value}")

            return significant_change

        except Exception as e:
            print(f"시장 상황 모니터링 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return True

    def _print_market_changes(self, current_state, current_diff, stoch_cross_up, 
                            stoch_cross_down, stoch_oversold, stoch_overbought,
                            current_k, last_k, current_knn, last_knn,
                            price_change, rsi_change, volatility_change,
                            ema_significant_change, momentum_direction_change,
                            bb_significant_change):
        """변화 상태 출력 함수"""
        
        # Stoch RSI 변화 출력
        if stoch_cross_up or stoch_cross_down or stoch_oversold or stoch_overbought:
            print("\nStoch RSI 유의미한 변화 감지:")
            if stoch_cross_up:
                print(f"- 골든크로스 발생 (K-D: {current_diff:.1f}%)")
            if stoch_cross_down:
                print(f"- 데드크로스 발생 (K-D: {current_diff:.1f}%)")
            if stoch_oversold:
                print("- 과매도 구간 진입")
            if stoch_overbought:
                print("- 과매수 구간 진입")
            print(f"- K값 변화: {last_k:.1f} → {current_k:.1f}")
            print(f"- K-D 차이: {current_diff:.1f}%")

        # KNN 변화 출력
        if current_knn != last_knn:
            print("\nKNN 예측 방향 변화 감지:")
            print(f"- 이전 예측: {last_knn:+.2f}")
            print(f"- 현재 예측: {current_knn:+.2f}")
            direction = "상승" if current_knn > 0 else "하락"
            strength = "강" if abs(current_knn) > 0.5 else "중" if abs(current_knn) > 0.2 else "약"
            print(f"- 새로운 예측: {direction} ({strength}한 신호)")

        # 종합 변화 출력
        print("\n유의미한 변화 감지:")
        changes = {
            '가격 변화': f"{price_change*100:.3f}%" if price_change > 0.005 else None,
            'RSI 변화': f"{rsi_change:.2f}" if rsi_change > 5 else None,
            '변동성 변화': f"{volatility_change:.3f}" if volatility_change > 0.1 else None,
            'EMA 상태 변화': "감지됨" if ema_significant_change else None,
            '모멘텀 방향 변화': "감지됨" if momentum_direction_change else None,
            '볼린저 밴드 변화': "감지됨" if bb_significant_change else None
        }
        
        for key, value in changes.items():
            if value:
                print(f"- {key}: {value}")

    def execute_trade(self, buy_signal, sell_signal, gpt_advice, analysis_results):
        """거래 실행 로직"""
        try:
            if analysis_results is None:
                print("분석 결과가 없습니다.")
                return False

            # GPT 자문 확인
            gpt_confidence = gpt_advice.get('confidence_score', 0)
            trade_recommendation = gpt_advice.get('trade_recommendation', '관망')

            print(f"\n=== 거래 실행 검토 ===")
            print(f"GPT 추천: {trade_recommendation}, 신뢰도: {gpt_confidence}%")

            current_price = pyupbit.get_current_price(self.ticker)
            if current_price is None:
                print("현재 가격을 가져올 수 없습니다.")
                return False

            balance = self.upbit.get_balance("KRW")
            coin_balance = self.upbit.get_balance(self.ticker.split('-')[1])

            # 매수 로직
            if buy_signal and trade_recommendation == '매수' and gpt_confidence >= 60:
                # 총자산 계산
                total_assets = balance + (coin_balance * current_price)
                
                # 현재 BTC 보유 비율 계산
                current_BTC_ratio = (coin_balance * current_price) / total_assets * 100 if total_assets > 0 else 0
                
                # GPT가 제안한 목표 BTC 보유 비율
                target_BTC_ratio = gpt_advice.get('investment_percentage', 10)
                
                # 목표 비율과 현재 비율 차이 계산
                ratio_difference = target_BTC_ratio - current_BTC_ratio
                
                print(f"\n=== 매수 분석 ===")
                print(f"총자산: {total_assets:,.0f} KRW")
                print(f"현재 BTC 비율: {current_BTC_ratio:.2f}%")
                print(f"목표 BTC 비율: {target_BTC_ratio:.2f}%")
                print(f"비율 차이: {ratio_difference:.2f}%")

                if ratio_difference > 1:  # 1% 이상 차이가 날 때만 매수
                    # 추가로 필요한 BTC 가치 계산
                    additional_BTC_value = total_assets * (ratio_difference / 100)
                    buy_amount = min(additional_BTC_value * 0.9995, balance * 0.9995)

                    if buy_amount >= self.MIN_ORDER_AMOUNT:
                        try:
                            print(f"\n매수 주문 시도:")
                            print(f"주문 금액: {buy_amount:,.0f} KRW")
                            
                            order = self.upbit.buy_market_order(self.ticker, buy_amount)
                            
                            if order and 'uuid' in order:
                                print(f"매수 성공! 주문 ID: {order['uuid']}")
                                self.log_trade(
                                    trade_type='buy',
                                    amount=buy_amount,
                                    price=current_price,
                                    confidence_score=gpt_confidence,
                                    reasoning=gpt_advice.get('reasoning', '매수 실행'),
                                    rsi=analysis_results['rsi'],
                                    volatility=analysis_results['volatility_ratio'],
                                    strategy_type='gpt_advised'
                                )
                                return True
                            else:
                                print(f"매수 주문 실패: {order}")
                        except Exception as e:
                            print(f"매수 주문 중 오류: {e}")
                            return False
                    else:
                        print(f"최소 주문 금액({self.MIN_ORDER_AMOUNT:,} KRW)보다 작은 주문")
                else:
                    print(f"현재 BTC 보유 비율이 충분합니다. 추가 매수가 필요하지 않습니다.")
                    self.log_trade(
                        trade_type='hold',
                        amount=0,
                        price=current_price,
                        confidence_score=gpt_confidence,
                        reasoning=f"현재 BTC 보유 비율({current_BTC_ratio:.2f}%)이 목표 비율({target_BTC_ratio:.2f}%)에 근접",
                        rsi=analysis_results['rsi'],
                        volatility=analysis_results['volatility_ratio'],
                        strategy_type='gpt_advised'
                    )
                        
            # 매도 로직
            elif sell_signal and trade_recommendation == '매도' and gpt_confidence >= 60:
                if coin_balance > 0:
                    sell_ratio = gpt_advice.get('investment_percentage', 10) / 100
                    base_sell_amount = coin_balance * sell_ratio
                    
                    expected_value = base_sell_amount * current_price * (1 - self.TRADING_FEE_RATE)
                    
                    print(f"\n=== 매도 분석 ===")
                    print(f"보유 BTC: {coin_balance:.8f}")
                    print(f"매도 비율: {sell_ratio*100:.1f}%")
                    print(f"매도 수량: {base_sell_amount:.8f}")
                    print(f"예상 가치: {expected_value:,.0f} KRW")
                    
                    if expected_value >= self.MIN_ORDER_AMOUNT:
                        try:
                            print(f"\n매도 주문 시도:")
                            print(f"매도 수량: {base_sell_amount:.8f} BTC")
                            print(f"예상 가치: {expected_value:,.0f} KRW")
                            
                            order = self.upbit.sell_market_order(self.ticker, base_sell_amount)
                            
                            if order and 'uuid' in order:
                                print(f"매도 성공! 주문 ID: {order['uuid']}")
                                self.log_trade(
                                    trade_type='sell',
                                    amount=base_sell_amount,
                                    price=current_price,
                                    confidence_score=gpt_confidence,
                                    reasoning=gpt_advice.get('reasoning', '매도 실행'),
                                    rsi=analysis_results['rsi'],
                                    volatility=analysis_results['volatility_ratio'],
                                    strategy_type='gpt_advised'
                                )
                                return True
                            else:
                                print(f"매도 주문 실패: {order}")
                        except Exception as e:
                            print(f"매도 주문 중 오류: {e}")
                            return False
                    else:
                        print(f"매도 금액이 최소 주문 금액보다 작음 ({expected_value:,.0f} < {self.MIN_ORDER_AMOUNT:,} KRW)")
                else:
                    print("매도 가능한 코인 잔액 없음")
            else:
                print("\n관망 상태 유지")
                self.log_trade(
                    trade_type='hold',
                    amount=0,
                    price=current_price,
                    confidence_score=gpt_confidence,
                    reasoning=f"GPT 추천: {trade_recommendation}, 신뢰도: {gpt_confidence}%",
                    rsi=analysis_results['rsi'],
                    volatility=analysis_results['volatility_ratio'],
                    strategy_type='gpt_advised'
                )
                
            return False
                
        except Exception as e:
            print(f"거래 실행 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    def check_significant_market_change(self, last_state, current_state):
        """시장 상황의 유의미한 변화 감지"""
        if not last_state or not current_state:
            return True
            
        try:
            # 가격 변화 확인
            price_change = abs(current_state['price'] - last_state['price']) / last_state['price']
            
            # RSI 변화 확인
            rsi_change = abs(current_state['rsi'] - last_state['rsi'])
            
            # 변동성 변화 확인
            volatility_change = abs(current_state['volatility'] - last_state['volatility'])
            
            # 볼린저 밴드 포지션 변화 (2단계 이상)
            position_change = abs(current_state['bollinger_position_num'] - last_state.get('bollinger_position_num', 0))
            significant_position_change = position_change >= 2
            
            # 시장 상황 변화 판단
            significant_change = (
                price_change > self.MARKET_CHANGE_THRESHOLD or  # 가격 2% 이상 변화
                rsi_change > 10 or  # RSI 10 이상 변화
                volatility_change > 0.1 or  # 변동성 10% 이상 변화
                significant_position_change  # 볼린저 밴드 2단계 이상 변화
            )
            
            return significant_change
            
        except Exception as e:
            print(f"시장 변화 감지 중 오류: {e}")
            return True  # 오류 발생 시 안전하게 True 반환

    def consult_gpt_for_trading(self, data, analysis_results, market_changed=None, force_check=False):
        """시장 상황에 따른 GPT 자문 요청 (이전 자문 내역 포함)"""
        try:
            if not market_changed and not force_check:
                return {
                    'trade_recommendation': '관망',
                    'investment_percentage': 0,
                    'confidence_score': 50,
                    'reasoning': '시장 상황 유지 중'
                }

            try:
                ohlcv_data = pyupbit.get_ohlcv(self.ticker, interval=self.interval, count=60)
                if ohlcv_data is None or ohlcv_data.empty:
                    ohlcv_data = data.tail(60).copy()
            except Exception as e:
                print(f"OHLCV 데이터 조회 실패: {e}")
                ohlcv_data = data.tail(60).copy()

            current_price = float(ohlcv_data['close'].iloc[-1])
            balance = self.upbit.get_balance("KRW")
            coin_balance = self.upbit.get_balance(self.ticker.split('-')[1])
            total_assets = balance + (coin_balance * current_price)
            current_BTC_ratio = (coin_balance * current_price / total_assets * 100) if total_assets > 0 else 0
            avg_buy_price = self.upbit.get_avg_buy_price(self.ticker)

            # OHLCV 데이터 포맷팅    
            ohlcv_formatted = "최근 240시간 OHLCV 데이터:\n"
            for index, row in ohlcv_data.iterrows():
                ohlcv_formatted += f"""
                시간: {index.strftime('%Y-%m-%d %H:%M')}
                시가: {row['open']:,.0f}
                고가: {row['high']:,.0f}
                저가: {row['low']:,.0f}
                종가: {row['close']:,.0f}
                거래량: {row['volume']:,.0f}
                -------------------"""
            
            # 이전 자문 내역 가져오기
            previous_advice = self.get_gpt_advice_history(limit=3, formatted=True)

            # Stoch RSI 신호 확인
            stoch_rsi_signal = ""
            if hasattr(self, 'last_stoch_cross_type') and self.last_stoch_cross_time:
                # 최근 30분 이내의 크로스 신호만 전달
                if time.time() - self.last_stoch_cross_time <= 1800:  # 30분
                    if self.last_stoch_cross_type == 'up':
                        stoch_rsi_signal = "최대 30분 이전에 골든크로스 발생했었음"
                    elif self.last_stoch_cross_type == 'down':
                        stoch_rsi_signal = "최대 30분 이전에 데드크로스 발생했었음"
            
            prompt = f"""BTC 시장 분석 보고서 ({force_check and '정기점검' or '시장변화'})
    당신은 BTC 시장 정보를 제공받고 그것을 바탕으로 당신의 견해를 제공하는 BTC 단타 트레이딩 전문가입니다.
    제공되는 각종 지표들을 해석하는 것도 중요하지만, 당신의 모든 지식을 총동원하여 OHLCV를 분석하십시오. 그리고 당신이 뉴스를 전달받았는지 확인해야하기 때문에 매 대답마다 뉴스에대한 분석도 조금이라도 적어주세요.
    단타 거래가 아닙니다 단기간의 오르 내림림이 아닌 큰흐름을 기준으로 거래하세요. 확실할 때 들어가고 확실한 익절을 하는 것이 목표입니다!

    {previous_advice}

    {ohlcv_formatted}
            
    지표 설명: 
    - KNN 지표
    KNN 지표의 신호강도는 '얼마나 크게 움직일 것인가'를, KNN 지표의 신뢰도는 '얼마나 확실한가'를 나타냅니다.

    신뢰도 범위 해석:
    40-60%: 낮은 신뢰도
    60-75%: 중간 신뢰도
    75-85%: 높은 신뢰도
    85-95%: 매우 높은 신뢰도

    - 볼린저 밴드 포지션 (6단계 구분):
    * extreme_upper: 상단 밴드 초과.
    * upper_strong: 상단과 중앙 밴드 사이 상위 1/3.
    * upper_weak: 상단과 중앙 밴드 사이 하위 2/3.
    * lower_weak: 중앙과 하단 밴드 사이 상위 2/3.
    * lower_strong: 중앙과 하단 밴드 사이 하위 1/3.
    * extreme_lower: 하단 밴드 미만.

    - 볼린저 밴드 추가 지표:
    * band_width: 밴드폭(%). 변동성 수준을 나타내며, 높을수록 시장의 변동성이 큼
        - 20% 이상: 매우 높은 변동성
        - 10-20%: 높은 변동성
        - 5-10%: 보통 변동성
        - 5% 미만: 낮은 변동성

    -Stoch RSI: k값도 물론 중요하지만 Stoch RSI의 특징인 k값과 d값을 모두 고려해주세요!
        
    현재 시장 상황:
    - 현재가: {round(current_price / 100) * 100:,.0f}원
    - EMA: {analysis_results['ema_ribbon_status']}
    - Stoch RSI: K:{analysis_results['stoch_rsi_k']:.1f}, D:{analysis_results['stoch_rsi_d']:.1f} 
          (K > 75: 과매수, K < 25: 과매도)
          {stoch_rsi_signal}  # 최근 30분 이내 발생한 신호만 표시
    - 모멘텀: {analysis_results['momentum']*100:.1f}%
    - 변동성: {analysis_results['volatility_ratio']:.1f}%
    - 볼린저밴드: {analysis_results['bollinger_position']}
    - 볼린저 밴드폭: {analysis_results.get('band_width', 0):.2f}%
    - 다이버전스: {analysis_results['divergence']['bearish_divergence'] and '베어리시' or ''} {analysis_results['divergence']['bullish_divergence'] and '불리시' or ''}

    자산 현황:
    - 보유KRW: {balance:.0f}원
    - 보유BTC: {coin_balance:.8f}개 
    - 평단가: {avg_buy_price > 0 and f"{avg_buy_price:.0f}원" or "없음"}
    - 수익률: {avg_buy_price > 0 and f"{((current_price - avg_buy_price) / avg_buy_price * 100):.2f}%" or "없음"}
    - BTC비중: {current_BTC_ratio:.2f}%

    KNN 분석:
    - 예측방향: {analysis_results['knn_prediction'] > 0 and '상승' or analysis_results['knn_prediction'] < 0 and '하락' or '중립'}
    - 신뢰도: {analysis_results['knn_signal_strength']:.1f}%
    - 신호강도: {abs(analysis_results['knn_prediction']) > 0.5 and '강' or abs(analysis_results['knn_prediction']) > 0.2 and '중' or '약'}

    뉴스 요약:
    {self.fetch_BTC_news()}

    아래 JSON 형식으로 매매 판단을 응답해주세요:
    {{
    "trade_recommendation": "매수 또는 매도 또는 관망",
    "investment_percentage": 0부터 100까지의 정수(관망 추천시 0),
    "confidence_score": 0부터 100까지의 정수(KNN 신뢰도가 아닌 당신의 답변에 대한 당신이 생각하는 신뢰도를 적어주세요!),
    "reasoning": "투자 판단의 근거"
    }}

    거래 제약:
    - 매수시: 총자산 대비 목표 보유 BTC%를 investment_percentage에 입력 (ex: 현재 총 자산의 25%를 BTC로 보유중인데 BTC를 추가 매수하여 총자산의 45%를 BTC로 보유할려는 경우 투자 비율에 45를 입력하세요)
    - 매도시: 보유 BTC 중 매도할 비율을 investment_percentage에 입력
    - 관망시: 0% 입력
    - 여유를 두고 확실한 거래를 해주세요.
    - 제발! OHCLV를 바탕으로 프랙탈 분석도 신경쓰세요.
    - KNN 지표는 매수할 때 최대한 낮은 가격에 매수하고 익절할 때 최대한 높은 가격에서 익절하기 위한 지표이지, 단타 거래를 위한 지표가 아닙니다."""

            client = openai.OpenAI(api_key=self.openai_api_key)
            response = client.chat.completions.create(
                model="o3-mini-2025-01-31",
                messages=[{
                    "role": "user",
                    "content": prompt
                }],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "trading_decision",
                        "description": "Trading decision with recommendation and reasoning",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "trade_recommendation": {
                                    "type": "string",
                                    "enum": ["매수", "매도", "관망"]
                                },
                                "investment_percentage": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 100
                                },
                                "confidence_score": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 100
                                },
                                "reasoning": {
                                    "type": "string"
                                }
                            },
                            "required": ["trade_recommendation", "investment_percentage", "confidence_score", "reasoning"]
                        }
                    }
                },
                reasoning_effort="high"
            )

            content = response.choices[0].message.content.strip()
            try:
                gpt_advice = json.loads(content)
                current_market_state = {
                    'price': current_price,
                    'rsi': float(analysis_results['rsi']),
                    'volatility': float(analysis_results['volatility_ratio']),
                    'ema_status': str(analysis_results['ema_ribbon_status']),
                    'momentum': float(analysis_results['momentum']),
                    'bollinger_position': str(analysis_results['bollinger_position']),
                    'bollinger_position_num': analysis_results.get('bollinger_position_num', 0),
                    'stoch_rsi_k': float(analysis_results['stoch_rsi_k']),
                    'stoch_rsi_d': float(analysis_results['stoch_rsi_d']),
                    'knn_prediction': float(analysis_results['knn_prediction']),
                    'knn_signal_strength': float(analysis_results['knn_signal_strength'])
                }
                self.log_gpt_advice(gpt_advice, current_market_state)
                self.last_gpt_market_state = current_market_state
                return gpt_advice

            except Exception as e:
                print(f"응답 처리 중 오류 발생: {e}")
                return {
                    'trade_recommendation': '관망',
                    'investment_percentage': 0,
                    'confidence_score': 50,
                    'reasoning': f'처리 오류: {str(e)}'
                }

        except Exception as e:
            print(f"GPT 자문 요청 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            return {
                'trade_recommendation': '관망',
                'investment_percentage': 0,
                'confidence_score': 50,
                'reasoning': f'시스템 오류: {str(e)}'
            }
            
    def log_gpt_advice(self, advice_data, market_state):
        """GPT 자문 결과를 데이터베이스에 저장하는 함수 개선"""
        try:
            # 입력 데이터 검증
            if not isinstance(advice_data, dict):
                print("잘못된 자문 데이터 형식")
                return False

            required_fields = ['trade_recommendation', 'investment_percentage', 
                            'confidence_score', 'reasoning']
            if not all(field in advice_data for field in required_fields):
                print(f"필수 필드 누락: {[f for f in required_fields if f not in advice_data]}")
                return False

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 현재 시간을 한국 시간대로 설정
            korean_time = datetime.now(self.timezone)
            timestamp = korean_time.strftime('%Y-%m-%d %H:%M:%S')

            # market_state가 None이 아닌 경우에만 JSON으로 변환
            market_state_json = None
            if market_state is not None:
                try:
                    market_state_json = json.dumps(market_state, ensure_ascii=False)
                except Exception as e:
                    print(f"market_state JSON 변환 중 오류: {e}")
                    market_state_json = None

            # 데이터 정수 변환 및 유효성 검사
            try:
                confidence_score = advice_data.get('confidence_score', 0)
                if isinstance(confidence_score, (int, float)):
                    confidence_score = int(round(confidence_score))  # 반올림 후 정수 변환
                else:
                    print(f"잘못된 confidence_score 형식: {confidence_score}")
                    confidence_score = 0

                investment_percentage = advice_data.get('investment_percentage', 0)
                if isinstance(investment_percentage, (int, float)):
                    investment_percentage = int(round(investment_percentage))  # 반올림 후 정수 변환
                else:
                    print(f"잘못된 investment_percentage 형식: {investment_percentage}")
                    investment_percentage = 0

                # 값 범위 제한
                confidence_score = max(0, min(100, confidence_score))
                investment_percentage = max(0, min(100, investment_percentage))

            except Exception as e:
                print(f"데이터 변환 중 오류: {e}")
                confidence_score = 0
                investment_percentage = 0

            # 데이터 삽입
            try:
                cursor.execute('''
                INSERT INTO gpt_advice_log 
                (timestamp, trade_recommendation, investment_percentage,
                confidence_score, reasoning, market_state)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    timestamp,
                    str(advice_data.get('trade_recommendation', '관망')),
                    investment_percentage,
                    confidence_score,
                    str(advice_data.get('reasoning', '없음')),
                    market_state_json
                ))
                
                conn.commit()
                print(f"GPT 자문 저장 완료 - {timestamp}")
                
                # 저장된 데이터 확인
                cursor.execute('''
                SELECT * FROM gpt_advice_log 
                WHERE timestamp = ? 
                ORDER BY id DESC LIMIT 1
                ''', (timestamp,))
                
                saved_data = cursor.fetchone()
                if saved_data:
                    print("\n저장된 GPT 자문 데이터:")
                    print(f"Timestamp: {saved_data[1]}")
                    print(f"추천: {saved_data[2]}")
                    print(f"투자 비율: {saved_data[3]}%")
                    print(f"신뢰도: {saved_data[4]}%")
                    print(f"근거: {saved_data[5]}")
                
                return True

            except sqlite3.Error as e:
                print(f"데이터베이스 저장 중 오류: {e}")
                return False

        except Exception as e:
            print(f"GPT 자문 로깅 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            if 'conn' in locals():
                conn.close()
            
    def run_trading_strategy(self):
        """수정된 트레이딩 전략 실행"""
        try:
            # 초기화
            gc_counter = 0
            last_forced_check_time = time.time()
            
            # 초기 뉴스 로드
            cached_news = self.load_cached_news()
            if cached_news:
                self.cached_news = cached_news
                print("\n마지막 저장된 뉴스 로드 완료")
            else:
                print("\n저장된 뉴스가 없습니다. 다음 정해진 시간에 업데이트될 예정입니다.")
            
            # 다음 뉴스 업데이트 시간 초기화
            current_time = datetime.now(self.timezone)
            next_news_update = self.get_next_news_update_time(current_time)
            print(f"\n트레이딩 봇 시작 - 다음 뉴스 업데이트 예정: {next_news_update.strftime('%Y-%m-%d %H:%M')}")

            while True:
                try:
                    current_time = datetime.now(self.timezone)
                    
                    # 1. 뉴스 업데이트 체크 (정해진 시간에만)
                    if current_time >= next_news_update:
                        fixed_hours = [0, 4, 8, 12, 16, 20]
                        if current_time.hour in fixed_hours:
                            print("\n=== 정해진 시간 뉴스 업데이트 시작 ===")
                            print(f"현재 시간: {current_time.strftime('%Y-%m-%d %H:%M')}")
                            
                            try:
                                updated_news = self.fetch_BTC_news()
                                if updated_news:
                                    self.cached_news = updated_news
                                    print("뉴스 업데이트 완료")
                                else:
                                    print("뉴스 업데이트 실패 - 기존 뉴스 유지")
                            except Exception as e:
                                print(f"뉴스 업데이트 실패: {e}")
                                import traceback
                                traceback.print_exc()
                        else:
                            print(f"\n현재 시간({current_time.hour}시)은 뉴스 업데이트 시간이 아님")
                        
                        # 다음 업데이트 시간 계산 (현재 시간 기준)
                        next_news_update = self.get_next_news_update_time(current_time)
                        print(f"다음 뉴스 업데이트 예정: {next_news_update.strftime('%Y-%m-%d %H:%M')}")

                    # 2. 시장 데이터 분석
                    with self.market_data_lock:
                        # 히스토리컬 데이터 가져오기
                        data = self.get_historical_data()
                        if data is None:
                            print("히스토리컬 데이터를 가져오는데 실패했습니다.")
                            time.sleep(60)
                            continue
                        
                        # 기술적 분석 수행
                        analysis_results = self.calculate_indicators(data)
                        if analysis_results is None:
                            print("기술적 분석 실패")
                            time.sleep(60)
                            continue

                        # 변동성에 따른 강제 점검 간격 동적 조정
                        volatility = analysis_results.get('volatility_ratio', 0)
                        if volatility < 2.35:
                            force_check_interval = 7200  # 2시간간
                        elif volatility < 3:
                            force_check_interval = 3600  # 1시간
                        else:
                            force_check_interval = 1800   # 30분

                        # 3. 시장 상황 모니터링
                        market_changed = self.monitor_market_conditions(data, analysis_results)
                        
                        # 강제 점검 시간 확인
                        current_ts = time.time()
                        time_since_last_check = current_ts - last_forced_check_time
                        time_to_force_check = time_since_last_check >= force_check_interval
                        
                        # GPT 자문이 필요한지 결정
                        should_consult_gpt = market_changed or time_to_force_check

                        # 4. 거래 신호 생성 및 실행
                        if should_consult_gpt:
                            if market_changed:
                                print("\n=== 시장 상황 변화 감지 - GPT 자문 요청 ===")
                            else:
                                print(f"\n=== 정기 점검 시작 (마지막 점검으로부터 {time_since_last_check/60:.1f}분 경과) ===")
                            
                            # 포트폴리오 상태 출력
                            portfolio = self.get_portfolio_status()
                            if portfolio:
                                print("\n현재 포트폴리오 상태:")
                                print(f"KRW 잔고: {portfolio['krw_balance']:,.0f}원")
                                print(f"BTC 잔고: {portfolio['coin_balance']:.8f}")
                                print(f"총 자산가치: {portfolio['total_value']:,.0f}원")
                                if portfolio['avg_buy_price'] > 0:
                                    print(f"평균 매수가: {portfolio['avg_buy_price']:,.0f}원")
                                    print(f"현재 수익률: {portfolio['roi']:.2f}%")
                                print(f"BTC 비중: {portfolio['coin_ratio']:.2f}%")
                            
                            # GPT 자문 요청 및 거래 신호 생성
                            signals = self.generate_trading_signal(
                                data=data,
                                market_changed=market_changed,
                                force_check=time_to_force_check
                            )
                            
                            if signals is None:
                                print("거래 신호 생성에 실패했습니다.")
                                time.sleep(60)
                                continue
                                
                            buy_signal, sell_signal, gpt_advice, _ = signals
                            
                            # 거래 실행 시도
                            if analysis_results is not None:
                                trade_executed = self.execute_trade(
                                    buy_signal, 
                                    sell_signal, 
                                    gpt_advice, 
                                    analysis_results
                                )
                                
                                if trade_executed:
                                    print("\n거래 실행 완료 - 포트폴리오 재확인")
                                    updated_portfolio = self.get_portfolio_status()
                                    if updated_portfolio:
                                        print(f"업데이트된 KRW 잔고: {updated_portfolio['krw_balance']:,.0f}원")
                                        print(f"업데이트된 BTC 잔고: {updated_portfolio['coin_balance']:.8f}")
                            
                            last_forced_check_time = current_ts  # 강제 점검 타이머 리셋
                        else:
                            minutes_to_next_check = (force_check_interval - time_since_last_check) / 60
                            print(f"\n다음 강제 점검까지 {minutes_to_next_check:.1f}분 남음")
                            print("시장 변화 없음 - 관망 상태 유지")
                    
                    # 5. 가비지 컬렉션 및 메모리 관리
                    gc_counter += 1
                    if gc_counter >= 10:
                        gc.collect()
                        gc_counter = 0
                        
                    # 6. 대기
                    time.sleep(60)  # 1분 간격으로 체크
                    
                except Exception as e:
                    print(f"Trading loop 실행 중 오류: {e}")
                    import traceback
                    traceback.print_exc()
                    time.sleep(60)

        except KeyboardInterrupt:
            print("\n트레이딩 봇 종료 요청 감지")
            print("진행 중인 작업 정리 중...")
            # 정리 작업 수행
            if hasattr(self, 'db_connection') and self.db_connection:
                self.db_connection.close()
            print("트레이딩 봇이 안전하게 종료되었습니다.")
            
        except Exception as e:
            print(f"치명적인 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            raise  # 심각한 오류는 상위로 전파하여 봇 재시작 유도

if __name__ == "__main__":
    bot = BTCTradingBot()
    bot.run_trading_strategy()
