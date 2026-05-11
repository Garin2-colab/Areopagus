import Link from "next/link";

import { fetchHistory } from "@/lib/history";
import { buildCategoryIndex } from "@/lib/posts";

export default async function CategoriesPage() {
  const history = await fetchHistory();
  const turns = [...history.turns].sort((left, right) => left.turn - right.turn);
  const categories = buildCategoryIndex(turns);

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.06),_transparent_30%),linear-gradient(180deg,_#09090b_0%,_#020202_100%)] text-zinc-50">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <nav className="flex items-center justify-between text-[10px] uppercase tracking-[0.32em] text-zinc-500">
          <Link href={"/" as any} className="transition-colors hover:text-zinc-200">
            [← HOME]
          </Link>
          <span>[CATEGORIES]</span>
        </nav>

        <header className="mx-auto mt-10 max-w-4xl text-center">
          <h1 className="mt-4 font-display text-4xl font-bold tracking-tighter text-zinc-50 md:text-6xl">Categories</h1>
        </header>

        <div className="mx-auto mt-12 flex flex-wrap justify-center gap-3">
          {categories.map((category) => (
            <Link
              key={category.slug}
              href={`/categories/${category.slug}` as any}
              className="group inline-flex items-center gap-3 rounded-full border border-zinc-800 bg-zinc-950/70 px-4 py-2 transition-colors hover:border-zinc-600 hover:bg-zinc-900/70"
            >
              <span className="font-display text-lg font-bold tracking-tighter text-zinc-50">{category.label}</span>
              <span className="text-[10px] uppercase tracking-[0.3em] text-zinc-500">{category.turns.length}</span>
            </Link>
          ))}
        </div>
      </div>
    </main>
  );
}
