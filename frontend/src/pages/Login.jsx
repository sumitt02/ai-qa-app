import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth.jsx";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await login(email, password);
      nav("/");
    } catch (e) {
      setErr(e.message || "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen auth-bg grid place-items-center px-4 py-12">
      <div className="w-full max-w-md">
        {/* Brand header */}
        <div className="text-center mb-8 fade-in">
          <div className="inline-flex items-center gap-2 mb-4">
            <span className="text-4xl">📚</span>
            <span className="text-2xl font-bold gradient-text">AI Q&A</span>
          </div>
          <h1 className="text-3xl font-bold text-slate-900 mb-2">Welcome back</h1>
          <p className="text-slate-500 text-sm">Sign in to continue to your workspace</p>
        </div>

        {/* Login form */}
        <form
          onSubmit={submit}
          className="glass-card rounded-2xl p-7 space-y-5 fade-in"
          style={{ animationDelay: "0.1s" }}
        >
          {err && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 flex items-start gap-2">
              <span>⚠️</span>
              <span>{err}</span>
            </div>
          )}

          <label className="block">
            <span className="text-sm font-medium text-slate-700">Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="mt-1.5 block w-full rounded-lg border border-slate-300 bg-white/80 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">Password</span>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="mt-1.5 block w-full rounded-lg border border-slate-300 bg-white/80 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition"
            />
          </label>

          <button
            type="submit"
            disabled={busy}
            className="w-full bg-gradient-to-r from-brand-600 to-violet-600 hover:from-brand-700 hover:to-violet-700 text-white rounded-lg py-2.5 text-sm font-medium disabled:opacity-50 lift-hover"
          >
            {busy ? (
              <span className="inline-flex items-center gap-2">
                <span className="loader" /> Signing in…
              </span>
            ) : (
              "Sign in"
            )}
          </button>

          <p className="text-sm text-center text-slate-500 pt-1">
            No account?{" "}
            <Link to="/register" className="text-brand-600 hover:text-brand-700 font-medium">
              Create one →
            </Link>
          </p>
        </form>

        {/* Feature pills */}
        <div className="mt-8 flex flex-wrap justify-center gap-2 fade-in" style={{ animationDelay: "0.2s" }}>
          {["📄 PDFs", "🎧 Audio", "🎬 Video", "⚡ Streaming"].map((t) => (
            <span
              key={t}
              className="text-xs bg-white/60 backdrop-blur border border-slate-200 rounded-full px-3 py-1 text-slate-600"
            >
              {t}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
