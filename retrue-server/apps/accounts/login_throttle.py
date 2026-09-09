"""登录失败限流：基于数据库缓存的账号/IP 双维度计数。

不依赖单进程内存：计数写入 Django DatabaseCache（PostgreSQL 后端），
多进程/多 worker 共享。达到阈值返回 429；缓存窗口过期后自动恢复，
不提供“永久锁号”语义，避免被用于恶意锁定账号。

实现注意：
- 计数器只在“本次确实认证失败”时递增，成功登录即清除本人/本 IP 计数，
  避免合法用户被自己此前的尝试困住。
- 键不含明文密码、不记原始消息，只含用户名与脱敏后的访问方标识。
"""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache


def _username_key(username: str) -> str:
    """构造按用户名计数的缓存键（规范化小写，避免大小写绕过）。"""
    return f"login_fail:user:{str(username or '').strip().lower()}"


def _ip_key(ip: str) -> str:
    """构造按来源 IP 计数的缓存键。"""
    return f"login_fail:ip:{ip or ''}"


def _window() -> int:
    """读取失败计数窗口（秒）。"""
    return int(getattr(settings, "LOGIN_THROTTLE_WINDOW_SECONDS", 900))


def _incr(key: str) -> int:
    """原子递增计数器，返回当前计数。"""
    try:
        return int(cache.incr(key))
    except ValueError:
        # 键不存在：写入 1 并设置窗口过期
        cache.set(key, 1, timeout=_window())
        return 1


def user_failures(username: str) -> int:
    """读取某用户名当前失败计数。"""
    return int(cache.get(_username_key(username), 0))


def ip_failures(ip: str) -> int:
    """读取某 IP 当前失败计数。"""
    return int(cache.get(_ip_key(ip), 0))


def record_failure(username: str, ip: str) -> None:
    """记录一次登录失败，递增账号与 IP 两个维度计数。"""
    _incr(_username_key(username))
    _incr(_ip_key(ip))


def clear_failures(username: str, ip: str) -> None:
    """登录成功后清除该账号与该 IP 的失败计数。"""
    cache.delete(_username_key(username))
    cache.delete(_ip_key(ip))


def is_blocked(username: str, ip: str) -> bool:
    """判断账号或 IP 是否已达阈值而应拒绝（返回 429）。"""
    user_max = int(getattr(settings, "LOGIN_THROTTLE_MAX_FAILURES", 5))
    ip_max = int(getattr(settings, "LOGIN_THROTTLE_IP_MAX_FAILURES", 20))
    return user_failures(username) >= user_max or ip_failures(ip) >= ip_max
