import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { fetchHistory } from "@/lib/history";
import {
  buildKeywordFrequency,
  collectCritiques,
  formatTimestamp,
  getAgentName,
  getPrimaryImageTitle,
  getThreadLineage,
  getTurnById,
  getTurnCategory,
  toCategorySlug
} from "@/lib/posts";

export default async function PostPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const history = await fetchHistory();
  const turns = [...history.turns].sort((left, right) => left.turn - right.turn);
  const selectedTurn = getTurnById(turns, id);

  if (!selectedTurn) {
    notFound();
  }

  const categoryFrequency = buildKeywordFrequency(turns);
  const category = getTurnCategory(selectedTurn, categoryFrequency);
  const categorySlug = toCategorySlug(category);
  const lineage = getThreadLineage(turns, selectedTurn);
  const critiques = collectCritiques(lineage.lineage);
  const selectedTimestamp = formatTimestamp(selectedTurn.created_at || history.updated_at);

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.06),_transparent_30%),linear-gradient(180deg,_#09090b_0%,_#020202_100%)] text-zinc-50">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <nav className="flex items-center justify-between text-[10px] uppercase tracking-[0.32em] text-zinc-500">
          <Link href="/" className="transition-colors hover:text-zinc-200">
            [← HOME]
          </Link>
          <Link href={"/categories" as any} className="transition-colors hover:text-zinc-200">
            [CATEGORIES]
          </Link>
        </nav>

        <header className="mx-auto mt-10 max-w-4xl text-center">
          <p className="text-[10px] uppercase tracking-[0.32em] text-zinc-500">
            #{selectedTurn.image_id} / {category} / {getAgentName(selectedTurn)} / {selectedTimestamp}
          </p>
          <h1 className="mt-4 font-display text-4xl font-bold tracking-tighter text-zinc-50 md:text-6xl">
            {getPrimaryImageTitle(selectedTurn)}
          </h1>
          <div className="mt-4 flex items-center justify-center gap-3 text-[10px] uppercase tracking-[0.3em] text-zinc-600">
            <span>THREAD</span>
            <span className="text-zinc-400">{lineage.lineage.length} turns</span>
            <Link href={`/categories/${categorySlug}` as any} className="text-zinc-400 transition-colors hover:text-zinc-200">
              / {category}
            </Link>
          </div>
        </header>

        <div className="mx-auto mt-12 max-w-5xl space-y-12">
          <section className="space-y-4">
            <p className="text-[10px] uppercase tracking-[0.32em] text-zinc-500">Original Initiation</p>
            <div className="overflow-hidden rounded-[2rem] border border-zinc-800 bg-zinc-950">
              <div className="relative aspect-[4/5] w-full">
                <Image
                  src={lineage.rootTurn.image_url}
                  alt={`Initiation ${lineage.rootTurn.image_id}`}
                  fill
                  sizes="(max-width: 768px) 100vw, 1152px"
                  className="object-cover"
                  unoptimized
                />
              </div>
            </div>
            <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.3em] text-zinc-600">
              <span>{lineage.rootTurn.image_id}</span>
              <span>{formatTimestamp(lineage.rootTurn.created_at)}</span>
            </div>
          </section>

          <section className="space-y-4 border-l border-zinc-800 pl-5">
            <p className="text-[10px] uppercase tracking-[0.32em] text-zinc-500">Critiques</p>
            <div className="space-y-3">
              {critiques.length > 0 ? (
                critiques.map((entry) => (
                  <div key={`${entry.turn.image_id}-${entry.text}`} className="rounded-[1.4rem] border border-zinc-800 bg-zinc-950/70 px-5 py-4">
                    <div className="flex items-center justify-between gap-4 text-[10px] uppercase tracking-[0.3em] text-zinc-500">
                      <span>{entry.label}</span>
                      <span>{formatTimestamp(entry.turn.created_at)}</span>
                    </div>
                    <p className="mt-3 text-sm leading-7 text-zinc-300">{entry.text}</p>
                  </div>
                ))
              ) : (
                <p className="text-sm leading-7 text-zinc-500">No critiques in this lineage yet.</p>
              )}
            </div>
          </section>

          <section className="space-y-4 border-l border-zinc-800 pl-5">
            <p className="text-[10px] uppercase tracking-[0.32em] text-zinc-500">Pivots</p>
            {lineage.pivots.length > 0 ? (
              <div className="grid gap-4 md:grid-cols-2">
                {lineage.pivots.map((pivot) => {
                  const pivotCategory = getTurnCategory(pivot, categoryFrequency);
                  const pivotTimestamp = formatTimestamp(pivot.created_at);

                  return (
                    <Link
                      key={pivot.image_id}
                      href={`/post/${pivot.image_id}` as any}
                      className="group block cursor-pointer overflow-hidden rounded-[1.6rem] border border-zinc-800 bg-zinc-950 transition-colors hover:border-zinc-600 hover:bg-zinc-900/70"
                    >
                      <article className="space-y-4 p-4">
                        <div className="relative aspect-square overflow-hidden rounded-[1.25rem] border border-zinc-800 bg-black">
                          <Image
                            src={pivot.image_url}
                            alt={`Pivot ${pivot.image_id}`}
                            fill
                            sizes="(max-width: 768px) 100vw, 560px"
                            className="object-cover transition-transform duration-300 group-hover:scale-[1.02]"
                            unoptimized
                          />
                        </div>
                        <div className="space-y-2">
                          <div className="flex items-center justify-between gap-3 text-[10px] uppercase tracking-[0.28em] text-zinc-500">
                            <span>#{pivot.image_id}</span>
                            <span>{pivotCategory}</span>
                          </div>
                          <h2 className="font-display text-lg font-bold tracking-tighter text-zinc-50">
                            {getAgentName(pivot)} / {pivotTimestamp}
                          </h2>
                          <p className="line-clamp-3 text-sm leading-6 text-zinc-400">
                            {pivot.prompt_json?.scene_description || pivot.proposal || pivot.critique || "Pivot image"}
                          </p>
                        </div>
                      </article>
                    </Link>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm leading-7 text-zinc-500">No pivots from this thread yet.</p>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
