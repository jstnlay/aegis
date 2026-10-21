import { useState } from "react"
import { Link } from "react-router-dom"
import { Loader2, MailCheck } from "lucide-react"
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
import { forgotPasswordRequest } from "@/features/auth/api"
import { normalizeApiError } from "@/lib/error"

const forgotSchema = z.object({
  email: z
    .string()
    .min(1, "Email is required.")
    .email("Enter a valid email address."),
})

type ForgotFormValues = z.infer<typeof forgotSchema>

/**
 * Forgot password (document element 4).
 *
 * The page says the same thing whether or not the address belongs to an
 * account, because the server answers the same way. The page cannot be used
 * to find out who has an account, and it must not pretend otherwise by
 * showing a different message for a known address.
 */
export function ForgotPasswordPage() {
  const [serverError, setServerError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)

  const form = useForm<ForgotFormValues>({
    resolver: zodResolver(forgotSchema),
    defaultValues: { email: "" },
    mode: "onBlur",
  })

  const isSubmitting = form.formState.isSubmitting

  async function onSubmit(values: ForgotFormValues) {
    setServerError(null)
    try {
      await forgotPasswordRequest(values.email)
      setSent(true)
    } catch (error) {
      const normalized = normalizeApiError(error)
      if (normalized.isCancelled) return
      setServerError(normalized.message)
    }
  }

  if (sent) {
    return (
      <div
        role="status"
        className="flex min-h-svh items-center justify-center bg-background px-4 py-10"
      >
        <Card className="w-full max-w-md">
          <CardHeader className="gap-2 text-center">
            <div className="mx-auto flex size-12 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <MailCheck className="size-6" aria-hidden="true" />
            </div>
            <h1 className="text-xl font-bold text-foreground">
              Check your inbox
            </h1>
            <CardDescription>
              If an account exists for that address, a password reset link is on
              its way. The link stops working in 30 minutes and can only be used
              once.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild variant="outline" className="w-full">
              <Link to="/login">Back to sign in</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-background px-4 py-10">
      <Card className="w-full max-w-md">
        <CardHeader className="gap-2 text-center">
          <h1 className="text-xl font-bold text-foreground">
            Reset your password
          </h1>
          <CardDescription>
            Enter the address you sign in with and we will send a link to choose
            a new password.
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

              <Button type="submit" className="w-full" disabled={isSubmitting}>
                {isSubmitting ? (
                  <>
                    <Loader2
                      className="size-4 animate-spin"
                      aria-hidden="true"
                    />
                    Sending...
                  </>
                ) : (
                  "Send reset link"
                )}
              </Button>

              <p className="text-center text-sm">
                <Link
                  to="/login"
                  className="underline underline-offset-4 transition-colors hover:text-foreground"
                >
                  Back to sign in
                </Link>
              </p>
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  )
}
