"""测试增强索引输出质量"""
import json

with open("../resource_enhanced/DLT 5440-2020 重覆冰架空输电线路设计技术规程_enhanced.json",
          "r", encoding="utf-8") as f:
    data = json.load(f)

def find_media(nodes, prefix=""):
    for n in nodes:
        imgs = n.get("images", [])
        tbls = n.get("tables", [])
        if imgs or tbls:
            title = (n.get("title") or "")[:50]
            print(f"{prefix}[{n.get('node_id','')}] {title}")
            for img in imgs[:2]:
                cap = (img.get("caption") or "")[:60]
                path = img.get("path", "")[-40:]
                print(f"{prefix}  IMG: {path} | {cap}")
            for tbl in tbls[:1]:
                cap = (tbl.get("caption") or "")[:60]
                html = (tbl.get("html") or "")[:80]
                print(f"{prefix}  TBL: caption='{cap}' html='{html}...'")
        if n.get("nodes"):
            find_media(n["nodes"], prefix + "  ")

print("=== 包含图表的节点 ===")
find_media(data["structure"])

# 统计
flat = [data["structure"]]
def flatten(nodes, result):
    for n in nodes:
        result.append(n)
        if n.get("nodes"):
            flatten(n["nodes"], result)
all_nodes = []
flatten(data["structure"], all_nodes)

nodes_with_img = [n for n in all_nodes if n.get("images")]
nodes_with_tbl = [n for n in all_nodes if n.get("tables")]
total_imgs = sum(len(n.get("images", [])) for n in all_nodes)
total_tbls = sum(len(n.get("tables", [])) for n in all_nodes)

print(f"\n=== 统计 ===")
print(f"总结点数: {len(all_nodes)}")
print(f"含图片节点: {len(nodes_with_img)} (共 {total_imgs} 张)")
print(f"含表格节点: {len(nodes_with_tbl)} (共 {total_tbls} 个)")
