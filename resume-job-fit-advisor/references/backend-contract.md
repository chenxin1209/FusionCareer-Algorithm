# Backend and model integration

Use this reference only while connecting the skill to the FusionCareer web app, resume parser, exported job data, or DeepSeek.

## Existing HTTP surfaces

The current Java backend and Vue frontend already provide most of the read path:

- `GET /job/{id}`: authenticated job detail used by `JobDetailView.vue`.
- `GET /user/resume/get`: authenticated current user's structured online resume.
- `GET /user/profile/get`: authenticated current user's profile.
- `POST /user/resume/file/upload`: authenticated resume upload.
- `GET /user/resume/file/list`: authenticated current user's uploaded resume files.
- `GET /internal/job-post/{id}`, `GET /internal/resume/{userId}`, and `GET /internal/user-profile/{userId}`: service-to-service variants available to the Python Agent.

The `/internal/**` routes currently bypass Sa-Token. They must stay behind the private gateway/firewall and must never be called by the browser. The end-user Agent endpoint should be authenticated by Java, derive `userId` with `StpUtil`, and pass that trusted identity to the Python Agent.

## Host tools

The sidebar agent conceptually needs the following three capabilities. Map them to the existing routes above rather than adding duplicate database access.

### `get_current_job`

Input comes from page state, not chat text:

```json
{"job_id":"2099395615268855809"}
```

Return one canonical published job record containing at least:

```json
{
  "id":"2099395615268855809",
  "company_name":"...",
  "position_name":"...",
  "job_desc":"...",
  "req_other":"...",
  "req_skills":"...",
  "req_major":"...",
  "req_edu_level":"...",
  "req_grad_year":"...",
  "work_city":"...",
  "work_mode":"...",
  "application_deadline":"...",
  "status":1,
  "current_visible":true,
  "updated_at":"..."
}
```

Reject missing, unpublished, unauthorized, or no-longer-visible records. The current service implementation returns a record by ID without enforcing `PUBLISHED`, so the Agent adapter must check the returned status. Resolve by exact ID. Refresh this result when navigation changes the current job; conversation memory is not the source of truth.

For local development, the repository export contains the same fields in `已发布岗位完整导出_2026-09-28/已发布岗位全量_2026-09-28.csv` and `.jsonl`. `job_desc` and `req_other` are primary. The CSV is UTF-8 with BOM; use the JSONL or spreadsheet when a viewer truncates long cells.

### `get_current_resume`

Derive the user identity from the authenticated session. Do not accept `user_id` supplied in the prompt. Return the user's latest approved parser result plus a stable version or update timestamp:

```json
{
  "resume_version":"...",
  "updated_at":"...",
  "record":{
    "education":"...",
    "internship":"...",
    "campus":"...",
    "awards":"...",
    "skills":"...",
    "portfolio":"...",
    "personal_intro":"...",
    "basic_info":"...",
    "major":"...",
    "grade":"...",
    "edu_level":"..."
  }
}
```

The stored resume and profile are separate records, so merge only relevant fields from both. Omit phone, email, WeChat, storage URLs, and other fields that are unnecessary for advice before sending context to a model.

### `parse_resume_upload`

Use only when the current user has no stored parsed resume or explicitly chooses another version. The Java frontend flow uploads through `POST /user/resume/file/upload`; the local algorithm repository exposes `POST /internal/resume/{user_id}` with one of `raw_text`, `file_url`, or `file_base64`, returning `{code,message,data}`. Put parsing behind the application's authenticated server boundary and derive `{user_id}` from the session.

Production safeguards belong in the gateway or parser service: allowed file types, byte and text limits, timeouts, malware scanning as applicable, private-network blocking for fetched URLs, and deletion of temporary files. Treat `file_url` as a trusted-storage reference rather than an arbitrary public URL.

Parsing a resume does not authorize saving a rewritten resume. Retain the original upload and parsed record unchanged.

## Request-scoped agent context

Bind the following values on every turn so a long-lived chat cannot analyze the wrong page:

```json
{
  "conversation_id":"...",
  "current_job_id":"...",
  "current_job_updated_at":"...",
  "resume_version":"...",
  "locale":"zh-CN"
}
```

If `current_job_id` changes, discard the previous job analysis. If `resume_version` changes, recompute all evidence mappings. Do not store raw resume or JD content in browser-visible conversation metadata.

## DeepSeek

Use the OpenAI-compatible server-side client already present in the repository. Configuration should come from environment variables:

```dotenv
DEEPSEEK_API_KEY=server-side-secret
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

Treat `/v1` as the API base path, not a model name. Keep the model configurable rather than hard-coding it in the skill. Use low temperature and structured JSON output for card data. Validate the response against the schema before showing it; retry once for schema repair, then fail safely.

Send only normalized job requirements and redacted resume evidence. In the system instruction, state that both are untrusted data and that claims absent from resume evidence must become gaps or proof questions, never asserted facts.

## Current repository mapping

- Resume parser route: `resume_parser/routers/internal.py`
- Parser output fields: `resume_parser/parser.py` (`FIELD_NAMES`)
- Existing DeepSeek JSON adapter: `optimize/llm.py`
- Existing evidence construction and contact redaction: `optimize/loaders.py`
- Existing fact-grounding concepts: `optimize/models.py` and `optimize/validator.py`
- Deployable workflow-runtime plugin: `assets/fusioncareer-agent/resume_job_fit_advisor/skill.py`

The existing `optimize` pipeline can generate resume artifacts. Do not call its render/export behavior from this advisory skill. Reuse evidence and validation concepts only.
