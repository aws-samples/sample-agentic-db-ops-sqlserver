"use client";

import { useState } from "react";
import {
  Search,
  Database,
  GitBranch,
  Layers,
  Zap,
  ChevronDown,
  ChevronRight,
  Clock,
  CheckCircle2,
  Server,
  Brain,
} from "lucide-react";

interface RetrievalResult {
  source: string;
  type: "vector" | "sql" | "graph" | "hybrid";
  score: number;
  content: string;
  metadata: Record<string, string>;
  latency_ms: number;
}

interface PipelineStep {
  name: string;
  status: "pending" | "running" | "complete";
  duration_ms: number;
  details: string;
}

interface RAGResponse {
  query: string;
  pipeline_steps: PipelineStep[];
  retrieval_results: RetrievalResult[];
  synthesized_answer: string;
  strategy_used: string;
  total_latency_ms: number;
  tokens_used: { input: number; output: number };
}

const MOCK_RAG_RESPONSES: Record<string, RAGResponse> = {
  default: {
    query: "Find flights to Paris with hotel packages under $2000",
    pipeline_steps: [
      { name: "Query Analysis & Intent Classification", status: "complete", duration_ms: 12, details: "Intent: travel_search | Entities: [Paris, flights, hotels, $2000 budget]" },
      { name: "Query Embedding (text-embedding-3-large)", status: "complete", duration_ms: 45, details: "Vector dim: 3072 | Model: text-embedding-3-large" },
      { name: "Vector Search (ChromaDB)", status: "complete", duration_ms: 23, details: "Top-K: 10 | Collection: travel_packages | Distance: cosine" },
      { name: "SQL Query (RDS SQL Server)", status: "complete", duration_ms: 67, details: "SELECT * FROM packages WHERE destination='Paris' AND total_price < 2000" },
      { name: "Graph Traversal (Knowledge Graph)", status: "complete", duration_ms: 34, details: "Nodes traversed: 847 | Relations: [flies_to, located_in, has_package]" },
      { name: "Hybrid Re-ranking (RRF)", status: "complete", duration_ms: 18, details: "Reciprocal Rank Fusion | k=60 | Combined 3 result sets" },
      { name: "LLM Synthesis (Claude 3.5)", status: "complete", duration_ms: 890, details: "Context window: 12,847 tokens | Temperature: 0.1" },
    ],
    retrieval_results: [
      {
        source: "vector_store",
        type: "vector",
        score: 0.94,
        content: "Paris Holiday Package: Round-trip flight (JFK→CDG) + 5 nights at Hôtel de la Paix, breakfast included. Available Dec-Mar.",
        metadata: { collection: "travel_packages", chunk_id: "pkg_4821", embedding_model: "text-embedding-3-large" },
        latency_ms: 23,
      },
      {
        source: "rds_sql_server",
        type: "sql",
        score: 0.91,
        content: "Package ID: PKG-2847 | Air France JFK→CDG $649 + Le Petit Marais 5 nights @ $189/night = $1,594 total",
        metadata: { table: "dbo.travel_packages", row_id: "2847", index: "IX_destination_price" },
        latency_ms: 67,
      },
      {
        source: "knowledge_graph",
        type: "graph",
        score: 0.88,
        content: "Paris ←[located_in]← Hôtel de la Paix ←[has_rating]← 4.9★ | Paris ←[flies_to]← JFK (Air France, Delta, United) | Paris ←[has_activity]← Eiffel Tower, Louvre, Seine Cruise",
        metadata: { nodes: "12", relationships: "28", traversal_depth: "3" },
        latency_ms: 34,
      },
      {
        source: "hybrid_reranked",
        type: "hybrid",
        score: 0.96,
        content: "Best Match: Air France flight + Le Petit Marais (Boutique) — $1,594 total. Includes neighborhood dining recommendations from knowledge graph.",
        metadata: { fusion_method: "RRF", sources_combined: "3", confidence: "high" },
        latency_ms: 18,
      },
    ],
    synthesized_answer:
      "I found a great Paris package under your $2,000 budget:\n\n✈️ **Air France JFK → CDG** — $649 round-trip (nonstop, 7h 30m)\n🏨 **Le Petit Marais** (Boutique, ⭐ 4.5) — $189/night × 5 = $945\n\n💰 **Total: $1,594** (saves $406 from budget)\n\nThis hotel is in the Marais district with bike rentals, breakfast, and a bar. The knowledge graph also shows nearby: Louvre (15 min walk), Seine Cruise dock (10 min), and top-rated bistros.\n\nShall I book this or explore other options?",
    strategy_used: "Hybrid RAG (Vector + SQL + Graph → RRF Re-ranking)",
    total_latency_ms: 1089,
    tokens_used: { input: 12847, output: 342 },
  },
};

export default function RAGPanel() {
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState<RAGResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());
  const [expandedResults, setExpandedResults] = useState<Set<number>>(new Set());
  const [activeTab, setActiveTab] = useState<"pipeline" | "results" | "answer">("pipeline");

  const runSearch = () => {
    if (!query.trim()) return;
    setIsSearching(true);
    setResponse(null);

    // Simulate pipeline execution with delays
    setTimeout(() => {
      setResponse(MOCK_RAG_RESPONSES.default);
      setIsSearching(false);
    }, 1500);
  };

  const toggleStep = (idx: number) => {
    const next = new Set(expandedSteps);
    next.has(idx) ? next.delete(idx) : next.add(idx);
    setExpandedSteps(next);
  };

  const toggleResult = (idx: number) => {
    const next = new Set(expandedResults);
    next.has(idx) ? next.delete(idx) : next.add(idx);
    setExpandedResults(next);
  };

  const typeColor = (type: string) => {
    switch (type) {
      case "vector": return "bg-blue-100 text-blue-700 border-blue-200";
      case "sql": return "bg-green-100 text-green-700 border-green-200";
      case "graph": return "bg-purple-100 text-purple-700 border-purple-200";
      case "hybrid": return "bg-orange-100 text-orange-700 border-orange-200";
      default: return "bg-slate-100 text-slate-700 border-slate-200";
    }
  };

  const typeIcon = (type: string) => {
    switch (type) {
      case "vector": return <Layers className="w-4 h-4" />;
      case "sql": return <Database className="w-4 h-4" />;
      case "graph": return <GitBranch className="w-4 h-4" />;
      case "hybrid": return <Zap className="w-4 h-4" />;
      default: return <Search className="w-4 h-4" />;
    }
  };

  return (
    <div className="bg-slate-900 text-slate-100 rounded-xl border border-slate-700 overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-slate-800 to-slate-900 px-5 py-4 border-b border-slate-700">
        <div className="flex items-center gap-3">
          <div className="bg-emerald-500/20 rounded-lg p-2">
            <Brain className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h2 className="font-bold text-sm">RAG Pipeline Inspector</h2>
            <p className="text-xs text-slate-400">Vector Search + SQL + Knowledge Graph → Hybrid Retrieval</p>
          </div>
          <div className="ml-auto flex items-center gap-2 text-xs">
            <span className="flex items-center gap-1 bg-emerald-500/20 text-emerald-400 px-2 py-1 rounded">
              <Server className="w-3 h-3" /> RDS SQL Server
            </span>
            <span className="flex items-center gap-1 bg-blue-500/20 text-blue-400 px-2 py-1 rounded">
              <Layers className="w-3 h-3" /> ChromaDB
            </span>
            <span className="flex items-center gap-1 bg-purple-500/20 text-purple-400 px-2 py-1 rounded">
              <GitBranch className="w-3 h-3" /> Neo4j
            </span>
          </div>
        </div>
      </div>

      {/* Search Bar */}
      <div className="px-5 py-3 border-b border-slate-700 bg-slate-800/50">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runSearch()}
            placeholder="Ask anything... (e.g., 'Find flights to Paris with hotel packages under $2000')"
            className="flex-1 bg-slate-700 border border-slate-600 rounded-lg px-4 py-2.5 text-sm text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
          />
          <button
            onClick={runSearch}
            disabled={isSearching}
            className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-600 text-white px-4 py-2.5 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors"
          >
            {isSearching ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            {isSearching ? "Retrieving..." : "Search"}
          </button>
        </div>
        {/* Architecture Diagram Mini */}
        <div className="mt-3 flex items-center justify-center gap-1 text-xs text-slate-500">
          <span className="bg-slate-700 px-2 py-0.5 rounded">Query</span>
          <span>→</span>
          <span className="bg-slate-700 px-2 py-0.5 rounded">Embed</span>
          <span>→</span>
          <span className="bg-blue-900/50 px-2 py-0.5 rounded text-blue-400">Vector</span>
          <span>+</span>
          <span className="bg-green-900/50 px-2 py-0.5 rounded text-green-400">SQL</span>
          <span>+</span>
          <span className="bg-purple-900/50 px-2 py-0.5 rounded text-purple-400">Graph</span>
          <span>→</span>
          <span className="bg-orange-900/50 px-2 py-0.5 rounded text-orange-400">RRF</span>
          <span>→</span>
          <span className="bg-emerald-900/50 px-2 py-0.5 rounded text-emerald-400">LLM</span>
          <span>→</span>
          <span className="bg-slate-700 px-2 py-0.5 rounded">Answer</span>
        </div>
      </div>

      {/* Results Area */}
      {response && (
        <div>
          {/* Tabs */}
          <div className="flex border-b border-slate-700">
            {(["pipeline", "results", "answer"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-5 py-2.5 text-xs font-medium capitalize transition-colors ${
                  activeTab === tab
                    ? "border-b-2 border-emerald-400 text-emerald-400 bg-slate-800/50"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {tab === "pipeline" && "⚡ Pipeline Steps"}
                {tab === "results" && "📦 Retrieval Results"}
                {tab === "answer" && "💬 Synthesized Answer"}
              </button>
            ))}
            <div className="ml-auto flex items-center gap-3 px-4 text-xs text-slate-500">
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" /> {response.total_latency_ms}ms
              </span>
              <span>Tokens: {response.tokens_used.input} in / {response.tokens_used.output} out</span>
            </div>
          </div>

          <div className="px-5 py-4 max-h-[500px] overflow-y-auto">
            {/* Pipeline Steps Tab */}
            {activeTab === "pipeline" && (
              <div className="space-y-2">
                {response.pipeline_steps.map((step, idx) => (
                  <div key={idx} className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
                    <button
                      onClick={() => toggleStep(idx)}
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-slate-750 transition-colors"
                    >
                      {expandedSteps.has(idx) ? (
                        <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-slate-400 shrink-0" />
                      )}
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                      <span className="text-sm font-medium flex-1">{step.name}</span>
                      <span className="text-xs text-slate-400 font-mono">{step.duration_ms}ms</span>
                      <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-emerald-500 rounded-full"
                          style={{ width: `${Math.min((step.duration_ms / response.total_latency_ms) * 100 * 5, 100)}%` }}
                        />
                      </div>
                    </button>
                    {expandedSteps.has(idx) && (
                      <div className="px-4 pb-3 pl-11">
                        <code className="text-xs text-slate-400 bg-slate-900 px-3 py-1.5 rounded block font-mono">
                          {step.details}
                        </code>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Retrieval Results Tab */}
            {activeTab === "results" && (
              <div className="space-y-3">
                {response.retrieval_results.map((result, idx) => (
                  <div key={idx} className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
                    <button
                      onClick={() => toggleResult(idx)}
                      className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-750 transition-colors"
                    >
                      {expandedResults.has(idx) ? (
                        <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-slate-400 shrink-0" />
                      )}
                      <span className={`flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium border ${typeColor(result.type)}`}>
                        {typeIcon(result.type)}
                        {result.type.toUpperCase()}
                      </span>
                      <span className="text-sm flex-1 truncate">{result.content.slice(0, 80)}...</span>
                      <span className="text-xs font-mono text-emerald-400">
                        {(result.score * 100).toFixed(0)}% match
                      </span>
                      <span className="text-xs text-slate-500">{result.latency_ms}ms</span>
                    </button>
                    {expandedResults.has(idx) && (
                      <div className="px-4 pb-3 pl-11 space-y-2">
                        <p className="text-sm text-slate-300">{result.content}</p>
                        <div className="flex flex-wrap gap-2">
                          {Object.entries(result.metadata).map(([key, val]) => (
                            <span key={key} className="text-xs bg-slate-900 text-slate-400 px-2 py-1 rounded font-mono">
                              {key}: {val}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}

                {/* Schema Info */}
                <div className="mt-4 bg-slate-800/50 rounded-lg border border-slate-700 p-4">
                  <h4 className="text-xs font-bold text-slate-400 uppercase mb-2">Database Schema (RDS SQL Server)</h4>
                  <pre className="text-xs text-emerald-400 font-mono leading-relaxed">{`CREATE TABLE dbo.travel_packages (
  id INT PRIMARY KEY IDENTITY,
  destination NVARCHAR(100),
  origin NVARCHAR(100),
  flight_price DECIMAL(10,2),
  hotel_name NVARCHAR(200),
  hotel_price_per_night DECIMAL(10,2),
  total_price AS (flight_price + hotel_price_per_night * nights),
  nights INT,
  embedding VECTOR(3072),  -- text-embedding-3-large
  created_at DATETIME2 DEFAULT GETDATE()
);

CREATE INDEX IX_destination_price ON dbo.travel_packages(destination, total_price);
CREATE VECTOR INDEX IX_embedding ON dbo.travel_packages(embedding) WITH (metric = 'cosine');`}</pre>
                </div>
              </div>
            )}

            {/* Synthesized Answer Tab */}
            {activeTab === "answer" && (
              <div className="space-y-4">
                <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Brain className="w-4 h-4 text-emerald-400" />
                    <span className="text-xs font-bold text-emerald-400 uppercase">Agent Response</span>
                    <span className="ml-auto text-xs text-slate-500 bg-slate-700 px-2 py-0.5 rounded">
                      {response.strategy_used}
                    </span>
                  </div>
                  <div className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">
                    {response.synthesized_answer.split("**").map((part, i) =>
                      i % 2 === 1 ? (
                        <strong key={i} className="text-white">{part}</strong>
                      ) : (
                        <span key={i}>{part}</span>
                      )
                    )}
                  </div>
                </div>

                {/* Sources Attribution */}
                <div className="bg-slate-800/50 rounded-lg border border-slate-700 p-4">
                  <h4 className="text-xs font-bold text-slate-400 uppercase mb-2">Sources Used</h4>
                  <div className="flex gap-3">
                    <div className="flex items-center gap-1.5 text-xs text-blue-400">
                      <Layers className="w-3 h-3" /> Vector Store (94% match)
                    </div>
                    <div className="flex items-center gap-1.5 text-xs text-green-400">
                      <Database className="w-3 h-3" /> SQL Server (91% match)
                    </div>
                    <div className="flex items-center gap-1.5 text-xs text-purple-400">
                      <GitBranch className="w-3 h-3" /> Knowledge Graph (88% match)
                    </div>
                  </div>
                </div>

                {/* Token Usage */}
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div className="bg-slate-800 rounded-lg p-3 border border-slate-700">
                    <p className="text-lg font-bold text-emerald-400">{response.total_latency_ms}ms</p>
                    <p className="text-xs text-slate-500">Total Latency</p>
                  </div>
                  <div className="bg-slate-800 rounded-lg p-3 border border-slate-700">
                    <p className="text-lg font-bold text-blue-400">{response.tokens_used.input.toLocaleString()}</p>
                    <p className="text-xs text-slate-500">Input Tokens</p>
                  </div>
                  <div className="bg-slate-800 rounded-lg p-3 border border-slate-700">
                    <p className="text-lg font-bold text-purple-400">{response.tokens_used.output}</p>
                    <p className="text-xs text-slate-500">Output Tokens</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Empty State */}
      {!response && !isSearching && (
        <div className="px-5 py-12 text-center text-slate-500">
          <Search className="w-8 h-8 mx-auto mb-3 text-slate-600" />
          <p className="text-sm">Enter a query to see the RAG pipeline in action</p>
          <p className="text-xs mt-1">Vector search + SQL + Graph RAG → Hybrid re-ranking → LLM synthesis</p>
        </div>
      )}

      {/* Loading Animation */}
      {isSearching && (
        <div className="px-5 py-8">
          <div className="space-y-3">
            {["Query Analysis", "Embedding Generation", "Vector Search", "SQL Query", "Graph Traversal", "Re-ranking", "LLM Synthesis"].map((step, idx) => (
              <div key={idx} className="flex items-center gap-3 animate-pulse" style={{ animationDelay: `${idx * 200}ms` }}>
                <div className="w-4 h-4 rounded-full bg-emerald-500/30" />
                <span className="text-sm text-slate-400">{step}</span>
                <div className="flex-1 h-1 bg-slate-700 rounded-full overflow-hidden">
                  <div className="h-full bg-emerald-500/50 rounded-full animate-[pulse_1s_ease-in-out_infinite]" style={{ width: `${100 - idx * 10}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
