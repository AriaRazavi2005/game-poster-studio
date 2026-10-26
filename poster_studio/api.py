"""
poster_studio.api
~~~~~~~~~~~~~~~~~
Lightweight HTTP REST API for Game Poster Studio v2 (FastAPI).
Run via: uvicorn poster_studio.api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from typing import List, Optional
from poster_studio import __version__
from poster_studio.core.presets import list_presets
from poster_studio.core.collage import list_collage_templates
from poster_studio.telegram_bridge import create_game_poster, create_game_collage, poster_to_bytes


def create_app():
    from fastapi import FastAPI, File, Form, Response, UploadFile

    app = FastAPI(title="Game Poster Studio API", version=__version__)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/presets")
    def get_presets_endpoint():
        return list_presets()

    @app.get("/templates")
    def get_templates_endpoint():
        return list_collage_templates()

    @app.post("/poster")
    async def generate_poster_endpoint(
        file: UploadFile = File(...),
        ratio: str = Form("4:5"),
        preset: Optional[str] = Form(None),
        title: Optional[str] = Form(None),
        subtitle: Optional[str] = Form(None),
        badge: Optional[str] = Form(None),
        watermark: str = Form("BAZYEPC"),
    ):
        raw = await file.read()
        img = create_game_poster(
            input_image=raw,
            ratio=ratio,
            preset=preset,
            title=title,
            subtitle=subtitle,
            badge=badge,
            watermark=watermark,
        )
        return Response(content=poster_to_bytes(img), media_type="image/jpeg")

    @app.post("/collage")
    async def generate_collage_endpoint(
        files: List[UploadFile] = File(...),
        ratio: str = Form("4:5"),
        template: str = Form("auto"),
        fit: str = Form("cover"),
        title: Optional[str] = Form(None),
        watermark: str = Form("BAZYEPC"),
    ):
        raws = [await f.read() for f in files]
        img = create_game_collage(
            input_images=raws,
            ratio=ratio,
            template=template,
            fit=fit,
            title=title,
            watermark=watermark,
        )
        return Response(content=poster_to_bytes(img), media_type="image/jpeg")

    return app


try:
    app = create_app()
except ImportError:
    app = None
