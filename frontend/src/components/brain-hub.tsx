"use client";

import React, { useRef, useState, useMemo, useEffect, useCallback } from "react";
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
  X,
} from "lucide-react";
import type { BrainItem, BriefItem, InspirationItem } from "@/lib/history";
import { fetchHistory } from "@/lib/history";
import { adminFetch } from "@/lib/admin-client";
import { Button } from "@/components/ui/button";
import { compressImage } from "@/lib/utils";

type BrainHubProps = {
  brain: BrainItem[];
  inspiration: InspirationItem[];
  briefs: BriefItem[];
  totalBrainItems?: number;
  brainTypeCounts?: {
    image: number;
    document: number;
    reference: number;
  };
  onRefresh: () => Promise<void>;
  onImageClick: (url: string) => void;
};

type FilterType = "all" | "image" | "document" | "reference" | "brief";

export function BrainHub({ brain, inspiration, briefs, totalBrainItems, brainTypeCounts, onRefresh, onImageClick }: BrainHubProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<FilterType>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<{ id: string; isLegacy: boolean } | null>(null);
  const [optimisticDeletedIds, setOptimisticDeletedIds] = useState<Set<string>>(new Set());

  // Pagination and local data states
  const [loadedBrain, setLoadedBrain] = useState<BrainItem[]>(brain);
  const [loadedInspiration, setLoadedInspiration] = useState<InspirationItem[]>(inspiration);
  const [totalBrainItemsState, setTotalBrainItemsState] = useState(totalBrainItems ?? brain.length);
  const [brainTypeCountsState, setBrainTypeCountsState] = useState(brainTypeCounts);
  const [offset, setOffset] = useState(brain.length);
  const [isLoading, setIsLoading] = useState(false);
  const [hasMore, setHasMore] = useState(brain.length < (totalBrainItems ?? brain.length));

  // Sync state if props change (e.g. from parent refresh)
  useEffect(() => {
    setLoadedBrain(brain);
    setLoadedInspiration(inspiration);
    setTotalBrainItemsState(totalBrainItems ?? brain.length);
    setOffset(brain.length);
    setHasMore(brain.length < (totalBrainItems ?? brain.length));
    if (brainTypeCounts) {
      setBrainTypeCountsState(brainTypeCounts);
    }
  }, [brain, inspiration, totalBrainItems, brainTypeCounts]);

  // Debounced search query
  const [debouncedSearch, setDebouncedSearch] = useState(searchQuery);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, 400);
    return () => clearTimeout(handler);
  }, [searchQuery]);

  const fetchPage = async (reset: boolean, currentFilter: FilterType, currentSearch: string) => {
    setIsLoading(true);
    setUploadError(null);
    try {
      const newOffset = reset ? 0 : offset;
      const limit = 24;
      let apiType = "";
      if (currentFilter !== "all" && currentFilter !== "brief") {
        apiType = currentFilter;
      }
      
      const data = await fetchHistory(true, limit, newOffset, apiType, currentSearch);
      const newBrain = data.brain || [];
      
      if (reset) {
        setLoadedBrain(newBrain);
        setOffset(newBrain.length);
      } else {
        setLoadedBrain((prev) => [...prev, ...newBrain]);
        setOffset((prev) => prev + newBrain.length);
      }
      
      if (data.total_brain_items !== undefined) {
        setTotalBrainItemsState(data.total_brain_items);
        setHasMore((reset ? 0 : offset) + newBrain.length < data.total_brain_items);
      } else {
        setHasMore(newBrain.length === limit);
      }

      if (data.brain_type_counts) {
        setBrainTypeCountsState(data.brain_type_counts);
      }
    } catch (error) {
      console.error("Failed to fetch page:", error);
      setUploadError(error instanceof Error ? error.message : "Failed to load brain items.");
    } finally {
      setIsLoading(false);
    }
  };

  // Fetch when filter or debounced search changes
  useEffect(() => {
    // Skip the very first render if we already have props and search/filter are default
    if (activeFilter === "all" && !debouncedSearch && brain.length > 0) {
      return;
    }
    fetchPage(true, activeFilter, debouncedSearch);
  }, [activeFilter, debouncedSearch]);

  // Merge brain items with legacy inspiration items (shown as references)
  const allItems = useMemo(() => {
    const brainItems: (BrainItem & { _source: "brain" })[] = loadedBrain.map((b) => ({
      ...b,
      _source: "brain" as const,
    }));

    // If searching or filtering, filter local inspiration items
    let filteredLegacy = loadedInspiration;
    if (activeFilter !== "all" && activeFilter !== "reference") {
      filteredLegacy = [];
    }
    if (debouncedSearch) {
      const q = debouncedSearch.toLowerCase();
      filteredLegacy = filteredLegacy.filter(
        (insp) =>
          insp.id.toLowerCase().includes(q) ||
          insp.keywords.some((k) => k.toLowerCase().includes(q))
      );
    }

    const legacyItems: (BrainItem & { _source: "brain" })[] = filteredLegacy.map((insp) => ({
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
  }, [loadedBrain, loadedInspiration, activeFilter, debouncedSearch]);

  // Filter and search
  const filteredItems = useMemo(() => {
    // Briefs are handled separately
    if (activeFilter === "brief") return [];

    let items = allItems.filter((item) => !optimisticDeletedIds.has(item.id));

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
    setSyncMessage("Initializing sync...");

    try {
      const response = await adminFetch("/api/sync-brain", {
        method: "POST",
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `Sync failed with status ${response.status}`);
      }

      let result = await response.json();
      if (!result.ok) {
        throw new Error(result.error || "Sync was not successful.");
      }

      // If in progress, start polling (capped at 5 minutes so a stalled
      // sync process can't poll forever)
      if (result.in_progress) {
        const maxPolls = 150;
        let polls = 0;
        while (polls < maxPolls) {
          polls += 1;
          await new Promise((resolve) => setTimeout(resolve, 2000));
          const statusRes = await fetch("/api/sync-brain");
          if (!statusRes.ok) {
            throw new Error(`Status check failed with status ${statusRes.status}`);
          }
          const statusData = await statusRes.json();
          if (!statusData.ok) {
            throw new Error(statusData.error || "Failed to fetch sync status.");
          }
          
          if (statusData.in_progress) {
            setSyncMessage(`Syncing... (${statusData.current}/${statusData.total} files processed, ${statusData.downloaded} new, ${statusData.failed} failed)`);
          } else {
            result = statusData;
            break;
          }
        }
        if (polls >= maxPolls) {
          throw new Error("Sync status polling timed out after 5 minutes.");
        }
      }

      const msg = `Synced: ${result.downloaded} downloaded, ${result.skipped} already local${result.failed ? `, ${result.failed} failed` : ""}`;
      setSyncMessage(msg);
      setTimeout(() => setSyncMessage(null), 6000);

      await onRefresh();
    } catch (error) {
      console.error("Sync error:", error);
      setUploadError(error instanceof Error ? error.message : "Sync failed.");
      setSyncMessage(null);
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

      const response = await adminFetch("/api/upload-inspiration", {
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

  const handleDeleteClick = (id: string, isLegacy: boolean) => {
    setConfirmDeleteId({ id, isLegacy });
  };

  const executeDelete = async () => {
    if (!confirmDeleteId) return;
    const { id, isLegacy } = confirmDeleteId;
    
    setConfirmDeleteId(null);
    setDeletingId(id);
    setOptimisticDeletedIds((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
    setUploadError(null);

    try {
      const endpoint = isLegacy ? "/api/delete-inspiration" : "/api/delete-brain-item";
      const response = await adminFetch(endpoint, {
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
      
      // Successfully refreshed, remove from optimistic delete tracking
      setOptimisticDeletedIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    } catch (error) {
      console.error("Delete error:", error);
      // Revert optimistic delete tracking on error so the card restores
      setOptimisticDeletedIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      setUploadError(error instanceof Error ? error.message : "Failed to delete.");
    } finally {
      setDeletingId(null);
    }
  };

  const filterCounts = useMemo(() => {
    const counts = {
      all: 0,
      image: brainTypeCountsState?.image ?? 0,
      document: brainTypeCountsState?.document ?? 0,
      reference: (brainTypeCountsState?.reference ?? 0) + loadedInspiration.length,
      brief: briefs.length,
    };

    // Apply optimistic deletions
    for (const id of optimisticDeletedIds) {
      const brainItem = loadedBrain.find((item) => item.id === id);
      if (brainItem) {
        if (brainItem.type === "image") {
          counts.image = Math.max(0, counts.image - 1);
        } else if (brainItem.type === "document" || brainItem.type === "note") {
          counts.document = Math.max(0, counts.document - 1);
        } else if (brainItem.type === "reference") {
          counts.reference = Math.max(0, counts.reference - 1);
        }
      } else {
        const inspItem = loadedInspiration.find((item) => item.id === id);
        if (inspItem) {
          counts.reference = Math.max(0, counts.reference - 1);
        }
      }
    }

    counts.all = counts.image + counts.document + counts.reference + counts.brief;
    return counts;
  }, [brainTypeCountsState, loadedInspiration, loadedBrain, briefs.length, optimisticDeletedIds]);

  // Filter briefs by search query
  const filteredBriefs = useMemo(() => {
    if (activeFilter !== "all" && activeFilter !== "brief") return [];
    let items = briefs;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      items = items.filter(
        (b) =>
          b.title?.toLowerCase().includes(q) ||
          b.thesis?.toLowerCase().includes(q) ||
          b.keywords?.some((k) => k.toLowerCase().includes(q)) ||
          b.mood?.toLowerCase().includes(q)
      );
    }
    return items;
  }, [briefs, activeFilter, searchQuery]);

  // Combine briefs and items for a unified grid display
  const gridItems = useMemo(() => {
    if (activeFilter === "brief") {
      return filteredBriefs.map((b) => ({
        id: b.brief_id,
        isBrief: true as const,
        title: b.title,
        thesis: b.thesis,
        keywords: b.keywords,
        visual_rules: b.visual_rules,
        mood: b.mood,
        color_palette: b.color_palette,
        source_items: b.source_items,
        created_at: b.created_at,
        // Mock properties to keep typescript type-checker happy
        type: "brief" as const,
        source_file: "",
        excerpt: b.thesis,
        image_url: undefined,
        updated_at: b.created_at,
      }));
    }
    if (activeFilter === "all") {
      const mappedItems = filteredItems.map((item) => ({
        ...item,
        isBrief: false as const,
      }));
      const mappedBriefs = filteredBriefs.map((b) => ({
        id: b.brief_id,
        isBrief: true as const,
        title: b.title,
        thesis: b.thesis,
        keywords: b.keywords,
        visual_rules: b.visual_rules,
        mood: b.mood,
        color_palette: b.color_palette,
        source_items: b.source_items,
        created_at: b.created_at,
        // Mock properties to keep typescript type-checker happy
        type: "brief" as const,
        source_file: "",
        excerpt: b.thesis,
        image_url: undefined,
        updated_at: b.created_at,
      }));
      return [...mappedItems, ...mappedBriefs].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
    }
    return filteredItems.map((item) => ({
      ...item,
      isBrief: false as const,
    }));
  }, [filteredItems, filteredBriefs, activeFilter]);

  const typeIcon = (type: string) => {
    if (type === "document" || type === "note") return <FileText className="h-3.5 w-3.5" />;
    if (type === "reference") return <FileArchive className="h-3.5 w-3.5" />;
    return <ImageIcon className="h-3.5 w-3.5" />;
  };

  const typeLabel = (type: string) => {
    return type.charAt(0).toUpperCase() + type.slice(1);
  };

  // Infinite scroll: IntersectionObserver sentinel
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const loadMoreRef = useCallback(
    (node: HTMLDivElement | null) => {
      sentinelRef.current = node;
    },
    []
  );

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMore && !isLoading) {
          fetchPage(false, activeFilter, debouncedSearch);
        }
      },
      { rootMargin: "200px" }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, isLoading, activeFilter, debouncedSearch, offset]);

  return (
    <div className="space-y-5">
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept="image/*"
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
                Drop images, documents, and references to expand the collective memory of autonomous agents.
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
            {(["all", "image", "document", "reference", "brief"] as FilterType[]).map((filter) => (
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

      {/* Unified Card Grid & Creative Briefs */}
      {gridItems.length === 0 ? (
        activeFilter === "brief" ? (
          <div className="flex flex-col items-center justify-center py-20 text-[#858076]">
            <span className="text-4xl mb-3">📋</span>
            <p className="text-sm font-medium">No Creative Briefs yet.</p>
            <p className="text-xs text-[#858076]/80 mt-1 max-w-sm text-center">
              Briefs are auto-generated when brain items share overlapping keywords. Sync more content to trigger synthesis.
            </p>
          </div>
        ) : (
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
        )
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {gridItems.map((item) => {
            const isExpanded = expandedId === item.id;

            if (item.isBrief) {
              return (
                <div
                  key={item.id}
                  className={`group relative rounded-2xl border transition-all duration-200 overflow-hidden ${
                    isExpanded
                      ? "col-span-2 row-span-2 border-[#D45113]/40 shadow-md shadow-[#D45113]/10 bg-[#FAF9F6]"
                      : "border-[#D8D4CC]/60 bg-[#FAF9F6] hover:border-[#D8D4CC] hover:shadow-sm"
                  }`}
                >
                  {isExpanded && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandedId(null);
                      }}
                      className="absolute top-2 right-2 z-10 flex h-6 w-6 items-center justify-center rounded-full bg-[#252422]/70 hover:bg-[#252422] text-[#FAF9F6] shadow-sm backdrop-blur-sm transition-colors"
                      title="Collapse"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                  {/* Thumbnail / Header block */}
                  <div
                    onClick={() => setExpandedId(isExpanded ? null : item.id)}
                    className="cursor-pointer"
                  >
                    <div
                      className={`flex flex-col items-center justify-center bg-[#F5F2EB] relative p-4 text-center ${
                        isExpanded ? "aspect-[4/3]" : "aspect-square"
                      }`}
                    >
                      <span className="text-3xl mb-2">📋</span>
                      <span className="text-[10px] font-semibold text-[#858076] uppercase tracking-wider">
                        Creative Brief
                      </span>
                      
                      {/* Type badge */}
                      <div className="absolute top-2 left-2 flex items-center gap-1 rounded-full bg-[#D45113] px-2 py-0.5 text-[9px] font-semibold text-[#FAF9F6]">
                        <span>Brief</span>
                      </div>
                    </div>
                  </div>

                  {/* Card Footer */}
                  <div className="p-3 space-y-1.5">
                    <div className="flex items-start justify-between gap-2">
                      <h4
                        className="text-xs font-semibold text-[#252422] line-clamp-1 cursor-pointer"
                        onClick={() => setExpandedId(isExpanded ? null : item.id)}
                      >
                        {item.title}
                      </h4>
                    </div>

                    {/* Keywords */}
                    <div className="flex flex-wrap gap-1">
                      {item.keywords.slice(0, isExpanded ? 20 : 3).map((kw) => (
                        <span
                          key={kw}
                          className="rounded-full bg-[#D45113]/8 px-1.5 py-0.5 text-[9px] font-semibold text-[#D45113]"
                        >
                          {kw}
                        </span>
                      ))}
                      {!isExpanded && item.keywords.length > 3 && (
                        <span className="text-[9px] text-[#858076]">+{item.keywords.length - 3}</span>
                      )}
                    </div>

                    {/* Expanded Detail */}
                    {isExpanded && (
                      <div className="mt-3 space-y-2 animate-in fade-in slide-in-from-top-2 duration-200">
                        <p className="text-[11px] text-[#44423E] leading-relaxed">{item.thesis}</p>
                        
                        {item.visual_rules && item.visual_rules.length > 0 && (
                          <div>
                            <p className="text-[10px] font-semibold text-[#858076] uppercase tracking-wider mb-1">Visual Rules</p>
                            <ul className="space-y-0.5">
                              {item.visual_rules.map((rule, idx) => (
                                <li key={idx} className="text-[11px] text-[#44423E] flex items-start gap-1.5">
                                  <span className="text-[#D45113] mt-0.5">•</span>
                                  <span>{rule}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
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

                        <p className="text-[9px] text-[#858076]/60">
                          Sources: {item.source_items.length} brain items
                        </p>
                        <p className="text-[9px] text-[#858076]/60">
                          {new Date(item.created_at).toLocaleString(undefined, {
                            dateStyle: "medium",
                            timeStyle: "short",
                          })}
                        </p>
                      </div>
                    )}

                    {/* Expand indicator */}
                    {!isExpanded && (
                      <button
                        onClick={() => setExpandedId(item.id)}
                        className="flex items-center gap-0.5 text-[9px] text-[#858076]/60 hover:text-[#D45113] transition-colors"
                      >
                        <ChevronDown className="h-3 w-3" />
                        <span>{item.visual_rules.length} rules • {item.source_items.length} sources</span>
                      </button>
                    )}
                  </div>
                </div>
              );
            } else {
              const isLegacy = item.id.startsWith("insp_");
              const hasImage = !!((item.type === "image" || item.type === "reference") && item.image_url && item.image_url.trim() !== "");

              return (
                <div
                  key={item.id}
                  className={`group relative rounded-2xl border transition-all duration-200 overflow-hidden ${
                    isExpanded
                      ? "col-span-2 row-span-2 border-[#D45113]/40 shadow-md shadow-[#D45113]/10 bg-[#FAF9F6]"
                      : "border-[#D8D4CC]/60 bg-[#FAF9F6] hover:border-[#D8D4CC] hover:shadow-sm"
                  }`}
                >
                  {isExpanded && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandedId(null);
                      }}
                      className="absolute top-2 right-2 z-10 flex h-6 w-6 items-center justify-center rounded-full bg-[#252422]/70 hover:bg-[#252422] text-[#FAF9F6] shadow-sm backdrop-blur-sm transition-colors"
                      title="Collapse"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
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
                        {item.type === "document" || item.type === "note" ? (
                          <FileText className="h-10 w-10 text-[#858076]/40 stroke-[1.5]" />
                        ) : (
                          <FileArchive className="h-10 w-10 text-[#858076]/40 stroke-[1.5]" />
                        )}
                        <span className="mt-2 text-[10px] font-semibold text-[#858076]/60 uppercase tracking-wider">
                          {item.type === "note" ? "document" : item.type}
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
                          handleDeleteClick(item.id, isLegacy);
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
            }
          })}
        </div>
      )}

      {/* Infinite scroll sentinel */}
      {hasMore && (
        <div ref={loadMoreRef} className="flex justify-center pt-4 pb-2">
          {isLoading && (
            <div className="flex items-center gap-2 text-xs text-[#858076]">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-[#D45113]" />
              <span>Loading more…</span>
            </div>
          )}
        </div>
      )}

      {/* Custom Delete Confirmation Modal */}
      {confirmDeleteId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-in fade-in duration-200">
          {/* Backdrop */}
          <div 
            className="absolute inset-0 bg-[#252422]/40 backdrop-blur-sm"
            onClick={() => setConfirmDeleteId(null)}
          />
          {/* Dialog Container */}
          <div className="relative w-full max-w-sm overflow-hidden rounded-[2rem] border border-[#D8D4CC] bg-[#FAF9F6] p-6 shadow-2xl animate-in zoom-in-95 duration-200 z-10">
            <div className="flex flex-col items-center text-center space-y-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-red-600">
                <Trash2 className="h-6 w-6" />
              </div>
              <div className="space-y-1.5">
                <h4 className="text-base font-bold text-[#252422]">Delete Item?</h4>
                <p className="text-xs text-[#858076] leading-relaxed">
                  Are you sure you want to permanently delete this item from your Second Brain? This action cannot be undone.
                </p>
              </div>
              <div className="flex w-full gap-2 pt-2">
                <Button
                  type="button"
                  onClick={() => setConfirmDeleteId(null)}
                  className="flex-1 rounded-full border border-[#D8D4CC] bg-white hover:bg-[#F5F2EB] text-[#44423E] font-semibold text-xs h-9 px-4 transition-all"
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  onClick={executeDelete}
                  className="flex-1 rounded-full border-transparent bg-red-600 hover:bg-red-700 text-[#FAF9F6] font-semibold text-xs h-9 px-4 shadow-sm transition-all"
                >
                  Delete
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
