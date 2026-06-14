import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  createConversation,
  getConversationMessages,
  getDocuments,
  getPdfBlob,
  queryDocumentStream,
} from "../api";
import {
  ArrowLeft,
  Eye,
  Plus,
  Send,
  MessageSquare,
  ChevronDown,
  ChevronUp,
  BookOpen,
  Calendar,
  Layers,
  Sparkles
} from "lucide-react";

function CitationCard({ citation, index }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="bg-brand-paper border border-brand-forest/10 rounded-xl overflow-hidden shadow-sm transition-all duration-200">
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 bg-brand-cream/30 hover:bg-brand-cream/60 transition-colors text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-brand-forest bg-brand-forest/5 border border-brand-forest/15 px-2 py-0.5 rounded-full">
            Source [{index + 1}]
          </span>
          <span className="text-xs font-semibold text-brand-forest/80 truncate max-w-[180px] sm:max-w-xs">
            {citation.page_number ? `Page ${citation.page_number}` : "Page N/A"}
            {citation.filename ? ` · ${citation.filename}` : ""}
          </span>
        </div>
        <div className="text-brand-forest/50">
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </div>
      </button>
      {expanded && (
        <div className="px-4 py-3 border-t border-brand-forest/10 bg-brand-cream/10 text-xs md:text-sm text-brand-forest/90 leading-relaxed font-sans italic">
          "{citation.text_snippet}…"
        </div>
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

  const handleOpenPdf = async () => {
    if (!document?.pdf_url) return;
    try {
      const blob = await getPdfBlob(document.id);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank");
    } catch {
      setError("Failed to open PDF");
    }
  };

  return (
    <div className="min-h-screen bg-brand-bg flex flex-col h-screen">
      {/* Top Navigation Bar */}
      <header className="bg-brand-cream border-b border-brand-forest/10 px-6 py-4 shadow-sm z-20 flex-shrink-0">
        <div className="max-w-5xl mx-auto flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate("/home")}
              className="p-2 hover:bg-brand-forest/5 rounded-xl border border-brand-forest/10 text-brand-forest transition-colors"
              title="Back to Documents"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="min-w-0">
              <h1 className="font-serif text-lg font-bold text-brand-forest truncate leading-tight">
                {document?.filename || "Loading document..."}
              </h1>
              {document && (
                <div className="flex items-center gap-x-2 gap-y-0.5 text-xs text-[#5c723d] flex-wrap mt-0.5">
                  <span className="flex items-center gap-1">
                    <Layers className="w-3 h-3" />
                    {document.page_count} pages
                  </span>
                  <span>•</span>
                  <span>{document.chunk_count} text chunks index</span>
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {document?.pdf_url && (
              <button
                onClick={handleOpenPdf}
                className="p-2 hover:bg-brand-forest/5 rounded-xl border border-brand-forest/10 text-brand-forest transition-colors flex items-center gap-1.5 text-xs font-semibold"
                title="View PDF Source"
              >
                <Eye className="w-4 h-4" />
                <span className="hidden sm:inline">View PDF</span>
              </button>
            )}
            <button
              onClick={handleNewChat}
              className="p-2 bg-brand-forest hover:bg-brand-forest-hover text-brand-bg rounded-xl shadow-sm transition-all duration-300 flex items-center gap-1.5 text-xs font-semibold"
              title="Start a new chat conversation"
            >
              <Plus className="w-4 h-4" />
              <span className="hidden sm:inline">New Chat</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Conversation Stream */}
      <main className="flex-1 overflow-y-auto px-6 py-6 scrollbar-none max-w-4xl mx-auto w-full flex flex-col gap-6">
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl p-4 flex items-start gap-2 flex-shrink-0 shadow-sm">
            <span className="font-semibold">Error:</span>
            <span>{error}</span>
          </div>
        )}

        {messages.length === 0 && !loading && (
          <div className="my-auto flex flex-col items-center justify-center text-center py-12">
            <div className="p-4 bg-brand-forest/5 rounded-full border border-brand-forest/10 inline-block mb-4">
              <MessageSquare className="w-8 h-8 text-brand-forest" />
            </div>
            <h2 className="font-serif text-2xl text-brand-forest mb-2">Ask a Question</h2>
            <p className="text-sm text-brand-forest/60 max-w-sm mx-auto">
              Type a prompt below to query the text contents of <span className="font-semibold">"{document?.filename}"</span>. 
              The assistant retrieves context and answers using grounded RAG nodes.
            </p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex flex-col gap-2 max-w-[85%] ${
              msg.type === "user" ? "self-end items-end" : "self-start items-start"
            }`}
          >
            {/* Bubble content */}
            <div
              className={`px-6 py-4 rounded-2xl text-sm leading-relaxed shadow-sm font-sans whitespace-pre-wrap ${
                msg.type === "user"
                  ? "bg-brand-forest text-brand-bg rounded-br-sm"
                  : "bg-brand-cream border border-brand-forest/10 text-brand-forest rounded-bl-sm"
              }`}
            >
              {msg.content}
              {msg.streaming && (
                <span className="inline-block w-1.5 h-4 bg-current ml-1 align-middle animate-cursor-blink" />
              )}
            </div>

            {/* AI message metadata/source/citations */}
            {msg.type === "ai" && !msg.streaming && (
              <div className="w-full flex flex-col gap-2 mt-1">
                {msg.source && (
                  <div className="flex items-center gap-1.5 text-xs text-brand-forest/60 font-semibold px-1">
                    <Sparkles className="w-3.5 h-3.5 text-brand-forest/85" />
                    <span>Mode: {msg.source}</span>
                    {msg.chunksUsed > 0 && (
                      <>
                        <span>•</span>
                        <span>{msg.chunksUsed} context chunks referenced</span>
                      </>
                    )}
                  </div>
                )}

                {msg.citations?.length > 0 && (
                  <div className="flex flex-col gap-2 mt-1 pl-1">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-brand-forest/45">
                      Grounding Context References
                    </div>
                    <div className="flex flex-col gap-1.5">
                      {msg.citations.map((c, i) => (
                        <CitationCard key={i} citation={c} index={i} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        <div ref={messagesEndRef} />
      </main>

      {/* Message Input Section */}
      <footer className="bg-brand-cream border-t border-brand-forest/10 px-6 py-4 flex-shrink-0 z-20">
        <div className="max-w-4xl mx-auto">
          <form onSubmit={handleSubmit} className="flex gap-3 relative items-center">
            <input
              type="text"
              className="flex-1 bg-brand-paper border border-brand-forest/10 rounded-xl py-3.5 pl-4 pr-14 text-sm text-brand-forest placeholder-brand-forest/40 focus:outline-none focus:border-brand-forest/30 transition-colors shadow-sm disabled:opacity-75"
              placeholder="Ask a question about this document..."
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !question.trim()}
              className="absolute right-2 p-2 bg-brand-forest hover:bg-brand-forest-hover disabled:bg-brand-forest/30 text-brand-bg rounded-lg shadow-sm transition-all duration-300"
              title="Send Prompt"
            >
              <Send className="w-4.5 h-4.5" />
            </button>
          </form>
          <div className="text-[10px] text-center text-brand-forest/45 mt-2">
            AskYourPDF uses context retrieval to <b>reduce</b> hallucination.
          </div>
        </div>
      </footer>
    </div>
  );
}

export default Chat;
