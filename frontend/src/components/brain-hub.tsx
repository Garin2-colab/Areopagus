"use client";

import React, { useRef, useState, useMemo } from "react";
import {
  Upload,
  Trash2,
  Loader2,
  Image as ImageIcon,
  FileText,
  FileArchive,
  Search,
  AlertCircle,
  Brain,
  ChevronDown,
  RefreshCw,
} from "lucide-react";
import type { BrainItem, InspirationItem } from "@/lib/history";
import { Button } from "@/components/ui/button";
import { compressImage } from "@/lib/utils";

type BrainHubProps = {
  brain: BrainItem[];
  inspiration: InspirationItem[];
  onRefresh: () => Promise<void>;
  onImageClick: (url: string) => void;
};

type FilterType = "all" | "image" | "note" | "reference";

export function BrainHub({ brain, inspiration, onRefresh, onImageClick }: BrainHubProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<FilterType>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Merge brain items with legacy inspiration items (shown as references)
  const allItems = useMemo(() => {
    const brainItems: (BrainItem & { _source: "brain" })[] = brain.map((b) => ({
      ...b,
      _source: "brain" as const,
    }));

    const legacyItems: (BrainItem & { _source: "brain" })[] = inspiration.map((insp) => ({
      id: insp.id,
      type: "reference" as const,
      source_file: "",
      title: insp.id,
      keywords: insp.keywords,
      summary: "",
      mood: "",
      color_palette: [],
      excerpt: "",
      image_url: insp.image_url,
      created_at: insp.created_at,
      updated_at: insp.created_at,
      _source: "brain" as const,
    }));

    return [...brainItems, ...legacyItems].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );
  }, [brain, inspiration]);

  // Filter and search
  const filteredItems = useMemo(() => {
    let items = allItems;

    if (activeFilter !== "all") {
      items = items.filter((item) => item.type === activeFilter);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      items = items.filter(
        (item) =>
          item.title?.toLowerCase().includes(q) ||
          item.summary?.toLowerCase().includes(q) ||
          item.keywords?.some((k) => k.toLowerCase().includes(q)) ||
          item.mood?.toLowerCase().includes(q)
      );
    }

    return items;
  }, [allItems, activeFilter, searchQuery]);

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleSync = async () => {
    setIsSyncing(true);
    setUploadError(null);
    setSyncMessage(null);

    try {
      const response = await fetch("/api/sync-brain", {
        method: "POST",
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `Sync failed with status ${response.status}`);
      }

      const result = await response.json();
      if (!result.ok) {
        throw new Error(result.error || "Sync was not successful.");
      }

      const msg = `Synced: ${result.downloaded} downloaded, ${result.skipped} already local${result.failed ? `, ${result.failed} failed` : ""}`;
      setSyncMessage(msg);
      setTimeout(() => setSyncMessage(null), 6000);

      await onRefresh();
    } catch (error) {
      console.error("Sync error:", error);
      setUploadError(error instanceof Error ? error.message : "Sync failed.");
    } finally {
      setIsSyncing(false);
    }
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadError(null);

    try {
      const base64Data = await compressImage(file);

      const response = await fetch("/api/upload-inspiration", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
          /* ignore */
        }
        throw new Error(errMsg);
      }

      const result = await response.json();
      if (!result.ok) {
        throw new Error(result.error || "Upload was not successful.");
      }

      await onRefresh();
    } catch (error) {
      console.error("Upload error:", error);
      setUploadError(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDelete = async (id: string, isLegacy: boolean) => {
    if (!confirm("Delete this item from the Second Brain?")) return;

    setDeletingId(id);
    setUploadError(null);

    try {
      const endpoint = isLegacy ? "/api/delete-inspiration" : "/api/delete-brain-item";
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `Deletion failed with status ${response.status}`);
      }

      const result = await response.json();
      if (!result.ok) {
        throw new Error(result.error || "Deletion was not successful.");
      }

      if (expandedId === id) setExpandedId(null);
      await onRefresh();
    } catch (error) {
      console.error("Delete error:", error);
      setUploadError(error instanceof Error ? error.message : "Failed to delete.");
    } finally {
      setDeletingId(null);
    }
  };

  const filterCounts = useMemo(() => {
    const counts = { all: allItems.length, image: 0, note: 0, reference: 0 };
    for (const item of allItems) {
      if (item.type === "image") {
        counts.image++;
      } else if (item.type === "note") {
        counts.note++;
      } else if (item.type === "reference") {
        counts.reference++;
      }
    }
    return counts;
  }, [allItems]);

  const typeIcon = (type: string) => {
    if (type === "note") return <FileText className="h-3.5 w-3.5" />;
    if (type === "reference") return <FileArchive className="h-3.5 w-3.5" />;
    return <ImageIcon className="h-3.5 w-3.5" />;
  };

  const typeLabel = (type: string) => {
    return type.charAt(0).toUpperCase() + type.slice(1);
  };

  return (
    <div className="space-y-5">
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept="image/*,.md,.txt,.pdf"
        className="hidden"
      />

      {/* Header Bar */}
      <div className="flex flex-col gap-4 rounded-2xl border border-[#D8D4CC]/60 bg-[#FAF9F6] p-4 md:p-5 shadow-sm shadow-[#252422]/5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Brain className="h-5 w-5 text-[#D45113]" />
            <div>
              <h3 className="text-base font-semibold text-[#252422]">Second Brain</h3>
              <p className="text-[10px] text-[#858076] mt-0.5">
                Drop images, notes, and references to expand the collective memory of autonomous agents.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {(isUploading || isSyncing) && (
              <div className="flex items-center gap-2 text-xs font-semibold text-[#D45113]">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>{isSyncing ? "Syncing..." : "Analyzing..."}</span>
              </div>
            )}
            <Button
              type="button"
              onClick={handleSync}
              disabled={isUploading || isSyncing}
              className="flex items-center gap-2 rounded-full border border-[#D8D4CC] bg-white hover:bg-[#F5F2EB] text-[#44423E] font-semibold text-xs h-9 px-4 shadow-sm transition-all"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isSyncing ? "animate-spin" : ""}`} />
              <span>Sync</span>
            </Button>
            <Button
              type="button"
              onClick={handleUploadClick}
              disabled={isUploading || isSyncing}
              className="flex items-center gap-2 rounded-full bg-[#D45113] hover:bg-[#b0400d] text-[#FAF9F6] font-semibold text-xs h-9 px-4 shadow-sm transition-all"
            >
              <Upload className="h-3.5 w-3.5" />
              <span>Upload</span>
            </Button>
          </div>
        </div>

        {/* Search + Filters */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#858076]" />
            <input
              type="text"
              placeholder="Search brain..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-xl border border-[#D8D4CC] bg-white py-2 pl-9 pr-3 text-xs text-[#252422] placeholder:text-[#858076]/60 focus:border-[#D45113] focus:outline-none focus:ring-1 focus:ring-[#D45113]/30 transition-colors"
            />
          </div>

          <div className="flex items-center gap-1.5">
            {(["all", "image", "note", "reference"] as FilterType[]).map((filter) => (
              <button
                key={filter}
                onClick={() => setActiveFilter(filter)}
                className={`rounded-lg px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-wider transition-all ${
                  activeFilter === filter
                    ? "bg-[#252422] text-[#FAF9F6]"
                    : "text-[#858076] hover:bg-[#F5F2EB] hover:text-[#44423E]"
                }`}
              >
                {filter === "all" ? "All" : filter.charAt(0).toUpperCase() + filter.slice(1)}
                <span className="ml-1 opacity-60">{filterCounts[filter]}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {uploadError && (
        <div className="flex items-center gap-1.5 text-xs font-semibold text-rose-600 animate-in fade-in duration-200">
          <AlertCircle className="h-4 w-4" />
          <span>{uploadError}</span>
        </div>
      )}

      {syncMessage && (
        <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600 animate-in fade-in duration-200">
          <RefreshCw className="h-3.5 w-3.5" />
          <span>{syncMessage}</span>
        </div>
      )}

      {/* Card Grid */}
      {filteredItems.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-[#858076]">
          <Brain className="h-10 w-10 text-[#858076]/40 stroke-[1.5] mb-3" />
          <p className="text-sm font-medium">
            {searchQuery ? "No items match your search." : "Your Second Brain is empty."}
          </p>
          <p className="text-xs text-[#858076]/80 mt-1 max-w-sm text-center">
            {searchQuery
              ? "Try different keywords or clear the search."
              : "Drop images into brain/images/ and run sync_brain.py, or upload directly."}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {filteredItems.map((item) => {
            const isLegacy = item.id.startsWith("insp_");
            const isExpanded = expandedId === item.id;
            const hasImage = (item.type === "image" || (item.type === "reference" && item.image_url)) && item.image_url;

            return (
              <div
                key={item.id}
                className={`group relative rounded-2xl border transition-all duration-200 overflow-hidden ${
                  isExpanded
                    ? "col-span-2 row-span-2 border-[#D45113]/40 shadow-md shadow-[#D45113]/10 bg-[#FAF9F6]"
                    : "border-[#D8D4CC]/60 bg-[#FAF9F6] hover:border-[#D8D4CC] hover:shadow-sm"
                }`}
              >
                {/* Thumbnail / Icon */}
                <div
                  onClick={() => {
                    if (hasImage) {
                      if (isExpanded) {
                        onImageClick(item.image_url);
                      } else {
                        setExpandedId(isExpanded ? null : item.id);
                      }
                    } else {
                      setExpandedId(isExpanded ? null : item.id);
                    }
                  }}
                  className="cursor-pointer"
                >
                  {hasImage ? (
                    <div className={`relative overflow-hidden ${isExpanded ? "aspect-[4/3]" : "aspect-square"}`}>
                      <img
                        src={item.image_url}
                        alt={item.title || "Brain item"}
                        className="h-full w-full object-contain bg-[#F5F2EB]"
                      />
                      {/* Type badge */}
                      <div className="absolute top-2 left-2 flex items-center gap-1 rounded-full bg-[#252422]/70 px-2 py-0.5 text-[9px] font-semibold text-[#FAF9F6] backdrop-blur-sm">
                        {typeIcon(item.type)}
                        <span>{typeLabel(item.type)}</span>
                      </div>
                    </div>
                  ) : (
                    <div
                      className={`flex flex-col items-center justify-center bg-[#F5F2EB] ${
                        isExpanded ? "aspect-[4/3]" : "aspect-square"
                      }`}
                    >
                      {item.type === "note" ? (
                        <FileText className="h-10 w-10 text-[#858076]/40 stroke-[1.5]" />
                      ) : (
                        <FileArchive className="h-10 w-10 text-[#858076]/40 stroke-[1.5]" />
                      )}
                      <span className="mt-2 text-[10px] font-semibold text-[#858076]/60 uppercase tracking-wider">
                        {item.type}
                      </span>
                    </div>
                  )}
                </div>

                {/* Card Footer */}
                <div className="p-3 space-y-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <h4
                      className="text-xs font-semibold text-[#252422] line-clamp-1 cursor-pointer"
                      onClick={() => setExpandedId(isExpanded ? null : item.id)}
                    >
                      {item.title || item.id}
                    </h4>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(item.id, isLegacy);
                      }}
                      disabled={deletingId === item.id}
                      className="h-6 w-6 shrink-0 text-[#858076]/40 hover:text-red-600 hover:bg-red-50 rounded-full transition-colors opacity-0 group-hover:opacity-100"
                    >
                      {deletingId === item.id ? (
                        <Loader2 className="h-3 w-3 animate-spin text-[#D45113]" />
                      ) : (
                        <Trash2 className="h-3 w-3" />
                      )}
                    </Button>
                  </div>

                  {/* Keywords */}
                  <div className="flex flex-wrap gap-1">
                    {(item.keywords || []).slice(0, isExpanded ? 20 : 3).map((kw) => (
                      <span
                        key={kw}
                        className="rounded-full bg-[#D45113]/8 px-1.5 py-0.5 text-[9px] font-semibold text-[#D45113]"
                      >
                        {kw}
                      </span>
                    ))}
                    {!isExpanded && (item.keywords?.length || 0) > 3 && (
                      <span className="text-[9px] text-[#858076]">+{item.keywords.length - 3}</span>
                    )}
                  </div>

                  {/* Expanded Detail */}
                  {isExpanded && (
                    <div className="mt-3 space-y-2 animate-in fade-in slide-in-from-top-2 duration-200">
                      {item.summary && (
                        <p className="text-[11px] text-[#44423E] leading-relaxed">{item.summary}</p>
                      )}
                      {item.mood && (
                        <p className="text-[10px] text-[#858076] italic">Mood: {item.mood}</p>
                      )}
                      {item.color_palette && item.color_palette.length > 0 && (
                        <div className="flex items-center gap-1">
                          {item.color_palette.map((color, idx) => (
                            <div
                              key={idx}
                              className="h-4 w-4 rounded-full border border-[#D8D4CC]/60"
                              style={{ backgroundColor: color }}
                              title={color}
                            />
                          ))}
                        </div>
                      )}
                      {item.source_file && (
                        <p className="text-[9px] text-[#858076]/60 font-mono">
                          {item.source_file}
                        </p>
                      )}
                      <p className="text-[9px] text-[#858076]/60">
                        {new Date(item.created_at).toLocaleString(undefined, {
                          dateStyle: "medium",
                          timeStyle: "short",
                        })}
                      </p>
                    </div>
                  )}

                  {/* Expand indicator */}
                  {!isExpanded && (item.summary || item.mood) && (
                    <button
                      onClick={() => setExpandedId(item.id)}
                      className="flex items-center gap-0.5 text-[9px] text-[#858076]/60 hover:text-[#D45113] transition-colors"
                    >
                      <ChevronDown className="h-3 w-3" />
                      <span>Details</span>
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
