import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { FacultyAttendancePanel } from "./FacultyAttendancePanel"

const attendance = {
  attendance_rate: 80,
  present: 7,
  late: 1,
  absent: 2,
  records: 10,
}

describe("FacultyAttendancePanel", () => {
  it("shows the measured attendance rate with the actual record breakdown", () => {
    render(
      <FacultyAttendancePanel data={attendance} loading={false} error={false} />
    )
    const progress = screen.getByRole("progressbar", {
      name: "Recorded attendance rate",
    })
    expect(progress).toHaveAttribute("aria-valuenow", "80")
    expect(progress).toHaveAttribute("aria-valuetext", "80.0% present or late")
    expect(screen.getByText("7")).toBeInTheDocument()
    expect(screen.getByText("1")).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
  })

  it("preserves a recorded zero instead of treating it as missing", () => {
    render(
      <FacultyAttendancePanel
        data={{
          ...attendance,
          attendance_rate: 0,
          present: 0,
          late: 0,
          absent: 10,
        }}
        loading={false}
        error={false}
      />
    )
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "0"
    )
  })

  it("does not invent a progress value when there are no records", () => {
    render(
      <FacultyAttendancePanel
        data={{
          attendance_rate: null,
          present: 0,
          late: 0,
          absent: 0,
          records: 0,
        }}
        loading={false}
        error={false}
      />
    )
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument()
    expect(screen.getByText(/once records are available/i)).toBeInTheDocument()
  })

  it.each([null, Number.NaN, -1, 101])(
    "does not render an invalid rate (%s) as progress",
    (rate) => {
      render(
        <FacultyAttendancePanel
          data={{ ...attendance, attendance_rate: rate }}
          loading={false}
          error={false}
        />
      )
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument()
      expect(
        screen.getByText("The attendance rate is unavailable.")
      ).toBeInTheDocument()
    }
  )

  it("announces loading and keeps a failed request distinct from an empty record", () => {
    const { rerender } = render(
      <FacultyAttendancePanel loading error={false} />
    )
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true")
    rerender(<FacultyAttendancePanel data={attendance} loading={false} error />)
    expect(screen.getByText(/Unable to load attendance/)).toBeInTheDocument()
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument()
  })
})
