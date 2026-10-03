"""Validate the deployable FusionCareer Agent plugin without network or API keys."""

from __future__ import annotations

import ast
import asyncio
import re
import sys
import types
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


FORBIDDEN_IMPORT_ROOTS = {
    "os",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
    "ctypes",
    "multiprocessing",
    "pickle",
    "builtins",
}


class BaseSkill(ABC):
    @abstractmethod
    def define(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class BackendClient:
    pass


class LLMClient:
    pass


def _install_stubs() -> None:
    app = types.ModuleType("app")
    core = types.ModuleType("app.core")
    base_skill = types.ModuleType("app.core.base_skill")
    integrations = types.ModuleType("app.integrations")
    backend = types.ModuleType("app.integrations.backend")
    llm = types.ModuleType("app.integrations.llm")
    base_skill.BaseSkill = BaseSkill
    backend.BackendClient = BackendClient
    llm.LLMClient = LLMClient
    sys.modules.update(
        {
            "app": app,
            "app.core": core,
            "app.core.base_skill": base_skill,
            "app.integrations": integrations,
            "app.integrations.backend": backend,
            "app.integrations.llm": llm,
        }
    )


def _check_imports(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        roots: list[str] = []
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".", 1)[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots = [node.module.split(".", 1)[0]]
        blocked = sorted(set(roots) & FORBIDDEN_IMPORT_ROOTS)
        if blocked:
            raise AssertionError(f"Plugin uses forbidden imports: {blocked}")


def main() -> None:
    skill_root = Path(__file__).resolve().parents[1]
    plugin_path = skill_root / "assets" / "fusioncareer-agent" / "resume_job_fit_advisor" / "skill.py"
    source = plugin_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(plugin_path))
    _check_imports(tree)
    _install_stubs()

    namespace = {"__name__": "fusioncareer_agent_plugin_resume_job_fit_advisor"}
    exec(compile(tree, str(plugin_path), "exec"), namespace)  # noqa: S102 - local validated asset

    skill_markdown = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    prompt_match = re.search(
        r"<!-- BUILTIN_PROMPT_START -->\s*```text\s*(.*?)\s*```\s*<!-- BUILTIN_PROMPT_END -->",
        skill_markdown,
        re.DOTALL,
    )
    assert prompt_match is not None, "SKILL.md is missing the marked built-in prompt"
    documented_prompt = prompt_match.group(1).strip()
    runtime_prompt = namespace["_SYSTEM_PROMPT"].strip()
    assert documented_prompt == runtime_prompt, "SKILL.md and runtime prompts have diverged"
    for domain in ("新闻媒体", "内容与新媒体运营", "品牌传播与公关", "市场营销与广告", "管培生"):
        assert domain in runtime_prompt, f"Built-in prompt is missing target domain: {domain}"

    skill_classes = [
        value
        for value in namespace.values()
        if isinstance(value, type) and issubclass(value, BaseSkill) and value is not BaseSkill
    ]
    assert len(skill_classes) == 1
    definition = skill_classes[0]().define()
    assert definition["name"] == "resume_job_fit_advisor"
    assert definition["inputs"] == {"user_id": "text", "job_id": "text", "question": "text"}
    assert definition["outputs"] == {"advice": "resume_advice"}

    normalize_result = namespace["_normalize_result"]
    result = normalize_result(
        {
            "summary": "测试",
            "fitLevel": "strong",
            "requirements": [{"text": "Python", "status": "matched", "evidenceIds": ["unknown"]}],
            "sectionSuggestions": [
                {"priority": "low", "example": "补充作品链接", "evidenceIds": ["resume-skills"]},
                {"priority": "high", "example": "提升 30%", "evidenceIds": []},
            ],
            "proofQuestions": [
                {"question": f"追问 {index}", "relatedRequirementIds": []} for index in range(4)
            ],
        },
        job_id="2099395615268855809",
        resume_version="v1",
        valid_evidence={"resume-skills"},
    )
    assert result["requirements"][0]["status"] == "gap"
    assert result["sectionSuggestions"][0]["needsUserConfirmation"] is True
    assert result["sectionSuggestions"][0]["example"].startswith("仅在属实时使用")
    assert [item["priority"] for item in result["sectionSuggestions"]] == ["high", "low"]
    assert len(result["proofQuestions"]) == 3
    assert result["safeguards"] == {"resumeModified": False, "unsupportedClaimsAsserted": False}

    class FakeBackend:
        async def _get(self, _path: str) -> dict[str, Any]:
            return {
                "id": "2099395615268855809",
                "status": "PUBLISHED",
                "positionName": "新媒体运营实习生",
                "jobDesc": "负责选题策划、内容编辑与短视频制作",
                "reqSkills": "文字功底、视频剪辑、数据复盘",
            }

        async def get_resume(self, _user_id: int) -> dict[str, Any]:
            return {
                "skills": "新闻写作、剪映",
                "internship": "参与校园媒体选题和短视频制作",
                "updatedAt": "v2",
            }

        async def get_profile(self, _user_id: int) -> dict[str, Any]:
            return {"email": "private@example.com", "major": "新闻学"}

        async def close(self) -> None:
            return None

    class FakeLLM:
        def __init__(self) -> None:
            self._client = None

        async def chat_json(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "summary": "具备部分直接证据。",
                "fitLevel": "mixed",
                "requirements": [
                    {
                        "requirementId": "req-001",
                        "text": "选题策划与短视频制作",
                        "sourceField": "reqSkills",
                        "kind": "required",
                        "status": "matched",
                        "evidenceIds": ["resume-internship"],
                        "reason": "校园媒体经历直接支持",
                        "action": "补充个人职责、制作流程与已确认的传播结果",
                    }
                ],
                "sectionSuggestions": [],
                "proofQuestions": [],
            }

    namespace["BackendClient"] = FakeBackend
    namespace["LLMClient"] = FakeLLM
    execution = asyncio.run(
        skill_classes[0]().execute(
            {
                "user_id": "2099395615268855808",
                "job_id": "2099395615268855809",
                "question": "我应该先改哪里？",
            }
        )
    )
    advice = execution["advice"]
    assert advice["jobId"] == "2099395615268855809"
    assert advice["requirements"][0]["status"] == "matched"
    assert advice["safeguards"]["resumeModified"] is False
    print("runtime plugin validation: ok")


if __name__ == "__main__":
    main()
