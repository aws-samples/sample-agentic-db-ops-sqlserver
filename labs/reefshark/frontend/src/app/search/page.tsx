"use client";

import { useState, useEffect, useCallback } from "react";
import Header from "../components/Header";
import {
  Database, Layers, Brain, ChevronDown, ChevronRight,
  CheckCircle2, RotateCcw, Server, Zap,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/app";

const TAGS = [
  "eco-friendly beach snorkeling",
  "relaxing tropical island getaway",
  "family adventure hiking mountains",
  "romantic sunset wine and food",
  "cultural museums and ancient history",
  "luxury ski resort in the alps",
  "wildlife safari nature photography",
  "budget backpacking city break",
];

const STRATEGY_ORDER = ["semantic", "freetext", "hybrid", "sql"] as const;

type Strategy = { name: string; color: string; desc: string; latency: number | null; count: number };
type Result = {
  title: string; country: string; continent: string; climate: string;
  season: string; snippet: string; score: number | null;
};
type Chunk = { source: string; snippet: string };
type SearchResponse = {
  query: string;
  strategies: Record<string, Strategy>;
  winner: string | null;
  results: Result[];
  ragChunks: Chunk[];
  total_latency_ms: number;
  errors: Record<string, string>;
};

const ICON_BY_CLIMATE: Record<string, string> = {
  tropical: "🏝️", mediterranean: "🌊", alpine: "🏔️", "semi-arid": "🏜️",
  subarctic: "❄️", temperate: "🌿", highland: "⛰️", savanna: "🦁",
};

function iconFor(r: Result) {
  return ICON_BY_CLIMATE[(r.climate || "").toLowerCase()] || "📍";
}

export default function SearchPage() {
  const [query, setQuery] = useState("eco-friendly beach snorkeling");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedLoops, setExpandedLoops] = useState<Set<number>>(new Set([0, 1]));

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(q)}&topk=6`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: SearchResponse = await res.json();
      setData(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-run the default query on first load.
  useEffect(() => { doSearch("eco-friendly beach snorkeling"); }, [doSearch]);

  const toggleLoop = (idx: number) => {
    const next = new Set(expandedLoops);
    next.has(idx) ? next.delete(idx) : next.add(idx);
    setExpandedLoops(next);
  };

  const strategies = data?.strategies || {};
  const results = data?.results || [];
  const ragChunks = data?.ragChunks || [];
  const hybrid = strategies["hybrid"];
  const topScore = results[0]?.score;

  // Terminal logs derived from the real run.
  const terminalLogs: { msg: string; cls: string }[] = [];
  terminalLogs.push({ msg: `Query: "${data?.query ?? query}"`, cls: "" });
  terminalLogs.push({ msg: "Embedding via Bedrock Titan V2 (1024-dim)...", cls: "agent" });
  for (const k of STRATEGY_ORDER) {
    const s = strategies[k];
    if (!s) continue;
    if (s.latency == null) {
      terminalLogs.push({ msg: `${s.name}: ERROR`, cls: "err" });
    } else {
      terminalLogs.push({ msg: `${s.name}: ${s.latency}ms | ${s.count} results`, cls: "ok" });
    }
  }
  if (data) terminalLogs.push({ msg: `Final: Hybrid RRF winner | ${data.total_latency_ms}ms total`, cls: "ok" });

  // Lightweight agent reasoning trace, grounded in the real results.
  const agentLoops = [
    {
      iteration: 1,
      tool: "vector_search",
      thought: "Multi-attribute natural-language query. Vector (semantic) search should capture intent best; run it first.",
      action: "EXEC usp_SearchVector with Bedrock Titan V2 embedding of the query",
      observation: hybrid
        ? `Semantic search returned ${strategies["semantic"]?.count ?? 0} results in ${strategies["semantic"]?.latency ?? "?"}ms.`
        : "Waiting for results...",
      sufficient: false,
      reason: "Good semantic candidates, but enrich with RAG document chunks and verify with Full-Text.",
    },
    {
      iteration: 2,
      tool: "hybrid_rrf + freetext",
      thought: "Fuse vector + full-text via Reciprocal Rank Fusion and pull supporting RAG chunks for citations.",
      action: "EXEC usp_HybridSearch (RRF over VECTOR_DISTANCE + FREETEXTTABLE + DocumentChunks)",
      observation: `Hybrid returned ${results.length} destinations + ${ragChunks.length} RAG chunks` +
        (topScore != null ? ` (top RRF ${topScore}).` : "."),
      sufficient: true,
      reason: "Combined semantic + lexical + RAG context. High confidence — present with source attribution.",
    },
  ];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 overflow-x-hidden">
      <Header />
      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

          {/* LEFT */}
          <div className="col-span-12 lg:col-span-4 space-y-4">
            <div className="bg-white rounded-lg border border-slate-200 p-4">
              <div className="text-xs font-bold text-slate-500 uppercase mb-3">Search Strategy Hub · Live TravelAI</div>
              <div className="relative">
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && doSearch(query)}
                  placeholder="Describe your ideal trip..."
                  className="w-full bg-slate-100 border border-slate-200 rounded-lg px-4 py-3 pr-20 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <button
                  onClick={() => doSearch(query)}
                  disabled={loading}
                  className="absolute right-2 top-2 bottom-2 bg-gradient-to-r from-purple-600 to-indigo-600 text-white px-3 rounded-md text-xs font-semibold hover:from-purple-500 hover:to-indigo-500 transition-all disabled:opacity-50"
                >
                  {loading ? "..." : "Search"}
                </button>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-3">
                {TAGS.map((tag, idx) => (
                  <button
                    key={idx}
                    onClick={() => { setQuery(tag); doSearch(tag); }}
                    className={`text-[10px] px-2 py-1 rounded-md border transition-colors ${
                      query === tag
                        ? "border-purple-500 bg-purple-50 text-purple-700"
                        : "border-slate-200 bg-slate-100 text-slate-500 hover:border-purple-400"
                    }`}
                  >
                    {tag}
                  </button>
                ))}
              </div>
              {error && <p className="text-[11px] text-red-500 mt-3">Backend error: {error}</p>}
            </div>

            {/* Pipeline */}
            <div className="bg-white rounded-lg border border-slate-200 p-4">
              <div className="text-xs font-bold text-slate-500 uppercase mb-2">Pipeline Flow</div>
              <div className="flex flex-wrap items-center gap-1 text-[10px]">
                <span className="bg-slate-100 px-2 py-0.5 rounded text-slate-600">Query</span>
                <span className="text-slate-600">→</span>
                <span className="bg-indigo-50 px-2 py-0.5 rounded text-indigo-700">Agent Reasons</span>
                <span className="text-slate-600">→</span>
                <span className="bg-purple-50 px-2 py-0.5 rounded text-purple-700">Vector</span>
                <span className="text-slate-600">+</span>
                <span className="bg-amber-50 px-2 py-0.5 rounded text-amber-700">FTS</span>
                <span className="text-slate-600">+</span>
                <span className="bg-emerald-50 px-2 py-0.5 rounded text-emerald-700">RAG</span>
                <span className="text-slate-600">→</span>
                <span className="bg-emerald-50 px-2 py-0.5 rounded text-emerald-700">RRF Answer</span>
              </div>
              <div className="mt-2 flex items-center gap-3 text-[10px] text-slate-500">
                <span className="flex items-center gap-1"><Server className="w-3 h-3" /> RDS SQL Server 2025</span>
                <span className="flex items-center gap-1"><Layers className="w-3 h-3" /> Titan V2</span>
              </div>
            </div>

            {/* Terminal */}
            <div className="bg-white rounded-lg border border-slate-200 p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-slate-500">Agent Terminal</span>
                <span className="text-[10px] text-slate-600">{data ? `${data.total_latency_ms}ms total` : "—"}</span>
              </div>
              <div className="bg-slate-950 rounded-lg p-3 max-h-[220px] overflow-y-auto font-mono text-[10px] leading-relaxed space-y-0.5">
                {terminalLogs.map((log, idx) => (
                  <div key={idx} className={log.cls === "ok" ? "text-emerald-400" : log.cls === "agent" ? "text-purple-400" : log.cls === "err" ? "text-red-400" : "text-slate-500"}>
                    {log.msg}
                  </div>
                ))}
              </div>
            </div>

            {/* Reasoning */}
            <div className="bg-white rounded-lg border border-slate-200 p-4">
              <div className="flex items-center gap-2 mb-3">
                <Brain className="w-4 h-4 text-purple-500" />
                <span className="text-xs font-bold text-slate-500">Agent Reasoning Loop</span>
                <span className="ml-auto text-[10px] bg-purple-50 text-purple-600 px-2 py-0.5 rounded">2 iterations</span>
              </div>
              <div className="space-y-2">
                {agentLoops.map((loop, idx) => (
                  <div key={idx} className="bg-slate-50 rounded-lg border border-slate-200 overflow-hidden">
                    <button onClick={() => toggleLoop(idx)} className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-white/50">
                      {expandedLoops.has(idx) ? <ChevronDown className="w-3 h-3 text-slate-500" /> : <ChevronRight className="w-3 h-3 text-slate-500" />}
                      <RotateCcw className="w-3 h-3 text-purple-500" />
                      <span className="text-[10px] font-medium">Iteration {loop.iteration}</span>
                      <span className="text-[10px] text-slate-500 flex-1 truncate ml-1">{loop.tool}</span>
                      <span className={`text-[9px] px-1.5 py-0.5 rounded ${loop.sufficient ? "bg-emerald-50 text-emerald-600" : "bg-orange-50 text-orange-600"}`}>
                        {loop.sufficient ? "sufficient" : "loop"}
                      </span>
                    </button>
                    {expandedLoops.has(idx) && (
                      <div className="px-3 pb-3 space-y-1.5 text-[10px]">
                        <div className="bg-white rounded p-2"><span className="text-purple-500 font-semibold">💭 Think: </span><span className="text-slate-600">{loop.thought}</span></div>
                        <div className="bg-white rounded p-2"><span className="text-blue-500 font-semibold">🔧 Act: </span><span className="text-slate-600">{loop.action}</span></div>
                        <div className="bg-white rounded p-2"><span className="text-green-600 font-semibold">👁️ Observe: </span><span className="text-slate-600">{loop.observation}</span></div>
                        <div className={`rounded p-2 ${loop.sufficient ? "bg-emerald-50" : "bg-orange-50"}`}>
                          <span className={loop.sufficient ? "text-emerald-600" : "text-orange-600"}>{loop.sufficient ? "✅" : "🔄"} {loop.reason}</span>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* RIGHT */}
          <div className="col-span-12 lg:col-span-8 space-y-4">
            {/* Strategy cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {STRATEGY_ORDER.map((key) => {
                const strat = strategies[key];
                const colorBorder: Record<string, string> = {
                  purple: "border-purple-300", amber: "border-amber-300",
                  emerald: "border-emerald-300", slate: "border-slate-200",
                };
                const textColors: Record<string, string> = {
                  purple: "text-purple-600", amber: "text-amber-600",
                  emerald: "text-emerald-600", slate: "text-slate-500",
                };
                const bgColors: Record<string, string> = {
                  purple: "bg-purple-500", amber: "bg-amber-500",
                  emerald: "bg-emerald-500", slate: "bg-slate-500",
                };
                const color = strat?.color || "slate";
                return (
                  <div key={key} className={`bg-white rounded-lg border p-3 ${colorBorder[color]}`}>
                    <h4 className={`text-[10px] font-bold uppercase ${textColors[color]}`}>{strat?.name || key}</h4>
                    <div className="flex items-center justify-between mt-2">
                      <span className="text-lg font-bold text-slate-900">{strat?.latency != null ? `${strat.latency}ms` : "—"}</span>
                      <span className="text-xs text-slate-500">{strat?.count ?? 0} results</span>
                    </div>
                    <div className="h-1.5 bg-slate-100 rounded-full mt-2">
                      <div className={`h-full rounded-full ${bgColors[color]}`} style={{ width: `${Math.min(100, (strat?.latency || 0))}%` }} />
                    </div>
                    <p className="text-[9px] text-slate-500 mt-2">{strat?.desc}</p>
                  </div>
                );
              })}
            </div>

            {/* Winner */}
            {data?.winner && (
              <div className="bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-2 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <span className="text-xs font-semibold text-emerald-700">Winner: {strategies[data.winner]?.name}</span>
                <span className="text-[10px] text-slate-500 ml-2">
                  RRF fusion · {hybrid?.latency}ms · {hybrid?.count} results{topScore != null ? ` · top score ${topScore}` : ""}
                </span>
              </div>
            )}

            {/* Results */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-500">Search Results</span>
                <span className="text-[10px] text-slate-500">{results.length} destinations found</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {results.map((result, idx) => (
                  <div key={idx} className="bg-white rounded-lg border border-slate-200 p-4 hover:border-purple-300 transition-colors">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{iconFor(result)}</span>
                        <h4 className="text-sm font-bold">{result.title}</h4>
                      </div>
                      {result.score != null && (
                        <span className="text-xs font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded">{result.score}</span>
                      )}
                    </div>
                    <p className="text-[10px] text-slate-500 mt-2 line-clamp-3">{result.snippet}</p>
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {result.country && <span className="text-[9px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-500">{result.country}</span>}
                      {result.climate && <span className="text-[9px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-500">{result.climate}</span>}
                      {result.season && <span className="text-[9px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-500">{result.season}</span>}
                    </div>
                  </div>
                ))}
                {!loading && results.length === 0 && (
                  <div className="text-xs text-slate-500">No results{error ? " (backend unreachable)" : ""}.</div>
                )}
              </div>
            </div>

            {/* RAG Context */}
            <div className="bg-emerald-50/60 rounded-lg border border-emerald-200 p-4">
              <div className="flex items-center gap-2 mb-3">
                <Database className="w-4 h-4 text-emerald-600" />
                <span className="text-xs font-bold text-emerald-700">RAG Context Retrieved</span>
                <span className="text-[10px] text-slate-500 ml-2">{ragChunks.length} document chunks</span>
              </div>
              <div className="space-y-2">
                {ragChunks.map((chunk, idx) => (
                  <div key={idx} className="border-l-2 border-emerald-500/50 pl-3">
                    <span className="text-[10px] font-bold text-emerald-700">{chunk.source}</span>
                    <p className="text-xs text-slate-600 mt-0.5">{chunk.snippet}</p>
                  </div>
                ))}
                {ragChunks.length === 0 && <p className="text-[11px] text-slate-400">No chunks returned for this query.</p>}
              </div>
            </div>

            {/* Schema */}
            <div className="bg-white rounded-lg border border-slate-200 p-4">
              <span className="text-xs font-bold text-slate-500">Database Schema (RDS SQL Server 2025)</span>
              <pre className="text-[10px] text-emerald-600 font-mono mt-2 leading-relaxed whitespace-pre-wrap break-all">{`CREATE TABLE dbo.Destinations (
  destination_id INT PRIMARY KEY,
  name NVARCHAR(200),
  description NVARCHAR(MAX),          -- Full-Text indexed
  description_vector VECTOR(1024),     -- Bedrock Titan V2 embedding
  attributes JSON,
  climate AS JSON_VALUE(attributes,'$.climate') PERSISTED
);

EXEC usp_HybridSearch @QueryText = N'${(data?.query ?? query).replace(/'/g, "''")}', @TopK = 6;
-- AI_GENERATE_EMBEDDINGS() + VECTOR_DISTANCE() + FREETEXTTABLE() -> RRF fusion`}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
