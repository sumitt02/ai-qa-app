export default function SummaryCard({ file }) {
  if (!file) return null;
  if (file.status === "ready" && file.summary) {
    return (
      <div className="rounded-lg bg-white border border-slate-200 p-4">
        <div className="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-2">
          Summary
        </div>
        <div className="text-sm text-slate-700 whitespace-pre-wrap">{file.summary}</div>
      </div>
    );
  }
  if (file.status === "ready") {
    return (
      <div className="rounded-lg bg-slate-50 border border-slate-200 p-4 text-sm text-slate-500 italic">
        No summary available.
      </div>
    );
  }
  return (
    <div className="rounded-lg bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800 flex items-center gap-2">
      <span className="loader" />
      Summary will appear once processing finishes.
    </div>
  );
}
