# Retrue Web

Retrue 的 Vue 前端，提供今日工作台、客户档案、课程安排、训练记录和统一 AI 助理界面。产品介绍、运行截图与完整启动步骤见[根目录 README](../README.md)。

## 技术与职责

- Vue 3、TypeScript、Vite、Pinia、Element Plus。
- 通过 REST API 读写业务数据，通过 SSE 展示 AI 任务进度。
- AI 草稿允许人工核对后确认；正式写入、客户归属、课程完成和课时消耗由后端服务校验。
- 桌面与移动端页面共用业务接口；构建通过不代表手机交互已验收。

## 本地运行

使用 Node.js 24，在当前目录执行：

```powershell
npm ci
npm run dev
```

先启动 Django 后端。开发服务器使用 `http://localhost:5173`，`/api` 代理到 `http://127.0.0.1:8000`，Session Cookie 保持同源。

## 检查与构建

```powershell
npm test
npm run build
```

`build` 包含 TypeScript 类型检查和 Vite 生产构建。生产资源默认使用 `/retrue/` 路径，可通过 `VITE_APP_BASE_PATH` 配置。完整部署见[部署说明](../DEPLOY.md)。

开发约定见[前端规范](../docs/frontend-development-standards.md)，独立前后端验证见[本地开发说明](../docs/local-development.md)。
