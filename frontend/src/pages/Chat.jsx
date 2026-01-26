import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { queryDocument, getDocuments } from "../api";

function Chat() {
  const { documentId } = useParams();
  const navigate = useNavigate();
  const [document, setDocument] = useState(null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const messagesEndRef = useRef(null);

  useEffect(() => {
    fetchDocument();
  }, [documentId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const fetchDocument = async () => {
    try {
      const docs = await getDocuments();
      const doc = docs.find((d) => d.id === parseInt(documentId));
      if (doc) {
        setDocument(doc);
      } else {
        setError("Document not found");
      }
    } catch (err) {
      setError("Failed to load document");
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim() || loading) return;

    const userMessage = { type: "user", content: question };
    setMessages((prev) => [...prev, userMessage]);
    setQuestion("");
    setLoading(true);
    setError("");

    try {
      const response = await queryDocument(parseInt(documentId), question);
      const aiMessage = {
        type: "ai",
        content: response.answer,
        source: response.source,
        chunksUsed: response.chunks_used,
        bestDistance: response.best_distance,
      };
      setMessages((prev) => [...prev, aiMessage]);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to get answer");
    } finally {
      setLoading(false);
    }
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
              {document.page_count} pages • {document.chunk_count} chunks
              indexed
            </span>
          )}
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <h3>Ask a question</h3>
            <p>Start by asking something about this document</p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} className={`message message-${msg.type}`}>
            <div>{msg.content}</div>
            {msg.type === "ai" && msg.source && (
              <div className="message-source">
                Source: {msg.source}
                {msg.chunksUsed > 0 && ` • ${msg.chunksUsed} chunks used`}
                {msg.bestDistance !== null &&
                  ` • Relevance: ${(1 - msg.bestDistance).toFixed(2)}`}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="message message-ai">
            <div className="loading">
              <span className="spinner"></span>
              Thinking...
            </div>
          </div>
        )}

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
          Send
        </button>
      </form>
    </div>
  );
}

export default Chat;
