import { useState, useRef, useEffect, Suspense } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Puzzle, Download, Settings, Clock, CreditCard, LogOut, Zap, Moon, Sun, Monitor } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '@/shared/api/client'
import { useAuthStore } from '@/features/auth/store'
import { useThemeStore } from '@/shared/store/theme'
import { Modal, Spinner } from '@/shared/ui'

// Direct imports to avoid potential lazy loading issues in dev
import TaskList from '@/features/tasks/TaskList'
import BillingPage from '@/features/billing/BillingPage'
import SettingsPage from '@/features/settings/SettingsPage'

interface Skill {
  id: number
  name: string
  version: string
  description: string
  tags: string
}

type ModalType = 'tasks' | 'billing' | 'settings' | null

export function TopBar() {
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [themeMenuOpen, setThemeMenuOpen] = useState(false)
  const [activeModal, setActiveModal] = useState<ModalType>(null)
  
  const dropdownRef = useRef<HTMLDivElement>(null)
  const themeRef = useRef<HTMLDivElement>(null)
  const user = useAuthStore((s) => s.user)
  const { logout } = useAuthStore()
  const { theme, setTheme } = useThemeStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const { data: skills = [] } = useQuery<Skill[]>({
    queryKey: ['skills'],
    queryFn: () => api.get('/skills').then((r) => r.data),
  })

  const filtered = search.trim()
    ? skills.filter(
        (s) =>
          s.name.toLowerCase().includes(search.toLowerCase()) ||
          s.description?.toLowerCase().includes(search.toLowerCase()) ||
          s.tags?.toLowerCase().includes(search.toLowerCase())
      )
    : skills

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
      if (themeRef.current && !themeRef.current.contains(e.target as Node)) {
        setThemeMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const themeIcons = {
    light: Sun,
    dark: Moon,
    system: Monitor,
  }
  const CurrentThemeIcon = themeIcons[theme]

  return (
    <>
      <header className="h-14 border-b border-border bg-background/95 backdrop-blur-md flex items-center px-6 gap-6 shrink-0 relative z-[70]">
        {/* Brand */}
        <Link to="/" className="flex items-center gap-2.5 shrink-0 group">
          <div className="w-8 h-8 premium-gradient rounded-lg flex items-center justify-center shadow-lg shadow-primary/20 group-hover:scale-105 transition-transform">
            <Zap className="w-5 h-5 text-white fill-current" />
          </div>
          <span className="font-bold text-foreground text-base tracking-tight">Cognix</span>
        </Link>

        {/* Skills Search */}
        <div className="flex-1 flex justify-center" ref={dropdownRef}>
          <div className="relative w-full max-w-xl">
            <div className="relative group">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
              <input
                type="text"
                placeholder="Search skills, tools, or agents..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setOpen(true)
                }}
                onFocus={() => setOpen(true)}
                className="w-full pl-10 pr-4 py-2 text-sm border border-border rounded-xl bg-muted/50 hover:bg-muted focus:bg-card focus:ring-2 focus:ring-primary/20 focus:border-primary/40 outline-none transition-all placeholder:text-muted-foreground/50 text-foreground"
              />
            </div>

            {/* Dropdown */}
            {open && (
              <div className="absolute top-full left-0 right-0 mt-2 bg-card rounded-2xl shadow-2xl shadow-black/20 border border-border max-h-[480px] overflow-auto z-[80] p-2 animate-in fade-in slide-in-from-top-1">
                {filtered.length === 0 ? (
                  <div className="px-4 py-12 text-center">
                    <Puzzle className="h-8 w-8 text-muted-foreground/20 mx-auto mb-3" />
                    <p className="text-sm text-muted-foreground font-medium">No skills found matching your search</p>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <div className="px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
                      Available Skills
                    </div>
                    {filtered.map((skill) => (
                      <div
                        key={skill.id}
                        className="group px-3 py-3 hover:bg-muted rounded-xl border border-transparent hover:border-border transition-all cursor-pointer"
                      >
                        <div className="flex items-center justify-between gap-4">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-9 h-9 bg-primary/10 rounded-lg flex items-center justify-center shrink-0 border border-primary/20 group-hover:bg-primary/20 transition-colors">
                              <Puzzle className="h-5 w-5 text-primary" />
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-semibold text-foreground truncate">
                                  {skill.name}
                                </span>
                                <span className="text-[10px] bg-muted text-muted-foreground rounded-md px-1.5 py-0.5 border border-border">
                                  v{skill.version}
                                </span>
                              </div>
                              {skill.description && (
                                <p className="text-xs text-muted-foreground mt-0.5 truncate">{skill.description}</p>
                              )}
                            </div>
                          </div>
                          <button
                            className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider rounded-lg bg-primary/10 text-primary border border-primary/20 hover:bg-primary hover:text-white transition-all shadow-sm shadow-primary/10"
                            onClick={(e) => {
                              e.stopPropagation()
                            }}
                          >
                            <Download className="h-3 w-3" />
                            Install
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right: theme + nav links + user */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="flex items-center gap-1 mr-2 px-2 py-1 bg-muted rounded-xl border border-border">
            <div className="relative" ref={themeRef}>
              <button
                onClick={() => setThemeMenuOpen(!themeMenuOpen)}
                className={`p-2 rounded-lg transition-colors ${themeMenuOpen ? 'bg-background text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-background'}`}
                title="Switch theme"
              >
                <CurrentThemeIcon className="h-4 w-4" />
              </button>

              {themeMenuOpen && (
                <div className="absolute top-full right-0 mt-3 w-44 bg-card border border-border rounded-2xl shadow-2xl z-[90] p-1.5 animate-in fade-in zoom-in-95 slide-in-from-top-2 duration-200">
                  <div className="px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest border-b border-border mb-1">
                    Appearance
                  </div>
                  {(['light', 'dark', 'system'] as const).map((t) => {
                    const Icon = themeIcons[t]
                    return (
                      <button
                        key={t}
                        onClick={() => {
                          setTheme(t)
                          setThemeMenuOpen(false)
                        }}
                        className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-semibold transition-all ${
                          theme === t
                            ? 'bg-primary/10 text-primary shadow-sm shadow-primary/5'
                            : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                        }`}
                      >
                        <Icon className={`h-4 w-4 ${theme === t ? 'text-primary' : ''}`} />
                        <span className="capitalize">{t} Mode</span>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

            <div className="w-px h-4 bg-border mx-1" />

            {[
              { type: 'tasks' as const, icon: Clock, title: 'Tasks' },
              { type: 'billing' as const, icon: CreditCard, title: 'Billing' },
              { type: 'settings' as const, icon: Settings, title: 'Settings' },
            ].map((item) => (
              <button
                key={item.type}
                onClick={() => setActiveModal(item.type)}
                className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-background transition-colors"
                title={item.title}
              >
                <item.icon className="h-4 w-4" />
              </button>
            ))}
          </div>
          
          <div className="flex items-center gap-3 pl-2 border-l border-border">
            <button 
              onClick={() => setActiveModal('settings')}
              className="w-8 h-8 rounded-full bg-gradient-to-tr from-primary to-purple-500 p-[1px] hover:scale-110 active:scale-95 transition-all cursor-pointer shadow-lg shadow-primary/20"
            >
              <div className="w-full h-full bg-card rounded-full flex items-center justify-center">
                <span className="text-xs font-bold text-foreground">
                  {(user?.name || user?.email || '?')[0].toUpperCase()}
                </span>
              </div>
            </button>
            <button
              onClick={handleLogout}
              className="p-2 rounded-lg text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 transition-all border border-transparent hover:border-rose-500/20"
              title="Logout"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Modals */}
      <Modal 
        isOpen={activeModal === 'tasks'} 
        onClose={() => setActiveModal(null)} 
        title="Scheduled Tasks"
        size="xl"
      >
        <Suspense fallback={<div className="py-20 flex flex-col items-center gap-4 text-muted-foreground"><Spinner /><p className="text-sm animate-pulse">Initializing tasks...</p></div>}>
          <TaskList />
        </Suspense>
      </Modal>

      <Modal 
        isOpen={activeModal === 'billing'} 
        onClose={() => setActiveModal(null)} 
        title="Subscription & Billing"
        size="lg"
      >
        <Suspense fallback={<div className="py-20 flex flex-col items-center gap-4 text-muted-foreground"><Spinner /><p className="text-sm animate-pulse">Loading billing details...</p></div>}>
          <BillingPage />
        </Suspense>
      </Modal>

      <Modal 
        isOpen={activeModal === 'settings'} 
        onClose={() => setActiveModal(null)} 
        title="Account Settings"
        size="lg"
      >
        <Suspense fallback={<div className="py-20 flex flex-col items-center gap-4 text-muted-foreground"><Spinner /><p className="text-sm animate-pulse">Accessing security settings...</p></div>}>
          <SettingsPage />
        </Suspense>
      </Modal>
    </>
  )
}
