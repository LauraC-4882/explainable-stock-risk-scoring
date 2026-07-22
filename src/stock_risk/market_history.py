"""[G8] Historical market-regime timeline, overlaid on one stock's own prices.

Answers "what did this stock actually do during each of the past century's
named bull markets, bear markets, economic expansions, recessions, and
financial crises?" — its realised return, its worst peak-to-trough drawdown,
and its realised volatility inside each event window.

**These events do not contribute to `risk_score`, and this module is not
wired into the producer layer at all.** That is a deliberate design decision
with two independent reasons:

  1. *The repo's own rule.* `scoring/producers/base.py` refuses a nonzero
     weight on any producer whose `validation` is None, and no walk-forward
     backtest exists showing that "a stock drew down 60% in 2008" predicts
     anything about its forward risk today. Folding it into the headline
     number would be exactly the launder-unvalidated-numbers failure the
     producer layer was built to prevent — the same reason `[G6]`'s
     regime_technicals block ships at weight 0.
  2. *A survivorship problem the weight-0 rule alone would not catch.* Only
     stocks that still trade have a 2008 drawdown to display. Scoring a
     living stock on how it survived a crisis, without the delisted names
     that did not, ranks survivors against survivors and calls the result
     risk. There is no honest way to weight this per-stock without the
     failures in the sample, and the failures are not in the sample.

So the payload carries `contributes_to_risk_score: False` explicitly rather
than leaving a reader to infer it from the panel's placement, and the UI
states it in prose.

**Prose is cited, numbers are computed.** Each event's `summary` is
contextual description sourced from the references in `SOURCES` — it says
what drove the episode, never what it returned. Every *number* the user sees
is computed here from the actual price series for the actual ticker
(`overlay_events`), not copied from a secondary source. Widely-quoted index
figures ("the Nasdaq surged over 400%", "the Dow rose 500%") are deliberately
absent: they vary by index, by exact start/end date, and by whether dividends
are counted, and this file has no way to verify them. What it *can* verify is
what the stock in front of the user did, so that is what it reports.

Coverage is reported, never silently assumed. An event that predates a
ticker's first trade is returned with `coverage: "none"` and null statistics
rather than omitted — "Apple did not exist during the 1929 crash" is
information, and dropping the row would leave a reader to conclude the crash
did not happen. A ticker that listed midway through an event gets
`coverage: "partial"` and stats computed over the portion actually traded,
flagged so the number is not read as the full-window figure.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

TRADING_DAYS = 252

# Below this many bars inside a window, return/drawdown/vol are describing a
# handful of prints rather than the event, so the row degrades to coverage
# "none". Ten sessions is two trading weeks — short enough that the 1987 and
# 2020 crashes (both well under a month of real damage) still qualify.
MIN_BARS = 10

# Event kinds, in the order the UI groups them. "bull"/"bear" are equity-market
# episodes; "expansion"/"recession" are macroeconomic (NBER-dated) and
# deliberately kept separate — the economy and the stock market turn on
# different dates, and collapsing them would imply a synchrony that is not
# there (the 2009-2020 expansion and the 2009-2020 bull market share a decade
# and almost nothing else about their start conditions).
KINDS = ("bull", "bear", "expansion", "recession", "crisis")


@dataclass(frozen=True)
class MarketEvent:
    """One named historical episode. Dates are ISO; `end=None` means ongoing."""

    id: str
    kind: str
    name: str
    name_zh: str
    start: str
    end: Optional[str]
    region: str
    summary: str
    summary_zh: str
    sources: tuple[str, ...] = field(default=())


# ── Citations ────────────────────────────────────────────────────────────────
# Referenced by key from each event's `sources`. Served with the payload so the
# UI can attribute the contextual prose rather than presenting it unsourced.

# Two URLs below carry `noqa: E501`: they are single tokens over the 100-column
# limit with no legal break point, and splitting a URL across concatenated
# string literals to satisfy a linter makes it harder to verify by eye against
# the page it cites.
SOURCES: dict[str, dict[str, str]] = {
    "wiki_expansions": {
        "title": "List of economic expansions in the United States — Wikipedia",
        "url": "https://en.wikipedia.org/wiki/List_of_economic_expansions_in_the_United_States",
    },
    "wiki_crises_zh": {
        "title": "金融危机 — 维基百科",
        "url": "https://zh.wikipedia.org/wiki/%E9%87%91%E8%9E%8D%E5%8D%B1%E6%9C%BA",
    },
    "finder_bulls": {
        "title": "The biggest bull markets in history — Finder UK",
        "url": "https://www.finder.com/uk/share-trading/share-trading-research/biggest-bull-markets-in-history",  # noqa: E501
    },
    "rockco": {
        "title": "Bull and Bear Markets — Rockefeller Capital Management",
        "url": "https://www.rockco.com/strategic-insights/bull-and-bear-markets/",
    },
    "wallst_247": {
        "title": "This Bull Market Is Crushing History — 24/7 Wall St.",
        "url": "https://247wallst.com/investing/2026/07/17/this-bull-market-is-crushing-history-heres-why-investors-shouldnt-think-its-over/",  # noqa: E501
    },
}


# ── Equity bull markets ──────────────────────────────────────────────────────

_BULLS = [
    MarketEvent(
        id="bull_postwar",
        kind="bull",
        name="Post-World War II Boom",
        name_zh="二战后繁荣期",
        start="1949-06-13",
        end="1956-08-02",
        region="us",
        summary=(
            "Post-war industrial rebuilding and pent-up consumer demand drove one of the longest "
            "uninterrupted advances in S&P 500 history."
        ),
        summary_zh=(
            "战后工业重建与被压抑的消费需求，推动标普 500 走出历史上最长的连续上涨行情之一。"
        ),
        sources=("finder_bulls", "rockco"),
    ),
    MarketEvent(
        id="bull_reaganomics",
        kind="bull",
        name="Reaganomics Era",
        name_zh="里根经济学时期",
        start="1982-08-12",
        end="1987-08-25",
        region="us",
        summary=(
            "Broad deregulation and a sustained fall in interest rates from their early-1980s peak "
            "lifted US equities sharply, until the advance ended in the October 1987 crash."
        ),
        summary_zh=(
            "大规模放松管制，加上利率自 1980 年代初高点持续回落，推动美股大幅上行，直到 1987 年 10 "
            "月股灾终结这轮行情。"
        ),
        sources=("finder_bulls", "rockco"),
    ),
    MarketEvent(
        id="bull_dotcom",
        kind="bull",
        name="Dot-Com Boom",
        name_zh="互联网泡沫牛市",
        start="1990-10-11",
        end="2000-03-24",
        region="us",
        summary=(
            "The commercialisation of the internet, cheap credit and a 1997 capital-gains tax cut "
            "pushed technology valuations to records — concentrated in the Nasdaq — before the "
            "bubble broke in 2000."
        ),
        summary_zh=(
            "互联网商业化、宽松信贷与 1997 年资本利得税下调，把科技股估值推上历史高位（集中体现在纳"
            "斯达克），直至 2000 年泡沫破裂。"
        ),
        sources=("finder_bulls", "wiki_expansions"),
    ),
    MarketEvent(
        id="bull_post_gfc",
        kind="bull",
        name="Post-Financial-Crisis Run",
        name_zh="金融危机后长牛",
        start="2009-03-09",
        end="2020-02-19",
        region="us",
        summary=(
            "Born out of the 2008 crisis and sustained by near-zero policy rates and three rounds "
            "of quantitative easing, this became the longest bull market on record before the "
            "COVID-19 crash ended it."
        ),
        summary_zh=(
            "脱胎于 2008 年危机，由接近零的政策利率与三轮量化宽松支撑，成为有记录以来最长的牛市，直"
            "到新冠疫情引发的崩盘将其终结。"
        ),
        sources=("finder_bulls", "rockco", "wiki_expansions"),
    ),
    MarketEvent(
        id="bull_ai",
        kind="bull",
        name="AI-Driven Rally",
        name_zh="人工智能驱动行情",
        start="2022-10-12",
        end=None,
        region="global",
        summary=(
            "Beginning at the October 2022 low, global equity indices ran to successive record "
            "highs on cooling inflation and heavy capital spending on artificial-intelligence "
            "infrastructure."
        ),
        summary_zh=(
            "自 2022 年 10 月低点起，随着通胀回落与人工智能基础设施的大规模资本开支，全球股指接连刷"
            "新历史高位。"
        ),
        sources=("wallst_247", "rockco"),
    ),
]


# ── Equity bear markets ──────────────────────────────────────────────────────

_BEARS = [
    MarketEvent(
        id="bear_1929",
        kind="bear",
        name="Wall Street Crash and Great Depression",
        name_zh="1929 年股灾与大萧条",
        start="1929-09-03",
        end="1932-07-08",
        region="us",
        summary=(
            "The deepest and longest equity decline in US history, and the market leg of the Great "
            "Depression."
        ),
        summary_zh="美国历史上最深、最长的股市下跌，也是大萧条在股票市场上的体现。",
        sources=("rockco", "wiki_crises_zh"),
    ),
    MarketEvent(
        id="bear_1973",
        kind="bear",
        name="1973–74 Oil Shock Bear Market",
        name_zh="1973–74 年石油危机熊市",
        start="1973-01-11",
        end="1974-10-03",
        region="global",
        summary=(
            "The 1973 oil embargo quadrupled crude prices into an economy already running high "
            "inflation, producing the stagflation decline."
        ),
        summary_zh="1973 年石油禁运使原油价格翻两番，叠加本已高企的通胀，形成滞胀式下跌。",
        sources=("rockco", "wiki_crises_zh"),
    ),
    MarketEvent(
        id="bear_dotcom_bust",
        kind="bear",
        name="Dot-Com Bust",
        name_zh="互联网泡沫破裂",
        start="2000-03-24",
        end="2002-10-09",
        region="us",
        summary=(
            "The Fed's 1999 rate rises punctured technology valuations; the decline ran through a "
            "string of high-profile bankruptcies over the next two years."
        ),
        summary_zh="美联储 1999 年起加息刺破科技股估值，随后两年伴随一连串知名企业破产，跌势持续。",
        sources=("rockco", "wiki_expansions"),
    ),
    MarketEvent(
        id="bear_gfc",
        kind="bear",
        name="Global Financial Crisis Bear Market",
        name_zh="全球金融危机熊市",
        start="2007-10-09",
        end="2009-03-09",
        region="global",
        summary=(
            "Mortgage defaults spread into bank balance sheets and then into every risk asset — "
            "the equity leg of the 2007–2008 crisis."
        ),
        summary_zh=(
            "房贷违约蔓延至银行资产负债表，再传导到所有风险资产——2007–2008 年危机的股市部分。"
        ),
        sources=("rockco", "wiki_crises_zh"),
    ),
    MarketEvent(
        id="bear_covid",
        kind="bear",
        name="COVID-19 Crash",
        name_zh="新冠疫情崩盘",
        start="2020-02-19",
        end="2020-03-23",
        region="global",
        summary=(
            "The fastest peak-to-bear-market decline on record, as pandemic lockdowns shut down "
            "travel, hospitality and much of the service economy."
        ),
        summary_zh="有记录以来从高点跌入熊市最快的一次，疫情封锁使旅游、酒店与大部分服务业停摆。",
        sources=("rockco", "wiki_crises_zh"),
    ),
    MarketEvent(
        id="bear_2022",
        kind="bear",
        name="2022 Inflation Bear Market",
        name_zh="2022 年通胀熊市",
        start="2022-01-03",
        end="2022-10-12",
        region="global",
        summary=(
            "The fastest tightening cycle in four decades repriced long-duration assets, with "
            "technology and unprofitable growth names hit hardest."
        ),
        summary_zh="四十年来最快的加息周期重定价长久期资产，科技股与未盈利成长股跌幅最大。",
        sources=("rockco", "wallst_247"),
    ),
]


# ── US economic expansions (NBER-dated; figures per Wikipedia's table) ────────
# `summary` carries the employment/GDP growth figures *as published in the
# cited table* — these are macroeconomic statistics about the US economy, not
# claims about any stock, and they are attributed rather than recomputed.

_EXPANSIONS = [
    MarketEvent(
        id="exp_1945",
        kind="expansion",
        name="Post-war demobilisation expansion",
        name_zh="战后复员扩张期",
        start="1945-10-01",
        end="1948-11-30",
        region="us",
        summary=(
            "37 months. Employment +5.2%/yr, GDP +1.5%/yr. Falling government spending after "
            "demobilisation suppressed GDP, but private activity expanded briskly throughout."
        ),
        summary_zh=(
            "持续 37 个月。就业年增 5.2%，GDP 年增 1.5%。复员后政府支出下降压低了 GDP，但私人部门活"
            "动全程快速扩张。"
        ),
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="exp_1949",
        kind="expansion",
        name="Korean War expansion",
        name_zh="朝鲜战争扩张期",
        start="1949-10-01",
        end="1953-07-31",
        region="us",
        summary=(
            "45 months. Employment +4.4%/yr, GDP +6.9%/yr — the strongest GDP growth of any "
            "post-war expansion. Ended when the Fed tightened after the war."
        ),
        summary_zh=(
            "持续 45 个月。就业年增 4.4%，GDP 年增 6.9%，是战后所有扩张期中 GDP 增速最高的一次。战"
            "后美联储收紧货币政策使其结束。"
        ),
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="exp_1954",
        kind="expansion",
        name="Mid-1950s expansion",
        name_zh="1950 年代中期扩张",
        start="1954-05-01",
        end="1957-08-31",
        region="us",
        summary=(
            "39 months. Employment +2.5%/yr, GDP +4.0%/yr — slower than the two expansions before "
            "it."
        ),
        summary_zh="持续 39 个月。就业年增 2.5%，GDP 年增 4.0%，慢于此前两轮扩张。",
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="exp_1958",
        kind="expansion",
        name="Late-1950s expansion",
        name_zh="1950 年代末扩张",
        start="1958-04-01",
        end="1960-04-30",
        region="us",
        summary=(
            "24 months. Employment +3.6%/yr, GDP +5.6%/yr. A brief expansion ended by the 1960 "
            "monetary recession."
        ),
        summary_zh=(
            "持续 24 个月。就业年增 3.6%，GDP 年增 5.6%。这一短暂扩张被 1960 年的货币紧缩型衰退终结"
            "。"
        ),
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="exp_1961",
        kind="expansion",
        name="1960s long expansion",
        name_zh="1960 年代长扩张",
        start="1961-02-01",
        end="1969-12-31",
        region="us",
        summary=(
            "106 months. Employment +3.3%/yr, GDP +4.9%/yr. Incomes and employment rose and "
            "poverty fell sharply; Vietnam War fiscal policy left rising inflation by the decade's "
            "end."
        ),
        summary_zh=(
            "持续 106 个月。就业年增 3.3%，GDP 年增 4.9%。收入与就业上升、贫困率大幅下降；越战期间"
            "的扩张性财政政策在十年末留下了上升的通胀。"
        ),
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="exp_1970",
        kind="expansion",
        name="Early-1970s expansion",
        name_zh="1970 年代初扩张",
        start="1970-11-01",
        end="1973-11-30",
        region="us",
        summary=(
            "36 months. Employment +3.4%/yr, GDP +5.1%/yr. Ended abruptly with the 1973 oil "
            "crisis, after which stagflation set in."
        ),
        summary_zh=(
            "持续 36 个月。就业年增 3.4%，GDP 年增 5.1%。因 1973 年石油危机戛然而止，此后进入滞胀。"
        ),
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="exp_1975",
        kind="expansion",
        name="Late-1970s expansion",
        name_zh="1970 年代末扩张",
        start="1975-03-01",
        end="1980-01-31",
        region="us",
        summary=(
            "58 months. Employment +3.6%/yr, GDP +4.3%/yr, with high inflation throughout. Ended "
            "with the second energy crisis, whose real oil price peak stood until 2008."
        ),
        summary_zh=(
            "持续 58 个月。就业年增 3.6%，GDP 年增 4.3%，全程伴随高通胀。以第二次石油危机告终，其实"
            "际油价高点直到 2008 年才被超越。"
        ),
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="exp_1980",
        kind="expansion",
        name="1980–81 short expansion",
        name_zh="1980–81 年短暂扩张",
        start="1980-07-01",
        end="1981-07-31",
        region="us",
        summary=(
            "12 months. Employment +2.0%/yr, GDP +4.4%/yr, but unemployment never fell below 7.2%. "
            "Rebounding inflation drove further tightening — the 1980–82 'double-dip' recession."
        ),
        summary_zh=(
            "持续 12 个月。就业年增 2.0%，GDP 年增 4.4%，但失业率从未低于 7.2%。通胀反弹促使进一步"
            "紧缩，形成 1980–82 年的「二次探底」衰退。"
        ),
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="exp_1982",
        kind="expansion",
        name="1980s expansion",
        name_zh="1980 年代扩张",
        start="1982-12-01",
        end="1990-07-31",
        region="us",
        summary=(
            "92 months. Employment +2.8%/yr, GDP +4.3%/yr. Inflation under control, stable oil "
            "prices and a steep rise in private investment made this the then-second-longest "
            "peacetime expansion."
        ),
        summary_zh=(
            "持续 92 个月。就业年增 2.8%，GDP 年增 4.3%。通胀受控、油价稳定、私人投资大幅上升，使其"
            "成为当时和平时期第二长的扩张。"
        ),
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="exp_1991",
        kind="expansion",
        name="1990s expansion",
        name_zh="1990 年代扩张",
        start="1991-03-01",
        end="2001-03-31",
        region="us",
        summary=(
            "120 months. Employment +2.0%/yr, GDP +3.6%/yr. Job growth was weak at first amid "
            "post-Cold-War defence layoffs; the second half saw the dot-com bubble inflate and "
            "then burst."
        ),
        summary_zh=(
            "持续 120 个月。就业年增 2.0%，GDP 年增 3.6%。初期受冷战结束后国防业裁员拖累、就业疲弱"
            "；后半段经历互联网泡沫的膨胀与破裂。"
        ),
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="exp_2001",
        kind="expansion",
        name="2000s housing expansion",
        name_zh="2000 年代房地产扩张",
        start="2001-11-01",
        end="2007-12-31",
        region="us",
        summary=(
            "73 months. Employment +0.9%/yr, GDP +2.8%/yr — a 'jobless recovery'. Low rates and "
            "loosened lending standards grew the mid-1990s rise in home prices into a real-estate "
            "bubble."
        ),
        summary_zh=(
            "持续 73 个月。就业年增 0.9%，GDP 年增 2.8%，被称为「无就业复苏」。低利率与放松的信贷标"
            "准把 1990 年代中期开始的房价上涨推成房地产泡沫。"
        ),
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="exp_2009",
        kind="expansion",
        name="Post-Great-Recession expansion",
        name_zh="大衰退后扩张期",
        start="2009-06-01",
        end="2020-02-29",
        region="us",
        summary=(
            "128 months, the longest on record. Employment +1.1%/yr, GDP +2.3%/yr — and, uniquely "
            "among post-war expansions, GDP growth stayed under 3% in every calendar year. Ended "
            "by the COVID-19 pandemic."
        ),
        summary_zh=(
            "持续 128 个月，为有记录以来最长。就业年增 1.1%，GDP 年增 2.3%——且在所有战后扩张中独一"
            "无二地，每个日历年 GDP 增速都低于 3%。因新冠疫情结束。"
        ),
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="exp_2020",
        kind="expansion",
        name="Post-COVID expansion",
        name_zh="新冠疫情后扩张期",
        start="2020-04-01",
        end=None,
        region="us",
        summary=(
            "Ongoing. Followed the shortest recession in US history, which had the largest GDP "
            "decline since 1945. Marked by supply-chain shortages, a sustained rise in inflation "
            "and a brief banking crisis in 2023."
        ),
        summary_zh=(
            "仍在进行中。承接美国历史上最短的一次衰退——但其 GDP 降幅为 1945 年以来最大。期间出现供"
            "应链短缺、通胀持续上行，以及 2023 年的短暂银行业危机。"
        ),
        sources=("wiki_expansions",),
    ),
]


# ── Recessions (the post-war contractions between the expansions above) ───────

_RECESSIONS = [
    MarketEvent(
        id="rec_1973",
        kind="recession",
        name="1973–75 recession",
        name_zh="1973–75 年衰退",
        start="1973-11-01",
        end="1975-03-31",
        region="us",
        summary=(
            "Oil-shock recession; inflation stayed high through the contraction, the pattern that "
            "came to be called stagflation."
        ),
        summary_zh="石油冲击引发的衰退；收缩期间通胀居高不下，形成后来被称为「滞胀」的格局。",
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="rec_1981",
        kind="recession",
        name="1981–82 Volcker recession",
        name_zh="1981–82 年沃尔克衰退",
        start="1981-08-01",
        end="1982-11-30",
        region="us",
        summary=(
            "The Fed raised rates hard to break double-digit inflation, at the cost of the deepest "
            "post-war contraction to that point."
        ),
        summary_zh="美联储大幅加息以打破两位数通胀，代价是当时战后最深的一次经济收缩。",
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="rec_1990",
        kind="recession",
        name="1990–91 recession",
        name_zh="1990–91 年衰退",
        start="1990-08-01",
        end="1991-02-28",
        region="us",
        summary=(
            "A mild contraction, followed by a slow recovery hampered by defence-industry layoffs "
            "and 1980s overbuilding in real estate."
        ),
        summary_zh="较温和的收缩，其后复苏缓慢，受国防工业裁员与 1980 年代房地产过度开发拖累。",
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="rec_2001",
        kind="recession",
        name="2001 recession",
        name_zh="2001 年衰退",
        start="2001-04-01",
        end="2001-11-30",
        region="us",
        summary=(
            "A mild recession as the dot-com bubble deflated, followed by a recovery long "
            "criticised as jobless."
        ),
        summary_zh="互联网泡沫消退引发的温和衰退，其后的复苏长期被批评为「无就业复苏」。",
        sources=("wiki_expansions",),
    ),
    MarketEvent(
        id="rec_2007",
        kind="recession",
        name="Great Recession",
        name_zh="大衰退",
        start="2007-12-01",
        end="2009-06-30",
        region="global",
        summary=(
            "The subprime mortgage collapse destabilised the banking system and ended the Great "
            "Moderation — the deepest contraction since the 1930s."
        ),
        summary_zh="次贷崩溃动摇银行体系，终结了「大缓和」时期——为 1930 年代以来最深的一次收缩。",
        sources=("wiki_expansions", "wiki_crises_zh"),
    ),
    MarketEvent(
        id="rec_2020",
        kind="recession",
        name="COVID-19 recession",
        name_zh="新冠疫情衰退",
        start="2020-02-01",
        end="2020-04-30",
        region="global",
        summary=(
            "The shortest recession in US history, but with the largest GDP decline since 1945."
        ),
        summary_zh="美国历史上最短的一次衰退，但 GDP 降幅为 1945 年以来最大。",
        sources=("wiki_expansions",),
    ),
]


# ── Financial crises ─────────────────────────────────────────────────────────
# Includes pre-market-data episodes (1637, 1720, …). They will always return
# coverage "none" for any tradeable ticker — that is the point: the list is the
# record of what has happened to markets, and truncating it at the start of one
# ticker's price history would misrepresent that record.

_CRISES = [
    MarketEvent(
        id="cri_tulip",
        kind="crisis",
        name="Tulip Mania",
        name_zh="郁金香狂热",
        start="1636-11-01",
        end="1637-05-31",
        region="nl",
        summary=(
            "The first well-documented speculative bubble: Dutch tulip bulb contracts collapsed "
            "after a near-vertical rise."
        ),
        summary_zh="有据可查的第一次投机泡沫：荷兰郁金香球茎合约在近乎垂直的上涨后崩溃。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_south_sea",
        kind="crisis",
        name="South Sea and Mississippi Bubbles",
        name_zh="南海泡沫与密西西比泡沫",
        start="1720-01-01",
        end="1720-12-31",
        region="global",
        summary=(
            "Twin state-sponsored share bubbles in Britain and France collapsed within months of "
            "each other."
        ),
        summary_zh="英国与法国两场由国家背书的股票泡沫在数月之内相继崩溃。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_1792",
        kind="crisis",
        name="Panic of 1792",
        name_zh="1792 年美国金融恐慌",
        start="1792-03-01",
        end="1792-04-30",
        region="us",
        summary=(
            "The first financial crisis of the United States, triggered by speculation in the "
            "newly created bank scrip."
        ),
        summary_zh="美国的第一场金融危机，起因是对新发行银行票据的投机。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_1825",
        kind="crisis",
        name="Panic of 1825",
        name_zh="1825 年英国股市恐慌",
        start="1825-01-01",
        end="1826-12-31",
        region="gb",
        summary=(
            "A London stock-market panic following speculation in Latin American investments, "
            "often called the first modern banking crisis."
        ),
        summary_zh="伦敦股市在拉美投资投机之后陷入恐慌，常被称为第一次现代银行业危机。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_1857",
        kind="crisis",
        name="Panic of 1857",
        name_zh="1857 年危机",
        start="1857-08-01",
        end="1858-12-31",
        region="global",
        summary=(
            "Widely regarded as the first genuinely global financial crisis, transmitted between "
            "continents by telegraph and trade."
        ),
        summary_zh="普遍被视为第一场真正全球化的金融危机，通过电报与贸易在各大洲之间传导。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_1907",
        kind="crisis",
        name="Panic of 1907",
        name_zh="1907 年危机",
        start="1907-10-01",
        end="1908-03-31",
        region="us",
        summary=(
            "A trust-company run with no central bank to stop it — the crisis that led directly to "
            "the founding of the Federal Reserve."
        ),
        summary_zh="信托公司挤兑，而当时没有中央银行可以出手制止——这场危机直接促成了美联储的建立。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_shanghai_rubber",
        kind="crisis",
        name="Shanghai Rubber Stock Crisis",
        name_zh="上海橡皮股票风潮",
        start="1910-06-01",
        end="1910-12-31",
        region="cn",
        summary=(
            "Speculation in rubber-plantation shares collapsed, taking several Shanghai native "
            "banks with it."
        ),
        summary_zh="橡胶种植园股票投机崩盘，拖垮了上海多家钱庄。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_shanghai_1921",
        kind="crisis",
        name="Shanghai Trust and Exchange Crisis",
        name_zh="上海民十信交风潮",
        start="1921-01-01",
        end="1922-12-31",
        region="cn",
        summary=(
            "A boom in newly founded exchanges and trust companies in Shanghai ended in mass "
            "failures."
        ),
        summary_zh="上海新设交易所与信托公司的热潮，最终以大批倒闭收场。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_1929",
        kind="crisis",
        name="Great Depression",
        name_zh="1929 年经济大萧条",
        start="1929-10-01",
        end="1939-12-31",
        region="global",
        summary=(
            "The defining economic collapse of the twentieth century, beginning with the October "
            "1929 crash."
        ),
        summary_zh="二十世纪最具标志性的经济崩溃，始于 1929 年 10 月的股灾。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_oil_1973",
        kind="crisis",
        name="1973 Oil Crisis",
        name_zh="1973 年石油危机",
        start="1973-10-01",
        end="1974-03-31",
        region="global",
        summary="An OPEC embargo quadrupled crude prices, feeding the decade's stagflation.",
        summary_zh="欧佩克禁运使原油价格翻两番，助推了这十年的滞胀。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_latam_debt",
        kind="crisis",
        name="Latin American Debt Crisis",
        name_zh="拉丁美洲债务危机",
        start="1982-08-01",
        end="1989-12-31",
        region="latam",
        summary=(
            "Beginning with Mexico's 1982 default, sovereign debt across Latin America became "
            "unpayable — the region's 'lost decade'."
        ),
        summary_zh=(
            "始于墨西哥 1982 年违约，拉美各国主权债务陷入无法偿付的境地——即该地区的「失落的十年」。"
        ),
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_black_monday",
        kind="crisis",
        name="Black Monday 1987",
        name_zh="1987 年美国股灾",
        start="1987-10-19",
        end="1987-12-31",
        region="global",
        summary=(
            "The largest single-day percentage fall in Dow Jones history, widely attributed in "
            "part to programme trading and portfolio insurance."
        ),
        summary_zh=(
            "道琼斯指数史上单日百分比跌幅最大的一天，普遍认为程序化交易与投资组合保险是部分原因。"
        ),
        sources=("wiki_crises_zh", "rockco"),
    ),
    MarketEvent(
        id="cri_snl",
        kind="crisis",
        name="Savings and Loan Crisis",
        name_zh="储蓄和贷款危机",
        start="1989-01-01",
        end="1991-12-31",
        region="us",
        summary=(
            "Roughly a third of US savings-and-loan associations failed, requiring a large federal "
            "resolution programme."
        ),
        summary_zh="约三分之一的美国储贷协会倒闭，需要联邦政府大规模出手处置。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_japan_bubble",
        kind="crisis",
        name="Japanese Asset Price Bubble Collapse",
        name_zh="日本泡沫经济崩溃",
        start="1990-01-01",
        end="1999-12-31",
        region="jp",
        summary=(
            "Japanese equity and land prices collapsed from their 1989 peak, beginning decades of "
            "deflationary stagnation."
        ),
        summary_zh="日本股价与地价自 1989 年高点崩落，此后进入长达数十年的通缩性停滞。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_black_wednesday",
        kind="crisis",
        name="Black Wednesday (ERM Crisis)",
        name_zh="欧洲汇率机制黑色星期三",
        start="1992-09-16",
        end="1993-08-02",
        region="eu",
        summary=(
            "Speculative attacks forced sterling out of the European Exchange Rate Mechanism and "
            "widened the system's bands."
        ),
        summary_zh="投机性攻击迫使英镑退出欧洲汇率机制，并使该体系的波动区间被迫放宽。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_tequila",
        kind="crisis",
        name="Mexican Peso Crisis",
        name_zh="墨西哥比索危机",
        start="1994-12-01",
        end="1995-12-31",
        region="latam",
        summary=(
            "A sudden devaluation triggered capital flight and default fears, contained by an "
            "international rescue package."
        ),
        summary_zh="突然贬值引发资本外逃与违约担忧，最终靠国际救助方案得以控制。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_asian",
        kind="crisis",
        name="Asian Financial Crisis",
        name_zh="亚洲金融风暴",
        start="1997-07-02",
        end="1998-12-31",
        region="asia",
        summary=(
            "Currency pegs across East and Southeast Asia broke under speculative attack, "
            "producing sharp devaluations and banking failures."
        ),
        summary_zh="东亚与东南亚多国的汇率钉住制在投机攻击下崩溃，引发大幅贬值与银行倒闭。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_russia_1998",
        kind="crisis",
        name="Russian Financial Crisis",
        name_zh="1998 年俄罗斯金融危机",
        start="1998-08-17",
        end="1998-12-31",
        region="ru",
        summary=(
            "Russia devalued the rouble and defaulted on domestic debt, and the shock brought down "
            "the hedge fund LTCM."
        ),
        summary_zh="俄罗斯让卢布贬值并对国内债务违约，冲击波拖垮了对冲基金 LTCM。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_argentina",
        kind="crisis",
        name="Argentine Economic Crisis",
        name_zh="阿根廷经济危机",
        start="2001-12-01",
        end="2002-12-31",
        region="latam",
        summary=(
            "The currency board collapsed, bank deposits were frozen and Argentina defaulted on "
            "its sovereign debt."
        ),
        summary_zh="货币局制度崩溃，银行存款被冻结，阿根廷主权债务违约。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_gfc",
        kind="crisis",
        name="Global Financial Crisis",
        name_zh="2007–2008 环球金融危机",
        start="2007-08-01",
        end="2009-06-30",
        region="global",
        summary=(
            "Subprime mortgage losses became a banking solvency crisis and then a global "
            "contraction — the most severe since the 1930s."
        ),
        summary_zh=(
            "次贷损失演变为银行偿付能力危机，进而引发全球性收缩——1930 年代以来最严重的一次。"
        ),
        sources=("wiki_crises_zh", "rockco"),
    ),
    MarketEvent(
        id="cri_eurozone",
        kind="crisis",
        name="European Sovereign Debt Crisis",
        name_zh="欧洲主权债务危机",
        start="2009-10-01",
        end="2012-09-30",
        region="eu",
        summary=(
            "Greek deficit revisions spread doubt over peripheral eurozone sovereign debt and the "
            "survival of the single currency."
        ),
        summary_zh=(
            "希腊财政赤字数据被修正，引发对欧元区外围国家主权债务乃至单一货币存续的普遍怀疑。"
        ),
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_trade_war",
        kind="crisis",
        name="US–China Trade War",
        name_zh="中美贸易战",
        start="2018-03-22",
        end=None,
        region="global",
        summary=(
            "Successive rounds of tariffs and export controls between the world's two largest "
            "economies, ongoing."
        ),
        summary_zh="全球最大的两个经济体之间接连出台关税与出口管制措施，至今仍在持续。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_covid",
        kind="crisis",
        name="COVID-19 Market Panic",
        name_zh="2020 年新冠国际金融恐慌",
        start="2020-02-19",
        end="2020-04-30",
        region="global",
        summary=(
            "Pandemic lockdowns triggered a liquidity scramble across every asset class, met by "
            "unprecedented central-bank intervention."
        ),
        summary_zh="疫情封锁在所有资产类别引发流动性恐慌，各国央行以史无前例的力度出手干预。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_ukraine",
        kind="crisis",
        name="Russian Invasion of Ukraine",
        name_zh="俄罗斯入侵乌克兰的经济影响",
        start="2022-02-24",
        end=None,
        region="global",
        summary=(
            "Sanctions and the disruption of energy and grain exports drove an energy price shock, "
            "sharpest in Europe."
        ),
        summary_zh="制裁与能源、粮食出口中断引发能源价格冲击，欧洲受影响最为剧烈。",
        sources=("wiki_crises_zh",),
    ),
    MarketEvent(
        id="cri_banks_2023",
        kind="crisis",
        name="2023 Banking Crisis",
        name_zh="2023 年银行危机",
        start="2023-03-08",
        end="2023-05-01",
        region="global",
        summary=(
            "Silvergate, Silicon Valley Bank and Signature Bank failed within a week, and UBS was "
            "pushed to absorb Credit Suisse."
        ),
        summary_zh="银门银行、硅谷银行与签名银行在一周内相继关闭，瑞银被推动收购瑞士信贷。",
        sources=("wiki_crises_zh",),
    ),
]


EVENTS: tuple[MarketEvent, ...] = tuple(_BULLS + _BEARS + _EXPANSIONS + _RECESSIONS + _CRISES)


def _stats(window: pd.Series) -> dict:
    """Realised return, worst peak-to-trough drawdown and annualised volatility
    inside one event window.

    Every value is cast to a native Python float — a numpy scalar reaching an
    API response raises inside json.dumps (CLAUDE.md rule 4).
    """
    first = float(window.iloc[0])
    last = float(window.iloc[-1])
    drawdown = float((window / window.cummax() - 1.0).min())
    log_returns = np.log(window / window.shift(1)).dropna()
    vol = (
        float(log_returns.std() * np.sqrt(TRADING_DAYS) * 100)
        if len(log_returns) > 1
        else None
    )
    return {
        "return_pct": round((last / first - 1.0) * 100, 2),
        "max_drawdown_pct": round(drawdown * 100, 2),
        "annualized_vol_pct": round(vol, 2) if vol is not None else None,
        "trading_days": int(len(window)),
    }


def overlay_events(
    close: pd.Series,
    events: tuple[MarketEvent, ...] = EVENTS,
) -> dict:
    """Overlay the historical event timeline on one ticker's close series.

    `close` is a date-indexed price series (the `close` column of a processed
    history frame). For every event, the slice of `close` inside the event's
    date range yields the stock's realised return, worst drawdown and
    annualised volatility over that window.

    Events are returned newest-first and *all* of them are returned, including
    those entirely outside the price history — see the module docstring for why
    omitting them would misrepresent the record.
    """
    if close is None or len(close.dropna()) == 0:
        raise ValueError("close series is empty — cannot overlay events")

    close = close.dropna()
    index = pd.DatetimeIndex(close.index)
    # tz-naive throughout: the preprocessor already strips tz, and comparing a
    # tz-aware index against a naive Timestamp raises rather than coercing.
    if index.tz is not None:
        index = index.tz_localize(None)
        close = pd.Series(close.to_numpy(), index=index)

    history_start, history_end = index[0], index[-1]

    rows = []
    for event in events:
        start = pd.Timestamp(event.start)
        end = pd.Timestamp(event.end) if event.end else history_end
        window = close.loc[(index >= start) & (index <= end)]

        row = asdict(event)
        row["sources"] = list(event.sources)
        row["ongoing"] = event.end is None

        if len(window) < MIN_BARS:
            rows.append({
                **row,
                "coverage": "none",
                "observed_start": None,
                "observed_end": None,
                "return_pct": None,
                "max_drawdown_pct": None,
                "annualized_vol_pct": None,
                "trading_days": int(len(window)),
            })
            continue

        # "full" only when the stock was already trading when the event began.
        # An ongoing event is full whenever the stock predates its start —
        # there is no future data anyone could be missing.
        rows.append({
            **row,
            "coverage": "full" if history_start <= start else "partial",
            "observed_start": window.index[0].strftime("%Y-%m-%d"),
            "observed_end": window.index[-1].strftime("%Y-%m-%d"),
            **_stats(window),
        })

    rows.sort(key=lambda r: r["start"], reverse=True)

    covered = sum(1 for r in rows if r["coverage"] != "none")
    return {
        "price_history_start": history_start.strftime("%Y-%m-%d"),
        "price_history_end": history_end.strftime("%Y-%m-%d"),
        "events_total": len(rows),
        "events_covered": covered,
        # Stated in the payload, not left to be inferred from the panel's
        # placement — see the module docstring for the two reasons.
        "contributes_to_risk_score": False,
        "events": rows,
        "sources": SOURCES,
    }
