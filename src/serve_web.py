# -*- coding: utf-8 -*-
"""
轻量级静态文件服务器 · 用于本地查看 web 前端
python src/serve_web.py → http://localhost:8899
python main.py serve-web
"""
import http.server, socketserver, os, webbrowser

PORT = 8899
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web')


def main():
    os.chdir(WEB_DIR)

    Handler = http.server.SimpleHTTPRequestHandler

    class MyHandler(Handler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=WEB_DIR, **kwargs)

        def end_headers(self):
            self.send_header('Cache-Control', 'no-store')
            super().end_headers()

    with socketserver.TCPServer(("127.0.0.1", PORT), MyHandler) as httpd:
        print(f'[OK] Web服务已启动: http://localhost:{PORT}')
        print(f'     目录: {WEB_DIR}')
        print(f'     按 Ctrl+C 停止')
        try:
            webbrowser.open(f'http://localhost:{PORT}')
        except Exception:
            pass
        httpd.serve_forever()


if __name__ == '__main__':
    main()
