"""
图片位置增强索引 - 从 MinerU 输出中提取图片位置信息

用法:
    py -3.12 build_enhance_index.py <MinerU输出目录>
"""
import sys
import json
import re
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')


def find_content_list(output_dir: Path) -> Path | None:
    """查找 MinerU 输出的 content_list.json"""
    for f in output_dir.glob("**/*content_list*.json"):
        if "_v2" not in f.name:
            return f
    for f in output_dir.glob("**/*content_list*.json"):
        return f
    return None


def extract_image_info(content_list_path: Path) -> list[dict]:
    """从 content_list.json 提取所有图片信息"""
    with open(content_list_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    images = []
    for block in data:
        if block.get("type") == "image":
            img_name = Path(block["img_path"]).name
            images.append({
                "img_name": img_name,
                "img_path": block["img_path"],
                "page": block["page_idx"] + 1,  # 0-index → 1-index
                "bbox": block.get("bbox", []),   # [x1, y1, x2, y2]
                "caption": " ".join(block.get("image_caption", [])),
                "footnote": " ".join(block.get("image_footnote", [])),
            })
    return images


def find_image_in_md(md_path: Path, img_name: str) -> int | None:
    """在 full.md 中查找图片所在行号"""
    if not md_path.exists():
        return None
    content = md_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    # 匹配 ![...](images/xxx.jpg)
    for i, line in enumerate(lines, 1):
        if img_name in line:
            return i
    return None


def match_images_to_context(image_list: list[dict], md_path: Path, md_lines: list[str]) -> list[dict]:
    """为每张图片补充正文上下文（前后各2行）"""
    for img in image_list:
        line_num = find_image_in_md(md_path, img["img_name"])
        img["md_line"] = line_num

        # 提取上下文
        if line_num:
            start = max(0, line_num - 3)
            end = min(len(md_lines), line_num + 2)
            img["context_before"] = [l.strip() for l in md_lines[start:line_num - 1] if l.strip()]
            img["context_after"] = [l.strip() for l in md_lines[line_num:end] if l.strip()]

    return image_list


def build_enhance_index(output_dir: Path) -> dict:
    """构建增强索引"""
    content_list = find_content_list(output_dir)
    if not content_list:
        print(f"❌ 未找到 content_list.json")
        return {}

    # 1. 提取图片信息
    images = extract_image_info(content_list)
    if not images:
        print("⚠️  没有图片")
        return {}

    # 2. 匹配 MD 文件
    md_files = list(output_dir.glob("*.md"))
    md_path = md_files[0] if md_files else None
    md_lines = md_path.read_text(encoding="utf-8").split("\n") if md_path else []

    # 3. 关联上下文
    images = match_images_to_context(images, md_path, md_lines)

    # 4. 构建索引
    result = {
        "source_dir": str(output_dir),
        "total_images": len(images),
        "images": images,
        # 按文件名快速查找
        "by_name": {img["img_name"]: img for img in images},
        # 按页码归组
        "by_page": {}
    }
    for img in images:
        p = str(img["page"])
        result["by_page"].setdefault(p, []).append(img["img_name"])

    return result


def main():
    if len(sys.argv) < 2:
        print("用法: py -3.12 build_enhance_index.py <MinerU输出目录>")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    if not output_dir.exists():
        print(f"❌ 目录不存在: {output_dir}")
        sys.exit(1)

    print(f"📂 处理: {output_dir.name}")
    index = build_enhance_index(output_dir)

    if not index or not index.get("images"):
        sys.exit(0)

    # 保存
    out_path = output_dir / "enhance_index.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 增强索引已生成: {out_path.name}")
    print(f"   图片总数: {index['total_images']}")
    print(f"   页码分布: {list(index['by_page'].keys())}")

    # 展示前3张
    for img in index["images"][:3]:
        print(f"\n   📷 {img['img_name']}")
        print(f"      页面: {img['page']}  位置: {img['bbox']}")
        print(f"      标题: {img['caption']}")
        print(f"      MD行号: {img.get('md_line')}")


if __name__ == "__main__":
    main()
