"""检查增强索引中的节点大小分布"""
import json, os, sys

for fname in sorted(os.listdir("../resource_enhanced")):
    if not fname.endswith(".json"):
        continue
    with open(f"../resource_enhanced/{fname}", "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes = []
    def walk(nds, result, depth=0):
        for n in nds:
            text_len = len(n.get("text", ""))
            summary_len = len(n.get("summary", "") or n.get("prefix_summary", ""))
            children = len(n.get("nodes", []))
            result.append({
                "title": (n.get("title", "") or "")[:60],
                "text_len": text_len,
                "summary_len": summary_len,
                "children": children,
                "depth": depth,
            })
            if n.get("nodes"):
                walk(n["nodes"], result, depth + 1)

    walk(data["structure"], nodes)
    nodes.sort(key=lambda x: x["text_len"], reverse=True)

    doc = data.get("doc_name", fname)[:30]
    print(f"\n=== {doc} ===")
    print(f"Total nodes: {len(nodes)}")

    # Top 10 largest
    for n in nodes[:10]:
        print(f"  d={n['depth']} text={n['text_len']:>6} sum={n['summary_len']:>4} ch={n['children']:<3} | {n['title']}")

    # Size distribution
    buckets = {"<1k": 0, "1k-5k": 0, "5k-10k": 0, "10k-30k": 0, "30k+": 0}
    for n in nodes:
        t = n["text_len"]
        if t < 1000:       buckets["<1k"] += 1
        elif t < 5000:     buckets["1k-5k"] += 1
        elif t < 10000:    buckets["5k-10k"] += 1
        elif t < 30000:    buckets["10k-30k"] += 1
        else:              buckets["30k+"] += 1
    print(f"  Size: {buckets}")
