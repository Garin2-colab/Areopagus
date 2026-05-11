export type DebateContextEntry = {
  turn?: number;
  critique?: string;
  keywords?: string[];
};

export type HistoryTurn = {
  turn: number;
  created_at: string;
  image_id: string;
  image_url: string;
  keywords: string[];
  prompt_json?: {
    debate_context?: DebateContextEntry[];
    scene_description?: string;
    subject?: {
      type?: string;
    };
    [key: string]: unknown;
  };
  action?: string;
  agent_name?: string;
  category?: string;
  thread_id?: string;
  parent_image_id?: string;
  proposal?: string;
  critique?: string;
  agent2?: {
    critique?: string;
    agreed_keywords?: string[];
  };
};

export type ThreadComment = {
  id: string;
  agent_id: string;
  agent_name: string;
  post_image_id: string;
  comment: string;
  interest_score: number;
  created_at: string;
};

export type Thread = {
  thread_id: string;
  root_image_id: string;
  title?: string;
  agent_id?: string;
  action?: string;
  interest_score?: number;
  active?: boolean;
  category?: string;
  posts: string[];
  comments: ThreadComment[];
  created_at: string;
  updated_at: string;
};

export type HistoryData = {
  project?: string;
  created_at?: string;
  updated_at?: string;
  turns: HistoryTurn[];
  threads?: Thread[];
  graph?: {
    nodes?: Array<Record<string, unknown>>;
    edges?: Array<Record<string, unknown>>;
  };
};

export function sortTurnsNewestFirst(turns: HistoryTurn[]) {
  return [...turns].sort((left, right) => {
    const dateDelta = new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
    if (dateDelta !== 0) return dateDelta;
    return right.turn - left.turn;
  });
}

function resolveHistorySource() {
  const configured = process.env.MODAL_API_URL || process.env.NEXT_PUBLIC_MODAL_API_URL;
  if (configured) {
    return configured;
  }

  if (typeof window !== "undefined") {
    return "/api/history";
  }

  throw new Error("MODAL_API_URL is not configured.");
}

export async function fetchHistory(): Promise<HistoryData> {
  const response = await fetch(resolveHistorySource(), {
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch history: ${response.status} ${response.statusText}`);
  }

  const data = (await response.json()) as HistoryData;
  return {
    ...data,
    turns: Array.isArray(data.turns) ? data.turns : []
  };
}
