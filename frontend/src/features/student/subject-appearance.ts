import {
  Atom,
  BookOpen,
  Calculator,
  Compass,
  Heart,
  Languages,
  Palette,
  Wrench,
} from "lucide-react"

export const subjectThemes = [
  { name: "indigo", icon: Calculator },
  { name: "teal", icon: Atom },
  { name: "coral", icon: BookOpen },
  { name: "amber", icon: Languages },
  { name: "violet", icon: Compass },
  { name: "rose", icon: Palette },
  { name: "blue", icon: Wrench },
  { name: "sage", icon: Heart },
] as const

export type SubjectTheme = (typeof subjectThemes)[number]["name"]

/** Subject identity, rather than list position, keeps colors consistent across periods and pages. */
export function getSubjectTheme(name: string, code = ""): SubjectTheme {
  const subject = `${name} ${code}`.toLowerCase()
  if (/math|algebra|geometry|calculus|statistics/.test(subject)) return "indigo"
  if (/science|sci\d|biology|chemistry|physics|earth/.test(subject))
    return "teal"
  if (/english|literature|reading|oral communication/.test(subject))
    return "coral"
  if (/filipino|pagbasa|komunikasyon|panitikan/.test(subject)) return "amber"
  if (/araling|social|history|geography|politics|ap\d/.test(subject))
    return "violet"
  if (/mapeh|music|arts|physical education|health/.test(subject)) return "rose"
  if (/tle|ict|technology|computer|livelihood|entrepreneur/.test(subject))
    return "blue"
  if (
    /values|esp\d|edukasyon|christian|religion|personal development/.test(
      subject
    )
  )
    return "sage"

  const identity = (code || name).trim().toLowerCase()
  const hash = Array.from(identity).reduce(
    (value, char) => (value * 31 + char.charCodeAt(0)) >>> 0,
    0
  )
  return subjectThemes[hash % subjectThemes.length]?.name ?? "indigo"
}
