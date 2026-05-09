"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";

type MockHistory = typeof import("../data/mock_history.json");
type Turn = MockHistory["turns"][number];

type GraphNode =
  | {
      id: string;
      kind: "image";
      turn: number;
      imageUrl: string;
      label: string;
      x?: number;
      y?: number;
      fx?: number;
      fy?: number;
      val?: number;
    }
  | {
      id: string;
      kind: "keyword";
      label: string;
      x?: number;
      y?: number;
      fx?: number;
      fy?: number;
      val?: number;
    };

type GraphLink = {
  source: string;
  target: string;
};

const ForceGraph2D = dynamic(async () => (await import("react-force-graph-2d")).default, {
  ssr: false
});

function buildGraph(turns: Turn[]) {
  const nodes: GraphNode[] = [];
  const links: GraphLink[] = [];
  const keywordNodes = new Map<string, GraphNode>();

  for (const turn of turns) {
    const imageNode: GraphNode = {
      id: turn.image_id,
      kind: "image",
      turn: turn.turn,
      imageUrl: turn.image_url,
      label: `Turn ${turn.turn}`
    };
    nodes.push(imageNode);

    for (const keyword of turn.keywords) {
      if (!keywordNodes.has(keyword)) {
        const keywordNode: GraphNode = {
          id: keyword,
          kind: "keyword",
          label: keyword
        };
        keywordNodes.set(keyword, keywordNode);
        nodes.push(keywordNode);
      }

      links.push({ source: keyword, target: turn.image_id });
    }
  }

  return { nodes, links };
}

type KnowledgeWebProps = {
  turns: Turn[];
  onImageSelect: (turnId: string) => void;
  selectedTurnId?: string | null;
};

export function KnowledgeWeb({ turns, onImageSelect, selectedTurnId }: KnowledgeWebProps) {
  const graphRef = useRef<any>(null);
  const { nodes, links } = useMemo(() => buildGraph(turns), [turns]);
  const [hoverNode, setHoverNode] = useState<GraphNode | null>(null);
  const selectedNode = useMemo(
    () => nodes.find((node) => node.kind === "image" && node.id === selectedTurnId) ?? null,
    [nodes, selectedTurnId]
  );

  useEffect(() => {
    if (!graphRef.current) return;
    graphRef.current.zoomToFit(300, 60);
  }, []);

  return (
    <div className="border border-zinc-800 bg-black">
      <div className="relative h-[72vh] min-h-[640px] bg-black">
        <ForceGraph2D
          ref={graphRef}
          graphData={{ nodes, links }}
          backgroundColor="#000000"
          nodeRelSize={4}
          linkWidth={0.6}
          linkColor={() => "rgba(160,160,160,0.35)"}
          linkDirectionalParticles={0}
          nodePointerAreaPaint={(node: unknown, color: string, ctx: CanvasRenderingContext2D) => {
            const typed = node as GraphNode;
            ctx.fillStyle = color;
            ctx.beginPath();
            const radius = typed.kind === "image" ? 20 : 12;
            ctx.arc(typed.x ?? 0, typed.y ?? 0, radius, 0, Math.PI * 2, false);
            ctx.fill();
          }}
          nodeCanvasObjectMode={() => "replace"}
          nodeCanvasObject={(node: unknown, ctx: CanvasRenderingContext2D, globalScale: number) => {
            const typed = node as GraphNode;
            const hovered = hoverNode?.id === typed.id;
            const selected = selectedNode?.id === typed.id;
            const radius = typed.kind === "image" ? 16 : 6;
            const labelScale = Math.max(0.55, 1 / globalScale);

            ctx.save();
            ctx.translate(typed.x ?? 0, typed.y ?? 0);

            ctx.fillStyle = selected || hovered ? "#f5f5f5" : "#a3a3a3";
            ctx.beginPath();
            ctx.arc(0, 0, radius, 0, Math.PI * 2);
            ctx.fill();

            if (typed.kind === "image") {
              ctx.strokeStyle = selected || hovered ? "#e5e5e5" : "#737373";
              ctx.lineWidth = selected || hovered ? 1.5 : 1;
              ctx.beginPath();
              ctx.arc(0, 0, radius + 4, 0, Math.PI * 2);
              ctx.stroke();

              ctx.save();
              ctx.beginPath();
              ctx.arc(0, 0, radius - 1, 0, Math.PI * 2);
              ctx.clip();
              ctx.fillStyle = "#111";
              ctx.fillRect(-radius, -radius, radius * 2, radius * 2);
              ctx.restore();

              ctx.fillStyle = "#f5f5f5";
              ctx.font = `${12 * labelScale}px Arial`;
              ctx.fillText(typed.label, radius + 8, 4);
            } else {
              ctx.fillStyle = selected || hovered ? "#f5f5f5" : "#b5b5b5";
              ctx.font = `${11 * labelScale}px Arial`;
              ctx.fillText(typed.label, 10, 4);
            }

            if (hovered) {
              ctx.fillStyle = "#e5e5e5";
              ctx.font = `${10 * labelScale}px Arial`;
              if (typed.kind === "image") {
                ctx.fillText(typed.imageUrl, radius + 8, 18);
              }
            }

            ctx.restore();
          }}
          onNodeHover={(node: unknown) => {
            setHoverNode((node as GraphNode) || null);
          }}
          onNodeClick={(node: unknown) => {
            const typed = node as GraphNode;
            if (typed.kind === "image") {
              onImageSelect(typed.id);
            }
          }}
        />
      </div>

      <div className="border-t border-zinc-800 px-5 py-4">
        <div className="grid gap-4 md:grid-cols-[220px_1fr]">
          <div className="border border-zinc-800 bg-zinc-950 p-4">
            <p className="text-[10px] uppercase tracking-[0.3em] text-zinc-500">Hover</p>
            <p className="mt-2 text-sm text-zinc-300">
              {hoverNode ? hoverNode.label : "Hover a node to inspect it."}
            </p>
          </div>

          <div className="border border-zinc-800 bg-zinc-950 p-4">
            <p className="text-[10px] uppercase tracking-[0.3em] text-zinc-500">Detail</p>
            {hoverNode?.kind === "image" ? (
              <div className="mt-3 grid gap-4 md:grid-cols-[160px_1fr]">
                <div className="aspect-square border border-zinc-800 bg-zinc-900 p-4 text-zinc-50">
                  <div className="flex h-full flex-col justify-between">
                    <span className="text-xs uppercase tracking-[0.3em] text-zinc-500">{hoverNode.label}</span>
                    <div className="space-y-2">
                      <div className="text-4xl font-medium">{hoverNode.turn}</div>
                      <div className="h-px bg-zinc-700" />
                    </div>
                  </div>
                </div>
                <div className="space-y-2">
                  <p className="text-sm text-zinc-300">{hoverNode.imageUrl}</p>
                  <p className="text-sm leading-6 text-zinc-500">
                    Clicking it jumps back to the Micro tab and scrolls the strip to the same turn.
                  </p>
                </div>
              </div>
            ) : hoverNode?.kind === "keyword" ? (
              <p className="mt-3 text-sm leading-6 text-zinc-400">
                {hoverNode.label} connects the image turns that share a conceptual thread in the mock debate history.
              </p>
            ) : (
              <p className="mt-3 text-sm leading-6 text-zinc-500">
                Select a node to inspect its connected meaning.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
