import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/features/auth/store'
import Layout from './Layout'
import LoginPage from '@/features/auth/LoginPage'
import { Workspace } from '@/features/workspace/Workspace'
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

      {/* All authenticated routes share the Layout */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Workspace />} />
        <Route path="tasks" element={<TaskList />} />
        <Route path="skills" element={<SkillList />} />
        <Route path="billing" element={<BillingPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  )
}
