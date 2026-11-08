import { useId } from "react"
import type { SubjectTheme } from "./subject-appearance"
import "./student-journal.css"

/** Decorative paper artwork; deliberately separate from the header controls. */
export function StudentNotebookArt() {
  const id = useId().replaceAll(":", "")
  return (
    <svg
      className="student-notebook-art"
      viewBox="0 0 380 150"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient
          id={`${id}-page`}
          x1="100"
          y1="40"
          x2="200"
          y2="130"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#fffdf7" />
          <stop offset="1" stopColor="#eddfcc" />
        </linearGradient>
        <filter
          id={`${id}-shadow`}
          x="-20%"
          y="-30%"
          width="150%"
          height="180%"
        >
          <feDropShadow
            dx="0"
            dy="4"
            stdDeviation="3"
            floodColor="#664238"
            floodOpacity=".13"
          />
        </filter>
      </defs>
      <path
        d="M7 131 49 105 93 112 141 77 206 104 255 87 320 128 368 145 9 145Z"
        fill="#DCD0E8"
        opacity=".65"
      />
      <path
        d="m222 16 61-10 28 14-14 52-72 11-15-18Z"
        fill="#CBD3BC"
        opacity=".6"
      />
      <path d="M314 134c0-25 18-46 39-46 14 0 25 11 27 32v14Z" fill="#F3D3B5" />
      <path
        d="M6 105c49 15 66-43 110-31s63 34 105 8 82-8 153-50"
        stroke="#981919"
        strokeWidth=".8"
        opacity=".35"
      />
      <g stroke="#7f8866" strokeWidth="1.15" strokeLinecap="round">
        <path d="m83 119-11-85m6 50 25-30m-28 9-18-18m23 52 32-14" />
        <path
          d="M73 61C57 56 53 39 57 29c14 9 18 18 16 32Zm5 24c3-18 13-28 27-31-1 16-11 26-27 31ZM74 48c-9-8-9-22-3-34 10 11 11 22 3 34Zm7 51c7-14 19-20 32-16-7 12-18 17-32 16Z"
          fill="#a4a784"
          stroke="none"
        />
      </g>
      <g filter={`url(#${id}-shadow)`}>
        <path
          d="m108 61 73-16 12 12 55-22 26 17-31 77-64-2-74 5Z"
          fill="#8b3934"
        />
        <path
          d="m112 56 65-11c10-1 18 2 22 7l-17 67c-19-6-44-7-78 8Z"
          fill={`url(#${id}-page)`}
        />
        <path d="m199 52 66-17-25 83c-26-7-45-6-58 1Z" fill="#fcf4e8" />
        <path
          d="m199 52-17 67m-78 8c29-11 54-14 78-8 19-8 38-8 58-1"
          stroke="#b99c83"
          strokeWidth="1.3"
        />
        <path
          d="m198 54-17 69-4 14"
          stroke="#913b35"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
        <g stroke="#c9b39c" strokeWidth=".7" opacity=".7">
          <path d="m123 65 45-8m-48 16 46-8m-49 17 47-8m-50 17 47-7m-50 16 48-6m-50 15 47-5m54-45 40-9m-42 17 39-8m-41 16 38-7m-40 16 38-7m-40 15 38-6m-40 15 36-5" />
        </g>
      </g>
      <g transform="rotate(-18 303 111)">
        <path d="m264 106 67 0 0 9-67 0Z" fill="#bc8b50" />
        <path d="M264 106h67v3h-67Z" fill="#ead2a1" />
        <path d="m264 106-16 4.5 16 4.5Z" fill="#e2c3a2" />
        <path d="m253 109-5 1.5 5 1.5Z" fill="#66524b" />
        <path d="M331 106h8v9h-8Z" fill="#b4746b" />
        <path d="M329 106h3v9h-3Z" fill="#d6c6ad" />
      </g>
    </svg>
  )
}

export function StudentJournalBackdrop() {
  return (
    <svg
      className="student-journal-backdrop"
      viewBox="0 0 1400 1600"
      fill="none"
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M0 27 73 9 123 26 150 13 211 39 165 77 85 69 36 105 0 86Z"
        fill="#CBD3BC"
        opacity=".25"
      />
      <path
        d="m1275 160 80-49 45 24v242l-26 10-63-38 16-52-40-34Z"
        fill="#DCD0E8"
        opacity=".24"
      />
      <path
        d="M0 662c74-31 91 24 157 6l40 42-23 61-73-2-47 34-54-16Z"
        fill="#F3D3B5"
        opacity=".24"
      />
      <path
        d="m1300 1031 58-28 42 19v185l-72-14-23-51 24-38Z"
        fill="#CBD3BC"
        opacity=".28"
      />
      <path
        d="M0 1455c96-68 155 14 243-41l77 40-26 49-140 36-154-26Z"
        fill="#DCD0E8"
        opacity=".2"
      />
      <g stroke="#981919" strokeWidth="1" opacity=".18">
        <path d="M2 178c199 77 299-63 479-34s203 113 405 54 314-63 512-9" />
        <path d="M0 712c192-75 254 73 420 18s276-50 452 39 368-38 528 0" />
        <path d="M0 1290c220 18 266-99 452-54s284 134 499 55 306-44 449-7" />
      </g>
    </svg>
  )
}

/** Journal sketches used only on the student's subject cards. */
export function StudentSubjectSketch({ theme }: { theme: SubjectTheme }) {
  return (
    <svg
      className="student-subject-sketch"
      viewBox="0 0 120 100"
      fill="none"
      aria-hidden="true"
      focusable="false"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {theme === "amber" ? (
        <>
          <path d="M26 88c10-30 26-49 60-75 12 22-8 48-40 56M39 74l46-59M57 51l1-18m11 8 20-3M48 62l-1-16m11 8 21-3M88 13l12-5-2 14" />
          <path d="M79 77h24v16H76V80Zm3-6h16v6H82Zm-6 11h27M8 91c13-10 29-11 43-5" />
        </>
      ) : theme === "indigo" || theme === "blue" ? (
        <>
          <path d="m16 83 68-68 17 68Zm23-13h40l-8-39ZM26 20h28v8H26Zm6 0v8m6-8v4m6-4v8m6-8v4M94 25h12v59H94Zm0 11h6m-6 9h4m-4 10h6m-6 9h4m-4 10h6M9 92h102" />
          <path d="M17 72A50 50 0 0 1 67 22" opacity=".55" />
        </>
      ) : theme === "teal" ? (
        <>
          <ellipse cx="60" cy="47" rx="43" ry="16" />
          <ellipse
            cx="60"
            cy="47"
            rx="43"
            ry="16"
            transform="rotate(60 60 47)"
          />
          <ellipse
            cx="60"
            cy="47"
            rx="43"
            ry="16"
            transform="rotate(120 60 47)"
          />
          <circle cx="60" cy="47" r="4" />
          <path d="M21 92h78m-65-8h52" />
        </>
      ) : (
        <>
          <path d="M14 26c16-7 33-7 46 2 14-9 31-9 47-2l-7 54c-13-5-27-5-40 2-14-7-28-7-41-2ZM60 28v54M14 26 9 85c20-6 36-3 51 2 14-5 30-8 49-2l-2-59M25 35c9-3 18-3 26 1m-25 7c9-2 16-1 24 2m-23 6c8-1 15 0 22 2m-21 6c7 0 13 1 20 3m23-26c8-4 16-4 25-2m-25 10c8-3 15-4 24-2m-24 10c8-3 14-4 23-3m-23 11c7-2 14-3 22-2" />
        </>
      )}
    </svg>
  )
}
