"use client";

import { useState, useRef, useEffect, type ReactNode } from "react";
import { Send, Sparkles, Loader2, Search, Plane, Hotel, MapPin, Ticket, Calendar, Star, Clock, Briefcase, Trash2, Plus } from "lucide-react";
import Header from "./components/Header";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/app";

type Tab = "Destinations" | "Flights" | "Hotels" | "Activities" | "Plan Trip";
type Component = "Flights" | "Hotels" | "Activities";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;
interface TripItem { id: number; type: Component; data: Row; }

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("Destinations");
  const [wizardStarted, setWizardStarted] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Search inputs (shared across the standalone tabs and the Plan Trip tab)
  const [destQ, setDestQ] = useState("tropical beach");
  const [flightFrom, setFlightFrom] = useState("");
  const [flightTo, setFlightTo] = useState("");
  const [flightDate, setFlightDate] = useState("");
  const [flightReturn, setFlightReturn] = useState("");
  const [hotelDest, setHotelDest] = useState("");
  const [hotelCheckin, setHotelCheckin] = useState("");
  const [hotelCheckout, setHotelCheckout] = useState("");
  const [actQ, setActQ] = useState("");

  // Plan Trip state
  const [tripComponent, setTripComponent] = useState<Component>("Flights");
  const [trip, setTrip] = useState<TripItem[]>([]);

  // Results
  const [results, setResults] = useState<Row[]>([]);
  const [meta, setMeta] = useState<{ count: number; ms?: number; source?: string }>({ count: 0 });
  const [searching, setSearching] = useState(false);
  const [searchErr, setSearchErr] = useState<string | null>(null);

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  useEffect(() => { scrollToBottom(); }, [messages]);

  async function runSearch(kind: Exclude<Tab, "Plan Trip">) {
    setSearching(true);
    setSearchErr(null);
    try {
      let url = "";
      if (kind === "Destinations") {
        url = `${API_BASE}/api/search?q=${encodeURIComponent(destQ)}&topk=8`;
      } else if (kind === "Flights") {
        url = `${API_BASE}/api/flights?origin=${encodeURIComponent(flightFrom)}&destination=${encodeURIComponent(flightTo)}&date=${encodeURIComponent(flightDate)}&return_date=${encodeURIComponent(flightReturn)}&topk=8`;
      } else if (kind === "Hotels") {
        url = `${API_BASE}/api/hotels?destination=${encodeURIComponent(hotelDest)}&checkin=${encodeURIComponent(hotelCheckin)}&checkout=${encodeURIComponent(hotelCheckout)}&topk=8`;
      } else {
        url = `${API_BASE}/api/activities?q=${encodeURIComponent(actQ)}&topk=8`;
      }

      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setResults(data.results || []);
      setMeta({ count: data.count ?? (data.results || []).length, ms: data.latency_ms, source: data.source });
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

  function switchComponent(c: Component) {
    setTripComponent(c);
    setResults([]);
    setMeta({ count: 0 });
    setSearchErr(null);
  }

  function addToTrip(type: Component, data: Row) {
    setTrip(prev => [...prev, { id: Date.now() + Math.random(), type, data }]);
  }
  function removeFromTrip(id: number) {
    setTrip(prev => prev.filter(i => i.id !== id));
  }
  function itemPrice(i: TripItem): number {
    if (i.type === "Hotels") return Number(i.data.total ?? i.data.price ?? 0);
    return Number(i.data.price ?? 0);
  }
  const tripTotal = Math.round(trip.reduce((s, i) => s + itemPrice(i), 0) * 100) / 100;

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
      setMessages(prev => [...prev, { role: "assistant", content: "\u26a0\ufe0f Backend not connected." }]);
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
      setMessages(prev => [...prev, { role: "assistant", content: "\u26a0\ufe0f Backend not connected." }]);
    } finally { setIsLoading(false); }
  }

  const inputCls = "w-full pl-11 pr-4 py-3 border-2 border-slate-200 rounded-xl text-sm focus:outline-none focus:border-indigo-400 transition-colors";
  const plainInput = "flex-1 px-4 py-3 border-2 border-slate-200 rounded-xl text-sm focus:outline-none focus:border-indigo-400";
  const dateInput = "px-4 py-3 border-2 border-slate-200 rounded-xl text-sm text-slate-600 focus:outline-none focus:border-indigo-400";
  const btnCls = "px-6 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-xl text-sm font-semibold hover:shadow-lg transition-all disabled:opacity-50";

  const inTrip = activeTab === "Plan Trip";
  const cardKind: Exclude<Tab, "Plan Trip"> = inTrip ? tripComponent : (activeTab as Exclude<Tab, "Plan Trip">);

  // The search form for a given component (reused by standalone tabs + Plan Trip).
  function FlightsForm() {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex flex-col sm:flex-row gap-3">
          <input type="text" value={flightFrom} onChange={e => setFlightFrom(e.target.value)}
            onKeyDown={e => e.key === "Enter" && runSearch("Flights")}
            placeholder="From (e.g. Sydney)" className={plainInput} />
          <input type="text" value={flightTo} onChange={e => setFlightTo(e.target.value)}
            onKeyDown={e => e.key === "Enter" && runSearch("Flights")}
            placeholder="To (e.g. Tokyo)" className={plainInput} />
        </div>
        <div className="flex flex-col sm:flex-row gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-500">
            <Calendar className="w-4 h-4 text-slate-400" /> Departure
            <input type="date" value={flightDate} onChange={e => setFlightDate(e.target.value)} className={dateInput} />
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-500">
            Return
            <input type="date" value={flightReturn} min={flightDate || undefined} onChange={e => setFlightReturn(e.target.value)} className={dateInput} />
          </label>
          <button onClick={() => runSearch("Flights")} disabled={searching} className={`${btnCls} sm:ml-auto`}>Search flights</button>
        </div>
      </div>
    );
  }
  function HotelsForm() {
    return (
      <div className="flex flex-col gap-3">
        <div className="relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input type="text" value={hotelDest} onChange={e => setHotelDest(e.target.value)}
            onKeyDown={e => e.key === "Enter" && runSearch("Hotels")}
            placeholder="City or amenity (e.g. Bali, Paris, beachfront, spa)" className={inputCls} />
        </div>
        <div className="flex flex-col sm:flex-row gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-500">
            <Calendar className="w-4 h-4 text-slate-400" /> Check-in
            <input type="date" value={hotelCheckin} onChange={e => setHotelCheckin(e.target.value)} className={dateInput} />
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-500">
            Check-out
            <input type="date" value={hotelCheckout} onChange={e => setHotelCheckout(e.target.value)} className={dateInput} />
          </label>
          <button onClick={() => runSearch("Hotels")} disabled={searching} className={`${btnCls} sm:ml-auto`}>Search hotels</button>
        </div>
      </div>
    );
  }
  function ActivitiesForm() {
    return (
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input type="text" value={actQ} onChange={e => setActQ(e.target.value)}
            onKeyDown={e => e.key === "Enter" && runSearch("Activities")}
            placeholder="Try: diving, hiking, cooking, wine, safari, museum..." className={inputCls} />
        </div>
        <button onClick={() => runSearch("Activities")} disabled={searching} className={btnCls}>Search</button>
      </div>
    );
  }

  return (
    <main className="min-h-screen flex flex-col">
      <Header />
      <div className="flex-1 flex flex-col lg:grid lg:grid-cols-[1fr_380px] min-h-0 overflow-hidden">
        {/* Left: Search */}
        <div className="flex-1 p-4 sm:p-6 lg:p-8 overflow-y-auto">
          <h2 className="text-xl sm:text-3xl font-extrabold text-slate-900 tracking-tight mb-1">Where to next?</h2>
          <p className="text-slate-500 text-sm mb-6">
            Search live travel inventory &mdash; destinations, flights, hotels &amp; activities &mdash; powered by full-text search over TravelHub on RDS SQL Server.
          </p>

          {/* Tabs */}
          <div className="flex gap-0 border-b-2 border-slate-200 mb-5 overflow-x-auto">
            {(["Destinations", "Flights", "Hotels", "Activities", "Plan Trip"] as Tab[]).map(tab => (
              <button key={tab} onClick={() => switchTab(tab)}
                className={`px-5 py-2.5 text-sm font-semibold border-b-2 -mb-[2px] whitespace-nowrap transition-colors ${activeTab === tab ? "border-indigo-500 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-700"} ${tab === "Plan Trip" ? "flex items-center gap-1.5" : ""}`}>
                {tab === "Plan Trip" && <Briefcase className="w-4 h-4" />}
                {tab === "Plan Trip" && trip.length > 0 ? `Plan Trip (${trip.length})` : tab}
              </button>
            ))}
          </div>

          {/* Plan Trip: component selector */}
          {inTrip && (
            <div className="flex gap-2 mb-4">
              {(["Flights", "Hotels", "Activities"] as Component[]).map(c => (
                <button key={c} onClick={() => switchComponent(c)}
                  className={`px-4 py-2 text-xs font-semibold rounded-lg border transition-colors flex items-center gap-1.5 ${tripComponent === c ? "bg-indigo-500 text-white border-indigo-500" : "bg-white text-slate-600 border-slate-200 hover:border-indigo-300"}`}>
                  {c === "Flights" ? <Plane className="w-3.5 h-3.5" /> : c === "Hotels" ? <Hotel className="w-3.5 h-3.5" /> : <Ticket className="w-3.5 h-3.5" />}
                  {c}
                </button>
              ))}
            </div>
          )}

          {/* Search bar */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 mb-6 space-y-3">
            {(activeTab === "Destinations") && (
              <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1">
                  <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <input type="text" value={destQ} onChange={e => setDestQ(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && runSearch("Destinations")}
                    placeholder="Try: beach, skiing, northern lights, temples, wine, safari..." className={inputCls} />
                </div>
                <button onClick={() => runSearch("Destinations")} disabled={searching} className={btnCls}>Search</button>
              </div>
            )}
            {cardKind === "Flights" && activeTab !== "Destinations" && FlightsForm()}
            {cardKind === "Hotels" && activeTab !== "Destinations" && HotelsForm()}
            {cardKind === "Activities" && activeTab !== "Destinations" && ActivitiesForm()}

            <div className="flex items-center gap-2 text-[11px] text-slate-500">
              {searching ? <><Loader2 className="w-3 h-3 animate-spin" /> Searching...</>
                : searchErr ? <span className="text-red-500">Error: {searchErr}</span>
                : <span>{meta.count} results{meta.ms != null ? ` \u00b7 ${meta.ms}ms` : ""}{meta.source ? ` \u00b7 ${meta.source}` : ""}</span>}
            </div>
          </div>

          {/* Plan Trip: current itinerary */}
          {inTrip && <TripCart items={trip} total={tripTotal} onRemove={removeFromTrip} onClear={() => setTrip([])} />}

          {/* Results */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {results.map((r, i) => (
              <ResultCard key={i} tab={cardKind} r={r}
                onAdd={inTrip ? () => addToTrip(tripComponent, r) : undefined} />
            ))}
            {!searching && results.length === 0 && !searchErr && (
              <div className="text-sm text-slate-400">No results &mdash; try a different search.</div>
            )}
          </div>
        </div>

        {/* Right: Chat */}
        <div className="bg-white border-t lg:border-t-0 lg:border-l border-slate-200 flex flex-col h-[300px] lg:h-auto">
          <div className="p-4 border-b border-slate-100">
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" /> Finn &mdash; Trip Planner
            </h3>
            <p className="text-[11px] text-slate-500 mt-0.5">AI-powered travel assistant. Ask me anything.</p>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {!wizardStarted ? (
              <div className="flex flex-col items-center justify-center h-full text-center px-4">
                <div className="bg-gradient-to-br from-indigo-500 to-purple-600 rounded-full p-4 mb-4"><Sparkles className="w-8 h-8 text-white" /></div>
                <h3 className="text-lg font-bold text-slate-800 mb-2">Plan Your Dream Trip</h3>
                <p className="text-xs text-slate-500 mb-5">Finn will guide you step by step &mdash; destination, flights, hotels, activities, and booking.</p>
                <button onClick={startWizard} className="bg-gradient-to-r from-indigo-500 to-purple-600 text-white px-6 py-3 rounded-full text-sm font-semibold hover:shadow-lg transition-all hover:scale-105">{"\u2708\ufe0f"} Start Planning My Trip</button>
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

function TagList({ tags, max = 4 }: { tags?: string; max?: number }) {
  if (!tags) return null;
  const items = tags.split(",").map(t => t.trim()).filter(Boolean).slice(0, max);
  return <div className="flex gap-1.5 flex-wrap mt-2">{items.map((t, i) => <Tag key={i}>{t}</Tag>)}</div>;
}

function ResultCard({ tab, r, onAdd }: { tab: Exclude<Tab, "Plan Trip">; r: Row; onAdd?: () => void }) {
  let body: ReactNode;
  if (tab === "Destinations") {
    body = (
      <>
        <div className="flex items-start justify-between">
          <h4 className="font-bold text-slate-900 mb-1.5 flex items-center gap-1.5"><MapPin className="w-4 h-4 text-indigo-500" />{r.title}{r.country ? `, ${r.country}` : ""}</h4>
          {r.score != null && <Tag>{`Popularity ${r.score}`}</Tag>}
        </div>
        <p className="text-xs text-slate-500 leading-relaxed mb-1 line-clamp-3">{r.snippet}</p>
        <div className="flex gap-1.5 flex-wrap mt-2"><Tag>{r.climate}</Tag><Tag>{r.season}</Tag><Tag>{r.continent}</Tag></div>
        <TagList tags={r.tags} />
      </>
    );
  } else if (tab === "Flights") {
    body = (
      <>
        {r.leg && <span className={`inline-block text-[9px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded mb-2 ${r.leg === "Return" ? "bg-emerald-100 text-emerald-700" : "bg-indigo-100 text-indigo-700"}`}>{r.leg}</span>}
        <div className="flex items-start justify-between">
          <h4 className="font-bold text-slate-900 mb-1.5 flex items-center gap-1.5"><Plane className="w-4 h-4 text-indigo-500" />{r.airline} {r.flightNumber}</h4>
          {r.price != null && <Price>${r.price}</Price>}
        </div>
        <p className="text-sm text-slate-700 font-medium mb-1">{r.origin} &rarr; {r.destination}</p>
        <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
          <Calendar className="w-3 h-3" />{r.departDate}
          {r.departTime && <><Clock className="w-3 h-3 ml-1" />{r.departTime}{r.arriveTime ? ` - ${r.arriveTime}` : ""}</>}
        </div>
        <div className="flex gap-1.5 flex-wrap"><Tag>{r.aircraft}</Tag><Tag>{r.seats != null ? `${r.seats} seats left` : null}</Tag>{r.durationMinutes != null && <Tag>{`${Math.floor(r.durationMinutes/60)}h ${r.durationMinutes%60}m`}</Tag>}</div>
      </>
    );
  } else if (tab === "Hotels") {
    body = (
      <>
        <div className="flex items-start justify-between">
          <h4 className="font-bold text-slate-900 mb-1.5 flex items-center gap-1.5"><Hotel className="w-4 h-4 text-indigo-500" />{r.name}</h4>
          {r.price != null && <Price>${r.price}/night</Price>}
        </div>
        <p className="text-xs text-slate-500 mb-1">{r.city}{r.country ? `, ${r.country}` : ""}</p>
        <div className="flex items-center gap-2 mb-1">
          <span className="text-amber-500 text-xs flex items-center">{"\u2605".repeat(r.stars || 0)}<span className="text-slate-300">{"\u2605".repeat(Math.max(0, 5 - (r.stars || 0)))}</span></span>
          {r.review != null && <span className="text-[11px] text-slate-500 flex items-center gap-0.5"><Star className="w-3 h-3 text-emerald-500" />{r.review}/5</span>}
        </div>
        {r.nights != null && (
          <p className="text-xs text-slate-600 font-medium mb-1">
            {r.nights} night{r.nights === 1 ? "" : "s"}{r.total != null ? ` \u00b7 $${r.total} total` : ""}
            {r.checkin ? ` \u00b7 ${r.checkin} \u2192 ${r.checkout}` : ""}
          </p>
        )}
        <TagList tags={r.amenities} max={5} />
      </>
    );
  } else {
    body = (
      <>
        <div className="flex items-start justify-between">
          <h4 className="font-bold text-slate-900 mb-1.5 flex items-center gap-1.5"><Ticket className="w-4 h-4 text-indigo-500" />{r.name}</h4>
          {r.price != null && <Price>${r.price}</Price>}
        </div>
        <p className="text-xs text-slate-500 mb-1">{r.city}{r.country ? `, ${r.country}` : ""}</p>
        <div className="flex gap-1.5 flex-wrap"><Tag>{r.difficulty}</Tag><Tag>{r.duration != null ? `${r.duration}h` : null}</Tag></div>
        <TagList tags={r.tags} />
      </>
    );
  }
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 hover:border-indigo-200 hover:shadow-md transition-all flex flex-col">
      <div className="flex-1">{body}</div>
      {onAdd && (
        <button onClick={onAdd}
          className="mt-3 w-full py-2 text-xs font-semibold rounded-lg bg-indigo-50 text-indigo-700 border border-indigo-200 hover:bg-indigo-100 transition-colors flex items-center justify-center gap-1.5">
          <Plus className="w-3.5 h-3.5" /> Add to trip
        </button>
      )}
    </div>
  );
}

function tripItemLabel(i: TripItem): string {
  const d = i.data;
  if (i.type === "Flights") return `${d.airline} ${d.flightNumber}: ${d.origin} \u2192 ${d.destination}${d.departDate ? ` (${d.departDate})` : ""}`;
  if (i.type === "Hotels") return `${d.name}${d.nights ? ` \u00b7 ${d.nights} night${d.nights === 1 ? "" : "s"}` : ""}`;
  return `${d.name}${d.city ? ` in ${d.city}` : ""}`;
}

function TripCart({ items, total, onRemove, onClear }:
  { items: TripItem[]; total: number; onRemove: (id: number) => void; onClear: () => void }) {
  const icon = (t: Component) => t === "Flights" ? <Plane className="w-3.5 h-3.5 text-indigo-500" />
    : t === "Hotels" ? <Hotel className="w-3.5 h-3.5 text-indigo-500" />
    : <Ticket className="w-3.5 h-3.5 text-indigo-500" />;
  const price = (i: TripItem) => i.type === "Hotels" ? Number(i.data.total ?? i.data.price ?? 0) : Number(i.data.price ?? 0);
  return (
    <div className="bg-gradient-to-br from-indigo-50 to-purple-50 border border-indigo-200 rounded-xl p-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5"><Briefcase className="w-4 h-4 text-indigo-600" /> Your Trip</h3>
        {items.length > 0 && (
          <button onClick={onClear} className="text-[11px] text-slate-500 hover:text-red-500 transition-colors">Clear all</button>
        )}
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-slate-500">No items yet &mdash; search for flights, hotels or activities and click <span className="font-semibold">Add to trip</span> to build your itinerary.</p>
      ) : (
        <>
          <ul className="space-y-2">
            {items.map(i => (
              <li key={i.id} className="flex items-center gap-2 bg-white rounded-lg border border-slate-200 px-3 py-2">
                {icon(i.type)}
                <span className="flex-1 text-xs text-slate-700 truncate">{tripItemLabel(i)}</span>
                <span className="text-xs font-semibold text-emerald-700">${price(i).toFixed(2)}</span>
                <button onClick={() => onRemove(i.id)} className="text-slate-400 hover:text-red-500 transition-colors" aria-label="Remove">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </li>
            ))}
          </ul>
          <div className="flex items-center justify-between mt-3 pt-3 border-t border-indigo-200">
            <span className="text-xs text-slate-500">{items.length} item{items.length === 1 ? "" : "s"} &middot; flights, hotels &amp; activities</span>
            <span className="text-sm font-extrabold text-slate-900">Total ${total.toFixed(2)}</span>
          </div>
        </>
      )}
    </div>
  );
}
