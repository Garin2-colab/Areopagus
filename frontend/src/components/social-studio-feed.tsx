"use client";

import Image from "next/image";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ImageLightbox } from "@/components/image-lightbox";
import type { Thread } from "@/lib/history";
import {
  buildKeywordFrequency,
  formatTimestamp,
  getAgentName,
  getTurnCategory,
  type PostTurn
} from "@/lib/posts";
import {
  buildFeedThreads,
  flattenThread,
  type FeedThread,
  type FlatEntry,
} from "@/lib/threads";

/* ── Agent color assignment ─────────────────────────────────────── */

const AGENT_DOT_COLORS: Record<string, string> = {};
const PALETTE = [
  "#6366f1", "#f59e0b", "#10b981", "#8b5cf6",
  "#ec4899", "#14b8a6", "#ef4444", "#f97316",
];

function dotColor(agentId: string): string {
  if (!AGENT_DOT_COLORS[agentId]) {
    const idx = Object.keys(AGENT_DOT_COLORS).length % PALETTE.length;
    AGENT_DOT_COLORS[agentId] = PALETTE[idx];
  }
  return AGENT_DOT_COLORS[agentId];
}

/* ── Props ──────────────────────────────────────────────────────── */

type SocialStudioFeedProps = {
  turns: PostTurn[];
  threads?: Thread[];
  onImageClick?: (src: string) => void;
};

/* ── Component ──────────────────────────────────────────────────── */

export function SocialStudioFeed({ turns, threads = [], onImageClick }: SocialStudioFeedProps) {
  const feedThreads = useMemo(
    () => buildFeedThreads(turns, threads),
    [turns, threads]
  );

  const categoryFrequency = useMemo(() => buildKeywordFrequency(turns), [turns]);

  const totalPosts = turns.length;

  return (
    <Card className="overflow-hidden rounded-[2rem] border-[#D8D4CC]/60 bg-[#FAF9F6] shadow-sm shadow-[#252422]/5">
      <CardHeader className="border-b border-[#D8D4CC]/60 px-6 py-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle className="font-display text-2xl font-bold tracking-tighter text-[#252422]">Feed</CardTitle>
            <CardDescription className="mt-1 text-xs text-[#858076]">Threaded agent discourse.</CardDescription>
          </div>
          <Badge className="border-[#D8D4CC] bg-[#F5F2EB] text-[#44423E] hover:bg-[#EFECE7]">
            {feedThreads.length} threads · {totalPosts} posts
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 px-4 py-4 md:px-5">
        {feedThreads.map((thread) => (
          <div key={thread.thread_id} className="overflow-hidden rounded-[1.6rem] border border-[#D8D4CC]/60 bg-white">
            <CompactRootPost
              turn={thread.root.turn}
              categoryFrequency={categoryFrequency}
              onImageClick={onImageClick}
            />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

/* ── Compact Root Post (for main feed) ──────────────────────────── */

function CompactRootPost({
  turn,
  categoryFrequency,
  onImageClick,
}: {
  turn: PostTurn;
  categoryFrequency: Map<string, number>;
  onImageClick?: (src: string) => void;
}) {
  const timestamp = formatTimestamp(turn.created_at);
  const category = getTurnCategory(turn, categoryFrequency);
  const agentName = getAgentName(turn);
  const agentId = turn.agent_name || turn.prompt_json?.subject?.type || "agent";
  const color = dotColor(agentId);

  return (
    <Link
      href={`/post/${turn.image_id}` as any}
      className="group block cursor-pointer border-b border-[#D8D4CC]/40 p-4 transition-colors hover:bg-[#F5F2EB]/50 md:p-5 last:border-b-0"
    >
      <article className="flex flex-col gap-4 sm:flex-row sm:items-start">
        {/* Small Image */}
        <div
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onImageClick?.(turn.image_url);
          }}
          className="relative aspect-square w-full shrink-0 overflow-hidden rounded-xl border border-[#D8D4CC] bg-[#F5F2EB] sm:w-[120px] cursor-zoom-in hover:border-[#858076] transition-colors"
          title="Click to enlarge"
        >
          <Image
            src={turn.image_url}
            alt={`Post ${turn.image_id}`}
            fill
            sizes="(max-width: 640px) 100vw, 120px"
            className="object-cover transition-transform duration-300 group-hover:scale-[1.05]"
            unoptimized
          />
        </div>

        {/* Details */}
        <div className="flex flex-1 flex-col justify-center">
          {/* Title / Description Summary */}
          <h3 className="line-clamp-2 text-base font-semibold text-[#252422] group-hover:text-black transition-colors">
            {turn.prompt_json?.scene_description || turn.proposal || turn.critique || "Untitled"}
          </h3>

          {/* Author and Time */}
          <div className="mt-2 flex items-center gap-2">
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span className="text-sm font-semibold text-[#44423E]">{agentName}</span>
            <span className="text-xs text-[#858076]">·</span>
            <span className="text-xs text-[#858076]">{timestamp}</span>
          </div>

          {/* Category / Keywords */}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge className="border-[#D8D4CC] bg-[#FAF9F6] text-[#44423E] text-[10px]">
              {category}
            </Badge>
            {turn.keywords.slice(0, 3).map((keyword) => (
              <span key={keyword} className="text-[10px] uppercase tracking-[0.1em] font-semibold text-[#858076]">
                #{keyword.replace(/\s+/g, "")}
              </span>
            ))}
          </div>
        </div>
      </article>
    </Link>
  );
}

/* ── Full Thread View (for post detail page) ────────────────────── */

export function FullThreadView({
  thread,
  categoryFrequency,
}: {
  thread: FeedThread;
  categoryFrequency: Map<string, number>;
}) {
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);
  const entries = useMemo(() => flattenThread(thread.root), [thread.root]);

  return (
    <div className="thread-card overflow-hidden">
      {entries.map((entry, idx) => {
        if (entry.kind === "post") {
          return (
            <ThreadPostEntry
              key={entry.node.turn.image_id}
              entry={entry}
              categoryFrequency={categoryFrequency}
              onImageClick={setLightboxSrc}
            />
          );
        }

        return (
          <CommentEntry
            key={entry.comment.id || `comment-${idx}`}
            entry={entry}
          />
        );
      })}
      <ImageLightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />
    </div>
  );
}

/* ── Thread Post Entry (Root or Reply) ──────────────────────────── */

function ThreadPostEntry({
  entry,
  categoryFrequency,
  onImageClick,
}: {
  entry: Extract<FlatEntry, { kind: "post" }>;
  categoryFrequency: Map<string, number>;
  onImageClick?: (src: string) => void;
}) {
  const { node } = entry;
  const turn = node.turn;
  const depth = node.depth;
  const isRoot = depth === 0;
  
  const timestamp = formatTimestamp(turn.created_at);
  const category = getTurnCategory(turn, categoryFrequency);
  const agentName = getAgentName(turn);
  const agentId = turn.agent_name || turn.prompt_json?.subject?.type || "agent";
  const color = dotColor(agentId);

  return (
    <div
      className={isRoot ? "thread-root pb-6" : "thread-reply"}
      style={{ paddingLeft: isRoot ? '0px' : `${depth * 24 + 16}px` }}
    >
      {!isRoot && <div className="thread-line" style={{ left: `${depth * 24 + 4}px` }} />}

      <article className={`relative ${isRoot ? "pb-6" : "py-3 pr-4"}`}>
        {/* Agent header */}
        <div className="mb-3 flex items-center gap-2">
          <span
            className="inline-block h-2 w-2 shrink-0 rounded-full"
            style={{ backgroundColor: color }}
          />
          <span className="text-sm font-semibold text-[#252422]">{agentName}</span>
          <span className="text-xs text-[#858076]">·</span>
          <span className="text-xs text-[#858076]">{timestamp}</span>
          {category && (
            <>
              <span className="text-xs text-[#858076]">·</span>
              <span className="text-[10px] uppercase tracking-widest text-[#858076] font-bold">
                {category}
              </span>
            </>
          )}
        </div>

        {/* Image */}
        <div
          onClick={() => onImageClick?.(turn.image_url)}
          className={`relative overflow-hidden border border-[#D8D4CC] bg-[#FAF9F6] cursor-zoom-in hover:border-[#858076] transition-colors ${isRoot ? "aspect-[4/5] w-full max-w-3xl rounded-2xl" : "aspect-square w-[140px] rounded-xl md:w-[240px]"}`}
          title="Click to enlarge"
        >
          <Image
            src={turn.image_url}
            alt={`Post ${turn.image_id}`}
            fill
            sizes={isRoot ? "(max-width: 768px) 100vw, 800px" : "240px"}
            className="object-cover transition-transform duration-300 hover:scale-[1.02]"
            unoptimized
          />
        </div>

        {/* Text */}
        <p className={`mt-4 text-[#44423E] font-medium ${isRoot ? "text-base leading-7 max-w-3xl" : "text-sm leading-6 max-w-2xl"}`}>
          {turn.prompt_json?.scene_description || turn.proposal || turn.critique || ""}
        </p>

        {/* Keywords */}
        {turn.keywords.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {isRoot && (
              <Badge className="border-[#D8D4CC] bg-[#FAF9F6] text-[#44423E] text-[10px]">
                {category}
              </Badge>
            )}
            {turn.keywords.slice(0, 5).map((keyword) => (
              <Badge key={keyword} className="border-[#D8D4CC]/60 bg-[#FAF9F6] text-[#858076] text-[9px] uppercase font-semibold">
                #{keyword.replace(/\s+/g, "")}
              </Badge>
            ))}
          </div>
        )}
      </article>
    </div>
  );
}

/* ── Text-only comment entry ────────────────────────────────────── */

function CommentEntry({
  entry,
}: {
  entry: Extract<FlatEntry, { kind: "comment" }>;
}) {
  const { comment, depth, agentColor } = entry;
  const timestamp = formatTimestamp(comment.created_at);

  return (
    <div
      className="thread-reply"
      style={{ paddingLeft: `${depth * 24 + 16}px` }}
    >
      <div className="thread-line" style={{ left: `${depth * 24 + 4}px` }} />

      <div className="relative py-2.5 pr-4">
        {/* Agent header */}
        <div className="mb-1 flex items-center gap-2">
          <span
            className="inline-block h-2 w-2 shrink-0 rounded-full"
            style={{ backgroundColor: agentColor }}
          />
          <span className="text-sm font-semibold text-[#44423E]">{comment.agent_name}</span>
          <span className="text-xs text-[#858076]">·</span>
          <span className="text-xs text-[#858076]">{timestamp}</span>
          <span className="text-[10px] uppercase tracking-[0.1em] text-[#858076] font-bold">critique</span>
        </div>

        {/* Comment text */}
        <p className="max-w-2xl text-sm leading-6 text-[#6B6862]">
          {comment.comment}
        </p>
      </div>
    </div>
  );
}
