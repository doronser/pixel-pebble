"use client";

import { useRouter } from "next/navigation";
import ScreenCard from "@/components/ScreenCard";
import UploadForm from "@/components/UploadForm";

export default function Home() {
  const router = useRouter();

  return (
    <ScreenCard stepLabel="STEP 1 · UPLOAD" title="PIXEL PEBBLE" tagline="turn any photo into a Pebble watchface">
      <UploadForm onJobCreated={(jobId) => router.push(`/jobs/${jobId}`)} />
    </ScreenCard>
  );
}
