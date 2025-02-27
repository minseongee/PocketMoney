# 🚀 Mytheong's PocketMoney Bot ( 용돈 벌이 깡통 )

## 📖 Overview

PocketMoney Bot is a sophisticated, AI-enhanced cryptocurrency trading bot specifically designed for Bitcoin markets on the Upbit exchange. Leveraging a combination of technical analysis, machine learning, and natural language processing, BitBot aims to make data-driven trading decisions while adapting to changing market conditions.

### 🌟 Key Features

- **Technical Analysis Engine**: Comprehensive implementation of key technical indicators including RSI, EMA Ribbon, Bollinger Bands, Stochastic RSI, and more
- **Machine Learning Integration**: Custom KNN (K-Nearest Neighbors) algorithm for price movement prediction with adaptive parameters
- **AI-Powered Decision Making**: GPT model integration for market analysis and trading recommendations
- **Real-time News Analysis**: Automatic fetching and analysis of Bitcoin news to incorporate market sentiment
- **Dynamic Risk Management**: Adaptive position sizing based on market volatility and confidence levels
- **Robust Database Logging**: Detailed transaction and analysis history for performance evaluation
- **Market Change Detection**: Smart monitoring of significant market condition changes to trigger analysis

## 🔧 Technology Stack

- **Python 3.8+**: Core programming language
- **PyUpbit**: API for Upbit exchange interactions
- **OpenAI API**: For GPT model integration (market analysis)
- **SerpAPI**: For news data collection
- **SQLite**: Local database for logging and caching
- **Pandas & NumPy**: Data processing and numerical computations
- **Technical Analysis Libraries**: Custom implementations for market indicators

## 📊 Trading Strategies

PocketMoney Bot employs a hybrid trading approach combining multiple strategies:

1. **Technical Analysis-Based Trading**:
   - RSI overbought/oversold conditions
   - EMA ribbon trend identification
   - Bollinger Band breakouts and mean reversion
   - Stochastic RSI crossovers

2. **Momentum Trading**:
   - Price momentum calculation and thresholds
   - Volatility-adjusted position sizing

3. **Pattern Recognition**:
   - Divergence detection between price and indicators
   - Support and resistance identification

4. **AI-Enhanced Decision Making**:
   - GPT analysis of market conditions
   - Integration of news sentiment with technical signals
   - Confidence scoring for trade execution

5. **Counter-Trend Strategies**:
   - Identifying potential reversal points
   - Risk-adjusted contrarian entries

## 🛠️ Installation & Setup

### Prerequisites

- Python 3.8 or higher
- Upbit API keys with trading permissions
- OpenAI API key
- SerpAPI key(s)

## 🚀 Usage

To start the trading bot:

```bash
python trading_bot.py
```

### Configuration Options

The bot's behavior can be customized by modifying these parameters in the `__init__` method:

- `OVERSOLD_RSI`: RSI threshold for oversold conditions (default: 25)
- `OVERBOUGHT_RSI`: RSI threshold for overbought conditions (default: 75)
- `BOLLINGER_PERIOD`: Period for Bollinger Bands calculation (default: 20)
- `BOLLINGER_STD`: Standard deviation multiplier for Bollinger Bands (default: 2.2)
- `MOMENTUM_THRESHOLD`: Threshold for momentum signals (default: 0.025)
- `VOLATILITY_THRESHOLD`: Volatility threshold for trading decisions (default: 2)
- `CONFIDENCE_THRESHOLD`: Minimum confidence score to execute trades (default: 60)
- `MIN_TRADE_INTERVAL`: Minimum time between trades (default: 180 seconds)
- `COOLDOWN_HOURS`: Cooldown period after a trade (default: 2 hours)

## 📈 Performance Monitoring

BitBot maintains detailed logs of all its operations in an SQLite database, allowing for comprehensive performance analysis:

- **Trade Log**: Records of all executed trades with prices, amounts, and reasoning
- **GPT Advice Log**: History of AI trading recommendations
- **News Fetch Log**: Archive of retrieved news data
- **API Usage Tracking**: Monitoring of API call limits

To analyze performance:

```bash
python analyze_performance.py --days 30
```

## 🔍 Key Components

### Technical Analysis Module

The technical analysis engine implements advanced versions of popular indicators:

- RSI with TradingView-compatible calculations
- EMA Ribbon for trend detection with five different periods
- Bollinger Bands with six-level position classification
- Stochastic RSI with customizable smoothing
- Custom momentum indicators

### KNN Prediction Engine

The machine learning component uses a modified K-Nearest Neighbors algorithm:

- Feature engineering tailored for cryptocurrency markets
- Adaptive K-value based on market conditions
- Distance-weighted prediction with time decay
- Confidence scoring system for signal quality assessment

### News Analysis Integration

The news module provides real-time market sentiment data:

- Scheduled fetching from major cryptocurrency news sources
- Keyword-based filtering for relevant information
- API usage optimization with multiple key rotation
- Cache management for efficient operation

### Market Change Detection

The market monitoring system detects significant changes in conditions:

- Multi-factor change detection across different indicators
- Stochastic RSI crossover detection with validation
- KNN prediction direction chang드

트레이딩 봇 시작:

```bash
python trading_bot.py
```

### 설정 옵션

봇의 동작은 `__init__` 메서드에서 다음 매개변수를 수정하여 사용자 정의 가능:

- `OVERSOLD_RSI`: 과매도 조건을 위한 RSI 임계값(기본값: 25)
- `OVERBOUGHT_RSI`: 과매수 조건을 위한 RSI 임계값(기본값: 75)
- `BOLLINGER_PERIOD`: 볼린저 밴드 계산을 위한 기간(기본값: 20)
- `BOLLINGER_STD`: 볼린저 밴드를 위한 표준 편차 승수(기본값: 2.2)
- `MOMENTUM_THRESHOLD`: 모멘텀 신호를 위한 임계값(기본값: 0.025)
- `VOLATILITY_THRESHOLD`: 트레이딩 결정을 위한 변동성 임계값(기본값: 2)
- `CONFIDENCE_THRESHOLD`: 거래 실행을 위한 최소 신뢰도 점수(기본값: 60)
- `MIN_TRADE_INTERVAL`: 거래 간 최소 시간(기본값: 180초)
- `COOLDOWN_HOURS`: 거래 후 대기 시간(기본값: 2시간)

## 📈 성능 모니터링

용돈 벌이 깡통은 모든 작업에 대한 자세한 로그를 SQLite 데이터베이스에 유지하여 포괄적인 성능 분석 가능:

- **거래 로그**: 가격, 수량, 근거가 포함된 모든 실행 거래 기록
- **GPT 자문 로그**: AI 트레이딩 권장 사항 기록
- **뉴스 수집 로그**: 검색된 뉴스 데이터 보관
- **API 사용량 추적**: API 호출 제한 모니터링

성능 분석:

```bash
python analyze_performance.py --days 30
```

## 🔍 주요 구성 요소

### 기술적 분석 모듈

기술적 분석 엔진은 인기 있는 지표의 고급 버전을 구현:

- TradingView 호환 계산이 포함된 RSI
- 다섯 가지 다른 기간의 추세 감지를 위한 EMA 리본
- 6단계 위치 분류가 있는 볼린저 밴드
- 사용자 정의 가능한 스무딩이 있는 스토캐스틱 RSI
- 맞춤형 모멘텀 지표

### KNN 예측 엔진

기계 학습 구성 요소는 수정된 K-최근접 이웃 알고리즘을 사용:

- 암호화폐 시장에 맞춘 특징 공학
- 시장 상황에 기반한 적응형 K값
- 시간 감쇠가 있는 거리 가중 예측
- 신호 품질 평가를 위한 신뢰도 점수 시스템

### 뉴스 분석 통합

뉴스 모듈은 실시간 시장 감성 데이터 제공:

- 주요 암호화폐 뉴스 소스에서 예약된 수집
- 관련 정보를 위한 키워드 기반 필터링
- 여러 키 회전으로 API 사용량 최적화
- 효율적인 작동을 위한 캐시 관리

### 시장 변화 감지

시장 모니터링 시스템은 중요한 조건 변화를 감지:

- 다양한 지표에 걸친 다중 요인 변화 감지
- 검증이 있는 스토캐스틱 RSI 크로스오버 감지
- KNN 예측 방향 변화 모니터링
- 변동성 기반 분석 빈도 조정
---

*면책 조항: 이 소프트웨어는 교육 목적으로만 제공. 자신의 책임 하에 사용.*
