import { useEffect, useImperativeHandle, useRef, useState, forwardRef } from "react";
import { api, getToken } from "../api/client.js";

/**
 * Plays audio/video, exposes seek(seconds) imperatively.
 * Loads the file as a blob (so the Authorization header is honored).
 */
const MediaPlayer = forwardRef(function MediaPlayer({ file }, ref) {
  const elRef = useRef(null);
  const [blobUrl, setBlobUrl] = useState(null);
  const [err, setErr] = useState("");

  useImperativeHandle(
    ref,
    () => ({
      seek: (seconds) => {
        const el = elRef.current;
        if (!el) return;
        try {
          el.currentTime = Math.max(0, seconds);
          el.play().catch(() => {});
        } catch {
          /* ignore */
        }
      },
    }),
    []
  );

  useEffect(() => {
    if (!file) return;
    let cancelled = false;
    let createdUrl = null;
    setErr("");
    setBlobUrl(null);
    (async () => {
      try {
        const res = await fetch(api.mediaUrl(file.id), {
          headers: { Authorization: `Bearer ${getToken()}` },
        });
        if (!res.ok) throw new Error("Failed to load media");
        const blob = await res.blob();
        if (cancelled) return;
        createdUrl = URL.createObjectURL(blob);
        setBlobUrl(createdUrl);
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [file?.id]);

  if (!file) return null;
  if (err) return <div className="text-sm text-red-600">{err}</div>;
  if (!blobUrl) {
    return (
      <div className="text-sm text-slate-500 flex items-center gap-2">
        <span className="loader" /> Loading media…
      </div>
    );
  }

  if (file.file_type === "video") {
    return (
      <video
        ref={elRef}
        src={blobUrl}
        controls
        className="w-full rounded-lg bg-black max-h-72"
      />
    );
  }
  return <audio ref={elRef} src={blobUrl} controls className="w-full" />;
});

export default MediaPlayer;
