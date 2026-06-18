"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ImageLightbox } from "@/components/image-lightbox";
import type { Thread } from "@/lib/history";
import { cn } from "@/lib/utils";
import {
  buildKeywordFrequency,
  formatTimestamp,
  formatRelativeTime,
  getAgentName,
  getTurnCategory,
  type PostTurn
} from "@/lib/posts";
import {
  buildFeedThreads,
  flattenThread,
  type FeedThread,
  type FlatEntry,
  type ThreadNode,
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

function getAspectClass(turn: PostTurn) {
  const width = turn.image_webp?.dimensions?.width || turn.image_webp?.width;
  const height = turn.image_webp?.dimensions?.height || turn.image_webp?.height;
  if (width && height) {
    const ratio = width / height;
    if (ratio < 0.7) return "aspect-[9/16]";
    if (ratio < 0.9) return "aspect-[3/4]";
    if (ratio > 1.4) return "aspect-video";
  }
  return "aspect-square";
}

/* ── Props ──────────────────────────────────────────────────────── */

type SocialStudioFeedProps = {
  turns: PostTurn[];
  threads?: Thread[];
  onImageClick?: (src: string) => void;
};

function countCommentsAndReplies(thread: FeedThread) {
  let commentsCount = 0;
  let repliesCount = 0;

  function walk(node: ThreadNode) {
    commentsCount += node.comments.length;
    repliesCount += node.replies.length;
    for (const reply of node.replies) {
      walk(reply);
    }
  }

  walk(thread.root);
  return { comments: commentsCount, replies: repliesCount };
}

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
            <CardTitle className="font-display text-2xl text-[#D45113]">Feed</CardTitle>
            <CardDescription className="mt-1 text-xs text-[#858076]">Threaded agent discourse.</CardDescription>
          </div>
          <Badge className="border-[#D8D4CC] bg-[#F5F2EB] text-[#44423E] hover:bg-[#EFECE7]">
            {feedThreads.length} threads · {totalPosts} posts
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-6 px-4 py-4 md:px-5">
        {feedThreads.map((thread, index) => {
          const counts = countCommentsAndReplies(thread);
          const totalComments = counts.comments + counts.replies;
          
          const lastActivityTime = new Date(thread.updated_at).getTime();
          const hrs24Ms = 24 * 60 * 60 * 1000;
          const isHighlighted = index < 3 && !isNaN(lastActivityTime) && (Date.now() - lastActivityTime <= hrs24Ms);
          
          const threadTurns = [thread.root.turn, ...thread.root.replies.map((r) => r.turn)];

          return (
            <div
              key={thread.thread_id}
              id={`feed-post-${thread.root.turn.image_id}`}
              className={cn(
                "overflow-hidden rounded-[1.6rem] transition-all duration-300 border bg-white flex flex-col aspect-[2/3]",
                isHighlighted
                  ? "border-[#D45113] ring-1 ring-[#D45113]/50 shadow-md shadow-[#D45113]/10"
                  : "border-[#D8D4CC]/60"
              )}
            >
              <CompactRootPost
                rootTurn={thread.root.turn}
                turns={threadTurns}
                categoryFrequency={categoryFrequency}
                onImageClick={onImageClick}
                commentCount={totalComments}
                lastActivityAt={thread.updated_at}
                isHighlighted={isHighlighted}
              />
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

/* ── Compact Media Slideshow Viewer ─────────────────────────────── */

function CompactMediaViewer({ turns }: { turns: PostTurn[] }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [prevTurn, setPrevTurn] = useState<PostTurn | null>(null);

  const handleNext = () => {
    setPrevTurn(turns[currentIndex]);
    setCurrentIndex((prev) => (prev + 1) % turns.length);
  };

  useEffect(() => {
    if (turns.length <= 1) return;

    const currentTurn = turns[currentIndex];
    const isVideo = currentTurn.image_webp?.format === "mp4" || currentTurn.image_url.includes("format=mp4");

    if (isVideo) {
      // For videos, display entire length and transition on ended.
      // We also add a fallback timeout of 15 seconds so we never get stuck on a broken video.
      const fallbackTimer = setTimeout(() => {
        handleNext();
      }, 15000);
      return () => clearTimeout(fallbackTimer);
    } else {
      // For images, transition after 1 second.
      const timer = setTimeout(() => {
        handleNext();
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [currentIndex, turns.length]);

  if (turns.length === 0) return null;

  const currentTurn = turns[currentIndex];
  const isVideo = currentTurn.image_webp?.format === "mp4" || currentTurn.image_url.includes("format=mp4");
  const prevIsVideo = prevTurn ? (prevTurn.image_webp?.format === "mp4" || prevTurn.image_url.includes("format=mp4")) : false;

  return (
    <div className="relative aspect-square w-full shrink-0 overflow-hidden border-b border-[#D8D4CC]/40 bg-[#FAF9F6]">
      {/* Background (Previous Slide) */}
      {prevTurn && (
        <div className="absolute inset-0 z-0">
          {prevIsVideo ? (
            <video
              src={prevTurn.image_url}
              className="h-full w-full object-contain"
              muted
              playsInline
              autoPlay
            />
          ) : (
            <Image
              src={prevTurn.image_url}
              alt="Previous Slide"
              fill
              sizes="(max-width: 640px) 100vw, 380px"
              className="object-contain"
              unoptimized
            />
          )}
        </div>
      )}

      {/* Foreground (Current Slide with Dissolve Transition) */}
      <div 
        key={currentTurn.image_url} 
        className="absolute inset-0 z-10 animate-dissolve-in"
      >
        {isVideo ? (
          <video
            src={currentTurn.image_url}
            className="h-full w-full object-contain transition-transform duration-300 group-hover:scale-[1.05]"
            muted
            playsInline
            autoPlay
            onEnded={handleNext}
          />
        ) : (
          <Image
            src={currentTurn.image_url}
            alt={`Post ${currentTurn.image_id}`}
            fill
            sizes="(max-width: 640px) 100vw, 380px"
            className="object-contain transition-transform duration-300 group-hover:scale-[1.05]"
            unoptimized
          />
        )}
      </div>
      
      {turns.length > 1 && (
        <div className="absolute bottom-2 right-2 bg-[#252422]/80 text-[#FAF9F6] text-[9px] px-1.5 py-0.5 rounded-md font-bold tracking-wider z-20 select-none">
          {currentIndex + 1} / {turns.length}
        </div>
      )}
    </div>
  );
}

/* ── Compact Root Post (for main feed) ──────────────────────────── */

function CompactRootPost({
  rootTurn,
  turns,
  categoryFrequency,
  onImageClick,
  commentCount = 0,
  lastActivityAt,
  isHighlighted = false,
}: {
  rootTurn: PostTurn;
  turns: PostTurn[];
  categoryFrequency: Map<string, number>;
  onImageClick?: (src: string) => void;
  commentCount?: number;
  lastActivityAt?: string;
  isHighlighted?: boolean;
}) {
  const timestamp = formatRelativeTime(lastActivityAt || rootTurn.created_at);
  const category = getTurnCategory(rootTurn, categoryFrequency);
  const agentName = getAgentName(rootTurn);
  const agentId = rootTurn.agent_name || rootTurn.prompt_json?.subject?.type || "agent";
  const color = dotColor(agentId);

  return (
    <Link
      href={`/post/${rootTurn.image_id}` as any}
      className="group flex flex-col h-full w-full cursor-pointer hover:bg-[#F5F2EB]/30 transition-colors"
    >
      {/* Square Image / Video Window with slideshow capabilities */}
      <CompactMediaViewer turns={turns} />

      {/* Metadata Section - fills the bottom 1/3 of the 2:3 card */}
      <div className="flex flex-col flex-1 p-4 justify-between bg-white text-xs">
        {/* Row 1: Agent name & Date */}
        <div className="flex items-center justify-between gap-2 min-w-0">
          <div className="flex items-center gap-1.5 min-w-0">
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span className="truncate font-semibold text-[#252422] group-hover:text-black transition-colors">
              {agentName}
            </span>
          </div>
          <span className="text-[10px] text-[#858076] shrink-0 font-medium">{timestamp}</span>
        </div>

        {/* Row 2: Category Badge & Comment Count */}
        <div className="flex items-center justify-between gap-2 mt-2">
          <Badge className="border-[#D8D4CC] bg-[#FAF9F6] text-[#D45113] text-[9px] font-bold uppercase tracking-wider py-0.5 px-2 rounded-md shrink-0">
            {category}
          </Badge>
          {commentCount > 0 ? (
            <span className="text-[10px] font-bold text-[#D45113] bg-[#D45113]/5 px-2.5 py-0.5 rounded-full shrink-0">
              {commentCount} {commentCount === 1 ? "comment" : "comments"}
            </span>
          ) : (
            <span className="text-[10px] text-[#858076] italic shrink-0">No comments</span>
          )}
        </div>

        {/* Row 3: Keywords */}
        <div className="mt-3 pt-2.5 border-t border-[#D8D4CC]/40 flex flex-wrap gap-1.5">
          {rootTurn.keywords.slice(0, 3).map((keyword) => (
            <span
              key={keyword}
              className="text-[9px] uppercase tracking-[0.08em] font-bold text-[#858076] hover:text-[#D45113] transition-colors"
            >
              #{keyword.replace(/\s+/g, "")}
            </span>
          ))}
        </div>
      </div>
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
              <span className="text-[10px] uppercase tracking-widest text-[#D45113] font-bold">
                {category}
              </span>
            </>
          )}
        </div>

        {/* Image / Video */}
        {(() => {
          const isVideo = turn.image_webp?.format === "mp4" || turn.image_url.includes("format=mp4");
          return (
            <div
              onClick={() => onImageClick?.(turn.image_url)}
              className={`overflow-hidden border border-[#D8D4CC] bg-[#FAF9F6] cursor-zoom-in hover:border-[#858076] transition-colors ${
                isRoot ? "w-full max-w-3xl rounded-2xl" : "w-[140px] md:w-[240px] rounded-xl"
              }`}
              title="Click to enlarge"
            >
              {isVideo ? (
                <video
                  src={turn.image_url}
                  muted
                  playsInline
                  autoPlay
                  loop
                  className={`w-full h-auto object-contain transition-transform duration-300 hover:scale-[1.01] ${
                    isRoot ? "max-h-[80vh]" : ""
                  }`}
                />
              ) : (
                <img
                  src={turn.image_url}
                  alt={`Post ${turn.image_id}`}
                  className={`w-full h-auto object-contain transition-transform duration-300 hover:scale-[1.01] ${
                    isRoot ? "max-h-[80vh]" : ""
                  }`}
                />
              )}
            </div>
          );
        })()}

        {/* Text */}
        <p className={`mt-4 text-[#44423E] font-medium ${isRoot ? "text-base leading-7 max-w-3xl" : "text-sm leading-6 max-w-2xl"}`}>
          {turn.prompt_json?.scene_description || turn.proposal || turn.critique || ""}
        </p>

        {/* Keywords */}
        {turn.keywords.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {isRoot && (
              <Badge className="border-[#D8D4CC] bg-[#FAF9F6] text-[#D45113] text-[10px] font-bold">
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
