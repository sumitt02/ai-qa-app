import { useEffect } from "react";
import { api } from "../api/client.js";

const ICONS = { pdf: "📄", audio: "🎧", video: "🎬" };

function StatusBadge({ status }) {
  if (status === "ready") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 font-semibold">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
        Ready
      </span>
    );
  }
  if (status === "processing" || status === "pending") {
    return (
      <span className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-semibold">
        <span className="pulse-dot"></span>
        {status}
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-red-100 text-red-700 font-semibold">
        <span className="w-1.5 h-1.5 rounded-full bg-red-500"></span>
        Failed
      </span>
    );
  }
  return null;
}

export default function FileList({ files, selectedId, onSelect, onRefresh, onDelete }) {
  useEffect(() => {
    const pending = files.some(
      (f) => f.status === "pending" || f.status === "processing"
    );
    if (!pending) return;
    const t = setInterval(onRefresh, 3000);
    return () => clearInterval(t);
  }, [files, onRefresh]);

  if (files.length === 0) {
    return (
      <div className="text-sm text-slate-400 italic px-1 py-3 text-center">
        No files yet
      </div>
    );
  }

  const remove = async (e, f) => {
    e.stopPropagation();
    if (!confirm(`Delete "${f.filename}"?`)) return;
    try {
      await api.deleteFile(f.id);
      onDelete?.(f.id);
    } catch (err) {
      alert(err.message || "Delete failed");
    }
  };

  return (
    <ul className="space-y-1.5">
      {files.map((f) => {
        const isSelected = selectedId === f.id;
        return (
          <li
            key={f.id}
            onClick={() => onSelect(f)}
            className={`group cursor-pointer rounded-lg p-2.5 border transition-all duration-200 ${
              isSelected
                ? "border-brand-500 bg-gradient-to-br from-brand-50 to-violet-50 shadow-sm"
                : "border-slate-200 bg-white/60 hover:bg-white hover:border-slate-300 hover:-translate-y-px hover:shadow-sm"
            }`}
          >
            <div className="flex items-start gap-2.5">
              <div className="text-xl shrink-0 mt-0.5">{ICONS[f.file_type] || "📁"}</div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-slate-900 truncate leading-tight">
                  {f.filename}
                </div>
                <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                  <StatusBadge status={f.status} />
                  {f.status === "ready" && f.duration_seconds && (
                    <span className="text-[11px] text-slate-500">
                      {Math.round(f.duration_seconds)}s
                    </span>
                  )}
                </div>
                {f.error_message && (
                  <div className="text-[11px] text-red-600 mt-1 line-clamp-1">{f.error_message}</div>
                )}
              </div>
              <button
                onClick={(e) => remove(e, f)}
                className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-600 transition px-1 -mr-1"
                title="Delete"
              >
                ✕
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
