import json
import re
import shutil
import uuid
from io import BytesIO
from pathlib import Path

import qrcode
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image, UnidentifiedImageError

from pixelize import (
    FRAME_MS,
    center_crop_square,
    extract_accent_color,
    load_oriented,
    make_animation_frames,
    pixelize,
    render_face_mockup,
    save_apng,
)
import kling

BASE = Path("/data")
UPLOADS = BASE / "uploads"
STORAGE = BASE / "storage"
QUEUE = BASE / "build-queue"
TEMPLATE = Path("/watchface-template")
FONT = TEMPLATE / "resources" / "fonts" / "pixel_time.ttf"

AVATAR_BOX = 160
SOURCE_MAX_SIDE = 1024       # the cropper already exports ~1024px; this caps API clients
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
JOB_ID_RE = re.compile(r"^[0-9a-f]{12}$")

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


def job_dir(job_id: str) -> Path:
    if not JOB_ID_RE.match(job_id):
        raise HTTPException(404, "unknown job")
    return STORAGE / job_id


def new_job(guidance: str) -> tuple[str, Path]:
    job_id = uuid.uuid4().hex[:12]
    path = STORAGE / job_id
    path.mkdir(parents=True, exist_ok=True)
    (path / "meta.json").write_text(json.dumps({"guidance": guidance}))
    (path / "avatar_status.json").write_text(json.dumps({"state": "generating"}))
    return job_id, path


def run_generation(job_id: str, guidance: str) -> None:
    """Stylize (Kling) + pixelize + render the web preview. Runs as a
    background task so the slow Kling round-trip doesn't hold the request —
    or, since kling.stylize blocks, the whole event loop — open."""
    path = STORAGE / job_id
    status_file = path / "avatar_status.json"
    source = path / "source.jpg"

    raw_for_pixelize = source
    source_is_stylized = False
    try:
        try:
            stylized_path = path / "stylized.png"
            kling.stylize(str(source), str(stylized_path), guidance=guidance or None)
            raw_for_pixelize = stylized_path
            source_is_stylized = True
        except kling.KlingUnavailable:
            pass  # demo/fallback mode: pixelize the raw photo directly

        preview_path = path / "preview.png"
        pixelize(str(raw_for_pixelize), str(preview_path), AVATAR_BOX, source_is_stylized=source_is_stylized)

        accent = extract_accent_color(str(preview_path))
        frames = make_animation_frames(str(preview_path), seed=job_id)
        render_face_mockup(str(preview_path), str(path / "face.png"), accent, str(FONT), frames=frames)

        status_file.write_text(json.dumps({"state": "ready", "accent": accent}))
    except Exception as e:
        status_file.write_text(json.dumps({"state": "error", "message": str(e)}))


@app.post("/api/generate-avatar")
async def generate_avatar(background: BackgroundTasks, photo: UploadFile = File(...), guidance: str = Form("")):
    """Phase 1: upload + style. Produces a reviewable avatar preview but does
    NOT queue a watchface build yet — that only happens once the user
    confirms via /api/jobs/{id}/build. Returns as soon as the upload is
    saved; the client polls avatar-status for the result."""
    data = await photo.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Photo is too large (20MB max).")

    job_id, path = new_job(guidance)
    upload_path = UPLOADS / f"{job_id}{Path(photo.filename or 'photo.jpg').suffix or '.jpg'}"
    upload_path.write_bytes(data)

    # Normalize once up front: fix EXIF rotation, square it (the web cropper
    # already does, this covers other clients), and cap the size. Kling and
    # pixelize both work from this copy, and regenerate reuses it.
    try:
        img = center_crop_square(load_oriented(str(upload_path)))
    except (UnidentifiedImageError, OSError):
        shutil.rmtree(path, ignore_errors=True)
        raise HTTPException(400, "That file doesn't look like an image we can read.")
    img.thumbnail((SOURCE_MAX_SIDE, SOURCE_MAX_SIDE), Image.LANCZOS)
    img.save(path / "source.jpg", "JPEG", quality=92)

    background.add_task(run_generation, job_id, guidance)
    return {"job_id": job_id}


@app.post("/api/jobs/{job_id}/regenerate")
def regenerate_avatar(job_id: str, background: BackgroundTasks, guidance: str = Form("")):
    """Re-run styling on an existing job's photo with new guidance, as a new
    job (so the old result stays viewable via the back button)."""
    source = job_dir(job_id) / "source.jpg"
    if not source.exists():
        raise HTTPException(404, "original photo not found — upload it again")
    new_id, path = new_job(guidance)
    shutil.copy(source, path / "source.jpg")
    background.add_task(run_generation, new_id, guidance)
    return {"job_id": new_id}


@app.get("/api/jobs/{job_id}/meta")
def job_meta(job_id: str):
    return read_json(job_dir(job_id) / "meta.json")


@app.get("/api/jobs/{job_id}/avatar-status")
def avatar_status(job_id: str):
    return read_json(job_dir(job_id) / "avatar_status.json")


@app.get("/api/jobs/{job_id}/preview.png")
def job_preview(job_id: str):
    return FileResponse(job_dir(job_id) / "preview.png")


@app.get("/api/jobs/{job_id}/source.jpg")
def job_source(job_id: str):
    return FileResponse(job_dir(job_id) / "source.jpg")


@app.post("/api/jobs/{job_id}/build")
def build_watchface(job_id: str):
    """Phase 2: the user confirmed the avatar — copy the template, bake in
    the avatar image, tap animation and accent color, and hand it to the
    builder container."""
    styled_path = job_dir(job_id)
    preview_path = styled_path / "preview.png"
    if not preview_path.exists():
        raise HTTPException(409, "avatar isn't ready yet")

    # Build the project in a staging dir the builder's glob can't see (leading
    # dot), then atomically rename it into the queue as the last step. The
    # builder polls every 2s and deletes whatever it finds once processed —
    # without this staging step it can grab (and delete) a job we're still
    # in the middle of writing.
    staging_dir = QUEUE / f".building-{job_id}"
    queued_dir = QUEUE / job_id
    shutil.rmtree(staging_dir, ignore_errors=True)
    shutil.copytree(TEMPLATE, staging_dir)

    images = staging_dir / "resources" / "images"
    shutil.copy(preview_path, images / "avatar.png")
    frames = make_animation_frames(str(preview_path), seed=job_id)
    save_apng(frames, str(images / "avatar_anim.png"), FRAME_MS, loop=1)
    accent_r, accent_g, accent_b = extract_accent_color(str(preview_path))

    pkg_template = (TEMPLATE / "package.json.template").read_text()
    watch_uuid = str(uuid.uuid4())
    pkg = pkg_template.replace("{{NAME}}", f"avatar-{job_id}") \
                       .replace("{{DISPLAY_NAME}}", "My Pixel Avatar") \
                       .replace("{{UUID}}", watch_uuid)
    (staging_dir / "package.json").write_text(pkg)
    (staging_dir / "package.json.template").unlink(missing_ok=True)

    main_c_template = (TEMPLATE / "src" / "c" / "main.c.template").read_text()
    main_c = main_c_template.replace("{{ACCENT_COLOR}}", f"GColorFromRGB({accent_r}, {accent_g}, {accent_b})")
    (staging_dir / "src" / "c" / "main.c").write_text(main_c)
    (staging_dir / "src" / "c" / "main.c.template").unlink(missing_ok=True)

    staging_dir.rename(queued_dir)

    # status.json is created by the builder container once it picks the job up;
    # we must not create it here, or the builder's "already processed" check
    # (which keys off status.json existing) would skip the job forever.

    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}/status")
def job_status(job_id: str):
    return read_json(job_dir(job_id) / "status.json")


@app.get("/api/jobs/{job_id}/screenshot.png")
def job_screenshot(job_id: str):
    path = job_dir(job_id)
    for name in ("face.png", "screenshot.png", "preview.png"):
        if (path / name).exists():
            return FileResponse(path / name, media_type="image/png")
    raise HTTPException(404, "no preview yet")


@app.get("/api/jobs/{job_id}/download")
def job_download(job_id: str):
    pbw_path = job_dir(job_id) / "watchface.pbw"
    return FileResponse(pbw_path, media_type="application/octet-stream", filename=f"{job_id}.pbw")


@app.get("/api/jobs/{job_id}/qr.png")
def job_qr(job_id: str, request: Request):
    job_dir(job_id)
    url = f"{public_base_url(request)}/api/jobs/{job_id}/download"
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
