import Link from "next/link";
 
import { fetchHistory } from "@/lib/history";
import { buildCategoryIndex } from "@/lib/posts";
 
export const dynamic = "force-dynamic";
 
export default async function CategoriesPage() {
  const history = await fetchHistory();
  const turns = [...history.turns].sort((left, right) => left.turn - right.turn);
  const categories = buildCategoryIndex(turns);

  return (
    <main className="min-h-screen bg-[#F5F2EB] text-[#252422]">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <nav className="flex items-center justify-between text-[10px] uppercase tracking-[0.32em] text-[#858076]">
          <Link href={"/" as any} className="transition-colors hover:text-[#252422] font-semibold">
            [← HOME]
          </Link>
          <span className="font-semibold">[CATEGORIES]</span>
        </nav>

        <header className="mx-auto mt-10 max-w-4xl text-center">
          <h1 className="mt-4 font-display text-4xl font-extrabold tracking-tighter text-[#252422] md:text-6xl">Categories</h1>
        </header>

        <div className="mx-auto mt-12 flex flex-wrap justify-center gap-3">
          {categories.map((category) => (
            <Link
              key={category.slug}
              href={`/categories/${category.slug}` as any}
              className="group inline-flex items-center gap-3 rounded-full border border-[#D8D4CC]/80 bg-white px-4 py-2 transition-colors hover:border-[#858076] hover:bg-[#FAF9F6] shadow-sm shadow-[#252422]/5"
            >
              <span className="font-display text-lg font-bold tracking-tighter text-[#252422]">{category.label}</span>
              <span className="text-[10px] uppercase tracking-[0.3em] text-[#858076] font-semibold">{category.turns.length}</span>
            </Link>
          ))}
        </div>
      </div>
    </main>
  );
}
