"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";


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
    }
  | {
      id: string;
      kind: "comment";
      label: string;
      text: string;
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

import type { HistoryTurn, Thread } from "@/lib/history";

function buildGraph(turns: HistoryTurn[], threads: Thread[] = []) {
  const nodes: GraphNode[] = [];
  const links: GraphLink[] = [];
  const keywordNodes = new Map<string, GraphNode>();
  const imageKeywords = new Map<string, string[]>();

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

    if (turn.parent_image_id) {
      links.push({ source: turn.image_id, target: turn.parent_image_id });
    }

    imageKeywords.set(turn.image_id, [...turn.keywords]);
  }

  for (const thread of threads) {
    for (const comment of thread.comments || []) {
      const commentNodeId = `comment-${comment.id}`;
      nodes.push({
        id: commentNodeId,
        kind: "comment",
        label: comment.agent_name,
        text: comment.comment,
      });
      links.push({ source: commentNodeId, target: comment.post_image_id });
    }
  }

  return { nodes, links, imageKeywords };
}

type KnowledgeWebProps = {
  turns: HistoryTurn[];
  threads?: Thread[];
  onImageSelect: (turnId: string) => void;
  selectedTurnId?: string | null;
  resetToken?: number;
};

export function KnowledgeWeb({ turns, threads = [], onImageSelect, selectedTurnId, resetToken = 0 }: KnowledgeWebProps) {
  const graphRef = useRef<any>(null);
  const graphFrameRef = useRef<HTMLDivElement | null>(null);
  const imageCacheRef = useRef<Map<string, HTMLImageElement>>(new Map());
  const [graphSize, setGraphSize] = useState({ width: 0, height: 0 });
  const { nodes, links, imageKeywords } = useMemo(() => buildGraph(turns, threads), [turns, threads]);
  const [hoverNode, setHoverNode] = useState<GraphNode | null>(null);
  const selectedNode = useMemo(
    () => nodes.find((node) => node.kind === "image" && node.id === selectedTurnId) ?? null,
    [nodes, selectedTurnId]
  );

  useEffect(() => {
    const frame = graphFrameRef.current;
    if (!frame) return;

    const updateSize = () => {
      const bounds = frame.getBoundingClientRect();
      setGraphSize({
        width: Math.max(1, Math.floor(bounds.width)),
        height: Math.max(1, Math.floor(bounds.height))
      });
    };

    updateSize();

    const observer = new ResizeObserver(updateSize);
    observer.observe(frame);

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!graphRef.current || graphSize.width <= 1 || graphSize.height <= 1) return;

    const resetGraph = () => {
      graphRef.current?.d3ReheatSimulation?.();
      graphRef.current?.centerAt?.(0, 0, 0);
      graphRef.current?.zoomToFit?.(0, 90);
    };

    const animationFrame = requestAnimationFrame(resetGraph);
    const settleTimer = window.setTimeout(resetGraph, 120);
    const finalTimer = window.setTimeout(resetGraph, 420);

    return () => {
      cancelAnimationFrame(animationFrame);
      window.clearTimeout(settleTimer);
      window.clearTimeout(finalTimer);
    };
  }, [graphSize.height, graphSize.width, resetToken]);

  useEffect(() => {
    const urls = Array.from(new Set(turns.map((turn) => turn.image_url)));
    let cancelled = false;

    const preload = async () => {
      const cache = imageCacheRef.current;

      await Promise.all(
        urls.map(
          (url) =>
            new Promise<void>((resolve) => {
              if (cache.has(url)) {
                resolve();
                return;
              }

              const image = new window.Image();
              image.onload = () => {
                cache.set(url, image);
                resolve();
              };
              image.onerror = () => resolve();
              image.src = url;
            })
        )
      );

      if (!cancelled) {
        graphRef.current?.refresh?.();
        graphRef.current?.d3ReheatSimulation?.();
      }
    };

    preload();

    return () => {
      cancelled = true;
    };
  }, [turns]);

  const forceGraphData = useMemo(() => {
    return {
      nodes: nodes.map((node, index) => {
        const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2;
        const radius = node.kind === "image" ? 70 : 140;

        return {
          ...node,
          x: Math.cos(angle) * radius,
          y: Math.sin(angle) * radius
        };
      }),
      links
    };
  }, [links, nodes]);

  const handleBackgroundClick = () => {
    requestAnimationFrame(() => {
      graphRef.current?.centerAt?.(0, 0, 250);
      graphRef.current?.zoomToFit?.(250, 90);
    });
  };

  const getLabelOpacity = (globalScale: number, baseSize: number, hovered: boolean, selected: boolean) => {
    if (hovered || selected) return 1;

    const renderedSize = baseSize * Math.max(globalScale, 0.01);
    if (renderedSize >= 11) return 1;
    if (renderedSize <= 6) return 0;

    return (renderedSize - 6) / 5;
  };

  return (
    <div className="rounded-2xl border border-zinc-800 bg-black">
      <div ref={graphFrameRef} className="relative h-[72vh] min-h-[640px] cursor-grab bg-black active:cursor-grabbing">
        {graphSize.width > 1 && graphSize.height > 1 ? (
          <ForceGraph2D
            ref={graphRef}
            width={graphSize.width}
            height={graphSize.height}
            graphData={forceGraphData}
            backgroundColor="#000000"
            nodeRelSize={4}
            enableZoomInteraction
            enablePanInteraction
            linkWidth={0.6}
            linkColor={() => "rgba(160,160,160,0.35)"}
            linkDirectionalParticles={0}
            onBackgroundClick={handleBackgroundClick}
            nodePointerAreaPaint={(node: unknown, color: string, ctx: CanvasRenderingContext2D) => {
              const typed = node as GraphNode;
              ctx.fillStyle = color;
              ctx.beginPath();
              const radius = typed.kind === "image" ? 22 : 12;
              ctx.arc(typed.x ?? 0, typed.y ?? 0, radius, 0, Math.PI * 2, false);
              ctx.fill();
            }}
            nodeCanvasObjectMode={() => "replace"}
            nodeCanvasObject={(node: unknown, ctx: CanvasRenderingContext2D, globalScale: number) => {
              const typed = node as GraphNode;
              const hovered = hoverNode?.id === typed.id;
              const selected = selectedNode?.id === typed.id;
              const radius = typed.kind === "image" ? (hovered || selected ? 18 : 14) : typed.kind === "comment" ? 8 : 6;
              const labelScale = Math.max(0.55, 1 / globalScale);
              const mainLabelOpacity = getLabelOpacity(globalScale, typed.kind === "image" ? 12 : 11, hovered, selected);

              ctx.save();
              ctx.translate(typed.x ?? 0, typed.y ?? 0);

              if (typed.kind === "image") {
                const cachedImage = imageCacheRef.current.get(typed.imageUrl);

                ctx.fillStyle = "#101010";
                ctx.beginPath();
                ctx.arc(0, 0, radius + 4, 0, Math.PI * 2);
                ctx.fill();

                ctx.save();
                ctx.beginPath();
                ctx.arc(0, 0, radius, 0, Math.PI * 2);
                ctx.clip();

                if (cachedImage && cachedImage.complete && cachedImage.naturalWidth > 0) {
                  ctx.drawImage(cachedImage, -radius, -radius, radius * 2, radius * 2);
                } else {
                  ctx.fillStyle = "#171717";
                  ctx.fillRect(-radius, -radius, radius * 2, radius * 2);
                }

                ctx.restore();

                ctx.strokeStyle = selected || hovered ? "#f5f5f5" : "#737373";
                ctx.lineWidth = selected || hovered ? 1.8 : 1;
                ctx.beginPath();
                ctx.arc(0, 0, radius + 2, 0, Math.PI * 2);
                ctx.stroke();

                ctx.fillStyle = `rgba(245,245,245,${mainLabelOpacity})`;
                ctx.font = `${12 * labelScale}px Arial`;
                ctx.fillText(typed.label, radius + 8, 4);

                if (hovered) {
                  ctx.fillStyle = "#f5f5f5";
                  ctx.font = `${10 * labelScale}px Arial`;
                  const keywords = imageKeywords.get(typed.id)?.join(" | ") ?? "";
                  ctx.fillText(keywords, radius + 8, 20);
                }
              } else {
                ctx.fillStyle = selected || hovered ? "#f5f5f5" : typed.kind === "comment" ? "#3b82f6" : "#a3a3a3";
                ctx.beginPath();
                ctx.arc(0, 0, radius, 0, Math.PI * 2);
                ctx.fill();

                ctx.fillStyle = `rgba(181,181,181,${mainLabelOpacity})`;
                ctx.font = `${11 * labelScale}px Arial`;
                ctx.fillText(typed.label, 10, 4);
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
        ) : null}
      </div>

      <div className="border-t border-zinc-800 px-5 py-4">
        <div className="grid gap-4 md:grid-cols-[220px_1fr]">
          <div className="rounded-2xl border border-zinc-800 bg-zinc-950 p-4">
            <p className="text-[10px] uppercase tracking-[0.3em] text-zinc-500">Hover</p>
            <p className="mt-2 text-sm text-zinc-300">{hoverNode ? hoverNode.label : "Hover a node to inspect it."}</p>
          </div>

          <div className="rounded-2xl border border-zinc-800 bg-zinc-950 p-4">
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
                  <p className="break-all text-sm text-zinc-300">{hoverNode.imageUrl}</p>
                  <p className="text-sm leading-6 text-zinc-500">
                    Clicking it jumps back to the Micro tab and scrolls the strip to the same turn.
                  </p>
                </div>
              </div>
            ) : hoverNode?.kind === "keyword" ? (
              <p className="mt-3 text-sm leading-6 text-zinc-400">
                {hoverNode.label} connects the image turns that share a conceptual thread in the debate history.
              </p>
            ) : hoverNode?.kind === "comment" ? (
              <p className="mt-3 text-sm leading-6 text-zinc-400">
                <span className="font-semibold text-zinc-300">{hoverNode.label}</span>: {hoverNode.text}
              </p>
            ) : (
              <p className="mt-3 text-sm leading-6 text-zinc-500">Select a node to inspect its connected meaning.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
