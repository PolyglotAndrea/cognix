import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/features/auth/store'
import Layout from './Layout'
import LoginPage from '@/features/auth/LoginPage'
import Dashboard from '@/features/auth/Dashboard'
import AgentList from '@/features/agents/AgentList'
import AgentDetail from '@/features/agents/AgentDetail'
import TaskList from '@/features/tasks/TaskList'
import SkillList from '@/features/skills/SkillList'
import BillingPage from '@/features/billing/BillingPage'
import SettingsPage from '@/features/settings/SettingsPage'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="agents" element={<AgentList />} />
        <Route path="agents/:id" element={<AgentDetail />} />
        <Route path="tasks" element={<TaskList />} />
        <Route path="skills" element={<SkillList />} />
        <Route path="billing" element={<BillingPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  )
}
