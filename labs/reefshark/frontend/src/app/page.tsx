"use client";

import { useState, useRef, useEffect, type ReactNode } from "react";
import { Send, Sparkles, Loader2, Search, Plane, Hotel, MapPin, Ticket } from "lucide-react";
import Header from "./components/Header";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/app";

type Tab = "Destinations" | "Flights" | "Hotels" | "Activities";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("Destinations");
  const [wizardStarted, setWizardStarted] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Search inputs per tab
  const [destQ, setDestQ] = useState("eco-friendly beach snorkeling");
  const [flightFrom, setFlightFrom] = useState("");
  const [flightTo, setFlightTo] = useState("");
  const [hotelDest, setHotelDest] = useState("");
  const [actQ, setActQ] = useState("");

  // Results
  const [results, setResults] = useState<Row[]>([]);
  const [meta, setMeta] = useState<{ count: number; ms?: number; source?: string; winner?: string }>({ count: 0 });
  const [searching, setSearching] = useState(false);
  const [searchErr, setSearchErr] = useState<string | null>(null);

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  useEffect(() => { scrollToBottom(); }, [messages]);

  async function runSearch(tab: Tab) {
    setSearching(true);
    setSearchErr(null);
    try {
      let url = "";
      if (tab === "Destinations") url = `${API_BASE}/api/search?q=${encodeURIComponent(destQ)}&topk=8`;
      else if (tab === "Flights") url = `${API_BASE}/api/flights?origin=${encodeURIComponent(flightFrom)}&destination=${encodeURIComponent(flightTo)}&topk=8`;
      else if (tab === "Hotels") url = `${API_BASE}/api/hotels?destination=${encodeURIComponent(hotelDest)}&topk=8`;
      else url = `${API_BASE}/api/activities?q=${encodeURIComponent(actQ)}&topk=8`;

      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setResults(data.results || []);
      setMeta({ count: data.count ?? (data.results || []).length, ms: data.total_latency_ms ?? data.latency_ms, source: data.source, winner: data.winner });
    } catch (e) {
      setResults([]);
      setSearchErr(e instanceof Error ? e.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  // Auto-run the Destinations search on first load.
  useEffect(() => { runSearch("Destinations"); /* eslint-disable-next-line */ }, []);

  function switchTab(tab: Tab) {
    setActiveTab(tab);
    setResults([]);
    setMeta({ count: 0 });
    setSearchErr(null);
  }

  async function startWizard() {
    setWizardStarted(true);
    setMessages([{ role: "user", content: "Hello! I want to plan a trip." }]);
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "Hello! I want to plan a trip.", session_id: "default" }),
      });
      const data = await res.json();
      setMessages(prev => [...prev, { role: "assistant", content: data.message }]);
    } catch {
      setMessages(prev => [...prev, { role: "assistant", content: "⚠️ Backend not connected." }]);
    } finally { setIsLoading(false); }
  }

  async function sendMessage() {
    if (!input.trim()) return;
    setMessages(prev => [...prev, { role: "user", content: input }]);
    const msg = input;
    setInput("");
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, session_id: "default" }),
      });
      const data = await res.json();
      setMessages(prev => [...prev, { role: "assistant", content: data.message }]);
    } catch {
      setMessages(prev => [...prev, { role: "assistant", content: "⚠️ Backend not connected." }]);
    } finally { setIsLoading(false); }
  }

  const inputCls = "w-full pl-11 pr-4 py-3 border-2 border-slate-200 rounded-xl text-sm focus:outline-none focus:border-indigo-400 transition-colors";
  const btnCls = "px-6 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-xl text-sm font-semibold hover:shadow-lg transition-all disabled:opacity-50";

  return (
    <main className="min-h-screen flex flex-col">
      <Header />
      <div className="flex-1 flex flex-col lg:grid lg:grid-cols-[1fr_380px] min-h-0 overflow-hidden">
        {/* Left: Search */}
        <div className="flex-1 p-4 sm:p-6 lg:p-8 overflow-y-auto">
          <h2 className="text-xl sm:text-3xl font-extrabold text-slate-900 tracking-tight mb-1">Where to next?</h2>
          <p className="text-slate-500 text-sm mb-6">
            Destinations use TravelAI semantic search; Flights, Hotels &amp; Activities query live TravelHub data on RDS SQL Server.
          </p>

          {/* Tabs */}
          <div className="flex gap-0 border-b-2 border-slate-200 mb-5">
            {(["Destinations", "Flights", "Hotels", "Activities"] as Tab[]).map(tab => (
              <button key={tab} onClick={() => switchTab(tab)}
                className={`px-5 py-2.5 text-sm font-semibold border-b-2 -mb-[2px] transition-colors ${activeTab === tab ? "border-indigo-500 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
                {tab}
              </button>
            ))}
          </div>

          {/* Search bar per tab */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 mb-6 space-y-3">
            {activeTab === "Destinations" && (
              <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1">
                  <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <input type="text" value={destQ} onChange={e => setDestQ(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && runSearch("Destinations")}
                    placeholder="Describe your trip: eco-friendly beach, alpine skiing..." className={inputCls} />
                </div>
                <button onClick={() => runSearch("Destinations")} disabled={searching} className={btnCls}>Search</button>
              </div>
            )}

            {activeTab === "Flights" && (
              <div className="flex flex-col sm:flex-row gap-3">
                <input type="text" value={flightFrom} onChange={e => setFlightFrom(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && runSearch("Flights")}
                  placeholder="From (e.g. Paris)" className="flex-1 px-4 py-3 border-2 border-slate-200 rounded-xl text-sm focus:outline-none focus:border-indigo-400" />
                <input type="text" value={flightTo} onChange={e => setFlightTo(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && runSearch("Flights")}
                  placeholder="To (e.g. Bali)" className="flex-1 px-4 py-3 border-2 border-slate-200 rounded-xl text-sm focus:outline-none focus:border-indigo-400" />
                <button onClick={() => runSearch("Flights")} disabled={searching} className={btnCls}>Search</button>
              </div>
            )}

            {activeTab === "Hotels" && (
              <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1">
                  <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <input type="text" value={hotelDest} onChange={e => setHotelDest(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && runSearch("Hotels")}
                    placeholder="Destination city (e.g. Paris, Tokyo, Bali)" className={inputCls} />
                </div>
                <button onClick={() => runSearch("Hotels")} disabled={searching} className={btnCls}>Search</button>
              </div>
            )}

            {activeTab === "Activities" && (
              <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1">
                  <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <input type="text" value={actQ} onChange={e => setActQ(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && runSearch("Activities")}
                    placeholder="Activity or city (e.g. diving, hiking, Paris)" className={inputCls} />
                </div>
                <button onClick={() => runSearch("Activities")} disabled={searching} className={btnCls}>Search</button>
              </div>
            )}

            <div className="flex items-center gap-2 text-[11px] text-slate-500">
              {searching ? <><Loader2 className="w-3 h-3 animate-spin" /> Querying...</>
                : searchErr ? <span className="text-red-500">Error: {searchErr}</span>
                : <span>{meta.count} results{meta.ms != null ? ` · ${meta.ms}ms` : ""}{meta.source ? ` · ${meta.source}` : ""}{meta.winner ? ` · winner: ${meta.winner}` : ""}</span>}
            </div>
          </div>

          {/* Results */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {results.map((r, i) => <ResultCard key={i} tab={activeTab} r={r} />)}
            {!searching && results.length === 0 && !searchErr && (
              <div className="text-sm text-slate-400">No results — try a different search.</div>
            )}
          </div>
        </div>

        {/* Right: Chat */}
        <div className="bg-white border-t lg:border-t-0 lg:border-l border-slate-200 flex flex-col h-[300px] lg:h-auto">
          <div className="p-4 border-b border-slate-100">
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" /> Finn — Trip Planner
            </h3>
            <p className="text-[11px] text-slate-500 mt-0.5">AI-powered travel assistant. Ask me anything.</p>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {!wizardStarted ? (
              <div className="flex flex-col items-center justify-center h-full text-center px-4">
                <div className="bg-gradient-to-br from-indigo-500 to-purple-600 rounded-full p-4 mb-4"><Sparkles className="w-8 h-8 text-white" /></div>
                <h3 className="text-lg font-bold text-slate-800 mb-2">Plan Your Dream Trip</h3>
                <p className="text-xs text-slate-500 mb-5">Finn will guide you step by step — destination, flights, hotels, activities, and booking.</p>
                <button onClick={startWizard} className="bg-gradient-to-r from-indigo-500 to-purple-600 text-white px-6 py-3 rounded-full text-sm font-semibold hover:shadow-lg transition-all hover:scale-105">✈️ Start Planning My Trip</button>
              </div>
            ) : (
              <>
                {messages.map((msg, i) => (
                  <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[85%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${msg.role === "user" ? "bg-indigo-500 text-white rounded-br-md" : "bg-slate-100 text-slate-800 rounded-bl-md"}`}>
                      {msg.role === "assistant" && <div className="text-[10px] font-semibold text-slate-500 mb-1">Finn</div>}
                      <div className="whitespace-pre-wrap">{msg.content}</div>
                    </div>
                  </div>
                ))}
                {isLoading && <div className="flex items-center gap-2 text-slate-400 text-xs"><Loader2 className="w-3 h-3 animate-spin" /> Finn is thinking...</div>}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>
          <div className="p-4 border-t border-slate-100 flex gap-2">
            <input type="text" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === "Enter" && sendMessage()}
              placeholder="Plan my trip..." className="flex-1 px-4 py-2.5 border-2 border-slate-200 rounded-xl text-sm focus:outline-none focus:border-indigo-400" />
            <button onClick={sendMessage} disabled={isLoading || !input.trim()} className="p-2.5 bg-indigo-500 text-white rounded-xl hover:bg-indigo-600 disabled:opacity-40 transition-colors"><Send className="w-4 h-4" /></button>
          </div>
        </div>
      </div>
    </main>
  );
}

function Tag({ children }: { children: ReactNode }) {
  if (children == null || children === "") return null;
  return <span className="text-[10px] px-2 py-0.5 bg-slate-100 border border-slate-200 rounded text-slate-600">{children}</span>;
}

function Price({ children }: { children: ReactNode }) {
  return <span className="text-[10px] px-2 py-0.5 bg-emerald-50 border border-emerald-200 rounded text-emerald-700 font-medium">{children}</span>;
}

function ResultCard({ tab, r }: { tab: Tab; r: Row }) {
  if (tab === "Destinations") {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-5 hover:border-indigo-200 hover:shadow-md transition-all">
        <div className="flex items-start justify-between">
          <h4 className="font-bold text-slate-900 mb-1.5 flex items-center gap-1.5"><MapPin className="w-4 h-4 text-indigo-500" />{r.title}</h4>
          {r.score != null && <span className="text-[10px] px-2 py-0.5 bg-emerald-50 border border-emerald-200 rounded text-emerald-700 font-medium">{r.score}</span>}
        </div>
        <p className="text-xs text-slate-500 leading-relaxed mb-3 line-clamp-3">{r.snippet}</p>
        <div className="flex gap-2 flex-wrap"><Tag>{r.country}</Tag><Tag>{r.climate}</Tag><Tag>{r.season}</Tag></div>
      </div>
    );
  }
  if (tab === "Flights") {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-5 hover:border-indigo-200 hover:shadow-md transition-all">
        <div className="flex items-start justify-between">
          <h4 className="font-bold text-slate-900 mb-1.5 flex items-center gap-1.5"><Plane className="w-4 h-4 text-indigo-500" />{r.airline} {r.flightNumber}</h4>
          {r.price != null && <Price>${r.price}</Price>}
        </div>
        <p className="text-xs text-slate-500 mb-3">{r.origin} → {r.destination}</p>
        <div className="flex gap-2 flex-wrap"><Tag>{r.departDate}</Tag><Tag>{r.seats} seats</Tag></div>
      </div>
    );
  }
  if (tab === "Hotels") {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-5 hover:border-indigo-200 hover:shadow-md transition-all">
        <div className="flex items-start justify-between">
          <h4 className="font-bold text-slate-900 mb-1.5 flex items-center gap-1.5"><Hotel className="w-4 h-4 text-indigo-500" />{r.name}</h4>
          {r.price != null && <Price>${r.price}/night</Price>}
        </div>
        <p className="text-xs text-slate-500 mb-3">{r.city}{r.country ? `, ${r.country}` : ""}</p>
        <div className="flex gap-2 flex-wrap"><Tag>{"★".repeat(r.stars || 0)}</Tag><Tag>{r.review != null ? `${r.review} review` : null}</Tag></div>
      </div>
    );
  }
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 hover:border-indigo-200 hover:shadow-md transition-all">
      <div className="flex items-start justify-between">
        <h4 className="font-bold text-slate-900 mb-1.5 flex items-center gap-1.5"><Ticket className="w-4 h-4 text-indigo-500" />{r.name}</h4>
        {r.price != null && <Price>${r.price}</Price>}
      </div>
      <p className="text-xs text-slate-500 mb-3">{r.city}{r.country ? `, ${r.country}` : ""}</p>
      <div className="flex gap-2 flex-wrap"><Tag>{r.difficulty}</Tag><Tag>{r.duration != null ? `${r.duration}h` : null}</Tag></div>
    </div>
  );
}
