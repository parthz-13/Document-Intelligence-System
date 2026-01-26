import { Routes, Route, Navigate } from "react-router-dom";
import Auth from "./pages/Auth";
import Home from "./pages/Home";
import Chat from "./pages/Chat";

function ProtectedRoute({ children }) {
  const token = localStorage.getItem("token");
  if (!token) {
    return <Navigate to="/" replace />;
  }
  return children;
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Auth />} />
      <Route
        path="/home"
        element={
          <ProtectedRoute>
            <Home />
          </ProtectedRoute>
        }
      />
      <Route
        path="/chat/:documentId"
        element={
          <ProtectedRoute>
            <Chat />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default App;
