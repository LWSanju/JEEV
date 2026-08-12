import json
import re
import sys
from pathlib import Path


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


PLANNER_PROMPT = """You are the planning module of MARK XXV, a personal AI assistant.

Your job is to break any user goal into a sequence of steps using ONLY the tools listed below.

ABSOLUTE RULES:

- NEVER use generated_code.
- NEVER write Python scripts.
- NEVER reference previous step results in parameters.
- Every step must be independently executable.
- Use web_search for information retrieval, research, or current data.
- Use file_controller to save or manipulate files.
- Use cmd_control to open files or run system commands.
- Maximum 5 steps.
- Use the minimum number of steps needed.
- Return ONLY valid JSON.

AVAILABLE TOOLS:

open_app
Parameters:
- app_name: string

web_search
Parameters:
- query: string
- mode: "search" or "compare"
- items: list of strings
- aspect: string

game_updater
Parameters:
- action: "update" | "install" | "list" | "download_status" | "schedule"
- platform: "steam" | "epic" | "both"
- game_name: string
- app_id: string
- shutdown_when_done: boolean

browser_control
Parameters:
- action: "go_to" | "search" | "click" | "type" | "scroll" | "get_text" | "press" | "close"
- url: string
- query: string
- text: string
- direction: "up" | "down"

file_controller
Parameters:
- action: "write" | "create_file" | "read" | "list" | "delete" | "move" | "copy" | "find" | "disk_usage"
- path: string
- name: string
- content: string

cmd_control
Parameters:
- task: string
- visible: boolean

computer_settings
Parameters:
- action: string
- description: string
- value: string

computer_control
Parameters:
- action: "type" | "click" | "hotkey" | "press" | "scroll" | "screenshot" | "screen_find" | "screen_click"
- text: string
- x: integer
- y: integer
- keys: string
- key: string
- direction: "up" | "down"
- description: string

screen_process
Parameters:
- text: string
- angle: "screen" | "camera"

send_message
Parameters:
- receiver: string
- message_text: string
- platform: string

reminder
Parameters:
- date: string
- time: string
- message: string

desktop_control
Parameters:
- action: "wallpaper" | "organize" | "clean" | "list" | "task"
- path: string
- task: string

youtube_video
Parameters:
- action: "play" | "summarize" | "trending"
- query: string

weather_report
Parameters:
- city: string

flight_finder
Parameters:
- origin: string
- destination: string
- date: string

code_helper
Parameters:
- action: "write" | "edit" | "run" | "explain"
- description: string
- language: string
- output_path: string
- file_path: string

dev_agent
Parameters:
- description: string
- language: string

OUTPUT FORMAT:

{
    "goal": "...",
    "steps": [
        {
            "step": 1,
            "tool": "tool_name",
            "description": "what this step does",
            "parameters": {},
            "critical": true
        }
    ]
}

Return ONLY valid JSON.
"""


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    api_key = config.get("gemini_api_key")

    if not api_key:
        raise ValueError(
            f"gemini_api_key not found in {API_CONFIG_PATH}"
        )

    return api_key


def _clean_json_response(text: str) -> str:
    """Remove markdown code fences if Gemini returns them."""

    text = text.strip()

    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    return text.strip()


def _validate_plan(plan: dict, goal: str) -> dict:
    """Validate and normalize the planner response."""

    if not isinstance(plan, dict):
        raise ValueError("Planner response is not a JSON object")

    if "steps" not in plan:
        raise ValueError("Planner response has no steps")

    if not isinstance(plan["steps"], list):
        raise ValueError("Planner steps must be a list")

    if len(plan["steps"]) > 5:
        print("[Planner] ⚠️ More than 5 steps returned. Trimming to 5.")
        plan["steps"] = plan["steps"][:5]

    plan["goal"] = plan.get("goal", goal)

    allowed_tools = {
        "open_app",
        "web_search",
        "game_updater",
        "browser_control",
        "file_controller",
        "cmd_control",
        "computer_settings",
        "computer_control",
        "screen_process",
        "send_message",
        "reminder",
        "desktop_control",
        "youtube_video",
        "weather_report",
        "flight_finder",
        "code_helper",
        "dev_agent",
    }

    for index, step in enumerate(plan["steps"], start=1):

        if not isinstance(step, dict):
            raise ValueError(f"Step {index} is not an object")

        step["step"] = index

        tool = step.get("tool")

        if tool == "generated_code":
            print(
                f"[Planner] ⚠️ generated_code detected in step "
                f"{index} — replacing with web_search"
            )

            description = step.get("description", goal)

            step["tool"] = "web_search"
            step["parameters"] = {
                "query": str(description)[:200]
            }

        elif tool not in allowed_tools:
            raise ValueError(
                f"Unknown tool '{tool}' in step {index}"
            )

        if "description" not in step:
            step["description"] = f"Execute {step['tool']}"

        if "parameters" not in step:
            step["parameters"] = {}

        if "critical" not in step:
            step["critical"] = True

    return plan


def create_plan(goal: str, context: str = "") -> dict:
    """Create an execution plan using Gemini."""

    import google.generativeai as genai

    try:
        genai.configure(api_key=_get_api_key())

        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash-lite",
            system_instruction=PLANNER_PROMPT
        )

        user_input = f"Goal: {goal}"

        if context:
            user_input += f"\n\nContext: {context}"

        response = model.generate_content(user_input)

        text = response.text.strip()
        text = _clean_json_response(text)

        plan = json.loads(text)

        plan = _validate_plan(plan, goal)

        print(
            f"[Planner] ✅ Plan created: "
            f"{len(plan['steps'])} step(s)"
        )

        for step in plan["steps"]:
            print(
                f"  Step {step['step']}: "
                f"[{step['tool']}] "
                f"{step['description']}"
            )

        return plan

    except json.JSONDecodeError as e:
        print(f"[Planner] ⚠️ JSON parse failed: {e}")
        return _fallback_plan(goal)

    except Exception as e:
        print(f"[Planner] ⚠️ Planning failed: {e}")
        return _fallback_plan(goal)


def _fallback_plan(goal: str) -> dict:
    """Create a safe fallback plan if Gemini fails."""

    print("[Planner] 🔄 Using fallback plan")

    return {
        "goal": goal,
        "steps": [
            {
                "step": 1,
                "tool": "web_search",
                "description": f"Search for: {goal}",
                "parameters": {
                    "query": goal
                },
                "critical": True
            }
        ]
    }


def replan(
    goal: str,
    completed_steps: list,
    failed_step: dict,
    error: str
) -> dict:
    """Create a revised plan after a failed step."""

    import google.generativeai as genai

    try:
        genai.configure(api_key=_get_api_key())

        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=PLANNER_PROMPT
        )

        completed_summary = "\n".join(
            f"  - Step {step.get('step')} "
            f"({step.get('tool')}): DONE"
            for step in completed_steps
        )

        prompt = f"""Goal: {goal}

Already completed:
{completed_summary if completed_summary else "  (none)"}

Failed step:
[{failed_step.get("tool")}] {failed_step.get("description")}

Error:
{error}

Create a REVISED plan for the remaining work only.

Do not repeat completed steps.
Do not use generated_code.
Return ONLY valid JSON.
"""

        response = model.generate_content(prompt)

        text = response.text.strip()
        text = _clean_json_response(text)

        plan = json.loads(text)

        plan = _validate_plan(plan, goal)

        print(
            f"[Planner] 🔄 Revised plan: "
            f"{len(plan['steps'])} step(s)"
        )

        for step in plan["steps"]:
            print(
                f"  Step {step['step']}: "
                f"[{step['tool']}] "
                f"{step['description']}"
            )

        return plan

    except Exception as e:
        print(f"[Planner] ⚠️ Replan failed: {e}")
        return _fallback_plan(goal)