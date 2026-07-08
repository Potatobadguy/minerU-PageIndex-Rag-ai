"""
增强索引配置 — 文档名 → MinerU 输出目录映射
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # day2_pageindex/
RESOURCE_DIR = BASE_DIR / "resource"
RESOURCE_ENHANCED_DIR = BASE_DIR / "resource_enhanced"

# MinerU 输出根目录
MINERU_OUTPUT_DIR = Path(r"c:\Work\day1_PDF2MD\output")

# 文档输出目录列表（按顺序扫描）
OUTPUT_DIRS = sorted(str(d) for d in MINERU_OUTPUT_DIR.iterdir() if d.is_dir())


def find_mineru_dir(doc_name: str) -> Path | None:
    """
    根据文档名匹配合适的 MinerU 输出目录。
    如果有重复，优先选非 dbd12ef0 的版本（更全的那个）。
    """
    candidates = []
    for d in OUTPUT_DIRS:
        dir_name = Path(d).name
        if doc_name in dir_name or doc_name[:8] in dir_name:
            candidates.append(Path(d))
    if not candidates:
        return None
    # 排除已知的不完整版本
    preferred = [c for c in candidates if "dbd12ef0" not in str(c)]
    return preferred[0] if preferred else candidates[0]
