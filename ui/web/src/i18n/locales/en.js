export default {
  header: {
    title: 'Riscore',
    subtitle: 'Invest smarter, risk safer — real-time explainable risk scoring on live market data',
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
    slogan: 'Invest smarter · Risk safer',
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
  keyFactors: {
    title: 'Key Factor Contributions',
    impact: {
      high: 'High',
      elevated: 'Elevated',
      moderate: 'Moderate',
      low: 'Low',
    },
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
      short: 'Vol',
      plain: 'How much the price swings day to day. Higher means choppier, less predictable price moves.',
    },
    tail: {
      label: 'Tail Risk',
      short: 'Tail Risk',
      plain: 'How bad the worst-case days have historically been for this stock — the "what if things go really wrong" risk.',
    },
    drawdown: {
      label: 'Drawdown',
      short: 'Drawdown',
      plain: 'How far the stock has fallen from its recent peak, and how long it has stayed down before recovering.',
    },
    sensitivity: {
      label: 'Market Sensitivity',
      short: 'Sensitivity',
      plain: 'How much this stock tends to move when the overall market moves. Higher means it amplifies market-wide swings.',
    },
    liquidity: {
      label: 'Liquidity',
      short: 'Liquidity',
      plain: 'How easily shares can be bought or sold without noticeably moving the price. Lower liquidity can mean bigger price jumps on trades.',
    },
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
  stressTest: {
    toggle: 'Historical stress test',
    intro:
      'How this stock’s risk score would move if conditions like these past crises recurred, based only on this stock’s own volatility/tail/drawdown/sensitivity/liquidity profile — not a forecast that any of these events will happen again.',
    baseline: 'baseline',
  },
  mlSignal: {
    toggle: 'ML downside-risk signal (secondary)',
    intro:
      'A machine-learning estimate of the probability of a 10%+ drawdown in the next 20 trading days. Since validation (mean ROC-AUC 0.67, 56 stocks x 5 years) it contributes 15% of the headline risk score — the percentile composite carries the rest. Recall is low, so it misses more real drawdowns than it flags (see the README for the full writeup).',
    probability: 'Estimated 20-day drawdown probability:',
    topFeatures: 'Top contributing factors',
  },
  auth: {
    signIn: 'Sign in',
    signUp: 'Create account',
    signUpShort: 'Sign up',
    signOut: 'Sign out',
    email: 'Email',
    password: 'Password',
    passwordHint: 'At least 8 characters',
    submit: 'Continue',
    submitting: 'Please wait…',
    switchToSignUp: "Don't have an account? Sign up",
    switchToSignIn: 'Already have an account? Sign in',
  },
  watchlist: {
    button: 'Watchlist',
    title: 'My Watchlist',
    empty: 'No saved stocks yet — tap the star on any card to save it here.',
    add: 'Add to dashboard',
    remove: 'Remove',
    favorite: 'Save to watchlist',
    unfavorite: 'Remove from watchlist',
  },
  profile: {
    title: 'Profile',
    memberSince: 'Member since',
    watchlistCount: 'Stocks on watchlist',
    myPosts: 'Analysis posts',
    myVotes: 'Posts voted on',
    viewAll: 'View all',
    replayTour: 'Replay tutorial',
  },
  community: {
    navButton: 'Community',
    title: 'Community Risk Analysis',
    disclaimer:
      'The risk score is computed from objective market data. Everything in this community section is other users’ personal opinion, including accuracy rates derived from votes — use your own judgment, don’t treat it as advice.',
    tab: {
      feed: 'Feed',
      leaderboard: 'Leaderboard',
    },
    sort: {
      recent: 'Recent',
      top: 'Top',
      accuracy: 'Accuracy',
    },
    feedEmpty: 'No analysis posted yet — be the first to share your take.',
    leaderboardEmpty: 'No ranked analysts yet — accuracy needs a minimum number of votes to appear here.',
    posts: 'posts',
    accuracy: 'accuracy',
    accuracyPending: 'new analyst',
    voteUp: 'This analysis was right',
    voteDown: 'This analysis was wrong',
    deletePost: 'Delete this post',
    ownPost: 'Your post',
    tickerPlaceholder: 'TICKER',
    bodyPlaceholder: 'Share your read on this stock’s risk…',
    posting: 'Posting…',
    post: 'Post',
    signInToPost: 'Sign in to share your own analysis.',
    topAnalysis: 'Top community take',
    beFirst: 'No analysis yet for this stock — be the first to share your take.',
  },
  onboarding: {
    title: 'Quick tour',
    skip: 'Skip',
    back: 'Back',
    next: 'Next',
    done: 'Start exploring',
    replayTitle: 'Replay the quick tour',
    steps: {
      welcome: {
        title: 'Welcome to Riscore',
        body: 'Riscore turns a stock’s recent price and volatility behavior into one explainable 0–100 risk score, plus the individual signals behind it — so you can quickly judge how turbulent a stock is acting right now. This short tour explains what each piece of information is actually useful for when deciding what to do next.',
      },
      score: {
        title: 'The Risk Score (0–100)',
        body: 'Your at-a-glance read: LOW / MODERATE / HIGH / EXTREME compares the stock to its own recent history, not to other stocks. Use it to triage which of your positions deserve a closer look today — a jump into HIGH or EXTREME is a cue to check position size or hedges, not a buy/sell signal by itself.',
      },
      breakdown: {
        title: 'What’s driving the score',
        body: 'Open "What does this score mean?" to see the five ingredients — Volatility, Tail Risk, Drawdown, Market Sensitivity, Liquidity — and their weights. Knowing which category is elevated tells you what kind of risk you’re actually holding: high Liquidity risk and high Tail risk call for very different responses.',
      },
      mlSignal: {
        title: 'ML downside-risk signal',
        body: 'A secondary machine-learning estimate of the probability of a 10%+ drop in the next 20 trading days, with the specific factors (SHAP) that drove it. It’s a deliberately small (15%) input to the score — treat it as one more corroborating data point, not a standalone forecast; its recall is intentionally documented as low.',
      },
      stressTest: {
        title: 'Historical stress test',
        body: 'Shows how this stock’s score would move if a past crisis (2008 / 2020 / 2022) repeated, based only on its own volatility/tail/drawdown profile. Use it for worst-case scenario planning — it’s not a prediction that any of these events will happen again.',
      },
      metrics: {
        title: 'Quant metrics at a glance',
        body: '30-day volatility, VaR 95%, Beta, and RSI — the numbers analysts check first. VaR 95% estimates a plausible bad-day loss; Beta tells you how much the stock amplifies market-wide moves; RSI flags short-term overbought/oversold momentum.',
      },
      watchlist: {
        title: 'Save stocks to your watchlist',
        body: 'Sign in and tap the star on any card to track it here across visits — useful for monitoring how a position’s risk profile evolves over time instead of starting fresh every time you check it.',
      },
    },
  },
}
