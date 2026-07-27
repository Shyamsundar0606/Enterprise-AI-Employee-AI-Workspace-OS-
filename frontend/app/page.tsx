"use client";

import { useEffect, useMemo, useState } from "react";

interface Conversation {
  id: string;
  title: string;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

interface MessageItem {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  metadata?: Record<string, unknown> | null;
  token_count?: number | null;
  created_at: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function formatTime(value: string) {
  return new Date(value).toLocaleString();
}

function getAuthHeaders() {
  if (typeof window === "undefined") {
    return {};
  }
  const token = localStorage.getItem("access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function HomePage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [draft, setDraft] = useState("");
  const [title, setTitle] = useState("New conversation");
  const [authReady, setAuthReady] = useState(false);

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === activeConversationId) ?? null,
    [activeConversationId, conversations],
  );

  useEffect(() => {
    const register = async () => {
      const response = await fetch(`${API_BASE}/api/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: `demo${Date.now()}@example.com`,
          username: `demo${Date.now()}`,
          password: "secret123",
        }),
      });
      if (response.ok) {
        const payload = await response.json();
        localStorage.setItem("access_token", payload.access_token);
        localStorage.setItem("refresh_token", payload.refresh_token);
      }
      setAuthReady(true);
    };

    register();
  }, []);

  useEffect(() => {
    if (!authReady) {
      return;
    }
    const loadConversations = async () => {
      const response = await fetch(`${API_BASE}/api/v1/chat/conversations`, { headers: getAuthHeaders() });
      if (response.ok) {
        const payload = await response.json();
        setConversations(payload.items);
        if (!activeConversationId && payload.items.length > 0) {
          setActiveConversationId(payload.items[0].id);
        }
      }
    };

    loadConversations();
  }, [activeConversationId, authReady]);

  useEffect(() => {
    if (!activeConversationId || !authReady) {
      return;
    }
    const loadMessages = async () => {
      const response = await fetch(`${API_BASE}/api/v1/chat/messages/${activeConversationId}`, {
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        const payload = await response.json();
        setMessages(payload.items);
      }
    };

    loadMessages();
  }, [activeConversationId, authReady]);

  const createConversation = async () => {
    if (!title.trim()) {
      return;
    }
    const response = await fetch(`${API_BASE}/api/v1/chat/conversations`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify({ title: title.trim() }),
    });
    if (response.ok) {
      const conversation = await response.json();
      setConversations((current) => [conversation, ...current]);
      setActiveConversationId(conversation.id);
      setTitle("New conversation");
    }
  };

  const renameConversation = async (conversationId: string, nextTitle: string) => {
    const response = await fetch(`${API_BASE}/api/v1/chat/conversations/${conversationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify({ title: nextTitle }),
    });
    if (response.ok) {
      const updated = await response.json();
      setConversations((current) => current.map((conversation) => (conversation.id === conversationId ? updated : conversation)));
    }
  };

  const deleteConversation = async (conversationId: string) => {
    const response = await fetch(`${API_BASE}/api/v1/chat/conversations/${conversationId}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });
    if (response.ok) {
      setConversations((current) => current.filter((conversation) => conversation.id !== conversationId));
      if (activeConversationId === conversationId) {
        setActiveConversationId(null);
        setMessages([]);
      }
    }
  };

  const sendMessage = async () => {
    if (!draft.trim() || !activeConversationId) {
      return;
    }
    const content = draft.trim();
    setDraft("");
    const response = await fetch(`${API_BASE}/api/v1/chat/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify({
        conversation_id: activeConversationId,
        role: "user",
        content,
        metadata: { source: "web" },
        token_count: content.split(/\s+/).length,
      }),
    });
    if (response.ok) {
      const message = await response.json();
      setMessages((current) => [...current, message]);
    }
  };

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col p-4 md:flex-row md:gap-4 md:p-6">
        <aside className="w-full rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4 md:w-80">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">Chat workspace</p>
              <h2 className="text-lg font-semibold">Conversations</h2>
            </div>
          </div>
          <div className="mb-4 space-y-2">
            <input
              className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
              placeholder="New conversation title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && createConversation()}
            />
            <button className="w-full rounded-xl bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900" onClick={createConversation}>
              New conversation
            </button>
          </div>
          <div className="space-y-2">
            {conversations.map((conversation) => (
              <div key={conversation.id} className="rounded-xl border border-zinc-800 p-3">
                <div className="flex items-center justify-between gap-2">
                  <button className="truncate text-left text-sm font-medium" onClick={() => setActiveConversationId(conversation.id)}>
                    {conversation.title}
                  </button>
                  <button className="text-xs text-zinc-500" onClick={() => renameConversation(conversation.id, `${conversation.title} (renamed)`)}>
                    Rename
                  </button>
                </div>
                <div className="mt-2 flex items-center justify-between text-xs text-zinc-500">
                  <span>{formatTime(conversation.updated_at)}</span>
                  <button className="text-red-400" onClick={() => deleteConversation(conversation.id)}>
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </aside>

        <section className="mt-4 flex min-h-[60vh] flex-1 flex-col rounded-2xl border border-zinc-800 bg-zinc-900/70 md:mt-0">
          <div className="border-b border-zinc-800 px-4 py-4">
            <h3 className="text-lg font-semibold">{activeConversation?.title ?? "Select a conversation"}</h3>
            <p className="text-sm text-zinc-500">Responsive chat workspace with persistence and websocket-ready messaging.</p>
          </div>
          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {messages.map((message) => (
              <div key={message.id} className={`rounded-2xl px-4 py-3 ${message.role === "user" ? "ml-auto max-w-[80%] bg-zinc-100 text-zinc-900" : "mr-auto max-w-[80%] bg-zinc-800 text-zinc-100"}`}>
                <div className="mb-1 text-xs uppercase tracking-[0.2em] opacity-70">{message.role}</div>
                <div className="whitespace-pre-wrap text-sm">{message.content}</div>
              </div>
            ))}
          </div>
          <div className="border-t border-zinc-800 p-4">
            <textarea
              className="min-h-[96px] w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-3 text-sm"
              placeholder="Type your message"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
            />
            <div className="mt-3 flex justify-end">
              <button className="rounded-xl bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-900" onClick={sendMessage}>
                Send message
              </button>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
