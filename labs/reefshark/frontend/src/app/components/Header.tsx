"use client";

import Link from "next/link";
import { Sparkles, Server, Zap } from "lucide-react";

export default function Header() {
  return (
    <header className="bg-white border-b border-slate-200 px-4 sm:px-6 py-3 flex items-center justify-between sticky top-0 z-50">
      <Link href="/" className="flex items-center gap-3">
        <div className="bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl p-2">
          <Sparkles className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-lg font-bold text-slate-900 tracking-tight">ReefShark Adventures</h1>
          <p className="text-xs text-slate-500 hidden sm:block">Navigate smarter. Dive deeper.</p>
        </div>
      </Link>
      <div className="flex gap-2 text-[10px] sm:text-xs">
        <Link href="/sre" className="px-2 sm:px-3 py-1.5 text-[10px] sm:text-xs font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-600 rounded-lg hover:shadow-md transition-all">
          <Server className="w-3 h-3 inline mr-1" />SRE Dashboard
        </Link>
        <Link href="/search" className="px-2 sm:px-3 py-1.5 text-[10px] sm:text-xs font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-600 rounded-lg hover:shadow-md transition-all">
          <Zap className="w-3 h-3 inline mr-1" />Agentic Search
        </Link>
      </div>
    </header>
  );
}
