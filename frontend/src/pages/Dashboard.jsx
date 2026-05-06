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
  const [detail, setDetail] = useState(null); // selected file with transcript
  const playerRef = useRef(null);

  const refresh = async () => {
    try {
      const list = await api.listFiles();
      setFiles(list);
      // Update selected from list (status may have changed)
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

  // Load detailed file info when selection or status changes
  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    if (selected.status !== "ready") {
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

  return (
    <div className="h-screen flex flex-col">
      <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-2xl">📚</span>
          <span className="font-semibold text-slate-900">AI Q&A</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-600">{user?.email}</span>
          <button
            onClick={logout}
            className="text-sm text-slate-600 hover:text-red-600 transition"
          >
            Sign out
          </button>
        </div>
      </header>

      <div className="flex-1 grid grid-cols-12 overflow-hidden">
        {/* Sidebar */}
        <aside className="col-span-3 border-r border-slate-200 bg-white p-4 overflow-y-auto space-y-4">
          <FileUpload onUploaded={onUploaded} />
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-2 px-1">
              Your files
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
          <section className="col-span-5 border-r border-slate-200 overflow-y-auto p-5 space-y-4">
            {selected ? (
              <>
                <div>
                  <h2 className="text-lg font-semibold text-slate-900 break-all">
                    {selected.filename}
                  </h2>
                  <div className="text-xs text-slate-500 mt-1">
                    {selected.file_type} · {(selected.size_bytes / 1024 / 1024).toFixed(2)} MB
                    {selected.duration_seconds
                      ? ` · ${formatTime(selected.duration_seconds)}`
                      : ""}
                  </div>
                </div>
                {(selected.file_type === "audio" || selected.file_type === "video") &&
                  selected.status === "ready" && (
                    <MediaPlayer ref={playerRef} file={selected} />
                  )}
                <SummaryCard file={selected} />
                {detail?.transcript_segments?.length > 0 && (
                  <TranscriptList
                    segments={detail.transcript_segments}
                    onPlayAt={onPlayAt}
                  />
                )}
              </>
            ) : (
              <div className="h-full grid place-items-center text-center text-slate-500">
                <div>
                  <div className="text-5xl mb-3">📁</div>
                  <div className="text-sm">Upload or select a file to view details.</div>
                </div>
              </div>
            )}
          </section>

          <section className="col-span-7 bg-slate-50 overflow-hidden">
            <ChatPanel file={selected} onPlayAt={onPlayAt} />
          </section>
        </main>
      </div>
    </div>
  );
}

function TranscriptList({ segments, onPlayAt }) {
  return (
    <div className="rounded-lg bg-white border border-slate-200 p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-2">
        Transcript
      </div>
      <div className="max-h-72 overflow-y-auto space-y-1.5 text-sm">
        {segments.map((s, i) => (
          <div
            key={i}
            className="flex gap-2 hover:bg-slate-50 rounded p-1 -mx-1 cursor-pointer group"
            onClick={() => onPlayAt(s.start)}
          >
            <span className="text-xs text-brand-600 font-mono shrink-0 mt-0.5 w-12 group-hover:underline">
              {formatTime(s.start)}
            </span>
            <span className="text-slate-700">{s.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
