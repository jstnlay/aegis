import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"

/**
 * The labelled-field pattern, shared.
 *
 * PH11.11 promoted this out of `AdminAcademicsPage`, where it was written during
 * PH11.9's repair of the broken create forms and was the only implementation in
 * the application that satisfied PH11.2 §16.5 in full:
 *
 * - a real `<label htmlFor>` bound to the control's `id`;
 * - `aria-invalid` on the control when it is in error;
 * - the message linked back by `aria-describedby`, so focusing the control
 *   reads the error rather than leaving it orphaned beside the input.
 *
 * Everything else in the app was hand-rolling one of these and getting part of it
 * wrong — most often omitting `aria-invalid` and `aria-describedby`, which is why
 * a 400 naming the offending field produced an alert the reader could hear but
 * not locate. One component means the wiring cannot be forgotten.
 *
 * `required` marks the field both ways PH11.2 §16.5 asks for: a visible asterisk
 * and `aria-required="true"` on the control. The two are deliberately not the
 * same signal — the asterisk is the sighted reader's cue and `aria-required` is
 * the programmatic one — so neither has to carry the other. The label's own text
 * stays exactly the field's name; see `FieldLabel` for why.
 */

export interface FieldProps {
  label: string
  /** Must be unique on the page; the error node's id is derived from it. */
  id: string
  value: string
  onChange: (value: string) => void
  /**
   * The control's `type`, passed straight to `<Input>`.
   *
   * `password` is here because `AdminUsersPage`'s "Initial password" field is one
   * and has to stay masked: admitting the field to the shared pattern must never
   * cost it the masking it had as a hand-rolled `<Input type="password">`.
   */
  type?: "text" | "password" | "date" | "number"
  placeholder?: string
  min?: number
  max?: number
  step?: number
  required?: boolean
  error?: string | null
  /** Helper text under the control. Folded into `aria-describedby`. */
  hint?: string
  className?: string
}

/** The inline message for one field, linked to the control by aria-describedby. */
function FieldError({
  id,
  message,
}: {
  id: string
  message: string | null | undefined
}) {
  if (!message) return null
  return (
    <p id={id} className="text-xs text-destructive">
      {message}
    </p>
  )
}

/**
 * A label, with the required marker when the field is mandatory.
 *
 * The asterisk sits *outside* the `<label>` element, as a sibling. This is
 * deliberate: an element inside the label — even one marked `aria-hidden` — is
 * still part of the label's text content, so the control's accessible name would
 * become "Name *" rather than "Name". The accessible name of a field should be
 * the field's name; that it is mandatory is a property of the control, which
 * `aria-required` already states, and duplicating it inside the name would make
 * every announcement read "Name, required, edit text" with the requirement said
 * twice.
 *
 * So the requirement is carried by `aria-required` on the control and by the
 * visual asterisk, and the label stays exactly the field's name. The asterisk is
 * `aria-hidden` so it is not announced twice even though it is inside the flex
 * row that visually groups it with the label.
 */
function FieldLabel({
  label,
  required,
  htmlFor,
}: {
  label: string
  required?: boolean
  htmlFor: string
}) {
  const asterisk = required ? (
    <span aria-hidden="true" className="text-destructive">
      *
    </span>
  ) : null

  return (
    <div className="flex items-center gap-1">
      <Label htmlFor={htmlFor}>{label}</Label>
      {asterisk}
    </div>
  )
}

/**
 * Join the ids a control should be described by.
 *
 * `aria-describedby` must not point at an id that is not in the document: a
 * dangling reference is announced as an empty string by some screen readers and
 * is an HTML validity error regardless. Only ids actually rendered are included.
 */
function describedBy(
  ...ids: (string | null | undefined)[]
): string | undefined {
  const present = ids.filter(
    (id): id is string => typeof id === "string" && id.length > 0
  )
  return present.length > 0 ? present.join(" ") : undefined
}

export function Field({
  label,
  id,
  value,
  onChange,
  type = "text",
  placeholder,
  min,
  max,
  step,
  required = false,
  error,
  hint,
  className,
}: FieldProps) {
  const errorId = `${id}-error`
  const hintId = hint ? `${id}-hint` : undefined

  return (
    // PH11.11: `min-w-0` on the wrapper.
    //
    // A grid or flex item's default `min-width` is `auto`, which resolves to its
    // content's min-content width — so a field placed in a narrow track refuses to
    // shrink below its widest part and pushes the track wider than the grid was
    // asked for. The grading-period form on `AdminAcademicsPage` is a real case:
    // `sm:grid-cols-5` puts five fields in tracks that are about a sixth of a
    // phone's width, and a `<input type="date">` has an intrinsic width the
    // browser will not compress.
    //
    // `Input` already carries `min-w-0` for the control itself; this is the same
    // requirement one level up, on the element that is actually the grid item.
    //
    // Honest limitation, recorded rather than papered over: jsdom performs no
    // layout, so no test here can prove a grid clips or that it no longer does.
    // This removes the mechanism by construction instead of asserting an outcome.
    <div className={cn("min-w-0 space-y-1.5", className)}>
      <FieldLabel label={label} required={required} htmlFor={id} />
      <Input
        id={id}
        type={type}
        value={value}
        placeholder={placeholder}
        min={min}
        max={max}
        step={step}
        required={required}
        aria-required={required || undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(error ? errorId : null, hintId)}
        onChange={(event) => onChange(event.target.value)}
      />
      {hint ? (
        <p id={hintId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
      <FieldError id={errorId} message={error} />
    </div>
  )
}

export interface ChoiceFieldProps {
  label: string
  id: string
  value: string
  onChange: (value: string) => void
  options: readonly { value: string; label: string }[]
  /** Adds a "None" entry representing the empty value. */
  optional?: boolean
  /** Shown when there are no options at all, explaining why. */
  emptyLabel?: string
  required?: boolean
  error?: string | null
  hint?: string
  className?: string
}

/**
 * A labelled select.
 *
 * The Radix `SelectTrigger` is a real `<button>`, so `<label htmlFor>` pointing
 * at its `id` is a valid association and the control is keyboard operable.
 */
export function ChoiceField({
  label,
  id,
  value,
  onChange,
  options,
  optional = false,
  emptyLabel,
  required = false,
  error,
  hint,
  className,
}: ChoiceFieldProps) {
  const errorId = `${id}-error`
  const hintId = hint ? `${id}-hint` : undefined

  return (
    // `min-w-0` for the same reason as `Field`: this wrapper is the grid item, and
    // `min-width: auto` is what stops a select in a narrow track from shrinking.
    <div className={cn("min-w-0 space-y-1.5", className)}>
      <FieldLabel label={label} required={required} htmlFor={id} />
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger
          id={id}
          aria-required={required || undefined}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(error ? errorId : null, hintId)}
        >
          <SelectValue placeholder={`Select ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          {optional ? <SelectItem value="">None</SelectItem> : null}
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {hint ? (
        <p id={hintId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
      <FieldError id={errorId} message={error} />
      {options.length === 0 && emptyLabel ? (
        <p className="text-xs text-muted-foreground">{emptyLabel}</p>
      ) : null}
    </div>
  )
}
