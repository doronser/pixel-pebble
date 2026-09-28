import os
import time
import base64

import requests

KLING_API_KEY = os.environ.get("KLING_API_KEY", "")
KLING_BASE_URL = "https://api-singapore.klingai.com"

# The watchface shows a square avatar, and the web app crops uploads square,
# so ask for square output too. Without this Kling defaults to 16:9 and
# reframes the subject, which pixelize then center-crops away.
ASPECT_RATIO = "1:1"

PROMPT = (
    "Redraw this exact image as 16-bit SNES/Game Boy Color style pixel art. "
    "Preserve the same subject, composition, and framing as the source "
    "photo — do not invent a different subject. Use a limited retro color "
    "palette and crisp pixel-art shading."
)


class KlingUnavailable(Exception):
    pass


def _image_to_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


MAX_GUIDANCE_LEN = 200


def stylize(photo_path: str, output_path: str, guidance: str | None = None) -> None:
    """Send the user's photo to Kling's image-to-image
    endpoint and save the result to output_path. Raises KlingUnavailable if
    no API key is configured, so callers can fall back to a direct-pixelize
    demo mode instead of failing the whole job.

    guidance is optional free text from the user (e.g. "make me a wizard"),
    appended as an additional instruction rather than replacing the base
    prompt — so it can't accidentally undo the "preserve the subject" fix."""
    if not KLING_API_KEY:
        raise KlingUnavailable("KLING_API_KEY not set")

    prompt = PROMPT
    if guidance:
        prompt += " Additional guidance from the user: " + guidance[:MAX_GUIDANCE_LEN]

    # Note: the API's image_reference field is a mode enum ("subject"/"face"),
    # not a second image, so there's no way to pass a separate style image here.
    payload = {
        "model_name": "kling-v3",
        "prompt": prompt,
        "image": _image_to_b64(photo_path),
        "aspect_ratio": ASPECT_RATIO,
    }

    headers = {"Authorization": f"Bearer {KLING_API_KEY}"}

    resp = requests.post(f"{KLING_BASE_URL}/v1/images/generations", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    task_id = resp.json()["data"]["task_id"]

    for _ in range(60):
        time.sleep(2)
        poll = requests.get(f"{KLING_BASE_URL}/v1/images/generations/{task_id}", headers=headers, timeout=30)
        poll.raise_for_status()
        data = poll.json()["data"]
        if data["task_status"] == "succeed":
            image_url = data["task_result"]["images"][0]["url"]
            img_resp = requests.get(image_url, timeout=30)
            img_resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(img_resp.content)
            return
        if data["task_status"] == "failed":
            raise RuntimeError(f"Kling generation failed: {data}")

    raise TimeoutError("Kling generation did not complete in time")
