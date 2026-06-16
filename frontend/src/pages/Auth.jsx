import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login, register } from "../api";
import { 
  ArrowRight, 
  ArrowLeft, 
  Lock, 
  Mail, 
  BookOpen, 
  Sparkles, 
  FileText, 
  ShieldCheck 
} from "lucide-react";

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
      <div className="min-height-screen bg-brand-bg flex flex-col justify-between p-6 md:p-12 min-h-screen">
        {/* Header / Brand */}
        <header className="flex items-center justify-between max-w-6xl mx-auto w-full">
          <div className="flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-brand-forest" />
            <span className="font-serif text-xl font-bold text-brand-forest tracking-tight">AskYourPDF</span>
          </div>
          <button 
            onClick={() => setShowAuth(true)}
            className="text-sm font-semibold text-brand-forest hover:opacity-80 transition-opacity"
          >
            Sign In
          </button>
        </header>

        {/* Hero Section */}
        <main className="max-w-4xl mx-auto w-full my-auto flex flex-col items-center text-center py-12">
          {/* Tagline Badge */}


          <h1 className="text-4xl md:text-6xl lg:text-7xl font-serif text-brand-forest leading-[1.1] tracking-tight max-w-3xl mb-6">
            Ask your PDFs.<br />
            <span className="text-[#5c723d] italic font-normal">Get grounded answers.</span>
          </h1>

          <p className="text-base md:text-xl text-brand-forest/80 font-normal leading-relaxed max-w-2xl mb-10">
            Upload documents, ask questions in plain English, and get accurate
            answers backed by your PDF. Powered by Retrieval-Augmented Generation (RAG).
          </p>

          <div className="flex flex-col sm:flex-row gap-4 items-center justify-center">
            <button
              onClick={() => setShowAuth(true)}
              className="inline-flex items-center gap-2 bg-brand-forest hover:bg-brand-forest-hover text-brand-bg px-8 py-4 rounded-full font-semibold shadow-md hover:shadow-lg transition-all duration-300 transform hover:-translate-y-0.5"
            >
              Get Started
              <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
            </button>
          </div>
        </main>

        {/* Feature Grid */}
        <footer className="max-w-6xl mx-auto w-full grid grid-cols-1 md:grid-cols-3 gap-8 pt-8 border-t border-brand-forest/10 mt-12">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-brand-forest/5 rounded-xl border border-brand-forest/10">
              <FileText className="w-5 h-5 text-brand-forest" />
            </div>
            <div>
              <h3 className="font-serif font-bold text-brand-forest text-lg mb-1">Instant Extraction</h3>
              <p className="text-sm text-brand-forest/75">Our pipeline chunks and indexes your PDFs within seconds of upload.</p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="p-3 bg-brand-forest/5 rounded-xl border border-brand-forest/10">
              <Sparkles className="w-5 h-5 text-brand-forest" />
            </div>
            <div>
              <h3 className="font-serif font-bold text-brand-forest text-lg mb-1">Grounded Citations</h3>
              <p className="text-sm text-brand-forest/75">Every response includes the exact source pages and text snippets used.</p>
            </div>
          </div>

          <div className="flex items-start gap-4">
            <div className="p-3 bg-brand-forest/5 rounded-xl border border-brand-forest/10">
              <ShieldCheck className="w-5 h-5 text-brand-forest" />
            </div>
            <div>
              <h3 className="font-serif font-bold text-brand-forest text-lg mb-1">Secure Isolation</h3>
              <p className="text-sm text-brand-forest/75">Your documents are isolated and secure, only accessible by you.</p>
            </div>
          </div>
        </footer>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-brand-bg flex flex-col justify-center items-center p-6 relative">
      {/* Back Button */}
      <button 
        onClick={() => setShowAuth(false)}
        className="absolute top-6 left-6 inline-flex items-center gap-2 text-sm font-semibold text-brand-forest hover:opacity-75 transition-opacity"
      >
        <ArrowLeft className="w-4 h-4" />
        Back
      </button>

      {/* Auth Card */}
      <div className="w-full max-w-md bg-brand-cream border border-brand-forest/10 rounded-2xl p-8 shadow-sm">
        <div className="flex flex-col items-center mb-8">
          <div className="p-3.5 bg-brand-forest/5 rounded-2xl border border-brand-forest/10 mb-3">
            <BookOpen className="w-6 h-6 text-brand-forest" />
          </div>
          <h1 className="text-2xl font-serif text-brand-forest font-bold tracking-tight">Welcome to AskYourPDF</h1>
          <p className="text-xs text-brand-forest/60 mt-1">Enter your details to access your account</p>
        </div>

        {/* Tabs */}
        <div className="flex bg-brand-bg/50 p-1 rounded-xl border border-brand-forest/10 mb-6">
          <button
            onClick={() => {
              setActiveTab("login");
              setError("");
            }}
            className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${
              activeTab === "login" 
                ? "bg-brand-paper text-brand-forest shadow-sm" 
                : "text-brand-forest/65 hover:text-brand-forest"
            }`}
          >
            Login
          </button>
          <button
            onClick={() => {
              setActiveTab("register");
              setError("");
            }}
            className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${
              activeTab === "register" 
                ? "bg-brand-paper text-brand-forest shadow-sm" 
                : "text-brand-forest/65 hover:text-brand-forest"
            }`}
          >
            Register
          </button>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl p-3 mb-6 flex items-start gap-2">
            <span className="font-semibold">Error:</span>
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-xs font-semibold text-brand-forest/80 uppercase tracking-wider mb-2" htmlFor="email">
              Email Address
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 text-brand-forest/40 absolute left-3.5 top-3.5" />
              <input
                id="email"
                type="email"
                className="w-full bg-brand-paper border border-brand-forest/10 rounded-xl py-3 pl-11 pr-4 text-sm text-brand-forest focus:outline-none focus:border-brand-forest/30 transition-colors"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-brand-forest/80 uppercase tracking-wider mb-2" htmlFor="password">
              Password
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 text-brand-forest/40 absolute left-3.5 top-3.5" />
              <input
                id="password"
                type="password"
                className="w-full bg-brand-paper border border-brand-forest/10 rounded-xl py-3 pl-11 pr-4 text-sm text-brand-forest focus:outline-none focus:border-brand-forest/30 transition-colors"
                placeholder={activeTab === "register" ? "Min 8 characters" : "••••••••"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={activeTab === "register" ? 8 : undefined}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-brand-forest hover:bg-brand-forest-hover disabled:bg-brand-forest/50 text-brand-bg py-3.5 rounded-xl font-semibold shadow-sm hover:shadow transition-all duration-300 flex items-center justify-center gap-2 mt-2"
          >
            {loading ? (
              <>
                <span className="w-4 h-4 border-2 border-brand-bg/30 border-t-brand-bg rounded-full animate-spin"></span>
                <span>{activeTab === "login" ? "Signing In..." : "Creating Account..."}</span>
              </>
            ) : (
              <span>{activeTab === "login" ? "Sign In" : "Create Account"}</span>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}

export default Auth;
