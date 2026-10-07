import { BookOpen } from "lucide-react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card"

/**
 * Admin-facing Academics view.
 *
 * PH11.7 shipped the student and faculty Academics surfaces and deliberately
 * left admin on a documented placeholder, because that page resolved no
 * StudentProfile for an administrator. PH11.9 adds the admin academic-structure
 * administration surface, which supersedes this file.
 *
 * What remains here is the honest statement of what the admin Academics route
 * does today: it lists the academic structure that *is* readable through the
 * verified read-only endpoints, and says plainly that authoring is not part of
 * this screen. The previous wording claimed "full functionality lands in
 * PH11.6" and listed academic years, grade levels, sections, subjects, subject
 * assignments, schedules, grading periods, enrollments and grade encoding as
 * "Planned features" — all of which shipped in PH11.7. A placeholder that
 * describes implemented functionality as future work is a bug, not a
 * placeholder.
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
          <h2 className="text-2xl font-bold text-foreground">Academics</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Academic records and grading tools for faculty and administrators.
        </p>
      </div>

      <Card>
        <CardHeader className="gap-1">
          <h3 className="text-lg font-semibold">Academic structure</h3>
          <CardDescription>
            Academic years, grade levels, sections, subjects, subject
            assignments, schedules and grading periods are administered from the
            Administration section of this workspace.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-foreground">
          <p className="text-muted-foreground">
            Grade records for a student are read from that student&apos;s own
            profile. Encoding and finalization of grades are faculty and
            administrator actions respectively, and are recorded in the audit
            log.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
