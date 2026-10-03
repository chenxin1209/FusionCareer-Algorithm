# Advice response contract

Use this contract when the web UI needs structured sidebar cards or when the backend persists an analysis result. Natural-language chat replies do not need to expose it.

```json
{
  "jobId":"string",
  "resumeVersion":"string",
  "summary":"string",
  "fitLevel":"strong|mixed|weak|unknown",
  "requirements":[
    {
      "requirementId":"req-001",
      "text":"string",
      "sourceField":"jobDesc|reqOther|reqSkills|reqMajor|reqEduLevel|reqGradYear|other",
      "kind":"required|preferred|responsibility|constraint",
      "status":"matched|partial|gap",
      "evidenceIds":["resume-internship"],
      "reason":"string",
      "action":"string"
    }
  ],
  "sectionSuggestions":[
    {
      "priority":"high|medium|low",
      "section":"internship|projects|campus|awards|skills|education|summary|other",
      "issue":"string",
      "action":"string",
      "example":"string",
      "evidenceIds":["resume-internship"],
      "needsUserConfirmation":false
    }
  ],
  "proofQuestions":[
    {
      "question":"string",
      "whyItMatters":"string",
      "relatedRequirementIds":["req-001"]
    }
  ],
  "safeguards":{
    "resumeModified":false,
    "unsupportedClaimsAsserted":false
  }
}
```

## Validation rules

- `jobId` and `resumeVersion` must match the request-scoped context used for analysis.
- Every matched or partial requirement needs at least one valid resume `evidenceId`. A gap has none.
- Examples with no complete factual support must set `needsUserConfirmation` to `true` and use conditional wording.
- `resumeModified` must always be `false` for this skill.
- Do not include raw phone, email, WeChat, user ID, storage URL, or authentication data.
- `fitLevel` is qualitative. Do not translate it into a percentage unless the caller supplies and displays an explicit rubric.
