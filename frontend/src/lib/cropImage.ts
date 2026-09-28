import type { Area } from "react-easy-crop";

// The server works from a square ~1024px source (Kling is asked for 1:1 and the
// watch shows a 160×160 avatar), so there's no point uploading more than this.
const OUTPUT_SIZE = 1024;

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Could not load image"));
    img.src = src;
  });
}

/** Crop the selected area out of the image and export it as a square JPEG.
 *  Drawing through an <img> also applies EXIF rotation (browsers honor it
 *  by default), so the upload is always upright. */
export async function cropToBlob(src: string, area: Area): Promise<Blob> {
  const img = await loadImage(src);
  const size = Math.min(OUTPUT_SIZE, Math.round(area.width));
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas not supported");
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, area.x, area.y, area.width, area.height, 0, 0, size, size);
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Export failed"))), "image/jpeg", 0.92),
  );
}
