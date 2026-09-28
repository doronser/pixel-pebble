"use client";

import { useState } from "react";
import styles from "./pixel-ui.module.css";
import PixelButton from "./PixelButton";

export default function UploadForm({
  initialGuidance = "",
  submitLabel = "▶ GENERATE AVATAR",
  onJobCreated,
}: {
  initialGuidance?: string;
  submitLabel?: string;
  onJobCreated: (jobId: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [guidance, setGuidance] = useState(initialGuidance);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    setFile(selected);
    setPreviewUrl(selected ? URL.createObjectURL(selected) : null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Pick a photo first.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const body = new FormData();
      body.set("photo", file);
      body.set("guidance", guidance);
      const res = await fetch("/api/generate-avatar", { method: "POST", body });
      if (!res.ok) throw new Error("Upload failed");
      const data = await res.json();
      onJobCreated(data.job_id);
    } catch {
      setError("Something went wrong — try again.");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <label className={styles.dropzone}>
        {previewUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={previewUrl} alt="Selected photo" className={styles.previewThumb} />
        ) : (
          <>
            <div className={styles.dropzoneIcon}>📷</div>
            <div>TAP TO UPLOAD
              <br />
              OR TAKE A PHOTO
            </div>
          </>
        )}
        <input type="file" accept="image/*" capture="environment" onChange={handleFileChange} />
      </label>

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

      <PixelButton type="submit" disabled={submitting}>
        {submitting ? "GENERATING..." : submitLabel}
      </PixelButton>
    </form>
  );
}
