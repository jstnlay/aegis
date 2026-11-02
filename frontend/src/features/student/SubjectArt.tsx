import { subjectThemes, type SubjectTheme } from "./subject-appearance"

export function SubjectArt({ theme }: { theme: SubjectTheme }) {
  const Icon = subjectThemes.find((item) => item.name === theme)!.icon
  return (
    <span className="student-subject-art" aria-hidden="true">
      <span className="student-subject-orbit" />
      <Icon strokeWidth={1.25} />
      <span className="student-subject-spark">+</span>
    </span>
  )
}
