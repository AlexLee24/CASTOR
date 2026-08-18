"""
Standalone host for the frontend/ calculator — the CASTOR-side equivalent of the
Flask blueprint Kinder mounts it under.

Its only job is to serve the same three routes Kinder serves, with the same paths
and the same error shape, so frontend/js/etc.js runs unmodified against either
host and a bug reproduced here reproduces there. It holds no physics and no
validation rules of its own: requests go straight into castor.schema and the
result of run_calculation() straight back out.

    python src/castorGUI/server.py            # http://127.0.0.1:8600
"""
import json
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from castor import schema  # noqa: E402
from castor.calculator import run_calculation  # noqa: E402
from castor.batch_calculator import run_batch_calculation  # noqa: E402

def _asset_root() -> Path:
    """Where frontend/ and data/ live at runtime.

    Running from source that is simply this file's directory. Inside a PyInstaller
    bundle the sources are unpacked to a temporary directory it advertises as
    sys._MEIPASS, and __file__ points into the frozen archive instead — so the
    desktop build would serve a 404 for every asset without this.
    """
    bundled = getattr(sys, "_MEIPASS", None)
    return Path(bundled) if bundled else Path(__file__).resolve().parent


FRONTEND_DIR = _asset_root() / "frontend"
PRESETS_PATH = _asset_root() / "data" / "presets.json"
BODY_MARKER = "<!--CASTOR_ETC_BODY-->"

app = FastAPI(title="CASTOR ETC")
app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """Assembles index.html around the shared body partial.

    The substitution exists so etc_body.html can stay a plain, framework-free
    fragment: Kinder pulls the same file in with {% include %}, and neither host
    keeps its own copy of the markup to drift out of step with the other.
    Re-read per request rather than cached, so editing the partial only needs a
    browser refresh.
    """
    shell = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    body = (FRONTEND_DIR / "etc_body.html").read_text(encoding="utf-8")
    return HTMLResponse(shell.replace(BODY_MARKER, body))


@app.get("/api/exposure_time_calculator/presets")
def presets() -> JSONResponse:
    """Thin passthrough of the hardware preset file the Flet GUI also reads."""
    if not PRESETS_PATH.is_file():
        return JSONResponse({"error": "Presets file not found"}, status_code=404)
    return JSONResponse(json.loads(PRESETS_PATH.read_text(encoding="utf-8")))


def _validation_error_response(exc: ValidationError) -> JSONResponse:
    messages = [
        "{}: {}".format(".".join(str(part) for part in err["loc"]), err["msg"])
        for err in exc.errors()
    ]
    return JSONResponse({"error": "; ".join(messages) or "Invalid input"}, status_code=400)


@app.post("/api/exposure_time_calculator")
async def calculate(request: Request) -> JSONResponse:
    data = await request.json()
    try:
        return JSONResponse(run_calculation(schema.ObservationRequest.model_validate(data)).model_dump())
    except ValidationError as exc:
        return _validation_error_response(exc)
    except Exception as exc:  # noqa: BLE001 - a readable message beats a 500 in the UI
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/exposure_time_calculator/batch")
async def calculate_batch(request: Request) -> JSONResponse:
    data = await request.json()
    try:
        return JSONResponse(
            run_batch_calculation(schema.BatchObservationRequest.model_validate(data)).model_dump()
        )
    except ValidationError as exc:
        return _validation_error_response(exc)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=400)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8600)
