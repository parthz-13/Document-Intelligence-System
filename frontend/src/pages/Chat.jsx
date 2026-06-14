import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  createConversation,
  getConversationMessages,
  getDocuments,
  queryDocumentStream,
} from "../api";

function CitationCard({ citation, index }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="citation-card">
      <button
        className="citation-header"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="citation-badge">[{index + 1}]</span>
        <span className="citation-page">
          {citation.page_number ? `Page ${citation.page_number}` : "Page N/A"}
          {citation.filename ? ` · ${citation.filename}` : ""}
        </span>
        <span className="citation-chevron">{expanded ? "▲" : "▼"}</span>
      </button>
      {expanded && (
        <div className="citation-snippet">"{citation.text_snippet}…"</div>
      )}
    </div>
  );
}

function Chat() {
  const { documentId } = useParams();
  const navigate = useNavigate();
  const [document, setDocument] = useState(null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [conversationId, setConversationId] = useState(null);
  const messagesEndRef = useRef(null);
  const streamControllerRef = useRef(null);

  useEffect(() => {
    fetchDocument();
  }, [documentId]);

  useEffect(() => {
    if (document) initConversation();
  }, [document]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const fetchDocument = async () => {
    try {
      const docs = await getDocuments();
      const doc = docs.find((d) => d.id === parseInt(documentId));
      if (doc) setDocument(doc);
      else setError("Document not found");
    } catch {
      setError("Failed to load document");
    }
  };

  const initConversation = async () => {
    const storageKey = `conv_${documentId}`;
    const stored = localStorage.getItem(storageKey);

    if (stored) {
      const convId = parseInt(stored);
      setConversationId(convId);
      try {
        const msgs = await getConversationMessages(convId);
        setMessages(
          msgs.map((m) => ({
            type: m.role === "user" ? "user" : "ai",
            content: m.content,
            citations: [],
            streaming: false,
          }))
        );
      } catch {
        // Conversation may have been deleted — create a fresh one
        localStorage.removeItem(storageKey);
        await startNewConversation(storageKey);
      }
    } else {
      await startNewConversation(storageKey);
    }
  };

  const startNewConversation = async (storageKey) => {
    try {
      const conv = await createConversation(parseInt(documentId));
      setConversationId(conv.id);
      localStorage.setItem(storageKey, conv.id);
    } catch (err) {
      console.error("Failed to create conversation:", err);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim() || loading) return;

    const currentQuestion = question;
    setQuestion("");
    setLoading(true);
    setError("");

    // Add user message immediately
    setMessages((prev) => [...prev, { type: "user", content: currentQuestion }]);

    // Add empty AI placeholder that fills in via streaming
    setMessages((prev) => [
      ...prev,
      { type: "ai", content: "", citations: [], source: null, chunksUsed: 0, streaming: true },
    ]);

    const updateLast = (updater) => {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = updater(next[next.length - 1]);
        return next;
      });
    };

    const controller = queryDocumentStream(
      parseInt(documentId),
      currentQuestion,
      conversationId,
      // onToken
      (token) => updateLast((msg) => ({ ...msg, content: msg.content + token })),
      // onCitations
      (citations) => updateLast((msg) => ({ ...msg, citations })),
      // onDone
      (doneData) => {
        updateLast((msg) => ({
          ...msg,
          streaming: false,
          source: doneData?.source ?? null,
          chunksUsed: doneData?.chunks_used ?? 0,
        }));
        setLoading(false);
      },
      // onError
      (errMsg) => {
        // Remove the empty AI placeholder on error
        setMessages((prev) => prev.slice(0, -1));
        setError(errMsg || "Failed to get answer");
        setLoading(false);
      }
    );

    streamControllerRef.current = controller;
  };

  const handleNewChat = () => {
    localStorage.removeItem(`conv_${documentId}`);
    setMessages([]);
    setConversationId(null);
    startNewConversation(`conv_${documentId}`);
  };

  return (
    <div className="container chat-container">
      <div className="chat-header">
        <button
          className="btn btn-secondary btn-small"
          onClick={() => navigate("/home")}
        >
          ← Back
        </button>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: "1.25rem", color: "var(--accent)" }}>
            {document?.filename || "Loading..."}
          </h2>
          {document && (
            <span style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>
              {document.page_count} pages · {document.chunk_count} chunks
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          {document?.pdf_url && (
            <a
              href={document.pdf_url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-secondary btn-small"
            >
              View PDF
            </a>
          )}
          <button
            className="btn btn-secondary btn-small"
            onClick={handleNewChat}
            title="Start a new conversation"
          >
            New chat
          </button>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="chat-messages">
        {messages.length === 0 && !loading && (
          <div className="empty-state">
            <h3>Ask a question</h3>
            <p>Start by asking something about this document</p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} className={`message message-${msg.type}`}>
            <div style={{ whiteSpace: "pre-wrap" }}>
              {msg.content}
              {msg.streaming && <span className="streaming-cursor" />}
            </div>

            {msg.type === "ai" && !msg.streaming && msg.source && (
              <div className="message-source">
                Source: {msg.source}
                {msg.chunksUsed > 0 && ` · ${msg.chunksUsed} chunks used`}
              </div>
            )}

            {msg.type === "ai" && msg.citations?.length > 0 && (
              <div className="citations-container">
                <div className="citations-label">Sources</div>
                {msg.citations.map((c, i) => (
                  <CitationCard key={i} citation={c} index={i} />
                ))}
              </div>
            )}
          </div>
        ))}

        <div ref={messagesEndRef} />
      </div>

      <form className="chat-input" onSubmit={handleSubmit}>
        <input
          type="text"
          className="form-input"
          placeholder="Ask a question about this document..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={loading}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={loading || !question.trim()}
        >
          {loading ? "..." : "Send"}
        </button>
      </form>
    </div>
  );
}

export default Chat;
