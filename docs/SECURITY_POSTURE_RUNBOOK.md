# Security posture runbook

What a deployment has to get right before student data is put in it, and how to
check that it did.

The application covers the **data in the columns**: the student free text and
the counseling narrative are encrypted with AES-SIV before they are written.
The **disk** — the Postgres volume, its snapshots, its backups and the
transit between them — is the platform's business and is not something this
codebase can do. Both halves are here so neither is assumed.

---

## 1. What the application encrypts

| Model | Field | What it is |
|---|---|---|
| `chatbot.ChatMessage` | `message` | what the student typed |
| `chatbot.ChatMessage` | `reply` | the assistant's reply |
| `chatbot.ChatMessage` | `detection_detail` | what the two detection layers decided, including the model's rationale |
| `chatbot.Flag` | `summary` | the line a counselor reads first |
| `chatbot.FlagAction` | `note` | private case notes |
| `guidance.BehavioralNote` | `note_text` | a teacher's observation about a student |
| `guidance.ConsultationRecord` | `session_notes` | a counselor's session notes |
| `guidance.ConsultationRecord` | `recommendations` | what the counselor advised |
| `guidance.InterventionStep` | `description` | what is planned for a student |
| `guidance.ProgressNote` | `note_text` | a progress note |

Everything else is clear text: grades, attendance, risk scores, structured
concern categories, announcement text. Those are structured records, not
narrative about a child, and encrypting them is a much larger change.

Run `manage.py security_posture` to see this list from the deployment itself.

## 2. The key

* Generated with `python manage.py generate_encryption_key` — 512 bits,
  base64.
* Stored in the environment as `FIELD_ENCRYPTION_KEYS=key_id:value`. Never in
  the repository, never in the database.
* **The first key encrypts; every key decrypts.** That is what makes a
  rotation possible without a data migration.

### Rotation

1. Generate a new key.
2. Add it to `FIELD_ENCRYPTION_KEYS` **first**, keeping the old one:
   `FIELD_ENCRYPTION_KEYS=k2:<new>,k1:<old>`.
3. Deploy. New writes use `k2`; old rows still read with `k1`.
4. Once nothing is encrypted with `k1`, drop it from the list.

Rolling back to a single key is safe: the old key can still read everything it
wrote.

**A key that is lost cannot be recovered.** Rows encrypted with it become
unreadable, and the deployment will raise rather than serve a counselor a
wall of ciphertext. Keep the key in the platform's secret store, and keep a
copy of the old key for the length of one rotation.

## 3. Checking a deployment

```powershell
python manage.py security_posture
```

It prints, without printing any key:

* whether field encryption is on, with which algorithm and how many keys;
* every encrypted column, from the live models;
* whether encryption is *required* in this environment;
* the acknowledgment window per severity;
* the retention window — and says so loudly when it is unset, because nothing
  is then ever deleted;
* the model in use, how many API keys are spent, and why the last call failed.

The same facts are on the administrator console at `/app/admin/chatbot`.

## 4. Questions to ask the platform

These are the things application code cannot answer. Get them answered in
writing before the deployment carries real students.

**Storage**

1. Is the Postgres data volume encrypted at rest? (Not "is the database
   encrypted" — is the *volume*.)
2. Are automated backups encrypted, and with a key separate from the volume's?
3. Are snapshots and read replicas encrypted too?
4. Where are those encryption keys held, and who can read them?

**Access**

5. Who can reach a production database or a snapshot, and is that access
   logged?
6. Is there a copy of the data in a staging or support environment, and is it
   encrypted the same way?
7. Can a support engineer read production rows, and is that recorded?

**Transfers and exit**

8. Is the traffic between the application and the database encrypted, and
   between the database and its replicas?
9. What happens to the volumes and the backups when the deployment is
   deleted — are they destroyed or kept?
10. Has anyone ever restored a backup into a clean environment? A backup
    that has never been restored is a hypothesis, not a backup.

## 5. What to do when something is wrong

**The console says "Field encryption is OFF".** No key is configured. Generate
one and set `FIELD_ENCRYPTION_KEYS`, then deploy. The rows written while it
was off are still in plain text; the next write encrypts them, and
`chatbot/0005_encrypt_existing_text` and `guidance/0007_encrypt_existing_narrative`
rewrite the ones already stored.

**A read fails with "FIELD_ENCRYPTION_KEYS has no key with id 'k1'".** A key
that wrote the row is no longer configured. Put it back — this is the
rotation mistake of dropping the old key too early.

**The model is unavailable and the console says "quota exhausted".** Every
key has spent its quota; Layer 1 is screening alone and anything it misses is
marked for manual review. Add a key or fix the plan. Nothing is lost while
Layer 1 carries the screening — but recall is lower, so manual review is
doing the work.

**The escalation timer did not fire.** It runs when the guidance inbox or the
administrator dashboard is opened. A deployment that needs a hard guarantee
schedules `python manage.py escalate_stale_flags` — every minute or every
five — instead of relying on somebody to look.

**Nothing is being deleted.** `chatbot.retention_days` is 0, which means "keep
everything". Set it to a number in days and schedule
`python manage.py purge_chatbot_data`. Open flags are never deleted at any
age, whatever the window says.
