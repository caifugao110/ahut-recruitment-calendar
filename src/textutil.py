"""
textutil.py — 简章原文的展示层清洗。

招聘简章正文里常带条目序号（1. / 2、/ （3）/ ① / 1.1）与装饰性符号（？ ● ★ …）。
这些在原文语境里没问题，但被单独摘出来展示时只会让人困惑：
「明明只有一条却写着 2.」「前面挂着一个问号」。

这里统一在展示前剥掉行首的这类前缀，**只动行首**，不碰正文里的标点与内容。
薪资待遇（generate.extract_salary）与匹配依据（matcher.evidence）共用这一份规则。
"""

from __future__ import annotations

import re

# 1.1 / 2.3.1 这类多级序号：先于单级判断，否则只会剥掉「1.」而留下「1 运营」。
# 结尾的负向前瞻避免误伤「12.5万元」「1.5万」这类正常的数字写法。
_LEAD_MULTI = re.compile(
    r"^[（(【\[]?\s*\d{1,2}(?:\s*[.．]\s*\d{1,2})+\s*[)）】\].、,，:：]?\s*(?![万元千KkWw])"
)
# 1. / 2、 / （3） 这类单级序号
_LEAD_NUM = re.compile(r"^[（(【\[]?\s*\d{1,2}\s*[)）】\].、,，:：]\s*")
# ①②③ 这类带圈数字
_LEAD_CIRCLED = re.compile(r"^[①-⑳⒈-⒛]\s*")
# ？ ● ★ ◆ ■ ▪ · — 这类装饰性项目符号（原文里的图标被爬成问号是常见现象）
_LEAD_MARK = re.compile(r"^[？?＊*★☆◆◇■□▪▫•·※※▎▏\-–—－~～>》]+\s*")


def clean_leading_marks(text: str) -> str:
    """剥掉行首的序号与装饰符号；没有这类前缀时原样返回。"""
    s = (text or "").strip()
    for _ in range(5):
        before = s
        s = _LEAD_MULTI.sub("", s)
        s = _LEAD_NUM.sub("", s)
        s = _LEAD_CIRCLED.sub("", s)
        s = _LEAD_MARK.sub("", s)
        s = s.strip()
        if s == before:
            break
    return s
