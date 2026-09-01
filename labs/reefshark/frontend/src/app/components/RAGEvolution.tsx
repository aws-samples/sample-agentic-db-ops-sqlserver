"use client";

import { useState } from "react";
import {
  ArrowRight,
  ArrowDown,
  RotateCcw,
  CheckCircle2,
  XCircle,
  Brain,
  Search,
  Database,
  MessageSquare,
  GitBranch,
  Zap,
  Target,
  Layers,
  ChevronDown,
  ChevronRight,
  Clock,
  AlertTriangle,
} from "lucide-react";

// ==================== TYPES ====================

interface StandardRAGStep {
  name: string;
  description: string;
  duration_ms: number;
  output: string;
}

interface AgentLoop {
  iteration: number;
  thought: string;
  action: string;
  tool_used: string;
  tool_input: string;
  observation: string;
  evaluation: { score: number; sufficient: boolean; reason: string };
  duration_ms: number;
}

interface AgenticRAGResult {
  goal: string;
  total_iterations: number;
  loops: AgentLoop[];
  final_answer: string;
  total_duration_ms: number;
  tools_called: string[];
  evaluation_metrics: {
    faithfulness: number;
    relevancy: number;
    context_precision: number;
    answer_completeness: number;
  };
}

interface ComparisonResult {
  standard: { steps: StandardRAGStep[]; answer: string; total_ms: number; quality_score: number };
  agentic: AgenticRAGResult;
}

// ==================== MOCK DATA ====================

const MOCK_COMPARISON: ComparisonResult = {
  standard: {
    steps: [
      { name: "Query Parsing", description: "Extract intent and entities", duration_ms: 8, output: "Intent: travel_search | Entities: [Paris, budget, family]" },
      { name: "Embedding", description: "Generate query vector", duration_ms: 42, output: "Vector[3072] generated via text-embedding-3-large" },
      { name: "Retrieval", description: "Single-pass vector search", duration_ms: 31, output: "Retrieved 5 chunks (top score: 0.87)" },
      { name: "Generation", description: "LLM generates answer from context", duration_ms: 650, output: "Generated response using retrieved context" },
    ],
    answer: "Here are some Paris travel options for families:\n\n1. Air France flights from $649\n2. Family-friendly hotels from $189/night\n3. Activities include Eiffel Tower and Louvre\n\nBudget estimate: ~$2,500 for a week.",
    total_ms: 731,
    quality_score: 0.72,
  },
  agentic: {
    goal: "Plan a complete family trip to Paris within budget, ensuring kid-friendly options and optimal scheduling",
    total_iterations: 4,
    loops: [
      {
        iteration: 1,
        thought: "User wants a family trip to Paris. I need to understand: budget constraints, travel dates, children's ages, and interests. Let me first search for family-specific Paris packages.",
        action: "Search for family Paris travel packages with budget constraints",
        tool_used: "vector_search",
        tool_input: "family friendly Paris vacation packages budget",
        observation: "Found 5 results. Top result mentions a family package but doesn't include children's activity details or age-appropriate recommendations.",
        evaluation: { score: 0.6, sufficient: false, reason: "Missing kid-specific activities and age-appropriate hotel amenities. Need to search specifically for family activities." },
        duration_ms: 145,
      },
      {
        iteration: 2,
        thought: "The initial results lack children's activity details. I should query the knowledge graph for Paris family attractions with age ratings, and check SQL for hotels with family amenities.",
        action: "Query knowledge graph for family attractions + SQL for family hotels",
        tool_used: "graph_rag + sql_query",
        tool_input: "MATCH (a:Activity)-[:SUITABLE_FOR]->(age:AgeGroup {range:'4-12'}) WHERE a.city='Paris' RETURN a | SELECT * FROM hotels WHERE family_friendly=1 AND city='Paris'",
        observation: "Graph returned 12 kid-friendly activities with age ratings. SQL returned 8 family hotels with amenities like kids' clubs, connecting rooms, and child menus.",
        evaluation: { score: 0.78, sufficient: false, reason: "Good activity and hotel data, but missing transportation logistics and scheduling optimization for families with kids." },
        duration_ms: 234,
      },
      {
        iteration: 3,
        thought: "I have flights, hotels, and activities. But families need logistics — travel time between venues, nap schedules for young kids, restaurant booking times. Let me query for proximity data and build an optimal schedule.",
        action: "Query graph for venue proximity + build day-by-day itinerary",
        tool_used: "graph_rag + reasoning",
        tool_input: "MATCH (v1:Venue)-[:NEAR {max_distance: '2km'}]->(v2:Venue) WHERE v1.city='Paris' AND v1.kid_friendly=true RETURN v1, v2, distance",
        observation: "Built proximity map. Eiffel Tower → Champ de Mars playground (200m), Louvre → Tuileries Garden (50m), Sacré-Cœur → artist playground (300m). Can cluster activities by area for minimal transit.",
        evaluation: { score: 0.91, sufficient: false, reason: "Excellent logistics data. Still need to verify total cost fits budget and add contingency recommendations." },
        duration_ms: 189,
      },
      {
        iteration: 4,
        thought: "Final check: calculate total cost, verify it's within budget, and add practical family travel tips (stroller access, metro with kids, restaurant high chairs).",
        action: "Calculate final budget + retrieve practical family tips",
        tool_used: "sql_query + vector_search",
        tool_input: "SELECT SUM(cost) FROM (flight + hotel + activities) | family travel tips Paris with young children practical advice",
        observation: "Total: $2,147 (under $2,500 budget with $353 buffer). Retrieved 3 highly relevant tip documents about Paris with kids (metro accessibility, restaurant culture, pharmacy locations).",
        evaluation: { score: 0.95, sufficient: true, reason: "Complete family itinerary with budget verification, age-appropriate activities, logistics, and practical tips. Ready to present." },
        duration_ms: 178,
      },
    ],
    final_answer: "🎉 **Your Complete Paris Family Trip** (Under Budget: $2,147 / $2,500)\n\n✈️ **Flights:** Air France JFK→CDG — $649/person × 2 adults + $489 × 2 kids = $2,276... wait, let me use the family package: **$1,890 total (family of 4)**\n\n🏨 **Hotel:** Le Petit Family Suites — $185/night × 5 nights = $925\n- Connecting rooms, kids' club, high chairs at breakfast\n- 5 min walk to metro (stroller accessible)\n\n🎯 **Day-by-Day Itinerary (kid-optimized):**\n\nDay 1: Eiffel Tower (morning, less crowds) → Champ de Mars playground → Crêpes at Rue Cler\nDay 2: Louvre (kids' trail, 2hr max) → Tuileries Garden → Carousel\nDay 3: Sacré-Cœur (funicular!) → Artist square → Playground\nDay 4: Jardin du Luxembourg (boats & puppet show) → Luxembourg playground\nDay 5: Versailles gardens (bike rental with kid seats)\n\n💰 **Budget Breakdown:**\n- Flights: $1,890 | Hotel: $925 | Activities: $180 | Food buffer: $300\n- **Total: $2,147** (buffer: $353 for souvenirs & treats)\n\n💡 **Pro Tips:**\n- Metro lines 1 & 14 are fully automated (wide doors for strollers)\n- Most restaurants seat families before 7:30 PM\n- Pharmacies (green cross) are everywhere for emergencies",
    total_duration_ms: 1846,
    tools_called: ["vector_search", "graph_rag", "sql_query", "reasoning"],
    evaluation_metrics: {
      faithfulness: 0.94,
      relevancy: 0.96,
      context_precision: 0.91,
      answer_completeness: 0.95,
    },
  },
};

const VECTOR_DB_COMPARISON = [
  {
    name: "ChromaDB",
    type: "Embedded",
    best_for: "Prototyping, small-medium datasets",
    max_vectors: "~1M",
    latency: "5-20ms",
    features: ["Python-native", "Auto-embedding", "Metadata filtering", "Persistent storage"],
    pros: ["Zero config", "Great DX", "Lightweight"],
    cons: ["Not distributed", "Limited scale"],
  },
  {
    name: "Pinecone",
    type: "Managed Cloud",
    best_for: "Production, serverless scale",
    max_vectors: "Billions",
    latency: "10-50ms",
    features: ["Serverless", "Hybrid search", "Namespaces", "Metadata filtering"],
    pros: ["Zero ops", "Auto-scaling", "High availability"],
    cons: ["Vendor lock-in", "Cost at scale", "No self-host"],
  },
  {
    name: "Weaviate",
    type: "Self-hosted / Cloud",
    best_for: "Multi-modal, GraphQL-native apps",
    max_vectors: "Billions",
    latency: "10-30ms",
    features: ["Multi-modal", "GraphQL API", "Hybrid search", "Generative modules"],
    pros: ["Flexible", "Multi-modal", "Good community"],
    cons: ["Complex setup", "Resource heavy"],
  },
  {
    name: "pgvector (RDS)",
    type: "PostgreSQL Extension",
    best_for: "Existing Postgres stacks, transactional + vector",
    max_vectors: "~10M",
    latency: "10-50ms",
    features: ["SQL interface", "ACID transactions", "HNSW + IVFFlat", "Hybrid queries"],
    pros: ["Use existing DB", "SQL familiar", "Transactional"],
    cons: ["Performance ceiling", "Manual tuning", "Limited ANN"],
  },
  {
    name: "Azure AI Search",
    type: "Managed Cloud",
    best_for: "Enterprise, SQL Server ecosystems",
    max_vectors: "Billions",
    latency: "20-80ms",
    features: ["Hybrid (BM25 + vector)", "Semantic ranker", "Integrated with Azure AI", "Skillsets"],
    pros: ["Enterprise ready", "Hybrid native", "Azure ecosystem"],
    cons: ["Cost", "Azure-only", "Complex pricing"],
  },
];

const MULTI_AGENT_ARCHITECTURE = {
  coordinator: {
    name: "Trip Coordinator Agent",
    role: "Orchestrates sub-agents, maintains goal state, evaluates completeness",
    model: "Claude 3.5 Sonnet",
  },
  agents: [
    { name: "Flight Agent", role: "Searches and compares flights", tools: ["vector_search", "airline_api", "price_compare"], color: "blue" },
    { name: "Hotel Agent", role: "Finds accommodations matching preferences", tools: ["vector_search", "sql_query", "review_analyzer"], color: "green" },
    { name: "Activity Agent", role: "Discovers and schedules activities", tools: ["graph_rag", "vector_search", "scheduling_engine"], color: "orange" },
    { name: "Budget Agent", role: "Tracks costs, optimizes spend, finds deals", tools: ["sql_query", "price_monitor", "coupon_search"], color: "purple" },
    { name: "Logistics Agent", role: "Handles transport, timing, accessibility", tools: ["graph_rag", "maps_api", "transit_api"], color: "pink" },
  ],
  communication: "Message passing via shared context + event bus",
  coordination_pattern: "Hierarchical with parallel execution",
};

// ==================== COMPONENT ====================

export default function RAGEvolution() {
  const [activeSection, setActiveSection] = useState<"comparison" | "vectordb" | "agents" | "metrics">("comparison");
  const [expandedLoops, setExpandedLoops] = useState<Set<number>>(new Set([0]));
  const [showStandard, setShowStandard] = useState(true);
  const [showAgentic, setShowAgentic] = useState(true);

  const toggleLoop = (idx: number) => {
    const next = new Set(expandedLoops);
    next.has(idx) ? next.delete(idx) : next.add(idx);
    setExpandedLoops(next);
  };

  return (
    <div className="bg-slate-900 text-slate-100 rounded-xl border border-slate-700 overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-900 to-purple-900 px-5 py-4 border-b border-slate-700">
        <div className="flex items-center gap-3">
          <div className="bg-white/10 rounded-lg p-2">
            <Brain className="w-5 h-5 text-indigo-300" />
          </div>
          <div>
            <h2 className="font-bold text-sm">RAG Evolution: Standard → Agentic</h2>
            <p className="text-xs text-indigo-200">Compare retrieval strategies, vector DBs, and multi-agent coordination</p>
          </div>
        </div>

        {/* Flow Diagrams */}
        <div className="mt-4 space-y-2">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-400 w-24">Standard RAG:</span>
            <div className="flex items-center gap-1">
              <span className="bg-slate-700 px-2 py-0.5 rounded">User Query</span>
              <ArrowRight className="w-3 h-3 text-slate-500" />
              <span className="bg-blue-900/50 px-2 py-0.5 rounded text-blue-300">Search DB</span>
              <ArrowRight className="w-3 h-3 text-slate-500" />
              <span className="bg-emerald-900/50 px-2 py-0.5 rounded text-emerald-300">Generate Answer</span>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-400 w-24">Agentic RAG:</span>
            <div className="flex items-center gap-1">
              <span className="bg-slate-700 px-2 py-0.5 rounded">User Goal</span>
              <ArrowRight className="w-3 h-3 text-slate-500" />
              <span className="bg-purple-900/50 px-2 py-0.5 rounded text-purple-300">Agent Reasons</span>
              <ArrowRight className="w-3 h-3 text-slate-500" />
              <span className="bg-blue-900/50 px-2 py-0.5 rounded text-blue-300">Calls RAG Tool</span>
              <ArrowRight className="w-3 h-3 text-slate-500" />
              <span className="bg-orange-900/50 px-2 py-0.5 rounded text-orange-300">Evaluates</span>
              <ArrowRight className="w-3 h-3 text-slate-500" />
              <span className="bg-pink-900/50 px-2 py-0.5 rounded text-pink-300 flex items-center gap-1">
                <RotateCcw className="w-3 h-3" /> Loop/Output
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Section Tabs */}
      <div className="flex border-b border-slate-700 bg-slate-800/50">
        {([
          { key: "comparison", label: "⚔️ Side-by-Side Comparison" },
          { key: "vectordb", label: "🗄️ Vector DB Selection" },
          { key: "agents", label: "🤖 Multi-Agent Design" },
          { key: "metrics", label: "📊 Evaluation Metrics" },
        ] as const).map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveSection(tab.key)}
            className={`px-4 py-2.5 text-xs font-medium transition-colors ${
              activeSection === tab.key
                ? "border-b-2 border-indigo-400 text-indigo-300 bg-slate-800"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="p-5 max-h-[600px] overflow-y-auto">
        {/* ==================== COMPARISON SECTION ==================== */}
        {activeSection === "comparison" && (
          <div className="space-y-4">
            {/* Toggle buttons */}
            <div className="flex gap-3">
              <button
                onClick={() => setShowStandard(!showStandard)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  showStandard ? "bg-blue-900/50 border-blue-600 text-blue-300" : "bg-slate-800 border-slate-600 text-slate-400"
                }`}
              >
                Standard RAG
              </button>
              <button
                onClick={() => setShowAgentic(!showAgentic)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  showAgentic ? "bg-purple-900/50 border-purple-600 text-purple-300" : "bg-slate-800 border-slate-600 text-slate-400"
                }`}
              >
                Agentic RAG
              </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Standard RAG */}
              {showStandard && (
                <div className="bg-slate-800 rounded-lg border border-blue-800/50 overflow-hidden">
                  <div className="bg-blue-900/30 px-4 py-2.5 border-b border-blue-800/50 flex items-center gap-2">
                    <Search className="w-4 h-4 text-blue-400" />
                    <span className="text-sm font-bold text-blue-300">Standard RAG</span>
                    <span className="ml-auto text-xs text-slate-400">{MOCK_COMPARISON.standard.total_ms}ms</span>
                  </div>
                  <div className="p-4 space-y-3">
                    {/* Pipeline */}
                    <div className="space-y-2">
                      {MOCK_COMPARISON.standard.steps.map((step, idx) => (
                        <div key={idx} className="flex items-center gap-2">
                          <div className="w-5 h-5 rounded-full bg-blue-500/20 flex items-center justify-center">
                            <span className="text-xs text-blue-400">{idx + 1}</span>
                          </div>
                          <span className="text-xs flex-1">{step.name}</span>
                          <code className="text-xs text-slate-500 font-mono">{step.duration_ms}ms</code>
                        </div>
                      ))}
                    </div>
                    {/* Answer */}
                    <div className="bg-slate-900 rounded-lg p-3 mt-3">
                      <p className="text-xs text-slate-400 mb-1">Generated Answer:</p>
                      <p className="text-sm text-slate-200 whitespace-pre-wrap">{MOCK_COMPARISON.standard.answer}</p>
                    </div>
                    {/* Score */}
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-xs text-slate-400">Quality Score:</span>
                      <div className="flex-1 h-2 bg-slate-700 rounded-full">
                        <div className="h-full bg-blue-500 rounded-full" style={{ width: `${MOCK_COMPARISON.standard.quality_score * 100}%` }} />
                      </div>
                      <span className="text-xs font-mono text-blue-400">{(MOCK_COMPARISON.standard.quality_score * 100).toFixed(0)}%</span>
                    </div>
                    <div className="text-xs text-yellow-500 flex items-center gap-1 mt-2">
                      <AlertTriangle className="w-3 h-3" />
                      Single-pass retrieval — may miss context, no self-evaluation
                    </div>
                  </div>
                </div>
              )}

              {/* Agentic RAG */}
              {showAgentic && (
                <div className="bg-slate-800 rounded-lg border border-purple-800/50 overflow-hidden">
                  <div className="bg-purple-900/30 px-4 py-2.5 border-b border-purple-800/50 flex items-center gap-2">
                    <Brain className="w-4 h-4 text-purple-400" />
                    <span className="text-sm font-bold text-purple-300">Agentic RAG</span>
                    <span className="ml-auto text-xs text-slate-400">{MOCK_COMPARISON.agentic.total_duration_ms}ms · {MOCK_COMPARISON.agentic.total_iterations} loops</span>
                  </div>
                  <div className="p-4 space-y-3">
                    {/* Goal */}
                    <div className="bg-purple-900/20 rounded-lg px-3 py-2 border border-purple-800/30">
                      <p className="text-xs text-purple-400 mb-0.5">🎯 Goal:</p>
                      <p className="text-xs text-slate-300">{MOCK_COMPARISON.agentic.goal}</p>
                    </div>

                    {/* Agent Loops */}
                    <div className="space-y-2">
                      {MOCK_COMPARISON.agentic.loops.map((loop, idx) => (
                        <div key={idx} className="bg-slate-900 rounded-lg border border-slate-700 overflow-hidden">
                          <button
                            onClick={() => toggleLoop(idx)}
                            className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-slate-800/50"
                          >
                            {expandedLoops.has(idx) ? <ChevronDown className="w-3 h-3 text-slate-400" /> : <ChevronRight className="w-3 h-3 text-slate-400" />}
                            <RotateCcw className="w-3 h-3 text-purple-400" />
                            <span className="text-xs font-medium">Loop {loop.iteration}</span>
                            <span className="text-xs text-slate-500 flex-1 truncate ml-2">{loop.action}</span>
                            <span className={`text-xs px-1.5 py-0.5 rounded ${loop.evaluation.sufficient ? "bg-emerald-900/50 text-emerald-400" : "bg-orange-900/50 text-orange-400"}`}>
                              {(loop.evaluation.score * 100).toFixed(0)}%
                            </span>
                            {loop.evaluation.sufficient ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <RotateCcw className="w-3 h-3 text-orange-400" />}
                          </button>
                          {expandedLoops.has(idx) && (
                            <div className="px-3 pb-3 space-y-2 text-xs">
                              <div className="bg-slate-800 rounded p-2">
                                <span className="text-purple-400 font-medium">💭 Thought: </span>
                                <span className="text-slate-300">{loop.thought}</span>
                              </div>
                              <div className="bg-slate-800 rounded p-2">
                                <span className="text-blue-400 font-medium">🔧 Tool: </span>
                                <code className="text-blue-300">{loop.tool_used}</code>
                                <div className="mt-1 text-slate-400 font-mono text-[10px]">{loop.tool_input}</div>
                              </div>
                              <div className="bg-slate-800 rounded p-2">
                                <span className="text-green-400 font-medium">👁️ Observation: </span>
                                <span className="text-slate-300">{loop.observation}</span>
                              </div>
                              <div className={`rounded p-2 ${loop.evaluation.sufficient ? "bg-emerald-900/20" : "bg-orange-900/20"}`}>
                                <span className={`font-medium ${loop.evaluation.sufficient ? "text-emerald-400" : "text-orange-400"}`}>
                                  {loop.evaluation.sufficient ? "✅" : "🔄"} Evaluation:
                                </span>
                                <span className="text-slate-300 ml-1">{loop.evaluation.reason}</span>
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>

                    {/* Quality Score */}
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-xs text-slate-400">Quality Score:</span>
                      <div className="flex-1 h-2 bg-slate-700 rounded-full">
                        <div className="h-full bg-purple-500 rounded-full" style={{ width: "95%" }} />
                      </div>
                      <span className="text-xs font-mono text-purple-400">95%</span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Key Differences Summary */}
            <div className="bg-slate-800 rounded-lg border border-slate-700 p-4 mt-4">
              <h4 className="text-xs font-bold text-slate-300 uppercase mb-3">Key Differences</h4>
              <div className="grid grid-cols-3 gap-4 text-xs">
                <div>
                  <p className="text-slate-500 mb-1">Metric</p>
                  <p className="text-slate-400">Latency</p>
                  <p className="text-slate-400">Quality</p>
                  <p className="text-slate-400">Self-correcting</p>
                  <p className="text-slate-400">Multi-source</p>
                  <p className="text-slate-400">Reasoning</p>
                </div>
                <div>
                  <p className="text-blue-400 mb-1">Standard RAG</p>
                  <p className="text-emerald-400">731ms ✓ Fast</p>
                  <p className="text-orange-400">72% — Acceptable</p>
                  <p className="text-red-400">✗ No</p>
                  <p className="text-red-400">✗ Single retrieval</p>
                  <p className="text-red-400">✗ None</p>
                </div>
                <div>
                  <p className="text-purple-400 mb-1">Agentic RAG</p>
                  <p className="text-orange-400">1,846ms — Slower</p>
                  <p className="text-emerald-400">95% ✓ Excellent</p>
                  <p className="text-emerald-400">✓ Loops until sufficient</p>
                  <p className="text-emerald-400">✓ Vector + SQL + Graph</p>
                  <p className="text-emerald-400">✓ Chain-of-thought</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ==================== VECTOR DB SECTION ==================== */}
        {activeSection === "vectordb" && (
          <div className="space-y-4">
            <p className="text-xs text-slate-400">Choose based on your scale, infrastructure, and integration requirements:</p>
            <div className="grid gap-3">
              {VECTOR_DB_COMPARISON.map((db, idx) => (
                <div key={idx} className="bg-slate-800 rounded-lg border border-slate-700 p-4">
                  <div className="flex items-center gap-3 mb-2">
                    <Database className="w-4 h-4 text-indigo-400" />
                    <span className="font-bold text-sm">{db.name}</span>
                    <span className="text-xs bg-slate-700 px-2 py-0.5 rounded text-slate-300">{db.type}</span>
                    <span className="ml-auto text-xs text-slate-500">Latency: {db.latency}</span>
                  </div>
                  <p className="text-xs text-indigo-300 mb-2">Best for: {db.best_for}</p>
                  <div className="flex flex-wrap gap-1 mb-2">
                    {db.features.map((f, i) => (
                      <span key={i} className="text-[10px] bg-indigo-900/30 text-indigo-300 px-2 py-0.5 rounded border border-indigo-800/30">{f}</span>
                    ))}
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs mt-2">
                    <div>
                      {db.pros.map((p, i) => (
                        <p key={i} className="text-emerald-400">✓ {p}</p>
                      ))}
                    </div>
                    <div>
                      {db.cons.map((c, i) => (
                        <p key={i} className="text-red-400">✗ {c}</p>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Recommendation */}
            <div className="bg-indigo-900/20 rounded-lg border border-indigo-700/50 p-4">
              <h4 className="text-xs font-bold text-indigo-300 uppercase mb-2">💡 Recommendation for This Architecture</h4>
              <p className="text-xs text-slate-300 leading-relaxed">
                <strong className="text-white">Primary:</strong> Azure AI Search (hybrid BM25 + vector, integrates with your RDS SQL Server ecosystem)<br/>
                <strong className="text-white">Secondary:</strong> pgvector on RDS PostgreSQL (for transactional data that also needs vector search)<br/>
                <strong className="text-white">Graph Layer:</strong> Neo4j or Amazon Neptune (for relationship traversal in knowledge graph RAG)
              </p>
            </div>
          </div>
        )}

        {/* ==================== MULTI-AGENT SECTION ==================== */}
        {activeSection === "agents" && (
          <div className="space-y-4">
            {/* Coordinator */}
            <div className="bg-gradient-to-r from-indigo-900/30 to-purple-900/30 rounded-lg border border-indigo-700/50 p-4">
              <div className="flex items-center gap-2 mb-2">
                <Brain className="w-5 h-5 text-indigo-400" />
                <span className="font-bold text-sm">{MULTI_AGENT_ARCHITECTURE.coordinator.name}</span>
                <span className="ml-auto text-xs bg-indigo-900/50 px-2 py-0.5 rounded text-indigo-300">
                  {MULTI_AGENT_ARCHITECTURE.coordinator.model}
                </span>
              </div>
              <p className="text-xs text-slate-300">{MULTI_AGENT_ARCHITECTURE.coordinator.role}</p>
              <div className="mt-2 flex gap-2 text-xs">
                <span className="bg-slate-700 px-2 py-0.5 rounded text-slate-300">Pattern: {MULTI_AGENT_ARCHITECTURE.coordination_pattern}</span>
                <span className="bg-slate-700 px-2 py-0.5 rounded text-slate-300">Comms: {MULTI_AGENT_ARCHITECTURE.communication}</span>
              </div>
            </div>

            {/* Agents Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {MULTI_AGENT_ARCHITECTURE.agents.map((agent, idx) => {
                const colors: Record<string, string> = {
                  blue: "border-blue-700/50 bg-blue-900/10",
                  green: "border-green-700/50 bg-green-900/10",
                  orange: "border-orange-700/50 bg-orange-900/10",
                  purple: "border-purple-700/50 bg-purple-900/10",
                  pink: "border-pink-700/50 bg-pink-900/10",
                };
                const textColors: Record<string, string> = {
                  blue: "text-blue-400",
                  green: "text-green-400",
                  orange: "text-orange-400",
                  purple: "text-purple-400",
                  pink: "text-pink-400",
                };
                return (
                  <div key={idx} className={`rounded-lg border p-3 ${colors[agent.color]}`}>
                    <div className="flex items-center gap-2 mb-1.5">
                      <Zap className={`w-4 h-4 ${textColors[agent.color]}`} />
                      <span className={`text-xs font-bold ${textColors[agent.color]}`}>{agent.name}</span>
                    </div>
                    <p className="text-xs text-slate-400 mb-2">{agent.role}</p>
                    <div className="flex flex-wrap gap-1">
                      {agent.tools.map((tool, i) => (
                        <span key={i} className="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded font-mono">{tool}</span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Communication Flow */}
            <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
              <h4 className="text-xs font-bold text-slate-300 uppercase mb-3">Agent Communication Flow</h4>
              <pre className="text-xs text-emerald-400 font-mono leading-relaxed">{`┌─────────────────────────────────────────────────────┐
│              Trip Coordinator Agent                   │
│    (Goal tracking, evaluation, orchestration)        │
└──────┬──────┬──────┬──────┬──────┬──────────────────┘
       │      │      │      │      │
  ┌────▼──┐ ┌─▼───┐ ┌▼────┐ ┌─▼──┐ ┌▼────────┐
  │Flight │ │Hotel│ │Act- │ │Bud-│ │Logistics│
  │Agent  │ │Agent│ │ivity│ │get │ │Agent    │
  └───┬───┘ └──┬──┘ │Agent│ │Agt │ └────┬────┘
      │        │    └──┬──┘ └─┬──┘      │
      ▼        ▼       ▼      ▼         ▼
  ┌─────────────────────────────────────────┐
  │         Shared Context Store            │
  │   (Vector DB + SQL + Knowledge Graph)   │
  └─────────────────────────────────────────┘`}</pre>
            </div>
          </div>
        )}

        {/* ==================== METRICS SECTION ==================== */}
        {activeSection === "metrics" && (
          <div className="space-y-4">
            <p className="text-xs text-slate-400">RAGAS-based evaluation framework for measuring RAG quality:</p>

            {/* Metrics Cards */}
            <div className="grid grid-cols-2 gap-3">
              {Object.entries(MOCK_COMPARISON.agentic.evaluation_metrics).map(([key, value]) => {
                const labels: Record<string, { label: string; description: string; color: string }> = {
                  faithfulness: { label: "Faithfulness", description: "Is the answer grounded in retrieved context?", color: "emerald" },
                  relevancy: { label: "Answer Relevancy", description: "Does the answer address the original question?", color: "blue" },
                  context_precision: { label: "Context Precision", description: "Are retrieved passages actually relevant?", color: "purple" },
                  answer_completeness: { label: "Answer Completeness", description: "Does the answer cover all aspects of the query?", color: "orange" },
                };
                const meta = labels[key];
                return (
                  <div key={key} className="bg-slate-800 rounded-lg border border-slate-700 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold text-slate-300">{meta.label}</span>
                      <span className={`text-lg font-bold text-${meta.color}-400`}>{(value * 100).toFixed(0)}%</span>
                    </div>
                    <div className="h-2 bg-slate-700 rounded-full mb-2">
                      <div className={`h-full bg-${meta.color}-500 rounded-full`} style={{ width: `${value * 100}%` }} />
                    </div>
                    <p className="text-xs text-slate-500">{meta.description}</p>
                  </div>
                );
              })}
            </div>

            {/* Evaluation Framework */}
            <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
              <h4 className="text-xs font-bold text-slate-300 uppercase mb-3">Evaluation Pipeline</h4>
              <div className="space-y-2 text-xs">
                <div className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-blue-500/20 flex items-center justify-center text-blue-400 text-[10px]">1</span>
                  <span className="text-slate-300">Generate test queries from your document corpus (synthetic QA pairs)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-blue-500/20 flex items-center justify-center text-blue-400 text-[10px]">2</span>
                  <span className="text-slate-300">Run queries through both Standard and Agentic RAG pipelines</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-blue-500/20 flex items-center justify-center text-blue-400 text-[10px]">3</span>
                  <span className="text-slate-300">Score with RAGAS metrics: faithfulness, relevancy, precision, completeness</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-blue-500/20 flex items-center justify-center text-blue-400 text-[10px]">4</span>
                  <span className="text-slate-300">Compare latency vs. quality tradeoffs per strategy</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-blue-500/20 flex items-center justify-center text-blue-400 text-[10px]">5</span>
                  <span className="text-slate-300">A/B test in production with user satisfaction signals</span>
                </div>
              </div>
            </div>

            {/* When to use which */}
            <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
              <h4 className="text-xs font-bold text-slate-300 uppercase mb-3">When to Use Which?</h4>
              <div className="grid grid-cols-2 gap-4 text-xs">
                <div>
                  <p className="text-blue-400 font-bold mb-2">✓ Use Standard RAG when:</p>
                  <ul className="space-y-1 text-slate-400">
                    <li>• Simple factual lookups</li>
                    <li>• Low-latency requirements (&lt;500ms)</li>
                    <li>• Single-domain queries</li>
                    <li>• Cost-sensitive at scale</li>
                    <li>• High query volume, simple answers</li>
                  </ul>
                </div>
                <div>
                  <p className="text-purple-400 font-bold mb-2">✓ Use Agentic RAG when:</p>
                  <ul className="space-y-1 text-slate-400">
                    <li>• Complex, multi-step reasoning needed</li>
                    <li>• Multiple data sources required</li>
                    <li>• Quality &gt; speed tradeoff acceptable</li>
                    <li>• Self-correction improves outcomes</li>
                    <li>• Planning and scheduling tasks</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
