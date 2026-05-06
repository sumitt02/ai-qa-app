import { useRef, useState } from "react";
import { api } from "../api/client.js";

export default function FileUpload({ onUploaded }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [progress, setProgress] = useState(0);

  const accepted =
    ".pdf,.mp3,.wav,.m4a,.webm,.ogg,.mp4,.mov,.mkv,application/pdf,audio/*,video/*";

  const upload = async (file) => {
    setErr("");
    setBusy(true);
    setProgress(0);
    try {
      // Simple progress: indeterminate via interval. Real progress would need XHR.
      const tick = setInterval(() => setProgress((p) => Math.min(p + 7, 90)), 250);
      const res = await api.uploadFile(file);
      clearInterval(tick);
      setProgress(100);
      onUploaded?.(res);
      setTimeout(() => setProgress(0), 600);
    } catch (e) {
      setErr(e.message || "Upload failed");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const onChange = (e) => {
    const f = e.target.files?.[0];
    if (f) upload(f);
  };

  const onDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer?.files?.[0];
    if (f) upload(f);
  };

  return (
    <div className="space-y-2">
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className="cursor-pointer border-2 border-dashed border-slate-300 hover:border-brand-500 hover:bg-brand-50 transition rounded-xl p-6 text-center"
      >
        <input
          ref={inputRef}
          type="file"
          accept={accepted}
          onChange={onChange}
          className="hidden"
          disabled={busy}
        />
        <div className="text-3xl mb-2">📎</div>
        <div className="text-sm text-slate-700 font-medium">
          {busy ? "Uploading..." : "Click or drop a file"}
        </div>
        <div className="text-xs text-slate-500 mt-1">PDF, audio, or video (up to 100 MB)</div>
        {progress > 0 && (
          <div className="mt-3 h-1.5 w-full bg-slate-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-brand-500 transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}
      </div>
      {err && <div className="text-xs text-red-600">{err}</div>}
    </div>
  );
}
