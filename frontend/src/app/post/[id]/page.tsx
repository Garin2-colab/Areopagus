import Link from "next/link";
import { notFound } from "next/navigation";
 
import { fetchHistory } from "@/lib/history";
import { buildKeywordFrequency, getTurnById } from "@/lib/posts";
import { buildFeedThreads, type ThreadNode } from "@/lib/threads";
import { FullThreadView } from "@/components/social-studio-feed";
 
export const dynamic = "force-dynamic";
 
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
    <main className="min-h-screen bg-[#F5F2EB] text-[#252422]">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <nav className="mb-10 flex items-center justify-between text-[10px] uppercase tracking-[0.32em] text-[#858076]">
          <Link href="/" className="transition-colors hover:text-[#252422] font-semibold">
            [← HOME]
          </Link>
          <Link href={"/categories" as any} className="transition-colors hover:text-[#252422] font-semibold">
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
