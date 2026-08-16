"""Web 页面展示（扩展，默认关闭）。

独立服务：在 config 中将 web.enabled 设为 true 后，可单独运行 `python web/app.py` 启动。
提供：首页展示最新报告；/api/report 返回最新报告文本；/api/history 返回 JSON 数据库。
"""
from __future__ import annotations

import os

from src.database import load


def _latest_report_path(report_dir: str = "reports"):
    if not os.path.isdir(report_dir):
        return None
    files = [f for f in os.listdir(report_dir) if f.endswith(".md")]
    if not files:
        return None
    files.sort(reverse=True)
    return os.path.join(report_dir, files[0])


def create_app():
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse, PlainTextResponse

    app = FastAPI(title="大乐透AI娱乐分析助手")

    @app.get("/", response_class=HTMLResponse)
    def index():
        path = _latest_report_path()
        if not path:
            return HTMLResponse("<h1>暂无报告</h1><p>请先运行 python -m src.scheduler 生成报告。</p>")
        text = open(path, encoding="utf-8").read()
        html = (
            "<html><head><meta charset='utf-8'><title>大乐透娱乐分析</title></head>"
            f"<body><pre style='white-space:pre-wrap;font-family:monospace'>{text}</pre></body></html>"
        )
        return HTMLResponse(html)

    @app.get("/api/report")
    def api_report():
        path = _latest_report_path()
        if not path:
            raise HTTPException(404, "no report")
        return PlainTextResponse(open(path, encoding="utf-8").read())

    @app.get("/api/history")
    def api_history():
        return load("data/dlt_history.json")

    return app


def main():
    import uvicorn

    from src.scheduler import load_config

    cfg = load_config()
    web_cfg = cfg.get("web", {})
    app = create_app()
    uvicorn.run(app, host=web_cfg.get("host", "0.0.0.0"), port=int(web_cfg.get("port", 8080)))


if __name__ == "__main__":
    main()
