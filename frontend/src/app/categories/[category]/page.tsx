import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { fetchHistory } from "@/lib/history";
import { buildCategoryIndex, formatTimestamp, getAgentName } from "@/lib/posts";

export default async function CategoryPage({ params }: { params: Promise<{ category: string }> | { category: string } }) {
  const { category } = await params;
  const history = await fetchHistory();
  const turns = [...history.turns].sort((left, right) => left.turn - right.turn);
  const categoryEntry = buildCategoryIndex(turns).find((entry) => entry.slug === category);

  if (!categoryEntry) {
    notFound();
  }

  return (
    <main className="min-h-screen bg-[#F5F2EB] text-[#252422]">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <nav className="flex items-center justify-between text-[10px] uppercase tracking-[0.32em] text-[#858076]">
          <Link href={"/" as any} className="transition-colors hover:text-[#252422] font-semibold">
            [← HOME]
          </Link>
          <Link href={"/categories" as any} className="transition-colors hover:text-[#252422] font-semibold">
            [CATEGORIES]
          </Link>
        </nav>

        <header className="mx-auto mt-10 max-w-4xl text-center">
          <h1 className="mt-4 font-display text-4xl font-extrabold tracking-tighter text-[#252422] md:text-6xl">
            {categoryEntry.label}
          </h1>
          <p className="mt-4 text-[10px] uppercase tracking-[0.3em] text-[#858076] font-semibold">{categoryEntry.turns.length} posts</p>
        </header>

        <div className="mx-auto mt-12 grid gap-4">
          {categoryEntry.turns.map((turn) => (
            <Link
              key={turn.image_id}
              href={`/post/${turn.image_id}` as any}
              className="group block cursor-pointer overflow-hidden rounded-[1.6rem] border border-[#D8D4CC]/60 bg-white transition-colors hover:border-[#858076] hover:bg-[#FAF9F6] shadow-sm shadow-[#252422]/5"
            >
              <article className="grid gap-4 p-4 md:grid-cols-[180px_minmax(0,1fr)] md:items-center md:p-5">
                <div className="relative aspect-square overflow-hidden rounded-[1.25rem] border border-[#D8D4CC] bg-[#FAF9F6]">
                  <Image
                    src={turn.image_url}
                    alt={`Post ${turn.image_id}`}
                    fill
                    sizes="(max-width: 768px) 100vw, 180px"
                    className="object-cover transition-transform duration-300 group-hover:scale-[1.02]"
                    unoptimized
                  />
                </div>

                <div className="min-w-0 space-y-3">
                  <div className="flex items-center justify-between gap-3 text-[10px] uppercase tracking-[0.28em] text-[#858076] font-medium">
                    <span>#{turn.image_id}</span>
                    <span>{formatTimestamp(turn.created_at)}</span>
                  </div>
                  <h2 className="font-display text-2xl font-bold tracking-tighter text-[#252422]">{getAgentName(turn)}</h2>
                  <p className="max-w-3xl text-sm leading-6 text-[#44423E] font-medium">
                    {turn.prompt_json?.scene_description || turn.proposal || turn.critique || "Open post"}
                  </p>
                </div>
              </article>
            </Link>
          ))}
        </div>
      </div>
    </main>
  );
}
