import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Check,
  FileText,
  Globe2,
  History,
  Link2,
  MemoryStick,
  Plus,
  Search,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { useWorkspaceStore, type NotebookSource } from './store'

const EMPTY_FILES: WorkspaceFile[] = []
const EMPTY_ARTIFACTS: ArtifactSource[] = []

interface WorkspaceFile {
  name: string
  path: string
  is_dir: boolean
  size?: number
  modified_at?: string
}

interface ArtifactSource {
  id: string
  title: string
  artifact_type: string
  source: string
  updated_at: string
}

interface SourceItem {
  id: string
  kind: 'file' | 'url' | 'artifact' | 'memory'
  title: string
  subtitle: string
  selected: boolean
}

export function SourcesPanel({ workspaceId }: { workspaceId: string }) {
  const setNotebookSources = useWorkspaceStore((state) => state.setNotebookSources)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const [urlSources, setUrlSources] = useState<SourceItem[]>([])
  const [urlInput, setUrlInput] = useState('')

  const { data: files = EMPTY_FILES } = useQuery<WorkspaceFile[]>({
    queryKey: ['workspace-files', workspaceId, 'notebook-sources'],
    queryFn: () => api.get(`/workspaces/${workspaceId}/files`, { params: { path: '' } }).then((r) => r.data),
    enabled: !!workspaceId,
  })

  const { data: artifacts = EMPTY_ARTIFACTS } = useQuery<ArtifactSource[]>({
    queryKey: ['artifacts', workspaceId],
    queryFn: () => api.get(`/workspaces/${workspaceId}/artifacts`).then((r) => r.data),
    enabled: !!workspaceId,
  })

  const sources = useMemo<SourceItem[]>(() => {
    const fileSources = files
      .filter((file) => !file.is_dir)
      .map((file) => ({
        id: `file:${file.path}`,
        kind: 'file' as const,
        title: file.name,
        subtitle: file.path,
        selected: selected[`file:${file.path}`] ?? true,
      }))
    const artifactSources = artifacts.slice(0, 12).map((artifact) => ({
      id: `artifact:${artifact.id}`,
      kind: 'artifact' as const,
      title: artifact.title,
      subtitle: `${artifact.artifact_type} · ${artifact.source}`,
      selected: selected[`artifact:${artifact.id}`] ?? false,
    }))
    const memorySource: SourceItem = {
      id: 'memory:workspace',
      kind: 'memory',
      title: 'Workspace memory',
      subtitle: 'Hot, cold, procedural, and approved long-term context',
      selected: selected['memory:workspace'] ?? true,
    }
    return [memorySource, ...urlSources, ...fileSources, ...artifactSources]
  }, [artifacts, files, selected, urlSources])

  const filtered = search.trim()
    ? sources.filter((source) =>
        `${source.title} ${source.subtitle}`.toLowerCase().includes(search.toLowerCase()),
      )
    : sources

  const selectedCount = sources.filter((source) => source.selected).length

  useEffect(() => {
    const activeSources: NotebookSource[] = sources
      .filter((source) => source.selected)
      .map((source) => ({
        id: source.id,
        kind: source.kind,
        title: source.title,
        subtitle: source.subtitle,
      }))
    const currentSources = useWorkspaceStore.getState().notebookSources
    if (sameNotebookSources(currentSources, activeSources)) return
    setNotebookSources(activeSources)
  }, [setNotebookSources, sources])

  const addUrl = () => {
    const value = urlInput.trim()
    if (!value) return
    const item: SourceItem = {
      id: `url:${value}`,
      kind: 'url',
      title: value.replace(/^https?:\/\//, ''),
      subtitle: 'Web source for planning and browser automation',
      selected: true,
    }
    setUrlSources((current) => [item, ...current.filter((source) => source.id !== item.id)])
    setSelected((current) => ({ ...current, [item.id]: true }))
    setUrlInput('')
  }

  return (
    <aside className="flex h-full flex-col overflow-hidden rounded-[1.35rem] border border-border/70 bg-card shadow-sm">
      <div className="border-b border-border/70 px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Sources</h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              {selectedCount} selected for context
            </p>
          </div>
          <button className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-background text-muted-foreground hover:text-foreground">
            <Plus className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="space-y-3 border-b border-border/70 p-4">
        <div className="rounded-2xl border border-border bg-background/80 p-2">
          <div className="flex items-center gap-2">
            <Globe2 className="h-4 w-4 text-muted-foreground" />
            <input
              value={urlInput}
              onChange={(event) => setUrlInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') addUrl()
              }}
              placeholder="Add URL as source"
              className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground/60"
            />
            <button
              type="button"
              onClick={addUrl}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-foreground text-background hover:opacity-90"
            >
              <Link2 className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search sources"
            className="h-9 w-full rounded-full border border-border bg-background pl-9 pr-3 text-xs outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/15"
          />
        </div>
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto p-3 scrollbar-hide">
        {filtered.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-border p-6 text-center">
            <FileText className="mx-auto mb-2 h-6 w-6 text-muted-foreground/30" />
            <p className="text-xs font-semibold text-muted-foreground">No sources found</p>
          </div>
        ) : (
          filtered.map((source) => (
            <button
              key={source.id}
              type="button"
              onClick={() => setSelected((current) => ({ ...current, [source.id]: !source.selected }))}
              className="flex w-full items-center gap-3 rounded-2xl px-2.5 py-2.5 text-left transition-colors hover:bg-muted/55"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary/8 text-primary">
                <SourceIcon kind={source.kind} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-semibold text-foreground">{source.title}</div>
                <div className="mt-0.5 truncate text-[10px] text-muted-foreground">{source.subtitle}</div>
              </div>
              <span
                className={cn(
                  'flex h-5 w-5 shrink-0 items-center justify-center rounded-md border',
                  source.selected
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border bg-muted text-transparent',
                )}
              >
                <Check className="h-3.5 w-3.5" />
              </span>
            </button>
          ))
        )}
      </div>
    </aside>
  )
}

function sameNotebookSources(a: NotebookSource[], b: NotebookSource[]) {
  if (a.length !== b.length) return false
  return a.every((source, index) => {
    const other = b[index]
    return (
      source.id === other.id &&
      source.kind === other.kind &&
      source.title === other.title &&
      source.subtitle === other.subtitle
    )
  })
}

function SourceIcon({ kind }: { kind: SourceItem['kind'] }) {
  if (kind === 'url') return <Globe2 className="h-4 w-4" />
  if (kind === 'artifact') return <History className="h-4 w-4" />
  if (kind === 'memory') return <MemoryStick className="h-4 w-4" />
  return <FileText className="h-4 w-4" />
}
