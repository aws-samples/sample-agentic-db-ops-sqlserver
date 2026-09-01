"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import Header from "../components/Header";
import {
  Server, Cpu, Activity, AlertTriangle, CheckCircle2, Zap,
  TrendingUp, Clock, Play, Square, Brain, Database,
  RefreshCw, BarChart3, Shield, Flame,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/app";

// ===== SCENARIO DATA =====
const SCENARIOS = [
  {
    category: "🏖️ Seasonal",
    items: [
      { id: "summer", name: "Summer Holiday Rush", icon: "☀️", desc: "Jun-Aug family vacation surge", pattern: "ramp", intensity: 4, duration: "3 min", problem: "CPU + I/O", workers: 40, color: "amber" },
      { id: "christmas", name: "Christmas & New Year", icon: "🎄", desc: "Last-minute ski + warm escapes", pattern: "spike", intensity: 6, duration: "60s", problem: "Locks + CPU", workers: 60, color: "red" },
      { id: "spring", name: "Spring Break", icon: "🌸", desc: "Students flooding budget beaches", pattern: "burst-decay", intensity: 5, duration: "45s", problem: "Plan Sniffing", workers: 30, color: "pink" },
      { id: "thanksgiving", name: "Thanksgiving Week", icon: "🦃", desc: "US domestic flight search spike", pattern: "ramp", intensity: 3, duration: "5 min", problem: "Plan Sniffing", workers: 50, color: "orange" },
    ],
  },
  {
    category: "🏟️ Sporting Events",
    items: [
      { id: "fifa", name: "FIFA World Cup", icon: "⚽", desc: "Millions search host-city flights + hotels", pattern: "sustained", intensity: 8, duration: "5 min", problem: "ALL", workers: 80, color: "green" },
      { id: "olympics", name: "Olympics 2028 LA", icon: "🏅", desc: "Single-city demand concentration", pattern: "ramp", intensity: 6, duration: "3 min", problem: "Locks + TempDB", workers: 60, color: "blue" },
      { id: "superbowl", name: "Super Bowl Weekend", icon: "🏈", desc: "Short burst, premium bookings", pattern: "spike", intensity: 10, duration: "30s", problem: "Lock Contention", workers: 100, color: "red" },
      { id: "ucl", name: "Champions League Final", icon: "🏆", desc: "European routes hammered", pattern: "burst-decay", intensity: 5, duration: "60s", problem: "Plan Sniffing", workers: 50, color: "blue" },
      { id: "f1", name: "F1 Grand Prix", icon: "🏎️", desc: "Monaco/Singapore surge", pattern: "sustained", intensity: 4, duration: "2 min", problem: "CPU + TempDB", workers: 35, color: "red" },
      { id: "cricket", name: "Cricket World Cup", icon: "🏏", desc: "India/Aus/UK routes saturated", pattern: "sustained", intensity: 6, duration: "3 min", problem: "I/O + Plan Sniffing", workers: 55, color: "green" },
    ],
  },
  {
    category: "🎵 Entertainment",
    items: [
      { id: "swift", name: "Taylor Swift Eras Tour", icon: "🎤", desc: "City announced → instant flood", pattern: "spike", intensity: 10, duration: "20s", problem: "Locks + CPU", workers: 100, color: "pink" },
      { id: "beyonce", name: "Beyoncé World Tour", icon: "👑", desc: "Premium hotel search surge", pattern: "spike", intensity: 8, duration: "30s", problem: "TempDB + Locks", workers: 80, color: "yellow" },
      { id: "coldplay", name: "Coldplay Mumbai Concert", icon: "🎸", desc: "Asian routes + specific city", pattern: "spike", intensity: 7, duration: "25s", problem: "Plan Sniffing", workers: 70, color: "cyan" },
      { id: "coachella", name: "Coachella / Glastonbury", icon: "🎪", desc: "Festival announcement → bookings", pattern: "ramp", intensity: 4, duration: "2 min", problem: "CPU", workers: 40, color: "orange" },
      { id: "kpop", name: "K-Pop Concert Drop", icon: "💜", desc: "BTS/BLACKPINK ticket + travel", pattern: "spike", intensity: 9, duration: "15s", problem: "ALL", workers: 90, color: "purple" },
    ],
  },
  {
    category: "⚡ Flash Events",
    items: [
      { id: "flash", name: "Flash Sale (40% off)", icon: "💥", desc: "Marketing email → everyone at once", pattern: "spike", intensity: 10, duration: "10s", problem: "ALL", workers: 100, color: "red" },
      { id: "viral", name: "Travel Influencer Post", icon: "📱", desc: "Viral destination → text searches", pattern: "ramp", intensity: 5, duration: "90s", problem: "I/O (full scans)", workers: 50, color: "pink" },
      { id: "blackfriday", name: "Black Friday Deals", icon: "🛒", desc: "All endpoints hammered equally", pattern: "ramp", intensity: 8, duration: "3 min", problem: "ALL", workers: 80, color: "slate" },
      { id: "pricedrop", name: "Airline Price Drop Alert", icon: "📉", desc: "Bot + human traffic to routes", pattern: "sustained", intensity: 4, duration: "2 min", problem: "Plan Sniffing", workers: 40, color: "green" },
      { id: "disaster", name: "Natural Disaster Rerouting", icon: "🌋", desc: "Mass rebooking, availability checks", pattern: "sustained", intensity: 6, duration: "5 min", problem: "Deadlocks", workers: 60, color: "red" },
    ],
  },
  {
    category: "📅 Time-Based",
    items: [
      { id: "friday", name: "Friday Evening Browsing", icon: "🌙", desc: "After-work trip planning", pattern: "ramp", intensity: 2, duration: "3 min", problem: "CPU", workers: 20, color: "indigo" },
      { id: "sunday", name: "Sunday Night Last-Minute", icon: "⏰", desc: "Book before Monday rush", pattern: "burst-decay", intensity: 4, duration: "90s", problem: "Locks", workers: 35, color: "purple" },
      { id: "payday", name: "Pay Day Spike (1st/15th)", icon: "💰", desc: "Monthly salary → booking surge", pattern: "wave", intensity: 3, duration: "4 min", problem: "CPU + I/O", workers: 30, color: "green" },
      { id: "longweekend", name: "Long Weekend Announced", icon: "🗓️", desc: "Govt holiday → instant demand", pattern: "spike", intensity: 5, duration: "60s", problem: "Plan Sniffing + Locks", workers: 50, color: "blue" },
    ],
  },
];

const PATTERNS: Record<string, { shape: string; label: string }> = {
  spike: { shape: "▁▁██████▁▁", label: "Spike" },
  ramp: { shape: "▁▂▃▅▆▇████", label: "Ramp-Up" },
  sustained: { shape: "▅▅▅▅▅▅▅▅▅▅", label: "Sustained" },
  wave: { shape: "▃▅▇▅▃▅▇▅▃▅", label: "Wave" },
  "burst-decay": { shape: "████▇▅▃▂▁▁", label: "Burst-Decay" },
  sawtooth: { shape: "▁▃▅▇▁▃▅▇▁▃", label: "Sawtooth" },
};

const TRENDING = [
  { name: "Coldplay Mumbai", heat: 5, change: "+540%", pattern: "spike", spark: [1, 2, 3, 8, 15, 25, 40, 38, 30, 20] },
  { name: "UCL Final Munich", heat: 4, change: "+280%", pattern: "ramp", spark: [2, 3, 5, 8, 12, 16, 20, 24, 28, 30] },
  { name: "Bali Peak Season", heat: 3, change: "+180%", pattern: "sustained", spark: [15, 16, 18, 19, 20, 20, 21, 20, 19, 20] },
  { name: "Maldives Viral Reel", heat: 4, change: "+340%", pattern: "burst-decay", spark: [2, 5, 20, 35, 30, 22, 15, 10, 8, 6] },
];

const ALERTS = [
  { time: "12:54:01", type: "warning", agent: "Health", msg: "CPU crossed 80% threshold (current: 87%)" },
  { time: "12:54:03", type: "error", agent: "Performance", msg: "Plan regression detected on sp_SearchFlightsByRoute (query_id: 847)" },
  { time: "12:54:05", type: "info", agent: "Performance", msg: "Root cause: Parameter sniffing — plan compiled for JFK→LHR, reused for all routes" },
  { time: "12:54:07", type: "action", agent: "Actions", msg: "Recommending: Add OPTION(RECOMPILE) hint or force plan_id 12" },
  { time: "12:54:08", type: "approval", agent: "Supervisor", msg: "Approved: Force plan_id 12 via sp_query_store_force_plan (low risk)" },
  { time: "12:54:10", type: "success", agent: "Actions", msg: "Fix applied. Monitoring recovery..." },
  { time: "12:54:15", type: "success", agent: "Health", msg: "CPU dropped to 42%. Latency recovered: 450ms → 28ms" },
];

const REMEDIATION_TRACE = [
  { step: "Think", content: "CPU at 87% correlates with spike in sp_SearchFlightsByRoute executions. Checking Query Store for plan regression.", icon: "🧠" },
  { step: "Act", content: "EXEC get_query_store_top_queries @hours_back=1, @metric='cpu' → Found query_id 847 with avg_cpu_ms: 340 (was 12ms yesterday)", icon: "🔧" },
  { step: "Observe", content: "Plan compiled at 09:00 for JFK→LHR (2 rows). Now executing for all routes (avg 50K rows). Hash match spilling to TempDB.", icon: "👁️" },
  { step: "Evaluate", content: "Confidence: 94%. Root cause confirmed: parameter sniffing. Best fix: force good plan (plan_id 12) or add recompile hint.", icon: "⚖️" },
  { step: "Fix", content: "EXEC sp_query_store_force_plan @query_id=847, @plan_id=12 — Applied. CPU recovering.", icon: "✅" },
];

// ===== COMPONENT =====
export default function DBOpsPage() {
  const [selectedScenarios, setSelectedScenarios] = useState<Set<string>>(new Set());
  const [isRunning, setIsRunning] = useState(false);
  const [cpuData, setCpuData] = useState([25, 28, 30, 32, 35, 42, 55, 72, 87, 42]);
  const [expandedAlert, setExpandedAlert] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<"scenarios" | "trending" | "patterns">("scenarios");
  const [metrics, setMetrics] = useState<any>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [alertsData, setAlertsData] = useState<any[]>([]);
  const [remediation, setRemediation] = useState<any>(null);

  // Poll live RDS/SQL metrics every 5s.
  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/metrics`);
        const d = await res.json();
        if (!active) return;
        setMetrics(d);
        setMetricsError(d?.error ?? null);
        if (Array.isArray(d?.cpu?.series) && d.cpu.series.length) setCpuData(d.cpu.series);
        try {
          const ra = await fetch(`${API_BASE}/api/alerts`);
          const da = await ra.json();
          if (active && Array.isArray(da?.alerts)) setAlertsData(da.alerts);
        } catch {}
        try {
          const rr = await fetch(`${API_BASE}/api/remediation`);
          const dr = await rr.json();
          if (active) setRemediation(dr);
        } catch {}
      } catch (e: any) {
        if (active) setMetricsError(e?.message || "fetch failed");
      }
    };
    load();
    const t = setInterval(load, 5000);
    return () => { active = false; clearInterval(t); };
  }, []);

  const cpu = metrics?.cpu?.current ?? null;
  const peak = cpuData.length ? Math.max(...cpuData) : null;
  const fmt = (v: any) => (v === null || v === undefined ? "n/a" : v);
  const cpuColor = (v: number | null) =>
    v === null ? "text-slate-400"
      : v > 80 ? "text-red-500"
      : v > 60 ? "text-orange-400"
      : v > 40 ? "text-yellow-500"
      : "text-emerald-500";

  const loadRunning = metrics?.load_running ?? 0;
  const totalWorkers = Array.from(selectedScenarios).reduce((sum, id) => {
    const sc = SCENARIOS.flatMap((c) => c.items).find((s) => s.id === id);
    return sum + (sc?.workers || 0);
  }, 0);
  const launch = async () => {
    setIsRunning(true);
    try {
      await fetch(`${API_BASE}/api/load/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workers: totalWorkers || 16, scenarios: Array.from(selectedScenarios) }),
      });
    } catch {}
  };
  const stopAll = async () => {
    try {
      await fetch(`${API_BASE}/api/load/stop`, { method: "POST" });
    } finally {
      setIsRunning(false);
    }
  };

  const toggleScenario = (id: string) => {
    const next = new Set(selectedScenarios);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelectedScenarios(next);
  };

  const problemColor = (problem: string) => {
    if (problem.includes("ALL")) return "text-red-400 bg-red-900/30";
    if (problem.includes("CPU")) return "text-orange-400 bg-orange-900/30";
    if (problem.includes("Lock")) return "text-red-400 bg-red-900/30";
    if (problem.includes("I/O")) return "text-blue-400 bg-blue-900/30";
    if (problem.includes("TempDB")) return "text-yellow-400 bg-yellow-900/30";
    if (problem.includes("Plan")) return "text-purple-400 bg-purple-900/30";
    return "text-slate-500 bg-white";
  };

  const alertColor = (type: string) => {
    switch (type) {
      case "warning": return "border-l-yellow-500 bg-yellow-900/10";
      case "error": return "border-l-red-500 bg-red-900/10";
      case "info": return "border-l-blue-500 bg-blue-900/10";
      case "action": return "border-l-purple-500 bg-purple-900/10";
      case "approval": return "border-l-indigo-500 bg-indigo-900/10";
      case "success": return "border-l-emerald-500 bg-emerald-900/10";
      default: return "border-l-slate-500";
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      {/* Header */}
      <Header />

      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

          {/* LEFT: Scenario Panel */}
          <div className="col-span-5 space-y-4">
            {/* Tabs */}
            <div className="flex gap-1 bg-white rounded-lg p-1">
              {(["scenarios", "trending", "patterns"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`flex-1 px-3 py-2 rounded-md text-xs font-medium transition-colors capitalize ${
                    activeTab === tab ? "bg-indigo-50 text-indigo-700 border border-indigo-200" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  {tab === "scenarios" && "⚡ Scenarios"}
                  {tab === "trending" && "📈 Trending"}
                  {tab === "patterns" && "📊 Patterns"}
                </button>
              ))}
            </div>

            {/* Scenarios Tab */}
            {activeTab === "scenarios" && (
              <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
                {SCENARIOS.map((cat) => (
                  <div key={cat.category}>
                    <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">{cat.category}</h3>
                    <div className="space-y-1.5">
                      {cat.items.map((sc) => (
                        <div
                          key={sc.id}
                          onClick={() => toggleScenario(sc.id)}
                          className={`flex items-center gap-3 px-3 py-2.5 rounded-lg border cursor-pointer transition-all ${
                            selectedScenarios.has(sc.id)
                              ? "border-emerald-600 bg-emerald-900/20"
                              : "border-slate-200 bg-white hover:border-slate-200"
                          }`}
                        >
                          <span className="text-lg">{sc.icon}</span>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-semibold truncate">{sc.name}</span>
                              <span className={`text-[9px] px-1.5 py-0.5 rounded ${problemColor(sc.problem)}`}>{sc.problem}</span>
                            </div>
                            <div className="text-[10px] text-slate-500 mt-0.5">{sc.desc}</div>
                          </div>
                          <div className="text-right shrink-0">
                            <div className="text-[10px] text-slate-500 font-mono">{PATTERNS[sc.pattern]?.shape}</div>
                            <div className="text-[9px] text-slate-600">{sc.intensity}x · {sc.duration}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Trending Tab */}
            {activeTab === "trending" && (
              <div className="space-y-3">
                <h3 className="text-xs font-bold text-slate-500 uppercase">🔥 Hot Right Now</h3>
                {TRENDING.map((trend, idx) => (
                  <div key={idx} className="bg-white rounded-lg border border-slate-200 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-bold">{trend.name}</span>
                      <span className="text-xs font-bold text-emerald-400">{trend.change}</span>
                    </div>
                    <div className="flex items-end gap-0.5 h-8">
                      {trend.spark.map((v, i) => (
                        <div
                          key={i}
                          className="flex-1 rounded-sm bg-emerald-500/70 transition-all"
                          style={{ height: `${(v / 40) * 100}%` }}
                        />
                      ))}
                    </div>
                    <div className="flex items-center justify-between mt-2">
                      <span className="text-[10px] text-slate-500">{PATTERNS[trend.pattern]?.label} pattern</span>
                      <div className="flex gap-0.5">
                        {Array.from({ length: trend.heat }).map((_, i) => (
                          <Flame key={i} className="w-3 h-3 text-orange-400" />
                        ))}
                      </div>
                    </div>
                  </div>
                ))}

                {/* Time of Day */}
                <div className="bg-white rounded-lg border border-slate-200 p-4">
                  <h4 className="text-xs font-bold text-slate-500 mb-3">🕐 Typical Daily Pattern</h4>
                  <div className="flex items-end gap-0.5 h-16">
                    {[5, 4, 3, 3, 4, 8, 15, 25, 35, 40, 38, 42, 45, 40, 35, 30, 28, 32, 38, 42, 35, 25, 15, 8].map((v, i) => (
                      <div
                        key={i}
                        className={`flex-1 rounded-sm transition-all ${v > 35 ? "bg-orange-500/70" : v > 20 ? "bg-blue-500/70" : "bg-slate-100/70"}`}
                        style={{ height: `${(v / 45) * 100}%` }}
                        title={`${i}:00 - ${v}% capacity`}
                      />
                    ))}
                  </div>
                  <div className="flex justify-between mt-1 text-[9px] text-slate-600">
                    <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span>
                  </div>
                </div>
              </div>
            )}

            {/* Patterns Tab */}
            {activeTab === "patterns" && (
              <div className="space-y-3">
                <h3 className="text-xs font-bold text-slate-500 uppercase">Load Pattern Library</h3>
                {Object.entries(PATTERNS).map(([key, pat]) => (
                  <div key={key} className="bg-white rounded-lg border border-slate-200 p-3 flex items-center gap-4">
                    <span className="text-lg font-mono text-emerald-400 tracking-tighter">{pat.shape}</span>
                    <div>
                      <span className="text-xs font-bold">{pat.label}</span>
                      <p className="text-[10px] text-slate-500">
                        {key === "spike" && "Instant 8-10x, drops after 10-30s. Concerts, flash sales."}
                        {key === "ramp" && "Gradual 3-5x over 1-5min. Holiday seasons, growing demand."}
                        {key === "sustained" && "Steady 2-4x for 5-30min. FIFA matches, major events."}
                        {key === "wave" && "Repeating 2-3x cycles. Weekend patterns, commuter hours."}
                        {key === "burst-decay" && "Sharp 10x→1x over 30-60s. Flash sales ending, news breaking."}
                        {key === "sawtooth" && "Repeating ramps. Hourly batch jobs, cron-triggered load."}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Launch Controls */}
            <div className="bg-white rounded-lg border border-slate-200 p-4">
              <div className="flex items-center gap-3">
                <button
                  onClick={launch}
                  className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-slate-900 px-4 py-2 rounded-lg text-xs font-semibold transition-colors"
                >
                  <Play className="w-3 h-3" /> Launch ({selectedScenarios.size})
                </button>
                <button
                  onClick={stopAll}
                  className="flex items-center gap-2 bg-red-600/80 hover:bg-red-500 text-slate-900 px-4 py-2 rounded-lg text-xs font-semibold transition-colors"
                >
                  <Square className="w-3 h-3" /> Stop All
                </button>
                <span className="ml-auto text-xs text-slate-500">
                  {loadRunning > 0 ? `${loadRunning} workers running` : `${selectedScenarios.size} selected, ${totalWorkers} workers`}
                </span>
              </div>
            </div>
          </div>

          {/* RIGHT: Metrics + Alerts + Remediation */}
          <div className="col-span-7 space-y-4">
            {/* Metrics Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
                <Cpu className="w-4 h-4 text-orange-400 mx-auto mb-1" />
                <p className={`text-2xl font-bold ${cpuColor(cpu)}`}>{cpu === null ? "n/a" : `${cpu}%`}</p>
                <p className="text-[10px] text-slate-500">CPU</p>
              </div>
              <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
                <AlertTriangle className="w-4 h-4 text-red-400 mx-auto mb-1" />
                <p className="text-2xl font-bold text-red-400">{fmt(metrics?.blocking)}</p>
                <p className="text-[10px] text-slate-500">Blocking</p>
              </div>
              <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
                <Activity className="w-4 h-4 text-blue-400 mx-auto mb-1" />
                <p className="text-2xl font-bold text-blue-400">{fmt(metrics?.qps)}</p>
                <p className="text-[10px] text-slate-500">QPS</p>
              </div>
              <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
                <Zap className="w-4 h-4 text-emerald-400 mx-auto mb-1" />
                <p className="text-2xl font-bold text-emerald-400">{fmt(metrics?.workers)}</p>
                <p className="text-[10px] text-slate-500">Workers</p>
              </div>
            </div>

            {/* CPU Chart */}
            <div className="bg-white rounded-lg border border-slate-200 p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-slate-500">CPU Utilization (last 10 min)</span>
                <span className="text-xs text-slate-500">{metricsError ? "metrics unavailable" : `Peak: ${peak === null ? "n/a" : `${peak}%`}`}</span>
              </div>
              <div className="flex items-end gap-1 h-16">
                {cpuData.map((v, i) => (
                  <div
                    key={i}
                    className={`flex-1 rounded-sm transition-all ${v > 80 ? "bg-red-500" : v > 60 ? "bg-orange-500" : v > 40 ? "bg-yellow-500" : "bg-emerald-500"}`}
                    style={{ height: `${v}%` }}
                  />
                ))}
              </div>
              <div className="flex justify-between mt-1 text-[9px] text-slate-600">
                <span>-10min</span><span>-5min</span><span>Now</span>
              </div>
            </div>

            {/* Alerts Feed */}
            <div className="bg-white rounded-lg border border-slate-200 p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold text-slate-500">🔔 Real-Time Alerts</span>
                <span className="text-[10px] text-slate-500">{alertsData.length} events</span>
              </div>
              <div className="space-y-1.5 max-h-[180px] overflow-y-auto">
                {alertsData.map((alert, idx) => (
                  <div
                    key={idx}
                    className={`border-l-2 px-3 py-2 rounded-r-lg text-xs ${alertColor(alert.type)}`}
                  >
                    <span className="text-slate-500 font-mono mr-2">{alert.time}</span>
                    <span className="font-semibold text-slate-600 mr-1">[{alert.agent}]</span>
                    <span className="text-slate-600">{alert.msg}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Remediation Trace */}
            <div className="bg-white rounded-lg border border-slate-200 p-4">
              <div className="flex items-center gap-2 mb-3">
                <Brain className="w-4 h-4 text-purple-400" />
                <span className="text-xs font-bold text-slate-500">Agent Remediation Trace</span>
                <span className="ml-auto text-[10px] bg-emerald-900/30 text-emerald-400 px-2 py-0.5 rounded">{remediation?.status || "monitoring"}</span>
              </div>
              <div className="space-y-2">
                {(remediation?.steps || []).map((step: any, idx: number) => (
                  <div key={idx} className="flex gap-3 items-start">
                    <span className="text-sm shrink-0 text-purple-400 font-bold">{idx + 1}</span>
                    <div>
                      <span className="text-[10px] font-bold text-purple-400 uppercase">{step.step}</span>
                      <p className="text-xs text-slate-600 mt-0.5">{step.content}</p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Before/After */}
              <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="bg-red-900/20 rounded-lg p-3 border border-red-800/30 text-center">
                  <p className="text-[10px] text-red-400 font-bold uppercase">Peak</p>
                  <p className="text-lg font-bold text-red-400">{remediation?.cpu_before != null ? `${remediation.cpu_before}%` : "n/a"}</p>
                  <p className="text-[10px] text-slate-500">CPU before</p>
                </div>
                <div className="bg-emerald-900/20 rounded-lg p-3 border border-emerald-800/30 text-center">
                  <p className="text-[10px] text-emerald-400 font-bold uppercase">Now</p>
                  <p className="text-lg font-bold text-emerald-400">{remediation?.cpu_after != null ? `${remediation.cpu_after}%` : "n/a"}</p>
                  <p className="text-[10px] text-slate-500">CPU after</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
