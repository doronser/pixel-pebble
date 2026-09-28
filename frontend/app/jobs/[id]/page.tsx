"use client";

import { use, useEffect, useState } from "react";
import ScreenCard from "@/components/ScreenCard";
import PixelButton from "@/components/PixelButton";
import LoadingState from "@/components/LoadingState";
import UploadForm from "@/components/UploadForm";
import styles from "@/components/pixel-ui.module.css";

type Phase = "generating" | "review" | "try-again" | "building" | "done" | "avatar-error" | "build-error";

const GENERATING_MESSAGES = [
  "Mixing 16-bit pixels...",
  "Talking to Kling AI...",
  "Waking up the sprite...",
];

const BUILDING_MESSAGES = [
  "Compiling for Pebble Time 2...",
  "Packing pixels into a .pbw...",
  "Snapping a screenshot...",
];

export default function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [phase, setPhase] = useState<Phase>("generating");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [cacheBust, setCacheBust] = useState(0);

  useEffect(() => {
    if (phase !== "generating") return;
    const interval = setInterval(async () => {
      const res = await fetch(`/api/jobs/${id}/avatar-status`);
      const data = await res.json();
      if (data.state === "ready") {
        setPhase("review");
      } else if (data.state === "error") {
        setErrorMessage(data.message || "Something went wrong.");
        setPhase("avatar-error");
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [phase, id]);

  useEffect(() => {
    if (phase !== "building") return;
    const interval = setInterval(async () => {
      const res = await fetch(`/api/jobs/${id}/status`);
      const data = await res.json();
      if (data.state === "done") {
        setCacheBust(Date.now());
        setPhase("done");
      } else if (data.state === "error") {
        setErrorMessage(data.message || "Build failed.");
        setPhase("build-error");
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [phase, id]);

  async function confirmAvatar() {
    setPhase("building");
    await fetch(`/api/jobs/${id}/build`, { method: "POST" });
  }

  if (phase === "generating") {
    return (
      <ScreenCard stepLabel="STEP 2 · STYLING" title="PIXEL PEBBLE">
        <LoadingState messages={GENERATING_MESSAGES} spriteColor="yellow" />
      </ScreenCard>
    );
  }

  if (phase === "avatar-error") {
    return (
      <ScreenCard stepLabel="STEP 2 · OOPS" title="PIXEL PEBBLE">
        <div className={styles.errorBox}>{errorMessage}</div>
        <PixelButton onClick={() => (window.location.href = "/")}>← START OVER</PixelButton>
      </ScreenCard>
    );
  }

  if (phase === "review") {
    return (
      <ScreenCard stepLabel="STEP 2 · REVIEW" title="PIXEL PEBBLE" tagline="here's your pixel avatar!">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={`/api/jobs/${id}/preview.png`} alt="Your pixel avatar" className={styles.avatarFrame} />
        <PixelButton onClick={confirmAvatar}>✓ LOOKS GREAT</PixelButton>
        <PixelButton variant="secondary" onClick={() => setPhase("try-again")}>
          ↻ TRY AGAIN
        </PixelButton>
      </ScreenCard>
    );
  }

  if (phase === "try-again") {
    return (
      <ScreenCard stepLabel="STEP 2 · RETRY" title="PIXEL PEBBLE" tagline="pick a photo and/or tweak the guidance">
        <UploadForm
          submitLabel="▶ REGENERATE"
          onJobCreated={(newId) => (window.location.href = `/jobs/${newId}`)}
        />
      </ScreenCard>
    );
  }

  if (phase === "building") {
    return (
      <ScreenCard stepLabel="STEP 3 · BUILDING" title="PIXEL PEBBLE">
        <LoadingState messages={BUILDING_MESSAGES} spriteColor="cyan" />
      </ScreenCard>
    );
  }

  if (phase === "build-error") {
    return (
      <ScreenCard stepLabel="STEP 3 · OOPS" title="PIXEL PEBBLE">
        <div className={styles.errorBox}>{errorMessage}</div>
        <PixelButton onClick={() => (window.location.href = "/")}>← START OVER</PixelButton>
      </ScreenCard>
    );
  }

  // done
  return (
    <ScreenCard stepLabel="STEP 4 · INSTALL" title="YOUR WATCHFACE IS READY!">
      <div className={styles.watchFrame}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={`/api/jobs/${id}/screenshot.png?t=${cacheBust}`} alt="Your watchface" />
      </div>
      <div className={styles.qrBox}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={`/api/jobs/${id}/qr.png`} alt="QR code to download" />
      </div>
      <a href={`/api/jobs/${id}/download`} className={`${styles.btn} ${styles.primary} pixel-font`} style={{ display: "block", textDecoration: "none" }}>
        ⬇ DOWNLOAD .PBW
      </a>
      <div className={styles.installSteps}>
        1. Open the official <b>Pebble</b> / <b>Pebble Core</b> app
        <br />
        2. Enable Developer Mode → Dev Connection
        <br />
        3. Open the downloaded file
      </div>
    </ScreenCard>
  );
}
