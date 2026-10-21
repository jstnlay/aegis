// Generates the phone screen specs for the Figma bridge.
//
//   node docs/mobile/figma/generate-specs.cjs
//
// Writes one JSON spec per screen into docs/mobile/figma/. Each spec is the
// intermediate representation the Design Bridge plugin understands
// (see C:/Users/Lay/Tools/figma-design-bridge/src/schema.js).
//
// The screens are the phone layouts that now ship in the app, at 390 wide.
// Colours come from the design tokens: maroon #9B1313, light grey #F2F2F2,
// white #FFFFFF, and the Figma risk scale --risk-high / --risk-moderate /
// --risk-low.

const fs = require("fs");
const path = require("path");

const MAROON = "#9B1313";
const MAROON_DARK = "#7A0F0F";
const PAPER = "#F2F2F2";
const WHITE = "#FFFFFF";
const INK = "#1A1A1A";
const MUTED = "#6B6B6B";
const BORDER = "#E4E4E4";
const RISK_HIGH = "#AF1C2E";
const RISK_MODERATE = "#DF5E6A";
const RISK_LOW = "#F5BAC1";

const OUT = path.join(__dirname);

const text = (content, o = {}) => ({
  type: "text",
  content,
  size: o.size ?? 14,
  weight: o.weight ?? "Regular",
  color: o.color ?? INK,
  width: o.width ?? "hug",
  ...(o.name ? { name: o.name } : {}),
});

const frame = (children, o = {}) => ({
  type: "frame",
  layout: o.layout ?? "col",
  gap: o.gap ?? 0,
  pad: o.pad ?? 0,
  align: o.align ?? "start",
  justify: o.justify ?? "start",
  width: o.width ?? "hug",
  fill: o.fill,
  radius: o.radius ?? 0,
  ...(o.stroke ? { stroke: o.stroke, strokeWidth: o.strokeWidth ?? 1 } : {}),
  ...(o.w ? { w: o.w } : {}),
  ...(o.h ? { h: o.h } : {}),
  ...(o.name ? { name: o.name } : {}),
  children,
});

const rect = (o) => ({
  type: "rect",
  w: o.w ?? 100,
  h: o.h ?? 8,
  fill: o.fill,
  radius: o.radius ?? 0,
  ...(o.name ? { name: o.name } : {}),
});

const card = (children, o = {}) =>
  frame(children, {
    fill: WHITE,
    radius: 12,
    pad: 16,
    gap: 8,
    width: o.width ?? "fill",
    stroke: BORDER,
    ...o,
  });

const kpi = (title, value, hint, o = {}) =>
  card(
    [
      text(title, { size: 13, color: MUTED, weight: "Medium" }),
      text(value, { size: 24, color: o.valueColor ?? INK, weight: "Bold" }),
      ...(hint ? [text(hint, { size: 11, color: MUTED })] : []),
    ],
    { width: o.width ?? "fill", gap: 6 }
  );

const row = (children, o = {}) =>
  frame(children, {
    layout: "row",
    gap: o.gap ?? 12,
    align: o.align ?? "start",
    width: o.width ?? "fill",
  });

const sectionTitle = (label) =>
  text(label, { size: 12, color: MAROON, weight: "Bold", letterSpacing: 1.2 });

const topBar = (title) =>
  frame(
    [
      text(title, { size: 15, color: MAROON, weight: "Bold", letterSpacing: 1 }),
      rect({ w: 32, h: 32, fill: MAROON, radius: 16, name: "avatar" }),
    ],
    {
      layout: "row",
      justify: "space-between",
      align: "center",
      pad: [12, 16],
      fill: WHITE,
      width: "fill",
    }
  );

const page = (key, name, title, subtitle, body) => ({
  key,
  name,
  width: 390,
  background: PAPER,
  root: frame(
    [
      topBar(title.toUpperCase()),
      frame(
        [
          text(title, { size: 22, color: INK, weight: "Bold" }),
          ...(subtitle ? [text(subtitle, { size: 13, color: MUTED })] : []),
          ...body,
        ],
        { gap: 16, pad: 16, fill: PAPER, width: "fill" }
      ),
    ],
    { gap: 0, fill: PAPER, width: "fill" }
  ),
});

const subjectRow = (subject, code, score) =>
  frame(
    [
      frame(
        [
          text(subject, { size: 14, weight: "Medium" }),
          text(code, { size: 11, color: MUTED }),
        ],
        { gap: 2, width: "fill" }
      ),
      frame(
        [
          text(score, { size: 14, weight: "Bold" }),
          rect({ w: 62, h: 22, fill: "#EFEFEF", radius: 11, name: "badge" }),
        ],
        { layout: "row", gap: 8, align: "center" }
      ),
    ],
    { layout: "row", justify: "space-between", align: "center", pad: 12, stroke: BORDER, radius: 8, width: "fill" }
  );

const chartPlaceholder = (label, bars) =>
  card(
    [
      text(label, { size: 15, weight: "Semi Bold" }),
      frame(
        bars.map((b) => rect({ w: b, h: 120, fill: MAROON, radius: 4 })),
        { layout: "row", gap: 16, align: "end", width: "fill", h: 140 }
      ),
    ],
    { gap: 12 }
  );

const specs = [];

// Landing -------------------------------------------------------------------
specs.push({
  key: "aegis-landing-mobile",
  name: "Landing / Mobile",
  width: 390,
  background: PAPER,
  root: frame(
    [
      frame(
        [
          text("AEGIS", { size: 18, color: MAROON, weight: "Bold" }),
          text("HIS CARE CHRISTIAN INSTITUTE", { size: 10, color: MUTED }),
        ],
        { gap: 2, pad: [12, 16], fill: WHITE, width: "fill" }
      ),
      frame(
        [
          card(
            [
              text("HIS CARE CHRISTIAN INSTITUTE", {
                size: 24,
                color: MAROON,
                weight: "Bold",
              }),
              text("of Santa Maria, Sto. Tomas Batangas Inc.", {
                size: 14,
                weight: "Medium",
              }),
              text(
                "His Care Christian Institute was founded in April 2007 by Leila D. Paragoso and Clemente T. Paragoso. From a small preschool, it has grown into a school serving students from Nursery to Grade 10 in Batangas.",
                { size: 13, color: MUTED }
              ),
              rect({ w: 118, h: 40, fill: MAROON, radius: 8, name: "Read more" }),
            ],
            { gap: 12 }
          ),
          frame(
            [
              sectionTitle("ABOUT THE SCHOOL"),
              text(
                "Leila D. Paragoso and Clemente T. Paragoso both in their 60's founded His Care Christian Institute in April 2007.",
                { size: 13, color: MUTED }
              ),
              rect({ w: 110, h: 36, fill: WHITE, radius: 8, stroke: BORDER, name: "Read more" }),
            ],
            { gap: 12, width: "fill" }
          ),
          frame(
            [
              sectionTitle("MISSION"),
              text(
                "His Care Christian Institute is dedicated to providing quality basic education where biblical values are injected and incorporated as a guide in training up the students.",
                { size: 13, color: MUTED }
              ),
            ],
            { gap: 12, width: "fill" }
          ),
          frame(
            [sectionTitle("VISION"), text("â€”", { size: 13, color: MUTED })],
            { gap: 12, width: "fill" }
          ),
        ],
        { gap: 16, pad: 16, fill: PAPER, width: "fill" }
      ),
    ],
    { fill: PAPER, width: "fill" }
  ),
});

// Student -------------------------------------------------------------------
specs.push(
  page(
    "aegis-student-dashboard-mobile",
    "Student Dashboard / Mobile",
    "Student Dashboard",
    "Your academic record at a glance.",
    [
      kpi("Average Grade", "80.61%", "Overall academic performance"),
      row([
        kpi("Attendance Rate", "80.0%", "12 present, 3 absent"),
        kpi("Total Subjects", "8", "Subjects with finalized grades"),
      ]),
      card(
        [
          text("Academic Progress", { size: 15, weight: "Semi Bold" }),
          text("Grading period", { size: 12, color: MUTED }),
          rect({ w: 300, h: 36, fill: WHITE, radius: 8, stroke: BORDER, name: "Term 1 â€” Average: 80.61%" }),
          text("Grades by Subject", { size: 13, weight: "Medium" }),
          subjectRow("Filipino", "FIL-10", "84.41%"),
          subjectRow("English", "ENG-10", "81.21%"),
          subjectRow("Mathematics", "MATH-10", "76.69%"),
        ],
        { gap: 10 }
      ),
      card(
        [
          text("Recommended for you", { size: 15, weight: "Semi Bold" }),
          text("Matched to your grades and attendance.", { size: 12, color: MUTED }),
        ],
        { gap: 6 }
      ),
      chartPlaceholder("Academic Trend", [40, 72, 56, 96]),
    ]
  )
);

// Parent --------------------------------------------------------------------
specs.push(
  page(
    "aegis-parent-dashboard-mobile",
    "Parent Dashboard / Mobile",
    "Parent Portal",
    "Follow your child's academic record.",
    [
      card(
        [
          text("Linked Students", { size: 15, weight: "Semi Bold" }),
          frame(
            [
              text("Josefina Ocampo Lopez", { size: 13, weight: "Medium" }),
              text("Luna", { size: 11, color: MUTED }),
            ],
            { layout: "row", gap: 8, align: "center", pad: [8, 12], stroke: MAROON, radius: 18, width: "fill" }
          ),
        ],
        { gap: 10 }
      ),
      row([
        kpi("Average Grade", "80.61%", "Across 8 finalized grades"),
        kpi("Attendance Rate", "80.0%", "12 present, 0 late, 3 absent"),
      ]),
      card(
        [
          text("Academic Progress", { size: 15, weight: "Semi Bold" }),
          text("Grading period", { size: 12, color: MUTED }),
          rect({ w: 300, h: 36, fill: WHITE, radius: 8, stroke: BORDER, name: "Term 1 â€” Average: 80.61%" }),
          subjectRow("Filipino", "FIL-10", "84.41%"),
          subjectRow("English", "ENG-10", "81.21%"),
          subjectRow("Mathematics", "MATH-10", "76.69%"),
        ],
        { gap: 10 }
      ),
      card(
        [
          text("Guidance & Support", { size: 15, weight: "Semi Bold" }),
          text(
            "Counseling sessions, intervention plans and behavioral notes live on the support record.",
            { size: 12, color: MUTED }
          ),
          rect({ w: 150, h: 34, fill: WHITE, radius: 8, stroke: BORDER, name: "Open support record" }),
        ],
        { gap: 8 }
      ),
    ]
  )
);

// Faculty -------------------------------------------------------------------
specs.push(
  page(
    "aegis-faculty-dashboard-mobile",
    "Faculty Dashboard / Mobile",
    "Faculty Dashboard",
    "Your sections, attendance and grading at a glance.",
    [
      row([
        kpi("Total Students", "25", "Active enrollments across all sections"),
        kpi("Attendance", "90.1%", "303 present, 35 late, 37 absent"),
      ]),
      row([
        kpi("Pending Grades", "25", "16 drafts + 9 submissions"),
        kpi("Behavior Notes", "0", "No notes for your students"),
      ]),
      card(
        [
          text("Quick actions", { size: 15, weight: "Semi Bold" }),
          frame(
            [
              rect({ w: 120, h: 34, fill: WHITE, radius: 8, stroke: BORDER, name: "Encode a grade" }),
              rect({ w: 120, h: 34, fill: WHITE, radius: 8, stroke: BORDER, name: "Take attendance" }),
              rect({ w: 120, h: 34, fill: WHITE, radius: 8, stroke: BORDER, name: "Advisory class" }),
              rect({ w: 130, h: 34, fill: WHITE, radius: 8, stroke: BORDER, name: "Add behavior note" }),
            ],
            { layout: "row", gap: 8, width: "fill" }
          ),
        ],
        { gap: 10 }
      ),
      card(
        [
          text("Recent Notes", { size: 15, weight: "Semi Bold" }),
          text("No behavior notes recorded yet.", { size: 12, color: MUTED }),
        ],
        { gap: 6 }
      ),
    ]
  )
);

// Guidance ------------------------------------------------------------------
specs.push(
  page(
    "aegis-guidance-dashboard-mobile",
    "Guidance Dashboard / Mobile",
    "Welcome back, Benigno!",
    "Here's an overview of the student support activities today.",
    [
      card(
        [
          text("October 21, 2026", { size: 16, weight: "Semi Bold" }),
          text("16 open alerts on file", { size: 12, color: MUTED }),
        ],
        { gap: 4 }
      ),
      row([
        kpi("Active Cases", "16", "Open risk alerts (not yet resolved)"),
        kpi("At-Risk Students", "13", "Distinct students with an open alert"),
      ]),
      row([
        kpi("Pending Follow-up", "6", "Your ongoing consultations"),
        kpi("Assessment Completion", "100%", "Completed vs started"),
      ]),
      card(
        [
          text("Risk Alerts", { size: 15, weight: "Semi Bold" }),
          frame(
            [
              text("High Risk", { size: 12, color: MUTED }),
              rect({ w: 210, h: 18, fill: RISK_HIGH, radius: 4 }),
              text("8", { size: 12, weight: "Bold" }),
            ],
            { layout: "row", gap: 8, align: "center", width: "fill" }
          ),
          frame(
            [
              text("Moderate Risk", { size: 12, color: MUTED }),
              rect({ w: 210, h: 18, fill: RISK_MODERATE, radius: 4 }),
              text("8", { size: 12, weight: "Bold" }),
            ],
            { layout: "row", gap: 8, align: "center", width: "fill" }
          ),
          frame(
            [
              text("Low Risk", { size: 12, color: MUTED }),
              rect({ w: 105, h: 18, fill: RISK_LOW, radius: 4 }),
              text("4", { size: 12, weight: "Bold" }),
            ],
            { layout: "row", gap: 8, align: "center", width: "fill" }
          ),
        ],
        { gap: 12 }
      ),
    ]
  )
);

// Admin ---------------------------------------------------------------------
specs.push(
  page(
    "aegis-admin-dashboard-mobile",
    "Administration Panel / Mobile",
    "Administration Panel",
    "School-wide aggregates only. Individual student records are not shown here.",
    [
      row([
        kpi("Total Students", "104", "Active student enrollments"),
        kpi("At-Risk Students", "0", "Latest score moderate or high"),
      ]),
      row([
        kpi("High Risk Students", "0", "Latest score at the high level"),
        kpi("Active Alerts", "16", "Alerts not yet resolved"),
      ]),
      card(
        [
          text("Risk distribution", { size: 15, weight: "Semi Bold" }),
          text("Students by their latest computed risk level.", { size: 12, color: MUTED }),
          text(
            "The risk engine has not produced any scores yet, so there is no distribution to show.",
            { size: 12, color: MUTED }
          ),
        ],
        { gap: 6 }
      ),
      chartPlaceholder("Trend overview (last 30 days)", [40, 72, 56, 96]),
    ]
  )
);

for (const spec of specs) {
  const file = path.join(OUT, `${spec.key}.json`);
  fs.writeFileSync(file, JSON.stringify(spec, null, 2));
  console.log("wrote " + path.basename(file));
}
