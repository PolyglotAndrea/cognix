import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2, CheckCircle2, XCircle } from 'lucide-react'
import { api } from '@/shared/api/client'

export default function ConnectorOAuthCallback() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
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

    // Parse platform from state or URL path
    // State format: {random}:{workspace_id} — platform is inferred from the authorize call
    // We need to determine the platform. Store it in sessionStorage before redirect.
    const platform = sessionStorage.getItem('connector_oauth_platform')
    if (!platform) {
      setStatus('error')
      setMessage('Platform not found in session. Please try connecting again.')
      return
    }

    api
      .post(`/connectors/oauth/${platform}/callback`, { code, state })
      .then(() => {
        setStatus('success')
        setMessage(`Successfully connected to ${platform}!`)
        sessionStorage.removeItem('connector_oauth_platform')
        setTimeout(() => navigate('/connectors'), 1500)
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
