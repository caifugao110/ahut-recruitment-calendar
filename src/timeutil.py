"""
timeutil.py —— 统一按北京时间（UTC+8）取「现在」和「今天」。

为什么需要它：GitHub Actions 与腾讯云函数的运行环境默认是 UTC。
直接用 dt.datetime.now() / dt.date.today() 会让：
  - 页面上的「数据更新」时间比北京时间慢 8 小时（18:02 显示成 10:02）
  - 定时任务在 UTC 18:00（北京次日 02:00）跑时，「今天」差一天，
    进而把过期状态（expired / today / upcoming）算错

所有面向用户展示或决定业务状态的时间，一律走这里的 cn_now() / cn_today()。
"""

from __future__ import annotations

import datetime as dt

CN_TZ = dt.timezone(dt.timedelta(hours=8))


def cn_now() -> dt.datetime:
    """当前北京时间（带 +08:00 时区信息）。"""
    return dt.datetime.now(CN_TZ)


def cn_today() -> dt.date:
    """北京时间的「今天」。"""
    return cn_now().date()
