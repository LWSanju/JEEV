import json
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from agent.planner import create_plan, replan
from agent.error_handler import analyze_error, ErrorDecision


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _inject_context(
    params: dict,
    tool: str,
    step_results: dict,
    goal: str = ""
) -> dict:
    if not params:
        return {}

    return dict(params)


def _call_tool(
    tool: str,
    parameters: dict,
    speak: Callable | None
) -> str:

    parameters = parameters or {}

    if tool == "open_app":
        from actions.open_app import open_app
        return open_app(parameters=parameters, player=None) or "Done."

    elif tool == "web_search":
        from actions.web_search import web_search
        return web_search(parameters=parameters, player=None) or "Done."

    elif tool == "game_updater":
        from actions.game_updater import game_updater
        return game_updater(
            parameters=parameters,
            player=None,
            speak=speak
        ) or "Done."

    elif tool == "browser_control":
        from actions.browser_control import browser_control
        return browser_control(
            parameters=parameters,
            player=None
        ) or "Done."

    elif tool == "file_controller":
        from actions.file_controller import file_controller
        return file_controller(
            parameters=parameters,
            player=None
        ) or "Done."

    elif tool == "cmd_control":
        from actions.cmd_control import cmd_control
        return cmd_control(
            parameters=parameters,
            player=None
        ) or "Done."

    elif tool == "code_helper":
        from actions.code_helper import code_helper
        return code_helper(
            parameters=parameters,
            player=None,
            speak=speak
        ) or "Done."

    elif tool == "dev_agent":
        from actions.dev_agent import dev_agent
        return dev_agent(
            parameters=parameters,
            player=None,
            speak=speak
        ) or "Done."

    elif tool == "screen_process":
        from actions.screen_processor import screen_process
        screen_process(
            parameters=parameters,
            player=None
        )
        return "Screen captured and analyzed."

    elif tool == "send_message":
        from actions.send_message import send_message
        return send_message(
            parameters=parameters,
            player=None
        ) or "Done."

    elif tool == "reminder":
        from actions.reminder import reminder
        return reminder(
            parameters=parameters,
            player=None
        ) or "Done."

    elif tool == "youtube_video":
        from actions.youtube_video import youtube_video
        return youtube_video(
            parameters=parameters,
            player=None
        ) or "Done."

    elif tool == "weather_report":
        from actions.weather_report import weather_action
        return weather_action(
            parameters=parameters,
            player=None
        ) or "Done."

    elif tool == "computer_settings":
        from actions.computer_settings import computer_settings
        return computer_settings(
            parameters=parameters,
            player=None
        ) or "Done."

    elif tool == "desktop_control":
        from actions.desktop import desktop_control
        return desktop_control(
            parameters=parameters,
            player=None
        ) or "Done."

    elif tool == "computer_control":
        from actions.computer_control import computer_control
        return computer_control(
            parameters=parameters,
            player=None
        ) or "Done."

    elif tool == "flight_finder":
        from actions.flight_finder import flight_finder
        return flight_finder(
            parameters=parameters,
            player=None,
            speak=speak
        ) or "Done."

    else:
        raise ValueError(
            f"Unknown tool '{tool}'. "
            f"The planner must select a supported tool."
        )


class AgentExecutor:

    MAX_REPLAN_ATTEMPTS = 2
    MAX_STEP_ATTEMPTS = 3

    def execute(
        self,
        goal: str,
        speak: Callable | None = None,
        cancel_flag: threading.Event | None = None,
    ) -> str:

        print(f"\n[Executor] Goal: {goal}")

        replan_attempts = 0
        completed_steps = []
        step_results = {}

        # Create initial plan
        try:
            plan = create_plan(goal)
        except Exception as e:
            print(f"[Executor] Planner failed: {e}")

            msg = "I couldn't create a plan for that task, sir."

            if speak:
                speak(msg)

            return msg

        # Main execution loop
        while True:

            steps = plan.get("steps", [])

            if not steps:
                msg = "I couldn't create a valid plan for this task, sir."

                if speak:
                    speak(msg)

                return msg

            success = True
            failed_step = None
            failed_error = ""

            # Execute each step
            for step in steps:

                # Cancellation
                if cancel_flag and cancel_flag.is_set():

                    if speak:
                        speak("Task cancelled, sir.")

                    return "Task cancelled."

                step_num = step.get("step", "?")
                tool = step.get("tool")
                desc = step.get("description", "")
                params = step.get("parameters", {})

                # Validate tool
                if not tool:
                    failed_step = step
                    failed_error = (
                        "Planner returned a step without a tool."
                    )
                    success = False
                    break

                # Never allow generated_code
                if tool == "generated_code":

                    failed_step = step
                    failed_error = (
                        "generated_code is disabled. "
                        "Use an existing supported tool instead."
                    )

                    print(
                        "[Executor] generated_code is disabled."
                    )

                    success = False
                    break

                params = _inject_context(
                    params,
                    tool,
                    step_results,
                    goal
                )

                print(
                    f"\n[Executor] Step {step_num}: "
                    f"[{tool}] {desc}"
                )

                step_ok = False
                attempt = 1

                # Retry loop
                while attempt <= self.MAX_STEP_ATTEMPTS:

                    if cancel_flag and cancel_flag.is_set():
                        break

                    try:

                        result = _call_tool(
                            tool,
                            params,
                            speak
                        )

                        if result is None:
                            result = "Done."

                        result = str(result)

                        step_results[step_num] = result
                        completed_steps.append(step)

                        print(
                            f"[Executor] Step {step_num} done: "
                            f"{result[:120]}"
                        )

                        step_ok = True
                        break

                    except Exception as e:

                        error_msg = str(e)

                        print(
                            f"[Executor] Step {step_num} "
                            f"attempt {attempt} failed: "
                            f"{error_msg}"
                        )

                        try:
                            recovery = analyze_error(
                                step,
                                error_msg,
                                attempt=attempt,
                                max_attempts=self.MAX_STEP_ATTEMPTS
                            )

                        except Exception as handler_error:

                            print(
                                "[Executor] Error handler failed: "
                                f"{handler_error}"
                            )

                            recovery = {
                                "decision": ErrorDecision.REPLAN,
                                "reason": error_msg,
                                "fix_suggestion": (
                                    "Try another supported tool."
                                ),
                                "max_retries": 0,
                                "user_message": (
                                    "I'm adjusting my approach, sir."
                                )
                            }

                        decision = recovery.get(
                            "decision",
                            ErrorDecision.REPLAN
                        )

                        user_msg = recovery.get(
                            "user_message",
                            ""
                        )

                        if speak and user_msg:
                            speak(user_msg)

                        # Retry
                        if decision == ErrorDecision.RETRY:

                            attempt += 1

                            print(
                                f"[Executor] Retrying "
                                f"step {step_num}..."
                            )

                            time.sleep(2)
                            continue

                        # Skip
                        elif decision == ErrorDecision.SKIP:

                            if step.get("critical", False):

                                print(
                                    "[Executor] Critical step "
                                    "cannot be skipped."
                                )

                                failed_step = step
                                failed_error = (
                                    "Critical step failed "
                                    "and cannot be skipped."
                                )

                                success = False
                                break

                            print(
                                f"[Executor] Skipping "
                                f"step {step_num}"
                            )

                            completed_steps.append(step)
                            step_ok = True
                            break

                        # Abort
                        elif decision == ErrorDecision.ABORT:

                            reason = recovery.get(
                                "reason",
                                "The task cannot continue."
                            )

                            msg = (
                                f"Task aborted, sir. {reason}"
                            )

                            if speak:
                                speak(msg)

                            return msg

                        # Replan
                        else:

                            failed_step = step
                            failed_error = error_msg
                            success = False

                            print(
                                "[Executor] Replanning required."
                            )

                            break

                # Step failed
                if not step_ok:

                    if failed_step is None:
                        failed_step = step
                        failed_error = (
                            "Maximum step attempts exceeded."
                        )

                    success = False
                    break

            # Task succeeded
            if success:

                return self._summarize(
                    goal,
                    completed_steps,
                    speak
                )

            # Maximum replans
            if replan_attempts >= self.MAX_REPLAN_ATTEMPTS:

                msg = (
                    f"Task failed after "
                    f"{replan_attempts} replan attempts, sir."
                )

                if speak:
                    speak(msg)

                return msg

            # Replan
            if speak:
                speak("Adjusting my approach, sir.")

            print(
                f"[Executor] Replanning attempt "
                f"{replan_attempts + 1}"
            )

            replan_attempts += 1

            try:

                plan = replan(
                    goal,
                    completed_steps,
                    failed_step,
                    failed_error
                )

            except Exception as e:

                print(
                    f"[Executor] Replan failed: {e}"
                )

                msg = (
                    "I couldn't recover from that task, sir."
                )

                if speak:
                    speak(msg)

                return msg

    def _summarize(
        self,
        goal: str,
        completed_steps: list,
        speak: Callable | None
    ) -> str:

        fallback = (
            f"All done, sir. Completed "
            f"{len(completed_steps)} steps."
        )

        try:

            import google.generativeai as genai

            genai.configure(
                api_key=_get_api_key()
            )

            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash-lite"
            )

            steps_str = "\n".join(
                f"- {s.get('description', '')}"
                for s in completed_steps
            )

            prompt = (
                f'User goal: "{goal}"\n'
                f"Completed steps:\n{steps_str}\n\n"
                "Write one short natural sentence "
                "summarizing what was accomplished. "
                "Address the user as 'sir'. "
                "Be direct and positive."
            )

            response = model.generate_content(prompt)

            summary = response.text.strip()

            if not summary:
                summary = fallback

            if speak:
                speak(summary)

            return summary

        except Exception as e:

            print(
                f"[Executor] Summary generation failed: {e}"
            )

            if speak:
                speak(fallback)

            return fallback