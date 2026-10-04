"""从已验证的项目虚拟环境生成后端版本锁，不执行安装或读取 pip 配置。"""

from collections import deque
from importlib.metadata import distribution
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def main() -> None:
    """锁定直接和传递依赖；缺包/版本不符直接失败，避免生成部分锁。"""
    server = Path(__file__).resolve().parents[1] / "retrue-server"
    roots = [
        Requirement(line.strip())
        for line in (server / "requirements.txt").read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    pending = deque(roots)
    seen = set()
    versions = {}
    while pending:
        requirement = pending.popleft()
        name = canonicalize_name(requirement.name)
        key = (name, tuple(sorted(requirement.extras)))
        if key in seen:
            continue
        seen.add(key)
        installed = distribution(name)
        if requirement.specifier and installed.version not in requirement.specifier:
            raise RuntimeError(f"{name} 已安装版本不满足 requirements.txt，停止生成锁")
        versions[name] = installed.version
        for raw in installed.requires or []:
            dependency = Requirement(raw)
            environments = []
            for system, platform in (("Linux", "linux"), ("Windows", "win32")):
                for extra in {"", *requirement.extras}:
                    environment = default_environment()
                    environment.update(platform_system=system, sys_platform=platform, extra=extra)
                    environments.append(environment)
            if dependency.marker is None or any(dependency.marker.evaluate(env) for env in environments):
                pending.append(dependency)
    output = server / "requirements-lock.txt"
    output.write_text(
        "# 从项目 Python 3.14 虚拟环境生成；直接及传递依赖固定版本。\n"
        "# 修改 requirements.txt 后，在验证过的环境中重新运行 scripts/lock_backend_dependencies.py。\n"
        + "\n".join(f"{name}=={version}" for name, version in sorted(versions.items())) + "\n",
        encoding="utf-8",
    )
    print(f"已锁定 {len(versions)} 个后端运行依赖")


if __name__ == "__main__":
    main()
