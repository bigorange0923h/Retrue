"""AI provider 抽象层。

业务层不直接依赖具体模型供应商，统一通过 factory.get_provider() 调用 provider。
provider 通过配置（settings.AI_PROVIDER）选择，见 factory.PROVIDER_REGISTRY。
当前内置 MockProvider（确定性规则解析），真实服务商（openai/dashscope）为预留，
接入时实现对应 provider 类并注册到 PROVIDER_REGISTRY。
"""
