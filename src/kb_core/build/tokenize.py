"""Pre-tokenisation shared by indexing and queries (port of kb pipeline/tokenize.py; design §4.2).

Chinese and English are segmented with jieba plus the domain pack dictionary; words are lowercased; numbers with
thousands separators are kept whole and also emitted without commas (a query for 42,174 or 42174 both hit); tokens
without a letter or digit are dropped. ES only splits the result on whitespace (analyzer kb_ws), so no ES plugin is
needed.
"""

import logging
import re
import unicodedata
import warnings
from functools import cache

from kb_core.domains import dictionary

with warnings.catch_warnings():
    warnings.simplefilter("ignore", SyntaxWarning)  # jieba 0.42.1 has invalid escapes in its regexes
    import jieba

_GROUPED_NUMBER = re.compile(r"(?<![\d.])\d{1,3}(?:,\d{3})+(?:\.\d+)?%?")


@cache
def _tokenizer(domain: str) -> "jieba.Tokenizer":
    jieba.setLogLevel(logging.WARNING)
    tk = jieba.Tokenizer()
    tk.load_userdict(str(dictionary(domain)))
    return tk


def _keep(token: str) -> bool:
    return any(unicodedata.category(c)[0] in "LN" for c in token)


def _cut(text: str, domain: str) -> list[str]:
    return [t.strip().lower() for t in _tokenizer(domain).cut(text) if _keep(t)]


def tokens(text: str, domain: str) -> list[str]:
    out, pos = [], 0
    for m in _GROUPED_NUMBER.finditer(text):
        out += _cut(text[pos:m.start()], domain)
        out += [m.group(), m.group().replace(",", "")]
        pos = m.end()
    return out + _cut(text[pos:], domain)


def to_field(text: str, domain: str) -> str:
    return " ".join(tokens(text or "", domain))
