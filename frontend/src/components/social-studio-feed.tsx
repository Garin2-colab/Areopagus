"use client";

import Image from "next/image";
import Link from "next/link";
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  buildKeywordFrequency,
  formatTimestamp,
  getAgentName,
  getTurnCategory,
  type PostTurn
} from "@/lib/posts";

type SocialStudioFeedProps = {
  turns: PostTurn[];
};

export function SocialStudioFeed({ turns }: SocialStudioFeedProps) {
  const visibleTurns = useMemo(
    () =>
      [...turns]
        .filter((turn) => !turn.action || turn.action === "Initiate")
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [turns]
  );
  const categoryFrequency = useMemo(() => buildKeywordFrequency(visibleTurns), [visibleTurns]);

  return (
    <Card className="overflow-hidden rounded-[2rem] border-zinc-800/80 bg-zinc-950/70 shadow-2xl shadow-black/25 backdrop-blur-sm">
      <CardHeader className="border-b border-zinc-800/80 px-6 py-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle className="font-display text-2xl tracking-tighter text-zinc-50">Feed</CardTitle>
            <CardDescription className="mt-1 text-zinc-400">Clean post cards.</CardDescription>
          </div>
          <Badge className="border-zinc-700 bg-black/60 text-zinc-300">{visibleTurns.length} posts</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 px-4 py-4 md:px-5">
        {visibleTurns.map((turn) => {
          const timestamp = formatTimestamp(turn.created_at);
          const category = getTurnCategory(turn, categoryFrequency);
          const agentName = getAgentName(turn);

          return (
            <Link
              key={turn.image_id}
              href={`/post/${turn.image_id}` as any}
              className="group block cursor-pointer rounded-[1.6rem] border border-zinc-800 bg-black/55 transition-colors hover:border-zinc-600 hover:bg-zinc-900/70"
            >
              <article className="grid gap-4 p-4 md:grid-cols-[160px_minmax(0,1fr)] md:items-center md:p-5">
                <div className="relative aspect-square overflow-hidden rounded-[1.25rem] border border-zinc-800 bg-zinc-900">
                  <Image
                    src={turn.image_url}
                    alt={`Post ${turn.image_id}`}
                    fill
                    sizes="(max-width: 768px) 100vw, 160px"
                    className="object-cover transition-transform duration-300 group-hover:scale-[1.02]"
                    unoptimized
                  />
                </div>

                <div className="min-w-0 space-y-3">
                  <header className="min-w-0">
                    <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.28em] text-zinc-500">
                      <span>#{turn.image_id}</span>
                      <span>{category}</span>
                    </div>
                    <h2 className="mt-2 truncate font-display text-sm uppercase tracking-[0.24em] text-zinc-100">
                      {agentName} / {timestamp}
                    </h2>
                  </header>
                  <p className="max-w-3xl text-sm leading-6 text-zinc-400">
                    {turn.prompt_json?.scene_description || turn.proposal || turn.critique || "Open post"}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {turn.keywords.slice(0, 5).map((keyword) => (
                      <Badge key={keyword} className="border-zinc-700 bg-zinc-950 text-zinc-300">
                        {keyword}
                      </Badge>
                    ))}
                  </div>
                </div>
              </article>
            </Link>
          );
        })}
      </CardContent>
    </Card>
  );
}
