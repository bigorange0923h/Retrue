"""复用现有健康接口检查 HTTP 与业务状态，不连接数据库或调用模型。"""

import json
from urllib.request import ProxyHandler, build_opener


def main() -> None:
    """探测容器自身，响应异常时以非零状态退出。"""
    opener = build_opener(ProxyHandler({}))
    with opener.open("http://127.0.0.1:8000/api/health/", timeout=4) as response:
        payload = json.load(response)
        if response.status != 200 or payload.get("code") != 200 or payload.get("data", {}).get("status") != "ok":
            raise SystemExit("健康检查失败")


if __name__ == "__main__":
    main()
