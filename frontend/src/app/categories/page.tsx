"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import Image from "next/image";
import { fetchHistory, type HistoryTurn } from "@/lib/history";
import { buildCategoryIndex, formatTimestamp, getAgentName } from "@/lib/posts";

export default function CategoriesPage() {
  const [turns, setTurns] = useState<HistoryTurn[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchHistory()
      .then((history) => {
        const sorted = [...history.turns].sort((left, right) => left.turn - right.turn);
        setTurns(sorted);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  const categories = useMemo(() => buildCategoryIndex(turns), [turns]);

  // Default selection to first category once categories load
  useEffect(() => {
    if (categories.length > 0 && !selectedCategory) {
      setSelectedCategory(categories[0].slug);
    }
  }, [categories, selectedCategory]);

  const activeCategoryEntry = useMemo(() => {
    return categories.find((c) => c.slug === selectedCategory) ?? null;
  }, [categories, selectedCategory]);

  return (
    <main className="min-h-screen bg-[#F5F2EB] text-[#252422]">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <nav className="flex items-center justify-between text-[10px] uppercase tracking-[0.32em] text-[#858076]">
          <Link href={"/" as any} className="transition-colors hover:text-[#252422] font-semibold">
            [← HOME]
          </Link>
          <span className="font-semibold text-[#858076]">[CATEGORIES]</span>
        </nav>

        <header className="mx-auto mt-10 max-w-4xl text-center">
          <h1 className="mt-4 font-display text-4xl font-extrabold tracking-tighter text-[#D45113] md:text-6xl">
            Categories
          </h1>
        </header>

        {loading ? (
          <div className="mt-12 text-center text-sm text-[#858076]">Loading categories...</div>
        ) : (
          <>
            <div className="mx-auto mt-12 flex flex-wrap justify-center gap-3">
              {categories.map((category) => {
                const isSelected = selectedCategory === category.slug;
                return (
                  <button
                    key={category.slug}
                    onClick={() => setSelectedCategory(category.slug)}
                    className={`group inline-flex items-center gap-3 rounded-full border px-5 py-2.5 transition-all shadow-sm shadow-[#252422]/5 ${
                      isSelected
                        ? "border-[#D45113] bg-white ring-1 ring-[#D45113]"
                        : "border-[#D8D4CC]/80 bg-white hover:border-[#858076] hover:bg-[#FAF9F6]"
                    }`}
                  >
                    <span
                      className={`font-display text-lg font-bold tracking-tighter transition-colors ${
                        isSelected ? "text-[#D45113]" : "text-[#252422] group-hover:text-[#D45113]"
                      }`}
                    >
                      {category.label}
                    </span>
                    <span
                      className={`text-[10px] uppercase tracking-[0.3em] font-semibold transition-colors ${
                        isSelected ? "text-[#D45113]" : "text-[#858076]"
                      }`}
                    >
                      {category.turns.length}
                    </span>
                  </button>
                );
              })}
            </div>

            {activeCategoryEntry && (
              <div className="mx-auto mt-12 grid gap-4 animate-in fade-in-50 duration-200">
                {activeCategoryEntry.turns.map((turn) => (
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
                        <h2 className="font-display text-2xl font-bold tracking-tighter text-[#252422]">
                          {getAgentName(turn)}
                        </h2>
                        <p className="max-w-3xl text-sm leading-6 text-[#44423E] font-medium">
                          {turn.prompt_json?.scene_description || turn.proposal || turn.critique || "Open post"}
                        </p>
                      </div>
                    </article>
                  </Link>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
