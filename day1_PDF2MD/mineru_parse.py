"""
MinerU 精确解析脚本 — vlm 模型
- 自动拆分超过 200 页的 PDF
- 单文件/批量上传，结果自动合并

用法:
    py -3.12 mineru_parse.py                     # 解析 resource 下所有文件
    py -3.12 mineru_parse.py "文件名.pdf"          # 只解析指定文件
    py -3.12 mineru_parse.py "报告.docx"           # 支持 Word 文件
"""
import os
import sys
import json
import time
import uuid
import zipfile
import shutil
import tempfile
import requests
from pathlib import Path
from dotenv import load_dotenv

# Windows 终端 UTF-8 支持
sys.stdout.reconfigure(encoding='utf-8')

# ========== 配置 ==========
BASE_DIR = Path(__file__).parent.resolve()
RESOURCE_DIR = BASE_DIR / "resource"
OUTPUT_DIR = BASE_DIR / "output"

SUPPORTED_EXT = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx")
MAX_PAGES = 200      # MinerU 单文件最大页数
BATCH_LIMIT = 50     # API 单次最多 50 个文件
POLL_INTERVAL = 5    # 轮询间隔（秒）
POLL_TIMEOUT = 3600  # 总超时（秒，60分钟）

load_dotenv(BASE_DIR / "MinerU" / "mineru_env" / ".env")
TOKEN = os.getenv("api-key")
if not TOKEN:
    print("❌ 未找到 api-key，请检查 .env 文件")
    sys.exit(1)

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TOKEN}"
}
API_BATCH_FILE_URL = "https://mineru.net/api/v4/file-urls/batch"
API_BATCH_RESULT = "https://mineru.net/api/v4/extract-results/batch"
MODEL = "vlm"


# ========== 文件发现与拆分 ==========

def get_pdf_page_count(pdf_path: Path) -> int:
    """获取 PDF 页数"""
    from PyPDF2 import PdfReader
    with open(pdf_path, "rb") as f:
        return len(PdfReader(f).pages)


def split_pdf(pdf_path: Path, temp_dir: Path) -> list[Path]:
    """拆分超大 PDF 为 ≤200 页的片段"""
    from PyPDF2 import PdfReader, PdfWriter
    reader = PdfReader(str(pdf_path))
    total = len(reader.pages)
    total_parts = (total + MAX_PAGES - 1) // MAX_PAGES
    chunks = []

    for part in range(1, total_parts + 1):
        start = (part - 1) * MAX_PAGES
        end = min(part * MAX_PAGES, total)
        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])

        chunk_name = f"{pdf_path.stem}_part{part}of{total_parts}.pdf"
        chunk_path = temp_dir / chunk_name
        with open(chunk_path, "wb") as f:
            writer.write(f)
        print(f"  ✂️  拆分: {chunk_name} (p.{start + 1}~{end}, {end - start} 页)")
        chunks.append(chunk_path)

    return chunks


def prepare_files(target_file: str = None) -> tuple[list[Path], dict[str, list[str]]]:
    """
    准备待上传文件列表，自动拆分超大 PDF。
    Returns:
        all_files: 所有待上传文件路径
        chunk_map: {原始文件名_stem: [分片名列表]}，空列表表示无需合并
    """
    # 1. 收集原始文件
    if target_file:
        file_path = RESOURCE_DIR / target_file
        if not file_path.exists():
            print(f"❌ 文件不存在: {file_path}")
            sys.exit(1)
        if file_path.suffix.lower() not in SUPPORTED_EXT:
            print(f"❌ 不支持的文件类型: {file_path.suffix}")
            sys.exit(1)
        raw_files = [file_path]
    else:
        raw_files = []
        for ext in SUPPORTED_EXT:
            raw_files.extend(RESOURCE_DIR.glob(f"*{ext}"))
        raw_files = sorted(set(raw_files), key=lambda f: f.name)
        if not raw_files:
            print(f"❌ resource 目录中没有支持的文件: {RESOURCE_DIR}")
            sys.exit(1)

    # 2. 检查 PDF 页数，拆分超限文件
    all_files = []
    chunk_map = {}
    temp_dir = Path(tempfile.mkdtemp(prefix="mineru_split_"))

    for f in raw_files:
        if f.suffix.lower() == ".pdf":
            pages = get_pdf_page_count(f)
            if pages > MAX_PAGES:
                print(f"📐 {f.name}: {pages} 页，超过 {MAX_PAGES} 页限制，自动拆分...")
                chunks = split_pdf(f, temp_dir)
                all_files.extend(chunks)
                chunk_map[f.stem] = chunks
            else:
                all_files.append(f)
                chunk_map[f.stem] = []  # 无需合并
        else:
            all_files.append(f)
            chunk_map[f.stem] = []  # 非 PDF，无需合并

    return all_files, chunk_map, temp_dir


# ========== API 调用 ==========

def submit_batch(files: list[dict]) -> dict:
    """提交批量上传任务"""
    payload = {
        "files": files,
        "model_version": MODEL,
        "enable_formula": True,
        "enable_table": True,
        "language": "ch",
    }
    resp = requests.post(API_BATCH_FILE_URL, headers=HEADERS, json=payload)
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"提交失败: {data}")
    return data["data"]


def upload_files(file_paths: list[Path], file_urls: list[str]) -> None:
    """上传本地文件到 OSS"""
    for file_path, file_url in zip(file_paths, file_urls):
        size_kb = file_path.stat().st_size / 1024
        print(f"  ↑ 上传: {file_path.name} ({size_kb:.0f} KB)")
        with open(file_path, "rb") as f:
            resp = requests.put(file_url, data=f)
            if resp.status_code not in (200, 204):
                raise RuntimeError(f"上传失败 {file_path.name}: HTTP {resp.status_code}")


def poll_batch_results(batch_id: str) -> list[dict]:
    """轮询直到全部完成或超时"""
    start = time.time()
    while time.time() - start < POLL_TIMEOUT:
        resp = requests.get(
            f"{API_BATCH_RESULT}/{batch_id}",
            headers={"Authorization": f"Bearer {TOKEN}"}
        )
        data = resp.json()
        if data.get("code") != 0:
            time.sleep(POLL_INTERVAL)
            continue

        results = data["data"]["extract_result"]
        states = [r["state"] for r in results]
        done = states.count("done")
        failed = states.count("failed")
        elapsed = int(time.time() - start)
        print(f"  进度: {done}/{len(results)} 完成, {failed} 失败 (已等待 {elapsed}s)")

        if all(s in ("done", "failed") for s in states):
            return results
        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"轮询超时 ({POLL_TIMEOUT}s)")


def download_zip(result: dict, extract_dir: Path) -> bool:
    """下载 ZIP 并解压，返回是否成功"""
    zip_url = result.get("full_zip_url")
    if not zip_url:
        return False

    extract_dir.mkdir(parents=True, exist_ok=True)
    zip_path = extract_dir / "result.zip"

    zip_resp = requests.get(zip_url)
    with open(zip_path, "wb") as f:
        f.write(zip_resp.content)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    zip_path.unlink()
    return True


# ========== 合并拆分结果 ==========

def merge_chunks(stem: str, chunk_results: list[dict], temp_dir: Path):
    """合并拆分后各分片的 full.md、content_list.json、images 等"""
    output_dir = OUTPUT_DIR / f"{stem}-{uuid.uuid4()}"
    output_dir.mkdir(parents=True, exist_ok=True)

    merged_md = []
    merged_content_list = []
    page_offset = 0  # 第二个分片开始需要偏移页码
    part_num = 0

    for result in sorted(chunk_results, key=lambda r: r["file_name"]):
        part_dir = temp_dir / f"chunk_{result['file_name']}"
        if not download_zip(result, part_dir):
            continue

        # --- 合并 full.md ---
        md_file = part_dir / "full.md"
        if md_file.exists():
            content = md_file.read_text(encoding="utf-8")
            if merged_md:
                merged_md.append(f"\n\n<!-- 分片 {part_num + 2}/{len(chunk_results)} -->\n\n")
            merged_md.append(content)

        # --- 合并 content_list.json（调整页码） ---
        for cl_file in part_dir.glob("*content_list*.json"):
            if "_v2" in cl_file.name:
                continue
            cl_data = json.loads(cl_file.read_text(encoding="utf-8"))
            if part_num > 0:
                for block in cl_data:
                    if "page_idx" in block:
                        block["page_idx"] += page_offset
            merged_content_list.extend(cl_data)
            break

        # --- 统计本分片页数（从 content_list 推断） ---
        if part_num == 0:
            # 第一个分片后，计算页数偏移
            pages_in_part = max(
                (b.get("page_idx", 0) for b in json.loads(
                    next(part_dir.glob("*content_list*.json")).read_text(encoding="utf-8")
                ) if "page_idx" in b),
                default=0
            ) + 1
            page_offset = pages_in_part

        # --- 合并 images ---
        images_dir = part_dir / "images"
        if images_dir.exists():
            target_images = output_dir / "images"
            target_images.mkdir(exist_ok=True)
            for img in images_dir.iterdir():
                dest = target_images / img.name
                # 处理重名：部分前缀避免覆盖
                if dest.exists():
                    dest = target_images / f"part{part_num + 1}_{img.name}"
                shutil.copy2(img, dest)

        part_num += 1

    # 写入合并结果
    (output_dir / f"{stem}.md").write_text("".join(merged_md), encoding="utf-8")
    if merged_content_list:
        (output_dir / "content_list.json").write_text(
            json.dumps(merged_content_list, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"  ✅ {stem} (合并 {len(chunk_results)} 分片) → {output_dir.name}/")


# ========== 主流程 ==========

def process_batch(file_paths: list[Path], chunk_map: dict[str, list[Path]]) -> dict[str, list]:
    """上传 + 轮询 + 下载"""
    files_spec = [{"name": f.name} for f in file_paths]

    mode = "单文件上传模式" if len(files_spec) == 1 else f"批量上传模式 ({len(files_spec)} 文件)"
    print(f"\n📤 提交 [{mode}]...")
    for f in file_paths:
        print(f"   - {f.name}")

    # 1. 获取上传 URL
    data = submit_batch(files_spec)
    batch_id = data["batch_id"]
    file_urls = data["file_urls"]
    print(f"   batch_id: {batch_id}")

    # 2. 上传
    print(f"\n📦 上传文件中...")
    upload_files(file_paths, file_urls)

    # 3. 轮询
    print(f"\n⏳ 等待解析完成...")
    results = poll_batch_results(batch_id)

    # 4. 分类结果
    done_results = []
    for r, fp in zip(results, file_paths):
        if r["state"] == "done":
            done_results.append((r, fp))
        else:
            err = r.get("err_msg", "未知错误")
            print(f"  ❌ {r['file_name']}: {err}")

    # 5. 下载/合并
    print(f"\n📥 下载结果...")
    temp_dir = Path(tempfile.mkdtemp(prefix="mineru_dl_"))

    # 按原始文件分组
    processed = set()
    for stem, chunks in chunk_map.items():
        if stem in processed:
            continue
        processed.add(stem)

        # 找出该原始文件的所有结果
        related = [(r, fp) for r, fp in done_results
                   if fp.stem.startswith(stem)]
        if not related:
            continue

        if len(related) > 1:
            # 分片文件：合并
            print(f"\n  🔗 合并: {stem} ({len(related)} 分片)")
            merge_chunks(stem, [r for r, _ in related], temp_dir)
        else:
            # 单文件：直接解压
            result, file_path = related[0]
            print(f"\n  ↓ 下载: {result['file_name']}")
            output_dir = OUTPUT_DIR / f"{stem}-{uuid.uuid4()}"
            if download_zip(result, output_dir):
                # 重命名 full.md → {原文件名}.md
                full_md = output_dir / "full.md"
                target_md = output_dir / f"{stem}.md"
                if full_md.exists():
                    full_md.rename(target_md)
                print(f"  ✅ {stem} → {output_dir.name}/{target_md.name}")
            else:
                print(f"  ⚠️  {stem}: 无下载链接")

    # 6. 汇总
    done = len(done_results)
    failed = len(results) - done
    print(f"\n{'=' * 50}")
    print(f"📊 完成: 成功 {done} / 失败 {failed} / 共 {len(results)}")


def main():
    target_file = sys.argv[1] if len(sys.argv) > 1 else None

    all_files, chunk_map, split_temp_dir = prepare_files(target_file)

    if target_file:
        print(f"📂 单文件解析: {target_file}")
    else:
        print(f"📂 找到 {len(all_files)} 个文件（含拆分包）")

    # 按 BATCH_LIMIT 分批上传
    for i in range(0, len(all_files), BATCH_LIMIT):
        batch = all_files[i : i + BATCH_LIMIT]
        process_batch(batch, chunk_map)

    # 清理临时文件
    if split_temp_dir.exists():
        shutil.rmtree(split_temp_dir, ignore_errors=True)

    print(f"\n✅ 全部处理完成，输出目录: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
