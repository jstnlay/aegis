import { useEffect, useRef, useState } from "react"
import { Navigate, Link } from "react-router-dom"
import { KeyRound, Loader2, CheckCircle2 } from "lucide-react"
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

const changePasswordSchema = z
  .object({
    current_password: z.string().min(1, "Current password is required."),
    new_password: z
      .string()
      .min(1, "New password is required.")
      .min(8, "Password must be at least 8 characters."),
    confirm_password: z.string().min(1, "Please confirm your new password."),
  })
  .refine((data) => data.new_password === data.confirm_password, {
    message: "Passwords do not match.",
    path: ["confirm_password"],
  })

type ChangePasswordFormValues = z.infer<typeof changePasswordSchema>

export function ChangePasswordPage() {
  const {
    status,
    isAuthenticated,
    mustChangePassword,
    changePassword,
    logout,
  } = useAuth()
  const [serverError, setServerError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const successHeadingRef = useRef<HTMLHeadingElement>(null)

  /*
   * PH11.11: focus the confirmation once the success panel exists.
   *
   * `success` unmounts the form, so focus — wherever it was — falls back to
   * `<body>`. Focusing the new heading is what tells the reader the flow
   * completed and that a "Continue to AEGIS" button is now the only thing left.
   */
  useEffect(() => {
    if (success) successHeadingRef.current?.focus()
  }, [success])

  const form = useForm<ChangePasswordFormValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: {
      current_password: "",
      new_password: "",
      confirm_password: "",
    },
    mode: "onBlur",
  })

  const isSubmitting = form.formState.isSubmitting

  if (success) {
    return (
      /*
        PH11.11. Setting `success` unmounted the entire form, which took the
        focused submit button with it and left focus on `<body>`. The `role="alert"`
        region that had been reporting failures was unmounted in the same commit,
        so the confirmation was not announced either — the reader was left in
        silence at the one moment in this flow that mattered.

        The wrapper is the live region, not the heading: `role="status"` on the
        `<h1>` would replace its heading role and stop it appearing in a heading
        list. Focusing the heading locates the reader, and the surrounding status
        region announces the change.
      */
      <div
        role="status"
        className="flex min-h-svh items-center justify-center bg-background px-4 py-10"
      >
        <Card className="w-full max-w-md">
          <CardHeader className="gap-2 text-center">
            <div className="mx-auto flex size-12 items-center justify-center rounded-md bg-success text-success-foreground">
              <CheckCircle2 className="size-6" aria-hidden="true" />
            </div>
            <h1
              ref={successHeadingRef}
              tabIndex={-1}
              className="text-xl font-bold text-foreground focus:outline-none"
            >
              Password updated
            </h1>
            <CardDescription>
              Your password has been changed successfully. You can now access
              the application.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild className="w-full">
              <Link to="/app">Continue to AEGIS</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (isAuthenticated && !mustChangePassword) {
    return <Navigate to="/app" replace />
  }

  if (status === "loading") {
    return null
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" replace />
  }

  async function onSubmit(values: ChangePasswordFormValues) {
    setServerError(null)
    try {
      await changePassword(values.current_password, values.new_password)
      setSuccess(true)
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
          <div className="mx-auto flex size-12 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <KeyRound className="size-6" aria-hidden="true" />
          </div>
          <h1 className="text-xl font-bold text-foreground">
            Change your password
          </h1>
          <CardDescription>
            Your account requires an initial password change before you can
            continue.
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
                name="current_password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Current password</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        type="password"
                        autoComplete="current-password"
                        disabled={isSubmitting}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="new_password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>New password</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        type="password"
                        autoComplete="new-password"
                        disabled={isSubmitting}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="confirm_password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Confirm new password</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        type="password"
                        autoComplete="new-password"
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
                    Updating...
                  </>
                ) : (
                  "Update password"
                )}
              </Button>
            </form>
          </Form>

          <div className="mt-4 text-center text-sm">
            <button
              type="button"
              onClick={() => void logout()}
              className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring"
            >
              Sign in with a different account
            </button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
