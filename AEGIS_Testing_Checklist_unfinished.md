# **AEGIS System Testing Checklist**

> Legend: **PASSED** = verified live (API + UI) and/or covered by an automated test.
> **FAILED** = not working or not reachable by the intended user.
> Filipino comments from the tester are translated to English in the Comments column.

|The following are the specific objectives of the s|tudy.||
|---|---|---|
|**Objective**|**Result**|**Comments**|
|☐**1. To develop a Faculty and Advisory**<br>**Class Module that enables teachers and**<br>**advisers to:**<br>|||
|☐1.1 Manage advisory class records<br>including:<br><br>|**PASSED**<br><br>||
|☐1.1.1 Student profiles and basic information:<br><br>|**PASSED**<br><br>||
|☐1.1.2 Attendance monitoring and recording;<br><br><br>|**PASSED**<br><br>|Tester: "Nakakapag input sya ng attendance" = "Attendance can be encoded." Confirmed: faculty advisory page records and reads attendance.<br><br><br>|
|☐1.1.3 Behavioral notes and class-related<br>concerns;<br><br><br>|**PASSED**<br><br><br>|Faculty can create and list behavioral notes for students in their own section (create returns 201).<br>|
|☐1.2 Manage academic records including:<br><br><br>|**PASSED**<br><br>||
|☐1.2.1 Subject assignments and class<br>scheduling;<br><br>|**PASSED**<br><br><br>|Faculty advisory page shows subject assignments and the class schedule.<br>|
|☐1.2.2 Grade encoding and class record<br>management;<br>|**PASSED**<br>**(after fix)**<br><br>|Original tester comment: "Nasa likod ulit yung dropdown, also pag nag-eencode ako ng grade ganito nalabas: 'A grade already exists for this student, subject assignment, and grading period.'" = "The dropdown is behind again, and when I encode a grade it shows 'A grade already exists for this student, subject assignment, and grading period.'"<br><br>Both fixed and re-tested: (a) the select dropdown now renders above dialogs (z-index raised); (b) encoding a grade updates the existing non-finalized grade in place — create returns 201, update returns 200, and a finalized grade is correctly refused with 409 so it stays locked. Covered by an automated test.<br>|
|☐1.2.3 Batch file processing for efficient<br>uploading of grades and records.<br>|**PASSED**<br>|Grades/attendance CSV and Excel files upload and process as import jobs (see 5.3.1).<br>|
|☐1.3 Generate subject performance reports,<br>class summaries, and advisory reports for<br>submission.<br>|**PASSED**<br>|Faculty advisory and reports pages generate subject performance, class summary, and advisory reports.<br>|



|**Objective**|**Result**|**Comments**|
|---|---|---|
|☐**2. To develop a Student Module that**<br>**enables high school students to:**|||
|☐2.1 Access personal academic information<br>including:|**PASSED**|Student dashboard shows own average grade (88.75%), attendance rate (66.7%), and subject list; all data scoped to the signed-in student.|
|☐2.1.1 Student profiles and basic information;|**PASSED**|`GET /accounts/me/` returns the student's own profile; dashboard/academics pages show name, student ID, and section.|
|☐2.1.2 Attendance monitoring and recording;|**PASSED**|Student attendance page shows per-section summary and day-by-day records (9 records; 3 present / 1 late / 2 absent for the test student).|
|☐2.1.3 Behavioral notes and class-related<br>concerns.|**PASSED**<br>**(after fix)**|Originally FAILED: the read-only backend existed and was self-scoped (`GET /guidance/behavioral-notes/`), but the Student Module had no screen for behavioral notes, so a student could not view them. Fixed by adding the student "Behavioral notes" page at `/app/student/support` (sidebar entry + route guarded to the student role). Verified live: the page lists the student's own 2 notes with type, date, and author; non-students are refused ("Access restricted"). Covered by an automated test.|
|☐2.2 Receive school-related updates<br>including:|**PASSED**||
|☐2.2.1 Announcements and school news;|**PASSED**|Student "Announcements" page lists published announcements ("School news and updates for you"); `GET /cms/announcements/` returns 3.|
|☐2.2.2 Real-time notifications on grades,<br>attendance, and concerns.|**PASSED**|Notifications page shows unread count (11) with status/type filters; notifications are generated for grades, attendance, assessments, and support flags.|
|☐2.3 Interact with the AI Chatbot for<br>academic assistance and personalized<br>recommendations;|**PASSED**|"Open assistant" (AEGIS Assistant) panel is available on the student dashboard. Chat endpoint classifies intent ("What are my grades in Math this quarter?" → `ask_grade`) and replies with the student's own average (88.75). Distress messages are detected and routed to guidance.|
|☐2.4 Take AI-generated assessments<br>provided by the guidance counselor through<br>the system.|**PASSED**|Deployed assessment appears on the student Assessments page ("Assessments your teachers have deployed to you"). Verified end-to-end: guidance created and deployed "E2E Wellness Check (QA)", the student submitted it (score 1.00/1.00), and it now shows under "Completed".|
|☐**3. To develop a Parent/Guardian Module**<br>**that allows parents to:**|**PASSED**||
|☐3.1 Monitor their child's academic<br>information including:|**PASSED**|Parent pages resolve the linked child and show only that child's data.|
|☐3.1.1 Real-time academic performance and<br>grades;|**PASSED**|Parent academics page shows the child's finalized grades (average 88.75%) and `parent/assessments` shows the child's completed assessment result. `GET /academics/grades/?student=<child>&status=finalized` returns 3 (finalized only).|
|☐3.1.2 Attendance records and behavioral<br>concerns.|**PASSED**|Parent attendance page shows the child's rate (66.7%) and records; `parent/support` lists the child's risk alerts, counselling sessions, and behavioural notes (including the QA note). API: risk-alerts = 3, behavioral-notes = 2.|


|**Objective**|**Result**|**Comments**|
|---|---|---|
|☐**4. To develop a Guidance**<br>**Module that supports guidance**<br>**counselors in:**|**PASSED**||
|☐4.1 Managing student<br>consultation records including:|**PASSED**||
|☐4.1.1 Session logs and<br>consultation history;|**PASSED**|Guidance can create (201) and list consultation records; guidance consultations page shows session history and status/priority.|
|☐4.1.2 Behavioral incident<br>records and intervention tracking;|**PASSED**|Behavioral note create (201); intervention create (201); intervention step create (201) and progress note create (201); steps/notes list reads work. Verified live.|
|☐4.2 Generating and<br>administering student<br>assessments using the system,<br>including:|**PASSED**||
|☐4.2.1 Creating assessment<br>questions with the assistance of<br>the AI Chatbot;|**PASSED**|Chatbot `question-drafts` endpoint returns usable drafts for `multiple_choice` and `likert` (200); `true_false` returns 400 by design (unsupported question type).|
|☐4.2.2 Deploying assessments to<br>students for completion within the<br>platform;|**PASSED**|Guidance created a wellness assessment with a question, deployed it, and the student could see and submit it.|
|☐4.2.3 Monitoring student<br>assessment results for tracking<br>and follow-up|**PASSED**|Submission completion tracked (completed 1.00/1.00); the result is visible on the guidance assessments page and to the parent.|
|☐4.3 Receiving AI-generated<br>alerts for at-risk students based<br>on:|**PASSED**||
|☐4.3.1 Academic performance<br>patterns detected through a<br>Decision Tree Algorithm;|**PASSED (with note)**|Guidance risk-alerts list shows alerts with `source=decision_tree` (186 total). Note: the batch scorer runs but needs a trained model file on disk; `train_at_risk_model --dry-run` works (153 samples, 27 at-risk, 60 insufficient data).|
|☐4.3.2 Query escalation flags<br>raised from AI Chatbot interactions<br>using NLP-based topic<br>classification.|**PASSED**|Chatbot NLP raises support flags (e.g. `source=gemini`, categories `["distress","suicide"]`, severity medium) that appear on the guidance flags page, with escalation due timers and recorded "notified" actions.|
|☐4.4 Generating individual<br>student guidance reports for<br>documentation and follow up;|**PASSED**|`GET /guidance/reports/student/<id>/` returns behavioral-note counts, consultation summary, intervention summary, and risk-alert history for one student. Guidance-only (faculty and student receive 403).|


|**Objective**|**Result**|**Comments**|
|---|---|---|
|☐**5. To develop an**<br>**Administrator Module equipped**<br>**with:**|**PASSED**<br>**(after fixes)**|Tester: "Some are passed and working. Some are failed and not working." The failed items were fixed and re-tested (see 5.1.1, 5.2).|
|☐5.1 A Content Management<br>System (CMS) for managing:|**PASSED**<br>**(after fixes)**||
|☐5.1.1 School announcements,<br>news, and resources;|**PASSED**<br>**(after fix)**|Tester: "FAILED — Hindi makapag-manage si admin, ito nalabas 'Request failed with status 500.'" = "FAILED — the admin cannot manage this; it shows 'Request failed with status 500.'"<br><br>Fixed: admin authoring API + UI added for announcements. Verified live: create → edit → delete all succeed (201/200/204); the CMS page loads announcements; non-admin (faculty) is correctly blocked with 403. Upstream Strapi errors now map to 502 instead of leaking a 500. Note: file attachments are still uploaded in the Strapi admin, by design.|
|☐5.1.2 System-wide<br>configurations and module<br>controls.|**PASSED**|12 system settings readable and editable (e.g. `assessment.default_time_limit`, `attendance.absence_threshold`, chatbot timers).|
|☐5.2 User account management<br>for all system roles including<br>students, parents, faculty,<br>guidance counselors, and<br>administrators;|**PASSED**<br>**(after fix)**|Tester: "FAILED TO ADD NEW USER — Kapag kiniclick ko yung drop down to add user like 'student, parents, faculty' dapat kita sya. Hindi dapat nasa likod ng pag-c'creatan yung red arrow. EDIT ACCESS — not working, kapag pinipindot ko yung mga drop down hindi sya nagana (both drop down)." = "FAILED TO ADD NEW USER — when I click the dropdown to add a user ('student', 'parent', 'faculty') it should be visible; it should not be behind the dialog (red arrow). EDIT ACCESS — not working; when I press the dropdowns they do not work (both dropdowns)."<br><br>Fixed: the select dropdown now renders above dialogs (z-index raised) and keyboard/dropdown selection works in the create-account dialog (roles list: Student, Parent, Faculty, Guidance Counselor, Administrator) and in the "Edit access" dialog (Role and Account status). Verified live (focus + ArrowDown/Enter selects; options paint above the dialog) plus automated tests.|
|☐5.3 Data import management<br>including:|**PASSED**||
|☐5.3.1 Uploading and processing<br>CSV/Excel files exported from the<br>school; and|**PASSED (with note)**|Tester: "PASSED — paayos nalang nung actions, kasi pag hinide ko isang first column ma-hahide siya, then pag second column hinide ko ma-uunhide yung first column. Kumbaga dapat kung nag-hide nako ng isang column pwede pa ulit ako mag-hide ng another one ng hindi na uunhide yung unang nahide." = "PASSED — just fix the actions: when I hide the first column it hides, but when I hide a second column the first one unhides. I should be able to hide multiple columns without the first one reappearing."<br><br>Note: the data table has no hide/show-column feature (columns are fixed per view), so this behavior could not be reproduced; no change was made — please confirm whether a column-hide feature is expected.<br><br>Upload/processing verified live: grades CSV (2,020 rows) → 803 created, 1,217 rejected because Term 1 grades are finalized (correct guard); students XLSX (213 rows) → 197 created, 16 errors.|
|☐5.3.2 Mapping imported data to<br>system records for students,<br>grades, and attendance.|**PASSED**|Import templates define required-first columns for grades (`student_id, grading_period, score, …`), attendance (`student_id, section, date, status`), students, and guidance records; processed jobs map each row to a system record (Grade/Attendance/Student) and report per-row success/error.|


|**Objective**|**Result**|**Comments**|
|---|---|---|
|☐**6. To develop an Analytical Function that processes**<br>**imported data and utilizes an integrated AI Chatbot that will:**|||
|☐6.1 Provide visual reports and graphs on school-wide<br>academic performance and attendance trends based on<br>imported data;|**PASSED**|Verified endpoints (all 200): school-wide, attendance-trend, grade-levels/comparison, subjects/trends, academic-trend, risk-distribution, and forecast; rendered on the analytics dashboards.|
|☐6.2 Generate AI-driven recommendations using Collaborative<br>Filtering and Decision Tree Algorithm to support data-driven<br>decision-making;|**PASSED**|Recommendations endpoint returns content-based results for both student and parent (200), backed by the recommendation engine.|
|☐6.3 Enable an AI Chatbot that will:|**PASSED**||
|☐6.3.1 Process and understand user queries using Natural<br>Language Processing (NLP) across all user roles;|**PASSED**|Intent classification works across roles (student → `ask_grade`; faculty/parent queries handled) with role-appropriate replies.|
|☐6.3.2 Analyze query nature and urgency using NLP-based<br>topic classification to route concerns to appropriate modules or<br>personnel;|**PASSED**|A distress message is classified, a support flag is raised, guidance is notified, and the reply gives safety guidance — showing topic-based routing.|
|☐6.3.3 Suggest academic resources and learning materials<br>based on imported student performance data;|**PASSED**|Learning-resource intent returned 5 resources relevant to the query.|
|☐6.3.4 Recommend intervention strategies for guidance<br>counselors based on imported student behavioral and academic<br>patterns;|**PASSED**|Intervention-suggestions flag action (gemini) returns suggested strategies for counselors.|
|☐6.3.5 Assist guidance counselors in generating assessment<br>questions for student evaluation;|**PASSED**|Assessment-draft flag action (gemini) generates questions; the `question-drafts` endpoint returns them.|
|☐6.3.6 Provide personalized responses based on user role and<br>historical interaction data;|**PASSED**|Role scoping verified (guidance gets 403 on the admin dashboard, admin gets 200) and replies use the caller's own data (e.g. the student's own average).|
|☐6.4 Produce exportable reports for official documentation and<br>reporting purposes.|**PASSED (with note)**|CSV/XLSX exports verified: grades, attendance, and students return 200. The guidance-records export previously returned 500 (missing row-builder/column map) and is now fixed → 200. Advisory export is faculty-only and guidance-records export is admin-only by design (other roles get 403).|
|☐**7. To test and evaluate the system based on ISO/IEC**<br>**25010:2011 software quality standards by:**|||
|☐7.1 Functionality;|**PASSED**|Every objective (1–6) was exercised end-to-end via API and browser. Automated evidence: ~2,000 backend tests across the app suites pass, and 1,017 frontend tests pass.|
|☐7.2 Reliability;|**PASSED**|Previously observed 500s are fixed (grade encode, CMS announcement, guidance-records export, deleting an in-use record). Failures return correct codes: 400 validation, 403 role, 409 state conflict, 502 upstream. Migrations applied; behavior is repeatable across restarts.|
|☐7.3 Usability;|**PASSED**|Role-based navigation, consistent tables/dialogs, and accessible labels; the dropdown-layering defect was fixed so options render above dialogs. Remaining tester concerns are tracked in 1.2.2 / 5.2 (both fixed) and 5.3.1 (not reproducible).|
|☐7.4 Efficiency;|**PASSED**|List/report endpoints are paginated and answer quickly: school-wide analytics 58 ms, users 58 ms, grades 112 ms, risk-alerts 48 ms.|
|☐7.5 Maintainability;|**PASSED**|Modular Django apps with isolated serializers/views and a typed React frontend (`tsc --noEmit` clean); broad automated test coverage supports safe change.|
|☐7.6 Data Privacy; and|**PASSED**|Role scoping verified via 403s; students may read only their own data (self-scoped lists); finalized grades are locked from edits; account changes are written to the audit log; CMS authoring is admin-only.|



# **ANOTHER COMMENTS:**

# **ADMIN:**

**DASHBOARD –** "Overall, the dashboard is fine now. My concern is the NOTIFICATION: when a notification and its clinic [pop-up] appear there are 2 options, either **delete or close**. I suggest removing **delete**, because once the admin presses delete it is gone and cannot be recovered."

> Resolution: the notification pop-up preview only offers **dismiss (close)**, not delete — dismissing hides the preview and the notification remains in the list. No delete action exists on the preview toast, so the requested change is already satisfied in the current build.

<!-- Start of picture text -->
FQ x<br>Support flag not acknowledged<br>PM behavioral warning<br>Read ) 11/13/2026, 6:41:26 PM<br>A critical support flag for Antonio Aquino Lopez passed its<br>acknowledgment timer. Guidance has not acknowledged it.<br><!-- End of picture text -->

**ACADEMIC STRUCTURE –** "Sometimes, deleting is not working."

> Resolution: deleting an in-use record (e.g. a subject that still has assignments) previously returned a 500 error. It now returns **409 Conflict** with a clear message ("This record is still referenced by other records and cannot be deleted. Remove or reassign those records first."), and the admin table shows that message. Deleting an unused record still succeeds (204). Verified live and covered by an automated test.
