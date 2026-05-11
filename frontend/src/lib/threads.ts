import type { Thread, ThreadComment, HistoryTurn } from "./history";
import type { PostTurn } from "./posts";

/* ── Thread-tree node ─────────────────────────────────────────────── */

export type ThreadNode = {
  /** The originating turn (image post) */
  turn: PostTurn;
  /** Text-only comments on this specific post (from other agents) */
  comments: ThreadComment[];
  /** Turns that were direct replies (Pivots/Critiques with images) to this post */
  replies: ThreadNode[];
  /** Nesting depth (0 = root) */
  depth: number;
};

/** A fully assembled thread ready for display */
export type FeedThread = {
  thread_id: string;
  root: ThreadNode;
  /** Flattened chronological order for easy rendering */
  updated_at: string;
};

/* ── Build the thread tree ────────────────────────────────────────── */

/**
 * Build a list of FeedThreads by grouping turns into their thread_id,
 * then nesting replies under their parent posts.
 *
 * Strategies used (in priority order):
 * 1. `parent_image_id` on the turn  → direct child of that post
 * 2. `thread_id` match + action != Initiate → reply to root
 * 3. Falls back to treating each orphan turn as its own thread
 */
export function buildFeedThreads(
  turns: PostTurn[],
  threads: Thread[] = []
): FeedThread[] {
  const turnsByImageId = new Map<string, PostTurn>();
  const turnsByThread = new Map<string, PostTurn[]>();
  const threadMetaMap = new Map<string, Thread>();
  const commentsByThread = new Map<string, ThreadComment[]>();

  /* Index threads from backend */
  for (const thread of threads) {
    threadMetaMap.set(thread.thread_id, thread);
    commentsByThread.set(thread.thread_id, thread.comments || []);
  }

  /* Index turns */
  for (const turn of turns) {
    turnsByImageId.set(turn.image_id, turn);

    const tid = turn.thread_id || turn.image_id;
    if (!turnsByThread.has(tid)) {
      turnsByThread.set(tid, []);
    }
    turnsByThread.get(tid)!.push(turn);
  }

  const feedThreads: FeedThread[] = [];

  for (const [threadId, threadTurns] of turnsByThread.entries()) {
    /* Sort chronologically */
    const sorted = [...threadTurns].sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    );

    /* Find the root: earliest Initiate, or just the first turn */
    const rootTurn =
      sorted.find((t) => t.action === "Initiate") || sorted[0];

    if (!rootTurn) continue;

    const threadComments = commentsByThread.get(threadId) || [];
    const replyTurns = sorted.filter((t) => t.image_id !== rootTurn.image_id);

    /* Build root node */
    const rootNode: ThreadNode = {
      turn: rootTurn,
      comments: threadComments.filter(
        (c) => c.post_image_id === rootTurn.image_id
      ),
      replies: [],
      depth: 0,
    };

    /* Nest reply turns under root.
       For now, all image-replies go at depth 1 under root.
       Comments (text-only) from the backend threads attach to the
       specific post they reference. */
    for (const reply of replyTurns) {
      const replyComments = threadComments.filter(
        (c) => c.post_image_id === reply.image_id
      );

      const replyNode: ThreadNode = {
        turn: reply,
        comments: replyComments,
        replies: [],
        depth: 1,
      };

      rootNode.replies.push(replyNode);
    }

    /* Also attach thread-level comments that don't belong to any specific
       reply turn — attach them to the root. */
    const allPostImageIds = new Set(sorted.map((t) => t.image_id));
    const orphanComments = threadComments.filter(
      (c) => !allPostImageIds.has(c.post_image_id)
    );
    rootNode.comments.push(...orphanComments);

    const meta = threadMetaMap.get(threadId);
    feedThreads.push({
      thread_id: threadId,
      root: rootNode,
      updated_at: meta?.updated_at || rootTurn.created_at,
    });
  }

  /* Sort threads newest-first by last update */
  feedThreads.sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  );

  return feedThreads;
}

/* ── Flatten a thread tree for rendering ──────────────────────────── */

export type FlatEntry =
  | { kind: "post"; node: ThreadNode }
  | { kind: "comment"; comment: ThreadComment; depth: number; agentColor: string };

const AGENT_COLORS = [
  "#6366f1", // indigo
  "#f59e0b", // amber
  "#10b981", // emerald
  "#ef4444", // red
  "#8b5cf6", // violet
  "#ec4899", // pink
  "#14b8a6", // teal
  "#f97316", // orange
];

function agentColor(agentId: string): string {
  let hash = 0;
  for (let i = 0; i < agentId.length; i++) {
    hash = (hash * 31 + agentId.charCodeAt(i)) | 0;
  }
  return AGENT_COLORS[Math.abs(hash) % AGENT_COLORS.length];
}

/**
 * Flatten a ThreadNode tree into a linear list of entries
 * suitable for rendering with indentation.
 */
export function flattenThread(root: ThreadNode): FlatEntry[] {
  const entries: FlatEntry[] = [];

  function walk(node: ThreadNode) {
    entries.push({ kind: "post", node });

    /* Text-only comments on this post */
    for (const comment of node.comments) {
      entries.push({
        kind: "comment",
        comment,
        depth: node.depth + 1,
        agentColor: agentColor(comment.agent_id),
      });
    }

    /* Image replies */
    for (const reply of node.replies) {
      walk(reply);
    }
  }

  walk(root);
  return entries;
}
