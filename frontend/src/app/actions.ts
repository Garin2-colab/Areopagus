"use server";

import { revalidateTag } from "next/cache";

function getMutateUrl() {
  const saveUrl = (process.env.MODAL_SAVE_URL || "").trim();
  const apiUrl = (process.env.MODAL_API_URL || "").trim();
  const statusUrl = (process.env.MODAL_STATUS_URL || "").trim();
  const historyUrl = (process.env.MODAL_HISTORY_URL || "").trim();

  const referenceUrl = saveUrl || apiUrl || statusUrl || historyUrl;
  if (!referenceUrl) {
    return "https://heebok-lee--areopagus-mutate-history-endpoint.modal.run";
  }

  if (referenceUrl.includes("mutate-history-endpoint")) {
    return referenceUrl;
  }

  const match = referenceUrl.match(/https:\/\/([a-zA-Z0-9-]+)--/);
  if (match) {
    const username = match[1];
    return `https://${username}--areopagus-mutate-history-endpoint.modal.run`;
  }

  return "https://heebok-lee--areopagus-mutate-history-endpoint.modal.run";
}

function getModalImageUrl() {
  const saveUrl = (process.env.MODAL_SAVE_URL || "").trim();
  const apiUrl = (process.env.MODAL_API_URL || "").trim();
  const statusUrl = (process.env.MODAL_STATUS_URL || "").trim();
  const historyUrl = (process.env.MODAL_HISTORY_URL || "").trim();

  const referenceUrl = saveUrl || apiUrl || statusUrl || historyUrl;
  if (!referenceUrl) {
    return "https://heebok-lee--areopagus-get-image.modal.run";
  }

  if (referenceUrl.includes("get-image")) {
    return referenceUrl;
  }

  const match = referenceUrl.match(/https:\/\/([a-zA-Z0-9-]+)--/);
  if (match) {
    const username = match[1];
    return `https://${username}--areopagus-get-image.modal.run`;
  }

  return "https://heebok-lee--areopagus-get-image.modal.run";
}

export async function replaceImageAction(imageId: string, base64Data: string, mimeType: string) {
  try {
    const mutateUrl = getMutateUrl();
    const payload = {
      action: "replace_image",
      image_id: imageId,
      image_base64: base64Data,
      mime_type: mimeType
    };

    const response = await fetch(mutateUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      throw new Error(`Modal replace-image endpoint failed with status ${response.status}`);
    }

    const data = await response.json();

    if (data.ok) {
      try {
        revalidateTag("history", "max");
      } catch (err) {
        console.error("Failed to revalidate cache tag:", err);
      }

      const modalImageBase = getModalImageUrl();
      if (modalImageBase) {
        const base = modalImageBase.endsWith("/") ? modalImageBase : `${modalImageBase}/`;
        const v = Math.floor(Date.now() / 1000);
        data.url = `${base}?id=${encodeURIComponent(imageId)}&v=${v}`;
      }
    }

    return data;
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : "Image replacement failed."
    };
  }
}
