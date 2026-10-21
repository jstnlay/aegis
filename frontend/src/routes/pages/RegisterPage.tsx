import { useEffect, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { Loader2, MailCheck, UserPlus } from "lucide-react"
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
import {
  submitRegistrationRequest,
  verifyRegistrationRequest,
} from "@/features/auth/api"
import { normalizeApiError } from "@/lib/error"

const registerSchema = z
  .object({
    full_name: z.string().min(1, "Your full name is required."),
    email: z
      .string()
      .min(1, "Email is required.")
      .email("Enter a valid email address."),
    student_code: z.string().max(20).optional(),
    password: z
      .string()
      .min(1, "Password is required.")
      .min(8, "Password must be at least 8 characters."),
    confirm_password: z.string().min(1, "Please confirm your password."),
  })
  .refine((data) => data.password === data.confirm_password, {
    message: "Passwords do not match.",
    path: ["confirm_password"],
  })

type RegisterFormValues = z.infer<typeof registerSchema>

/**
 * Student registration (document elements 7-12).
 *
 * A registration is a request, not an account. The page says so plainly:
 * the student's own answer is sent to their inbox, and an administrator
 * decides. There is no role picker, because the role is the school's to
 * give, not the student's to claim.
 */
export function RegisterPage() {
  const [searchParams] = useSearchParams()
  const verificationToken = searchParams.get("token") ?? ""
  const [serverError, setServerError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const [verificationState, setVerificationState] = useState<
    "idle" | "verifying" | "verified" | "failed"
  >(verificationToken ? "verifying" : "idle")

  const form = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      full_name: "",
      email: "",
      student_code: "",
      password: "",
      confirm_password: "",
    },
    mode: "onBlur",
  })

  const isSubmitting = form.formState.isSubmitting

  useEffect(() => {
    if (!verificationToken) return
    let cancelled = false
    verifyRegistrationRequest(verificationToken)
      .then(() => {
        if (!cancelled) setVerificationState("verified")
      })
      .catch(() => {
        if (!cancelled) setVerificationState("failed")
      })
    return () => {
      cancelled = true
    }
  }, [verificationToken])

  async function onSubmit(values: RegisterFormValues) {
    setServerError(null)
    try {
      await submitRegistrationRequest({
        full_name: values.full_name,
        email: values.email,
        student_code: values.student_code ?? "",
        password: values.password,
        confirm_password: values.confirm_password,
      })
      setSent(true)
    } catch (error) {
      const normalized = normalizeApiError(error)
      if (normalized.isCancelled) return
      setServerError(normalized.message)
    }
  }

  if (verificationState === "verifying") {
    return (
      <div
        role="status"
        className="flex min-h-svh items-center justify-center bg-background px-4 py-10"
      >
        <Card className="w-full max-w-md">
          <CardContent className="flex items-center justify-center gap-3 py-10 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            Verifying your request...
          </CardContent>
        </Card>
      </div>
    )
  }

  if (verificationState === "verified") {
    return (
      <div
        role="status"
        className="flex min-h-svh items-center justify-center bg-background px-4 py-10"
      >
        <Card className="w-full max-w-md">
          <CardHeader className="gap-2 text-center">
            <div className="mx-auto flex size-12 items-center justify-center rounded-md bg-success text-success-foreground">
              <MailCheck className="size-6" aria-hidden="true" />
            </div>
            <h1 className="text-xl font-bold text-foreground">
              Request verified
            </h1>
            <CardDescription>
              Your address is confirmed. An administrator will review the
              request and create your account, and you will get an email when it
              is ready.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild className="w-full">
              <Link to="/login">Back to sign in</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (verificationState === "failed") {
    return (
      <div className="flex min-h-svh items-center justify-center bg-background px-4 py-10">
        <Card className="w-full max-w-md">
          <CardHeader className="gap-2 text-center">
            <h1 className="text-xl font-bold text-foreground">
              This link has expired
            </h1>
            <CardDescription>
              The verification link is invalid or has expired. Ask for a new
              one.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild className="w-full">
              <Link to="/register">Register again</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    )
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
              If that address can be registered, a verification link is on its
              way. Open it, and an administrator will review your request.
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
          <div className="mx-auto flex size-12 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <UserPlus className="size-6" aria-hidden="true" />
          </div>
          <h1 className="text-xl font-bold text-foreground">
            Request a student account
          </h1>
          <CardDescription>
            Fill this in and we will send a verification link to your address.
            An administrator reviews the request before the account is created.
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
                name="full_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Full name</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        autoComplete="name"
                        placeholder="Juan Dela Cruz"
                        disabled={isSubmitting}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

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
                        autoComplete="email"
                        inputMode="email"
                        placeholder="you@school.edu"
                        disabled={isSubmitting}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="student_code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Student number (optional)</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        placeholder="AEGIS-QA-S0001"
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
                    <FormLabel>Confirm password</FormLabel>
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
                    Sending...
                  </>
                ) : (
                  "Send verification link"
                )}
              </Button>

              <p className="text-center text-sm">
                Already have an account?{" "}
                <Link
                  to="/login"
                  className="underline underline-offset-4 transition-colors hover:text-foreground"
                >
                  Sign in
                </Link>
              </p>
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  )
}
