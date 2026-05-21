import { useEffect, useId, useMemo, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import 'highlight.js/styles/github-dark.css'
import 'katex/dist/katex.min.css'

interface RichMessageProps {
  content: string
  compact?: boolean
}

function MermaidBlock({ code }: { code: string }) {
  const id = useId().replace(/:/g, '')
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    import('mermaid')
      .then(({ default: mermaid }) => {
        mermaid.initialize({
          startOnLoad: false,
          theme: document.documentElement.classList.contains('dark') ? 'dark' : 'default',
          securityLevel: 'strict',
        })
        return mermaid.render(`mermaid-${id}`, code)
      })
      .then(({ svg }) => {
        if (!cancelled && ref.current) ref.current.innerHTML = svg
      })
      .catch(() => {
        if (!cancelled && ref.current) {
          ref.current.textContent = code
        }
      })
    return () => {
      cancelled = true
    }
  }, [code, id])

  return (
    <div className="my-4 overflow-x-auto rounded-xl border border-border bg-background p-4">
      <div ref={ref} className="min-w-fit" />
    </div>
  )
}

export function RichMessage({ content, compact = false }: RichMessageProps) {
  const plugins = useMemo(() => [remarkGfm, remarkMath], [])
  const rehypePlugins = useMemo(() => [rehypeKatex, rehypeHighlight], [])
  const normalizedContent = useMemo(
    () => content.replace(/(^|\n)\s*•\s+/g, '$1- '),
    [content],
  )

  if (!content) return null

  return (
    <div className={compact ? 'rich-message rich-message-compact' : 'rich-message'}>
      <ReactMarkdown
        remarkPlugins={plugins}
        rehypePlugins={rehypePlugins}
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '')
            const language = match?.[1]
            const code = String(children).replace(/\n$/, '')
            if (language === 'mermaid') {
              return <MermaidBlock code={code} />
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            )
          },
          a({ children, ...props }) {
            return (
              <a {...props} target="_blank" rel="noreferrer">
                {children}
              </a>
            )
          },
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  )
}
