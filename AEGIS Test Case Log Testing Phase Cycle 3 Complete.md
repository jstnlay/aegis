# **E9: Test Case Log** 

_AEGIS: An AI-Enhanced Guidance and Integrated School Information System_ 

|**Test Name:**|AEGIS Functional/System Test – Admin|
|---|---|
|**Test Case Author:**|Palomo, Karl Zyrele|
|**Tester Name:**|Palomo, Karl Zyrele|
|**Project ID/Name:**|AEGIS: An AI-Enhanced Guidance and Integrated School Information System|
|**Test Cycle ID:**|TestingPhase Cycle 3|
|**Date Tested:**|October 9, 2026|



|**Test**<br>**Case ID**|**Test**<br>**Objective**|**Category**|**Condition**|**Expected Results**|**Actual Results**|**Requirement**<br>**ID**|
|---|---|---|---|---|---|---|
||**ID**||||||
|**Admin M**|**odule**||||||
|TC-ADM-<br>01|TO-ADM-<br>01|Authentication|Verify that an Administrator<br>with valid credentials can<br>successfully log in to<br>AEGIS.|Admin is authenticated and<br>redirected to the Admin<br>Dashboard.|PASSED|NFR-011|
|TC-ADM-<br>02|TO-ADM-<br>01|Authentication<br>(Negative)|<br>Verify that the system<br>denies access and displays<br>an appropriate error when<br>invalid credentials are<br>entered.|System displays a clear error<br>message indicating the login<br>failed and denies access to<br>the Admin Dashboard.|PASSED|NFR-002|
|TC-ADM-<br>03|TO-ADM-<br>02|File<br>Upload/Import|Verify that an Admin can<br>import a valid academic<br>records file (CSV/Excel)<br>into the system.|Academic data is<br>successfully parsed, mapped,<br>and stored in the Academic<br>DB without error.|FAILED<br>(Cycle 2) –<br>Test File not<br>available.<br>FAILED<br>(Cycle 3) –<br>Importing an<br>Exported<br>Grades failed.<br>Missing<br>required<br>column(s):<br>subject_assign<br>ment<br>FAILED<br>(Cycle 3) –<br>Importing an<br>Exported<br>Student failed.<br>Missing<br>required<br>column(s):<br>email,<br>first_name,<br>last_name|FR-037|



|TC-ADM-<br>04|TO-ADM-<br>03|File<br>Upload/Import|Verify that an Admin can<br>import a valid attendance<br>records file (CSV/Excel)<br>into the system.|Attendance data is<br>successfully parsed, mapped,<br>and stored in the Attendance<br>DB without error.|FAILED<br>(Cycle 2) –<br>Test File not<br>available.<br>Could not be<br>tested<br>FAILED<br>(Cycle 3) –<br>Importing an<br>Exported<br>Attendance<br>failed.<br>Unknown<br>column(s) not<br>supported by<br>this import:<br>recorded_by,<br>student_name|FR-037|
|---|---|---|---|---|---|---|
|TC-ADM-<br>05|TO-ADM-<br>04|File<br>Upload/Import|Verify that an Admin can<br>import a valid guidance<br>records file (CSV/Excel)<br>into the system.|Guidance record data is<br>successfully parsed, mapped,<br>and stored in the Guidance<br>DB without error.|FAILED<br>(Cycle 2) –<br>Test File not<br>available.<br>Could not be<br>tested<br>FAILED<br>(Cycle 3) –<br>Export of<br>Guidance<br>records not<br>implemented|FR-037|
|TC-ADM-<br>06|TO-ADM-<br>05|Data Entry|Verify that an Admin can<br>create a new Faculty<br>account.|Faculty account is<br>successfully created, stored<br>in the system, and assigned<br>the Facultyrole.|PASSED|FR-036, FR-005|
|TC-ADM-<br>07|TO-ADM-<br>05|Data Entry|Verify that an Admin can<br>create a new Student<br>account.|Student account is<br>successfully created, stored<br>in the system, and assigned<br>the Student role.|PASSED|FR-036, FR-002|
|TC-ADM-<br>08|TO-ADM-<br>05|Data Entry|Verify that an Admin can<br>create a new Parent account.|Parent account is<br>successfully created, stored<br>in the system, and assigned<br>the Parent role.|PASSED|FR-036, FR-003|
|TC-ADM-<br>09|TO-ADM-<br>05|Data Entry|Verify that an Admin can<br>create a new Guidance<br>Counselor account.|Guidance Counselor account<br>is successfully created, stored<br>in the system, and assigned<br>the Guidance Counselor role.|<br>PASSED|FR-036, FR-004|
|TC-ADM-<br>10|TO-ADM-<br>06|Access<br>Control|Verify that an Admin can<br>assign/modify role-based<br>access for a selected user.|Role-based access is<br>successfully configured for<br>the selected user and takes<br>effect on their next login.|PASSED|NFR-011|
|TC-ADM-<br>11|TO-ADM-<br>07|Configuration|Verify that an Admin can<br>update system-wide settings.|System settings are<br>successfully updated and<br>applied across the system.|PASSED|FR-034|
|TC-ADM-<br>12|TO-ADM-<br>08|Content<br>Management|Verify that an Admin can<br>create a new school<br>announcement.|Announcement is<br>successfully created and<br>stored in the system.|FAILED –<br>Request Failed|FR-033|



||||||with status 502<br>/ Read-only<br>view<br>Implementatio<br>n||
|---|---|---|---|---|---|---|
|TC-ADM-<br>13|TO-ADM-<br>08|Content<br>Management|Verify that an Admin can<br>publish a school<br>announcement to all users.|Announcement is<br>successfully deployed and<br>made visible to all intended<br>user roles.|FAILED –<br>Request Failed<br>with status 502<br>/ Read-only<br>view<br>Implementatio<br>|<br> <br>FR-033|
||||||n||
|TC-ADM-<br>14|TO-ADM-<br>09|Content<br>Management|Verify that an Admin can<br>add a new school resource<br>(e.g., a guidance/academic<br>reference document)<br>through the CMS.|Resource is successfully<br>created, stored in the system,<br>and made available through<br>the CMS.|<br>FAILED –<br>Request Failed<br>with status 502<br>/ Read-only<br>view<br>Implementatio<br>|<br> <br>FR-035|
||||||n||
|TC-ADM-<br>15|TO-ADM-<br>09|Content<br>Management<br>(Negative)|Verify that the system<br>rejects an invalid resource<br>upload (e.g., an unsupported<br>file type).|System displays a validation<br>error and does not save the<br>invalid resource.|FAILED –<br>Request Failed<br>with status 502<br>/ Read-only<br>view<br>Implementatio|<br> <br>FR-035|
||||||n||
|TC-ADM-<br>16|TO-ADM-<br>10|Audit/Logging|Verify that a system-wide<br>action performed by any<br>user is captured in the audit<br>log.|The action is recorded in the<br>audit log with the correct<br>actor, action type, and<br>timestamp.|PASSED|FR-038|
|TC-ADM-<br>17|TO-ADM-<br>11|Security<br>(Negative)|Verify that an Admin<br>without explicit consent can<br>only view student data in<br>aggregated or anonymized<br>form.|System restricts the view to<br>aggregated/anonymized data<br>only and does not expose<br>individually identifiable<br>student records.|PASSED –<br>*But, Could<br>not verify if<br>explicit consent<br>isgiven|<br>NFR-010|
|TC-ADM-<br>18|TO-ADM-<br>12|File<br>Upload/Import<br>(Negative)|<br>Verify that the system<br>rejects a malformed data<br>import file.|System displays a validation<br>error identifying the issue<br>and does not import the<br>malformed data.|PASSED|FR-037|



# **E9: Test Case Log** 

_AEGIS: An AI-Enhanced Guidance and Integrated School Information System_ 

|**Test Name:**|AEGIS Functional/System Test – Faculty|
|---|---|
|**Test Case Author:**|Pesigan, Junior|
|**Tester Name:**|Pesigan, Junior|
|**Project ID/Name:**|AEGIS: An AI-Enhanced Guidance and Integrated School Information System|
|**Test Cycle ID:**|TestingPhase Cycle 3|
|**Date Tested:**|October 9, 2026|



|**Test**<br>**Case ID**<br>**Faculty **|**Test**<br>**Objective**<br>**ID**<br>**Module**|**Category**|**Condition**|**Expected Results**|**Actual**<br>**Results**|**Requirement**<br>**ID**|
|---|---|---|---|---|---|---|
|TC-FAC-<br>01|TO-FAC-<br>01|Authentication|Verify that a Faculty<br>member with valid<br>credentials can<br>successfully log in to<br>AEGIS.|Faculty is authenticated<br>and redirected to the<br>Faculty Dashboard.|FAILED<br>Student<br>Profile<br>Management<br>works, but<br>adding a<br>student<br>profile is not<br>functional|<br> <br>NFR-011|
|TC-FAC-<br>02|TO-FAC-<br>01|Authentication<br>(Negative)|<br>Verify that the system<br>denies access and<br>displays an appropriate<br>error when invalid<br>credentials are entered.|System displays a clear<br>error message indicating<br>the login failed and<br>denies access to the<br>Faculty Dashboard.|FAILED -<br>System<br>Allows<br>guardian<br>contact<br>numbers<br>containing<br>letters and<br>more than<br>11 digits to<br>be saved|NFR-002|
|TC-FAC-<br>03|TO-FAC-<br>02|Data Entry|Verify that a Faculty<br>member can<br>add/manage a student<br>profile within their<br>advisoryclass.|Student profile is<br>successfully updated and<br>stored in the system.|<br>PASSED|FR-007|
|TC-FAC-<br>04|TO-FAC-<br>02|Data Entry<br>(Negative)|Verify that the system<br>rejects a student profile<br>update with a missing<br>required field.|System displays a<br>validation error and does<br>not save the incomplete<br>profile.|<br>PASSED|FR-007|
|TC-FAC-<br>05|TO-FAC-<br>03|Data Entry|Verify that a Faculty<br>member can record<br>attendance for their<br>advisoryclass.|Attendance record is<br>successfully saved and<br>reflected in the class<br>record.|PASSED|FR-008|
|TC-FAC-<br>06|TO-FAC-<br>03|Data Entry<br>(Negative)|Verify that the system<br>rejects an attendance<br>entry with an invalid<br>date or status value.|System displays a<br>validation error and does<br>not save the invalid<br>attendance entry.|<br>PASSED|FR-008|



|TC-FAC-<br>07|TO-FAC-<br>04|Data Entry|Verify that a Faculty<br>member can add a<br>behavioral note for a<br>student in their advisory<br>class.|Behavioral note is<br>successfully saved and<br>stored in the student's<br>record.|FAILED-<br>Systems<br>Displays<br>“Request<br>Failed with<br>status 409”<br>when<br>encoding a<br>draftgrade|FR-009|
|---|---|---|---|---|---|---|
|TC-FAC-<br>08|TO-FAC-<br>04|Data Entry<br>(Negative)|Verify that the system<br>rejects an empty/blank<br>behavioral note<br>submission.|System displays a<br>validation error and does<br>not save an empty note.|<br>FAILED-<br>Unable to<br>verify<br>inavlid<br>grade<br>validation<br>due to an<br>existing<br>error when<br>encoding a<br>draftgrade|FR-009|
|TC-FAC-<br>09|TO-FAC-<br>05|Data Entry|Verify that a Faculty<br>member can encode a<br>grade for a student.|Grade is successfully<br>encoded and stored in<br>the Academic DB.|PASSED|FR-010|
|TC-FAC-<br>10|TO-FAC-<br>05|Data Entry<br>(Negative)|Verify that the system<br>rejects an out-of-range<br>or invalid grade value.|System displays a<br>validation error and does<br>not save the invalid<br>grade.|<br>BLOCKED<br>- Unable to<br>verify access<br>control<br>functionality|<br>FR-010|
|TC-FAC-<br>11|TO-FAC-<br>06|Data Entry|Verify that a Faculty<br>member can update a<br>previously encoded<br>grade.|Grade is successfully<br>updated and the change<br>is reflected in the<br>student's record.|FAILED-<br>Grade data<br>is<br>successfully<br>parsed, but<br>the excel<br>files fails to<br>import and<br>save the<br>records|FR-011|
|TC-FAC-<br>12|TO-FAC-<br>06|Access<br>Control<br>(Negative)|Verify that a Faculty<br>member cannot update a<br>grade for a student<br>outside their assigned<br>advisory class.|<br>System denies the action<br>and displays an access-<br>restricted message,<br>consistent with role-<br>based access control.|<br>FAILED-<br>Systems<br>displays a<br>fasiled to<br>import status<br>with 0 of 0<br>rows<br>processed,<br>without<br>displaying a<br>clear<br>validation<br>error for<br>malformed<br>grade data|<br>NFR-011|
|TC-FAC-<br>13|TO-FAC-<br>07|File<br>Upload/Impor|t<br>Verify that a Faculty<br>member can batch-<br>upload grades via a<br>valid CSV/Excel file.|Grades data is<br>successfully parsed and<br>stored for the<br>correspondingstudents.|FAILED –<br>System fails<br>to import the|FR-012|



||||||attendance<br>Excel file<br>and displays<br>a failed<br>status,<br>preventing<br>successful<br>attendance<br>data<br>processing.||
|---|---|---|---|---|---|---|
|TC-FAC-<br>14|TO-FAC-<br>07|File<br>Upload/Import<br>(Negative)|<br>Verify that the system<br>rejects a malformed<br>grades upload file.|System displays a<br>validation error and does<br>not import the<br>malformed data.|<br>FAILED –<br>System<br>displays a<br>failed import<br>status when<br>uploading<br>malformed<br>attendance<br>data, without<br>clearly<br>identifying<br>the validation<br>errors.|<br>FR-012|
|TC-FAC-<br>15|TO-FAC-<br>08|File<br>Upload/Import|Verify that a Faculty<br>member can batch-<br>upload attendance via a<br>valid CSV/Excel file.|Attendance data is<br>successfully parsed and<br>stored for the<br>correspondingstudents.|PASSED|FR-013|
|TC-FAC-<br>16|TO-FAC-<br>08|File<br>Upload/Import<br>(Negative)|<br>Verify that the system<br>rejects a malformed<br>attendance upload file.|System displays a<br>validation error and does<br>not import the<br>malformed data.|<br>PASSED|FR-013|
|TC-FAC-<br>17|TO-FAC-<br>09|Data Display|Verify that a Faculty<br>member can view a<br>consolidated one-page<br>summary of their<br>advisory class data.|A single-page summary<br>displaying key advisory<br>class data (profiles,<br>attendance, grades<br>overview) is displayed<br>correctly.|FAILED -<br>System<br>Generates<br>the subject<br>Performance<br>Report<br>without<br>displaying<br>“No Data<br>available”<br>message for<br>a subject<br>with no<br>recorded<br>grades|<br>FR-014|
|TC-FAC-<br>18|TO-FAC-<br>10|Report<br>Generation|Verify that a Faculty<br>member can generate<br>and export a subject<br>performance report.|Subject performance<br>report is successfully<br>generated and exported<br>as a downloadable file.|PASSED|FR-015|
|TC-FAC-<br>19|TO-FAC-<br>10|Report<br>Generation<br>(Negative)|Verify that the system<br>handles an export<br>request gracefully when<br>no data is available for<br>the selected subject.|System displays an<br>appropriate “no data<br>available” message<br>instead of generating an<br>empty or broken export<br>file.|FAILED<br>Student<br>Profile<br>Management<br>works, but<br>adding a<br>student<br>profile is not|<br> <br>FR-015|



||||||functional||
|---|---|---|---|---|---|---|
|TC-FAC-<br>20|TO-FAC-<br>11|Report<br>Generation|Verify that a Faculty<br>member can generate<br>and export an advisory<br>class summary report.|Advisory summary<br>report is successfully<br>generated and exported<br>as a downloadable file.|FAILED -<br>System<br>Allows<br>guardian<br>contact<br>numbers<br>containing<br>letters and<br>more than<br>11 digits to<br>be saved|FR-016|



# **E9: Test Case Log** 

_AEGIS: An AI-Enhanced Guidance and Integrated School Information System_ 

|**Test Name:**|AEGIS Functional/System Test – Guidance Counselor + Parent|
|---|---|
|**Test Case Author:**|Pitarde, Ken|
|**Tester Name:**|Pitarde, Ken|
|**Project ID/Name:**|AEGIS: An AI-Enhanced Guidance and Integrated School Information System|
|**Test Cycle ID:**|TestingPhase Cycle 3|
|**Date Tested:**|October 9, 2026|



|**Test**<br>**Case**|<br> <br>**Test**<br>**Objective**|<br>**Category**|**Condition**|**Expected**<br>**Results**|**Actual Results**|**Requirement**<br>**ID**|
|---|---|---|---|---|---|---|
|**ID**|**ID**||||||
|**Guid**|**ance Coun**|**selor Module**|||||
|TC-<br>GUI-<br>01|TO-GUI-<br>01|Authentication|Verify that a<br>Guidance<br>Counselor with<br>valid credentials<br>can successfully<br>login to AEGIS.|Counselor is<br>authenticated<br>and redirected<br>to the<br>Counselor<br>Dashboard.|PASSED|NFR-011|
|TC-<br>GUI-<br>02|TO-GUI-<br>01|Authentication<br>(Negative)|Verify that the<br>system denies<br>access and<br>displays an<br>appropriate error<br>when invalid<br>credentials are<br>entered.|System<br>displays a<br>clear error<br>message<br>indicating the<br>login failed<br>and denies<br>access to the<br>Counselor<br>Dashboard.|PASSED|NFR-002|
|TC-<br>GUI-<br>03|TO-GUI-<br>02|Data Entry|Verify that a<br>counselor can<br>document and<br>save a<br>consultation<br>record for a<br>student.|Consultation<br>record is<br>successfully<br>saved and<br>stored in the<br>system.|PASSED|Not specified<br>in SRS|
|TC-<br>GUI-<br>04|TO-GUI-<br>03|AI-Assisted Content<br>Creation|Verify that a<br>counselor can<br>create a student<br>assessment with<br>AI Chatbot-<br>assisted question<br>generation.|Assessment is<br>successfully<br>created with<br>AI-generated<br>questions<br>included.|FAILED – AI Generated Question<br>Not Implemented Yet<br>Note:<br>- Manual Question Adding only.<br>- UI can’t adopt when in different<br>sizes some buttons like the content in<br>the sidebar can’t click.<br>- Add question shows in the sidebar<br>when user in different sizes of the<br>screen<br>- Chat bot in student portal and<br>guidance portal, not implemented.|FR-027|



|TC-<br>GUI-<br>05|TO-GUI-<br>04|Workflow/Deployment|Verify that a<br>counselor can<br>deploy a created<br>assessment to an<br>assigned student.|Assessment is<br>successfully<br>deployed and<br>made<br>available to<br>the assigned<br>student.|FAILED – Notice shows “I don’t<br>have permission” to create<br>assessment.<br>Note:<br>- The Counselor account and Student<br>account combines without<br>authentication.<br>- It auto changes account login even,<br>withoutproper sign authentication.|FR-028|
|---|---|---|---|---|---|---|
|TC-<br>GUI-<br>06|TO-GUI-<br>05|Monitoring/Reporting|Verify that a<br>counselor can<br>monitor the<br>status/completion<br>of a deployed<br>assessment.|<br>Assessment<br>status and<br>completion<br>results are<br>successfully<br>displayed.|PASSED|FR-029|
|TC-<br>GUI-<br>07|TO-GUI-<br>06|AI/Alert|Verify that a<br>counselor<br>receives an AI-<br>generated at-risk<br>alert produced by<br>the Decision<br>Tree algorithm.|<br>Alert is<br>successfully<br>received and<br>displayed in<br>the Guidance<br>Module.|FAILED - Unexpected Application<br>Error!<br>object is not iterable (cannot read<br>property Symbol(Symbol.iterator))<br>Note:<br>- AI Features not implementedyet|FR-030|
|TC-<br>GUI-<br>08|TO-GUI-<br>07|Report Generation|Verify that a<br>counselor can<br>generate an<br>individual<br>student guidance<br>report.|Report is<br>successfully<br>generated for<br>the selected<br>student.|FAILED – Not Implemented Yet<br>Note:<br>- The guidance can download a<br>CSV/EXCEL file reports|FR-032|
|TC-<br>GUI-<br>09|TO-GUI-<br>08|Report Generation|Verify that a<br>counselor can<br>export a student<br>assessment<br>report to a file.|Report file is<br>successfully<br>exported and<br>downloadable.|PASSED|Not specified<br>in SRS<br>(closest: FR-<br>032)|
|TC-<br>GUI-<br>10|TO-GUI-<br>03|AI-Assisted Content<br>Creation (Negative)|Verify that the<br>system rejects<br>assessment<br>creation when<br>required fields<br>are missing.|System<br>displays a<br>validation<br>error and does<br>not save the<br>incomplete<br>assessment.|PASSED|FR-027|
|TC-<br>GUI-<br>11|TO-GUI-<br>04|Workflow/Deployment<br>(Negative)|<br>Verify that the<br>system prevents<br>deployment of an<br>assessment to an<br>invalid or<br>unassigned<br>student.|<br>System denies<br>the<br>deployment<br>and displays<br>an appropriate<br>error message.|PASSED – Invalid/Unassigned<br>students are not visible nor assignable|<br>FR-028|
|TC-<br>GUI-<br>12|TO-GUI-<br>06|AI/Alert (Edge Case)|Verify that the<br>Decision Tree at-<br>risk classification<br>handles<br>incomplete input<br>data gracefully<br>instead of<br>producing an<br>incorrect or<br>crashing result.|<br>System either<br>withholds<br>classification<br>until sufficient<br>data is<br>available or<br>clearly flags<br>the result as<br>based on<br>incomplete<br>data, without<br>crashingor|FAILED – AI Features not<br>implemented yet|FR-030, NFR-<br>007|



|||||producing a<br>misleading<br>alert.|||
|---|---|---|---|---|---|---|
|TC-<br>GUI-<br>13|TO-GUI-<br>02|Data Entry (Negative)|Verify that the<br>system rejects a<br>consultation<br>record<br>submission with<br>required fields<br>left blank.|System<br>displays a<br>validation<br>error and does<br>not save the<br>incomplete<br>consultation<br>record.|PASSED – Create Consultation<br>button is disabled unless session<br>notes is filled in.<br>Note:<br>- I can create a consultation with the<br>date and time in the past, there is no<br>notice that says invalid date/time.|Not specified<br>in SRS|
|TC-<br>GUI-<br>14|TO-GUI-<br>09|Access Control<br>(Negative)|Verify that a<br>Guidance<br>Counselor cannot<br>access Admin-<br>only functions<br>such as User<br>Management.|<br>System denies<br>access and<br>displays an<br>appropriate<br>access-<br>restricted<br>message,<br>consistent<br>with role-<br>based access<br>control.|<br>PASSED – System redirects user to<br>the correct role.<br>Note:<br>- There is something inside the<br>system a bug, that sometimes it<br>automatically login from guidance to<br>student same with student to<br>guidance.|NFR-011|
|**Pare**|**nt Module**||||||
|TC-<br>PAR<br>01|-<br>TO-PAR-<br>01|Authentication|Verify that a<br>Parent with valid<br>credentials can<br>successfully log<br>in to AEGIS.|<br>Parent is<br>authenticated<br>and redirected<br>to the Parent<br>Dashboard.|PASSED|NFR-011|
|TC-<br>PAR<br>02|-<br>TO-PAR-<br>01|Authentication<br>(Negative)|Verify that the<br>system denies<br>access and<br>displays an<br>appropriate error<br>when invalid<br>credentials are<br>entered.|<br>System<br>displays a<br>clear error<br>message<br>indicating the<br>login failed<br>and denies<br>access to the<br>Parent<br>Dashboard.|PASSED|NFR-002|
|TC-<br>PAR<br>03|-<br>TO-PAR-<br>02|Data Display|Verify that a<br>Parent can view<br>their child's<br>academic<br>performance in<br>real time.|Academic<br>performance<br>data is<br>displayed<br>accurately and<br>reflects real-<br>time updates.|<br>PASSED|FR-024|
|TC-<br>PAR<br>04|-<br>TO-PAR-<br>03|Data Display|Verify that a<br>Parent can view<br>their child's<br>attendance in real<br>time.|<br>Attendance<br>data is<br>displayed<br>accurately and<br>reflects real-<br>time updates.|<br>FAILED – Not yet implemented|FR-025|
|TC-<br>PAR<br>05|-<br>TO-PAR-<br>04|Data Display|Verify that a<br>Parent can view<br>their child's<br>behavioral<br>concerns in real<br>time.|Behavioral<br>concern data<br>is displayed<br>accurately and<br>reflects real-<br>time updates.|<br>FAILED – Not yet implemented<br>Note:<br>- UI can’t adopt in different sizes of<br>the screen.|FR-026|
|TC-<br>PAR<br>06|-<br>TO-PAR-<br>05|Notification|Verify that a<br>Parent receives a<br>real-time|<br>Notification is<br>successfully<br>received and|<br>FAILED – Add this when parents can<br>view the notification in in full<br>messagejust like apop-up.|<br>Not specified<br>in SRS (FR-<br>020–022 cover|



||||notification<br>regarding their<br>child's grades,<br>attendance, or<br>concerns.|displayed to<br>the Parent.||Student<br>notifications<br>only, not<br>Parent)|
|---|---|---|---|---|---|---|
|TC-<br>PAR-<br>07|TO-PAR-<br>06|Security (Negative)|Verify that a<br>Parent cannot<br>view data for a<br>student not<br>linked to their<br>account.|System denies<br>access to the<br>unrelated<br>student's data<br>and displays<br>an appropriate<br>access-<br>restricted<br>message.|PASSED – Only linked students are<br>selectable|NFR-011|
|TC-<br>PAR-<br>08|TO-PAR-<br>07|Data Display (Edge<br>Case)|Verify that the<br>Parent<br>Dashboard<br>handles the<br>absence of recent<br>data gracefully<br>(e.g., a newly<br>enrolled student<br>with no records<br>yet).|<br>Dashboard<br>displays an<br>appropriate<br>“no data<br>available”<br>state instead<br>of an error or<br>a<br>blank/broken<br>layout.|PASSED – Shows N/A labels to data|<sup>FR-024, FR-</sup><br>025, FR-026|



# **E9: Test Case Log** 

_AEGIS: An AI-Enhanced Guidance and Integrated School Information System_ 

|**Test Name:**|AEGIS Functional/System Test – Student + System / Cross-Cutting|
|---|---|
|**Test Case Author:**|Tagpeo, John Russel|
|**Tester Name:**|Tagpeo, John Russel|
|**Project ID/Name:**|AEGIS: An AI-Enhanced Guidance and Integrated School Information System|
|**Test Cycle ID:**|TestingPhase Cycle 3|
|**Date Tested:**|October 9, 2026|



|**Test**<br>**Case**<br>|**Test**<br>**Objective**<br>|**Category**|**Condition**|**Expected Results**|**Actual Results**|**Requirement**<br>**ID**|
|---|---|---|---|---|---|---|
|**ID**|**ID**||||||
|**Studen**|**t Module**||||||
|TC-<br>STU-01|TO-STU-<br>01|Authentication|Verify that a Student<br>with valid credentials<br>can successfully log in<br>to AEGIS.|Student is<br>authenticated and<br>redirected to the<br>Student Dashboard.|**PASSED**|NFR-011|
|TC-<br>STU-02|TO-STU-<br>01|Authentication<br>(Negative)|<br>Verify that the system<br>denies access and<br>displays an appropriate<br>error when invalid<br>credentials are entered.|System displays a clear<br>error message<br>indicating the login<br>failed and denies<br>access to the Student<br>Dashboard.|<br>**PASSED**|NFR-002|
|TC-<br>STU-03|TO-STU-<br>02|Data Display|Verify that a Student<br>can view their own<br>grades.|Grades are<br>successfully displayed<br>and match the student's<br>actual records.|<br>**PASSED**|FR-017|
|TC-<br>STU-04|TO-STU-<br>03|Data Display|Verify that a Student<br>can view their own<br>class schedule.|Class schedule is<br>successfully displayed<br>and matches the<br>student's actual<br>enrollment.|**PASSED**|FR-018|
|TC-<br>STU-05|TO-STU-<br>04|Data Display|Verify that a Student<br>can view their own<br>attendance records.|Attendance records are<br>successfully displayed<br>and match the student's<br>actual records.|<br> <br>**PASSED**|FR-019|
|TC-<br>STU-06|TO-STU-<br>05|Notification|Verify that a Student<br>receives a real-time<br>notification regarding<br>grades, attendance, or<br>concerns.|Notification is<br>successfully received<br>and displayed to the<br>Student.|**PASSED**|FR-020, FR-<br>021, FR-022|
|TC-<br>STU-07|TO-STU-<br>06|Assessment|Verify that a Student<br>can take an AI-<br>generated assessment<br>deployed by the<br>Guidance Counselor.|Assessment loads<br>correctly, accepts<br>responses, and records<br>the submission.|PASSED|FR-023|
|TC-<br>STU-08|TO-STU-<br>07|Chatbot|Verify that a Student<br>receives a relevant<br>response when<br>interacting with the AI<br>Chatbot.|Chatbot returns a<br>relevant response<br>based on the<br>recognized user intent;<br>concerning queries are|**PASSED –**<br>**make**<br>**notification**<br>**clickable to view**<br>**full the message **|<br>FR-031<br>(escalation<br>only)|



|||||escalated per FR-031.|**and**<br>**automatically**<br>**mark them as**<br>**read.**||
|---|---|---|---|---|---|---|
|TC-<br>STU-09|TO-STU-<br>08|Security<br>(Negative)|Verify that a Student<br>cannot view another<br>student's grades,<br>attendance, or personal<br>records.|<br>System denies access<br>and displays an<br>appropriate access-<br>restricted message,<br>consistent with NFR-<br>009.|**PASSED**|NFR-009|
|TC-<br>STU-10|TO-STU-<br>09|Assessment<br>(Negative)|Verify that the system<br>prevents a Student<br>from resubmitting an<br>assessment that has<br>already been completed<br>and submitted.|<br>System blocks the<br>resubmission and<br>displays a message<br>indicating the<br>assessment has already<br>been completed.|<br>**PASSED**|FR-023|
|TC-<br>STU-11|TO-STU-<br>10|Analytics|Verify that a Student<br>receives AI-driven<br>academic resource<br>recommendations.|Relevant academic<br>resource<br>recommendations are<br>generated and<br>displayed, consistent<br>with the student's<br>academicprofile.|**PASSED**|FR-039, FR-<br>040|
|TC-<br>STU-12|TO-STU-<br>10|Analytics<br>(Edge Case)|Verify that the<br>recommendation<br>engine handles a<br>student profile with<br>insufficient data<br>gracefully.|System displays a<br>default/fallback state<br>(e.g., general resources<br>or a “not enough data<br>yet” message) rather<br>than an error or empty|<br>**PASSED**|FR-039, FR-<br>040|
|**System**|**/ Cross-C**|**utting Module**||broken display.|||
|TC-<br>SYS-01|TO-SYS-<br>01|Authentication|Verify that a new user<br>can successfully<br>register for an AEGIS<br>account.|Account is<br>successfully created,<br>and the appropriate<br>role is assigned per the<br>registration context.|**FAILED – no**<br>**register option**<br>**on the login**<br>**screen**|FR-001|
|TC-<br>SYS-02|TO-SYS-<br>01|Authentication<br>(Negative)|<br>Verify that the system<br>prevents duplicate<br>registration using an<br>already-registered<br>email address.|System rejects the<br>registration and<br>displays a message<br>indicating the email is<br>already in use.|**FAILED –**<br>**Cannot test**<br>**duplicate email**<br>**validation due**<br>**the lack of a**<br>**registration**<br>**page.**|FR-001, NFR-<br>006|
|TC-<br>SYS-03|TO-SYS-<br>02|Performance|Verify that the system<br>maintains acceptable<br>response times under<br>multiple simultaneous<br>user sessions (tested at<br>a reduced scale per<br>SQAP Section 14.6).|Response time does<br>not degrade by more<br>than 2 seconds<br>compared to single-<br>user baseline, at the<br>tested scale.|**FAILED –**<br>**cannot test**<br>**manually ,**<br>**requires**<br>**automated load**<br>**testing  tools for**<br>**concurrent**<br>**users**|NFR-004|
|TC-<br>SYS-04|TO-SYS-<br>03|Performance|Verify that each role-<br>specific dashboard<br>loads and displays its<br>data within 5 seconds<br>of login.|Dashboard loads and<br>displays all data within<br>5 seconds under<br>normal network<br>conditions.|<br>**PASSED**|NFR-005|
|TC-<br>SYS-05|TO-SYS-<br>04|Reliability|Verify that the<br>Decision Tree|Both runs produce the<br>same at-risk|**FAILED –**<br>**cannot test via**|NFR-007|



||||algorithm produces<br>consistent at-risk<br>classification output<br>when given the same<br>input data.|classification result for<br>the identical input<br>data.|**student UI,**<br>**requires**<br>**backend ML**<br>**model**<br>**verification**||
|---|---|---|---|---|---|---|
|TC-<br>SYS-06|TO-SYS-<br>05|Security|Verify that user<br>passwords are stored<br>using a hashing<br>algorithm and never<br>stored inplaintext.|The stored value is a<br>hashed representation<br>of the password, not<br>the plaintext password.|**PASSED**|NFR-008|
|TC-<br>SYS-07|TO-SYS-<br>06|Access<br>Control<br>(Negative)|Verify that an<br>authenticated user<br>cannot access a page or<br>endpoint belonging to a<br>role other than their<br>own by directly<br>enteringthe URL.|<br> <br>System denies access<br>and redirects or<br>displays an access-<br>restricted message,<br>consistent with role-<br>based access control.|**PASSED**|NFR-011|
|TC-<br>SYS-08|TO-SYS-<br>07|Availability|Verify that users<br>receive advance notice<br>of scheduled system<br>maintenance.|All users receive a<br>maintenance<br>notification at least 24<br>hours in advance of the<br>scheduled<br>maintenance.|<br>**PASSED**|NFR-012|
|TC-<br>SYS-09|TO-SYS-<br>08|Security<br>(Negative)|Verify that the system<br>safely handles<br>malformed or<br>potentially malicious<br>input submitted<br>through a text field.|System safely rejects,<br>escapes, or sanitizes<br>the input without<br>executing it or<br>corrupting the stored<br>data.|**PASSED**|NFR-002|
|TC-<br>SYS-10|TO-SYS-<br>09|Compatibility|Verify that core<br>AEGIS functions<br>behave correctly across<br>supported browsers.|<br>The system functions<br>correctly and<br>consistently across all<br>three supported<br>browsers.|**PASSED**|NFR-014|
|TC-<br>SYS-11|TO-SYS-<br>10|Compatibility|Verify that the system's<br>interface remains<br>usable across the<br>specified range of<br>screen sizes.|<br>Interface remains<br>legible, navigable, and<br>functional at both<br>320px and 1920px,<br>with no broken or<br>clipped elements.|**PASSED**|NFR-015|
|TC-<br>SYS-12|TO-SYS-<br>11|Usability|Verify that AEGIS<br>presents a consistent<br>layout and navigation<br>menu across different<br>pages and roles.|Layout structure and<br>navigation menu<br>remain consistent in<br>placement and<br>behavior across all<br>visited pages.|**PASSED –**<br>**improve sidebar**<br>**responsiveness**<br>**on 320px mobile**<br>**screen and**<br>**ensure it stays**<br>**fixed while**<br>**scrolling**|<br> <br>NFR-001|
|TC-<br>SYS-13|TO-SYS-<br>12|Performance|Verify that a typical<br>user action (e.g., saving<br>a form) completes<br>within an acceptable<br>time under normal<br>network conditions.|<br>The action completes<br>within 5 seconds under<br>normal network<br>conditions.|<br>**PASSED**|NFR-003|



