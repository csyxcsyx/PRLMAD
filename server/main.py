from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from server.routers import chat, generate, session, tutor, evaluate, knowledge

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="KnowStack 知栈", version="0.2.0")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app.include_router(chat.router)
app.include_router(generate.router)
app.include_router(session.router)
app.include_router(tutor.router)
app.include_router(evaluate.router)
app.include_router(knowledge.router)


@app.get("/api/health")
async def health():
    return {"ok": True, "version": "0.2.0"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "pages/chat.html", {"page": "chat"})


@app.get("/page/chat", response_class=HTMLResponse)
async def page_chat(request: Request):
    return templates.TemplateResponse(request, "pages/chat.html", {"page": "chat"})


@app.get("/page/generate", response_class=HTMLResponse)
async def page_generate(request: Request):
    return templates.TemplateResponse(request, "pages/generate.html", {"page": "generate"})


@app.get("/page/learning-path", response_class=HTMLResponse)
async def page_path(request: Request):
    return templates.TemplateResponse(request, "pages/learning_path.html", {"page": "learning_path"})


@app.get("/page/tutor", response_class=HTMLResponse)
async def page_tutor(request: Request):
    return templates.TemplateResponse(request, "pages/tutor.html", {"page": "tutor"})


@app.get("/page/evaluate", response_class=HTMLResponse)
async def page_evaluate(request: Request):
    return templates.TemplateResponse(request, "pages/evaluate.html", {"page": "evaluate"})


@app.get("/page/knowledge", response_class=HTMLResponse)
async def page_knowledge(request: Request):
    return templates.TemplateResponse(request, "pages/knowledge.html", {"page": "knowledge"})


@app.get("/page/os-lab", response_class=HTMLResponse)
async def page_os_lab(request: Request):
    return templates.TemplateResponse(request, "pages/os_lab.html", {"page": "os_lab"})
