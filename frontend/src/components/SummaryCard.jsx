export default function SummaryCard({ file }) {
  if (!file) return null;
  if (file.status === "ready" && file.summary) {
    return (
      <div className="rounded-xl bg-white border border-slate-200 p-4 shadow-sm">
        <div className="flex items-center gap-2 mb-2.5">
          <span className="text-base">✨</span>
          <span className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">
            Summary
          </span>
        </div>
        <div className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
          {file.summary}
        </div>
      </div>
    );
  }
  if (file.status === "ready") {
    return (
      <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 text-sm text-slate-500 italic">
        No summary available.
      </div>
    );
  }
  return (
    <div className="rounded-xl bg-gradient-to-br from-amber-50 to-orange-50 border border-amber-200 p-4 text-sm text-amber-800 flex items-center gap-2.5">
      <span className="loader" />
      <span>Summary will appear once processing finishes.</span>
    </div>
  );
}
