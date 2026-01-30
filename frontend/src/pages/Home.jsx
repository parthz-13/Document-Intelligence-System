import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { getDocuments, uploadDocument, deleteDocument } from "../api";

function Home() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
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

  const handleDelete = async (e, docId) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this document?")) return;

    try {
      await deleteDocument(docId);
      setDocuments(documents.filter((d) => d.id !== docId));
      setSuccess("Document deleted");
    } catch (err) {
      setError("Failed to delete document");
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
    <div className="container">
      <div className="header">
        <h1>My Documents</h1>
        <button className="btn btn-secondary" onClick={handleLogout}>
          Logout
        </button>
      </div>

      <div className="card upload-section">
        <div className="upload-area">
          <input
            ref={fileInputRef}
            type="file"
            id="file-upload"
            className="file-input"
            accept=".pdf"
            onChange={handleFileChange}
            disabled={uploading}
          />
          {uploading ? (
            <div className="loading">
              <span className="spinner"></span>
              Uploading and processing PDF...
            </div>
          ) : (
            <p>
              Drag and drop a PDF or{" "}
              <label htmlFor="file-upload" className="upload-label">
                browse files
              </label><br></br>
              PDF formats, upto 10MB
            </p>
          )}
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      <div className="card">
        <h2 style={{ marginBottom: "1rem", color: "var(--text-secondary)" }}>
          Your Documents
        </h2>

        {loading ? (
          <div className="loading" style={{ padding: "2rem" }}>
            <span className="spinner"></span>
            Loading documents...
          </div>
        ) : documents.length === 0 ? (
          <div className="empty-state">
            <h3>No documents yet</h3>
            <p>Upload a PDF to get started</p>
          </div>
        ) : (
          <div className="document-list">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className="document-item"
                onClick={() => navigate(`/chat/${doc.id}`)}
              >
                <div className="document-info">
                  <div className="document-name">{doc.filename}</div>
                  <div className="document-meta">
                    {doc.page_count} pages • {formatSize(doc.file_size)} •{" "}
                    {formatDate(doc.upload_date)}
                  </div>
                </div>
                <div className="document-actions">
                  <button
                    className="btn btn-danger btn-small"
                    onClick={(e) => handleDelete(e, doc.id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default Home;
