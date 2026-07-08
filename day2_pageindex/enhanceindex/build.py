"""
构建增强版索引 — 将 MinerU 提取的图片/表格注入 PageIndex 结构

流水线:
  1. 读取 resource/*.json      → PageIndex 结构（含 line_num）
  2. 读取 MinerU Markdown      → 提取 ![](images/hash.jpg) 行号→图片映射
  3. 读取 content_list_v2.json → 提取所有 image/table 条目（含 caption/html）
  4. 按行号匹配：将图片/表格附加到对应结构节点
  5. 写入 resource_enhanced/

用法:
    python -m enhanceindex.build          # 构建全部
    python -m enhanceindex.build --dry-run # 预览不写入
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from .config import (
    RESOURCE_DIR,
    RESOURCE_ENHANCED_DIR,
    find_mineru_dir,
)


# ---------- 解析 content_list (兼容 v1 和 v2) ----------

def parse_media_from_content_list(json_path: str) -> dict[int, dict]:
    """
    解析 content_list.json 或 content_list_v2.json，提取图片/表格信息。

    自动识别格式：
      v1: [{type, img_path, image_caption, page_idx}, ...]     (扁平列表)
      v2: [[{type, content: {image_source: {path}}, ...}], ...] (按页分组)

    返回: {page_idx: {"images": [...], "tables": [...]}}
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list) and data and isinstance(data[0], list):
        # v2: 按页分组
        return _parse_v2(data)
    else:
        # v1: 扁平列表
        return _parse_v1(data)


def _parse_v1(blocks: list) -> dict[int, dict]:
    """解析 v1 格式（扁平列表，每项有 page_idx）"""
    result: dict[int, dict] = {}
    for block in blocks:
        t = block.get("type", "")
        page_idx = block.get("page_idx", 0)
        if page_idx not in result:
            result[page_idx] = {"images": [], "tables": []}

        if t in ("image", "chart"):
            path = block.get("img_path", "")
            caption = _extract_text_parts(block.get("image_caption", []))
            result[page_idx]["images"].append({
                "path": path, "caption": caption, "page_idx": page_idx,
            })
        elif t == "table":
            path = block.get("img_path", "")
            caption = _extract_text_parts(block.get("table_caption", []))
            html = block.get("table_body", "")
            result[page_idx]["tables"].append({
                "path": path, "caption": caption, "html": html, "page_idx": page_idx,
            })
    return result


def _parse_v2(pages: list) -> dict[int, dict]:
    """解析 v2 格式（按页分组）"""
    result: dict[int, dict] = {}
    for page_idx, blocks in enumerate(pages):
        images = []
        tables = []
        for block in blocks:
            t = block.get("type", "")
            content = block.get("content", {})
            if t in ("image", "chart"):
                src = content.get("image_source", {})
                path = src.get("path", "")
                caption = _extract_text_parts(content.get("image_caption", []))
                images.append({"path": path, "caption": caption, "page_idx": page_idx})
            elif t == "table":
                src = content.get("image_source", {})
                path = src.get("path", "")
                caption = _extract_text_parts(content.get("table_caption", []))
                html = content.get("html", "")
                tables.append({"path": path, "caption": caption, "html": html, "page_idx": page_idx})
        if images or tables:
            result[page_idx] = {"images": images, "tables": tables}
    return result


def _extract_text_parts(caption_list: list) -> str:
    """提取 caption 文本内容"""
    parts = []
    for item in caption_list:
        if isinstance(item, dict):
            parts.append(item.get("content", ""))
    return " ".join(parts).strip()


# ---------- 解析 Markdown ----------

def parse_markdown_image_lines(md_path: str) -> dict[int, str]:
    """
    扫描 MD 文件，提取行号→图片 hash 的映射。

    返回: {line_num: "images/hash.jpg"}
    """
    mapping: dict[int, str] = {}
    with open(md_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            m = re.search(r'!\[\]\((images/[^)]+)\)', line)
            if m:
                mapping[i] = m.group(1)
    return mapping


def parse_markdown_table_lines(md_path: str) -> dict[int, str]:
    """
    扫描 MD 文件，提取行号→ `<table>` HTML 的映射。

    返回: {line_num: "<table>...</table>"}
    """
    mapping: dict[int, str] = {}
    with open(md_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            m = re.search(r'(<table>.+?</table>)', line, re.DOTALL)
            if m:
                mapping[i] = m.group(1)
    return mapping


# ---------- 核心：匹配与注入 ----------

def _inject_media(
    structure: list[dict],
    md_image_lines: dict[int, str],
    md_table_lines: dict[int, str],
    page_media: dict[int, dict],
) -> list[dict]:
    """
    递归遍历结构树，为每个节点注入 images 和 tables 字段。
    """
    if not structure:
        return structure

    # 1) 先拍平获取所有节点的 line_num 区间
    flat_nodes = _flatten_with_line_range(structure)

    # 2) 为每个节点建立 line_num 区间
    node_ranges = []
    for n in flat_nodes:
        start = n["line_num"]
        end = n.get("end_line_num", start + 10000)
        node_ranges.append((start, end, n))

    # 3) 匹配 MD 图片行号到节点
    for line_no, img_path in md_image_lines.items():
        for start, end, node in node_ranges:
            if start <= line_no < end:
                node.setdefault("_images_md", []).append(img_path)
                break

    # 4) 匹配 MD 表格行号到节点
    for line_no, html in md_table_lines.items():
        for start, end, node in node_ranges:
            if start <= line_no < end:
                node.setdefault("_tables_md", []).append(html)
                break

    # 5) 匹配 content_list 中的图片/表格（用 caption 的关键词与节点 title/text 匹配）
    _match_page_media_to_nodes(flat_nodes, page_media)

    # 6) 最终注入 images/tables 字段
    def _inject_recursive(nodes: list[dict]):
        for node in nodes:
            imgs = []
            # 从 MD 图片引用获取路径
            md_imgs = node.pop("_images_md", [])
            for p in md_imgs:
                # 尝试从 page_media 找匹配的 caption
                caption = _find_caption_for_path(page_media, Path(p).name)
                imgs.append({"path": p, "caption": caption, "source": "md"})

            # 从 content_list 获取图片
            cl_imgs = node.pop("_images_cl", [])
            for ci in cl_imgs:
                if not any(i["path"] == ci["path"] for i in imgs):
                    imgs.append({**ci, "source": "content_list"})

            node["images"] = imgs if imgs else []

            # 表格
            tables = []
            md_tabs = node.pop("_tables_md", [])
            for h in md_tabs:
                tables.append({"html": h, "source": "md"})
            cl_tabs = node.pop("_tables_cl", [])
            for ct in cl_tabs:
                tables.append({**ct, "source": "content_list"})
            node["tables"] = tables if tables else []

            if node.get("nodes"):
                _inject_recursive(node["nodes"])

    _inject_recursive(structure)
    return structure


def _flatten_with_line_range(structure: list[dict]) -> list[dict]:
    """拍平树，并为每个节点计算 end_line_num"""
    nodes = []
    _flatten_recursive(structure, nodes)

    for i, n in enumerate(nodes):
        if i + 1 < len(nodes):
            n["end_line_num"] = nodes[i + 1]["line_num"]
        else:
            n["end_line_num"] = 999999
    return nodes


def _flatten_recursive(nodes: list[dict], result: list[dict]):
    for n in nodes:
        result.append(n)
        if n.get("nodes"):
            _flatten_recursive(n["nodes"], result)


def _find_caption_for_path(page_media: dict[int, dict], hash_name: str) -> str:
    """在 page_media 中查找图片的 caption"""
    for pg_data in page_media.values():
        for img in pg_data.get("images", []):
            if Path(img["path"]).name == hash_name:
                return img.get("caption", "")
        for tbl in pg_data.get("tables", []):
            if Path(tbl["path"]).name == hash_name:
                return tbl.get("caption", "")
    return ""


def _match_page_media_to_nodes(flat_nodes: list[dict], page_media: dict[int, dict]):
    """
    为每个节点匹配 content_list 中的图片/表格（补充 MD 中没有的图片）。
    策略：用 caption 中的关键词与节点的 title / text / summary 做交集匹配。
    """
    if not page_media:
        return

    # 预处理 page_media 中的图片信息
    all_images: list[dict] = []
    all_tables: list[dict] = []
    for pg_data in page_media.values():
        all_images.extend(pg_data.get("images", []))
        all_tables.extend(pg_data.get("tables", []))

    for node in flat_nodes:
        title = node.get("title", "")
        text = node.get("text", "")
        summary = node.get("summary", "")

        # 从 title 提取表格/图编号（如"表4.0.2"、"图5"）
        node_refs = set(re.findall(r'[图表表]\s*\d[\d.\-]*', title + text[:500]))

        matched_imgs = []
        matched_tbls = []

        for img in all_images:
            cap = img.get("caption", "")
            cap_refs = set(re.findall(r'[图表表]\s*\d[\d.\-]*', cap))
            if cap_refs & node_refs:
                matched_imgs.append(img)

        for tbl in all_tables:
            cap = tbl.get("caption", "")
            cap_refs = set(re.findall(r'[图表表]\s*\d[\d.\-]*', cap))
            if cap_refs & node_refs:
                matched_tbls.append(tbl)

        if matched_imgs:
            node["_images_cl"] = matched_imgs
        if matched_tbls:
            node["_tables_cl"] = matched_tbls


# ---------- 主入口 ----------

def build_enhanced_index(dry_run: bool = False) -> list[Path]:
    """
    构建增强版索引，为 resource/ 下每个 JSON 生成对应的 resource_enhanced/JSON。

    返回生成的文件列表。
    """
    RESOURCE_ENHANCED_DIR.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    for fname in sorted(os.listdir(RESOURCE_DIR)):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue

        src_path = RESOURCE_DIR / fname
        print(f"\n{'=' * 60}")
        print(f"处理: {fname}")

        with open(src_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        doc_name = data.get("doc_name", fname)
        print(f"  文档名: {doc_name}")

        # 查找 MinerU 输出目录
        mineru_dir = find_mineru_dir(doc_name)
        if not mineru_dir:
            print(f"  [WARN] 未找到 MinerU 输出目录，跳过图片注入")
            enhanced = data
        else:
            print(f"  MinerU 目录: {mineru_dir.name}")

            # 找 content_list（优先 v2，回退 v1）
            cl_files = list(mineru_dir.glob("*content_list_v2.json"))
            if not cl_files:
                cl_files = list(mineru_dir.glob("*content_list.json"))
            md_files = list(mineru_dir.glob("*.md"))

            if not cl_files or not md_files:
                print(f"  [WARN] 缺少 content_list.json 或 .md，跳过图片注入")
                enhanced = data
            else:
                cl_path = cl_files[0]
                md_path = md_files[0]

                # Step 1: 解析 content_list
                cl_type = "v2" if "_v2" in cl_path.name else "v1"
                print(f"  content_list ({cl_type}): {cl_path.name}")
                page_media = parse_media_from_content_list(str(cl_path))
                total_imgs = sum(len(v.get("images", [])) for v in page_media.values())
                total_tbls = sum(len(v.get("tables", [])) for v in page_media.values())
                print(f"  content_list: {total_imgs} 张图片, {total_tbls} 个表格")

                # Step 2: 解析 MD
                md_image_lines = parse_markdown_image_lines(str(md_path))
                md_table_lines = parse_markdown_table_lines(str(md_path))
                print(f"  Markdown: {len(md_image_lines)} 处图片引用, {len(md_table_lines)} 处表格")

                # Step 3: 注入
                structure = data.get("structure", [])
                enhanced_structure = _inject_media(
                    structure,
                    md_image_lines,
                    md_table_lines,
                    page_media,
                )
                enhanced = dict(data)
                enhanced["structure"] = enhanced_structure
                enhanced["_mineru_dir"] = str(mineru_dir)  # 记录 MinerU 输出目录路径

                # 统计
                flat = _flatten_with_line_range(enhanced_structure)
                nodes_with_img = sum(1 for n in flat if n.get("images"))
                nodes_with_tbl = sum(1 for n in flat if n.get("tables"))
                total_img_refs = sum(len(n.get("images", [])) for n in flat)
                total_tbl_refs = sum(len(n.get("tables", [])) for n in flat)
                print(f"  注入结果: {nodes_with_img} 个节点含图片 (共 {total_img_refs} 张)")
                print(f"             {nodes_with_tbl} 个节点含表格 (共 {total_tbl_refs} 个)")

        # 写入
        out_name = fname.replace(".json", "_enhanced.json")
        out_path = RESOURCE_ENHANCED_DIR / out_name

        if not dry_run:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(enhanced, f, ensure_ascii=False, indent=2)
            generated.append(out_path)
            print(f"  [OK] 已写入: {out_path}")
        else:
            print(f"  [DRY-RUN] 将写入: {out_path}")

    return generated


# ========== CLI ==========
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="构建增强版索引")
    parser.add_argument("--dry-run", action="store_true", help="预览不写入")
    args = parser.parse_args()

    print("=" * 60)
    print("enhanceindex — 图片增强索引构建")
    print("=" * 60)

    files = build_enhanced_index(dry_run=args.dry_run)

    print(f"\n{'=' * 60}")
    print(f"完成。共生成 {len(files)} 个增强索引文件。")
    print(f"输出目录: {RESOURCE_ENHANCED_DIR}")
