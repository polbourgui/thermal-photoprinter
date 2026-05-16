from dataclasses import asdict
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import (
    CaptionSettings,
    ImageSettings,
    LayoutSettings,
    PrinterSettings,
    Settings,
    get_settings,
    save_settings,
)
from layout import make_mockup

app = FastAPI(title="Photobooth")

_base = Path(__file__).parent
templates = Jinja2Templates(directory=_base / "templates")
app.mount("/static", StaticFiles(directory=_base / "static"), name="static")


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html", context={"s": get_settings()}
    )


@app.post("/settings")
async def update_settings(
    # Image
    dither_algorithm: str = Form(...),
    contrast: float = Form(...),
    brightness: float = Form(...),
    sharpness: float = Form(...),
    auto_rotate: str = Form("off"),
    grayscale_mode: str = Form("luminosity"),
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
    # Layout
    margin_top: int = Form(10),
    margin_bottom: int = Form(20),
    margin_sides: int = Form(0),
    caption_position: str = Form("bottom"),
    caption_font_size: int = Form(22),
    caption_padding: int = Form(14),
    separator: str = Form("off"),
):
    settings = Settings(
        image=ImageSettings(
            dither_algorithm=dither_algorithm,
            contrast=round(contrast, 2),
            brightness=round(brightness, 2),
            sharpness=round(sharpness, 2),
            auto_rotate=(auto_rotate == "on"),
            grayscale_mode=grayscale_mode,
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
            max_width=max(64, min(832, max_width)),
            align=align,
        ),
        layout=LayoutSettings(
            margin_top=max(0, margin_top),
            margin_bottom=max(0, margin_bottom),
            margin_sides=max(0, margin_sides),
            caption_position=caption_position,
            caption_font_size=max(10, min(60, caption_font_size)),
            caption_padding=max(0, caption_padding),
            separator=(separator == "on"),
        ),
    )
    save_settings(settings)
    return RedirectResponse(url="/", status_code=303)


@app.get("/mockup")
async def mockup():
    """Return a PNG mockup of the ticket at exact printer resolution."""
    img = make_mockup(get_settings())
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/settings")
async def api_settings():
    return asdict(get_settings())
