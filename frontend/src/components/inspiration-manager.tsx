"use client";

import React, { useRef, useState } from "react";
import { Upload, Trash2, Loader2, Image as ImageIcon, AlertCircle } from "lucide-react";
import type { InspirationItem } from "@/lib/history";
import { Button } from "@/components/ui/button";
import { compressImage } from "@/lib/utils";

type InspirationManagerProps = {
  inspiration: InspirationItem[];
  onRefresh: () => Promise<void>;
  onImageClick: (url: string) => void;
};

export function InspirationManager({ inspiration, onRefresh, onImageClick }: InspirationManagerProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadError(null);

    try {
      // 1. Compress file client-side to keep payload size optimal
      const base64Data = await compressImage(file);

      // 2. Post to Next.js API route
      const response = await fetch("/api/upload-inspiration", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          image_base64: base64Data,
          mime_type: "image/jpeg",
        }),
      });

      if (!response.ok) {
        let errMsg = `Upload failed with status ${response.status}`;
        try {
          const errorData = await response.json();
          errMsg = errorData.error || errMsg;
        } catch {
          try {
            const txt = await response.text();
            if (txt && txt.length < 200) {
              errMsg = txt;
            }
          } catch {}
        }
        throw new Error(errMsg);
      }

      const result = await response.json();
      if (!result.ok) {
        throw new Error(result.error || "Inspiration upload was not successful.");
      }

      // 3. Refresh parent data
      await onRefresh();
    } catch (error) {
      console.error("Upload error:", error);
      setUploadError(error instanceof Error ? error.message : "Inspiration upload failed.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this inspiration item?")) {
      return;
    }

    setDeletingId(id);
    setUploadError(null);

    try {
      const response = await fetch("/api/delete-inspiration", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ id }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `Deletion failed with status ${response.status}`);
      }

      const result = await response.json();
      if (!result.ok) {
        throw new Error(result.error || "Inspiration deletion was not successful.");
      }

      await onRefresh();
    } catch (error) {
      console.error("Delete error:", error);
      setUploadError(error instanceof Error ? error.message : "Failed to delete inspiration.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept="image/*"
        className="hidden"
      />

      {/* Control / Upload Bar */}
      <div className="flex flex-col items-center justify-between gap-4 rounded-2xl border border-[#D8D4CC]/60 bg-[#FAF9F6] p-4 md:flex-row md:p-5 shadow-sm shadow-[#252422]/5">
        <div className="space-y-1">
          <h3 className="text-base font-semibold text-[#252422]">Inspiration Board</h3>
          <p className="text-xs text-[#858076]">
            Upload image references to expand the visual memory of autonomous agents and connect concepts on the Knowledge Web.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {isUploading && (
            <div className="flex items-center gap-2 text-xs font-semibold text-[#D45113]">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Analyzing & Extracting Keywords...</span>
            </div>
          )}

          <Button
            type="button"
            onClick={handleUploadClick}
            disabled={isUploading}
            className="flex items-center gap-2 rounded-full bg-[#D45113] hover:bg-[#b0400d] text-[#FAF9F6] font-semibold text-xs h-10 px-5 shadow-sm transition-all"
          >
            <Upload className="h-3.5 w-3.5" />
            <span>Upload Reference</span>
          </Button>
        </div>
      </div>

      {uploadError && (
        <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-800 animate-in fade-in duration-200">
          <AlertCircle className="h-4 w-4 text-red-600" />
          <span>{uploadError}</span>
        </div>
      )}

      {/* Table grid container */}
      <div className="overflow-hidden rounded-2xl border border-[#D8D4CC]/60 bg-[#FAF9F6] shadow-sm shadow-[#252422]/5">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm text-[#44423E]">
            <thead>
              <tr className="border-b border-[#D8D4CC] bg-[#F5F2EB]/60 text-[10px] uppercase tracking-[0.25em] text-[#858076]">
                <th className="py-4 pl-6 pr-3 font-semibold">Preview</th>
                <th className="px-3 py-4 font-semibold">Reference ID</th>
                <th className="px-3 py-4 font-semibold w-1/2">Generated Keywords</th>
                <th className="px-3 py-4 font-semibold">Created At</th>
                <th className="py-4 pl-3 pr-6 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#D8D4CC]/40">
              {inspiration.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-16 text-center text-[#858076]">
                    <div className="flex flex-col items-center justify-center space-y-3">
                      <ImageIcon className="h-8 w-8 text-[#858076]/60 stroke-[1.5]" />
                      <p className="text-sm font-medium">No inspiration reference images uploaded yet.</p>
                      <p className="text-xs text-[#858076]/80 max-w-sm">
                        Use the button above to upload visual assets that AI agents will scan to initiate or pivot debate threads.
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                inspiration.map((item) => (
                  <tr key={item.id} className="hover:bg-[#F5F2EB]/30 transition-colors">
                    {/* Preview Thumbnail */}
                    <td className="py-3 pl-6 pr-3">
                      <div
                        onClick={() => onImageClick(item.image_url)}
                        className="group relative h-14 w-14 cursor-zoom-in overflow-hidden rounded-xl border border-[#D8D4CC] bg-white transition-transform hover:scale-105 active:scale-95"
                      >
                        <img
                          src={item.image_url}
                          alt="Inspiration Preview"
                          className="h-full w-full object-cover"
                        />
                      </div>
                    </td>

                    {/* ID */}
                    <td className="px-3 py-3 font-mono text-xs text-[#252422]">
                      {item.id}
                    </td>

                    {/* Keywords tags */}
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap gap-1.5">
                        {item.keywords && item.keywords.length > 0 ? (
                          item.keywords.map((kw) => (
                            <span
                              key={kw}
                              className="rounded-full bg-[#D45113]/10 px-2.5 py-0.5 text-xs font-semibold text-[#D45113]"
                            >
                              {kw}
                            </span>
                          ))
                        ) : (
                          <span className="text-xs italic text-[#858076]">No keywords generated</span>
                        )}
                      </div>
                    </td>

                    {/* Created date */}
                    <td className="px-3 py-3 text-xs text-[#858076]">
                      {new Date(item.created_at).toLocaleString(undefined, {
                        dateStyle: "medium",
                        timeStyle: "short",
                      })}
                    </td>

                    {/* Action Trash */}
                    <td className="py-3 pl-3 pr-6 text-right">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDelete(item.id)}
                        disabled={deletingId === item.id}
                        className="h-8 w-8 text-[#858076] hover:text-red-600 hover:bg-red-50 rounded-full transition-colors"
                      >
                        {deletingId === item.id ? (
                          <Loader2 className="h-4 w-4 animate-spin text-[#D45113]" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
