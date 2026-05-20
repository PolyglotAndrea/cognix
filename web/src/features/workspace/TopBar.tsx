import { useState, useRef, useEffect, Suspense } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Puzzle, Download, Settings, Clock, CreditCard, LogOut, Zap, Moon, Sun, Monitor } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '@/shared/api/client'
import { useAuthStore } from '@/features/auth/store'
import { useThemeStore } from '@/shared/store/theme'
import { Modal, Spinner } from '@/shared/ui'
import { useCurrentWorkspace } from './useCurrentWorkspace'

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
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [themeMenuOpen, setThemeMenuOpen] = useState(false)
  const [activeModal, setActiveModal] = useState<ModalType>(null)
  
  const dropdownRef = useRef<HTMLDivElement>(null)
  const themeRef = useRef<HTMLDivElement>(null)
  const settingsRef = useRef<HTMLDivElement>(null)
  const user = useAuthStore((s) => s.user)
  const { logout } = useAuthStore()
  const { theme, setTheme } = useThemeStore()
  const { workspaces, workspace, setSelectedWorkspace } = useCurrentWorkspace()
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
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) {
        setSettingsOpen(false)
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

        <div
          className="hidden lg:flex h-10 min-w-0 max-w-sm items-center gap-2 rounded-xl border border-border bg-muted/50 px-3 shadow-sm shadow-black/5 shrink-0"
          title={workspace?.path || 'No workspace selected'}
        >
          <span className="text-[9px] font-black uppercase tracking-[0.18em] text-muted-foreground/50">
            Workspace
          </span>
          <div className="h-4 w-px bg-border/70" />
          <select
            value={workspace?.id || ''}
            onChange={(event) => setSelectedWorkspace(event.target.value || null)}
            className="h-8 min-w-0 max-w-44 bg-transparent pr-7 text-xs font-semibold text-foreground outline-none"
            aria-label="Current workspace"
          >
            {workspaces.length === 0 ? (
              <option value="">No workspace</option>
            ) : (
              workspaces.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))
            )}
          </select>
        </div>

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
        <div className="flex items-center gap-4 shrink-0">
          <div className="flex items-center gap-1 px-1.5 py-1 bg-muted/50 rounded-xl border border-border/50">
            <div className="relative" ref={themeRef}>
              <button
                onClick={() => setThemeMenuOpen(!themeMenuOpen)}
                className={`p-2 rounded-lg transition-all ${themeMenuOpen ? 'bg-background text-primary shadow-sm' : 'text-muted-foreground hover:text-foreground hover:bg-background/80'}`}
                title="Switch theme"
              >
                <CurrentThemeIcon className="h-4 w-4" />
              </button>

              {themeMenuOpen && (
                <div className="absolute top-full right-0 mt-3 w-44 bg-card border border-border rounded-2xl shadow-2xl z-[90] p-1.5 animate-in fade-in zoom-in-95 slide-in-from-top-2 duration-200">
                  <div className="px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest border-b border-border/50 mb-1">
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

            <div className="w-px h-4 bg-border/50 mx-1" />

            <div className="relative" ref={settingsRef}>
              <button
                onClick={() => setSettingsOpen(!settingsOpen)}
                className={`p-2 rounded-lg transition-all ${settingsOpen ? 'bg-background text-primary shadow-sm' : 'text-muted-foreground hover:text-foreground hover:bg-background/80'}`}
                title="Settings & Tools"
              >
                <Settings className="h-4 w-4" />
              </button>

              {settingsOpen && (
                <div className="absolute top-full right-0 mt-3 w-56 bg-card border border-border rounded-2xl shadow-2xl z-[90] p-1.5 animate-in fade-in zoom-in-95 slide-in-from-top-2 duration-200">
                  <div className="px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest border-b border-border/50 mb-1">
                    Platform Modules
                  </div>
                  <div className="space-y-0.5">
                    <button
                      onClick={() => {
                        setActiveModal('tasks')
                        setSettingsOpen(false)
                      }}
                      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted transition-all group"
                    >
                      <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center text-blue-500 group-hover:bg-blue-500 group-hover:text-white transition-colors shadow-sm">
                        <Clock className="h-4 w-4" />
                      </div>
                      <div className="flex-1 text-left">
                        <div className="font-bold">Scheduled Tasks</div>
                        <div className="text-[10px] font-medium opacity-60">Automation & Cron</div>
                      </div>
                    </button>

                    <button
                      onClick={() => {
                        setActiveModal('billing')
                        setSettingsOpen(false)
                      }}
                      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted transition-all group"
                    >
                      <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-500 group-hover:bg-emerald-500 group-hover:text-white transition-colors shadow-sm">
                        <CreditCard className="h-4 w-4" />
                      </div>
                      <div className="flex-1 text-left">
                        <div className="font-bold">Billing & Usage</div>
                        <div className="text-[10px] font-medium opacity-60">Plans & Invoices</div>
                      </div>
                    </button>

                    <button
                      onClick={() => {
                        setActiveModal('settings')
                        setSettingsOpen(false)
                      }}
                      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted transition-all group"
                    >
                      <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-500 group-hover:bg-indigo-500 group-hover:text-white transition-colors shadow-sm">
                        <Settings className="h-4 w-4" />
                      </div>
                      <div className="flex-1 text-left">
                        <div className="font-bold">Workspace Settings</div>
                        <div className="text-[10px] font-medium opacity-60">Models & Memory</div>
                      </div>
                    </button>
                  </div>

                  <div className="mt-1 pt-1 border-t border-border/50">
                    <button
                      onClick={handleLogout}
                      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-bold text-rose-500 hover:bg-rose-500/10 transition-all"
                    >
                      <div className="w-8 h-8 rounded-lg bg-rose-500/10 flex items-center justify-center">
                        <LogOut className="h-4 w-4" />
                      </div>
                      Sign Out
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            <button 
              onClick={() => {
                setActiveModal('settings')
                setSettingsOpen(false)
              }}
              className="w-9 h-9 rounded-xl bg-gradient-to-tr from-primary to-indigo-600 p-[1.5px] hover:scale-105 active:scale-95 transition-all cursor-pointer shadow-lg shadow-primary/20 flex items-center justify-center"
            >
              <div className="w-full h-full bg-card rounded-[10px] flex items-center justify-center group overflow-hidden relative">
                <div className="absolute inset-0 bg-primary/0 group-hover:bg-primary/5 transition-colors" />
                <span className="text-xs font-bold text-foreground relative z-10">
                  {(user?.name || user?.email || '?')[0].toUpperCase()}
                </span>
              </div>
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
        title="Workspace Settings"
        size="xl"
      >
        <Suspense fallback={<div className="py-20 flex flex-col items-center gap-4 text-muted-foreground"><Spinner /><p className="text-sm animate-pulse">Accessing runtime settings...</p></div>}>
          <SettingsPage scope="workspace" />
        </Suspense>
      </Modal>
    </>
  )
}
