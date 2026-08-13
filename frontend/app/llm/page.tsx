"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export default function LLMPage() {
  const [provider, setProvider] = useState("ollama");
  const [model, setModel] = useState("qwen3");
  const [health, setHealth] = useState<{ provider: string; model: string; status: string; detail?: string | null } | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [draft, setDraft] = useState("Hello from the LLM layer");
  const [streamed, setStreamed] = useState("");

  useEffect(() => {
    const load = async () => {
      const healthResponse = await fetch(`${API_BASE}/llm/health`);
      if (healthResponse.ok) {
        const payload = await healthResponse.json();
        setHealth(payload);
        setProvider(payload.provider);
        setModel(payload.model || "qwen3");
      }
      const modelsResponse = await fetch(`${API_BASE}/llm/models`);
      if (modelsResponse.ok) {
        const payload = await modelsResponse.json();
        setModels(payload.models.map((item: { name: string }) => item.name));
      }
    };

    load();
  }, []);

  const runStream = async () => {
    setStreamed("");
    const response = await fetch(`${API_BASE}/agents/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", accept: "text/event-stream" },
      body: JSON.stringify({ conversation_id: "frontend-demo", user_message: draft }),
    });
    const text = await response.text();
    setStreamed(text.replace(/data: /g, "").replace(/\n\n/g, ""));
  };

  return (
    <main className="min-h-screen bg-zinc-950 px-6 py-10 text-zinc-100">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-6">
          <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">LLM Provider Layer</p>
          <h1 className="mt-2 text-3xl font-semibold">Settings and streaming demo</h1>
          <p className="mt-2 text-sm text-zinc-400">Switch providers, inspect models, and demo streamed responses through one interface.</p>
        </header>

        <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
          <section className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-6">
            <h2 className="text-xl font-semibold">Provider settings</h2>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <label className="text-sm">
                <span className="mb-2 block text-zinc-400">Provider</span>
                <select className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2" value={provider} onChange={(event) => setProvider(event.target.value)}>
                  <option value="ollama">Ollama</option>
                  <option value="openai">OpenAI</option>
                  <option value="gemini">Gemini</option>
                </select>
              </label>
              <label className="text-sm">
                <span className="mb-2 block text-zinc-400">Current model</span>
                <input className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2" value={model} onChange={(event) => setModel(event.target.value)} />
              </label>
              <label className="text-sm">
                <span className="mb-2 block text-zinc-400">Temperature</span>
                <input className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2" type="range" min="0" max="1" step="0.1" defaultValue="0.7" />
              </label>
              <label className="text-sm">
                <span className="mb-2 block text-zinc-400">Max tokens</span>
                <input className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2" type="number" defaultValue="512" />
              </label>
            </div>
            <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-950/70 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-zinc-400">Health</p>
                  <p className="text-lg font-medium">{health?.status ?? "unknown"}</p>
                </div>
                <div className={`rounded-full px-3 py-1 text-sm ${health?.status === "ok" ? "bg-emerald-500/15 text-emerald-400" : "bg-amber-500/15 text-amber-400"}`}>
                  {health?.provider ?? "unknown"}
                </div>
              </div>
              <p className="mt-3 text-sm text-zinc-500">{health?.detail ?? "No health detail available yet."}</p>
            </div>
          </section>

          <section className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-6">
            <h2 className="text-xl font-semibold">Installed models</h2>
            <div className="mt-4 space-y-2">
              {models.map((item) => (
                <div key={item} className="rounded-xl border border-zinc-800 bg-zinc-950/70 px-3 py-2 text-sm">
                  {item}
                </div>
              ))}
            </div>
          </section>
        </div>

        <section className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-6">
          <h2 className="text-xl font-semibold">Streaming demo</h2>
          <textarea className="mt-4 min-h-[96px] w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-3 text-sm" value={draft} onChange={(event) => setDraft(event.target.value)} />
          <div className="mt-4 flex justify-end">
            <button className="rounded-xl bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-900" onClick={runStream}>Run stream</button>
          </div>
          <div className="mt-4 rounded-2xl border border-zinc-800 bg-zinc-950/70 p-4 text-sm text-zinc-300">{streamed || "No stream output yet."}</div>
        </section>
      </div>
    </main>
  );
}
