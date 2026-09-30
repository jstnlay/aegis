import { BookOpen } from "lucide-react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card"

/**
 * First-domain entry point (PH11.5).
 *
 * Academics is the first domain feature chosen for implementation
 * based on the strongest backend/API evidence (full academics module,
 * grading periods, sections, subjects, enrollments, grades). This is an
 * intentionally documented placeholder — PH11.6 begins implementation.
 * No fabricated data is displayed.
 */
export function AcademicsLandingPage() {
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <div className="flex items-center gap-3">
          <BookOpen
            className="size-5 text-muted-foreground"
            aria-hidden="true"
          />
          <h1 className="text-2xl font-bold text-foreground">Academics</h1>
        </div>
        <p className="text-sm text-muted-foreground">
          Academic records and grading tools for faculty and administrators.
        </p>
      </div>

      <Card>
        <CardHeader className="gap-1">
          <h2 className="text-lg font-semibold">Getting started</h2>
          <CardDescription>
            Academics is the first domain to be implemented. This page is the
            documented entry point — full functionality lands in PH11.6.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-foreground">
          Planned features: academic years, grade levels, sections, subjects,
          subject assignments, schedules, grading periods, enrollments, and
          grade encoding.
        </CardContent>
      </Card>
    </div>
  )
}
