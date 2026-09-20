"""FastAPI 入口：提供静态页面与逐行求值 API。"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .parser import evaluate_plan

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="编织行指令审校工具", version="1.0.0")


class EvalRequest(BaseModel):
    start: int = Field(default=0, ge=0, le=10_000_000, description="起始针数")
    rows: list[str] = Field(default_factory=list, max_length=1000, description="逐行指令")


@app.post("/api/evaluate")
def evaluate(req: EvalRequest):
    """解析并逐行求值，返回每行的消耗 / 产出 / 剩余及错误定位。"""
    return {"start": req.start, "rows": evaluate_plan(req.start, req.rows)}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
