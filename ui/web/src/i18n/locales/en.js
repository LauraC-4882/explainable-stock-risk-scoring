export default {
  header: {
    title: 'Riscore',
    subtitle: 'Invest smarter, risk safer — real-time explainable risk scoring on live market data',
    homeTitle: 'Back to homepage',
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
    trustTitle: 'Why trust this score',
    trust: {
      data: { title: 'Real market data', body: 'Live US / CN / HK prices with daily snapshot fallback.' },
      explain: { title: 'Explainable by construction', body: 'Five visible lenses; every number carries a plain-language reading.' },
      validated: { title: 'Walk-forward validated ML', body: '56 stocks × 5 years; accuracy published, weight capped at 15%.' },
      honest: { title: 'Honest about limits', body: 'Weaknesses documented. Descriptive statistics — never advice.' },
    },
    learnMore: 'How Riscore works →',
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
    LOW: 'Quieter than this stock’s own normal — smaller day-to-day moves, and it hasn’t fallen as far as it usually does.',
    MODERATE: 'About normal for this stock. Nothing unusual compared with how it usually behaves.',
    HIGH: 'Bumpier than this stock’s own normal — either it’s swinging more each day, or it has fallen further than it typically does.',
    EXTREME: 'About as wild as this stock gets — it’s moving near the most extreme levels seen in its own recent history.',
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
      'We compare this stock only with its own past two years — never with other stocks. 0 means “about as calm as this stock ever gets”, 100 means “about as wild as it ever gets”. A high score doesn’t mean it’s a bad stock, and it doesn’t mean it’s about to fall — it means it’s moving around more than this particular stock usually does.',
    makeup: 'What makes up the score',
    weight: 'weight',
  },
  // Each category carries `plainShort` — the everyday question it answers, in
  // a handful of words. It renders directly on the tile so the meaning is
  // visible without hovering: users told us the finance terms alone
  // ("drawdown", "tail risk") meant nothing to them.
  categories: {
    volatility: {
      label: 'Volatility',
      short: 'Vol',
      plainShort: 'How bumpy the ride is',
      plain: 'Realised volatility. A percentile blend of 21-day (40%) and 63-day (35%) annualised return standard deviation, plus 63-day downside deviation (25%), which counts only downward moves. Each input is ranked against this stock’s own ~2-year history.',
    },
    tail: {
      label: 'Tail Risk',
      short: 'Tail Risk',
      plainShort: 'How ugly the rare bad days get',
      plain: 'Left-tail severity. Blends 21-day 95% Conditional VaR (expected shortfall, 35%) and 95% Value at Risk (25%) with 63-day return skewness (20%) and kurtosis (20%) — the shape of the return distribution, not just its width.',
    },
    drawdown: {
      label: 'Drawdown',
      short: 'Drawdown',
      plainShort: 'How far it can fall at worst',
      plain: 'Peak-to-trough decline. Blends 63-day maximum drawdown (45%), the current drawdown from the running peak (35%), and drawdown duration — sessions spent below that peak (20%).',
    },
    sensitivity: {
      label: 'Market Sensitivity',
      short: 'Sensitivity',
      plainShort: 'Does it follow the whole market?',
      plain: 'Beta against the market benchmark (SPY, CSI 300 or HSI, by listing), estimated over a rolling 63-day window as the covariance of returns divided by the benchmark’s variance. 1.0 = moves one-for-one with the benchmark.',
    },
    liquidity: {
      label: 'Liquidity',
      short: 'Liquidity',
      plainShort: 'How easy it is to sell',
      plain: 'Trading frictions. Blends the 21-day Amihud illiquidity ratio — absolute return per unit of dollar volume (50%) — with volume volatility (30%) and the dollar-volume level (20%).',
    },
  },
  radar: {
    title: 'Risk profile radar',
    hint: 'The five score ingredients, each vs. this stock’s own 2-year history — shape, not verdict.',
  },
  metrics: {
    vol30d: '30d Vol',
    var95: 'VaR 95%',
    beta: 'Beta',
    rsi: 'RSI 14',
  },
  // Hover/expand layer: the professional definition, naming the actual
  // inputs and windows. The plain-language version lives in
  // `categories.*.plainShort`, which renders on the tile itself.
  glossary: {
    volatility:
      'Annualised realised volatility: the standard deviation of daily returns over the trailing window, scaled by √252. Direction-agnostic — it measures dispersion, not drift, so a stock trending steadily upward can still read high.',
    var95:
      'Value at Risk (95%), 21-day window: the loss threshold that the worst 5% of daily returns exceed, taken as an empirical quantile rather than assuming a normal distribution. It bounds the typical bad day, not the worst case — Conditional VaR (under Tail Risk) measures what lies beyond it.',
    beta:
      'Beta over a rolling 63-day window: the covariance of this stock’s returns with its benchmark, divided by the benchmark’s variance. 1.0 = one-for-one with the benchmark; below 1 damped, above 1 amplified. It captures co-movement, not causation.',
    rsi:
      'Relative Strength Index (14) — Wilder’s momentum oscillator: 100 − 100/(1 + average gain ÷ average loss) over 14 sessions. Above 70 is conventionally “overbought”, below 30 “oversold”. A description of momentum, not a forecast.',
  },
  readings: {
    title: 'What this number actually means',
    disclaimer: 'This describes what already happened — it is not a prediction, and not advice.',
    chip: {
      low: 'LOW',
      normal: 'NORMAL',
      mild: 'MILD',
      moderate: 'MODERATE',
      elevated: 'ELEVATED',
      high: 'HIGH',
      severe: 'SEVERE',
      negative: 'INVERSE',
      defensive: 'DEFENSIVE',
      inline: 'IN LINE',
      amplified: 'AMPLIFIED',
      oversold: 'OVERSOLD',
      weak: 'SOFT',
      neutral: 'NEUTRAL',
      firm: 'FIRM',
      overbought: 'OVERBOUGHT',
    },
    vol: {
      low: 'The price has been moving in small steps lately — a fairly smooth ride.',
      normal: 'Day-to-day moves are about what you’d expect from an ordinary stock.',
      elevated: 'It’s been jumping around more than most stocks — bigger moves in both directions.',
      high: 'Very bumpy lately. Daily moves have been much bigger than a typical stock’s.',
    },
    var95: {
      mild: 'On a bad day it has typically lost about this much — small, as these things go.',
      moderate: 'On a bad day it has typically lost about this much — a middling amount.',
      elevated: 'On a bad day it has typically lost about this much — enough to sting.',
      severe: 'On a bad day it has typically lost about this much — a heavy one-day hit.',
    },
    beta: {
      negative: 'It’s been going the opposite way to the market — up on days the market fell, and vice versa.',
      defensive: 'It moves less than the market, so market-wide drops land more gently here.',
      inline: 'It moves roughly in step with the market.',
      amplified: 'It exaggerates the market — when the market moves 1%, this tends to move more.',
      high: 'It exaggerates the market strongly, so market-wide swings hit this much harder.',
    },
    rsi: {
      oversold: 'A lot of selling recently. Below 30 is what people call “oversold” — it describes what just happened, not what comes next.',
      weak: 'Sellers have had the upper hand lately, but nothing extreme.',
      neutral: 'Buyers and sellers have been fairly evenly matched.',
      firm: 'Buyers have had the upper hand lately, but nothing extreme.',
      overbought: 'A lot of buying recently. Above 70 is what people call “overbought” — it describes what just happened, not what comes next.',
    },
    factor: {
      low: 'Quieter than this stock’s own normal.',
      moderate: 'About normal for this stock.',
      elevated: 'Higher than this stock’s own normal — one of the main things pushing the score up.',
      high: 'Near the highest this stock has ever been — a main reason the score sits where it does.',
    },
  },
  // Signed-in watchlist board (WatchlistBoard.jsx). "Up = warning" wording is
  // market-independent on purpose — see the component's colour-semantics note.
  board: {
    title: 'Your watchlist',
    subtitle: 'Risk movement since the previous reading',
    asOf: 'as of',
    firstReading: 'first reading',
    noReading: 'no reading yet',
    note: 'A rising score means risk increased, a falling score means it eased — shown the same way for every market, because a risk score is not a price. Readings come from stored daily snapshots, not a live quote.',
  },
  // Risk-movement bell (AlertsBell.jsx).
  alerts: {
    title: 'Risk movement',
    subtitle: 'Notable changes on your watchlist',
    empty: 'No notable movement since you last checked.',
    note: 'Triggered by a large change or a band crossing. Descriptive of stored readings — not a forecast or a recommendation.',
  },
  // Side-by-side comparison table (CompareView.jsx).
  compare: {
    viewCards: 'Cards',
    viewCompare: 'Compare',
    measure: 'Measure',
    riskScore: 'Risk score',
    unavailable: 'unavailable',
    note: 'Each score is relative to that stock’s own history, so a higher number means "more turbulent than usual for itself" — not "riskier than the stock next to it". Descriptive statistics, not a recommendation.',
  },
  charts: {
    price: 'Price History',
    riskScore: 'Daily Risk Score (0–100)',
  },
  stressTest: {
    toggle: 'Historical stress test',
    intro:
      'A “what if” exercise: if a crash like one of these happened again, where would this stock’s score likely end up? We take how this particular stock behaves today and replay those past conditions against it. Nobody is predicting these events will repeat — it’s a way to see how much room there is to get worse.',
    baseline: 'baseline',
  },
  regimeSignals: {
    toggle: 'Market regime & technical structure',
    intro:
      'Context, not scoring. These read the market backdrop and the stock’s own price structure: is volatility running hotter than the market priced, does it behave like a cyclical or a defensive name, has it run up hard while getting choppy, and what has its candle chart printed lately. None of it moves the risk score above — it has not been backtested against future losses yet, so it is shown as information rather than folded into the number.',
    regime: {
      label: 'Volatility regime',
      risk_on: 'Risk-on',
      risk_off: 'Risk-off',
      realized: 'Realized vol',
      implied: 'Implied (1M ago)',
      persistence: 'Risk-on days (21d)',
    },
    momentum: {
      label: 'Momentum & crash risk',
      crashRisk: 'Crash risk',
      vs52wHigh: 'vs 52w high',
      band: { low: 'Low', moderate: 'Moderate', elevated: 'Elevated' },
    },
    squeeze: {
      label: 'Volatility compression',
      compressed: 'Compressed',
      normal: 'Normal',
      expanded: 'Expanded',
      bandWidth: 'Band width',
      atr: 'ATR vs 60d',
      note: 'Where this stock’s trading range sits against its own past year. A narrow range tends to be followed by wider ones — that says the next moves are likely to be bigger, not when they come or which way they go.',
    },
    extremes: {
      label: 'Momentum extremes',
      oversold: 'Stretched low',
      overbought: 'Stretched high',
      neutral: 'No extreme',
    },
    stack: {
      label: 'Moving-average stack',
      bullish_stack: 'Fast above slow',
      bearish_stack: 'Fast below slow',
      mixed: 'Tangled',
      alignment: 'Alignment',
    },
    participation: {
      label: 'Volume participation',
      confirmed: 'Volume agrees',
      price_up_volume_weak: 'Price up, volume not confirming',
      price_down_volume_firm: 'Price down, volume not confirming',
      obv: 'OBV vs 20d',
    },
    tilt: {
      label: 'Sector tilt',
      cyclical: 'Cyclical',
      defensive: 'Defensive',
      balanced: 'Balanced',
      betaOn: 'β cyclical',
      betaOff: 'β defensive',
    },
    trend: {
      label: 'Trend',
      above: 'Above trend',
      below: 'Below trend',
      window: 'Optimized SMA',
      distance: 'Distance',
    },
    patterns: {
      label: 'Candlestick patterns',
      none: 'No reversal patterns in the last {days} sessions.',
      hammer: 'Hammer',
      shooting_star: 'Shooting star',
      bullish_engulfing: 'Bullish engulfing',
      bearish_engulfing: 'Bearish engulfing',
      doji: 'Doji',
    },
  },
  mlSignal: {
    toggle: 'ML downside-risk signal (secondary)',
    intro:
      'A computer model’s rough guess at the odds of a 10%-or-worse fall within the next month of trading. It’s one small input (15%) to the headline score, not the whole thing. Be aware of its weak spot: it misses more real falls than it catches, so treat a low number as “no signal here”, not as “this is safe”.',
    probability: 'Estimated 20-day drawdown probability:',
    topFeatures: 'Top contributing factors',
  },
  outcomes: {
    toggle: 'What happened at this risk level before',
    intro:
      'Looking back over the last two years: on days when this stock sat in each risk band, what actually happened over the following 20 trading days? These are historical frequencies for this stock — how often it ended higher or lower, the typical range of outcomes, and how often a 10%+ drop or 10%+ jump occurred along the way.',
    samples: 'past occurrences',
    currentBand: 'current level',
    insufficient: 'small sample — read loosely',
    noData: 'This stock hasn’t traded at this risk level in the lookback window.',
    range: 'Typical outcome range',
    drawdown10: '10%+ drop occurred',
    rally10: '10%+ jump occurred',
    takeaway:
      'Note what the score actually shifts: higher risk bands widen the range of outcomes in BOTH directions — bigger drops and bigger jumps become more common — rather than simply making a fall more likely. That is what the risk score measures: turbulence, not direction.',
    disclaimer:
      'Historical frequencies for this stock only — past patterns, not probabilities of what happens next, and not investment advice.',
  },
  history: {
    toggle: 'Bull, bear and crisis history',
    intro:
      'The named bull markets, bear markets, economic expansions, recessions and financial crises of the past century — and what this stock actually did inside each window it was trading through. The descriptions are historical context; every number is measured from this stock’s own price series, not quoted from anywhere.',
    noScoreImpact:
      'None of this feeds the risk score. Nothing on this panel is an input to the number at the top of the card — it is background you read alongside it. Two reasons: no backtest shows that a stock’s 2008 drawdown predicts its risk today, and only stocks that survived a crisis have a drawdown to show, so scoring on it would rank survivors against survivors.',
    coverage:
      '{ticker} price history begins {start} · {covered} of {total} listed events overlap it',
    ongoing: 'now',
    partial: 'listed mid-event',
    noneCovered: 'No events of the selected types overlap this stock’s price history.',
    priorToggle: '{count} events before {ticker} began trading',
    kind: {
      bull: 'Bull market',
      bear: 'Bear market',
      expansion: 'Expansion',
      recession: 'Recession',
      crisis: 'Crisis',
    },
    stat: {
      return: 'Return in window',
      drawdown: 'Worst drawdown',
      vol: 'Realised volatility',
      days: 'Trading days',
    },
    takeaway:
      'What to read here: the same event moves different stocks by wildly different amounts, and the drawdown column is usually the more revealing one — a stock can finish a crisis window roughly flat having fallen by half in the middle of it.',
    sources: 'Sources:',
    disclaimer:
      'Historical record and this stock’s realised past behaviour — not a forecast, not a claim that any of these events will recur, and not investment advice.',
  },
  auth: {
    signIn: 'Sign in',
    signUp: 'Create account',
    signUpShort: 'Sign up',
    signOut: 'Sign out',
    email: 'Email',
    password: 'Password',
    passwordHint: 'At least 8 characters',
    nickname: 'Nickname',
    nicknameHint: '2–30 characters — shown on your posts instead of your email',
    agreeNotAdvice:
      'I understand risk scores and all community posts are data-driven reference only, not investment advice',
    agreeCommunityRules:
      'I agree to only post stock risk-analysis content here — no trading directives, political discussion, solicitation, or off-topic content',
    consentNotice:
      'Your nickname (not your email) is shown publicly on your posts. The site admin can see your nickname, the email you sign up with, and basic usage data (which features you use and when) — used only for data analysis and keeping the site secure.',
    consentLabel: 'I understand and agree',
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
    scopeHint: '💡 Risk-analysis observations only — no trading directives, political content, or off-topic posts.',
    postDisclaimer: 'Posting means this is a risk-analysis discussion, not investment advice.',
    posting: 'Posting…',
    post: 'Post',
    signInToPost: 'Sign in to share your own analysis.',
    topAnalysis: 'Top community take',
    recentTakes: 'Recent community takes',
    viewAll: 'View all',
    opinionNote:
      'Community observations are individual users’ own opinions — not Riscore’s view, and not investment advice.',
    beFirst: 'No analysis yet for this stock — be the first to share your take.',
    shareCta: 'Share your analysis',
    moderation: {
      trading_directive:
        'Posts can’t contain buy/sell calls or price targets — describe the risk data instead.',
      solicitation: 'Posts can’t contain contact info, group invites, or promotions.',
      abuse: 'That language isn’t allowed here — keep it civil.',
    },
    report: {
      button: 'Report this post',
      prompt: 'Why are you reporting this post?',
      done: 'Reported',
      reasons: {
        investment_advice: 'Investment advice',
        political: 'Political content',
        misinformation: 'Misinformation',
        solicitation: 'Spam / solicitation',
        abuse: 'Abusive language',
        off_topic: 'Off-topic',
      },
    },
  },
  admin: {
    navButton: 'Admin',
    title: 'Admin Dashboard',
    tab: {
      overview: 'Overview',
      usage: 'Usage',
      users: 'Users',
      reports: 'Reports',
    },
    reports: {
      empty: 'No pending reports — the community queue is clear.',
      reportedBy: 'reported by',
      dismiss: 'Dismiss',
      deletePost: 'Delete post',
    },
    totalRequests: 'Total requests',
    uniqueUsers: 'Unique users',
    last24h: 'Last 24h',
    last7d: 'Last 7 days',
    hourlyHistogram: 'Requests by hour (UTC)',
    topPaths: 'Top pages',
    searchUsers: 'Search users by email…',
    noUsers: 'No users found.',
    adminBadge: 'Admin',
    bannedBadge: 'Banned',
    ban: 'Ban',
    unban: 'Unban',
    deleteAsAdmin: 'Delete this post (admin)',
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
        body: 'Riscore turns a stock’s recent price and volatility behavior into one explainable 0–100 risk score, plus the individual signals behind it — so you can quickly see how turbulent a stock is acting right now. This short tour explains what each number describes, and what it deliberately does not: Riscore visualizes risk statistics; it never gives investment advice.',
      },
      score: {
        title: 'The Risk Score (0–100)',
        body: 'Your at-a-glance read: LOW / MODERATE / HIGH / EXTREME compares the stock to its own recent history, not to other stocks. A jump into HIGH or EXTREME describes turbulence — bigger swings than this stock’s own normal — and nothing more. It is not a buy/sell signal, and Riscore never suggests what to do about it; for decisions, consult a licensed financial adviser.',
      },
      breakdown: {
        title: 'What’s driving the score',
        body: 'Open "What does this score mean?" to see the five ingredients — Volatility, Tail Risk, Drawdown, Market Sensitivity, Liquidity — and their weights. Knowing which category is elevated tells you what kind of turbulence the number is describing: elevated Liquidity and elevated Tail Risk are very different situations, even at the same headline score.',
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
  about: {
    navButton: 'About',
    title: 'About Riscore — how it works',
    intro:
      'Riscore turns live market data into one explainable 0–100 risk score per stock — a reading of how turbulently a stock is behaving versus its own history, with every input visible and every number explained in plain language. Built as a serious, transparent risk-analysis tool: no black boxes, no advice, no hype.',
    pipelineTitle: 'How the score is built',
    pipeline: {
      data: {
        title: 'Live market data, resilient by design',
        body: 'US prices via the Twelve Data market-data API; China & Hong Kong via akshare. Daily-refreshed snapshots keep scores available even when an upstream source throttles.',
      },
      lenses: {
        title: 'Five explainable risk lenses',
        body: 'Volatility, tail risk, drawdown, market sensitivity and liquidity — each measured as a percentile against the same stock’s own ~2-year history, then combined with regime-aware weights that adapt to overall market stress (VIX).',
      },
      ml: {
        title: 'Machine learning, kept on a leash',
        body: 'A walk-forward-validated XGBoost model estimates the probability of a 10%+ drawdown in the next 20 trading days. It contributes a deliberately capped 15% of the headline score, and every prediction ships with its SHAP factor breakdown.',
      },
      stress: {
        title: 'Historical stress tests & outcome bands',
        body: 'Every stock is replayed against 2008 / 2020 / 2022 crisis conditions, and each risk band shows what actually happened at that level in the past — real frequencies, not promises.',
      },
      explain: {
        title: 'Deterministic plain-language explanations',
        body: 'Every metric’s reading comes from reviewed threshold tables — not from a language model — so the wording is auditable, consistent, and can never drift into advice.',
      },
    },
    validationTitle: 'Validated, with the numbers published',
    validationIntro:
      'The ML leg is evaluated walk-forward — trained only on data that came before what it is tested on, the same way it would run live:',
    stats: {
      stocks: { value: '56', label: 'stocks in the validation universe' },
      years: { value: '5 yrs', label: 'of walk-forward evaluation' },
      auc: { value: '0.67', label: 'mean ROC-AUC, documented' },
      weight: { value: '15%', label: 'capped ML share of the score' },
    },
    honesty1:
      'We publish the model’s weaknesses too: its recall is documented as low — it misses more real drawdowns than it flags. Treat a low probability as “no signal here”, never as “safe”.',
    honesty2:
      'The score describes the past and present — percentiles of observed behavior. It is not a prediction of future prices and never becomes one.',
    honesty3:
      'When a data source is throttled or a model artefact is unavailable, the app says so and degrades visibly — it never silently invents numbers.',
    securityTitle: 'Security & privacy',
    security: {
      accounts: {
        title: 'Accounts done properly',
        body: 'Passwords are bcrypt-hashed (never stored or logged in plain text) and sessions use signed JWTs. Banned accounts are locked out at every endpoint on their next request.',
      },
      data: {
        title: 'Minimal data, explicit consent',
        body: 'We store only what the product needs: email, nickname, watchlist, posts and votes. Sign-up requires itemized consent, and the privacy notice says exactly what the admin can see and why — data analysis and site security, nothing else. Nothing is sold or shared.',
      },
      community: {
        title: 'A moderated community',
        body: 'Posts are screened against scope rules (no trade directives, no solicitation, no abuse), any user can report a post, and reports go to an admin review queue with ban powers behind it.',
      },
      transparency: {
        title: 'Transparent by construction',
        body: 'The factor weights, thresholds, validation write-up and known limitations are documented openly — the same numbers this page quotes. If the docs and the app ever disagree, that’s a bug, not marketing.',
      },
    },
    responsible:
      'Riscore is an educational risk-analysis tool. Scores are descriptive statistics about observed market behavior; community posts are individual users’ opinions. Nothing on this site is investment advice or a solicitation to trade — always use your own judgment.',
  },
  footer: {
    tagline: 'Explainable risk scoring on live market data.',
    legal: 'Legal',
    disclaimer: 'Disclaimer',
    disclaimerTitle: 'Disclaimer',
    disclaimerBody1:
      'Riscore is a quantitative risk visualization tool. We display statistical risk metrics based on historical market data.',
    disclaimerNotHeading: 'We do NOT provide:',
    disclaimerNot1: 'Investment advice',
    disclaimerNot2: 'Buy / sell recommendations',
    disclaimerNot3: 'Return forecasts',
    disclaimerNot4: 'Personalized financial guidance',
    disclaimerAdviser:
      'Always consult a licensed financial adviser before making investment decisions.',
    privacy: 'Privacy & Consent',
    license: 'License & Data Sources',
    support: 'Support',
    contact: 'Contact Admin',
    privacyTitle: 'Privacy & Consent',
    privacyBody1:
      'We store only what your account needs to work: your email, your hashed password, your watchlist, and any posts or votes you make in the Community board. We do not sell your data or share it with advertisers.',
    privacyBody2:
      'By creating an account and using this site, you consent to that data being processed to provide the service. You can delete your own posts at any time, or contact the admin below about closing your account.',
    licenseTitle: 'License & Data Sources',
    licenseBody1:
      'Risk scores are computed from market data provided by Twelve Data (US) and akshare (China/Hong Kong). This tool is for informational and educational purposes only — it is not investment advice, and nothing on this site is a solicitation to buy or sell any security.',
    licenseBody2: 'Community analysis posts are the personal opinions of individual users, not the platform.',
    contactTitle: 'Contact the Admin',
    contactBody:
      "We don't publish a support email address — the way to reach the site admin is inside the app, through the Community board where the admin account is active.",
    openCommunity: 'Open Community',
  },
}
