"""
管线服务：将 pipeline.py 逻辑封装为可被上传端点调用的异步函数。
支持 PDF / DOCX / MD 三种格式，处理完成后 JSON 写入 resource/ 目录。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import AsyncIterator

BASE_DIR = Path(__file__).resolve().parent.parent
PAGEINDEX_DIR = BASE_DIR / "PageIndex"
RESOURCE_DIR = BASE_DIR / "resource"
OUTPUT_DIR = Path(r"c:\Work\day1_PDF2MD\output")
MINERU_DIR = Path(r"c:\Work\day1_PDF2MD")

import sys
sys.path.insert(0, str(BASE_DIR))       # 使 enhanceindex 等可导入
sys.path.insert(0, str(PAGEINDEX_DIR))  # 使 pageindex 等可导入

from dotenv import load_dotenv
load_dotenv(PAGEINDEX_DIR / ".env")

PIPELINE_STAGES = [
    "uploading",    # 文件上传中
    "parsing",      # PDF/DOCX 解析中
    "indexing",     # 知识检索树生成中
    "enhancing",    # 图片增强索引构建中
    "done",         # 文件成功加入知识库
    "error",        # 处理失败
]


async def process_file(file_path: str, original_name: str) -> AsyncIterator[dict]:
    """
    处理上传文件的主入口。
    Step 0: 归档 → Step 1: 格式解析 → Step 2: PageIndex 建树 → Step 3: 图片增强索引
    Yields: {"stage": str, "message": str, "filename": str}
    """
    import shutil
    ext = Path(original_name).suffix.lower()
    filename = original_name
    RESOURCE_DIR.mkdir(parents=True, exist_ok=True)

    # Step -1: 保存原始文件到 PDF2MD/resource/ 归档
    MINERU_RESOURCE = MINERU_DIR / "resource"
    MINERU_RESOURCE.mkdir(parents=True, exist_ok=True)
    archive_path = MINERU_RESOURCE / Path(original_name).name
    shutil.copy2(file_path, archive_path)

    yield {"stage": "uploading", "message": f"文件已接收: {filename} → {archive_path}", "filename": filename}

    try:
        has_error = False
        done_event = None  # 暂存 done 事件，等增强索引完成后再发送

        if ext == ".pdf":
            async for evt in _process_pdf(file_path, filename):
                if evt["stage"] == "error":
                    has_error = True
                    yield evt
                elif evt["stage"] == "done":
                    done_event = evt  # 暂不发送
                else:
                    yield evt
        elif ext == ".md":
            async for evt in _process_md(file_path, filename):
                if evt["stage"] == "error":
                    has_error = True
                    yield evt
                elif evt["stage"] == "done":
                    done_event = evt  # 暂不发送
                else:
                    yield evt
        elif ext in (".docx", ".doc"):
            async for evt in _process_docx(file_path, filename):
                if evt["stage"] == "error":
                    has_error = True
                    yield evt
                elif evt["stage"] == "done":
                    done_event = evt  # 暂不发送
                else:
                    yield evt
        else:
            yield {"stage": "error", "message": f"不支持的文件格式: {ext}", "filename": filename}
            return

        if has_error:
            if done_event:
                yield done_event  # 基础索引成功，仍通知前端
            return

        # Step 3: 构建增强检索索引（注入图片/表格）
        yield {"stage": "enhancing", "message": "正在构建图片增强检索…", "filename": filename}
        await _build_enhanced(filename)

        # 增强索引完成后才发送 done
        if done_event:
            yield done_event
        else:
            yield {"stage": "done", "message": f"{filename} 已加入知识库", "filename": filename}
    except Exception as e:
        yield {"stage": "error", "message": f"处理失败: {str(e)[:200]}", "filename": filename}


# ========== PDF 处理 ==========

async def _process_pdf(file_path: str, filename: str) -> AsyncIterator[dict]:
    """Step 0: PDF → MinerU → MD,  Step 1: MD → PageIndex → JSON"""
    yield {"stage": "parsing", "message": "正在调用 MinerU 解析 PDF…", "filename": filename}

    # 文件已在 process_file 中存档到 MINERU_DIR/resource/

    # 记录已有目录
    existing = set(d.name for d in OUTPUT_DIR.iterdir() if d.is_dir())

    loop = asyncio.get_event_loop()
    cmd = ["py", "-3.12", str(MINERU_DIR / "mineru_parse.py"), Path(filename).name]

    proc = await loop.run_in_executor(
        None,
        lambda: subprocess.run(
            cmd, cwd=str(MINERU_DIR),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=3600,
        )
    )

    if proc.returncode != 0:
        yield {"stage": "error", "message": f"MinerU 解析失败: {proc.stderr[-300:]}", "filename": filename}
        return

    # 等待新目录出现
    md_path = None
    for _ in range(30):
        new = set(d.name for d in OUTPUT_DIR.iterdir() if d.is_dir()) - existing
        if new:
            dir_name = new.pop()
            md_files = list((OUTPUT_DIR / dir_name).glob("*.md"))
            if md_files:
                md_path = str(md_files[0])
                break
        await asyncio.sleep(2)

    if not md_path:
        yield {"stage": "error", "message": "MinerU 完成但未找到 MD 文件", "filename": filename}
        return

    # 继续走 MD→PageIndex 流程
    async for evt in _process_md(md_path, filename):
        yield evt


# ========== MD 处理 ==========

async def _process_md(file_path: str, filename: str) -> AsyncIterator[dict]:
    """Step 1: MD → PageIndex → JSON（检索树构建）"""
    yield {"stage": "indexing", "message": "正在构建知识检索树…", "filename": filename}

    loop = asyncio.get_event_loop()

    try:
        from pageindex.page_index_md import md_to_tree
        from pageindex.utils import ConfigLoader

        out_name = Path(filename).stem
        out_path = RESOURCE_DIR / f"{out_name}.json"

        opt = ConfigLoader().load({
            "if_add_node_summary": "yes",
            "if_add_doc_description": "yes",
            "if_add_node_text": "yes",
            "if_add_node_id": "yes",
        })

        result = await loop.run_in_executor(
            None,
            lambda: asyncio.run(md_to_tree(
                md_path=file_path,
                if_thinning=False,
                min_token_threshold=5000,
                if_add_node_summary="yes",
                summary_token_threshold=50,
                model=opt.model,
                if_add_doc_description="yes",
                if_add_node_text="yes",
                if_add_node_id="yes",
            ))
        )

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        line_count = result.get("line_count", 0)
        yield {"stage": "done", "message": f"{filename} 已加入知识库 ({line_count} 行)", "filename": filename, "output": str(out_path)}
    except Exception as e:
        yield {"stage": "error", "message": f"索引构建失败: {str(e)[:200]}", "filename": filename}


# ========== 增强索引 ==========

async def _build_enhanced(filename: str):
    """Step 3: 为刚处理完的文档构建增强版索引（注入 MinerU 图片/表格）"""
    loop = asyncio.get_event_loop()

    try:
        # 刷新 OUTPUT_DIRS：MinerU 刚创建工作目录，需重新扫描
        import enhanceindex.config as enhance_cfg
        enhance_cfg.OUTPUT_DIRS = sorted(
            str(d) for d in enhance_cfg.MINERU_OUTPUT_DIR.iterdir() if d.is_dir()
        )

        await loop.run_in_executor(
            None,
            _run_enhanced_build,
        )
    except Exception as e:
        # 增强索引失败不阻塞主流程 — 基础索引已就绪
        import sys
        print(f"[enhanced] build failed for {filename}: {e}", file=sys.stderr)


def _run_enhanced_build():
    """同步执行增强索引构建（在 executor 中运行，隔离 print 输出）"""
    import io
    import sys
    from enhanceindex.build import build_enhanced_index

    # 将 print 输出重定向以便调试（不影响 SSE 流）
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        files = build_enhanced_index()
    finally:
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        if output.strip():
            print(f"[enhanced] {output.strip()[:500]}")


# ========== DOCX 处理 ==========

async def _process_docx(file_path: str, filename: str) -> AsyncIterator[dict]:
    """Step 0: DOCX → 纯文本 → MD,  Step 1: MD → PageIndex → JSON"""
    yield {"stage": "parsing", "message": "正在提取 DOCX 文档内容…", "filename": filename}

    loop = asyncio.get_event_loop()

    try:
        import docx2txt

        text = await loop.run_in_executor(None, docx2txt.process, file_path)
        if not text or not text.strip():
            yield {"stage": "error", "message": "DOCX 文件内容为空", "filename": filename}
            return

        # 转换为 Markdown 格式（为章节添加 # 标题）
        md_lines = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                md_lines.append("")
                continue
            # 检测可能的标题行（全中文且较短，以数字或"第"开头）
            if re.match(r'^第.{1,40}条', line) or re.match(r'^\d+[\.\、]', line) and len(line) < 60:
                md_lines.append(f"## {line}")
            elif len(line) < 40 and not line.endswith((".", "。", "，", "；")):
                md_lines.append(f"# {line}")
            else:
                md_lines.append(line)

        md_content = "\n".join(md_lines)

        # 写入临时文件然后走 MD 流程
        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False)
        tf.write(md_content)
        tf.close()

        async for evt in _process_md(tf.name, filename):
            yield evt

        # 清理临时文件
        try:
            os.unlink(tf.name)
        except Exception:
            pass

    except ImportError:
        yield {"stage": "error", "message": "缺少 docx2txt 库，请先安装: pip install docx2txt", "filename": filename}
    except Exception as e:
        yield {"stage": "error", "message": f"DOCX 处理失败: {str(e)[:200]}", "filename": filename}
