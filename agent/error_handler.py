import json
import re
import sys
from pathlib import Path
from enum import Enum


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


class ErrorDecision(Enum):
    RETRY = "retry"
    SKIP = "skip"
    REPLAN = "replan"
    ABORT = "abort"


ERROR_ANALYST_PROMPT = """You are the error recovery module of MARK XXV AI assistant.

A task step has failed. Analyze the error and decide what to do.

DECISIONS:

- retry: Transient error such as network timeout, temporary file lock, or race condition.
- skip: This step is not critical and the task can succeed without it.
- replan: The approach was wrong. A different existing tool or method should be tried.
- abort: The task is fundamentally impossible or unsafe to continue.

IMPORTANT:
- NEVER generate Python code.
- NEVER use generated_code.
- NEVER create a code_helper step as an automatic fix.
- For replan, suggest using one of the existing tools from the planner.
- Max retries: 1 or 2.

Return ONLY valid JSON:

{
    "decision": "retry|skip|replan|abort",
    "reason": "why it failed",
    "fix_suggestion": "what to try instead",
    "max_retries": 1,
    "user_message": "Short message to tell the user (max 15 words)"
}
"""


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def analyze_error(
    step: dict,
    error: str,
    attempt: int = 1,
    max_attempts: int = 2
) -> dict:

    import google.generativeai as genai

    if attempt >= max_attempts:
        print(
            f"[ErrorHandler] Max attempts reached for step "
            f"{step.get('step')} - forcing replan"
        )

        return {
            "decision": ErrorDecision.REPLAN,
            "reason": f"Failed {attempt} times: {error[:100]}",
            "fix_suggestion": "Try a different existing tool or approach.",
            "max_retries": 0,
            "user_message": "Trying a different approach, sir."
        }

    genai.configure(api_key=_get_api_key())

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash-lite",
        system_instruction=ERROR_ANALYST_PROMPT
    )

    prompt = f"""Failed step:

Tool: {step.get('tool')}
Description: {step.get('description')}
Parameters: {json.dumps(step.get('parameters', {}), indent=2)}
Critical: {step.get('critical', False)}

Error:
{error[:500]}

Attempt number: {attempt}

Analyze the failure and return the correct recovery decision.
"""

    try:
        response = model.generate_content(prompt)

        text = response.text.strip()
        text = re.sub(r"```(?:json)?", "", text).strip()
        text = text.rstrip("`").strip()

        result = json.loads(text)

        decision_str = str(
            result.get("decision", "replan")
        ).lower().strip()

        decision_map = {
            "retry": ErrorDecision.RETRY,
            "skip": ErrorDecision.SKIP,
            "replan": ErrorDecision.REPLAN,
            "abort": ErrorDecision.ABORT,
        }

        result["decision"] = decision_map.get(
            decision_str,
            ErrorDecision.REPLAN
        )

        if (
            step.get("critical")
            and result["decision"] == ErrorDecision.SKIP
        ):
            result["decision"] = ErrorDecision.REPLAN
            result["user_message"] = (
                "This step is critical - finding an alternative approach, sir."
            )

        print(
            f"[ErrorHandler] Decision: "
            f"{result['decision'].value} - "
            f"{result.get('reason', '')}"
        )

        return result

    except Exception as e:
        print(
            f"[ErrorHandler] Analysis failed: {e} "
            f"- defaulting to replan"
        )

        return {
            "decision": ErrorDecision.REPLAN,
            "reason": str(e),
            "fix_suggestion": "Try an alternative existing tool.",
            "max_retries": 1,
            "user_message": (
                "Encountered an issue, adjusting approach, sir."
            )
        }


def generate_fix(
    step: dict,
    error: str,
    fix_suggestion: str
) -> dict:

    print(
        f"[ErrorHandler] Replan requested for step "
        f"{step.get('step')}"
    )

    return {
        "step": step.get("step"),
        "tool": "replan",
        "description": (
            f"Find an alternative approach for: "
            f"{step.get('description', '')}"
        ),
        "parameters": {
            "original_tool": step.get("tool"),
            "original_description": step.get("description", ""),
            "error": error[:300],
            "fix_suggestion": fix_suggestion
        },
        "critical": step.get("critical", False)
    }