import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react'
import { api } from '@/shared/api/client'

export default function ConnectorOAuthCallback() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState<'loading' | 'success' | 'warning' | 'error'>('loading')
  const [message, setMessage] = useState('')

  useEffect(() => {
    const code = searchParams.get('code')
    const state = searchParams.get('state')
    const error = searchParams.get('error')

    if (error) {
      setStatus('error')
      setMessage(searchParams.get('error_description') || 'Authorization denied')
      return
    }

    if (!code || !state) {
      setStatus('error')
      setMessage('Missing authorization code or state')
      return
    }

    const platform = sessionStorage.getItem('connector_oauth_platform')
    if (!platform) {
      setStatus('error')
      setMessage('Platform not found in session. Please try connecting again.')
      return
    }

    api
      .post(`/connectors/oauth/${platform}/callback`, { code, state })
      .then((res) => {
        sessionStorage.removeItem('connector_oauth_platform')
        if (res.data.missing_scopes?.length) {
          setStatus('warning')
          setMessage(res.data.warning || `Connected but missing scopes: ${res.data.missing_scopes.join(', ')}`)
        } else {
          setStatus('success')
          setMessage(`Successfully connected to ${platform}!`)
        }
        setTimeout(() => navigate('/connectors'), 2500)
      })
      .catch((err) => {
        setStatus('error')
        setMessage(err?.response?.data?.detail || 'Failed to complete connection')
      })
  }, [searchParams, navigate])

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-8 text-center">
        {status === 'loading' && (
          <>
            <Loader2 className="mx-auto h-10 w-10 animate-spin text-primary" />
            <h3 className="mt-4 text-lg font-bold text-foreground">Connecting...</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Completing the authorization flow
            </p>
          </>
        )}
        {status === 'success' && (
          <>
            <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-500" />
            <h3 className="mt-4 text-lg font-bold text-foreground">Connected!</h3>
            <p className="mt-2 text-sm text-muted-foreground">{message}</p>
          </>
        )}
        {status === 'warning' && (
          <>
            <AlertTriangle className="mx-auto h-10 w-10 text-amber-500" />
            <h3 className="mt-4 text-lg font-bold text-foreground">Connected with warnings</h3>
            <p className="mt-2 text-sm text-muted-foreground">{message}</p>
            <p className="mt-1 text-xs text-muted-foreground/70">
              Some features may not work. You can re-authorize to grant missing permissions.
            </p>
          </>
        )}
        {status === 'error' && (
          <>
            <XCircle className="mx-auto h-10 w-10 text-rose-500" />
            <h3 className="mt-4 text-lg font-bold text-foreground">Connection Failed</h3>
            <p className="mt-2 text-sm text-muted-foreground">{message}</p>
            <button
              onClick={() => navigate('/connectors')}
              className="mt-4 text-sm font-medium text-primary hover:underline"
            >
              Back to Connectors
            </button>
          </>
        )}
      </div>
    </div>
  )
}
