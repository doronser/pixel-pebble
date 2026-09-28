import json
import shutil
import uuid
from pathlib import Path

import qrcode
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse, FileResponse, Response, RedirectResponse

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


@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <html><body style="font-family: sans-serif; max-width: 480px; margin: 40px auto;">
    <h2>Pixel Pebble</h2>
    <p>Upload a photo. Get back an 8-bit avatar watchface for your Pebble Time 2.</p>
    <form action="/generate" method="post" enctype="multipart/form-data">
      <input type="file" name="photo" accept="image/*" required>
      <button type="submit">Generate</button>
    </form>
    </body></html>
    """


@app.post("/generate")
async def generate(photo: UploadFile = File(...)):
    job_id = uuid.uuid4().hex[:12]

    upload_path = UPLOADS / f"{job_id}{Path(photo.filename or 'photo.jpg').suffix or '.jpg'}"
    with open(upload_path, "wb") as f:
        shutil.copyfileobj(photo.file, f)

    # Build the project in a staging dir the builder's glob can't see (leading
    # dot), then atomically rename it into the queue as the last step. The
    # builder polls every 2s and deletes whatever it finds once processed —
    # without this staging step it can grab (and delete) a job the app is
    # still in the middle of writing, especially once the Kling call above
    # adds real network latency.
    staging_dir = QUEUE / f".building-{job_id}"
    job_dir = QUEUE / job_id
    shutil.copytree(TEMPLATE, staging_dir)

    styled_path = STORAGE / job_id
    styled_path.mkdir(parents=True, exist_ok=True)
    raw_for_pixelize = upload_path
    source_is_stylized = False

    try:
        stylized_path = styled_path / "stylized.png"
        kling.stylize(str(upload_path), str(stylized_path))
        raw_for_pixelize = stylized_path
        source_is_stylized = True
    except kling.KlingUnavailable:
        pass  # demo/fallback mode: pixelize the raw photo directly

    preview_path = styled_path / "preview.png"
    pixelize(str(raw_for_pixelize), str(preview_path), AVATAR_BOX, source_is_stylized=source_is_stylized)
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
    # the app must not create it, or the builder's "already processed" check
    # (which keys off status.json existing) would skip the job forever.

    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


def read_status(job_id: str) -> dict:
    status_file = STORAGE / job_id / "status.json"
    if not status_file.exists():
        return {"state": "unknown"}
    return json.loads(status_file.read_text())


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_status(job_id: str, request: Request):
    status = read_status(job_id)
    state = status.get("state", "unknown")

    if state == "done":
        download_url = f"{public_base_url(request)}/jobs/{job_id}/download"
        return f"""
        <html><body style="font-family: sans-serif; max-width: 480px; margin: 40px auto; text-align: center;">
        <h2>Your watchface is ready!</h2>
        <img src="/jobs/{job_id}/preview.png" width="160" style="image-rendering: pixelated; border: 4px solid #222;">
        <p><img src="/jobs/{job_id}/qr.png" width="200"></p>
        <p>Scan the QR code on your phone, or <a href="{download_url}">download the .pbw</a> directly.</p>
        <p>Install: open the official <b>Pebble</b> (Android) / <b>Pebble Core</b> (iOS) app,
        enable Developer Mode &rarr; Developer Connection, then open the downloaded file,
        or run <code>pebble install --cloudpebble</code> from a dev machine after <code>pebble login</code>.</p>
        </body></html>
        """
    if state == "error":
        return f"<html><body><h2>Build failed</h2><pre>{status.get('message', '')}</pre></body></html>"

    return f"""
    <html><head><meta http-equiv="refresh" content="3"></head>
    <body style="font-family: sans-serif; max-width: 480px; margin: 40px auto; text-align: center;">
    <h2>Building your watchface...</h2>
    <p>State: {state}</p>
    </body></html>
    """


@app.get("/jobs/{job_id}/preview.png")
def job_preview(job_id: str):
    return FileResponse(STORAGE / job_id / "preview.png")


@app.get("/jobs/{job_id}/download")
def job_download(job_id: str):
    pbw_path = STORAGE / job_id / "watchface.pbw"
    return FileResponse(pbw_path, media_type="application/octet-stream", filename=f"{job_id}.pbw")


@app.get("/jobs/{job_id}/qr.png")
def job_qr(job_id: str, request: Request):
    url = f"{public_base_url(request)}/jobs/{job_id}/download"
    img = qrcode.make(url)
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
