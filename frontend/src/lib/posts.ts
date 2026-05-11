import type { DebateContextEntry, HistoryTurn } from "./history";

export type PostTurn = HistoryTurn & {
  action?: string;
  agent_name?: string;
  category?: string;
  thread_id?: string;
  parent_image_id?: string;
  proposal?: string;
  prompt_json?: {
    debate_context?: DebateContextEntry[];
    scene_description?: string;
    subject?: {
      type?: string;
    };
    [key: string]: unknown;
  };
  agent2?: {
    critique?: string;
    agreed_keywords?: string[];
  };
};

function normalizeLabel(value: string) {
  return value
    .trim()
    .replace(/^#/, "")
    .replace(/\s+/g, " ")
    .toLowerCase();
}

export function formatTimestamp(value?: string) {
  if (!value) return "";

  try {
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export function getAgentName(turn: PostTurn) {
  return turn.agent_name || turn.prompt_json?.subject?.type || "Agent";
}

export function getPrimaryImageTitle(turn: PostTurn) {
  return turn.prompt_json?.subject?.type || turn.prompt_json?.scene_description || turn.proposal || turn.image_id;
}

export function buildKeywordFrequency(turns: PostTurn[]) {
  const frequency = new Map<string, number>();

  for (const turn of turns) {
    for (const keyword of turn.keywords || []) {
      const normalized = normalizeLabel(keyword);
      frequency.set(normalized, (frequency.get(normalized) || 0) + 1);
    }
  }

  return frequency;
}

export function getTurnCategory(turn: PostTurn, frequency: Map<string, number>) {
  if (turn.category?.trim()) return turn.category.trim().replace(/^#/, "");
  if (turn.action?.trim()) return turn.action.trim().replace(/^#/, "");

  const keywords = turn.keywords || [];
  if (keywords.length > 0) {
    const ranked = [...keywords].sort((left, right) => {
      const leftScore = frequency.get(normalizeLabel(left)) || 0;
      const rightScore = frequency.get(normalizeLabel(right)) || 0;
      return rightScore - leftScore;
    });

    return (ranked[0] || keywords[0]).trim().replace(/^#/, "");
  }

  return "post";
}

export function toCategorySlug(value: string) {
  return normalizeLabel(value).replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "post";
}

export function getTurnById(turns: PostTurn[], id: string) {
  return turns.find((turn) => turn.image_id === id || String(turn.turn) === id);
}

function getDebateContextTurns(turn: PostTurn) {
  return (turn.prompt_json?.debate_context || [])
    .map((entry) => entry.turn)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
}

function gatherAncestors(turns: PostTurn[], selectedTurn: PostTurn) {
  const byTurnNumber = new Map<number, PostTurn>();

  for (const turn of turns) {
    byTurnNumber.set(turn.turn, turn);
  }

  const seen = new Set<number>();
  const stack = [...getDebateContextTurns(selectedTurn)];

  while (stack.length > 0) {
    const current = stack.pop();
    if (current == null || seen.has(current)) continue;

    seen.add(current);

    const ancestor = byTurnNumber.get(current);
    if (!ancestor) continue;

    for (const next of getDebateContextTurns(ancestor)) {
      if (!seen.has(next)) stack.push(next);
    }
  }

  return turns.filter((turn) => seen.has(turn.turn)).sort((left, right) => left.turn - right.turn);
}

export function getThreadLineage(turns: PostTurn[], selectedTurn: PostTurn) {
  const ancestors = gatherAncestors(turns, selectedTurn);
  const lineage = [...ancestors, selectedTurn].filter(
    (turn, index, array) => array.findIndex((candidate) => candidate.image_id === turn.image_id) === index
  );

  const lineageIds = new Set(lineage.map((turn) => turn.image_id));
  const rootTurn = lineage[0] || selectedTurn;
  const currentTurnNumber = selectedTurn.turn;

  const pivots = turns
    .filter((turn) => {
      if (turn.image_id === selectedTurn.image_id) return false;
      if (turn.parent_image_id === selectedTurn.image_id) return true;
      return getDebateContextTurns(turn).includes(currentTurnNumber);
    })
    .sort((left, right) => left.turn - right.turn)
    .filter((turn) => !lineageIds.has(turn.image_id));

  return {
    rootTurn,
    lineage,
    pivots
  };
}

export function collectCritiques(turns: PostTurn[]) {
  const critiques: Array<{ turn: PostTurn; text: string; label: string }> = [];
  const seen = new Set<string>();

  for (const turn of turns) {
    const entries = [turn.critique, turn.agent2?.critique].filter(
      (value): value is string => typeof value === "string" && value.trim().length > 0
    );

    for (const text of entries) {
      const key = `${turn.image_id}:${text}`;
      if (seen.has(key)) continue;
      seen.add(key);
      critiques.push({
        turn,
        text,
        label: `Turn ${turn.turn}`
      });
    }
  }

  return critiques;
}

export function buildCategoryIndex(turns: PostTurn[]) {
  const frequency = buildKeywordFrequency(turns);
  const categories = new Map<
    string,
    {
      label: string;
      slug: string;
      turns: PostTurn[];
    }
  >();

  for (const turn of turns) {
    const label = getTurnCategory(turn, frequency);
    const slug = toCategorySlug(label);
    const existing = categories.get(slug);

    if (existing) {
      existing.turns.push(turn);
      continue;
    }

    categories.set(slug, {
      label,
      slug,
      turns: [turn]
    });
  }

  return [...categories.values()]
    .map((entry) => ({
      ...entry,
      turns: [...entry.turns].sort((left, right) => left.turn - right.turn)
    }))
    .sort((left, right) => right.turns.length - left.turns.length || left.label.localeCompare(right.label));
}

export function getCategoryTurns(turns: PostTurn[], categorySlug: string) {
  const frequency = buildKeywordFrequency(turns);
  return turns
    .filter((turn) => toCategorySlug(getTurnCategory(turn, frequency)) === categorySlug)
    .sort((left, right) => left.turn - right.turn);
}
