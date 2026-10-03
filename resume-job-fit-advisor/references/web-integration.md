# Website integration

Use this reference when connecting the existing Java backend, Python `fusioncareer-agent`, and Vue job-detail page.

## Observed repository state

- Backend `main` exposes authenticated `GET /job/{id}`, `GET /user/resume/get`, `GET /user/profile/get`, resume upload/list/download routes, and private `/internal/**` equivalents.
- Backend `main` contains a Python Agent workflow runtime with `BaseSkill`, runtime plugin installation, typed data classes, and preset workflows.
- `PythonServiceClient` currently has only `/api/v1/ping`; there is no Java-to-Agent resume-advice method yet.
- Frontend `codex/frontend-integration` loads the route job with `apiJson(`/job/${route.params.id}`)` in `JobDetailView.vue`. It has a resume picker and profile resume upload/parse UI, but no Agent panel.
- The public frontend `main` is empty; use the integration branch as the implementation baseline.

## Recommended request path

```text
JobDetailView.vue
  -> POST /agent/resume-advice                 (new Java authenticated route)
       Java derives userId from StpUtil
       Java validates jobId as a decimal string
       Java forwards userId, jobId, message
  -> POST /api/workflows/resume-job-fit-advisor/run  (private Agent service)
       workflow plugin reads /internal/job-post/{jobId}
       workflow plugin reads /internal/resume/{userId}
       workflow plugin reads /internal/user-profile/{userId}
       DeepSeek returns validated advice JSON
  <- Java returns only advice data to the browser
```

Do not let the browser call `/internal/**`, the Agent admin APIs, or send an authoritative `userId`. Keep `AGENT_ADMIN_TOKEN` and `DEEPSEEK_API_KEY` server-side.

Use string IDs end to end. Existing Snowflake-style IDs exceed JavaScript's exact integer range, so `jobId` and `userId` must not be converted through `Number` before transport.

## Vue placement

Mount a collapsible Agent card in the existing `.apply-sidebar` in `JobDetailView.vue`. Pass `String(route.params.id)` as the page-scoped job identifier. On route-ID change:

- cancel the in-flight advice request;
- clear job-specific messages or start a new conversation scope;
- send the new `jobId` on the next request;
- keep the panel read-only with respect to resume storage.

If the response status is `needs_resume`, show a link to `/#/profile?tab=resume`. The profile page already supports uploading a resume and maintaining the structured resume fields.

The Agent card should display the structured response from `references/advice-schema.md` as a short conclusion, matched/gap cards, prioritized changes, and proof questions. Do not expose evidence IDs unless they help debugging; do not render model-produced HTML.

## Runtime plugin assets

The deployable files are:

- `assets/fusioncareer-agent/resume_job_fit_advisor/skill.py`
- `assets/fusioncareer-agent/resume_job_fit_advisor/introduces.json`
- `assets/fusioncareer-agent/workflows/resume-job-fit-advisor.json`

Install `skill.py` through `PUT /api/admin/skills/resume_job_fit_advisor`, passing the contents of `introduces.json` as `introduces`. Then install the workflow with `PUT /api/admin/workflows/resume-job-fit-advisor`. Both admin calls require `X-Agent-Admin-Token` and belong in deployment tooling, not frontend code.

Configure the Agent service for DeepSeek:

```dotenv
BACKEND_BASE_URL=http://fusioncareer-java:9100
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=server-side-secret
LLM_MODEL=deepseek-chat
```

## Missing integration work

The skill asset is intentionally read-only. Production integration still needs:

1. a Java authenticated proxy/controller method that derives the user identity;
2. a matching `PythonServiceClient` POST method or a dedicated Agent client;
3. an end-user chat/advice route on the private Agent boundary or the preset-workflow call shown above;
4. the Vue sidebar component and request cancellation on job navigation;
5. rate limits, request-size limits, conversation retention rules, and audit logging without raw resume content.

These are application integration tasks, not permissions granted to the skill.
