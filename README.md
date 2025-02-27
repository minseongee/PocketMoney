# 🚀 BitBot: Advanced Bitcoin Trading Bot

## 📖 Overview

BitBot is a sophisticated, AI-enhanced cryptocurrency trading bot specifically designed for Bitcoin markets on the Upbit exchange. Leveraging a combination of technical analysis, machine learning, and natural language processing, BitBot aims to make data-driven trading decisions while adapting to changing market conditions.

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

BitBot employs a hybrid trading approach combining multiple strategies:

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

### Installation Steps

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/BitBot.git
   cd BitBot
   ```

2. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your API keys:
   ```
   UPBIT_ACCESS_KEY=your_upbit_access_key
   UPBIT_SECRET_KEY=your_upbit_secret_key
   OPENAI_API_KEY=your_openai_api_key
   SERPAPI_KEY_1=your_serpapi_key_1
   SERPAPI_KEY_2=your_serpapi_key_2
   ```

4. Initialize the database:
   ```bash
   python init_database.py
   ```

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
- KNN prediction direction change monitoring
- Volatility-based analysis frequency adjustment

## ⚠️ Risk Warning

Cryptocurrency trading involves significant risk and BitBot is provided for educational and research purposes only. Use at your own risk. Key considerations:

- **Past Performance**: Historical performance is not indicative of future results
- **Market Volatility**: Cryptocurrency markets are highly volatile
- **Technical Limitations**: Software bugs or API issues may affect performance
- **API Rate Limits**: Exchange and service API limits may impact operation
- **Testing Recommended**: Start with small amounts or in a test environment

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👥 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 🙏 Acknowledgements

- Upbit for their cryptocurrency exchange API
- OpenAI for their powerful GPT models
- SerpAPI for news data access
- All contributors and the cryptocurrency community

---

⭐ If you find this project useful, please consider giving it a star on GitHub! ⭐

*Disclaimer: This software is for educational purposes only. Use at your own risk.*
