import { useState } from "react"
import { Navigate } from "react-router-dom"
import { GraduationCap, Loader2 } from "lucide-react"
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

const loginSchema = z.object({
  email: z
    .string()
    .min(1, "Email is required.")
    .email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
})

type LoginFormValues = z.infer<typeof loginSchema>

export function LoginPage() {
  const { status, isAuthenticated, mustChangePassword, login } = useAuth()
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
          <div className="mx-auto flex size-12 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <GraduationCap className="size-6" aria-hidden="true" />
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
