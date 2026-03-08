import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ChatProvider } from "./context/ChatContext";
import { ProtectedRoute } from "./components/layout/ProtectedRoute";
import { AppLayout } from "./components/layout/AppLayout";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { EventExplorerPage } from "./pages/EventExplorerPage";
import { NodesPage } from "./pages/NodesPage";
import { LogsPage } from "./pages/LogsPage";
import { AIInsightsPage } from "./pages/AIInsightsPage";
import { ResourceAllocationPage } from "./pages/ResourceAllocationPage";
import { JvmDetailsPage } from "./pages/JvmDetailsPage";
import { NetworkLatencyPage } from "./pages/NetworkLatencyPage";
import { SettingsPage } from "./pages/SettingsPage";

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <ProtectedRoute>
                <ChatProvider>
                  <AppLayout />
                </ChatProvider>
              </ProtectedRoute>
            }
          >
            <Route path="/" element={<DashboardPage />} />
            <Route path="/events" element={<EventExplorerPage />} />
            <Route path="/nodes" element={<NodesPage />} />
            <Route path="/logs" element={<LogsPage />} />
            <Route path="/resources" element={<ResourceAllocationPage />} />
            <Route path="/jvm" element={<JvmDetailsPage />} />
            <Route path="/network" element={<NetworkLatencyPage />} />
            <Route path="/ai-insights" element={<AIInsightsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
