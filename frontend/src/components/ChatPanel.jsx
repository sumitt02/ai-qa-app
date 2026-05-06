import { useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";
import { formatTime } from "../api/format.js";

export default function ChatPanel({ file, onPlayAt }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [streamMode, setStreamMode] = useState(true);
  const scrollRef = useRef(null);

  // Reset when file changes
  useEffect(() => {
    setMessages([]);
    setSessionId(null);
  }, [file?.id]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  if (!file) {
    return (
      <div className="h-full grid place-items-center text-center text-slate-500 px-6">
        <div>
          <div className="text-5xl mb-3">💬</div>
          <div className="text-sm">Select a file from the left to start asking questions.</div>
        </div>
      </div>
    );
  }

  if (file.status !== "ready") {
    return (
      <div className="h-full grid place-items-center text-center text-slate-500 px-6">
        <div>
          <div className="text-3xl mb-3">⏳</div>
          <div className="text-sm">
            File is <span className="font-medium">{file.status}</span>. Chat will be available
            once processing finishes.
          </div>
          {file.error_message && (
            <div className="text-xs text-red-600 mt-2">{file.error_message}</div>
          )}
        </div>
      </div>
    );
  }

  const send = async () => {
    const q = input.trim();
    if (!q || busy) return;

    const userMsg = { role: "user", content: q, citations: [] };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setBusy(true);

    if (!streamMode) {
      try {
        const res = await api.ask(q, file.id, sessionId);
        setMessages((m) => [
          ...m,
          { role: "assistant", content: res.content, citations: res.citations },
        ]);
        // First response — sessionId is set on backend; refetch sessions to get it
        if (!sessionId) {
          const sessions = await api.listSessions();
          if (sessions.length > 0) setSessionId(sessions[0].id);
        }
      } catch (e) {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: `Error: ${e.message}`, citations: [] },
        ]);
      } finally {
        setBusy(false);
      }
      return;
    }

    // Streaming mode
    const placeholder = { role: "assistant", content: "", citations: [], streaming: true };
    setMessages((m) => [...m, placeholder]);
    let citations = [];
    let answer = "";
    try {
      await api.askStream(q, file.id, sessionId, (event, data) => {
        if (event === "session") {
          try {
            const j = JSON.parse(data);
            if (j.session_id) setSessionId(j.session_id);
          } catch {}
        } else if (event === "citations") {
          try {
            citations = JSON.parse(data);
            setMessages((m) => {
              const next = [...m];
              next[next.length - 1] = { ...next[next.length - 1], citations };
              return next;
            });
          } catch {}
        } else if (event === "token") {
          answer += data.replace(/\\n/g, "\n");
          setMessages((m) => {
            const next = [...m];
            next[next.length - 1] = {
              ...next[next.length - 1],
              content: answer,
            };
            return next;
          });
        } else if (event === "done") {
          setMessages((m) => {
            const next = [...m];
            next[next.length - 1] = { ...next[next.length - 1], streaming: false };
            return next;
          });
        }
      });
    } catch (e) {
      setMessages((m) => {
        const next = [...m];
        next[next.length - 1] = {
          role: "assistant",
          content: `Error: ${e.message}`,
          citations: [],
        };
        return next;
      });
    } finally {
      setBusy(false);
    }
  };

  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-sm text-slate-500 mt-8">
            Ask anything about <span className="font-medium">{file.filename}</span>
          </div>
        )}
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} file={file} onPlayAt={onPlayAt} />
        ))}
      </div>

      <div className="border-t border-slate-200 bg-white p-3">
        <div className="flex items-center gap-2 mb-2">
          <label className="text-xs text-slate-500 flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={streamMode}
              onChange={(e) => setStreamMode(e.target.checked)}
            />
            Stream responses
          </label>
        </div>
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            rows={1}
            placeholder="Ask a question..."
            className="flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500 text-sm"
            disabled={busy}
          />
          <button
            onClick={send}
            disabled={busy || !input.trim()}
            className="px-4 py-2 rounded-lg bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50 text-sm font-medium"
          >
            {busy ? "..." : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message, file, onPlayAt }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] ${isUser ? "" : "w-full"}`}>
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap ${
            isUser
              ? "bg-brand-600 text-white"
              : "bg-white border border-slate-200 text-slate-900"
          }`}
        >
          {message.content || (message.streaming ? <span className="loader" /> : "")}
        </div>
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="mt-2 space-y-1.5">
            {message.citations.map((c, i) => {
              const isMedia = c.start != null;
              return (
                <div
                  key={i}
                  className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-xs"
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <div className="font-medium text-slate-700">
                      {isMedia
                        ? `${formatTime(c.start)} – ${formatTime(c.end)}`
                        : c.page != null
                        ? `Page ${c.page}`
                        : "Source"}
                    </div>
                    {isMedia && (file.file_type === "audio" || file.file_type === "video") && (
                      <button
                        onClick={() => onPlayAt?.(c.start)}
                        className="px-2 py-0.5 rounded bg-brand-600 text-white text-[10px] hover:bg-brand-700 transition"
                      >
                        ▶ Play
                      </button>
                    )}
                  </div>
                  <div className="text-slate-600 italic">{c.snippet}</div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
