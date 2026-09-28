import json
import shutil
import uuid
from io import BytesIO
from pathlib import Path

import qrcode
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, Response

from pixelize import pixelize, extract_accent_color
import kling

BASE = Path("/data")
UPLOADS = BASE / "uploads"
STORAGE = BASE / "storage"
QUEUE = BASE / "build-queue"
TEMPLATE = Path("/watchface-template")

AVATAR_BOX = 160

for d in (UPLOADS, STORAGE, QUEUE):
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI()


def public_base_url(request: Request) -> str:
    # Traefik terminates TLS; trust its forwarded proto/host.
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host"))
    return f"{proto}://{host}"


def read_json(path: Path) -> dict:
    if not path.exists():
        return {"state": "unknown"}
    return json.loads(path.read_text())


@app.post("/api/generate-avatar")
async def generate_avatar(photo: UploadFile = File(...), guidance: str = Form("")):
    """Phase 1: upload + style. Produces a reviewable avatar preview but does
    NOT queue a watchface build yet — that only happens once the user
    confirms via /api/jobs/{id}/build."""
    job_id = uuid.uuid4().hex[:12]

    upload_path = UPLOADS / f"{job_id}{Path(photo.filename or 'photo.jpg').suffix or '.jpg'}"
    with open(upload_path, "wb") as f:
        shutil.copyfileobj(photo.file, f)

    styled_path = STORAGE / job_id
    styled_path.mkdir(parents=True, exist_ok=True)
    avatar_status_file = styled_path / "avatar_status.json"
    avatar_status_file.write_text(json.dumps({"state": "generating"}))

    raw_for_pixelize = upload_path
    source_is_stylized = False

    try:
        stylized_path = styled_path / "stylized.png"
        kling.stylize(str(upload_path), str(stylized_path), guidance=guidance or None)
        raw_for_pixelize = stylized_path
        source_is_stylized = True
    except kling.KlingUnavailable:
        pass  # demo/fallback mode: pixelize the raw photo directly
    except Exception as e:
        avatar_status_file.write_text(json.dumps({"state": "error", "message": str(e)}))
        return {"job_id": job_id}

    preview_path = styled_path / "preview.png"
    pixelize(str(raw_for_pixelize), str(preview_path), AVATAR_BOX, source_is_stylized=source_is_stylized)

    avatar_status_file.write_text(json.dumps({"state": "ready"}))
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}/avatar-status")
def avatar_status(job_id: str):
    return read_json(STORAGE / job_id / "avatar_status.json")


@app.get("/api/jobs/{job_id}/preview.png")
def job_preview(job_id: str):
    return FileResponse(STORAGE / job_id / "preview.png")


@app.post("/api/jobs/{job_id}/build")
def build_watchface(job_id: str):
    """Phase 2: the user confirmed the avatar — copy the template, bake in
    the avatar image + accent color, and hand it to the builder container."""
    styled_path = STORAGE / job_id
    preview_path = styled_path / "preview.png"

    # Build the project in a staging dir the builder's glob can't see (leading
    # dot), then atomically rename it into the queue as the last step. The
    # builder polls every 2s and deletes whatever it finds once processed —
    # without this staging step it can grab (and delete) a job we're still
    # in the middle of writing.
    staging_dir = QUEUE / f".building-{job_id}"
    job_dir = QUEUE / job_id
    shutil.copytree(TEMPLATE, staging_dir)

    shutil.copy(preview_path, staging_dir / "resources" / "images" / "avatar.png")
    accent_r, accent_g, accent_b = extract_accent_color(str(preview_path))

    pkg_template = (TEMPLATE / "package.json.template").read_text()
    watch_uuid = str(uuid.uuid4())
    pkg = pkg_template.replace("{{NAME}}", f"avatar-{job_id}") \
                       .replace("{{DISPLAY_NAME}}", "My Pixel Avatar") \
                       .replace("{{UUID}}", watch_uuid)
    (staging_dir / "package.json").write_text(pkg)
    (staging_dir / "package.json.template").unlink(missing_ok=True)

    main_c_template = (TEMPLATE / "src" / "c" / "main.c.template").read_text()
    main_c = main_c_template.replace("{{TIME_COLOR}}", f"GColorFromRGB({accent_r}, {accent_g}, {accent_b})")
    (staging_dir / "src" / "c" / "main.c").write_text(main_c)
    (staging_dir / "src" / "c" / "main.c.template").unlink(missing_ok=True)

    staging_dir.rename(job_dir)

    # status.json is created by the builder container once it picks the job up;
    # we must not create it here, or the builder's "already processed" check
    # (which keys off status.json existing) would skip the job forever.

    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}/status")
def job_status(job_id: str):
    return read_json(STORAGE / job_id / "status.json")


@app.get("/api/jobs/{job_id}/screenshot.png")
def job_screenshot(job_id: str):
    screenshot_path = STORAGE / job_id / "screenshot.png"
    if screenshot_path.exists():
        return FileResponse(screenshot_path)
    return FileResponse(STORAGE / job_id / "preview.png")


@app.get("/api/jobs/{job_id}/download")
def job_download(job_id: str):
    pbw_path = STORAGE / job_id / "watchface.pbw"
    return FileResponse(pbw_path, media_type="application/octet-stream", filename=f"{job_id}.pbw")


@app.get("/api/jobs/{job_id}/qr.png")
def job_qr(job_id: str, request: Request):
    url = f"{public_base_url(request)}/api/jobs/{job_id}/download"
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
