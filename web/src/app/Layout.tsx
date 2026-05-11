import { Outlet, NavLink, useNavigate, useLocation, Link } from 'react-router-dom'
import { useAuthStore } from '@/features/auth/store'
import {
  Zap,
  Clock,
  Puzzle,
  Plug,
  CreditCard,
  Settings,
  LogOut,
} from 'lucide-react'
import { useThemeStore } from '@/shared/store/theme'
import { useEffect } from 'react'

const navItems = [
  { to: '/', icon: Zap, label: 'Workspace' },
  { to: '/tasks', icon: Clock, label: 'Tasks' },
  { to: '/skills', icon: Puzzle, label: 'Skills' },
  { to: '/connectors', icon: Plug, label: 'Connectors' },
  { to: '/billing', icon: CreditCard, label: 'Billing' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const isWorkspace = location.pathname === '/'
  const { theme } = useThemeStore()

  useEffect(() => {
    const root = window.document.documentElement
    root.classList.remove('light', 'dark')

    if (theme === 'system') {
      const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light'
      root.classList.add(systemTheme)
    } else {
      root.classList.add(theme)
    }
  }, [theme])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  if (isWorkspace) {
    return <Outlet />
  }

  return (
    <div className="flex h-screen bg-background text-foreground transition-colors duration-300 font-outfit">
      {/* Sidebar */}
      <aside className="w-64 bg-card border-r border-border flex flex-col relative z-20">
        <div className="p-8">
          <Link to="/" className="group flex items-center gap-3">
            <div className="w-10 h-10 premium-gradient rounded-xl flex items-center justify-center shadow-lg shadow-primary/20 group-hover:scale-110 transition-transform">
              <Zap className="w-6 h-6 text-white fill-current" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight">Cognix</h1>
              <p className="text-[10px] text-muted-foreground uppercase tracking-widest font-semibold">Agent OS</p>
            </div>
          </Link>
        </div>

        <nav className="flex-1 px-4 space-y-1.5">
          <div className="px-4 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
            Main Menu
          </div>
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm transition-all duration-200 group ${
                  isActive
                    ? 'bg-primary/10 text-primary border border-primary/20 shadow-sm shadow-primary/5'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`
              }
            >
              <Icon className={`w-4 h-4 transition-colors ${location.pathname === to ? 'text-primary' : 'group-hover:text-primary'}`} />
              <span className="font-medium">{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-border">
          <div className="bg-muted rounded-2xl p-4 border border-border">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-primary to-purple-500 p-[2px]">
                <div className="w-full h-full bg-card rounded-full flex items-center justify-center overflow-hidden">
                  <span className="text-sm font-bold text-foreground uppercase">
                    {user?.name?.[0] || user?.email?.[0] || '?'}
                  </span>
                </div>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-foreground truncate">{user?.name || 'User'}</p>
                <p className="text-[10px] text-muted-foreground truncate">{user?.email}</p>
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-card rounded-lg transition-all border border-transparent hover:border-border"
            >
              <LogOut className="w-3.5 h-3.5" />
              Sign Out
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto relative">
        {/* Background glow effects */}
        <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-primary/5 blur-[120px] -z-10 rounded-full" />
        <div className="absolute bottom-0 left-0 w-[300px] h-[300px] bg-purple-500/5 blur-[100px] -z-10 rounded-full" />
        
        <div className="p-10 max-w-7xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
