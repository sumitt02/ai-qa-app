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
        <div className="fade-in">
          <div className="text-5xl mb-3">💬</div>
          <div className="text-base font-medium text-slate-700 mb-1">Pick a file to chat</div>
          <div className="text-sm text-slate-500">Select one from the left to start asking questions</div>
        </div>
      </div>
    );
  }

  if (file.status !== "ready") {
    return (
      <div className="h-full grid place-items-center text-center text-slate-500 px-6">
        <div className="fade-in">
          <div className="text-4xl mb-3">⏳</div>
          <div className="text-sm">
            File is <span className="font-semibold text-slate-700">{file.status}</span>. Chat will be available
            once processing finishes.
          </div>
          {file.error_message && (
            <div className="text-xs text-red-600 mt-2 max-w-md mx-auto">{file.error_message}</div>
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
            next[next.length - 1] = { ...next[next.length - 1], content: answer };
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

  const examples = [
    "What is this about?",
    "Summarize the key points",
    "What are the main topics?",
  ];

  return (
    <div className="h-full flex flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-5 space-y-4">
        {messages.length === 0 && (
          <div className="text-center mt-10 fade-in">
            <div className="text-4xl mb-3">✨</div>
            <div className="text-sm text-slate-700 font-medium mb-1">Ask anything about</div>
            <div className="text-sm text-brand-600 font-semibold mb-6">{file.filename}</div>
            <div className="space-y-1.5 max-w-sm mx-auto">
              <div className="text-[10px] uppercase tracking-widest text-slate-400 font-semibold mb-2">Try these</div>
              {examples.map((e) => (
                <button
                  key={e}
                  onClick={() => setInput(e)}
                  className="block w-full text-sm bg-white hover:bg-brand-50 border border-slate-200 hover:border-brand-300 rounded-lg px-3 py-2 text-slate-700 transition lift-hover text-left"
                >
                  {e}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} file={file} onPlayAt={onPlayAt} />
        ))}
      </div>

      <div className="border-t border-slate-200/80 bg-white/80 backdrop-blur p-3">
        <div className="flex items-center gap-2 mb-2 px-1">
          <label className="text-[11px] text-slate-500 flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={streamMode}
              onChange={(e) => setStreamMode(e.target.checked)}
              className="accent-brand-600"
            />
            Stream responses
          </label>
        </div>
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            rows={1}
            placeholder="Ask a question… (Enter to send)"
            className="flex-1 resize-none rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 text-sm transition"
            disabled={busy}
          />
          <button
            onClick={send}
            disabled={busy || !input.trim()}
            className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-brand-600 to-violet-600 hover:from-brand-700 hover:to-violet-700 text-white disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium lift-hover"
          >
            {busy ? <span className="loader" /> : "Send →"}
          </button>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message, file, onPlayAt }) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end slide-in-right">
        <div className="flex items-start gap-2 max-w-[80%]">
          <div className="rounded-2xl rounded-tr-md px-4 py-2.5 text-sm bg-gradient-to-br from-brand-600 to-violet-600 text-white shadow-sm whitespace-pre-wrap">
            {message.content}
          </div>
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-brand-500 to-violet-600 text-white grid place-items-center text-xs font-semibold shrink-0 mt-0.5">
            {/* User avatar — initial */}
            U
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start fade-in">
      <div className="flex items-start gap-2 max-w-[90%] w-full">
        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 text-white grid place-items-center shrink-0 mt-0.5 shadow-sm">
          <span className="text-xs">📚</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="rounded-2xl rounded-tl-md px-4 py-2.5 text-sm bg-white border border-slate-200 text-slate-900 shadow-sm whitespace-pre-wrap">
            {message.content || (message.streaming ? <span className="loader" /> : "")}
          </div>
          {message.citations && message.citations.length > 0 && (
            <div className="mt-2 space-y-1.5">
              <div className="text-[10px] uppercase tracking-widest text-slate-400 font-semibold pl-1">
                {message.citations.length} source{message.citations.length === 1 ? "" : "s"}
              </div>
              {message.citations.map((c, i) => {
                const isMedia = c.start != null;
                return (
                  <div
                    key={i}
                    className="bg-white/80 backdrop-blur border border-slate-200 hover:border-brand-300 rounded-lg p-2.5 text-xs transition"
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <div className="font-semibold text-slate-700 flex items-center gap-1.5">
                        <span className="text-brand-500">
                          {isMedia ? "⏱" : "📄"}
                        </span>
                        {isMedia
                          ? `${formatTime(c.start)} – ${formatTime(c.end)}`
                          : c.page != null
                          ? `Page ${c.page}`
                          : "Source"}
                      </div>
                      {isMedia && (file.file_type === "audio" || file.file_type === "video") && (
                        <button
                          onClick={() => onPlayAt?.(c.start)}
                          className="px-2 py-0.5 rounded-md bg-gradient-to-r from-brand-600 to-violet-600 text-white text-[10px] hover:from-brand-700 hover:to-violet-700 transition font-semibold shadow-sm"
                        >
                          ▶ Play
                        </button>
                      )}
                    </div>
                    <div className="text-slate-600 italic leading-relaxed">{c.snippet}</div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
