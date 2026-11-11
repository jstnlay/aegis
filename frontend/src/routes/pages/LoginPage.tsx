import { useState } from "react"
import { Link, Navigate, useNavigate } from "react-router-dom"
import {
  ArrowLeft,
  Eye,
  EyeOff,
  Loader2,
  Mail,
  LockKeyhole,
} from "lucide-react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/features/auth/AuthContext"
import { normalizeApiError } from "@/lib/error"
import { SCHOOL_NAME } from "@/lib/school-content"
import { HomepageBackground } from "@/components/brand/HomepageBackground"
import { PolicyWelcome } from "@/components/brand/PolicyWelcome"
import { hasAcknowledgedPolicies } from "@/lib/policy-acknowledgment"
import { LoginLegalPolicies } from "./LoginLegalPolicies"
import "./login-page.css"

const loginSchema = z.object({
  email: z
    .string()
    .min(1, "Email is required.")
    .email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
  /**
   * Document element 3, "Remember Me".
   *
   * It picks the session length and nothing else: ticked, the refresh token
   * lives a day; unticked, the session is idle-bounded at 15 minutes. The
   * password is never stored either way.
   */
  rememberMe: z.boolean(),
})

type LoginFormValues = z.infer<typeof loginSchema>

export function LoginPage() {
  const navigate = useNavigate()
  const [policiesAccepted, setPoliciesAccepted] = useState(
    hasAcknowledgedPolicies
  )
  const {
    status,
    isAuthenticated,
    mustChangePassword,
    sessionExpired,
    sessionEndedBy,
    login,
  } = useAuth()
  const [serverError, setServerError] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState(false)

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "", rememberMe: false },
    mode: "onBlur",
  })

  const isSubmitting = form.formState.isSubmitting

  if (isAuthenticated) {
    return <Navigate to="/app" replace />
  }

  if (mustChangePassword) {
    return <Navigate to="/change-password" replace />
  }

  if (status === "loading") {
    return null
  }

  async function onSubmit(values: LoginFormValues) {
    if (!policiesAccepted) return
    setServerError(null)
    try {
      await login(values.email, values.password, values.rememberMe)
    } catch (error) {
      const normalized = normalizeApiError(error)
      if (normalized.isCancelled) return
      setServerError(normalized.message)
    }
  }

  return (
    <div className="school-login-page school-brand-background">
      {!policiesAccepted ? (
        <PolicyWelcome
          open
          cancelLabel="Back to homepage"
          onCancel={() => {
            void navigate("/")
          }}
          onAccepted={() => setPoliciesAccepted(true)}
        />
      ) : null}
      <HomepageBackground />
      <div className="school-login-atmosphere" aria-hidden="true">
        <span className="school-login-orbit" />
        <span className="school-login-ribbon" />
      </div>
      <div className="school-login-mobile-art" aria-hidden="true">
        <svg viewBox="0 0 800 520" preserveAspectRatio="none" focusable="false">
          <path fill="#ead8ce" d="M0 0H800V270C590 470 260 230 0 470Z" />
          <path fill="#a64d57" d="M0 0H800V230C550 440 240 210 0 420Z" />
          <path fill="#7d202b" d="M0 0H800V185C560 390 260 190 0 365Z" />
          <path
            d="M-80 320C220 100 500 370 880 100M-80 292C220 72 500 342 880 72"
            fill="none"
            stroke="#dbb68d"
            strokeOpacity=".35"
          />
          <circle
            cx="730"
            cy="20"
            r="150"
            fill="none"
            stroke="#ffffff"
            strokeOpacity=".08"
          />
          <circle
            cx="730"
            cy="20"
            r="185"
            fill="none"
            stroke="#ffffff"
            strokeOpacity=".08"
          />
        </svg>
      </div>
      <Link
        to="/"
        className="school-login-corner-home"
        aria-label="Back to landing page"
      >
        <ArrowLeft aria-hidden="true" />
        Back to Home
      </Link>
      <aside className="school-login-visual" aria-label="Welcome to HIS CARE">
        <div className="school-login-welcome">
          <p className="school-login-welcome-school">
            HIS CARE CHRISTIAN INSTITUTE
          </p>
          <h2>
            Every step shapes
            <br />
            your future.
          </h2>
          <p className="school-login-welcome-message">
            Stay connected to your learning journey with AEGIS.
          </p>
        </div>
      </aside>
      <main className="school-login-main" aria-labelledby="login-title">
        <Card className="school-login-card">
          <CardHeader className="school-login-heading text-center">
            <div className="school-login-seal">
              <img
                src="/hcci-logo.png"
                alt={SCHOOL_NAME}
                className="size-full object-contain"
                width={381}
                height={377}
              />
            </div>
            <p className="school-login-mobile-brand">
              HIS CARE CHRISTIAN INSTITUTE
            </p>
            <h1 id="login-title">Sign in to AEGIS</h1>
            <p className="school-login-subtitle">
              Welcome to your learning space.
            </p>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form
                onSubmit={(e) => void form.handleSubmit(onSubmit)(e)}
                className="space-y-4"
                noValidate
                aria-busy={isSubmitting}
              >
                {/*
                PH11.11. `sessionExpired` is the explanation for arriving here
                without having signed out. `role="status"`, not `alert`: nothing
                failed because of a mistake, and the reader should not be
                interrupted — but they must be told, because the alternative is a
                bare sign-in form that looks like a normal visit while the page
                behind it has been unmounted along with any unsaved input. It is
                polite rather than silent because the user is mid-task, not
                debugging anything.

                The copy deliberately does not blame the user and does not blame
                the network: the refresh flow already exhausted its one retry
                before setting this, so "your session has ended, please sign in
                again" is what the code actually knows.

                PH11 QA cycle 2 (TC-GUI-05) splits the two causes, because one
                sentence cannot cover both honestly. A rotated refresh token is
                a credential that aged out; another account signing in on this
                browser is somebody else's action, and the affected user needs
                to know their session did not simply lapse — it was replaced,
                and this tab is no longer acting as the account it used to show.
                Saying only "your session has ended" would leave them thinking
                they had been idle too long.
              */}
                {sessionExpired ? (
                  <p
                    role="status"
                    className="rounded-sm border border-border bg-muted/60 px-3 py-2 text-sm text-muted-foreground"
                  >
                    {sessionEndedBy === "other-account"
                      ? "A different account signed in on this browser, so this session ended. Sign in again to continue."
                      : "Your session has ended. Please sign in again to continue."}
                  </p>
                ) : null}

                {serverError ? (
                  <div
                    role="alert"
                    className="rounded-sm border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive"
                  >
                    {serverError}
                  </div>
                ) : null}

                <FormField
                  control={form.control}
                  name="email"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Email</FormLabel>
                      <div className="school-login-field">
                        <Mail
                          className="school-login-field-icon"
                          aria-hidden="true"
                        />
                        <FormControl>
                          <Input
                            {...field}
                            type="email"
                            placeholder="your@email.com"
                            autoComplete="email"
                            inputMode="email"
                            disabled={isSubmitting}
                          />
                        </FormControl>
                      </div>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Password</FormLabel>
                      <div className="school-login-password school-login-field">
                        <LockKeyhole
                          className="school-login-field-icon"
                          aria-hidden="true"
                        />
                        <FormControl>
                          <Input
                            {...field}
                            type={showPassword ? "text" : "password"}
                            placeholder="Enter your password"
                            autoComplete="current-password"
                            autoCapitalize="none"
                            autoCorrect="off"
                            spellCheck={false}
                            disabled={isSubmitting}
                          />
                        </FormControl>
                        <button
                          type="button"
                          className="school-login-password-toggle"
                          aria-label={
                            showPassword ? "Hide password" : "Show password"
                          }
                          title={
                            showPassword ? "Hide password" : "Show password"
                          }
                          disabled={isSubmitting}
                          onClick={() => setShowPassword((visible) => !visible)}
                        >
                          {showPassword ? (
                            <EyeOff aria-hidden="true" />
                          ) : (
                            <Eye aria-hidden="true" />
                          )}
                        </button>
                      </div>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="flex items-center justify-between gap-3">
                  <FormField
                    control={form.control}
                    name="rememberMe"
                    render={({ field }) => (
                      <FormItem>
                        <div className="flex items-center gap-2">
                          <input
                            id="remember-me"
                            type="checkbox"
                            checked={field.value}
                            onChange={(event) =>
                              field.onChange(event.target.checked)
                            }
                            onBlur={field.onBlur}
                            disabled={isSubmitting}
                            className="size-4 shrink-0 rounded border-border accent-maroon-600"
                          />
                          <Label
                            htmlFor="remember-me"
                            className="text-sm font-normal text-muted-foreground"
                          >
                            Remember me
                          </Label>
                        </div>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  {/* Document element 4, "Forgot Password" link. */}
                  <Link
                    to="/forgot-password"
                    className="text-sm underline underline-offset-4 transition-colors hover:text-foreground"
                  >
                    Forgot password?
                  </Link>
                </div>

                <Button
                  type="submit"
                  className="w-full"
                  disabled={isSubmitting}
                >
                  {isSubmitting ? (
                    <>
                      <Loader2
                        className="size-4 animate-spin"
                        aria-hidden="true"
                      />
                      Signing in...
                    </>
                  ) : (
                    "Sign in"
                  )}
                </Button>
              </form>
            </Form>
            <div className="school-login-support">
              <p className="school-login-help">
                Need help signing in?{" "}
                <Link to="/#contact">Contact the school</Link>
              </p>
              <LoginLegalPolicies />
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  )
}
