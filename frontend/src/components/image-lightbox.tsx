"use client";

import { X } from "lucide-react";
import { useEffect } from "react";

type ImageLightboxProps = {
  src: string | null;
  alt?: string;
  onClose: () => void;
};

export function ImageLightbox({ src, alt = "Enlarged view", onClose }: ImageLightboxProps) {
  useEffect(() => {
    if (!src) return;

    // Prevent body scrolling when zoom popup is open
    const originalStyle = window.getComputedStyle(document.body).overflow;
    document.body.style.overflow = "hidden";

    // Handle Escape key closure
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = originalStyle;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [src, onClose]);

  if (!src) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/95 p-4 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={onClose}
    >
      <button
        onClick={onClose}
        className="absolute right-6 top-6 rounded-full border border-zinc-800 bg-zinc-950/85 p-2.5 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 transition-colors z-50"
        aria-label="Close image preview"
      >
        <X className="h-5 w-5" />
      </button>

      <div
        className="relative max-h-[90vh] max-w-[90vw] overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950/20 shadow-2xl animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()} // Prevent close on clicking the image itself
      >
        {/* Using standard img to preserve natural aspect ratio and fit wrapper dynamically */}
        <img
          src={src}
          alt={alt}
          className="max-h-[85vh] max-w-[85vw] object-contain rounded-xl select-none"
        />
      </div>
    </div>
  );
}
