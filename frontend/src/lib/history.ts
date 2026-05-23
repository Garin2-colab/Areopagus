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
  image_webp?: {
    path?: string;
    url?: string;
    format?: string;
    quality?: number;
    source_mime_type?: string;
    size_bytes?: number;
    dimensions?: {
      width: number;
      height: number;
    };
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
  if (typeof window !== "undefined") {
    return "/api/history";
  }

  const configured = process.env.MODAL_API_URL || process.env.NEXT_PUBLIC_MODAL_API_URL;
  if (configured) {
    return configured;
  }

  throw new Error("MODAL_API_URL is not configured.");
}

function sanitizeImageUrls(url: string | undefined): string {
  if (!url) return "";
  if (url.includes("-get-image.modal.run") || url.includes("-get-image-dev.modal.run")) {
    const match = url.match(/[?&]id=([^&]+)/);
    if (match && match[1]) {
      const vMatch = url.match(/[?&]v=([^&]+)/);
      const vParam = vMatch ? `&v=${vMatch[1]}` : "";
      const devParam = url.includes("-dev.modal.run") ? "&dev=true" : "";
      return `/api/image?id=${match[1]}${vParam}${devParam}`;
    }
  }
  return url;
}

export async function fetchHistory(bypassCache = false): Promise<HistoryData> {
  const source = resolveHistorySource();
  const isClient = typeof window !== "undefined";

  let fetchUrl = source;
  const init: RequestInit = {};

  if (isClient) {
    if (bypassCache) {
      fetchUrl = `${source}?bypass=true`;
      init.cache = "no-store";
    }
  } else {
    if (bypassCache) {
      init.cache = "no-store";
    } else {
      (init as any).next = { revalidate: 86400, tags: ["history"] };
    }
  }

  const response = await fetch(fetchUrl, init);

  if (!response.ok) {
    throw new Error(`Failed to fetch history: ${response.status} ${response.statusText}`);
  }

  const data = (await response.json()) as HistoryData;
  
  const turns = (Array.isArray(data.turns) ? data.turns : []).map(turn => {
    const turnCopy = { 
      ...turn, 
      image_url: sanitizeImageUrls(turn.image_url) 
    };
    if (turnCopy.image_webp) {
      turnCopy.image_webp = {
        ...turnCopy.image_webp,
        url: sanitizeImageUrls(turnCopy.image_webp.url)
      };
    }
    return turnCopy;
  });

  let graph = data.graph;
  if (graph && Array.isArray(graph.nodes)) {
    graph = {
      ...graph,
      nodes: graph.nodes.map(node => {
        if (node.type === "image" && typeof node.url === "string") {
          return { ...node, url: sanitizeImageUrls(node.url) };
        }
        return node;
      })
    };
  }

  return {
    ...data,
    turns,
    graph
  };
}

