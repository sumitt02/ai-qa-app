import { useEffect } from "react";
import { api } from "../api/client.js";

const ICONS = { pdf: "📄", audio: "🎧", video: "🎬" };
const STATUS_COLORS = {
  pending: "bg-slate-100 text-slate-700",
  processing: "bg-amber-100 text-amber-800",
  ready: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-700",
};

export default function FileList({ files, selectedId, onSelect, onRefresh, onDelete }) {
  // Poll for status updates while anything is pending/processing
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
      <div className="text-sm text-slate-500 italic px-1 py-4">
        No files yet. Upload one to get started.
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
      {files.map((f) => (
        <li
          key={f.id}
          onClick={() => onSelect(f)}
          className={`group cursor-pointer rounded-lg p-2.5 border transition ${
            selectedId === f.id
              ? "border-brand-500 bg-brand-50"
              : "border-slate-200 hover:bg-slate-50"
          }`}
        >
          <div className="flex items-start gap-2">
            <div className="text-xl shrink-0">{ICONS[f.file_type] || "📁"}</div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-slate-900 truncate">{f.filename}</div>
              <div className="flex items-center gap-2 mt-1">
                <span
                  className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded ${STATUS_COLORS[f.status]}`}
                >
                  {f.status}
                </span>
                {(f.status === "pending" || f.status === "processing") && (
                  <span className="loader" aria-hidden />
                )}
                {f.status === "ready" && f.duration_seconds && (
                  <span className="text-[11px] text-slate-500">
                    {Math.round(f.duration_seconds)}s
                  </span>
                )}
              </div>
              {f.error_message && (
                <div className="text-[11px] text-red-600 mt-1 truncate">{f.error_message}</div>
              )}
            </div>
            <button
              onClick={(e) => remove(e, f)}
              className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-600 transition px-1"
              title="Delete"
            >
              ✕
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
