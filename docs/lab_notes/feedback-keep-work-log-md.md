# feedback-keep-work-log-md

_Write every stage of radar2/guru work into ~/radar2/guru10ms/docs/WORK_LOG.md as it happens (sessions get compacted); commit and push it to shankarjatti/guru10ms._

User (2026-09-28): "every time keep updating things on .md file ... some time we need to compact the session".

**Why:** sessions are compacted or restarted; details only in the conversation get lost.
**How to apply:**
- Read `~/radar2/guru10ms/docs/WORK_LOG.md` at the start of any radar2 session. Its CURRENT STATE block says where things are and what is next.
- After every stage (a test, a fix, a decision, a user instruction), add a dated entry at the top: what was asked, done, measured (numbers + results file), failed, decided, next. Keep the CURRENT STATE block true.
- Commit and push it to https://github.com/shankarjatti/guru10ms (public, the user chose that) along with the code change it describes. Put finished findings in `docs/DEVELOPMENT_LOG.md` / `docs/lab_notes/` too.
- Only measured facts, per [feedback-permanent-real-solutions](feedback-permanent-real-solutions.md). Related: [guru-known-good-sources](guru-known-good-sources.md).
