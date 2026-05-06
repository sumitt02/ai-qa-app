// API client. Uses /api proxy in dev; configurable via VITE_API_URL otherwise.
const API_BASE = import.meta.env.VITE_API_URL || "";

const TOKEN_KEY = "ai_qa_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request(path, { method = "GET", body, headers = {}, isForm = false } = {}) {
  const h = { ...headers };
  const token = getToken();
  if (token) h["Authorization"] = `Bearer ${token}`;
  if (!isForm && body !== undefined) h["Content-Type"] = "application/json";

  const res = await fetch(`${API_BASE}/api/v1${path}`, {
    method,
    headers: h,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return null;
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const err = new Error(
      (data && (data.detail || data.message)) || `Request failed (${res.status})`
    );
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

export const api = {
  // Auth
  register: (email, password, full_name) =>
    request("/auth/register", { method: "POST", body: { email, password, full_name } }),
  login: (email, password) =>
    request("/auth/login", { method: "POST", body: { email, password } }),
  me: () => request("/auth/me"),

  // Files
  uploadFile: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return request("/files", { method: "POST", body: fd, isForm: true });
  },
  listFiles: () => request("/files"),
  getFile: (id) => request(`/files/${id}`),
  deleteFile: (id) => request(`/files/${id}`, { method: "DELETE" }),
  mediaUrl: (id) => {
    // Returns a fetch-able URL with auth header — but <video>/<audio> tags need
    // either same-origin or a token in URL. We fetch as blob in the player.
    return `${API_BASE}/api/v1/files/${id}/media`;
  },

  // Chat
  listSessions: () => request("/chat/sessions"),
  getSession: (id) => request(`/chat/sessions/${id}`),
  createSession: (file_id, title) =>
    request("/chat/sessions", { method: "POST", body: { file_id, title } }),
  ask: (question, file_id, session_id) =>
    request("/chat/ask", {
      method: "POST",
      body: { question, file_id, session_id },
    }),
  // Streaming via fetch + ReadableStream — simpler than EventSource here
  // because EventSource can't send Authorization header.
  askStream: async (question, file_id, session_id, onEvent) => {
    const token = getToken();
    const res = await fetch(`${API_BASE}/api/v1/chat/ask/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ question, file_id, session_id }),
    });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(t || `Stream failed (${res.status})`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      // Parse SSE events: separated by \n\n
      let idx;
      while ((idx = buf.indexOf("\n\n")) !== -1) {
        const raw = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const lines = raw.split("\n");
        let event = "message";
        let data = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) event = line.slice(7);
          else if (line.startsWith("data: ")) data += line.slice(6);
        }
        onEvent(event, data);
      }
    }
  },
};
