import { Component, type ErrorInfo, type ReactNode } from "react"

import { Button } from "@/components/ui/button"

/**
 * Application-level error boundary.
 *
 * Without one, a single malformed record — an object handed to React as a
 * child, an undefined access on a partially-populated row — throws during
 * render and unmounts the *entire* SPA, leaving the user on a blank page and
 * forcing a full reload. Two boundaries are mounted:
 *
 * - around `<Outlet />` in `AppShell`, so the sidebar, header and routing
 *   survive a page-level failure and the user can navigate somewhere else
 *   instead of being stranded;
 * - around the whole tree in `main.tsx`, as the last resort before React tears
 *   down `#root`.
 *
 * `resetKeys` clears a caught error when one of its values changes, so moving
 * to another route recovers without a reload even though the boundary keeps its
 * state. Navigating to the *same* broken URL again will not reset, because the
 * key did not change — that case is the Retry button's job.
 */
interface ErrorBoundaryProps {
  children: ReactNode
  /** Changing any of these clears a caught error. */
  resetKeys?: readonly unknown[]
  /** Short description of the area that failed, shown in the recovery state. */
  label?: string
  /** Custom recovery UI. Receives `reset`, which clears the error. */
  fallback?: (reset: () => void, error: Error) => ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Always logged, in every environment: this is the only place the real
    // stack and component trace survive, and a swallowed render error is
    // undiagnosable. The UI copy below is what differs.
    console.error(
      "[aegis] render error caught by ErrorBoundary",
      error,
      info.componentStack
    )
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps): void {
    if (this.state.error === null) return
    if (prevProps.resetKeys?.length !== this.props.resetKeys?.length) return
    const changed = this.props.resetKeys?.some(
      (key, index) => !Object.is(key, prevProps.resetKeys?.[index])
    )
    if (changed) this.reset()
  }

  reset = (): void => {
    this.setState({ error: null })
  }

  render(): ReactNode {
    const { error } = this.state
    if (error === null) return this.props.children

    if (this.props.fallback) {
      return this.props.fallback(this.reset, error)
    }

    return (
      <div
        role="alert"
        className="mx-auto flex w-full max-w-2xl flex-col gap-4 rounded-lg border border-destructive/40 bg-destructive/5 p-6"
      >
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-foreground">
            {this.props.label
              ? `${this.props.label} could not be displayed`
              : "This page could not be displayed"}
          </h2>
          <p className="text-sm text-muted-foreground">
            The rest of the application is still available. Use the navigation
            to continue, or try this view again.
          </p>
        </div>

        <p className="text-sm text-destructive">{error.message}</p>

        {/*
          Development diagnostics are shown, not hidden: the component stack is
          what identifies the offending record. Production shows the message
          only, because a stack is noise for an end user and may name internal
          component paths.
        */}
        {import.meta.env.DEV ? (
          <details className="rounded-md border border-border bg-muted/40 p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Diagnostics
            </summary>
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs text-muted-foreground">
              {error.stack ?? "No stack available."}
            </pre>
          </details>
        ) : null}

        <div className="flex gap-2">
          <Button onClick={this.reset}>Try again</Button>
          <Button variant="outline" onClick={() => window.location.reload()}>
            Reload the page
          </Button>
        </div>
      </div>
    )
  }
}
