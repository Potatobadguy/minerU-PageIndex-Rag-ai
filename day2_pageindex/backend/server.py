"""
PageIndex RAG Agent - 后端 API 服务器
基于 FastAPI + SSE 流式输出，封装 PageIndex 多文档检索能力。

启动方式:
    python backend/server.py
或:
    uvicorn backend.server:app --host 127.0.0.1 --port 8765

接口:
    GET  /api/kb-info          知识库元信息
    GET  /api/models           可用模型列表
    POST /api/chat/stream      SSE 流式问答（含检索过程）
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import AsyncIterator

# 把 PageIndex 包加入 sys.path（gui.py 同款做法）
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "PageIndex"))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / "PageIndex" / ".env")

import litellm
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# 强制绕过系统代理（避免 WinError 10061 Connection refused）
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

from pageindex import PageIndexClient
from pageindex.utils import llm_completion

# ========== 配置 ==========
RESOURCE_DIR = BASE_DIR / "resource"
MAX_STRUCTURE_PREVIEW = 400
MAX_SNIPPETS = 500
MAX_NODES_PER_DOC = 30
MAX_CONTEXT_CHARS = 8000
MAX_RELEVANT_NODE_CHARS = 2500

# 模型配置表：每个模型独立指定 API-Key 和 Base URL
# 配置中的 api_key / api_base 可直接写值，也可写 "env:变量名" 从 .env 读取
MODEL_CONFIG: dict[str, dict] = {
    "openai/deepseek-v4-pro": {
        "label": "DeepSeek V4 Pro",
        "api_key":  os.getenv("DEEPSEEK_API_KEY",  os.getenv("OPENAI_API_KEY", "")),
        "api_base": os.getenv("DEEPSEEK_API_BASE", os.getenv("OPENAI_API_BASE", "")),
    },
    "openai/deepseek-v4-flash": {
        "label": "DeepSeek V4 Flash",
        "api_key":  os.getenv("DEEPSEEK_API_KEY",  os.getenv("OPENAI_API_KEY", "")),
        "api_base": os.getenv("DEEPSEEK_API_BASE", os.getenv("OPENAI_API_BASE", "")),
    }, "openai/LongCat-2.0": {
        "label": "LongCat-2.0",
        "api_key":  os.getenv("LONGCAT_API_KEY",  os.getenv("OPENAI_API_KEY", "")),
        "api_base": os.getenv("LONGCAT_API_BASE", os.getenv("OPENAI_API_BASE", "")),
    },
    
}
MODEL_OPTIONS = list(MODEL_CONFIG.keys())


def get_model_config(model_name: str) -> dict:
    """获取指定模型的 {api_key, api_base} 配置，找不到则回退到默认环境变量"""
    return MODEL_CONFIG.get(model_name, {
        "api_key":  os.getenv("OPENAI_API_KEY", ""),
        "api_base": os.getenv("OPENAI_API_BASE", ""),
    })

# 关闭 litellm 啰嗦日志
litellm.suppress_debug_info = True
import logging
logging.getLogger("litellm").setLevel(logging.WARNING)

app = FastAPI(title="PageIndex RAG Agent", version="1.0.0")

# 允许前端跨域（Electron / dev server 都需要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MinerU 图片静态文件服务（从 day1_PDF2MD/output 提供增强版索引中的图片）
MINERU_IMAGE_DIR = BASE_DIR.parent / "day1_PDF2MD" / "output"
if MINERU_IMAGE_DIR.exists():
    app.mount("/api/images", StaticFiles(directory=str(MINERU_IMAGE_DIR)), name="images")
    print(f"[Init] MinerU 图片服务已挂载: /api/images -> {MINERU_IMAGE_DIR}")
else:
    print(f"[Init] 警告: MinerU 图片目录不存在: {MINERU_IMAGE_DIR}")


# ========== 工具函数 ==========
def flatten_structure(structure: list) -> list[dict]:
    result: list[dict] = []
    for node in structure:
        result.append(node)
        if node.get("nodes"):
            result.extend(flatten_structure(node["nodes"]))
    return result


def _build_media_context(images: list, tables: list, doc_name: str) -> list[str]:
    """将节点的图片/表格信息转换为 LLM 上下文字符串"""
    lines = []
    for img in images:
        cap = img.get("caption", "")
        if cap:
            lines.append(f"[附图: {cap}]")
        else:
            lines.append(f"[附图]")
    for tbl in tables:
        cap = tbl.get("caption", "")
        html = tbl.get("html", "")
        if cap:
            lines.append(f"[表格: {cap}]\n{html}")
        elif html:
            lines.append(f"[表格]\n{html}")
    return lines


# ========== RAG 引擎（单例） ==========
class RAGEngine:
    def __init__(self, resource_dir: Path, model: str | None = None):
        self.resource_dir = resource_dir
        self.kb_docs: list[dict] = []
        self.client: PageIndexClient | None = None
        self._mineru_dirs: dict[str, str] = {}  # doc_name → mineru输出目录路径
        self._enhanced_available = False
        self.reload(model=model)

    def reload(self, resource_dir: Path | None = None, model: str | None = None):
        if resource_dir:
            self.resource_dir = resource_dir
        self.client = PageIndexClient(retrieve_model=model)
        self.kb_docs = []
        self._raw_structures: dict[str, list] = {}
        self._mineru_dirs: dict[str, str] = {}

        # 优先加载增强版资源
        enhanced_dir = self.resource_dir.parent / "resource_enhanced"
        if enhanced_dir.exists() and list(enhanced_dir.glob("*_enhanced.json")):
            print("[RAGEngine] 使用增强版索引 (含图片/表格)")
            self._enhanced_available = True
            load_dir = enhanced_dir
        else:
            print("[RAGEngine] 使用基础版索引 (纯文本)")
            self._enhanced_available = False
            load_dir = self.resource_dir

        for fname in sorted(os.listdir(load_dir)):
            if not fname.endswith(".json"):
                continue
            fpath = load_dir / fname
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            doc_id = str(uuid.uuid4())
            doc_name = data.get("doc_name", fname)
            doc_entry = {
                "id": doc_id,
                "type": "md",
                "path": str(fpath),
                "doc_name": doc_name,
                "doc_description": data.get("doc_description", ""),
                "line_count": data.get("line_count", 0),
                "structure": data.get("structure", []),
            }
            self.client.documents[doc_id] = doc_entry
            self.kb_docs.append({
                "doc_id": doc_id,
                "doc_name": doc_name,
                "doc_description": doc_entry.get("doc_description", ""),
                "line_count": doc_entry.get("line_count", 0),
                "path": str(fpath),
            })
            self._raw_structures[doc_name] = data.get("structure", [])

            # 记录 MinerU 输出目录（用于图片 HTTP 服务）
            mineru_dir = data.get("_mineru_dir", "")
            if mineru_dir and doc_name not in self._mineru_dirs:
                self._mineru_dirs[doc_name] = mineru_dir
        print(f"[RAGEngine] 已加载 {len(self.kb_docs)} 篇文档,"
              f" 增强索引={self._enhanced_available}")

    def get_kb_info(self) -> dict:
        return {
            "resource_dir": str(self.resource_dir),
            "doc_count": len(self.kb_docs),
            "documents": [
                {
                    "doc_name": d["doc_name"],
                    "doc_description": d.get("doc_description", ""),
                    "line_count": d.get("line_count", 0),
                }
                for d in self.kb_docs
            ],
        }

    def set_model(self, model: str):
        self.client.retrieve_model = model

    def get_model(self) -> str:
        return self.client.retrieve_model

    # ---- 检索过程（同步分步，每步通过 callback 上报进度） ----
    def _collect_snippets(self) -> list[dict]:
        """收集所有文档结构片段，按节点信息量排序（大节点优先），
        返回 [{doc_name, title, text_preview}]"""
        snippets = []
        for d in self.kb_docs:
            doc_id = d["doc_id"]
            doc_name = d["doc_name"]
            flat = flatten_structure(self.client.documents[doc_id]["structure"])
            for node in flat:
                text = (node.get("text", "") or "")
                text_preview = text[:MAX_STRUCTURE_PREVIEW]
                # 如果 text 被截断且节点有子节点，追加子节点标题
                # 这样 LLM 能看到这个大节点包含哪些子条文
                if len(text) > MAX_STRUCTURE_PREVIEW:
                    children = node.get("nodes", [])
                    if children:
                        child_titles = [c.get("title", "") for c in children[:8]]
                        child_titles = [t for t in child_titles if t]
                        if child_titles:
                            text_preview += f"\n[含子节点] " + " · ".join(child_titles[:8])
                snippets.append({
                    "doc_name": doc_name,
                    "title": node.get("title", ""),
                    "text_preview": text_preview,
                    "info_score": len(text) + len(node.get("nodes", [])) * 100,
                })
        # 按文档分组，组内按信息量排序（大节点优先）
        doc_groups: dict[str, list[dict]] = {}
        for s in snippets:
            doc_groups.setdefault(s["doc_name"], []).append(s)
        for group in doc_groups.values():
            group.sort(key=lambda x: x.pop("info_score", 0), reverse=True)
        # 保持文档原有顺序，合并排序后的各文档片段
        sorted_snippets: list[dict] = []
        for d in self.kb_docs:
            sorted_snippets.extend(doc_groups.get(d["doc_name"], []))
        return sorted_snippets

    def _locate_with_llm(self, query: str, snippets: list[dict]) -> str:
        """Step 1: 让 LLM 在结构片段中定位相关内容。
        均匀抽取各文档的片段，避免只看到前几本。"""
        # 将 snippets 按文档分组
        doc_groups: dict[str, list[dict]] = {}
        for s in snippets:
            doc_groups.setdefault(s["doc_name"], []).append(s)

        doc_order = list(doc_groups.keys())

        # 轮询抽取：确保每个文档都有公平的代表性
        balanced: list[dict] = []
        finished = set()
        idx = 0
        while len(balanced) < MAX_SNIPPETS and len(finished) < len(doc_order):
            doc_name = doc_order[idx % len(doc_order)]
            group = doc_groups[doc_name]
            gi = idx // len(doc_order)
            if gi < len(group):
                balanced.append(group[gi])
            else:
                finished.add(doc_name)
            idx += 1

        snippet_lines = []
        for s in balanced:
            snippet_lines.append(
                f"文档: {s['doc_name']} | 节点: {s['title']} | {s['text_preview']}"
            )
        snippets_text = "\n".join(snippet_lines)
        if len(snippets) > MAX_SNIPPETS:
            snippets_text += f"\n...（共 {len(snippets)} 个片段，已截断，{len(doc_order)} 篇文档均匀抽取）"

        prompt = f"""你是一个文档检索助手。根据用户问题，从以下文档片段中找出最相关的信息源。

用户问题: {query}

文档片段:
{snippets_text}

请分析并回答：
1. 哪些文档包含与用户问题最相关的信息？
2. 具体的章节编号和标题是什么？（请明确写出，如"第8.0.6条 导线舞动的振幅"）
3. 简要说明相关内容的要点。

如果片段中有对应内容，请直接引用。如果没有，请说明。"""
        cfg = get_model_config(self.client.retrieve_model)
        return litellm.completion(
            model=self.client.retrieve_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            api_key=cfg["api_key"],
            api_base=cfg["api_base"] or None,
        ).choices[0].message.content

    def _extract_details(self, locate_result: str, query: str) -> tuple[str, list[dict]]:
        """Step 2: 根据 Step 1 提到的文档和 query 关键词，提取章节详情。
        对于关键词匹配的节点，优先提取完整 text（而非压缩 summary）。
        返回 (detailed_context, sources)"""
        detailed_context = ""
        sources: list[dict] = []

        # ---- 1) 提取章节号（如 8.0.6, 3.2.1） ----
        # NOTE: 不用 \b 因为中文前后没有 word boundary
        section_nums: set[str] = set()
        for candidate in re.findall(r'(?:^|[^\w.])(\d+(?:\.\d+){1,3})(?=[^\w.]|$)', locate_result):
            section_nums.add(candidate)
        for candidate in re.findall(r'(?:^|[^\w.])(\d+(?:\.\d+){1,3})(?=[^\w.]|$)', query):
            section_nums.add(candidate)

        # ---- 2) 从 query 提取滑动 n-gram（2~4 字窗口） ----
        pure_cn = re.sub(r'[^\u4e00-\u9fff]', '', query)
        STOP_CHARS = set('的了着过是和也不就都吗呢吧')
        query_grams: set[str] = set()
        for n in (2, 3, 4):
            for i in range(len(pure_cn) - n + 1):
                gram = pure_cn[i:i + n]
                if gram not in query_grams and not all(c in STOP_CHARS for c in gram):
                    query_grams.add(gram)

        # ---- 2a) 提取数字关键词（如 3500, 10, 110）—— 用户常问具体数值 ----
        num_keywords: set[str] = set()
        for candidate in re.findall(r'\b\d{2,4}\b', query):
            num_keywords.add(candidate)
        # 同时从 locate_result 中提取数字
        for candidate in re.findall(r'\b\d{2,4}\b', locate_result):
            num_keywords.add(candidate)

        detailed_context = ""
        sources: list[dict] = []
        total_chars = 0
        matched_ids: set[str] = set()

        # 优先处理 LLM 定位的文档，再处理其他文档（避免预算被无关文档占满）
        mentioned_docs = [d for d in self.kb_docs if d["doc_name"] in locate_result]
        other_docs = [d for d in self.kb_docs if d["doc_name"] not in locate_result]
        sorted_docs = mentioned_docs + other_docs

        for d in sorted_docs:
            is_mentioned = d["doc_name"] in locate_result
            # 直接使用缓存的完整 structure（含 text 字段），不走 get_document_structure
            structure = self._raw_structures.get(d["doc_name"], [])
            flat = flatten_structure(structure)

            # 第一遍：收集所有匹配节点（按精度分类）
            specific_hits: list[dict] = []
            general_hits: list[dict] = []

            for node in flat:
                title = node.get("title", "")
                text = node.get("text", "")
                summary = node.get("summary", "") or node.get("prefix_summary", "")
                images = node.get("images", [])
                tables = node.get("tables", [])
                nid = node.get("node_id", "")
                has_decimal = bool(re.search(r'\d+\.\d+', title))

                is_hit = False
                if section_nums:
                    t_nums = set(re.findall(r'\d+(?:\.\d+){1,3}', title))
                    if t_nums & section_nums:
                        is_hit = True

                if not is_hit and query_grams:
                    t_lower = title.lower()
                    if any(g in t_lower for g in query_grams):
                        is_hit = True
                    elif text and any(g in text[:500].lower() for g in query_grams):
                        is_hit = True
                    # 图片 caption 匹配
                    elif images and any(g in " ".join(
                            img.get("caption","") for img in images).lower()
                                       for g in query_grams):
                        is_hit = True

                # 数字关键词匹配（如 3500, 10, 110）—— 用户常问具体数值参数
                if not is_hit and num_keywords:
                    check_text = (title + " " + (text[:1000] if text else "")).lower()
                    for num in num_keywords:
                        if num in check_text:
                            is_hit = True
                            break

                if is_hit and nid not in matched_ids:
                    matched_ids.add(nid)
                    t_lower2 = title.lower()
                    title_score = sum(1 for g in query_grams if g in t_lower2)
                    text_score = sum(1 for g in query_grams if text and g in text[:500].lower()) if text else 0
                    score = title_score * 10 + text_score
                    if is_mentioned:
                        score += 30  # LLM 推荐的文档优先
                    entry = dict(title=title, text=text, summary=summary,
                                 images=images, tables=tables,
                                 doc_name=d["doc_name"], score=score)
                    (specific_hits if has_decimal else general_hits).append(entry)

            # 按相关性降序排列：最相关的节点优先分配上下文预算
            specific_hits.sort(key=lambda x: x["score"], reverse=True)
            general_hits.sort(key=lambda x: x["score"], reverse=True)
            # 第二遍：精确节点优先（取完整 text）
            doc_entries: list[str] = []
            for entry in specific_hits:
                content = (entry["text"] or entry["summary"])[:MAX_RELEVANT_NODE_CHARS]
                if content.strip():
                    # 附加图片和表格信息
                    media_extras = _build_media_context(entry.get("images", []),
                                                        entry.get("tables", []),
                                                        d["doc_name"])
                    media_text = "\n\n".join(media_extras) if media_extras else ""
                    full_entry = f"[{entry['title']}]\n{content}"
                    if media_text:
                        full_entry += "\n\n" + media_text
                    doc_entries.append(full_entry)

                    source = {
                        "doc_name": entry["doc_name"],
                        "section": entry["title"],
                        "summary": (entry["text"] or entry["summary"])[:500],
                    }
                    # 附加图片 URL 到引用来源
                    images = entry.get("images", [])
                    if images:
                        mineru = self._mineru_dirs.get(entry["doc_name"], "")
                        if mineru:
                            dir_name = os.path.basename(mineru)
                            source["images"] = [
                                {"url": f"/api/images/{dir_name}/{img['path']}",
                                 "caption": img.get("caption", "")}
                                for img in images[:5]  # 最多5张
                            ]
                    tables = entry.get("tables", [])
                    if tables:
                        source["tables"] = [
                            {"caption": t.get("caption", ""),
                             "html": t.get("html", "")[:300]}
                            for t in tables[:3]
                        ]
                    sources.append(source)

                    total_chars += len(full_entry)
                    if total_chars > MAX_CONTEXT_CHARS:
                        break

            # 一般节点以摘要补充
            for entry in general_hits:
                if total_chars > MAX_CONTEXT_CHARS:
                    break
                content = entry["summary"][:300]
                if content.strip():
                    doc_entries.append(f"[{entry['title']}] {content}")
                    sources.append({"doc_name": entry["doc_name"], "section": entry["title"], "summary": content[:200]})
                    total_chars += len(content)

            if doc_entries:
                detailed_context += f"\n\n--- 文档: {d['doc_name']} ---\n" + "\n\n".join(doc_entries)

        return detailed_context, sources

    def _build_final_prompt(self, query: str, detailed_context: str) -> str:
        return f"""根据以下文档内容回答用户问题，引用具体章节名称。

背景资料（[附图] 表示该章节关联的图片，[表格] 表示关联的数据表）:
{detailed_context[:MAX_CONTEXT_CHARS]}

用户问题: {query}

请给出准确的回答，注明信息来源（文档名称+章节名）。如果信息不足以回答，请说明。

回答要求:
1. 涉及数据对比时使用 Markdown 表格呈现
2. 涉及数学公式时使用 LaTeX 语法（行内公式用 $...$，独立公式用 $$...$$）
3. 公式中不要使用 \\tag 命令标记编号
4. 如果上下文中有 [附图] 标注，回答时在相关位置用 [图X: 图注描述] 引用
5. 结构化、分点陈述，便于阅读"""


# ========== 全局引擎 ==========
engine: RAGEngine | None = None


def get_engine() -> RAGEngine:
    global engine
    if engine is None:
        engine = RAGEngine(RESOURCE_DIR)
    return engine


# ========== Pydantic 模型 ==========
class ChatRequest(BaseModel):
    query: str
    model: str | None = None


class ModelSwitchRequest(BaseModel):
    model: str


# ========== SSE 事件辅助 ==========
def sse_event(event: str, data: dict) -> str:
    return json.dumps({"event": event, "data": data}, ensure_ascii=False)


# ========== 路由 ==========
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "PageIndex RAG Agent"}


@app.get("/api/kb-info")
async def kb_info():
    return get_engine().get_kb_info()


@app.get("/api/models")
async def list_models():
    current = get_engine().get_model()
    return {"models": MODEL_OPTIONS, "current": current}


@app.post("/api/model/switch")
async def switch_model(req: ModelSwitchRequest):
    if req.model not in MODEL_OPTIONS:
        raise HTTPException(400, f"Unsupported model: {req.model}")
    get_engine().set_model(req.model)
    return {"ok": True, "current": req.model}


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """SSE 流式问答。事件类型:
    - step: 检索过程进度 {stage, message, detail?}
    - token: 生成答案的 token {delta}
    - sources: 引用来源 {sources: [...]}
    - done: 完成 {answer}
    - error: 出错 {message}
    """
    query = req.query.strip()
    if not query:
        raise HTTPException(400, "query is empty")

    eng = get_engine()
    if req.model and req.model != eng.get_model():
        eng.set_model(req.model)

    async def event_generator() -> AsyncIterator[dict]:
        loop = asyncio.get_event_loop()

        # ---- Step 1: 收集结构片段 ----
        yield {"event": "step", "data": json.dumps({
            "stage": "collect",
            "message": "正在扫描知识库结构…",
        }, ensure_ascii=False)}

        t0 = time.time()
        snippets = await loop.run_in_executor(None, eng._collect_snippets)
        yield {"event": "step", "data": json.dumps({
            "stage": "collect_done",
            "message": f"已扫描 {len(eng.kb_docs)} 篇文档 / {len(snippets)} 个章节节点",
            "duration_ms": int((time.time() - t0) * 1000),
        }, ensure_ascii=False)}

        if not snippets:
            yield {"event": "error", "data": json.dumps({"message": "知识库为空"}, ensure_ascii=False)}
            return

        # ---- Step 2: LLM 定位相关节点 ----
        yield {"event": "step", "data": json.dumps({
            "stage": "locate",
            "message": "正在让模型定位相关章节…",
        }, ensure_ascii=False)}

        t0 = time.time()
        try:
            locate_result = await loop.run_in_executor(
                None, eng._locate_with_llm, query, snippets
            )
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": f"定位失败: {e}"}, ensure_ascii=False)}
            return

        # 简单提取被命中的文档名
        hit_docs = [d["doc_name"] for d in eng.kb_docs if d["doc_name"] in locate_result]
        yield {"event": "step", "data": json.dumps({
            "stage": "locate_done",
            "message": f"模型初步命中 {len(hit_docs)} 篇文档" if hit_docs else "模型完成初步检索",
            "hit_docs": hit_docs[:10],
            "duration_ms": int((time.time() - t0) * 1000),
        }, ensure_ascii=False)}

        # ---- Step 3: 提取详细章节摘要 ----
        yield {"event": "step", "data": json.dumps({
            "stage": "extract",
            "message": "正在提取相关章节详情…",
        }, ensure_ascii=False)}

        t0 = time.time()
        detailed_context, sources = await loop.run_in_executor(
            None, eng._extract_details, locate_result, query
        )
        yield {"event": "step", "data": json.dumps({
            "stage": "extract_done",
            "message": f"已提取 {len(sources)} 个章节详情作为上下文",
            "source_count": len(sources),
            "duration_ms": int((time.time() - t0) * 1000),
        }, ensure_ascii=False)}

        # 上报引用来源
        if sources:
            yield {"event": "sources", "data": json.dumps({
                "sources": sources[:30],
            }, ensure_ascii=False)}

        # ---- Step 4: 流式生成最终答案 ----
        yield {"event": "step", "data": json.dumps({
            "stage": "generate",
            "message": "正在生成回答…",
        }, ensure_ascii=False)}

        if not detailed_context:
            # 没有详细上下文，直接用 Step 1 结果
            yield {"event": "token", "data": json.dumps({"delta": locate_result}, ensure_ascii=False)}
            yield {"event": "done", "data": json.dumps({"answer": locate_result}, ensure_ascii=False)}
            return

        final_prompt = eng._build_final_prompt(query, detailed_context)
        model_name = eng.get_model()
        if model_name:
            model_name = model_name.removeprefix("litellm/")

        t0 = time.time()
        full_answer = ""
        try:
            # litellm streaming — 传入模型专属的 api_key / api_base
            cfg = get_model_config(model_name)
            stream = await litellm.acompletion(
                model=model_name,
                messages=[{"role": "user", "content": final_prompt}],
                temperature=0,
                stream=True,
                api_key=cfg["api_key"],
                api_base=cfg["api_base"] or None,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_answer += delta
                    yield {"event": "token", "data": json.dumps({"delta": delta}, ensure_ascii=False)}
        except Exception as e:
            # 流式失败，降级为非流式
            yield {"event": "step", "data": json.dumps({
                "stage": "fallback",
                "message": f"流式失败，切换非流式重试…",
            }, ensure_ascii=False)}
            try:
                cfg = get_model_config(model_name)
                full_answer = litellm.completion(
                    model=model_name,
                    messages=[{"role": "user", "content": final_prompt}],
                    temperature=0,
                    stream=False,
                    api_key=cfg["api_key"],
                    api_base=cfg["api_base"] or None,
                ).choices[0].message.content
                full_answer = full_answer or ""
                if full_answer:
                    yield {"event": "token", "data": json.dumps({"delta": full_answer}, ensure_ascii=False)}
                else:
                    yield {"event": "error", "data": json.dumps({"message": "生成失败且无内容返回"}, ensure_ascii=False)}
                    return
            except Exception as e2:
                yield {"event": "error", "data": json.dumps({"message": f"生成失败: {e2}"}, ensure_ascii=False)}
                return

        # 清理 LLM 可能输出的不兼容 LaTeX 命令
        full_answer = re.sub(r'\\tag\{[^}]*\}', '', full_answer)

        yield {"event": "step", "data": json.dumps({
            "stage": "generate_done",
            "message": "回答生成完成",
            "duration_ms": int((time.time() - t0) * 1000),
        }, ensure_ascii=False)}

        yield {"event": "done", "data": json.dumps({
            "answer": full_answer,
            "total_sources": len(sources),
        }, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


@app.post("/api/kb/upload")
async def upload_document(file: UploadFile = File(...)):
    """上传文档到知识库（PDF / DOCX / MD），SSE 流式回报处理进度"""
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".pdf", ".docx", ".doc", ".md"):
        raise HTTPException(400, "仅支持 PDF、DOCX、MD 文件")

    ALLOWED = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
               ".doc": "application/msword", ".md": "text/markdown"}
    if file.content_type and file.content_type not in ("application/octet-stream",) and \
       file.content_type not in ALLOWED.get(ext, ""):
        pass  # 宽松校验，不因 MIME 类型拒绝

    # 写入临时文件
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    try:
        shutil.copyfileobj(file.file, tf)
        tf.close()
    except Exception:
        tf.close()
        os.unlink(tf.name)
        raise HTTPException(500, "文件写入失败")

    from pipeline_service import process_file

    async def progress_generator():
        try:
            async for evt in process_file(tf.name, file.filename):
                yield {"event": evt["stage"], "data": json.dumps(evt, ensure_ascii=False)}
            # 重新加载知识库
            get_engine().reload()
            yield {"event": "reload_done", "data": json.dumps({"message": "知识库已刷新"}, ensure_ascii=False)}
        finally:
            try:
                os.unlink(tf.name)
            except Exception:
                pass

    return EventSourceResponse(progress_generator())


@app.get("/api/kb/path/{doc_name}")
async def get_document_path(doc_name: str):
    """返回文档的本地文件路径（供 Electron 直接打开）"""
    mineru_resource = BASE_DIR.parent / "day1_PDF2MD" / "resource"
    if mineru_resource.exists():
        for f in mineru_resource.iterdir():
            stem = Path(f.name).stem
            if stem == doc_name or doc_name in stem or stem in doc_name:
                return {"path": str(f), "filename": f.name}
    raise HTTPException(404, f"未找到文档: {doc_name}")


@app.get("/api/kb/view/{doc_name}")
async def view_document(doc_name: str):
    """查看文档：返回对应的 PDF 或原始文件供浏览器打开"""
    from fastapi.responses import FileResponse

    # 在 PDF2MD/resource/ 中查找匹配的文档
    mineru_resource = BASE_DIR.parent / "day1_PDF2MD" / "resource"
    if mineru_resource.exists():
        for f in mineru_resource.iterdir():
            # 匹配文档名（去掉路径后缀）
            stem = Path(f.name).stem
            if stem == doc_name or doc_name in stem or stem in doc_name:
                return FileResponse(
                    f,
                    media_type="application/pdf",
                    headers={"Content-Disposition": "inline"},
                )
    raise HTTPException(404, f"未找到文档: {doc_name}")


@app.delete("/api/kb/document/{doc_name}")
async def delete_document(doc_name: str):
    """删除知识库文档及其全部生成物"""
    import shutil
    deleted = []

    # 1) day2_pageindex/resource/{doc_name}.json
    rp = RESOURCE_DIR / f"{doc_name}.json"
    if rp.exists():
        rp.unlink()
        deleted.append(str(rp))

    # 2) day2_pageindex/resource_enhanced/{doc_name}_enhanced.json
    re_dir = BASE_DIR / "resource_enhanced"
    rp2 = re_dir / f"{doc_name}_enhanced.json"
    if rp2.exists():
        rp2.unlink()
        deleted.append(str(rp2))

    # 3) day1_PDF2MD/output/ 中匹配的目录
    mineru_output = BASE_DIR.parent / "day1_PDF2MD" / "output"
    if mineru_output.exists():
        for d in mineru_output.iterdir():
            if d.is_dir() and doc_name in d.name:
                shutil.rmtree(d, ignore_errors=True)
                deleted.append(str(d))

    # 4) day1_PDF2MD/resource/ 中匹配的原始文件
    mineru_resource = BASE_DIR.parent / "day1_PDF2MD" / "resource"
    if mineru_resource.exists():
        for f in mineru_resource.iterdir():
            stem = Path(f.name).stem
            if stem == doc_name or doc_name in stem or stem in doc_name:
                f.unlink()
                deleted.append(str(f))

    # 重新加载知识库
    get_engine().reload()

    return {"ok": True, "doc_name": doc_name, "deleted": deleted}


# ========== 入口 ==========
if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("PageIndex RAG Agent 后端启动中…")
    print("=" * 60)
    eng = get_engine()
    info = eng.get_kb_info()
    print(f"[KB] 知识库目录: {info['resource_dir']}")
    print(f"[KB] 已加载文档: {info['doc_count']} 篇")
    for d in info["documents"]:
        print(f"     - {d['doc_name']} ({d['line_count']} 行)")
    print(f"\n[API] 服务地址: http://127.0.0.1:8765")
    print(f"[API] 文档地址: http://127.0.0.1:8765/docs\n")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
