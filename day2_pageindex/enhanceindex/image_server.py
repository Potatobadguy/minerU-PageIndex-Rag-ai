"""
图片静态服务器 — 暴露 MinerU 输出目录的 images/ 文件

用法:
    python -m enhanceindex.image_server              # 默认端口 8766
    python -m enhanceindex.image_server --port 9999  # 自定义端口
"""
import argparse
import mimetypes
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from .config import MINERU_OUTPUT_DIR


class ImageHandler(SimpleHTTPRequestHandler):
    """代理多个 MinerU 输出目录下的 images/ 子目录"""

    def do_GET(self):
        """GET /{dir_name}/images/{hash}.jpg → 对应输出目录下的文件"""
        path = self.path.lstrip("/")
        parts = path.split("/", 2)
        if len(parts) >= 3 and parts[1] == "images":
            dir_name = parts[0]
            img_path = "/".join(parts[1:])  # images/hash.jpg
            # 查找对应的 MinerU 输出目录
            target = MINERU_OUTPUT_DIR / dir_name / img_path
            if target.exists():
                self._serve_file(str(target))
                return
        # 回退到根目录
        root = str(MINERU_OUTPUT_DIR)
        full_path = os.path.join(root, path.lstrip("/"))
        if os.path.isfile(full_path):
            self._serve_file(full_path)
        else:
            super().do_GET()

    def _serve_file(self, filepath: str):
        """发送文件并提供正确的 MIME 类型与 CORS 头"""
        try:
            with open(filepath, "rb") as f:
                content = f.read()
        except OSError:
            self.send_error(404, "File not found")
            return

        mime, _ = mimetypes.guess_type(filepath)
        if mime is None:
            mime = "application/octet-stream"

        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", len(content))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        # 压缩日志，只打印非 200 的请求
        if "200" in str(args[0]) if args else False:
            return
        super().log_message(format, *args)


def serve(port: int = 8766):
    """启动图片 HTTP 服务"""
    server = HTTPServer(("0.0.0.0", port), ImageHandler)
    print(f"[ImageServer] 图片服务已启动: http://localhost:{port}")
    print(f"   示例: http://localhost:{port}/DLT 5440-2020...ae2a064d.../images/xxx.jpg")
    print(f"   按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="图片静态服务器")
    parser.add_argument("--port", type=int, default=8766, help="服务端口")
    args = parser.parse_args()
    serve(args.port)
