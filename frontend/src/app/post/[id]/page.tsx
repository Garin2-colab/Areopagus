import Link from "next/link";
import { notFound } from "next/navigation";

import { fetchHistory } from "@/lib/history";
import { buildKeywordFrequency, getTurnById } from "@/lib/posts";
import { buildFeedThreads, type ThreadNode } from "@/lib/threads";
import { FullThreadView } from "@/components/social-studio-feed";

export default async function PostPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const history = await fetchHistory();
  const turns = [...history.turns].sort((left, right) => left.turn - right.turn);
  const threads = history.threads ?? [];
  const selectedTurn = getTurnById(turns, id);

  if (!selectedTurn) {
    notFound();
  }

  const categoryFrequency = buildKeywordFrequency(turns);
  const feedThreads = buildFeedThreads(turns, threads);

  // Find the full thread tree that contains this specific turn
  let selectedThread = feedThreads.find(
    (t) => t.thread_id === selectedTurn.thread_id || t.root.turn.image_id === selectedTurn.image_id
  );

  if (!selectedThread) {
    const hasId = (node: ThreadNode): boolean => {
      if (node.turn.image_id === id) return true;
      return node.replies.some(hasId);
    };
    selectedThread = feedThreads.find((t) => hasId(t.root));
  }

  if (!selectedThread) {
    notFound();
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.06),_transparent_30%),linear-gradient(180deg,_#09090b_0%,_#020202_100%)] text-zinc-50">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <nav className="mb-10 flex items-center justify-between text-[10px] uppercase tracking-[0.32em] text-zinc-500">
          <Link href="/" className="transition-colors hover:text-zinc-200">
            [← HOME]
          </Link>
          <Link href={"/categories" as any} className="transition-colors hover:text-zinc-200">
            [CATEGORIES]
          </Link>
        </nav>

        {/* Full threaded discourse view */}
        <FullThreadView
          thread={selectedThread}
          categoryFrequency={categoryFrequency}
        />
      </div>
    </main>
  );
}
