import { useState } from "react"
import { Navigate } from "react-router-dom"
import { Loader2 } from "lucide-react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { useAuth } from "@/features/auth/AuthContext"
import { normalizeApiError } from "@/lib/error"
import { SCHOOL_NAME } from "@/lib/school-content"

const loginSchema = z.object({
  email: z
    .string()
    .min(1, "Email is required.")
    .email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
})

type LoginFormValues = z.infer<typeof loginSchema>

export function LoginPage() {
  const {
    status,
    isAuthenticated,
    mustChangePassword,
    sessionExpired,
    sessionEndedBy,
    login,
  } = useAuth()
  const [serverError, setServerError] = useState<string | null>(null)

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
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
    setServerError(null)
    try {
      await login(values.email, values.password)
    } catch (error) {
      const normalized = normalizeApiError(error)
      if (normalized.isCancelled) return
      setServerError(normalized.message)
    }
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-background px-4 py-10">
      <Card className="w-full max-w-md">
        <CardHeader className="gap-2 text-center">
          <div className="mx-auto size-14 overflow-hidden rounded-md border border-border">
            <img
              src="/hcci-logo.png"
              alt={SCHOOL_NAME}
              className="size-full object-cover"
            />
          </div>
          <h1 className="text-xl font-bold text-foreground">
            Sign in to AEGIS
          </h1>
          <CardDescription>
            Academic Governance and Intervention System
          </CardDescription>
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
                    <FormControl>
                      <Input
                        {...field}
                        type="email"
                        placeholder="you@school.edu"
                        autoComplete="email"
                        inputMode="email"
                        disabled={isSubmitting}
                      />
                    </FormControl>
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
                    <FormControl>
                      <Input
                        {...field}
                        type="password"
                        placeholder="Enter your password"
                        autoComplete="current-password"
                        disabled={isSubmitting}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <Button type="submit" className="w-full" disabled={isSubmitting}>
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
        </CardContent>
      </Card>
    </div>
  )
}
