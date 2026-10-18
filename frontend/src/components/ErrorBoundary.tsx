import { Component, type ErrorInfo, type ReactNode } from 'react'

/** Last line of defence: an unexpected render error shows a recoverable message, not a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI error', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="crash" role="alert">
        <h1>The interface hit an unexpected error.</h1>
        <p>Saved decisions, drafts and runs are stored in FalkorDB and are not affected.</p>
        <pre className="source-doc">{this.state.error.message}</pre>
        <button type="button" className="btn primary" onClick={() => window.location.reload()}>Reload the app</button>
      </div>
    )
  }
}
