from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import (
    CaptionSettings,
    ImageSettings,
    PrinterSettings,
    Settings,
    get_settings,
    save_settings,
)

app = FastAPI(title="Thermal Printer")

_base = Path(__file__).parent
templates = Jinja2Templates(directory=_base / "templates")
app.mount("/static", StaticFiles(directory=_base / "static"), name="static")


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html", {"request": request, "s": get_settings()}
    )


@app.post("/settings")
async def update_settings(
    # Image
    dither_algorithm: str = Form(...),
    contrast: float = Form(...),
    brightness: float = Form(...),
    sharpness: float = Form(...),
    auto_rotate: str = Form("off"),
    # Visual effects
    gamma: float = Form(1.0),
    threshold: int = Form(128),
    pre_blur: float = Form(0.0),
    vignette: float = Form(0.0),
    grain: float = Form(0.0),
    posterize_bits: int = Form(0),
    invert: str = Form("off"),
    # Caption
    caption_enabled: str = Form("off"),
    caption_location: str = Form(""),
    caption_show_date: str = Form("off"),
    # Printer
    max_width: int = Form(576),
    align: str = Form("center"),
):
    settings = Settings(
        image=ImageSettings(
            dither_algorithm=dither_algorithm,
            contrast=round(contrast, 2),
            brightness=round(brightness, 2),
            sharpness=round(sharpness, 2),
            auto_rotate=(auto_rotate == "on"),
            gamma=round(gamma, 2),
            threshold=max(0, min(255, threshold)),
            pre_blur=round(pre_blur, 1),
            vignette=round(vignette, 2),
            grain=round(grain, 2),
            posterize_bits=max(0, min(7, posterize_bits)),
            invert=(invert == "on"),
        ),
        caption=CaptionSettings(
            enabled=(caption_enabled == "on"),
            location=caption_location.strip(),
            show_date=(caption_show_date == "on"),
        ),
        printer=PrinterSettings(
            max_width=max_width,
            align=align,
        ),
    )
    save_settings(settings)
    return RedirectResponse(url="/", status_code=303)


@app.get("/api/settings")
async def api_settings():
    return asdict(get_settings())
