import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import { Clock, Play, Pause, Trash2 } from 'lucide-react'
import { Badge } from '@/shared/ui'

export default function TaskList() {
  const { data: tasks, isLoading } = useQuery({
    queryKey: ['tasks'],
    queryFn: () => api.get('/tasks').then((r) => r.data),
  })

  return (
    <div className="animate-in fade-in duration-500 font-outfit">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-bold text-foreground tracking-tight">Scheduled Tasks</h2>
          <p className="text-muted-foreground mt-1 text-sm">Monitor and manage your automated agent workflows.</p>
        </div>
        <button className="premium-gradient text-white px-5 py-2.5 rounded-xl text-sm font-bold shadow-lg shadow-primary/20 hover:scale-105 transition-all active:scale-95">
          New Task
        </button>
      </div>

      {isLoading ? (
        <div className="text-center py-24 bg-card rounded-3xl border border-border backdrop-blur-xl">
           <div className="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin mx-auto mb-4" />
           <p className="text-muted-foreground font-medium">Synchronizing task scheduler...</p>
        </div>
      ) : tasks?.length ? (
        <div className="bg-card rounded-3xl shadow-2xl border border-border overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="bg-muted/50 border-b border-border">
                <th className="px-8 py-5 text-left text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em]">Name</th>
                <th className="px-8 py-5 text-left text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em]">Type</th>
                <th className="px-8 py-5 text-left text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em]">Schedule</th>
                <th className="px-8 py-5 text-left text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em]">State</th>
                <th className="px-8 py-5 text-left text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em]">Runs</th>
                <th className="px-8 py-5 text-right text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em]">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {tasks.map((task: any) => (
                <tr key={task.id} className="group hover:bg-muted/30 transition-colors">
                  <td className="px-8 py-5">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 bg-muted rounded-xl flex items-center justify-center border border-border group-hover:border-primary/30 transition-colors">
                        <Clock className="w-5 h-5 text-primary/70 group-hover:text-primary" />
                      </div>
                      <span className="font-bold text-foreground group-hover:text-primary transition-colors">{task.name}</span>
                    </div>
                  </td>
                  <td className="px-8 py-5">
                    <Badge variant="default" className="bg-muted border-border text-muted-foreground">{task.task_type}</Badge>
                  </td>
                  <td className="px-8 py-5 text-sm text-muted-foreground font-mono font-medium">{task.schedule}</td>
                  <td className="px-8 py-5">
                    <Badge variant={task.state === 'active' ? 'success' : task.state === 'paused' ? 'warning' : 'default'}>
                      {task.state}
                    </Badge>
                  </td>
                  <td className="px-8 py-5">
                    <div className="flex items-center gap-2">
                       <div className="w-1.5 h-1.5 rounded-full bg-primary/40" />
                       <span className="text-sm font-bold text-foreground">{task.run_count}</span>
                    </div>
                  </td>
                  <td className="px-8 py-5 text-right">
                    <div className="flex items-center justify-end gap-3 opacity-0 group-hover:opacity-100 transition-opacity">
                      {task.state === 'active' ? (
                        <button className="w-9 h-9 flex items-center justify-center text-muted-foreground hover:text-amber-500 hover:bg-amber-500/10 rounded-xl transition-all border border-transparent hover:border-amber-500/20">
                          <Pause className="w-4 h-4" />
                        </button>
                      ) : (
                        <button className="w-9 h-9 flex items-center justify-center text-muted-foreground hover:text-emerald-500 hover:bg-emerald-500/10 rounded-xl transition-all border border-transparent hover:border-emerald-500/20">
                          <Play className="w-4 h-4" />
                        </button>
                      )}
                      <button className="w-9 h-9 flex items-center justify-center text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 rounded-xl transition-all border border-transparent hover:border-rose-500/20">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-center py-24 bg-card rounded-[2.5rem] border border-border relative overflow-hidden group">
          <div className="absolute inset-0 bg-primary/5 opacity-0 group-hover:opacity-100 transition-opacity blur-3xl -z-10 rounded-full scale-50" />
          <div className="w-20 h-20 bg-muted rounded-3xl flex items-center justify-center mx-auto mb-6 border border-border shadow-2xl transition-transform group-hover:scale-110">
            <Clock className="w-10 h-10 text-muted-foreground/20" />
          </div>
          <h3 className="text-xl font-bold text-foreground mb-2">No Scheduled Tasks</h3>
          <p className="text-muted-foreground max-w-xs mx-auto leading-relaxed">Automate your agents by creating one-shot or recurring task schedules.</p>
          <button className="mt-8 bg-muted hover:bg-card text-foreground px-6 py-3 rounded-xl text-sm font-bold border border-border transition-all">
             Initialize First Task
          </button>
        </div>
      )}
    </div>
  )
}
