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
      plain: 'How much the price jumps around day to day. Big moves up and down = high; steady, small moves = low. High isn’t automatically bad — it just means a rougher ride.',
    },
    tail: {
      label: 'Tail Risk',
      short: 'Tail Risk',
      plainShort: 'How ugly the rare bad days get',
      plain: 'The “what if things really go wrong” risk. Not the normal ups and downs — this is about the handful of genuinely awful days, and how bad they’ve been for this stock.',
    },
    drawdown: {
      label: 'Drawdown',
      short: 'Drawdown',
      plainShort: 'How far it can fall at worst',
      plain: 'The worst drop from top to bottom. If you’d bought at the peak, how much would you have been down at the lowest point — and how long did it stay down before climbing back?',
    },
    sensitivity: {
      label: 'Market Sensitivity',
      short: 'Sensitivity',
      plainShort: 'Does it follow the whole market?',
      plain: 'When the market as a whole drops, does this one drop with it? Moving about the same = it follows the market; moving less = steadier than the market; moving more = it magnifies whatever the market does.',
    },
    liquidity: {
      label: 'Liquidity',
      short: 'Liquidity',
      plainShort: 'How easy it is to sell',
      plain: 'Whether there are enough people buying and selling to trade without shoving the price around. Busy trading = you can usually get in and out near the price you see. Thin trading = your own order can move the price.',
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
      'How bumpy the ride is. It measures how much the price jumps around over a stretch of time — bigger, choppier moves mean higher volatility. It says nothing about direction: a stock climbing steadily upward can still be very volatile.',
    var95:
      'What a typical bad day looks like. Out of roughly every 20 trading days, the worst one has historically cost about this much. It’s a rough yardstick, not a floor — a genuinely bad day can be far worse.',
    beta:
      'How closely it follows the whole market. 1.0 means it moves about the same as the market; below 1.0 means it moves less (steadier); above 1.0 means it exaggerates the market’s moves — in both directions.',
    rsi: 'Whether it’s been bought or sold hard recently. Above 70 means a lot of buying lately (people call that “overbought”); below 30 means a lot of selling (“oversold”). It describes what just happened — it does not predict what happens next.',
  },
  // Deterministic "what this number means" readings (see explain/readings.js).
  // Strictly descriptive: they characterise the measurement and never suggest
  // an action. Generated from threshold tables, not an LLM — so the wording
  // can be reviewed once and cannot drift.
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
