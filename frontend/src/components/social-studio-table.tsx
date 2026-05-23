"use client";

import { useState, useRef } from "react";
import Image from "next/image";
import { Upload, Eye, Search, AlertCircle, CheckCircle2, Trash2 } from "lucide-react";
import { type HistoryTurn } from "@/lib/history";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Input } from "./ui/input";
import { compressImage } from "@/lib/utils";

type SocialStudioTableProps = {
  turns: HistoryTurn[];
  onRefresh: () => Promise<void>;
  onImageClick?: (src: string) => void;
};

const CATEGORY_OPTIONS = [
  "Fashion",
  "Illustration",
  "Graphic Design",
  "Architecture",
  "UX/UI",
  "Industrial Design"
];

export function SocialStudioTable({ turns, onRefresh, onImageClick }: SocialStudioTableProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [replacingId, setReplacingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [updatingCategoryId, setUpdatingCategoryId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const activeReplaceIdRef = useRef<string | null>(null);

  const showFeedback = (type: "success" | "error", message: string) => {
    setFeedback({ type, message });
    if (type === "success") {
      setTimeout(() => {
        setFeedback((prev) => (prev?.message === message ? null : prev));
      }, 4000);
    }
  };

  const handleDelete = async (imageId: string) => {
    if (!window.confirm("Are you sure you want to delete this post?")) {
      return;
    }

    setDeletingId(imageId);
    setFeedback(null);

    try {
      const response = await fetch("/api/delete-post", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          image_id: imageId
        })
      });

      const result = await response.json();
      if (response.ok && result.ok) {
        showFeedback("success", `Successfully deleted post: ${imageId}`);
        await onRefresh();
      } else {
        throw new Error(result.error || "Failed to delete post.");
      }
    } catch (err) {
      showFeedback("error", err instanceof Error ? err.message : "Failed to delete post.");
    } finally {
      setDeletingId(null);
    }
  };

  const handleCategoryChange = async (imageId: string, newCategory: string) => {
    setUpdatingCategoryId(imageId);
    setFeedback(null);

    try {
      const response = await fetch("/api/update-category", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          image_id: imageId,
          category: newCategory
        })
      });

      const result = await response.json();
      if (response.ok && result.ok) {
        showFeedback("success", `Successfully updated category to ${newCategory}`);
        await onRefresh();
      } else {
        throw new Error(result.error || "Failed to update category.");
      }
    } catch (err) {
      showFeedback("error", err instanceof Error ? err.message : "Failed to update category.");
    } finally {
      setUpdatingCategoryId(null);
    }
  };

  // Filter turns by agent name, action, keywords or prompt content
  const filteredTurns = turns.filter((turn) => {
    const textSearch = [
      turn.agent_name,
      turn.action,
      turn.image_id,
      turn.proposal,
      turn.critique,
      turn.prompt_json?.scene_description,
      ...(turn.keywords ?? [])
    ]
      .join(" ")
      .toLowerCase();
    return textSearch.includes(searchTerm.toLowerCase());
  });

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    const imageId = activeReplaceIdRef.current;
    if (!file || !imageId) return;

    setReplacingId(imageId);
    setFeedback(null);

    try {
      const base64Data = await compressImage(file);
      const response = await fetch("/api/replace-image", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          image_id: imageId,
          image_base64: base64Data,
          mime_type: "image/jpeg"
        })
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
      if (result.ok) {
        showFeedback("success", `Successfully replaced image for turn: ${imageId}`);
        await onRefresh();
      } else {
        throw new Error(result.error || "Failed to upload image.");
      }
    } catch (err) {
      showFeedback("error", err instanceof Error ? err.message : "Failed to replace image.");
    } finally {
      setReplacingId(null);
      activeReplaceIdRef.current = null;
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const triggerReplacement = (imageId: string) => {
    activeReplaceIdRef.current = imageId;
    fileInputRef.current?.click();
  };

  const agentBadgeColor = (agentName?: string) => {
    const name = (agentName || "").toLowerCase();
    if (name.includes("anatomist")) return "bg-rose-50 text-rose-800 border-rose-200/80 hover:bg-rose-50";
    if (name.includes("subversive")) return "bg-violet-50 text-violet-800 border-violet-200/80 hover:bg-violet-50";
    return "bg-zinc-100 text-zinc-805 border-zinc-200 hover:bg-zinc-100";
  };

  const getTurnPreviewText = (turn: HistoryTurn) => {
    return (
      turn.prompt_json?.scene_description ||
      turn.proposal ||
      turn.critique ||
      turn.agent2?.critique ||
      "No critique or description content"
    );
  };

  return (
    <div className="space-y-4">
      {/* Hidden file input */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept="image/*"
        className="hidden"
      />

      {/* Control bar */}
      <div className="flex flex-col items-center justify-between gap-4 rounded-2xl border border-[#D8D4CC]/60 bg-[#FAF9F6] p-4 md:flex-row md:p-5 shadow-sm shadow-[#252422]/5">
        <div className="relative w-full max-w-md">
          <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[#858076]" />
          <Input
            type="text"
            placeholder="Search Turn, Agent, content keywords..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="h-10 w-full rounded-xl border-[#D8D4CC] bg-white pl-10 pr-4 text-sm text-[#252422] placeholder:text-[#858076] focus-visible:ring-1 focus-visible:ring-[#858076] focus-visible:ring-offset-0"
          />
        </div>

        {feedback && (
          <div
            className={`flex items-center gap-2 rounded-xl border px-4 py-2 text-xs font-medium animate-in fade-in slide-in-from-top-1 duration-200 ${
              feedback.type === "success"
                ? "border-emerald-800/30 bg-emerald-950/20 text-emerald-400"
                : "border-rose-800/30 bg-rose-950/20 text-rose-400"
            }`}
          >
            {feedback.type === "success" ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
            <span>{feedback.message}</span>
          </div>
        )}
      </div>

      {/* Table grid container */}
      <div className="overflow-hidden rounded-2xl border border-[#D8D4CC]/60 bg-[#FAF9F6] shadow-sm shadow-[#252422]/5">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm text-[#44423E]">
            <thead>
              <tr className="border-b border-[#D8D4CC] bg-[#F5F2EB]/60 text-[10px] uppercase tracking-[0.25em] text-[#858076]">
                <th className="py-4 pl-6 pr-3 font-semibold">Turn</th>
                <th className="px-3 py-4 font-semibold">Image</th>
                <th className="px-3 py-4 font-semibold">Agent</th>
                <th className="px-3 py-4 font-semibold">Action</th>
                <th className="px-3 py-4 font-semibold w-1/3">Discourse Content</th>
                <th className="px-3 py-4 font-semibold">Keywords</th>
                <th className="px-3 py-4 font-semibold">Category</th>
                <th className="px-3 py-4 font-semibold">Timestamp</th>
                <th className="py-4 pl-3 pr-6 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#D8D4CC]/40">
              {filteredTurns.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-[#858076]">
                    No matching turns found.
                  </td>
                </tr>
              ) : (
                filteredTurns.map((turn) => {
                  const isThisReplacing = replacingId === turn.image_id;
                  const isThisUpdatingCategory = updatingCategoryId === turn.image_id;
                  return (
                    <tr
                      key={turn.image_id}
                      className="group transition-colors hover:bg-[#F5F2EB]/30"
                    >
                      {/* Turn ID */}
                      <td className="py-4 pl-6 pr-3 font-mono text-xs text-[#858076] font-semibold">
                        {turn.turn}
                      </td>

                      {/* Image Thumbnail */}
                      <td className="px-3 py-3">
                        <div
                          onClick={() => onImageClick?.(turn.image_url)}
                          className="relative h-12 w-12 overflow-hidden rounded-lg border border-[#D8D4CC] bg-[#F5F2EB] cursor-zoom-in hover:border-[#858076] transition-colors"
                          title="Click to enlarge"
                        >
                          <Image
                            src={turn.image_url}
                            alt={`Turn ${turn.turn}`}
                            fill
                            sizes="48px"
                            className="object-cover transition-transform duration-300 hover:scale-105"
                            unoptimized
                          />
                        </div>
                      </td>

                      {/* Agent Badge */}
                      <td className="px-3 py-4">
                        <Badge className={`rounded-md font-display px-2 py-0.5 text-xs font-semibold ${agentBadgeColor(turn.agent_name)}`}>
                          {turn.agent_name || "Unknown"}
                        </Badge>
                      </td>

                      {/* Action */}
                      <td className="px-3 py-4 text-xs font-mono text-[#858076]">
                        {turn.action || "None"}
                      </td>

                      {/* Discourse Text Content */}
                      <td className="px-3 py-4 max-w-sm">
                        <div className="line-clamp-2 text-xs text-[#44423E] leading-5 font-medium" title={getTurnPreviewText(turn)}>
                          {getTurnPreviewText(turn)}
                        </div>
                      </td>

                      {/* Keywords */}
                      <td className="px-3 py-4">
                        <div className="flex flex-wrap gap-1 max-w-[180px]">
                          {(turn.keywords ?? []).slice(0, 3).map((kw) => (
                            <span
                              key={kw}
                              className="rounded bg-[#F5F2EB] px-1.5 py-0.5 text-[9px] font-mono tracking-wide text-[#44423E] border border-[#D8D4CC]/60"
                            >
                              {kw}
                            </span>
                          ))}
                          {(turn.keywords ?? []).length > 3 && (
                            <span className="text-[9px] text-[#858076] font-mono self-center">
                              +{turn.keywords.length - 3}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Category */}
                      <td className="px-3 py-4">
                        <div className="flex items-center gap-1.5">
                          <select
                            value={turn.category || "Illustration"}
                            disabled={isThisUpdatingCategory}
                            onChange={(e) => handleCategoryChange(turn.image_id, e.target.value)}
                            className="h-8 rounded-lg border border-[#D8D4CC] bg-white px-2 text-xs font-semibold text-[#D45113] focus:outline-none focus:ring-1 focus:ring-[#858076] hover:bg-[#F5F2EB]/50 transition-colors disabled:opacity-50"
                          >
                            {(CATEGORY_OPTIONS.includes(turn.category || "")
                              ? CATEGORY_OPTIONS
                              : [turn.category || "Illustration", ...CATEGORY_OPTIONS.filter((c) => c !== (turn.category || "Illustration"))]
                            ).map((cat) => (
                              <option key={cat} value={cat}>
                                {cat}
                              </option>
                            ))}
                          </select>
                          {isThisUpdatingCategory && (
                            <span className="h-3.5 w-3.5 animate-spin rounded-full border border-zinc-400 border-t-transparent" />
                          )}
                        </div>
                      </td>

                      {/* Timestamp */}
                      <td className="px-3 py-4 text-[10px] text-[#858076] whitespace-nowrap font-medium">
                        {new Date(turn.created_at).toLocaleString([], {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit"
                        })}
                      </td>

                      {/* Actions */}
                      <td className="py-4 pl-3 pr-6 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            asChild
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 rounded-lg text-[#858076] hover:text-[#252422] hover:bg-[#F5F2EB]"
                            title="View post"
                          >
                            <a href={`/post/${turn.image_id}`}>
                              <Eye className="h-4 w-4" />
                            </a>
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={isThisReplacing}
                            onClick={() => triggerReplacement(turn.image_id)}
                            className="h-8 rounded-lg border-[#D8D4CC] bg-[#FAF9F6] hover:bg-[#F5F2EB] hover:text-[#252422] px-3 text-xs text-[#44423E]"
                          >
                            {isThisReplacing ? (
                              <span className="flex items-center gap-1.5">
                                <span className="h-3 w-3 animate-spin rounded-full border border-zinc-400 border-t-transparent" />
                                Replacing...
                              </span>
                            ) : (
                              <span className="flex items-center gap-1.5">
                                <Upload className="h-3.5 w-3.5" />
                                Replace
                              </span>
                            )}
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            disabled={deletingId === turn.image_id}
                            onClick={() => handleDelete(turn.image_id)}
                            className="h-8 w-8 rounded-lg text-rose-500 hover:text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                            title="Delete post"
                          >
                            {deletingId === turn.image_id ? (
                              <span className="h-3.5 w-3.5 animate-spin rounded-full border border-rose-500 border-t-transparent" />
                            ) : (
                              <Trash2 className="h-4 w-4" />
                            )}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
