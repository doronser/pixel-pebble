"use client";

import { useCallback, useEffect, useState } from "react";
import Cropper, { type Area } from "react-easy-crop";
import styles from "./pixel-ui.module.css";
import PixelButton from "./PixelButton";
import { cropToBlob } from "@/lib/cropImage";

export default function UploadForm({
  initialGuidance = "",
  submitLabel = "▶ GENERATE AVATAR",
  sourceJobId,
  onJobCreated,
}: {
  initialGuidance?: string;
  submitLabel?: string;
  /** Regenerate from this job's already-cropped photo unless the user picks a new one. */
  sourceJobId?: string;
  onJobCreated: (jobId: string) => void;
}) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [cropArea, setCropArea] = useState<Area | null>(null);
  const [reusePhoto, setReusePhoto] = useState(Boolean(sourceJobId));
  const [dragging, setDragging] = useState(false);
  const [guidance, setGuidance] = useState(initialGuidance);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pickFile = useCallback((file: File | null | undefined) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("That's not an image — try a JPEG or PNG.");
      return;
    }
    setError(null);
    setReusePhoto(false);
    setCrop({ x: 0, y: 0 });
    setZoom(1);
    setImageUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return URL.createObjectURL(file);
    });
  }, []);

  // Paste an image from the clipboard anywhere on the page.
  useEffect(() => {
    function onPaste(e: ClipboardEvent) {
      const item = Array.from(e.clipboardData?.items ?? []).find((i) => i.type.startsWith("image/"));
      if (item) pickFile(item.getAsFile());
    }
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [pickFile]);

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    pickFile(e.dataTransfer.files?.[0]);
  }

  function clearPhoto() {
    setImageUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return null;
    });
    setCropArea(null);
    setReusePhoto(false);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      let res: Response;
      if (reusePhoto && sourceJobId) {
        const body = new FormData();
        body.set("guidance", guidance);
        res = await fetch(`/api/jobs/${sourceJobId}/regenerate`, { method: "POST", body });
      } else {
        if (!imageUrl || !cropArea) {
          setError("Pick a photo first.");
          setSubmitting(false);
          return;
        }
        const blob = await cropToBlob(imageUrl, cropArea);
        const body = new FormData();
        body.set("photo", blob, "photo.jpg");
        body.set("guidance", guidance);
        res = await fetch("/api/generate-avatar", { method: "POST", body });
      }
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail || "Upload failed");
      }
      const data = await res.json();
      onJobCreated(data.job_id);
    } catch (err) {
      setError(err instanceof Error && err.message !== "Upload failed" ? err.message : "Something went wrong — try again.");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      {reusePhoto && sourceJobId ? (
        <div className={styles.cropWrap}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`/api/jobs/${sourceJobId}/source.jpg`} alt="Your photo" className={styles.sourceThumb} />
          <PixelButton variant="ghost" onClick={clearPhoto}>
            use a different photo
          </PixelButton>
        </div>
      ) : imageUrl ? (
        <div className={styles.cropWrap}>
          <div className={styles.cropArea}>
            <Cropper
              image={imageUrl}
              crop={crop}
              zoom={zoom}
              maxZoom={5}
              aspect={1}
              showGrid
              onCropChange={setCrop}
              onZoomChange={setZoom}
              onCropComplete={(_, pixels) => setCropArea(pixels)}
              onMediaLoaded={() => setError(null)}
              mediaProps={{
                onError: () => {
                  clearPhoto();
                  setError("Your browser can't open that image format — try a JPEG or PNG.");
                },
              }}
            />
          </div>
          <label className={styles.zoomRow}>
            <span>ZOOM</span>
            <input
              type="range"
              min={1}
              max={5}
              step={0.05}
              value={zoom}
              onChange={(e) => setZoom(Number(e.target.value))}
            />
          </label>
          <div className={styles.cropHint}>drag &amp; pinch to frame your watchface</div>
          <PixelButton variant="ghost" onClick={clearPhoto}>
            choose a different photo
          </PixelButton>
        </div>
      ) : (
        <label
          className={`${styles.dropzone} ${dragging ? styles.dropzoneActive : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <div className={styles.dropzoneIcon}>📷</div>
          <div>
            TAP TO UPLOAD
            <br />
            OR TAKE A PHOTO
          </div>
          <div className={styles.cropHint}>or drop / paste an image</div>
          <input type="file" accept="image/*" onChange={(e) => pickFile(e.target.files?.[0])} />
        </label>
      )}

      <label className={styles.fieldLabel} htmlFor="guidance">
        ADD GUIDANCE (OPTIONAL)
      </label>
      <input
        id="guidance"
        className={styles.guidance}
        placeholder="e.g. make me a wizard..."
        value={guidance}
        maxLength={200}
        onChange={(e) => setGuidance(e.target.value)}
      />

      {error && <div className={styles.errorBox}>{error}</div>}

      <PixelButton type="submit" disabled={submitting || (!reusePhoto && !imageUrl)}>
        {submitting ? "UPLOADING..." : submitLabel}
      </PixelButton>
    </form>
  );
}
