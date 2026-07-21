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
  // Deterministic "what this number means" readings (see explain/readings.js).
  // Strictly descriptive: they characterise the measurement and never suggest
  // an action. Generated from threshold tables, not an LLM — so the wording
  // can be reviewed once and cannot drift.
  readings: {
    title: 'What this number means',
    disclaimer: 'Descriptive statistics about past behavior — not a forecast or a recommendation.',
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
      low: 'Day-to-day price swings are small — a comparatively steady tape for a listed stock.',
      normal: 'Day-to-day swings sit in an ordinary range for a listed stock.',
      elevated: 'This stock is swinging more than a typical one — wider daily moves in both directions.',
      high: 'Daily moves are substantially wider than a typical stock’s over the last month.',
    },
    var95: {
      mild: 'This is roughly the loss seen on the worst 1-in-20 trading days — currently a mild figure.',
      moderate: 'This is roughly the loss seen on the worst 1-in-20 trading days — a moderate figure.',
      elevated: 'This is roughly the loss seen on the worst 1-in-20 trading days — a sizeable figure.',
      severe: 'This is roughly the loss seen on the worst 1-in-20 trading days — a large figure.',
    },
    beta: {
      negative: 'Over this window it moved inversely to the benchmark — rising when the market fell, and vice versa.',
      defensive: 'It moves less than the benchmark, so market-wide swings arrive damped.',
      inline: 'It moves roughly in step with the benchmark.',
      amplified: 'It amplifies the benchmark — a 1% market move has tended to produce a larger move here.',
      high: 'It strongly amplifies the benchmark, so market-wide swings land here magnified.',
    },
    rsi: {
      oversold: 'Selling pressure has dominated recently. Below 30 is conventionally called “oversold” — a description of momentum, not a forecast.',
      weak: 'Momentum has leaned to the downside, without reaching an extreme.',
      neutral: 'Buying and selling pressure have been roughly balanced.',
      firm: 'Momentum has leaned to the upside, without reaching an extreme.',
      overbought: 'Buying pressure has dominated recently. Above 70 is conventionally called “overbought” — a description of momentum, not a forecast.',
    },
    factor: {
      low: 'Sits in the calmer end of this stock’s own history.',
      moderate: 'Sits in a normal range for this stock.',
      elevated: 'Running above this stock’s normal range — one of the main things lifting the score.',
      high: 'Near the top of this stock’s own historical range — a main driver of the score.',
    },
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
  footer: {
    tagline: 'Explainable risk scoring on live market data.',
    legal: 'Legal',
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
