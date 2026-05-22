"use client";

import { X } from "lucide-react";
import Image from "next/image";
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={onClose}
    >
      <button
        onClick={onClose}
        className="absolute right-6 top-6 rounded-full border border-zinc-800 bg-zinc-950/80 p-2.5 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 transition-colors"
        aria-label="Close image preview"
      >
        <X className="h-5 w-5" />
      </button>

      <div
        className="relative max-h-[85vh] max-w-[95vw] overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950/50 shadow-2xl animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()} // Prevent close on clicking the container itself
      >
        <div className="relative aspect-[4/5] w-[80vw] max-w-[600px] md:h-[75vh] md:w-auto">
          <Image
            src={src}
            alt={alt}
            fill
            className="object-contain"
            unoptimized
          />
        </div>
      </div>
    </div>
  );
}
