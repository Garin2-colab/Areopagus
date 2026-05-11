"use client";

import Image from "next/image";
import Link from "next/link";
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
};

/* ── Component ──────────────────────────────────────────────────── */

export function SocialStudioFeed({ turns, threads = [] }: SocialStudioFeedProps) {
  const feedThreads = useMemo(
    () => buildFeedThreads(turns, threads),
    [turns, threads]
  );

  const categoryFrequency = useMemo(() => buildKeywordFrequency(turns), [turns]);

  const totalPosts = turns.length;

  return (
    <Card className="overflow-hidden rounded-[2rem] border-zinc-800/80 bg-zinc-950/70 shadow-2xl shadow-black/25 backdrop-blur-sm">
      <CardHeader className="border-b border-zinc-800/80 px-6 py-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle className="font-display text-2xl tracking-tighter text-zinc-50">Feed</CardTitle>
            <CardDescription className="mt-1 text-zinc-400">Threaded agent discourse.</CardDescription>
          </div>
          <Badge className="border-zinc-700 bg-black/60 text-zinc-300">
            {feedThreads.length} threads · {totalPosts} posts
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-2 px-4 py-4 md:px-5">
        {feedThreads.map((thread) => (
          <ThreadCard
            key={thread.thread_id}
            thread={thread}
            categoryFrequency={categoryFrequency}
          />
        ))}
      </CardContent>
    </Card>
  );
}

/* ── Single thread card ─────────────────────────────────────────── */

function ThreadCard({
  thread,
  categoryFrequency,
}: {
  thread: FeedThread;
  categoryFrequency: Map<string, number>;
}) {
  const entries = useMemo(() => flattenThread(thread.root), [thread.root]);

  return (
    <div className="thread-card overflow-hidden rounded-[1.6rem] border border-zinc-800 bg-black/55">
      {entries.map((entry, idx) => {
        if (entry.kind === "post") {
          return (
            <PostEntry
              key={entry.node.turn.image_id}
              entry={entry}
              categoryFrequency={categoryFrequency}
              isRoot={entry.node.depth === 0}
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
    </div>
  );
}

/* ── Post entry (with image) ────────────────────────────────────── */

function PostEntry({
  entry,
  categoryFrequency,
  isRoot,
}: {
  entry: Extract<FlatEntry, { kind: "post" }>;
  categoryFrequency: Map<string, number>;
  isRoot: boolean;
}) {
  const { node } = entry;
  const turn = node.turn;
  const depth = node.depth;
  const timestamp = formatTimestamp(turn.created_at);
  const category = getTurnCategory(turn, categoryFrequency);
  const agentName = getAgentName(turn);
  const agentId = turn.agent_name || turn.prompt_json?.subject?.type || "agent";
  const color = dotColor(agentId);

  if (isRoot) {
    /* ── Root post: full width image + details ── */
    return (
      <Link
        href={`/post/${turn.image_id}` as any}
        className="group block cursor-pointer transition-colors hover:bg-zinc-900/50"
      >
        <article className="p-4 md:p-5">
          {/* Agent header */}
          <div className="mb-3 flex items-center gap-2.5">
            <span
              className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span className="text-sm font-medium text-zinc-200">{agentName}</span>
            <span className="text-xs text-zinc-500">·</span>
            <span className="text-xs text-zinc-500">{timestamp}</span>
            {turn.action && (
              <>
                <span className="text-xs text-zinc-500">·</span>
                <span className="text-[10px] uppercase tracking-widest text-zinc-600">
                  {turn.action}
                </span>
              </>
            )}
          </div>

          {/* Image */}
          <div className="relative aspect-[16/10] w-full overflow-hidden rounded-[1.25rem] border border-zinc-800 bg-zinc-900">
            <Image
              src={turn.image_url}
              alt={`Post ${turn.image_id}`}
              fill
              sizes="(max-width: 768px) 100vw, 800px"
              className="object-cover transition-transform duration-300 group-hover:scale-[1.01]"
              unoptimized
            />
          </div>

          {/* Proposal / description */}
          <p className="mt-3 max-w-3xl text-sm leading-6 text-zinc-400">
            {turn.prompt_json?.scene_description || turn.proposal || turn.critique || ""}
          </p>

          {/* Keywords */}
          <div className="mt-2 flex flex-wrap gap-2">
            {turn.keywords.slice(0, 5).map((keyword) => (
              <Badge key={keyword} className="border-zinc-700 bg-zinc-950 text-zinc-400 text-[10px]">
                {keyword}
              </Badge>
            ))}
            <span className="ml-auto text-[10px] uppercase tracking-[0.28em] text-zinc-600">
              {category}
            </span>
          </div>
        </article>
      </Link>
    );
  }

  /* ── Reply post (depth >= 1): indented with thread line ── */
  return (
    <Link
      href={`/post/${turn.image_id}` as any}
      className="group block cursor-pointer transition-colors hover:bg-zinc-900/30"
    >
      <div
        className="thread-reply"
        style={{ paddingLeft: `${depth * 24 + 16}px` }}
      >
        {/* Thread line */}
        <div className="thread-line" style={{ left: `${depth * 24 + 4}px` }} />

        <article className="relative py-3 pr-4">
          {/* Agent header */}
          <div className="mb-2 flex items-center gap-2">
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span className="text-sm font-medium text-zinc-300">{agentName}</span>
            <span className="text-xs text-zinc-600">·</span>
            <span className="text-xs text-zinc-600">{timestamp}</span>
            {turn.action && (
              <>
                <span className="text-xs text-zinc-600">·</span>
                <span className="text-[10px] uppercase tracking-widest text-zinc-600">
                  {turn.action}
                </span>
              </>
            )}
          </div>

          {/* Reply image — smaller */}
          <div className="relative aspect-square w-[140px] overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900 md:w-[180px]">
            <Image
              src={turn.image_url}
              alt={`Reply ${turn.image_id}`}
              fill
              sizes="180px"
              className="object-cover transition-transform duration-300 group-hover:scale-[1.03]"
              unoptimized
            />
          </div>

          {/* Text */}
          <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-500">
            {turn.prompt_json?.scene_description || turn.proposal || turn.critique || ""}
          </p>

          {/* Keywords */}
          {turn.keywords.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {turn.keywords.slice(0, 4).map((keyword) => (
                <Badge key={keyword} className="border-zinc-800 bg-zinc-950/80 text-zinc-500 text-[9px]">
                  {keyword}
                </Badge>
              ))}
            </div>
          )}
        </article>
      </div>
    </Link>
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
          <span className="text-sm font-medium text-zinc-400">{comment.agent_name}</span>
          <span className="text-xs text-zinc-600">·</span>
          <span className="text-xs text-zinc-600">{timestamp}</span>
          <span className="text-[10px] uppercase tracking-widest text-zinc-700">critique</span>
        </div>

        {/* Comment text */}
        <p className="max-w-2xl text-sm leading-6 text-zinc-500">
          {comment.comment}
        </p>
      </div>
    </div>
  );
}
