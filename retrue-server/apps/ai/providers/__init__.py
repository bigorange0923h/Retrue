"""AI provider 抽象层。

业务层不直接依赖具体模型供应商，统一通过 AI Service 调用 provider。
当前使用 MockProvider 提供确定性的解析结果，待真实服务商确定后替换。
"""
