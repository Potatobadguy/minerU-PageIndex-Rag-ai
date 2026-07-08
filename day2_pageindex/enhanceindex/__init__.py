"""
enhanceindex — 图片增强索引模块

三步走：
  1. build  — 构建增强版 JSON 索引，注入图片/表格元数据
  2. image_server — 启动静态文件服务，暴露 MinerU 输出目录的 images/
  3. 检索时自动携带关联图片路径与表格 HTML
"""
from .build import build_enhanced_index
