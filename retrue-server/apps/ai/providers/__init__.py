"""AI provider 抽象层。

业务层不直接依赖具体模型供应商，统一通过 factory.get_provider() 调用 provider。
provider 通过配置（settings.AI_PROVIDER）选择，见 factory.PROVIDER_REGISTRY。
当前内置：
- MockProvider：本地确定性规则解析，用于无外部服务的开发。
- DeepSeekProvider：DeepSeek（OpenAI 兼容协议），需配置 AI_API_KEY。
"""
