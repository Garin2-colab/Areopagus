/**
 * Single source of truth for the Modal mutate endpoint URL.
 *
 * Derives the workspace subdomain from whichever MODAL_* URL is configured
 * (MODAL_MUTATE_URL wins if set). The hardcoded fallback preserves the
 * current deployment; set MODAL_MUTATE_URL in env to override it.
 */
export function getMutateUrl(): string {
  const mutateUrl = (process.env.MODAL_MUTATE_URL || "").trim();
  const saveUrl = (process.env.MODAL_SAVE_URL || "").trim();
  const apiUrl = (process.env.MODAL_API_URL || "").trim();
  const statusUrl = (process.env.MODAL_STATUS_URL || "").trim();
  const historyUrl = (process.env.MODAL_HISTORY_URL || "").trim();

  const referenceUrl = mutateUrl || saveUrl || apiUrl || statusUrl || historyUrl;
  if (!referenceUrl) {
    return "https://heebok-lee--areopagus-mutate-history-endpoint.modal.run";
  }

  if (referenceUrl.includes("mutate-history-endpoint")) {
    return referenceUrl;
  }

  const match = referenceUrl.match(/https:\/\/([a-zA-Z0-9-]+)--/);
  if (match) {
    return `https://${match[1]}--areopagus-mutate-history-endpoint.modal.run`;
  }

  return "https://heebok-lee--areopagus-mutate-history-endpoint.modal.run";
}

/**
 * Validates a base64 data-URL / plain-base64 image payload server-side.
 * Returns null when acceptable, or an error message string.
 * Client-side checks are advisory only — this is the real gate.
 */
export function validateImagePayload(imageBase64: unknown): string | null {
  if (typeof imageBase64 !== "string" || imageBase64.length === 0) {
    return "Missing image_base64.";
  }

  // 15M chars of base64 ≈ 11MB binary — well above any legitimate upload
  // (uploads are compressed to ~1200px webp/jpeg client-side).
  if (imageBase64.length > 15_000_000) {
    return "Image too large (limit ~11MB after encoding).";
  }

  let base64Data = imageBase64;
  let declaredMime = "";
  if (imageBase64.startsWith("data:")) {
    const headerMatch = imageBase64.match(/^data:([^;]+);base64,/);
    if (!headerMatch) {
      return "Invalid data URL.";
    }
    declaredMime = headerMatch[1].toLowerCase();
    base64Data = imageBase64.slice(imageBase64.indexOf(",") + 1);
  }

  let buffer: Buffer;
  try {
    buffer = Buffer.from(base64Data, "base64");
  } catch {
    return "image_base64 is not valid base64.";
  }

  if (buffer.length === 0) {
    return "Decoded image is empty.";
  }
  if (buffer.length > 11_000_000) {
    return "Image too large (limit 11MB).";
  }

  // Magic-byte sniffing — the declared MIME type is untrusted.
  const isJpeg = buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff;
  const isPng =
    buffer[0] === 0x89 && buffer[1] === 0x50 && buffer[2] === 0x4e && buffer[3] === 0x47;
  const isWebp =
    buffer.subarray(0, 4).toString("ascii") === "RIFF" &&
    buffer.subarray(8, 12).toString("ascii") === "WEBP";
  const isMp4 = buffer.subarray(4, 8).toString("ascii") === "ftyp";
  const isGif = buffer.subarray(0, 3).toString("ascii") === "GIF";

  if (declaredMime.startsWith("video/") || isMp4) {
    if (!isMp4) {
      return "Video payload must be MP4.";
    }
    return null;
  }

  if (!(isJpeg || isPng || isWebp || isGif)) {
    return "Unsupported image format. Use JPEG, PNG, WebP or GIF.";
  }

  return null;
}
