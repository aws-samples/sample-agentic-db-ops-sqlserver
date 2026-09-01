import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ReefShark Adventures - Navigate Smarter. Dive Deeper.",
  description: "AI-powered travel planning with agentic search and booking",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased bg-slate-50">
        {children}
      </body>
    </html>
  );
}
