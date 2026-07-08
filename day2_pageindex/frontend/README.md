# PageIndex RAG Agent 前端

基于 React 18 + Vite + TypeScript + TailwindCSS 的 PageIndex 多文档 RAG Agent 前端。

## 特性

- 🎨 **暗色科技风 UI**：渐变品牌色、流畅动画、玻璃拟态
- 📊 **表格 & 公式渲染**：remark-gfm 支持 GFM 表格，KaTeX 支持 LaTeX 公式（`$...$` 行内、`$$...$$` 块级）
- 🔍 **检索过程可视化**：分步展示 Agent 思考链路（扫描 → 定位 → 提取 → 生成），含命中文档标签与耗时
- 📌 **引用来源面板**：每条 AI 回答附带可折叠的引用章节列表
- ⚡ **SSE 流式输出**：token 级实时渲染，可中断（停止按钮）
- 📱 **响应式设计**：适配桌面 / 平板 / 手机
- ♿ **无障碍支持**：ARIA 标签、键盘导航、`prefers-reduced-motion` 适配
- 🤖 **多模型切换**：支持 deepseek-v4-pro / deepseek-v3 / gpt-4.1 / gpt-4o / claude-sonnet-4-6

## 目录结构

```
frontend/
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── tsconfig.json
├── index.html
└── src/
    ├── main.tsx                    # 入口
    ├── App.tsx                     # 主应用（状态管理 + 消息流）
    ├── api.ts                      # 后端 API 封装 + SSE 客户端
    ├── index.css                   # 全局样式 + Markdown 主题
    ├── vite-env.d.ts               # Vite 环境类型
    └── components/
        ├── Header.tsx              # 顶栏（标题 + 模型选择 + 连接状态）
        ├── KbInfoBar.tsx           # 知识库信息栏（可折叠文档列表）
        ├── MessageBubble.tsx       # 消息气泡
        ├── MarkdownView.tsx        # Markdown 渲染（表格 + 公式）
        ├── RetrievalSteps.tsx      # 检索过程时间线
        ├── SourcesPanel.tsx        # 引用来源面板
        └── InputBar.tsx            # 输入框（自适应高度 + 快捷键）
```

## 快速开始

### 1. 启动后端

在项目根目录 `C:\Work\day2_pageindex`：

```bash
py -3.12 backend/server.py
```

后端默认监听 `http://127.0.0.1:8765`。

### 2. 启动前端（开发模式）

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。

### 3. 桌面应用模式（Electron）

```bash
cd frontend
npm run electron:dev
```

会同时启动 Vite + Electron，并自动拉起 Python 后端。

## 构建生产包

```bash
cd frontend
npm run build      # 产物在 dist/
npm run electron:build  # 打包桌面应用
```

## 后端接口

| 方法   | 路径                  | 说明                            |
| ------ | --------------------- | ------------------------------- |
| GET    | `/api/health`         | 健康检查                        |
| GET    | `/api/kb-info`        | 知识库元信息                    |
| GET    | `/api/models`         | 可用模型列表与当前模型          |
| POST   | `/api/model/switch`   | 切换模型                        |
| POST   | `/api/chat/stream`    | SSE 流式问答（含检索过程）      |

### SSE 事件类型

| 事件     | data 字段                                       | 说明                |
| -------- | ----------------------------------------------- | ------------------- |
| `step`   | `{stage, message, duration_ms?, hit_docs?}`     | 检索过程进度        |
| `sources`| `{sources: [{doc_name, section, summary}]}`     | 引用来源列表        |
| `token`  | `{delta}`                                       | 答案 token 流       |
| `done`   | `{answer, total_sources}`                       | 生成完成            |
| `error`  | `{message}`                                     | 错误                |

## 配置

- 后端地址默认 `http://127.0.0.1:8765`，可通过环境变量 `VITE_API_BASE` 覆盖（在 `frontend/.env` 中设置）。
- 模型列表在 `backend/server.py` 的 `MODEL_OPTIONS` 中维护。

## 键盘快捷键

| 快捷键            | 功能       |
| ----------------- | ---------- |
| `Enter`           | 发送消息   |
| `Shift + Enter`   | 换行       |
| `Ctrl/Cmd + Enter`| 发送消息   |
