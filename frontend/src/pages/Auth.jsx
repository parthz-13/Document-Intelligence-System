import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login, register } from "../api";

function Auth() {
  const [showAuth, setShowAuth] = useState(false);
  const [activeTab, setActiveTab] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const authFn = activeTab === "login" ? login : register;
      const data = await authFn(email, password);
      localStorage.setItem("token", data.access_token);
      navigate("/home");
    } catch (err) {
      const message = err.response?.data?.detail || "An error occurred";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  if (!showAuth) {
    return (
      <div className="landing-container">
        <div className="landing-content">
          <h1 className="landing-hero">
            Ask your PDFs.
            <br />
            <span>Get grounded answers.</span>
          </h1>

          <p className="landing-subheading">
            Upload documents, ask questions in plain English, and get accurate
            answers backed by your PDF.
          </p>

          <p className="landing-micro">
            Powered by Retrieval-Augmented Generation (RAG) for factual,
            document-grounded responses.
          </p>

          <button
            className="btn btn-primary btn-large"
            onClick={() => setShowAuth(true)}
          >
            Get Started
            <span className="btn-arrow">→</span>
          </button>
        </div>
      </div>
    );
  }


  return (
    <div className="auth-container">
      <button className="back-to-landing" onClick={() => setShowAuth(false)}>
        ← Back
      </button>

      <div className="card auth-card">
        <h1 className="auth-title">AskYourPDF</h1>

        <div className="tabs">
          <button
            className={`tab ${activeTab === "login" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("login");
              setError("");
            }}
          >
            Login
          </button>
          <button
            className={`tab ${activeTab === "register" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("register");
              setError("");
            }}
          >
            Register
          </button>
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              className="form-input"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              className="form-input"
              placeholder={
                activeTab === "register" ? "Min 8 characters" : "Your password"
              }
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={activeTab === "register" ? 8 : undefined}
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: "100%" }}
            disabled={loading}
          >
            {loading ? (
              <span className="loading">
                <span className="spinner"></span>
                {activeTab === "login"
                  ? "Signing in..."
                  : "Creating account..."}
              </span>
            ) : activeTab === "login" ? (
              "Sign In"
            ) : (
              "Create Account"
            )}
          </button>
        </form>
      </div>
    </div>
  );
}

export default Auth;
