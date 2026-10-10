# 本地开发补充说明

首次启动、环境变量、mock 模型配置和演示数据入口见[README](../README.md)。以下命令在专用开发环境使用，不作为公开体验服务的初始化方案。

## 辅助记忆任务

普通回复中的记忆候选评估会持久排队。在 `retrue-server` 目录执行：

```powershell
.venv\Scripts\python.exe manage.py process_auxiliary_tasks --limit 20
```

部署时需配置定时执行。该命令只生成待审核候选，同一来源不重复排队，失败最多重试三次。未配置消费命令时普通对话仍可回复，但辅助候选不会自动生成。

## 课程目录初始化

课程目录通过 [seed_rehab_catalog.sql](database/seed_rehab_catalog.sql) 初始化。执行前查阅[数据库约定](database/README.md)并确认目标用户名；账号缺失或同账号目录重名会报错回滚，锁等待最多 10 秒。脚本不更新已有目录项，不清理历史数据。

## 独立验证

前端在 `retrue-web` 下使用 Node.js 24 执行 `npm test` 和 `npm run build`。

仓库根目录的 `scripts/verify.ps1` 创建随机临时 pgvector 容器，在独立测试库串行运行后端检查及全部测试，再测试和构建前端，最后清理该容器。需要 Docker、现有项目虚拟环境和已安装的前端依赖；不连接业务数据库。

在仓库根目录执行：

```powershell
.\scripts\verify.ps1 -PythonPath "$PWD\retrue-server\.venv\Scripts\python.exe"
```

检查结果应标明运行日期、代码版本和环境。Mock 测试不证明真实模型准确率、延迟或生产容量；前端构建不证明浏览器和手机交互验收。
