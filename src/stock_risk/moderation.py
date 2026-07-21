"""Rule-based content screening for community posts.

Deliberately narrow: every pattern targets *how* something is said — an
imperative trading call, a contact-info solicitation, a slur — never *what*
is being discussed. Entity and event words (countries, politicians,
"election", "war", "sanctions", "Taiwan") are core risk-analysis vocabulary
("election uncertainty lifts volatility", "TSMC's geopolitical exposure")
and must never appear in these lists; blocking them would gut the platform's
main use case. Judgment-call content this can't catch mechanically
(political stance-taking, misinformation, subtle advice) is handled by the
user report + admin review flow instead, not by broader regexes.

English patterns use \b word boundaries so "sell now" never matches
"sell-off" or "oversold". Chinese has no word boundaries, so its patterns
are multi-character phrases specific enough not to occur inside legitimate
analysis prose (e.g. "建议买入" not bare "买入", which appears in factual
text like "买入压力").
"""

from __future__ import annotations

import re
from typing import Optional

# Category code -> compiled patterns. Codes are stable API strings: the
# frontend maps "moderation:<code>" 422 details onto localized messages.
_RULES: dict[str, list[re.Pattern]] = {
    "trading_directive": [
        re.compile(
            r"\b(?:"
            r"strong\s+(?:buy|sell)"
            r"|(?:buy|sell)\s+(?:now|immediately|today|asap)"
            r"|price\s+target"
            r"|target\s+price"
            r"|guaranteed\s+(?:profit|return|gain)s?"
            r"|(?:sure|risk[- ]free)\s+(?:profit|win|bet|thing)"
            r"|all[- ]in"
            r"|can'?t\s+lose"
            r"|to\s+the\s+moon"
            r"|get\s+in\s+(?:now|before)"
            r"|100%\s+(?:gain|return|profit)s?"
            r")\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"建议(?:买入|卖出|加仓|减仓|清仓|抄底|入手)"
            r"|(?:赶紧|快点|马上|抓紧)(?:买|卖|上车|入手)"
            r"|梭哈|满仓干|稳赚不赔|包赚|必涨|必跌"
            r"|一定(?:涨|跌)|目标价|带你(?:赚|飞)|跟(?:我|着)买"
        ),
    ],
    "solicitation": [
        re.compile(
            r"\b(?:"
            r"dm\s+me|pm\s+me|message\s+me|add\s+me\s+on"
            r"|join\s+my\s+(?:group|channel|discord|telegram|server)"
            r"|(?:telegram|whatsapp|discord)\s+group"
            r"|paid\s+(?:group|signals?|course)"
            r"|t\.me/|wa\.me/|onlyfans"
            r")\b",
            re.IGNORECASE,
        ),
        # Structured handle-sharing ("微信: xyz", "vx：abc123") — requires the
        # separator so a bare product mention ("微信支付业务") never matches.
        re.compile(r"(?:wechat|weixin|vx)\s*(?:id)?\s*[:：]\s*\S+", re.IGNORECASE),
        re.compile(
            r"加(?:我)?(?:微信|微|vx|v信|qq|群)"
            r"|进群|私聊我|私信我|付费群|收徒|代操盘|荐股群|约吗|约不约"
        ),
    ],
    "abuse": [
        # Small, high-confidence slur/abuse list only — anything softer or
        # context-dependent goes through the report flow, not a regex.
        re.compile(r"\b(?:nigger|faggot|retards?|cunts?)\b", re.IGNORECASE),
        re.compile(r"操你妈|草泥马|傻逼|煞笔|狗娘养|去死吧|滚你妈"),
    ],
}


def check_post_body(body: str) -> Optional[str]:
    """The violated category code, or None if the text passes every rule."""
    for category, patterns in _RULES.items():
        for pattern in patterns:
            if pattern.search(body):
                return category
    return None
