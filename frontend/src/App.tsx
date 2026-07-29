import { Route, Routes } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { ToastProvider } from "./components/Toast";
import { Overview } from "./pages/Overview";
import { Accounts } from "./pages/Accounts";
import { Transactions } from "./pages/Transactions";
import { Budgets } from "./pages/Budgets";
import { Import } from "./pages/Import";
import { History } from "./pages/History";
import { Settings } from "./pages/Settings";

export function App() {
  return (
    <ToastProvider>
      <div className="app">
        <Sidebar />
        <div className="main">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/accounts" element={<Accounts />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/budgets" element={<Budgets />} />
            <Route path="/import" element={<Import />} />
            <Route path="/history" element={<History />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </div>
      </div>
    </ToastProvider>
  );
}
