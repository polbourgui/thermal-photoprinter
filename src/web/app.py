from dataclasses import asdict
from io import BytesIO
from pathlib import Path
import shutil
import subprocess

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import state
from config import (
    CaptionSettings,
    HardwareSettings,
    ImageSettings,
    LayoutSettings,
    PrinterSettings,
    Settings,
    get_settings,
    save_settings,
)
from counter import peek
from layout import make_mockup, list_available_fonts
import trigger as trig

app = FastAPI(title="Photobooth")

_base = Path(__file__).parent
templates = Jinja2Templates(directory=_base / "templates")
app.mount("/static", StaticFiles(directory=_base / "static"), name="static")


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html",
        context={"s": get_settings(), "fonts": list_available_fonts()},
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
    # Layout — fonts
    font_logo: str = Form(""),
    font_body: str = Form(""),
    # Layout — spacing
    margin_top: int = Form(12),
    margin_bottom: int = Form(24),
    margin_sides: int = Form(8),
    header_padding: int = Form(8),
    footer_padding: int = Form(10),
    logo_font_size: int = Form(34),
    proof_font_size: int = Form(18),
    footer_font_size: int = Form(20),
    separator: str = Form("off"),
    # Hardware
    num_leds: int = Form(111),
):
    hw = get_settings().hardware  # preserve fields not exposed in the form
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
            font_logo=font_logo,
            font_body=font_body,
            margin_top=max(0, margin_top),
            margin_bottom=max(0, margin_bottom),
            margin_sides=max(0, margin_sides),
            header_padding=max(0, header_padding),
            footer_padding=max(0, footer_padding),
            logo_font_size=max(16, min(72, logo_font_size)),
            proof_font_size=max(10, min(40, proof_font_size)),
            footer_font_size=max(10, min(40, footer_font_size)),
            separator=(separator == "on"),
        ),
        hardware=HardwareSettings(
            camera_device=hw.camera_device,
            serial_port=hw.serial_port,
            storage_path=hw.storage_path,
            num_leds=max(1, min(500, num_leds)),
        ),
    )
    save_settings(settings)
    if state._esp is not None:
        try:
            state._esp.apply_led_config(settings.hardware.num_leds)
        except Exception:
            pass
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


@app.get("/api/fonts")
async def api_fonts():
    return list_available_fonts()


@app.get("/api/settings")
async def api_settings():
    return asdict(get_settings())


@app.post("/trigger")
async def virtual_trigger():
    """Simulate a button press — for testing without physical hardware."""
    fired = trig.fire()
    if fired:
        return JSONResponse({"status": "ok", "message": "Trigger fired"})
    return JSONResponse(
        {"status": "busy", "message": "Shot already in progress"},
        status_code=409,
    )


@app.get("/healthz")
async def healthz():
    from printer import get_status as printer_status

    def _serial_present() -> bool:
        return Path("/dev/ttyUSB0").exists() or Path("/dev/ttyESP8266").exists()

    storage_path = Path(get_settings().hardware.storage_path)
    disk = shutil.disk_usage(storage_path if storage_path.exists() else ".")
    printer = printer_status()

    return JSONResponse({
        "camera":        Path("/dev/video0").exists(),
        "printer":       printer,
        "esp8266":       _serial_present(),
        "disk_free_gb":  round(disk.free / 1e9, 1),
        "disk_used_pct": round(disk.used / disk.total * 100),
        "proof_count":   peek(),
        "trigger_armed": trig._armed,
    })


@app.post("/api/wifi")
async def wifi_add(ssid: str = Form(...), password: str = Form("")):
    """Add a WiFi network to known connections (auto-connect when in range)."""
    try:
        subprocess.run(["nmcli", "con", "delete", ssid],
                       capture_output=True)  # ignore if not found
        cmd = ["nmcli", "con", "add", "type", "wifi",
               "con-name", ssid, "ssid", ssid,
               "connection.autoconnect", "yes"]
        if password:
            cmd += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password]
        subprocess.run(cmd, check=True, capture_output=True)
        return JSONResponse({"status": "ok", "message": f"Réseau \"{ssid}\" ajouté"})
    except subprocess.CalledProcessError as e:
        return JSONResponse({"status": "error", "message": e.stderr.decode()},
                            status_code=500)
