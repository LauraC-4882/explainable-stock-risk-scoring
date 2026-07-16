export default {
  header: {
    title: 'Stock Risk Analyzer',
    subtitle: 'Real-time downside risk · direction signals · live data via yfinance',
  },
  market: {
    us: 'US',
    cn: 'China',
  },
  search: {
    placeholder: {
      us: 'Search US stocks — Apple, TSLA, NVDA…',
      cn: 'Search China stocks — Moutai, Tencent, 600519, 0700…',
    },
  },
  timeframe: {
    '5d': '5D',
    '1mo': '1M',
    '3mo': '3M',
    '6mo': '6M',
    '1y': '1Y',
    '2y': '2Y',
  },
  emptyState: {
    heading: 'Search any stock to see its risk',
    body: 'Type a company name or ticker above. Scores update live using real market data.',
  },
  card: {
    remove: 'Remove',
    riskScoreLabel: 'risk score out of 100',
    fetching: 'Fetching…',
  },
  riskLabel: {
    LOW: 'LOW',
    MODERATE: 'MODERATE',
    HIGH: 'HIGH',
    EXTREME: 'EXTREME',
  },
  labelExplanation: {
    LOW: 'Calmer than usual for this stock — lower volatility and shallower drawdowns than its own recent history.',
    MODERATE: 'Within a fairly normal range for this stock — nothing unusual compared to its own recent history.',
    HIGH: 'More turbulent than usual for this stock — bigger price swings or deeper drawdowns than typical.',
    EXTREME: 'Near the most turbulent levels seen in this stock’s recent history.',
  },
  explainer: {
    toggle: 'What does this score mean?',
    intro:
      'This 0–100 score compares the stock’s current behavior to its own trading history over roughly the last two years — it is not compared against other stocks, and it is not a prediction of future price movement or investment advice. A high score just means this stock is acting more turbulently than it usually does.',
    makeup: 'What makes up the score',
    weight: 'weight',
  },
  categories: {
    volatility: {
      label: 'Volatility',
      plain: 'How much the price swings day to day. Higher means choppier, less predictable price moves.',
    },
    tail: {
      label: 'Tail Risk',
      plain: 'How bad the worst-case days have historically been for this stock — the "what if things go really wrong" risk.',
    },
    drawdown: {
      label: 'Drawdown',
      plain: 'How far the stock has fallen from its recent peak, and how long it has stayed down before recovering.',
    },
    sensitivity: {
      label: 'Market Sensitivity',
      plain: 'How much this stock tends to move when the overall market moves. Higher means it amplifies market-wide swings.',
    },
    liquidity: {
      label: 'Liquidity',
      plain: 'How easily shares can be bought or sold without noticeably moving the price. Lower liquidity can mean bigger price jumps on trades.',
    },
  },
  direction: {
    heading: 'Today’s Direction Signal',
    upside: 'Upside',
    downside: 'Downside',
    bull: '↑ Likely to INCREASE',
    bear: '↓ Likely to DECREASE',
    flat: '→ Neutral — unclear direction',
  },
  metrics: {
    vol30d: '30d Vol',
    var95: 'VaR 95%',
    beta: 'Beta',
    rsi: 'RSI 14',
  },
  glossary: {
    volatility:
      'How much a stock’s price swings up and down over a period. Higher volatility means bigger, choppier, less predictable moves — not necessarily a bad sign, just a wilder ride.',
    var95:
      'Value at Risk (95%): on a typical "bad day" (roughly the worst 1-in-20 trading days), this is about how much the stock could drop. It’s a rough guide, not a guaranteed floor.',
    beta: 'How much this stock tends to move compared to its market benchmark. Beta = 1.0 means it moves with the benchmark; above 1.0 means bigger swings; below 1.0 means calmer than the benchmark.',
    rsi: 'Relative Strength Index: a 0–100 gauge of recent buying/selling momentum. Above 70 is often called "overbought," below 30 "oversold" — these are just labels for recent momentum, not predictions of what happens next.',
  },
  charts: {
    price: 'Price History',
    riskScore: 'Daily Risk Score (0–100)',
  },
}
