# PageIndex RAG Agent 项目记忆

## 项目架构
- **技术栈**: Electron + React (Vite/TypeScript/TailwindCSS) + Python FastAPI 后端
- **端口**: 前端 Vite dev 5173, 后端 FastAPI 8765, Electron 加载 localhost:5173
- **启动**: `start-dev.bat` (前后端) / `start-desktop.bat` (Electron)

## 关键路径
- 前端: `frontend/src/`
- 后端: `backend/server.py` (RAG引擎) | `backend/pipeline_service.py` (上传管线)
- 知识库: `resource/` (基础索引) | `resource_enhanced/` (增强索引含图片/表格)
- MinerU 图片: `C:\Work\day1_PDF2MD\output\{doc}/images/`
- 图片API: `/api/images/{dir_name}/{img_path}` (通过 StaticFiles 挂载)

## 增强版索引 (resource_enhanced)
- 节点结构含 `images[]` (path/caption/source) 和 `tables[]` (html/caption/source/page_idx)
- 顶层含 `_mineru_dir` 字段指向 MinerU 输出目录
- 后端 RAGEngine 自动检测并优先使用增强版索引

## 检索流水线
1. _collect_snippets: 收集所有文档结构片段
2. _locate_with_llm: LLM 定位相关节点
3. _extract_details: n-gram 匹配 + 评分排序提取章节详情（含图片/表格）
4. SSE 流式生成: token → sources → done

## 已修复的关键 Bug
- SSE 解析: Windows CRLF 需用 `\r?\n\r?\n` 分割
- 深层节点检索: 两遍收集+评分排序，图片caption匹配
- KaTeX: `\tag{}` 清理 + throwOnError: false
- 模型切换: MODEL_CONFIG 字典为每模型独立 api_key/api_base
