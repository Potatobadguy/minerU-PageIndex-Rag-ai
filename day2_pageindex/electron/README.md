# Electron 桌面壳（pageindex-rag-agent-desktop）

本目录是 Electron 主进程壳，负责：
1. 启动 Python 后端子进程（`backend/server.py`）
2. 加载前端（开发：`http://127.0.0.1:5173`；打包：`../frontend/dist/index.html`）
3. 应用退出时清理后端进程

## 开发模式

在项目根目录的 `frontend/` 下运行（推荐，前端热更新）：

```bash
cd frontend
npm install
npm run electron:dev
```

这会同时启动：
- Vite dev server（前端，5173）
- Electron 主进程（加载前端 dev URL，并启动 Python 后端）

> 要求本机已安装 Python，且 `PageIndex/.env` 配置好 `OPENAI_API_KEY` 与 `OPENAI_API_BASE`。

## 打包模式

```bash
cd frontend
npm install
npm run electron:build
```

打包产物在 `frontend/dist_electron/` 下。打包时会把 `backend/` 作为 extraResources 一并放入。

## 注意事项

- Windows 下后端进程通过 `taskkill /f /t` 终止整个进程树。
- 后端默认监听 `127.0.0.1:8765`，仅本机访问。
- 若系统 `python` 命令不可用，可设置环境变量 `PYTHON_CMD=python3` 或 `PYTHON_CMD=C:\path\to\python.exe`。
