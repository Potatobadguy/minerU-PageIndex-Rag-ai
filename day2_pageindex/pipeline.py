"""
完整流水线: PDF -> MinerU -> MD -> PageIndex -> enhanceindex 图片增强

用法:
    python pipeline.py                                       # Step 1~2: 处理 output/ 下已有 MD
    python pipeline.py --pdf "xxx.pdf"                       # Step 0~2: PDF 转 MD 后全流程
    python pipeline.py --pdf "xxx.pdf" --model openai/gpt-4.1
    python pipeline.py --dir "xxx" --model openai/gpt-4o
    python pipeline.py --force
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# 路径配置
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = Path(r"c:\Work\day1_PDF2MD\output")
MINERU_DIR = Path(r"c:\Work\day1_PDF2MD")
RESOURCE_DIR = BASE_DIR / "resource"
RESOURCE_ENHANCED_DIR = BASE_DIR / "resource_enhanced"
PAGEINDEX_DIR = BASE_DIR / "PageIndex"

sys.path.insert(0, str(PAGEINDEX_DIR))

# 加载 .env 中的 API Key
from dotenv import load_dotenv
load_dotenv(PAGEINDEX_DIR / ".env")

from pageindex.page_index_md import md_to_tree
from pageindex.utils import ConfigLoader


# ========== Step 0: PDF -> MD (MinerU) ==========

def run_mineru_parse(pdf_name: str) -> str | None:
    """
    调用 mineru_parse.py 将 PDF 转为 MD + images。

    pdf_name: resource/ 下的 PDF 文件名（如 "DLT 5582-2020 xxx.pdf"）
    返回: 新生成的 output 目录名，或 None（失败）
    """
    mineru_script = MINERU_DIR / "mineru_parse.py"
    if not mineru_script.exists():
        print(f"  [ERROR] 找不到 mineru_parse.py: {mineru_script}")
        return None

    # 记录 output 目录下已有的文件夹（用于后续发现新生成的）
    existing = set(d.name for d in OUTPUT_DIR.iterdir() if d.is_dir())

    print(f"\n{'=' * 60}")
    print("Step 0: MinerU PDF -> MD")
    print(f"  脚本: {mineru_script}")
    print(f"  文件: {pdf_name}")
    print(f"{'=' * 60}")

    cmd = ["py", "-3.12", str(mineru_script), pdf_name]
    print(f"  [exec] {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd, cwd=str(MINERU_DIR),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=3600,
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"  [stderr] {result.stderr[-500:]}")
            return None
    except subprocess.TimeoutExpired:
        print("  [ERROR] MinerU 解析超时")
        return None
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None

    # 等待新目录出现
    for _ in range(30):
        new = set(d.name for d in OUTPUT_DIR.iterdir() if d.is_dir()) - existing
        if new:
            dir_name = new.pop()
            print(f"  [OK] MinerU 完成 -> {dir_name}")
            return dir_name
        time.sleep(2)

    print("  [WARN] MinerU 完成但未找到新目录")
    return None


# ========== 工具函数 ==========

def get_output_name(md_path: str) -> str:
    """生成输出文件名：以 MD 文件自身的文件名（不含 .md 后缀）为准"""
    return Path(md_path).stem


def find_md_in_dir(dir_path: Path) -> dict | None:
    """在单个 output 子目录中查找 .md 和统计图片数"""
    md_files = list(dir_path.glob("*.md"))
    if not md_files:
        print(f"  [WARN] {dir_path.name} 中没有 .md 文件")
        return None
    md = md_files[0]
    images_dir = dir_path / "images"
    img_count = len(list(images_dir.glob("*.jpg"))) if images_dir.exists() else 0
    name = get_output_name(str(md))
    return {
        "md_path": str(md),
        "output_dir": str(dir_path),
        "output_name": name,
        "doc_name": name,
        "img_count": img_count,
    }


def scan_all_dirs(output_dir: Path) -> list[dict]:
    """扫描全部，去重（排除 dbd12ef0，选图片最多版本）"""
    doc_candidates: dict[str, list[dict]] = {}
    for mdfile in sorted(output_dir.rglob("*.md")):
        rel_dir = mdfile.parent
        images_dir = rel_dir / "images"
        img_count = len(list(images_dir.glob("*.jpg"))) if images_dir.exists() else 0
        name = get_output_name(str(mdfile))
        doc_candidates.setdefault(name, []).append({
            "md_path": str(mdfile),
            "output_dir": str(rel_dir),
            "output_name": name,
            "doc_name": name,
            "img_count": img_count,
        })

    selected = []
    for candidates in doc_candidates.values():
        good = [c for c in candidates if "dbd12ef0" not in c["output_dir"]]
        if not good:
            good = candidates
        best = max(good, key=lambda c: c["img_count"])
        selected.append(best)

    return sorted(selected, key=lambda x: x["output_name"])


# ========== 核心流程 ==========

def process_md(md_path: str, resource_dir: Path, model: str | None = None, force: bool = False) -> dict | None:
    """
    用 PageIndex 处理单个 MD 文件。
    - summary_token_threshold=50：降低阈值让更多节点触发 LLM 摘要
    - if_add_node_text='yes'：保留完整原文
    - if_add_node_summary='yes'：LLM 生成节点摘要
    - if_add_doc_description='yes'：LLM 生成文档描述
    - model: 覆盖 config.yaml 中的 model
    """
    output_name = get_output_name(md_path)
    out_name = f"{output_name}.json"
    out_path = resource_dir / out_name

    if out_path.exists() and not force:
        print(f"  [SKIP] {output_name} (已存在，用 --force 覆盖)")
        with open(out_path, "r", encoding="utf-8") as f:
            return json.load(f)

    print(f"  [PageIndex] 处理: {output_name}")
    overrides = {
        "if_add_node_summary": "yes",
        "if_add_doc_description": "yes",
        "if_add_node_text": "yes",
        "if_add_node_id": "yes",
    }
    if model:
        overrides["model"] = model
        print(f"  模型: {model}")
    opt = ConfigLoader().load(overrides)

    try:
        result = asyncio.run(md_to_tree(
            md_path=md_path,
            if_thinning=False,
            min_token_threshold=5000,
            if_add_node_summary="yes",
            summary_token_threshold=50,
            model=opt.model,
            if_add_doc_description="yes",
            if_add_node_text="yes",
            if_add_node_id="yes",
        ))
    except Exception as e:
        print(f"  [ERROR] {output_name}: {e}")
        return None

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  [OK] 已保存: {out_path}")
    return result


def rebuild_enhanced_index():
    """运行 enhanceindex 构建增强索引"""
    print(f"\n{'=' * 60}")
    print("Step 2: 构建增强索引 (图片注入)")
    print(f"{'=' * 60}")
    from enhanceindex.build import build_enhanced_index
    build_enhanced_index()


# ========== 主入口 ==========

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PDF -> MinerU -> PageIndex -> enhanceindex 全流程")
    parser.add_argument("--pdf", type=str, default=None,
                        help="PDF 文件名（位于 day1_PDF2MD/resource/ 下），先调 MinerU 转 MD 再走后续流程")
    parser.add_argument("--dir", type=str, default=None,
                        help="指定 output/ 下的单个文件夹名")
    parser.add_argument("--model", type=str, default=None,
                        help="检索树构建模型，如 openai/gpt-4.1, openai/deepseek-v4-pro")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    RESOURCE_DIR.mkdir(parents=True, exist_ok=True)
    RESOURCE_ENHANCED_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Pipeline: PDF -> MinerU -> PageIndex -> enhanceindex")
    print("=" * 60)

    # ====== Step 0: PDF -> MD ======
    if args.pdf:
        dir_name = run_mineru_parse(args.pdf)
        if not dir_name:
            print("MinerU 解析失败，流水线中断")
            sys.exit(1)
        # 自动绑定 --dir
        args.dir = dir_name

    if args.dir:
        target_dir = OUTPUT_DIR / args.dir
        if not target_dir.is_dir():
            print(f"错误: 目录不存在: {target_dir}")
            sys.exit(1)
        info = find_md_in_dir(target_dir)
        if info is None:
            sys.exit(1)
        md_files = [info]
        print(f"\n处理文件夹: {target_dir.name}")
        print(f"  输出名: {info['output_name']} ({info['img_count']} 张图片)")
    else:
        md_files = scan_all_dirs(OUTPUT_DIR)
        print(f"\n扫描到 {len(md_files)} 个文档 (已去重):")
        for m in md_files:
            print(f"  -> {m['output_name']}.json ({m['img_count']} 张图片)")
            print(f"     Dir: {Path(m['output_dir']).name}")

    # ====== Step 1: PageIndex ======
    print(f"\n{'=' * 60}")
    print("Step 1: PageIndex 结构化处理")
    model = args.model or ConfigLoader().load(None).model
    print(f"  模型: {model}")
    print(f"  summary_token_threshold=50 (更多节点触发 LLM 摘要)")
    if args.force:
        print("  (强制覆盖模式)")
    print(f"{'=' * 60}")

    results = {}
    for m in md_files:
        r = process_md(m["md_path"], RESOURCE_DIR, model=model, force=args.force)
        if r:
            results[m["output_name"]] = r

    print(f"\n处理完成: {len(results)}/{len(md_files)} 成功")

    # ====== Step 2: enhanceindex ======
    rebuild_enhanced_index()

    print(f"\n{'=' * 60}")
    print("流水线完成!")
    print(f"  resource/          : {len(list(RESOURCE_DIR.glob('*.json')))} 个索引")
    print(f"  resource_enhanced/ : {len(list(RESOURCE_ENHANCED_DIR.glob('*.json')))} 个增强索引")
    print(f"{'=' * 60}")
