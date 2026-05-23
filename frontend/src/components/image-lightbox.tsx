"use client";

import { X, Download } from "lucide-react";
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

  const handleDownload = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!src) return;
    try {
      const response = await fetch(src);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      
      // Determine file name from target parameter or default
      const urlObj = new URL(src, window.location.origin);
      const id = urlObj.searchParams.get("id") || "areopagus_image";
      a.download = `${id}.webp`;
      
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      // Fallback: open direct asset link in a new window tab
      window.open(src, "_blank", "noopener,noreferrer");
    }
  };

  if (!src) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#F5F2EB]/95 p-4 backdrop-blur-md animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="relative max-h-[90vh] max-w-[90vw] overflow-hidden rounded-2xl border border-[#D8D4CC] bg-white/40 shadow-2xl shadow-[#252422]/10 animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()} // Prevent close on clicking the image itself
      >
        <div className="absolute right-4 top-4 flex items-center gap-2 z-50">
          <button
            onClick={handleDownload}
            className="rounded-full border border-[#D8D4CC] bg-[#FAF9F6]/90 p-2 text-[#44423E] hover:text-[#252422] hover:bg-white transition-colors shadow-md backdrop-blur-sm"
            aria-label="Download image"
            title="Download image"
          >
            <Download className="h-4.5 w-4.5" />
          </button>
          
          <button
            onClick={onClose}
            className="rounded-full border border-[#D8D4CC] bg-[#FAF9F6]/90 p-2 text-[#44423E] hover:text-[#252422] hover:bg-white transition-colors shadow-md backdrop-blur-sm"
            aria-label="Close image preview"
            title="Close preview"
          >
            <X className="h-4.5 w-4.5" />
          </button>
        </div>

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
