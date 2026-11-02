import { useState, type ComponentProps } from "react"
import { Eye, EyeOff } from "lucide-react"
import { Input } from "@/components/ui/input"

export function RecoveryPasswordInput({
  visibilityLabel,
  ...props
}: ComponentProps<typeof Input> & { visibilityLabel: string }) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="school-recovery-password">
      <Input
        {...props}
        type={visible ? "text" : "password"}
        autoComplete="new-password"
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
      />
      <button
        type="button"
        aria-label={`${visible ? "Hide" : "Show"} ${visibilityLabel}`}
        aria-pressed={visible}
        disabled={props.disabled}
        onClick={() => setVisible((value) => !value)}
      >
        {visible ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
      </button>
    </div>
  )
}
