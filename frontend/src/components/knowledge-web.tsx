"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { Sparkles, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";


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
    }
  | {
      id: string;
      kind: "inspiration";
      imageUrl: string;
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

import type { HistoryTurn, Thread, InspirationItem } from "@/lib/history";

function getGraphImageUrl(url: string, format?: string) {
  if (!url) return "";
  const isMp4 = url.includes("format=mp4") || url.endsWith(".mp4") || format === "mp4";
  if (isMp4) {
    if (url.includes("?id=")) {
      const parts = url.split("?");
      const base = parts[0];
      const query = parts[1] || "";
      const params = query.split("&").filter(p => !p.startsWith("format="));
      params.push("format=webp");
      return `${base}?${params.join("&")}`;
    }
    if (url.endsWith(".mp4")) {
      return url.slice(0, -4) + ".webp";
    }
  }
  return url;
}

function buildGraph(turns: HistoryTurn[], threads: Thread[] = [], inspiration: InspirationItem[] = []) {
  const nodes: GraphNode[] = [];
  const links: GraphLink[] = [];
  const keywordNodes = new Map<string, GraphNode>();
  const imageKeywords = new Map<string, string[]>();

  for (const turn of turns) {
    const imageNode: GraphNode = {
      id: turn.image_id,
      kind: "image",
      turn: turn.turn,
      imageUrl: getGraphImageUrl(turn.image_url, turn.image_webp?.format),
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

  for (const item of inspiration) {
    const inspNode: GraphNode = {
      id: item.id,
      kind: "inspiration",
      imageUrl: getGraphImageUrl(item.image_url),
      label: `Inspiration`
    };
    nodes.push(inspNode);

    for (const keyword of item.keywords || []) {
      if (!keywordNodes.has(keyword)) {
        const keywordNode: GraphNode = {
          id: keyword,
          kind: "keyword",
          label: keyword
        };
        keywordNodes.set(keyword, keywordNode);
        nodes.push(keywordNode);
      }

      links.push({ source: keyword, target: item.id });
    }

    imageKeywords.set(item.id, [...(item.keywords || [])]);
  }



  // Filter out links that reference non-existent nodes (e.g. deleted posts)
  const nodeIds = new Set(nodes.map((n) => n.id));
  const validLinks = links.filter((link) => nodeIds.has(link.source) && nodeIds.has(link.target));

  return { nodes, links: validLinks, imageKeywords };
}

type KnowledgeWebProps = {
  turns: HistoryTurn[];
  threads?: Thread[];
  inspiration?: InspirationItem[];
  onImageSelect: (id: string, kind: "image" | "inspiration") => void;
  selectedTurnId?: string | null;
  activeNodes?: string[];
  onRefresh?: () => Promise<void> | void;
};

export function KnowledgeWeb({
  turns,
  threads = [],
  inspiration = [],
  onImageSelect,
  selectedTurnId,
  activeNodes = [],
  onRefresh
}: KnowledgeWebProps) {
  const graphRef = useRef<any>(null);
  const graphFrameRef = useRef<HTMLDivElement | null>(null);
  const imageCacheRef = useRef<Map<string, HTMLImageElement | HTMLVideoElement>>(new Map());
  const [graphSize, setGraphSize] = useState({ width: 0, height: 0 });
  const forcesConfigured = useRef(false);

  // O(1) lookup set for active (highlighted) nodes
  const activeNodeSet = useMemo(() => new Set(activeNodes), [activeNodes]);
  
  const [simplifying, setSimplifying] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const handleSimplifyKeywords = async () => {
    setSimplifying(true);
    setFeedback(null);
    try {
      const res = await fetch("/api/simplify-keywords", {
        method: "POST"
      });
      const data = await res.json();
      if (res.ok && data.ok) {
        setFeedback({ type: "success", message: data.message || "Keywords simplified successfully!" });
        if (onRefresh) {
          await onRefresh();
        }
      } else {
        throw new Error(data.error || "Failed to simplify keywords.");
      }
    } catch (err) {
      setFeedback({
        type: "error",
        message: err instanceof Error ? err.message : "An error occurred."
      });
    } finally {
      setSimplifying(false);
      setTimeout(() => {
        setFeedback(null);
      }, 4000);
    }
  };
  
  const { nodes, links, imageKeywords } = useMemo(
    () => buildGraph(turns, threads, inspiration),
    [turns, threads, inspiration]
  );
  
  const router = useRouter();
  const isTurnVideoUrl = useCallback((url: string) => {
    const turn = turns.find((t) => t.image_url === url || (t.image_webp && t.image_webp.url === url));
    if (turn?.image_webp?.format === "mp4") return true;
    return url.includes("format=mp4") || url.endsWith(".mp4");
  }, [turns]);

  const [hoverNode, setHoverNode] = useState<GraphNode | null>(null);
  const selectedNode = useMemo(
    () => nodes.find((node) => node.kind === "image" && node.id === selectedTurnId) ?? null,
    [nodes, selectedTurnId]
  );

  const connectedImages = useMemo(() => {
    if (!hoverNode || hoverNode.kind !== "keyword") return [];
    const keyword = hoverNode.id;
    const list: { id: string; url: string; label: string; kind: "image" | "inspiration" }[] = [];

    for (const turn of turns) {
      if (turn.keywords && turn.keywords.includes(keyword)) {
        list.push({
          id: turn.image_id,
          url: getGraphImageUrl(turn.image_url, turn.image_webp?.format),
          label: `Turn ${turn.turn}`,
          kind: "image"
        });
      }
    }

    for (const item of inspiration) {
      if (item.keywords && item.keywords.includes(keyword)) {
        list.push({
          id: item.id,
          url: item.image_url,
          label: `Inspiration`,
          kind: "inspiration"
        });
      }
    }

    return list;
  }, [hoverNode, turns, inspiration]);

  // Measure container
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

  // Configure D3 forces once after the ForceGraph2D mounts
  // This runs via a ref callback, ensuring the graph instance is ready
  useEffect(() => {
    if (!graphRef.current || forcesConfigured.current) return;
    forcesConfigured.current = true;

    const fg = graphRef.current;

    // Obsidian-style forces:
    // - moderate charge repulsion to keep nodes apart
    // - short link distance for tight hub-spoke clusters
    // - gentle center force to prevent drift
    fg.d3Force("charge")?.strength(-120);
    fg.d3Force("link")?.distance(50);
    fg.d3Force("center")?.strength(0.05);

    // Reheat so the new force parameters take effect
    fg.d3ReheatSimulation?.();
  });

  // Preload images and videos (only refresh canvas visuals, don't reheat physics)
  useEffect(() => {
    const urls = Array.from(
      new Set([
        ...turns.map((turn) => getGraphImageUrl(turn.image_url, turn.image_webp?.format)),
        ...inspiration.map((item) => getGraphImageUrl(item.image_url))
      ])
    );
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

              const isVideo = isTurnVideoUrl(url);
              if (isVideo) {
                const video = document.createElement("video");
                video.src = url;
                video.muted = true;
                video.playsInline = true;
                video.crossOrigin = "anonymous";
                
                let resolved = false;
                const finishWithVideo = () => {
                  if (!resolved) {
                    resolved = true;
                    cache.set(url, video);
                    video.play().catch(() => {});
                    resolve();
                  }
                };

                const tryCapture = () => {
                  if (resolved) return;
                  try {
                    if (video.videoWidth === 0 || video.videoHeight === 0) {
                      return;
                    }
                    const canvas = document.createElement("canvas");
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    const ctx = canvas.getContext("2d");
                    if (ctx) {
                      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                      const img = new Image();
                      img.onload = () => {
                        if (!resolved) {
                          resolved = true;
                          cache.set(url, img);
                          resolve();
                        }
                      };
                      img.onerror = () => {
                        finishWithVideo();
                      };
                      img.src = canvas.toDataURL("image/webp", 0.8) || canvas.toDataURL("image/jpeg", 0.8);
                    } else {
                      finishWithVideo();
                    }
                  } catch (e) {
                    console.error("Failed to extract video thumbnail frame", e);
                    finishWithVideo();
                  }
                };

                video.onloadeddata = () => {
                  video.currentTime = 0;
                  tryCapture();
                };

                video.onseeked = () => {
                  tryCapture();
                };

                video.onerror = () => {
                  finishWithVideo();
                };

                // Safety timeout after 2 seconds
                setTimeout(finishWithVideo, 2000);
              } else {
                const image = new window.Image();
                image.onload = () => {
                  cache.set(url, image);
                  resolve();
                };
                image.onerror = () => resolve();
                image.src = url;
              }
            })
        )
      );

      // Only repaint the canvas to show loaded images — do NOT reheat physics
      if (!cancelled) {
        graphRef.current?.refresh?.();
      }
    };

    preload();

    return () => {
      cancelled = true;
      // Pause video elements to free resources
      const cache = imageCacheRef.current;
      for (const val of cache.values()) {
        if (val instanceof HTMLVideoElement) {
          val.pause();
          val.src = "";
          val.load();
        }
      }
      cache.clear();
    };
  }, [turns, inspiration, isTurnVideoUrl]);

  // Set up an animation refresh loop for videos in the canvas
  useEffect(() => {
    let animationFrameId: number;
    
    const update = () => {
      let hasVideos = false;
      const cache = imageCacheRef.current;
      for (const val of cache.values()) {
        if (val instanceof HTMLVideoElement && !val.paused) {
          hasVideos = true;
          break;
        }
      }
      
      if (hasVideos) {
        graphRef.current?.refresh?.();
      }
      
      animationFrameId = requestAnimationFrame(update);
    };
    
    animationFrameId = requestAnimationFrame(update);
    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [turns]);

  // Build graphData with cloned nodes so D3 can freely mutate positions
  const forceGraphData = useMemo(() => {
    return {
      nodes: nodes.map((node) => ({ ...node })),
      links: links.map((link) => ({ ...link }))
    };
  }, [links, nodes]);

  const handleBackgroundClick = useCallback(() => {
    requestAnimationFrame(() => {
      graphRef.current?.zoomToFit?.(250, 60);
    });
  }, []);

  // Zoom to fit once the simulation settles
  const handleEngineStop = useCallback(() => {
    graphRef.current?.zoomToFit?.(400, 60);
  }, []);

  const getLabelOpacity = (globalScale: number, baseSize: number, hovered: boolean, selected: boolean) => {
    if (hovered || selected) return 1;

    const renderedSize = baseSize * Math.max(globalScale, 0.01);
    if (renderedSize >= 11) return 1;
    if (renderedSize <= 6) return 0;

    return (renderedSize - 6) / 5;
  };

  return (
    <div className="rounded-2xl border border-[#D8D4CC]/60 bg-[#FAF9F6] shadow-sm shadow-[#252422]/5">
      <div ref={graphFrameRef} className="relative h-[72vh] min-h-[640px] cursor-grab bg-[#FAF9F6] active:cursor-grabbing">


        {graphSize.width > 1 && graphSize.height > 1 ? (
          <ForceGraph2D
            ref={graphRef}
            width={graphSize.width}
            height={graphSize.height}
            graphData={forceGraphData}
            backgroundColor="#FAF9F6"
            nodeRelSize={4}
            enableZoomInteraction
            enablePanInteraction

            // Physics: pre-settle 50 ticks before first paint, then run 300 more
            warmupTicks={50}
            cooldownTicks={300}
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}

            // Links
            linkWidth={(link: unknown) => {
              const l = link as { source: any; target: any };
              const sId = typeof l.source === "object" ? l.source.id : l.source;
              const tId = typeof l.target === "object" ? l.target.id : l.target;
              return (activeNodeSet.size > 0 && activeNodeSet.has(sId) && activeNodeSet.has(tId)) ? 1.8 : 0.6;
            }}
            linkColor={(link: unknown) => {
              const l = link as { source: any; target: any };
              const sId = typeof l.source === "object" ? l.source.id : l.source;
              const tId = typeof l.target === "object" ? l.target.id : l.target;
              if (activeNodeSet.size > 0 && activeNodeSet.has(sId) && activeNodeSet.has(tId)) {
                return "rgba(212, 81, 19, 0.6)";
              }
              return "rgba(133, 128, 118, 0.35)";
            }}
            linkDirectionalParticles={0}

            // Events
            onBackgroundClick={handleBackgroundClick}
            onEngineStop={handleEngineStop}

            nodePointerAreaPaint={(node: unknown, color: string, ctx: CanvasRenderingContext2D) => {
              const typed = node as GraphNode;
              ctx.fillStyle = color;
              ctx.beginPath();
              const radius = (typed.kind === "image" || typed.kind === "inspiration") ? 22 : 12;
              ctx.arc(typed.x ?? 0, typed.y ?? 0, radius, 0, Math.PI * 2, false);
              ctx.fill();
            }}
            nodeCanvasObjectMode={() => "replace"}
            nodeCanvasObject={(node: unknown, ctx: CanvasRenderingContext2D, globalScale: number) => {
              const typed = node as GraphNode;
              const hovered = hoverNode?.id === typed.id;
              const selected = selectedNode?.id === typed.id;
              const isActive = activeNodeSet.size > 0 && activeNodeSet.has(typed.id);
              const radius = (typed.kind === "image" || typed.kind === "inspiration")
                ? (hovered || selected ? 18 : 14)
                : typed.kind === "comment" ? 8 : 6;
              const labelScale = Math.max(0.55, 1 / globalScale);
              const mainLabelOpacity = getLabelOpacity(
                globalScale,
                (typed.kind === "image" || typed.kind === "inspiration") ? 12 : 11,
                hovered || isActive,
                selected
              );

              ctx.save();
              ctx.translate(typed.x ?? 0, typed.y ?? 0);



              if (typed.kind === "image" || typed.kind === "inspiration") {
                const cachedImage = imageCacheRef.current.get(typed.imageUrl);

                ctx.fillStyle = "#FAF9F6";
                ctx.beginPath();
                ctx.arc(0, 0, radius + 4, 0, Math.PI * 2);
                ctx.fill();

                ctx.save();
                ctx.beginPath();
                ctx.arc(0, 0, radius, 0, Math.PI * 2);
                ctx.clip();

                const isVideoElement = cachedImage instanceof HTMLVideoElement;
                if (isVideoElement) {
                  if (cachedImage.readyState >= 2) {
                    ctx.drawImage(cachedImage, -radius, -radius, radius * 2, radius * 2);
                  } else {
                    ctx.fillStyle = "#FAF9F6";
                    ctx.fillRect(-radius, -radius, radius * 2, radius * 2);
                  }
                } else if (cachedImage && cachedImage.complete && cachedImage.naturalWidth > 0) {
                  ctx.drawImage(cachedImage, -radius, -radius, radius * 2, radius * 2);
                } else {
                  ctx.fillStyle = "#FAF9F6";
                  ctx.fillRect(-radius, -radius, radius * 2, radius * 2);
                }

                ctx.restore();

                ctx.strokeStyle = isActive ? "#D45113" : (typed.kind === "inspiration" ? "#D45113" : (selected || hovered ? "#252422" : "#858076"));
                ctx.lineWidth = isActive ? 2.5 : (selected || hovered ? 1.8 : 1);
                ctx.beginPath();
                ctx.arc(0, 0, radius + 2, 0, Math.PI * 2);
                ctx.stroke();

                ctx.fillStyle = `rgba(37,36,34,${mainLabelOpacity})`;
                ctx.font = `${12 * labelScale}px Arial`;
                ctx.fillText(typed.label, radius + 8, 4);

                if (hovered) {
                  ctx.fillStyle = "#252422";
                  ctx.font = `${10 * labelScale}px Arial`;
                  const keywords = imageKeywords.get(typed.id)?.join(" | ") ?? "";
                  ctx.fillText(keywords, radius + 8, 20);
                }
              } else {
                ctx.fillStyle = isActive ? "#D45113" : (selected || hovered ? "#252422" : typed.kind === "comment" ? "#6366f1" : "#858076");
                ctx.beginPath();
                ctx.arc(0, 0, radius, 0, Math.PI * 2);
                ctx.fill();

                ctx.fillStyle = isActive ? `rgba(212,81,19,${mainLabelOpacity})` : `rgba(68,66,62,${mainLabelOpacity})`;
                ctx.font = `${isActive ? "bold " : ""}${11 * labelScale}px Arial`;
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
                router.push(`/post/${typed.id}`);
              } else if (typed.kind === "inspiration") {
                onImageSelect(typed.id, typed.kind);
              }
            }}
          />
        ) : null}
      </div>

      <div className="border-t border-[#D8D4CC]/60 bg-[#FAF9F6] px-5 py-4">
        <div className="grid gap-4 md:grid-cols-[220px_1fr]">
          <div className="rounded-2xl border border-[#D8D4CC]/60 bg-white p-4">
            <p className="text-[10px] uppercase tracking-[0.3em] text-[#858076] font-semibold">Hover</p>
            <p className="mt-2 text-sm text-[#252422] font-semibold">{hoverNode ? hoverNode.label : "Hover a node to inspect it."}</p>
          </div>

          <div className="rounded-2xl border border-[#D8D4CC]/60 bg-white p-4">
            <p className="text-[10px] uppercase tracking-[0.3em] text-[#858076] font-semibold">Detail</p>
            {hoverNode?.kind === "image" ? (
              <div className="mt-3 flex flex-col sm:flex-row items-center sm:items-start gap-4">
                <div className="w-24 h-24 rounded-full overflow-hidden border border-[#D8D4CC] bg-[#FAF9F6] flex-shrink-0 shadow-sm">
                  {(() => {
                    const originalTurn = turns.find((t) => t.image_id === hoverNode.id);
                    const isVideo = originalTurn?.image_webp?.format === "mp4" || 
                                    originalTurn?.image_url.includes("format=mp4") || 
                                    originalTurn?.image_url.endsWith(".mp4");
                    return (isVideo && originalTurn) ? (
                      <video
                        src={originalTurn.image_url}
                        autoPlay
                        loop
                        muted
                        playsInline
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <img
                        src={hoverNode.imageUrl}
                        alt={hoverNode.label}
                        className="w-full h-full object-cover"
                      />
                    );
                  })()}
                </div>
                <div className="space-y-1 text-center sm:text-left flex-1 min-w-0">
                  <div className="flex items-center justify-center sm:justify-start gap-2">
                    <span className="text-lg font-bold text-[#252422]">{hoverNode.label}</span>
                    <span className="px-2 py-0.5 text-[10px] uppercase font-semibold tracking-wider rounded-full bg-[#FAF9F6] border border-[#D8D4CC] text-[#858076]">
                      Image Turn
                    </span>
                  </div>
                  <p className="text-xs text-[#858076] break-all max-w-lg font-mono">
                    {hoverNode.imageUrl}
                  </p>
                  <p className="text-sm leading-6 text-[#858076] mt-2">
                    Clicking opens the detail page for this post's thread.
                  </p>
                </div>
              </div>
            ) : hoverNode?.kind === "keyword" ? (
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold text-[#252422]">{hoverNode.label}</span>
                  <span className="px-2 py-0.5 text-[10px] uppercase font-semibold tracking-wider rounded-full bg-zinc-100 border border-zinc-200 text-zinc-600">
                    Keyword
                  </span>
                </div>
                {connectedImages.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-xs uppercase tracking-wider font-semibold text-[#858076]">
                      Connected Concepts ({connectedImages.length})
                    </p>
                    <div className="flex flex-wrap gap-4 pt-1">
                      {connectedImages.map((img) => (
                        <div
                          key={img.id}
                          className="group relative cursor-pointer"
                          onClick={() => {
                            if (img.kind === "image") {
                              router.push(`/post/${img.id}`);
                            } else {
                              onImageSelect(img.id, "inspiration");
                            }
                          }}
                        >
                          <div className={cn(
                            "w-16 h-16 rounded-full overflow-hidden border border-[#D8D4CC] bg-[#FAF9F6] shadow-sm transition-all duration-300 hover:scale-110 hover:shadow-md hover:border-[#252422]",
                            img.kind === "inspiration" && "border-[#D45113]/55 hover:border-[#D45113]"
                          )}>
                            {isTurnVideoUrl(img.url) ? (
                              <video
                                src={img.url}
                                autoPlay
                                loop
                                muted
                                playsInline
                                className="w-full h-full object-cover"
                              />
                            ) : (
                              <img
                                src={img.url}
                                alt={img.label}
                                className="w-full h-full object-cover"
                              />
                            )}
                          </div>
                          <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 scale-0 transition-transform duration-200 group-hover:scale-100 bg-[#252422] text-[#FAF9F6] text-[9px] font-bold px-1.5 py-0.5 rounded whitespace-nowrap z-10 shadow">
                            {img.label}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-[#858076]">
                    This keyword is not connected to any images in the active web.
                  </p>
                )}
              </div>
            ) : hoverNode?.kind === "comment" ? (
              <p className="mt-3 text-sm leading-6 text-[#44423E]">
                <span className="font-semibold text-[#252422]">{hoverNode.label}</span>: {hoverNode.text}
              </p>
            ) : hoverNode?.kind === "inspiration" ? (
              <div className="mt-3 flex flex-col sm:flex-row items-center sm:items-start gap-4">
                <div className="w-24 h-24 rounded-full overflow-hidden border border-[#D45113]/50 bg-[#FAF9F6] flex-shrink-0 shadow-sm">
                  <img
                    src={hoverNode.imageUrl}
                    alt={hoverNode.label}
                    className="w-full h-full object-cover"
                  />
                </div>
                <div className="space-y-1 text-center sm:text-left flex-1 min-w-0">
                  <div className="flex items-center justify-center sm:justify-start gap-2">
                    <span className="text-lg font-bold text-[#252422]">{hoverNode.id}</span>
                    <span className="px-2 py-0.5 text-[10px] uppercase font-semibold tracking-wider rounded-full bg-[#D45113]/10 border border-[#D45113]/25 text-[#D45113]">
                      Inspiration
                    </span>
                  </div>
                  <p className="text-xs text-[#858076] break-all max-w-lg font-mono">
                    {hoverNode.imageUrl}
                  </p>
                  <p className="text-sm leading-6 text-[#858076] mt-2">
                    This is a user-uploaded reference inspiration image.
                  </p>
                </div>
              </div>
            ) : (
              <p className="mt-3 text-sm leading-6 text-[#858076]">Select a node to inspect its connected meaning.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
