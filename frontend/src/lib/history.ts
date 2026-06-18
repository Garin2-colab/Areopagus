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
    width?: number;
    height?: number;
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

export type InspirationItem = {
  id: string;
  image_url: string;
  keywords: string[];
  created_at: string;
};

export type BrainItem = {
  id: string;
  type: "image" | "note" | "reference";
  source_file: string;
  title: string;
  keywords: string[];
  summary: string;
  mood: string;
  color_palette: string[];
  excerpt: string;
  image_url: string;
  full_text?: string;
  created_at: string;
  updated_at: string;
};

export type BriefItem = {
  brief_id: string;
  title: string;
  thesis: string;
  visual_rules: string[];
  mood: string;
  color_palette: string[];
  source_items: string[];
  keywords: string[];
  active: boolean;
  auto_generated: boolean;
  created_at: string;
  updated_at: string;
};

export type HistoryData = {
  project?: string;
  created_at?: string;
  updated_at?: string;
  turns: HistoryTurn[];
  threads?: Thread[];
  inspiration?: InspirationItem[];
  brain?: BrainItem[];
  briefs?: BriefItem[];
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

function sanitizeImageUrls(url: string | undefined, format?: string): string {
  if (!url) return "";
  if (url.includes("-get-image.modal.run") || url.includes("-get-image-dev.modal.run")) {
    const match = url.match(/[?&]id=([^&]+)/);
    if (match && match[1]) {
      const vMatch = url.match(/[?&]v=([^&]+)/);
      const vParam = vMatch ? `&v=${vMatch[1]}` : "";
      const devParam = url.includes("-dev.modal.run") ? "&dev=true" : "";
      const formatParam = format ? `&format=${format}` : "";
      return `/api/image?id=${match[1]}${vParam}${devParam}${formatParam}`;
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
    const format = turn.image_webp?.format;
    const turnCopy = { 
      ...turn, 
      image_url: sanitizeImageUrls(turn.image_url, format) 
    };
    if (turnCopy.image_webp) {
      turnCopy.image_webp = {
        ...turnCopy.image_webp,
        url: sanitizeImageUrls(turnCopy.image_webp.url, format)
      };
    }
    return turnCopy;
  });

  const inspiration = (Array.isArray(data.inspiration) ? data.inspiration : []).map(item => ({
    ...item,
    image_url: sanitizeImageUrls(item.image_url)
  }));

  const brain = (Array.isArray(data.brain) ? data.brain : []).map(item => ({
    ...item,
    image_url: sanitizeImageUrls(item.image_url)
  }));

  let graph = data.graph;
  if (graph && Array.isArray(graph.nodes)) {
    graph = {
      ...graph,
      nodes: graph.nodes.map(node => {
        if ((node.type === "image" || node.type === "inspiration" || String(node.type).startsWith("brain")) && typeof node.url === "string") {
          return { ...node, url: sanitizeImageUrls(node.url) };
        }
        return node;
      })
    };
  }

  const briefs: BriefItem[] = (data.briefs || []).map((item: Record<string, unknown>) => ({
    brief_id: String(item.brief_id || ""),
    title: String(item.title || ""),
    thesis: String(item.thesis || ""),
    visual_rules: Array.isArray(item.visual_rules) ? item.visual_rules.map(String) : [],
    mood: String(item.mood || ""),
    color_palette: Array.isArray(item.color_palette) ? item.color_palette.map(String) : [],
    source_items: Array.isArray(item.source_items) ? item.source_items.map(String) : [],
    keywords: Array.isArray(item.keywords) ? item.keywords.map(String) : [],
    active: Boolean(item.active ?? true),
    auto_generated: Boolean(item.auto_generated ?? true),
    created_at: String(item.created_at || ""),
    updated_at: String(item.updated_at || ""),
  }));

  return {
    ...data,
    turns,
    inspiration,
    brain,
    briefs,
    graph
  };
}

