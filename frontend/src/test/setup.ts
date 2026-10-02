import "@testing-library/jest-dom/vitest"
import { cleanup } from "@testing-library/react"
import { afterEach } from "vitest"

/**
 * jsdom implements no Pointer Events. Radix primitives (`Select`, `Popover`,
 * `DropdownMenu`) call `hasPointerCapture` / `setPointerCapture` /
 * `releasePointerCapture` on the event target, so any test that opens one of
 * those surfaces throws `target.hasPointerCapture is not a function` without
 * these shims. They are inert no-ops: nothing in jsdom tracks pointer capture
 * state, and the primitives only use it to suppress text selection.
 */
const noop = () => {}

if (typeof window !== "undefined") {
  const proto = window.Element.prototype as unknown as Record<string, unknown>
  if (typeof proto.hasPointerCapture !== "function") {
    proto.hasPointerCapture = () => false
    proto.setPointerCapture = noop
    proto.releasePointerCapture = noop
  }

  // Radix `Select` scrolls the focused option into view on open. jsdom has no
  // layout engine, so `scrollIntoView` is absent and the open throws.
  if (typeof proto.scrollIntoView !== "function") {
    proto.scrollIntoView = noop
  }

  if (typeof window.PointerEvent !== "function") {
    class PointerEventPolyfill extends MouseEvent {
      public readonly pointerId: number
      public readonly pointerType: string
      public readonly isPrimary: boolean

      constructor(type: string, params: PointerEventInit = {}) {
        super(type, params)
        this.pointerId = params.pointerId ?? 1
        this.pointerType = params.pointerType ?? "mouse"
        this.isPrimary = params.isPrimary ?? true
      }
    }

    window.PointerEvent = PointerEventPolyfill as unknown as typeof PointerEvent
  }
}

afterEach(() => {
  cleanup()
})
