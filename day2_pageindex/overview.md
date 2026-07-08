# PageIndex RAG Agent —— 全栈实现说明

## 概述

将原 `gui.py`（Tkinter 简陋界面）重构为现代化的 **PageIndex RAG Agent**，基于 PageIndex 多文档检索能力，提供：

- 📊 支持 Markdown 表格渲染
- ➗ 支持 LaTeX 数学公式渲染（KaTeX）
- 📱 响应式设计（桌面/平板/手机）
- 🔍 检索过程可视化（让用户看到 Agent 思考链路）
- ⚡ SSE 流式输出（token 级实时渲染，可中断）
- 🖥️ Electron 桌面应用（双击即用）

## 架构

```
┌─────────────────────────────────────────────────────┐
│                Electron 桌面壳                        │
│  (electron/main.js)                                  │
│   ├─ 启动 Python 后端子进程                          │
│   └─ 加载前端 (dev URL / dist/index.html)            │
└──────────────┬──────────────────────────────────────┘
               │ HTTP + SSE
┌──────────────▼──────────────────────────────────────┐
│           FastAPI 后端 (backend/server.py)            │
│   ├─ /api/kb-info      知识库元信息                  │
│   ├─ /api/models       模型列表                      │
│   ├─ /api/chat/stream  SSE 流式问答                  │
│   │   ├─ Step1: 收集知识库结构片段                   │
│   │   ├─ Step2: LLM 定位相关章节                     │
│   │   ├─ Step3: 提取章节摘要作为上下文               │
│   │   └─ Step4: litellm 流式生成答案                 │
│   └─ 复用 PageIndex 库 + llm_completion              │
└──────────────┬──────────────────────────────────────┘
               │ sys.path
┌──────────────▼──────────────────────────────────────┐
│       PageIndex 库 (PageIndex/pageindex/)            │
│   RAGEngine → PageIndexClient → llm_completion       │
└─────────────────────────────────────────────────────┘
```

## 技术选型

| 层级 | 技术 | 理由 |
|------|------|------|
| 前端框架 | React 18 + TypeScript | 生态成熟，类型安全 |
| 构建工具 | Vite 5 | 启动快、HMR 体验好 |
| 样式 | TailwindCSS 3 | 原子化、暗色主题易维护 |
| Markdown | react-markdown + remark-gfm | 支持 GFM 表格 |
| 公式 | KaTeX + remark-math + rehype-katex | 比 MathJax 快、渲染稳定 |
| 后端 | FastAPI + sse-starlette | 原生 async + SSE 支持 |
| LLM 调用 | litellm (stream=True) | 复用 PageIndex 已有依赖 |
| 桌面壳 | Electron 33 | 跨平台、可加载本地 Python 子进程 |
| 一键启动 | Windows .bat 脚本 | 双击即用，自动 build + 拉起后端 |

## 目录结构

```
day2_pageindex/
├── gui.py                     # 原 Tkinter 界面（保留，未改动）
├── backend/                   # ★ 新增：FastAPI 后端
│   ├── server.py              # 主服务（SSE 流式 + 检索过程）
│   └── requirements.txt
├── frontend/                  # ★ 新增：React 前端
│   ├── src/
│   │   ├── App.tsx            # 主应用
│   │   ├── api.ts             # API + SSE 客户端
│   │   └── components/        # 8 个组件
│   ├── package.json
│   └── README.md
├── electron/                  # ★ 新增：Electron 壳
│   ├── main.js                # 主进程
│   └── README.md
├── overview.md                # 本文档
├── PageIndex/                 # 既有 PageIndex 库（未改动）
└── resource/                  # 既有知识库 JSON（未改动）
```

## 启动方式

### 方式一：Web 开发模式（推荐调试）

```bash
# 终端 1：启动后端
cd C:\Work\day2_pageindex
py -3.12 backend/server.py

# 终端 2：启动前端
cd C:\Work\day2_pageindex\frontend
npm install
npm run dev
# 浏览器访问 http://127.0.0.1:5173
```

### 方式二：一键打开桌面客户端（推荐，双击即用）

在项目根目录双击 `start-desktop.bat`，或在 PowerShell/CMD 运行：

```bash
cd C:\Work\day2_pageindex
.\start-desktop.bat
```

脚本会自动：① 首次运行时 build 前端 → ② 检查 electron 依赖 → ③ 启动桌面客户端（含 Python 后端）。
之后每次双击秒开，无需手动起任何服务。关闭窗口即退出，后端自动停止。

### 方式三：Electron 开发模式（热更新）

```bash
cd C:\Work\day2_pageindex\frontend
npm install
npm run electron:dev
# 自动启动 Vite + Electron + Python 后端
```

或双击项目根目录的 `start-dev.bat`。

### 方式四：打包桌面应用

```bash
cd C:\Work\day2_pageindex\frontend
npm run electron:build
# 产物在 frontend/dist_electron/
```

## 已验证

- ✅ 后端启动正常，`/api/health` 与 `/api/kb-info` 返回正确（2 篇文档 / 171 节点）
- ✅ SSE 流式全链路打通：step → sources → token → done 事件顺序正确
- ✅ 检索过程分步上报：collect(1ms) → locate(10435ms) → extract(1ms) → generate
- ✅ 引用来源正确提取（28 个章节摘要）
- ✅ 最终答案含 Markdown 结构、分点列表、文档章节引用
- ✅ 前端 TypeScript 编译通过，Vite 构建成功（590KB，含 KaTeX 字体）
- ✅ 模型切换接口正常

## 关键设计决策

1. **保留 `gui.py` 不动**：用户偏好在新增逻辑到独立目录，原 Tkinter 界面作为 fallback 保留。
2. **后端复用 PageIndex 库**：通过 `sys.path.insert` 引入 `PageIndex/`，复用 `PageIndexClient` 与 `llm_completion`，与 `gui.py` 同款做法。
3. **SSE 而非 WebSocket**：SSE 单向流更适合"问答流式输出"场景，且 FastAPI + sse-starlette 实现简洁；前端用 fetch + ReadableStream 手动解析（绕开 EventSource 不支持 POST 的限制）。
4. **检索过程可见**：用户明确要求展示检索过程，后端在每个阶段上报 `step` 事件，前端用时间线组件可视化（扫描 → 定位 → 提取 → 生成），并显示命中文档标签与各阶段耗时。
5. **litellm streaming 降级**：流式失败时自动降级为非流式 `llm_completion`，保证可用性。
6. **公式用 KaTeX 而非 MathJax**：KaTeX 同步渲染、体积小、与 react-markdown 集成成熟。
7. **暗色主题**：符合开发者工具审美，且 IDE 主题为 dark。
8. **响应式**：TailwindCSS 断点 sm/md/lg，消息列表最大宽度 max-w-4xl，移动端单列、桌面端舒适阅读宽度。

## 后续可扩展

- [ ] 多轮对话上下文（当前每条 query 独立）
- [ ] 文档上传与索引（调用 `PageIndexClient.index()`）
- [ ] 答案导出为 Markdown / PDF
- [ ] 暗色/亮色主题切换
- [ ] 国际化（中英双语）
