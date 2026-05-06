import { useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";
import { useAuth } from "../hooks/useAuth.jsx";
import FileUpload from "../components/FileUpload.jsx";
import FileList from "../components/FileList.jsx";
import ChatPanel from "../components/ChatPanel.jsx";
import MediaPlayer from "../components/MediaPlayer.jsx";
import SummaryCard from "../components/SummaryCard.jsx";
import { formatTime } from "../api/format.js";

export default function Dashboard() {
  const { user, logout } = useAuth();
  const [files, setFiles] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const playerRef = useRef(null);

  const refresh = async () => {
    try {
      const list = await api.listFiles();
      setFiles(list);
      if (selected) {
        const s = list.find((f) => f.id === selected.id);
        if (s) setSelected(s);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selected || selected.status !== "ready") {
      setDetail(null);
      return;
    }
    api.getFile(selected.id).then(setDetail).catch(() => setDetail(null));
  }, [selected?.id, selected?.status]);

  const onUploaded = (file) => {
    setFiles((prev) => [file, ...prev]);
    setSelected(file);
  };

  const onPlayAt = (seconds) => {
    playerRef.current?.seek(seconds);
  };

  const initial = (user?.email || "?")[0].toUpperCase();

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-md border-b border-slate-200/80 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="text-2xl">📚</span>
          <div>
            <div className="font-bold text-slate-900 text-base leading-tight gradient-text">AI Q&A</div>
            <div className="text-[10px] text-slate-500 leading-tight">Documents · Audio · Video</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right hidden sm:block">
            <div className="text-xs text-slate-500">Signed in as</div>
            <div className="text-sm text-slate-700 font-medium">{user?.email}</div>
          </div>
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-brand-500 to-violet-600 text-white grid place-items-center font-semibold text-sm">
            {initial}
          </div>
          <button
            onClick={logout}
            className="text-sm text-slate-500 hover:text-red-600 transition px-2 py-1 rounded"
            title="Sign out"
          >
            Sign out
          </button>
        </div>
      </header>

      <div className="flex-1 grid grid-cols-12 overflow-hidden">
        {/* Sidebar */}
        <aside className="col-span-3 border-r border-slate-200/80 bg-white/40 backdrop-blur p-4 overflow-y-auto space-y-5">
          <FileUpload onUploaded={onUploaded} />
          <div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold mb-2 px-1">
              Your files {files.length > 0 && <span className="text-slate-400">· {files.length}</span>}
            </div>
            <FileList
              files={files}
              selectedId={selected?.id}
              onSelect={setSelected}
              onRefresh={refresh}
              onDelete={(id) => {
                setFiles((p) => p.filter((f) => f.id !== id));
                if (selected?.id === id) setSelected(null);
              }}
            />
          </div>
        </aside>

        {/* Main content */}
        <main className="col-span-9 grid grid-cols-12 overflow-hidden">
          <section className="col-span-5 border-r border-slate-200/80 overflow-y-auto p-5 space-y-4">
            {selected ? (
              <>
                <div className="fade-in">
                  <h2 className="text-lg font-semibold text-slate-900 break-all leading-tight">
                    {selected.filename}
                  </h2>
                  <div className="text-xs text-slate-500 mt-1.5 flex items-center gap-2 flex-wrap">
                    <span className="bg-slate-100 px-2 py-0.5 rounded font-medium uppercase tracking-wide text-[10px]">
                      {selected.file_type}
                    </span>
                    <span>{(selected.size_bytes / 1024 / 1024).toFixed(2)} MB</span>
                    {selected.duration_seconds ? (
                      <>
                        <span className="text-slate-300">•</span>
                        <span>{formatTime(selected.duration_seconds)}</span>
                      </>
                    ) : null}
                  </div>
                </div>
                {(selected.file_type === "audio" || selected.file_type === "video") &&
                  selected.status === "ready" && (
                    <div className="fade-in" style={{ animationDelay: "0.1s" }}>
                      <MediaPlayer ref={playerRef} file={selected} />
                    </div>
                  )}
                <div className="fade-in" style={{ animationDelay: "0.15s" }}>
                  <SummaryCard file={selected} />
                </div>
                {detail?.transcript_segments?.length > 0 && (
                  <div className="fade-in" style={{ animationDelay: "0.2s" }}>
                    <TranscriptList
                      segments={detail.transcript_segments}
                      onPlayAt={onPlayAt}
                    />
                  </div>
                )}
              </>
            ) : (
              <div className="h-full grid place-items-center text-center text-slate-500 px-6">
                <div className="fade-in">
                  <div className="text-6xl mb-4">📁</div>
                  <div className="text-base font-medium text-slate-700 mb-1">No file selected</div>
                  <div className="text-sm text-slate-500">Upload or pick a file from the sidebar</div>
                </div>
              </div>
            )}
          </section>

          <section className="col-span-7 bg-gradient-to-br from-slate-50 to-white overflow-hidden">
            <ChatPanel file={selected} onPlayAt={onPlayAt} />
          </section>
        </main>
      </div>
    </div>
  );
}

function TranscriptList({ segments, onPlayAt }) {
  return (
    <div className="rounded-xl bg-white border border-slate-200 p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-base">📝</span>
        <span className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">
          Transcript
        </span>
      </div>
      <div className="max-h-72 overflow-y-auto space-y-1.5 text-sm pr-1">
        {segments.map((s, i) => (
          <div
            key={i}
            className="flex gap-2.5 hover:bg-brand-50 rounded-md p-1.5 -mx-1.5 cursor-pointer group transition"
            onClick={() => onPlayAt(s.start)}
          >
            <span className="text-xs text-brand-600 font-mono shrink-0 mt-0.5 w-12 group-hover:underline font-semibold">
              {formatTime(s.start)}
            </span>
            <span className="text-slate-700 leading-relaxed">{s.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
