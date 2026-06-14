import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { getDocuments, uploadDocument, deleteDocument, getPdfBlob } from "../api";
import { 
  LogOut, 
  UploadCloud, 
  FileText, 
  Eye, 
  Trash2, 
  MessageSquare, 
  BookOpen,
  Calendar,
  Layers,
  AlertTriangle
} from "lucide-react";

function Home() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  
  // Custom delete confirmation modal state
  const [deleteTarget, setDeleteTarget] = useState(null); // { id: number, filename: string } | null
  const [isDeleting, setIsDeleting] = useState(false);

  const fileInputRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      const data = await getDocuments();
      setDocuments(data);
    } catch (err) {
      setError("Failed to load documents");
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith(".pdf")) {
      setError("Only PDF files are allowed");
      return;
    }

    setUploading(true);
    setError("");
    setSuccess("");

    try {
      await uploadDocument(file);
      setSuccess("Document uploaded successfully!");
      fetchDocuments();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to upload document");
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  // Custom Delete Action Trigger
  const triggerDeleteConfirm = (e, doc) => {
    e.stopPropagation();
    setDeleteTarget({ id: doc.id, filename: doc.filename });
  };

  // Perform Delete operation
  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    setError("");
    try {
      await deleteDocument(deleteTarget.id);
      setDocuments(documents.filter((d) => d.id !== deleteTarget.id));
      setSuccess(`"${deleteTarget.filename}" deleted successfully.`);
      setDeleteTarget(null);
    } catch (err) {
      setError("Failed to delete document");
    } finally {
      setIsDeleting(false);
    }
  };

  const handleViewPdf = async (e, doc) => {
    e.stopPropagation();
    e.preventDefault();
    try {
      const blob = await getPdfBlob(doc.id);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank");
    } catch {
      setError("Failed to open PDF");
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/");
  };

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  const formatSize = (bytes) => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  return (
    <div className="min-h-screen bg-brand-bg flex flex-col">
      {/* Navigation Header */}
      <nav className="bg-brand-cream border-b border-brand-forest/10 px-6 py-4 shadow-sm sticky top-0 z-30">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-brand-forest" />
            <span className="font-serif text-xl font-bold text-brand-forest tracking-tight">AskYourPDF</span>
          </div>
          <button
            onClick={handleLogout}
            className="inline-flex items-center gap-2 text-sm font-semibold text-brand-forest hover:opacity-75 transition-opacity"
          >
            <LogOut className="w-4.5 h-4.5" />
            Logout
          </button>
        </div>
      </nav>

      {/* Main Container */}
      <main className="flex-1 max-w-5xl mx-auto w-full px-6 py-8 flex flex-col gap-8">
        
        {/* Page Title & Stats */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-serif text-brand-forest leading-tight">My Documents</h1>
            <p className="text-sm text-[#5c723d] mt-1">Manage files and query grounding databases</p>
          </div>
          <div className="text-xs font-semibold text-brand-forest/65 bg-brand-cream border border-brand-forest/15 px-3 py-1.5 rounded-full">
            Total Library: {documents.length} {documents.length === 1 ? 'file' : 'files'}
          </div>
        </div>

        {/* Upload Zone Card */}
        <div className="bg-brand-cream border border-brand-forest/10 rounded-2xl p-6 shadow-sm">
          <div className="border-2 border-dashed border-brand-forest/20 rounded-xl p-8 hover:border-brand-forest/45 transition-colors text-center relative group">
            <input
              ref={fileInputRef}
              type="file"
              id="file-upload"
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
              accept=".pdf"
              onChange={handleFileChange}
              disabled={uploading}
            />
            {uploading ? (
              <div className="flex flex-col items-center justify-center gap-6">
                <div className="relative flex items-center justify-center">
                  <span className="w-14 h-14 border-[3px] border-brand-forest/20 border-t-brand-forest rounded-full animate-spin absolute"></span>
                  <UploadCloud className="w-6 h-6 text-brand-forest animate-pulse" />
                </div>
                <span className="text-sm font-semibold text-brand-forest/80">Uploading and Processing PDF...</span>
                <span className="text-xs text-brand-forest/50">This may take a few seconds</span>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center">
                <div className="p-3 bg-brand-forest/5 rounded-full border border-brand-forest/10 mb-4 group-hover:scale-105 transition-transform duration-300">
                  <UploadCloud className="w-6 h-6 text-brand-forest" />
                </div>
                <p className="text-sm text-brand-forest/75 mb-1">
                  Drag and drop a PDF or <span className="text-brand-forest font-semibold underline decoration-brand-forest/20 decoration-2 underline-offset-2 hover:decoration-brand-forest">browse files</span>
                </p>
                <p className="text-xs text-brand-forest/50">PDF formats up to 10MB</p>
              </div>
            )}
          </div>
        </div>

        {/* Status Alerts */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl p-4 flex items-start gap-2 shadow-sm">
            <span className="font-semibold">Error:</span>
            <span>{error}</span>
          </div>
        )}
        {success && (
          <div className="bg-brand-sage/20 border border-brand-forest/20 text-brand-forest text-sm rounded-xl p-4 flex items-start gap-2 shadow-sm">
            <span className="font-semibold">Success:</span>
            <span>{success}</span>
          </div>
        )}

        {/* Document List Section */}
        <div className="bg-brand-cream border border-brand-forest/10 rounded-2xl p-6 shadow-sm flex-1">
          <h2 className="text-xl font-serif text-brand-forest font-bold mb-4 border-b border-brand-forest/10 pb-2">
            Library Archive
          </h2>

          {loading ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <span className="w-8 h-8 border-3 border-brand-forest/30 border-t-brand-forest rounded-full animate-spin"></span>
              <span className="text-sm text-brand-forest/60">Loading documents...</span>
            </div>
          ) : documents.length === 0 ? (
            <div className="text-center py-16">
              <div className="p-4 bg-brand-forest/5 rounded-full border border-brand-forest/10 inline-block mb-4">
                <FileText className="w-8 h-8 text-brand-forest/65" />
              </div>
              <h3 className="font-serif text-lg text-brand-forest mb-1">No documents in your library</h3>
              <p className="text-sm text-brand-forest/60 max-w-sm mx-auto">Upload a PDF file using the zone above to get started with grounding chat.</p>
            </div>
          ) : (
            <div className="divide-y divide-brand-forest/10">
              {documents.map((doc) => (
                <div
                  key={doc.id}
                  className="py-4 first:pt-0 last:pb-0 flex flex-col sm:flex-row sm:items-center justify-between gap-4 group hover:bg-brand-forest/[0.01] px-2 rounded-xl transition-colors duration-200"
                >
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <div className="p-2.5 bg-brand-forest/5 rounded-xl border border-brand-forest/10 text-brand-forest mt-0.5">
                      <FileText className="w-5 h-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold text-brand-forest truncate mb-0.5" title={doc.filename}>
                        {doc.filename}
                      </div>
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-brand-forest/65">
                        <span className="flex items-center gap-1">
                          <Layers className="w-3.5 h-3.5" />
                          {doc.page_count} pages
                        </span>
                        <span>•</span>
                        <span>{formatSize(doc.file_size)}</span>
                        <span>•</span>
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3.5 h-3.5" />
                          {formatDate(doc.upload_date)}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Actions (icons instead of buttons) */}
                  <div className="flex items-center gap-2 self-end sm:self-center">
                    <button
                      onClick={() => navigate(`/chat/${doc.id}`)}
                      title="Chat with Document"
                      className="p-2 text-brand-forest bg-brand-bg border border-brand-forest/10 hover:bg-brand-forest hover:text-brand-bg rounded-lg shadow-sm transition-all duration-300"
                    >
                      <MessageSquare className="w-4 h-4" />
                    </button>

                    {doc.pdf_url && (
                      <button
                        onClick={(e) => handleViewPdf(e, doc)}
                        title="View PDF"
                        className="p-2 text-brand-forest bg-brand-bg border border-brand-forest/10 hover:bg-brand-forest hover:text-brand-bg rounded-lg shadow-sm transition-all duration-300"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                    )}

                    <button
                      onClick={(e) => triggerDeleteConfirm(e, doc)}
                      title="Delete Document"
                      className="p-2 text-red-600 bg-brand-bg border border-red-200 hover:bg-red-600 hover:text-white rounded-lg shadow-sm transition-all duration-300"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* Custom Delete Confirmation Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-brand-forest/20 modal-backdrop-blur transition-all duration-300">
          <div className="bg-brand-cream border border-brand-forest/15 rounded-2xl max-w-md w-full p-6 shadow-xl transform scale-100 animate-fade-in">
            <div className="flex items-start gap-4 mb-4">
              <div className="p-3 bg-red-50 text-red-600 border border-red-100 rounded-2xl">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-serif text-lg font-bold text-brand-forest">Delete Document?</h3>
                <p className="text-sm text-brand-forest/75 mt-1">
                  Are you sure you want to permanently delete <span className="font-semibold text-brand-forest">"{deleteTarget.filename}"</span>? This action cannot be undone and will delete all associated chats and index chunks.
                </p>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setDeleteTarget(null)}
                disabled={isDeleting}
                className="px-4 py-2 text-sm font-semibold text-brand-forest hover:bg-brand-forest/5 rounded-xl border border-brand-forest/10 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={isDeleting}
                className="px-4 py-2 text-sm font-semibold bg-red-600 hover:bg-red-700 text-white rounded-xl shadow-sm transition-colors flex items-center gap-1.5"
              >
                {isDeleting ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                    Deleting...
                  </>
                ) : (
                  "Delete Document"
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Home;
