import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/";
    }
    return Promise.reject(error);
  }
);

// ── Auth ───────────────────────────────────────────────────────────────────────

export const register = async (email, password) => {
  const response = await api.post("/register", { email, password });
  return response.data;
};

export const login = async (email, password) => {
  const response = await api.post("/login", { email, password });
  return response.data;
};

// ── Documents ──────────────────────────────────────────────────────────────────

export const uploadDocument = async (file) => {
  const formData = new FormData();
  formData.append("file", file);
  const response = await api.post("/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
};

export const getDocuments = async () => {
  const response = await api.get("/documents");
  return response.data;
};

export const deleteDocument = async (documentId) => {
  const response = await api.delete(`/documents/${documentId}`);
  return response.data;
};

export const getPdfBlob = async (documentId) => {
  const response = await api.get(`/documents/${documentId}/pdf`, {
    responseType: "blob",
  });
  return response.data;
};

// ── Query (legacy) ─────────────────────────────────────────────────────────────

export const queryDocument = async (documentId, question) => {
  const response = await api.post("/query", { document_id: documentId, question });
  return response.data;
};

// ── Conversations ──────────────────────────────────────────────────────────────

export const createConversation = async (documentId) => {
  const response = await api.post("/conversations", { document_id: documentId });
  return response.data;
};

export const getConversationMessages = async (conversationId) => {
  const response = await api.get(`/conversations/${conversationId}/messages`);
  return response.data;
};

export const deleteConversation = async (conversationId) => {
  const response = await api.delete(`/conversations/${conversationId}`);
  return response.data;
};

// ── SSE Streaming query ────────────────────────────────────────────────────────

/**
 * Opens an SSE stream to /query/stream.
 * Calls onToken(str), onCitations(arr), onDone(data), onError(str) as events arrive.
 * Returns an AbortController — call .abort() to cancel mid-stream.
 */
export const queryDocumentStream = (
  documentId,
  question,
  conversationId,
  onToken,
  onCitations,
  onDone,
  onError
) => {
  const controller = new AbortController();
  const token = localStorage.getItem("token");

  fetch(`${API_BASE_URL}/query/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      document_id: documentId,
      question,
      conversation_id: conversationId ?? null,
    }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        onError(err.detail || `Request failed (${response.status})`);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop(); // keep incomplete trailing chunk

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const payload = JSON.parse(line.slice(6));
            if (payload.event === "token") onToken(payload.data);
            else if (payload.event === "citations") onCitations(payload.data);
            else if (payload.event === "done") onDone(payload.data);
            else if (payload.event === "error") onError(payload.data);
          } catch {
            // malformed line — skip
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== "AbortError") onError(err.message || "Stream error");
    });

  return controller;
};

export default api;
