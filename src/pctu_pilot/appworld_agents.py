from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass
from typing import Any

from .rave_dsl import IntentFrame, IntentMachine, IntentSchema, SlotSpec, ToolAction
from .llm_client import ChatMessage, OpenAICompatibleClient, parse_json_object
from .rave_runtime import AvailableTools, RaveRuntime, RaveRuntimeHooks, RaveRuntimePolicy


RELATION_ALIASES = {
    "managers": "manager",
    "manager": "manager",
    "parents": "parent",
    "parent": "parent",
    "mothers": "mother",
    "mother": "mother",
    "children": "child",
    "child": "child",
    "sons": "son",
    "son": "son",
    "daughters": "daughter",
    "daughter": "daughter",
    "siblings": "sibling",
    "sibling": "sibling",
    "sisters": "sister",
    "sister": "sister",
    "brothers": "brother",
    "brother": "brother",
    "roommates": "roommate",
    "roommate": "roommate",
    "friends": "friend",
    "friend": "friend",
    "coworkers": "coworker",
    "coworker": "coworker",
    "partners": "partner",
    "partner": "partner",
    "husbands": "husband",
    "husband": "husband",
    "wives": "wife",
    "wife": "wife",
    "spouses": "partner",
    "spouse": "partner",
}


@dataclass(frozen=True)
class AppWorldRaveResult:
    supported: bool
    intent_type: str
    reason: str
    output: str
    code: str
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    code_exec_calls: int = 0
    raw_model_output: str = ""
    parse_error: str = ""


class AppWorldRuntimePolicy(RaveRuntimePolicy):
    def abstention_message(self, frame: IntentFrame) -> str:
        missing = ", ".join(frame.missing_slots) or frame.abstain_reason
        return f"I do not have enough information to safely complete this AppWorld task: {missing}."

    def verify_action(
        self,
        frame: IntentFrame,
        action: ToolAction,
        available_tools: AvailableTools,
    ) -> ToolAction:
        if action.tool != "execute_code":
            return ToolAction(
                tool="blocked",
                args={},
                reason=f"blocked_unregistered_appworld_tool:{action.tool}",
            )
        code = str(action.args.get("code", ""))
        blocked_markers = ["ground_truth", "data/tasks", "compiled_solution", "solution.py"]
        if any(marker in code for marker in blocked_markers):
            return ToolAction(
                tool="blocked",
                args={},
                reason=f"blocked_oracle_reference:{frame.intent_type}",
            )
        return action


class AppWorldRaveAgent:
    """Small AppWorld binding for RAVE's typed intent/runtime interface.

    The agent covers a deliberately narrow set of public state-changing task families.
    It compiles natural-language instructions into deterministic AppWorld code cells and
    lets the AppWorld evaluator decide success and collateral state failures.
    """

    def __init__(self) -> None:
        self.runtime = RaveRuntime(build_appworld_intent_machines())
        self.hooks = RaveRuntimeHooks.from_policy(AppWorldRuntimePolicy())

    def run_instruction(self, instruction: str, execute_code: Any) -> AppWorldRaveResult:
        result = self.runtime.step(
            instruction,
            instruction,
            {"execute_code": execute_code},
            hooks=self.hooks,
        )
        if result.action is None:
            return AppWorldRaveResult(
                supported=False,
                intent_type="unsupported",
                reason="no_appworld_intent_machine_matched",
                output="",
                code="",
            )
        if not isinstance(result.action, ToolAction) or result.action.tool != "execute_code":
            return AppWorldRaveResult(
                supported=False,
                intent_type=result.frame.intent_type if result.frame else "blocked",
                reason=getattr(result.action, "reason", "blocked"),
                output="",
                code="",
            )
        code = str(result.action.args["code"])
        output = execute_appworld_code_safely(execute_code, code)
        return AppWorldRaveResult(
            supported=True,
            intent_type=result.frame.intent_type if result.frame else "unknown",
            reason=result.action.reason,
            output=output,
            code=code,
        )


def execute_appworld_code_safely(execute_code: Any, code: str) -> str:
    try:
        return str(execute_code(code))
    except Exception as exc:  # noqa: BLE001
        return f"Execution failed before AppWorld returned output: {type(exc).__name__}: {exc}"


class AppWorldLLMIntentAgent:
    """Real-LLM intent/slot extractor with the same runtime-checked AppWorld executor."""

    def __init__(
        self,
        client: OpenAICompatibleClient,
        *,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> None:
        self.client = client
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.runtime = RaveRuntime(build_appworld_intent_machines())
        self.policy = AppWorldRuntimePolicy()

    def run_instruction(self, instruction: str, execute_code: Any) -> AppWorldRaveResult:
        response = self.client.chat(
            [
                ChatMessage("system", appworld_intent_system_prompt()),
                ChatMessage("user", f"Task instruction:\n{instruction}\n\nReturn JSON only."),
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        try:
            payload = parse_json_object(response.content)
            frame = self._frame_from_payload(payload)
            frame = verify_or_repair_llm_intent_frame(
                frame,
                instruction,
                self.runtime,
                {"execute_code": execute_code},
            )
        except Exception as exc:  # noqa: BLE001
            return AppWorldRaveResult(
                supported=False,
                intent_type="parse_error",
                reason="llm_intent_parse_error",
                output="",
                code="",
                llm_calls=1,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                raw_model_output=response.content,
                parse_error=str(exc),
            )

        machine = self.runtime.intent_machine_by_type.get(frame.intent_type)
        if machine is None:
            return AppWorldRaveResult(
                supported=False,
                intent_type=frame.intent_type,
                reason="llm_intent_unsupported",
                output="",
                code="",
                llm_calls=1,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                raw_model_output=response.content,
            )
        frame.validate(machine.schema)
        if not frame.complete:
            return AppWorldRaveResult(
                supported=False,
                intent_type=frame.intent_type,
                reason=f"llm_intent_missing_slots:{','.join(frame.missing_slots)}",
                output="",
                code="",
                llm_calls=1,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                raw_model_output=response.content,
            )

        action = self.runtime.next_frame_action(frame, {"execute_code": execute_code})
        if action is None:
            return AppWorldRaveResult(
                supported=False,
                intent_type=frame.intent_type,
                reason="llm_intent_no_action",
                output="",
                code="",
                llm_calls=1,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                raw_model_output=response.content,
            )
        action = self.policy.verify_action(frame, action, {"execute_code": execute_code})
        if action.tool != "execute_code":
            return AppWorldRaveResult(
                supported=False,
                intent_type=frame.intent_type,
                reason=action.reason,
                output="",
                code="",
                llm_calls=1,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                raw_model_output=response.content,
            )
        code = str(action.args["code"])
        output = execute_appworld_code_safely(execute_code, code)
        return AppWorldRaveResult(
            supported=True,
            intent_type=frame.intent_type,
            reason=action.reason,
            output=output,
            code=code,
            llm_calls=1,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            raw_model_output=response.content,
        )

    def _frame_from_payload(self, payload: dict[str, Any]) -> IntentFrame:
        intent_type = str(payload.get("intent_type") or "")
        slots = payload.get("slots")
        if not isinstance(slots, dict):
            raise ValueError("Expected payload.slots to be an object.")
        slots = normalize_llm_slots(intent_type, slots)
        frame = IntentFrame(intent_type)
        for name, value in slots.items():
            frame.set_slot(name, value, source="llm_intent")
        return frame


class AppWorldLLMCodeAgent:
    """Direct LLM code baseline for the targeted AppWorld slice.

    This baseline lets the model author one AppWorld code cell from task text and a
    compact API sketch. It blocks oracle references but does not compile the request into
    a verified intent machine.
    """

    def __init__(
        self,
        client: OpenAICompatibleClient,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1400,
    ) -> None:
        self.client = client
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.policy = AppWorldRuntimePolicy()

    def run_instruction(self, instruction: str, execute_code: Any) -> AppWorldRaveResult:
        response = self.client.chat(
            [
                ChatMessage("system", appworld_code_system_prompt()),
                ChatMessage("user", f"Task instruction:\n{instruction}\n\nReturn Python code only."),
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        try:
            code = extract_python_code(response.content)
        except Exception as exc:  # noqa: BLE001
            return AppWorldRaveResult(
                supported=False,
                intent_type="appworld_llm_direct_code",
                reason="llm_code_parse_error",
                output="",
                code="",
                llm_calls=1,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                raw_model_output=response.content,
                parse_error=str(exc),
            )

        frame = IntentFrame("appworld_llm_direct_code")
        action = self.policy.verify_action(
            frame,
            ToolAction("execute_code", {"code": code}, "appworld_llm_direct_code"),
            {"execute_code": execute_code},
        )
        if action.tool != "execute_code":
            return AppWorldRaveResult(
                supported=False,
                intent_type="appworld_llm_direct_code",
                reason=action.reason,
                output="",
                code=code,
                llm_calls=1,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                raw_model_output=response.content,
            )
        output = execute_appworld_code_safely(execute_code, code)
        return AppWorldRaveResult(
            supported=True,
            intent_type="appworld_llm_direct_code",
            reason=action.reason,
            output=output,
            code=code,
            llm_calls=1,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            code_exec_calls=1,
            raw_model_output=response.content,
        )


class AppWorldLLMCodeRepairAgent:
    """Multi-attempt direct-code baseline with execution-error repair."""

    def __init__(
        self,
        client: OpenAICompatibleClient,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1400,
        max_attempts: int = 3,
    ) -> None:
        self.client = client
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_attempts = max_attempts
        self.policy = AppWorldRuntimePolicy()

    def run_instruction(self, instruction: str, execute_code: Any) -> AppWorldRaveResult:
        messages = [
            ChatMessage("system", appworld_code_system_prompt()),
            ChatMessage("user", f"Task instruction:\n{instruction}\n\nReturn Python code only."),
        ]
        prompt_tokens = 0
        completion_tokens = 0
        raw_outputs: list[str] = []
        code_attempts: list[str] = []
        output_parts: list[str] = []
        failed_attempts = 0

        for attempt_index in range(1, self.max_attempts + 1):
            response = self.client.chat(
                messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            prompt_tokens += response.prompt_tokens
            completion_tokens += response.completion_tokens
            raw_outputs.append(response.content)
            try:
                code = extract_python_code(response.content)
            except Exception as exc:  # noqa: BLE001
                failed_attempts += 1
                output_parts.append(f"attempt {attempt_index} parse failed: {exc}")
                messages.append(ChatMessage("assistant", response.content))
                messages.append(
                    ChatMessage(
                        "user",
                        "The previous response was not executable Python code. "
                        "Return one corrected Python code cell only.",
                    )
                )
                continue

            code_attempts.append(code)
            frame = IntentFrame("appworld_llm_code_repair")
            action = self.policy.verify_action(
                frame,
                ToolAction("execute_code", {"code": code}, "appworld_llm_code_repair"),
                {"execute_code": execute_code},
            )
            if action.tool != "execute_code":
                failed_attempts += 1
                output_parts.append(f"attempt {attempt_index} blocked: {action.reason}")
                break

            output = execute_appworld_code_safely(execute_code, code)
            output_parts.append(f"attempt {attempt_index} output:\n{output}")
            if not output.startswith("Execution failed"):
                break

            failed_attempts += 1
            messages.append(ChatMessage("assistant", response.content))
            messages.append(
                ChatMessage(
                    "user",
                    "The code failed when executed in AppWorld. "
                    "Use the traceback below to produce a corrected Python code cell. "
                    "Do not use ground-truth data, and avoid repeating already completed "
                    f"state changes if your previous code made any.\n\n{compact_text(output)[:1200]}",
                )
            )

        output_parts.append(
            json.dumps(
                {
                    "failed_api_attempts": failed_attempts,
                    "code_attempts": len(code_attempts),
                },
                sort_keys=True,
            )
        )
        return AppWorldRaveResult(
            supported=bool(code_attempts),
            intent_type="appworld_llm_code_repair",
            reason="appworld_llm_code_repair",
            output="\n".join(output_parts),
            code="\n\n# --- next attempt ---\n\n".join(code_attempts),
            llm_calls=len(raw_outputs),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            code_exec_calls=len(code_attempts),
            raw_model_output="\n\n--- next response ---\n\n".join(raw_outputs),
            parse_error="" if code_attempts else "no_executable_code_attempt",
        )


class AppWorldLLMReactCodeAgent:
    """Multi-step AppWorld code-observation baseline without verified handlers."""

    def __init__(
        self,
        client: OpenAICompatibleClient,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1400,
        max_steps: int = 5,
    ) -> None:
        self.client = client
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_steps = max_steps
        self.policy = AppWorldRuntimePolicy()

    def run_instruction(self, instruction: str, execute_code: Any) -> AppWorldRaveResult:
        messages = [
            ChatMessage("system", appworld_react_code_system_prompt()),
            ChatMessage(
                "user",
                f"Task instruction:\n{instruction}\n\n"
                "Start by inspecting live state if needed. Return JSON only.",
            ),
        ]
        prompt_tokens = 0
        completion_tokens = 0
        raw_outputs: list[str] = []
        code_attempts: list[str] = []
        output_parts: list[str] = []
        failed_steps = 0
        stopped_reason = "max_steps_exhausted"

        for step_index in range(1, self.max_steps + 1):
            response = self.client.chat(
                messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            prompt_tokens += response.prompt_tokens
            completion_tokens += response.completion_tokens
            raw_outputs.append(response.content)

            try:
                payload = parse_json_object(response.content)
            except Exception as exc:  # noqa: BLE001
                failed_steps += 1
                output_parts.append(f"step {step_index} parse failed: {exc}")
                messages.append(ChatMessage("assistant", response.content))
                messages.append(
                    ChatMessage(
                        "user",
                        "The previous response was not valid JSON. Return exactly "
                        '{"action":"code","code":"..."} or {"action":"final","message":"..."}.',
                    )
                )
                continue

            action_type = str(payload.get("action", "")).strip().lower()
            if action_type == "final":
                stopped_reason = "model_final"
                output_parts.append(f"step {step_index} final: {payload.get('message', '')}")
                break
            if action_type != "code":
                failed_steps += 1
                output_parts.append(f"step {step_index} unsupported action: {action_type}")
                messages.append(ChatMessage("assistant", response.content))
                messages.append(
                    ChatMessage(
                        "user",
                        'Unsupported action. Return {"action":"code","code":"..."} '
                        'or {"action":"final","message":"..."}.',
                    )
                )
                continue

            code = str(payload.get("code", "")).strip()
            if not code:
                failed_steps += 1
                output_parts.append(f"step {step_index} empty code")
                messages.append(ChatMessage("assistant", response.content))
                messages.append(ChatMessage("user", "The code field was empty. Return a useful code cell."))
                continue
            code = clean_code(code)
            code_attempts.append(code)
            frame = IntentFrame("appworld_llm_react_code")
            action = self.policy.verify_action(
                frame,
                ToolAction("execute_code", {"code": code}, "appworld_llm_react_code"),
                {"execute_code": execute_code},
            )
            if action.tool != "execute_code":
                failed_steps += 1
                stopped_reason = action.reason
                output_parts.append(f"step {step_index} blocked: {action.reason}")
                break

            output = execute_appworld_code_safely(execute_code, code)
            compact_output = compact_text(output)
            output_parts.append(f"step {step_index} output:\n{output}")
            if output.startswith("Execution failed"):
                failed_steps += 1
            if "complete_task" in code and not output.startswith("Execution failed"):
                stopped_reason = "completed_after_code"
                break
            messages.append(ChatMessage("assistant", response.content))
            messages.append(
                ChatMessage(
                    "user",
                    "Observation from executing that code:\n"
                    f"{compact_output[:1600]}\n\n"
                    "Continue if the task is not complete. If it is complete, return "
                    '{"action":"final","message":"done"}.',
                )
            )

        output_parts.append(
            json.dumps(
                {
                    "failed_api_attempts": failed_steps,
                    "code_attempts": len(code_attempts),
                    "stopped_reason": stopped_reason,
                },
                sort_keys=True,
            )
        )
        return AppWorldRaveResult(
            supported=bool(code_attempts),
            intent_type="appworld_llm_react_code",
            reason="appworld_llm_react_code",
            output="\n".join(output_parts),
            code="\n\n# --- next step ---\n\n".join(code_attempts),
            llm_calls=len(raw_outputs),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            code_exec_calls=len(code_attempts),
            raw_model_output="\n\n--- next response ---\n\n".join(raw_outputs),
            parse_error="" if code_attempts else "no_executable_code_step",
        )


class AppWorldLLMIntentCodeAgent:
    """Ablation: LLM extracts typed intent, then LLM writes code without RAVE handler."""

    def __init__(
        self,
        client: OpenAICompatibleClient,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1400,
    ) -> None:
        self.client = client
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.policy = AppWorldRuntimePolicy()

    def run_instruction(self, instruction: str, execute_code: Any) -> AppWorldRaveResult:
        intent_response = self.client.chat(
            [
                ChatMessage("system", appworld_intent_system_prompt()),
                ChatMessage("user", f"Task instruction:\n{instruction}\n\nReturn JSON only."),
            ],
            temperature=self.temperature,
            max_tokens=min(self.max_tokens, 512),
        )
        try:
            payload = parse_json_object(intent_response.content)
            intent_type = str(payload.get("intent_type") or "")
            slots = payload.get("slots")
            if not isinstance(slots, dict):
                raise ValueError("Expected payload.slots to be an object.")
            normalized_slots = normalize_llm_slots(intent_type, slots)
        except Exception as exc:  # noqa: BLE001
            return AppWorldRaveResult(
                supported=False,
                intent_type="appworld_llm_intent_code",
                reason="llm_intent_code_parse_error",
                output="",
                code="",
                llm_calls=1,
                prompt_tokens=intent_response.prompt_tokens,
                completion_tokens=intent_response.completion_tokens,
                raw_model_output=intent_response.content,
                parse_error=str(exc),
            )

        code_response = self.client.chat(
            [
                ChatMessage("system", appworld_code_system_prompt()),
                ChatMessage(
                    "user",
                    "Use this typed intent frame as the source of task parameters, "
                    "but write the AppWorld code yourself without using the ICVE runtime.\n\n"
                    f"Task instruction:\n{instruction}\n\n"
                    f"Typed intent frame:\n{json.dumps({'intent_type': intent_type, 'slots': normalized_slots}, sort_keys=True)}\n\n"
                    "Return Python code only.",
                ),
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        prompt_tokens = intent_response.prompt_tokens + code_response.prompt_tokens
        completion_tokens = intent_response.completion_tokens + code_response.completion_tokens
        raw_model_output = (
            intent_response.content
            + "\n\n--- code response ---\n\n"
            + code_response.content
        )
        try:
            code = extract_python_code(code_response.content)
        except Exception as exc:  # noqa: BLE001
            return AppWorldRaveResult(
                supported=False,
                intent_type="appworld_llm_intent_code",
                reason="llm_intent_code_code_parse_error",
                output="",
                code="",
                llm_calls=2,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                raw_model_output=raw_model_output,
                parse_error=str(exc),
            )

        frame = IntentFrame("appworld_llm_intent_code")
        action = self.policy.verify_action(
            frame,
            ToolAction("execute_code", {"code": code}, "appworld_llm_intent_code"),
            {"execute_code": execute_code},
        )
        if action.tool != "execute_code":
            return AppWorldRaveResult(
                supported=False,
                intent_type="appworld_llm_intent_code",
                reason=action.reason,
                output="",
                code=code,
                llm_calls=2,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                raw_model_output=raw_model_output,
            )
        output = execute_appworld_code_safely(execute_code, code)
        return AppWorldRaveResult(
            supported=True,
            intent_type="appworld_llm_intent_code",
            reason=action.reason,
            output=output,
            code=code,
            llm_calls=2,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            code_exec_calls=1,
            raw_model_output=raw_model_output,
        )


def build_appworld_intent_machines() -> list[IntentMachine]:
    return [
        IntentMachine(
            schema=IntentSchema(
                "appworld_phone_message_non_venmo_contacts",
                (
                    SlotSpec("relationships"),
                    SlotSpec("excluded_app"),
                    SlotSpec("message"),
                ),
            ),
            compiler=compile_phone_message_non_venmo_contacts,
            handler=handle_phone_message_non_venmo_contacts,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_phone_send_message_to_relationship",
                (
                    SlotSpec("relationships"),
                    SlotSpec("message_kind"),
                    SlotSpec("message"),
                ),
            ),
            compiler=compile_phone_send_message_to_relationship,
            handler=handle_phone_send_message_to_relationship,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_phone_reply_favorite_recipe_to_relationship",
                (SlotSpec("relationship"),),
            ),
            compiler=compile_phone_reply_favorite_recipe_to_relationship,
            handler=handle_phone_reply_favorite_recipe_to_relationship,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_splitwise_accept_known_phone_invitations",
                (
                    SlotSpec("message_kind"),
                    SlotSpec("date_window"),
                ),
            ),
            compiler=compile_splitwise_accept_known_phone_invitations,
            handler=handle_splitwise_accept_known_phone_invitations,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_signup_missing_relationship_accounts",
                (
                    SlotSpec("relationships"),
                    SlotSpec("password"),
                    SlotSpec("message"),
                ),
            ),
            compiler=compile_venmo_signup_missing_relationship_accounts,
            handler=handle_venmo_signup_missing_relationship_accounts,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_phone_message_app_account_verify_reset",
                (
                    SlotSpec("relationship"),
                    SlotSpec("password"),
                    SlotSpec("date_window"),
                ),
            ),
            compiler=compile_phone_message_app_account_verify_reset,
            handler=handle_phone_message_app_account_verify_reset,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_shared_subscription_password_reset_and_text",
                (
                    SlotSpec("app_name"),
                    SlotSpec("subscription_name"),
                    SlotSpec("relationships"),
                    SlotSpec("new_password"),
                ),
            ),
            compiler=compile_shared_subscription_password_reset_and_text,
            handler=handle_shared_subscription_password_reset_and_text,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_change_password",
                (SlotSpec("new_password"),),
            ),
            compiler=compile_venmo_change_password,
            handler=handle_venmo_change_password,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_splitwise_record_venmo_receipt_payments",
                (SlotSpec("note"),),
            ),
            compiler=compile_splitwise_record_venmo_receipt_payments,
            handler=handle_splitwise_record_venmo_receipt_payments,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_todoist_reassign_accepted_takeover_tasks",
                (SlotSpec("comment_template"),),
            ),
            compiler=compile_todoist_reassign_accepted_takeover_tasks,
            handler=handle_todoist_reassign_accepted_takeover_tasks,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_apply_todoist_playlist_suggestions",
                (
                    SlotSpec("destination"),
                    SlotSpec("relationship_type"),
                    SlotSpec("final_comment"),
                ),
            ),
            compiler=compile_spotify_apply_todoist_playlist_suggestions,
            handler=handle_spotify_apply_todoist_playlist_suggestions,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_apply_phone_playlist_suggestions",
                (SlotSpec("relationship_type"),),
            ),
            compiler=compile_spotify_apply_phone_playlist_suggestions,
            handler=handle_spotify_apply_phone_playlist_suggestions,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_pay_csv_debts_via_venmo_or_splitwise",
                (
                    SlotSpec("csv_file_name"),
                    SlotSpec("private"),
                ),
            ),
            compiler=compile_pay_csv_debts_via_venmo_or_splitwise,
            handler=handle_pay_csv_debts_via_venmo_or_splitwise,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_send_to_phone_number",
                (
                    SlotSpec("phone_number"),
                    SlotSpec("amount"),
                    SlotSpec("private"),
                ),
            ),
            compiler=compile_venmo_send_to_phone_number,
            handler=handle_venmo_send_to_phone_number,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_send_to_named_user",
                (
                    SlotSpec("person_first_name"),
                    SlotSpec("amount"),
                ),
            ),
            compiler=compile_venmo_send_to_named_user,
            handler=handle_venmo_send_to_named_user,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_send_to_named_user_with_optional_signup",
                (
                    SlotSpec("person_first_name"),
                    SlotSpec("amount"),
                ),
            ),
            compiler=compile_venmo_send_to_named_user_with_optional_signup,
            handler=handle_venmo_send_to_named_user_with_optional_signup,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_pay_flight_bill_from_email",
                (
                    SlotSpec("person_first_name"),
                    SlotSpec("note"),
                ),
            ),
            compiler=compile_venmo_pay_flight_bill_from_email,
            handler=handle_venmo_pay_flight_bill_from_email,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_pay_coworkers_and_email",
                (
                    SlotSpec("relationships"),
                    SlotSpec("amount"),
                    SlotSpec("note"),
                    SlotSpec("email_subject"),
                    SlotSpec("email_body"),
                ),
            ),
            compiler=compile_venmo_pay_coworkers_and_email,
            handler=handle_venmo_pay_coworkers_and_email,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_accept_named_carpool_request_this_month",
                (SlotSpec("person_first_name"),),
            ),
            compiler=compile_venmo_accept_named_carpool_request_this_month,
            handler=handle_venmo_accept_named_carpool_request_this_month,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_correct_housing_bill_request",
                (
                    SlotSpec("percent"),
                    SlotSpec("adjustment"),
                    SlotSpec("note"),
                ),
            ),
            compiler=compile_venmo_correct_housing_bill_request,
            handler=handle_venmo_correct_housing_bill_request,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_approve_requests_and_withdraw_balance",
                (
                    SlotSpec("date_window"),
                    SlotSpec("card_last4"),
                ),
            ),
            compiler=compile_venmo_approve_requests_and_withdraw_balance,
            handler=handle_venmo_approve_requests_and_withdraw_balance,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_request_money_from_contact",
                (
                    SlotSpec("relationships"),
                    SlotSpec("person_first_name"),
                    SlotSpec("amount"),
                    SlotSpec("private"),
                    SlotSpec("note"),
                ),
            ),
            compiler=compile_venmo_request_money_from_contact,
            handler=handle_venmo_request_money_from_contact,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_settle_trip_note_debts",
                (
                    SlotSpec("relationship"),
                    SlotSpec("trip_name"),
                    SlotSpec("note"),
                ),
            ),
            compiler=compile_venmo_settle_trip_note_debts,
            handler=handle_venmo_settle_trip_note_debts,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_settle_roommate_dinner",
                (
                    SlotSpec("taxi_total"),
                    SlotSpec("food_total"),
                    SlotSpec("food_payer_first_name"),
                    SlotSpec("taxi_note"),
                    SlotSpec("food_note"),
                ),
            ),
            compiler=compile_venmo_settle_roommate_dinner,
            handler=handle_venmo_settle_roommate_dinner,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_send_to_each_relationship_with_refill",
                (
                    SlotSpec("relationships"),
                    SlotSpec("amount"),
                    SlotSpec("note"),
                ),
            ),
            compiler=compile_venmo_send_to_each_relationship_with_refill,
            handler=handle_venmo_send_to_each_relationship_with_refill,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_birthday_child_payment_and_text",
                (
                    SlotSpec("relationship"),
                    SlotSpec("multiplier"),
                    SlotSpec("note"),
                    SlotSpec("message"),
                ),
            ),
            compiler=compile_venmo_birthday_child_payment_and_text,
            handler=handle_venmo_birthday_child_payment_and_text,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_correct_sent_requests_yesterday_evening",
                (
                    SlotSpec("relationships"),
                    SlotSpec("adjustment"),
                    SlotSpec("difference_amount"),
                ),
            ),
            compiler=compile_venmo_correct_sent_requests_yesterday_evening,
            handler=handle_venmo_correct_sent_requests_yesterday_evening,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_file_update_reunion_rsvps_from_phone",
                (SlotSpec("directory_path"),),
            ),
            compiler=compile_file_update_reunion_rsvps_from_phone,
            handler=handle_file_update_reunion_rsvps_from_phone,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_remind_old_payment_requests",
                (
                    SlotSpec("relationships"),
                    SlotSpec("min_days"),
                ),
            ),
            compiler=compile_venmo_remind_old_payment_requests,
            handler=handle_venmo_remind_old_payment_requests,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_process_pending_payment_requests",
                (
                    SlotSpec("decision"),
                    SlotSpec("relationships"),
                ),
            ),
            compiler=compile_venmo_process_pending_payment_requests,
            handler=handle_venmo_process_pending_payment_requests,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_add_friends_by_relationships",
                (SlotSpec("relationships"),),
            ),
            compiler=compile_venmo_add_friends_by_relationships,
            handler=handle_venmo_add_friends_by_relationships,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_delete_phone_spam_messages",
                (SlotSpec("phone_number"),),
            ),
            compiler=compile_delete_phone_spam_messages,
            handler=handle_delete_phone_spam_messages,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_phone_update_wake_alarm_snooze",
                (
                    SlotSpec("day_type"),
                    SlotSpec("snooze_minutes"),
                ),
            ),
            compiler=compile_phone_update_wake_alarm_snooze,
            handler=handle_phone_update_wake_alarm_snooze,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_move_rating_filtered_products",
                (
                    SlotSpec("source_container"),
                    SlotSpec("target_container"),
                    SlotSpec("comparison"),
                    SlotSpec("threshold_rating"),
                ),
            ),
            compiler=compile_amazon_move_rating_filtered_products,
            handler=handle_amazon_move_rating_filtered_products,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_move_product_type_between_saved_lists",
                (
                    SlotSpec("source_container"),
                    SlotSpec("target_container"),
                    SlotSpec("product_type"),
                ),
            ),
            compiler=compile_amazon_move_product_type_between_saved_lists,
            handler=handle_amazon_move_product_type_between_saved_lists,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_order_product_type_from_saved_list",
                (
                    SlotSpec("source_container"),
                    SlotSpec("product_type"),
                    SlotSpec("address_name"),
                    SlotSpec("card_name"),
                ),
            ),
            compiler=compile_amazon_order_product_type_from_saved_list,
            handler=handle_amazon_order_product_type_from_saved_list,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_purchase_phone_recommendation",
                (
                    SlotSpec("recommender_first_name"),
                    SlotSpec("product_type"),
                    SlotSpec("address_name"),
                    SlotSpec("card_name"),
                ),
            ),
            compiler=compile_amazon_purchase_phone_recommendation,
            handler=handle_amazon_purchase_phone_recommendation,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_text_wishlist_itemized_costs",
                (SlotSpec("relationship"),),
            ),
            compiler=compile_amazon_text_wishlist_itemized_costs,
            handler=handle_amazon_text_wishlist_itemized_costs,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_answer_cart_wishlist_total",
                (),
            ),
            compiler=compile_amazon_answer_cart_wishlist_total,
            handler=handle_amazon_answer_cart_wishlist_total,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_order_saved_collections",
                (
                    SlotSpec("containers"),
                    SlotSpec("address_name"),
                    SlotSpec("card_name"),
                ),
            ),
            compiler=compile_amazon_order_saved_collections,
            handler=handle_amazon_order_saved_collections,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_cart_buy_cheapest_per_type_move_rest",
                (
                    SlotSpec("address_name"),
                    SlotSpec("card_name"),
                ),
            ),
            compiler=compile_amazon_cart_buy_cheapest_per_type_move_rest,
            handler=handle_amazon_cart_buy_cheapest_per_type_move_rest,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_order_exact_products_restore_cart",
                (
                    SlotSpec("items"),
                    SlotSpec("address_name"),
                    SlotSpec("preferred_card_name"),
                    SlotSpec("restore_cart"),
                ),
            ),
            compiler=compile_amazon_order_exact_products_restore_cart,
            handler=handle_amazon_order_exact_products_restore_cart,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_order_product_and_archive_receipt",
                (
                    SlotSpec("product_name"),
                    SlotSpec("quantity"),
                    SlotSpec("address_name"),
                    SlotSpec("bills_root"),
                ),
            ),
            compiler=compile_amazon_order_product_and_archive_receipt,
            handler=handle_amazon_order_product_and_archive_receipt,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_download_all_order_receipts",
                (
                    SlotSpec("directory_path"),
                    SlotSpec("file_format"),
                ),
            ),
            compiler=compile_amazon_download_all_order_receipts,
            handler=handle_amazon_download_all_order_receipts,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_order_trip_supplies_by_deadline",
                (
                    SlotSpec("product_types"),
                    SlotSpec("quantity"),
                    SlotSpec("trip_day"),
                    SlotSpec("address_name"),
                    SlotSpec("card_name"),
                ),
            ),
            compiler=compile_amazon_order_trip_supplies_by_deadline,
            handler=handle_amazon_order_trip_supplies_by_deadline,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_return_recent_orders",
                (
                    SlotSpec("order_count"),
                    SlotSpec("deliverer_name"),
                ),
            ),
            compiler=compile_amazon_return_recent_orders,
            handler=handle_amazon_return_recent_orders,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_return_same_product_except_size_this_week",
                (
                    SlotSpec("product_name"),
                    SlotSpec("keep_size"),
                    SlotSpec("deliverer_name"),
                ),
            ),
            compiler=compile_amazon_return_same_product_except_size_this_week,
            handler=handle_amazon_return_same_product_except_size_this_week,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_buy_last_product_variants",
                (
                    SlotSpec("product_type"),
                    SlotSpec("colors"),
                    SlotSpec("address_name"),
                    SlotSpec("card_name"),
                ),
            ),
            compiler=compile_amazon_buy_last_product_variants,
            handler=handle_amazon_buy_last_product_variants,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_replace_last_product_adjacent_size",
                (
                    SlotSpec("product_type"),
                    SlotSpec("size_direction"),
                    SlotSpec("preferred_color"),
                    SlotSpec("address_name"),
                    SlotSpec("card_name"),
                ),
            ),
            compiler=compile_amazon_replace_last_product_adjacent_size,
            handler=handle_amazon_replace_last_product_adjacent_size,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_order_preferred_color_size_product",
                (
                    SlotSpec("product_name"),
                    SlotSpec("relative_size"),
                    SlotSpec("color_preferences"),
                    SlotSpec("quantity"),
                    SlotSpec("address_name"),
                    SlotSpec("card_name"),
                ),
            ),
            compiler=compile_amazon_order_preferred_color_size_product,
            handler=handle_amazon_order_preferred_color_size_product,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_order_filtered_product",
                (
                    SlotSpec("product_type"),
                    SlotSpec("min_price", required=False),
                    SlotSpec("max_price", required=False),
                    SlotSpec("min_product_rating", required=False),
                    SlotSpec("min_product_reviews", required=False),
                    SlotSpec("min_seller_rating", required=False),
                    SlotSpec("price_bounds_inclusive", required=False),
                    SlotSpec("rating_threshold_inclusive", required=False),
                    SlotSpec("prefer_highest_seller", required=False),
                    SlotSpec("source_container", required=False),
                    SlotSpec("prior_ordered_sellers_only", required=False),
                    SlotSpec("max_length", required=False),
                    SlotSpec("max_width", required=False),
                    SlotSpec("quantity_relationship", required=False),
                    SlotSpec("allow_mixed_products", required=False),
                    SlotSpec("quantity"),
                    SlotSpec("address_name"),
                    SlotSpec("card_name"),
                ),
            ),
            compiler=compile_amazon_order_filtered_product,
            handler=handle_amazon_order_filtered_product,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_post_question_last_ordered_product",
                (
                    SlotSpec("product_type"),
                    SlotSpec("question"),
                ),
            ),
            compiler=compile_amazon_post_question_last_ordered_product,
            handler=handle_amazon_post_question_last_ordered_product,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_update_last_month_order_review",
                (
                    SlotSpec("product_color"),
                    SlotSpec("product_type"),
                    SlotSpec("target_rating"),
                    SlotSpec("title"),
                ),
            ),
            compiler=compile_amazon_update_last_month_order_review,
            handler=handle_amazon_update_last_month_order_review,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_answer_last_order_question_yes_no",
                (
                    SlotSpec("product_type"),
                    SlotSpec("question"),
                ),
            ),
            compiler=compile_amazon_answer_last_order_question_yes_no,
            handler=handle_amazon_answer_last_order_question_yes_no,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_answer_verified_battery_life_hours",
                (SlotSpec("product_name"),),
            ),
            compiler=compile_amazon_answer_verified_battery_life_hours,
            handler=handle_amazon_answer_verified_battery_life_hours,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_answer_returned_product_yes_no",
                (
                    SlotSpec("product_type"),
                    SlotSpec("period"),
                ),
            ),
            compiler=compile_amazon_answer_returned_product_yes_no,
            handler=handle_amazon_answer_returned_product_yes_no,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_answer_order_arrival_date",
                (
                    SlotSpec("day_offset"),
                    SlotSpec("date_format"),
                ),
            ),
            compiler=compile_amazon_answer_order_arrival_date,
            handler=handle_amazon_answer_order_arrival_date,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_answer_spending_total",
                (SlotSpec("period"),),
            ),
            compiler=compile_amazon_answer_spending_total,
            handler=handle_amazon_answer_spending_total,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_amazon_answer_current_price_from_birthday_order",
                (
                    SlotSpec("product_type"),
                    SlotSpec("relationship"),
                ),
            ),
            compiler=compile_amazon_answer_current_price_from_birthday_order,
            handler=handle_amazon_answer_current_price_from_birthday_order,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_membership_paid_total",
                (SlotSpec("app_name"),),
            ),
            compiler=compile_membership_paid_total,
            handler=handle_membership_paid_total,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_membership_last_payment_card_name",
                (SlotSpec("app_name"),),
            ),
            compiler=compile_membership_last_payment_card_name,
            handler=handle_membership_last_payment_card_name,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_membership_remaining_duration",
                (
                    SlotSpec("app_name"),
                    SlotSpec("unit"),
                ),
            ),
            compiler=compile_membership_remaining_duration,
            handler=handle_membership_remaining_duration,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_delete_gmail_empty_drafts",
                (SlotSpec("condition"),),
            ),
            compiler=compile_delete_gmail_empty_drafts,
            handler=handle_delete_gmail_empty_drafts,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_send_future_scheduled_drafts_now",
                (),
            ),
            compiler=compile_gmail_send_future_scheduled_drafts_now,
            handler=handle_gmail_send_future_scheduled_drafts_now,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_amazon_promo_codes_answer",
                (),
            ),
            compiler=compile_gmail_amazon_promo_codes_answer,
            handler=handle_gmail_amazon_promo_codes_answer,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_count_threads",
                (
                    SlotSpec("mailbox"),
                    SlotSpec("read_state"),
                    SlotSpec("label", required=False),
                ),
            ),
            compiler=compile_gmail_count_threads,
            handler=handle_gmail_count_threads,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_schedule_resignation_draft",
                (
                    SlotSpec("attachment_path"),
                    SlotSpec("weekday"),
                    SlotSpec("week_offset"),
                    SlotSpec("hour"),
                ),
            ),
            compiler=compile_gmail_schedule_resignation_draft,
            handler=handle_gmail_schedule_resignation_draft,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_thread_cleanup",
                (
                    SlotSpec("action"),
                    SlotSpec("exception_mode"),
                ),
            ),
            compiler=compile_gmail_thread_cleanup,
            handler=handle_gmail_thread_cleanup,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_mark_threads_read_state_by_calendar_window",
                (
                    SlotSpec("target_state"),
                    SlotSpec("window"),
                ),
            ),
            compiler=compile_gmail_mark_threads_read_state_by_calendar_window,
            handler=handle_gmail_mark_threads_read_state_by_calendar_window,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_delete_archived_threads_by_calendar_window",
                (SlotSpec("window"),),
            ),
            compiler=compile_gmail_delete_archived_threads_by_calendar_window,
            handler=handle_gmail_delete_archived_threads_by_calendar_window,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_forward_anniversary_announcement_email",
                (SlotSpec("recipient_email"),),
            ),
            compiler=compile_gmail_forward_anniversary_announcement_email,
            handler=handle_gmail_forward_anniversary_announcement_email,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_forward_caterer_bill_to_manager_with_note",
                (SlotSpec("note_prefix"),),
            ),
            compiler=compile_gmail_forward_caterer_bill_to_manager_with_note,
            handler=handle_gmail_forward_caterer_bill_to_manager_with_note,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_forward_roommate_bill_to_other_roommates",
                (SlotSpec("file_name"),),
            ),
            compiler=compile_gmail_forward_roommate_bill_to_other_roommates,
            handler=handle_gmail_forward_roommate_bill_to_other_roommates,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_forward_trip_expenses_thread_with_attachment",
                (
                    SlotSpec("sender_first_name"),
                    SlotSpec("recipient_first_name"),
                    SlotSpec("attachment_path"),
                    SlotSpec("note_prefix"),
                ),
            ),
            compiler=compile_gmail_forward_trip_expenses_thread_with_attachment,
            handler=handle_gmail_forward_trip_expenses_thread_with_attachment,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_reply_weekly_manager_tasks_by_star_state",
                (
                    SlotSpec("subject_prefix"),
                    SlotSpec("done_reply"),
                    SlotSpec("not_done_reply"),
                ),
            ),
            compiler=compile_gmail_reply_weekly_manager_tasks_by_star_state,
            handler=handle_gmail_reply_weekly_manager_tasks_by_star_state,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_star_threads_by_relationship",
                (SlotSpec("relationship"),),
            ),
            compiler=compile_gmail_star_threads_by_relationship,
            handler=handle_gmail_star_threads_by_relationship,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_label_notification_threads_by_app",
                (),
            ),
            compiler=compile_gmail_label_notification_threads_by_app,
            handler=handle_gmail_label_notification_threads_by_app,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_relabel_priority_threads",
                (
                    SlotSpec("source_label_1"),
                    SlotSpec("source_label_2"),
                    SlotSpec("target_label_1"),
                    SlotSpec("target_label_2"),
                    SlotSpec("remove_label"),
                ),
            ),
            compiler=compile_gmail_relabel_priority_threads,
            handler=handle_gmail_relabel_priority_threads,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_attach_job_search_files_and_send",
                (
                    SlotSpec("days_back"),
                    SlotSpec("file_name"),
                ),
            ),
            compiler=compile_gmail_attach_job_search_files_and_send,
            handler=handle_gmail_attach_job_search_files_and_send,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_download_flight_ticket_attachment",
                (
                    SlotSpec("destination"),
                    SlotSpec("directory_path"),
                ),
            ),
            compiler=compile_gmail_download_flight_ticket_attachment,
            handler=handle_gmail_download_flight_ticket_attachment,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_gmail_email_named_file_to_relationship",
                (
                    SlotSpec("file_description"),
                    SlotSpec("relationship"),
                ),
            ),
            compiler=compile_gmail_email_named_file_to_relationship,
            handler=handle_gmail_email_named_file_to_relationship,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_remove_expired_payment_cards",
                (),
            ),
            compiler=compile_remove_expired_payment_cards,
            handler=handle_remove_expired_payment_cards,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_bucket_list_status_update",
                (
                    SlotSpec("item"),
                    SlotSpec("done"),
                ),
            ),
            compiler=compile_bucket_list_status_update,
            handler=handle_bucket_list_status_update,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_simple_note_count_bucket_list_status",
                (SlotSpec("status"),),
            ),
            compiler=compile_simple_note_count_bucket_list_status,
            handler=handle_simple_note_count_bucket_list_status,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_simple_note_fill_liked_song_release_months",
                (),
            ),
            compiler=compile_simple_note_fill_liked_song_release_months,
            handler=handle_simple_note_fill_liked_song_release_months,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_follow_artists_by_genre_followers",
                (
                    SlotSpec("genre"),
                    SlotSpec("min_follower_count"),
                ),
            ),
            compiler=compile_spotify_follow_artists_by_genre_followers,
            handler=handle_spotify_follow_artists_by_genre_followers,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_add_artist_playcount_songs_to_queue",
                (
                    SlotSpec("artist_name"),
                    SlotSpec("min_play_count"),
                ),
            ),
            compiler=compile_spotify_add_artist_playcount_songs_to_queue,
            handler=handle_spotify_add_artist_playcount_songs_to_queue,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_like_songs_from_followed_artists",
                (),
            ),
            compiler=compile_spotify_like_songs_from_followed_artists,
            handler=handle_spotify_like_songs_from_followed_artists,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_public_liked_library_playlist_share",
                (SlotSpec("partner_relationship"),),
            ),
            compiler=compile_spotify_public_liked_library_playlist_share,
            handler=handle_spotify_public_liked_library_playlist_share,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_sync_following_by_liked_song_artists",
                (SlotSpec("operation"),),
            ),
            compiler=compile_spotify_sync_following_by_liked_song_artists,
            handler=handle_spotify_sync_following_by_liked_song_artists,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_playlist_best_song_per_collection",
                (
                    SlotSpec("playlist_title"),
                    SlotSpec("song_metric"),
                    SlotSpec("collection_type"),
                ),
            ),
            compiler=compile_spotify_playlist_best_song_per_collection,
            handler=handle_spotify_playlist_best_song_per_collection,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_playlist_from_recent_simple_note",
                (SlotSpec("playlist_title"),),
            ),
            compiler=compile_spotify_playlist_from_recent_simple_note,
            handler=handle_spotify_playlist_from_recent_simple_note,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_append_most_common_playlist_genre",
                (),
            ),
            compiler=compile_spotify_append_most_common_playlist_genre,
            handler=handle_spotify_append_most_common_playlist_genre,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_like_all_library_items",
                (),
            ),
            compiler=compile_spotify_like_all_library_items,
            handler=handle_spotify_like_all_library_items,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_download_liked_library_songs",
                (SlotSpec("collection_type"),),
            ),
            compiler=compile_spotify_download_liked_library_songs,
            handler=handle_spotify_download_liked_library_songs,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_rate_library_songs_by_liked_status",
                (
                    SlotSpec("collection_type"),
                    SlotSpec("liked_filter"),
                    SlotSpec("target_rating"),
                ),
            ),
            compiler=compile_spotify_rate_library_songs_by_liked_status,
            handler=handle_spotify_rate_library_songs_by_liked_status,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_follow_artists_from_liked_songs_and_albums",
                (),
            ),
            compiler=compile_spotify_follow_artists_from_liked_songs_and_albums,
            handler=handle_spotify_follow_artists_from_liked_songs_and_albums,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_follow_playlist_song_artists_by_genre",
                (SlotSpec("genre"),),
            ),
            compiler=compile_spotify_follow_playlist_song_artists_by_genre,
            handler=handle_spotify_follow_playlist_song_artists_by_genre,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_top_played_genre_titles",
                (
                    SlotSpec("genre"),
                    SlotSpec("limit"),
                ),
            ),
            compiler=compile_spotify_top_played_genre_titles,
            handler=handle_spotify_top_played_genre_titles,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_count_unique_library_songs",
                (),
            ),
            compiler=compile_spotify_count_unique_library_songs,
            handler=handle_spotify_count_unique_library_songs,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_pay_grocery_from_text_and_notify",
                (
                    SlotSpec("person_first_name"),
                    SlotSpec("note"),
                    SlotSpec("message"),
                ),
            ),
            compiler=compile_venmo_pay_grocery_from_text_and_notify,
            handler=handle_venmo_pay_grocery_from_text_and_notify,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_count_recent_release_library_songs",
                (
                    SlotSpec("years_back"),
                    SlotSpec("include_current_year"),
                ),
            ),
            compiler=compile_spotify_count_recent_release_library_songs,
            handler=handle_spotify_count_recent_release_library_songs,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_navigate_until_artist",
                (
                    SlotSpec("direction"),
                    SlotSpec("artist_name"),
                ),
            ),
            compiler=compile_spotify_navigate_until_artist,
            handler=handle_spotify_navigate_until_artist,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_reset_friends_to_phone_friends",
                (),
            ),
            compiler=compile_venmo_reset_friends_to_phone_friends,
            handler=handle_venmo_reset_friends_to_phone_friends,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_filter_queue_by_liked_status",
                (SlotSpec("remove_filter"),),
            ),
            compiler=compile_spotify_filter_queue_by_liked_status,
            handler=handle_spotify_filter_queue_by_liked_status,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_navigate_until_private_status",
                (
                    SlotSpec("direction"),
                    SlotSpec("status_property"),
                ),
            ),
            compiler=compile_spotify_navigate_until_private_status,
            handler=handle_spotify_navigate_until_private_status,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_play_offline_downloaded_collection",
                (
                    SlotSpec("collection_type"),
                    SlotSpec("required_minutes"),
                ),
            ),
            compiler=compile_spotify_play_offline_downloaded_collection,
            handler=handle_spotify_play_offline_downloaded_collection,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_sum_month_transactions",
                (SlotSpec("direction"),),
            ),
            compiler=compile_venmo_sum_month_transactions,
            handler=handle_venmo_sum_month_transactions,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_sum_recent_received_requests",
                (SlotSpec("days"),),
            ),
            compiler=compile_venmo_sum_recent_received_requests,
            handler=handle_venmo_sum_recent_received_requests,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_reset_queue_with_recommendations",
                (),
            ),
            compiler=compile_spotify_reset_queue_with_recommendations,
            handler=handle_spotify_reset_queue_with_recommendations,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_archive_playlist_songs_from_file",
                (
                    SlotSpec("source_file_path"),
                    SlotSpec("playlist_title"),
                ),
            ),
            compiler=compile_spotify_archive_playlist_songs_from_file,
            handler=handle_spotify_archive_playlist_songs_from_file,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_playlist_from_workout_email",
                (SlotSpec("playlist_title"),),
            ),
            compiler=compile_spotify_playlist_from_workout_email,
            handler=handle_spotify_playlist_from_workout_email,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_reply_liked_song_recommendations_email",
                (
                    SlotSpec("relationship"),
                    SlotSpec("message_prefix"),
                ),
            ),
            compiler=compile_spotify_reply_liked_song_recommendations_email,
            handler=handle_spotify_reply_liked_song_recommendations_email,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_update_song_recommendation_draft_from_library",
                (SlotSpec("person_first_name"),),
            ),
            compiler=compile_spotify_update_song_recommendation_draft_from_library,
            handler=handle_spotify_update_song_recommendation_draft_from_library,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_simple_note_import_markdown_files",
                (SlotSpec("source_directory"),),
            ),
            compiler=compile_simple_note_import_markdown_files,
            handler=handle_simple_note_import_markdown_files,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_simple_note_workout_duration",
                (SlotSpec("day_ref"),),
            ),
            compiler=compile_simple_note_workout_duration,
            handler=handle_simple_note_workout_duration,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_simple_note_random_quote",
                (SlotSpec("quote_type"),),
            ),
            compiler=compile_simple_note_random_quote,
            handler=handle_simple_note_random_quote,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_simple_note_longest_habit_streak",
                (SlotSpec("habit_key"),),
            ),
            compiler=compile_simple_note_longest_habit_streak,
            handler=handle_simple_note_longest_habit_streak,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_simple_note_add_today_habit_log",
                (
                    SlotSpec("habit_key"),
                    SlotSpec("value"),
                ),
            ),
            compiler=compile_simple_note_add_today_habit_log,
            handler=handle_simple_note_add_today_habit_log,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_simple_note_export_habit_tracker_csv",
                (
                    SlotSpec("destination_path"),
                    SlotSpec("sort_order"),
                ),
            ),
            compiler=compile_simple_note_export_habit_tracker_csv,
            handler=handle_simple_note_export_habit_tracker_csv,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_simple_note_update_monthly_venmo_expense",
                (),
            ),
            compiler=compile_simple_note_update_monthly_venmo_expense,
            handler=handle_simple_note_update_monthly_venmo_expense,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_todoist_fill_today_from_schedule",
                (SlotSpec("target_project_name"),),
            ),
            compiler=compile_todoist_fill_today_from_schedule,
            handler=handle_todoist_fill_today_from_schedule,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_splitwise_record_trip_expenses_from_simple_note",
                (SlotSpec("relationship_type"),),
            ),
            compiler=compile_splitwise_record_trip_expenses_from_simple_note,
            handler=handle_splitwise_record_trip_expenses_from_simple_note,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_approve_roommate_requests_this_month",
                (),
            ),
            compiler=compile_venmo_approve_roommate_requests_this_month,
            handler=handle_venmo_approve_roommate_requests_this_month,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_file_delete_downloads_by_extension",
                (SlotSpec("extension"),),
            ),
            compiler=compile_file_delete_downloads_by_extension,
            handler=handle_file_delete_downloads_by_extension,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_followed_artist_follower_extreme",
                (SlotSpec("extreme"),),
            ),
            compiler=compile_spotify_followed_artist_follower_extreme,
            handler=handle_spotify_followed_artist_follower_extreme,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_liked_genre_extreme",
                (
                    SlotSpec("collection_type"),
                    SlotSpec("extreme"),
                ),
            ),
            compiler=compile_spotify_liked_genre_extreme,
            handler=handle_spotify_liked_genre_extreme,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_playlist_artist_song_count_extreme",
                (
                    SlotSpec("extreme"),
                    SlotSpec("limit"),
                ),
            ),
            compiler=compile_spotify_playlist_artist_song_count_extreme,
            handler=handle_spotify_playlist_artist_song_count_extreme,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_sum_year_bill_payments",
                (SlotSpec("bill_type"),),
            ),
            compiler=compile_venmo_sum_year_bill_payments,
            handler=handle_venmo_sum_year_bill_payments,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_friend_transaction_counterparties",
                (
                    SlotSpec("direction"),
                    SlotSpec("sync_mode"),
                ),
            ),
            compiler=compile_venmo_friend_transaction_counterparties,
            handler=handle_venmo_friend_transaction_counterparties,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_count_friends_since_month_start",
                (
                    SlotSpec("month"),
                    SlotSpec("year_offset"),
                ),
            ),
            compiler=compile_venmo_count_friends_since_month_start,
            handler=handle_venmo_count_friends_since_month_start,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_play_released_year_from_collection",
                (
                    SlotSpec("release_year"),
                    SlotSpec("collection_type"),
                ),
            ),
            compiler=compile_spotify_play_released_year_from_collection,
            handler=handle_spotify_play_released_year_from_collection,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_like_transactions_by_relationship_period",
                (
                    SlotSpec("relationships"),
                    SlotSpec("period"),
                ),
            ),
            compiler=compile_venmo_like_transactions_by_relationship_period,
            handler=handle_venmo_like_transactions_by_relationship_period,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_manager_meal_total_from_social_feed",
                (
                    SlotSpec("relationships"),
                    SlotSpec("meal"),
                    SlotSpec("venue"),
                    SlotSpec("share_amount"),
                ),
            ),
            compiler=compile_venmo_manager_meal_total_from_social_feed,
            handler=handle_venmo_manager_meal_total_from_social_feed,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_venmo_sum_transaction_likes",
                (
                    SlotSpec("direction"),
                    SlotSpec("period"),
                ),
            ),
            compiler=compile_venmo_sum_transaction_likes,
            handler=handle_venmo_sum_transaction_likes,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_file_prefix_and_move_old_files",
                (
                    SlotSpec("source_directory"),
                    SlotSpec("prefix_format"),
                    SlotSpec("old_destination_directory"),
                ),
            ),
            compiler=compile_file_prefix_and_move_old_files,
            handler=handle_file_prefix_and_move_old_files,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_file_reorganize_dated_meeting_files",
                (SlotSpec("source_directory"),),
            ),
            compiler=compile_file_reorganize_dated_meeting_files,
            handler=handle_file_reorganize_dated_meeting_files,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_spotify_current_artist_followers",
                (),
            ),
            compiler=compile_spotify_current_artist_followers,
            handler=handle_spotify_current_artist_followers,
        ),
        IntentMachine(
            schema=IntentSchema(
                "appworld_simple_note_export_markdown",
                (SlotSpec("destination_directory"),),
            ),
            compiler=compile_simple_note_export_markdown,
            handler=handle_simple_note_export_markdown,
        ),
    ]


def compile_phone_message_non_venmo_contacts(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.search(
        r'Send the following phone message to my (?P<relations>.+?), who do not have a '
        r'(?P<app>[A-Za-z0-9_ -]+) account, "(?P<message>[^"]+)"\.?',
        raw_request,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_phone_message_non_venmo_contacts")
    frame.set_slot("relationships", extract_relationships(match.group("relations")), source="regex")
    frame.set_slot("excluded_app", match.group("app").strip().lower(), source="regex")
    frame.set_slot("message", match.group("message"), source="regex")
    return frame


def compile_phone_send_message_to_relationship(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.search(
        r'Send a phone (?P<kind>text|voice) message to my (?P<relations>.+?), "(?P<message>[^"]+)"\.?',
        raw_request,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    relationships = extract_relationships(match.group("relations"))
    if not relationships:
        return None
    frame = IntentFrame("appworld_phone_send_message_to_relationship")
    frame.set_slot("relationships", relationships, source="regex")
    frame.set_slot("message_kind", match.group("kind").lower(), source="regex")
    frame.set_slot("message", match.group("message"), source="regex")
    return frame


def compile_phone_reply_favorite_recipe_to_relationship(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"My (?P<relation>wife|husband|mother) has asked me what I'd like for dinner on phone\. "
        r"Reply (?:her|him) with any one of my favorite recipes' name from my Simple Note account\. "
        r"Just the name, nothing else\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    relation = match.group("relation").lower()
    frame = IntentFrame("appworld_phone_reply_favorite_recipe_to_relationship")
    frame.set_slot("relationship", relation, source="regex")
    return frame


def compile_splitwise_accept_known_phone_invitations(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"I got some Splitwise group invitations over phone (?P<kind>text|voice) messages "
        r"(?P<window>yesterday|the day before yesterday|this week)\. If their number is in my "
        r"phone contact book, accept it, otherwise delete those messages\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_splitwise_accept_known_phone_invitations")
    frame.set_slot("message_kind", match.group("kind").lower(), source="regex")
    frame.set_slot(
        "date_window",
        match.group("window").lower().replace(" ", "_"),
        source="regex",
    )
    return frame


def compile_venmo_signup_missing_relationship_accounts(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'I need my (?P<relations>parents|roommates) to have a venmo account\. Last time I checked '
        r'none had one\. Make an account for whoever that does not have it yet, using their '
        r'email address and (?P<password>.+?) as password\. Then send them a phone text '
        r'message, "(?P<message>[^"]+)"\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    relationships = extract_relationships(match.group("relations"))
    if not relationships:
        return None
    frame = IntentFrame("appworld_venmo_signup_missing_relationship_accounts")
    frame.set_slot("relationships", relationships, source="regex")
    frame.set_slot("password", match.group("password").strip(), source="regex")
    frame.set_slot("message", match.group("message"), source="regex")
    return frame


def compile_phone_message_app_account_verify_reset(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"My (?P<relation>son|daughter|child) sent me a message (?P<window>yesterday) "
        r"on phone about an app account creation\. Please do as per (?:his|her|their) "
        r"message\. Use password (?P<password>.+?) for the new account\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    relationship = RELATION_ALIASES.get(match.group("relation").lower(), match.group("relation").lower())
    frame = IntentFrame("appworld_phone_message_app_account_verify_reset")
    frame.set_slot("relationship", relationship, source="regex")
    frame.set_slot("password", match.group("password").strip(), source="regex")
    frame.set_slot("date_window", match.group("window").lower(), source="regex")
    return frame


def compile_shared_subscription_password_reset_and_text(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"I share my (?P<app>amazon|spotify) (?P<subscription>prime|premium) account "
        r"with my (?P<relations>roommates|siblings)\. I am having trouble logging in\. "
        r"Change its password to (?P<password>.+?) and share it with them via phone text message\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    relationships = extract_relationships(match.group("relations"))
    if not relationships:
        return None
    frame = IntentFrame("appworld_shared_subscription_password_reset_and_text")
    frame.set_slot("app_name", match.group("app").lower(), source="regex")
    frame.set_slot("subscription_name", match.group("subscription").lower(), source="regex")
    frame.set_slot("relationships", relationships, source="regex")
    frame.set_slot("new_password", match.group("password").strip(), source="regex")
    return frame


def compile_venmo_change_password(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Change my venmo password to (?P<password>.+?)\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    password = match.group("password").strip()
    if len(password) < 5:
        return None
    frame = IntentFrame("appworld_venmo_change_password")
    frame.set_slot("new_password", password, source="regex")
    return frame


def compile_splitwise_record_venmo_receipt_payments(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'I owed people some money\. They put the associated expenses on Splitwise yesterday\. '
        r'I paid some of them up on Venmo today\. Please record payments on Splitwise for each '
        r'in their respective groups\. Each payment should have a note, "(?P<note>[^"]+)", '
        r'and an attached Venmo receipt of it as a proof\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_splitwise_record_venmo_receipt_payments")
    frame.set_slot("note", match.group("note"), source="regex")
    return frame


def compile_todoist_reassign_accepted_takeover_tasks(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'At my job, we manage the tasks on todoist\. But I am changing job soon, so for each task '
        r'that is assigned to me and is incomplete yet, I have asked who can take it from me\. '
        r'See the discussion in comments and reassign based on it\. Then, leave a comment there, '
        r'"(?P<template>[^"]*<person_first_name>[^"]*)"\. Here <person_first_name> is the first '
        r'name of the person who is reassigned the task\. If no one has agreed to take the task, '
        r'leave it as is\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_todoist_reassign_accepted_takeover_tasks")
    frame.set_slot("comment_template", match.group("template"), source="regex")
    return frame


def compile_todoist_fill_today_from_schedule(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'I maintain my work schedule in SimpleNote and track my tasks in Todoist\. '
        r'Every night, I delete the completed tasks from my "(?P<project>[^"]+)" project\. '
        r'Then, I move the maximum number of incomplete tasks from my Inbox to the '
        r'"(?P=project)" project\. The maximum here is assuming I work back-to-back as '
        r'per my schedule and I find time for the left overs from the current day first\. '
        r'I am busy tonight, please do it for me\. Note that the moved tasks must be '
        r'identical to the original ones\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_todoist_fill_today_from_schedule")
    frame.set_slot("target_project_name", match.group("project"), source="regex")
    return frame


def compile_spotify_apply_todoist_playlist_suggestions(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'I am going on a trip to (?P<destination>[^.]+?) with some of my '
        r'(?P<relationship>roommates|siblings|friends)\. We are managing its planning on a '
        r'Todoist project for it\. One of the tasks in it is about preparing a Spotify playlist\. '
        r'I have made the playlist and shared it with others on the project\. But they have made '
        r'some suggestions in comments\. Please incorporate them, leave a final comment, '
        r'"(?P<final_comment>[^"]+)", and mark it complete\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_apply_todoist_playlist_suggestions")
    frame.set_slot("destination", match.group("destination").strip(), source="regex")
    frame.set_slot("relationship_type", match.group("relationship").lower(), source="regex")
    frame.set_slot("final_comment", match.group("final_comment"), source="regex")
    return frame


def compile_spotify_apply_phone_playlist_suggestions(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"My (?P<relationship>roommates|siblings) and I are preparing a playlist for a "
        r"roadtrip together\. I prepared the initial playlist on Spotify and shared it "
        r"with them on phone messages\. They have replied with suggested changes\. "
        r"Please update this playlist accordingly\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_apply_phone_playlist_suggestions")
    frame.set_slot("relationship_type", match.group("relationship").lower(), source="regex")
    return frame


def compile_pay_csv_debts_via_venmo_or_splitwise(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"I have a list of people I owe money to, including amounts and descriptions, in "
        r"(?P<csv_file_name>[A-Za-z0-9_-]+\.csv)\. For each person, \(1\) If they have "
        r"a Venmo account, send the money (?P<privacy>privately|publicly) with the specified "
        r"amount and description\. \(2\) If not, create an individual \(non-grouped\) "
        r"Splitwise expense with the same details so I remember to pay them later\. For "
        r"Splitwise expenses, attach the PDF receipt as well\. They are in the same folder "
        r"as the CSV file\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_pay_csv_debts_via_venmo_or_splitwise")
    frame.set_slot("csv_file_name", match.group("csv_file_name"), source="regex")
    frame.set_slot("private", match.group("privacy").lower() == "privately", source="regex")
    return frame


def compile_venmo_send_to_phone_number(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.search(
        r"Send \$(?P<amount>\d+(?:\.\d+)?) (?P<privacy>privately|publicly) on Venmo "
        r"to the person with this phone number (?P<phone>\d+)\.?",
        raw_request,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_venmo_send_to_phone_number")
    frame.set_slot("phone_number", match.group("phone"), source="regex")
    frame.set_slot("amount", float(match.group("amount")), source="regex")
    frame.set_slot("private", match.group("privacy").lower() == "privately", source="regex")
    return frame


def compile_venmo_send_to_named_user(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Send \$(?P<amount>\d+(?:\.\d+)?) on venmo to (?P<first_name>[A-Z][A-Za-z]+)\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_venmo_send_to_named_user")
    frame.set_slot("person_first_name", match.group("first_name"), source="regex")
    frame.set_slot("amount", float(match.group("amount")), source="regex")
    return frame


def compile_venmo_send_to_named_user_with_optional_signup(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Send \$(?P<amount>\d+(?:\.\d+)?) to (?P<first_name>[A-Z][A-Za-z]+) via Venmo\. "
        r"You may need to make me an account first, if I do not have one\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_venmo_send_to_named_user_with_optional_signup")
    frame.set_slot("person_first_name", match.group("first_name"), source="regex")
    frame.set_slot("amount", float(match.group("amount")), source="regex")
    return frame


def compile_venmo_pay_flight_bill_from_email(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"(?P<first_name>[A-Z][A-Za-z]+) booked a flight for me\. "
        r"They have sent me my part of the bill recently over email\. "
        r"Send them the owed amount on venmo with a description note, "
        r"\"(?P<note>[^\"]+)\"\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_venmo_pay_flight_bill_from_email")
    frame.set_slot("person_first_name", match.group("first_name"), source="regex")
    frame.set_slot("note", match.group("note"), source="regex")
    return frame


def compile_venmo_pay_coworkers_and_email(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'Send \$(?P<amount>\d+(?:\.\d+)?) to each of my (?P<relations>coworkers) '
        r'privately on venmo with a note\s*"(?P<note>[^"]+)"\. '
        r'Then send an email with all of them in the recipients with\s*'
        r'the subject, "(?P<subject>[^"]+)", and body "(?P<body>[^"]+)"',
        raw_request.strip(),
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    relationships = extract_relationships(match.group("relations"))
    if not relationships:
        return None
    frame = IntentFrame("appworld_venmo_pay_coworkers_and_email")
    frame.set_slot("relationships", relationships, source="regex")
    frame.set_slot("amount", float(match.group("amount")), source="regex")
    frame.set_slot("note", match.group("note"), source="regex")
    frame.set_slot("email_subject", match.group("subject"), source="regex")
    frame.set_slot("email_body", match.group("body"), source="regex")
    return frame


def compile_venmo_accept_named_carpool_request_this_month(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"(?P<first_name>[A-Z][A-Za-z]+) and I have been carpooling to work this month\. "
        r"They have requested money for it on venmo\. Accept it\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_venmo_accept_named_carpool_request_this_month")
    frame.set_slot("person_first_name", match.group("first_name"), source="regex")
    return frame


def compile_venmo_correct_housing_bill_request(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'My roommate requested me to pay for my share of the housing bill this month on venmo today\. '
        r'But they forgot about the (?P<percent>\d+(?:\.\d+)?)% rent (?P<adjustment>increase|decrease) '
        r'starting this month\. So reject that payment request and send them the corrected amount of money '
        r'with a note, "(?P<note>[^"]+)"\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_venmo_correct_housing_bill_request")
    frame.set_slot("percent", float(match.group("percent")), source="regex")
    frame.set_slot("adjustment", match.group("adjustment").lower(), source="regex")
    frame.set_slot("note", match.group("note"), source="regex")
    return frame


def compile_venmo_approve_requests_and_withdraw_balance(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Approve all pending venmo payment requests I have received in "
        r"(?P<date_window>this month|this or the last month), and withdraw the remaining "
        r"venmo balance, if any, to my card ending in (?P<card_last4>\d{4})\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    date_window = match.group("date_window").lower().replace(" ", "_")
    frame = IntentFrame("appworld_venmo_approve_requests_and_withdraw_balance")
    frame.set_slot("date_window", date_window, source="regex")
    frame.set_slot("card_last4", match.group("card_last4"), source="regex")
    return frame


def compile_venmo_request_money_from_contact(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.search(
        r'Request \$(?P<amount>\d+(?:\.\d+)?) (?P<privacy>privately|publicly) on Venmo '
        r'from my (?P<relation>[A-Za-z]+), (?P<first_name>[A-Za-z]+), with a note, '
        r'"(?P<note>[^"]+)"\.?',
        raw_request,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    relationships = extract_relationships(match.group("relation"))
    if not relationships:
        return None
    frame = IntentFrame("appworld_venmo_request_money_from_contact")
    frame.set_slot("relationships", relationships, source="regex")
    frame.set_slot("person_first_name", match.group("first_name"), source="regex")
    frame.set_slot("amount", float(match.group("amount")), source="regex")
    frame.set_slot("private", match.group("privacy").lower() == "privately", source="regex")
    frame.set_slot("note", match.group("note"), source="regex")
    return frame


def compile_venmo_settle_trip_note_debts(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'I went on a trip with (?P<relationship>friends) to (?P<trip_name>[A-Za-z][A-Za-z ]*?) '
        r'recently\. I have maintained a note of money I owe to others and others owe me '
        r'from the trip in simple note\. Make private venmo payments or requests accordingly\. '
        r'In the payments/requests, add a note, "(?P<note>[^"]+)"\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_venmo_settle_trip_note_debts")
    frame.set_slot("relationship", RELATION_ALIASES[match.group("relationship").lower()], source="regex")
    frame.set_slot("trip_name", match.group("trip_name").strip(), source="regex")
    frame.set_slot("note", match.group("note"), source="regex")
    return frame


def compile_venmo_settle_roommate_dinner(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'My roommates and I went for a dinner yesterday\. I paid for the taxi back and forth '
        r'\(total \$(?P<taxi_total>\d+(?:\.\d+)?)\) and (?P<food_payer>[A-Za-z]+) paid for '
        r"everyone's food \(total \$(?P<food_total>\d+(?:\.\d+)?)\)\. Both food and commute "
        r'are supposed to be shared equally among all\. Make necessary payment requests with a '
        r'note "(?P<taxi_note>[^"]+)", and a payment to (?P=food_payer) with a note '
        r'"(?P<food_note>[^"]+)", on venmo\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_venmo_settle_roommate_dinner")
    frame.set_slot("taxi_total", float(match.group("taxi_total")), source="regex")
    frame.set_slot("food_total", float(match.group("food_total")), source="regex")
    frame.set_slot("food_payer_first_name", match.group("food_payer"), source="regex")
    frame.set_slot("taxi_note", match.group("taxi_note"), source="regex")
    frame.set_slot("food_note", match.group("food_note"), source="regex")
    return frame


def compile_venmo_send_to_each_relationship_with_refill(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'Send \$(?P<amount>\d+(?:\.\d+)?) to each of my (?P<relations>.+?) '
        r'via venmo with a note, "(?P<note>[^"]+)"\. Refill venmo balance if you need to\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    relationships = extract_relationships(match.group("relations"))
    if not relationships:
        return None
    frame = IntentFrame("appworld_venmo_send_to_each_relationship_with_refill")
    frame.set_slot("relationships", relationships, source="regex")
    frame.set_slot("amount", float(match.group("amount")), source="regex")
    frame.set_slot("note", match.group("note"), source="regex")
    return frame


def compile_venmo_birthday_child_payment_and_text(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'Today is my (?P<relationship>son|daughter)\'s birthday\. Venmo '
        r'(?:him|her) (?P<multiplier_word>twice|thrice|four times|\d+(?:\.\d+)? times) '
        r'the money I sent (?:him|her) on (?:his|her) last birthday, privately, '
        r'with a description note, "(?P<note>[^"]+)"\. Then leave (?:him|her) '
        r'a phone text message, "(?P<message>[^"]+)"\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    multiplier_text = match.group("multiplier_word").lower().strip()
    multiplier_by_word = {"twice": 2.0, "thrice": 3.0, "four times": 4.0}
    if multiplier_text in multiplier_by_word:
        multiplier = multiplier_by_word[multiplier_text]
    else:
        multiplier = float(multiplier_text.split()[0])
    frame = IntentFrame("appworld_venmo_birthday_child_payment_and_text")
    frame.set_slot("relationship", match.group("relationship").lower(), source="regex")
    frame.set_slot("multiplier", multiplier, source="regex")
    frame.set_slot("note", match.group("note"), source="regex")
    frame.set_slot("message", match.group("message"), source="regex")
    return frame


def compile_venmo_correct_sent_requests_yesterday_evening(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"I made venmo payment requests to (?P<target>some of my friends|my roommates) "
        r"yesterday evening\. Unfortunately, I have made a mistake in calculation\. "
        r"Each of them owes me \$(?P<amount>\d+(?:\.\d+)?) "
        r"(?P<direction>less|more) than the requested amount\. So delete those requests "
        r"and make new ones with everything else the same, but with the corrected amount\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    target = match.group("target").lower()
    relationships = ["roommate"] if "roommate" in target else ["friend"]
    adjustment = "decrease" if match.group("direction").lower() == "less" else "increase"
    frame = IntentFrame("appworld_venmo_correct_sent_requests_yesterday_evening")
    frame.set_slot("relationships", relationships, source="regex")
    frame.set_slot("adjustment", adjustment, source="regex")
    frame.set_slot("difference_amount", float(match.group("amount")), source="regex")
    return frame


def compile_file_update_reunion_rsvps_from_phone(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'I have invited some of my friends to a reunion party via phone messages\. '
        r'I have made a CSV to track who is coming or not in "(?P<directory>~\/documents\/(?:personal|personal_stuff|personal_files)\/)" '
        r"in my file system\. Please update RSVPs in it as per their latest replies\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_file_update_reunion_rsvps_from_phone")
    frame.set_slot("directory_path", match.group("directory"), source="regex")
    return frame


def compile_venmo_remind_old_payment_requests(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.search(
        r"Send a reminder on Venmo for all my payment requests to my (?P<relations>.+?) which have not been approved or denied for (?P<days>\d+) or more days\.?",
        raw_request,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    relationships = extract_relationships(match.group("relations"))
    if not relationships:
        return None
    frame = IntentFrame("appworld_venmo_remind_old_payment_requests")
    frame.set_slot("relationships", relationships, source="regex")
    frame.set_slot("min_days", int(match.group("days")), source="regex")
    return frame


def compile_venmo_process_pending_payment_requests(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.search(
        r"(?P<decision>Accept|Reject) all pending Venmo payment requests from my (?P<relations>.+?)\.?$",
        raw_request,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    relationships = extract_relationships(match.group("relations"))
    if not relationships:
        return None
    decision = "approve" if match.group("decision").lower() == "accept" else "deny"
    frame = IntentFrame("appworld_venmo_process_pending_payment_requests")
    frame.set_slot("decision", decision, source="regex")
    frame.set_slot("relationships", relationships, source="regex")
    return frame


def compile_venmo_add_friends_by_relationships(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.search(
        r"Add all my (?P<relations>.+?) as friends on venmo, if they are not already\.?",
        raw_request,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    relationships = extract_relationships(match.group("relations"))
    if not relationships:
        return None
    frame = IntentFrame("appworld_venmo_add_friends_by_relationships")
    frame.set_slot("relationships", relationships, source="regex")
    return frame


def compile_delete_phone_spam_messages(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.search(
        r"All phone text messages and voice messages from (?P<phone>\d+) are spam, delete them\.?",
        raw_request,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_delete_phone_spam_messages")
    frame.set_slot("phone_number", match.group("phone"), source="regex")
    return frame


def compile_delete_gmail_empty_drafts(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Delete all my Gmail drafts that have empty subject (?P<joiner>and|or) body\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_delete_gmail_empty_drafts")
    condition = "both" if match.group("joiner").lower() == "and" else "either"
    frame.set_slot("condition", condition, source="regex")
    return frame


def compile_gmail_send_future_scheduled_drafts_now(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r"Send all my future-scheduled emails on Gmail right away\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    return IntentFrame("appworld_gmail_send_future_scheduled_drafts_now")


def compile_gmail_amazon_promo_codes_answer(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r"Find all Amazon promo codes from my Gmail account, including spam and archived emails, "
        r"and give it to me in a comma-separated list\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    return IntentFrame("appworld_gmail_amazon_promo_codes_answer")


def compile_gmail_count_threads(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"How many (?:(?P<label>priority-[123]) )?(?P<state>read|unread) email threads "
        r"are in my Gmail (?P<mailbox>inbox|outbox)\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_gmail_count_threads")
    frame.set_slot("mailbox", match.group("mailbox").lower(), source="regex")
    frame.set_slot("read_state", match.group("state").lower(), source="regex")
    label = match.group("label")
    if label:
        frame.set_slot("label", label.lower(), source="regex", required=False)
    return frame


def compile_gmail_schedule_resignation_draft(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'I have drafted my resignation email on Gmail\. Attach "(?P<path>~\/documents\/work\/[^"]+\.pdf)" '
        r"from my file system to it and schedule it to be sent to my manager on "
        r"(?P<week_ref>next|next to next) (?P<weekday>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) "
        r"at (?P<hour>\d{1,2}) am\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_gmail_schedule_resignation_draft")
    week_ref = match.group("week_ref").lower()
    frame.set_slot("attachment_path", match.group("path").strip(), source="regex")
    frame.set_slot("weekday", match.group("weekday").lower(), source="regex")
    frame.set_slot("week_offset", 2 if week_ref == "next to next" else 1, source="regex")
    frame.set_slot("hour", int(match.group("hour")), source="regex")
    return frame


def compile_gmail_thread_cleanup(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"(?P<action>Archive|Delete) all my read Gmail threads from inbox/outbox, except the ones that have some priority label (?P<joiner>and|or) (?:are also|are) starred\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_gmail_thread_cleanup")
    action = match.group("action").lower()
    exception_mode = "and" if match.group("joiner").lower() == "and" else "or"
    frame.set_slot("action", action, source="regex")
    frame.set_slot("exception_mode", exception_mode, source="regex")
    return frame


def compile_gmail_mark_threads_read_state_by_calendar_window(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Mark everything in my Gmail inbox and outbox (?P<window>before the last calendar month|in the current calendar month|before the current calendar year) as (?P<state>read|unread)\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_gmail_mark_threads_read_state_by_calendar_window")
    frame.set_slot("target_state", match.group("state").lower(), source="regex")
    window = match.group("window").lower().replace(" ", "_")
    frame.set_slot("window", window, source="regex")
    return frame


def compile_gmail_delete_archived_threads_by_calendar_window(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Delete all my archived gmail threads that are from (?P<window>before this calendar month|this calendar month|this or the last calendar month)\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_gmail_delete_archived_threads_by_calendar_window")
    window = match.group("window").lower().replace(" ", "_")
    frame.set_slot("window", window, source="regex")
    return frame


def compile_gmail_forward_anniversary_announcement_email(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"I just made an announcement about our company's anniversary celebration but I forgot (?P<email>[^\s]+@[^\s]+)\. Please forward the announcement email \(not the entire thread\) to them\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_gmail_forward_anniversary_announcement_email")
    frame.set_slot("recipient_email", match.group("email").strip(), source="regex")
    return frame


def compile_gmail_forward_caterer_bill_to_manager_with_note(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'I helped organize my company celebration recently\. The caterers have emailed me the bill\. '
        r'Forward it to my manager with a note prefixed to its body, "(?P<note>[^"]+)"\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_gmail_forward_caterer_bill_to_manager_with_note")
    frame.set_slot("note_prefix", match.group("note").strip(), source="regex")
    return frame


def compile_gmail_forward_roommate_bill_to_other_roommates(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'My roommate sent me "(?P<file_name>[\w.\-]+\.pdf)" on Gmail sometime ago\. '
        r"Please find it and forward that email to the rest of my roommates in a single email\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_gmail_forward_roommate_bill_to_other_roommates")
    frame.set_slot("file_name", match.group("file_name").strip(), source="regex")
    return frame


def compile_gmail_forward_trip_expenses_thread_with_attachment(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'(?P<sender>[A-Z][a-z]+), (?P<recipient>[A-Z][a-z]+) and I went on a trip recently\. '
        r'Yesterday, (?P=sender) emailed me their expenses in a pdf\. '
        r'Forward that thread to (?P=recipient) with an additional attachment of '
        r'"(?P<path>~/documents/personal/[^"]+\.pdf)" from my file system, and a note prefixed to its body, '
        r'"(?P<note>[^"]+)"\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_gmail_forward_trip_expenses_thread_with_attachment")
    frame.set_slot("sender_first_name", match.group("sender").strip(), source="regex")
    frame.set_slot("recipient_first_name", match.group("recipient").strip(), source="regex")
    frame.set_slot("attachment_path", match.group("path").strip(), source="regex")
    frame.set_slot("note_prefix", match.group("note").strip(), source="regex")
    return frame


def compile_gmail_reply_weekly_manager_tasks_by_star_state(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'My manager assigns me tasks at the beginning of every week with a subject starting with "(?P<prefix>[^"]+)"\. '
        r'At the end of each week, I reply to them "(?P<done>[^"]+)" or "(?P<not_done>[^"]+)"\. '
        r'For this week, I have starred the emails/tasks which I finished working on, and left the others unstarred\. '
        r'I am closing off this week now, please reply accordingly, and unstar those threads\. '
        r'I may have non-todo emails starred, please keep them as is\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_gmail_reply_weekly_manager_tasks_by_star_state")
    frame.set_slot("subject_prefix", match.group("prefix").strip(), source="regex")
    frame.set_slot("done_reply", match.group("done").strip(), source="regex")
    frame.set_slot("not_done_reply", match.group("not_done").strip(), source="regex")
    return frame


def compile_gmail_star_threads_by_relationship(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Star all my gmail threads with email/s from or to my (?P<relationship>[a-z]+) "
        r"and unstar the rest\. Ignore the archived threads\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    relationship = RELATION_ALIASES.get(
        match.group("relationship").lower(),
        match.group("relationship").lower(),
    )
    frame = IntentFrame("appworld_gmail_star_threads_by_relationship")
    frame.set_slot("relationship", relationship, source="regex")
    return frame


def compile_gmail_label_notification_threads_by_app(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r"Label all email threads in my Gmail inbox from notifications@<app>\.com "
        r"with the label of the respective app\. Ignore spam and archived ones\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    return IntentFrame("appworld_gmail_label_notification_threads_by_app")


def compile_gmail_relabel_priority_threads(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Relabel all my (?P<src1>priority-1|P1|pr-1) and (?P<src2>priority-2|P2|pr-2) "
        r"email threads with (?P<tgt1>priority-1|P1|pr-1) and (?P<tgt2>priority-2|P2|pr-2), "
        r"respectively, and remove all (?P<remove>priority-3|P3|pr-3) labels\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_gmail_relabel_priority_threads")
    frame.set_slot("source_label_1", match.group("src1"), source="regex")
    frame.set_slot("source_label_2", match.group("src2"), source="regex")
    frame.set_slot("target_label_1", match.group("tgt1"), source="regex")
    frame.set_slot("target_label_2", match.group("tgt2"), source="regex")
    frame.set_slot("remove_label", match.group("remove"), source="regex")
    return frame


def compile_gmail_attach_job_search_files_and_send(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"For my job search, I've drafted emails to all potential employers in the last "
        r"(?P<days_back>\d+) days\. Attach (?P<file_name>[\w.\-]+\.pdf) from my file "
        r"system to each of them\. If it's already attached, update it as I just made "
        r"some changes to it\. Then send the emails\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_gmail_attach_job_search_files_and_send")
    frame.set_slot("days_back", int(match.group("days_back")), source="regex")
    frame.set_slot("file_name", match.group("file_name"), source="regex")
    return frame


def compile_gmail_download_flight_ticket_attachment(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'Download the ticket for my flight to (?P<destination>[A-Za-z][A-Za-z ]*?) '
        r'this weekend from gmail into the "(?P<directory>~\/[^"]+)" folder of my file system\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    directory_path = match.group("directory").strip()
    if not directory_path.endswith("/"):
        directory_path += "/"
    frame = IntentFrame("appworld_gmail_download_flight_ticket_attachment")
    frame.set_slot("destination", match.group("destination").strip(), source="regex")
    frame.set_slot("directory_path", directory_path, source="regex")
    return frame


def compile_gmail_email_named_file_to_relationship(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Email the (?P<file_description>[a-z ]+) found in my file system to my (?P<relationship>[a-z]+)\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    relationship = RELATION_ALIASES.get(
        match.group("relationship").lower(),
        match.group("relationship").lower(),
    )
    frame = IntentFrame("appworld_gmail_email_named_file_to_relationship")
    frame.set_slot("file_description", match.group("file_description").strip().lower(), source="regex")
    frame.set_slot("relationship", relationship, source="regex")
    return frame


def compile_remove_expired_payment_cards(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r"Remove expired payment cards from all my app accounts that have payment cards\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    return IntentFrame("appworld_remove_expired_payment_cards")


def compile_spotify_playlist_from_workout_email(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'My workout partner has sent me some songs over email\. Make a new Spotify '
        r'playlist titled "(?P<title>[^"]+)" with those songs in it\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_playlist_from_workout_email")
    frame.set_slot("playlist_title", match.group("title").strip(), source="regex")
    return frame


def compile_spotify_reply_liked_song_recommendations_email(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'One of my (?P<relationship>friends|coworkers|roommates) has asked me for '
        r'song recommendations over email\. Reply them with a list of my liked songs '
        r'that are in my Spotify song library\. It should say "(?P<prefix>[^"]+)" '
        r'and then a comma-separated list of song titles\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    relationship = RELATION_ALIASES.get(
        match.group("relationship").lower(),
        match.group("relationship").lower(),
    )
    frame = IntentFrame("appworld_spotify_reply_liked_song_recommendations_email")
    frame.set_slot("relationship", relationship, source="regex")
    frame.set_slot("message_prefix", match.group("prefix").strip(), source="regex")
    return frame


def compile_spotify_update_song_recommendation_draft_from_library(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"(?P<name>[A-Z][A-Za-z]+) asked me for my song recommendations over email\. "
        r"I started drafting the response email off the top of my head\. "
        r"But then realized I can mine it from my Spotify account! "
        r"Please update the email draft with all of my liked songs that are in my song "
        r"or album library or any of my plalists\. Keep the existing format of the email, "
        r"making changes only to the song entries\. Once done, send the email\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_update_song_recommendation_draft_from_library")
    frame.set_slot("person_first_name", match.group("name").strip(), source="regex")
    return frame


def compile_bucket_list_status_update(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.search(
        r'Mark "(?P<item>[^"]+)" in my Bucket List Simple Note as (?P<status>done|not done)\.?',
        raw_request,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_bucket_list_status_update")
    frame.set_slot("item", match.group("item"), source="regex")
    frame.set_slot("done", match.group("status").lower() == "done", source="regex")
    return frame


def compile_simple_note_count_bucket_list_status(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"How many activities are (?P<status>completed|done|left to do) in my bucket list "
        r"as per my SimpleNote note\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    status = match.group("status").lower()
    frame = IntentFrame("appworld_simple_note_count_bucket_list_status")
    frame.set_slot("status", "todo" if "left" in status else "done", source="regex")
    return frame


def compile_simple_note_fill_liked_song_release_months(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if re.fullmatch(
        r"I keep a log of all my liked songs and respective artists in a note in simple_note\. "
        r"I want to add release month information for them as well\. "
        r"I have added it for the first few songs\. Add it for the rest\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return IntentFrame("appworld_simple_note_fill_liked_song_release_months")
    return None


def compile_spotify_follow_artists_by_genre_followers(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.search(
        r"Follow all the (?P<genre>[A-Za-z0-9_& -]+) artists on Spotify that have at least "
        r"(?P<count>\d+) followers\.?",
        raw_request,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_follow_artists_by_genre_followers")
    frame.set_slot("genre", match.group("genre").strip().lower(), source="regex")
    frame.set_slot("min_follower_count", int(match.group("count")), source="regex")
    return frame


def compile_spotify_add_artist_playcount_songs_to_queue(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Add all the songs from (?P<artist>.+?) that have been played over "
        r"(?P<count>\d+) times to my Spotify player queue\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_add_artist_playcount_songs_to_queue")
    frame.set_slot("artist_name", match.group("artist").strip(), source="regex")
    frame.set_slot("min_play_count", int(match.group("count")), source="regex")
    return frame


def compile_spotify_like_songs_from_followed_artists(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r"Like all the songs from the artists I follow on Spotify\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    return IntentFrame("appworld_spotify_like_songs_from_followed_artists")


def compile_spotify_public_liked_library_playlist_share(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Make a new public playlist from all my liked songs from my Spotify song, album "
        r"and playlist libraries, and share its URL with my (?P<relation>husband|wife) "
        r"via phone text message\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_public_liked_library_playlist_share")
    frame.set_slot("partner_relationship", match.group("relation").lower(), source="regex")
    return frame


def compile_spotify_sync_following_by_liked_song_artists(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    follow_match = re.search(
        r"Follow all the artists who have sung at least one song I have liked on Spotify\.?",
        raw_request,
        flags=re.IGNORECASE,
    )
    if follow_match:
        frame = IntentFrame("appworld_spotify_sync_following_by_liked_song_artists")
        frame.set_slot("operation", "follow_liked_song_artists", source="regex")
        return frame
    unfollow_match = re.search(
        r"Unfollow all the artists who have not sung even a single song I have liked on Spotify\.?",
        raw_request,
        flags=re.IGNORECASE,
    )
    if unfollow_match:
        frame = IntentFrame("appworld_spotify_sync_following_by_liked_song_artists")
        frame.set_slot("operation", "unfollow_non_liked_song_artists", source="regex")
        return frame
    return None


def compile_spotify_playlist_best_song_per_collection(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.search(
        r'Make me a Spotify playlist called "(?P<title>[^"]+)" containing only the '
        r'(?P<adjective>most-played|highest-rated) song from each '
        r'(?P<collection>album in my album library|of my playlists)\.?',
        raw_request,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    collection = match.group("collection").lower()
    metric = "play_count" if match.group("adjective").lower() == "most-played" else "rating"
    collection_type = "album_library" if "album" in collection else "playlist_library"
    frame = IntentFrame("appworld_spotify_playlist_best_song_per_collection")
    frame.set_slot("playlist_title", match.group("title"), source="regex")
    frame.set_slot("song_metric", metric, source="regex")
    frame.set_slot("collection_type", collection_type, source="regex")
    return frame


def compile_spotify_playlist_from_recent_simple_note(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.search(
        r'I jotted down some songs in Simple[ _]?Note recently\. '
        r'Make a playlist titled "(?P<title>[^"]+)" out of it\.?',
        raw_request,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_playlist_from_recent_simple_note")
    frame.set_slot("playlist_title", match.group("title"), source="regex")
    return frame


def compile_spotify_append_most_common_playlist_genre(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r'Update all my Spotify playlist titles with the most common song genre in that playlist '
        r'in this format: "<original_title> \| <most_common_genre>"\. Replace '
        r"<original_title> and <most_common_genre> with the actual values\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    return IntentFrame("appworld_spotify_append_most_common_playlist_genre")


def compile_spotify_like_all_library_items(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r"Like all the songs and albums in my Spotify song and album library, respectively, that I have not liked yet\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    return IntentFrame("appworld_spotify_like_all_library_items")


def compile_spotify_download_liked_library_songs(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Download all the songs from my Spotify (?P<collection>playlists|song library|album library) that I have liked\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    collection = match.group("collection").lower()
    if collection == "playlists":
        collection_type = "playlist_library"
    elif collection == "song library":
        collection_type = "song_library"
    else:
        collection_type = "album_library"
    frame = IntentFrame("appworld_spotify_download_liked_library_songs")
    frame.set_slot("collection_type", collection_type, source="regex")
    return frame


def compile_spotify_rate_library_songs_by_liked_status(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Give a (?P<rating>[1-5])-star rating to all songs in my Spotify "
        r"(?P<collection>playlists|song library|album library) which I have "
        r"(?P<liked_status>liked|not liked)\. If I have already rated it "
        r"(?P<direction>lower|higher), (?P<change_type>increase|decrease) it to "
        r"(?P=rating)\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    collection = match.group("collection").lower()
    if collection == "playlists":
        collection_type = "playlist_library"
    elif collection == "song library":
        collection_type = "song_library"
    else:
        collection_type = "album_library"
    liked_status = match.group("liked_status").lower()
    frame = IntentFrame("appworld_spotify_rate_library_songs_by_liked_status")
    frame.set_slot("collection_type", collection_type, source="regex")
    frame.set_slot("liked_filter", "not_liked" if liked_status == "not liked" else "liked", source="regex")
    frame.set_slot("target_rating", int(match.group("rating")), source="regex")
    return frame


def compile_spotify_follow_artists_from_liked_songs_and_albums(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r"Follow artists of all the songs and albums I have ever liked on Spotify\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    return IntentFrame("appworld_spotify_follow_artists_from_liked_songs_and_albums")


def compile_spotify_follow_playlist_song_artists_by_genre(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Follow all artists of all (?P<genre>[A-Za-z0-9_& -]+)-genre songs in any of my playlists on Spotify\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_follow_playlist_song_artists_by_genre")
    frame.set_slot("genre", match.group("genre").strip().lower(), source="regex")
    return frame


def compile_phone_update_wake_alarm_snooze(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Set my (?P<day_type>weekday|weekend) wake up alarm snooze to "
        r"(?P<snooze_minutes>\d+) minutes\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_phone_update_wake_alarm_snooze")
    frame.set_slot("day_type", match.group("day_type").lower(), source="regex")
    frame.set_slot("snooze_minutes", int(match.group("snooze_minutes")), source="regex")
    return frame


def compile_spotify_top_played_genre_titles(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Give me a comma-separated list of top (?P<limit>\d+) most played "
        r"(?P<genre>[A-Za-z0-9_& -]+) song titles from across my Spotify song, "
        r"album and playlist libraries\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_top_played_genre_titles")
    frame.set_slot("genre", match.group("genre").strip().lower(), source="regex")
    frame.set_slot("limit", int(match.group("limit")), source="regex")
    return frame


def compile_spotify_count_unique_library_songs(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r"How many unique songs are there across my Spotify song library, albums "
        r"library and all playlists\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    return IntentFrame("appworld_spotify_count_unique_library_songs")


def compile_venmo_pay_grocery_from_text_and_notify(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'(?P<first_name>[A-Z][A-Za-z]+) paid for my grocery recently as my payment '
        r'cards were not working at the time\. Send them the owed money with a '
        r'description note "(?P<note>[^"]+)" as per my phone text conversation, '
        r'and then send them a phone text message, "(?P<message>[^"]+)"\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_venmo_pay_grocery_from_text_and_notify")
    frame.set_slot("person_first_name", match.group("first_name"), source="regex")
    frame.set_slot("note", match.group("note"), source="regex")
    frame.set_slot("message", match.group("message"), source="regex")
    return frame


def compile_spotify_count_recent_release_library_songs(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    stripped = raw_request.strip()
    if re.fullmatch(
        r"How many songs from across my spotify song and album libraries were "
        r"released in this or last year\?",
        stripped,
        flags=re.IGNORECASE,
    ):
        frame = IntentFrame("appworld_spotify_count_recent_release_library_songs")
        frame.set_slot("years_back", 1, source="regex")
        frame.set_slot("include_current_year", True, source="regex")
        return frame
    if re.fullmatch(
        r"How many songs from across my spotify song and album libraries were "
        r"released in this year\?",
        stripped,
        flags=re.IGNORECASE,
    ):
        frame = IntentFrame("appworld_spotify_count_recent_release_library_songs")
        frame.set_slot("years_back", 0, source="regex")
        frame.set_slot("include_current_year", True, source="regex")
        return frame
    if re.fullmatch(
        r"How many songs from across my spotify song and album libraries were "
        r"released before this year\?",
        stripped,
        flags=re.IGNORECASE,
    ):
        frame = IntentFrame("appworld_spotify_count_recent_release_library_songs")
        frame.set_slot("years_back", -1, source="regex")
        frame.set_slot("include_current_year", False, source="regex")
        return frame
    return None


def compile_spotify_navigate_until_artist(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Keep going to the (?P<direction>previous|next) song on Spotify until you reach a "
        r"song by (?P<artist_name>[^.]+)\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_navigate_until_artist")
    frame.set_slot("direction", match.group("direction").lower(), source="regex")
    frame.set_slot("artist_name", match.group("artist_name").strip(), source="regex")
    return frame


def compile_venmo_reset_friends_to_phone_friends(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r"Reset friends on venmo to be the same as my friends in my phone\. "
        r"Befriend and unfriend as needed\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    return IntentFrame("appworld_venmo_reset_friends_to_phone_friends")


def compile_spotify_filter_queue_by_liked_status(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Remove all the songs that I have (?P<negation>not )?liked from my Spotify queue, "
        r"and then start the player\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_filter_queue_by_liked_status")
    frame.set_slot(
        "remove_filter",
        "not_liked" if match.group("negation") else "liked",
        source="regex",
    )
    return frame


def compile_spotify_navigate_until_private_status(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Keep going to the (?P<direction>previous|next) song on Spotify until you "
        r"reach (?:a (?P<direct_status>liked|downloaded) song|a song I have already "
        r"(?P<already_status>liked|downloaded))\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_navigate_until_private_status")
    frame.set_slot("direction", match.group("direction").lower(), source="regex")
    status_property = match.group("direct_status") or match.group("already_status")
    frame.set_slot("status_property", status_property.lower(), source="regex")
    return frame


def compile_spotify_play_offline_downloaded_collection(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"I am going for a (?P<duration>15-minute|20-minute|half-hour) "
        r"(?:drive|walk) without internet\. Play (?:an?|the) (?P<collection>album|playlist) "
        r"from my Spotify library that already has enough downloaded songs for it, "
        r"so I do not have to repeat\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    duration = match.group("duration").lower()
    required_minutes = 30 if duration == "half-hour" else int(duration.split("-", 1)[0])
    frame = IntentFrame("appworld_spotify_play_offline_downloaded_collection")
    frame.set_slot("collection_type", match.group("collection").lower(), source="regex")
    frame.set_slot("required_minutes", required_minutes, source="regex")
    return frame


def compile_venmo_sum_month_transactions(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"How much money have I (?P<direction>sent|received|sent to or received) "
        r"(?:(?:to|from) others )?on venmo this month so far\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    direction = match.group("direction").lower().replace(" to or ", "_or_")
    frame = IntentFrame("appworld_venmo_sum_month_transactions")
    frame.set_slot("direction", direction, source="regex")
    return frame


def compile_venmo_sum_recent_received_requests(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"How much money have I been requested on Venmo in the last "
        r"(?P<days>\d+) days \(including today\)\?\s*",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_venmo_sum_recent_received_requests")
    frame.set_slot("days", int(match.group("days")), source="regex")
    return frame


def compile_spotify_reset_queue_with_recommendations(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r"Reset my Spotify queue with all of its recommended songs, shuffle it, and play it\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    return IntentFrame("appworld_spotify_reset_queue_with_recommendations")


def compile_spotify_archive_playlist_songs_from_file(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'Go through all my Spotify playlists and remove all the songs from them that '
        r'are in "(?P<source_file_path>~\/[^"]+\.txt)" from my file system and put '
        r'them in a new playlist named "(?P<playlist_title>[^"]+)"\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_archive_playlist_songs_from_file")
    frame.set_slot("source_file_path", match.group("source_file_path"), source="regex")
    frame.set_slot("playlist_title", match.group("playlist_title"), source="regex")
    return frame


def compile_simple_note_import_markdown_files(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'Import markdown notes in the "(?P<source_directory>~\/[^"]+\/)" directory of my '
        r"file system to my Simple Note account\. Each markdown file should become a "
        r"separate note in the Simple Note account\. The title of each note should be "
        r"taken from the name of the source file \(excluding the directory path and file "
        r"extension\), replacing underscores in it with blank spaces\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_simple_note_import_markdown_files")
    frame.set_slot("source_directory", match.group("source_directory"), source="regex")
    return frame


def compile_simple_note_workout_duration(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"How long (?:is|was) my workout duration (?P<day_ref>today|yesterday|on sundays), "
        r"in minutes, as per my plan in Simple Note\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_simple_note_workout_duration")
    frame.set_slot("day_ref", match.group("day_ref").lower().replace("on ", ""), source="regex")
    return frame


def compile_simple_note_random_quote(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Give me a random (?P<quote_type>funny|inspirational|movie) quote from my "
        r"SimpleNote note about it\. Just the quote, nothing else\.",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_simple_note_random_quote")
    frame.set_slot("quote_type", match.group("quote_type").lower(), source="regex")
    return frame


def compile_simple_note_longest_habit_streak(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"What is my longest (?P<habit>[a-z0-9-]+) habit streak, in number of days, "
        r"as per my Simple Note habit tracking logs\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    habit_key = match.group("habit").lower().replace("-", "_")
    frame = IntentFrame("appworld_simple_note_longest_habit_streak")
    frame.set_slot("habit_key", habit_key, source="regex")
    return frame


def compile_simple_note_add_today_habit_log(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    patterns = [
        (
            r"Add a new habit tracking log note for today in my Simple Note account\. "
            r"It should be the same as yesterday, except I had a good posture today\.",
            "practiced_good_posture",
            True,
        ),
        (
            r"Add a new habit tracking log note for today in my Simple Note account\. "
            r"It should be the same as yesterday, except I did not meditate today\.",
            "practiced_meditation",
            False,
        ),
        (
            r"Add a new habit tracking log note for today in my Simple Note account\. "
            r"It should be the same as yesterday, except I ate home-prepared meals today\.",
            "ate_homemade_meals",
            True,
        ),
    ]
    for pattern, habit_key, value in patterns:
        if re.fullmatch(pattern, raw_request.strip(), flags=re.IGNORECASE):
            frame = IntentFrame("appworld_simple_note_add_today_habit_log")
            frame.set_slot("habit_key", habit_key, source="regex")
            frame.set_slot("value", value, source="regex")
            return frame
    return None


def compile_simple_note_export_habit_tracker_csv(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'I maintain my habit tracking logs in Simple Note\. Export it in '
        r'"(?P<destination_path>~\/[^"]+\.csv)" in my file system\. Its first header '
        r'column should be "date" and the rest should be correspond to the habits I '
        r'track as per my logs\. The rows for date column should be in yyyy-mm-dd '
        r'format and the rest should be yes or no as per my logs\. The rows should be '
        r'sorted in (?P<sort_order>ascending|descending) order of the date from top to '
        r'bottom, and habit columns as per their order in logs\.',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_simple_note_export_habit_tracker_csv")
    frame.set_slot("destination_path", match.group("destination_path"), source="regex")
    frame.set_slot("sort_order", match.group("sort_order").lower(), source="regex")
    return frame


def compile_simple_note_update_monthly_venmo_expense(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r"I maintain a log of my monthly venmo expense in SimpleNote note\. "
        r"Update it with an entry for this month\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    return IntentFrame("appworld_simple_note_update_monthly_venmo_expense")


def compile_splitwise_record_trip_expenses_from_simple_note(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"I went on a few trips each with some of my (?P<relationship>friends|coworkers)\. "
        r"My Simple Note has information on who owes whom what from each trip\. "
        r"I have already created Splitwise groups for the trips\. "
        r"Record the expenses accordingly in the respective groups\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_splitwise_record_trip_expenses_from_simple_note")
    frame.set_slot("relationship_type", match.group("relationship").lower(), source="regex")
    return frame


def compile_venmo_approve_roommate_requests_this_month(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r"Approve all venmo payment requests from my roommates from this calendar month\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    return IntentFrame("appworld_venmo_approve_roommate_requests_this_month")


def compile_file_delete_downloads_by_extension(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Delete all (?P<extension>\.[A-Za-z0-9]+) files from my file system "
        r"~\/downloads folder\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_file_delete_downloads_by_extension")
    frame.set_slot("extension", match.group("extension").lower(), source="regex")
    return frame


def compile_spotify_followed_artist_follower_extreme(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Who is the (?P<extreme>most|least) followed artist I follow on Spotify\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_followed_artist_follower_extreme")
    frame.set_slot("extreme", match.group("extreme").lower(), source="regex")
    return frame


def compile_spotify_liked_genre_extreme(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Songs of which genre have I liked the (?P<extreme>most|least) in my "
        r"Spotify (?P<collection>song library|album library|playlists)\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    collection = match.group("collection").lower()
    if collection == "song library":
        collection_type = "song_library"
    elif collection == "album library":
        collection_type = "album_library"
    else:
        collection_type = "playlist_library"
    frame = IntentFrame("appworld_spotify_liked_genre_extreme")
    frame.set_slot("extreme", match.group("extreme").lower(), source="regex")
    frame.set_slot("collection_type", collection_type, source="regex")
    return frame


def compile_spotify_playlist_artist_song_count_extreme(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Give me (?P<limit>\d+) comma-separated artist names with the "
        r"(?P<extreme>most|least) songs in my Spotify playlists\. If the same "
        r"song is present in multiple playlists, count it once\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_spotify_playlist_artist_song_count_extreme")
    frame.set_slot("limit", int(match.group("limit")), source="regex")
    frame.set_slot("extreme", match.group("extreme").lower(), source="regex")
    return frame


def compile_venmo_sum_year_bill_payments(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"How much have I paid in (?P<bill_type>phone|electricity|internet) bill "
        r"on venmo this year so far\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_venmo_sum_year_bill_payments")
    frame.set_slot("bill_type", match.group("bill_type").lower(), source="regex")
    return frame


def compile_venmo_friend_transaction_counterparties(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Befriend on Venmo anyone I have (?P<direction>sent or received|sent|received) "
        r"money (?P<suffix>from this month|to this month|this month)(?P<sync> and unfriend everyone else)?\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    direction = match.group("direction").lower().replace(" ", "_")
    if direction == "sent_or_received":
        direction = "sent_or_received"
    frame = IntentFrame("appworld_venmo_friend_transaction_counterparties")
    frame.set_slot("direction", direction, source="regex")
    frame.set_slot("sync_mode", "sync" if match.group("sync") else "add_only", source="regex")
    return frame


def compile_venmo_count_friends_since_month_start(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"How many venmo friends have I made since the start of "
        r"(?P<month>January|February|March|April|May|June|July|August|September|October|November|December) "
        r"(?P<year_ref>this year|last year)\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_venmo_count_friends_since_month_start")
    frame.set_slot("month", match.group("month").lower(), source="regex")
    frame.set_slot(
        "year_offset",
        0 if match.group("year_ref").lower() == "this year" else -1,
        source="regex",
    )
    return frame


def compile_spotify_play_released_year_from_collection(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Play any song released in (?P<year>\d{4}) from my Spotify "
        r"(?P<collection>song library|album library|playlists)\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    collection = match.group("collection").lower()
    if collection == "song library":
        collection_type = "song_library"
    elif collection == "album library":
        collection_type = "album_library"
    else:
        collection_type = "playlist_library"
    frame = IntentFrame("appworld_spotify_play_released_year_from_collection")
    frame.set_slot("release_year", int(match.group("year")), source="regex")
    frame.set_slot("collection_type", collection_type, source="regex")
    return frame


def compile_venmo_like_transactions_by_relationship_period(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Like all the venmo transactions of the ongoing (?P<period>year|month) "
        r"to and from my (?P<relations>.+?)\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_venmo_like_transactions_by_relationship_period")
    frame.set_slot("period", match.group("period").lower(), source="regex")
    frame.set_slot("relationships", extract_relationships(match.group("relations")), source="regex")
    return frame


def compile_venmo_manager_meal_total_from_social_feed(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"I went on (?P<meal>dinner|lunch) with my (?P<relations>.+?) yesterday at "
        r"(?P<venue>[^.]+)\. My manager paid for food and everyone venmoed them\. "
        r"Everyones' transactions except mine should be on my social feed\. My share "
        r"was \$(?P<share_amount>\d+(?:\.\d+)?)\. How much did my manager pay for "
        r"the others, including me, yesterday\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_venmo_manager_meal_total_from_social_feed")
    frame.set_slot("meal", match.group("meal").lower(), source="regex")
    frame.set_slot("relationships", extract_relationships(match.group("relations")), source="regex")
    frame.set_slot("venue", match.group("venue").strip(), source="regex")
    frame.set_slot("share_amount", float(match.group("share_amount")), source="regex")
    return frame


def compile_venmo_sum_transaction_likes(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"How many likes did all Venmo transactions, I (?P<direction>sent|received|sent or received) "
        r"this (?P<period>month|year), have in total\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_venmo_sum_transaction_likes")
    direction = match.group("direction").lower().replace(" ", "_")
    frame.set_slot("direction", direction, source="regex")
    frame.set_slot("period", match.group("period").lower(), source="regex")
    return frame


def compile_file_prefix_and_move_old_files(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'In my file system, add the prefix "(?P<prefix_format>YYYY[-_]MM[-_]DD[-_])" '
        r"to all file names in the (?P<source_directory>~\/[^ ]+\/) directory, based on "
        r"their creation dates, and then move all files not from this year to "
        r"(?P<destination_directory>~\/[^ ]+\/)\.",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_file_prefix_and_move_old_files")
    frame.set_slot("source_directory", match.group("source_directory"), source="regex")
    frame.set_slot("prefix_format", match.group("prefix_format"), source="regex")
    frame.set_slot("old_destination_directory", match.group("destination_directory"), source="regex")
    return frame


def compile_file_reorganize_dated_meeting_files(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'My work meeting files are available in the "(?P<source_directory>~\/[^"]+\/)" '
        r'directory in my file system\. Currently, they are organized as '
        r'"<date>__<file_name>\.<extension>"\. Reorganize them in this format, '
        r'"<file_name>/<date>\.<extension>"\.?',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_file_reorganize_dated_meeting_files")
    frame.set_slot("source_directory", match.group("source_directory"), source="regex")
    return frame


def compile_spotify_current_artist_followers(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r"How many people follow the artist of the currently playing song on Spotify\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    return IntentFrame("appworld_spotify_current_artist_followers")


def compile_simple_note_export_markdown(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r'Export all my Simple Note notes to "(?P<destination_directory>~\/[^"]+\/)" '
        r'directory in my file system\. The files should be named according to the note '
        r'title, replacing white space with "_", and the extension should be "\.md"\.',
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_simple_note_export_markdown")
    frame.set_slot("destination_directory", match.group("destination_directory"), source="regex")
    return frame


def compile_amazon_move_rating_filtered_products(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Move all products with (?P<comparison>under|over) "
        r"(?P<threshold>\d+(?:\.\d+)?) rating from my amazon "
        r"(?P<source>cart|wish list) to (?P<target>wish list|cart)\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_move_rating_filtered_products")
    frame.set_slot("source_container", normalize_amazon_container(match.group("source")), source="regex")
    frame.set_slot("target_container", normalize_amazon_container(match.group("target")), source="regex")
    frame.set_slot("comparison", match.group("comparison").lower(), source="regex")
    frame.set_slot("threshold_rating", float(match.group("threshold")), source="regex")
    return frame


def compile_amazon_move_product_type_between_saved_lists(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Move all (?P<product_type>.+?) from my amazon "
        r"(?P<source>cart|wish list) to (?P<target>wish list|cart)\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_move_product_type_between_saved_lists")
    frame.set_slot("source_container", normalize_amazon_container(match.group("source")), source="regex")
    frame.set_slot("target_container", normalize_amazon_container(match.group("target")), source="regex")
    frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
    return frame


def compile_amazon_order_product_type_from_saved_list(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Place an order for all (?P<product_type>.+?) in my amazon "
        r"(?P<source>cart|wish list)\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_order_product_type_from_saved_list")
    frame.set_slot("source_container", normalize_amazon_container(match.group("source")), source="regex")
    frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
    frame.set_slot("address_name", "Home", source="default")
    frame.set_slot("card_name", "", source="default")
    return frame


def compile_amazon_purchase_phone_recommendation(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Buy me a (?P<product_type>.+?) as (?P<first_name>[A-Z][A-Za-z'-]+) "
        r"recommended in (?:his|her|their) phone message\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_purchase_phone_recommendation")
    frame.set_slot("recommender_first_name", match.group("first_name"), source="regex")
    frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
    frame.set_slot("address_name", "Home", source="default")
    frame.set_slot("card_name", "", source="default")
    return frame


def compile_amazon_text_wishlist_itemized_costs(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Send an itemized list of my amazon wish list to my (?P<relationship>husband|wife|partner) via a phone text\. "
        r"The message should be a newline-separated list of '<product_name> => \$<total_price>'\. "
        r"Replace <total_price> with the price of the product times its quantity in the wish list, rounded to the nearest whole number, "
        r"and <product_name> with the product name\. Ignore potential tax or delivery fees\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_text_wishlist_itemized_costs")
    relationship = RELATION_ALIASES.get(match.group("relationship").lower(), match.group("relationship").lower())
    frame.set_slot("relationship", relationship, source="regex")
    return frame


def compile_amazon_answer_cart_wishlist_total(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r"How much does my amazon cart and wishlist cost in total, ignoring potential tax and delivery fees\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    return IntentFrame("appworld_amazon_answer_cart_wishlist_total")


def compile_amazon_order_saved_collections(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    text = raw_request.strip()
    match = re.fullmatch(
        r"Buy everything on my amazon wishlist, and have it delivered to my (?P<address>home|work) address\.?",
        text,
        flags=re.IGNORECASE,
    )
    containers = ["wish_list"]
    if not match:
        match = re.fullmatch(
            r"Place an order for everything in my amazon cart and wishlist for my (?P<address>home|work) address\.?",
            text,
            flags=re.IGNORECASE,
        )
        containers = ["cart", "wish_list"]
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_order_saved_collections")
    frame.set_slot("containers", containers, source="regex")
    frame.set_slot("address_name", match.group("address").title(), source="regex")
    frame.set_slot("card_name", "", source="default")
    return frame


def compile_amazon_cart_buy_cheapest_per_type_move_rest(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    if not re.fullmatch(
        r"I have a few things in my amazon cart\. For each product type in it, "
        r"buy the cheapest product and move the rest to the wish list\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    ):
        return None
    frame = IntentFrame("appworld_amazon_cart_buy_cheapest_per_type_move_rest")
    frame.set_slot("address_name", "Home", source="default")
    frame.set_slot("card_name", "", source="default")
    return frame


def parse_amazon_exact_order_items(items_text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    pattern = re.compile(
        r"(?P<quantity>\d+)\s+quantity\s+of\s+'(?P<product_name>[^']+)'",
        flags=re.IGNORECASE,
    )
    position = 0
    for match in pattern.finditer(items_text):
        separator = items_text[position:match.start()].strip()
        if separator and not re.fullmatch(r",|\band\b|,\s*\band\b", separator, flags=re.IGNORECASE):
            return []
        quantity = int(match.group("quantity"))
        product_name = compact_text(match.group("product_name"))
        if quantity < 1 or not product_name:
            return []
        items.append({"product_name": product_name, "quantity": quantity})
        position = match.end()
    trailing = items_text[position:].strip()
    if trailing:
        return []
    return items


def compile_amazon_order_exact_products_restore_cart(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Place an amazon order for (?P<items>.+?), and have it delivered to my "
        r"(?P<address>home|work)\. Use (?P<card_name>[A-Za-z0-9 .&'-]+?) payment card "
        r"if it's already in my account, otherwise use what I have in it\. "
        r"Also, I have important things in my cart, so revert its state to as it is now "
        r"after the order\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    items = parse_amazon_exact_order_items(match.group("items"))
    if not items:
        return None
    frame = IntentFrame("appworld_amazon_order_exact_products_restore_cart")
    frame.set_slot("items", items, source="regex")
    frame.set_slot("address_name", match.group("address").title(), source="regex")
    frame.set_slot("preferred_card_name", compact_text(match.group("card_name")), source="regex")
    frame.set_slot("restore_cart", True, source="regex")
    return frame


def compile_amazon_order_product_and_archive_receipt(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Order (?P<quantity>one|\d+) (?P<product_name>.+?) on Amazon for "
        r"(?P<address>home|work) delivery\. Save the receipt in the "
        r"\"(?P<bills_root>~/bills/)\" folder\. I keep my receipts well-organized "
        r"by category in that folder\. So make sure the file location and name are "
        r"as per the existing organization\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    quantity_text = match.group("quantity").strip().lower()
    quantity = 1 if quantity_text == "one" else int(quantity_text)
    product_name = compact_text(match.group("product_name"))
    if quantity < 1 or not product_name:
        return None
    frame = IntentFrame("appworld_amazon_order_product_and_archive_receipt")
    frame.set_slot("product_name", product_name, source="regex")
    frame.set_slot("quantity", quantity, source="regex")
    frame.set_slot("address_name", match.group("address").title(), source="regex")
    frame.set_slot("bills_root", match.group("bills_root"), source="regex")
    return frame


def compile_amazon_download_all_order_receipts(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Download receipts of all my amazon orders in \"(?P<directory>~/[^\"]+/)\" "
        r"folder in my file system\. Name the files in the format, "
        r"\"(?P<file_format>[^\"]+?)\"\. Replace <order_id> with the actual order id, "
        r"and yyyy-mm-dd with the date when the order was placed\. You should be able "
        r"to find receipts from order confirmation emails\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_download_all_order_receipts")
    frame.set_slot("directory_path", match.group("directory"), source="regex")
    frame.set_slot("file_format", match.group("file_format"), source="regex")
    return frame


def compile_amazon_order_trip_supplies_by_deadline(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"I am going on a trip with friends this (?P<trip_day>Saturday|Sunday)\. "
        r"For it, I need (?P<quantity>\d+) (?P<first_product_type>.+?) and "
        r"(?P<second_product_type>.+?), each\. Place an amazon order for them, "
        r"making sure everything reaches my home by the end of the day before I leave\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    quantity = int(match.group("quantity"))
    product_types = [
        normalize_amazon_product_type(match.group("first_product_type")),
        normalize_amazon_product_type(match.group("second_product_type")),
    ]
    if quantity < 1 or any(not product_type for product_type in product_types):
        return None
    frame = IntentFrame("appworld_amazon_order_trip_supplies_by_deadline")
    frame.set_slot("product_types", product_types, source="regex")
    frame.set_slot("quantity", quantity, source="regex")
    frame.set_slot("trip_day", match.group("trip_day").lower(), source="regex")
    frame.set_slot("address_name", "Home", source="default")
    frame.set_slot("card_name", "", source="default")
    return frame


def compile_amazon_return_recent_orders(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Initiate returns via (?P<deliverer>[A-Za-z0-9 .&'-]+?) for everything in my last (?P<count>\d+) amazon order\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_return_recent_orders")
    frame.set_slot("order_count", int(match.group("count")), source="regex")
    frame.set_slot("deliverer_name", compact_text(match.group("deliverer")), source="regex")
    return frame


def compile_amazon_return_same_product_except_size_this_week(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"I bought a few (?P<product_name>.+?) on amazon this week\. "
        r"But only the one in (?P<keep_size>extra-large|extra-small|large|small|medium) size fits me well\. "
        r"Initiate a return for the rest\. Prefer (?P<deliverer>UPS|USPS|FedEx) as a deliverer, if available\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_return_same_product_except_size_this_week")
    frame.set_slot("product_name", compact_text(match.group("product_name")), source="regex")
    frame.set_slot("keep_size", compact_text(match.group("keep_size")).lower(), source="regex")
    frame.set_slot("deliverer_name", compact_text(match.group("deliverer")), source="regex")
    return frame


def compile_amazon_buy_last_product_variants(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"I liked that last (?P<product_type>t-shirt|sweater) I bought on amazon\. "
        r"Place a new order for the same in (?P<color_one>[A-Za-z -]+) and (?P<color_two>[A-Za-z -]+), one each\. "
        r"Make sure to get the size as per that order, and have them delivered (?P<address>home|work)\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_buy_last_product_variants")
    frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
    frame.set_slot(
        "colors",
        [
            compact_text(match.group("color_one")).lower(),
            compact_text(match.group("color_two")).lower(),
        ],
        source="regex",
    )
    frame.set_slot("address_name", match.group("address").title(), source="regex")
    frame.set_slot("card_name", "", source="default")
    return frame


def compile_amazon_replace_last_product_adjacent_size(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"The last (?P<product_type>.+?) I bought on Amazon is a bit too (?P<fit>small|large) for me\. "
        r"Initiate a return for it, and buy a replacement of the same in the next (?P<direction>larger|smaller) size\. "
        r"If it's available now in (?P<preferred_color>[A-Za-z -]+), prefer it, otherwise go with the same color\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    fit = match.group("fit").lower()
    direction = match.group("direction").lower()
    if (fit == "small" and direction != "larger") or (fit == "large" and direction != "smaller"):
        return None
    frame = IntentFrame("appworld_amazon_replace_last_product_adjacent_size")
    frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
    frame.set_slot("size_direction", direction, source="regex")
    frame.set_slot("preferred_color", compact_text(match.group("preferred_color")).lower(), source="regex")
    frame.set_slot("address_name", "Home", source="default")
    frame.set_slot("card_name", "", source="default")
    return frame


def compile_amazon_order_preferred_color_size_product(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Make an order for (?P<quantity>\d+|one|two|three|four|five) same-colored (?P<product_name>.+?) "
        r"in (?P<relative_size>extra-small|small|medium|large|extra-large) size on Amazon\. "
        r"My color preference is, (?P<preferences>[A-Za-z0-9 >-]+)\. "
        r"Pick the most preferred color that is available\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    preferences = [
        compact_text(part).lower()
        for part in match.group("preferences").split(">")
        if part.strip()
    ]
    if not preferences:
        return None
    quantity_text = match.group("quantity").lower()
    quantity_by_word = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
    }
    quantity = quantity_by_word[quantity_text] if quantity_text in quantity_by_word else int(quantity_text)
    frame = IntentFrame("appworld_amazon_order_preferred_color_size_product")
    frame.set_slot("product_name", compact_text(match.group("product_name")), source="regex")
    frame.set_slot("relative_size", compact_text(match.group("relative_size")).lower(), source="regex")
    frame.set_slot("color_preferences", preferences, source="regex")
    frame.set_slot("quantity", quantity, source="regex")
    frame.set_slot("address_name", "Home", source="default")
    frame.set_slot("card_name", "", source="default")
    return frame


def compile_amazon_order_filtered_product(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    text = raw_request.strip()
    match = re.fullmatch(
        r"Buy me a (?P<product_type>.+?) on amazon within \$(?P<max_price>\d+(?:\.\d+)?) "
        r"\(excluding tax\) and have it delivered to my (?P<address>home|work) address\.?",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        frame = IntentFrame("appworld_amazon_order_filtered_product")
        frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
        frame.set_slot("min_price", None, source="default", required=False)
        frame.set_slot("max_price", float(match.group("max_price")), source="regex", required=False)
        frame.set_slot("min_product_rating", None, source="default", required=False)
        frame.set_slot("min_product_reviews", None, source="default", required=False)
        frame.set_slot("min_seller_rating", None, source="default", required=False)
        frame.set_slot("price_bounds_inclusive", False, source="default", required=False)
        frame.set_slot("rating_threshold_inclusive", False, source="default", required=False)
        frame.set_slot("prefer_highest_seller", False, source="default", required=False)
        frame.set_slot("source_container", "search", source="default", required=False)
        frame.set_slot("prior_ordered_sellers_only", False, source="default", required=False)
        frame.set_slot("max_length", None, source="default", required=False)
        frame.set_slot("max_width", None, source="default", required=False)
        frame.set_slot("quantity_relationship", "", source="default", required=False)
        frame.set_slot("allow_mixed_products", True, source="default", required=False)
        frame.set_slot("quantity", 1, source="default")
        frame.set_slot("address_name", match.group("address").title(), source="regex")
        frame.set_slot("card_name", "", source="default")
        return frame
    match = re.fullmatch(
        r"Buy me a (?P<product_type>.+?) from amazon within \$(?P<max_price>\d+(?:\.\d+)?) "
        r"\(excluding tax\)\. Only trust sellers I have ordered from in the past\.?",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        frame = IntentFrame("appworld_amazon_order_filtered_product")
        frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
        frame.set_slot("min_price", None, source="default", required=False)
        frame.set_slot("max_price", float(match.group("max_price")), source="regex", required=False)
        frame.set_slot("min_product_rating", None, source="default", required=False)
        frame.set_slot("min_product_reviews", None, source="default", required=False)
        frame.set_slot("min_seller_rating", None, source="default", required=False)
        frame.set_slot("price_bounds_inclusive", False, source="default", required=False)
        frame.set_slot("rating_threshold_inclusive", False, source="default", required=False)
        frame.set_slot("prefer_highest_seller", False, source="default", required=False)
        frame.set_slot("source_container", "search", source="default", required=False)
        frame.set_slot("prior_ordered_sellers_only", True, source="regex", required=False)
        frame.set_slot("max_length", None, source="default", required=False)
        frame.set_slot("max_width", None, source="default", required=False)
        frame.set_slot("quantity_relationship", "", source="default", required=False)
        frame.set_slot("allow_mixed_products", True, source="default", required=False)
        frame.set_slot("quantity", 1, source="default")
        frame.set_slot("address_name", "Home", source="default")
        frame.set_slot("card_name", "", source="default")
        return frame
    match = re.fullmatch(
        r"Buy me a (?P<product_type>.+?) on amazon under \$(?P<max_price>\d+(?:\.\d+)?) "
        r"\(excluding tax\), over (?P<min_rating>\d+(?:\.\d+)?) rating, and over "
        r"(?P<min_reviews>\d+) reviews, and have it delivered to (?P<address>home|work) address\.?",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        frame = IntentFrame("appworld_amazon_order_filtered_product")
        frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
        frame.set_slot("min_price", None, source="default", required=False)
        frame.set_slot("max_price", float(match.group("max_price")), source="regex", required=False)
        frame.set_slot("min_product_rating", float(match.group("min_rating")), source="regex", required=False)
        frame.set_slot("min_product_reviews", int(match.group("min_reviews")), source="regex", required=False)
        frame.set_slot("min_seller_rating", None, source="default", required=False)
        frame.set_slot("price_bounds_inclusive", False, source="default", required=False)
        frame.set_slot("rating_threshold_inclusive", False, source="default", required=False)
        frame.set_slot("prefer_highest_seller", False, source="default", required=False)
        frame.set_slot("source_container", "search", source="default", required=False)
        frame.set_slot("prior_ordered_sellers_only", False, source="default", required=False)
        frame.set_slot("max_length", None, source="default", required=False)
        frame.set_slot("max_width", None, source="default", required=False)
        frame.set_slot("quantity_relationship", "", source="default", required=False)
        frame.set_slot("allow_mixed_products", True, source="default", required=False)
        frame.set_slot("quantity", 1, source="default")
        frame.set_slot("address_name", match.group("address").title(), source="regex")
        frame.set_slot("card_name", "", source="default")
        return frame
    match = re.fullmatch(
        r"Buy me a (?P<product_type>.+?) on amazon with a rating over "
        r"(?P<min_rating>\d+(?:\.\d+)?) and have it delivered to my "
        r"(?P<address>home|work) address\.?",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        frame = IntentFrame("appworld_amazon_order_filtered_product")
        frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
        frame.set_slot("min_price", None, source="default", required=False)
        frame.set_slot("max_price", None, source="default", required=False)
        frame.set_slot("min_product_rating", float(match.group("min_rating")), source="regex", required=False)
        frame.set_slot("min_product_reviews", None, source="default", required=False)
        frame.set_slot("min_seller_rating", None, source="default", required=False)
        frame.set_slot("price_bounds_inclusive", False, source="default", required=False)
        frame.set_slot("rating_threshold_inclusive", False, source="default", required=False)
        frame.set_slot("prefer_highest_seller", False, source="default", required=False)
        frame.set_slot("source_container", "search", source="default", required=False)
        frame.set_slot("prior_ordered_sellers_only", False, source="default", required=False)
        frame.set_slot("max_length", None, source="default", required=False)
        frame.set_slot("max_width", None, source="default", required=False)
        frame.set_slot("quantity_relationship", "", source="default", required=False)
        frame.set_slot("allow_mixed_products", True, source="default", required=False)
        frame.set_slot("quantity", 1, source="default")
        frame.set_slot("address_name", match.group("address").title(), source="regex")
        frame.set_slot("card_name", "", source="default")
        return frame
    match = re.fullmatch(
        r"Buy me (?P<quantity>\d+) (?P<product_type>.+?) on amazon of at least "
        r"(?P<min_product_rating>\d+(?:\.\d+)?) product rating and "
        r"(?P<min_seller_rating>\d+(?:\.\d+)?) seller rating for my "
        r"(?P<address>home|work) address\. They do not have to be identical\.?",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        frame = IntentFrame("appworld_amazon_order_filtered_product")
        frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
        frame.set_slot("min_price", None, source="default", required=False)
        frame.set_slot("max_price", None, source="default", required=False)
        frame.set_slot("min_product_rating", float(match.group("min_product_rating")), source="regex", required=False)
        frame.set_slot("min_product_reviews", None, source="default", required=False)
        frame.set_slot("min_seller_rating", float(match.group("min_seller_rating")), source="regex", required=False)
        frame.set_slot("price_bounds_inclusive", False, source="default", required=False)
        frame.set_slot("rating_threshold_inclusive", True, source="regex", required=False)
        frame.set_slot("prefer_highest_seller", False, source="default", required=False)
        frame.set_slot("source_container", "search", source="default", required=False)
        frame.set_slot("prior_ordered_sellers_only", False, source="default", required=False)
        frame.set_slot("max_length", None, source="default", required=False)
        frame.set_slot("max_width", None, source="default", required=False)
        frame.set_slot("quantity_relationship", "", source="default", required=False)
        frame.set_slot("allow_mixed_products", True, source="default", required=False)
        frame.set_slot("quantity", int(match.group("quantity")), source="regex")
        frame.set_slot("address_name", match.group("address").title(), source="regex")
        frame.set_slot("card_name", "", source="default")
        return frame
    match = re.fullmatch(
        r"Buy me a (?P<product_type>.+?) on amazon from its highest-rated seller "
        r"using my (?P<card_name>.+?) card for my (?P<address>home|work) address\.?",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        frame = IntentFrame("appworld_amazon_order_filtered_product")
        frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
        frame.set_slot("min_price", None, source="default", required=False)
        frame.set_slot("max_price", None, source="default", required=False)
        frame.set_slot("min_product_rating", None, source="default", required=False)
        frame.set_slot("min_product_reviews", None, source="default", required=False)
        frame.set_slot("min_seller_rating", None, source="default", required=False)
        frame.set_slot("price_bounds_inclusive", False, source="default", required=False)
        frame.set_slot("rating_threshold_inclusive", True, source="default", required=False)
        frame.set_slot("prefer_highest_seller", True, source="regex", required=False)
        frame.set_slot("source_container", "search", source="default", required=False)
        frame.set_slot("prior_ordered_sellers_only", False, source="default", required=False)
        frame.set_slot("max_length", None, source="default", required=False)
        frame.set_slot("max_width", None, source="default", required=False)
        frame.set_slot("quantity_relationship", "", source="default", required=False)
        frame.set_slot("allow_mixed_products", True, source="default", required=False)
        frame.set_slot("quantity", 1, source="default")
        frame.set_slot("address_name", match.group("address").title(), source="regex")
        frame.set_slot("card_name", compact_text(match.group("card_name")).lower(), source="regex")
        return frame
    match = re.fullmatch(
        r"Buy me a (?P<product_type>.+?) on amazon with at least "
        r"(?P<min_seller_rating>\d+(?:\.\d+)?) seller rating that will fit in my .+? "
        r"of (?P<max_length>\d+(?:\.\d+)?)X(?P<max_width>\d+(?:\.\d+)?) "
        r"\(LxW\) inches\.?",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        frame = IntentFrame("appworld_amazon_order_filtered_product")
        frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
        frame.set_slot("min_price", None, source="default", required=False)
        frame.set_slot("max_price", None, source="default", required=False)
        frame.set_slot("min_product_rating", None, source="default", required=False)
        frame.set_slot("min_product_reviews", None, source="default", required=False)
        frame.set_slot("min_seller_rating", float(match.group("min_seller_rating")), source="regex", required=False)
        frame.set_slot("price_bounds_inclusive", False, source="default", required=False)
        frame.set_slot("rating_threshold_inclusive", True, source="regex", required=False)
        frame.set_slot("prefer_highest_seller", False, source="default", required=False)
        frame.set_slot("source_container", "search", source="default", required=False)
        frame.set_slot("prior_ordered_sellers_only", False, source="default", required=False)
        frame.set_slot("max_length", float(match.group("max_length")), source="regex", required=False)
        frame.set_slot("max_width", float(match.group("max_width")), source="regex", required=False)
        frame.set_slot("quantity_relationship", "", source="default", required=False)
        frame.set_slot("allow_mixed_products", True, source="default", required=False)
        frame.set_slot("quantity", 1, source="default")
        frame.set_slot("address_name", "Home", source="default")
        frame.set_slot("card_name", "", source="default")
        return frame
    match = re.fullmatch(
        r"Buy me a (?P<product_type>.+?) from my amazon wishlist that will fit in my .+? "
        r"of (?P<max_length>\d+(?:\.\d+)?)X(?P<max_width>\d+(?:\.\d+)?) "
        r"\(LxW\) inches\.?",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        frame = IntentFrame("appworld_amazon_order_filtered_product")
        frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
        frame.set_slot("min_price", None, source="default", required=False)
        frame.set_slot("max_price", None, source="default", required=False)
        frame.set_slot("min_product_rating", None, source="default", required=False)
        frame.set_slot("min_product_reviews", None, source="default", required=False)
        frame.set_slot("min_seller_rating", None, source="default", required=False)
        frame.set_slot("price_bounds_inclusive", False, source="default", required=False)
        frame.set_slot("rating_threshold_inclusive", True, source="default", required=False)
        frame.set_slot("prefer_highest_seller", False, source="default", required=False)
        frame.set_slot("source_container", "wish_list", source="regex", required=False)
        frame.set_slot("prior_ordered_sellers_only", False, source="default", required=False)
        frame.set_slot("max_length", float(match.group("max_length")), source="regex", required=False)
        frame.set_slot("max_width", float(match.group("max_width")), source="regex", required=False)
        frame.set_slot("quantity_relationship", "", source="default", required=False)
        frame.set_slot("allow_mixed_products", True, source="default", required=False)
        frame.set_slot("quantity", 1, source="default")
        frame.set_slot("address_name", "Home", source="default")
        frame.set_slot("card_name", "", source="default")
        return frame
    match = re.fullmatch(
        r"Buy the highest-rated (?P<product_type>.+?) on amazon in "
        r"(?P<min_price>\d+(?:\.\d+)?)-(?P<max_price>\d+(?:\.\d+)?) price range "
        r"\(ignoring tax and other fees\) for each of my (?P<relationship>roommates|siblings) "
        r"and get them delivered to my home\.?",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        frame = IntentFrame("appworld_amazon_order_filtered_product")
        frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
        frame.set_slot("min_price", float(match.group("min_price")), source="regex", required=False)
        frame.set_slot("max_price", float(match.group("max_price")), source="regex", required=False)
        frame.set_slot("min_product_rating", None, source="default", required=False)
        frame.set_slot("min_product_reviews", None, source="default", required=False)
        frame.set_slot("min_seller_rating", None, source="default", required=False)
        frame.set_slot("price_bounds_inclusive", True, source="regex", required=False)
        frame.set_slot("rating_threshold_inclusive", True, source="default", required=False)
        frame.set_slot("prefer_highest_seller", False, source="default", required=False)
        frame.set_slot("source_container", "search", source="default", required=False)
        frame.set_slot("prior_ordered_sellers_only", False, source="default", required=False)
        frame.set_slot("max_length", None, source="default", required=False)
        frame.set_slot("max_width", None, source="default", required=False)
        frame.set_slot("quantity_relationship", match.group("relationship").lower(), source="regex", required=False)
        frame.set_slot("allow_mixed_products", False, source="regex", required=False)
        frame.set_slot("quantity", 0, source="derived_from_relationship")
        frame.set_slot("address_name", "Home", source="regex")
        frame.set_slot("card_name", "", source="default")
        return frame
    return None


def compile_amazon_post_question_last_ordered_product(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Post a question about the last (?P<product_type>.+?) I ordered on amazon, \"(?P<question>.+)\"\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_post_question_last_ordered_product")
    frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
    frame.set_slot("question", match.group("question").strip(), source="regex")
    return frame


def compile_amazon_update_last_month_order_review(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Change my amazon review about the (?P<color>[A-Za-z]+) "
        r"(?P<product_type>t-shirt|sweater) I ordered last calendar month\. "
        r"Make it (?P<rating>[1-5]) stars? with the title \"(?P<title>.+)\"\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_update_last_month_order_review")
    frame.set_slot("product_color", compact_text(match.group("color")).lower(), source="regex")
    frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
    frame.set_slot("target_rating", int(match.group("rating")), source="regex")
    frame.set_slot("title", match.group("title").strip(), source="regex")
    return frame


def compile_amazon_answer_last_order_question_yes_no(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Based on the question I posted about my last (?P<product_type>.+?) order on amazon, "
        r"(?P<question>.+?) Say yes or no\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_answer_last_order_question_yes_no")
    frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
    frame.set_slot("question", compact_text(match.group("question")).rstrip("?"), source="regex")
    return frame


def compile_amazon_answer_verified_battery_life_hours(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"How many hours does the battery of (?P<product_name>.+?) last\? "
        r"Please answer as per its amazon reviews or questions/answers and and only trust information from its verified purchasers\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_answer_verified_battery_life_hours")
    frame.set_slot("product_name", compact_text(match.group("product_name")), source="regex")
    return frame


def compile_amazon_answer_returned_product_yes_no(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Have I returned any (?P<product_type>.+?) on amazon in (?P<period>this month|this year|this or last month)\? "
        r"Say yes or no\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_answer_returned_product_yes_no")
    frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
    frame.set_slot("period", compact_text(match.group("period")).lower(), source="regex")
    return frame


def compile_amazon_answer_order_arrival_date(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"By when should everything from my (?P<day>today's|yesterday's) amazon order arrive\? "
        r"Tell me the date in (?P<date_format>DD-MM|MM-DD|DD/MM) format\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_answer_order_arrival_date")
    frame.set_slot("day_offset", 0 if match.group("day").lower().startswith("today") else 1, source="regex")
    frame.set_slot("date_format", match.group("date_format").upper(), source="regex")
    return frame


def compile_amazon_answer_spending_total(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"How much did I spend on amazon in (?P<period>this calendar year|the last calendar month|this or the last calendar month)\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    frame = IntentFrame("appworld_amazon_answer_spending_total")
    frame.set_slot("period", compact_text(match.group("period")).lower(), source="regex")
    return frame


def compile_amazon_answer_current_price_from_birthday_order(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"I ordered an? (?P<product_type>.+?) on amazon on my "
        r"(?P<relationship>mother|sister|brother|father|parent|sibling)'s birthday last year\. "
        r"How much does it cost now, ignoring tax and delivery fees\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    relationship = match.group("relationship").lower()
    frame = IntentFrame("appworld_amazon_answer_current_price_from_birthday_order")
    frame.set_slot("product_type", normalize_amazon_product_type(match.group("product_type")), source="regex")
    frame.set_slot("relationship", RELATION_ALIASES.get(relationship, relationship), source="regex")
    return frame


def compile_membership_paid_total(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"How much have I paid in (?P<membership>prime|premium) membership since I made the "
        r"(?P<app>amazon|spotify) account\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    app_name = match.group("app").lower()
    membership = match.group("membership").lower()
    if (app_name, membership) not in {("amazon", "prime"), ("spotify", "premium")}:
        return None
    frame = IntentFrame("appworld_membership_paid_total")
    frame.set_slot("app_name", app_name, source="regex")
    return frame


def compile_membership_last_payment_card_name(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"Tell me the card name I used for my last (?P<app>amazon|spotify) "
        r"(?P<membership>prime|premium) membership payment\?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    app_name = match.group("app").lower()
    membership = match.group("membership").lower()
    if (app_name, membership) not in {("amazon", "prime"), ("spotify", "premium")}:
        return None
    frame = IntentFrame("appworld_membership_last_payment_card_name")
    frame.set_slot("app_name", app_name, source="regex")
    return frame


def compile_membership_remaining_duration(
    request: str,
    raw_request: str,
    available_tools: AvailableTools,
) -> IntentFrame | None:
    match = re.fullmatch(
        r"How many (?P<unit>days|months) of (?P<app>amazon|spotify) "
        r"(?P<membership>prime|premium) subscription do I still have left\? "
        r"Round to the nearest number\.?",
        raw_request.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    app_name = match.group("app").lower()
    membership = match.group("membership").lower()
    unit = match.group("unit").lower()
    if (app_name, membership) not in {("amazon", "prime"), ("spotify", "premium")}:
        return None
    frame = IntentFrame("appworld_membership_remaining_duration")
    frame.set_slot("app_name", app_name, source="regex")
    frame.set_slot("unit", unit, source="regex")
    return frame


def handle_phone_message_non_venmo_contacts(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationships = frame.get("relationships", [])
    message = frame.get("message")
    excluded_app = frame.get("excluded_app")
    if not relationships or not message or excluded_app != "venmo":
        frame.abstain_reason = "missing_or_unsupported_phone_message_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
relationships = {json.dumps(relationships)}
message = {json.dumps(message)}
sent_to = []
seen_contacts = set()
for relationship in relationships:
    for contact in paged(lambda page: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship=relationship,
        page_index=page,
        page_limit=20,
    )):
        key = contact.get("contact_id") or contact.get("phone_number")
        if key in seen_contacts:
            continue
        seen_contacts.add(key)
        email = (contact.get("email") or "").lower()
        venmo_users = apis.venmo.search_users(
            access_token=tokens["venmo"],
            query=email,
            page_limit=20,
        )
        has_venmo = any((user.get("email") or "").lower() == email for user in venmo_users)
        if not has_venmo:
            apis.phone.send_text_message(
                access_token=tokens["phone"],
                phone_number=contact["phone_number"],
                message=message,
            )
            sent_to.append(contact["phone_number"])
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"sent_text_messages": sent_to, "count": len(sent_to)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_phone_message_non_venmo_contacts",
    )


def handle_phone_send_message_to_relationship(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationships = frame.get("relationships", [])
    message_kind = frame.get("message_kind")
    message = frame.get("message")
    if not relationships or message_kind not in {"text", "voice"} or not message:
        frame.abstain_reason = "missing_or_unsupported_phone_send_message_slots"
        return None
    code = common_appworld_prelude(["phone"]) + f"""
relationships = {json.dumps(relationships)}
message_kind = {json.dumps(message_kind)}
message = {json.dumps(message)}
sent_to = []
seen_phone_numbers = set()
for relationship in relationships:
    contacts = paged(lambda page: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship=relationship,
        page_index=page,
        page_limit=20,
    ))
    for contact in contacts:
        phone_number = contact["phone_number"]
        if phone_number in seen_phone_numbers:
            continue
        seen_phone_numbers.add(phone_number)
        if message_kind == "text":
            apis.phone.send_text_message(
                access_token=tokens["phone"],
                phone_number=phone_number,
                message=message,
            )
        else:
            apis.phone.send_voice_message(
                access_token=tokens["phone"],
                phone_number=phone_number,
                message=message,
            )
        sent_to.append(phone_number)
if not sent_to:
    raise Exception(f"No contacts found for relationships: {{relationships}}")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"message_kind": message_kind, "sent_to": sent_to, "count": len(sent_to)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_phone_send_message_to_relationship",
    )


def handle_phone_reply_favorite_recipe_to_relationship(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationship = frame.get("relationship")
    if relationship not in {"wife", "husband", "mother"}:
        frame.abstain_reason = "missing_favorite_recipe_reply_relationship"
        return None
    code = common_appworld_prelude(["phone", "simple_note"]) + f"""
relationship = {json.dumps(str(relationship))}
contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship=relationship,
    page_index=page,
    page_limit=20,
))
if len(contacts) != 1:
    raise Exception(f"Expected exactly one {{relationship}} contact, found {{len(contacts)}}.")
phone_number = contacts[0]["phone_number"]
notes = paged(lambda page: apis.simple_note.search_notes(
    access_token=tokens["simple_note"],
    query="Food Recipes",
    page_index=page,
    page_limit=20,
    dont_reorder_pinned=True,
))
favorite_names = []
for note_summary in notes:
    note = apis.simple_note.show_note(
        access_token=tokens["simple_note"],
        note_id=note_summary["note_id"],
    )
    if "recipe" not in str(note.get("title") or "").lower():
        continue
    current_name = None
    for line in str(note.get("content") or "").splitlines():
        name_match = re.match(r"\\s*name\\s*:\\s*(.+?)\\s*$", line, flags=re.IGNORECASE)
        if name_match:
            current_name = name_match.group(1).strip()
            continue
        favorite_match = re.match(r"\\s*favorite\\s*:\\s*(true|false)\\s*$", line, flags=re.IGNORECASE)
        if favorite_match and current_name and favorite_match.group(1).lower() == "true":
            favorite_names.append(current_name)
            current_name = None
if not favorite_names:
    raise Exception("No favorite recipe found in Simple Note.")
message = favorite_names[0]
apis.phone.send_text_message(
    access_token=tokens["phone"],
    phone_number=phone_number,
    message=message,
)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"relationship": relationship, "phone_number": phone_number, "message": message, "favorite_count": len(favorite_names)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_phone_reply_favorite_recipe_to_relationship",
    )


def handle_splitwise_accept_known_phone_invitations(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    message_kind = frame.get("message_kind")
    date_window = frame.get("date_window")
    if message_kind not in {"text", "voice"} or date_window not in {
        "yesterday",
        "the_day_before_yesterday",
        "this_week",
    }:
        frame.abstain_reason = "missing_splitwise_phone_invitation_window"
        return None
    code = common_appworld_prelude(["phone", "splitwise"]) + f"""
message_kind = {json.dumps(str(message_kind))}
date_window = {json.dumps(str(date_window))}
now = DateTime.now()
if date_window == "yesterday":
    window_start = now.subtract(days=1).start_of("day")
    window_end = now.subtract(days=1).end_of("day")
elif date_window == "the_day_before_yesterday":
    window_start = now.subtract(days=2).start_of("day")
    window_end = now.subtract(days=2).end_of("day")
else:
    window_start = now.start_of("week")
    window_end = now.end_of("week")

def normalize_phone(value):
    return re.sub(r"\\D", "", str(value or ""))

def contact_book_has_phone(phone_number):
    target = normalize_phone(phone_number)
    if not target:
        return False
    contacts = paged(lambda page: apis.phone.search_contacts(
        access_token=tokens["phone"],
        query=phone_number,
        page_index=page,
        page_limit=20,
    ))
    return any(normalize_phone(contact.get("phone_number")) == target for contact in contacts)

def extract_invitation_code(message):
    text = str(message or "")
    patterns = [
        r"(?:splitwise[^\\n]{{0,80}}(?:invitation|invite)[^\\n]{{0,80}}(?:code|link)[^A-Za-z0-9]{{0,20}})([A-Za-z0-9]{{5,32}})",
        r"(?:(?:invitation|invite)[^\\n]{{0,80}}(?:code|link)[^A-Za-z0-9]{{0,20}})([A-Za-z0-9]{{5,32}})",
        r"(?:group_invitation|invite|invitation)/([A-Za-z0-9]{{5,32}})",
        r"\\bcode\\s*(?:is|:)?\\s*([A-Za-z0-9]{{5,32}})\\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    candidates = re.findall(r"\\b[0-9a-fA-F]{{5}}\\b", text)
    if len(candidates) == 1 and "splitwise" in text.lower():
        return candidates[0]
    return ""

if message_kind == "text":
    messages = paged(lambda page: apis.phone.search_text_messages(
        access_token=tokens["phone"],
        page_index=page,
        page_limit=20,
        sort_by="+created_at",
    ))
    id_key = "text_message_id"
else:
    messages = paged(lambda page: apis.phone.search_voice_messages(
        access_token=tokens["phone"],
        page_index=page,
        page_limit=20,
        sort_by="+created_at",
    ))
    id_key = "voice_message_id"

profile_phone = normalize_phone(profile.get("phone_number"))
relevant = []
for message in messages:
    sent_at = DateTime.fromisoformat(message["sent_at"])
    if sent_at < window_start or sent_at > window_end:
        continue
    text = str(message.get("message") or "")
    invitation_code = extract_invitation_code(text)
    if not invitation_code:
        continue
    sender_phone = ((message.get("sender") or {{}}).get("phone_number") or "")
    receiver_phone = ((message.get("receiver") or {{}}).get("phone_number") or "")
    other_phone = sender_phone if normalize_phone(sender_phone) != profile_phone else receiver_phone
    relevant.append((message, other_phone, invitation_code))

accepted = []
deleted = []
seen_codes = set()
for message, other_phone, invitation_code in relevant:
    if contact_book_has_phone(other_phone):
        if invitation_code not in seen_codes:
            apis.splitwise.accept_group_invitation(
                access_token=tokens["splitwise"],
                invitation_code=invitation_code,
            )
            accepted.append({{"message_id": message[id_key], "phone_number": other_phone, "invitation_code": invitation_code}})
            seen_codes.add(invitation_code)
    else:
        if message_kind == "text":
            apis.phone.delete_text_message(
                access_token=tokens["phone"],
                text_message_id=message[id_key],
            )
        else:
            apis.phone.delete_voice_message(
                access_token=tokens["phone"],
                voice_message_id=message[id_key],
            )
        deleted.append({{"message_id": message[id_key], "phone_number": other_phone, "invitation_code": invitation_code}})

if not relevant:
    raise Exception(f"No Splitwise invitation phone {{message_kind}} messages found for {{date_window}}.")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"accepted": accepted, "deleted": deleted, "message_kind": message_kind, "date_window": date_window}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_splitwise_accept_known_phone_invitations",
    )


def handle_venmo_signup_missing_relationship_accounts(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationships = frame.get("relationships", [])
    password = frame.get("password")
    message = frame.get("message")
    if not relationships or not password or not message:
        frame.abstain_reason = "missing_venmo_signup_relationship_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
relationships = {json.dumps(relationships)}
password = {json.dumps(str(password))}
message = {json.dumps(str(message))}
seen_contact_ids = set()
contacts_to_check = []
for relationship in relationships:
    contacts = paged(lambda page, relationship=relationship: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship=relationship,
        page_index=page,
        page_limit=20,
    ))
    for contact in contacts:
        key = contact.get("contact_id") or contact.get("phone_number") or contact.get("email")
        if key in seen_contact_ids:
            continue
        seen_contact_ids.add(key)
        contacts_to_check.append(contact)

created = []
already_had_account = []
messaged = []
for contact in contacts_to_check:
    email = (contact.get("email") or "").strip().lower()
    phone_number = contact.get("phone_number")
    if not email or not phone_number:
        continue
    venmo_users = apis.venmo.search_users(
        access_token=tokens["venmo"],
        query=email,
        page_limit=20,
    )
    has_venmo = any((user.get("email") or "").strip().lower() == email for user in venmo_users)
    if has_venmo:
        already_had_account.append(email)
        continue
    first_name = str(contact.get("first_name") or "").strip()
    last_name = str(contact.get("last_name") or "").strip()
    if not first_name or not last_name:
        full_name = str(contact.get("name") or "").strip().split()
        first_name = first_name or (full_name[0] if full_name else "User")
        last_name = last_name or (" ".join(full_name[1:]) if len(full_name) > 1 else "Contact")
    apis.venmo.signup(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password=password,
    )
    apis.phone.send_text_message(
        access_token=tokens["phone"],
        phone_number=phone_number,
        message=message,
    )
    created.append(email)
    messaged.append(phone_number)

if not contacts_to_check:
    raise Exception(f"No contacts found for relationships: {{relationships}}")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"relationships": relationships, "created": created, "messaged": messaged, "already_had_account": already_had_account}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_signup_missing_relationship_accounts",
    )


def handle_phone_message_app_account_verify_reset(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationship = str(frame.get("relationship") or "").strip().lower()
    password = frame.get("password")
    date_window = str(frame.get("date_window") or "yesterday").strip().lower()
    if relationship not in {"son", "daughter", "child"} or not password:
        frame.abstain_reason = "missing_phone_message_account_reset_slots"
        return None
    if date_window != "yesterday":
        frame.abstain_reason = "unsupported_phone_message_account_reset_window"
        return None
    code = common_appworld_prelude(["phone", "gmail"]) + f"""
relationship = {json.dumps(relationship)}
new_password = {json.dumps(str(password))}
now = DateTime.now()
yesterday = now.subtract(days=1).to_date_string()
supported_apps = {{
    "amazon",
    "file_system",
    "simple_note",
    "splitwise",
    "spotify",
    "todoist",
    "venmo",
}}

def one_line(text):
    return " ".join(str(text or "").split())

def app_label(app_name):
    return {{
        "file_system": "file system",
        "simple_note": "simple note",
    }}.get(app_name, app_name.replace("_", " "))

def app_from_text(text):
    lower = text.lower()
    match = re.search(r"created an? ([a-z_ ]+?) account", lower)
    if not match:
        return ""
    phrase = match.group(1).strip().replace("-", " ").replace("_", " ")
    normalized = phrase.replace(" ", "_")
    aliases = {{
        "simplenote": "simple_note",
        "simple_note": "simple_note",
        "simple note": "simple_note",
        "file system": "file_system",
        "filesystem": "file_system",
    }}
    return aliases.get(phrase, aliases.get(normalized, normalized))

def temp_password_from_text(text):
    match = re.search(r"(?:password to be|password is|temporary password is|set your password to be)\\s+(.+?)\\s+(?:for now|\\.\\s|$)", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).strip().strip('"').strip("'").strip(".")

def code_from_email(text, code_kind):
    if code_kind == "verification":
        patterns = [
            r"account verification code is:\\s*([A-Za-z0-9_-]+)",
            r"verification code is:\\s*([A-Za-z0-9_-]+)",
        ]
    else:
        patterns = [
            r"password reset code is:\\s*([A-Za-z0-9_-]+)",
            r"reset code is:\\s*([A-Za-z0-9_-]+)",
        ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""

def find_recent_email_code(query, code_kind):
    threads = paged(lambda page: apis.gmail.show_inbox_threads(
        access_token=tokens["gmail"],
        query=query,
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    ))
    if not threads:
        threads = paged(lambda page: apis.gmail.show_inbox_threads(
            access_token=tokens["gmail"],
            page_index=page,
            page_limit=20,
            sort_by="-created_at",
        ))
    candidates = []
    for thread in threads:
        thread_id = thread.get("email_thread_id")
        if thread_id is None:
            continue
        detail = apis.gmail.show_thread(
            access_token=tokens["gmail"],
            email_thread_id=thread_id,
        )
        for email in detail.get("emails", []):
            subject = email.get("subject") or ""
            body = email.get("body") or ""
            text = subject + "\\n" + body
            code = code_from_email(text, code_kind)
            if code:
                candidates.append((email.get("created_at") or "", code, subject))
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][1]

contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship=relationship,
    page_index=page,
    page_limit=20,
))
if not contacts and relationship in {{"son", "daughter"}}:
    contacts = paged(lambda page: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship="child",
        page_index=page,
        page_limit=20,
    ))

candidate_messages = []
for contact in contacts:
    phone_number = contact.get("phone_number")
    if not phone_number:
        continue
    messages = paged(lambda page, phone_number=phone_number: apis.phone.search_text_messages(
        access_token=tokens["phone"],
        phone_number=phone_number,
        page_index=page,
        page_limit=20,
    ))
    for message in messages:
        sent_at = str(message.get("sent_at") or "")
        if not sent_at.startswith(yesterday):
            continue
        sender_phone = ((message.get("sender") or {{}}).get("phone_number") or "")
        if sender_phone != phone_number:
            continue
        text = str(message.get("message") or "")
        if "created" not in text.lower() or "account" not in text.lower():
            continue
        app_name = app_from_text(text)
        temp_password = temp_password_from_text(text)
        if app_name and temp_password:
            candidate_messages.append((sent_at, contact, message, app_name, temp_password))

if not candidate_messages:
    raise Exception(f"No yesterday app-account-creation phone message found for {{relationship}}.")
candidate_messages.sort(reverse=True, key=lambda item: item[0])
sent_at, contact, message, app_name, temporary_password = candidate_messages[0]
if app_name not in supported_apps:
    raise Exception(f"Unsupported app-account verification target: {{app_name}}")

app_api = getattr(apis, app_name)
email = profile["email"]
verify_result = app_api.send_verification_code(email=email)
verification_code = find_recent_email_code(app_label(app_name) + " Account Verficiation Code", "verification")
if not verification_code:
    verification_code = find_recent_email_code(app_label(app_name) + " verification code", "verification")
if not verification_code:
    raise Exception(f"No {{app_name}} verification code found in Gmail.")
app_api.verify_account(email=email, verification_code=verification_code)

reset_result = app_api.send_password_reset_code(email=email)
reset_code = find_recent_email_code(app_label(app_name) + " Password Reset Code", "password_reset")
if not reset_code:
    reset_code = find_recent_email_code(app_label(app_name) + " password reset code", "password_reset")
if not reset_code:
    raise Exception(f"No {{app_name}} password reset code found in Gmail.")
app_api.reset_password(
    email=email,
    password_reset_code=reset_code,
    new_password=new_password,
)

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "relationship": relationship,
    "app_name": app_name,
    "message_id": message.get("text_message_id"),
    "message_sent_at": sent_at,
    "temporary_password_observed": bool(temporary_password),
    "verification_result": verify_result,
    "reset_result": reset_result,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_phone_message_app_account_verify_reset",
    )


def handle_shared_subscription_password_reset_and_text(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    app_name = str(frame.get("app_name") or "").strip().lower()
    subscription_name = str(frame.get("subscription_name") or "").strip().lower()
    relationships = frame.get("relationships", [])
    new_password = str(frame.get("new_password") or "").strip()
    if (
        app_name not in {"amazon", "spotify"}
        or subscription_name not in {"prime", "premium"}
        or not relationships
        or not new_password
    ):
        frame.abstain_reason = "missing_shared_subscription_password_reset_slots"
        return None
    code = common_appworld_prelude(["phone", "gmail", app_name]) + f"""
app_name = {json.dumps(app_name)}
subscription_name = {json.dumps(subscription_name)}
relationships = {json.dumps(relationships)}
new_password = {json.dumps(new_password)}
app_api = getattr(apis, app_name)

def code_from_email(text):
    patterns = [
        r"password reset code is:\\s*([A-Za-z0-9_-]+)",
        r"reset code is:\\s*([A-Za-z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""

def find_recent_password_reset_code():
    app_label = app_name
    queries = [
        f"{{app_label}} Password Reset Code",
        f"{{app_label}} password reset code",
        "Password Reset Code",
    ]
    for query in queries:
        page_index = 0
        while page_index < 3:
            threads = apis.gmail.show_inbox_threads(
                access_token=tokens["gmail"],
                query=query,
                page_index=page_index,
                page_limit=20,
                sort_by="-created_at",
            )
            for thread in threads:
                thread_id = thread.get("email_thread_id")
                if thread_id is None:
                    continue
                detail = apis.gmail.show_thread(
                    access_token=tokens["gmail"],
                    email_thread_id=thread_id,
                )
                for email in detail.get("emails", []):
                    subject = str(email.get("subject") or "")
                    body = str(email.get("body") or "")
                    text = subject + "\\n" + body
                    if app_label not in text.lower():
                        continue
                    code = code_from_email(text)
                    if code:
                        return code
            if len(threads) < 20:
                break
            page_index += 1
    return ""

email = profile["email"]
reset_request = app_api.send_password_reset_code(email=email)
reset_code = find_recent_password_reset_code()
if not reset_code:
    raise Exception(f"No {{app_name}} password reset code found in Gmail.")
app_api.reset_password(
    email=email,
    password_reset_code=reset_code,
    new_password=new_password,
)

message = (
    f"I changed the {{app_name}} {{subscription_name}} account password to {{new_password}}."
)
sent_to = []
seen_phone_numbers = set()
for relationship in relationships:
    contacts = paged(lambda page, relationship=relationship: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship=relationship,
        page_index=page,
        page_limit=20,
    ))
    for contact in contacts:
        phone_number = str(contact.get("phone_number") or "").strip()
        if not phone_number or phone_number in seen_phone_numbers:
            continue
        seen_phone_numbers.add(phone_number)
        apis.phone.send_text_message(
            access_token=tokens["phone"],
            phone_number=phone_number,
            message=message,
        )
        sent_to.append(phone_number)
if not sent_to:
    raise Exception(f"No phone contacts found for relationships: {{relationships}}")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "app_name": app_name,
    "subscription_name": subscription_name,
    "relationships": relationships,
    "password_reset_requested": bool(reset_request),
    "sent_to": sent_to,
    "message": message,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_shared_subscription_password_reset_and_text",
    )


def handle_venmo_change_password(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    new_password = frame.get("new_password")
    if not new_password:
        frame.abstain_reason = "missing_venmo_new_password"
        return None
    code = common_appworld_prelude(["gmail"]) + f"""
new_password = {json.dumps(str(new_password))}

def code_from_email(text):
    patterns = [
        r"password reset code is:\\s*([A-Za-z0-9_-]+)",
        r"reset code is:\\s*([A-Za-z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""

def find_recent_password_reset_code():
    queries = [
        "venmo Password Reset Code",
        "venmo password reset code",
        "Password Reset Code",
    ]
    candidates = []
    for query in queries:
        threads = paged(lambda page, query=query: apis.gmail.show_inbox_threads(
            access_token=tokens["gmail"],
            query=query,
            page_index=page,
            page_limit=20,
            sort_by="-created_at",
        ))
        for thread in threads:
            thread_id = thread.get("email_thread_id")
            if thread_id is None:
                continue
            detail = apis.gmail.show_thread(
                access_token=tokens["gmail"],
                email_thread_id=thread_id,
            )
            for email in detail.get("emails", []):
                subject = str(email.get("subject") or "")
                body = str(email.get("body") or "")
                if "venmo" not in (subject + "\\n" + body).lower():
                    continue
                code = code_from_email(subject + "\\n" + body)
                if code:
                    candidates.append((str(email.get("created_at") or ""), code, subject))
        if candidates:
            break
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][1]

email = profile["email"]
reset_request = apis.venmo.send_password_reset_code(email=email)
reset_code = find_recent_password_reset_code()
if not reset_code:
    raise Exception("No Venmo password reset code found in Gmail.")
apis.venmo.reset_password(
    email=email,
    password_reset_code=reset_code,
    new_password=new_password,
)

apis.supervisor.complete_task(answer=None)
print(json.dumps({{"app": "venmo", "password_reset_requested": bool(reset_request)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_change_password",
    )


def handle_splitwise_record_venmo_receipt_payments(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    note = frame.get("note")
    if not note:
        frame.abstain_reason = "missing_splitwise_venmo_payment_note"
        return None
    code = common_appworld_prelude(["venmo", "splitwise", "file_system"]) + f"""
note = {json.dumps(str(note))}
now = DateTime.now()
today = now.to_date_string()
yesterday = now.subtract(days=1).to_date_string()

sent_today = paged(lambda page: apis.venmo.show_transactions(
    access_token=tokens["venmo"],
    direction="sent",
    min_created_at=today,
    max_created_at=today,
    page_index=page,
    page_limit=20,
))
groups = paged(lambda page: apis.splitwise.show_groups(
    access_token=tokens["splitwise"],
    page_index=page,
    page_limit=20,
))

def user_debt_amount(expense):
    total = 0.0
    for share in expense.get("shares", []):
        debtor = share.get("debtor") or {{}}
        if (debtor.get("email") or "").strip().lower() == user.email.lower():
            total += float(share.get("debt_amount") or 0)
    return round(total, 2)

def splitwise_hint(transaction):
    description = str(transaction.get("description") or "")
    if "splitwise" not in description.lower():
        return ""
    if "=>" in description:
        return description.split("=>", 1)[1].strip().lower()
    return ""

targets = []
for transaction in sent_today:
    receiver = ((transaction.get("receiver") or {{}}).get("email") or "").strip().lower()
    if not receiver:
        continue
    hint = splitwise_hint(transaction)
    candidates = []
    for group in groups:
        expenses = paged(lambda page, group_id=group["group_id"], receiver=receiver: apis.splitwise.show_group_expenses(
            access_token=tokens["splitwise"],
            group_id=group_id,
            participant_email=receiver,
            page_index=page,
            page_limit=20,
        ))
        for expense in expenses:
            payer_email = ((expense.get("payer") or {{}}).get("email") or "").strip().lower()
            created_at = str(expense.get("created_at") or "")
            debt_amount = user_debt_amount(expense)
            if payer_email != receiver:
                continue
            if not created_at.startswith(yesterday):
                continue
            if abs(debt_amount - round(float(transaction.get("amount") or 0), 2)) > 0.01:
                continue
            candidates.append({{
                "expense": expense,
                "group_id": group["group_id"],
                "group_name": group.get("name"),
                "debt_amount": debt_amount,
                "exact_description": bool(hint) and str(expense.get("description") or "").strip().lower() == hint,
            }})
    exact_candidates = [candidate for candidate in candidates if candidate["exact_description"]]
    if len(exact_candidates) == 1:
        selected = exact_candidates[0]
    elif len(candidates) == 1:
        selected = candidates[0]
    else:
        selected = None
    if selected is not None:
        targets.append({{
            "transaction": transaction,
            "selected": selected,
            "candidate_count": len(candidates),
            "exact_candidate_count": len(exact_candidates),
        }})

if not targets:
    raise Exception("No unique Venmo-to-Splitwise payment matches found.")

recorded = []
for target in targets:
    transaction = target["transaction"]
    selected = target["selected"]
    receiver_email = transaction["receiver"]["email"]
    amount = round(float(transaction["amount"]), 2)
    receipt_result = apis.venmo.download_transaction_receipt(
        access_token=tokens["venmo"],
        transaction_id=transaction["transaction_id"],
        file_system_access_token=tokens["file_system"],
        download_to_file_path=f"~/downloads/venmo_transaction_{{transaction['transaction_id']}}_receipt.txt",
        overwrite=True,
    )
    receipt_file_path = receipt_result["file_path"]
    payment_result = apis.splitwise.record_payment(
        access_token=tokens["splitwise"],
        payer_email=user.email,
        receiver_email=receiver_email,
        amount=amount,
        group_id=selected["group_id"],
        description=note,
        receipt_file_path=receipt_file_path,
        file_system_access_token=tokens["file_system"],
    )
    recorded.append({{
        "transaction_id": transaction["transaction_id"],
        "payment_id": payment_result["payment_id"],
        "expense_id": selected["expense"]["expense_id"],
        "group_id": selected["group_id"],
        "receiver_email": receiver_email,
        "amount": amount,
        "receipt_file_path": receipt_file_path,
        "candidate_count": target["candidate_count"],
        "exact_candidate_count": target["exact_candidate_count"],
    }})

apis.supervisor.complete_task(answer=None)
print(json.dumps({{"note": note, "recorded": recorded, "today": today, "yesterday": yesterday}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_splitwise_record_venmo_receipt_payments",
    )


def handle_todoist_reassign_accepted_takeover_tasks(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    comment_template = frame.get("comment_template")
    if not comment_template or "<person_first_name>" not in str(comment_template):
        frame.abstain_reason = "missing_todoist_reassignment_comment_template"
        return None
    code = common_appworld_prelude(["todoist"]) + f"""
comment_template = {json.dumps(str(comment_template))}
profile_email = (profile.get("email") or "").strip().lower()

def flatten_tasks(project_tasks):
    tasks = []
    tasks.extend(project_tasks.get("no_section_tasks") or [])
    for section in project_tasks.get("sections") or []:
        tasks.extend(section.get("tasks") or [])
    return tasks

def first_name_from_user(user):
    name = str((user or {{}}).get("name") or "").strip()
    if name:
        return name.split()[0]
    email = str((user or {{}}).get("email") or "").strip()
    return email.split("@")[0] if email else ""

def agreed_to_take(content):
    text = re.sub(r"\\s+", " ", str(content or "").strip().lower())
    positive_patterns = [
        r"\\b(i can|i'll|i will|i would|i am happy to|i'm happy to|happy to|sure[, ]|yes[, ]|yeah[, ])\\b[^.?!]{{0,120}}\\b(take|handle|do|own|work on|pick up|take over)\\b",
        r"\\b(take|handle|do|own|work on|pick up|take over)\\b[^.?!]{{0,80}}\\b(this|it|task)\\b",
        r"\\bassign (it|this|the task) to me\\b",
        r"\\bi can take it\\b",
        r"\\bi have the bandwidth to complete this task\\b",
    ]
    negative_patterns = [
        r"\\b(can't|cannot|cant|won't|not able|unable|too busy|no[, ]|sorry|my plate is full)\\b",
        r"\\bnot\\b[^.?!]{{0,40}}\\b(take|handle|do|own|work on|pick up)\\b",
    ]
    if any(re.search(pattern, text) for pattern in negative_patterns):
        return False
    return any(re.search(pattern, text) for pattern in positive_patterns)

projects = paged(lambda page: apis.todoist.show_projects(
    access_token=tokens["todoist"],
    page_index=page,
    page_limit=20,
))
reassigned = []
checked = []
for project in projects:
    if project.get("is_archived"):
        continue
    project_id = project["project_id"]
    project_tasks = apis.todoist.show_tasks(
        access_token=tokens["todoist"],
        project_id=project_id,
        assignee_email=profile_email,
        is_completed=False,
    )
    for task in flatten_tasks(project_tasks):
        task_id = task["task_id"]
        checked.append(task_id)
        comments = paged(lambda page, task_id=task_id: apis.todoist.show_task_comments(
            access_token=tokens["todoist"],
            task_id=task_id,
            page_index=page,
            page_limit=20,
        ))
        candidates = []
        for comment in comments:
            user = comment.get("user") or {{}}
            email = str(user.get("email") or "").strip().lower()
            if not email or email == profile_email:
                continue
            if agreed_to_take(comment.get("content")):
                candidates.append(comment)
        if len(candidates) != 1:
            continue
        chosen = sorted(candidates, key=lambda comment: comment.get("created_at") or "")[-1]
        chosen_user = chosen.get("user") or {{}}
        assignee_email = str(chosen_user.get("email") or "").strip().lower()
        first_name = first_name_from_user(chosen_user)
        if not assignee_email or not first_name:
            continue
        apis.todoist.assign_or_unassign_task(
            access_token=tokens["todoist"],
            task_id=task_id,
            assignee_email=assignee_email,
        )
        comment_content = comment_template.replace("<person_first_name>", first_name)
        apis.todoist.post_task_comment(
            access_token=tokens["todoist"],
            task_id=task_id,
            content=comment_content,
        )
        reassigned.append({{"task_id": task_id, "assignee_email": assignee_email, "comment": comment_content}})

apis.supervisor.complete_task(answer=None)
print(json.dumps({{"checked": checked, "reassigned": reassigned}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_todoist_reassign_accepted_takeover_tasks",
    )


def handle_spotify_apply_todoist_playlist_suggestions(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    destination = str(frame.get("destination") or "").strip()
    relationship_type = str(frame.get("relationship_type") or "").strip().lower()
    final_comment = str(frame.get("final_comment") or "").strip()
    if (
        not destination
        or relationship_type not in {"roommates", "siblings", "friends"}
        or not final_comment
    ):
        frame.abstain_reason = "missing_todoist_spotify_playlist_suggestion_slots"
        return None
    code = common_appworld_prelude(["phone", "todoist", "spotify"]) + f"""
destination = {json.dumps(destination)}
relationship_type = {json.dumps(relationship_type)}
final_comment = {json.dumps(final_comment)}
profile_email = str(profile.get("email") or "").strip().lower()

def normalize_text(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

def normalize_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

def flatten_tasks(project_tasks):
    tasks = []
    tasks.extend(project_tasks.get("no_section_tasks") or [])
    for section in project_tasks.get("sections") or []:
        tasks.extend(section.get("tasks") or [])
    return tasks

def contact_emails_for_relationship(relationship):
    singular = {{"roommates": "roommate", "siblings": "sibling", "friends": "friend"}}[relationship]
    contacts = paged(lambda page: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship=singular,
        page_index=page,
        page_limit=20,
    ))
    return {{str(contact.get("email") or "").strip().lower() for contact in contacts if contact.get("email")}}

def parse_suggestion_line(line):
    match = re.fullmatch(r"\\s*(add|remove)\\s*=>\\s*(.+?)\\s+by\\s+(.+?)\\s*", line, flags=re.IGNORECASE)
    if not match:
        return None
    artists = [part.strip() for part in re.split(r"\\s*,\\s*", match.group(3)) if part.strip()]
    return {{
        "operation": match.group(1).lower(),
        "title": match.group(2).strip(),
        "artists": artists,
    }}

def song_identity(song):
    artists = song.get("artists") or []
    return (
        normalize_key(song.get("title")),
        tuple(sorted(normalize_key(artist.get("name")) for artist in artists)),
    )

def suggested_identity(suggestion):
    return (
        normalize_key(suggestion["title"]),
        tuple(sorted(normalize_key(artist) for artist in suggestion["artists"])),
    )

def exact_song_search(suggestion):
    candidates = paged(lambda page: apis.spotify.search_songs(
        query=suggestion["title"],
        page_index=page,
        page_limit=20,
    ))
    target = suggested_identity(suggestion)
    exact = [song for song in candidates if song_identity(song) == target]
    unique = {{}}
    for song in exact:
        song_id = int(song.get("song_id") or song.get("id"))
        unique[song_id] = song
    if len(unique) != 1:
        raise Exception(f"Expected exactly one exact song search match for {{suggestion}}, got {{len(unique)}}")
    return next(iter(unique.values()))

projects = paged(lambda page: apis.todoist.show_projects(
    access_token=tokens["todoist"],
    page_index=page,
    page_limit=20,
))
destination_key = normalize_key(destination)
relationship_key = normalize_key(relationship_type)
relationship_emails = contact_emails_for_relationship(relationship_type)

project_infos = []
for project in projects:
    if project.get("is_archived"):
        continue
    project_name = str(project.get("name") or project.get("title") or "")
    project_text_key = normalize_key(project_name + " " + str(project.get("description") or ""))
    project_tasks = apis.todoist.show_tasks(
        access_token=tokens["todoist"],
        project_id=project["project_id"],
        is_completed=False,
    )
    playlist_tasks = []
    comment_emails = set()
    for task in flatten_tasks(project_tasks):
        comments = paged(lambda page, task_id=task["task_id"]: apis.todoist.show_task_comments(
            access_token=tokens["todoist"],
            task_id=task_id,
            page_index=page,
            page_limit=20,
        ))
        for comment in comments:
            email = str((comment.get("user") or {{}}).get("email") or "").strip().lower()
            if email:
                comment_emails.add(email)
        combined = "\\n".join(
            [str(task.get("title") or ""), str(task.get("description") or "")]
            + [str(comment.get("content") or "") for comment in comments]
        )
        urls = re.findall(r"spotify\\.com/playlists/(\\d+)", combined)
        suggestion_lines = []
        for line in combined.splitlines():
            parsed = parse_suggestion_line(line)
            if parsed:
                suggestion_lines.append(parsed)
        task_title_key = normalize_key(task.get("title"))
        is_playlist_task = bool(urls or suggestion_lines or "playlist" in task_title_key or "spotify" in task_title_key or "music" in task_title_key)
        if is_playlist_task:
            playlist_tasks.append({{
                "task": task,
                "comments": comments,
                "urls": urls,
                "suggestions": suggestion_lines,
            }})
    project_infos.append({{
        "project": project,
        "project_text_key": project_text_key,
        "playlist_tasks": playlist_tasks,
        "comment_emails": comment_emails,
        "relationship_overlap": len((comment_emails | {{str(c.get("email") or "").strip().lower() for c in project.get("collaborators") or []}}) & relationship_emails),
    }})

destination_matches = [
    info for info in project_infos
    if destination_key and destination_key in info["project_text_key"] and info["playlist_tasks"]
]
if len(destination_matches) == 1:
    chosen_project = destination_matches[0]
else:
    relation_matches = [
        info for info in project_infos
        if relationship_key in info["project_text_key"] and info["playlist_tasks"]
    ]
    if len(relation_matches) == 1:
        chosen_project = relation_matches[0]
    else:
        overlap_matches = [
            info for info in project_infos
            if info["playlist_tasks"] and info["relationship_overlap"] > 0
        ]
        max_overlap = max([info["relationship_overlap"] for info in overlap_matches] or [0])
        overlap_matches = [info for info in overlap_matches if info["relationship_overlap"] == max_overlap and max_overlap > 0]
        if len(overlap_matches) != 1:
            raise Exception(
                "Could not uniquely identify Todoist trip project: "
                + json.dumps({{
                    "destination_matches": [info["project"]["project_id"] for info in destination_matches],
                    "relation_matches": [info["project"]["project_id"] for info in relation_matches],
                    "overlap_matches": [info["project"]["project_id"] for info in overlap_matches],
                }}, sort_keys=True)
            )
        chosen_project = overlap_matches[0]

playlist_tasks = [
    task_info for task_info in chosen_project["playlist_tasks"]
    if task_info["urls"] and task_info["suggestions"]
]
if len(playlist_tasks) != 1:
    raise Exception(f"Expected one playlist task with URL and suggestions, got {{len(playlist_tasks)}}")
playlist_task = playlist_tasks[0]
task_id = playlist_task["task"]["task_id"]
playlist_ids = sorted({{int(pid) for pid in playlist_task["urls"]}})
if len(playlist_ids) != 1:
    raise Exception(f"Expected one playlist URL in target task, got {{playlist_ids}}")
playlist_id = playlist_ids[0]
suggestions = playlist_task["suggestions"]
if not suggestions:
    raise Exception("No actionable playlist suggestions found.")

playlist = apis.spotify.show_playlist(
    access_token=tokens["spotify"],
    playlist_id=playlist_id,
)
current_by_identity = {{}}
for song in playlist.get("songs") or []:
    identity = song_identity(song)
    if identity in current_by_identity:
        raise Exception(f"Duplicate song identity in playlist: {{identity}}")
    current_by_identity[identity] = song

planned_removes = []
planned_adds = []
for suggestion in suggestions:
    identity = suggested_identity(suggestion)
    if suggestion["operation"] == "remove":
        song = current_by_identity.get(identity)
        if song is None:
            raise Exception(f"Suggested removal not present in playlist: {{suggestion}}")
        planned_removes.append(song)
    else:
        song = exact_song_search(suggestion)
        song_id = int(song.get("song_id") or song.get("id"))
        if identity not in current_by_identity:
            planned_adds.append(song)

removed = []
seen_removed = set()
for song in planned_removes:
    song_id = int(song.get("song_id") or song.get("id"))
    if song_id in seen_removed:
        continue
    apis.spotify.remove_song_from_playlist(
        access_token=tokens["spotify"],
        playlist_id=playlist_id,
        song_id=song_id,
    )
    seen_removed.add(song_id)
    removed.append({{"song_id": song_id, "title": song.get("title")}})

added = []
seen_added = set()
for song in planned_adds:
    song_id = int(song.get("song_id") or song.get("id"))
    if song_id in seen_added or song_id in seen_removed:
        continue
    apis.spotify.add_song_to_playlist(
        access_token=tokens["spotify"],
        playlist_id=playlist_id,
        song_id=song_id,
    )
    seen_added.add(song_id)
    added.append({{"song_id": song_id, "title": song.get("title")}})

apis.todoist.post_task_comment(
    access_token=tokens["todoist"],
    task_id=task_id,
    content=final_comment,
)
apis.todoist.update_task(
    access_token=tokens["todoist"],
    task_id=task_id,
    is_completed=True,
)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "project_id": chosen_project["project"]["project_id"],
    "project_name": chosen_project["project"].get("name"),
    "task_id": task_id,
    "playlist_id": playlist_id,
    "suggestion_count": len(suggestions),
    "added": added,
    "removed": removed,
    "final_comment": final_comment,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_apply_todoist_playlist_suggestions",
    )


def handle_spotify_apply_phone_playlist_suggestions(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationship_type = str(frame.get("relationship_type") or "").strip().lower()
    if relationship_type not in {"roommates", "siblings"}:
        frame.abstain_reason = "missing_phone_spotify_playlist_relationship"
        return None
    code = common_appworld_prelude(["phone", "spotify"]) + f"""
relationship_type = {json.dumps(relationship_type)}

def normalize_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

def message_text(message):
    return str(message.get("message") or message.get("content") or "")

def parse_suggestion_line(line):
    match = re.fullmatch(r"\\s*(add|remove)\\s*=>\\s*(.+?)\\s+by\\s+(.+?)\\s*", line, flags=re.IGNORECASE)
    if not match:
        return None
    artists = [part.strip() for part in re.split(r"\\s*,\\s*", match.group(3)) if part.strip()]
    if not artists:
        return None
    return {{
        "operation": match.group(1).lower(),
        "title": match.group(2).strip(),
        "artists": artists,
    }}

def song_identity(song):
    artists = song.get("artists") or []
    return (
        normalize_key(song.get("title")),
        tuple(sorted(normalize_key(artist.get("name")) for artist in artists)),
    )

def suggested_identity(suggestion):
    return (
        normalize_key(suggestion["title"]),
        tuple(sorted(normalize_key(artist) for artist in suggestion["artists"])),
    )

def exact_song_search(suggestion):
    candidates = paged(lambda page: apis.spotify.search_songs(
        query=suggestion["title"],
        page_index=page,
        page_limit=20,
    ))
    target = suggested_identity(suggestion)
    unique = {{}}
    for song in candidates:
        if song_identity(song) != target:
            continue
        song_id = int(song.get("song_id") or song.get("id"))
        unique[song_id] = song
    if len(unique) != 1:
        raise Exception(f"Expected exactly one exact song search match for {{suggestion}}, got {{len(unique)}}")
    return next(iter(unique.values()))

relationship = {{"roommates": "roommate", "siblings": "sibling"}}[relationship_type]
contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship=relationship,
    page_index=page,
    page_limit=20,
))
if not contacts:
    raise Exception(f"No phone contacts found for {{relationship_type}}.")

playlist_ids = set()
suggestions = []
windows_checked = 0
for contact in contacts:
    phone_number = contact.get("phone_number")
    if not phone_number:
        continue
    messages = paged(lambda page, phone_number=phone_number: apis.phone.search_text_messages(
        access_token=tokens["phone"],
        phone_number=phone_number,
        page_index=page,
        page_limit=20,
    ))
    if messages:
        windows_checked += 1
    for message in messages:
        text = message_text(message)
        playlist_ids.update(int(pid) for pid in re.findall(r"spotify\\.com/playlists/(\\d+)", text))
        for line in text.splitlines():
            parsed = parse_suggestion_line(line)
            if parsed:
                suggestions.append(parsed)

if len(playlist_ids) != 1:
    raise Exception(f"Expected exactly one shared Spotify playlist URL, got {{sorted(playlist_ids)}}.")
if not suggestions:
    raise Exception("No actionable phone playlist suggestions found.")
playlist_id = next(iter(playlist_ids))
playlist = apis.spotify.show_playlist(
    access_token=tokens["spotify"],
    playlist_id=playlist_id,
)
current_by_identity = {{}}
for song in playlist.get("songs") or []:
    identity = song_identity(song)
    if identity in current_by_identity:
        raise Exception(f"Duplicate song identity in playlist: {{identity}}")
    current_by_identity[identity] = song

planned_removes = []
planned_adds = []
for suggestion in suggestions:
    identity = suggested_identity(suggestion)
    if suggestion["operation"] == "remove":
        song = current_by_identity.get(identity)
        if song is None:
            raise Exception(f"Suggested removal not present in playlist: {{suggestion}}")
        planned_removes.append(song)
    else:
        song = exact_song_search(suggestion)
        song_id = int(song.get("song_id") or song.get("id"))
        if identity not in current_by_identity:
            planned_adds.append(song)

removed = []
seen_removed = set()
for song in planned_removes:
    song_id = int(song.get("song_id") or song.get("id"))
    if song_id in seen_removed:
        continue
    apis.spotify.remove_song_from_playlist(
        access_token=tokens["spotify"],
        playlist_id=playlist_id,
        song_id=song_id,
    )
    seen_removed.add(song_id)
    removed.append({{"song_id": song_id, "title": song.get("title")}})

added = []
seen_added = set()
for song in planned_adds:
    song_id = int(song.get("song_id") or song.get("id"))
    if song_id in seen_added or song_id in seen_removed:
        continue
    apis.spotify.add_song_to_playlist(
        access_token=tokens["spotify"],
        playlist_id=playlist_id,
        song_id=song_id,
    )
    seen_added.add(song_id)
    added.append({{"song_id": song_id, "title": song.get("title")}})

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "relationship_type": relationship_type,
    "playlist_id": playlist_id,
    "windows_checked": windows_checked,
    "suggestion_count": len(suggestions),
    "added": added,
    "removed": removed,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_apply_phone_playlist_suggestions",
    )


def handle_pay_csv_debts_via_venmo_or_splitwise(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    csv_file_name = str(frame.get("csv_file_name") or "").strip()
    private = frame.get("private")
    if not csv_file_name.endswith(".csv") or not isinstance(private, bool):
        frame.abstain_reason = "missing_csv_debt_payment_slots"
        return None
    private_literal = "True" if private else "False"
    code = common_appworld_prelude(["file_system", "venmo", "splitwise"]) + f"""
csv_file_name = {json.dumps(csv_file_name)}
private = {private_literal}
profile_email = str(profile.get("email") or "").strip().lower()

def receipt_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())

def find_receipt_path(directory, description, files):
    target_key = receipt_key(description)
    candidates = []
    for path in files:
        if not path.startswith(directory) or not path.lower().endswith(".pdf"):
            continue
        stem = path.rsplit("/", 1)[-1][:-4]
        if receipt_key(stem) == target_key:
            candidates.append(path)
    if len(candidates) != 1:
        raise Exception(
            f"Expected one PDF receipt for {{description}} in {{directory}}, got {{candidates}}"
        )
    return candidates[0]

def parse_money(value):
    cleaned = re.sub(r"[^0-9.]", "", str(value or ""))
    if not cleaned:
        raise Exception(f"Missing amount in CSV value: {{value}}")
    return round(float(cleaned), 2)

def parse_simple_csv(content):
    lines = [line.strip() for line in str(content or "").splitlines() if line.strip()]
    if len(lines) < 2:
        raise Exception("CSV file has no data rows.")
    headers = [part.strip() for part in lines[0].split(",")]
    required = ["Name", "Email", "Amount", "Description"]
    if headers != required:
        raise Exception(f"Unexpected CSV headers: {{headers}}")
    rows = []
    for line in lines[1:]:
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != len(headers):
            raise Exception(f"Unsupported CSV row shape: {{line}}")
        rows.append({{headers[index]: parts[index] for index in range(len(headers))}})
    return rows

def exact_user_email(app_name, email):
    if app_name == "venmo":
        users = paged(lambda page: apis.venmo.search_users(
            access_token=tokens["venmo"],
            query=email,
            page_index=page,
            page_limit=20,
        ))
    else:
        users = paged(lambda page: apis.splitwise.search_users(
            access_token=tokens["splitwise"],
            query=email,
            include_self=False,
            page_index=page,
            page_limit=20,
        ))
    matches = [user for user in users if str(user.get("email") or "").strip().lower() == email]
    if len(matches) > 1:
        raise Exception(f"Multiple {{app_name}} exact matches for {{email}}")
    return str(matches[0]["email"]).strip().lower() if matches else None

files = apis.file_system.show_directory(
    access_token=tokens["file_system"],
    directory_path="/",
    entry_type="files",
    recursive=True,
)
csv_paths = [path for path in files if path.endswith("/" + csv_file_name) or path == csv_file_name]
if len(csv_paths) != 1:
    raise Exception(f"Expected one CSV path for {{csv_file_name}}, got {{csv_paths}}")
csv_path = csv_paths[0]
directory = csv_path.rsplit("/", 1)[0] + "/"
csv_file = apis.file_system.show_file(
    access_token=tokens["file_system"],
    file_path=csv_path,
)
rows = parse_simple_csv(csv_file.get("content"))

plans = []
total_venmo_amount = 0.0
for row in rows:
    email = str(row["Email"]).strip().lower()
    amount = parse_money(row["Amount"])
    description = str(row["Description"]).strip()
    if not email or not description:
        raise Exception(f"CSV row missing email or description: {{row}}")
    receipt_path = find_receipt_path(directory, description, files)
    splitwise_email = exact_user_email("splitwise", email)
    if not splitwise_email:
        raise Exception(f"No Splitwise account found for {{email}}")
    venmo_email = exact_user_email("venmo", email)
    plan = {{
        "email": email,
        "venmo_email": venmo_email,
        "splitwise_email": splitwise_email,
        "amount": amount,
        "description": description,
        "receipt_path": receipt_path,
    }}
    if venmo_email:
        total_venmo_amount = round(total_venmo_amount + amount, 2)
    plans.append(plan)

payment_card_id = None
if total_venmo_amount > 0:
    account = apis.venmo.show_account(access_token=tokens["venmo"])
    if float(account.get("venmo_balance") or 0.0) + 1e-9 < total_venmo_amount:
        cards = sorted(
            apis.venmo.show_payment_cards(access_token=tokens["venmo"]),
            key=lambda card: card["payment_card_id"],
            reverse=True,
        )
        if not cards:
            raise Exception("No Venmo balance or payment card available for CSV debts.")
        payment_card_id = cards[0]["payment_card_id"]

venmo_transactions = []
splitwise_expenses = []
for plan in plans:
    if plan["venmo_email"]:
        transaction_args = {{
            "access_token": tokens["venmo"],
            "receiver_email": plan["venmo_email"],
            "amount": plan["amount"],
            "description": plan["description"],
            "private": private,
        }}
        if payment_card_id is not None:
            transaction_args["payment_card_id"] = payment_card_id
        result = apis.venmo.create_transaction(**transaction_args)
        if "transaction_id" not in result:
            raise Exception(f"Unable to create Venmo transaction for {{plan}}: {{result}}")
        venmo_transactions.append({{
            "transaction_id": result["transaction_id"],
            "receiver_email": plan["venmo_email"],
            "amount": plan["amount"],
            "description": plan["description"],
            "private": private,
        }})
    else:
        result = apis.splitwise.record_expense(
            access_token=tokens["splitwise"],
            group_id=None,
            description=plan["description"],
            paid_amount=plan["amount"],
            payer_email=plan["splitwise_email"],
            debtor_emails=[profile_email],
            debt_amounts=[plan["amount"]],
            receipt_file_path=plan["receipt_path"],
            file_system_access_token=tokens["file_system"],
        )
        if "expense_id" not in result:
            raise Exception(f"Unable to record Splitwise expense for {{plan}}: {{result}}")
        splitwise_expenses.append({{
            "expense_id": result["expense_id"],
            "payer_email": plan["splitwise_email"],
            "debtor_email": profile_email,
            "amount": plan["amount"],
            "description": plan["description"],
            "receipt_path": plan["receipt_path"],
        }})

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "csv_path": csv_path,
    "private": private,
    "venmo_transactions": venmo_transactions,
    "splitwise_expenses": splitwise_expenses,
    "total_venmo_amount": total_venmo_amount,
    "payment_card_id": payment_card_id,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_pay_csv_debts_via_venmo_or_splitwise",
    )


def handle_venmo_send_to_phone_number(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    phone_number = frame.get("phone_number")
    amount = frame.get("amount")
    private = frame.get("private")
    if not phone_number or amount is None or private is None:
        frame.abstain_reason = "missing_venmo_payment_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
target_phone = {json.dumps(phone_number)}
amount = {json.dumps(amount)}
private = {repr(private)}
contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    query=target_phone,
    page_index=page,
    page_limit=20,
))
matching_contacts = [contact for contact in contacts if contact.get("phone_number") == target_phone]
if not matching_contacts:
    raise Exception(f"No phone contact found for {{target_phone}}.")
contact = matching_contacts[0]
email = (contact.get("email") or "").lower()
venmo_users = apis.venmo.search_users(
    access_token=tokens["venmo"],
    query=email,
    page_limit=20,
)
matching_users = [user for user in venmo_users if (user.get("email") or "").lower() == email]
if not matching_users:
    raise Exception(f"No Venmo account found for {{email}}.")
receiver_email = matching_users[0]["email"]
transaction_args = {{
    "access_token": tokens["venmo"],
    "receiver_email": receiver_email,
    "amount": amount,
    "private": private,
}}
account = apis.venmo.show_account(access_token=tokens["venmo"])
failed_api_attempts = 0
if account.get("venmo_balance", 0) < amount:
    cards = apis.venmo.show_payment_cards(access_token=tokens["venmo"])
    if not cards:
        raise Exception("No Venmo balance or payment card available for transaction.")
    cards = [
        card
        for card in cards
        if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
    ]
    cards = sorted(cards, key=lambda card: card["payment_card_id"], reverse=True)
    result = {{"message": "No non-expired payment card available."}}
    for card in cards:
        transaction_args["payment_card_id"] = card["payment_card_id"]
        transaction_args["description"] = "Payment"
        result = apis.venmo.create_transaction(**transaction_args)
        if "transaction_id" in result:
            break
        failed_api_attempts += 1
else:
    result = apis.venmo.create_transaction(**transaction_args)
if "transaction_id" not in result:
    raise Exception(f"Unable to create Venmo transaction: {{result}}")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"failed_api_attempts": failed_api_attempts, "receiver_email": receiver_email, "result": result}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_send_to_phone_number",
    )


def handle_venmo_send_to_named_user(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    first_name = frame.get("person_first_name")
    amount = frame.get("amount")
    if not first_name or amount is None:
        frame.abstain_reason = "missing_venmo_named_payment_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
first_name = {json.dumps(str(first_name))}
amount = {float(amount)}
first_name_lower = first_name.lower()
contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    query=first_name,
    page_index=page,
    page_limit=20,
))
contact_matches = [
    contact
    for contact in contacts
    if (contact.get("first_name") or "").strip().lower() == first_name_lower
]
candidate_emails = [
    (contact.get("email") or "").strip().lower()
    for contact in contact_matches
    if (contact.get("email") or "").strip()
]
venmo_matches = []
for email in candidate_emails:
    users = apis.venmo.search_users(
        access_token=tokens["venmo"],
        query=email,
        page_limit=20,
    )
    venmo_matches.extend(
        user for user in users if (user.get("email") or "").strip().lower() == email
    )
if not venmo_matches:
    users = apis.venmo.search_users(
        access_token=tokens["venmo"],
        query=first_name,
        page_limit=20,
    )
    venmo_matches = [
        user
        for user in users
        if (user.get("first_name") or "").strip().lower() == first_name_lower
    ]
unique_by_email = {{}}
for user_record in venmo_matches:
    email = (user_record.get("email") or "").strip().lower()
    if email:
        unique_by_email[email] = user_record
if len(unique_by_email) != 1:
    raise Exception(f"Expected exactly one Venmo user named {{first_name}}, found {{len(unique_by_email)}}.")
receiver_email = next(iter(unique_by_email))
transaction_args = {{
    "access_token": tokens["venmo"],
    "receiver_email": receiver_email,
    "amount": amount,
    "private": False,
    "description": "",
}}
account = apis.venmo.show_account(access_token=tokens["venmo"])
failed_api_attempts = 0
if float(account.get("venmo_balance") or 0) >= amount:
    result = apis.venmo.create_transaction(**transaction_args)
else:
    result = {{"message": "No non-expired payment card available."}}
    cards = [
        card
        for card in apis.venmo.show_payment_cards(access_token=tokens["venmo"])
        if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
    ]
    cards = sorted(
        cards,
        key=lambda card: (
            float(card.get("balance") or 0),
            card["expiry_year"],
            card["expiry_month"],
            card["payment_card_id"],
        ),
        reverse=True,
    )
    existing_card_numbers = {{str(card.get("card_number")) for card in cards}}
    supervisor_cards = sorted(
        apis.supervisor.show_payment_cards(),
        key=lambda card: (
            float(card.get("balance") or 0),
            card["expiry_year"],
            card["expiry_month"],
            str(card["card_number"]),
        ),
        reverse=True,
    )
    for supervisor_card in supervisor_cards:
        if str(supervisor_card.get("card_number")) in existing_card_numbers:
            continue
        if DateTime(supervisor_card["expiry_year"], supervisor_card["expiry_month"], 1).start_of("month") <= DateTime.now():
            continue
        if "balance" in supervisor_card and float(supervisor_card.get("balance") or 0) < amount:
            continue
        add_result = apis.venmo.add_payment_card(
            access_token=tokens["venmo"],
            card_name=supervisor_card["card_name"],
            owner_name=supervisor_card["owner_name"],
            card_number=supervisor_card["card_number"],
            expiry_year=supervisor_card["expiry_year"],
            expiry_month=supervisor_card["expiry_month"],
            cvv_number=supervisor_card["cvv_number"],
        )
        if "payment_card_id" not in add_result:
            result = add_result
            failed_api_attempts += 1
            continue
        transaction_args["payment_card_id"] = add_result["payment_card_id"]
        result = apis.venmo.create_transaction(**transaction_args)
        if "transaction_id" in result:
            break
        failed_api_attempts += 1
    if "transaction_id" not in result:
        for card in cards:
            transaction_args["payment_card_id"] = card["payment_card_id"]
            result = apis.venmo.create_transaction(**transaction_args)
            if "transaction_id" in result:
                break
            failed_api_attempts += 1
if "transaction_id" not in result:
    raise Exception(f"Unable to create Venmo transaction: {{result}}")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"first_name": first_name, "receiver_email": receiver_email, "amount": amount, "failed_api_attempts": failed_api_attempts, "result": result}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_send_to_named_user",
    )


def handle_venmo_send_to_named_user_with_optional_signup(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    first_name = frame.get("person_first_name")
    amount = frame.get("amount")
    if not first_name or amount is None:
        frame.abstain_reason = "missing_venmo_optional_signup_payment_slots"
        return None
    code = common_appworld_prelude(["phone", "gmail"]) + f"""
first_name = {json.dumps(str(first_name))}
amount = {float(amount)}
first_name_lower = first_name.lower()
profile_first = str(profile.get("first_name") or "").strip()
profile_last = str(profile.get("last_name") or "").strip()
profile_email = str(profile.get("email") or "").strip().lower()
venmo_password = passwords.get("venmo") or passwords.get("gmail") or "TempVenmo1"
created_account = False
verified_account = False

def code_from_email(text):
    patterns = [
        r"account verification code is:\\s*([A-Za-z0-9_-]+)",
        r"verification code is:\\s*([A-Za-z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, str(text or ""), flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""

def find_recent_venmo_verification_code():
    queries = [
        "Venmo Account Verficiation Code",
        "Venmo verification code",
        "account verification code",
    ]
    candidates = []
    for query in queries:
        threads = paged(lambda page, query=query: apis.gmail.show_inbox_threads(
            access_token=tokens["gmail"],
            query=query,
            page_index=page,
            page_limit=20,
            sort_by="-created_at",
        ))
        for thread in threads:
            thread_id = thread.get("email_thread_id")
            if thread_id is None:
                continue
            detail = apis.gmail.show_thread(
                access_token=tokens["gmail"],
                email_thread_id=thread_id,
            )
            for email in detail.get("emails", []):
                subject = str(email.get("subject") or "")
                body = str(email.get("body") or "")
                if "venmo" not in (subject + "\\n" + body).lower():
                    continue
                code = code_from_email(subject + "\\n" + body)
                if code:
                    candidates.append((str(email.get("created_at") or ""), code, subject))
        if candidates:
            break
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][1]

login_result = apis.venmo.login(username=profile_email, password=venmo_password)
if "access_token" not in login_result:
    signup_result = apis.venmo.signup(
        first_name=profile_first,
        last_name=profile_last,
        email=profile_email,
        password=venmo_password,
    )
    created_account = "created" in str(signup_result.get("message", "")).lower()
    verification_code = find_recent_venmo_verification_code()
    if not verification_code:
        send_result = apis.venmo.send_verification_code(email=profile_email)
        verification_code = find_recent_venmo_verification_code()
    if not verification_code:
        raise Exception("No Venmo account verification code found in Gmail.")
    verify_result = apis.venmo.verify_account(
        email=profile_email,
        verification_code=verification_code,
    )
    verified_account = "verified" in str(verify_result.get("message", "")).lower()
    login_result = apis.venmo.login(username=profile_email, password=venmo_password)
if "access_token" not in login_result:
    raise Exception(f"Unable to log in to Venmo after optional signup: {{login_result}}")
tokens["venmo"] = login_result["access_token"]

contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    query=first_name,
    page_index=page,
    page_limit=20,
))
contact_matches = [
    contact
    for contact in contacts
    if (contact.get("first_name") or "").strip().lower() == first_name_lower
]
candidate_emails = [
    (contact.get("email") or "").strip().lower()
    for contact in contact_matches
    if (contact.get("email") or "").strip()
]
venmo_matches = []
for email in candidate_emails:
    users = apis.venmo.search_users(
        access_token=tokens["venmo"],
        query=email,
        page_limit=20,
    )
    venmo_matches.extend(
        user for user in users if (user.get("email") or "").strip().lower() == email
    )
if not venmo_matches:
    users = apis.venmo.search_users(
        access_token=tokens["venmo"],
        query=first_name,
        page_limit=20,
    )
    venmo_matches = [
        user
        for user in users
        if (user.get("first_name") or "").strip().lower() == first_name_lower
    ]
unique_by_email = {{}}
for user_record in venmo_matches:
    email = (user_record.get("email") or "").strip().lower()
    if email and email != profile_email:
        unique_by_email[email] = user_record
if len(unique_by_email) != 1:
    raise Exception(f"Expected exactly one Venmo receiver named {{first_name}}, found {{len(unique_by_email)}}.")
receiver_email = next(iter(unique_by_email))

transaction_args = {{
    "access_token": tokens["venmo"],
    "receiver_email": receiver_email,
    "amount": amount,
    "private": False,
    "description": "",
}}
account = apis.venmo.show_account(access_token=tokens["venmo"])
failed_api_attempts = 0
if float(account.get("venmo_balance") or 0) >= amount:
    result = apis.venmo.create_transaction(**transaction_args)
else:
    result = {{"message": "No non-expired payment card available."}}
    cards = [
        card
        for card in apis.venmo.show_payment_cards(access_token=tokens["venmo"])
        if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
    ]
    cards = sorted(
        cards,
        key=lambda card: (
            float(card.get("balance") or 0),
            card["expiry_year"],
            card["expiry_month"],
            card["payment_card_id"],
        ),
        reverse=True,
    )
    existing_card_numbers = {{str(card.get("card_number")) for card in cards}}
    supervisor_cards = sorted(
        apis.supervisor.show_payment_cards(),
        key=lambda card: (
            float(card.get("balance") or 0),
            card["expiry_year"],
            card["expiry_month"],
            str(card["card_number"]),
        ),
        reverse=True,
    )
    for supervisor_card in supervisor_cards:
        if str(supervisor_card.get("card_number")) in existing_card_numbers:
            continue
        if DateTime(supervisor_card["expiry_year"], supervisor_card["expiry_month"], 1).start_of("month") <= DateTime.now():
            continue
        if "balance" in supervisor_card and float(supervisor_card.get("balance") or 0) < amount:
            continue
        add_result = apis.venmo.add_payment_card(
            access_token=tokens["venmo"],
            card_name=supervisor_card["card_name"],
            owner_name=supervisor_card["owner_name"],
            card_number=supervisor_card["card_number"],
            expiry_year=supervisor_card["expiry_year"],
            expiry_month=supervisor_card["expiry_month"],
            cvv_number=supervisor_card["cvv_number"],
        )
        if "payment_card_id" not in add_result:
            result = add_result
            failed_api_attempts += 1
            continue
        transaction_args["payment_card_id"] = add_result["payment_card_id"]
        result = apis.venmo.create_transaction(**transaction_args)
        if "transaction_id" in result:
            break
        failed_api_attempts += 1
    if "transaction_id" not in result:
        for card in cards:
            transaction_args["payment_card_id"] = card["payment_card_id"]
            result = apis.venmo.create_transaction(**transaction_args)
            if "transaction_id" in result:
                break
            failed_api_attempts += 1
if "transaction_id" not in result:
    raise Exception(f"Unable to create Venmo transaction: {{result}}")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "first_name": first_name,
    "receiver_email": receiver_email,
    "amount": amount,
    "created_account": created_account,
    "verified_account": verified_account,
    "failed_api_attempts": failed_api_attempts,
    "result": result,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_send_to_named_user_with_optional_signup",
    )


def handle_venmo_pay_flight_bill_from_email(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    first_name = frame.get("person_first_name")
    note = frame.get("note")
    if not first_name or not note:
        frame.abstain_reason = "missing_venmo_flight_bill_payment_slots"
        return None
    code = common_appworld_prelude(["phone", "gmail", "file_system", "venmo"]) + f"""
first_name = {json.dumps(str(first_name))}
note = {json.dumps(str(note))}
first_name_lower = first_name.lower()

def normalize_email(value):
    return str(value or "").strip().lower()

def extract_amount_from_receipt(text):
    patterns = [
        r"Total\\s+Amount\\s*(?:=>|:|-)?\\s*\\$\\s*(\\d+(?:\\.\\d+)?)",
        r"Amount\\s*(?:owed|due|to pay)?\\s*(?:=>|:|-)?\\s*\\$\\s*(\\d+(?:\\.\\d+)?)",
        r"\\$\\s*(\\d+(?:\\.\\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, str(text or ""), flags=re.IGNORECASE)
        if match:
            return round(float(match.group(1)), 2)
    return None

def create_transaction_with_refill(receiver_email, amount, description):
    transaction_args = {{
        "access_token": tokens["venmo"],
        "receiver_email": receiver_email,
        "amount": amount,
        "private": False,
        "description": description,
    }}
    account = apis.venmo.show_account(access_token=tokens["venmo"])
    failed_attempts = 0
    if float(account.get("venmo_balance") or 0) >= amount:
        result = apis.venmo.create_transaction(**transaction_args)
    else:
        result = {{"message": "No non-expired payment card available."}}
        cards = [
            card
            for card in apis.venmo.show_payment_cards(access_token=tokens["venmo"])
            if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
        ]
        cards = sorted(
            cards,
            key=lambda card: (
                float(card.get("balance") or 0),
                card["expiry_year"],
                card["expiry_month"],
                card["payment_card_id"],
            ),
            reverse=True,
        )
        for card in cards:
            transaction_args["payment_card_id"] = card["payment_card_id"]
            result = apis.venmo.create_transaction(**transaction_args)
            if "transaction_id" in result:
                break
            failed_attempts += 1
        if "transaction_id" not in result:
            existing_card_numbers = {{str(card.get("card_number")) for card in cards}}
            supervisor_cards = sorted(
                apis.supervisor.show_payment_cards(),
                key=lambda card: (
                    float(card.get("balance") or 0),
                    card["expiry_year"],
                    card["expiry_month"],
                    str(card["card_number"]),
                ),
                reverse=True,
            )
            for supervisor_card in supervisor_cards:
                if str(supervisor_card.get("card_number")) in existing_card_numbers:
                    continue
                if DateTime(supervisor_card["expiry_year"], supervisor_card["expiry_month"], 1).start_of("month") <= DateTime.now():
                    continue
                if "balance" in supervisor_card and float(supervisor_card.get("balance") or 0) < amount:
                    continue
                add_result = apis.venmo.add_payment_card(
                    access_token=tokens["venmo"],
                    card_name=supervisor_card["card_name"],
                    owner_name=supervisor_card["owner_name"],
                    card_number=supervisor_card["card_number"],
                    expiry_year=supervisor_card["expiry_year"],
                    expiry_month=supervisor_card["expiry_month"],
                    cvv_number=supervisor_card["cvv_number"],
                )
                if "payment_card_id" not in add_result:
                    result = add_result
                    failed_attempts += 1
                    continue
                transaction_args["payment_card_id"] = add_result["payment_card_id"]
                result = apis.venmo.create_transaction(**transaction_args)
                if "transaction_id" in result:
                    break
                failed_attempts += 1
    if "transaction_id" not in result:
        raise Exception(f"Unable to create Venmo transaction to {{receiver_email}}: {{result}}")
    return result, failed_attempts

contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    query=first_name,
    page_index=page,
    page_limit=20,
))
matching_contacts = [
    contact
    for contact in contacts
    if str(contact.get("first_name") or "").strip().lower() == first_name_lower
]
unique_contacts = {{}}
for contact in matching_contacts:
    email = normalize_email(contact.get("email"))
    if email:
        unique_contacts[email] = contact
if len(unique_contacts) != 1:
    raise Exception(f"Expected exactly one phone contact named {{first_name}}, found {{len(unique_contacts)}}.")
contact_email = next(iter(unique_contacts))

threads = paged(lambda page: apis.gmail.show_inbox_threads(
    access_token=tokens["gmail"],
    query="flight",
    from_email=contact_email,
    attachment=True,
    page_index=page,
    page_limit=20,
    sort_by="-created_at",
))
candidate_receipts = []
for thread in threads:
    detail = apis.gmail.show_thread(
        access_token=tokens["gmail"],
        email_thread_id=thread["email_thread_id"],
    )
    for email in detail.get("emails", []):
        sender = email.get("sender") or {{}}
        sender_email = normalize_email(sender.get("email") if isinstance(sender, dict) else sender)
        if sender_email != contact_email:
            continue
        haystack = (str(email.get("subject") or "") + "\\n" + str(email.get("body") or "")).lower()
        if "flight" not in haystack:
            continue
        for attachment in email.get("attachments", []):
            file_name = str(attachment.get("file_name") or "")
            download_result = apis.gmail.download_attachment(
                access_token=tokens["gmail"],
                attachment_id=attachment["id"],
                overwrite=True,
                file_system_access_token=tokens["file_system"],
            )
            file_path = download_result["file_path"]
            file_info = apis.file_system.show_file(
                access_token=tokens["file_system"],
                file_path=file_path,
            )
            content = str(file_info.get("content") or "")
            amount = extract_amount_from_receipt(content)
            if amount is None:
                continue
            receipt_text = (str(email.get("subject") or "") + "\\n" + content).lower()
            if "flight" not in receipt_text:
                continue
            candidate_receipts.append({{
                "created_at": str(email.get("created_at") or thread.get("created_at") or ""),
                "email_thread_id": thread["email_thread_id"],
                "attachment_id": attachment["id"],
                "file_name": file_name,
                "amount": amount,
            }})
if not candidate_receipts:
    raise Exception(f"No flight bill receipt with an amount found from {{contact_email}}.")
candidate_receipts.sort(key=lambda item: (item["created_at"], item["email_thread_id"], item["attachment_id"]), reverse=True)
amount = candidate_receipts[0]["amount"]

venmo_users = apis.venmo.search_users(
    access_token=tokens["venmo"],
    query=contact_email,
    page_limit=20,
)
matching_users = [
    user for user in venmo_users
    if normalize_email(user.get("email")) == contact_email
]
if len(matching_users) != 1:
    raise Exception(f"Expected exactly one Venmo account for {{contact_email}}, found {{len(matching_users)}}.")
receiver_email = normalize_email(matching_users[0]["email"])
result, failed_api_attempts = create_transaction_with_refill(receiver_email, amount, note)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "first_name": first_name,
    "receiver_email": receiver_email,
    "amount": amount,
    "note": note,
    "receipt": candidate_receipts[0],
    "failed_api_attempts": failed_api_attempts,
    "result": result,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_pay_flight_bill_from_email",
    )


def handle_venmo_pay_coworkers_and_email(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationships = frame.get("relationships", [])
    amount = frame.get("amount")
    note = str(frame.get("note") or "").strip()
    email_subject = str(frame.get("email_subject") or "").strip()
    email_body = str(frame.get("email_body") or "").strip()
    if not relationships or amount is None or not note or not email_subject or not email_body:
        frame.abstain_reason = "missing_venmo_coworker_payment_email_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo", "gmail"]) + f"""
relationships = {json.dumps(relationships)}
amount = {float(amount)}
note = {json.dumps(note)}
email_subject = {json.dumps(email_subject)}
email_body = {json.dumps(email_body)}

def normalize_email(value):
    return str(value or "").strip().lower()

def exact_venmo_user_email(email):
    users = apis.venmo.search_users(
        access_token=tokens["venmo"],
        query=email,
        page_limit=20,
    )
    matches = [
        user for user in users
        if normalize_email(user.get("email")) == email
    ]
    if len(matches) != 1:
        raise Exception(f"Expected exactly one Venmo user for {{email}}, found {{len(matches)}}.")
    return normalize_email(matches[0]["email"])

target_emails = []
seen_emails = set()
for relationship in relationships:
    contacts = paged(lambda page, relationship=relationship: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship=relationship,
        page_index=page,
        page_limit=20,
    ))
    for contact in contacts:
        email = normalize_email(contact.get("email"))
        if not email or email in seen_emails:
            continue
        seen_emails.add(email)
        target_emails.append(email)
target_emails = sorted(target_emails)
if not target_emails:
    raise Exception(f"No phone contacts found for relationships: {{relationships}}")

venmo_receiver_emails = []
for email in target_emails:
    venmo_receiver_emails.append(exact_venmo_user_email(email))

total_needed = round(amount * len(venmo_receiver_emails), 2)
account = apis.venmo.show_account(access_token=tokens["venmo"])
starting_balance = float(account.get("venmo_balance") or 0)
bank_transfer_id = None
if starting_balance + 1e-9 < total_needed:
    refill_amount = round(total_needed - starting_balance, 2)
    cards = [
        card
        for card in apis.venmo.show_payment_cards(access_token=tokens["venmo"])
        if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
    ]
    cards = sorted(
        cards,
        key=lambda card: (
            float(card.get("balance") or 0),
            card["expiry_year"],
            card["expiry_month"],
            card["payment_card_id"],
        ),
        reverse=True,
    )
    refill_result = {{"message": "No Venmo payment card could fund the refill."}}
    for card in cards:
        refill_result = apis.venmo.add_to_venmo_balance(
            access_token=tokens["venmo"],
            amount=refill_amount,
            payment_card_id=card["payment_card_id"],
        )
        if "bank_transfer_id" in refill_result:
            bank_transfer_id = refill_result["bank_transfer_id"]
            break
    if bank_transfer_id is None:
        existing_card_numbers = {{str(card.get("card_number")) for card in cards}}
        supervisor_cards = sorted(
            apis.supervisor.show_payment_cards(),
            key=lambda card: (
                float(card.get("balance") or 0),
                card["expiry_year"],
                card["expiry_month"],
                str(card["card_number"]),
            ),
            reverse=True,
        )
        for supervisor_card in supervisor_cards:
            if str(supervisor_card.get("card_number")) in existing_card_numbers:
                continue
            if DateTime(supervisor_card["expiry_year"], supervisor_card["expiry_month"], 1).start_of("month") <= DateTime.now():
                continue
            if "balance" in supervisor_card and float(supervisor_card.get("balance") or 0) < refill_amount:
                continue
            add_result = apis.venmo.add_payment_card(
                access_token=tokens["venmo"],
                card_name=supervisor_card["card_name"],
                owner_name=supervisor_card["owner_name"],
                card_number=supervisor_card["card_number"],
                expiry_year=supervisor_card["expiry_year"],
                expiry_month=supervisor_card["expiry_month"],
                cvv_number=supervisor_card["cvv_number"],
            )
            if "payment_card_id" not in add_result:
                refill_result = add_result
                continue
            refill_result = apis.venmo.add_to_venmo_balance(
                access_token=tokens["venmo"],
                amount=refill_amount,
                payment_card_id=add_result["payment_card_id"],
            )
            if "bank_transfer_id" in refill_result:
                bank_transfer_id = refill_result["bank_transfer_id"]
                break
    if bank_transfer_id is None:
        raise Exception(f"Unable to refill Venmo balance: {{refill_result}}")

transactions = []
for email in venmo_receiver_emails:
    result = apis.venmo.create_transaction(
        access_token=tokens["venmo"],
        receiver_email=email,
        amount=amount,
        description=note,
        private=True,
    )
    if "transaction_id" not in result:
        raise Exception(f"Unable to create Venmo transaction for {{email}}: {{result}}")
    transactions.append({{
        "receiver_email": email,
        "transaction_id": result["transaction_id"],
    }})

email_result = apis.gmail.send_email(
    access_token=tokens["gmail"],
    email_addresses=target_emails,
    subject=email_subject,
    body=email_body,
)
if "email_id" not in email_result and "email_thread_id" not in email_result:
    if "sent_email_id" not in email_result and "sent_email_thread_id" not in email_result:
        raise Exception(f"Unable to send Gmail message: {{email_result}}")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "relationships": relationships,
    "amount": amount,
    "note": note,
    "target_emails": target_emails,
    "transaction_count": len(transactions),
    "transactions": transactions,
    "bank_transfer_id": bank_transfer_id,
    "email_result": email_result,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_pay_coworkers_and_email",
    )


def handle_venmo_accept_named_carpool_request_this_month(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    first_name = frame.get("person_first_name")
    if not first_name:
        frame.abstain_reason = "missing_venmo_carpool_first_name"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
first_name = {json.dumps(str(first_name))}
first_name_lower = first_name.lower()
contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    query=first_name,
    page_index=page,
    page_limit=20,
))
candidate_emails = {{
    (contact.get("email") or "").strip().lower()
    for contact in contacts
    if (contact.get("first_name") or "").strip().lower() == first_name_lower
    and (contact.get("email") or "").strip()
}}
if not candidate_emails:
    users = apis.venmo.search_users(
        access_token=tokens["venmo"],
        query=first_name,
        page_limit=20,
    )
    candidate_emails = {{
        (user.get("email") or "").strip().lower()
        for user in users
        if (user.get("first_name") or "").strip().lower() == first_name_lower
        and (user.get("email") or "").strip()
    }}
now = DateTime.now()
month_start = now.start_of("month")
requests = paged(lambda page: apis.venmo.show_received_payment_requests(
    access_token=tokens["venmo"],
    status="pending",
    page_index=page,
    page_limit=20,
))
matching_requests = []
for request in requests:
    sender_email = ((request.get("sender") or {{}}).get("email") or "").strip().lower()
    if sender_email not in candidate_emails:
        continue
    created_at = DateTime.fromisoformat(request["created_at"])
    if created_at < month_start or created_at > now:
        continue
    description = str(request.get("description") or "").lower()
    if "carpool" not in description and "work" not in description:
        continue
    matching_requests.append(request)
if len(matching_requests) != 1:
    raise Exception(f"Expected exactly one pending carpool request from {{first_name}}, found {{len(matching_requests)}}.")
request = matching_requests[0]
payment_request_id = request["payment_request_id"]
amount = float(request["amount"])
account = apis.venmo.show_account(access_token=tokens["venmo"])
failed_api_attempts = 0
current_balance = float(account.get("venmo_balance") or 0)
bank_transfer_id = None
if current_balance + 1e-9 < amount:
    refill_amount = round(amount - current_balance, 2)
    cards = [
        card
        for card in apis.venmo.show_payment_cards(access_token=tokens["venmo"])
        if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
    ]
    cards = sorted(cards, key=lambda card: card["payment_card_id"], reverse=True)
    for card in cards:
        refill_result = apis.venmo.add_to_venmo_balance(
            access_token=tokens["venmo"],
            amount=refill_amount,
            payment_card_id=card["payment_card_id"],
        )
        if "bank_transfer_id" in refill_result:
            bank_transfer_id = refill_result["bank_transfer_id"]
            break
        failed_api_attempts += 1
    if bank_transfer_id is None:
        existing_card_numbers = {{str(card.get("card_number")) for card in cards}}
        supervisor_cards = sorted(
            apis.supervisor.show_payment_cards(),
            key=lambda card: (card["expiry_year"], card["expiry_month"], str(card["card_number"])),
            reverse=True,
        )
        for supervisor_card in supervisor_cards:
            if str(supervisor_card.get("card_number")) in existing_card_numbers:
                continue
            add_result = apis.venmo.add_payment_card(
                access_token=tokens["venmo"],
                card_name=supervisor_card["card_name"],
                owner_name=supervisor_card["owner_name"],
                card_number=supervisor_card["card_number"],
                expiry_year=supervisor_card["expiry_year"],
                expiry_month=supervisor_card["expiry_month"],
                cvv_number=supervisor_card["cvv_number"],
            )
            if "payment_card_id" not in add_result:
                refill_result = add_result
                failed_api_attempts += 1
                continue
            refill_result = apis.venmo.add_to_venmo_balance(
                access_token=tokens["venmo"],
                amount=refill_amount,
                payment_card_id=add_result["payment_card_id"],
            )
            if "bank_transfer_id" in refill_result:
                bank_transfer_id = refill_result["bank_transfer_id"]
                break
            failed_api_attempts += 1
    if bank_transfer_id is None:
        raise Exception(f"Unable to refill Venmo balance for carpool request: {{refill_result}}")
result = apis.venmo.approve_payment_request(
    access_token=tokens["venmo"],
    payment_request_id=payment_request_id,
)
if not (isinstance(result, dict) and result.get("message")):
    raise Exception(f"Unable to approve payment request {{payment_request_id}}: {{result}}")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"first_name": first_name, "approved_id": payment_request_id, "amount": amount, "bank_transfer_id": bank_transfer_id, "failed_api_attempts": failed_api_attempts}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_accept_named_carpool_request_this_month",
    )


def handle_venmo_correct_housing_bill_request(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    percent = frame.get("percent")
    adjustment = frame.get("adjustment")
    note = frame.get("note")
    if percent is None or adjustment not in {"increase", "decrease"} or not note:
        frame.abstain_reason = "missing_venmo_housing_correction_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
percent = {float(percent)}
adjustment = {json.dumps(str(adjustment))}
note = {json.dumps(str(note))}
roommate_emails = set()
for contact in paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship="roommate",
    page_index=page,
    page_limit=20,
)):
    email = (contact.get("email") or "").strip().lower()
    if email:
        roommate_emails.add(email)
now = DateTime.now()
month_start = now.start_of("month")
month_end = now.end_of("month")
requests = paged(lambda page: apis.venmo.show_received_payment_requests(
    access_token=tokens["venmo"],
    status="pending",
    page_index=page,
    page_limit=20,
))
matching_requests = []
for request in requests:
    sender_email = ((request.get("sender") or {{}}).get("email") or "").strip().lower()
    if sender_email not in roommate_emails:
        continue
    created_at = DateTime.fromisoformat(request["created_at"])
    if created_at < month_start or created_at > month_end:
        continue
    description = str(request.get("description") or "").lower()
    if not any(keyword in description for keyword in ["housing", "rent", "bill"]):
        continue
    matching_requests.append(request)
if not matching_requests:
    raise Exception("No housing bill request from a roommate found in the active month.")
matching_requests = sorted(matching_requests, key=lambda item: item["created_at"], reverse=True)
request = matching_requests[0]
sender_email = ((request.get("sender") or {{}}).get("email") or "").strip().lower()
original_amount = float(request["amount"])
factor = 1 + percent / 100.0 if adjustment == "increase" else 1 - percent / 100.0
corrected_amount = round(original_amount * factor, 2)
apis.venmo.deny_payment_request(
    access_token=tokens["venmo"],
    payment_request_id=request["payment_request_id"],
)
transaction_args = {{
    "access_token": tokens["venmo"],
    "receiver_email": sender_email,
    "amount": corrected_amount,
    "private": bool(request.get("private")),
    "description": note,
}}
account = apis.venmo.show_account(access_token=tokens["venmo"])
failed_api_attempts = 0
if float(account.get("venmo_balance") or 0) >= corrected_amount:
    result = apis.venmo.create_transaction(**transaction_args)
else:
    result = {{"message": "No non-expired payment card available."}}
    cards = [
        card
        for card in apis.venmo.show_payment_cards(access_token=tokens["venmo"])
        if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
    ]
    cards = sorted(cards, key=lambda card: card["payment_card_id"], reverse=True)
    for card in cards:
        transaction_args["payment_card_id"] = card["payment_card_id"]
        result = apis.venmo.create_transaction(**transaction_args)
        if "transaction_id" in result:
            break
        failed_api_attempts += 1
if "transaction_id" not in result:
    raise Exception(f"Unable to create corrected Venmo transaction: {{result}}")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"denied_id": request["payment_request_id"], "sender_email": sender_email, "original_amount": original_amount, "corrected_amount": corrected_amount, "note": note, "failed_api_attempts": failed_api_attempts, "result": result}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_correct_housing_bill_request",
    )


def handle_venmo_approve_requests_and_withdraw_balance(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    date_window = frame.get("date_window")
    card_last4 = frame.get("card_last4")
    if date_window not in {"this_month", "this_or_the_last_month"} or not card_last4:
        frame.abstain_reason = "missing_venmo_approve_withdraw_slots"
        return None
    code = common_appworld_prelude(["venmo"]) + f"""
date_window = {json.dumps(str(date_window))}
card_last4 = {json.dumps(str(card_last4))}
now = DateTime.now()
if date_window == "this_month":
    start = now.start_of("month")
else:
    start = now.subtract(months=1).start_of("month")
requests = paged(lambda page: apis.venmo.show_received_payment_requests(
    access_token=tokens["venmo"],
    status="pending",
    page_index=page,
    page_limit=20,
))
cards = [
    card
    for card in apis.venmo.show_payment_cards(access_token=tokens["venmo"])
    if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
]
cards = sorted(cards, key=lambda card: card["payment_card_id"], reverse=True)
target_card = None
for card in cards:
    digits = str(card.get("last_four_digits") or card.get("card_number") or "").replace(".0", "")
    if digits.endswith(card_last4):
        target_card = card
        break
if target_card is None:
    raise Exception(f"No non-expired Venmo payment card ending in {{card_last4}}.")
approved_ids = []
failed_api_attempts = 0
account = apis.venmo.show_account(access_token=tokens["venmo"])
remaining_balance = float(account.get("venmo_balance") or 0)
for request in requests:
    created_at = DateTime.fromisoformat(request["created_at"])
    if created_at < start or created_at > now:
        continue
    payment_request_id = request["payment_request_id"]
    amount = float(request["amount"])
    if remaining_balance >= amount:
        result = apis.venmo.approve_payment_request(
            access_token=tokens["venmo"],
            payment_request_id=payment_request_id,
        )
        remaining_balance -= amount
    else:
        result = {{"message": "No non-expired payment card available."}}
        for card in cards:
            result = apis.venmo.approve_payment_request(
                access_token=tokens["venmo"],
                payment_request_id=payment_request_id,
                payment_card_id=card["payment_card_id"],
            )
            if isinstance(result, dict) and result.get("message"):
                break
            failed_api_attempts += 1
    if not (isinstance(result, dict) and result.get("message")):
        raise Exception(f"Unable to approve payment request {{payment_request_id}}: {{result}}")
    approved_ids.append(payment_request_id)
account = apis.venmo.show_account(access_token=tokens["venmo"])
withdraw_amount = round(float(account.get("venmo_balance") or 0), 2)
withdraw_result = {{"message": "No balance to withdraw."}}
if withdraw_amount > 0:
    withdraw_result = apis.venmo.withdraw_from_venmo_balance(
        access_token=tokens["venmo"],
        amount=withdraw_amount,
        payment_card_id=target_card["payment_card_id"],
    )
    if "bank_transfer_id" not in withdraw_result:
        raise Exception(f"Unable to withdraw Venmo balance: {{withdraw_result}}")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"date_window": date_window, "approved_ids": approved_ids, "card_last4": card_last4, "withdraw_amount": withdraw_amount, "withdraw_result": withdraw_result, "failed_api_attempts": failed_api_attempts}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_approve_requests_and_withdraw_balance",
    )


def handle_venmo_request_money_from_contact(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationships = frame.get("relationships", [])
    first_name = frame.get("person_first_name")
    amount = frame.get("amount")
    private = frame.get("private")
    note = frame.get("note")
    if len(relationships) != 1 or not first_name or amount is None or private is None or not note:
        frame.abstain_reason = "missing_venmo_request_money_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
relationship = {json.dumps(relationships[0])}
first_name = {json.dumps(str(first_name))}
amount = {json.dumps(float(amount))}
private = {repr(bool(private))}
note = {json.dumps(str(note))}
contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    query=first_name,
    relationship=relationship,
    page_index=page,
    page_limit=20,
))
first_name_lower = first_name.lower()
matching_contacts = [
    contact
    for contact in contacts
    if (contact.get("first_name") or "").lower() == first_name_lower
]
if not matching_contacts:
    contacts = paged(lambda page: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship=relationship,
        page_index=page,
        page_limit=20,
    ))
    matching_contacts = [
        contact
        for contact in contacts
        if (contact.get("first_name") or "").lower() == first_name_lower
    ]
if not matching_contacts:
    raise Exception(f"No {{relationship}} contact found with first name {{first_name}}.")
email = (matching_contacts[0].get("email") or "").lower()
if not email:
    raise Exception(f"Contact {{first_name}} has no email address.")
venmo_users = apis.venmo.search_users(
    access_token=tokens["venmo"],
    query=email,
    page_limit=20,
)
matching_users = [user for user in venmo_users if (user.get("email") or "").lower() == email]
if not matching_users:
    raise Exception(f"No Venmo account found for {{email}}.")
result = apis.venmo.create_payment_request(
    access_token=tokens["venmo"],
    user_email=matching_users[0]["email"],
    amount=amount,
    description=note,
    private=private,
)
if "payment_request_id" not in result:
    raise Exception(f"Unable to create Venmo payment request: {{result}}")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"receiver_email": matching_users[0]["email"], "amount": amount, "private": private, "result": result}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_request_money_from_contact",
    )


def handle_venmo_settle_trip_note_debts(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationship = str(frame.get("relationship") or "").strip().lower()
    trip_name = str(frame.get("trip_name") or "").strip()
    note = str(frame.get("note") or "").strip()
    if relationship != "friend" or not trip_name or not note:
        frame.abstain_reason = "missing_venmo_trip_note_debt_slots"
        return None
    code = common_appworld_prelude(["phone", "simple_note", "venmo"]) + f"""
relationship = {json.dumps(relationship)}
trip_name = {json.dumps(trip_name)}
note = {json.dumps(note)}

def normalize_text(value):
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def name_key(value):
    return normalize_text(value)

def parse_money(value):
    cleaned = re.sub(r"[^0-9.]", "", str(value or ""))
    if not cleaned:
        raise Exception(f"Missing money amount in {{value!r}}")
    return round(float(cleaned), 2)

def add_debt(rows, direction, person_name, amount, source_line):
    person_name = str(person_name or "").strip(" .:-")
    if not person_name or person_name.lower() in {{"i", "me", "my"}}:
        return
    rows.append({{
        "direction": direction,
        "person_name": person_name,
        "amount": parse_money(amount),
        "source_line": source_line,
    }})

def parse_debt_rows(content):
    rows = []
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[#*\\-\\s]+", "", line).strip()
        sep = r"(?:=>|:|,|-)?"
        patterns = [
            ("pay", rf"^I\\s+owe\\s+(?P<name>[A-Za-z][A-Za-z .'-]*?)\\s*{{sep}}\\s*\\$?(?P<amount>\\d+(?:\\.\\d+)?)\\b"),
            ("request", rf"^(?P<name>[A-Za-z][A-Za-z .'-]*?)\\s+owes\\s+me\\s*{{sep}}\\s*\\$?(?P<amount>\\d+(?:\\.\\d+)?)\\b"),
            ("request", rf"^(?P<name>[A-Za-z][A-Za-z .'-]*?)\\s*{{sep}}\\s*owes\\s+me\\s*\\$?(?P<amount>\\d+(?:\\.\\d+)?)\\b"),
            ("pay", rf"^(?:pay|send)\\s+(?P<name>[A-Za-z][A-Za-z .'-]*?)\\s*{{sep}}\\s*\\$?(?P<amount>\\d+(?:\\.\\d+)?)\\b"),
            ("request", rf"^(?:request|collect)\\s+(?:from\\s+)?(?P<name>[A-Za-z][A-Za-z .'-]*?)\\s*{{sep}}\\s*\\$?(?P<amount>\\d+(?:\\.\\d+)?)\\b"),
            ("pay", rf"^(?P<name>[A-Za-z][A-Za-z .'-]*?)\\s*{{sep}}\\s*(?:I\\s+owe|owed by me)\\s*\\$?(?P<amount>\\d+(?:\\.\\d+)?)\\b"),
            ("request", rf"^(?P<name>[A-Za-z][A-Za-z .'-]*?)\\s*{{sep}}\\s*(?:owes me|owed to me)\\s*\\$?(?P<amount>\\d+(?:\\.\\d+)?)\\b"),
        ]
        for direction, pattern in patterns:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                add_debt(rows, direction, match.group("name"), match.group("amount"), raw_line)
                break
    return rows

def exact_venmo_email(email):
    users = paged(lambda page: apis.venmo.search_users(
        access_token=tokens["venmo"],
        query=email,
        page_index=page,
        page_limit=20,
    ))
    matches = [user for user in users if str(user.get("email") or "").strip().lower() == email]
    if len(matches) != 1:
        raise Exception(f"Expected exactly one Venmo user for {{email}}, found {{len(matches)}}")
    return str(matches[0]["email"]).strip().lower()

def create_transaction_with_refill(receiver_email, amount, description):
    transaction_args = {{
        "access_token": tokens["venmo"],
        "receiver_email": receiver_email,
        "amount": amount,
        "description": description,
        "private": True,
    }}
    account = apis.venmo.show_account(access_token=tokens["venmo"])
    failed_attempts = 0
    if float(account.get("venmo_balance") or 0) >= amount:
        result = apis.venmo.create_transaction(**transaction_args)
    else:
        result = {{"message": "No non-expired payment card available."}}
        cards = [
            card
            for card in apis.venmo.show_payment_cards(access_token=tokens["venmo"])
            if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
        ]
        cards = sorted(
            cards,
            key=lambda card: (
                float(card.get("balance") or 0),
                card["expiry_year"],
                card["expiry_month"],
                card["payment_card_id"],
            ),
            reverse=True,
        )
        for card in cards:
            transaction_args["payment_card_id"] = card["payment_card_id"]
            result = apis.venmo.create_transaction(**transaction_args)
            if "transaction_id" in result:
                break
            failed_attempts += 1
        if "transaction_id" not in result:
            existing_card_numbers = {{str(card.get("card_number")) for card in cards}}
            supervisor_cards = sorted(
                apis.supervisor.show_payment_cards(),
                key=lambda card: (
                    float(card.get("balance") or 0),
                    card["expiry_year"],
                    card["expiry_month"],
                    str(card["card_number"]),
                ),
                reverse=True,
            )
            for supervisor_card in supervisor_cards:
                if str(supervisor_card.get("card_number")) in existing_card_numbers:
                    continue
                add_result = apis.venmo.add_payment_card(
                    access_token=tokens["venmo"],
                    card_name=supervisor_card["card_name"],
                    owner_name=supervisor_card["owner_name"],
                    card_number=supervisor_card["card_number"],
                    expiry_year=supervisor_card["expiry_year"],
                    expiry_month=supervisor_card["expiry_month"],
                    cvv_number=supervisor_card["cvv_number"],
                )
                if "payment_card_id" not in add_result:
                    result = add_result
                    failed_attempts += 1
                    continue
                transaction_args["payment_card_id"] = add_result["payment_card_id"]
                result = apis.venmo.create_transaction(**transaction_args)
                if "transaction_id" in result:
                    break
                failed_attempts += 1
    if "transaction_id" not in result:
        raise Exception(f"Unable to create Venmo transaction to {{receiver_email}}: {{result}}")
    return result, failed_attempts

trip_key = normalize_text(trip_name)
notes = paged(lambda page: apis.simple_note.search_notes(
    access_token=tokens["simple_note"],
    page_index=page,
    page_limit=20,
    dont_reorder_pinned=True,
))
candidate_notes = []
for short_note in notes:
    full_note = apis.simple_note.show_note(
        access_token=tokens["simple_note"],
        note_id=short_note["note_id"],
    )
    haystack = normalize_text(str(full_note.get("title") or "") + " " + str(full_note.get("content") or ""))
    if trip_key in haystack and ("owe" in haystack or "owed" in haystack):
        parsed_rows = parse_debt_rows(full_note.get("content"))
        if parsed_rows:
            candidate_notes.append({{"note": full_note, "rows": parsed_rows}})
if len(candidate_notes) != 1:
    raise Exception(f"Expected one Simple Note debt note for trip {{trip_name}}, found {{len(candidate_notes)}}")

contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship=relationship,
    page_index=page,
    page_limit=20,
))
contacts_by_name = {{}}
for contact in contacts:
    names = [
        contact.get("first_name"),
        contact.get("last_name"),
        " ".join(
            part for part in [contact.get("first_name"), contact.get("last_name")]
            if part
        ),
    ]
    for name in names:
        key = name_key(name)
        if key:
            contacts_by_name.setdefault(key, []).append(contact)

def contact_email_for(display_name):
    key = name_key(display_name)
    matches = contacts_by_name.get(key, [])
    if not matches and key:
        first = key.split()[0]
        matches = contacts_by_name.get(first, [])
    unique = []
    seen = set()
    for contact in matches:
        email = str(contact.get("email") or "").strip().lower()
        if email and email not in seen:
            unique.append(contact)
            seen.add(email)
    if len(unique) != 1:
        raise Exception(f"Could not uniquely resolve friend {{display_name!r}}; found {{len(unique)}}")
    return str(unique[0]["email"]).strip().lower()

payments = []
requests = []
failed_api_attempts = 0
seen_actions = set()
for row in candidate_notes[0]["rows"]:
    email = contact_email_for(row["person_name"])
    venmo_email = exact_venmo_email(email)
    key = (row["direction"], venmo_email, row["amount"])
    if key in seen_actions:
        continue
    seen_actions.add(key)
    if row["direction"] == "pay":
        result, failures = create_transaction_with_refill(venmo_email, row["amount"], note)
        failed_api_attempts += failures
        payments.append({{
            "receiver_email": venmo_email,
            "amount": row["amount"],
            "transaction_id": result["transaction_id"],
        }})
    else:
        result = apis.venmo.create_payment_request(
            access_token=tokens["venmo"],
            user_email=venmo_email,
            amount=row["amount"],
            description=note,
            private=True,
        )
        if "payment_request_id" not in result:
            raise Exception(f"Unable to create Venmo request for {{venmo_email}}: {{result}}")
        requests.append({{
            "user_email": venmo_email,
            "amount": row["amount"],
            "payment_request_id": result["payment_request_id"],
        }})

if not payments and not requests:
    raise Exception(f"No Venmo actions produced for trip {{trip_name}}")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "trip_name": trip_name,
    "note": note,
    "payments": payments,
    "requests": requests,
    "failed_api_attempts": failed_api_attempts,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_settle_trip_note_debts",
    )


def handle_venmo_settle_roommate_dinner(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    taxi_total = frame.get("taxi_total")
    food_total = frame.get("food_total")
    food_payer_first_name = str(frame.get("food_payer_first_name") or "").strip()
    taxi_note = str(frame.get("taxi_note") or "").strip()
    food_note = str(frame.get("food_note") or "").strip()
    if (
        taxi_total is None
        or food_total is None
        or not food_payer_first_name
        or not taxi_note
        or not food_note
    ):
        frame.abstain_reason = "missing_roommate_dinner_settlement_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
taxi_total = {float(taxi_total)}
food_total = {float(food_total)}
food_payer_first_name = {json.dumps(food_payer_first_name)}
taxi_note = {json.dumps(taxi_note)}
food_note = {json.dumps(food_note)}

def exact_venmo_user_by_email(email):
    users = apis.venmo.search_users(
        access_token=tokens["venmo"],
        query=email,
        page_limit=20,
    )
    matches = [
        user for user in users
        if (user.get("email") or "").strip().lower() == email
    ]
    if len(matches) != 1:
        raise Exception(f"Expected exactly one Venmo user for {{email}}, found {{len(matches)}}.")
    return matches[0]

def create_transaction_with_refill(receiver_email, amount, note):
    transaction_args = {{
        "access_token": tokens["venmo"],
        "receiver_email": receiver_email,
        "amount": amount,
        "private": False,
        "description": note,
    }}
    account = apis.venmo.show_account(access_token=tokens["venmo"])
    failed_attempts = 0
    if float(account.get("venmo_balance") or 0) >= amount:
        result = apis.venmo.create_transaction(**transaction_args)
    else:
        result = {{"message": "No non-expired payment card available."}}
        cards = [
            card
            for card in apis.venmo.show_payment_cards(access_token=tokens["venmo"])
            if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
        ]
        cards = sorted(
            cards,
            key=lambda card: (
                float(card.get("balance") or 0),
                card["expiry_year"],
                card["expiry_month"],
                card["payment_card_id"],
            ),
            reverse=True,
        )
        for card in cards:
            transaction_args["payment_card_id"] = card["payment_card_id"]
            result = apis.venmo.create_transaction(**transaction_args)
            if "transaction_id" in result:
                break
            failed_attempts += 1
        if "transaction_id" not in result:
            existing_card_numbers = {{str(card.get("card_number")) for card in cards}}
            supervisor_cards = sorted(
                apis.supervisor.show_payment_cards(),
                key=lambda card: (
                    float(card.get("balance") or 0),
                    card["expiry_year"],
                    card["expiry_month"],
                    str(card["card_number"]),
                ),
                reverse=True,
            )
            for supervisor_card in supervisor_cards:
                if str(supervisor_card.get("card_number")) in existing_card_numbers:
                    continue
                add_result = apis.venmo.add_payment_card(
                    access_token=tokens["venmo"],
                    card_name=supervisor_card["card_name"],
                    owner_name=supervisor_card["owner_name"],
                    card_number=supervisor_card["card_number"],
                    expiry_year=supervisor_card["expiry_year"],
                    expiry_month=supervisor_card["expiry_month"],
                    cvv_number=supervisor_card["cvv_number"],
                )
                if "payment_card_id" not in add_result:
                    result = add_result
                    failed_attempts += 1
                    continue
                transaction_args["payment_card_id"] = add_result["payment_card_id"]
                result = apis.venmo.create_transaction(**transaction_args)
                if "transaction_id" in result:
                    break
                failed_attempts += 1
    if "transaction_id" not in result:
        raise Exception(f"Unable to create Venmo transaction to {{receiver_email}}: {{result}}")
    return result, failed_attempts

roommates = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship="roommate",
    page_index=page,
    page_limit=20,
))
roommate_emails = []
seen_emails = set()
for contact in roommates:
    email = (contact.get("email") or "").strip().lower()
    if not email or email in seen_emails:
        continue
    seen_emails.add(email)
    roommate_emails.append(email)
if len(roommate_emails) < 2:
    raise Exception(f"Expected at least two roommates, found {{len(roommate_emails)}}.")

food_payer_lower = food_payer_first_name.lower()
food_payer_contacts = [
    contact for contact in roommates
    if (contact.get("first_name") or "").strip().lower() == food_payer_lower
]
if len(food_payer_contacts) != 1:
    raise Exception(f"Expected exactly one roommate named {{food_payer_first_name}}, found {{len(food_payer_contacts)}}.")
food_payer_email = (food_payer_contacts[0].get("email") or "").strip().lower()
if not food_payer_email:
    raise Exception(f"Roommate {{food_payer_first_name}} has no email.")

for email in roommate_emails:
    exact_venmo_user_by_email(email)

participant_count = len(roommate_emails) + 1
taxi_share = round(taxi_total / participant_count, 2)
food_share = round(food_total / participant_count, 2)
requests = []
for email in roommate_emails:
    result = apis.venmo.create_payment_request(
        access_token=tokens["venmo"],
        user_email=email,
        amount=taxi_share,
        description=taxi_note,
        private=False,
    )
    if "payment_request_id" not in result:
        raise Exception(f"Unable to create taxi payment request for {{email}}: {{result}}")
    requests.append({{"email": email, "amount": taxi_share, "result": result}})

payment_result, failed_api_attempts = create_transaction_with_refill(
    food_payer_email,
    food_share,
    food_note,
)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "participant_count": participant_count,
    "taxi_share": taxi_share,
    "food_share": food_share,
    "food_payer_email": food_payer_email,
    "requests": requests,
    "payment_result": payment_result,
    "failed_api_attempts": failed_api_attempts,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_settle_roommate_dinner",
    )


def handle_venmo_send_to_each_relationship_with_refill(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationships = frame.get("relationships", [])
    amount = frame.get("amount")
    note = frame.get("note")
    if not relationships or amount is None or not note:
        frame.abstain_reason = "missing_venmo_relationship_payment_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
relationships = {json.dumps(relationships)}
amount = {float(amount)}
note = {json.dumps(str(note))}
target_emails = []
seen_emails = set()
for relationship in relationships:
    contacts = paged(lambda page, relationship=relationship: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship=relationship,
        page_index=page,
        page_limit=20,
    ))
    for contact in contacts:
        email = (contact.get("email") or "").lower()
        if not email or email in seen_emails:
            continue
        venmo_users = apis.venmo.search_users(
            access_token=tokens["venmo"],
            query=email,
            page_limit=20,
        )
        if any((user.get("email") or "").lower() == email for user in venmo_users):
            seen_emails.add(email)
            target_emails.append(email)
if not target_emails:
    raise Exception(f"No Venmo users found for relationships: {{relationships}}")
total_needed = round(amount * len(target_emails), 2)
account = apis.venmo.show_account(access_token=tokens["venmo"])
starting_balance = float(account.get("venmo_balance") or 0)
bank_transfer_id = None
if starting_balance + 1e-9 < total_needed:
    refill_amount = round(total_needed - starting_balance, 2)
    cards = sorted(
        apis.venmo.show_payment_cards(access_token=tokens["venmo"]),
        key=lambda card: card["payment_card_id"],
        reverse=True,
    )
    refill_result = {{"message": "No Venmo payment card could fund the refill."}}
    for card in cards:
        refill_result = apis.venmo.add_to_venmo_balance(
            access_token=tokens["venmo"],
            amount=refill_amount,
            payment_card_id=card["payment_card_id"],
        )
        if "bank_transfer_id" in refill_result:
            bank_transfer_id = refill_result["bank_transfer_id"]
            break
    if bank_transfer_id is None:
        existing_card_numbers = {{str(card.get("card_number")) for card in cards}}
        supervisor_cards = sorted(
            apis.supervisor.show_payment_cards(),
            key=lambda card: (card["expiry_year"], card["expiry_month"], str(card["card_number"])),
            reverse=True,
        )
        for supervisor_card in supervisor_cards:
            if str(supervisor_card.get("card_number")) in existing_card_numbers:
                continue
            add_result = apis.venmo.add_payment_card(
                access_token=tokens["venmo"],
                card_name=supervisor_card["card_name"],
                owner_name=supervisor_card["owner_name"],
                card_number=supervisor_card["card_number"],
                expiry_year=supervisor_card["expiry_year"],
                expiry_month=supervisor_card["expiry_month"],
                cvv_number=supervisor_card["cvv_number"],
            )
            if "payment_card_id" not in add_result:
                refill_result = add_result
                continue
            refill_result = apis.venmo.add_to_venmo_balance(
                access_token=tokens["venmo"],
                amount=refill_amount,
                payment_card_id=add_result["payment_card_id"],
            )
            if "bank_transfer_id" in refill_result:
                bank_transfer_id = refill_result["bank_transfer_id"]
                break
    if bank_transfer_id is None:
        raise Exception(f"Unable to refill Venmo balance: {{refill_result}}")
transaction_ids = []
for email in target_emails:
    result = apis.venmo.create_transaction(
        access_token=tokens["venmo"],
        receiver_email=email,
        amount=amount,
        description=note,
        private=False,
    )
    if "transaction_id" not in result:
        raise Exception(f"Unable to create Venmo transaction for {{email}}: {{result}}")
    transaction_ids.append(result["transaction_id"])
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"relationships": relationships, "amount": amount, "note": note, "target_emails": target_emails, "transaction_ids": transaction_ids, "bank_transfer_id": bank_transfer_id}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_send_to_each_relationship_with_refill",
    )


def handle_file_update_reunion_rsvps_from_phone(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    directory_path = str(frame.get("directory_path") or "").strip()
    if directory_path not in {
        "~/documents/personal/",
        "~/documents/personal_stuff/",
        "~/documents/personal_files/",
    }:
        frame.abstain_reason = "missing_or_unsupported_reunion_rsvp_directory"
        return None
    code = common_appworld_prelude(["phone", "file_system"]) + f"""
directory_path = {json.dumps(directory_path)}

def split_csv_line(line):
    cells = []
    current = ""
    in_quote = False
    index = 0
    while index < len(line):
        character = line[index]
        if character == '"':
            if in_quote and index + 1 < len(line) and line[index + 1] == '"':
                current += '"'
                index += 1
            else:
                in_quote = not in_quote
        elif character == "," and not in_quote:
            cells.append(current)
            current = ""
        else:
            current += character
        index += 1
    cells.append(current)
    return cells

def csv_escape(value):
    text = str(value)
    if any(character in text for character in [",", '"', "\\n", "\\r"]):
        text = '"' + text.replace('"', '""') + '"'
    return text

def classify_rsvp(message):
    text = str(message or "").lower()
    negative_markers = [
        "can't join",
        "cannot make",
        "can't make",
        "have to miss",
        "sorry",
        "other commitment",
        "other commitments",
        "other plans",
    ]
    positive_markers = [
        "i'll be there",
        "i will be there",
        "yes",
        "looking forward",
        "at the reunion",
        "be at the reunion",
    ]
    if any(marker in text for marker in negative_markers):
        return "no"
    if any(marker in text for marker in positive_markers):
        return "yes"
    return ""

file_paths = apis.file_system.show_directory(
    access_token=tokens["file_system"],
    directory_path=directory_path,
    entry_type="files",
    recursive=True,
)
candidate_files = []
for file_path in file_paths:
    if not str(file_path).lower().endswith(".csv"):
        continue
    file_info = apis.file_system.show_file(
        access_token=tokens["file_system"],
        file_path=file_path,
    )
    content = str(file_info.get("content") or "")
    if "RSVP" in content and "Invited" in content:
        candidate_files.append((file_path, content))
if len(candidate_files) != 1:
    raise Exception(f"Expected exactly one reunion RSVP CSV in {{directory_path}}, found {{len(candidate_files)}}.")
file_path, content = candidate_files[0]
lines = [line for line in content.splitlines() if line.strip()]
if not lines:
    raise Exception(f"RSVP CSV is empty: {{file_path}}")
headers = split_csv_line(lines[0])
rows = [split_csv_line(line) for line in lines[1:]]
try:
    name_index = headers.index("Name")
    rsvp_index = headers.index("RSVP (unknown/yes/no)")
except ValueError as exc:
    raise Exception(f"RSVP CSV has unsupported headers: {{headers}}") from exc
invitee_names = [row[name_index].strip() for row in rows if len(row) > name_index and row[name_index].strip()]

messages = paged(lambda page: apis.phone.search_text_messages(
    access_token=tokens["phone"],
    page_index=page,
    page_limit=20,
    sort_by="+created_at",
))
invitation_times = [
    message["sent_at"]
    for message in messages
    if ((message.get("sender") or {{}}).get("phone_number") or "") == profile["phone_number"]
    and "organizing a reunion party" in str(message.get("message") or "").lower()
]
if not invitation_times:
    raise Exception("No outbound reunion invitation phone messages found.")
invite_start = min(invitation_times)

latest_by_first_name = {{}}
for message in messages:
    if message["sent_at"] < invite_start:
        continue
    sender = message.get("sender") or {{}}
    sender_name = str(sender.get("name") or "")
    first_name = sender_name.split()[0] if sender_name else ""
    if first_name not in invitee_names:
        continue
    rsvp = classify_rsvp(message.get("message"))
    if not rsvp:
        continue
    latest_by_first_name[first_name] = {{
        "rsvp": rsvp,
        "sent_at": message["sent_at"],
        "message_id": message["text_message_id"],
    }}

missing = [name for name in invitee_names if name not in latest_by_first_name]
if missing:
    raise Exception(f"Missing latest RSVP replies for invitees: {{missing}}")

updated_rows = []
for row in rows:
    while len(row) < len(headers):
        row.append("")
    name = row[name_index].strip()
    if name in latest_by_first_name:
        row[rsvp_index] = latest_by_first_name[name]["rsvp"]
    updated_rows.append(row)
new_content = "\\n".join(
    ",".join(csv_escape(cell) for cell in line)
    for line in [headers] + updated_rows
)
apis.file_system.update_file(
    access_token=tokens["file_system"],
    file_path=file_path,
    content=new_content,
)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"file_path": file_path, "updated": latest_by_first_name}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_file_update_reunion_rsvps_from_phone",
    )


def handle_venmo_birthday_child_payment_and_text(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationship = frame.get("relationship")
    multiplier = frame.get("multiplier")
    note = frame.get("note")
    message = frame.get("message")
    if relationship not in {"son", "daughter"} or multiplier is None or not note or not message:
        frame.abstain_reason = "missing_venmo_birthday_child_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
relationship = {json.dumps(str(relationship))}
multiplier = {float(multiplier)}
note = {json.dumps(str(note))}
message = {json.dumps(str(message))}
now = DateTime.now()
today_month = now.month
today_day = now.day
contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship=relationship,
    page_index=page,
    page_limit=20,
))
matching_contacts = []
for contact in contacts:
    birthday = str(contact.get("birthday") or "")
    try:
        birthday_dt = DateTime.fromisoformat(birthday)
    except Exception:
        continue
    if birthday_dt.month == today_month and birthday_dt.day == today_day:
        matching_contacts.append(contact)
if len(matching_contacts) != 1:
    raise Exception(f"Expected exactly one {{relationship}} with birthday today, found {{len(matching_contacts)}}.")
contact = matching_contacts[0]
receiver_email = (contact.get("email") or "").strip().lower()
if not receiver_email:
    raise Exception("Birthday child contact has no email.")
venmo_users = apis.venmo.search_users(
    access_token=tokens["venmo"],
    query=receiver_email,
    page_limit=20,
)
matching_users = [
    user for user in venmo_users
    if (user.get("email") or "").strip().lower() == receiver_email
]
if len(matching_users) != 1:
    raise Exception(f"Expected exactly one Venmo account for {{receiver_email}}, found {{len(matching_users)}}.")
phone_number = contact.get("phone_number")
if not phone_number:
    raise Exception("Birthday child contact has no phone number.")
previous_birthday = DateTime(now.year - 1, today_month, today_day)
transactions = paged(lambda page: apis.venmo.show_transactions(
    access_token=tokens["venmo"],
    page_index=page,
    page_limit=20,
))
previous_matches = []
for transaction in transactions:
    sender_email = ((transaction.get("sender") or {{}}).get("email") or "").strip().lower()
    transaction_receiver = ((transaction.get("receiver") or {{}}).get("email") or "").strip().lower()
    if sender_email != user.email.lower() or transaction_receiver != receiver_email:
        continue
    created_at = DateTime.fromisoformat(transaction["created_at"])
    if created_at.year != previous_birthday.year:
        continue
    if created_at.month != previous_birthday.month or created_at.day != previous_birthday.day:
        continue
    previous_matches.append(transaction)
if len(previous_matches) != 1:
    raise Exception(f"Expected exactly one prior birthday Venmo transaction to {{receiver_email}}, found {{len(previous_matches)}}.")
previous_transaction = previous_matches[0]
amount = round(float(previous_transaction["amount"]) * multiplier, 2)
account = apis.venmo.show_account(access_token=tokens["venmo"])
starting_balance = float(account.get("venmo_balance") or 0)
bank_transfer_id = None
failed_api_attempts = 0
if starting_balance + 1e-9 < amount:
    refill_amount = round(amount - starting_balance, 2)
    cards = [
        card
        for card in apis.venmo.show_payment_cards(access_token=tokens["venmo"])
        if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
    ]
    cards = sorted(
        cards,
        key=lambda card: (
            float(card.get("balance") or 0),
            card["expiry_year"],
            card["expiry_month"],
            card["payment_card_id"],
        ),
        reverse=True,
    )
    refill_result = {{"message": "No non-expired payment card available."}}
    for card in cards:
        refill_result = apis.venmo.add_to_venmo_balance(
            access_token=tokens["venmo"],
            amount=refill_amount,
            payment_card_id=card["payment_card_id"],
        )
        if "bank_transfer_id" in refill_result:
            bank_transfer_id = refill_result["bank_transfer_id"]
            break
        failed_api_attempts += 1
    if bank_transfer_id is None:
        existing_card_numbers = {{str(card.get("card_number")) for card in cards}}
        supervisor_cards = sorted(
            apis.supervisor.show_payment_cards(),
            key=lambda card: (
                float(card.get("balance") or 0),
                card["expiry_year"],
                card["expiry_month"],
                str(card["card_number"]),
            ),
            reverse=True,
        )
        for supervisor_card in supervisor_cards:
            if str(supervisor_card.get("card_number")) in existing_card_numbers:
                continue
            add_result = apis.venmo.add_payment_card(
                access_token=tokens["venmo"],
                card_name=supervisor_card["card_name"],
                owner_name=supervisor_card["owner_name"],
                card_number=supervisor_card["card_number"],
                expiry_year=supervisor_card["expiry_year"],
                expiry_month=supervisor_card["expiry_month"],
                cvv_number=supervisor_card["cvv_number"],
            )
            if "payment_card_id" not in add_result:
                refill_result = add_result
                failed_api_attempts += 1
                continue
            refill_result = apis.venmo.add_to_venmo_balance(
                access_token=tokens["venmo"],
                amount=refill_amount,
                payment_card_id=add_result["payment_card_id"],
            )
            if "bank_transfer_id" in refill_result:
                bank_transfer_id = refill_result["bank_transfer_id"]
                break
            failed_api_attempts += 1
    if bank_transfer_id is None:
        raise Exception(f"Unable to refill Venmo balance for birthday payment: {{refill_result}}")
result = apis.venmo.create_transaction(
    access_token=tokens["venmo"],
    receiver_email=receiver_email,
    amount=amount,
    description=note,
    private=True,
)
if "transaction_id" not in result:
    raise Exception(f"Unable to create birthday Venmo transaction: {{result}}")
text_result = apis.phone.send_text_message(
    access_token=tokens["phone"],
    phone_number=phone_number,
    message=message,
)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "relationship": relationship,
    "receiver_email": receiver_email,
    "phone_number": phone_number,
    "previous_amount": float(previous_transaction["amount"]),
    "multiplier": multiplier,
    "amount": amount,
    "note": note,
    "transaction_id": result["transaction_id"],
    "bank_transfer_id": bank_transfer_id,
    "failed_api_attempts": failed_api_attempts,
    "text_result": text_result,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_birthday_child_payment_and_text",
    )


def handle_venmo_correct_sent_requests_yesterday_evening(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationships = frame.get("relationships", [])
    adjustment = frame.get("adjustment")
    difference_amount = frame.get("difference_amount")
    if len(relationships) != 1 or adjustment not in {"increase", "decrease"} or difference_amount is None:
        frame.abstain_reason = "missing_venmo_sent_request_correction_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
relationship = {json.dumps(str(relationships[0]))}
adjustment = {json.dumps(str(adjustment))}
difference_amount = {float(difference_amount)}
now = DateTime.now()
yesterday = now.subtract(days=1).date()
target_emails = set()
for contact in paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship=relationship,
    page_index=page,
    page_limit=20,
)):
    email = (contact.get("email") or "").strip().lower()
    if email:
        target_emails.add(email)
requests = paged(lambda page: apis.venmo.show_sent_payment_requests(
    access_token=tokens["venmo"],
    status="pending",
    page_index=page,
    page_limit=20,
))
matching = []
for request in requests:
    receiver_email = ((request.get("receiver") or {{}}).get("email") or "").strip().lower()
    if receiver_email not in target_emails:
        continue
    created_at = DateTime.fromisoformat(request["created_at"])
    if created_at.date() != yesterday:
        continue
    if created_at.hour < 17:
        continue
    matching.append(request)
if not matching:
    raise Exception(f"No pending sent Venmo requests found for {{relationship}}s yesterday evening.")
amounts = {{round(float(request["amount"]), 2) for request in matching}}
descriptions = {{str(request.get("description") or "") for request in matching}}
if len(amounts) != 1 or len(descriptions) != 1:
    raise Exception(f"Ambiguous yesterday-evening requests: amounts={{sorted(amounts)}}, descriptions={{sorted(descriptions)}}")
deleted_ids = []
created_ids = []
for request in sorted(matching, key=lambda item: item["payment_request_id"]):
    old_amount = float(request["amount"])
    corrected_amount = round(
        old_amount + difference_amount if adjustment == "increase" else old_amount - difference_amount,
        2,
    )
    if corrected_amount <= 0:
        raise Exception(f"Corrected amount must be positive, got {{corrected_amount}}.")
    payment_request_id = request["payment_request_id"]
    delete_result = apis.venmo.delete_payment_request(
        access_token=tokens["venmo"],
        payment_request_id=payment_request_id,
    )
    if not (isinstance(delete_result, dict) and delete_result.get("message")):
        raise Exception(f"Unable to delete payment request {{payment_request_id}}: {{delete_result}}")
    deleted_ids.append(payment_request_id)
    receiver_email = ((request.get("receiver") or {{}}).get("email") or "").strip().lower()
    create_result = apis.venmo.create_payment_request(
        access_token=tokens["venmo"],
        user_email=receiver_email,
        amount=corrected_amount,
        private=bool(request.get("private")),
        description=request.get("description") or "",
    )
    if "payment_request_id" not in create_result:
        raise Exception(f"Unable to create corrected payment request for {{receiver_email}}: {{create_result}}")
    created_ids.append(create_result["payment_request_id"])
apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "relationship": relationship,
    "adjustment": adjustment,
    "difference_amount": difference_amount,
    "deleted_ids": deleted_ids,
    "created_ids": created_ids,
    "count": len(created_ids),
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_correct_sent_requests_yesterday_evening",
    )


def handle_venmo_remind_old_payment_requests(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationships = frame.get("relationships", [])
    min_days = frame.get("min_days")
    if not relationships or min_days is None:
        frame.abstain_reason = "missing_venmo_reminder_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
relationships = {json.dumps(relationships)}
min_days = {int(min_days)}
target_emails = set()
for relationship in relationships:
    for contact in paged(lambda page: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship=relationship,
        page_index=page,
        page_limit=20,
    )):
        email = (contact.get("email") or "").lower()
        if email:
            target_emails.add(email)
requests = paged(lambda page: apis.venmo.show_sent_payment_requests(
    access_token=tokens["venmo"],
    status="pending",
    page_index=page,
    page_limit=20,
))
reminded = []
for request in requests:
    receiver_email = (request.get("receiver") or {{}}).get("email", "").lower()
    if receiver_email not in target_emails:
        continue
    created_at = DateTime.fromisoformat(request["created_at"])
    if (DateTime.now() - created_at).days < min_days:
        continue
    apis.venmo.remind_payment_request(
        access_token=tokens["venmo"],
        payment_request_id=request["payment_request_id"],
    )
    reminded.append(request["payment_request_id"])
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"min_days": min_days, "reminded_payment_request_ids": reminded, "count": len(reminded)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_remind_old_payment_requests",
    )


def handle_venmo_process_pending_payment_requests(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    decision = frame.get("decision")
    relationships = frame.get("relationships", [])
    if decision not in {"approve", "deny"} or not relationships:
        frame.abstain_reason = "missing_venmo_pending_request_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
decision = {json.dumps(decision)}
relationships = {json.dumps(relationships)}
target_emails = set()
for relationship in relationships:
    for contact in paged(lambda page: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship=relationship,
        page_index=page,
        page_limit=20,
    )):
        email = (contact.get("email") or "").lower()
        if email:
            target_emails.add(email)
requests = paged(lambda page: apis.venmo.show_received_payment_requests(
    access_token=tokens["venmo"],
    status="pending",
    page_index=page,
    page_limit=20,
))
acted = []
account = apis.venmo.show_account(access_token=tokens["venmo"])
remaining_balance = float(account.get("venmo_balance", 0) or 0)
cards = []
if decision == "approve" and remaining_balance <= 0:
    cards = [
        card
        for card in apis.venmo.show_payment_cards(access_token=tokens["venmo"])
        if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
    ]
for request in requests:
    sender_email = (request.get("sender") or {{}}).get("email", "").lower()
    if sender_email not in target_emails:
        continue
    payment_request_id = request["payment_request_id"]
    if decision == "approve":
        amount = float(request["amount"])
        if remaining_balance >= amount:
            apis.venmo.approve_payment_request(
                access_token=tokens["venmo"],
                payment_request_id=payment_request_id,
            )
            remaining_balance -= amount
        else:
            approved = False
            for card in cards:
                result = apis.venmo.approve_payment_request(
                    access_token=tokens["venmo"],
                    payment_request_id=payment_request_id,
                    payment_card_id=card["payment_card_id"],
                )
                if isinstance(result, dict) and result.get("message"):
                    approved = True
                    break
            if not approved:
                raise Exception(f"Unable to approve payment request {{payment_request_id}}.")
    else:
        apis.venmo.deny_payment_request(
            access_token=tokens["venmo"],
            payment_request_id=payment_request_id,
        )
    acted.append(payment_request_id)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"decision": decision, "processed_payment_request_ids": acted, "count": len(acted)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_process_pending_payment_requests",
    )


def handle_venmo_add_friends_by_relationships(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationships = frame.get("relationships", [])
    if not relationships:
        frame.abstain_reason = "missing_venmo_friend_relationship_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
relationships = {json.dumps(relationships)}
target_emails = set()
for relationship in relationships:
    for contact in paged(lambda page: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship=relationship,
        page_index=page,
        page_limit=20,
    )):
        email = (contact.get("email") or "").lower()
        if email:
            users = apis.venmo.search_users(
                access_token=tokens["venmo"],
                query=email,
                page_limit=20,
            )
            if any((user.get("email") or "").lower() == email for user in users):
                target_emails.add(email)
current_friends = paged(lambda page: apis.venmo.search_friends(
    access_token=tokens["venmo"],
    page_index=page,
    page_limit=20,
))
current_friend_emails = {{
    (friend.get("email") or "").lower()
    for friend in current_friends
    if friend.get("email")
}}
added = []
for email in sorted(target_emails):
    if email in current_friend_emails:
        continue
    apis.venmo.add_friend(
        access_token=tokens["venmo"],
        user_email=email,
    )
    added.append(email)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"relationships": relationships, "added_friend_emails": added, "count": len(added)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_add_friends_by_relationships",
    )


def handle_delete_phone_spam_messages(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    phone_number = frame.get("phone_number")
    if not phone_number:
        frame.abstain_reason = "missing_spam_phone_number"
        return None
    code = common_appworld_prelude(["phone"]) + f"""
spam_phone = {json.dumps(phone_number)}
text_messages = paged(lambda page: apis.phone.search_text_messages(
    access_token=tokens["phone"],
    phone_number=spam_phone,
    page_index=page,
    page_limit=20,
))
voice_messages = paged(lambda page: apis.phone.search_voice_messages(
    access_token=tokens["phone"],
    phone_number=spam_phone,
    page_index=page,
    page_limit=20,
))
deleted_text = []
for message in text_messages:
    apis.phone.delete_text_message(
        access_token=tokens["phone"],
        text_message_id=message["text_message_id"],
    )
    deleted_text.append(message["text_message_id"])
deleted_voice = []
for message in voice_messages:
    apis.phone.delete_voice_message(
        access_token=tokens["phone"],
        voice_message_id=message["voice_message_id"],
    )
    deleted_voice.append(message["voice_message_id"])
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"deleted_text": deleted_text, "deleted_voice": deleted_voice}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_delete_phone_spam_messages",
    )


def handle_phone_update_wake_alarm_snooze(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    day_type = frame.get("day_type")
    snooze_minutes = frame.get("snooze_minutes")
    if day_type not in {"weekday", "weekend"} or snooze_minutes is None:
        frame.abstain_reason = "missing_phone_wake_alarm_snooze_slots"
        return None
    code = common_appworld_prelude(["phone"]) + f"""
day_type = {json.dumps(str(day_type))}
snooze_minutes = {int(snooze_minutes)}
weekday_days = ["monday", "tuesday", "wednesday", "thursday", "friday"]
weekend_days = ["saturday", "sunday"]
target_days = weekday_days if day_type == "weekday" else weekend_days
alarms = paged(lambda page: apis.phone.show_alarms(
    access_token=tokens["phone"],
    page_index=page,
    page_limit=20,
))
matching_alarms = []
for alarm in alarms:
    label = str(alarm.get("label") or "").strip().lower()
    repeat_days = alarm.get("repeat_days") or []
    if label == "wake up" and sorted(repeat_days) == sorted(target_days):
        matching_alarms.append(alarm)
if len(matching_alarms) != 1:
    raise Exception(f"Expected exactly one {{day_type}} wake-up alarm, found {{len(matching_alarms)}}.")
alarm = matching_alarms[0]
apis.phone.update_alarm(
    access_token=tokens["phone"],
    alarm_id=alarm["alarm_id"],
    snooze_minutes=snooze_minutes,
)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"alarm_id": alarm["alarm_id"], "day_type": day_type, "snooze_minutes": snooze_minutes}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_phone_update_wake_alarm_snooze",
    )


def handle_amazon_move_rating_filtered_products(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    source_container = frame.get("source_container")
    target_container = frame.get("target_container")
    comparison = frame.get("comparison")
    threshold_rating = frame.get("threshold_rating")
    if source_container not in {"cart", "wish_list"}:
        frame.abstain_reason = "missing_amazon_source_container"
        return None
    if target_container not in {"cart", "wish_list"}:
        frame.abstain_reason = "missing_amazon_target_container"
        return None
    if source_container == target_container or comparison not in {"under", "over"} or threshold_rating is None:
        frame.abstain_reason = "unsupported_amazon_rating_move_slots"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
source_container = {json.dumps(str(source_container))}
target_container = {json.dumps(str(target_container))}
comparison = {json.dumps(str(comparison))}
threshold_rating = {float(threshold_rating)}
if source_container == "cart":
    source_items = apis.amazon.show_cart(access_token=tokens["amazon"])["cart_items"]
else:
    source_items = apis.amazon.show_wish_list(access_token=tokens["amazon"])
moved_product_ids = []
for item in list(source_items):
    product_id = item["product_id"]
    quantity = int(item.get("quantity") or 1)
    product = apis.amazon.show_product(product_id=product_id)
    rating = float(product.get("rating") or 0)
    should_move = rating < threshold_rating if comparison == "under" else rating >= threshold_rating
    if not should_move:
        continue
    if source_container == "cart" and target_container == "wish_list":
        apis.amazon.move_product_from_cart_to_wish_list(
            access_token=tokens["amazon"],
            product_id=product_id,
            quantity=quantity,
        )
    elif source_container == "wish_list" and target_container == "cart":
        apis.amazon.move_product_from_wish_list_to_cart(
            access_token=tokens["amazon"],
            product_id=product_id,
            quantity=quantity,
        )
    else:
        raise Exception(f"Unsupported source/target move: {{source_container}} -> {{target_container}}")
    moved_product_ids.append(product_id)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"source_container": source_container, "target_container": target_container, "comparison": comparison, "threshold_rating": threshold_rating, "moved_product_ids": moved_product_ids, "count": len(moved_product_ids)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_move_rating_filtered_products",
    )


def handle_amazon_move_product_type_between_saved_lists(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    source_container = frame.get("source_container")
    target_container = frame.get("target_container")
    product_type = frame.get("product_type")
    if source_container not in {"cart", "wish_list"}:
        frame.abstain_reason = "missing_amazon_source_container"
        return None
    if target_container not in {"cart", "wish_list"}:
        frame.abstain_reason = "missing_amazon_target_container"
        return None
    if source_container == target_container or not product_type:
        frame.abstain_reason = "unsupported_amazon_product_type_move_slots"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
source_container = {json.dumps(str(source_container))}
target_container = {json.dumps(str(target_container))}
target_product_type = {json.dumps(normalize_amazon_product_type(product_type))}

def product_type_matches(product):
    return str(product.get("product_type", "")).strip().lower() == target_product_type

if source_container == "cart":
    source_items = apis.amazon.show_cart(access_token=tokens["amazon"])["cart_items"]
else:
    source_items = apis.amazon.show_wish_list(access_token=tokens["amazon"])

moved_product_ids = []
for item in list(source_items):
    product_id = item["product_id"]
    quantity = int(item.get("quantity") or 1)
    product = apis.amazon.show_product(product_id=product_id)
    if not product_type_matches(product):
        continue
    if source_container == "cart" and target_container == "wish_list":
        apis.amazon.move_product_from_cart_to_wish_list(
            access_token=tokens["amazon"],
            product_id=product_id,
            quantity=quantity,
        )
    elif source_container == "wish_list" and target_container == "cart":
        apis.amazon.move_product_from_wish_list_to_cart(
            access_token=tokens["amazon"],
            product_id=product_id,
            quantity=quantity,
        )
    else:
        raise Exception(f"Unsupported source/target move: {{source_container}} -> {{target_container}}")
    moved_product_ids.append(product_id)
if not moved_product_ids:
    raise Exception(f"No {{target_product_type}} products found in {{source_container}}.")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"source_container": source_container, "target_container": target_container, "product_type": target_product_type, "moved_product_ids": moved_product_ids, "count": len(moved_product_ids)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_move_product_type_between_saved_lists",
    )


def handle_amazon_order_product_type_from_saved_list(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    source_container = frame.get("source_container")
    product_type = frame.get("product_type")
    address_name = frame.get("address_name") or "Home"
    card_name = frame.get("card_name") or ""
    if source_container not in {"cart", "wish_list"}:
        frame.abstain_reason = "missing_amazon_order_source_container"
        return None
    if not product_type:
        frame.abstain_reason = "missing_amazon_order_product_type"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
source_container = {json.dumps(str(source_container))}
target_product_type = {json.dumps(normalize_amazon_product_type(product_type))}
address_name = {json.dumps(str(address_name))}
card_name = {json.dumps(str(card_name))}

def product_type_matches(product):
    return str(product.get("product_type", "")).strip().lower() == target_product_type

def pick_address():
    addresses = apis.amazon.show_addresses(access_token=tokens["amazon"])
    for address in addresses:
        if str(address.get("name", "")).strip().lower() == address_name.strip().lower():
            return address
    if address_name.strip().lower() == "home" and len(addresses) == 1:
        return addresses[0]
    raise Exception(f"No unique Amazon address named {{address_name}}.")

def pick_payment_card():
    cards = apis.amazon.show_payment_cards(access_token=tokens["amazon"])
    candidates = []
    for card in cards:
        if card_name and card_name.strip().lower() not in str(card.get("card_name", "")).strip().lower():
            continue
        candidates.append(card)
    if not candidates:
        raise Exception(f"No Amazon payment card matched {{card_name or 'any card'}}.")
    return sorted(
        candidates,
        key=lambda card: (
            int(card.get("expiry_year") or 0),
            int(card.get("expiry_month") or 0),
            int(card["payment_card_id"]),
        ),
        reverse=True,
    )

if source_container == "cart":
    source_items = apis.amazon.show_cart(access_token=tokens["amazon"])["cart_items"]
else:
    source_items = apis.amazon.show_wish_list(access_token=tokens["amazon"])

target_items = []
for item in list(source_items):
    product = apis.amazon.show_product(product_id=item["product_id"])
    if product_type_matches(product):
        target_items.append((item, product))
if not target_items:
    raise Exception(f"No {{target_product_type}} products found in {{source_container}}.")

if source_container == "cart":
    current_cart = list(apis.amazon.show_cart(access_token=tokens["amazon"])["cart_items"])
    target_ids = {{item["product_id"] for item, _product in target_items}}
    removed_items = []
    for item in current_cart:
        product_id = item["product_id"]
        if product_id in target_ids:
            continue
        quantity = int(item.get("quantity") or 1)
        apis.amazon.delete_product_from_cart(
            access_token=tokens["amazon"],
            product_id=product_id,
        )
        removed_items.append({{"product_id": product_id, "quantity": quantity}})
else:
    removed_items = []
    current_cart = list(apis.amazon.show_cart(access_token=tokens["amazon"])["cart_items"])
    for item in current_cart:
        product_id = item["product_id"]
        quantity = int(item.get("quantity") or 1)
        apis.amazon.delete_product_from_cart(
            access_token=tokens["amazon"],
            product_id=product_id,
        )
        removed_items.append({{"product_id": product_id, "quantity": quantity}})
    for item, _product in target_items:
        apis.amazon.move_product_from_wish_list_to_cart(
            access_token=tokens["amazon"],
            product_id=item["product_id"],
            quantity=int(item.get("quantity") or 1),
        )

address = pick_address()
cards = pick_payment_card()
result = {{"message": "No payment card attempted."}}
payment_card_id = None
failed_payment_attempts = []
for card in cards:
    payment_card_id = card["payment_card_id"]
    result = apis.amazon.place_order(
        access_token=tokens["amazon"],
        payment_card_id=payment_card_id,
        address_id=address["address_id"],
    )
    if "order_id" in result:
        break
    failed_payment_attempts.append({{"payment_card_id": payment_card_id, "message": result.get("message")}})
if "order_id" not in result:
    raise Exception(f"Unable to place Amazon order: {{result}}")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"source_container": source_container, "product_type": target_product_type, "ordered_product_ids": [item["product_id"] for item, _product in target_items], "address_id": address["address_id"], "payment_card_id": payment_card_id, "order_id": result["order_id"], "failed_payment_attempts": failed_payment_attempts, "removed_non_targets": removed_items}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_order_product_type_from_saved_list",
    )


def handle_amazon_purchase_phone_recommendation(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    recommender_first_name = frame.get("recommender_first_name")
    product_type = frame.get("product_type")
    address_name = frame.get("address_name") or "Home"
    card_name = frame.get("card_name") or ""
    if not recommender_first_name or not product_type:
        frame.abstain_reason = "missing_phone_recommended_amazon_purchase_slots"
        return None
    code = common_appworld_prelude(["phone", "amazon"]) + f"""
recommender_first_name = {json.dumps(str(recommender_first_name))}
target_product_type = {json.dumps(normalize_amazon_product_type(product_type))}
address_name = {json.dumps(str(address_name))}
card_name = {json.dumps(str(card_name))}

def normalize_text(value):
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def word_set(value):
    return set(normalize_text(value).split())

def product_type_matches(product):
    product_type = normalize_text(product.get("product_type"))
    target = normalize_text(target_product_type)
    if product_type == target:
        return True
    target_words = word_set(target)
    combined_words = word_set(str(product.get("name") or "") + " " + str(product.get("description") or ""))
    return bool(target_words) and target_words <= combined_words

def pick_address():
    addresses = apis.amazon.show_addresses(access_token=tokens["amazon"])
    for address in addresses:
        if str(address.get("name", "")).strip().lower() == address_name.strip().lower():
            return address
    if address_name.strip().lower() == "home" and len(addresses) == 1:
        return addresses[0]
    raise Exception(f"No unique Amazon address named {{address_name}}.")

def pick_payment_cards():
    cards = apis.amazon.show_payment_cards(access_token=tokens["amazon"])
    candidates = []
    for card in cards:
        if card_name and card_name.strip().lower() not in str(card.get("card_name", "")).strip().lower():
            continue
        candidates.append(card)
    if not candidates:
        raise Exception(f"No Amazon payment card matched {{card_name or 'any card'}}.")
    return sorted(
        candidates,
        key=lambda card: (
            int(card.get("expiry_year") or 0),
            int(card.get("expiry_month") or 0),
            int(card["payment_card_id"]),
        ),
        reverse=True,
    )

def extract_recommendation_queries(message):
    text = str(message or "")
    queries = []
    for quoted in re.findall(r"[\\\"']([^\\\"']+)[\\\"']", text):
        if quoted.strip():
            queries.append(quoted.strip())
    patterns = [
        r"recommend(?:ed|s)?\\s+(?:that\\s+you\\s+)?(?:buy|get|purchase)?\\s*(?:the|a|an)?\\s*(?P<item>[^.;!\\n]+)",
        r"suggest(?:ed|s)?\\s+(?:that\\s+you\\s+)?(?:buy|get|purchase)?\\s*(?:the|a|an)?\\s*(?P<item>[^.;!\\n]+)",
        r"(?:buy|get|purchase)\\s+(?:the|a|an)?\\s*(?P<item>[^.;!\\n]+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            item = re.sub(r"\\s+", " ", match.group("item")).strip(" ,:-")
            if item:
                queries.append(item)
    target_words = word_set(target_product_type)
    for sentence in re.split(r"[.!?\\n]+", text):
        sentence = sentence.strip()
        if sentence and target_words and target_words <= word_set(sentence):
            queries.append(sentence)
    queries.append(target_product_type)
    deduped = []
    seen = set()
    for query in queries:
        cleaned = re.sub(r"\\s+", " ", query).strip(" ,:-")
        key = normalize_text(cleaned)
        if cleaned and key and key not in seen:
            deduped.append(cleaned)
            seen.add(key)
    return deduped

def find_best_product_for_query(query, search_trace):
    best = None
    best_key = None
    for search_kwargs in [
        {{"query": query, "product_type": target_product_type}},
        {{"query": query}},
        {{"query": target_product_type, "product_type": target_product_type}},
    ]:
        products = paged(lambda page, search_kwargs=search_kwargs: apis.amazon.search_products(
            page_index=page,
            page_limit=20,
            **search_kwargs,
        ))
        search_trace.append({{"query": search_kwargs, "count": len(products)}})
        query_words = word_set(query)
        for product in products:
            if int(product.get("inventory_quantity") or 0) <= 0:
                continue
            if not product_type_matches(product):
                continue
            product_words = word_set(str(product.get("name") or "") + " " + str(product.get("description") or ""))
            overlap = len(query_words & product_words)
            exact_name = normalize_text(product.get("name")) == normalize_text(query)
            key = (
                int(exact_name),
                overlap,
                float(product.get("rating") or 0),
                -float(product.get("price") or 0),
                -int(product["product_id"]),
            )
            if best is None or key > best_key:
                best = product
                best_key = key
        if best is not None:
            break
    return best

contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    query=recommender_first_name,
    page_index=page,
    page_limit=20,
))
matching_contacts = []
for contact in contacts:
    if str(contact.get("first_name") or "").strip().lower() == recommender_first_name.strip().lower():
        matching_contacts.append(contact)
if len(matching_contacts) != 1:
    raise Exception(f"Could not uniquely resolve phone contact {{recommender_first_name}}.")
contact = matching_contacts[0]
phone_number = str(contact.get("phone_number") or "").strip()
if not phone_number:
    raise Exception(f"Contact {{recommender_first_name}} has no phone number.")

candidate_messages = []
text_messages = paged(lambda page: apis.phone.search_text_messages(
    access_token=tokens["phone"],
    phone_number=phone_number,
    page_index=page,
    page_limit=20,
))
voice_messages = paged(lambda page: apis.phone.search_voice_messages(
    access_token=tokens["phone"],
    phone_number=phone_number,
    page_index=page,
    page_limit=20,
))
for kind, messages in [("text", text_messages), ("voice", voice_messages)]:
    for message in messages:
        sender_phone = ((message.get("sender") or {{}}).get("phone_number") or "")
        if sender_phone != phone_number:
            continue
        message_text = str(message.get("message") or "")
        if word_set(target_product_type) <= word_set(message_text) or re.search(r"recommend|suggest|buy|get|purchase", message_text, flags=re.IGNORECASE):
            candidate_messages.append({{
                "kind": kind,
                "sent_at": message.get("sent_at", ""),
                "message": message_text,
                "id": message.get("text_message_id") or message.get("voice_message_id"),
            }})
if not candidate_messages:
    raise Exception(f"No recommendation phone message from {{recommender_first_name}} about {{target_product_type}}.")
candidate_messages.sort(key=lambda item: item["sent_at"], reverse=True)

searched = []
selected = None
for candidate_message in candidate_messages:
    message_text = candidate_message["message"]
    quoted_options = [
        item.strip()
        for item in re.findall(r"[\\\"']([^\\\"']+)[\\\"']", message_text)
        if item.strip()
    ]
    choose_cheapest = bool(re.search(r"\\bcheaper\\b|\\blowest[- ]price\\b|\\bleast expensive\\b", message_text, flags=re.IGNORECASE))
    option_products = []
    if choose_cheapest and len(quoted_options) >= 2:
        for option in quoted_options:
            option_trace = []
            product = find_best_product_for_query(option, option_trace)
            for trace in option_trace:
                searched.append({{"message_id": candidate_message["id"], "query": trace["query"], "count": trace["count"], "option": option}})
            if product is not None:
                option_products.append((float(product.get("price") or 0), -float(product.get("rating") or 0), int(product["product_id"]), option, product))
        if option_products:
            option_products.sort()
            selected = {{"message": candidate_message, "query": option_products[0][3], "product": option_products[0][4]}}
    if selected is None:
        for query in extract_recommendation_queries(message_text):
            query_trace = []
            product = find_best_product_for_query(query, query_trace)
            for trace in query_trace:
                searched.append({{"message_id": candidate_message["id"], "query": trace["query"], "count": trace["count"]}})
            if product is not None:
                selected = {{"message": candidate_message, "query": query, "product": product}}
                break
        if selected is not None:
            break
    if selected is not None:
        break

if selected is None:
    raise Exception(f"No in-stock Amazon product matched {{target_product_type}} recommendation from {{recommender_first_name}}.")

product = selected["product"]
apis.amazon.add_product_to_cart(
    access_token=tokens["amazon"],
    product_id=product["product_id"],
    quantity=1,
    clear_cart_first=True,
)
address = pick_address()
failed_payment_attempts = []
result = {{"message": "No payment card attempted."}}
payment_card_id = None
for card in pick_payment_cards():
    payment_card_id = card["payment_card_id"]
    result = apis.amazon.place_order(
        access_token=tokens["amazon"],
        payment_card_id=payment_card_id,
        address_id=address["address_id"],
    )
    if "order_id" in result:
        break
    failed_payment_attempts.append({{"payment_card_id": payment_card_id, "message": result.get("message")}})
if "order_id" not in result:
    raise Exception(f"Unable to place Amazon order: {{result}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "recommender_first_name": recommender_first_name,
    "phone_number": phone_number,
    "message_id": selected["message"]["id"],
    "message_kind": selected["message"]["kind"],
    "selected_query": selected["query"],
    "product_type": target_product_type,
    "product_id": product["product_id"],
    "product_name": product.get("name"),
    "address_id": address["address_id"],
    "payment_card_id": payment_card_id,
    "order_id": result["order_id"],
    "failed_payment_attempts": failed_payment_attempts,
    "search_trace": searched,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_purchase_phone_recommendation",
    )


def handle_amazon_text_wishlist_itemized_costs(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationship = str(frame.get("relationship") or "").strip().lower()
    relationship = RELATION_ALIASES.get(relationship, relationship)
    if relationship not in {"husband", "wife", "partner"}:
        frame.abstain_reason = "missing_or_unsupported_amazon_wishlist_text_relationship"
        return None
    code = common_appworld_prelude(["amazon", "phone"]) + f"""
relationship = {json.dumps(relationship)}

def rounded_whole(value):
    return str(int(round(float(value))))

contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship=relationship,
    page_index=page,
    page_limit=20,
))
phone_numbers = {{
    str(contact.get("phone_number") or "").strip()
    for contact in contacts
    if str(contact.get("phone_number") or "").strip()
}}
if len(phone_numbers) != 1:
    raise Exception(f"Expected exactly one {{relationship}} phone number, found {{sorted(phone_numbers)}}.")
phone_number = next(iter(phone_numbers))

items = list(apis.amazon.show_wish_list(access_token=tokens["amazon"]))
if not items:
    raise Exception("Amazon wish list is empty.")
lines = []
for item in items:
    product_name = str(item.get("product_name") or "").strip()
    if not product_name:
        raise Exception(f"Wish-list item {{item.get('product_id')}} is missing a product name.")
    total_price = float(item.get("price") or 0) * int(item.get("quantity") or 1)
    lines.append(f"{{product_name}} => ${{rounded_whole(total_price)}}")
message = "\\n".join(lines)
result = apis.phone.send_text_message(
    access_token=tokens["phone"],
    phone_number=phone_number,
    message=message,
)
if "text_message_id" not in result:
    raise Exception(f"Unable to send wishlist text message: {{result}}")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "relationship": relationship,
    "phone_number": phone_number,
    "line_count": len(lines),
    "text_message_id": result.get("text_message_id"),
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_text_wishlist_itemized_costs",
    )


def handle_amazon_answer_cart_wishlist_total(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["amazon"]) + """
cart = apis.amazon.show_cart(access_token=tokens["amazon"])
cart_total = 0.0
for item in cart.get("cart_items", []):
    cart_total += float(item.get("price") or 0) * int(item.get("quantity") or 1)
wishlist_total = 0.0
for item in apis.amazon.show_wish_list(access_token=tokens["amazon"]):
    wishlist_total += float(item.get("price") or 0) * int(item.get("quantity") or 1)
total = cart_total + wishlist_total
answer = str(int(round(total))) if abs(total - round(total)) < 1e-9 else str(round(total, 2))
apis.supervisor.complete_task(answer=answer)
print(json.dumps({
    "answer": answer,
    "cart_total": cart_total,
    "wishlist_total": wishlist_total,
    "total": total,
}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_answer_cart_wishlist_total",
    )


def handle_amazon_order_saved_collections(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    containers = frame.get("containers", [])
    if isinstance(containers, str):
        containers = [containers]
    containers = [normalize_amazon_container(container) for container in containers]
    if not containers or any(container not in {"cart", "wish_list"} for container in containers):
        frame.abstain_reason = "missing_or_unsupported_amazon_saved_collection_containers"
        return None
    unique_containers: list[str] = []
    for container in containers:
        if container not in unique_containers:
            unique_containers.append(container)
    address_name = frame.get("address_name") or "Home"
    card_name = frame.get("card_name") or ""
    code = common_appworld_prelude(["amazon"]) + f"""
containers = {json.dumps(unique_containers)}
address_name = {json.dumps(str(address_name))}
card_name = {json.dumps(str(card_name))}

def pick_address():
    addresses = apis.amazon.show_addresses(access_token=tokens["amazon"])
    for address in addresses:
        if str(address.get("name", "")).strip().lower() == address_name.strip().lower():
            return address
    raise Exception(f"No unique Amazon address named {{address_name}}.")

def pick_payment_cards():
    cards = apis.amazon.show_payment_cards(access_token=tokens["amazon"])
    candidates = []
    for card in cards:
        if card_name and card_name.strip().lower() not in str(card.get("card_name", "")).strip().lower():
            continue
        candidates.append(card)
    if not candidates:
        raise Exception(f"No Amazon payment card matched {{card_name or 'any card'}}.")
    return sorted(
        candidates,
        key=lambda card: (
            int(card.get("expiry_year") or 0),
            int(card.get("expiry_month") or 0),
            int(card["payment_card_id"]),
        ),
        reverse=True,
    )

def require_positive_quantity(item, source):
    quantity = int(item.get("quantity") or 1)
    if quantity < 1:
        raise Exception(f"Invalid {{source}} quantity for product {{item.get('product_id')}}: {{quantity}}")
    inventory = item.get("inventory_quantity")
    if inventory is not None and int(inventory) < quantity:
        raise Exception(f"Insufficient inventory for {{source}} product {{item.get('product_id')}}.")
    return quantity

target_items = []
if "cart" in containers:
    for item in apis.amazon.show_cart(access_token=tokens["amazon"]).get("cart_items", []):
        target_items.append({{
            "source": "cart",
            "product_id": item["product_id"],
            "quantity": require_positive_quantity(item, "cart"),
        }})
if "wish_list" in containers:
    for item in apis.amazon.show_wish_list(access_token=tokens["amazon"]):
        target_items.append({{
            "source": "wish_list",
            "product_id": item["product_id"],
            "quantity": require_positive_quantity(item, "wish_list"),
        }})
if not target_items:
    raise Exception(f"No Amazon items found in requested collections {{containers}}.")

cart_snapshot = list(apis.amazon.show_cart(access_token=tokens["amazon"]).get("cart_items", []))
apis.amazon.clear_cart(access_token=tokens["amazon"])
first = True
for item in target_items:
    if item["source"] == "wish_list":
        result = apis.amazon.move_product_from_wish_list_to_cart(
            access_token=tokens["amazon"],
            product_id=item["product_id"],
            quantity=item["quantity"],
        )
    else:
        result = apis.amazon.add_product_to_cart(
            access_token=tokens["amazon"],
            product_id=item["product_id"],
            quantity=item["quantity"],
            clear_cart_first=first,
        )
    first = False
    if result.get("message") and "not" in str(result.get("message")).lower() and "success" not in str(result.get("message")).lower():
        raise Exception(f"Unable to stage Amazon product {{item}}: {{result}}")

staged_cart = apis.amazon.show_cart(access_token=tokens["amazon"])
if staged_cart.get("promo_code") and not bool(staged_cart.get("promo_valid")):
    apis.amazon.remove_promo_code_from_cart(access_token=tokens["amazon"])

address = pick_address()
failed_payment_attempts = []
result = {{"message": "No payment card attempted."}}
payment_card_id = None
for card in pick_payment_cards():
    payment_card_id = card["payment_card_id"]
    result = apis.amazon.place_order(
        access_token=tokens["amazon"],
        payment_card_id=payment_card_id,
        address_id=address["address_id"],
    )
    if "order_id" in result:
        break
    failed_payment_attempts.append({{"payment_card_id": payment_card_id, "message": result.get("message")}})
if "order_id" not in result:
    raise Exception(f"Unable to place Amazon saved-collections order: {{result}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "containers": containers,
    "address_name": address_name,
    "address_id": address["address_id"],
    "payment_card_id": payment_card_id,
    "order_id": result["order_id"],
    "ordered_items": target_items,
    "cart_snapshot_count": len(cart_snapshot),
    "failed_payment_attempts": failed_payment_attempts,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_order_saved_collections",
    )


def handle_amazon_cart_buy_cheapest_per_type_move_rest(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    address_name = str(frame.get("address_name") or "Home")
    card_name = str(frame.get("card_name") or "")
    code = common_appworld_prelude(["amazon"]) + f"""
address_name = {json.dumps(address_name)}
card_name = {json.dumps(card_name)}

def normalize_text(value):
    value = str(value or "").lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def pick_address():
    addresses = apis.amazon.show_addresses(access_token=tokens["amazon"])
    for address in addresses:
        if normalize_text(address.get("name")) == normalize_text(address_name):
            return address
    if normalize_text(address_name) == "home" and len(addresses) == 1:
        return addresses[0]
    raise Exception(f"No unique Amazon address named {{address_name}}.")

def pick_payment_cards():
    cards = [
        card
        for card in apis.amazon.show_payment_cards(access_token=tokens["amazon"])
        if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
    ]
    candidates = []
    for card in cards:
        if card_name and normalize_text(card_name) not in normalize_text(card.get("card_name")):
            continue
        candidates.append(card)
    if not candidates:
        raise Exception(f"No Amazon payment card matched {{card_name or 'any card'}}.")
    return sorted(
        candidates,
        key=lambda card: (
            int(card.get("expiry_year") or 0),
            int(card.get("expiry_month") or 0),
            int(card["payment_card_id"]),
        ),
        reverse=True,
    )

cart = apis.amazon.show_cart(access_token=tokens["amazon"])
cart_items = list(cart.get("cart_items", []))
if not cart_items:
    raise Exception("Amazon cart is empty.")

groups = {{}}
for item in cart_items:
    product = apis.amazon.show_product(product_id=item["product_id"])
    product_type = normalize_text(product.get("product_type"))
    if not product_type:
        raise Exception(f"Cart product {{item['product_id']}} has no product_type.")
    quantity = int(item.get("quantity") or 1)
    if quantity < 1:
        raise Exception(f"Invalid cart quantity for product {{item['product_id']}}: {{quantity}}")
    inventory = int(item.get("inventory_quantity") or product.get("inventory_quantity") or 0)
    if inventory < quantity:
        raise Exception(f"Insufficient inventory for cart product {{item['product_id']}}.")
    groups.setdefault(product_type, []).append({{
        "cart_item": item,
        "product": product,
        "quantity": quantity,
        "price": float(item.get("price") if item.get("price") is not None else product.get("price") or 0),
    }})

to_buy = []
to_move = []
for product_type, entries in groups.items():
    entries.sort(key=lambda row: (row["price"], int(row["product"]["product_id"])))
    to_buy.append(entries[0])
    to_move.extend(entries[1:])

for entry in to_move:
    result = apis.amazon.move_product_from_cart_to_wish_list(
        access_token=tokens["amazon"],
        product_id=entry["product"]["product_id"],
        quantity=entry["quantity"],
    )
    if result.get("message") and "not" in str(result.get("message")).lower() and "success" not in str(result.get("message")).lower():
        raise Exception(f"Unable to move non-cheapest cart product {{entry['product']['product_id']}} to wishlist: {{result}}")

remaining_cart = apis.amazon.show_cart(access_token=tokens["amazon"]).get("cart_items", [])
remaining_ids = {{int(item["product_id"]) for item in remaining_cart}}
expected_ids = {{int(entry["product"]["product_id"]) for entry in to_buy}}
if remaining_ids != expected_ids:
    raise Exception(f"Unexpected cart contents before order: expected {{expected_ids}}, found {{remaining_ids}}")

address = pick_address()
failed_payment_attempts = []
result = {{"message": "No payment card attempted."}}
payment_card_id = None
for card in pick_payment_cards():
    payment_card_id = card["payment_card_id"]
    result = apis.amazon.place_order(
        access_token=tokens["amazon"],
        payment_card_id=payment_card_id,
        address_id=address["address_id"],
    )
    if "order_id" in result:
        break
    failed_payment_attempts.append({{"payment_card_id": payment_card_id, "message": result.get("message")}})
if "order_id" not in result:
    raise Exception(f"Unable to place Amazon cheapest-per-type order: {{result}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "ordered_product_ids": sorted(expected_ids),
    "moved_product_ids": sorted(int(entry["product"]["product_id"]) for entry in to_move),
    "product_types": sorted(groups.keys()),
    "address_id": address["address_id"],
    "payment_card_id": payment_card_id,
    "order_id": result["order_id"],
    "failed_payment_attempts": failed_payment_attempts,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_cart_buy_cheapest_per_type_move_rest",
    )


def handle_amazon_order_exact_products_restore_cart(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    raw_items = frame.get("items") or []
    if not isinstance(raw_items, list) or not raw_items:
        frame.abstain_reason = "missing_amazon_exact_order_items"
        return None
    items: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            frame.abstain_reason = "invalid_amazon_exact_order_item"
            return None
        product_name = compact_text(str(item.get("product_name") or ""))
        quantity = int(item.get("quantity") or 0)
        if not product_name or quantity < 1:
            frame.abstain_reason = "invalid_amazon_exact_order_item"
            return None
        items.append({"product_name": product_name, "quantity": quantity})
    address_name = str(frame.get("address_name") or "Home")
    preferred_card_name = str(frame.get("preferred_card_name") or "")
    restore_cart = bool(frame.get("restore_cart"))
    if not restore_cart:
        frame.abstain_reason = "amazon_exact_order_requires_cart_restore"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
requested_items = {json.dumps(items)}
address_name = {json.dumps(address_name)}
preferred_card_name = {json.dumps(preferred_card_name)}

def pick_address():
    addresses = apis.amazon.show_addresses(access_token=tokens["amazon"])
    for address in addresses:
        if str(address.get("name", "")).strip().lower() == address_name.strip().lower():
            return address
    raise Exception(f"No unique Amazon address named {{address_name}}.")

def card_rank(card):
    return (
        int(card.get("expiry_year") or 0),
        int(card.get("expiry_month") or 0),
        int(card["payment_card_id"]),
    )

def pick_payment_cards():
    cards = sorted(
        apis.amazon.show_payment_cards(access_token=tokens["amazon"]),
        key=card_rank,
        reverse=True,
    )
    if not cards:
        raise Exception("No Amazon payment card available.")
    preferred = []
    if preferred_card_name.strip():
        preferred = [
            card for card in cards
            if preferred_card_name.strip().lower() in str(card.get("card_name", "")).strip().lower()
        ]
    fallback = [card for card in cards if card not in preferred]
    return preferred + fallback

def all_search_results(query):
    results = []
    page = 0
    while True:
        batch = apis.amazon.search_products(query=query, page_index=page, page_limit=20)
        if not batch:
            break
        results.extend(batch)
        if len(batch) < 20:
            break
        page += 1
    return results

def resolve_product(product_name, quantity):
    matches = [
        product for product in all_search_results(product_name)
        if str(product.get("name", "")).strip().lower() == product_name.strip().lower()
    ]
    unique_by_id = {{}}
    for product in matches:
        unique_by_id[int(product["product_id"])] = product
    matches = list(unique_by_id.values())
    if len(matches) != 1:
        raise Exception(f"Could not uniquely resolve Amazon product {{product_name}}; found {{len(matches)}}.")
    product = apis.amazon.show_product(product_id=matches[0]["product_id"])
    inventory = int(product.get("inventory_quantity") or 0)
    if inventory < quantity:
        raise Exception(f"Insufficient inventory for {{product_name}}: need {{quantity}}, have {{inventory}}.")
    return product

def restore_cart(snapshot):
    apis.amazon.clear_cart(access_token=tokens["amazon"])
    first = True
    for item in snapshot.get("cart_items", []):
        result = apis.amazon.add_product_to_cart(
            access_token=tokens["amazon"],
            product_id=item["product_id"],
            quantity=int(item.get("quantity") or 1),
            clear_cart_first=first,
        )
        first = False
        if result.get("message") and "not" in str(result.get("message")).lower() and "success" not in str(result.get("message")).lower():
            raise Exception(f"Unable to restore Amazon cart item {{item}}: {{result}}")
        gift_wrap_quantity = int(item.get("gift_wrap_quantity") or 0)
        if gift_wrap_quantity:
            update_result = apis.amazon.add_gift_wrapping_to_product(
                access_token=tokens["amazon"],
                product_id=item["product_id"],
                quantity=gift_wrap_quantity,
            )
            if update_result.get("message") and "not" in str(update_result.get("message")).lower() and "success" not in str(update_result.get("message")).lower():
                raise Exception(f"Unable to restore Amazon gift wrapping for {{item}}: {{update_result}}")
    promo_code = snapshot.get("promo_code")
    if promo_code:
        result = apis.amazon.apply_promo_code_to_cart(
            access_token=tokens["amazon"],
            promo_code=promo_code,
        )
        if result.get("message") and "not" in str(result.get("message")).lower() and "success" not in str(result.get("message")).lower():
            raise Exception(f"Unable to restore Amazon cart promo code {{promo_code}}: {{result}}")

cart_snapshot = apis.amazon.show_cart(access_token=tokens["amazon"])
target_items = []
for item in requested_items:
    product = resolve_product(item["product_name"], int(item["quantity"]))
    target_items.append({{
        "product_id": product["product_id"],
        "product_name": product["name"],
        "quantity": int(item["quantity"]),
    }})

address = pick_address()
failed_payment_attempts = []
result = {{"message": "No payment card attempted."}}
payment_card_id = None
try:
    apis.amazon.clear_cart(access_token=tokens["amazon"])
    first = True
    for item in target_items:
        add_result = apis.amazon.add_product_to_cart(
            access_token=tokens["amazon"],
            product_id=item["product_id"],
            quantity=item["quantity"],
            clear_cart_first=first,
        )
        first = False
        if add_result.get("message") and "not" in str(add_result.get("message")).lower() and "success" not in str(add_result.get("message")).lower():
            raise Exception(f"Unable to stage Amazon product {{item}}: {{add_result}}")
    staged_cart = apis.amazon.show_cart(access_token=tokens["amazon"])
    if staged_cart.get("promo_code") and not bool(staged_cart.get("promo_valid")):
        apis.amazon.remove_promo_code_from_cart(access_token=tokens["amazon"])
    for card in pick_payment_cards():
        payment_card_id = card["payment_card_id"]
        result = apis.amazon.place_order(
            access_token=tokens["amazon"],
            payment_card_id=payment_card_id,
            address_id=address["address_id"],
        )
        if "order_id" in result:
            break
        failed_payment_attempts.append({{"payment_card_id": payment_card_id, "message": result.get("message")}})
    if "order_id" not in result:
        raise Exception(f"Unable to place Amazon exact-products order: {{result}}")
finally:
    restore_cart(cart_snapshot)

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "address_name": address_name,
    "address_id": address["address_id"],
    "preferred_card_name": preferred_card_name,
    "payment_card_id": payment_card_id,
    "order_id": result["order_id"],
    "ordered_items": target_items,
    "cart_snapshot_count": len(cart_snapshot.get("cart_items", [])),
    "failed_payment_attempts": failed_payment_attempts,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_order_exact_products_restore_cart",
    )


def handle_amazon_order_product_and_archive_receipt(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    product_name = compact_text(str(frame.get("product_name") or ""))
    quantity = int(frame.get("quantity") or 0)
    address_name = str(frame.get("address_name") or "Home")
    bills_root = str(frame.get("bills_root") or "~/bills/")
    if not product_name or quantity < 1:
        frame.abstain_reason = "missing_amazon_product_receipt_slots"
        return None
    if not bills_root.startswith("~/") or not bills_root.endswith("/"):
        frame.abstain_reason = "unsupported_amazon_receipt_bills_root"
        return None
    code = common_appworld_prelude(["amazon", "file_system"]) + f"""
product_name = {json.dumps(product_name)}
quantity = {quantity}
address_name = {json.dumps(address_name)}
bills_root = {json.dumps(bills_root)}

def normalize_text(value):
    value = str(value or "").lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def safe_slug(value):
    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return slug or "amazon_order"

def is_success_message(result):
    message = str(result.get("message", "")).lower()
    return not ("not" in message and "success" not in message)

def pick_address():
    addresses = apis.amazon.show_addresses(access_token=tokens["amazon"])
    for address in addresses:
        if normalize_text(address.get("name")) == normalize_text(address_name):
            return address
    if normalize_text(address_name) == "home" and len(addresses) == 1:
        return addresses[0]
    raise Exception(f"No unique Amazon address named {{address_name}}.")

def pick_payment_cards():
    cards = [
        card
        for card in apis.amazon.show_payment_cards(access_token=tokens["amazon"])
        if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
    ]
    if not cards:
        raise Exception("No unexpired Amazon payment card available.")
    return sorted(
        cards,
        key=lambda card: (
            int(card.get("expiry_year") or 0),
            int(card.get("expiry_month") or 0),
            int(card["payment_card_id"]),
        ),
        reverse=True,
    )

def all_search_results(query):
    results = []
    page = 0
    while True:
        batch = apis.amazon.search_products(query=query, page_index=page, page_limit=20)
        if not batch:
            break
        results.extend(batch)
        if len(batch) < 20:
            break
        page += 1
    return results

def resolve_product():
    target = normalize_text(product_name)
    matches = []
    seen = set()
    for product in all_search_results(product_name):
        product_id = int(product["product_id"])
        if product_id in seen:
            continue
        seen.add(product_id)
        if normalize_text(product.get("name")) == target:
            details = apis.amazon.show_product(product_id=product_id)
            if int(details.get("inventory_quantity") or 0) >= quantity:
                matches.append(details)
    if len(matches) != 1:
        raise Exception(f"Could not uniquely resolve in-stock Amazon product {{product_name}}; found {{len(matches)}}.")
    return matches[0]

def restore_cart(snapshot):
    apis.amazon.clear_cart(access_token=tokens["amazon"])
    first = True
    for item in snapshot.get("cart_items", []):
        result = apis.amazon.add_product_to_cart(
            access_token=tokens["amazon"],
            product_id=item["product_id"],
            quantity=int(item.get("quantity") or 1),
            clear_cart_first=first,
        )
        first = False
        if not is_success_message(result):
            raise Exception(f"Unable to restore Amazon cart item {{item}}: {{result}}")
        gift_wrap_quantity = int(item.get("gift_wrap_quantity") or 0)
        if gift_wrap_quantity:
            gift_result = apis.amazon.add_gift_wrapping_to_product(
                access_token=tokens["amazon"],
                product_id=item["product_id"],
                quantity=gift_wrap_quantity,
            )
            if not is_success_message(gift_result):
                raise Exception(f"Unable to restore Amazon gift wrapping for {{item}}: {{gift_result}}")
    promo_code = snapshot.get("promo_code")
    if promo_code:
        promo_result = apis.amazon.apply_promo_code_to_cart(
            access_token=tokens["amazon"],
            promo_code=promo_code,
        )
        if not is_success_message(promo_result):
            raise Exception(f"Unable to restore Amazon cart promo code {{promo_code}}: {{promo_result}}")

def ensure_directory(path):
    apis.file_system.create_directory(
        access_token=tokens["file_system"],
        directory_path=path,
        recursive=True,
        allow_if_exists=True,
    )

def infer_receipt_directory(product):
    root = bills_root.rstrip("/") + "/"
    ensure_directory(root)
    directories = apis.file_system.show_directory(
        access_token=tokens["file_system"],
        directory_path=root,
        entry_type="directories",
        recursive=True,
    )
    product_type = normalize_text(product.get("product_type"))
    best = None
    best_score = -1
    for directory in directories:
        lowered = str(directory).lower().rstrip("/") + "/"
        if not lowered.startswith(root.lower()):
            continue
        rel = lowered[len(root):].strip("/")
        score = 0
        if "amazon" in rel:
            score += 4
        if any(word in rel for word in ["shopping", "purchase", "order", "receipt", "bill"]):
            score += 2
        if product_type and normalize_text(rel) == product_type:
            score += 3
        depth_penalty = rel.count("/")
        score -= depth_penalty
        if score > best_score:
            best = directory
            best_score = score
    if best is not None and best_score > 0:
        directory = str(best).rstrip("/") + "/"
    else:
        directory = root + "amazon/"
    ensure_directory(directory)
    return directory

def existing_receipt_style(directory):
    files = apis.file_system.show_directory(
        access_token=tokens["file_system"],
        directory_path=directory,
        entry_type="files",
        recursive=False,
    )
    basenames = [str(path).rstrip("/").split("/")[-1] for path in files]
    if any(re.fullmatch(r"\\d{{4}}-\\d{{2}}-\\d{{2}}_order_id_\\d+\\.txt", name) for name in basenames):
        return "yyyy-mm-dd_order_id"
    if any(re.fullmatch(r"\\d{{4}}_\\d{{2}}_\\d{{2}}__orderid_\\d+\\.txt", name) for name in basenames):
        return "yyyy_mm_dd__orderid"
    if any(re.fullmatch(r"\\d{{4}}-\\d{{2}}-\\d{{2}}-order-id-\\d+\\.txt", name) for name in basenames):
        return "yyyy-mm-dd-order-id"
    if any("ordered_at_" in name and "_order_id_" in name for name in basenames):
        return "ordered_at_yyyy-mm-dd_order_id"
    if any("ordered-at-" in name and "-order-id-" in name for name in basenames):
        return "ordered-at-yyyy-mm-dd-order-id"
    if any(re.search(r"\\d{{4}}-\\d{{2}}-\\d{{2}}__", name) for name in basenames):
        return "yyyy-mm-dd__order_id"
    if any("amazon" in name.lower() or "order" in name.lower() for name in basenames):
        return "amazon_order_id_date"
    return "ordered_at_yyyy-mm-dd_order_id"

def receipt_path(directory, order_id):
    orders = apis.amazon.show_orders(
        access_token=tokens["amazon"],
        query=str(order_id),
        page_index=0,
        page_limit=20,
    )
    created_at = None
    for order in orders:
        if int(order.get("order_id") or -1) == int(order_id):
            created_at = str(order.get("created_at") or "")[:10]
            break
    if not created_at:
        created_at = DateTime.now().to_date_string()
    style = existing_receipt_style(directory)
    if style == "yyyy-mm-dd_order_id":
        filename = f"{{created_at}}_order_id_{{order_id}}.txt"
    elif style == "yyyy_mm_dd__orderid":
        filename = f"{{created_at.replace('-', '_')}}__orderid_{{order_id}}.txt"
    elif style == "yyyy-mm-dd-order-id":
        filename = f"{{created_at}}-order-id-{{order_id}}.txt"
    elif style == "ordered-at-yyyy-mm-dd-order-id":
        filename = f"ordered-at-{{created_at}}-order-id-{{order_id}}.txt"
    elif style == "yyyy-mm-dd__order_id":
        filename = f"{{created_at}}__{{order_id}}.txt"
    elif style == "amazon_order_id_date":
        filename = f"amazon_order_{{order_id}}_{{created_at}}.txt"
    else:
        filename = f"ordered_at_{{created_at}}_order_id_{{order_id}}.txt"
    return directory.rstrip("/") + "/" + filename

cart_snapshot = apis.amazon.show_cart(access_token=tokens["amazon"])
product = resolve_product()
address = pick_address()
failed_payment_attempts = []
result = {{"message": "No payment card attempted."}}
payment_card_id = None
receipt_result = None
download_path = None
try:
    apis.amazon.clear_cart(access_token=tokens["amazon"])
    add_result = apis.amazon.add_product_to_cart(
        access_token=tokens["amazon"],
        product_id=product["product_id"],
        quantity=quantity,
        clear_cart_first=True,
    )
    if not is_success_message(add_result):
        raise Exception(f"Unable to stage Amazon product {{product['product_id']}}: {{add_result}}")
    staged_cart = apis.amazon.show_cart(access_token=tokens["amazon"])
    if staged_cart.get("promo_code") and not bool(staged_cart.get("promo_valid")):
        apis.amazon.remove_promo_code_from_cart(access_token=tokens["amazon"])
    for card in pick_payment_cards():
        payment_card_id = card["payment_card_id"]
        result = apis.amazon.place_order(
            access_token=tokens["amazon"],
            payment_card_id=payment_card_id,
            address_id=address["address_id"],
        )
        if "order_id" in result:
            break
        failed_payment_attempts.append({{"payment_card_id": payment_card_id, "message": result.get("message")}})
    if "order_id" not in result:
        raise Exception(f"Unable to place Amazon receipt order: {{result}}")
    receipt_directory = infer_receipt_directory(product)
    download_path = receipt_path(receipt_directory, result["order_id"])
    receipt_result = apis.amazon.download_order_receipt(
        access_token=tokens["amazon"],
        order_id=result["order_id"],
        download_to_file_path=download_path,
        overwrite=True,
        file_system_access_token=tokens["file_system"],
    )
    if "file_path" not in receipt_result:
        raise Exception(f"Unable to download Amazon order receipt: {{receipt_result}}")
finally:
    restore_cart(cart_snapshot)

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "product_name": product_name,
    "product_id": product["product_id"],
    "quantity": quantity,
    "address_id": address["address_id"],
    "payment_card_id": payment_card_id,
    "order_id": result.get("order_id"),
    "receipt_path": receipt_result.get("file_path") if receipt_result else download_path,
    "cart_snapshot_count": len(cart_snapshot.get("cart_items", [])),
    "failed_payment_attempts": failed_payment_attempts,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_order_product_and_archive_receipt",
    )


def handle_amazon_download_all_order_receipts(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    directory_path = str(frame.get("directory_path") or "").strip()
    file_format = str(frame.get("file_format") or "").strip()
    if not directory_path.startswith("~/") or not directory_path.endswith("/") or not file_format:
        frame.abstain_reason = "missing_amazon_all_receipts_slots"
        return None
    code = common_appworld_prelude(["amazon", "file_system"]) + f"""
directory_path = {json.dumps(directory_path)}
file_format = {json.dumps(file_format)}

def filename_for_order(order):
    order_id = int(order["order_id"])
    date = str(order.get("created_at") or "")[:10]
    if not re.fullmatch(r"\\d{{4}}-\\d{{2}}-\\d{{2}}", date):
        raise Exception(f"Amazon order {{order_id}} has no yyyy-mm-dd created_at date.")
    if file_format == "ordered_at_yyyy-mm-dd_order_id_<order_id>.txt":
        return f"ordered_at_{{date}}_order_id_{{order_id}}.txt"
    if file_format == "ordered-at-yyyy-mm-dd-order-id-<order_id>.txt":
        return f"ordered-at-{{date}}-order-id-{{order_id}}.txt"
    if file_format == "yyyy-mm-dd__<order_id>.txt":
        return f"{{date}}__{{order_id}}.txt"
    raise Exception(f"Unsupported Amazon receipt filename format: {{file_format}}")

apis.file_system.create_directory(
    access_token=tokens["file_system"],
    directory_path=directory_path,
    recursive=True,
    allow_if_exists=True,
)
orders = paged(lambda page: apis.amazon.show_orders(
    access_token=tokens["amazon"],
    page_index=page,
    page_limit=20,
    sort_by="+created_at",
))
if not orders:
    raise Exception("No Amazon orders found.")

downloaded = []
for order in orders:
    target_path = directory_path.rstrip("/") + "/" + filename_for_order(order)
    result = apis.amazon.download_order_receipt(
        access_token=tokens["amazon"],
        order_id=order["order_id"],
        download_to_file_path=target_path,
        overwrite=True,
        file_system_access_token=tokens["file_system"],
    )
    if "file_path" not in result:
        raise Exception(f"Unable to download Amazon receipt for order {{order['order_id']}}: {{result}}")
    downloaded.append({{
        "order_id": int(order["order_id"]),
        "created_at": str(order.get("created_at") or "")[:10],
        "file_path": result["file_path"],
    }})

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "directory_path": directory_path,
    "file_format": file_format,
    "downloaded_count": len(downloaded),
    "downloaded": downloaded,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_download_all_order_receipts",
    )


def handle_amazon_order_trip_supplies_by_deadline(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    raw_product_types = frame.get("product_types") or []
    if not isinstance(raw_product_types, list) or len(raw_product_types) != 2:
        frame.abstain_reason = "missing_amazon_trip_product_types"
        return None
    product_types = [normalize_amazon_product_type(value) for value in raw_product_types]
    quantity = int(frame.get("quantity") or 0)
    trip_day = str(frame.get("trip_day") or "").strip().lower()
    address_name = str(frame.get("address_name") or "Home")
    card_name = str(frame.get("card_name") or "")
    if quantity < 1 or any(not value for value in product_types) or trip_day not in {"saturday", "sunday"}:
        frame.abstain_reason = "missing_amazon_trip_supply_slots"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
product_types = {json.dumps(product_types)}
quantity = {quantity}
trip_day = {json.dumps(trip_day)}
address_name = {json.dumps(address_name)}
card_name = {json.dumps(card_name)}

def normalize_text(value):
    value = str(value or "").lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def word_set(value):
    return set(normalize_text(value).split())

def singularize_word(word):
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("ches") or word.endswith("shes"):
        return word[:-2]
    if word.endswith("ses"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word

def normalized_word_set(value):
    words = set()
    for word in normalize_text(value).split():
        words.add(word)
        words.add(singularize_word(word))
    return words

def normalize_product_phrase(value):
    return " ".join(singularize_word(word) for word in normalize_text(value).split())

def product_type_matches(product, target_product_type):
    target_words = normalized_word_set(target_product_type)
    if normalize_product_phrase(product.get("product_type")) == normalize_product_phrase(target_product_type):
        return True
    text = " ".join([
        str(product.get("name") or ""),
        str(product.get("description") or ""),
        str(product.get("product_type") or ""),
    ])
    return bool(target_words) and target_words <= normalized_word_set(text)

def trip_deadline_days():
    now = DateTime.now()
    target_weekday = 5 if trip_day == "saturday" else 6
    days_until = (target_weekday - now.weekday()) % 7
    if days_until == 0:
        days_until = 7
    deadline = now.add(days=days_until - 1).end_of("day")
    current_end = now.end_of("day")
    return max(0, int((deadline.date() - current_end.date()).days))

max_delivery_days = trip_deadline_days()

def pick_address():
    addresses = apis.amazon.show_addresses(access_token=tokens["amazon"])
    for address in addresses:
        if normalize_text(address.get("name")) == normalize_text(address_name):
            return address
    if normalize_text(address_name) == "home" and len(addresses) == 1:
        return addresses[0]
    raise Exception(f"No unique Amazon address named {{address_name}}.")

def pick_payment_cards():
    cards = [
        card
        for card in apis.amazon.show_payment_cards(access_token=tokens["amazon"])
        if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
    ]
    candidates = []
    for card in cards:
        if card_name and normalize_text(card_name) not in normalize_text(card.get("card_name")):
            continue
        candidates.append(card)
    if not candidates:
        raise Exception(f"No Amazon payment card matched {{card_name or 'any card'}}.")
    return sorted(
        candidates,
        key=lambda card: (
            int(card.get("expiry_year") or 0),
            int(card.get("expiry_month") or 0),
            int(card["payment_card_id"]),
        ),
        reverse=True,
    )

def search_candidates(product_type):
    candidates = []
    products = paged(lambda page: apis.amazon.search_products(
        product_type=product_type,
        page_index=page,
        page_limit=20,
        sort_by="+delivery_days",
    ))
    if not products:
        products = paged(lambda page: apis.amazon.search_products(
            query=product_type,
            page_index=page,
            page_limit=20,
            sort_by="+delivery_days",
        ))
    for product in products:
        details = apis.amazon.show_product(product_id=product["product_id"])
        if not product_type_matches(details, product_type):
            continue
        inventory = int(details.get("inventory_quantity") or 0)
        delivery_days = int(details.get("delivery_days") or product.get("delivery_days") or 0)
        if inventory < quantity or delivery_days > max_delivery_days:
            continue
        candidates.append(details)
    candidates.sort(key=lambda product: (
        int(product.get("delivery_days") or 0),
        -float(product.get("rating") or 0),
        float(product.get("price") or 0),
        int(product["product_id"]),
    ))
    if not candidates:
        raise Exception(
            f"No in-stock Amazon {{product_type}} can deliver within {{max_delivery_days}} days."
        )
    return candidates[0]

selected = []
seen_product_ids = set()
for product_type in product_types:
    product = search_candidates(product_type)
    product_id = int(product["product_id"])
    if product_id in seen_product_ids:
        raise Exception(f"Same Amazon product selected for two product types: {{product_id}}")
    seen_product_ids.add(product_id)
    selected.append({{
        "product_type": product_type,
        "product_id": product_id,
        "product_name": product.get("name"),
        "delivery_days": int(product.get("delivery_days") or 0),
        "quantity": quantity,
    }})

apis.amazon.clear_cart(access_token=tokens["amazon"])
first = True
for item in selected:
    result = apis.amazon.add_product_to_cart(
        access_token=tokens["amazon"],
        product_id=item["product_id"],
        quantity=item["quantity"],
        clear_cart_first=first,
    )
    first = False
    if "not" in str(result.get("message", "")).lower() and "success" not in str(result.get("message", "")).lower():
        raise Exception(f"Unable to add Amazon trip supply {{item}}: {{result}}")

address = pick_address()
failed_payment_attempts = []
result = {{"message": "No payment card attempted."}}
payment_card_id = None
for card in pick_payment_cards():
    payment_card_id = card["payment_card_id"]
    result = apis.amazon.place_order(
        access_token=tokens["amazon"],
        payment_card_id=payment_card_id,
        address_id=address["address_id"],
    )
    if "order_id" in result:
        break
    failed_payment_attempts.append({{"payment_card_id": payment_card_id, "message": result.get("message")}})
if "order_id" not in result:
    raise Exception(f"Unable to place Amazon trip-supplies order: {{result}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "trip_day": trip_day,
    "max_delivery_days": max_delivery_days,
    "selected": selected,
    "quantity": quantity,
    "address_id": address["address_id"],
    "payment_card_id": payment_card_id,
    "order_id": result["order_id"],
    "failed_payment_attempts": failed_payment_attempts,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_order_trip_supplies_by_deadline",
    )


def handle_amazon_return_recent_orders(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    order_count = int(frame.get("order_count") or 0)
    deliverer_name = str(frame.get("deliverer_name") or "").strip()
    if order_count < 1 or not deliverer_name:
        frame.abstain_reason = "missing_amazon_recent_return_slots"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
order_count = {order_count}
deliverer_name = {json.dumps(deliverer_name)}

def pick_deliverer():
    deliverers = apis.amazon.show_return_deliverers()
    matches = [
        deliverer for deliverer in deliverers
        if str(deliverer.get("name") or "").strip().lower() == deliverer_name.strip().lower()
    ]
    if len(matches) != 1:
        raise Exception(f"Could not uniquely resolve Amazon return deliverer {{deliverer_name}}.")
    return matches[0]

orders = paged(lambda page: apis.amazon.show_orders(
    access_token=tokens["amazon"],
    page_index=page,
    page_limit=20,
    sort_by="-created_at",
))
orders = sorted(orders, key=lambda order: str(order.get("created_at") or ""), reverse=True)
target_orders = orders[:order_count]
if len(target_orders) != order_count:
    raise Exception(f"Expected {{order_count}} Amazon orders, found {{len(target_orders)}}.")

deliverer = pick_deliverer()
created_returns = []
skipped_fully_returned = []
for order in target_orders:
    order_id = order["order_id"]
    for item in order.get("order_items", []):
        ordered_quantity = int(item.get("ordered_quantity") or 0)
        returned_quantity = int(item.get("returned_quantity") or 0)
        quantity_to_return = ordered_quantity - returned_quantity
        if quantity_to_return <= 0:
            skipped_fully_returned.append({{
                "order_id": order_id,
                "product_id": item["product_id"],
                "ordered_quantity": ordered_quantity,
                "returned_quantity": returned_quantity,
            }})
            continue
        result = apis.amazon.initiate_return(
            access_token=tokens["amazon"],
            order_id=order_id,
            product_id=item["product_id"],
            deliverer_id=deliverer["deliverer_id"],
            quantity=quantity_to_return,
        )
        if "return_id" not in result:
            raise Exception(f"Unable to initiate return for order {{order_id}} product {{item['product_id']}}: {{result}}")
        created_returns.append({{
            "order_id": order_id,
            "product_id": item["product_id"],
            "quantity": quantity_to_return,
            "return_id": result["return_id"],
        }})
if not created_returns and not skipped_fully_returned:
    raise Exception("No returnable items found in recent Amazon orders.")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "order_count": order_count,
    "deliverer_name": deliverer["name"],
    "deliverer_id": deliverer["deliverer_id"],
    "target_order_ids": [order["order_id"] for order in target_orders],
    "created_returns": created_returns,
    "skipped_fully_returned": skipped_fully_returned,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_return_recent_orders",
    )


def handle_amazon_return_same_product_except_size_this_week(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    product_name = str(frame.get("product_name") or "").strip()
    keep_size = str(frame.get("keep_size") or "").strip().lower()
    deliverer_name = str(frame.get("deliverer_name") or "").strip()
    if not product_name or not keep_size or not deliverer_name:
        frame.abstain_reason = "missing_amazon_size_filtered_return_slots"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
target_product_name = {json.dumps(product_name)}
keep_size = {json.dumps(keep_size)}
preferred_deliverer_name = {json.dumps(deliverer_name)}

def normalize_text(value):
    value = str(value or "").lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def word_set(value):
    comparable = set()
    for word in normalize_text(value).split():
        if len(word) <= 1 or word in {{"and"}}:
            continue
        if word.endswith("ies"):
            word = word[:-3] + "y"
        elif word.endswith(("ches", "shes", "ses", "xes", "zes")):
            word = word[:-2]
        elif word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        comparable.add(word)
    return comparable

def product_matches(item, product):
    target_words = word_set(target_product_name)
    text = " ".join([
        str(item.get("product_name") or ""),
        str(product.get("name") or ""),
        str(product.get("description") or ""),
        str(product.get("product_type") or ""),
    ])
    words = word_set(text)
    return bool(target_words) and target_words <= words

def pick_deliverer():
    deliverers = apis.amazon.show_return_deliverers()
    exact = [
        deliverer for deliverer in deliverers
        if normalize_text(deliverer.get("name")) == normalize_text(preferred_deliverer_name)
    ]
    if exact:
        return exact[0]
    if deliverers:
        return sorted(deliverers, key=lambda row: int(row.get("deliverer_id") or 0))[0]
    raise Exception("No Amazon return deliverers available.")

now = DateTime.now()
min_created_at = now.start_of("week").to_date_string()
max_created_at = now.end_of("week").to_date_string()
orders = paged(lambda page: apis.amazon.show_orders(
    access_token=tokens["amazon"],
    page_index=page,
    page_limit=20,
    sort_by="-created_at",
))

return_targets = []
kept_items = []
matched_items = []
for order in orders:
    created_date = str(order.get("created_at") or "")[:10]
    if not (min_created_at <= created_date <= max_created_at):
        continue
    for item in order.get("order_items", []):
        product = apis.amazon.show_product(product_id=item["product_id"])
        if not product_matches(item, product):
            continue
        size = normalize_text(product.get("relative_size"))
        ordered_quantity = int(item.get("ordered_quantity") or 0)
        returned_quantity = int(item.get("returned_quantity") or 0)
        remaining_quantity = max(0, ordered_quantity - returned_quantity)
        matched_item = {{
            "order_id": order["order_id"],
            "product_id": item["product_id"],
            "product_name": item.get("product_name") or product.get("name"),
            "relative_size": product.get("relative_size"),
            "ordered_quantity": ordered_quantity,
            "returned_quantity": returned_quantity,
            "remaining_quantity": remaining_quantity,
            "created_at": order.get("created_at"),
        }}
        matched_items.append(matched_item)
        if size == normalize_text(keep_size):
            kept_items.append(matched_item)
            continue
        if remaining_quantity > 0:
            return_targets.append((order, item, product, remaining_quantity, matched_item))

if not kept_items:
    raise Exception(f"No this-week {{target_product_name}} item in keep size {{keep_size}} found.")
if not return_targets:
    raise Exception(f"No this-week {{target_product_name}} items outside keep size {{keep_size}} remain returnable. Matched: {{matched_items}}")

deliverer = pick_deliverer()
created_returns = []
for order, item, product, quantity_to_return, matched_item in return_targets:
    result = apis.amazon.initiate_return(
        access_token=tokens["amazon"],
        order_id=order["order_id"],
        product_id=item["product_id"],
        deliverer_id=deliverer["deliverer_id"],
        quantity=quantity_to_return,
    )
    if "return_id" not in result:
        raise Exception(f"Unable to initiate return for order {{order['order_id']}} product {{item['product_id']}}: {{result}}")
    created_returns.append({{
        **matched_item,
        "quantity": quantity_to_return,
        "return_id": result["return_id"],
    }})

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "product_name": target_product_name,
    "keep_size": keep_size,
    "date_window": [min_created_at, max_created_at],
    "deliverer_name": deliverer.get("name"),
    "deliverer_id": deliverer.get("deliverer_id"),
    "kept_items": kept_items,
    "created_returns": created_returns,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_return_same_product_except_size_this_week",
    )


def handle_amazon_buy_last_product_variants(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    product_type = frame.get("product_type")
    colors = frame.get("colors", [])
    address_name = frame.get("address_name") or "Home"
    card_name = frame.get("card_name") or ""
    if isinstance(colors, str):
        colors = [color.strip() for color in re.split(r"\band\b|,", colors, flags=re.IGNORECASE) if color.strip()]
    colors = [compact_text(str(color)).lower() for color in colors if str(color).strip()]
    if not product_type or len(colors) != 2:
        frame.abstain_reason = "missing_amazon_variant_purchase_slots"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
target_product_type = {json.dumps(normalize_amazon_product_type(product_type))}
target_colors = {json.dumps(colors)}
address_name = {json.dumps(str(address_name))}
card_name = {json.dumps(str(card_name))}

def normalize_text(value):
    value = str(value or "").lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def product_type_matches(product):
    return normalize_text(product.get("product_type")) == normalize_text(target_product_type)

def product_signature(product):
    name = normalize_text(product.get("name"))
    description = normalize_text(product.get("description"))
    for value in [
        normalize_text(product.get("color")),
        normalize_text(product.get("relative_size")),
        normalize_text(product.get("product_type")),
    ]:
        if value:
            name = re.sub(rf"\\b{{re.escape(value)}}\\b", " ", name)
            description = re.sub(rf"\\b{{re.escape(value)}}\\b", " ", description)
    return " ".join((name + " " + description).split())

def pick_address():
    addresses = apis.amazon.show_addresses(access_token=tokens["amazon"])
    for address in addresses:
        if normalize_text(address.get("name")) == normalize_text(address_name):
            return address
    if normalize_text(address_name) == "home" and len(addresses) == 1:
        return addresses[0]
    raise Exception(f"No unique Amazon address named {{address_name}}.")

def pick_payment_cards():
    cards = apis.amazon.show_payment_cards(access_token=tokens["amazon"])
    candidates = []
    for card in cards:
        if card_name and normalize_text(card_name) not in normalize_text(card.get("card_name")):
            continue
        candidates.append(card)
    if not candidates:
        raise Exception(f"No Amazon payment card matched {{card_name or 'any card'}}.")
    return sorted(
        candidates,
        key=lambda card: (
            int(card.get("expiry_year") or 0),
            int(card.get("expiry_month") or 0),
            int(card["payment_card_id"]),
        ),
        reverse=True,
    )

def find_last_ordered_product():
    orders = paged(lambda page: apis.amazon.show_orders(
        access_token=tokens["amazon"],
        query=target_product_type,
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    ))
    candidates = []
    for order in orders:
        for item in order.get("order_items", []):
            product = apis.amazon.show_product(product_id=item["product_id"])
            if not product_type_matches(product):
                continue
            candidates.append((str(order.get("created_at") or ""), int(order["order_id"]), int(item["product_id"]), order, item, product))
    if not candidates:
        raise Exception(f"No prior Amazon order matched {{target_product_type}}.")
    candidates.sort(reverse=True)
    return candidates[0][3], candidates[0][4], candidates[0][5]

def color_matches(product, target_color):
    return normalize_text(product.get("color")) == normalize_text(target_color)

def size_matches(product, target_size):
    return normalize_text(product.get("relative_size")) == normalize_text(target_size)

def choose_variant(original_product, target_color):
    target_size = original_product.get("relative_size")
    original_signature = product_signature(original_product)
    candidates = []
    variation_ids = [int(variation["product_id"]) for variation in original_product.get("variations", [])]
    if int(original_product["product_id"]) not in variation_ids:
        variation_ids.append(int(original_product["product_id"]))
    for product_id in variation_ids:
        product = apis.amazon.show_product(product_id=product_id)
        if not product_type_matches(product):
            continue
        if not color_matches(product, target_color):
            continue
        if not size_matches(product, target_size):
            continue
        if int(product.get("inventory_quantity") or 0) < 1:
            continue
        same_signature = int(product_signature(product) == original_signature)
        candidates.append((
            same_signature,
            float(product.get("rating") or 0),
            -float(product.get("price") or 0),
            -int(product["product_id"]),
            product,
        ))
    if not candidates:
        raise Exception(
            f"No in-stock {{target_product_type}} variant matched color={{target_color}} "
            f"and size={{target_size}} for product {{original_product['product_id']}}."
        )
    candidates.sort(reverse=True)
    return candidates[0][-1]

order, original_item, original_product = find_last_ordered_product()
if not original_product.get("relative_size"):
    raise Exception(f"Last ordered {{target_product_type}} product {{original_product['product_id']}} has no size.")

selected_products = []
for color in target_colors:
    product = choose_variant(original_product, color)
    selected_products.append(product)

if len({{int(product["product_id"]) for product in selected_products}}) != len(selected_products):
    raise Exception(f"Requested colors did not resolve to distinct product variants: {{selected_products}}")

apis.amazon.clear_cart(access_token=tokens["amazon"])
for product in selected_products:
    result = apis.amazon.add_product_to_cart(
        access_token=tokens["amazon"],
        product_id=product["product_id"],
        quantity=1,
        clear_cart_first=False,
    )
    if "not" in str(result.get("message", "")).lower() and "success" not in str(result.get("message", "")).lower():
        raise Exception(f"Unable to add product {{product['product_id']}} to cart: {{result}}")

address = pick_address()
failed_payment_attempts = []
result = {{"message": "No payment card attempted."}}
payment_card_id = None
for card in pick_payment_cards():
    payment_card_id = card["payment_card_id"]
    result = apis.amazon.place_order(
        access_token=tokens["amazon"],
        payment_card_id=payment_card_id,
        address_id=address["address_id"],
    )
    if "order_id" in result:
        break
    failed_payment_attempts.append({{"payment_card_id": payment_card_id, "message": result.get("message")}})
if "order_id" not in result:
    raise Exception(f"Unable to place Amazon variant order: {{result}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "product_type": target_product_type,
    "last_order_id": order["order_id"],
    "source_product_id": original_product["product_id"],
    "source_size": original_product.get("relative_size"),
    "target_colors": target_colors,
    "ordered_product_ids": [product["product_id"] for product in selected_products],
    "address_id": address["address_id"],
    "payment_card_id": payment_card_id,
    "order_id": result["order_id"],
    "failed_payment_attempts": failed_payment_attempts,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_buy_last_product_variants",
    )


def handle_amazon_replace_last_product_adjacent_size(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    product_type = frame.get("product_type")
    size_direction = str(frame.get("size_direction") or "").strip().lower()
    preferred_color = str(frame.get("preferred_color") or "").strip().lower()
    address_name = frame.get("address_name") or "Home"
    card_name = frame.get("card_name") or ""
    if not product_type or size_direction not in {"larger", "smaller"} or not preferred_color:
        frame.abstain_reason = "missing_amazon_adjacent_size_replacement_slots"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
target_product_type = {json.dumps(normalize_amazon_product_type(product_type))}
size_direction = {json.dumps(size_direction)}
preferred_color = {json.dumps(preferred_color)}
address_name = {json.dumps(str(address_name))}
card_name = {json.dumps(str(card_name))}
size_order = ["extra-small", "small", "medium", "large", "extra-large"]

def normalize_text(value):
    value = str(value or "").lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def word_set(value):
    comparable = set()
    for word in normalize_text(value).split():
        if len(word) <= 1 or word in {{"and"}}:
            continue
        if word.endswith("ies"):
            word = word[:-3] + "y"
        elif word.endswith(("ches", "shes", "ses", "xes", "zes")):
            word = word[:-2]
        elif word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        comparable.add(word)
    return comparable

def product_type_matches(product):
    target = normalize_text(target_product_type)
    if normalize_text(product.get("product_type")) == target:
        return True
    target_words = word_set(target)
    text = " ".join([
        str(product.get("name") or ""),
        str(product.get("description") or ""),
        str(product.get("product_type") or ""),
    ])
    return bool(target_words) and target_words <= word_set(text)

def product_signature(product):
    text = normalize_text(str(product.get("name") or "") + " " + str(product.get("description") or ""))
    for value in [
        normalize_text(product.get("color")),
        normalize_text(product.get("relative_size")),
        normalize_text(product.get("product_type")),
    ]:
        if value:
            text = re.sub(rf"\\b{{re.escape(value)}}\\b", " ", text)
    return " ".join(text.split())

def pick_address():
    addresses = apis.amazon.show_addresses(access_token=tokens["amazon"])
    for address in addresses:
        if normalize_text(address.get("name")) == normalize_text(address_name):
            return address
    if normalize_text(address_name) == "home" and len(addresses) == 1:
        return addresses[0]
    raise Exception(f"No unique Amazon address named {{address_name}}.")

def pick_payment_cards():
    cards = apis.amazon.show_payment_cards(access_token=tokens["amazon"])
    candidates = []
    for card in cards:
        if card_name and normalize_text(card_name) not in normalize_text(card.get("card_name")):
            continue
        candidates.append(card)
    if not candidates:
        raise Exception(f"No Amazon payment card matched {{card_name or 'any card'}}.")
    return sorted(
        candidates,
        key=lambda card: (
            int(card.get("expiry_year") or 0),
            int(card.get("expiry_month") or 0),
            int(card["payment_card_id"]),
        ),
        reverse=True,
    )

def pick_return_deliverer():
    deliverers = apis.amazon.show_return_deliverers()
    if not deliverers:
        raise Exception("No Amazon return deliverers available.")
    return sorted(deliverers, key=lambda row: int(row.get("deliverer_id") or 0))[0]

def adjacent_size(current_size):
    normalized = normalize_text(current_size)
    if normalized not in size_order:
        raise Exception(f"Unsupported size for replacement: {{current_size}}")
    index = size_order.index(normalized)
    target_index = index + 1 if size_direction == "larger" else index - 1
    if target_index < 0 or target_index >= len(size_order):
        raise Exception(f"No {{size_direction}} replacement size from {{current_size}}.")
    return size_order[target_index]

def find_last_ordered_product():
    orders = paged(lambda page: apis.amazon.show_orders(
        access_token=tokens["amazon"],
        query=target_product_type,
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    ))
    candidates = []
    for order in orders:
        for item in order.get("order_items", []):
            product = apis.amazon.show_product(product_id=item["product_id"])
            if not product_type_matches(product):
                continue
            remaining_quantity = int(item.get("ordered_quantity") or 0) - int(item.get("returned_quantity") or 0)
            if remaining_quantity <= 0:
                continue
            candidates.append((str(order.get("created_at") or ""), int(order["order_id"]), int(item["product_id"]), order, item, product, remaining_quantity))
    if not candidates:
        raise Exception(f"No returnable prior Amazon order matched {{target_product_type}}.")
    candidates.sort(reverse=True)
    return candidates[0][3], candidates[0][4], candidates[0][5], candidates[0][6]

def choose_replacement(original_product, target_size):
    original_signature = product_signature(original_product)
    original_color = normalize_text(original_product.get("color"))
    variation_ids = [int(variation["product_id"]) for variation in original_product.get("variations", [])]
    if int(original_product["product_id"]) not in variation_ids:
        variation_ids.append(int(original_product["product_id"]))
    candidates = []
    for product_id in variation_ids:
        product = apis.amazon.show_product(product_id=product_id)
        if not product_type_matches(product):
            continue
        if normalize_text(product.get("relative_size")) != normalize_text(target_size):
            continue
        if int(product.get("inventory_quantity") or 0) < 1:
            continue
        color = normalize_text(product.get("color"))
        preferred = int(color == normalize_text(preferred_color))
        same_color = int(color == original_color)
        if not preferred and not same_color:
            continue
        same_signature = int(product_signature(product) == original_signature)
        candidates.append((
            preferred,
            same_color,
            same_signature,
            float(product.get("rating") or 0),
            -float(product.get("price") or 0),
            -int(product["product_id"]),
            product,
        ))
    if not candidates:
        raise Exception(
            f"No in-stock replacement matched product={{original_product['product_id']}}, "
            f"target_size={{target_size}}, preferred_color={{preferred_color}}, or original_color={{original_color}}."
        )
    candidates.sort(reverse=True)
    return candidates[0][-1]

order, original_item, original_product, quantity_to_return = find_last_ordered_product()
target_size = adjacent_size(original_product.get("relative_size"))
replacement = choose_replacement(original_product, target_size)

deliverer = pick_return_deliverer()
return_result = apis.amazon.initiate_return(
    access_token=tokens["amazon"],
    order_id=order["order_id"],
    product_id=original_item["product_id"],
    deliverer_id=deliverer["deliverer_id"],
    quantity=quantity_to_return,
)
if "return_id" not in return_result:
    raise Exception(f"Unable to initiate return for order {{order['order_id']}} product {{original_item['product_id']}}: {{return_result}}")

apis.amazon.clear_cart(access_token=tokens["amazon"])
add_result = apis.amazon.add_product_to_cart(
    access_token=tokens["amazon"],
    product_id=replacement["product_id"],
    quantity=1,
    clear_cart_first=False,
)
if "not" in str(add_result.get("message", "")).lower() and "success" not in str(add_result.get("message", "")).lower():
    raise Exception(f"Unable to add replacement product {{replacement['product_id']}} to cart: {{add_result}}")

address = pick_address()
failed_payment_attempts = []
result = {{"message": "No payment card attempted."}}
payment_card_id = None
for card in pick_payment_cards():
    payment_card_id = card["payment_card_id"]
    result = apis.amazon.place_order(
        access_token=tokens["amazon"],
        payment_card_id=payment_card_id,
        address_id=address["address_id"],
    )
    if "order_id" in result:
        break
    failed_payment_attempts.append({{"payment_card_id": payment_card_id, "message": result.get("message")}})
if "order_id" not in result:
    raise Exception(f"Unable to place Amazon replacement order: {{result}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "product_type": target_product_type,
    "last_order_id": order["order_id"],
    "returned_product_id": original_item["product_id"],
    "return_id": return_result["return_id"],
    "return_quantity": quantity_to_return,
    "source_size": original_product.get("relative_size"),
    "target_size": target_size,
    "preferred_color": preferred_color,
    "replacement_product_id": replacement["product_id"],
    "replacement_color": replacement.get("color"),
    "address_id": address["address_id"],
    "payment_card_id": payment_card_id,
    "order_id": result["order_id"],
    "failed_payment_attempts": failed_payment_attempts,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_replace_last_product_adjacent_size",
    )


def handle_amazon_order_preferred_color_size_product(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    product_name = str(frame.get("product_name") or "").strip()
    relative_size = str(frame.get("relative_size") or "").strip().lower()
    color_preferences = frame.get("color_preferences", [])
    quantity = int(frame.get("quantity") or 0)
    address_name = frame.get("address_name") or "Home"
    card_name = frame.get("card_name") or ""
    if isinstance(color_preferences, str):
        color_preferences = [
            compact_text(part).lower()
            for part in color_preferences.split(">")
            if part.strip()
        ]
    color_preferences = [
        compact_text(str(color)).lower()
        for color in color_preferences
        if str(color).strip()
    ] if isinstance(color_preferences, list) else []
    if not product_name or relative_size not in {"extra-small", "small", "medium", "large", "extra-large"}:
        frame.abstain_reason = "missing_amazon_preferred_color_product_slots"
        return None
    if quantity < 1 or not color_preferences:
        frame.abstain_reason = "missing_amazon_preferred_color_order_slots"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
target_product_name = {json.dumps(product_name)}
target_relative_size = {json.dumps(relative_size)}
color_preferences = {json.dumps(color_preferences)}
quantity = {quantity}
address_name = {json.dumps(str(address_name))}
card_name = {json.dumps(str(card_name))}

def normalize_text(value):
    value = str(value or "").lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def word_set(value):
    comparable = set()
    for word in normalize_text(value).split():
        if len(word) <= 1 or word in {{"and"}}:
            continue
        if word.endswith("ies"):
            word = word[:-3] + "y"
        elif word.endswith(("ches", "shes", "ses", "xes", "zes")):
            word = word[:-2]
        elif word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        comparable.add(word)
    return comparable

def product_name_matches(product):
    target_words = word_set(target_product_name)
    text = " ".join([
        str(product.get("name") or ""),
        str(product.get("description") or ""),
        str(product.get("product_type") or ""),
    ])
    return bool(target_words) and target_words <= word_set(text)

def pick_address():
    addresses = apis.amazon.show_addresses(access_token=tokens["amazon"])
    for address in addresses:
        if normalize_text(address.get("name")) == normalize_text(address_name):
            return address
    if normalize_text(address_name) == "home" and len(addresses) == 1:
        return addresses[0]
    raise Exception(f"No unique Amazon address named {{address_name}}.")

def pick_payment_cards():
    cards = apis.amazon.show_payment_cards(access_token=tokens["amazon"])
    candidates = []
    for card in cards:
        if card_name and normalize_text(card_name) not in normalize_text(card.get("card_name")):
            continue
        candidates.append(card)
    if not candidates:
        raise Exception(f"No Amazon payment card matched {{card_name or 'any card'}}.")
    return sorted(
        candidates,
        key=lambda card: (
            int(card.get("expiry_year") or 0),
            int(card.get("expiry_month") or 0),
            int(card["payment_card_id"]),
        ),
        reverse=True,
    )

def find_product_for_color(color):
    products = paged(lambda page, color=color: apis.amazon.search_products(
        query=target_product_name,
        color=color,
        relative_size=target_relative_size,
        page_index=page,
        page_limit=20,
        sort_by="-rating",
    ))
    candidates = []
    for product in products:
        if normalize_text(product.get("color")) != normalize_text(color):
            continue
        if normalize_text(product.get("relative_size")) != normalize_text(target_relative_size):
            continue
        if not product_name_matches(product):
            continue
        if int(product.get("inventory_quantity") or 0) < quantity:
            continue
        exact_name = int(normalize_text(product.get("name")) == normalize_text(target_product_name))
        candidates.append((
            exact_name,
            float(product.get("rating") or 0),
            int(product.get("num_product_reviews") or 0),
            -float(product.get("price") or 0),
            -int(product["product_id"]),
            product,
        ))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][-1]

selected_color = None
selected_product = None
for color in color_preferences:
    product = find_product_for_color(color)
    if product is not None:
        selected_color = color
        selected_product = product
        break
if selected_product is None:
    raise Exception(f"No in-stock product matched {{target_product_name}}, size {{target_relative_size}}, preferences {{color_preferences}}.")

apis.amazon.clear_cart(access_token=tokens["amazon"])
add_result = apis.amazon.add_product_to_cart(
    access_token=tokens["amazon"],
    product_id=selected_product["product_id"],
    quantity=quantity,
    clear_cart_first=False,
)
if "not" in str(add_result.get("message", "")).lower() and "success" not in str(add_result.get("message", "")).lower():
    raise Exception(f"Unable to add product {{selected_product['product_id']}} to cart: {{add_result}}")

address = pick_address()
failed_payment_attempts = []
result = {{"message": "No payment card attempted."}}
payment_card_id = None
for card in pick_payment_cards():
    payment_card_id = card["payment_card_id"]
    result = apis.amazon.place_order(
        access_token=tokens["amazon"],
        payment_card_id=payment_card_id,
        address_id=address["address_id"],
    )
    if "order_id" in result:
        break
    failed_payment_attempts.append({{"payment_card_id": payment_card_id, "message": result.get("message")}})
if "order_id" not in result:
    raise Exception(f"Unable to place Amazon preferred-color order: {{result}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "product_name": target_product_name,
    "relative_size": target_relative_size,
    "color_preferences": color_preferences,
    "selected_color": selected_color,
    "product_id": selected_product["product_id"],
    "quantity": quantity,
    "address_id": address["address_id"],
    "payment_card_id": payment_card_id,
    "order_id": result["order_id"],
    "failed_payment_attempts": failed_payment_attempts,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_order_preferred_color_size_product",
    )


def handle_amazon_order_filtered_product(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    product_type = normalize_amazon_product_type(frame.get("product_type") or "")
    min_price_value = frame.get("min_price")
    max_price_value = frame.get("max_price")
    min_rating_value = frame.get("min_product_rating")
    min_reviews_value = frame.get("min_product_reviews")
    min_seller_rating_value = frame.get("min_seller_rating")
    price_bounds_inclusive = bool(frame.get("price_bounds_inclusive"))
    rating_threshold_inclusive = bool(frame.get("rating_threshold_inclusive"))
    prefer_highest_seller = bool(frame.get("prefer_highest_seller"))
    source_container = frame.get("source_container") or "search"
    prior_ordered_sellers_only = bool(frame.get("prior_ordered_sellers_only"))
    max_length_value = frame.get("max_length")
    max_width_value = frame.get("max_width")
    quantity_relationship = str(frame.get("quantity_relationship") or "").strip().lower()
    allow_mixed_products = bool(frame.get("allow_mixed_products", True))
    quantity = int(frame.get("quantity") or 0)
    address_name = frame.get("address_name") or "Home"
    card_name = frame.get("card_name") or ""
    if not product_type or (quantity < 1 and not quantity_relationship):
        frame.abstain_reason = "missing_amazon_filtered_product_order_slots"
        return None
    min_price = float(min_price_value) if min_price_value is not None else None
    max_price = float(max_price_value) if max_price_value is not None else None
    min_rating = float(min_rating_value) if min_rating_value is not None else None
    min_reviews = int(min_reviews_value) if min_reviews_value is not None else None
    min_seller_rating = float(min_seller_rating_value) if min_seller_rating_value is not None else None
    max_length = float(max_length_value) if max_length_value is not None else None
    max_width = float(max_width_value) if max_width_value is not None else None
    app_names = ["amazon"]
    if quantity_relationship:
        app_names.append("phone")
    code = common_appworld_prelude(app_names) + f"""
target_product_type = {json.dumps(product_type)}
min_price = {repr(min_price)}
max_price = {repr(max_price)}
min_rating = {repr(min_rating)}
min_reviews = {repr(min_reviews)}
min_seller_rating = {repr(min_seller_rating)}
price_bounds_inclusive = {repr(price_bounds_inclusive)}
rating_threshold_inclusive = {repr(rating_threshold_inclusive)}
prefer_highest_seller = {repr(prefer_highest_seller)}
source_container = {json.dumps(str(source_container))}
prior_ordered_sellers_only = {repr(prior_ordered_sellers_only)}
max_length = {repr(max_length)}
max_width = {repr(max_width)}
quantity_relationship = {json.dumps(quantity_relationship)}
allow_mixed_products = {repr(allow_mixed_products)}
quantity = {quantity}
address_name = {json.dumps(str(address_name))}
card_name = {json.dumps(str(card_name))}

def normalize_text(value):
    value = str(value or "").lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def word_set(value):
    comparable = set()
    for word in normalize_text(value).split():
        if len(word) <= 1 or word in {{"and"}}:
            continue
        if word.endswith("ies"):
            word = word[:-3] + "y"
        elif word.endswith(("ches", "shes", "ses", "xes", "zes")):
            word = word[:-2]
        elif word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        comparable.add(word)
    return comparable

def product_type_matches(product):
    product_type = normalize_text(product.get("product_type"))
    target = normalize_text(target_product_type)
    if product_type == target:
        return True
    target_words = word_set(target_product_type)
    text = " ".join([
        str(product.get("name") or ""),
        str(product.get("description") or ""),
        str(product.get("product_type") or ""),
    ])
    return bool(target_words) and target_words <= word_set(text)

def singular_relationship(value):
    value = normalize_text(value)
    if value in {{"roommates", "roommate"}}:
        return "roommate"
    if value in {{"siblings", "sibling", "sisters", "brothers"}}:
        return "sibling"
    return value[:-1] if value.endswith("s") else value

if quantity_relationship:
    relationship = singular_relationship(quantity_relationship)
    contacts = paged(lambda page: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship=relationship,
        page_index=page,
        page_limit=20,
    ))
    seen_contacts = set()
    for contact in contacts:
        key = contact.get("contact_id") or contact.get("email") or contact.get("phone_number")
        if key is not None:
            seen_contacts.add(str(key))
    quantity = len(seen_contacts)
    if quantity < 1:
        raise Exception(f"No phone contacts found for relationship {{quantity_relationship}}.")

def pick_address():
    addresses = apis.amazon.show_addresses(access_token=tokens["amazon"])
    for address in addresses:
        if normalize_text(address.get("name")) == normalize_text(address_name):
            return address
    for supervisor_address in apis.supervisor.show_addresses():
        if normalize_text(supervisor_address.get("name")) != normalize_text(address_name):
            continue
        add_result = apis.amazon.add_address(
            access_token=tokens["amazon"],
            name=supervisor_address["name"],
            street_address=supervisor_address["street_address"],
            city=supervisor_address["city"],
            state=supervisor_address["state"],
            country=supervisor_address["country"],
            zip_code=supervisor_address["zip_code"],
        )
        if "address_id" not in add_result:
            raise Exception(f"Unable to add Amazon address named {{address_name}}: {{add_result}}")
        for address in apis.amazon.show_addresses(access_token=tokens["amazon"]):
            if int(address.get("address_id") or -1) == int(add_result["address_id"]):
                return address
        return apis.amazon.show_addresses(access_token=tokens["amazon"])[-1]
    raise Exception(f"No unique Amazon address named {{address_name}}.")

def pick_payment_cards():
    cards = [
        card
        for card in apis.amazon.show_payment_cards(access_token=tokens["amazon"])
        if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
    ]
    candidates = []
    for card in cards:
        if card_name and normalize_text(card_name) not in normalize_text(card.get("card_name")):
            continue
        candidates.append(card)
    existing_card_numbers = {{str(card.get("card_number")) for card in cards}}
    supervisor_cards = sorted(
        [
            card
            for card in apis.supervisor.show_payment_cards()
            if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
        ],
        key=lambda card: (
            int(card.get("expiry_year") or 0),
            int(card.get("expiry_month") or 0),
            str(card.get("card_number") or ""),
        ),
        reverse=True,
    )
    for supervisor_card in supervisor_cards:
        if str(supervisor_card.get("card_number")) in existing_card_numbers:
            continue
        if card_name and normalize_text(card_name) not in normalize_text(supervisor_card.get("card_name")):
            continue
        add_result = apis.amazon.add_payment_card(
            access_token=tokens["amazon"],
            card_name=supervisor_card["card_name"],
            owner_name=supervisor_card["owner_name"],
            card_number=supervisor_card["card_number"],
            expiry_year=supervisor_card["expiry_year"],
            expiry_month=supervisor_card["expiry_month"],
            cvv_number=supervisor_card["cvv_number"],
        )
        if "payment_card_id" in add_result:
            added = dict(supervisor_card)
            added["payment_card_id"] = add_result["payment_card_id"]
            candidates.append(added)
            existing_card_numbers.add(str(supervisor_card.get("card_number")))
    if not candidates:
        raise Exception(f"No Amazon payment card matched {{card_name or 'any card'}}.")
    return sorted(
        candidates,
        key=lambda card: (
            int(card.get("expiry_year") or 0),
            int(card.get("expiry_month") or 0),
            int(card["payment_card_id"]),
        ),
        reverse=True,
    )

search_kwargs = {{
    "product_type": target_product_type,
    "page_index": 0,
    "page_limit": 20,
    "sort_by": "-rating",
}}
if min_price is not None:
    search_kwargs["min_price"] = min_price
if max_price is not None:
    search_kwargs["max_price"] = max_price
if min_rating is not None:
    search_kwargs["min_product_rating"] = min_rating
if min_seller_rating is not None:
    search_kwargs["min_seller_rating"] = min_seller_rating
if source_container == "wish_list":
    products = []
    for item in apis.amazon.show_wish_list(access_token=tokens["amazon"]):
        product = apis.amazon.show_product(product_id=item["product_id"])
        product["inventory_quantity"] = item.get("inventory_quantity", product.get("inventory_quantity"))
        product["wishlist_quantity"] = int(item.get("quantity") or 1)
        products.append(product)
elif source_container == "search":
    products = paged(lambda page: apis.amazon.search_products(
        **{{**search_kwargs, "page_index": page}}
    ))
else:
    raise Exception(f"Unsupported Amazon product source {{source_container}}.")
seller_cache = {{}}

def seller_for_product(product):
    seller_id = int(product.get("seller_id") or 0)
    if seller_id not in seller_cache:
        seller_cache[seller_id] = apis.amazon.show_seller(seller_id=seller_id)
    return seller_cache[seller_id]

prior_ordered_seller_ids = set()
if prior_ordered_sellers_only:
    orders = paged(lambda page: apis.amazon.show_orders(
        access_token=tokens["amazon"],
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    ))
    for order in orders:
        for item in order.get("order_items", []):
            product = apis.amazon.show_product(product_id=item["product_id"])
            seller_id = product.get("seller_id")
            if seller_id is not None:
                prior_ordered_seller_ids.add(int(seller_id))
    if not prior_ordered_seller_ids:
        raise Exception("No prior Amazon order sellers found.")

def below_minimum(value, threshold):
    if threshold is None:
        return False
    value = float(value or 0)
    if rating_threshold_inclusive:
        return value < threshold
    return value <= threshold

def fits_dimensions(product):
    if max_length is None or max_width is None:
        return True
    length = float(product.get("length") or 0)
    width = float(product.get("width") or 0)
    return (length <= max_length and width <= max_width) or (length <= max_width and width <= max_length)

candidates = []
for product in products:
    if not product_type_matches(product):
        continue
    if not fits_dimensions(product):
        continue
    inventory_quantity = int(product.get("inventory_quantity") or 0)
    if inventory_quantity < 1:
        continue
    price = float(product.get("price") or 0)
    if min_price is not None:
        if price_bounds_inclusive:
            if price < min_price:
                continue
        elif price <= min_price:
            continue
    if max_price is not None:
        if price_bounds_inclusive:
            if price > max_price:
                continue
        elif price >= max_price:
            continue
    if not allow_mixed_products and inventory_quantity < quantity:
        continue
    if below_minimum(product.get("rating"), min_rating):
        continue
    if min_reviews is not None and int(product.get("num_product_reviews") or 0) <= min_reviews:
        continue
    seller = seller_for_product(product)
    if prior_ordered_sellers_only and int(product.get("seller_id") or 0) not in prior_ordered_seller_ids:
        continue
    seller_rating = float(seller.get("rating") or 0)
    if below_minimum(seller_rating, min_seller_rating):
        continue
    if prefer_highest_seller:
        sort_key = (
            seller_rating,
            float(product.get("rating") or 0),
            int(product.get("num_product_reviews") or 0),
            -float(product.get("price") or 0),
            -float(product.get("delivery_days") or 0),
            -int(product["product_id"]),
        )
    else:
        sort_key = (
            float(product.get("rating") or 0),
            seller_rating,
            int(product.get("num_product_reviews") or 0),
            -float(product.get("price") or 0),
            -float(product.get("delivery_days") or 0),
            -int(product["product_id"]),
        )
    candidates.append((sort_key, product, seller, inventory_quantity))
if not candidates:
    raise Exception(
        f"No in-stock Amazon {{target_product_type}} matched max_price={{max_price}}, "
        f"min_rating={{min_rating}}, min_reviews={{min_reviews}}, "
        f"min_seller_rating={{min_seller_rating}}, "
        f"source={{source_container}}, max_length={{max_length}}, max_width={{max_width}}."
    )
candidates.sort(reverse=True)
remaining_quantity = quantity
selected_items = []
if allow_mixed_products:
    for _, product, seller, inventory_quantity in candidates:
        if remaining_quantity <= 0:
            break
        item_quantity = min(remaining_quantity, inventory_quantity)
        selected_items.append((product, seller, item_quantity))
        remaining_quantity -= item_quantity
else:
    _sort_key, product, seller, inventory_quantity = candidates[0]
    if inventory_quantity < quantity:
        raise Exception(
            f"Best in-stock {{target_product_type}} candidate has only {{inventory_quantity}} units; need {{quantity}}."
        )
    selected_items.append((product, seller, quantity))
    remaining_quantity = 0
if remaining_quantity > 0:
    raise Exception(
        f"Only found {{quantity - remaining_quantity}} in-stock {{target_product_type}} units "
        f"matching the requested filters; need {{quantity}}."
    )

apis.amazon.clear_cart(access_token=tokens["amazon"])
for product, seller, item_quantity in selected_items:
    add_result = apis.amazon.add_product_to_cart(
        access_token=tokens["amazon"],
        product_id=product["product_id"],
        quantity=item_quantity,
        clear_cart_first=False,
    )
    if "not" in str(add_result.get("message", "")).lower() and "success" not in str(add_result.get("message", "")).lower():
        raise Exception(f"Unable to add product {{product['product_id']}} to cart: {{add_result}}")

address = pick_address()
failed_payment_attempts = []
result = {{"message": "No payment card attempted."}}
payment_card_id = None
for card in pick_payment_cards():
    payment_card_id = card["payment_card_id"]
    result = apis.amazon.place_order(
        access_token=tokens["amazon"],
        payment_card_id=payment_card_id,
        address_id=address["address_id"],
    )
    if "order_id" in result:
        break
    failed_payment_attempts.append({{"payment_card_id": payment_card_id, "message": result.get("message")}})
if "order_id" not in result:
    raise Exception(f"Unable to place Amazon filtered-product order: {{result}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "product_type": target_product_type,
    "items": [
        {{
            "product_id": product["product_id"],
            "seller_id": product.get("seller_id"),
            "seller_rating": seller.get("rating"),
            "price": product.get("price"),
            "rating": product.get("rating"),
            "num_product_reviews": product.get("num_product_reviews"),
            "length": product.get("length"),
            "width": product.get("width"),
            "quantity": item_quantity,
        }}
        for product, seller, item_quantity in selected_items
    ],
    "quantity": quantity,
    "source_container": source_container,
    "quantity_relationship": quantity_relationship,
    "address_id": address["address_id"],
    "payment_card_id": payment_card_id,
    "order_id": result["order_id"],
    "failed_payment_attempts": failed_payment_attempts,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_order_filtered_product",
    )


def handle_amazon_post_question_last_ordered_product(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    product_type = frame.get("product_type")
    question = str(frame.get("question") or "").strip()
    if not product_type or not question:
        frame.abstain_reason = "missing_amazon_last_order_question_slots"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
target_product_type = {json.dumps(normalize_amazon_product_type(product_type))}
question = {json.dumps(question)}

def normalize_text(value):
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def word_set(value):
    return set(normalize_text(value).split())

def product_matches(item, product):
    target_words = word_set(target_product_type)
    item_text = " ".join([
        str(item.get("product_name") or ""),
        str(product.get("color") or ""),
        str(product.get("name") or ""),
        str(product.get("product_type") or ""),
        str(product.get("description") or ""),
    ])
    if normalize_text(product.get("product_type")) == normalize_text(target_product_type):
        return True
    return bool(target_words) and target_words <= word_set(item_text)

orders = paged(lambda page: apis.amazon.show_orders(
    access_token=tokens["amazon"],
    page_index=page,
    page_limit=20,
    sort_by="-created_at",
))
orders = sorted(orders, key=lambda order: str(order.get("created_at") or ""), reverse=True)
matches = []
for order in orders:
    for item in order.get("order_items", []):
        product = apis.amazon.show_product(product_id=item["product_id"])
        if product_matches(item, product):
            matches.append({{
                "order_id": order["order_id"],
                "created_at": order.get("created_at", ""),
                "product_id": item["product_id"],
                "product_name": item.get("product_name"),
            }})
if not matches:
    raise Exception(f"No prior Amazon order matched {{target_product_type}}.")
matches.sort(key=lambda row: (str(row.get("created_at") or ""), int(row["order_id"]), int(row["product_id"])), reverse=True)
selected = matches[0]
result = apis.amazon.write_product_question(
    access_token=tokens["amazon"],
    product_id=selected["product_id"],
    question=question,
)
if "question_id" not in result:
    raise Exception(f"Unable to post Amazon product question: {{result}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "product_type": target_product_type,
    "product_id": selected["product_id"],
    "order_id": selected["order_id"],
    "question_id": result["question_id"],
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_post_question_last_ordered_product",
    )


def handle_amazon_update_last_month_order_review(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    product_color = str(frame.get("product_color") or "").strip().lower()
    product_type = frame.get("product_type")
    target_rating = int(frame.get("target_rating") or 0)
    title = str(frame.get("title") or "").strip()
    if not product_color or not product_type or target_rating not in {1, 2, 3, 4, 5} or not title:
        frame.abstain_reason = "missing_amazon_review_update_slots"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
product_color = {json.dumps(product_color)}
product_type = {json.dumps(normalize_amazon_product_type(product_type))}
target_rating = {target_rating}
target_title = {json.dumps(title)}
color_aliases = {{
    "grey": {{"grey", "gray"}},
    "gray": {{"grey", "gray"}},
}}
product_color_values = color_aliases.get(product_color, {{product_color}})

def normalize_text(value):
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def word_set(value):
    return set(normalize_text(value).split())

def product_matches(item, product):
    item_text = " ".join([
        str(item.get("product_name") or ""),
        str(product.get("color") or ""),
        str(product.get("name") or ""),
        str(product.get("product_type") or ""),
        str(product.get("description") or ""),
    ])
    words = word_set(item_text)
    if not (product_color_values & words):
        return False
    if normalize_text(product.get("product_type")) == normalize_text(product_type):
        return True
    return word_set(product_type) <= words

now = DateTime.now()
min_created_at = now.subtract(months=1).start_of("month").to_date_string()
max_created_at = now.subtract(months=1).end_of("month").to_date_string()
orders = paged(lambda page: apis.amazon.show_orders(
    access_token=tokens["amazon"],
    page_index=page,
    page_limit=20,
    sort_by="-created_at",
))

matches = []
for order in orders:
    for item in order.get("order_items", []):
        product = apis.amazon.show_product(product_id=item["product_id"])
        if not product_matches(item, product):
            continue
        reviews = paged(lambda page, product_id=item["product_id"]: apis.amazon.show_product_reviews(
            product_id=product_id,
            user_email=profile["email"],
            page_index=page,
            page_limit=20,
            sort_by="-created_at",
        ))
        existing_review_id = item.get("product_review_id")
        for review in reviews:
            if existing_review_id and int(review.get("review_id") or -1) != int(existing_review_id):
                continue
            if not (min_created_at <= str(review.get("created_at") or "")[:10] <= max_created_at):
                continue
            matches.append({{
                "order_id": order["order_id"],
                "order_created_at": order.get("created_at", ""),
                "product_id": item["product_id"],
                "product_name": item.get("product_name"),
                "review_id": review["review_id"],
                "review_created_at": review.get("created_at", ""),
            }})

unique = {{}}
for match in matches:
    unique[int(match["review_id"])] = match
matches = list(unique.values())
if len(matches) != 1:
    raise Exception(f"Expected one last-month {{product_color}} {{product_type}} review target, found {{len(matches)}}: {{matches}}")

selected = matches[0]
result = apis.amazon.update_product_review(
    access_token=tokens["amazon"],
    review_id=selected["review_id"],
    rating=target_rating,
    title=target_title,
)
if not (isinstance(result, dict) and result.get("message")):
    raise Exception(f"Unable to update Amazon product review {{selected['review_id']}}: {{result}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "product_color": product_color,
    "product_type": product_type,
    "order_id": selected["order_id"],
    "product_id": selected["product_id"],
    "review_id": selected["review_id"],
    "target_rating": target_rating,
    "title": target_title,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_update_last_month_order_review",
    )


def handle_amazon_answer_last_order_question_yes_no(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    product_type = frame.get("product_type")
    question = str(frame.get("question") or "").strip()
    if not product_type or not question:
        frame.abstain_reason = "missing_amazon_last_order_question_answer_slots"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
target_product_type = {json.dumps(normalize_amazon_product_type(product_type))}
target_question = {json.dumps(question)}

def normalize_text(value):
    value = str(value or "").lower()
    value = re.sub(r"\\bfading\\b", "fade", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def word_set(value):
    return set(normalize_text(value).split())

def product_matches(item, product):
    target_words = word_set(target_product_type)
    item_text = " ".join([
        str(item.get("product_name") or ""),
        str(product.get("color") or ""),
        str(product.get("name") or ""),
        str(product.get("product_type") or ""),
        str(product.get("description") or ""),
    ])
    if normalize_text(product.get("product_type")) == normalize_text(target_product_type):
        return True
    return bool(target_words) and target_words <= word_set(item_text)

def question_matches(question_text):
    target_words = word_set(target_question)
    question_words = word_set(question_text)
    return bool(target_words) and target_words <= question_words

def classify_answer(answer_text):
    text = normalize_text(answer_text)
    if re.search(r"\\b(yes|yeah|yep|for sure|definitely|i have)\\b", text):
        return "yes"
    if re.search(r"\\b(no|nope|not|never|haven t|have not|doesn t|does not)\\b", text):
        return "no"
    return ""

orders = paged(lambda page: apis.amazon.show_orders(
    access_token=tokens["amazon"],
    page_index=page,
    page_limit=20,
    sort_by="-created_at",
))
orders = sorted(orders, key=lambda order: str(order.get("created_at") or ""), reverse=True)
candidates = []
for order in orders:
    for item in order.get("order_items", []):
        product = apis.amazon.show_product(product_id=item["product_id"])
        if not product_matches(item, product):
            continue
        questions = paged(lambda page, product_id=item["product_id"]: apis.amazon.show_product_questions(
            product_id=product_id,
            user_email=profile["email"],
            page_index=page,
            page_limit=20,
            sort_by="-created_at",
        ))
        for question in questions:
            if not question_matches(question.get("question")):
                continue
            answers = paged(lambda page, question_id=question["question_id"]: apis.amazon.show_product_question_answers(
                question_id=question_id,
                page_index=page,
                page_limit=20,
                sort_by="-created_at",
            ))
            labels = [classify_answer(answer.get("answer", "")) for answer in answers]
            labels = [label for label in labels if label]
            candidates.append({{
                "order_id": order["order_id"],
                "order_created_at": order.get("created_at", ""),
                "product_id": item["product_id"],
                "question_id": question["question_id"],
                "question": question.get("question"),
                "labels": labels,
            }})
if not candidates:
    raise Exception(f"No matching Amazon question found for last {{target_product_type}} order.")
candidates.sort(key=lambda row: (str(row.get("order_created_at") or ""), int(row["order_id"]), int(row["product_id"]), int(row["question_id"])), reverse=True)
selected = candidates[0]
labels = selected["labels"]
if not labels:
    raise Exception(f"Matching Amazon question {{selected['question_id']}} has no yes/no answers.")
label_set = set(labels)
if len(label_set) != 1:
    raise Exception(f"Conflicting yes/no answers for question {{selected['question_id']}}: {{labels}}")
answer = labels[0]
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{
    "product_type": target_product_type,
    "product_id": selected["product_id"],
    "order_id": selected["order_id"],
    "question_id": selected["question_id"],
    "answer": answer,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_answer_last_order_question_yes_no",
    )


def handle_amazon_answer_verified_battery_life_hours(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    product_name = str(frame.get("product_name") or "").strip()
    if not product_name:
        frame.abstain_reason = "missing_amazon_battery_life_product_name"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
target_product_name = {json.dumps(product_name)}

def normalize_text(value):
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def word_set(value):
    return set(normalize_text(value).split())

def score_product(product):
    target_words = word_set(target_product_name)
    name = str(product.get("name") or "")
    product_text = " ".join([
        name,
        str(product.get("product_type") or ""),
        str(product.get("description") or ""),
    ])
    product_words = word_set(product_text)
    if target_words and not target_words <= product_words:
        return None
    exact_name = normalize_text(name) == normalize_text(target_product_name)
    return (
        int(exact_name),
        len(target_words & word_set(name)),
        float(product.get("rating") or 0),
        int(product.get("num_product_reviews") or product.get("num_reviews") or 0),
        -int(product["product_id"]),
    )

def find_product():
    candidates = []
    for query in [target_product_name]:
        products = paged(lambda page, query=query: apis.amazon.search_products(
            query=query,
            page_index=page,
            page_limit=20,
        ))
        for product in products:
            score = score_product(product)
            if score is not None:
                candidates.append((score, product))
    unique = {{}}
    for score, product in candidates:
        product_id = int(product["product_id"])
        if product_id not in unique or score > unique[product_id][0]:
            unique[product_id] = (score, product)
    if not unique:
        raise Exception(f"No Amazon product matched {{target_product_name}}.")
    return sorted(unique.values(), key=lambda item: item[0], reverse=True)[0][1]

def extract_hour_values(text):
    text = str(text or "")
    lower = text.lower()
    snippets = []
    for match in re.finditer(r"battery|charge|lasts?|lasting|runtime|run time", lower):
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 140)
        snippets.append(text[start:end])
    snippets.append(text)
    values = []
    seen = set()
    patterns = [
        r"(?:battery|charge|runtime|run time|lasts?|lasting)[^\\.\\n]{{0,90}}?(?P<num>\\d+(?:\\.\\d+)?)\\s*(?:hours?|hrs?|hr\\b)",
        r"(?P<num>\\d+(?:\\.\\d+)?)\\s*(?:hours?|hrs?|hr\\b)[^\\.\\n]{{0,90}}?(?:battery|charge|runtime|run time|lasts?|lasting)",
        r"(?P<num>\\d+(?:\\.\\d+)?)\\s*(?:hours?|hrs?|hr\\b)",
    ]
    for snippet in snippets:
        for pattern in patterns:
            for match in re.finditer(pattern, snippet, flags=re.IGNORECASE):
                value = float(match.group("num"))
                if value <= 0 or value > 100:
                    continue
                key = int(value * 10)
                if key in seen:
                    continue
                seen.add(key)
                values.append(value)
    return values

def format_answer(value):
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return str(value).rstrip("0").rstrip(".")

product = find_product()
product_id = int(product["product_id"])
evidence = []
reviews = paged(lambda page: apis.amazon.show_product_reviews(
    product_id=product_id,
    query="battery hours",
    is_verified=True,
    page_index=page,
    page_limit=20,
    sort_by="-created_at",
))
for review in reviews:
    evidence.append({{
        "source": "review",
        "id": review.get("review_id"),
        "text": " ".join([
            str(review.get("title") or ""),
            str(review.get("text") or ""),
        ]),
    }})

questions = paged(lambda page: apis.amazon.show_product_questions(
    product_id=product_id,
    query="battery hours",
    page_index=page,
    page_limit=20,
    sort_by="-created_at",
))
for question in questions:
    answers = paged(lambda page, question_id=question["question_id"]: apis.amazon.show_product_question_answers(
        question_id=question_id,
        query="battery hours",
        is_verified=True,
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    ))
    for answer in answers:
        evidence.append({{
            "source": "question_answer",
            "id": answer.get("answer_id") or answer.get("question_answer_id"),
            "question_id": question["question_id"],
            "text": " ".join([
                str(question.get("question") or ""),
                str(answer.get("answer") or ""),
            ]),
        }})

hour_votes = {{}}
hour_examples = {{}}
for item in evidence:
    for value in extract_hour_values(item.get("text", "")):
        key = format_answer(value)
        hour_votes[key] = hour_votes.get(key, 0) + 1
        hour_examples.setdefault(key, []).append(item)

if not hour_votes:
    raise Exception(f"No verified purchaser battery-hour evidence found for product {{product_id}}.")

ranked = sorted(hour_votes.items(), key=lambda item: (item[1], -float(item[0])), reverse=True)
answer, count = ranked[0]
if len(ranked) > 1 and ranked[1][1] == count:
    raise Exception(f"Ambiguous verified purchaser battery-hour evidence for product {{product_id}}: {{hour_votes}}")

apis.supervisor.complete_task(answer=answer)
print(json.dumps({{
    "product_id": product_id,
    "product_name": product.get("name"),
    "answer": answer,
    "hour_votes": hour_votes,
    "evidence_count": len(evidence),
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_answer_verified_battery_life_hours",
    )


def handle_amazon_answer_returned_product_yes_no(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    product_type = frame.get("product_type")
    period = str(frame.get("period") or "").strip().lower()
    if not product_type or period not in {"this month", "this year", "this or last month"}:
        frame.abstain_reason = "missing_amazon_returned_product_answer_slots"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
target_product_type = {json.dumps(normalize_amazon_product_type(product_type))}
period = {json.dumps(period)}

def normalize_text(value):
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def word_set(value):
    return set(normalize_text(value).split())

def product_matches(return_row, product):
    target = normalize_text(target_product_type)
    if normalize_text(product.get("product_type")) == target:
        return True
    text = " ".join([
        str(return_row.get("product_name") or ""),
        str(product.get("name") or ""),
        str(product.get("product_type") or ""),
        str(product.get("description") or ""),
    ])
    target_words = word_set(target)
    return bool(target_words) and target_words <= word_set(text)

def date_window():
    now = DateTime.now()
    if period == "this month":
        return now.start_of("month").to_date_string(), now.end_of("month").to_date_string()
    if period == "this year":
        return now.start_of("year").to_date_string(), now.end_of("year").to_date_string()
    if period == "this or last month":
        start = now.subtract(months=1).start_of("month").to_date_string()
        end = now.end_of("month").to_date_string()
        return start, end
    raise Exception(f"Unsupported return answer period: {{period}}")

min_date, max_date = date_window()
returns = paged(lambda page: apis.amazon.show_returns(
    access_token=tokens["amazon"],
    page_index=page,
    page_limit=20,
    sort_by="-initiated_at",
))
matches = []
for row in returns:
    return_date = str(row.get("returned_at") or row.get("initiated_at") or "")[:10]
    if not return_date or not (min_date <= return_date <= max_date):
        continue
    product_id = row.get("product_id")
    if product_id is None:
        continue
    product = apis.amazon.show_product(product_id=int(product_id))
    if not product_matches(row, product):
        continue
    matches.append({{
        "return_id": row.get("return_id"),
        "order_id": row.get("order_id"),
        "product_id": int(product_id),
        "product_name": row.get("product_name") or product.get("name"),
        "return_date": return_date,
    }})

answer = "yes" if matches else "no"
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{
    "answer": answer,
    "period": period,
    "product_type": target_product_type,
    "date_window": [min_date, max_date],
    "matched_returns": matches,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_answer_returned_product_yes_no",
    )


def handle_amazon_answer_order_arrival_date(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    day_offset = int(frame.get("day_offset") or 0)
    date_format = str(frame.get("date_format") or "").strip().upper()
    if day_offset not in {0, 1} or date_format not in {"DD-MM", "MM-DD", "DD/MM"}:
        frame.abstain_reason = "missing_amazon_order_arrival_answer_slots"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
day_offset = {day_offset}
date_format = {json.dumps(date_format)}
now = DateTime.now()
target_date = now.subtract(days=day_offset).to_date_string()

orders = paged(lambda page: apis.amazon.show_orders(
    access_token=tokens["amazon"],
    page_index=page,
    page_limit=20,
    sort_by="-created_at",
))
target_orders = [
    order for order in orders
    if str(order.get("created_at") or "")[:10] == target_date
]
if not target_orders:
    raise Exception(f"No Amazon order found for {{target_date}}.")

expected_datetimes = []
order_ids = []
for order in target_orders:
    order_ids.append(order["order_id"])
    for item in order.get("order_items", []):
        expected = item.get("expected_delivery_at") or item.get("delivered_at")
        if expected:
            expected_datetimes.append(str(expected))
if not expected_datetimes:
    raise Exception(f"No expected delivery timestamps found for Amazon orders on {{target_date}}.")

latest = max(expected_datetimes)
latest_dt = DateTime.fromisoformat(latest)
if date_format == "DD-MM":
    answer = latest_dt.strftime("%d-%m")
elif date_format == "MM-DD":
    answer = latest_dt.strftime("%m-%d")
elif date_format == "DD/MM":
    answer = latest_dt.strftime("%d/%m")
else:
    raise Exception(f"Unsupported date format: {{date_format}}")

apis.supervisor.complete_task(answer=answer)
print(json.dumps({{
    "answer": answer,
    "date_format": date_format,
    "latest_expected_delivery_at": latest,
    "order_ids": sorted(order_ids),
    "target_date": target_date,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_answer_order_arrival_date",
    )


def handle_amazon_answer_spending_total(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    period = str(frame.get("period") or "").strip().lower()
    if period not in {
        "this calendar year",
        "the last calendar month",
        "this or the last calendar month",
    }:
        frame.abstain_reason = "missing_amazon_spending_total_period"
        return None
    code = common_appworld_prelude(["amazon"]) + f"""
period = {json.dumps(period)}
now = DateTime.now()
if period == "this calendar year":
    min_created_at = now.start_of("year").to_date_string()
    max_created_at = now.end_of("year").to_date_string()
elif period == "the last calendar month":
    min_created_at = now.subtract(months=1).start_of("month").to_date_string()
    max_created_at = now.subtract(months=1).end_of("month").to_date_string()
elif period == "this or the last calendar month":
    min_created_at = now.subtract(months=1).start_of("month").to_date_string()
    max_created_at = now.end_of("month").to_date_string()
else:
    raise Exception(f"Unsupported Amazon spending period: {{period}}")

orders = paged(lambda page: apis.amazon.show_orders(
    access_token=tokens["amazon"],
    page_index=page,
    page_limit=20,
    sort_by="-created_at",
))
matched_orders = []
total = 0.0
for order in orders:
    created_date = str(order.get("created_at") or "")[:10]
    if not created_date or not (min_created_at <= created_date <= max_created_at):
        continue
    paid = float(order.get("paid_amount") or 0)
    total += paid
    matched_orders.append({{
        "order_id": order.get("order_id"),
        "created_at": order.get("created_at"),
        "paid_amount": paid,
    }})
answer = str(int(round(total))) if abs(total - round(total)) < 1e-9 else str(round(total, 2))
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{
    "answer": answer,
    "period": period,
    "date_window": [min_created_at, max_created_at],
    "matched_orders": matched_orders,
    "total": total,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_answer_spending_total",
    )


def handle_amazon_answer_current_price_from_birthday_order(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    product_type = frame.get("product_type")
    relationship = str(frame.get("relationship") or "").strip().lower()
    if not product_type or relationship not in {"mother", "sister", "brother", "father", "parent", "sibling"}:
        frame.abstain_reason = "missing_amazon_current_price_birthday_order_slots"
        return None
    code = common_appworld_prelude(["phone", "amazon"]) + f"""
target_product_type = {json.dumps(normalize_amazon_product_type(product_type))}
relationship = {json.dumps(relationship)}

def normalize_text(value):
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def word_set(value):
    return set(normalize_text(value).split())

def product_matches(item, product):
    target = normalize_text(target_product_type)
    if normalize_text(product.get("product_type")) == target:
        return True
    item_text = " ".join([
        str(item.get("product_name") or ""),
        str(product.get("name") or ""),
        str(product.get("product_type") or ""),
        str(product.get("description") or ""),
    ])
    target_words = word_set(target)
    return bool(target_words) and target_words <= word_set(item_text)

def parse_birthday_date(value):
    birthday = str(value or "").strip()
    if not birthday:
        return None
    try:
        return DateTime.fromisoformat(birthday)
    except Exception:
        pass
    match = re.fullmatch(r"(\\d{{1,2}})[-/](\\d{{1,2}})(?:[-/](\\d{{2,4}}))?", birthday)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3) or DateTime.now().year)
        if year < 100:
            year += 1900
        return DateTime(year, month, day)
    return None

def amount_answer(value):
    amount = float(value)
    return str(int(round(amount))) if abs(amount - round(amount)) < 1e-9 else str(round(amount, 2))

contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship=relationship,
    page_index=page,
    page_limit=20,
))
if not contacts and relationship in {{"mother", "father"}}:
    contacts = paged(lambda page: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship="parent",
        page_index=page,
        page_limit=20,
    ))
if not contacts and relationship in {{"sister", "brother"}}:
    contacts = paged(lambda page: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship="sibling",
        page_index=page,
        page_limit=20,
    ))

now = DateTime.now()
candidate_dates = []
for contact in contacts:
    birthday_dt = parse_birthday_date(contact.get("birthday"))
    if birthday_dt is None:
        continue
    date = DateTime(now.year - 1, birthday_dt.month, birthday_dt.day).to_date_string()
    candidate_dates.append({{
        "date": date,
        "contact_id": contact.get("contact_id"),
        "name": contact.get("name"),
        "relationship": contact.get("relationship"),
    }})
if not candidate_dates:
    raise Exception(f"No {{relationship}} contacts with birthdays found.")

candidate_date_values = {{row["date"] for row in candidate_dates}}
orders = paged(lambda page: apis.amazon.show_orders(
    access_token=tokens["amazon"],
    page_index=page,
    page_limit=20,
    sort_by="-created_at",
))

matches = []
for order in orders:
    order_date = str(order.get("created_at") or "")[:10]
    if order_date not in candidate_date_values:
        continue
    for item in order.get("order_items", []):
        product = apis.amazon.show_product(product_id=item["product_id"])
        if not product_matches(item, product):
            continue
        matches.append({{
            "order_id": order.get("order_id"),
            "created_at": order.get("created_at"),
            "product_id": item.get("product_id"),
            "product_name": item.get("product_name") or product.get("name"),
            "product_type": product.get("product_type"),
            "current_price": float(product.get("price") or 0),
        }})

if len(matches) != 1:
    raise Exception(f"Expected exactly one {{target_product_type}} order on a {{relationship}} birthday last year, found {{len(matches)}}: {{matches}}")

selected = matches[0]
answer = amount_answer(selected["current_price"])
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{
    "answer": answer,
    "relationship": relationship,
    "product_type": target_product_type,
    "candidate_dates": candidate_dates,
    "selected": selected,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_amazon_answer_current_price_from_birthday_order",
    )


def handle_membership_paid_total(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    app_name = str(frame.get("app_name") or "").strip().lower()
    if app_name not in {"amazon", "spotify"}:
        frame.abstain_reason = "missing_membership_paid_total_app"
        return None
    code = common_appworld_prelude([app_name]) + f"""
app_name = {json.dumps(app_name)}

if app_name == "amazon":
    subscriptions = paged(lambda page: apis.amazon.show_prime_subscriptions(
        access_token=tokens["amazon"],
        page_index=page,
        page_limit=20,
    ))
elif app_name == "spotify":
    subscriptions = paged(lambda page: apis.spotify.show_premium_subscriptions(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    ))
else:
    raise Exception(f"Unsupported membership app: {{app_name}}")

total = 0.0
matched_subscriptions = []
for subscription in subscriptions:
    paid = float(subscription.get("paid_amount") or 0)
    total += paid
    matched_subscriptions.append({{
        "start_date": subscription.get("start_date"),
        "end_date": subscription.get("end_date"),
        "payment_card_digits": subscription.get("payment_card_digits"),
        "paid_amount": paid,
    }})

answer = str(int(round(total))) if abs(total - round(total)) < 1e-9 else str(round(total, 2))
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{
    "answer": answer,
    "app_name": app_name,
    "subscription_count": len(matched_subscriptions),
    "total": total,
    "subscriptions": matched_subscriptions,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_membership_paid_total",
    )


def handle_membership_last_payment_card_name(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    app_name = str(frame.get("app_name") or "").strip().lower()
    if app_name not in {"amazon", "spotify"}:
        frame.abstain_reason = "missing_membership_last_payment_card_app"
        return None
    code = common_appworld_prelude([app_name]) + f"""
app_name = {json.dumps(app_name)}

def last_digits(card_number):
    digits = re.sub(r"\\D+", "", str(card_number or ""))
    return digits[-4:] if len(digits) >= 4 else digits

if app_name == "amazon":
    subscriptions = paged(lambda page: apis.amazon.show_prime_subscriptions(
        access_token=tokens["amazon"],
        page_index=page,
        page_limit=20,
    ))
    app_payment_cards = apis.amazon.show_payment_cards(access_token=tokens["amazon"])
elif app_name == "spotify":
    subscriptions = paged(lambda page: apis.spotify.show_premium_subscriptions(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    ))
    app_payment_cards = apis.spotify.show_payment_cards(access_token=tokens["spotify"])
else:
    raise Exception(f"Unsupported membership app: {{app_name}}")

if not subscriptions:
    raise Exception(f"No membership subscriptions found for {{app_name}}.")

subscriptions.sort(key=lambda row: (str(row.get("start_date") or ""), str(row.get("end_date") or "")), reverse=True)
latest_subscription = subscriptions[0]
target_digits = re.sub(r"\\D+", "", str(latest_subscription.get("payment_card_digits") or ""))
if not target_digits:
    raise Exception(f"Latest membership subscription has no payment card digits for {{app_name}}.")

matches = []
for card in app_payment_cards:
    card_digits = last_digits(card.get("card_number"))
    if card_digits and target_digits.endswith(card_digits):
        matches.append(card)
if not matches:
    for card in apis.supervisor.show_payment_cards():
        card_digits = last_digits(card.get("card_number"))
        if card_digits and target_digits.endswith(card_digits):
            matches.append(card)

if len(matches) != 1:
    raise Exception(f"Expected exactly one payment card ending with {{target_digits}}, found {{len(matches)}}.")

answer = str(matches[0].get("card_name") or "").strip()
if not answer:
    raise Exception("Matched payment card has no card_name.")

apis.supervisor.complete_task(answer=answer)
print(json.dumps({{
    "answer": answer,
    "app_name": app_name,
    "latest_subscription": {{
        "start_date": latest_subscription.get("start_date"),
        "end_date": latest_subscription.get("end_date"),
        "payment_card_digits": latest_subscription.get("payment_card_digits"),
        "paid_amount": latest_subscription.get("paid_amount"),
    }},
    "matched_payment_card_digits": last_digits(matches[0].get("card_number")),
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_membership_last_payment_card_name",
    )


def handle_membership_remaining_duration(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    app_name = str(frame.get("app_name") or "").strip().lower()
    unit = str(frame.get("unit") or "").strip().lower()
    if app_name not in {"amazon", "spotify"} or unit not in {"days", "months"}:
        frame.abstain_reason = "missing_membership_remaining_duration_slots"
        return None
    code = common_appworld_prelude([app_name]) + f"""
app_name = {json.dumps(app_name)}
unit = {json.dumps(unit)}

if app_name == "amazon":
    subscriptions = paged(lambda page: apis.amazon.show_prime_subscriptions(
        access_token=tokens["amazon"],
        page_index=page,
        page_limit=20,
    ))
elif app_name == "spotify":
    subscriptions = paged(lambda page: apis.spotify.show_premium_subscriptions(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    ))
else:
    raise Exception(f"Unsupported membership app: {{app_name}}")

now = DateTime.now()
active = []
for subscription in subscriptions:
    end_raw = subscription.get("end_date")
    if not end_raw:
        continue
    end_dt = DateTime.fromisoformat(str(end_raw))
    start_raw = subscription.get("start_date")
    start_dt = DateTime.fromisoformat(str(start_raw)) if start_raw else None
    if end_dt >= now and (start_dt is None or start_dt <= now):
        active.append((end_dt, subscription))

if not active:
    answer = "0"
    chosen_subscription = None
    remaining_days = 0.0
else:
    active.sort(key=lambda item: item[0], reverse=True)
    end_dt, chosen_subscription = active[0]
    remaining_seconds = max(0.0, float(end_dt.timestamp() - now.timestamp()))
    remaining_days = remaining_seconds / 86400.0
    if unit == "days":
        remaining_calendar_days = max(0, (end_dt.date() - now.date()).days)
        answer = str(remaining_calendar_days)
    elif unit == "months":
        answer = str(int((remaining_days / 30.0) + 0.5))
    else:
        raise Exception(f"Unsupported duration unit: {{unit}}")

apis.supervisor.complete_task(answer=answer)
print(json.dumps({{
    "answer": answer,
    "app_name": app_name,
    "unit": unit,
    "remaining_days": remaining_days,
    "chosen_subscription": None if chosen_subscription is None else {{
        "start_date": chosen_subscription.get("start_date"),
        "end_date": chosen_subscription.get("end_date"),
        "payment_card_digits": chosen_subscription.get("payment_card_digits"),
        "paid_amount": chosen_subscription.get("paid_amount"),
    }},
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_membership_remaining_duration",
    )


def handle_delete_gmail_empty_drafts(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    condition = frame.get("condition")
    if condition not in {"both", "either"}:
        frame.abstain_reason = "missing_or_unsupported_gmail_draft_condition"
        return None
    code = common_appworld_prelude(["gmail"]) + f"""
condition = {json.dumps(condition)}
drafts = paged(lambda page: apis.gmail.show_drafts(
    access_token=tokens["gmail"],
    page_index=page,
    page_limit=20,
))
deleted = []
kept = []
for draft in drafts:
    subject_empty = not str(draft.get("subject") or "").strip()
    body_empty = not str(draft.get("body") or "").strip()
    should_delete = subject_empty and body_empty
    if condition == "either":
        should_delete = subject_empty or body_empty
    if should_delete:
        apis.gmail.delete_draft(
            access_token=tokens["gmail"],
            draft_id=draft["draft_id"],
        )
        deleted.append(draft["draft_id"])
    else:
        kept.append(draft["draft_id"])
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"condition": condition, "deleted": deleted, "kept": kept}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_delete_gmail_empty_drafts",
    )


def handle_gmail_send_future_scheduled_drafts_now(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["gmail", "file_system"]) + """
scheduled_drafts = paged(lambda page: apis.gmail.show_drafts(
    access_token=tokens["gmail"],
    scheduled=True,
    page_index=page,
    page_limit=20,
    sort_by="+created_at",
))

sent = []
for draft in scheduled_drafts:
    scheduled_send_at = draft.get("scheduled_send_at")
    if not scheduled_send_at:
        continue
    result = apis.gmail.send_email_from_draft(
        access_token=tokens["gmail"],
        draft_id=draft["draft_id"],
        file_system_access_token=tokens.get("file_system"),
    )
    sent.append({
        "draft_id": draft["draft_id"],
        "scheduled_send_at": scheduled_send_at,
        "sent_email_thread_id": result.get("sent_email_thread_id"),
        "sent_email_id": result.get("sent_email_id"),
    })

remaining = paged(lambda page: apis.gmail.show_drafts(
    access_token=tokens["gmail"],
    scheduled=True,
    page_index=page,
    page_limit=20,
))
if remaining:
    raise Exception(f"Expected no scheduled drafts after sending, found {[draft.get('draft_id') for draft in remaining]}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({"sent": sent}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_send_future_scheduled_drafts_now",
    )


def handle_gmail_amazon_promo_codes_answer(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["gmail"]) + """
def text_key(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

def thread_time(thread):
    return str(thread.get("created_at") or thread.get("updated_at") or "")

fetchers = [
    ("inbox", apis.gmail.show_inbox_threads),
    ("outbox", apis.gmail.show_outbox_threads),
    ("archived", apis.gmail.show_archived_threads),
    ("spam", apis.gmail.show_spam_threads),
    ("starred", apis.gmail.show_starred_threads),
    ("snoozed", apis.gmail.show_snoozed_threads),
]
queries = [
    "amazon promo code",
    "amazon promo",
    "promo code",
    "amazon coupon",
    "amazon discount",
    "amazon",
]

candidate_threads = {}
fetch_errors = []
for query in queries:
    for bucket, fetch in fetchers:
        try:
            threads = paged(lambda page, fetch=fetch, query=query: fetch(
                access_token=tokens["gmail"],
                query=query,
                page_index=page,
                page_limit=20,
                sort_by="+created_at",
            ))
        except Exception as exc:
            fetch_errors.append({"bucket": bucket, "query": query, "error": str(exc)})
            continue
        for thread in threads:
            thread_id = thread.get("email_thread_id")
            if thread_id is None:
                continue
            existing = candidate_threads.get(thread_id)
            if existing is None or thread_time(thread) < thread_time(existing):
                thread["_rave_bucket"] = bucket
                thread["_rave_query"] = query
                candidate_threads[thread_id] = thread

for bucket, fetch in fetchers:
    try:
        threads = paged(lambda page, fetch=fetch: fetch(
            access_token=tokens["gmail"],
            page_index=page,
            page_limit=20,
            sort_by="+created_at",
        ))
    except Exception as exc:
        fetch_errors.append({"bucket": bucket, "query": "", "error": str(exc)})
        continue
    for thread in threads:
        thread_id = thread.get("email_thread_id")
        if thread_id is None:
            continue
        thread["_rave_bucket"] = bucket
        thread["_rave_query"] = ""
        candidate_threads.setdefault(thread_id, thread)

promo_patterns = [
    r"\\bPromo\\s+Code\\s*(?:=>|:|=|-)\\s*([A-Za-z0-9][A-Za-z0-9_-]{2,})",
    r"\\bpromo\\s+code\\s*(?:is|=|=>|:|-)?\\s*([A-Za-z0-9][A-Za-z0-9_-]{2,})",
    r"\\bcoupon\\s+code\\s*(?:is|=|=>|:|-)?\\s*([A-Za-z0-9][A-Za-z0-9_-]{2,})",
    r"\\b(AMZ[A-Za-z0-9_-]{3,})\\b",
]
bad_codes = {"amazon", "promo", "promotion", "code", "coupon", "discount", "subject", "body"}

matches = []
seen_codes = set()
for thread_id in sorted(candidate_threads, key=lambda item: thread_time(candidate_threads[item])):
    detail = apis.gmail.show_thread(
        access_token=tokens["gmail"],
        email_thread_id=thread_id,
    )
    thread_created_at = str(detail.get("created_at") or candidate_threads[thread_id].get("created_at") or "")
    for email in detail.get("emails", []):
        subject = str(email.get("subject") or "")
        body = str(email.get("body") or "")
        sender = email.get("sender") or {}
        sender_text = " ".join([
            str(sender.get("name") or ""),
            str(sender.get("email") or ""),
        ])
        haystack_key = text_key(" ".join([subject, body, sender_text]))
        if "amazon" not in haystack_key:
            continue
        if not any(token in haystack_key for token in ["promo", "promotion", "discount", "coupon", "code"]):
            continue
        text = "\\n".join([subject, body])
        for pattern in promo_patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                code = match.group(1).strip().strip(".,;:!?)\\]}'\\\"")
                if not code or code.lower() in bad_codes:
                    continue
                if not re.fullmatch(r"AMZ[A-Za-z0-9_-]{3,}", code, flags=re.IGNORECASE):
                    continue
                start, end = match.span(1)
                nearby_key = text_key(text[max(0, start - 80): end + 80])
                if not (
                    "amazon" in haystack_key
                    or any(token in nearby_key for token in ["promo", "promotion", "discount", "coupon", "code"])
                ):
                    continue
                code_key = code.lower()
                if code_key in seen_codes:
                    continue
                seen_codes.add(code_key)
                matches.append({
                    "code": code,
                    "created_at": str(email.get("created_at") or thread_created_at),
                    "email_thread_id": thread_id,
                    "email_id": email.get("email_id"),
                    "subject": subject,
                })

if not matches:
    raise Exception(json.dumps({
        "error": "Could not find Amazon promo codes in Gmail.",
        "candidate_thread_count": len(candidate_threads),
        "fetch_errors": fetch_errors,
    }, sort_keys=True))

matches.sort(key=lambda item: (
    item["created_at"],
    str(item.get("email_thread_id") or ""),
    str(item.get("email_id") or ""),
    item["code"].lower(),
))
codes = [item["code"] for item in matches]
answer = ", ".join(codes)
apis.supervisor.complete_task(answer=answer)
print(json.dumps({
    "answer": answer,
    "codes": codes,
    "match_count": len(matches),
    "candidate_thread_count": len(candidate_threads),
    "matches": matches,
}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_amazon_promo_codes_answer",
    )


def handle_gmail_count_threads(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    mailbox = str(frame.get("mailbox") or "").strip().lower()
    read_state = str(frame.get("read_state") or "").strip().lower()
    label = str(frame.get("label") or "").strip().lower()
    if mailbox not in {"inbox", "outbox"} or read_state not in {"read", "unread"}:
        frame.abstain_reason = "missing_or_unsupported_gmail_thread_count_slots"
        return None
    if label and label not in {"priority-1", "priority-2", "priority-3"}:
        frame.abstain_reason = "missing_or_unsupported_gmail_thread_count_label"
        return None
    code = common_appworld_prelude(["gmail"]) + f"""
mailbox = {json.dumps(mailbox)}
read_state = {json.dumps(read_state)}
label = {json.dumps(label)}
fetch = apis.gmail.show_inbox_threads if mailbox == "inbox" else apis.gmail.show_outbox_threads
kwargs = {{
    "access_token": tokens["gmail"],
    "read": read_state == "read",
    "page_index": 0,
    "page_limit": 20,
    "sort_by": "+created_at",
}}
if label:
    kwargs["label"] = label

threads = []
page_index = 0
while True:
    kwargs["page_index"] = page_index
    batch = fetch(**kwargs)
    threads.extend(batch)
    if len(batch) < 20:
        break
    page_index += 1

seen_thread_ids = set()
thread_ids = []
for thread in threads:
    thread_id = thread.get("email_thread_id")
    if thread_id is None or thread_id in seen_thread_ids:
        continue
    seen_thread_ids.add(thread_id)
    thread_ids.append(thread_id)

answer = str(len(thread_ids))
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{
    "answer": answer,
    "mailbox": mailbox,
    "read_state": read_state,
    "label": label,
    "thread_count": len(thread_ids),
    "thread_ids": thread_ids,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_count_threads",
    )


def handle_gmail_schedule_resignation_draft(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    attachment_path = str(frame.get("attachment_path") or "").strip()
    weekday = str(frame.get("weekday") or "").strip().lower()
    try:
        week_offset = int(frame.get("week_offset") or 0)
        hour = int(frame.get("hour") or -1)
    except (TypeError, ValueError):
        frame.abstain_reason = "missing_or_invalid_resignation_schedule_slots"
        return None
    if not re.fullmatch(r"~/documents/work/[\w.\-]+\.pdf", attachment_path):
        frame.abstain_reason = "missing_or_invalid_resignation_attachment_path"
        return None
    if weekday not in {
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    } or week_offset not in {1, 2} or hour < 1 or hour > 11:
        frame.abstain_reason = "missing_or_invalid_resignation_schedule_slots"
        return None
    code = common_appworld_prelude(["gmail", "phone", "file_system"]) + f"""
attachment_path = {json.dumps(attachment_path)}
weekday = {json.dumps(weekday)}
week_offset = {week_offset}
hour = {hour}

weekday_to_index = {{
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}}

def text_key(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

def path_basename(path):
    return str(path).rstrip("/").split("/")[-1]

manager_contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship="manager",
    page_index=page,
    page_limit=20,
))
manager_emails = sorted({{
    str(contact.get("email") or "").strip().lower()
    for contact in manager_contacts
    if str(contact.get("email") or "").strip()
}})
if len(manager_emails) != 1:
    raise Exception(f"Expected exactly one manager email, found {{manager_emails}}.")
manager_email = manager_emails[0]

file_info = apis.file_system.show_file(
    access_token=tokens["file_system"],
    file_path=attachment_path,
)
if path_basename(attachment_path).lower() != path_basename(file_info.get("path") or attachment_path).lower():
    raise Exception(f"Unexpected file metadata for {{attachment_path}}: {{file_info}}")

now = DateTime.now()
days_until = (weekday_to_index[weekday] - now.weekday()) % 7
if days_until == 0:
    days_until = 7
days_until += 7 * (week_offset - 1)
scheduled_at = now.add(days=days_until).replace(hour=hour, minute=0, second=0, microsecond=0)
scheduled_send_at = scheduled_at.format("YYYY-MM-DD|HH:mm:ss")

drafts = paged(lambda page: apis.gmail.show_drafts(
    access_token=tokens["gmail"],
    query="resignation",
    page_index=page,
    page_limit=20,
    sort_by="-updated_at",
))
if not drafts:
    drafts = paged(lambda page: apis.gmail.show_drafts(
        access_token=tokens["gmail"],
        page_index=page,
        page_limit=20,
        sort_by="-updated_at",
    ))

candidates = []
for draft in drafts:
    subject = str(draft.get("subject") or "")
    body = str(draft.get("body") or "")
    haystack = text_key(subject + " " + body)
    if "resignation" not in haystack and "resign" not in haystack:
        continue
    recipients = draft.get("recipients") or []
    recipient_emails = sorted({{
        str(recipient.get("email") or "").strip().lower()
        for recipient in recipients
        if str(recipient.get("email") or "").strip()
    }})
    if recipient_emails and manager_email not in recipient_emails:
        continue
    candidates.append({{
        "draft": draft,
        "recipient_emails": recipient_emails,
    }})

if len(candidates) != 1:
    raise Exception(f"Expected one resignation draft for manager {{manager_email}}, found {{len(candidates)}}.")

draft = candidates[0]["draft"]
draft_id = draft["draft_id"]
recipient_emails = candidates[0]["recipient_emails"] or [manager_email]
apis.gmail.update_draft(
    access_token=tokens["gmail"],
    draft_id=draft_id,
    email_addresses=recipient_emails,
)
attachment_result = apis.gmail.upload_attachments_to_draft(
    access_token=tokens["gmail"],
    draft_id=draft_id,
    attachment_file_paths=[attachment_path],
    overwrite=True,
    file_system_access_token=tokens["file_system"],
)
apis.gmail.update_draft(
    access_token=tokens["gmail"],
    draft_id=draft_id,
    scheduled_send_at=scheduled_send_at,
)
updated = apis.gmail.show_draft(
    access_token=tokens["gmail"],
    draft_id=draft_id,
)
if str(updated.get("scheduled_send_at") or "").replace("T", "|")[:16] != scheduled_send_at[:16]:
    raise Exception(f"Draft schedule mismatch: expected {{scheduled_send_at}}, got {{updated.get('scheduled_send_at')}}")
updated_attachment_names = {{
    str(attachment.get("file_name") or "").strip().lower()
    for attachment in updated.get("attachments", []) or []
}}
if path_basename(attachment_path).lower() not in updated_attachment_names:
    raise Exception(f"Draft attachment missing after update: {{updated_attachment_names}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "draft_id": draft_id,
    "manager_email": manager_email,
    "recipient_emails": recipient_emails,
    "attachment_path": attachment_path,
    "scheduled_send_at": scheduled_send_at,
    "attachment_result": attachment_result,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_schedule_resignation_draft",
    )


def handle_gmail_thread_cleanup(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    action = str(frame.get("action") or "").strip().lower()
    exception_mode = str(frame.get("exception_mode") or "").strip().lower()
    if action not in {"archive", "delete"} or exception_mode not in {"and", "or"}:
        frame.abstain_reason = "missing_or_unsupported_gmail_thread_cleanup_slots"
        return None
    code = common_appworld_prelude(["gmail"]) + f"""
action = {json.dumps(action)}
exception_mode = {json.dumps(exception_mode)}
seen_thread_ids = set()
threads = []
threads.extend(paged(lambda page: apis.gmail.show_inbox_threads(
    access_token=tokens["gmail"],
    read=True,
    archived=False,
    page_index=page,
    page_limit=20,
)))
threads.extend(paged(lambda page: apis.gmail.show_outbox_threads(
    access_token=tokens["gmail"],
    read=True,
    archived=False,
    page_index=page,
    page_limit=20,
)))
processed = []
skipped = []
for thread in threads:
    thread_id = thread["email_thread_id"]
    if thread_id in seen_thread_ids:
        continue
    seen_thread_ids.add(thread_id)
    label = str(thread.get("label") or "").lower()
    priority_label = "priority" in label
    starred = bool(thread.get("starred"))
    skip = priority_label or starred
    if exception_mode == "and":
        skip = priority_label and starred
    if skip:
        skipped.append(thread_id)
        continue
    if action == "archive":
        apis.gmail.mark_thread_archived(
            access_token=tokens["gmail"],
            email_thread_id=thread_id,
        )
    else:
        apis.gmail.delete_thread(
            access_token=tokens["gmail"],
            email_thread_id=thread_id,
        )
    processed.append(thread_id)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"action": action, "exception_mode": exception_mode, "processed": processed, "skipped": skipped}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_thread_cleanup",
    )


def handle_gmail_mark_threads_read_state_by_calendar_window(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    target_state = str(frame.get("target_state") or "").strip().lower()
    window = str(frame.get("window") or "").strip().lower()
    if target_state not in {"read", "unread"} or window not in {
        "before_the_last_calendar_month",
        "in_the_current_calendar_month",
        "before_the_current_calendar_year",
    }:
        frame.abstain_reason = "missing_or_unsupported_gmail_read_state_window"
        return None
    code = common_appworld_prelude(["gmail"]) + f"""
target_state = {json.dumps(target_state)}
window = {json.dumps(window)}
now = DateTime.now()
if window == "before_the_last_calendar_month":
    min_created_at = "1500-01-01"
    max_created_at = now.subtract(months=1).start_of("month").subtract(microseconds=1).to_date_string()
elif window == "in_the_current_calendar_month":
    min_created_at = now.start_of("month").to_date_string()
    max_created_at = now.end_of("month").to_date_string()
elif window == "before_the_current_calendar_year":
    min_created_at = "1500-01-01"
    max_created_at = now.start_of("year").subtract(microseconds=1).to_date_string()
else:
    raise Exception(f"Unsupported calendar window: {{window}}")

target_read = target_state == "read"
seen_thread_ids = set()
threads = []
for fetch in [apis.gmail.show_inbox_threads, apis.gmail.show_outbox_threads]:
    threads.extend(paged(lambda page, fetch=fetch: fetch(
        access_token=tokens["gmail"],
        min_created_at=min_created_at,
        max_created_at=max_created_at,
        page_index=page,
        page_limit=20,
        sort_by="+created_at",
    )))

processed = []
already_matching = []
for thread in threads:
    thread_id = thread["email_thread_id"]
    if thread_id in seen_thread_ids:
        continue
    seen_thread_ids.add(thread_id)
    current_read = bool(thread.get("read"))
    if current_read == target_read:
        already_matching.append(thread_id)
        continue
    if target_read:
        apis.gmail.mark_thread_read(
            access_token=tokens["gmail"],
            email_thread_id=thread_id,
        )
    else:
        apis.gmail.mark_thread_unread(
            access_token=tokens["gmail"],
            email_thread_id=thread_id,
        )
    processed.append(thread_id)

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "target_state": target_state,
    "window": window,
    "min_created_at": min_created_at,
    "max_created_at": max_created_at,
    "processed": processed,
    "already_matching": already_matching,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_mark_threads_read_state_by_calendar_window",
    )


def handle_gmail_delete_archived_threads_by_calendar_window(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    window = str(frame.get("window") or "").strip().lower()
    if window not in {
        "before_this_calendar_month",
        "this_calendar_month",
        "this_or_the_last_calendar_month",
    }:
        frame.abstain_reason = "missing_or_unsupported_gmail_archived_delete_window"
        return None
    code = common_appworld_prelude(["gmail"]) + f"""
window = {json.dumps(window)}
now = DateTime.now()
if window == "before_this_calendar_month":
    min_created_at = "1500-01-01"
    max_created_at = now.start_of("month").subtract(microseconds=1).to_date_string()
elif window == "this_calendar_month":
    min_created_at = now.start_of("month").to_date_string()
    max_created_at = now.end_of("month").to_date_string()
elif window == "this_or_the_last_calendar_month":
    min_created_at = now.subtract(months=1).start_of("month").to_date_string()
    max_created_at = now.end_of("month").to_date_string()
else:
    raise Exception(f"Unsupported archived delete window: {{window}}")

candidate_threads = paged(lambda page: apis.gmail.show_archived_threads(
    access_token=tokens["gmail"],
    min_created_at=min_created_at,
    max_created_at=max_created_at,
    page_index=page,
    page_limit=20,
    sort_by="+created_at",
))
thread_ids = []
seen_thread_ids = set()
for thread in candidate_threads:
    thread_id = thread.get("email_thread_id")
    if thread_id is None or thread_id in seen_thread_ids:
        continue
    seen_thread_ids.add(thread_id)
    thread_ids.append(thread_id)

deleted = []
for thread_id in thread_ids:
    apis.gmail.delete_thread(
        access_token=tokens["gmail"],
        email_thread_id=thread_id,
    )
    deleted.append(thread_id)

remaining = paged(lambda page: apis.gmail.show_archived_threads(
    access_token=tokens["gmail"],
    min_created_at=min_created_at,
    max_created_at=max_created_at,
    page_index=page,
    page_limit=20,
    sort_by="+created_at",
))
remaining_ids = [thread.get("email_thread_id") for thread in remaining]
if remaining_ids:
    raise Exception(f"Expected no archived Gmail threads in window after deletion, found {{remaining_ids}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "window": window,
    "min_created_at": min_created_at,
    "max_created_at": max_created_at,
    "deleted": deleted,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_delete_archived_threads_by_calendar_window",
    )


def handle_gmail_forward_anniversary_announcement_email(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    recipient_email = str(frame.get("recipient_email") or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", recipient_email):
        frame.abstain_reason = "missing_or_invalid_gmail_forward_recipient_email"
        return None
    code = common_appworld_prelude(["gmail"]) + f"""
recipient_email = {json.dumps(recipient_email)}

def text_key(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

threads = paged(lambda page: apis.gmail.show_outbox_threads(
    access_token=tokens["gmail"],
    query="anniversary celebration announcement",
    page_index=page,
    page_limit=20,
    sort_by="-created_at",
))
if not threads:
    threads = paged(lambda page: apis.gmail.show_outbox_threads(
        access_token=tokens["gmail"],
        query="anniversary celebration",
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    ))
if not threads:
    threads = paged(lambda page: apis.gmail.show_outbox_threads(
        access_token=tokens["gmail"],
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    ))

candidates = []
seen_thread_ids = set()
for thread in threads:
    thread_id = thread.get("email_thread_id")
    if thread_id is None or thread_id in seen_thread_ids:
        continue
    seen_thread_ids.add(thread_id)
    detail = apis.gmail.show_thread(
        access_token=tokens["gmail"],
        email_thread_id=thread_id,
    )
    for email in detail.get("emails", []):
        sender = email.get("sender") or {{}}
        sender_email = str(sender.get("email") or "").strip().lower()
        if sender_email != user.email.lower():
            continue
        subject = str(email.get("subject") or "")
        body = str(email.get("body") or "")
        haystack = text_key(subject + " " + body)
        subject_key = text_key(subject)
        if "anniversary" not in haystack or "celebration" not in haystack:
            continue
        if "anniversary celebration" not in subject_key and "announce" not in haystack:
            continue
        recipient_emails = {{
            str(recipient.get("email") or "").strip().lower()
            for recipient in email.get("recipients", []) or []
            if str(recipient.get("email") or "").strip()
        }}
        candidates.append({{
            "email_thread_id": thread_id,
            "email_id": email["email_id"],
            "created_at": email.get("created_at") or detail.get("created_at") or "",
            "subject": subject,
            "recipient_emails": sorted(recipient_emails),
        }})

if not candidates:
    raise Exception("Could not find a sent anniversary celebration announcement email to forward.")
candidates.sort(key=lambda item: item["created_at"], reverse=True)
target = candidates[0]
if recipient_email in target["recipient_emails"]:
    raise Exception(f"Recipient {{recipient_email}} already appears on the selected announcement email.")

result = apis.gmail.forward_email_from_thread(
    access_token=tokens["gmail"],
    email_thread_id=target["email_thread_id"],
    email_id=target["email_id"],
    email_addresses=[recipient_email],
    draft_not_send=False,
)
if "sent_email_id" not in result and "sent_email_thread_id" not in result:
    raise Exception(f"Unable to forward announcement email: {{result}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "recipient_email": recipient_email,
    "source_email_thread_id": target["email_thread_id"],
    "source_email_id": target["email_id"],
    "candidate_count": len(candidates),
    "forward_result": result,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_forward_anniversary_announcement_email",
    )


def handle_gmail_forward_caterer_bill_to_manager_with_note(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    note_prefix = str(frame.get("note_prefix") or "").strip()
    if not note_prefix:
        frame.abstain_reason = "missing_gmail_caterer_bill_note_prefix"
        return None
    code = common_appworld_prelude(["gmail", "phone"]) + f"""
note_prefix = {json.dumps(note_prefix)}

def text_key(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

def email_set(contacts):
    return {{
        str(contact.get("email") or "").strip().lower()
        for contact in contacts
        if str(contact.get("email") or "").strip()
    }}

manager_contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship="manager",
    page_index=page,
    page_limit=20,
))
manager_emails = email_set(manager_contacts)
if len(manager_emails) != 1:
    raise Exception(f"Expected exactly one manager email, found {{sorted(manager_emails)}}.")
manager_email = next(iter(manager_emails))

queries = [
    "catering company celebration bill",
    "caterer company celebration bill",
    "company celebration bill",
    "catering bill",
    "bill",
]
threads = []
seen_thread_ids = set()
for query in queries:
    for thread in paged(lambda page, query=query: apis.gmail.show_inbox_threads(
        access_token=tokens["gmail"],
        query=query,
        attachment=True,
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    )):
        thread_id = thread.get("email_thread_id")
        if thread_id is None or thread_id in seen_thread_ids:
            continue
        seen_thread_ids.add(thread_id)
        threads.append(thread)

if not threads:
    threads = paged(lambda page: apis.gmail.show_inbox_threads(
        access_token=tokens["gmail"],
        attachment=True,
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    ))

candidates = []
for thread in threads:
    thread_id = thread.get("email_thread_id")
    if thread_id is None:
        continue
    detail = apis.gmail.show_thread(
        access_token=tokens["gmail"],
        email_thread_id=thread_id,
    )
    for email in detail.get("emails", []):
        sender_email = str((email.get("sender") or {{}}).get("email") or "").strip().lower()
        if sender_email == user.email.lower():
            continue
        subject = str(email.get("subject") or "")
        body = str(email.get("body") or "")
        sender_name = str((email.get("sender") or {{}}).get("name") or "")
        haystack = text_key(" ".join([subject, body, sender_name, sender_email]))
        attachments = email.get("attachments") or []
        attachment_names = " ".join(str(item.get("file_name") or "") for item in attachments)
        attachment_key = text_key(attachment_names)
        has_bill_attachment = bool(attachments) and ("bill" in attachment_key or "invoice" in attachment_key)
        has_bill_text = "bill" in haystack or "invoice" in haystack
        has_catering_text = (
            "catering" in haystack
            or "caterer" in haystack
            or "caterers" in haystack
            or "cuisine" in haystack
        )
        has_celebration_text = "company celebration" in haystack or (
            "company" in haystack and ("celebration" in haystack or "party" in haystack)
        )
        if not (has_bill_text and has_catering_text and has_celebration_text and has_bill_attachment):
            continue
        candidates.append({{
            "email_thread_id": thread_id,
            "email_id": email["email_id"],
            "created_at": email.get("created_at") or detail.get("created_at") or "",
            "subject": subject,
            "sender_email": sender_email,
            "attachment_count": len(attachments),
        }})

if not candidates:
    raise Exception("Could not find the caterer bill email for the company celebration.")
candidates.sort(key=lambda item: item["created_at"], reverse=True)
target = candidates[0]

forward = apis.gmail.forward_email_from_thread(
    access_token=tokens["gmail"],
    email_thread_id=target["email_thread_id"],
    email_id=target["email_id"],
    email_addresses=[manager_email],
    draft_not_send=True,
)
draft_id = forward.get("draft_id")
if draft_id is None:
    raise Exception(f"Forward did not create a draft: {{forward}}")
draft = apis.gmail.show_draft(
    access_token=tokens["gmail"],
    draft_id=draft_id,
)
old_body = str(draft.get("body") or "")
new_body = note_prefix + "\\n\\n" + old_body
apis.gmail.update_draft(
    access_token=tokens["gmail"],
    draft_id=draft_id,
    body=new_body,
)
sent = apis.gmail.send_email_from_draft(
    access_token=tokens["gmail"],
    draft_id=draft_id,
)
if "sent_email_id" not in sent and "sent_email_thread_id" not in sent:
    raise Exception(f"Unable to send caterer bill forward: {{sent}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "manager_email": manager_email,
    "note_prefix": note_prefix,
    "source_email_thread_id": target["email_thread_id"],
    "source_email_id": target["email_id"],
    "candidate_count": len(candidates),
    "draft_id": draft_id,
    "sent_email_id": sent.get("sent_email_id"),
    "sent_email_thread_id": sent.get("sent_email_thread_id"),
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_forward_caterer_bill_to_manager_with_note",
    )


def handle_gmail_forward_roommate_bill_to_other_roommates(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    file_name = str(frame.get("file_name") or "").strip()
    if not re.fullmatch(r"[\w.\-]+\.pdf", file_name):
        frame.abstain_reason = "missing_or_invalid_roommate_bill_file_name"
        return None
    code = common_appworld_prelude(["gmail", "phone"]) + f"""
file_name = {json.dumps(file_name)}
file_name_key = file_name.strip().lower()

def text_key(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

def attachment_file_names(email):
    return [
        str(attachment.get("file_name") or "").strip()
        for attachment in email.get("attachments", []) or []
        if str(attachment.get("file_name") or "").strip()
    ]

roommate_contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship="roommate",
    page_index=page,
    page_limit=20,
))
roommate_emails = sorted({{
    str(contact.get("email") or "").strip().lower()
    for contact in roommate_contacts
    if str(contact.get("email") or "").strip()
}})
if len(roommate_emails) < 2:
    raise Exception(f"Expected at least two roommate emails, found {{roommate_emails}}.")
roommate_email_set = set(roommate_emails)

queries = [
    file_name,
    file_name.rsplit(".", 1)[0].replace("_", " "),
    "bill pdf",
    "bill",
]
threads = []
seen_thread_ids = set()
for query in queries:
    for thread in paged(lambda page, query=query: apis.gmail.show_inbox_threads(
        access_token=tokens["gmail"],
        query=query,
        attachment=True,
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    )):
        thread_id = thread.get("email_thread_id")
        if thread_id is None or thread_id in seen_thread_ids:
            continue
        seen_thread_ids.add(thread_id)
        threads.append(thread)

if not threads:
    for thread in paged(lambda page: apis.gmail.show_inbox_threads(
        access_token=tokens["gmail"],
        attachment=True,
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    )):
        thread_id = thread.get("email_thread_id")
        if thread_id is None or thread_id in seen_thread_ids:
            continue
        seen_thread_ids.add(thread_id)
        threads.append(thread)

candidates = []
for thread in threads:
    thread_id = thread.get("email_thread_id")
    if thread_id is None:
        continue
    detail = apis.gmail.show_thread(
        access_token=tokens["gmail"],
        email_thread_id=thread_id,
    )
    for email in detail.get("emails", []):
        sender = email.get("sender") or {{}}
        sender_email = str(sender.get("email") or "").strip().lower()
        if sender_email not in roommate_email_set:
            continue
        names = attachment_file_names(email)
        if file_name_key not in {{name.lower() for name in names}}:
            continue
        recipient_emails = [
            email_address for email_address in roommate_emails
            if email_address != sender_email
        ]
        if not recipient_emails:
            continue
        subject = str(email.get("subject") or "")
        body = str(email.get("body") or "")
        haystack = text_key(" ".join([subject, body, " ".join(names)]))
        file_stem = text_key(file_name.rsplit(".", 1)[0])
        score = 0
        if "bill" in haystack:
            score += 2
        if file_stem and file_stem in haystack:
            score += 3
        candidates.append({{
            "email_thread_id": thread_id,
            "email_id": email.get("email_id"),
            "created_at": email.get("created_at") or detail.get("created_at") or "",
            "sender_email": sender_email,
            "recipient_emails": recipient_emails,
            "subject": subject,
            "attachment_names": names,
            "score": score,
        }})

if not candidates:
    raise Exception(json.dumps({{
        "error": "Could not find roommate email with requested bill attachment.",
        "file_name": file_name,
        "roommate_emails": roommate_emails,
        "candidate_thread_count": len(threads),
    }}, sort_keys=True))
candidates.sort(key=lambda item: (item["score"], item["created_at"], str(item["email_thread_id"])), reverse=True)
target = candidates[0]

result = apis.gmail.forward_email_from_thread(
    access_token=tokens["gmail"],
    email_thread_id=target["email_thread_id"],
    email_id=target["email_id"],
    email_addresses=target["recipient_emails"],
    draft_not_send=False,
)
if "sent_email_id" not in result and "sent_email_thread_id" not in result:
    raise Exception(f"Unable to forward roommate bill email: {{result}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "file_name": file_name,
    "source_sender_email": target["sender_email"],
    "recipient_emails": target["recipient_emails"],
    "source_email_thread_id": target["email_thread_id"],
    "source_email_id": target["email_id"],
    "candidate_count": len(candidates),
    "forward_result": result,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_forward_roommate_bill_to_other_roommates",
    )


def handle_gmail_forward_trip_expenses_thread_with_attachment(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    sender_first_name = str(frame.get("sender_first_name") or "").strip()
    recipient_first_name = str(frame.get("recipient_first_name") or "").strip()
    attachment_path = str(frame.get("attachment_path") or "").strip()
    note_prefix = str(frame.get("note_prefix") or "").strip()
    if not sender_first_name or not recipient_first_name or not note_prefix:
        frame.abstain_reason = "missing_gmail_trip_expense_forward_slots"
        return None
    if not re.fullmatch(r"~/documents/personal/[\w.\-]+\.pdf", attachment_path):
        frame.abstain_reason = "missing_or_invalid_trip_expense_attachment_path"
        return None
    code = common_appworld_prelude(["gmail", "phone", "file_system"]) + f"""
sender_first_name = {json.dumps(sender_first_name)}
recipient_first_name = {json.dumps(recipient_first_name)}
attachment_path = {json.dumps(attachment_path)}
note_prefix = {json.dumps(note_prefix)}

def text_key(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

def path_basename(path):
    return str(path).rstrip("/").split("/")[-1]

def contact_email_by_first_name(first_name):
    first_name_key = str(first_name or "").strip().lower()
    contacts = paged(lambda page: apis.phone.search_contacts(
        access_token=tokens["phone"],
        query=first_name,
        page_index=page,
        page_limit=20,
    ))
    matches = []
    seen_emails = set()
    for contact in contacts:
        if str(contact.get("first_name") or "").strip().lower() != first_name_key:
            continue
        email = str(contact.get("email") or "").strip().lower()
        if not email or email in seen_emails:
            continue
        seen_emails.add(email)
        matches.append({{
            "contact_id": contact.get("contact_id"),
            "email": email,
            "first_name": contact.get("first_name"),
            "last_name": contact.get("last_name"),
        }})
    if len(matches) != 1:
        raise Exception(f"Expected exactly one contact email for first name {{first_name}}, found {{matches}}.")
    return matches[0]["email"]

sender_email = contact_email_by_first_name(sender_first_name)
recipient_email = contact_email_by_first_name(recipient_first_name)

file_info = apis.file_system.show_file(
    access_token=tokens["file_system"],
    file_path=attachment_path,
)
if path_basename(attachment_path).lower() != path_basename(file_info.get("path") or attachment_path).lower():
    raise Exception(f"Unexpected file metadata for {{attachment_path}}: {{file_info}}")

now = DateTime.now()
yesterday = now.subtract(days=1).to_date_string()
queries = [
    f"{{sender_first_name}} expenses pdf",
    f"{{sender_first_name}} expense pdf",
    "expenses pdf",
    "expense pdf",
    "expenses",
    sender_first_name,
]

threads = []
seen_thread_ids = set()
for query in queries:
    for thread in paged(lambda page, query=query: apis.gmail.show_inbox_threads(
        access_token=tokens["gmail"],
        query=query,
        attachment=True,
        from_email=sender_email,
        min_created_at=yesterday,
        max_created_at=yesterday,
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    )):
        thread_id = thread.get("email_thread_id")
        if thread_id is None or thread_id in seen_thread_ids:
            continue
        seen_thread_ids.add(thread_id)
        threads.append(thread)

if not threads:
    for thread in paged(lambda page: apis.gmail.show_inbox_threads(
        access_token=tokens["gmail"],
        attachment=True,
        from_email=sender_email,
        min_created_at=yesterday,
        max_created_at=yesterday,
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    )):
        thread_id = thread.get("email_thread_id")
        if thread_id is None or thread_id in seen_thread_ids:
            continue
        seen_thread_ids.add(thread_id)
        threads.append(thread)

candidates = []
for thread in threads:
    thread_id = thread.get("email_thread_id")
    if thread_id is None:
        continue
    detail = apis.gmail.show_thread(
        access_token=tokens["gmail"],
        email_thread_id=thread_id,
    )
    for email in detail.get("emails", []):
        sender = email.get("sender") or {{}}
        email_sender = str(sender.get("email") or "").strip().lower()
        if email_sender != sender_email:
            continue
        created_date = str(email.get("created_at") or detail.get("created_at") or "")[:10]
        if created_date != yesterday:
            continue
        attachments = email.get("attachments") or []
        pdf_attachments = [
            attachment for attachment in attachments
            if str(attachment.get("file_name") or "").strip().lower().endswith(".pdf")
        ]
        if not pdf_attachments:
            continue
        subject = str(email.get("subject") or "")
        body = str(email.get("body") or "")
        sender_name = str(sender.get("name") or "")
        attachment_names = " ".join(str(item.get("file_name") or "") for item in attachments)
        haystack = text_key(" ".join([subject, body, sender_name, email_sender, attachment_names]))
        if "expense" not in haystack:
            continue
        candidates.append({{
            "email_thread_id": thread_id,
            "email_id": email.get("email_id"),
            "created_at": email.get("created_at") or detail.get("created_at") or "",
            "subject": subject,
            "pdf_attachment_names": [str(item.get("file_name") or "") for item in pdf_attachments],
        }})

if not candidates:
    raise Exception(json.dumps({{
        "error": "Could not find yesterday's trip expense PDF thread.",
        "sender_first_name": sender_first_name,
        "sender_email": sender_email,
        "candidate_thread_count": len(threads),
    }}, sort_keys=True))
candidates.sort(key=lambda item: (item["created_at"], str(item["email_thread_id"])), reverse=True)
target = candidates[0]

forward = apis.gmail.forward_email_thread(
    access_token=tokens["gmail"],
    email_thread_id=target["email_thread_id"],
    email_addresses=[recipient_email],
    draft_not_send=True,
)
draft_id = forward.get("draft_id")
if draft_id is None:
    raise Exception(f"Forward did not create a draft: {{forward}}")

draft = apis.gmail.show_draft(
    access_token=tokens["gmail"],
    draft_id=draft_id,
)
old_body = str(draft.get("body") or "")
new_body = note_prefix + "\\n\\n" + old_body
apis.gmail.update_draft(
    access_token=tokens["gmail"],
    draft_id=draft_id,
    body=new_body,
)
attachment_result = apis.gmail.upload_attachments_to_draft(
    access_token=tokens["gmail"],
    draft_id=draft_id,
    attachment_file_paths=[attachment_path],
    overwrite=True,
    file_system_access_token=tokens["file_system"],
)
updated = apis.gmail.show_draft(
    access_token=tokens["gmail"],
    draft_id=draft_id,
)
updated_attachment_names = {{
    str(attachment.get("file_name") or "").strip().lower()
    for attachment in updated.get("attachments", []) or []
}}
if path_basename(attachment_path).lower() not in updated_attachment_names:
    raise Exception(f"Draft attachment missing after update: {{updated_attachment_names}}")
sent = apis.gmail.send_email_from_draft(
    access_token=tokens["gmail"],
    draft_id=draft_id,
    file_system_access_token=tokens["file_system"],
)
if "sent_email_id" not in sent:
    raise Exception(f"Unable to send trip expense thread forward: {{sent}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "sender_email": sender_email,
    "recipient_email": recipient_email,
    "attachment_path": attachment_path,
    "source_email_thread_id": target["email_thread_id"],
    "source_email_id": target["email_id"],
    "candidate_count": len(candidates),
    "draft_id": draft_id,
    "sent_email_id": sent.get("sent_email_id"),
    "sent_email_thread_id": sent.get("sent_email_thread_id"),
    "attachment_result": attachment_result,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_forward_trip_expenses_thread_with_attachment",
    )


def handle_gmail_reply_weekly_manager_tasks_by_star_state(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    subject_prefix = str(frame.get("subject_prefix") or "").strip()
    done_reply = str(frame.get("done_reply") or "").strip()
    not_done_reply = str(frame.get("not_done_reply") or "").strip()
    if not subject_prefix or not done_reply or not not_done_reply:
        frame.abstain_reason = "missing_gmail_weekly_task_reply_slots"
        return None
    code = common_appworld_prelude(["gmail", "phone"]) + f"""
subject_prefix = {json.dumps(subject_prefix)}
done_reply = {json.dumps(done_reply)}
not_done_reply = {json.dumps(not_done_reply)}

def normalize_subject(value):
    return re.sub(r"\\s+", " ", str(value or "").strip()).lower()

manager_contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship="manager",
    page_index=page,
    page_limit=20,
))
manager_emails = {{
    str(contact.get("email") or "").strip().lower()
    for contact in manager_contacts
    if str(contact.get("email") or "").strip()
}}
if len(manager_emails) != 1:
    raise Exception(f"Expected exactly one manager email, found {{sorted(manager_emails)}}.")
manager_email = next(iter(manager_emails))

now = DateTime.now()
min_created_at = now.start_of("week").to_date_string()
max_created_at = now.end_of("week").to_date_string()
prefix_key = normalize_subject(subject_prefix)

threads = paged(lambda page: apis.gmail.show_inbox_threads(
    access_token=tokens["gmail"],
    from_email=manager_email,
    min_created_at=min_created_at,
    max_created_at=max_created_at,
    page_index=page,
    page_limit=20,
    sort_by="+created_at",
))

targets = []
seen_thread_ids = set()
for thread in threads:
    thread_id = thread.get("email_thread_id")
    if thread_id is None or thread_id in seen_thread_ids:
        continue
    seen_thread_ids.add(thread_id)
    subject = str(thread.get("subject") or "")
    if not normalize_subject(subject).startswith(prefix_key):
        continue
    detail = apis.gmail.show_thread(
        access_token=tokens["gmail"],
        email_thread_id=thread_id,
    )
    source_email = None
    for email in detail.get("emails", []):
        sender_email = str((email.get("sender") or {{}}).get("email") or "").strip().lower()
        if sender_email != manager_email:
            continue
        if not normalize_subject(email.get("subject")).startswith(prefix_key):
            continue
        source_email = email
        break
    if source_email is None:
        continue
    targets.append({{
        "email_thread_id": thread_id,
        "email_id": source_email["email_id"],
        "subject": subject,
        "was_starred": bool(thread.get("starred")),
        "created_at": thread.get("created_at") or "",
    }})

if not targets:
    raise Exception(f"Could not find this week's manager task threads starting with {{subject_prefix!r}}.")

replied = []
unstarred = []
for target in targets:
    body = done_reply if target["was_starred"] else not_done_reply
    reply = apis.gmail.reply_to_email(
        access_token=tokens["gmail"],
        email_thread_id=target["email_thread_id"],
        email_id=target["email_id"],
        body=body,
        email_addresses=None,
        attachment_file_paths=[],
    )
    if "sent_email_id" not in reply:
        raise Exception(f"Unable to reply to task thread {{target['email_thread_id']}}: {{reply}}")
    replied.append({{
        "email_thread_id": target["email_thread_id"],
        "email_id": target["email_id"],
        "sent_email_id": reply.get("sent_email_id"),
        "body": body,
        "was_starred": target["was_starred"],
    }})
    if target["was_starred"]:
        apis.gmail.mark_thread_unstarred(
            access_token=tokens["gmail"],
            email_thread_id=target["email_thread_id"],
        )
        unstarred.append(target["email_thread_id"])

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "manager_email": manager_email,
    "subject_prefix": subject_prefix,
    "min_created_at": min_created_at,
    "max_created_at": max_created_at,
    "target_count": len(targets),
    "replied": replied,
    "unstarred": unstarred,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_reply_weekly_manager_tasks_by_star_state",
    )


def handle_gmail_star_threads_by_relationship(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationship = str(frame.get("relationship") or "").strip().lower()
    if not relationship:
        frame.abstain_reason = "missing_or_unsupported_gmail_star_relationship"
        return None
    code = common_appworld_prelude(["gmail", "phone"]) + f"""
relationship = {json.dumps(relationship)}
contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship=relationship,
    page_index=page,
    page_limit=20,
))
target_emails = {{
    (contact.get("email") or "").strip().lower()
    for contact in contacts
    if (contact.get("email") or "").strip()
}}
if not target_emails:
    raise Exception(f"No contacts with relationship {{relationship}} and email addresses.")

seen_thread_ids = set()
threads = []
threads.extend(paged(lambda page: apis.gmail.show_inbox_threads(
    access_token=tokens["gmail"],
    archived=False,
    page_index=page,
    page_limit=20,
)))
threads.extend(paged(lambda page: apis.gmail.show_outbox_threads(
    access_token=tokens["gmail"],
    archived=False,
    page_index=page,
    page_limit=20,
)))
threads.extend(paged(lambda page: apis.gmail.show_spam_threads(
    access_token=tokens["gmail"],
    page_index=page,
    page_limit=20,
)))

starred = []
unstarred = []
unchanged = []
for thread in threads:
    thread_id = thread["email_thread_id"]
    if thread_id in seen_thread_ids:
        continue
    seen_thread_ids.add(thread_id)
    detail = apis.gmail.show_thread(
        access_token=tokens["gmail"],
        email_thread_id=thread_id,
    )
    if detail.get("archived"):
        continue
    thread_matches_target = False
    for email in detail.get("emails", []):
        sender = email.get("sender") or {{}}
        sender_email = (sender.get("email") or "").strip().lower()
        if sender_email in target_emails:
            thread_matches_target = True
        for recipient in email.get("recipients", []) or []:
            recipient_email = (recipient.get("email") or "").strip().lower()
            if sender_email == user.email.lower() and recipient_email in target_emails:
                thread_matches_target = True
    should_star = thread_matches_target
    is_starred = bool(detail.get("starred"))
    if should_star and not is_starred:
        apis.gmail.mark_thread_starred(
            access_token=tokens["gmail"],
            email_thread_id=thread_id,
        )
        starred.append(thread_id)
    elif not should_star and is_starred:
        apis.gmail.mark_thread_unstarred(
            access_token=tokens["gmail"],
            email_thread_id=thread_id,
        )
        unstarred.append(thread_id)
    else:
        unchanged.append(thread_id)

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "relationship": relationship,
    "target_emails": sorted(target_emails),
    "starred": starred,
    "unstarred": unstarred,
    "unchanged": unchanged,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_star_threads_by_relationship",
    )


def handle_gmail_label_notification_threads_by_app(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["gmail"]) + """
threads = paged(lambda page: apis.gmail.show_inbox_threads(
    access_token=tokens["gmail"],
    archived=False,
    spam=False,
    page_index=page,
    page_limit=20,
))

def app_label_from_email(email_address):
    email_address = str(email_address or "").strip().lower()
    match = re.fullmatch(r"notifications@([a-z0-9_\\-]+)\\.com", email_address)
    if not match:
        return ""
    return match.group(1).replace("_", " ").replace("-", " ").strip()

labeled = []
skipped = []
seen_thread_ids = set()
for thread in threads:
    thread_id = thread.get("email_thread_id")
    if thread_id in seen_thread_ids:
        continue
    seen_thread_ids.add(thread_id)
    detail = apis.gmail.show_thread(
        access_token=tokens["gmail"],
        email_thread_id=thread_id,
    )
    if detail.get("archived") or detail.get("spam"):
        skipped.append(thread_id)
        continue
    labels = []
    for email in detail.get("emails", []):
        sender = email.get("sender") or {}
        label = app_label_from_email(sender.get("email"))
        if label and label not in labels:
            labels.append(label)
    if len(labels) != 1:
        skipped.append(thread_id)
        continue
    label = labels[0]
    current_label = str(detail.get("label") or "").strip()
    if current_label != label:
        apis.gmail.label_thread(
            access_token=tokens["gmail"],
            email_thread_id=thread_id,
            label=label,
        )
    labeled.append({"email_thread_id": thread_id, "label": label})

apis.supervisor.complete_task(answer=None)
print(json.dumps({"labeled": labeled, "skipped": skipped}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_label_notification_threads_by_app",
    )


def handle_gmail_relabel_priority_threads(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    source_label_1 = str(frame.get("source_label_1") or "").strip()
    source_label_2 = str(frame.get("source_label_2") or "").strip()
    target_label_1 = str(frame.get("target_label_1") or "").strip()
    target_label_2 = str(frame.get("target_label_2") or "").strip()
    remove_label = str(frame.get("remove_label") or "").strip()
    valid_labels = {"priority-1", "priority-2", "priority-3", "P1", "P2", "P3", "pr-1", "pr-2", "pr-3"}
    if (
        source_label_1 not in valid_labels
        or source_label_2 not in valid_labels
        or target_label_1 not in valid_labels
        or target_label_2 not in valid_labels
        or remove_label not in valid_labels
    ):
        frame.abstain_reason = "missing_or_unsupported_gmail_priority_relabel_slots"
        return None
    code = common_appworld_prelude(["gmail"]) + f"""
source_label_1 = {json.dumps(source_label_1)}
source_label_2 = {json.dumps(source_label_2)}
target_label_1 = {json.dumps(target_label_1)}
target_label_2 = {json.dumps(target_label_2)}
remove_label = {json.dumps(remove_label)}

label_actions = {{
    source_label_1: target_label_1,
    source_label_2: target_label_2,
}}
target_labels = set(label_actions.values())
candidate_labels = sorted(set(label_actions) | {{remove_label}})

candidate_threads = {{}}
fetchers = [
    apis.gmail.show_inbox_threads,
    apis.gmail.show_outbox_threads,
    apis.gmail.show_archived_threads,
    apis.gmail.show_spam_threads,
    apis.gmail.show_snoozed_threads,
    apis.gmail.show_starred_threads,
]
for label in candidate_labels:
    for fetch in fetchers:
        for thread in paged(lambda page, fetch=fetch, label=label: fetch(
            access_token=tokens["gmail"],
            label=label,
            page_index=page,
            page_limit=20,
        )):
            thread_id = thread.get("email_thread_id")
            if thread_id is not None:
                candidate_threads[thread_id] = thread

relabelled = []
removed = []
unchanged = []
for thread_id in sorted(candidate_threads):
    detail = apis.gmail.show_thread(
        access_token=tokens["gmail"],
        email_thread_id=thread_id,
    )
    label = str(detail.get("label") or "").strip()
    if label in label_actions:
        new_label = label_actions[label]
        if new_label != label:
            apis.gmail.label_thread(
                access_token=tokens["gmail"],
                email_thread_id=thread_id,
                label=new_label,
            )
            relabelled.append({{
                "email_thread_id": thread_id,
                "old_label": label,
                "new_label": new_label,
            }})
        else:
            unchanged.append(thread_id)
    elif label == remove_label:
        apis.gmail.unlabel_thread(
            access_token=tokens["gmail"],
            email_thread_id=thread_id,
        )
        removed.append(thread_id)
    else:
        unchanged.append(thread_id)

remaining_removed = []
remaining_source = []
for label in candidate_labels:
    if label in target_labels:
        continue
    for fetch in fetchers:
        for thread in paged(lambda page, fetch=fetch, label=label: fetch(
            access_token=tokens["gmail"],
            label=label,
            page_index=page,
            page_limit=20,
        )):
            thread_id = thread.get("email_thread_id")
            if label == remove_label:
                remaining_removed.append(thread_id)
            elif label in label_actions:
                remaining_source.append(thread_id)
if remaining_removed or remaining_source:
    raise Exception(json.dumps({{
        "remaining_removed_label": remaining_removed,
        "remaining_source_labels": remaining_source,
    }}, sort_keys=True))

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "source_label_1": source_label_1,
    "source_label_2": source_label_2,
    "target_label_1": target_label_1,
    "target_label_2": target_label_2,
    "remove_label": remove_label,
    "relabelled": relabelled,
    "removed": removed,
    "unchanged": unchanged,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_relabel_priority_threads",
    )


def handle_gmail_attach_job_search_files_and_send(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    try:
        days_back = int(frame.get("days_back"))
    except (TypeError, ValueError):
        frame.abstain_reason = "missing_gmail_job_search_days_back"
        return None
    file_name = str(frame.get("file_name") or "").strip()
    if days_back < 1 or not re.fullmatch(r"[\w.\-]+\.pdf", file_name, flags=re.IGNORECASE):
        frame.abstain_reason = "missing_or_unsupported_gmail_job_search_file"
        return None
    code = common_appworld_prelude(["gmail", "file_system"]) + f"""
days_back = {days_back}
file_name = {json.dumps(file_name)}
now = DateTime.now()
window_start = now.subtract(days=days_back).start_of("day")
window_end = now.end_of("day")
min_created_at = window_start.to_date_string()
max_created_at = window_end.to_date_string()

candidate_paths = apis.file_system.show_directory(
    access_token=tokens["file_system"],
    directory_path="/",
    substring=file_name,
    entry_type="files",
    recursive=True,
)
matching_paths = [path for path in candidate_paths if path.rstrip("/").split("/")[-1].lower() == file_name.lower()]
if not matching_paths:
    raise Exception(f"No {{file_name}} was found in the file system.")
file_candidates = []
for path in matching_paths:
    file_info = apis.file_system.show_file(access_token=tokens["file_system"], file_path=path)
    in_trash = "/trash/" in path.lower() or path.lower().endswith("/trash/" + file_name.lower())
    file_candidates.append((in_trash, str(file_info.get("updated_at") or ""), path))
file_candidates.sort(key=lambda item: (item[0], item[1]), reverse=False)
non_trash_candidates = [item for item in file_candidates if not item[0]]
if non_trash_candidates:
    file_path = sorted(non_trash_candidates, key=lambda item: item[1], reverse=True)[0][2]
else:
    file_path = sorted(file_candidates, key=lambda item: item[1], reverse=True)[0][2]

drafts = paged(lambda page: apis.gmail.show_drafts(
    access_token=tokens["gmail"],
    query="",
    page_index=page,
    page_limit=20,
    min_created_at=min_created_at,
    max_created_at=max_created_at,
    sort_by="+created_at",
))

target_drafts = []
for draft in drafts:
    created_at = DateTime.fromisoformat(draft["created_at"])
    if created_at < window_start or created_at > window_end:
        continue
    if not draft.get("recipients"):
        continue
    text = (str(draft.get("subject") or "") + "\\n" + str(draft.get("body") or "")).lower()
    if "job" not in text and "application" not in text and "position" not in text:
        continue
    target_drafts.append(draft)

if not target_drafts:
    raise Exception("No recent job-search drafts with recipients were found.")

processed = []
for draft in target_drafts:
    draft_id = draft["draft_id"]
    apis.gmail.upload_attachments_to_draft(
        access_token=tokens["gmail"],
        draft_id=draft_id,
        attachment_file_paths=[file_path],
        overwrite=True,
        file_system_access_token=tokens["file_system"],
    )
    sent = apis.gmail.send_email_from_draft(
        access_token=tokens["gmail"],
        draft_id=draft_id,
        file_system_access_token=tokens["file_system"],
    )
    processed.append({{
        "draft_id": draft_id,
        "file_path": file_path,
        "sent_email_thread_id": sent.get("sent_email_thread_id"),
        "sent_email_id": sent.get("sent_email_id"),
    }})

apis.supervisor.complete_task(answer=None)
print(json.dumps({{"file_name": file_name, "days_back": days_back, "processed": processed}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_attach_job_search_files_and_send",
    )


def handle_gmail_download_flight_ticket_attachment(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    destination = str(frame.get("destination") or "").strip()
    directory_path = str(frame.get("directory_path") or "").strip()
    if not destination or not directory_path:
        frame.abstain_reason = "missing_gmail_flight_ticket_download_slots"
        return None
    if not directory_path.endswith("/"):
        directory_path += "/"
    code = common_appworld_prelude(["gmail", "file_system"]) + f"""
destination = {json.dumps(destination)}
directory_path = {json.dumps(directory_path)}
destination_lower = destination.lower()

def text_has_ticket_evidence(text):
    lower = str(text or "").lower()
    return destination_lower in lower and "flight" in lower and "ticket" in lower

apis.file_system.create_directory(
    access_token=tokens["file_system"],
    directory_path=directory_path,
    recursive=True,
    allow_if_exists=True,
)

queries = [
    f"{{destination}} flight ticket",
    f"{{destination}} ticket",
    "flight ticket",
]
candidates = []
for query in queries:
    threads = paged(lambda page, query=query: apis.gmail.show_inbox_threads(
        access_token=tokens["gmail"],
        query=query,
        attachment=True,
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    ))
    for thread in threads:
        thread_id = thread.get("email_thread_id")
        if thread_id is None:
            continue
        detail = apis.gmail.show_thread(
            access_token=tokens["gmail"],
            email_thread_id=thread_id,
        )
        for email in detail.get("emails", []):
            subject = str(email.get("subject") or "")
            body = str(email.get("body") or "")
            attachments = email.get("attachments", [])
            for attachment in attachments:
                file_name = str(attachment.get("file_name") or "")
                if "ticket" not in file_name.lower():
                    continue
                haystack = "\\n".join([subject, body, file_name])
                if not text_has_ticket_evidence(haystack):
                    continue
                candidates.append({{
                    "created_at": str(email.get("created_at") or thread.get("created_at") or ""),
                    "email_thread_id": thread_id,
                    "attachment_id": attachment["id"],
                    "file_name": file_name,
                }})
    if candidates:
        break

if not candidates:
    raise Exception(f"No Gmail flight ticket attachment found for {{destination}}.")
candidates.sort(key=lambda item: (item["created_at"], item["email_thread_id"], item["attachment_id"]), reverse=True)
selected = candidates[0]
target_path = directory_path + selected["file_name"]
download_result = apis.gmail.download_attachment(
    access_token=tokens["gmail"],
    attachment_id=selected["attachment_id"],
    download_to_file_path=target_path,
    overwrite=True,
    file_system_access_token=tokens["file_system"],
)
file_path = download_result.get("file_path") or target_path
if not apis.file_system.file_exists(
    access_token=tokens["file_system"],
    file_path=file_path,
):
    raise Exception(f"Downloaded ticket file does not exist: {{file_path}}")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "destination": destination,
    "directory_path": directory_path,
    "selected": selected,
    "file_path": file_path,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_download_flight_ticket_attachment",
    )


def handle_gmail_email_named_file_to_relationship(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    file_description = str(frame.get("file_description") or "").strip().lower()
    relationship = str(frame.get("relationship") or "").strip().lower()
    if not file_description or not relationship:
        frame.abstain_reason = "missing_gmail_file_email_slots"
        return None
    if relationship not in {
        "partner",
        "manager",
        "husband",
        "wife",
        "parent",
        "mother",
        "father",
        "sibling",
        "brother",
        "sister",
    }:
        frame.abstain_reason = "unsupported_gmail_file_email_relationship"
        return None
    code = common_appworld_prelude(["gmail", "phone", "file_system"]) + f"""
file_description = {json.dumps(file_description)}
relationship = {json.dumps(relationship)}

def text_key(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

def path_basename(path):
    return str(path).rstrip("/").split("/")[-1]

description_key = text_key(file_description)
search_terms = {{
    "driving license": ["driving_license", "drivers_license", "driver_license", "license", "driving"],
    "headshot": ["headshot", "head_shot", "profile_photo", "profile_picture"],
    "birth certificate": ["birth_certificate", "certificate", "birth"],
}}.get(description_key, [description_key.replace(" ", "_"), description_key])

contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship=relationship,
    page_index=page,
    page_limit=20,
))
recipient_emails = sorted({{
    str(contact.get("email") or "").strip().lower()
    for contact in contacts
    if str(contact.get("email") or "").strip()
}})
if len(recipient_emails) != 1:
    raise Exception(f"Expected exactly one {{relationship}} contact email, found {{recipient_emails}}.")
recipient_email = recipient_emails[0]

candidate_paths = []
seen_paths = set()
for term in search_terms:
    for path in apis.file_system.show_directory(
        access_token=tokens["file_system"],
        directory_path="/",
        substring=term,
        entry_type="files",
        recursive=True,
    ):
        if path in seen_paths:
            continue
        seen_paths.add(path)
        candidate_paths.append(path)

allowed_extensions = {{
    "driving license": [".pdf", ".jpg", ".jpeg", ".png"],
    "headshot": [".jpg", ".jpeg", ".png"],
    "birth certificate": [".pdf", ".jpg", ".jpeg", ".png"],
}}.get(description_key, [".pdf", ".jpg", ".jpeg", ".png"])

ranked = []
for path in candidate_paths:
    lower_path = path.lower()
    base = path_basename(path).lower()
    if any(part in lower_path for part in ["/trash/", "/recycle_bin/"]):
        continue
    if not any(base.endswith(extension) for extension in allowed_extensions):
        continue
    base_key = text_key(base.rsplit(".", 1)[0])
    if description_key not in text_key(lower_path) and not any(text_key(term) in base_key for term in search_terms):
        continue
    file_info = apis.file_system.show_file(
        access_token=tokens["file_system"],
        file_path=path,
    )
    ranked.append({{
        "path": path,
        "base": base,
        "updated_at": str(file_info.get("updated_at") or ""),
        "exact": base_key == description_key or base_key == description_key.replace(" ", "_"),
    }})

if not ranked:
    raise Exception(f"No file found for {{file_description}} using search terms {{search_terms}}.")
ranked.sort(key=lambda item: (item["exact"], item["updated_at"], item["path"]), reverse=True)
file_path = ranked[0]["path"]

subject = file_description.title()
sent = apis.gmail.send_email(
    access_token=tokens["gmail"],
    email_addresses=[recipient_email],
    subject=subject,
    body="",
    attachment_file_paths=[file_path],
    file_system_access_token=tokens["file_system"],
)
if "sent_email_id" not in sent:
    raise Exception(f"Unable to send file email: {{sent}}")

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "file_description": file_description,
    "relationship": relationship,
    "recipient_email": recipient_email,
    "file_name": path_basename(file_path),
    "candidate_count": len(ranked),
    "sent_email_thread_id": sent.get("sent_email_thread_id"),
    "sent_email_id": sent.get("sent_email_id"),
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_gmail_email_named_file_to_relationship",
    )


def handle_remove_expired_payment_cards(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["amazon", "spotify", "venmo"]) + """
target_apps = ["amazon", "spotify", "venmo"]
now_month = DateTime.now().start_of("month")
deleted = {}
kept = {}
missing_accounts = []
for app_name in target_apps:
    app_api = getattr(apis, app_name)
    token = tokens[app_name]
    try:
        cards = app_api.show_payment_cards(access_token=token)
    except Exception as exc:
        missing_accounts.append({"app": app_name, "message": str(exc)})
        continue
    deleted[app_name] = []
    kept[app_name] = []
    for card in cards:
        expiry_month = DateTime(
            int(card["expiry_year"]),
            int(card["expiry_month"]),
            1,
        ).start_of("month")
        if expiry_month <= now_month:
            app_api.delete_payment_card(
                access_token=token,
                payment_card_id=card["payment_card_id"],
            )
            deleted[app_name].append(card["payment_card_id"])
        else:
            kept[app_name].append(card["payment_card_id"])

apis.supervisor.complete_task(answer=None)
print(json.dumps({
    "deleted": deleted,
    "kept": kept,
    "missing_accounts": missing_accounts,
}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_remove_expired_payment_cards",
    )


def handle_bucket_list_status_update(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    item = frame.get("item")
    done = frame.get("done")
    if not item or done is None:
        frame.abstain_reason = "missing_bucket_list_slots"
        return None
    code = common_appworld_prelude(["simple_note"]) + f"""
item = {json.dumps(item)}
done = {repr(done)}
notes = paged(lambda page: apis.simple_note.search_notes(
    access_token=tokens["simple_note"],
    query="Bucket List",
    page_index=page,
    page_limit=20,
))
bucket_notes = [note for note in notes if "bucket list" in note.get("title", "").lower()]
if not bucket_notes:
    raise Exception("No Bucket List note found.")
note = apis.simple_note.show_note(
    access_token=tokens["simple_note"],
    note_id=bucket_notes[0]["note_id"],
)
lines = note["content"].splitlines()
new_lines = []
updated = False
for line in lines:
    stripped_item = re.sub(r"^\\[[ xX]\\]\\s*", "", line).strip()
    if stripped_item == item:
        new_lines.append(("[x] " if done else "[ ] ") + stripped_item)
        updated = True
    else:
        new_lines.append(line)
if not updated:
    raise Exception(f"Bucket List item not found: {{item}}")
new_content = "\\n".join(new_lines)
apis.simple_note.update_note(
    access_token=tokens["simple_note"],
    note_id=note["note_id"],
    content=new_content,
)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"bucket_item": item, "done": done}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_bucket_list_status_update",
    )


def handle_simple_note_count_bucket_list_status(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    status = str(frame.get("status") or "").strip().lower()
    if status not in {"done", "todo"}:
        frame.abstain_reason = "missing_bucket_list_count_status"
        return None
    code = common_appworld_prelude(["simple_note"]) + f"""
target_status = {json.dumps(status)}
notes = paged(lambda page: apis.simple_note.search_notes(
    access_token=tokens["simple_note"],
    query="Bucket List",
    page_index=page,
    page_limit=20,
    dont_reorder_pinned=True,
))
bucket_notes = [
    note for note in notes
    if "bucket list" in str(note.get("title") or "").lower()
]
if len(bucket_notes) != 1:
    raise Exception(f"Expected exactly one Bucket List note, found {{len(bucket_notes)}}.")
note = apis.simple_note.show_note(
    access_token=tokens["simple_note"],
    note_id=bucket_notes[0]["note_id"],
)
done_count = 0
todo_count = 0
items = []
for line in str(note.get("content") or "").splitlines():
    match = re.match(r"^\\s*\\[(?P<mark>[ xX])\\]\\s*(?P<item>.+?)\\s*$", line)
    if not match:
        continue
    item = match.group("item").strip()
    if not item:
        continue
    if match.group("mark").lower() == "x":
        done_count += 1
        state = "done"
    else:
        todo_count += 1
        state = "todo"
    items.append({{"item": item, "state": state}})
if not items:
    raise Exception("No bucket list checkbox items found.")
answer = str(done_count if target_status == "done" else todo_count)
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{"answer": answer, "done_count": done_count, "todo_count": todo_count, "items": items}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_simple_note_count_bucket_list_status",
    )


def handle_simple_note_fill_liked_song_release_months(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["simple_note", "spotify"]) + """
def normalize_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

def song_identity(song):
    artists = song.get("artists") or []
    return (
        normalize_key(song.get("title")),
        tuple(sorted(normalize_key(artist.get("name")) for artist in artists)),
    )

def wanted_identity(item):
    return (
        normalize_key(item["title"]),
        tuple(sorted(normalize_key(artist) for artist in item["artists"])),
    )

def parse_release_line(line):
    match = re.fullmatch(
        r"(?P<prefix>\\s*-\\s*)(?P<title>.+?)\\s+BY\\s+(?P<artists>.+?)\\s+RELEASED_AT\\s+(?P<released>TODO|\\d{2}/\\d{4})\\s*",
        str(line or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    artists = [part.strip() for part in re.split(r"\\s*,\\s*", match.group("artists")) if part.strip()]
    if not artists:
        return None
    return {
        "prefix": match.group("prefix"),
        "title": match.group("title").strip(),
        "artists": artists,
        "released": match.group("released").strip(),
    }

def exact_song_search(item):
    candidates = paged(lambda page: apis.spotify.search_songs(
        query=item["title"],
        page_index=page,
        page_limit=20,
    ))
    target = wanted_identity(item)
    exact = []
    seen = set()
    for song in candidates:
        song_id = int(song.get("song_id") or song.get("id"))
        if song_id in seen:
            continue
        if song_identity(song) == target:
            exact.append(song)
            seen.add(song_id)
    if len(exact) != 1:
        raise Exception(f"Expected exactly one Spotify match for {item}, found {len(exact)}.")
    return exact[0]

def release_month(song):
    release_date = str(song.get("release_date") or "")
    match = re.match(r"(?P<year>\\d{4})-(?P<month>\\d{2})-", release_date)
    if not match:
        raise Exception(f"Unexpected release_date for song {song.get('song_id')}: {release_date}")
    return f"{match.group('month')}/{match.group('year')}"

notes = paged(lambda page: apis.simple_note.search_notes(
    access_token=tokens["simple_note"],
    query="RELEASED_AT",
    page_index=page,
    page_limit=20,
    dont_reorder_pinned=True,
))
candidate_notes = []
for note_summary in notes:
    note = apis.simple_note.show_note(
        access_token=tokens["simple_note"],
        note_id=note_summary["note_id"],
    )
    lines = str(note.get("content") or "").splitlines()
    parsed = [parse_release_line(line) for line in lines]
    parsed = [item for item in parsed if item]
    todo_count = sum(1 for item in parsed if item["released"].upper() == "TODO")
    if parsed and todo_count and any(item["released"].upper() != "TODO" for item in parsed):
        title_key = normalize_key(note.get("title"))
        if "song" in title_key and ("liked" in title_key or "like" in title_key):
            candidate_notes.append({"note": note, "lines": lines, "parsed": parsed})
if len(candidate_notes) != 1:
    raise Exception(f"Expected exactly one liked-song release-month note, found {len(candidate_notes)}.")

target = candidate_notes[0]
new_lines = []
updates = []
for line in target["lines"]:
    item = parse_release_line(line)
    if not item or item["released"].upper() != "TODO":
        new_lines.append(line)
        continue
    song = exact_song_search(item)
    month = release_month(song)
    new_line = f"{item['prefix']}{item['title']} BY {', '.join(item['artists'])} RELEASED_AT {month}"
    new_lines.append(new_line)
    updates.append({
        "title": item["title"],
        "artists": item["artists"],
        "song_id": int(song.get("song_id") or song.get("id")),
        "release_month": month,
    })
if not updates:
    raise Exception("No TODO release-month rows found.")

new_content = "\\n".join(new_lines)
apis.simple_note.update_note(
    access_token=tokens["simple_note"],
    note_id=target["note"]["note_id"],
    content=new_content,
)
apis.supervisor.complete_task(answer=None)
print(json.dumps({
    "note_id": target["note"]["note_id"],
    "updated_count": len(updates),
    "updates": updates,
}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_simple_note_fill_liked_song_release_months",
    )


def handle_spotify_follow_artists_by_genre_followers(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    genre = frame.get("genre")
    min_follower_count = frame.get("min_follower_count")
    if not genre or min_follower_count is None:
        frame.abstain_reason = "missing_spotify_follow_artist_slots"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
genre = {json.dumps(genre)}
min_follower_count = {json.dumps(min_follower_count)}
artists = paged(lambda page: apis.spotify.search_artists(
    genre=genre,
    min_follower_count=min_follower_count,
    page_index=page,
    page_limit=20,
))
followed = []
for artist in artists:
    apis.spotify.follow_artist(
        access_token=tokens["spotify"],
        artist_id=artist["artist_id"],
    )
    followed.append(artist["artist_id"])
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"genre": genre, "followed_artist_ids": followed, "count": len(followed)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_follow_artists_by_genre_followers",
    )


def handle_spotify_add_artist_playcount_songs_to_queue(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    artist_name = frame.get("artist_name")
    min_play_count = frame.get("min_play_count")
    if not artist_name or min_play_count is None:
        frame.abstain_reason = "missing_spotify_artist_queue_slots"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
artist_name = {json.dumps(str(artist_name))}
min_play_count = {int(min_play_count)}
artists = paged(lambda page: apis.spotify.search_artists(
    query=artist_name,
    page_index=page,
    page_limit=20,
))
matching_artists = [
    artist for artist in artists
    if artist.get("name", "").strip().lower() == artist_name.strip().lower()
]
if not matching_artists:
    raise ValueError(f"Could not find Spotify artist: {{artist_name}}")
artist_id = matching_artists[0]["artist_id"]
songs = paged(lambda page: apis.spotify.search_songs(
    query=artist_name,
    artist_id=artist_id,
    min_play_count=min_play_count,
    page_index=page,
    page_limit=20,
))
added_song_ids = []
for song in songs:
    if song["play_count"] > min_play_count:
        apis.spotify.add_to_queue(
            access_token=tokens["spotify"],
            song_id=song["song_id"],
        )
        added_song_ids.append(song["song_id"])
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"artist_name": artist_name, "min_play_count": min_play_count, "added_song_ids": added_song_ids, "count": len(added_song_ids)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_add_artist_playcount_songs_to_queue",
    )


def handle_spotify_like_songs_from_followed_artists(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["spotify"]) + """
following_artists = paged(lambda page: apis.spotify.show_following_artists(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
target_song_ids = set()
for artist in following_artists:
    artist_id = artist["artist_id"]
    artist_name = artist["name"]
    songs = paged(lambda page, artist_id=artist_id, artist_name=artist_name: apis.spotify.search_songs(
        query=artist_name,
        artist_id=artist_id,
        page_index=page,
        page_limit=20,
    ))
    target_song_ids.update(song["song_id"] for song in songs)
liked_song_ids = []
for song_id in sorted(target_song_ids):
    privates = apis.spotify.show_song_privates(
        access_token=tokens["spotify"],
        song_id=song_id,
    )
    if privates.get("liked"):
        continue
    apis.spotify.like_song(
        access_token=tokens["spotify"],
        song_id=song_id,
    )
    liked_song_ids.append(song_id)
apis.supervisor.complete_task(answer=None)
print(json.dumps({"liked_song_ids": liked_song_ids, "count": len(liked_song_ids)}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_like_songs_from_followed_artists",
    )


def handle_spotify_public_liked_library_playlist_share(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    partner_relationship = frame.get("partner_relationship")
    if partner_relationship not in {"husband", "wife"}:
        frame.abstain_reason = "missing_or_unsupported_spotify_share_partner"
        return None
    code = common_appworld_prelude(["spotify", "phone"]) + f"""
partner_relationship = {json.dumps(str(partner_relationship))}
library_song_ids = set()
song_library = paged(lambda page: apis.spotify.show_song_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
library_song_ids.update(song["song_id"] for song in song_library)
album_library = paged(lambda page: apis.spotify.show_album_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
for album in album_library:
    library_song_ids.update(album.get("song_ids") or [])
playlist_library = paged(lambda page: apis.spotify.show_playlist_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
for playlist in playlist_library:
    library_song_ids.update(playlist.get("song_ids") or [])
liked_songs = paged(lambda page: apis.spotify.show_liked_songs(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
liked_song_ids = {{song["song_id"] for song in liked_songs}}
target_song_ids = sorted(library_song_ids & liked_song_ids)
new_playlist = apis.spotify.create_playlist(
    access_token=tokens["spotify"],
    title="Liked Library Songs",
    is_public=True,
)
playlist_id = new_playlist["playlist_id"]
for song_id in target_song_ids:
    apis.spotify.add_song_to_playlist(
        access_token=tokens["spotify"],
        playlist_id=playlist_id,
        song_id=song_id,
    )
playlist = apis.spotify.show_playlist(
    access_token=tokens["spotify"],
    playlist_id=playlist_id,
)
shareable_link = playlist["shareable_link"]
contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship=partner_relationship,
    page_index=page,
    page_limit=20,
))
if not contacts:
    raise Exception(f"No phone contact found for relationship: {{partner_relationship}}")
phone_number = contacts[0]["phone_number"]
apis.phone.send_text_message(
    access_token=tokens["phone"],
    phone_number=phone_number,
    message=shareable_link,
)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"playlist_id": playlist_id, "shareable_link": shareable_link, "song_count": len(target_song_ids), "sent_to": phone_number}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_public_liked_library_playlist_share",
    )


def handle_spotify_sync_following_by_liked_song_artists(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    operation = frame.get("operation")
    if operation not in {"follow_liked_song_artists", "unfollow_non_liked_song_artists"}:
        frame.abstain_reason = "missing_or_unsupported_spotify_follow_sync_operation"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
operation = {json.dumps(operation)}
liked_songs = paged(lambda page: apis.spotify.show_liked_songs(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
liked_artist_ids = set()
for song in liked_songs:
    for artist in song.get("artists", []):
        liked_artist_ids.add(artist.get("artist_id") or artist["id"])
changed_artist_ids = []
if operation == "follow_liked_song_artists":
    for artist_id in sorted(liked_artist_ids):
        apis.spotify.follow_artist(
            access_token=tokens["spotify"],
            artist_id=artist_id,
        )
        changed_artist_ids.append(artist_id)
else:
    following_artists = paged(lambda page: apis.spotify.show_following_artists(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    ))
    for artist in following_artists:
        artist_id = artist["artist_id"]
        if artist_id not in liked_artist_ids:
            apis.spotify.unfollow_artist(
                access_token=tokens["spotify"],
                artist_id=artist_id,
            )
            changed_artist_ids.append(artist_id)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"operation": operation, "changed_artist_ids": changed_artist_ids, "count": len(changed_artist_ids)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_sync_following_by_liked_song_artists",
    )


def handle_spotify_playlist_best_song_per_collection(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    playlist_title = frame.get("playlist_title")
    song_metric = frame.get("song_metric")
    collection_type = frame.get("collection_type")
    if not playlist_title or song_metric not in {"play_count", "rating"} or collection_type not in {
        "album_library",
        "playlist_library",
    }:
        frame.abstain_reason = "missing_spotify_playlist_best_song_slots"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
playlist_title = {json.dumps(str(playlist_title))}
song_metric = {json.dumps(str(song_metric))}
collection_type = {json.dumps(str(collection_type))}
if collection_type == "album_library":
    collections = paged(lambda page: apis.spotify.show_album_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    ))
else:
    collections = paged(lambda page: apis.spotify.show_playlist_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    ))
new_playlist = apis.spotify.create_playlist(
    access_token=tokens["spotify"],
    title=playlist_title,
)
playlist_id = new_playlist["playlist_id"]
added_song_ids = []
for collection in collections:
    if collection_type == "album_library":
        collection_songs = apis.spotify.show_album(
            album_id=collection["album_id"],
        )["songs"]
    else:
        collection_songs = apis.spotify.show_playlist(
            access_token=tokens["spotify"],
            playlist_id=collection["playlist_id"],
        )["songs"]
    if not collection_songs:
        continue
    scored_song_ids = {{}}
    for song in collection_songs:
        song_id = song.get("id") or song.get("song_id")
        song_detail = apis.spotify.show_song(song_id=song_id)
        scored_song_ids[song_id] = song_detail[song_metric]
    best_song_id = max(scored_song_ids, key=scored_song_ids.get)
    apis.spotify.add_song_to_playlist(
        access_token=tokens["spotify"],
        playlist_id=playlist_id,
        song_id=best_song_id,
    )
    added_song_ids.append(best_song_id)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"playlist_id": playlist_id, "added_song_ids": added_song_ids, "count": len(added_song_ids)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_playlist_best_song_per_collection",
    )


def handle_spotify_playlist_from_recent_simple_note(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    playlist_title = str(frame.get("playlist_title") or "").strip()
    if not playlist_title:
        frame.abstain_reason = "missing_spotify_simple_note_playlist_title"
        return None
    code = common_appworld_prelude(["simple_note", "spotify"]) + f"""
playlist_title = {json.dumps(playlist_title)}

def normalize_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

def song_identity(song):
    artists = song.get("artists") or []
    return (
        normalize_key(song.get("title")),
        tuple(sorted(normalize_key(artist.get("name")) for artist in artists)),
    )

def wanted_identity(item):
    return (
        normalize_key(item["title"]),
        tuple(sorted(normalize_key(artist) for artist in item["artists"])),
    )

def parse_song_line(line):
    text = re.sub(r"^\\s*[-*\\d.)]+\\s*", "", str(line or "")).strip()
    if not text or text.startswith("#"):
        return None
    match = re.fullmatch(r"(?P<title>.+?)\\s+by\\s+(?P<artists>.+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    artists = [part.strip() for part in re.split(r"\\s*,\\s*", match.group("artists")) if part.strip()]
    if not artists:
        return None
    return {{"title": match.group("title").strip(), "artists": artists, "raw": text}}

def exact_song_search(item):
    candidates = paged(lambda page: apis.spotify.search_songs(
        query=item["title"],
        page_index=page,
        page_limit=20,
    ))
    target = wanted_identity(item)
    exact = []
    seen = set()
    for song in candidates:
        song_id = int(song.get("song_id") or song.get("id"))
        if song_id in seen:
            continue
        if song_identity(song) == target:
            exact.append(song)
            seen.add(song_id)
    if len(exact) != 1:
        raise Exception(f"Expected exactly one Spotify match for {{item}}, found {{len(exact)}}.")
    return exact[0]

notes = paged(lambda page: apis.simple_note.search_notes(
    access_token=tokens["simple_note"],
    query="songs",
    page_index=page,
    page_limit=20,
    dont_reorder_pinned=True,
))
candidate_notes = []
for note_summary in notes:
    note = apis.simple_note.show_note(
        access_token=tokens["simple_note"],
        note_id=note_summary["note_id"],
    )
    title_key = normalize_key(note.get("title"))
    body = str(note.get("content") or "")
    items = []
    for line in body.splitlines():
        parsed = parse_song_line(line)
        if parsed:
            items.append(parsed)
    if (
        "song" in title_key
        and ("spotify" in title_key or "playlist" in title_key)
        and items
    ):
        candidate_notes.append({{"note": note, "items": items}})
if len(candidate_notes) != 1:
    raise Exception(f"Expected exactly one recent Simple Note song list, found {{len(candidate_notes)}}.")

items = candidate_notes[0]["items"]
if not items:
    raise Exception("No songs found in Simple Note.")

matched_songs = []
seen_song_ids = set()
for item in items:
    song = exact_song_search(item)
    song_id = int(song.get("song_id") or song.get("id"))
    if song_id in seen_song_ids:
        continue
    seen_song_ids.add(song_id)
    matched_songs.append(song)

playlist = apis.spotify.create_playlist(
    access_token=tokens["spotify"],
    title=playlist_title,
    is_public=False,
)
playlist_id = int(playlist["playlist_id"])
added_song_ids = []
for song in matched_songs:
    song_id = int(song.get("song_id") or song.get("id"))
    apis.spotify.add_song_to_playlist(
        access_token=tokens["spotify"],
        playlist_id=playlist_id,
        song_id=song_id,
    )
    added_song_ids.append(song_id)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "playlist_title": playlist_title,
    "playlist_id": playlist_id,
    "note_id": candidate_notes[0]["note"]["note_id"],
    "parsed_count": len(items),
    "added_song_ids": added_song_ids,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_playlist_from_recent_simple_note",
    )


def handle_spotify_playlist_from_workout_email(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    playlist_title = str(frame.get("playlist_title") or "").strip()
    if not playlist_title:
        frame.abstain_reason = "missing_spotify_workout_email_playlist_title"
        return None
    code = common_appworld_prelude(["gmail", "spotify"]) + f"""
playlist_title = {json.dumps(playlist_title)}

def normalize_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

def song_identity(song):
    artists = song.get("artists") or []
    return (
        normalize_key(song.get("title")),
        tuple(sorted(normalize_key(artist.get("name")) for artist in artists)),
    )

def wanted_identity(item):
    return (
        normalize_key(item["title"]),
        tuple(sorted(normalize_key(artist) for artist in item["artists"])),
    )

def parse_song_line(line):
    text = re.sub(r"^\\s*[-*\\d.)]+\\s*", "", str(line or "")).strip()
    if not text:
        return None
    text = text.strip('"').strip("'").strip()
    for pattern in [
        r"(?P<title>.+?)\\s+by\\s+(?P<artists>.+)",
        r"(?P<title>.+?)\\s+-\\s+(?P<artists>.+)",
    ]:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE)
        if match:
            artists = [part.strip() for part in re.split(r"\\s*(?:,|&| and )\\s*", match.group("artists")) if part.strip()]
            if artists:
                return {{"title": match.group("title").strip(), "artists": artists, "raw": text}}
    return None

def extract_song_items(text):
    items = []
    for line in str(text or "").splitlines():
        parsed = parse_song_line(line)
        if parsed:
            items.append(parsed)
    if items:
        return items
    # Some emails use semicolon-separated inline lists.
    for part in re.split(r"\\s*;\\s*", str(text or "")):
        parsed = parse_song_line(part)
        if parsed:
            items.append(parsed)
    return items

def exact_song_search(item):
    candidates = paged(lambda page: apis.spotify.search_songs(
        query=item["title"],
        page_index=page,
        page_limit=20,
    ))
    target = wanted_identity(item)
    exact = []
    seen = set()
    for song in candidates:
        song_id = int(song.get("song_id") or song.get("id"))
        if song_id in seen:
            continue
        if song_identity(song) == target:
            exact.append(song)
            seen.add(song_id)
    if len(exact) != 1:
        raise Exception(f"Expected exactly one Spotify match for {{item}}, found {{len(exact)}}.")
    return exact[0]

threads = []
for query in ["workout songs", "workout partner songs", "songs workout"]:
    threads.extend(paged(lambda page, query=query: apis.gmail.show_inbox_threads(
        access_token=tokens["gmail"],
        query=query,
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    )))

unique_threads = {{}}
for thread in threads:
    thread_id = thread.get("email_thread_id")
    if thread_id is not None:
        unique_threads[int(thread_id)] = thread
if not unique_threads:
    unique_threads = {{
        int(thread["email_thread_id"]): thread
        for thread in paged(lambda page: apis.gmail.show_inbox_threads(
            access_token=tokens["gmail"],
            page_index=page,
            page_limit=20,
            sort_by="-created_at",
        ))
        if thread.get("email_thread_id") is not None
    }}

candidate_emails = []
for thread_id in sorted(unique_threads):
    detail = apis.gmail.show_thread(
        access_token=tokens["gmail"],
        email_thread_id=thread_id,
    )
    for email in detail.get("emails", []):
        subject = str(email.get("subject") or "")
        body = str(email.get("body") or "")
        combined = subject + "\\n" + body
        lower = combined.lower()
        if "workout" not in lower or "song" not in lower:
            continue
        items = extract_song_items(body)
        if items:
            candidate_emails.append((str(email.get("created_at") or ""), thread_id, email, items))

if len(candidate_emails) != 1:
    raise Exception(f"Expected one workout song email, found {{len(candidate_emails)}}.")
_, thread_id, email, items = candidate_emails[0]
matched_songs = []
seen_song_ids = set()
for item in items:
    song = exact_song_search(item)
    song_id = int(song.get("song_id") or song.get("id"))
    if song_id in seen_song_ids:
        continue
    seen_song_ids.add(song_id)
    matched_songs.append(song)
if not matched_songs:
    raise Exception("No songs matched from workout email.")

playlist = apis.spotify.create_playlist(
    access_token=tokens["spotify"],
    title=playlist_title,
    is_public=False,
)
playlist_id = int(playlist["playlist_id"])
added_song_ids = []
for song in matched_songs:
    song_id = int(song.get("song_id") or song.get("id"))
    apis.spotify.add_song_to_playlist(
        access_token=tokens["spotify"],
        playlist_id=playlist_id,
        song_id=song_id,
    )
    added_song_ids.append(song_id)

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "playlist_title": playlist_title,
    "playlist_id": playlist_id,
    "email_thread_id": thread_id,
    "parsed_count": len(items),
    "added_song_ids": added_song_ids,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_playlist_from_workout_email",
    )


def handle_spotify_reply_liked_song_recommendations_email(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationship = str(frame.get("relationship") or "").strip().lower()
    message_prefix = str(frame.get("message_prefix") or "").strip()
    if not relationship or not message_prefix:
        frame.abstain_reason = "missing_spotify_email_recommendation_slots"
        return None
    code = common_appworld_prelude(["gmail", "spotify", "phone"]) + f"""
relationship = {json.dumps(relationship)}
message_prefix = {json.dumps(message_prefix)}

contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship=relationship,
    page_index=page,
    page_limit=20,
))
target_emails = {{
    (contact.get("email") or "").strip().lower()
    for contact in contacts
    if (contact.get("email") or "").strip()
}}
if not target_emails:
    raise Exception(f"No contact emails found for relationship {{relationship}}.")

threads = []
for query in ["song recommendations", "recommendations", "favorite songs"]:
    threads.extend(paged(lambda page, query=query: apis.gmail.show_inbox_threads(
        access_token=tokens["gmail"],
        query=query,
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    )))
if not threads:
    threads = paged(lambda page: apis.gmail.show_inbox_threads(
        access_token=tokens["gmail"],
        page_index=page,
        page_limit=20,
        sort_by="-created_at",
    ))

unique_thread_ids = []
seen_thread_ids = set()
for thread in threads:
    thread_id = thread.get("email_thread_id")
    if thread_id is None or thread_id in seen_thread_ids:
        continue
    unique_thread_ids.append(thread_id)
    seen_thread_ids.add(thread_id)

candidate_emails = []
for thread_id in unique_thread_ids:
    detail = apis.gmail.show_thread(
        access_token=tokens["gmail"],
        email_thread_id=thread_id,
    )
    if detail.get("archived") or detail.get("spam"):
        continue
    for email in detail.get("emails", []):
        sender = email.get("sender") or {{}}
        sender_email = (sender.get("email") or "").strip().lower()
        if sender_email not in target_emails:
            continue
        subject = str(email.get("subject") or "")
        body = str(email.get("body") or "")
        lower = (subject + "\\n" + body).lower()
        if "song" not in lower or "recommend" not in lower:
            continue
        candidate_emails.append((
            str(email.get("created_at") or ""),
            int(thread_id),
            int(email.get("email_id")),
            sender_email,
            subject,
        ))

if len(candidate_emails) != 1:
    raise Exception(f"Expected one target song-recommendation email, found {{len(candidate_emails)}}.")
_, thread_id, email_id, sender_email, subject = candidate_emails[0]

liked_songs = paged(lambda page: apis.spotify.show_liked_songs(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
song_library = paged(lambda page: apis.spotify.show_song_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
library_song_ids = {{
    int(song.get("song_id") or song.get("id"))
    for song in song_library
    if song.get("song_id") is not None or song.get("id") is not None
}}

titles = []
seen_song_ids = set()
for song in liked_songs:
    song_id = int(song.get("song_id") or song.get("id"))
    if song_id not in library_song_ids or song_id in seen_song_ids:
        continue
    seen_song_ids.add(song_id)
    title = str(song.get("title") or "").strip()
    if title:
        titles.append(title)

if not titles:
    raise Exception("No liked songs found in Spotify song library.")
body = message_prefix + " " + ", ".join(titles)
reply = apis.gmail.reply_to_email(
    access_token=tokens["gmail"],
    email_thread_id=thread_id,
    email_id=email_id,
    body=body,
    email_addresses=None,
    attachment_file_paths=[],
)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "relationship": relationship,
    "target_email": sender_email,
    "email_thread_id": thread_id,
    "email_id": email_id,
    "sent_email_id": reply.get("sent_email_id"),
    "song_count": len(titles),
    "titles": titles,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_reply_liked_song_recommendations_email",
    )


def handle_spotify_update_song_recommendation_draft_from_library(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    person_first_name = str(frame.get("person_first_name") or "").strip()
    if not person_first_name:
        frame.abstain_reason = "missing_spotify_draft_recipient_name"
        return None
    code = common_appworld_prelude(["gmail", "spotify"]) + f"""
person_first_name = {json.dumps(person_first_name)}

def normalize_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

def artist_names(song):
    return [str(artist.get("name") or "").strip() for artist in song.get("artists", []) if str(artist.get("name") or "").strip()]

def song_line(song):
    names = artist_names(song)
    if not names:
        raise Exception(f"Song {{song.get('song_id')}} has no artist names.")
    return f"- {{str(song.get('title') or '').strip()}} by {{', '.join(names)}}"

def library_song_ids_from_playlists(playlists):
    song_ids = set()
    for playlist in playlists:
        for song_id in playlist.get("song_ids") or []:
            song_ids.add(int(song_id))
    return song_ids

drafts = paged(lambda page: apis.gmail.show_drafts(
    access_token=tokens["gmail"],
    query="song recommendations",
    page_index=page,
    page_limit=20,
    sort_by="-updated_at",
))
if not drafts:
    drafts = paged(lambda page: apis.gmail.show_drafts(
        access_token=tokens["gmail"],
        page_index=page,
        page_limit=20,
        sort_by="-updated_at",
    ))

target_first_key = normalize_key(person_first_name)
candidate_drafts = []
for draft in drafts:
    subject_body = (str(draft.get("subject") or "") + "\\n" + str(draft.get("body") or "")).lower()
    if "song" not in subject_body or ("recommend" not in subject_body and "favorite" not in subject_body):
        continue
    recipients = draft.get("recipients") or []
    recipient_matches = False
    for recipient in recipients:
        name_key = normalize_key(recipient.get("name"))
        email_key = normalize_key(recipient.get("email"))
        if name_key.startswith(target_first_key) or email_key.startswith(target_first_key):
            recipient_matches = True
    if recipient_matches:
        candidate_drafts.append(draft)

if len(candidate_drafts) != 1:
    raise Exception(f"Expected one song-recommendation draft for {{person_first_name}}, found {{len(candidate_drafts)}}.")
draft = candidate_drafts[0]

liked_songs = paged(lambda page: apis.spotify.show_liked_songs(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
song_library = paged(lambda page: apis.spotify.show_song_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
album_library = paged(lambda page: apis.spotify.show_album_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
playlist_library = paged(lambda page: apis.spotify.show_playlist_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
library_song_ids = set()
library_song_ids.update(int(song.get("song_id") or song.get("id")) for song in song_library if song.get("song_id") is not None or song.get("id") is not None)
for album in album_library:
    for song_id in album.get("song_ids") or []:
        library_song_ids.add(int(song_id))
library_song_ids.update(library_song_ids_from_playlists(playlist_library))

target_songs = []
seen_song_ids = set()
for song in liked_songs:
    song_id = int(song.get("song_id") or song.get("id"))
    if song_id not in library_song_ids or song_id in seen_song_ids:
        continue
    if not str(song.get("title") or "").strip():
        continue
    seen_song_ids.add(song_id)
    target_songs.append(song)
if not target_songs:
    raise Exception("No liked songs found across Spotify song, album, or playlist libraries.")

old_lines = str(draft.get("body") or "").splitlines()
new_song_lines = [song_line(song) for song in target_songs]
new_lines = []
inserted = False
replaced_count = 0
for line in old_lines:
    if re.match(r"^\\s*[-*]\\s+.+\\s+by\\s+.+", line, flags=re.IGNORECASE):
        if not inserted:
            new_lines.extend(new_song_lines)
            inserted = True
        replaced_count += 1
        continue
    new_lines.append(line)
if not inserted:
    raise Exception("Could not find song-entry lines in the draft body.")
new_body = "\\n".join(new_lines)

apis.gmail.update_draft(
    access_token=tokens["gmail"],
    draft_id=draft["draft_id"],
    body=new_body,
)
sent = apis.gmail.send_email_from_draft(
    access_token=tokens["gmail"],
    draft_id=draft["draft_id"],
)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "person_first_name": person_first_name,
    "draft_id": draft["draft_id"],
    "replaced_count": replaced_count,
    "song_count": len(new_song_lines),
    "sent_email_id": sent.get("sent_email_id"),
    "sent_email_thread_id": sent.get("sent_email_thread_id"),
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_update_song_recommendation_draft_from_library",
    )


def handle_spotify_append_most_common_playlist_genre(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["spotify"]) + """
from collections import Counter

playlists = paged(lambda page: apis.spotify.show_playlist_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
updates = []
for playlist in playlists:
    playlist_id = playlist["playlist_id"]
    original_title = playlist["title"]
    detailed = apis.spotify.show_playlist(
        access_token=tokens["spotify"],
        playlist_id=playlist_id,
    )
    genres = []
    for playlist_song in detailed.get("songs", []):
        song_id = playlist_song.get("id") or playlist_song.get("song_id")
        if song_id is None:
            continue
        song = apis.spotify.show_song(song_id=song_id)
        genre = str(song.get("genre") or "").strip()
        if genre:
            genres.append(genre)
    if not genres:
        continue
    counts = Counter(genres)
    most_common_genre = sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))[0][0]
    new_title = f"{original_title} | {most_common_genre}"
    apis.spotify.update_playlist(
        access_token=tokens["spotify"],
        playlist_id=playlist_id,
        title=new_title,
    )
    updates.append({"playlist_id": playlist_id, "old_title": original_title, "new_title": new_title, "genre": most_common_genre})
apis.supervisor.complete_task(answer=None)
print(json.dumps({"updated_count": len(updates), "updates": updates}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_append_most_common_playlist_genre",
    )


def handle_spotify_like_all_library_items(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["spotify"]) + """
songs = paged(lambda page: apis.spotify.show_song_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
liked_song_ids = []
for song in songs:
    song_id = song["song_id"]
    privates = apis.spotify.show_song_privates(
        access_token=tokens["spotify"],
        song_id=song_id,
    )
    if not privates.get("liked"):
        apis.spotify.like_song(
            access_token=tokens["spotify"],
            song_id=song_id,
        )
        liked_song_ids.append(song_id)
albums = paged(lambda page: apis.spotify.show_album_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
liked_album_ids = []
for album in albums:
    album_id = album["album_id"]
    privates = apis.spotify.show_album_privates(
        access_token=tokens["spotify"],
        album_id=album_id,
    )
    if not privates.get("liked"):
        apis.spotify.like_album(
            access_token=tokens["spotify"],
            album_id=album_id,
        )
        liked_album_ids.append(album_id)
apis.supervisor.complete_task(answer=None)
print(json.dumps({"liked_song_ids": liked_song_ids, "liked_album_ids": liked_album_ids, "song_count": len(liked_song_ids), "album_count": len(liked_album_ids)}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_like_all_library_items",
    )


def handle_spotify_download_liked_library_songs(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    collection_type = frame.get("collection_type")
    if collection_type not in {"playlist_library", "song_library", "album_library"}:
        frame.abstain_reason = "missing_spotify_download_liked_library_collection_type"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
collection_type = {json.dumps(str(collection_type))}
library_song_ids = set()
if collection_type == "playlist_library":
    playlists = paged(lambda page: apis.spotify.show_playlist_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    ))
    for playlist in playlists:
        library_song_ids.update(playlist.get("song_ids") or [])
elif collection_type == "song_library":
    songs = paged(lambda page: apis.spotify.show_song_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    ))
    library_song_ids.update(song["song_id"] for song in songs)
else:
    albums = paged(lambda page: apis.spotify.show_album_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    ))
    for album in albums:
        library_song_ids.update(album.get("song_ids") or [])
liked_songs = paged(lambda page: apis.spotify.show_liked_songs(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
liked_song_ids = {{song["song_id"] for song in liked_songs}}
downloaded_song_ids = []
for song_id in sorted(library_song_ids & liked_song_ids):
    privates = apis.spotify.show_song_privates(
        access_token=tokens["spotify"],
        song_id=song_id,
    )
    if privates.get("downloaded"):
        continue
    apis.spotify.download_song(
        access_token=tokens["spotify"],
        song_id=song_id,
    )
    downloaded_song_ids.append(song_id)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"collection_type": collection_type, "downloaded_song_ids": downloaded_song_ids, "count": len(downloaded_song_ids)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_download_liked_library_songs",
    )


def handle_spotify_rate_library_songs_by_liked_status(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    collection_type = frame.get("collection_type")
    liked_filter = frame.get("liked_filter")
    target_rating = frame.get("target_rating")
    if collection_type not in {"playlist_library", "song_library", "album_library"}:
        frame.abstain_reason = "missing_spotify_rating_collection_type"
        return None
    if liked_filter not in {"liked", "not_liked"} or target_rating not in {1, 2, 3, 4, 5}:
        frame.abstain_reason = "missing_spotify_rating_filter_or_target"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
collection_type = {json.dumps(str(collection_type))}
liked_filter = {json.dumps(str(liked_filter))}
target_rating = {int(target_rating)}
library_song_ids = set()
if collection_type == "playlist_library":
    playlists = paged(lambda page: apis.spotify.show_playlist_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    ))
    for playlist in playlists:
        library_song_ids.update(playlist.get("song_ids") or [])
elif collection_type == "song_library":
    songs = paged(lambda page: apis.spotify.show_song_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    ))
    library_song_ids.update(song["song_id"] for song in songs)
else:
    albums = paged(lambda page: apis.spotify.show_album_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    ))
    for album in albums:
        library_song_ids.update(album.get("song_ids") or [])
liked_songs = paged(lambda page: apis.spotify.show_liked_songs(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
liked_song_ids = {{song["song_id"] for song in liked_songs}}
if liked_filter == "liked":
    target_song_ids = library_song_ids & liked_song_ids
else:
    target_song_ids = library_song_ids - liked_song_ids
added_review_song_ids = []
updated_review_song_ids = []
for song_id in sorted(target_song_ids):
    reviews = paged(lambda page, song_id=song_id: apis.spotify.show_song_reviews(
        song_id=song_id,
        user_email=profile["email"],
        page_index=page,
        page_limit=20,
    ))
    if reviews:
        apis.spotify.update_song_review(
            access_token=tokens["spotify"],
            review_id=reviews[0]["song_review_id"],
            rating=target_rating,
        )
        updated_review_song_ids.append(song_id)
    else:
        apis.spotify.review_song(
            access_token=tokens["spotify"],
            song_id=song_id,
            rating=target_rating,
        )
        added_review_song_ids.append(song_id)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"collection_type": collection_type, "liked_filter": liked_filter, "target_rating": target_rating, "added_review_song_ids": added_review_song_ids, "updated_review_song_ids": updated_review_song_ids}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_rate_library_songs_by_liked_status",
    )


def handle_spotify_follow_artists_from_liked_songs_and_albums(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["spotify"]) + """
target_artist_ids = set()
liked_songs = paged(lambda page: apis.spotify.show_liked_songs(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
for song in liked_songs:
    for artist in song.get("artists", []):
        target_artist_ids.add(artist.get("artist_id") or artist["id"])
liked_albums = paged(lambda page: apis.spotify.show_liked_albums(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
for album in liked_albums:
    for artist in album.get("artists", []):
        target_artist_ids.add(artist.get("artist_id") or artist["id"])
followed_artist_ids = []
for artist_id in sorted(target_artist_ids):
    apis.spotify.follow_artist(
        access_token=tokens["spotify"],
        artist_id=artist_id,
    )
    followed_artist_ids.append(artist_id)
apis.supervisor.complete_task(answer=None)
print(json.dumps({"followed_artist_ids": followed_artist_ids, "count": len(followed_artist_ids)}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_follow_artists_from_liked_songs_and_albums",
    )


def handle_spotify_follow_playlist_song_artists_by_genre(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    genre = frame.get("genre")
    if not genre:
        frame.abstain_reason = "missing_spotify_playlist_song_artist_genre"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
genre = {json.dumps(str(genre).lower())}
playlist_song_ids = set()
playlists = paged(lambda page: apis.spotify.show_playlist_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
for playlist in playlists:
    playlist_song_ids.update(playlist.get("song_ids") or [])
target_artist_ids = set()
for song_id in sorted(playlist_song_ids):
    song = apis.spotify.show_song(song_id=song_id)
    if str(song.get("genre", "")).strip().lower() != genre:
        continue
    for artist in song.get("artists", []):
        target_artist_ids.add(artist.get("artist_id") or artist["id"])
followed_artist_ids = []
for artist_id in sorted(target_artist_ids):
    apis.spotify.follow_artist(
        access_token=tokens["spotify"],
        artist_id=artist_id,
    )
    followed_artist_ids.append(artist_id)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"genre": genre, "followed_artist_ids": followed_artist_ids, "count": len(followed_artist_ids)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_follow_playlist_song_artists_by_genre",
    )


def handle_spotify_top_played_genre_titles(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    genre = frame.get("genre")
    limit = frame.get("limit")
    if not genre or limit is None:
        frame.abstain_reason = "missing_spotify_top_played_genre_slots"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
genre = {json.dumps(str(genre).lower())}
limit = {int(limit)}
library_song_ids = set()
song_library = paged(lambda page: apis.spotify.show_song_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
library_song_ids.update(song["song_id"] for song in song_library)
album_library = paged(lambda page: apis.spotify.show_album_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
for album in album_library:
    library_song_ids.update(album.get("song_ids") or [])
playlist_library = paged(lambda page: apis.spotify.show_playlist_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
for playlist in playlist_library:
    library_song_ids.update(playlist.get("song_ids") or [])
matching_songs = []
for song_id in sorted(library_song_ids):
    song = apis.spotify.show_song(song_id=song_id)
    if str(song.get("genre", "")).strip().lower() != genre:
        continue
    matching_songs.append(song)
matching_songs.sort(key=lambda song: (-int(song.get("play_count") or 0), str(song.get("title") or "").lower(), int(song.get("song_id") or song.get("id") or 0)))
titles = [song["title"] for song in matching_songs[:limit]]
answer = ", ".join(titles)
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{"genre": genre, "limit": limit, "answer": answer, "song_count": len(matching_songs)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_top_played_genre_titles",
    )


def handle_spotify_count_unique_library_songs(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["spotify"]) + """
song_ids = set()
song_library = paged(lambda page: apis.spotify.show_song_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
song_ids.update(song["song_id"] for song in song_library)
album_library = paged(lambda page: apis.spotify.show_album_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
for album in album_library:
    song_ids.update(album.get("song_ids") or [])
playlist_library = paged(lambda page: apis.spotify.show_playlist_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
for playlist in playlist_library:
    song_ids.update(playlist.get("song_ids") or [])
answer = str(len(song_ids))
apis.supervisor.complete_task(answer=answer)
print(json.dumps({"answer": answer, "unique_song_count": len(song_ids)}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_count_unique_library_songs",
    )


def handle_venmo_pay_grocery_from_text_and_notify(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    first_name = frame.get("person_first_name")
    note = frame.get("note")
    message = frame.get("message")
    if not first_name or not note or not message:
        frame.abstain_reason = "missing_venmo_grocery_payment_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
first_name = {json.dumps(str(first_name))}
note = {json.dumps(str(note))}
message = {json.dumps(str(message))}
contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    query=first_name,
    page_index=page,
    page_limit=20,
))
first_name_lower = first_name.lower()
matching_contacts = [
    contact
    for contact in contacts
    if (contact.get("first_name") or "").lower() == first_name_lower
]
if len(matching_contacts) != 1:
    raise Exception(f"Expected exactly one phone contact named {{first_name}}, found {{len(matching_contacts)}}.")
contact = matching_contacts[0]
phone_number = contact["phone_number"]
email = (contact.get("email") or "").lower()
messages = paged(lambda page: apis.phone.search_text_messages(
    access_token=tokens["phone"],
    phone_number=phone_number,
    page_index=page,
    page_limit=20,
))
messages = sorted(messages, key=lambda item: item.get("sent_at", ""), reverse=True)
amount = None
candidate_messages = []
for text_message in messages:
    text = str(text_message.get("message") or "")
    lower_text = text.lower()
    if not any(keyword in lower_text for keyword in ["grocery", "groceries", "it was", "owe you", "owed"]):
        continue
    for amount_match in re.finditer(r"\\$(\\d+(?:\\.\\d+)?)", text):
        candidate_messages.append({{"sent_at": text_message.get("sent_at"), "message": text, "amount": float(amount_match.group(1))}})
for candidate in candidate_messages:
    if "it was" in candidate["message"].lower() or "grocery" in candidate["message"].lower() or "groceries" in candidate["message"].lower():
        amount = candidate["amount"]
        break
if amount is None and candidate_messages:
    amount = candidate_messages[0]["amount"]
if amount is None:
    raise Exception(f"Could not infer grocery amount from text conversation with {{first_name}}.")
venmo_users = apis.venmo.search_users(
    access_token=tokens["venmo"],
    query=email,
    page_limit=20,
)
matching_users = [user for user in venmo_users if (user.get("email") or "").lower() == email]
if not matching_users:
    raise Exception(f"No Venmo account found for {{email}}.")
receiver_email = matching_users[0]["email"]
transaction_args = {{
    "access_token": tokens["venmo"],
    "receiver_email": receiver_email,
    "amount": amount,
    "private": False,
    "description": note,
}}
account = apis.venmo.show_account(access_token=tokens["venmo"])
failed_api_attempts = 0
if float(account.get("venmo_balance") or 0) >= amount:
    result = apis.venmo.create_transaction(**transaction_args)
else:
    result = {{"message": "No non-expired payment card available."}}
    cards = [
        card
        for card in apis.venmo.show_payment_cards(access_token=tokens["venmo"])
        if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
    ]
    cards = sorted(cards, key=lambda card: card["payment_card_id"], reverse=True)
    for card in cards:
        transaction_args["payment_card_id"] = card["payment_card_id"]
        result = apis.venmo.create_transaction(**transaction_args)
        if "transaction_id" in result:
            break
        failed_api_attempts += 1
if "transaction_id" not in result:
    raise Exception(f"Unable to create Venmo transaction: {{result}}")
apis.phone.send_text_message(
    access_token=tokens["phone"],
    phone_number=phone_number,
    message=message,
)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"receiver_email": receiver_email, "phone_number": phone_number, "amount": amount, "note": note, "message": message, "failed_api_attempts": failed_api_attempts}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_pay_grocery_from_text_and_notify",
    )


def handle_spotify_count_recent_release_library_songs(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    years_back = frame.get("years_back")
    include_current_year = frame.get("include_current_year")
    if years_back is None or include_current_year is None:
        frame.abstain_reason = "missing_spotify_recent_release_count_slots"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
years_back = {int(years_back)}
include_current_year = {repr(bool(include_current_year))}
current_year = DateTime.now().year
min_year = current_year - years_back
library_song_ids = set()
song_library = paged(lambda page: apis.spotify.show_song_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
library_song_ids.update(song["song_id"] for song in song_library)
album_library = paged(lambda page: apis.spotify.show_album_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
for album in album_library:
    library_song_ids.update(album.get("song_ids") or [])
matching_song_ids = []
for song_id in sorted(library_song_ids):
    song = apis.spotify.show_song(song_id=song_id)
    release_year = DateTime.fromisoformat(song["release_date"]).year
    if years_back < 0:
        if release_year >= current_year:
            continue
    else:
        if release_year < min_year:
            continue
        if not include_current_year and release_year == current_year:
            continue
    matching_song_ids.append(song_id)
answer = str(len(matching_song_ids))
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{"answer": answer, "matching_song_ids": matching_song_ids, "current_year": current_year, "min_year": min_year}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_count_recent_release_library_songs",
    )


def handle_spotify_navigate_until_artist(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    direction = frame.get("direction")
    artist_name = frame.get("artist_name")
    if direction not in {"previous", "next"} or not artist_name:
        frame.abstain_reason = "missing_spotify_navigation_slots"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
direction = {json.dumps(str(direction))}
target_artist_name = {json.dumps(str(artist_name))}
target_artist_lower = target_artist_name.strip().lower()
queue = apis.spotify.show_song_queue(access_token=tokens["spotify"])
if not queue:
    raise Exception("Spotify song queue is empty.")

def current_song_has_target_artist():
    current = apis.spotify.show_current_song(access_token=tokens["spotify"])
    detailed = apis.spotify.show_song(song_id=current["song_id"])
    artist_names = [
        str(artist.get("name") or "").strip().lower()
        for artist in detailed.get("artists", [])
    ]
    return current, target_artist_lower in artist_names, artist_names

visited_song_ids = []
current, matched, artist_names = current_song_has_target_artist()
visited_song_ids.append(current["song_id"])
steps = 0
while not matched and steps < len(queue):
    if direction == "previous":
        apis.spotify.previous_song(access_token=tokens["spotify"])
    else:
        apis.spotify.next_song(access_token=tokens["spotify"])
    steps += 1
    current, matched, artist_names = current_song_has_target_artist()
    visited_song_ids.append(current["song_id"])
if not matched:
    raise Exception(f"Could not reach artist {{target_artist_name}} within one full queue cycle.")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"direction": direction, "artist_name": target_artist_name, "steps": steps, "song_id": current["song_id"], "visited_song_ids": visited_song_ids}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_navigate_until_artist",
    )


def handle_venmo_reset_friends_to_phone_friends(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["phone", "venmo"]) + """
phone_contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship="friend",
    page_index=page,
    page_limit=20,
))
target_emails = {
    str(contact.get("email") or "").strip().lower()
    for contact in phone_contacts
    if str(contact.get("email") or "").strip()
}
current_friends = paged(lambda page: apis.venmo.search_friends(
    access_token=tokens["venmo"],
    page_index=page,
    page_limit=20,
))
current_emails = {
    str(friend.get("email") or "").strip().lower()
    for friend in current_friends
    if str(friend.get("email") or "").strip()
}
added = []
removed = []
for email in sorted(target_emails - current_emails):
    apis.venmo.add_friend(access_token=tokens["venmo"], user_email=email)
    added.append(email)
for email in sorted(current_emails - target_emails):
    apis.venmo.remove_friend(access_token=tokens["venmo"], user_email=email)
    removed.append(email)
apis.supervisor.complete_task(answer=None)
print(json.dumps({"target_count": len(target_emails), "initial_count": len(current_emails), "added": added, "removed": removed}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_reset_friends_to_phone_friends",
    )


def handle_spotify_filter_queue_by_liked_status(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    remove_filter = frame.get("remove_filter")
    if remove_filter not in {"liked", "not_liked"}:
        frame.abstain_reason = "missing_spotify_queue_liked_filter"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
remove_filter = {json.dumps(str(remove_filter))}
liked_songs = paged(lambda page: apis.spotify.show_liked_songs(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
liked_song_ids = {{song["song_id"] for song in liked_songs}}
queue = apis.spotify.show_song_queue(access_token=tokens["spotify"])
positions_to_remove = []
removed_song_ids = []
for entry in queue:
    song_id = entry["song_id"]
    is_liked = song_id in liked_song_ids
    should_remove = is_liked if remove_filter == "liked" else not is_liked
    if should_remove:
        positions_to_remove.append(int(entry["position"]))
        removed_song_ids.append(song_id)
for position in sorted(positions_to_remove, reverse=True):
    apis.spotify.remove_song_from_queue(
        access_token=tokens["spotify"],
        position=position,
    )
apis.spotify.play_music(access_token=tokens["spotify"])
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"remove_filter": remove_filter, "removed_positions": sorted(positions_to_remove), "removed_song_ids": removed_song_ids}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_filter_queue_by_liked_status",
    )


def handle_spotify_navigate_until_private_status(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    direction = frame.get("direction")
    status_property = frame.get("status_property")
    if direction not in {"previous", "next"} or status_property not in {"liked", "downloaded"}:
        frame.abstain_reason = "missing_spotify_private_status_navigation_slots"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
direction = {json.dumps(str(direction))}
status_property = {json.dumps(str(status_property))}
queue = apis.spotify.show_song_queue(access_token=tokens["spotify"])
if not queue:
    raise Exception("Spotify song queue is empty.")

def current_song_status():
    current = apis.spotify.show_current_song(access_token=tokens["spotify"])
    privates = apis.spotify.show_song_privates(
        access_token=tokens["spotify"],
        song_id=current["song_id"],
    )
    return current, bool(privates.get(status_property)), privates

visited_song_ids = []
current, matched, privates = current_song_status()
visited_song_ids.append(current["song_id"])
steps = 0
while not matched and steps < len(queue):
    if direction == "previous":
        apis.spotify.previous_song(access_token=tokens["spotify"])
    else:
        apis.spotify.next_song(access_token=tokens["spotify"])
    steps += 1
    current, matched, privates = current_song_status()
    visited_song_ids.append(current["song_id"])
if not matched:
    raise Exception(f"Could not reach a {{status_property}} song within one full queue cycle.")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"direction": direction, "status_property": status_property, "steps": steps, "song_id": current["song_id"], "visited_song_ids": visited_song_ids}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_navigate_until_private_status",
    )


def handle_spotify_play_offline_downloaded_collection(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    collection_type = frame.get("collection_type")
    required_minutes = frame.get("required_minutes")
    if collection_type not in {"album", "playlist"} or required_minutes is None:
        frame.abstain_reason = "missing_spotify_offline_collection_slots"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
collection_type = {json.dumps(str(collection_type))}
required_minutes = {float(required_minutes)}
downloaded = paged(lambda page: apis.spotify.show_downloaded_songs(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
downloaded_duration_by_id = {{
    int(song["song_id"]): int(song.get("duration") or apis.spotify.show_song(song_id=song["song_id"])["duration"])
    for song in downloaded
}}
if collection_type == "album":
    collections = paged(lambda page: apis.spotify.show_album_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    ))
    id_key = "album_id"
else:
    collections = paged(lambda page: apis.spotify.show_playlist_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    ))
    id_key = "playlist_id"

candidates = []
for collection in collections:
    song_ids = [int(song_id) for song_id in collection.get("song_ids", [])]
    downloaded_seconds = sum(
        downloaded_duration_by_id[song_id]
        for song_id in song_ids
        if song_id in downloaded_duration_by_id
    )
    downloaded_minutes = downloaded_seconds / 60.0
    candidates.append({{
        "collection_id": int(collection[id_key]),
        "title": collection["title"],
        "downloaded_minutes": downloaded_minutes,
        "downloaded_song_count": sum(1 for song_id in song_ids if song_id in downloaded_duration_by_id),
        "song_count": len(song_ids),
    }})
qualifying = [
    candidate
    for candidate in candidates
    if candidate["downloaded_minutes"] + 1e-9 >= required_minutes
]
if len(qualifying) != 1:
    raise Exception(
        f"Expected exactly one {{collection_type}} with enough downloaded songs; found {{len(qualifying)}}."
    )
selected = qualifying[0]
apis.spotify.clear_song_queue(access_token=tokens["spotify"])
if collection_type == "album":
    apis.spotify.play_music(access_token=tokens["spotify"], album_id=selected["collection_id"])
else:
    apis.spotify.play_music(access_token=tokens["spotify"], playlist_id=selected["collection_id"])
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"collection_type": collection_type, "required_minutes": required_minutes, "selected": selected, "qualifying_count": len(qualifying)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_play_offline_downloaded_collection",
    )


def handle_venmo_sum_month_transactions(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    direction = frame.get("direction")
    if direction not in {"sent", "received", "sent_or_received"}:
        frame.abstain_reason = "missing_venmo_sum_month_transaction_direction"
        return None
    code = common_appworld_prelude(["venmo"]) + f"""
direction = {json.dumps(str(direction))}
now = DateTime.now()
month_start = now.start_of("month").to_date_string()
month_end = now.end_of("month").to_date_string()
directions = [direction] if direction in ["sent", "received"] else ["sent", "received"]
seen_transaction_ids = set()
transactions = []
for direction_value in directions:
    batch = paged(lambda page, direction_value=direction_value: apis.venmo.show_transactions(
        access_token=tokens["venmo"],
        direction=direction_value,
        min_created_at=month_start,
        max_created_at=month_end,
        page_index=page,
        page_limit=20,
    ))
    for transaction in batch:
        transaction_id = transaction["transaction_id"]
        if transaction_id in seen_transaction_ids:
            continue
        seen_transaction_ids.add(transaction_id)
        transactions.append(transaction)
total = sum(float(transaction.get("amount") or 0) for transaction in transactions)
answer = str(int(total)) if abs(total - round(total)) < 1e-9 else str(round(total, 2))
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{"answer": answer, "direction": direction, "transaction_ids": [transaction["transaction_id"] for transaction in transactions], "total": total}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_sum_month_transactions",
    )


def handle_venmo_sum_recent_received_requests(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    days = frame.get("days")
    if days is None or int(days) <= 0:
        frame.abstain_reason = "missing_venmo_recent_request_days"
        return None
    code = common_appworld_prelude(["venmo"]) + f"""
days = {int(days)}
now = DateTime.now()
start = now.subtract(days=days - 1).start_of("day").to_date_string()
end = now.end_of("day").to_date_string()
requests = paged(lambda page: apis.venmo.show_received_payment_requests(
    access_token=tokens["venmo"],
    page_index=page,
    page_limit=20,
))
matching = []
for request in requests:
    created_at = DateTime.fromisoformat(request["created_at"])
    if start <= created_at.to_date_string() <= end:
        matching.append(request)
total = sum(float(request.get("amount") or 0) for request in matching)
answer = str(int(total)) if abs(total - round(total)) < 1e-9 else str(round(total, 2))
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{"answer": answer, "days": days, "request_ids": [request["payment_request_id"] for request in matching], "total": total}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_sum_recent_received_requests",
    )


def handle_spotify_reset_queue_with_recommendations(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["spotify"]) + """
recommendations = paged(lambda page: apis.spotify.show_recommendations(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
apis.spotify.clear_song_queue(access_token=tokens["spotify"])
added_song_ids = []
for song in recommendations:
    song_id = song["song_id"]
    apis.spotify.add_to_queue(access_token=tokens["spotify"], song_id=song_id)
    added_song_ids.append(song_id)
apis.spotify.shuffle_song_queue(access_token=tokens["spotify"])
apis.spotify.play_music(access_token=tokens["spotify"])
apis.supervisor.complete_task(answer=None)
print(json.dumps({"added_song_ids": added_song_ids, "count": len(added_song_ids)}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_reset_queue_with_recommendations",
    )


def handle_spotify_archive_playlist_songs_from_file(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    source_file_path = frame.get("source_file_path")
    playlist_title = frame.get("playlist_title")
    if not source_file_path or not playlist_title:
        frame.abstain_reason = "missing_spotify_archive_playlist_slots"
        return None
    code = common_appworld_prelude(["file_system", "spotify"]) + f"""
source_file_path = {json.dumps(str(source_file_path))}
playlist_title = {json.dumps(str(playlist_title))}
file_info = apis.file_system.show_file(
    access_token=tokens["file_system"],
    file_path=source_file_path,
)
raw_items = []
for line in str(file_info.get("content") or "").splitlines():
    item = line.strip()
    if not item or item.startswith("#"):
        continue
    item = re.sub(r"^[-*\\d.)\\s]+", "", item).strip()
    if item:
        raw_items.append(item)
target_titles = {{item.lower() for item in raw_items if not item.isdigit()}}
for item in raw_items:
    if " by " in item:
        target_titles.add(item.split(" by ", 1)[0].strip().lower())
target_ids = {{int(item) for item in raw_items if item.isdigit()}}
playlist_summaries = paged(lambda page: apis.spotify.show_playlist_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
playlist_details = [
    apis.spotify.show_playlist(
        access_token=tokens["spotify"],
        playlist_id=playlist["playlist_id"],
    )
    for playlist in playlist_summaries
]
archive_song_ids = set()
removed = []
for playlist in playlist_details:
    playlist_id = playlist["playlist_id"]
    for song in playlist.get("songs") or []:
        song_id = int(song.get("song_id") or song.get("id"))
        title = str(song.get("title") or "").strip().lower()
        if song_id not in target_ids and title not in target_titles:
            continue
        apis.spotify.remove_song_from_playlist(
            access_token=tokens["spotify"],
            playlist_id=playlist_id,
            song_id=song_id,
        )
        archive_song_ids.add(song_id)
        removed.append({{"playlist_id": playlist_id, "song_id": song_id, "title": song.get("title")}})
created = apis.spotify.create_playlist(
    access_token=tokens["spotify"],
    title=playlist_title,
    is_public=False,
)
archive_playlist_id = created["playlist_id"]
for song_id in sorted(archive_song_ids):
    apis.spotify.add_song_to_playlist(
        access_token=tokens["spotify"],
        playlist_id=archive_playlist_id,
        song_id=song_id,
    )
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"source_file_path": source_file_path, "playlist_title": playlist_title, "archive_playlist_id": archive_playlist_id, "archived_song_ids": sorted(archive_song_ids), "removed": removed, "raw_items": raw_items}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_archive_playlist_songs_from_file",
    )


def handle_simple_note_import_markdown_files(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    source_directory = frame.get("source_directory")
    if not source_directory:
        frame.abstain_reason = "missing_simple_note_import_source_directory"
        return None
    code = common_appworld_prelude(["file_system", "simple_note"]) + f"""
source_directory = {json.dumps(str(source_directory))}
file_paths = apis.file_system.show_directory(
    access_token=tokens["file_system"],
    directory_path=source_directory,
    entry_type="files",
    recursive=False,
)
created_notes = []
for file_path in sorted(file_paths):
    if not file_path.lower().endswith(".md"):
        continue
    file_info = apis.file_system.show_file(
        access_token=tokens["file_system"],
        file_path=file_path,
    )
    base_name = file_path.rstrip("/").split("/")[-1]
    title = re.sub(r"\\.md$", "", base_name, flags=re.IGNORECASE).replace("_", " ")
    result = apis.simple_note.create_note(
        access_token=tokens["simple_note"],
        title=title,
        content=file_info.get("content") or "",
    )
    created_notes.append({{"file_path": file_path, "title": title, "note_id": result.get("note_id")}})
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"source_directory": source_directory, "created_count": len(created_notes), "created_notes": created_notes}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_simple_note_import_markdown_files",
    )


def handle_simple_note_workout_duration(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    day_ref = str(frame.get("day_ref") or "").strip().lower()
    if day_ref not in {"today", "yesterday", "sunday", "sundays"}:
        frame.abstain_reason = "missing_workout_duration_day_ref"
        return None
    code = common_appworld_prelude(["simple_note"]) + f"""
day_ref = {json.dumps(day_ref)}
now = DateTime.now()
if day_ref == "today":
    target_day = now.format("dddd").lower()
elif day_ref == "yesterday":
    target_day = now.subtract(days=1).format("dddd").lower()
else:
    target_day = "sunday"
notes = paged(lambda page: apis.simple_note.search_notes(
    access_token=tokens["simple_note"],
    query="Workout Plan",
    page_index=page,
    page_limit=20,
    dont_reorder_pinned=True,
))
plan_notes = [
    note for note in notes
    if any(word in str(note.get("title") or "").lower() for word in ["workout", "exercise"])
]
if not plan_notes:
    all_notes = paged(lambda page: apis.simple_note.search_notes(
        access_token=tokens["simple_note"],
        page_index=page,
        page_limit=20,
        dont_reorder_pinned=True,
    ))
    plan_notes = [
        note for note in all_notes
        if any(word in str(note.get("title") or "").lower() for word in ["workout", "exercise"])
    ]
if len(plan_notes) != 1:
    raise Exception(f"Expected exactly one workout/exercise plan note, found {{len(plan_notes)}}.")
note = apis.simple_note.show_note(
    access_token=tokens["simple_note"],
    note_id=plan_notes[0]["note_id"],
)
current_day = None
duration = None
for raw_line in str(note.get("content") or "").splitlines():
    line = raw_line.strip()
    day_match = re.match(r"^day\\s*:\\s*([A-Za-z]+)\\s*$", line, flags=re.IGNORECASE)
    if day_match:
        current_day = day_match.group(1).lower()
        continue
    duration_match = re.match(r"^duration_mins\\s*:\\s*(\\d+(?:\\.\\d+)?)\\s*$", line, flags=re.IGNORECASE)
    if duration_match and current_day == target_day:
        duration = float(duration_match.group(1))
        break
if duration is None:
    raise Exception(f"No workout duration found for {{target_day}}.")
answer = str(int(duration)) if duration.is_integer() else str(duration)
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{"answer": answer, "target_day": target_day, "note_id": note["note_id"]}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_simple_note_workout_duration",
    )


def handle_simple_note_random_quote(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    quote_type = str(frame.get("quote_type") or "").strip().lower()
    if quote_type not in {"funny", "inspirational", "movie"}:
        frame.abstain_reason = "missing_simple_note_quote_type"
        return None
    code = common_appworld_prelude(["simple_note"]) + f"""
quote_type = {json.dumps(quote_type)}
notes = paged(lambda page: apis.simple_note.search_notes(
    access_token=tokens["simple_note"],
    query=quote_type + " quotes",
    page_index=page,
    page_limit=20,
    dont_reorder_pinned=True,
))
quote_notes = [
    note for note in notes
    if quote_type in str(note.get("title") or "").lower()
    and "quote" in str(note.get("title") or "").lower()
]
if len(quote_notes) != 1:
    raise Exception(f"Expected exactly one {{quote_type}} quote note, found {{len(quote_notes)}}.")
note = apis.simple_note.show_note(
    access_token=tokens["simple_note"],
    note_id=quote_notes[0]["note_id"],
)
quotes = []
current = None
for raw_line in str(note.get("content") or "").splitlines():
    line = raw_line.strip()
    quote_match = re.match(r"^-\\s*(.+?)\\s*$", line)
    if quote_match:
        if current:
            quotes.append(current.strip())
        current = quote_match.group(1).strip()
        continue
    if current and re.match(r"^(by|from)\\s+", line, flags=re.IGNORECASE):
        quotes.append(current.strip())
        current = None
if current:
    quotes.append(current.strip())
quotes = [quote for quote in quotes if quote]
if not quotes:
    raise Exception(f"No quotes parsed from {{note['title']}}.")
index = int(note["note_id"]) % len(quotes)
answer = quotes[index]
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{"answer": answer, "quote_type": quote_type, "quote_count": len(quotes), "index": index}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_simple_note_random_quote",
    )


def handle_simple_note_add_today_habit_log(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    habit_key = str(frame.get("habit_key") or "").strip().lower()
    value = frame.get("value")
    if not habit_key or value is None:
        frame.abstain_reason = "missing_today_habit_log_slots"
        return None
    code = common_appworld_prelude(["simple_note"]) + f"""
habit_key = {json.dumps(habit_key)}
target_value = {bool(value)}
today = DateTime.now().to_date_string()
yesterday = DateTime.now().subtract(days=1).to_date_string()
notes = paged(lambda page: apis.simple_note.search_notes(
    access_token=tokens["simple_note"],
    page_index=page,
    page_limit=20,
    dont_reorder_pinned=True,
))
existing_today = []
yesterday_notes = []
for summary in notes:
    note = apis.simple_note.show_note(
        access_token=tokens["simple_note"],
        note_id=summary["note_id"],
    )
    title = str(note.get("title") or "")
    content = str(note.get("content") or "")
    if "habit" not in (title + " " + content).lower():
        continue
    if not re.search(r"[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]", title):
        continue
    if not re.search(r"\\b[A-Za-z0-9_]+\\s*:\\s*(yes|no)\\b", content, flags=re.IGNORECASE):
        continue
    if today in title:
        existing_today.append(note)
    if yesterday in title:
        yesterday_notes.append(note)
if existing_today:
    raise Exception(f"Today habit log already exists: {{[note['note_id'] for note in existing_today]}}")
if len(yesterday_notes) != 1:
    raise Exception(f"Expected exactly one yesterday habit log, found {{len(yesterday_notes)}}.")
yesterday_note = yesterday_notes[0]
new_lines = []
updated = False
for line in str(yesterday_note.get("content") or "").splitlines():
    match = re.match(r"^(\\s*)([A-Za-z0-9_]+)(\\s*:\\s*)(yes|no)(\\s*)$", line, flags=re.IGNORECASE)
    if match and match.group(2).strip().lower() == habit_key:
        new_lines.append(match.group(1) + match.group(2) + match.group(3) + ("yes" if target_value else "no") + match.group(5))
        updated = True
    else:
        new_lines.append(line)
if not updated:
    raise Exception(f"Habit key not found in yesterday log: {{habit_key}}")
new_content = "\\n".join(new_lines).rstrip()
title = str(yesterday_note.get("title") or "").replace(yesterday, today)
if title == str(yesterday_note.get("title") or ""):
    title = f"Habit Tracking Log for {{today}}"
result = apis.simple_note.create_note(
    access_token=tokens["simple_note"],
    title=title,
    content=new_content,
    tags=yesterday_note.get("tags") or [],
    pinned=bool(yesterday_note.get("pinned")),
)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"created_note_id": result.get("note_id"), "title": title, "habit_key": habit_key, "value": "yes" if target_value else "no", "source_note_id": yesterday_note["note_id"]}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_simple_note_add_today_habit_log",
    )


def handle_simple_note_export_habit_tracker_csv(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    destination_path = str(frame.get("destination_path") or "").strip()
    sort_order = str(frame.get("sort_order") or "").strip().lower()
    if not destination_path or sort_order not in {"ascending", "descending"}:
        frame.abstain_reason = "missing_habit_tracker_csv_slots"
        return None
    code = common_appworld_prelude(["simple_note", "file_system"]) + f"""
destination_path = {json.dumps(destination_path)}
sort_order = {json.dumps(sort_order)}
notes = paged(lambda page: apis.simple_note.search_notes(
    access_token=tokens["simple_note"],
    page_index=page,
    page_limit=20,
    dont_reorder_pinned=True,
))

def csv_escape(value):
    text = str(value)
    if any(char in text for char in [",", '"', "\\n", "\\r"]):
        text = '"' + text.replace('"', '""') + '"'
    return text

records = []
habit_order = []
for summary in notes:
    note = apis.simple_note.show_note(
        access_token=tokens["simple_note"],
        note_id=summary["note_id"],
    )
    title = str(note.get("title") or "")
    match = re.search(r"([0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9])", title)
    if not match:
        continue
    content = str(note.get("content") or "")
    if "habit" not in (title + " " + content).lower():
        continue
    values = {{}}
    for line in content.splitlines():
        line_match = re.match(r"\\s*([A-Za-z0-9_]+)\\s*:\\s*(yes|no)\\s*$", line, flags=re.IGNORECASE)
        if not line_match:
            continue
        key = line_match.group(1).strip()
        if key not in habit_order:
            habit_order.append(key)
        values[key] = line_match.group(2).strip().lower()
    if values:
        records.append({{"date": match.group(1), "values": values, "note_id": note["note_id"]}})
if not records:
    raise Exception("No habit tracker records found.")
records.sort(key=lambda record: record["date"], reverse=(sort_order == "descending"))
rows = []
rows.append(",".join(csv_escape(value) for value in ["date"] + habit_order))
for record in records:
    rows.append(",".join(csv_escape(value) for value in [record["date"]] + [record["values"].get(key, "") for key in habit_order]))
content = "\\n".join(rows) + "\\n"
directory = destination_path.rsplit("/", 1)[0] + "/"
apis.file_system.create_directory(
    access_token=tokens["file_system"],
    directory_path=directory,
    recursive=True,
    allow_if_exists=True,
)
apis.file_system.create_file(
    access_token=tokens["file_system"],
    file_path=destination_path,
    content=content,
    overwrite=True,
)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"destination_path": destination_path, "sort_order": sort_order, "record_count": len(records), "habit_order": habit_order}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_simple_note_export_habit_tracker_csv",
    )


def handle_venmo_approve_roommate_requests_this_month(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["phone", "venmo"]) + """
now = DateTime.now()
month_start = now.start_of("month")
month_end = now
roommate_emails = set()
for contact in paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship="roommate",
    page_index=page,
    page_limit=20,
)):
    email = (contact.get("email") or "").strip().lower()
    if email:
        roommate_emails.add(email)
requests = paged(lambda page: apis.venmo.show_received_payment_requests(
    access_token=tokens["venmo"],
    status="pending",
    page_index=page,
    page_limit=20,
))
account = apis.venmo.show_account(access_token=tokens["venmo"])
remaining_balance = float(account.get("venmo_balance", 0) or 0)
cards = [
    card
    for card in apis.venmo.show_payment_cards(access_token=tokens["venmo"])
    if DateTime(card["expiry_year"], card["expiry_month"], 1).start_of("month") > DateTime.now()
]
cards = sorted(
    cards,
    key=lambda card: (
        float(card.get("balance") or 0),
        card["expiry_year"],
        card["expiry_month"],
        card["payment_card_id"],
    ),
    reverse=True,
)
approved_ids = []
failed_api_attempts = 0

def approve_with_card(payment_request_id, amount):
    global failed_api_attempts, cards
    existing_card_numbers = {str(card.get("card_number")) for card in cards}
    supervisor_cards = sorted(
        apis.supervisor.show_payment_cards(),
        key=lambda card: (
            float(card.get("balance") or 0),
            card["expiry_year"],
            card["expiry_month"],
            str(card["card_number"]),
        ),
        reverse=True,
    )
    for supervisor_card in supervisor_cards:
        if str(supervisor_card.get("card_number")) in existing_card_numbers:
            continue
        if DateTime(supervisor_card["expiry_year"], supervisor_card["expiry_month"], 1).start_of("month") <= DateTime.now():
            continue
        add_result = apis.venmo.add_payment_card(
            access_token=tokens["venmo"],
            card_name=supervisor_card["card_name"],
            owner_name=supervisor_card["owner_name"],
            card_number=supervisor_card["card_number"],
            expiry_year=supervisor_card["expiry_year"],
            expiry_month=supervisor_card["expiry_month"],
            cvv_number=supervisor_card["cvv_number"],
        )
        if "payment_card_id" not in add_result:
            failed_api_attempts += 1
            continue
        card = dict(supervisor_card)
        card["payment_card_id"] = add_result["payment_card_id"]
        result = apis.venmo.approve_payment_request(
            access_token=tokens["venmo"],
            payment_request_id=payment_request_id,
            payment_card_id=card["payment_card_id"],
        )
        if isinstance(result, dict) and result.get("message") == "Payment request approved.":
            cards.append(card)
            return True
        failed_api_attempts += 1
    for card in cards:
        result = apis.venmo.approve_payment_request(
            access_token=tokens["venmo"],
            payment_request_id=payment_request_id,
            payment_card_id=card["payment_card_id"],
        )
        if isinstance(result, dict) and result.get("message") == "Payment request approved.":
            cards.remove(card)
            cards.append(card)
            return True
        failed_api_attempts += 1
    return False

for request in requests:
    sender_email = ((request.get("sender") or {}).get("email") or "").strip().lower()
    if sender_email not in roommate_emails:
        continue
    created_at = DateTime.fromisoformat(request["created_at"])
    if created_at < month_start or created_at > month_end:
        continue
    payment_request_id = request["payment_request_id"]
    amount = float(request["amount"])
    if remaining_balance >= amount:
        apis.venmo.approve_payment_request(
            access_token=tokens["venmo"],
            payment_request_id=payment_request_id,
        )
        remaining_balance -= amount
        approved_ids.append(payment_request_id)
        continue
    approved = approve_with_card(payment_request_id, amount)
    if approved:
        approved_ids.append(payment_request_id)
    if not approved:
        raise Exception(f"Unable to approve payment request {payment_request_id}.")
apis.supervisor.complete_task(answer=None)
print(json.dumps({"approved_ids": approved_ids, "roommate_emails": sorted(roommate_emails), "failed_api_attempts": failed_api_attempts}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_approve_roommate_requests_this_month",
    )


def handle_file_delete_downloads_by_extension(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    extension = frame.get("extension")
    if not extension:
        frame.abstain_reason = "missing_file_delete_extension"
        return None
    code = common_appworld_prelude(["file_system"]) + f"""
extension = {json.dumps(str(extension).lower())}
file_paths = apis.file_system.show_directory(
    access_token=tokens["file_system"],
    directory_path="~/downloads/",
    entry_type="files",
    recursive=False,
)
deleted = []
for file_path in sorted(file_paths):
    if file_path.lower().endswith(extension):
        apis.file_system.delete_file(
            access_token=tokens["file_system"],
            file_path=file_path,
        )
        deleted.append(file_path)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"extension": extension, "deleted": deleted, "deleted_count": len(deleted)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_file_delete_downloads_by_extension",
    )


def handle_spotify_followed_artist_follower_extreme(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    extreme = frame.get("extreme")
    if extreme not in {"most", "least"}:
        frame.abstain_reason = "missing_spotify_followed_artist_extreme"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
extreme = {json.dumps(str(extreme))}
artists = paged(lambda page: apis.spotify.show_following_artists(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
))
if not artists:
    raise Exception("No followed Spotify artists.")
if extreme == "most":
    chosen = sorted(artists, key=lambda artist: (-int(artist.get("follower_count") or 0), str(artist.get("name") or "").lower(), int(artist.get("artist_id") or artist.get("id") or 0)))[0]
else:
    chosen = sorted(artists, key=lambda artist: (int(artist.get("follower_count") or 0), str(artist.get("name") or "").lower(), int(artist.get("artist_id") or artist.get("id") or 0)))[0]
answer = str(chosen["name"])
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{"answer": answer, "extreme": extreme, "artist_id": chosen.get("artist_id") or chosen.get("id"), "follower_count": chosen.get("follower_count")}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_followed_artist_follower_extreme",
    )


def handle_spotify_liked_genre_extreme(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    collection_type = frame.get("collection_type")
    extreme = frame.get("extreme")
    if collection_type not in {"song_library", "album_library", "playlist_library"} or extreme not in {"most", "least"}:
        frame.abstain_reason = "missing_spotify_liked_genre_extreme_slots"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
collection_type = {json.dumps(str(collection_type))}
extreme = {json.dumps(str(extreme))}
song_ids = set()
if collection_type == "song_library":
    for song in paged(lambda page: apis.spotify.show_song_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    )):
        song_ids.add(song["song_id"])
elif collection_type == "album_library":
    for album in paged(lambda page: apis.spotify.show_album_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    )):
        song_ids.update(album.get("song_ids") or [])
else:
    for playlist in paged(lambda page: apis.spotify.show_playlist_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    )):
        song_ids.update(playlist.get("song_ids") or [])
genre_counts = {{}}
liked_song_ids = []
for song_id in sorted(song_ids):
    privates = apis.spotify.show_song_privates(
        access_token=tokens["spotify"],
        song_id=song_id,
    )
    if not privates.get("liked"):
        continue
    song = apis.spotify.show_song(song_id=song_id)
    genre = str(song.get("genre") or "").strip()
    if not genre:
        continue
    genre_counts[genre] = genre_counts.get(genre, 0) + 1
    liked_song_ids.append(song_id)
if not genre_counts:
    raise Exception("No liked songs with genres found in collection.")
if extreme == "most":
    chosen_genre, count = sorted(genre_counts.items(), key=lambda item: (-item[1], item[0].lower()))[0]
else:
    chosen_genre, count = sorted(genre_counts.items(), key=lambda item: (item[1], item[0].lower()))[0]
answer = chosen_genre
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{"answer": answer, "extreme": extreme, "collection_type": collection_type, "count": count, "genre_counts": genre_counts, "liked_song_count": len(liked_song_ids)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_liked_genre_extreme",
    )


def handle_spotify_playlist_artist_song_count_extreme(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    extreme = frame.get("extreme")
    limit = frame.get("limit")
    if extreme not in {"most", "least"} or limit is None:
        frame.abstain_reason = "missing_spotify_playlist_artist_count_slots"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
extreme = {json.dumps(str(extreme))}
limit = {int(limit)}
song_ids = set()
for playlist in paged(lambda page: apis.spotify.show_playlist_library(
    access_token=tokens["spotify"],
    page_index=page,
    page_limit=20,
)):
    song_ids.update(playlist.get("song_ids") or [])
artist_counts = {{}}
for song_id in sorted(song_ids):
    song = apis.spotify.show_song(song_id=song_id)
    for artist in song.get("artists") or []:
        name = str(artist.get("name") or "").strip()
        if not name:
            continue
        artist_counts[name] = artist_counts.get(name, 0) + 1
if extreme == "most":
    ranked = sorted(artist_counts.items(), key=lambda item: (-item[1], item[0].lower()))
else:
    ranked = sorted(artist_counts.items(), key=lambda item: (item[1], item[0].lower()))
names = [name for name, count in ranked[:limit]]
answer = ", ".join(names)
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{"answer": answer, "extreme": extreme, "limit": limit, "artist_counts": artist_counts}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_playlist_artist_song_count_extreme",
    )


def handle_venmo_sum_year_bill_payments(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    bill_type = frame.get("bill_type")
    if bill_type not in {"phone", "electricity", "internet"}:
        frame.abstain_reason = "missing_venmo_bill_type"
        return None
    code = common_appworld_prelude(["venmo"]) + f"""
bill_type = {json.dumps(str(bill_type))}
now = DateTime.now()
year_start = now.start_of("year").to_date_string()
year_end = now.to_date_string()
transactions = paged(lambda page: apis.venmo.show_transactions(
    access_token=tokens["venmo"],
    direction="sent",
    min_created_at=year_start,
    max_created_at=year_end,
    page_index=page,
    page_limit=20,
))
matching = []
for transaction in transactions:
    description = str(transaction.get("description") or "").lower()
    if bill_type in description and "bill" in description:
        matching.append(transaction)
total = sum(float(transaction.get("amount") or 0) for transaction in matching)
answer = str(int(total)) if abs(total - round(total)) < 1e-9 else str(round(total, 2))
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{"answer": answer, "bill_type": bill_type, "transaction_ids": [transaction["transaction_id"] for transaction in matching], "total": total}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_sum_year_bill_payments",
    )


def handle_venmo_friend_transaction_counterparties(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    direction = frame.get("direction")
    sync_mode = frame.get("sync_mode")
    if direction not in {"sent", "received", "sent_or_received"} or sync_mode not in {"add_only", "sync"}:
        frame.abstain_reason = "missing_venmo_counterparty_friend_slots"
        return None
    code = common_appworld_prelude(["venmo"]) + f"""
direction = {json.dumps(str(direction))}
sync_mode = {json.dumps(str(sync_mode))}
now = DateTime.now()
month_start = now.start_of("month").to_date_string()
month_end = now.to_date_string()
directions = [direction] if direction in ["sent", "received"] else ["sent", "received"]
profile_email = (profile.get("email") or "").lower()
target_emails = set()
seen_transaction_ids = set()
for direction_value in directions:
    transactions = paged(lambda page, direction_value=direction_value: apis.venmo.show_transactions(
        access_token=tokens["venmo"],
        direction=direction_value,
        min_created_at=month_start,
        max_created_at=month_end,
        page_index=page,
        page_limit=20,
    ))
    for transaction in transactions:
        transaction_id = transaction["transaction_id"]
        if transaction_id in seen_transaction_ids:
            continue
        seen_transaction_ids.add(transaction_id)
        sender_email = ((transaction.get("sender") or {{}}).get("email") or "").lower()
        receiver_email = ((transaction.get("receiver") or {{}}).get("email") or "").lower()
        for email in (sender_email, receiver_email):
            if email and email != profile_email:
                target_emails.add(email)
current_friends = paged(lambda page: apis.venmo.search_friends(
    access_token=tokens["venmo"],
    page_index=page,
    page_limit=20,
))
current_emails = {{
    str(friend.get("email") or "").strip().lower()
    for friend in current_friends
    if str(friend.get("email") or "").strip()
}}
added = []
removed = []
for email in sorted(target_emails - current_emails):
    apis.venmo.add_friend(access_token=tokens["venmo"], user_email=email)
    added.append(email)
if sync_mode == "sync":
    for email in sorted(current_emails - target_emails):
        apis.venmo.remove_friend(access_token=tokens["venmo"], user_email=email)
        removed.append(email)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"direction": direction, "sync_mode": sync_mode, "target_emails": sorted(target_emails), "added": added, "removed": removed}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_friend_transaction_counterparties",
    )


def handle_venmo_count_friends_since_month_start(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    month = frame.get("month")
    year_offset = frame.get("year_offset")
    month_to_number = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    if month not in month_to_number or year_offset is None:
        frame.abstain_reason = "missing_venmo_friend_since_month_slots"
        return None
    code = common_appworld_prelude(["venmo"]) + f"""
month = {json.dumps(str(month))}
month_number = {month_to_number[str(month)]}
year_offset = {int(year_offset)}
now = DateTime.now()
start = DateTime(now.year + year_offset, month_number, 1).start_of("day")
friends = paged(lambda page: apis.venmo.search_friends(
    access_token=tokens["venmo"],
    page_index=page,
    page_limit=20,
))
matching = []
for friend in friends:
    friends_since = friend.get("friends_since")
    if not friends_since:
        continue
    if DateTime.fromisoformat(friends_since) >= start:
        matching.append(friend)
answer = str(len(matching))
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{"answer": answer, "month": month, "year": start.year, "friend_emails": [friend.get("email") for friend in matching]}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_count_friends_since_month_start",
    )


def handle_spotify_play_released_year_from_collection(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    release_year = frame.get("release_year")
    collection_type = frame.get("collection_type")
    if release_year is None or collection_type not in {"song_library", "album_library", "playlist_library"}:
        frame.abstain_reason = "missing_spotify_play_released_year_slots"
        return None
    code = common_appworld_prelude(["spotify"]) + f"""
release_year = {int(release_year)}
collection_type = {json.dumps(str(collection_type))}
song_ids = set()
if collection_type == "song_library":
    for song in paged(lambda page: apis.spotify.show_song_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    )):
        song_ids.add(song["song_id"])
elif collection_type == "album_library":
    for album in paged(lambda page: apis.spotify.show_album_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    )):
        song_ids.update(album.get("song_ids") or [])
else:
    for playlist in paged(lambda page: apis.spotify.show_playlist_library(
        access_token=tokens["spotify"],
        page_index=page,
        page_limit=20,
    )):
        song_ids.update(playlist.get("song_ids") or [])
matching_song_ids = []
for song_id in sorted(song_ids):
    song = apis.spotify.show_song(song_id=song_id)
    if DateTime.fromisoformat(song["release_date"]).year == release_year:
        matching_song_ids.append(song_id)
if not matching_song_ids:
    raise Exception(f"No song released in {{release_year}} found in {{collection_type}}.")
song_id = sorted(matching_song_ids)[0]
apis.spotify.play_music(access_token=tokens["spotify"], song_id=song_id)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"release_year": release_year, "collection_type": collection_type, "song_id": song_id, "matching_song_ids": matching_song_ids}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_play_released_year_from_collection",
    )


def handle_venmo_like_transactions_by_relationship_period(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationships = frame.get("relationships", [])
    period = frame.get("period")
    if not relationships or period not in {"month", "year"}:
        frame.abstain_reason = "missing_venmo_like_transactions_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
relationships = {json.dumps(relationships)}
period = {json.dumps(str(period))}
now = DateTime.now()
period_start = now.start_of(period).to_date_string()
period_end = now.end_of(period).to_date_string()
target_emails = set()
for relationship in relationships:
    contacts = paged(lambda page, relationship=relationship: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship=relationship,
        page_index=page,
        page_limit=20,
    ))
    for contact in contacts:
        email = (contact.get("email") or "").lower()
        if email:
            target_emails.add(email)
liked_transaction_ids = []
skipped_already_liked = []
failed_api_attempts = 0
seen_transaction_ids = set()
for email in sorted(target_emails):
    transactions = paged(lambda page, email=email: apis.venmo.show_transactions(
        access_token=tokens["venmo"],
        user_email=email,
        min_created_at=period_start,
        max_created_at=period_end,
        page_index=page,
        page_limit=20,
    ))
    for transaction in transactions:
        transaction_id = transaction["transaction_id"]
        if transaction_id in seen_transaction_ids:
            continue
        seen_transaction_ids.add(transaction_id)
        if transaction.get("liked"):
            skipped_already_liked.append(transaction_id)
            continue
        result = apis.venmo.like_transaction(
            access_token=tokens["venmo"],
            transaction_id=transaction_id,
        )
        if isinstance(result, dict) and result.get("message"):
            liked_transaction_ids.append(transaction_id)
        else:
            failed_api_attempts += 1
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"relationships": relationships, "period": period, "liked_transaction_ids": liked_transaction_ids, "skipped_already_liked": skipped_already_liked, "failed_api_attempts": failed_api_attempts}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_like_transactions_by_relationship_period",
    )


def handle_venmo_manager_meal_total_from_social_feed(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationships = frame.get("relationships", [])
    meal = frame.get("meal")
    venue = frame.get("venue")
    share_amount = frame.get("share_amount")
    if not relationships or meal not in {"dinner", "lunch"} or not venue or share_amount is None:
        frame.abstain_reason = "missing_venmo_manager_meal_slots"
        return None
    code = common_appworld_prelude(["phone", "venmo"]) + f"""
relationships = {json.dumps(relationships)}
meal = {json.dumps(str(meal))}
venue = {json.dumps(str(venue))}
share_amount = {float(share_amount)}
now = DateTime.now()
yesterday = now.subtract(days=1)
day_start = yesterday.start_of("day").to_date_string()
day_end = yesterday.end_of("day").to_date_string()
profile_email = (profile.get("email") or "").lower()
relationship_emails = set()
for relationship in relationships:
    contacts = paged(lambda page, relationship=relationship: apis.phone.search_contacts(
        access_token=tokens["phone"],
        relationship=relationship,
        page_index=page,
        page_limit=20,
    ))
    for contact in contacts:
        email = (contact.get("email") or "").lower()
        if email:
            relationship_emails.add(email)
feed = paged(lambda page: apis.venmo.show_social_feed(
    access_token=tokens["venmo"],
    page_index=page,
    page_limit=20,
))
venue_lower = venue.lower()
meal_lower = meal.lower()
candidate_transactions = []
for transaction in feed:
    created_at = DateTime.fromisoformat(transaction["created_at"])
    if created_at < yesterday.start_of("day") or created_at > yesterday.end_of("day"):
        continue
    description = str(transaction.get("description") or "")
    description_lower = description.lower()
    if venue_lower not in description_lower and meal_lower not in description_lower:
        continue
    sender_email = ((transaction.get("sender") or {{}}).get("email") or "").lower()
    receiver_email = ((transaction.get("receiver") or {{}}).get("email") or "").lower()
    if sender_email == profile_email or receiver_email == profile_email:
        continue
    if sender_email in relationship_emails or receiver_email in relationship_emails:
        candidate_transactions.append(transaction)
manager_counts = {{}}
for transaction in candidate_transactions:
    sender_email = ((transaction.get("sender") or {{}}).get("email") or "").lower()
    receiver_email = ((transaction.get("receiver") or {{}}).get("email") or "").lower()
    for email in (sender_email, receiver_email):
        if email not in relationship_emails:
            manager_counts[email] = manager_counts.get(email, 0) + 1
manager_email = ""
if manager_counts:
    manager_email = sorted(manager_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
if manager_email:
    matching_transactions = [
        transaction
        for transaction in candidate_transactions
        if ((transaction.get("sender") or {{}}).get("email") or "").lower() == manager_email
        or ((transaction.get("receiver") or {{}}).get("email") or "").lower() == manager_email
    ]
else:
    matching_transactions = candidate_transactions
other_total = sum(float(transaction.get("amount") or 0) for transaction in matching_transactions)
answer_value = other_total + share_amount
answer = str(int(answer_value)) if abs(answer_value - round(answer_value)) < 1e-9 else str(round(answer_value, 2))
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{"answer": answer, "manager_email": manager_email, "share_amount": share_amount, "transaction_ids": [transaction["transaction_id"] for transaction in matching_transactions], "other_total": other_total, "day_start": day_start, "day_end": day_end}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_manager_meal_total_from_social_feed",
    )


def handle_venmo_sum_transaction_likes(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    direction = frame.get("direction")
    period = frame.get("period")
    if direction not in {"sent", "received", "sent_or_received"} or period not in {"month", "year"}:
        frame.abstain_reason = "missing_venmo_sum_transaction_likes_slots"
        return None
    code = common_appworld_prelude(["venmo"]) + f"""
direction = {json.dumps(str(direction))}
period = {json.dumps(str(period))}
now = DateTime.now()
period_start = now.start_of(period).to_date_string()
period_end = now.end_of(period).to_date_string()
directions = [direction] if direction in ["sent", "received"] else ["sent", "received"]
seen_transaction_ids = set()
transactions = []
for direction_value in directions:
    batch = paged(lambda page, direction_value=direction_value: apis.venmo.show_transactions(
        access_token=tokens["venmo"],
        direction=direction_value,
        min_created_at=period_start,
        max_created_at=period_end,
        page_index=page,
        page_limit=20,
    ))
    for transaction in batch:
        transaction_id = transaction["transaction_id"]
        if transaction_id in seen_transaction_ids:
            continue
        seen_transaction_ids.add(transaction_id)
        transactions.append(transaction)
like_total = sum(int(transaction.get("like_count") or 0) for transaction in transactions)
answer = str(like_total)
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{"answer": answer, "direction": direction, "period": period, "transaction_ids": [transaction["transaction_id"] for transaction in transactions], "like_total": like_total}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_venmo_sum_transaction_likes",
    )


def handle_file_prefix_and_move_old_files(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    source_directory = frame.get("source_directory")
    prefix_format = frame.get("prefix_format")
    destination_directory = frame.get("old_destination_directory")
    if not source_directory or not prefix_format or not destination_directory:
        frame.abstain_reason = "missing_file_prefix_move_slots"
        return None
    code = common_appworld_prelude(["file_system"]) + f"""
source_directory = {json.dumps(str(source_directory))}
prefix_format = {json.dumps(str(prefix_format))}
destination_directory = {json.dumps(str(destination_directory))}
current_year = DateTime.now().year
file_paths = apis.file_system.show_directory(
    access_token=tokens["file_system"],
    directory_path=source_directory,
    entry_type="files",
    recursive=False,
)
moved = []
renamed = []
for source_path in sorted(file_paths):
    file_info = apis.file_system.show_file(
        access_token=tokens["file_system"],
        file_path=source_path,
    )
    created = DateTime.fromisoformat(file_info["created_at"])
    if prefix_format == "YYYY-MM-DD_":
        prefix = created.strftime("%Y-%m-%d_")
    elif prefix_format == "YYYY_MM_DD-":
        prefix = created.strftime("%Y_%m_%d-")
    elif prefix_format == "YYYY_MM_DD_":
        prefix = created.strftime("%Y_%m_%d_")
    else:
        raise Exception(f"Unsupported prefix format: {{prefix_format}}")
    old_name = source_path.rstrip("/").split("/")[-1]
    name_without_existing_prefix = re.sub(r"^\\d{{4}}[-_]\\d{{2}}[-_]\\d{{2}}[-_]", "", old_name)
    prefixed_name = prefix + name_without_existing_prefix
    target_directory = destination_directory if created.year != current_year else source_directory
    destination_path = target_directory.rstrip("/") + "/" + prefixed_name
    if source_path != destination_path:
        apis.file_system.move_file(
            access_token=tokens["file_system"],
            source_file_path=source_path,
            destination_file_path=destination_path,
            overwrite=True,
            retain_dates=True,
        )
        renamed.append({{"source": source_path, "destination": destination_path}})
        if created.year != current_year:
            moved.append(destination_path)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"source_directory": source_directory, "destination_directory": destination_directory, "renamed_count": len(renamed), "moved_count": len(moved), "renamed": renamed}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_file_prefix_and_move_old_files",
    )


def handle_file_reorganize_dated_meeting_files(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    source_directory = frame.get("source_directory")
    if not source_directory:
        frame.abstain_reason = "missing_file_meeting_source_directory"
        return None
    code = common_appworld_prelude(["file_system"]) + f"""
source_directory = {json.dumps(str(source_directory))}
file_paths = apis.file_system.show_directory(
    access_token=tokens["file_system"],
    directory_path=source_directory,
    entry_type="files",
    recursive=False,
)
moved = []
skipped = []
for source_path in sorted(file_paths):
    base_name = source_path.rstrip("/").split("/")[-1]
    match = re.fullmatch(r"(?P<date>[^/_.][^/]*)__+(?P<file_name>.+)\\.(?P<extension>[^./]+)", base_name)
    if not match:
        skipped.append(source_path)
        continue
    date = match.group("date")
    file_name = match.group("file_name")
    extension = match.group("extension")
    destination_directory = source_directory.rstrip("/") + "/" + file_name
    destination_path = destination_directory + "/" + date + "." + extension
    apis.file_system.create_directory(
        access_token=tokens["file_system"],
        directory_path=destination_directory,
        recursive=True,
        allow_if_exists=True,
    )
    apis.file_system.move_file(
        access_token=tokens["file_system"],
        source_file_path=source_path,
        destination_file_path=destination_path,
        overwrite=True,
        retain_dates=True,
    )
    moved.append({{"source": source_path, "destination": destination_path}})
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"source_directory": source_directory, "moved_count": len(moved), "skipped_count": len(skipped), "moved": moved, "skipped": skipped}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_file_reorganize_dated_meeting_files",
    )


def handle_spotify_current_artist_followers(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["spotify"]) + """
current = apis.spotify.show_current_song(access_token=tokens["spotify"])
song = apis.spotify.show_song(song_id=current["song_id"])
artists = song.get("artists") or current.get("artists") or []
if len(artists) != 1:
    raise Exception(f"Expected exactly one artist for current song, found {len(artists)}.")
artist_id = artists[0].get("artist_id") or artists[0].get("id")
artist = apis.spotify.show_artist(artist_id=artist_id)
answer = str(int(artist["follower_count"]))
apis.supervisor.complete_task(answer=answer)
print(json.dumps({"answer": answer, "song_id": current["song_id"], "artist_id": artist_id, "artist_name": artist.get("name")}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_spotify_current_artist_followers",
    )


def handle_simple_note_export_markdown(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    destination_directory = frame.get("destination_directory")
    if not destination_directory:
        frame.abstain_reason = "missing_simple_note_export_directory"
        return None
    code = common_appworld_prelude(["simple_note", "file_system"]) + f"""
destination_directory = {json.dumps(str(destination_directory))}
notes = paged(lambda page: apis.simple_note.search_notes(
    access_token=tokens["simple_note"],
    page_index=page,
    page_limit=20,
    dont_reorder_pinned=True,
))
created_files = []
seen_paths = set()
for note_summary in notes:
    note = apis.simple_note.show_note(
        access_token=tokens["simple_note"],
        note_id=note_summary["note_id"],
    )
    title = str(note.get("title") or f"note_{{note_summary['note_id']}}").strip()
    safe_name = re.sub(r"\\s+", "_", title)
    safe_name = re.sub(r"[/\\\\]+", "_", safe_name)
    safe_name = safe_name.strip("_") or f"note_{{note_summary['note_id']}}"
    file_path = destination_directory.rstrip("/") + "/" + safe_name + ".md"
    if file_path in seen_paths:
        stem = file_path[:-3]
        index = 2
        while f"{{stem}}_{{index}}.md" in seen_paths:
            index += 1
        file_path = f"{{stem}}_{{index}}.md"
    seen_paths.add(file_path)
    apis.file_system.create_file(
        access_token=tokens["file_system"],
        file_path=file_path,
        content=note.get("content") or "",
        overwrite=True,
    )
    created_files.append(file_path)
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"destination_directory": destination_directory, "created_count": len(created_files), "created_files": created_files}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_simple_note_export_markdown",
    )


def handle_simple_note_longest_habit_streak(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    habit_key = frame.get("habit_key")
    if not habit_key:
        frame.abstain_reason = "missing_simple_note_habit_key"
        return None
    code = common_appworld_prelude(["simple_note"]) + f"""
habit_key = {json.dumps(str(habit_key))}
notes = paged(lambda page: apis.simple_note.search_notes(
    access_token=tokens["simple_note"],
    tags=["habit-tracker"],
    page_index=page,
    page_limit=20,
    dont_reorder_pinned=True,
))
records = []
for note_summary in notes:
    note = apis.simple_note.show_note(
        access_token=tokens["simple_note"],
        note_id=note_summary["note_id"],
    )
    title = str(note.get("title") or "")
    title_match = re.search(r"(\\d{{4}}-\\d{{2}}-\\d{{2}})", title)
    if not title_match:
        continue
    value = None
    for line in str(note.get("content") or "").splitlines():
        line_match = re.match(r"\\s*([A-Za-z0-9_]+)\\s*:\\s*(yes|no)\\s*$", line, flags=re.IGNORECASE)
        if not line_match:
            continue
        if line_match.group(1).strip().lower() == habit_key:
            value = line_match.group(2).strip().lower() == "yes"
            break
    if value is not None:
        records.append((DateTime.fromisoformat(title_match.group(1)), value, note_summary["note_id"]))
if not records:
    raise Exception(f"No habit-tracker entries found for {{habit_key}}.")
records.sort(key=lambda item: item[0])
best = 0
current = 0
previous_date = None
for date, value, note_id in records:
    if value:
        if previous_date is not None and date.subtract(days=1).to_date_string() == previous_date.to_date_string():
            current += 1
        else:
            current = 1
        best = max(best, current)
    else:
        current = 0
    previous_date = date
answer = str(best)
apis.supervisor.complete_task(answer=answer)
print(json.dumps({{"answer": answer, "habit_key": habit_key, "record_count": len(records)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_simple_note_longest_habit_streak",
    )


def handle_simple_note_update_monthly_venmo_expense(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    code = common_appworld_prelude(["simple_note", "venmo"]) + """
now = DateTime.now()
month_start = now.start_of("month").to_date_string()
month_end = now.end_of("month").to_date_string()
month_label = now.format("MM/YY")
transactions = paged(lambda page: apis.venmo.show_transactions(
    access_token=tokens["venmo"],
    direction="sent",
    min_created_at=month_start,
    max_created_at=month_end,
    page_index=page,
    page_limit=20,
))
total = round(sum(float(transaction.get("amount") or 0) for transaction in transactions), 2)
notes = paged(lambda page: apis.simple_note.search_notes(
    access_token=tokens["simple_note"],
    query="Venmo Expenses",
    page_index=page,
    page_limit=20,
    dont_reorder_pinned=True,
))
expense_notes = [
    note for note in notes
    if "venmo" in str(note.get("title") or "").lower()
    and "expense" in str(note.get("title") or "").lower()
]
if not expense_notes:
    raise Exception("No Venmo Expenses Simple Note found.")
note = apis.simple_note.show_note(
    access_token=tokens["simple_note"],
    note_id=expense_notes[0]["note_id"],
)
entry = f"- {month_label} => ${total:.1f}"
lines = str(note.get("content") or "").splitlines()
new_lines = []
updated = False
month_pattern = re.compile(rf"^\\s*-\\s*{re.escape(month_label)}\\s*=>\\s*\\$[0-9]+(?:\\.[0-9]+)?\\s*$")
month_line_pattern = re.compile(r"^\\s*-\\s*(\\d{2}/\\d{2})\\s*=>\\s*\\$[0-9]+(?:\\.[0-9]+)?\\s*$")
inserted = False
for line in lines:
    if month_pattern.match(line):
        new_lines.append(entry)
        updated = True
        inserted = True
    else:
        new_lines.append(line)
if not inserted:
    month_labels = []
    for line in new_lines:
        match = month_line_pattern.match(line)
        if match:
            month_labels.append(match.group(1))
    descending = False
    if len(month_labels) >= 2:
        first = DateTime.strptime(month_labels[0], "%m/%y")
        last = DateTime.strptime(month_labels[-1], "%m/%y")
        descending = first > last
    if descending and new_lines and new_lines[0].strip().startswith("#"):
        new_lines.insert(1, entry)
    else:
        new_lines.append(entry)
new_content = "\\n".join(new_lines).rstrip() + "\\n"
apis.simple_note.update_note(
    access_token=tokens["simple_note"],
    note_id=note["note_id"],
    content=new_content,
)
apis.supervisor.complete_task(answer=None)
print(json.dumps({"month_label": month_label, "total": total, "transaction_ids": [transaction["transaction_id"] for transaction in transactions], "updated_existing": updated}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_simple_note_update_monthly_venmo_expense",
    )


def handle_todoist_fill_today_from_schedule(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    target_project_name = str(frame.get("target_project_name") or "").strip()
    if not target_project_name:
        frame.abstain_reason = "missing_todoist_schedule_target_project"
        return None
    code = common_appworld_prelude(["simple_note", "todoist"]) + f"""
target_project_name = {json.dumps(target_project_name)}

def flatten_tasks(project_tasks):
    tasks = []
    tasks.extend(project_tasks.get("no_section_tasks") or [])
    for section in project_tasks.get("sections") or []:
        for task in section.get("tasks") or []:
            item = dict(task)
            item["_section_id"] = section.get("section_id")
            item["_section_name"] = section.get("name")
            tasks.append(item)
    return tasks

def duration_minutes(task):
    duration = task.get("duration")
    if duration is None:
        return 0.0
    unit = str(task.get("duration_unit") or "minutes").strip().lower()
    minutes = float(duration)
    if unit.startswith("hour"):
        minutes *= 60.0
    return minutes

def parse_work_minutes(content):
    total = 0.0
    for line in str(content or "").splitlines():
        if "work hours" not in line.lower() or "=>" not in line:
            continue
        value = line.split("=>", 1)[1].strip().lower()
        match = re.search(r"(\\d+(?:\\.\\d+)?)", value)
        if not match:
            continue
        amount = float(match.group(1))
        total += amount if "minute" in value else amount * 60.0
    return total

def weekday_abbrev():
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return names[DateTime.now().weekday()]

def weekday_names():
    short_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    full_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    index = DateTime.now().weekday()
    return short_names[index], full_names[index]

def find_project(projects, name):
    matches = [
        project for project in projects
        if str(project.get("name") or "").strip().lower() == name.strip().lower()
    ]
    if len(matches) != 1:
        raise Exception(f"Expected exactly one Todoist project named {{name}}, got {{matches}}")
    return matches[0]

def find_work_schedule_note():
    day_short, day_full = weekday_names()
    notes = paged(lambda page: apis.simple_note.search_notes(
        access_token=tokens["simple_note"],
        query="Schedule",
        page_index=page,
        page_limit=20,
        dont_reorder_pinned=True,
    ))
    full_notes = []
    for summary in notes:
        note = apis.simple_note.show_note(
            access_token=tokens["simple_note"],
            note_id=summary["note_id"],
        )
        title = str(note.get("title") or "").strip().lower()
        if "schedule" in title and (title.startswith(day_short) or title.startswith(day_full) or title.endswith(day_full)):
            full_notes.append(note)
    if len(full_notes) != 1:
        all_notes = paged(lambda page: apis.simple_note.search_notes(
            access_token=tokens["simple_note"],
            query="",
            page_index=page,
            page_limit=20,
            dont_reorder_pinned=True,
        ))
        full_notes = []
        for summary in all_notes:
            note = apis.simple_note.show_note(
                access_token=tokens["simple_note"],
                note_id=summary["note_id"],
            )
            title = str(note.get("title") or "").strip().lower()
            if "schedule" in title and (title.startswith(day_short) or title.startswith(day_full) or title.endswith(day_full)):
                full_notes.append(note)
    if len(full_notes) != 1:
        raise Exception(f"Expected one SimpleNote work schedule for {{day_full}}, got {{[n.get('title') for n in full_notes]}}")
    return full_notes[0]

def choose_maximum_count_tasks(tasks, capacity_minutes):
    remaining = float(capacity_minutes)
    chosen = []
    for task in sorted(
        tasks,
        key=lambda task: (duration_minutes(task), task.get("order_index") or 0),
    ):
        minutes = duration_minutes(task)
        if minutes <= remaining + 1e-9:
            chosen.append(task)
            remaining -= minutes
    return chosen

projects = paged(lambda page: apis.todoist.show_projects(
    access_token=tokens["todoist"],
    page_index=page,
    page_limit=20,
))
target_project = find_project(projects, target_project_name)
inbox_project = find_project(projects, "Inbox")

target_tasks = flatten_tasks(apis.todoist.show_tasks(
    access_token=tokens["todoist"],
    project_id=target_project["project_id"],
))
inbox_tasks = flatten_tasks(apis.todoist.show_tasks(
    access_token=tokens["todoist"],
    project_id=inbox_project["project_id"],
))

work_note = find_work_schedule_note()
work_minutes = parse_work_minutes(work_note.get("content"))
remaining_target = [task for task in target_tasks if not task.get("is_completed")]
used_minutes = sum(duration_minutes(task) for task in remaining_target)
capacity = max(0.0, work_minutes - used_minutes)
inbox_incomplete = sorted(
    [task for task in inbox_tasks if not task.get("is_completed")],
    key=lambda task: task.get("order_index") or 0,
)
to_move = choose_maximum_count_tasks(inbox_incomplete, capacity)

for task in to_move:
    if task.get("_section_id") is not None or task.get("num_sub_tasks"):
        raise Exception(f"Task requires unsupported exact move fields: {{task}}")
    if task.get("labels"):
        raise Exception(f"Task has labels that create_task cannot copy exactly: {{task}}")

deleted_completed = []
for task in sorted(
    [task for task in target_tasks if task.get("is_completed")],
    key=lambda task: task.get("order_index") or 0,
    reverse=True,
):
    apis.todoist.delete_task(
        access_token=tokens["todoist"],
        task_id=task["task_id"],
    )
    deleted_completed.append({{"task_id": task["task_id"], "title": task.get("title")}})

moved = []
for task in to_move:
    create_args = {{
        "access_token": tokens["todoist"],
        "project_id": target_project["project_id"],
        "title": task["title"],
        "description": task.get("description") or "",
        "due_date": task.get("due_date"),
        "duration": task.get("duration"),
        "duration_unit": task.get("duration_unit"),
        "priority": task.get("priority") or "medium",
        "order_index": -1,
    }}
    result = apis.todoist.create_task(**create_args)
    if "task_id" not in result:
        raise Exception(f"Could not create moved task for {{task}}: {{result}}")
    apis.todoist.delete_task(
        access_token=tokens["todoist"],
        task_id=task["task_id"],
    )
    moved.append({{
        "old_task_id": task["task_id"],
        "new_task_id": result["task_id"],
        "title": task.get("title"),
        "minutes": duration_minutes(task),
    }})

apis.supervisor.complete_task(answer=None)
print(json.dumps({{
    "target_project_id": target_project["project_id"],
    "target_project_name": target_project.get("name"),
    "work_note": work_note.get("title"),
    "work_minutes": work_minutes,
    "used_minutes": used_minutes,
    "capacity_minutes": capacity,
    "deleted_completed": deleted_completed,
    "moved": moved,
}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_todoist_fill_today_from_schedule",
    )


def handle_splitwise_record_trip_expenses_from_simple_note(
    frame: IntentFrame,
    available_tools: AvailableTools,
) -> ToolAction | None:
    relationship_type = frame.get("relationship_type")
    if relationship_type not in {"friends", "coworkers"}:
        frame.abstain_reason = "missing_trip_expense_relationship_type"
        return None
    code = common_appworld_prelude(["phone", "simple_note", "splitwise"]) + f"""
relationship_type = {json.dumps(str(relationship_type))}
phone_relationship = "coworker" if relationship_type == "coworkers" else "friend"

def normalize_text(value):
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def name_key(value):
    return normalize_text(value)

def title_is_trip_expense(title):
    normalized = normalize_text(title)
    return "trip" in normalized and (
        "expense" in normalized
        or "expenditure" in normalized
        or "expenditures" in normalized
    )

def parse_expense_line(line):
    match = re.match(
        r'^\\s*-\\s*(?P<payer>.+?)\\s+paid\\s+\\$(?P<amount>\\d+(?:\\.\\d+)?)\\s+for\\s+"(?P<description>[^"]+)"\\.\\s+Owed equally by\\s+(?P<debtors>.+?)\\.\\s*$',
        line,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    raw_debtors = match.group("debtors").strip()
    debtor_names = [
        item.strip()
        for item in re.split(r"\\s*,\\s*|\\s+and\\s+", raw_debtors)
        if item.strip()
    ]
    return {{
        "payer_name": match.group("payer").strip(),
        "paid_amount": round(float(match.group("amount")), 2),
        "description": match.group("description").strip(),
        "debtor_names": debtor_names,
        "line": line,
    }}

notes = paged(lambda page: apis.simple_note.search_notes(
    access_token=tokens["simple_note"],
    page_index=page,
    page_limit=20,
    dont_reorder_pinned=True,
))
relationship_contacts = paged(lambda page: apis.phone.search_contacts(
    access_token=tokens["phone"],
    relationship=phone_relationship,
    page_index=page,
    page_limit=20,
))
relationship_emails = {{
    (contact.get("email") or "").strip().lower()
    for contact in relationship_contacts
    if (contact.get("email") or "").strip()
}}
groups = paged(lambda page: apis.splitwise.show_groups(
    access_token=tokens["splitwise"],
    page_index=page,
    page_limit=20,
))
group_by_title = {{normalize_text(group.get("name")): group for group in groups}}
trip_notes = []
for short_note in notes:
    note = apis.simple_note.show_note(
        access_token=tokens["simple_note"],
        note_id=short_note["note_id"],
    )
    title = str(note.get("title") or "")
    if not title_is_trip_expense(title):
        continue
    entries = []
    for line in str(note.get("content") or "").splitlines():
        entry = parse_expense_line(line)
        if entry is not None:
            entries.append(entry)
    if entries:
        trip_notes.append({{"note": note, "entries": entries}})

created = []
skipped_existing = []
for trip_note in trip_notes:
    note = trip_note["note"]
    title_key = normalize_text(note.get("title"))
    group = group_by_title.get(title_key)
    if group is None:
        raise Exception(f"No Splitwise group uniquely matching note title: {{note.get('title')}}")
    group_member_emails = {{
        (member.get("email") or "").strip().lower()
        for member in group.get("members", [])
        if (member.get("email") or "").strip().lower() != user.email.lower()
    }}
    if not group_member_emails or not group_member_emails <= relationship_emails:
        continue
    members_by_name = {{}}
    for member in group.get("members", []):
        key = name_key(member.get("name"))
        members_by_name.setdefault(key, []).append(member)
        first_name = key.split()[0] if key.split() else ""
        if first_name:
            members_by_name.setdefault(first_name, []).append(member)

    def member_email_for(display_name):
        key = name_key(display_name)
        matches = members_by_name.get(key, [])
        unique = []
        seen = set()
        for member in matches:
            email = (member.get("email") or "").strip().lower()
            if email and email not in seen:
                unique.append(member)
                seen.add(email)
        if len(unique) != 1:
            raise Exception(f"Could not uniquely resolve member {{display_name!r}} in group {{group.get('name')}}")
        return unique[0]["email"]

    existing = paged(lambda page, group_id=group["group_id"]: apis.splitwise.show_group_expenses(
        access_token=tokens["splitwise"],
        group_id=group_id,
        page_index=page,
        page_limit=20,
    ))
    existing_keys = set()
    for expense in existing:
        debtor_pairs = []
        for share in expense.get("shares", []):
            debtor = share.get("debtor") or {{}}
            debtor_pairs.append((
                (debtor.get("email") or "").strip().lower(),
                round(float(share.get("debt_amount") or 0), 2),
            ))
        existing_keys.add((
            str(expense.get("description") or "").strip().lower(),
            ((expense.get("payer") or {{}}).get("email") or "").strip().lower(),
            round(float(expense.get("paid_amount") or 0), 2),
            tuple(sorted(debtor_pairs)),
        ))

    for entry in trip_note["entries"]:
        payer_email = member_email_for(entry["payer_name"])
        debtor_emails = [member_email_for(name) for name in entry["debtor_names"]]
        if not debtor_emails:
            raise Exception(f"No debtors parsed for {{entry['line']}}")
        debt_amount = round(entry["paid_amount"] / len(debtor_emails), 2)
        debt_amounts = [debt_amount for _ in debtor_emails]
        key = (
            entry["description"].strip().lower(),
            payer_email.strip().lower(),
            round(entry["paid_amount"], 2),
            tuple(sorted((email.strip().lower(), amount) for email, amount in zip(debtor_emails, debt_amounts, strict=True))),
        )
        if key in existing_keys:
            skipped_existing.append({{
                "group_id": group["group_id"],
                "description": entry["description"],
                "payer_email": payer_email,
            }})
            continue
        result = apis.splitwise.record_expense(
            access_token=tokens["splitwise"],
            group_id=group["group_id"],
            description=entry["description"],
            paid_amount=entry["paid_amount"],
            payer_email=payer_email,
            debtor_emails=debtor_emails,
            debt_amounts=debt_amounts,
        )
        created.append({{
            "expense_id": result["expense_id"],
            "group_id": group["group_id"],
            "group_name": group.get("name"),
            "description": entry["description"],
            "paid_amount": entry["paid_amount"],
            "payer_email": payer_email,
            "debtor_emails": debtor_emails,
            "debt_amounts": debt_amounts,
        }})
        existing_keys.add(key)

if not created and not skipped_existing:
    raise Exception(f"No target {{relationship_type}} trip expense entries found in Simple Note.")
apis.supervisor.complete_task(answer=None)
print(json.dumps({{"relationship_type": relationship_type, "phone_relationship": phone_relationship, "created": created, "skipped_existing": skipped_existing, "note_count": len(trip_notes)}}, sort_keys=True))
"""
    return ToolAction(
        tool="execute_code",
        args={"code": clean_code(code)},
        reason="appworld_rave_splitwise_record_trip_expenses_from_simple_note",
    )


def common_appworld_prelude(app_names: list[str]) -> str:
    return f"""
import json
import re
from pendulum import DateTime

passwords = {{row["account_name"]: row["password"] for row in apis.supervisor.show_account_passwords()}}
profile = apis.supervisor.show_profile()

class RaveUser:
    pass

user = RaveUser()
user.email = profile["email"]
user.phone_number = profile["phone_number"]
user.account_passwords = passwords
tokens = {{}}
for app_name in {json.dumps(app_names)}:
    tokens[app_name] = getattr(apis, app_name).access_token_from(user)

def paged(fetch_page):
    records = []
    page_index = 0
    while True:
        batch = fetch_page(page_index)
        records.extend(batch)
        if len(batch) < 20:
            break
        page_index += 1
    return records
"""


def clean_code(code: str) -> str:
    return textwrap.dedent(code).strip() + "\n"


def extract_python_code(text: str) -> str:
    stripped = text.strip()
    match = re.search(r"```(?:python)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if match:
        stripped = match.group(1).strip()
    code = textwrap.dedent(stripped).strip()
    if not code:
        raise ValueError("Model returned empty code.")
    return code + "\n"


def compact_text(text: str) -> str:
    return " ".join(str(text).split())


def extract_relationships(text: str) -> list[str]:
    lower = text.lower()
    relationships: list[str] = []
    for phrase, relation in RELATION_ALIASES.items():
        if re.search(rf"\b{re.escape(phrase)}\b", lower) and relation not in relationships:
            relationships.append(relation)
    return relationships


def normalize_amazon_container(value: Any) -> str:
    container = str(value).strip().lower().replace("-", " ").replace("_", " ")
    if container in {"cart", "shopping cart", "amazon cart"}:
        return "cart"
    if container in {"wish list", "wishlist", "amazon wish list", "amazon wishlist"}:
        return "wish_list"
    return container.replace(" ", "_")


def normalize_amazon_product_type(value: Any) -> str:
    product_type = compact_text(str(value)).strip().lower().replace("-", " ")
    irregular = {
        "food processors": "food processor",
        "weightlifting benches": "weightlifting bench",
        "weightlifting benche": "weightlifting bench",
        "wrench sets": "wrench set",
    }
    if product_type in irregular:
        return irregular[product_type]
    if product_type.endswith("ies"):
        return product_type[:-3] + "y"
    if product_type.endswith("ches"):
        return product_type[:-2]
    if product_type.endswith("ses"):
        return product_type[:-2]
    if product_type.endswith("s") and not product_type.endswith("ss"):
        return product_type[:-1]
    return product_type


def normalize_llm_slots(intent_type: str, slots: dict[str, Any]) -> dict[str, Any]:
    if intent_type == "appworld_phone_message_non_venmo_contacts":
        relationships_value = slots.get("relationships", [])
        if isinstance(relationships_value, str):
            relationships = extract_relationships(relationships_value)
        else:
            relationships = []
            for item in relationships_value if isinstance(relationships_value, list) else []:
                key = str(item).lower().strip()
                relationship = RELATION_ALIASES.get(key, key)
                if relationship and relationship not in relationships:
                    relationships.append(relationship)
        return {
            "relationships": relationships,
            "excluded_app": str(slots.get("excluded_app", "")).lower().strip(),
            "message": slots.get("message"),
        }
    if intent_type == "appworld_phone_send_message_to_relationship":
        relationships_value = slots.get("relationships", [])
        if isinstance(relationships_value, str):
            relationships = extract_relationships(relationships_value)
        else:
            relationships = []
            for item in relationships_value if isinstance(relationships_value, list) else []:
                key = str(item).lower().strip()
                relationship = RELATION_ALIASES.get(key, key)
                if relationship and relationship not in relationships:
                    relationships.append(relationship)
        return {
            "relationships": relationships,
            "message_kind": str(slots.get("message_kind", "")).strip().lower(),
            "message": slots.get("message"),
        }
    if intent_type == "appworld_phone_reply_favorite_recipe_to_relationship":
        relationship = str(
            slots.get("relationship")
            or slots.get("partner_relationship")
            or ""
        ).strip().lower()
        relationship = RELATION_ALIASES.get(relationship, relationship)
        return {"relationship": relationship}
    if intent_type == "appworld_splitwise_record_venmo_receipt_payments":
        return {"note": str(slots.get("note", "")).strip()}
    if intent_type == "appworld_spotify_apply_todoist_playlist_suggestions":
        relationship_type = str(
            slots.get("relationship_type")
            or slots.get("relationship")
            or ""
        ).strip().lower()
        if relationship_type in {"roommate", "room mate", "room-mate"}:
            relationship_type = "roommates"
        if relationship_type in {"sibling"}:
            relationship_type = "siblings"
        if relationship_type in {"friend"}:
            relationship_type = "friends"
        return {
            "destination": str(slots.get("destination", "")).strip(),
            "relationship_type": relationship_type,
            "final_comment": str(slots.get("final_comment", "")).strip(),
        }
    if intent_type == "appworld_spotify_apply_phone_playlist_suggestions":
        relationship_type = str(
            slots.get("relationship_type")
            or slots.get("relationship")
            or ""
        ).strip().lower()
        if relationship_type in {"roommate", "room mate", "room-mate"}:
            relationship_type = "roommates"
        if relationship_type in {"sibling"}:
            relationship_type = "siblings"
        return {"relationship_type": relationship_type}
    if intent_type == "appworld_phone_message_app_account_verify_reset":
        relationship = str(slots.get("relationship") or "").strip().lower()
        relationship = RELATION_ALIASES.get(relationship, relationship)
        return {
            "relationship": relationship,
            "password": str(slots.get("password") or "").strip(),
            "date_window": str(slots.get("date_window") or "yesterday").strip().lower(),
        }
    if intent_type == "appworld_shared_subscription_password_reset_and_text":
        relationships_value = slots.get("relationships") or slots.get("relationship") or []
        if isinstance(relationships_value, str):
            relationships = extract_relationships(relationships_value)
        else:
            relationships = []
            for item in relationships_value if isinstance(relationships_value, list) else []:
                key = str(item).lower().strip()
                relationship = RELATION_ALIASES.get(key, key)
                if relationship and relationship not in relationships:
                    relationships.append(relationship)
        return {
            "app_name": str(slots.get("app_name") or slots.get("app") or "").strip().lower(),
            "subscription_name": str(
                slots.get("subscription_name")
                or slots.get("subscription")
                or ""
            ).strip().lower(),
            "relationships": relationships,
            "new_password": str(
                slots.get("new_password")
                or slots.get("password")
                or ""
            ).strip(),
        }
    if intent_type == "appworld_pay_csv_debts_via_venmo_or_splitwise":
        private_value = slots.get("private")
        privacy = str(slots.get("privacy") or "").strip().lower()
        if isinstance(private_value, str):
            private = private_value.lower() in {"true", "private", "privately", "yes"}
        elif private_value is None and privacy:
            private = privacy in {"private", "privately"}
        else:
            private = bool(private_value)
        return {
            "csv_file_name": str(
                slots.get("csv_file_name")
                or slots.get("file_name")
                or ""
            ).strip(),
            "private": private,
        }
    if intent_type == "appworld_venmo_send_to_phone_number":
        private_value = slots.get("private")
        if isinstance(private_value, str):
            private = private_value.lower() in {"true", "private", "privately", "yes"}
        else:
            private = bool(private_value)
        return {
            "phone_number": str(slots.get("phone_number", "")).strip(),
            "amount": float(slots["amount"]),
            "private": private,
        }
    if intent_type == "appworld_venmo_send_to_named_user":
        return {
            "person_first_name": str(
                slots.get("person_first_name")
                or slots.get("first_name")
                or ""
            ).strip(),
            "amount": float(slots["amount"]),
        }
    if intent_type == "appworld_venmo_send_to_named_user_with_optional_signup":
        return {
            "person_first_name": str(
                slots.get("person_first_name")
                or slots.get("first_name")
                or ""
            ).strip(),
            "amount": float(slots["amount"]),
        }
    if intent_type == "appworld_venmo_pay_flight_bill_from_email":
        return {
            "person_first_name": str(
                slots.get("person_first_name")
                or slots.get("first_name")
                or ""
            ).strip(),
            "note": str(slots.get("note") or slots.get("description") or "").strip(),
        }
    if intent_type == "appworld_venmo_pay_coworkers_and_email":
        relationships_value = slots.get("relationships") or slots.get("relationship") or []
        if isinstance(relationships_value, str):
            relationships = extract_relationships(relationships_value)
        else:
            relationships = []
            for item in relationships_value if isinstance(relationships_value, list) else []:
                key = str(item).lower().strip()
                relationship = RELATION_ALIASES.get(key, key)
                if relationship and relationship not in relationships:
                    relationships.append(relationship)
        return {
            "relationships": relationships,
            "amount": float(slots["amount"]),
            "note": str(slots.get("note") or slots.get("venmo_note") or "").strip(),
            "email_subject": str(slots.get("email_subject") or slots.get("subject") or "").strip(),
            "email_body": str(slots.get("email_body") or slots.get("body") or "").strip(),
        }
    if intent_type == "appworld_venmo_accept_named_carpool_request_this_month":
        return {
            "person_first_name": str(
                slots.get("person_first_name")
                or slots.get("first_name")
                or ""
            ).strip()
        }
    if intent_type == "appworld_venmo_correct_housing_bill_request":
        return {
            "percent": float(slots["percent"]),
            "adjustment": str(slots.get("adjustment", "")).strip().lower(),
            "note": str(slots.get("note", "")).strip(),
        }
    if intent_type == "appworld_venmo_approve_requests_and_withdraw_balance":
        date_window = str(slots.get("date_window", "")).strip().lower().replace(" ", "_")
        if date_window in {"this_or_last_month", "this_and_last_month"}:
            date_window = "this_or_the_last_month"
        return {
            "date_window": date_window,
            "card_last4": str(slots.get("card_last4", "")).strip(),
        }
    if intent_type == "appworld_venmo_request_money_from_contact":
        relationships_value = slots.get("relationships", [])
        if isinstance(relationships_value, str):
            relationships = extract_relationships(relationships_value)
        else:
            relationships = []
            for item in relationships_value if isinstance(relationships_value, list) else []:
                key = str(item).lower().strip()
                relationship = RELATION_ALIASES.get(key, key)
                if relationship and relationship not in relationships:
                    relationships.append(relationship)
        private_value = slots.get("private")
        if isinstance(private_value, str):
            private = private_value.lower() in {"true", "private", "privately", "yes"}
        else:
            private = bool(private_value)
        return {
            "relationships": relationships,
            "person_first_name": str(slots.get("person_first_name", "")).strip(),
            "amount": float(slots["amount"]),
            "private": private,
            "note": slots.get("note"),
        }
    if intent_type == "appworld_venmo_settle_trip_note_debts":
        relationship = str(
            slots.get("relationship")
            or slots.get("relationship_type")
            or ""
        ).strip().lower()
        relationship = RELATION_ALIASES.get(relationship, relationship)
        return {
            "relationship": relationship,
            "trip_name": str(slots.get("trip_name") or slots.get("vacation_spot") or "").strip(),
            "note": str(slots.get("note") or "").strip(),
        }
    if intent_type == "appworld_venmo_settle_roommate_dinner":
        return {
            "taxi_total": float(slots["taxi_total"]),
            "food_total": float(slots["food_total"]),
            "food_payer_first_name": str(
                slots.get("food_payer_first_name")
                or slots.get("food_payer")
                or ""
            ).strip(),
            "taxi_note": str(slots.get("taxi_note", "")).strip(),
            "food_note": str(slots.get("food_note", "")).strip(),
        }
    if intent_type == "appworld_venmo_send_to_each_relationship_with_refill":
        relationships_value = slots.get("relationships", [])
        if isinstance(relationships_value, str):
            relationships = extract_relationships(relationships_value)
        else:
            relationships = []
            for item in relationships_value if isinstance(relationships_value, list) else []:
                key = str(item).lower().strip()
                relationship = RELATION_ALIASES.get(key, key)
                if relationship and relationship not in relationships:
                    relationships.append(relationship)
        return {
            "relationships": relationships,
            "amount": float(slots["amount"]),
            "note": slots.get("note"),
        }
    if intent_type == "appworld_venmo_birthday_child_payment_and_text":
        relationship = str(slots.get("relationship") or "").strip().lower()
        relationship = RELATION_ALIASES.get(relationship, relationship)
        multiplier_value = slots.get("multiplier")
        if isinstance(multiplier_value, str):
            multiplier_text = multiplier_value.strip().lower()
            multiplier_by_word = {"twice": 2.0, "thrice": 3.0, "four times": 4.0}
            multiplier = multiplier_by_word.get(multiplier_text)
            if multiplier is None:
                multiplier = float(multiplier_text.split()[0])
        else:
            multiplier = float(multiplier_value)
        return {
            "relationship": relationship,
            "multiplier": multiplier,
            "note": str(slots.get("note", "")).strip(),
            "message": str(slots.get("message", "")).strip(),
        }
    if intent_type == "appworld_venmo_correct_sent_requests_yesterday_evening":
        relationships_value = slots.get("relationships") or slots.get("relationship") or []
        if isinstance(relationships_value, str):
            relationships = extract_relationships(relationships_value)
        else:
            relationships = []
            for item in relationships_value if isinstance(relationships_value, list) else []:
                key = str(item).lower().strip()
                relationship = RELATION_ALIASES.get(key, key)
                if relationship and relationship not in relationships:
                    relationships.append(relationship)
        adjustment = str(slots.get("adjustment", "")).strip().lower()
        direction = str(slots.get("direction", "")).strip().lower()
        if adjustment in {"less", "lower", "decrease"} or direction == "less":
            adjustment = "decrease"
        if adjustment in {"more", "higher", "increase"} or direction == "more":
            adjustment = "increase"
        amount_value = slots.get("difference_amount", slots.get("amount"))
        return {
            "relationships": relationships,
            "adjustment": adjustment,
            "difference_amount": float(amount_value),
        }
    if intent_type == "appworld_venmo_remind_old_payment_requests":
        relationships_value = slots.get("relationships", [])
        if isinstance(relationships_value, str):
            relationships = extract_relationships(relationships_value)
        else:
            relationships = []
            for item in relationships_value if isinstance(relationships_value, list) else []:
                key = str(item).lower().strip()
                relationship = RELATION_ALIASES.get(key, key)
                if relationship and relationship not in relationships:
                    relationships.append(relationship)
        return {
            "relationships": relationships,
            "min_days": int(slots["min_days"]),
        }
    if intent_type == "appworld_venmo_process_pending_payment_requests":
        relationships_value = slots.get("relationships", [])
        if isinstance(relationships_value, str):
            relationships = extract_relationships(relationships_value)
        else:
            relationships = []
            for item in relationships_value if isinstance(relationships_value, list) else []:
                key = str(item).lower().strip()
                relationship = RELATION_ALIASES.get(key, key)
                if relationship and relationship not in relationships:
                    relationships.append(relationship)
        decision = str(slots.get("decision", "")).strip().lower()
        if decision in {"accept", "approve"}:
            decision = "approve"
        if decision in {"reject", "deny"}:
            decision = "deny"
        return {
            "relationships": relationships,
            "decision": decision,
        }
    if intent_type == "appworld_venmo_add_friends_by_relationships":
        relationships_value = slots.get("relationships", [])
        if isinstance(relationships_value, str):
            relationships = extract_relationships(relationships_value)
        else:
            relationships = []
            for item in relationships_value if isinstance(relationships_value, list) else []:
                key = str(item).lower().strip()
                relationship = RELATION_ALIASES.get(key, key)
                if relationship and relationship not in relationships:
                    relationships.append(relationship)
        return {"relationships": relationships}
    if intent_type == "appworld_delete_phone_spam_messages":
        return {"phone_number": str(slots.get("phone_number", "")).strip()}
    if intent_type == "appworld_phone_update_wake_alarm_snooze":
        day_type = str(slots.get("day_type", "")).strip().lower()
        if day_type in {"weekdays", "workday", "workdays"}:
            day_type = "weekday"
        if day_type in {"weekends"}:
            day_type = "weekend"
        return {
            "day_type": day_type,
            "snooze_minutes": int(slots["snooze_minutes"]),
        }
    if intent_type == "appworld_amazon_move_rating_filtered_products":
        comparison = str(slots.get("comparison", "")).strip().lower()
        if comparison in {"less_than", "below", "lower", "<"}:
            comparison = "under"
        if comparison in {"greater_than", "above", "higher", ">"}:
            comparison = "over"
        return {
            "source_container": normalize_amazon_container(slots.get("source_container", "")),
            "target_container": normalize_amazon_container(slots.get("target_container", "")),
            "comparison": comparison,
            "threshold_rating": float(slots["threshold_rating"]),
        }
    if intent_type == "appworld_amazon_move_product_type_between_saved_lists":
        return {
            "source_container": normalize_amazon_container(slots.get("source_container", "")),
            "target_container": normalize_amazon_container(slots.get("target_container", "")),
            "product_type": normalize_amazon_product_type(slots.get("product_type", "")),
        }
    if intent_type == "appworld_amazon_order_product_type_from_saved_list":
        return {
            "source_container": normalize_amazon_container(slots.get("source_container", "")),
            "product_type": normalize_amazon_product_type(slots.get("product_type", "")),
            "address_name": str(slots.get("address_name") or "Home").strip(),
            "card_name": str(slots.get("card_name") or "").strip(),
        }
    if intent_type == "appworld_amazon_purchase_phone_recommendation":
        return {
            "recommender_first_name": str(
                slots.get("recommender_first_name")
                or slots.get("person_first_name")
                or slots.get("first_name")
                or ""
            ).strip(),
            "product_type": normalize_amazon_product_type(slots.get("product_type", "")),
            "address_name": str(slots.get("address_name") or "Home").strip(),
            "card_name": str(slots.get("card_name") or "").strip(),
        }
    if intent_type == "appworld_amazon_text_wishlist_itemized_costs":
        relationship = str(slots.get("relationship") or slots.get("partner_relationship") or "").strip().lower()
        return {"relationship": RELATION_ALIASES.get(relationship, relationship)}
    if intent_type == "appworld_amazon_answer_cart_wishlist_total":
        return {}
    if intent_type == "appworld_amazon_order_saved_collections":
        containers_value = slots.get("containers") or slots.get("source_containers") or []
        if isinstance(containers_value, str):
            containers = []
            lowered = containers_value.lower()
            if "cart" in lowered:
                containers.append("cart")
            if "wish" in lowered:
                containers.append("wish_list")
        else:
            containers = [
                normalize_amazon_container(container)
                for container in containers_value
                if str(container).strip()
            ] if isinstance(containers_value, list) else []
        unique_containers = []
        for container in containers:
            if container not in unique_containers:
                unique_containers.append(container)
        return {
            "containers": unique_containers,
            "address_name": str(slots.get("address_name") or "Home").strip(),
            "card_name": str(slots.get("card_name") or "").strip(),
        }
    if intent_type == "appworld_amazon_cart_buy_cheapest_per_type_move_rest":
        return {
            "address_name": str(slots.get("address_name") or "Home").strip(),
            "card_name": str(slots.get("card_name") or "").strip(),
        }
    if intent_type == "appworld_amazon_order_exact_products_restore_cart":
        items_value = slots.get("items") or slots.get("products") or []
        items = []
        if isinstance(items_value, list):
            for item in items_value:
                if isinstance(item, dict):
                    product_name = compact_text(str(item.get("product_name") or item.get("name") or ""))
                    quantity = int(item.get("quantity") or 0)
                    if product_name and quantity > 0:
                        items.append({"product_name": product_name, "quantity": quantity})
        return {
            "items": items,
            "address_name": str(slots.get("address_name") or "Home").strip(),
            "preferred_card_name": str(
                slots.get("preferred_card_name")
                or slots.get("card_name")
                or ""
            ).strip(),
            "restore_cart": bool(slots.get("restore_cart", True)),
        }
    if intent_type == "appworld_amazon_order_product_and_archive_receipt":
        quantity_value = slots.get("quantity") or 1
        if isinstance(quantity_value, str):
            quantity = 1 if quantity_value.strip().lower() == "one" else int(quantity_value)
        else:
            quantity = int(quantity_value)
        bills_root = str(slots.get("bills_root") or slots.get("directory_path") or "~/bills/").strip()
        if bills_root and not bills_root.endswith("/"):
            bills_root += "/"
        return {
            "product_name": compact_text(str(slots.get("product_name") or "")),
            "quantity": quantity,
            "address_name": str(slots.get("address_name") or "Home").strip(),
            "bills_root": bills_root,
        }
    if intent_type == "appworld_amazon_download_all_order_receipts":
        directory_path = str(
            slots.get("directory_path")
            or slots.get("directory")
            or ""
        ).strip()
        if directory_path and not directory_path.endswith("/"):
            directory_path += "/"
        return {
            "directory_path": directory_path,
            "file_format": str(slots.get("file_format") or "").strip(),
        }
    if intent_type == "appworld_amazon_order_trip_supplies_by_deadline":
        product_types_value = slots.get("product_types") or slots.get("products") or []
        product_types = [
            normalize_amazon_product_type(value)
            for value in product_types_value
            if str(value).strip()
        ] if isinstance(product_types_value, list) else []
        return {
            "product_types": product_types,
            "quantity": int(slots.get("quantity") or 0),
            "trip_day": str(slots.get("trip_day") or "").strip().lower(),
            "address_name": str(slots.get("address_name") or "Home").strip(),
            "card_name": str(slots.get("card_name") or "").strip(),
        }
    if intent_type == "appworld_amazon_return_recent_orders":
        return {
            "order_count": int(slots.get("order_count") or slots.get("count") or 0),
            "deliverer_name": str(slots.get("deliverer_name") or slots.get("carrier") or "").strip(),
        }
    if intent_type == "appworld_amazon_return_same_product_except_size_this_week":
        return {
            "product_name": compact_text(str(slots.get("product_name") or "")),
            "keep_size": compact_text(str(slots.get("keep_size") or slots.get("relative_size") or "")).lower(),
            "deliverer_name": str(slots.get("deliverer_name") or slots.get("carrier") or "").strip(),
        }
    if intent_type == "appworld_amazon_buy_last_product_variants":
        colors_value = slots.get("colors") or slots.get("target_colors") or slots.get("color") or []
        if isinstance(colors_value, str):
            colors = [
                compact_text(part).lower()
                for part in re.split(r"\band\b|,", colors_value, flags=re.IGNORECASE)
                if part.strip()
            ]
        else:
            colors = [
                compact_text(str(color)).lower()
                for color in colors_value
                if str(color).strip()
            ] if isinstance(colors_value, list) else []
        return {
            "product_type": normalize_amazon_product_type(slots.get("product_type", "")),
            "colors": colors,
            "address_name": str(slots.get("address_name") or "Home").strip(),
            "card_name": str(slots.get("card_name") or "").strip(),
        }
    if intent_type == "appworld_amazon_replace_last_product_adjacent_size":
        size_direction = str(
            slots.get("size_direction")
            or slots.get("direction")
            or slots.get("replacement_size_direction")
            or ""
        ).strip().lower()
        if size_direction in {"bigger", "larger", "up", "increase"}:
            size_direction = "larger"
        if size_direction in {"smaller", "down", "decrease"}:
            size_direction = "smaller"
        return {
            "product_type": normalize_amazon_product_type(slots.get("product_type", "")),
            "size_direction": size_direction,
            "preferred_color": compact_text(str(slots.get("preferred_color") or slots.get("color") or "")).lower(),
            "address_name": str(slots.get("address_name") or "Home").strip(),
            "card_name": str(slots.get("card_name") or "").strip(),
        }
    if intent_type == "appworld_amazon_order_preferred_color_size_product":
        preferences_value = (
            slots.get("color_preferences")
            or slots.get("colors")
            or slots.get("preferences")
            or []
        )
        if isinstance(preferences_value, str):
            color_preferences = [
                compact_text(part).lower()
                for part in preferences_value.split(">")
                if part.strip()
            ]
        else:
            color_preferences = [
                compact_text(str(color)).lower()
                for color in preferences_value
                if str(color).strip()
            ] if isinstance(preferences_value, list) else []
        return {
            "product_name": compact_text(str(slots.get("product_name") or "")),
            "relative_size": compact_text(str(slots.get("relative_size") or slots.get("size") or "")).lower(),
            "color_preferences": color_preferences,
            "quantity": int(slots.get("quantity") or 0),
            "address_name": str(slots.get("address_name") or "Home").strip(),
            "card_name": str(slots.get("card_name") or "").strip(),
        }
    if intent_type == "appworld_amazon_order_filtered_product":
        min_price_value = slots.get("min_price")
        max_price_value = slots.get("max_price")
        min_rating_value = slots.get("min_product_rating") or slots.get("min_rating")
        min_reviews_value = slots.get("min_product_reviews") or slots.get("min_reviews")
        min_seller_rating_value = slots.get("min_seller_rating") or slots.get("seller_rating")
        max_length_value = slots.get("max_length") or slots.get("length")
        max_width_value = slots.get("max_width") or slots.get("width")
        return {
            "product_type": normalize_amazon_product_type(slots.get("product_type", "")),
            "min_price": float(min_price_value) if min_price_value is not None else None,
            "max_price": float(max_price_value) if max_price_value is not None else None,
            "min_product_rating": float(min_rating_value) if min_rating_value is not None else None,
            "min_product_reviews": int(min_reviews_value) if min_reviews_value is not None else None,
            "min_seller_rating": (
                float(min_seller_rating_value) if min_seller_rating_value is not None else None
            ),
            "price_bounds_inclusive": bool(slots.get("price_bounds_inclusive")),
            "rating_threshold_inclusive": bool(slots.get("rating_threshold_inclusive")),
            "prefer_highest_seller": bool(slots.get("prefer_highest_seller")),
            "source_container": str(slots.get("source_container") or "search").strip(),
            "prior_ordered_sellers_only": bool(slots.get("prior_ordered_sellers_only")),
            "max_length": float(max_length_value) if max_length_value is not None else None,
            "max_width": float(max_width_value) if max_width_value is not None else None,
            "quantity_relationship": str(slots.get("quantity_relationship") or "").strip(),
            "allow_mixed_products": bool(slots.get("allow_mixed_products", True)),
            "quantity": int(slots.get("quantity") or 1),
            "address_name": str(slots.get("address_name") or "Home").strip(),
            "card_name": str(slots.get("card_name") or "").strip(),
        }
    if intent_type == "appworld_amazon_post_question_last_ordered_product":
        return {
            "product_type": normalize_amazon_product_type(slots.get("product_type", "")),
            "question": str(slots.get("question") or "").strip(),
        }
    if intent_type == "appworld_amazon_update_last_month_order_review":
        return {
            "product_color": str(slots.get("product_color") or slots.get("color") or "").strip().lower(),
            "product_type": normalize_amazon_product_type(slots.get("product_type", "")),
            "target_rating": int(slots.get("target_rating") or slots.get("rating") or 0),
            "title": str(slots.get("title") or slots.get("review_title") or "").strip(),
        }
    if intent_type == "appworld_amazon_answer_last_order_question_yes_no":
        return {
            "product_type": normalize_amazon_product_type(slots.get("product_type", "")),
            "question": str(slots.get("question") or "").strip().rstrip("?"),
        }
    if intent_type == "appworld_amazon_answer_verified_battery_life_hours":
        return {"product_name": compact_text(str(slots.get("product_name") or ""))}
    if intent_type == "appworld_amazon_answer_returned_product_yes_no":
        return {
            "product_type": normalize_amazon_product_type(slots.get("product_type", "")),
            "period": compact_text(str(slots.get("period") or "")).lower(),
        }
    if intent_type == "appworld_amazon_answer_order_arrival_date":
        return {
            "day_offset": int(slots.get("day_offset") or 0),
            "date_format": str(slots.get("date_format") or "").strip().upper(),
        }
    if intent_type == "appworld_amazon_answer_spending_total":
        return {"period": compact_text(str(slots.get("period") or "")).lower()}
    if intent_type == "appworld_amazon_answer_current_price_from_birthday_order":
        relationship = str(slots.get("relationship") or "").strip().lower()
        return {
            "product_type": normalize_amazon_product_type(slots.get("product_type", "")),
            "relationship": RELATION_ALIASES.get(relationship, relationship),
        }
    if intent_type == "appworld_membership_paid_total":
        app_name = str(slots.get("app_name") or slots.get("app") or "").strip().lower()
        membership = str(slots.get("membership") or slots.get("subscription") or "").strip().lower()
        if not app_name:
            if membership == "prime":
                app_name = "amazon"
            elif membership == "premium":
                app_name = "spotify"
        return {"app_name": app_name}
    if intent_type == "appworld_membership_last_payment_card_name":
        app_name = str(slots.get("app_name") or slots.get("app") or "").strip().lower()
        membership = str(slots.get("membership") or slots.get("subscription") or "").strip().lower()
        if not app_name:
            if membership == "prime":
                app_name = "amazon"
            elif membership == "premium":
                app_name = "spotify"
        return {"app_name": app_name}
    if intent_type == "appworld_membership_remaining_duration":
        app_name = str(slots.get("app_name") or slots.get("app") or "").strip().lower()
        membership = str(slots.get("membership") or slots.get("subscription") or "").strip().lower()
        if not app_name:
            if membership == "prime":
                app_name = "amazon"
            elif membership == "premium":
                app_name = "spotify"
        unit = str(slots.get("unit") or slots.get("duration_unit") or "").strip().lower()
        return {"app_name": app_name, "unit": unit}
    if intent_type == "appworld_delete_gmail_empty_drafts":
        condition = str(slots.get("condition", "")).strip().lower()
        if condition in {"and", "both", "all"}:
            condition = "both"
        if condition in {"or", "either", "any"}:
            condition = "either"
        return {"condition": condition}
    if intent_type == "appworld_gmail_send_future_scheduled_drafts_now":
        return {}
    if intent_type == "appworld_gmail_amazon_promo_codes_answer":
        return {}
    if intent_type == "appworld_gmail_count_threads":
        label = str(slots.get("label") or "").strip().lower()
        read_state = str(slots.get("read_state") or slots.get("state") or "").strip().lower()
        mailbox = str(slots.get("mailbox") or "").strip().lower()
        return {"mailbox": mailbox, "read_state": read_state, "label": label}
    if intent_type == "appworld_gmail_schedule_resignation_draft":
        return {
            "attachment_path": str(slots.get("attachment_path") or slots.get("file_path") or "").strip(),
            "weekday": str(slots.get("weekday") or slots.get("day") or "").strip().lower(),
            "week_offset": int(slots.get("week_offset") or 0),
            "hour": int(slots.get("hour") or 0),
        }
    if intent_type == "appworld_gmail_thread_cleanup":
        action = str(slots.get("action", "")).strip().lower()
        if action in {"archive_threads", "archive"}:
            action = "archive"
        if action in {"delete_threads", "delete"}:
            action = "delete"
        exception_mode = str(slots.get("exception_mode", "")).strip().lower()
        if exception_mode in {"or", "either", "any"}:
            exception_mode = "or"
        if exception_mode in {"and", "both"}:
            exception_mode = "and"
        return {"action": action, "exception_mode": exception_mode}
    if intent_type == "appworld_gmail_mark_threads_read_state_by_calendar_window":
        target_state = str(slots.get("target_state") or slots.get("state") or "").strip().lower()
        window = str(slots.get("window") or "").strip().lower().replace(" ", "_")
        return {"target_state": target_state, "window": window}
    if intent_type == "appworld_gmail_delete_archived_threads_by_calendar_window":
        window = str(slots.get("window") or "").strip().lower().replace(" ", "_")
        return {"window": window}
    if intent_type == "appworld_gmail_forward_anniversary_announcement_email":
        return {"recipient_email": str(slots.get("recipient_email") or "").strip().lower()}
    if intent_type == "appworld_gmail_forward_caterer_bill_to_manager_with_note":
        return {
            "note_prefix": str(
                slots.get("note_prefix") or slots.get("note") or slots.get("message") or ""
            ).strip()
        }
    if intent_type == "appworld_gmail_forward_roommate_bill_to_other_roommates":
        return {
            "file_name": str(
                slots.get("file_name")
                or slots.get("attachment_name")
                or slots.get("attachment")
                or ""
            ).strip()
        }
    if intent_type == "appworld_gmail_forward_trip_expenses_thread_with_attachment":
        return {
            "sender_first_name": str(
                slots.get("sender_first_name")
                or slots.get("sender")
                or ""
            ).strip(),
            "recipient_first_name": str(
                slots.get("recipient_first_name")
                or slots.get("recipient")
                or ""
            ).strip(),
            "attachment_path": str(
                slots.get("attachment_path")
                or slots.get("file_path")
                or ""
            ).strip(),
            "note_prefix": str(
                slots.get("note_prefix")
                or slots.get("note")
                or slots.get("message")
                or ""
            ).strip(),
        }
    if intent_type == "appworld_gmail_reply_weekly_manager_tasks_by_star_state":
        return {
            "subject_prefix": str(slots.get("subject_prefix") or slots.get("prefix") or "").strip(),
            "done_reply": str(slots.get("done_reply") or slots.get("done") or "").strip(),
            "not_done_reply": str(
                slots.get("not_done_reply") or slots.get("not_done") or slots.get("unfinished_reply") or ""
            ).strip(),
        }
    if intent_type == "appworld_gmail_star_threads_by_relationship":
        relationship = str(slots.get("relationship", "")).strip().lower()
        return {"relationship": RELATION_ALIASES.get(relationship, relationship)}
    if intent_type == "appworld_gmail_relabel_priority_threads":
        label_aliases = {
            "p1": "P1",
            "p2": "P2",
            "p3": "P3",
            "priority_1": "priority-1",
            "priority_2": "priority-2",
            "priority_3": "priority-3",
            "pr_1": "pr-1",
            "pr_2": "pr-2",
            "pr_3": "pr-3",
        }

        def normalize_priority_label(value: object) -> str:
            label = str(value or "").strip().replace(" ", "-")
            return label_aliases.get(label.lower(), label)

        return {
            "source_label_1": normalize_priority_label(slots.get("source_label_1")),
            "source_label_2": normalize_priority_label(slots.get("source_label_2")),
            "target_label_1": normalize_priority_label(slots.get("target_label_1")),
            "target_label_2": normalize_priority_label(slots.get("target_label_2")),
            "remove_label": normalize_priority_label(slots.get("remove_label")),
        }
    if intent_type == "appworld_gmail_attach_job_search_files_and_send":
        return {
            "days_back": int(slots["days_back"]),
            "file_name": str(slots.get("file_name") or "").strip(),
        }
    if intent_type == "appworld_gmail_download_flight_ticket_attachment":
        directory_path = str(
            slots.get("directory_path")
            or slots.get("directory")
            or ""
        ).strip()
        if directory_path and not directory_path.endswith("/"):
            directory_path += "/"
        return {
            "destination": str(slots.get("destination") or "").strip(),
            "directory_path": directory_path,
        }
    if intent_type == "appworld_gmail_email_named_file_to_relationship":
        relationship = str(slots.get("relationship") or "").strip().lower()
        relationship = RELATION_ALIASES.get(relationship, relationship)
        return {
            "file_description": str(
                slots.get("file_description")
                or slots.get("document")
                or slots.get("file")
                or ""
            ).strip().lower(),
            "relationship": relationship,
        }
    if intent_type == "appworld_bucket_list_status_update":
        done_value = slots.get("done")
        if isinstance(done_value, str):
            done = done_value.lower() in {"true", "done", "yes", "checked"}
        else:
            done = bool(done_value)
        return {"item": slots.get("item"), "done": done}
    if intent_type == "appworld_simple_note_count_bucket_list_status":
        status = str(slots.get("status") or "").strip().lower()
        if status in {"completed", "complete", "done", "checked"}:
            status = "done"
        if status in {"left", "left_to_do", "todo", "not_done", "remaining"}:
            status = "todo"
        return {"status": status}
    if intent_type == "appworld_spotify_follow_artists_by_genre_followers":
        return {
            "genre": str(slots.get("genre", "")).strip().lower(),
            "min_follower_count": int(slots["min_follower_count"]),
        }
    if intent_type == "appworld_spotify_add_artist_playcount_songs_to_queue":
        return {
            "artist_name": str(slots.get("artist_name", "")).strip(),
            "min_play_count": int(slots["min_play_count"]),
        }
    if intent_type == "appworld_spotify_like_songs_from_followed_artists":
        return {}
    if intent_type == "appworld_spotify_public_liked_library_playlist_share":
        relationship = str(slots.get("partner_relationship", "")).strip().lower()
        relationship = RELATION_ALIASES.get(relationship, relationship)
        return {"partner_relationship": relationship}
    if intent_type == "appworld_spotify_sync_following_by_liked_song_artists":
        operation = str(slots.get("operation", "")).strip().lower()
        if operation in {"follow", "follow_liked", "follow_liked_song_artists"}:
            operation = "follow_liked_song_artists"
        if operation in {"unfollow", "unfollow_non_liked", "unfollow_non_liked_song_artists"}:
            operation = "unfollow_non_liked_song_artists"
        return {"operation": operation}
    if intent_type == "appworld_spotify_playlist_best_song_per_collection":
        song_metric = str(slots.get("song_metric", "")).strip().lower()
        if song_metric in {"most-played", "most_played", "play-count", "play_count"}:
            song_metric = "play_count"
        if song_metric in {"highest-rated", "highest_rated", "rating"}:
            song_metric = "rating"
        collection_type = str(slots.get("collection_type", "")).strip().lower()
        if collection_type in {"album", "albums", "album_library", "album library"}:
            collection_type = "album_library"
        if collection_type in {"playlist", "playlists", "playlist_library", "playlist library"}:
            collection_type = "playlist_library"
        return {
            "playlist_title": slots.get("playlist_title"),
            "song_metric": song_metric,
            "collection_type": collection_type,
        }
    if intent_type == "appworld_spotify_playlist_from_recent_simple_note":
        return {
            "playlist_title": str(
                slots.get("playlist_title")
                or slots.get("title")
                or ""
            ).strip()
        }
    if intent_type == "appworld_spotify_reply_liked_song_recommendations_email":
        relationship = str(slots.get("relationship", "")).strip().lower()
        return {
            "relationship": RELATION_ALIASES.get(relationship, relationship),
            "message_prefix": str(
                slots.get("message_prefix")
                or slots.get("prefix")
                or ""
            ).strip(),
        }
    if intent_type == "appworld_spotify_update_song_recommendation_draft_from_library":
        return {
            "person_first_name": str(
                slots.get("person_first_name")
                or slots.get("first_name")
                or ""
            ).strip()
        }
    if intent_type == "appworld_simple_note_fill_liked_song_release_months":
        return {}
    if intent_type == "appworld_spotify_append_most_common_playlist_genre":
        return {}
    if intent_type == "appworld_spotify_like_all_library_items":
        return {}
    if intent_type == "appworld_spotify_download_liked_library_songs":
        collection_type = str(slots.get("collection_type", "")).strip().lower()
        if collection_type in {"playlist", "playlists", "playlist_library", "playlist library"}:
            collection_type = "playlist_library"
        if collection_type in {"song", "songs", "song_library", "song library"}:
            collection_type = "song_library"
        if collection_type in {"album", "albums", "album_library", "album library"}:
            collection_type = "album_library"
        return {"collection_type": collection_type}
    if intent_type == "appworld_spotify_rate_library_songs_by_liked_status":
        collection_type = str(slots.get("collection_type", "")).strip().lower()
        if collection_type in {"playlist", "playlists", "playlist_library", "playlist library"}:
            collection_type = "playlist_library"
        if collection_type in {"song", "songs", "song_library", "song library"}:
            collection_type = "song_library"
        if collection_type in {"album", "albums", "album_library", "album library"}:
            collection_type = "album_library"
        liked_filter = str(slots.get("liked_filter", "")).strip().lower()
        if liked_filter in {"liked", "like", "likes", "true"}:
            liked_filter = "liked"
        if liked_filter in {"not liked", "not_liked", "unliked", "false"}:
            liked_filter = "not_liked"
        return {
            "collection_type": collection_type,
            "liked_filter": liked_filter,
            "target_rating": int(slots["target_rating"]),
        }
    if intent_type == "appworld_spotify_follow_artists_from_liked_songs_and_albums":
        return {}
    if intent_type == "appworld_spotify_follow_playlist_song_artists_by_genre":
        return {"genre": str(slots.get("genre", "")).strip().lower()}
    if intent_type == "appworld_spotify_top_played_genre_titles":
        return {
            "genre": str(slots.get("genre", "")).strip().lower(),
            "limit": int(slots["limit"]),
        }
    if intent_type == "appworld_spotify_count_unique_library_songs":
        return {}
    if intent_type == "appworld_venmo_pay_grocery_from_text_and_notify":
        return {
            "person_first_name": str(slots.get("person_first_name", "")).strip(),
            "note": slots.get("note"),
            "message": slots.get("message"),
        }
    if intent_type == "appworld_spotify_count_recent_release_library_songs":
        include_current_year_value = slots.get("include_current_year", True)
        if isinstance(include_current_year_value, str):
            include_current_year = include_current_year_value.lower() in {
                "true",
                "yes",
                "include",
                "current",
                "this",
                "this_year",
            }
        else:
            include_current_year = bool(include_current_year_value)
        return {
            "years_back": int(slots.get("years_back", 1)),
            "include_current_year": include_current_year,
        }
    if intent_type == "appworld_spotify_navigate_until_artist":
        direction = str(slots.get("direction", "")).strip().lower()
        if direction in {"back", "backward", "prev", "previous_song"}:
            direction = "previous"
        if direction in {"forward", "next_song"}:
            direction = "next"
        return {
            "direction": direction,
            "artist_name": str(slots.get("artist_name", "")).strip(),
        }
    if intent_type == "appworld_venmo_reset_friends_to_phone_friends":
        return {}
    if intent_type == "appworld_spotify_filter_queue_by_liked_status":
        remove_filter = str(
            slots.get("remove_filter")
            or slots.get("liked_filter")
            or slots.get("status")
            or ""
        ).strip().lower()
        if remove_filter in {"liked", "like", "likes", "true"}:
            remove_filter = "liked"
        if remove_filter in {"not liked", "not_liked", "unliked", "false"}:
            remove_filter = "not_liked"
        return {"remove_filter": remove_filter}
    if intent_type == "appworld_spotify_navigate_until_private_status":
        direction = str(slots.get("direction", "")).strip().lower()
        if direction in {"back", "backward", "prev", "previous_song"}:
            direction = "previous"
        if direction in {"forward", "next_song"}:
            direction = "next"
        status_property = str(
            slots.get("status_property")
            or slots.get("status")
            or slots.get("private_status")
            or ""
        ).strip().lower()
        if status_property in {"like", "liked_song"}:
            status_property = "liked"
        if status_property in {"download", "downloaded_song"}:
            status_property = "downloaded"
        return {"direction": direction, "status_property": status_property}
    if intent_type == "appworld_venmo_sum_month_transactions":
        direction = str(slots.get("direction", "")).strip().lower().replace(" ", "_")
        if direction in {"both", "sent_and_received", "sent_or_received", "sent_to_or_received"}:
            direction = "sent_or_received"
        return {"direction": direction}
    if intent_type == "appworld_venmo_sum_recent_received_requests":
        return {"days": int(slots.get("days", 0))}
    if intent_type == "appworld_spotify_reset_queue_with_recommendations":
        return {}
    if intent_type == "appworld_spotify_archive_playlist_songs_from_file":
        return {
            "source_file_path": str(slots.get("source_file_path", "")).strip(),
            "playlist_title": str(slots.get("playlist_title", "")).strip(),
        }
    if intent_type == "appworld_simple_note_import_markdown_files":
        return {"source_directory": str(slots.get("source_directory", "")).strip()}
    if intent_type == "appworld_simple_note_workout_duration":
        day_ref = str(slots.get("day_ref") or slots.get("day") or "").strip().lower()
        if day_ref in {"on sundays", "sundays"}:
            day_ref = "sunday"
        return {"day_ref": day_ref}
    if intent_type == "appworld_simple_note_random_quote":
        quote_type = str(slots.get("quote_type") or slots.get("type") or "").strip().lower()
        return {"quote_type": quote_type}
    if intent_type == "appworld_simple_note_longest_habit_streak":
        habit_key = str(
            slots.get("habit_key")
            or slots.get("habit")
            or ""
        ).strip().lower().replace("-", "_").replace(" ", "_")
        return {"habit_key": habit_key}
    if intent_type == "appworld_simple_note_add_today_habit_log":
        habit_key = str(
            slots.get("habit_key")
            or slots.get("habit")
            or ""
        ).strip().lower().replace("-", "_").replace(" ", "_")
        value = slots.get("value")
        if isinstance(value, str):
            value = value.strip().lower() in {"yes", "true", "done", "1"}
        return {"habit_key": habit_key, "value": bool(value)}
    if intent_type == "appworld_simple_note_export_habit_tracker_csv":
        return {
            "destination_path": str(slots.get("destination_path") or slots.get("file_path") or "").strip(),
            "sort_order": str(slots.get("sort_order") or "").strip().lower(),
        }
    if intent_type == "appworld_simple_note_update_monthly_venmo_expense":
        return {}
    if intent_type == "appworld_todoist_fill_today_from_schedule":
        return {
            "target_project_name": str(
                slots.get("target_project_name")
                or slots.get("project_name")
                or slots.get("target_project")
                or ""
            ).strip()
        }
    if intent_type == "appworld_splitwise_record_trip_expenses_from_simple_note":
        relationship_type = str(
            slots.get("relationship_type")
            or slots.get("relationship")
            or ""
        ).strip().lower()
        if relationship_type in {"friend"}:
            relationship_type = "friends"
        if relationship_type in {"coworker", "co_worker", "co-workers", "co workers"}:
            relationship_type = "coworkers"
        return {"relationship_type": relationship_type}
    if intent_type == "appworld_venmo_approve_roommate_requests_this_month":
        return {}
    if intent_type == "appworld_file_update_reunion_rsvps_from_phone":
        return {
            "directory_path": str(
                slots.get("directory_path")
                or slots.get("source_directory")
                or slots.get("folder")
                or ""
            ).strip()
        }
    if intent_type == "appworld_file_delete_downloads_by_extension":
        extension = str(slots.get("extension", "")).strip().lower()
        if extension and not extension.startswith("."):
            extension = "." + extension
        return {"extension": extension}
    if intent_type == "appworld_spotify_followed_artist_follower_extreme":
        return {"extreme": str(slots.get("extreme", "")).strip().lower()}
    if intent_type == "appworld_spotify_liked_genre_extreme":
        collection_type = str(slots.get("collection_type", "")).strip().lower()
        if collection_type in {"song", "songs", "song library", "song_library"}:
            collection_type = "song_library"
        if collection_type in {"album", "albums", "album library", "album_library"}:
            collection_type = "album_library"
        if collection_type in {"playlist", "playlists", "playlist library", "playlist_library"}:
            collection_type = "playlist_library"
        return {
            "collection_type": collection_type,
            "extreme": str(slots.get("extreme", "")).strip().lower(),
        }
    if intent_type == "appworld_spotify_playlist_artist_song_count_extreme":
        return {
            "extreme": str(slots.get("extreme", "")).strip().lower(),
            "limit": int(slots.get("limit", 0)),
        }
    if intent_type == "appworld_venmo_sum_year_bill_payments":
        return {"bill_type": str(slots.get("bill_type", "")).strip().lower()}
    if intent_type == "appworld_venmo_friend_transaction_counterparties":
        direction = str(slots.get("direction", "")).strip().lower().replace(" ", "_")
        if direction in {"both", "sent_and_received", "sent_or_received"}:
            direction = "sent_or_received"
        sync_mode = str(slots.get("sync_mode", "add_only")).strip().lower()
        if sync_mode in {"replace", "reset", "sync"}:
            sync_mode = "sync"
        else:
            sync_mode = "add_only"
        return {"direction": direction, "sync_mode": sync_mode}
    if intent_type == "appworld_venmo_count_friends_since_month_start":
        month = str(slots.get("month", "")).strip().lower()
        year_ref = str(slots.get("year_ref", "")).strip().lower().replace(" ", "_")
        if "year_offset" in slots:
            year_offset = int(slots.get("year_offset", 0))
        else:
            year_offset = -1 if year_ref == "last_year" else 0
        return {"month": month, "year_offset": year_offset}
    if intent_type == "appworld_spotify_play_released_year_from_collection":
        collection_type = str(slots.get("collection_type", "")).strip().lower()
        if collection_type in {"song", "songs", "song library", "song_library"}:
            collection_type = "song_library"
        if collection_type in {"album", "albums", "album library", "album_library"}:
            collection_type = "album_library"
        if collection_type in {"playlist", "playlists", "playlist library", "playlist_library"}:
            collection_type = "playlist_library"
        return {
            "release_year": int(slots.get("release_year", 0)),
            "collection_type": collection_type,
        }
    if intent_type == "appworld_venmo_like_transactions_by_relationship_period":
        relationships_value = slots.get("relationships", [])
        if isinstance(relationships_value, str):
            relationships = extract_relationships(relationships_value)
        else:
            relationships = []
            for item in relationships_value if isinstance(relationships_value, list) else []:
                key = str(item).lower().strip()
                relationship = RELATION_ALIASES.get(key, key)
                if relationship and relationship not in relationships:
                    relationships.append(relationship)
        return {
            "relationships": relationships,
            "period": str(slots.get("period", "")).strip().lower(),
        }
    if intent_type == "appworld_venmo_manager_meal_total_from_social_feed":
        relationships_value = slots.get("relationships", [])
        if isinstance(relationships_value, str):
            relationships = extract_relationships(relationships_value)
        else:
            relationships = []
            for item in relationships_value if isinstance(relationships_value, list) else []:
                key = str(item).lower().strip()
                relationship = RELATION_ALIASES.get(key, key)
                if relationship and relationship not in relationships:
                    relationships.append(relationship)
        return {
            "relationships": relationships,
            "meal": str(slots.get("meal", "")).strip().lower(),
            "venue": str(slots.get("venue", "")).strip(),
            "share_amount": float(slots["share_amount"]),
        }
    if intent_type == "appworld_venmo_sum_transaction_likes":
        direction = str(slots.get("direction", "")).strip().lower().replace(" ", "_")
        if direction in {"both", "sent_and_received", "sent/received"}:
            direction = "sent_or_received"
        return {
            "direction": direction,
            "period": str(slots.get("period", "")).strip().lower(),
        }
    if intent_type == "appworld_file_prefix_and_move_old_files":
        return {
            "source_directory": str(slots.get("source_directory", "")).strip(),
            "prefix_format": str(slots.get("prefix_format", "")).strip(),
            "old_destination_directory": str(
                slots.get("old_destination_directory")
                or slots.get("destination_directory")
                or ""
            ).strip(),
        }
    if intent_type == "appworld_file_reorganize_dated_meeting_files":
        return {"source_directory": str(slots.get("source_directory", "")).strip()}
    if intent_type == "appworld_spotify_current_artist_followers":
        return {}
    if intent_type == "appworld_simple_note_export_markdown":
        return {"destination_directory": str(slots.get("destination_directory", "")).strip()}
    if intent_type == "appworld_spotify_play_offline_downloaded_collection":
        collection_type = str(slots.get("collection_type", "")).strip().lower()
        if collection_type in {"album_library", "albums"}:
            collection_type = "album"
        if collection_type in {"playlist_library", "playlists"}:
            collection_type = "playlist"
        return {
            "collection_type": collection_type,
            "required_minutes": float(slots["required_minutes"]),
        }
    return dict(slots)


def verify_or_repair_llm_intent_frame(
    frame: IntentFrame,
    instruction: str,
    runtime: RaveRuntime,
    available_tools: AvailableTools,
) -> IntentFrame:
    """Reject semantically invalid LLM frames that still satisfy the slot schema."""
    raw = instruction.strip().lower()
    strict_compiler_intents = {
        "appworld_splitwise_record_trip_expenses_from_simple_note",
        "appworld_venmo_request_money_from_contact",
        "appworld_venmo_settle_roommate_dinner",
        "appworld_file_update_reunion_rsvps_from_phone",
        "appworld_spotify_play_offline_downloaded_collection",
    }
    if frame.intent_type in strict_compiler_intents:
        repaired = runtime.compile_frame(instruction, instruction, available_tools)
        if repaired is not None and repaired.intent_type == frame.intent_type:
            return repaired
        return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_send_future_scheduled_drafts_now":
        if raw != "send all my future-scheduled emails on gmail right away.":
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_amazon_promo_codes_answer":
        if raw != (
            "find all amazon promo codes from my gmail account, including spam and archived emails, "
            "and give it to me in a comma-separated list."
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_count_threads":
        if not re.fullmatch(
            r"how many (?:(priority-[123]) )?(read|unread) email threads are in my gmail (inbox|outbox)\?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_schedule_resignation_draft":
        required = [
            "i have drafted my resignation email on gmail",
            "attach \"~/documents/work/",
            "schedule it to be sent to my manager",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_thread_cleanup":
        action = str(frame.get("action", "")).strip().lower()
        instruction_action = ""
        if raw.startswith("archive "):
            instruction_action = "archive"
        if raw.startswith("delete "):
            instruction_action = "delete"
        if instruction_action and action != instruction_action:
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
    if frame.intent_type == "appworld_gmail_mark_threads_read_state_by_calendar_window":
        required = [
            "mark everything in my gmail inbox and outbox",
            "calendar",
        ]
        if not all(part in raw for part in required) or not raw.endswith((" as read.", " as unread.")):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_delete_archived_threads_by_calendar_window":
        required = [
            "delete all my archived gmail threads",
            "calendar month",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_forward_anniversary_announcement_email":
        required = [
            "announcement about our company's anniversary celebration",
            "forward the announcement email",
            "not the entire thread",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_forward_caterer_bill_to_manager_with_note":
        required = [
            "company celebration",
            "caterers have emailed me the bill",
            "forward it to my manager",
            "note prefixed to its body",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_forward_roommate_bill_to_other_roommates":
        required = [
            "my roommate sent me",
            "on gmail sometime ago",
            "forward that email to the rest of my roommates in a single email",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_forward_trip_expenses_thread_with_attachment":
        required = [
            "went on a trip recently",
            "yesterday",
            "emailed me their expenses in a pdf",
            "forward that thread",
            "additional attachment",
            "note prefixed to its body",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_email_named_file_to_relationship":
        required = [
            "email the",
            "found in my file system",
            "to my",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_reply_weekly_manager_tasks_by_star_state":
        required = [
            "my manager assigns me tasks",
            "subject starting with",
            "for this week",
            "starred the emails/tasks",
            "reply accordingly",
            "unstar those threads",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_text_wishlist_itemized_costs":
        required = [
            "itemized list of my amazon wish list",
            "phone text",
            "newline-separated list",
            "price of the product times its quantity",
            "ignore potential tax or delivery fees",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_answer_cart_wishlist_total":
        if raw != "how much does my amazon cart and wishlist cost in total, ignoring potential tax and delivery fees?":
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_order_saved_collections":
        if not (
            re.fullmatch(
                r"buy everything on my amazon wishlist, and have it delivered to my (home|work) address\.?",
                raw,
            )
            or re.fullmatch(
                r"place an order for everything in my amazon cart and wishlist for my (home|work) address\.?",
                raw,
            )
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_cart_buy_cheapest_per_type_move_rest":
        if raw != (
            "i have a few things in my amazon cart. for each product type in it, "
            "buy the cheapest product and move the rest to the wish list."
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_order_exact_products_restore_cart":
        if not re.fullmatch(
            r"place an amazon order for .+?, and have it delivered to my (home|work)\. "
            r"use [a-z0-9 .&'-]+ payment card if it's already in my account, otherwise use what i have in it\. "
            r"also, i have important things in my cart, so revert its state to as it is now after the order\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_order_product_and_archive_receipt":
        if not re.fullmatch(
            r"order (one|\d+) .+? on amazon for (home|work) delivery\. "
            r"save the receipt in the \"~/bills/\" folder\. "
            r"i keep my receipts well-organized by category in that folder\. "
            r"so make sure the file location and name are as per the existing organization\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_download_all_order_receipts":
        if not re.fullmatch(
            r"download receipts of all my amazon orders in \"~/[^\"]+/\" folder in my file system\. "
            r"name the files in the format, \"[^\"]+\"\. replace <order_id> with the actual order id, "
            r"and yyyy-mm-dd with the date when the order was placed\. "
            r"you should be able to find receipts from order confirmation emails\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_order_trip_supplies_by_deadline":
        if not re.fullmatch(
            r"i am going on a trip with friends this (saturday|sunday)\. "
            r"for it, i need \d+ .+? and .+?, each\. place an amazon order for them, "
            r"making sure everything reaches my home by the end of the day before i leave\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_return_recent_orders":
        if not re.fullmatch(
            r"initiate returns via [a-z0-9 .&'-]+ for everything in my last \d+ amazon order\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_return_same_product_except_size_this_week":
        if not re.fullmatch(
            r"i bought a few .+? on amazon this week\. but only the one in "
            r"(extra-large|extra-small|large|small|medium) size fits me well\. "
            r"initiate a return for the rest\. prefer (ups|usps|fedex) as a deliverer, if available\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_buy_last_product_variants":
        if not re.fullmatch(
            r"i liked that last (t-shirt|sweater) i bought on amazon\. "
            r"place a new order for the same in [a-z -]+ and [a-z -]+, one each\. "
            r"make sure to get the size as per that order, and have them delivered (home|work)\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_replace_last_product_adjacent_size":
        if not re.fullmatch(
            r"the last .+? i bought on amazon is a bit too (small|large) for me\. "
            r"initiate a return for it, and buy a replacement of the same in the next (larger|smaller) size\. "
            r"if it's available now in [a-z -]+, prefer it, otherwise go with the same color\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_order_preferred_color_size_product":
        if not re.fullmatch(
            r"make an order for (\d+|one|two|three|four|five) same-colored .+? in "
            r"(extra-small|small|medium|large|extra-large) size on amazon\. "
            r"my color preference is, [a-z0-9 >-]+\. pick the most preferred color that is available\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_order_filtered_product":
        if not (
            re.fullmatch(
                r"buy me a .+? on amazon within \$\d+(?:\.\d+)? "
                r"\(excluding tax\) and have it delivered to my (home|work) address\.?",
                raw,
            )
            or re.fullmatch(
                r"buy me a .+? from amazon within \$\d+(?:\.\d+)? "
                r"\(excluding tax\)\. only trust sellers i have ordered from in the past\.?",
                raw,
            )
            or re.fullmatch(
                r"buy me a .+? on amazon under \$\d+(?:\.\d+)? "
                r"\(excluding tax\), over \d+(?:\.\d+)? rating, and over "
                r"\d+ reviews, and have it delivered to (home|work) address\.?",
                raw,
            )
            or re.fullmatch(
                r"buy me a .+? on amazon with a rating over \d+(?:\.\d+)? "
                r"and have it delivered to my (home|work) address\.?",
                raw,
            )
            or re.fullmatch(
                r"buy me \d+ .+? on amazon of at least \d+(?:\.\d+)? product rating "
                r"and \d+(?:\.\d+)? seller rating for my (home|work) address\. "
                r"they do not have to be identical\.?",
                raw,
            )
            or re.fullmatch(
                r"buy me a .+? on amazon from its highest-rated seller using my .+? card "
                r"for my (home|work) address\.?",
                raw,
            )
            or re.fullmatch(
                r"buy me a .+? on amazon with at least \d+(?:\.\d+)? seller rating "
                r"that will fit in my .+? of \d+(?:\.\d+)?x\d+(?:\.\d+)? "
                r"\(lxw\) inches\.?",
                raw,
            )
            or re.fullmatch(
                r"buy me a .+? from my amazon wishlist that will fit in my .+? "
                r"of \d+(?:\.\d+)?x\d+(?:\.\d+)? \(lxw\) inches\.?",
                raw,
            )
            or re.fullmatch(
                r"buy the highest-rated .+? on amazon in \d+(?:\.\d+)?-\d+(?:\.\d+)? "
                r"price range \(ignoring tax and other fees\) for each of my "
                r"(roommates|siblings) and get them delivered to my home\.?",
                raw,
            )
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_post_question_last_ordered_product":
        if not re.fullmatch(
            r"post a question about the last .+? i ordered on amazon, \".+\"\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_update_last_month_order_review":
        if not re.fullmatch(
            r"change my amazon review about the [a-z]+ (t-shirt|sweater) i ordered last calendar month\. "
            r"make it [1-5] stars? with the title \".+\"\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_answer_last_order_question_yes_no":
        if not re.fullmatch(
            r"based on the question i posted about my last .+? order on amazon, .+? say yes or no\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_answer_verified_battery_life_hours":
        if not re.fullmatch(
            r"how many hours does the battery of .+? last\? "
            r"please answer as per its amazon reviews or questions/answers and and only trust information from its verified purchasers\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_answer_returned_product_yes_no":
        if not re.fullmatch(
            r"have i returned any .+? on amazon in (this month|this year|this or last month)\? say yes or no\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_answer_order_arrival_date":
        if not re.fullmatch(
            r"by when should everything from my (today's|yesterday's) amazon order arrive\? "
            r"tell me the date in (dd-mm|mm-dd|dd/mm) format\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_answer_spending_total":
        if not re.fullmatch(
            r"how much did i spend on amazon in (this calendar year|the last calendar month|this or the last calendar month)\?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_amazon_answer_current_price_from_birthday_order":
        if not re.fullmatch(
            r"i ordered an? .+? on amazon on my (mother|sister|brother|father|parent|sibling)'s birthday last year\. "
            r"how much does it cost now, ignoring tax and delivery fees\?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_membership_paid_total":
        if not re.fullmatch(
            r"how much have i paid in (prime|premium) membership since i made the (amazon|spotify) account\?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_membership_last_payment_card_name":
        if not re.fullmatch(
            r"tell me the card name i used for my last (amazon|spotify) (prime|premium) membership payment\?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_membership_remaining_duration":
        if not re.fullmatch(
            r"how many (days|months) of (amazon|spotify) (prime|premium) subscription do i still have left\? round to the nearest number\.?",
            raw,
        ):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_star_threads_by_relationship":
        if not raw.startswith("star all my gmail threads"):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_label_notification_threads_by_app":
        required = [
            "label all email threads in my gmail inbox",
            "notifications@<app>.com",
            "ignore spam and archived",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_relabel_priority_threads":
        required = [
            "relabel all my",
            "email threads with",
            "respectively",
            "remove all",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_attach_job_search_files_and_send":
        required = [
            "for my job search",
            "drafted emails to all potential employers",
            "attach ",
            "from my file system",
            "then send the emails",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_gmail_download_flight_ticket_attachment":
        required = [
            "download the ticket for my flight to ",
            "this weekend from gmail",
            "folder of my file system",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_remove_expired_payment_cards":
        if raw != "remove expired payment cards from all my app accounts that have payment cards.":
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_venmo_change_password":
        if not raw.startswith("change my venmo password to "):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_shared_subscription_password_reset_and_text":
        required = [
            "i share my ",
            " account with my ",
            "having trouble logging in",
            "change its password to ",
            "via phone text message",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_venmo_send_to_named_user_with_optional_signup":
        required = [
            "send $",
            " via venmo",
            "may need to make me an account first",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_venmo_pay_flight_bill_from_email":
        required = [
            "booked a flight for me",
            "my part of the bill",
            "over email",
            "owed amount on venmo",
            "description note",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_venmo_pay_coworkers_and_email":
        required = [
            "to each of my coworkers",
            "privately on venmo",
            "then send an email",
            "all of them in the recipients",
            "the subject",
            "and body",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_spotify_playlist_from_workout_email":
        if "workout partner" not in raw or "spotify playlist" not in raw:
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_spotify_reply_liked_song_recommendations_email":
        required = [
            "asked me for song recommendations over email",
            "liked songs",
            "spotify song library",
            "comma-separated list",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type == "appworld_spotify_update_song_recommendation_draft_from_library":
        required = [
            "asked me for my song recommendations over email",
            "started drafting the response email",
            "mine it from my spotify account",
            "keep the existing format",
            "once done, send the email",
        ]
        if not all(part in raw for part in required):
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type in {
        "appworld_venmo_process_pending_payment_requests",
        "appworld_venmo_approve_roommate_requests_this_month",
    }:
        housing_bill_task = (
            "housing bill" in raw
            and ("rent increase" in raw or "rent decrease" in raw or "corrected amount" in raw)
        )
        carpool_payment_task = "carpooling to work" in raw and "requested money" in raw
        if housing_bill_task or carpool_payment_task:
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    vacation_settlement_task = (
        "went on a trip with friends to" in raw
        and "money i owe to others and others owe me" in raw
        and "make private venmo payments or requests accordingly" in raw
    )
    if vacation_settlement_task:
        repaired = runtime.compile_frame(instruction, instruction, available_tools)
        if repaired is not None:
            return repaired
        return IntentFrame("unsupported")
    if frame.intent_type == "appworld_spotify_download_liked_library_songs":
        offline_playback_task = (
            "without internet" in raw
            and "enough downloaded songs" in raw
            and ("play an album" in raw or "play a playlist" in raw)
        )
        if offline_playback_task:
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
            return IntentFrame("unsupported")
    if frame.intent_type in {
        "appworld_spotify_follow_artists_by_genre_followers",
        "appworld_spotify_follow_playlist_song_artists_by_genre",
    }:
        genre = str(frame.get("genre", "")).strip().lower()
        raw = instruction.lower()
        invalid_genre = genre in {"", "all", "any", "artist", "artists", "song", "songs"}
        liked_song_artist_task = "sung" in raw and "song" in raw and "liked" in raw
        if invalid_genre or liked_song_artist_task:
            repaired = runtime.compile_frame(instruction, instruction, available_tools)
            if repaired is not None:
                return repaired
    return frame


def appworld_intent_system_prompt() -> str:
    return """
You extract a typed intent frame for a runtime-checked AppWorld executor. Return exactly one JSON object and no prose.

Supported JSON format:
{"intent_type":"...", "slots":{...}}

Supported intent types and slots:
1. appworld_phone_message_non_venmo_contacts
   slots: relationships list using singular values from [parent, sibling, roommate, friend, coworker, partner, husband, wife], excluded_app string, message string.
2. appworld_phone_send_message_to_relationship
   slots: relationships list using singular values from [parent, sibling, roommate, friend, coworker, partner, husband, wife], message_kind string, one of text or voice, message string.
3. appworld_phone_reply_favorite_recipe_to_relationship
   slots: relationship string, one of wife, husband, or mother.
4. appworld_splitwise_accept_known_phone_invitations
   slots: message_kind string, one of text or voice; date_window string, one of yesterday, the_day_before_yesterday, or this_week.
5. appworld_venmo_signup_missing_relationship_accounts
   slots: relationships list using singular values from [parent, roommate], password string, message string.
6. appworld_phone_message_app_account_verify_reset
   slots: relationship string, one of son, daughter, or child; password string; date_window string, normally yesterday.
6. appworld_shared_subscription_password_reset_and_text
   slots: app_name string one of amazon or spotify; subscription_name string one of prime or premium; relationships list using singular values from [roommate, sibling]; new_password string.
6. appworld_venmo_change_password
   slots: new_password string.
6. appworld_splitwise_record_venmo_receipt_payments
   slots: note string.
7. appworld_todoist_reassign_accepted_takeover_tasks
   slots: comment_template string containing <person_first_name>.
8. appworld_spotify_apply_todoist_playlist_suggestions
   slots: destination string, relationship_type string one of roommates, siblings, or friends, final_comment string.
9. appworld_spotify_apply_phone_playlist_suggestions
   slots: relationship_type string one of roommates or siblings.
9. appworld_pay_csv_debts_via_venmo_or_splitwise
   slots: csv_file_name string, private boolean.
10. appworld_venmo_send_to_phone_number
   slots: phone_number string, amount number, private boolean.
10. appworld_venmo_send_to_named_user
   slots: person_first_name string, amount number.
10. appworld_venmo_send_to_named_user_with_optional_signup
   slots: person_first_name string, amount number.
10. appworld_venmo_pay_flight_bill_from_email
   slots: person_first_name string, note string.
10. appworld_venmo_pay_coworkers_and_email
   slots: relationships list using singular value [coworker], amount number, note string, email_subject string, email_body string.
10. appworld_venmo_accept_named_carpool_request_this_month
   slots: person_first_name string.
10. appworld_venmo_correct_housing_bill_request
   slots: percent number, adjustment string one of increase or decrease, note string.
10. appworld_venmo_approve_requests_and_withdraw_balance
   slots: date_window string, one of this_month or this_or_the_last_month; card_last4 string.
11. appworld_venmo_request_money_from_contact
   slots: relationships list with one singular value from [friend, roommate], person_first_name string, amount number, private boolean, note string.
11. appworld_venmo_settle_roommate_dinner
   slots: taxi_total number, food_total number, food_payer_first_name string, taxi_note string, food_note string.
12. appworld_venmo_send_to_each_relationship_with_refill
   slots: relationships list using singular values from [roommate, coworker, friend], amount number, note string.
13. appworld_venmo_birthday_child_payment_and_text
   slots: relationship string, one of son or daughter; multiplier number; note string; message string.
14. appworld_venmo_correct_sent_requests_yesterday_evening
   slots: relationships list with one singular value from [friend, roommate]; adjustment string, one of increase or decrease; difference_amount number.
13. appworld_venmo_remind_old_payment_requests
   slots: relationships list using singular values from [roommate, coworker, friend], min_days integer.
14. appworld_venmo_process_pending_payment_requests
   slots: decision string, one of approve or deny, relationships list using singular values from [roommate, coworker, friend].
13. appworld_venmo_add_friends_by_relationships
   slots: relationships list using singular values from [roommate, coworker, friend].
14. appworld_delete_phone_spam_messages
   slots: phone_number string.
14. appworld_phone_update_wake_alarm_snooze
   slots: day_type string, one of weekday or weekend; snooze_minutes integer.
15. appworld_amazon_move_rating_filtered_products
   slots: source_container string, one of cart or wish_list; target_container string, one of cart or wish_list; comparison string, one of under or over; threshold_rating number.
16. appworld_amazon_move_product_type_between_saved_lists
   slots: source_container string, one of cart or wish_list; target_container string, one of cart or wish_list; product_type string.
17. appworld_amazon_order_product_type_from_saved_list
   slots: source_container string, one of cart or wish_list; product_type string; address_name string, default Home; card_name string, optional.
18. appworld_amazon_purchase_phone_recommendation
   slots: recommender_first_name string; product_type string; address_name string, default Home; card_name string, optional.
18. appworld_amazon_text_wishlist_itemized_costs
   slots: relationship string, one of husband, wife, or partner.
18. appworld_amazon_answer_cart_wishlist_total
   slots: empty object.
18. appworld_amazon_order_saved_collections
   slots: containers list using values from [cart, wish_list]; address_name string, one of Home or Work; card_name string, optional.
18. appworld_amazon_cart_buy_cheapest_per_type_move_rest
   slots: address_name string, default Home; card_name string, optional.
18. appworld_amazon_order_exact_products_restore_cart
   slots: items list of objects with product_name string and quantity integer; address_name string, one of Home or Work; preferred_card_name string; restore_cart boolean.
18. appworld_amazon_order_product_and_archive_receipt
   slots: product_name string; quantity integer; address_name string, one of Home or Work; bills_root string, default ~/bills/.
18. appworld_amazon_download_all_order_receipts
   slots: directory_path string ending with /; file_format string exactly as requested.
18. appworld_amazon_order_trip_supplies_by_deadline
   slots: product_types list of two product type strings; quantity integer; trip_day string, saturday or sunday; address_name string, default Home; card_name string, optional.
18. appworld_amazon_return_recent_orders
   slots: order_count integer; deliverer_name string such as FedEx.
18. appworld_amazon_return_same_product_except_size_this_week
   slots: product_name string; keep_size string, one of extra-small, small, medium, large, or extra-large; deliverer_name string such as UPS, USPS, or FedEx.
18. appworld_amazon_buy_last_product_variants
   slots: product_type string, one of t-shirt or sweater; colors list of exactly two color strings; address_name string, default Home; card_name string, optional.
18. appworld_amazon_replace_last_product_adjacent_size
   slots: product_type string; size_direction string, one of larger or smaller; preferred_color string; address_name string, default Home; card_name string, optional.
18. appworld_amazon_order_preferred_color_size_product
   slots: product_name string; relative_size string; color_preferences list in preference order; quantity integer; address_name string, default Home; card_name string, optional.
18. appworld_amazon_order_filtered_product
   slots: product_type string; max_price number or null; min_product_rating number or null; min_product_reviews integer or null; prior_ordered_sellers_only boolean; quantity integer; address_name string, one of Home or Work; card_name string, optional.
18. appworld_amazon_post_question_last_ordered_product
   slots: product_type string; question string.
18. appworld_amazon_update_last_month_order_review
   slots: product_color string; product_type string; target_rating integer from 1 to 5; title string.
18. appworld_amazon_answer_last_order_question_yes_no
   slots: product_type string; question string without the trailing "Say yes or no".
18. appworld_amazon_answer_verified_battery_life_hours
   slots: product_name string.
18. appworld_amazon_answer_returned_product_yes_no
   slots: product_type string; period string, one of this month, this year, or this or last month.
18. appworld_amazon_answer_order_arrival_date
   slots: day_offset integer, 0 for today's order or 1 for yesterday's order; date_format string, one of DD-MM, MM-DD, or DD/MM.
18. appworld_amazon_answer_spending_total
   slots: period string, one of this calendar year, the last calendar month, or this or the last calendar month.
18. appworld_amazon_answer_current_price_from_birthday_order
   slots: product_type string; relationship string, one of mother, sister, brother, parent, sibling, or father.
18. appworld_membership_paid_total
   slots: app_name string, one of amazon or spotify.
18. appworld_membership_last_payment_card_name
   slots: app_name string, one of amazon or spotify.
18. appworld_membership_remaining_duration
   slots: app_name string, one of amazon or spotify; unit string, one of days or months.
18. appworld_delete_gmail_empty_drafts
   slots: condition string, one of both or either.
18. appworld_gmail_send_future_scheduled_drafts_now
   slots: empty object.
18. appworld_gmail_amazon_promo_codes_answer
   slots: empty object.
19. appworld_gmail_count_threads
   slots: mailbox string, one of inbox or outbox; read_state string, one of read or unread; label optional string, one of priority-1, priority-2, or priority-3.
20. appworld_gmail_schedule_resignation_draft
   slots: attachment_path string; weekday string; week_offset integer, 1 for next and 2 for next to next; hour integer in 12-hour morning time.
21. appworld_gmail_thread_cleanup
   slots: action string, one of archive or delete; exception_mode string, one of and or or.
22. appworld_gmail_mark_threads_read_state_by_calendar_window
   slots: target_state string, one of read or unread; window string, one of before_the_last_calendar_month, in_the_current_calendar_month, or before_the_current_calendar_year.
23. appworld_gmail_delete_archived_threads_by_calendar_window
   slots: window string, one of before_this_calendar_month, this_calendar_month, or this_or_the_last_calendar_month.
24. appworld_gmail_forward_anniversary_announcement_email
   slots: recipient_email string.
25. appworld_gmail_forward_caterer_bill_to_manager_with_note
   slots: note_prefix string.
26. appworld_gmail_forward_roommate_bill_to_other_roommates
   slots: file_name PDF attachment base name such as electricity_bill.pdf.
27. appworld_gmail_forward_trip_expenses_thread_with_attachment
   slots: sender_first_name string; recipient_first_name string; attachment_path string under ~/documents/personal/ ending in .pdf; note_prefix string.
28. appworld_gmail_reply_weekly_manager_tasks_by_star_state
   slots: subject_prefix string; done_reply string; not_done_reply string.
29. appworld_gmail_star_threads_by_relationship
   slots: relationship string, singular contact relationship such as manager, coworker, or friend.
30. appworld_gmail_label_notification_threads_by_app
   slots: empty object.
31. appworld_gmail_relabel_priority_threads
   slots: source_label_1 string, source_label_2 string, target_label_1 string, target_label_2 string, remove_label string; labels are one of priority-1, priority-2, priority-3, P1, P2, P3, pr-1, pr-2, or pr-3.
32. appworld_gmail_attach_job_search_files_and_send
   slots: days_back integer; file_name PDF base name such as resume.pdf or cv.pdf.
33. appworld_gmail_download_flight_ticket_attachment
   slots: destination string; directory_path string ending in /.
34. appworld_gmail_email_named_file_to_relationship
   slots: file_description string such as driving license, headshot, or birth certificate; relationship string such as partner, manager, or husband.
35. appworld_remove_expired_payment_cards
   slots: empty object.
18. appworld_bucket_list_status_update
   slots: item string, done boolean.
19. appworld_simple_note_count_bucket_list_status
   slots: status string, one of done or todo.
20. appworld_simple_note_fill_liked_song_release_months
   slots: empty object.
21. appworld_spotify_follow_artists_by_genre_followers
   slots: genre string, min_follower_count integer.
21. appworld_spotify_add_artist_playcount_songs_to_queue
   slots: artist_name string, min_play_count integer.
22. appworld_spotify_like_songs_from_followed_artists
   slots: empty object.
23. appworld_spotify_public_liked_library_playlist_share
   slots: partner_relationship string, one of husband or wife.
24. appworld_spotify_sync_following_by_liked_song_artists
   slots: operation string, one of follow_liked_song_artists or unfollow_non_liked_song_artists.
25. appworld_spotify_playlist_best_song_per_collection
   slots: playlist_title string, song_metric string, one of play_count or rating, collection_type string, one of album_library or playlist_library.
26. appworld_spotify_playlist_from_recent_simple_note
   slots: playlist_title string.
26. appworld_spotify_append_most_common_playlist_genre
   slots: empty object.
27. appworld_spotify_like_all_library_items
   slots: empty object.
27. appworld_spotify_download_liked_library_songs
   slots: collection_type string, one of playlist_library, song_library, or album_library.
28. appworld_spotify_rate_library_songs_by_liked_status
   slots: collection_type string, one of playlist_library, song_library, or album_library; liked_filter string, one of liked or not_liked; target_rating integer from 1 to 5.
29. appworld_spotify_follow_artists_from_liked_songs_and_albums
   slots: empty object.
30. appworld_spotify_follow_playlist_song_artists_by_genre
   slots: genre string.
31. appworld_spotify_top_played_genre_titles
   slots: genre string, limit integer.
32. appworld_spotify_count_unique_library_songs
   slots: empty object.
33. appworld_venmo_pay_grocery_from_text_and_notify
   slots: person_first_name string, note string, message string.
34. appworld_spotify_count_recent_release_library_songs
   slots: years_back integer, include_current_year boolean.
35. appworld_spotify_navigate_until_artist
   slots: direction string, one of previous or next, artist_name string.
36. appworld_venmo_reset_friends_to_phone_friends
   slots: empty object.
37. appworld_spotify_filter_queue_by_liked_status
   slots: remove_filter string, one of liked or not_liked.
38. appworld_spotify_navigate_until_private_status
   slots: direction string, one of previous or next; status_property string, one of liked or downloaded.
38. appworld_spotify_play_offline_downloaded_collection
   slots: collection_type string, one of album or playlist; required_minutes number.
39. appworld_venmo_sum_month_transactions
   slots: direction string, one of sent, received, or sent_or_received.
40. appworld_venmo_sum_recent_received_requests
   slots: days integer.
41. appworld_spotify_reset_queue_with_recommendations
   slots: empty object.
42. appworld_spotify_archive_playlist_songs_from_file
   slots: source_file_path string, playlist_title string.
42. appworld_spotify_playlist_from_workout_email
   slots: playlist_title string.
43. appworld_spotify_reply_liked_song_recommendations_email
   slots: relationship string, singular value from [friend, coworker, roommate]; message_prefix string.
44. appworld_spotify_update_song_recommendation_draft_from_library
   slots: person_first_name string.
43. appworld_simple_note_import_markdown_files
   slots: source_directory string.
44. appworld_simple_note_workout_duration
   slots: day_ref string, one of today, yesterday, or sunday.
45. appworld_simple_note_random_quote
   slots: quote_type string, one of funny, inspirational, or movie.
46. appworld_simple_note_longest_habit_streak
   slots: habit_key string, snake_case habit key from the Simple Note habit tracker.
47. appworld_simple_note_add_today_habit_log
   slots: habit_key string, snake_case habit key from the Simple Note habit tracker; value boolean.
48. appworld_simple_note_export_habit_tracker_csv
   slots: destination_path string ending in .csv; sort_order string, one of ascending or descending.
49. appworld_simple_note_update_monthly_venmo_expense
   slots: empty object.
50. appworld_todoist_fill_today_from_schedule
   slots: target_project_name string.
51. appworld_splitwise_record_trip_expenses_from_simple_note
   slots: relationship_type string, one of friends or coworkers.
52. appworld_venmo_approve_roommate_requests_this_month
   slots: empty object.
53. appworld_file_update_reunion_rsvps_from_phone
   slots: directory_path string, one of ~/documents/personal/, ~/documents/personal_stuff/, or ~/documents/personal_files/.
54. appworld_file_delete_downloads_by_extension
   slots: extension string such as .pdf or .jpg.
55. appworld_spotify_followed_artist_follower_extreme
   slots: extreme string, one of most or least.
56. appworld_spotify_liked_genre_extreme
   slots: collection_type string, one of song_library, album_library, or playlist_library; extreme string, one of most or least.
57. appworld_spotify_playlist_artist_song_count_extreme
   slots: extreme string, one of most or least; limit integer.
58. appworld_venmo_sum_year_bill_payments
   slots: bill_type string, one of phone, electricity, or internet.
59. appworld_venmo_friend_transaction_counterparties
   slots: direction string, one of sent, received, or sent_or_received; sync_mode string, one of add_only or sync.
60. appworld_venmo_count_friends_since_month_start
   slots: month string, one of january, february, march, april, may, june, july, august, september, october, november, december; year_offset integer, 0 for this year and -1 for last year.
61. appworld_spotify_play_released_year_from_collection
   slots: release_year integer; collection_type string, one of song_library, album_library, or playlist_library.
62. appworld_venmo_like_transactions_by_relationship_period
   slots: relationships list using singular values from [roommate, friend, coworker], period string, one of month or year.
63. appworld_venmo_manager_meal_total_from_social_feed
   slots: relationships list using singular values from [coworker], meal string, one of dinner or lunch, venue string, share_amount number.
64. appworld_venmo_sum_transaction_likes
   slots: direction string, one of sent, received, or sent_or_received, period string, one of month or year.
65. appworld_file_prefix_and_move_old_files
   slots: source_directory string, prefix_format string exactly one of YYYY-MM-DD_, YYYY_MM_DD-, or YYYY_MM_DD_, old_destination_directory string.
66. appworld_file_reorganize_dated_meeting_files
   slots: source_directory string.
67. appworld_spotify_current_artist_followers
   slots: empty object.
68. appworld_simple_note_export_markdown
   slots: destination_directory string.

Disambiguation rules:
- Use appworld_spotify_follow_artists_by_genre_followers only when the task explicitly names a music genre and a minimum follower count.
- Never set genre to all, any, artist, or artists. Those are not valid music genres for appworld_spotify_follow_artists_by_genre_followers.
- For tasks about artists who have or have not sung songs the user has liked, always use appworld_spotify_sync_following_by_liked_song_artists, even if the task says "all artists".
- For tasks about following artists of all liked songs and albums, use appworld_spotify_follow_artists_from_liked_songs_and_albums.
- For tasks about following artists of genre-specific songs in the user's playlists, use appworld_spotify_follow_playlist_song_artists_by_genre.
- For tasks about going without internet and playing an album or playlist that already has enough downloaded songs, use appworld_spotify_play_offline_downloaded_collection.
- For tasks about a named person's carpooling-to-work Venmo request this month, use appworld_venmo_accept_named_carpool_request_this_month; do not map it to generic all-pending request approval.
- For housing-bill or rent-correction Venmo tasks, use appworld_venmo_correct_housing_bill_request; do not map it to generic pending-request approval.
- For a child birthday task that asks to Venmo a son or daughter a multiple of the last birthday payment and then text them, use appworld_venmo_birthday_child_payment_and_text.
- For tasks that ask to delete sent Venmo payment requests from yesterday evening and recreate them with a fixed corrected amount, use appworld_venmo_correct_sent_requests_yesterday_evening.
- For roadtrip Spotify playlist suggestions shared and replied to on phone messages, use appworld_spotify_apply_phone_playlist_suggestions, not the Todoist playlist-suggestion machine.
- For roommate dinner tasks where the user paid taxi/commute and a named roommate paid food, use appworld_venmo_settle_roommate_dinner.

Examples:
Task: Send the following phone message to my parents and siblings, who do not have a venmo account, "Please get on venmo.".
JSON: {"intent_type":"appworld_phone_message_non_venmo_contacts","slots":{"relationships":["parent","sibling"],"excluded_app":"venmo","message":"Please get on venmo."}}

Task: Send a phone voice message to my all roommates, "I have taken out the trash.".
JSON: {"intent_type":"appworld_phone_send_message_to_relationship","slots":{"relationships":["roommate"],"message_kind":"voice","message":"I have taken out the trash."}}

Task: Send a phone text message to my partner, "The dishwasher is clean and ready to be emptied.".
JSON: {"intent_type":"appworld_phone_send_message_to_relationship","slots":{"relationships":["partner"],"message_kind":"text","message":"The dishwasher is clean and ready to be emptied."}}

Task: I got some Splitwise group invitations over phone voice messages the day before yesterday. If their number is in my phone contact book, accept it, otherwise delete those messages.
JSON: {"intent_type":"appworld_splitwise_accept_known_phone_invitations","slots":{"message_kind":"voice","date_window":"the_day_before_yesterday"}}

Task: I need my roommates to have a venmo account. Last time I checked none had one. Make an account for whoever that does not have it yet, using their email address and -kO6&A as password. Then send them a phone text message, "I made an account on venmo for you. You should have received an email for activation. Please do it soon. The temporary password is -kO6&A. Change it too.".
JSON: {"intent_type":"appworld_venmo_signup_missing_relationship_accounts","slots":{"relationships":["roommate"],"password":"-kO6&A","message":"I made an account on venmo for you. You should have received an email for activation. Please do it soon. The temporary password is -kO6&A. Change it too."}}

Task: My son sent me a message yesterday on phone about an app account creation. Please do as per his message. Use password UEHA7Gv for the new account.
JSON: {"intent_type":"appworld_phone_message_app_account_verify_reset","slots":{"relationship":"son","password":"UEHA7Gv","date_window":"yesterday"}}

Task: I share my spotify premium account with my siblings. I am having trouble logging in. Change its password to +68qUnL and share it with them via phone text message.
JSON: {"intent_type":"appworld_shared_subscription_password_reset_and_text","slots":{"app_name":"spotify","subscription_name":"premium","relationships":["sibling"],"new_password":"+68qUnL"}}

Task: Change my venmo password to aQAdQp
JSON: {"intent_type":"appworld_venmo_change_password","slots":{"new_password":"aQAdQp"}}

Task: Send $73 to Troy via Venmo. You may need to make me an account first, if I do not have one.
JSON: {"intent_type":"appworld_venmo_send_to_named_user_with_optional_signup","slots":{"person_first_name":"Troy","amount":73}}

Task: I owed people some money. They put the associated expenses on Splitwise yesterday. I paid some of them up on Venmo today. Please record payments on Splitwise for each in their respective groups. Each payment should have a note, "Sent on Venmo, see receipt.", and an attached Venmo receipt of it as a proof.
JSON: {"intent_type":"appworld_splitwise_record_venmo_receipt_payments","slots":{"note":"Sent on Venmo, see receipt."}}

Task: At my job, we manage the tasks on todoist. But I am changing job soon, so for each task that is assigned to me and is incomplete yet, I have asked who can take it from me. See the discussion in comments and reassign based on it. Then, leave a comment there, "Thanks <person_first_name>!". Here <person_first_name> is the first name of the person who is reassigned the task. If no one has agreed to take the task, leave it as is.
JSON: {"intent_type":"appworld_todoist_reassign_accepted_takeover_tasks","slots":{"comment_template":"Thanks <person_first_name>!"}}

Task: I am going on a trip to Beijing with some of my roommates. We are managing its planning on a Todoist project for it. One of the tasks in it is about preparing a Spotify playlist. I have made the playlist and shared it with others on the project. But they have made some suggestions in comments. Please incorporate them, leave a final comment, "Incorporated changes.", and mark it complete.
JSON: {"intent_type":"appworld_spotify_apply_todoist_playlist_suggestions","slots":{"destination":"Beijing","relationship_type":"roommates","final_comment":"Incorporated changes."}}

Task: I am going on a trip to Edinburgh with some of my siblings. We are managing its planning on a Todoist project for it. One of the tasks in it is about preparing a Spotify playlist. I have made the playlist and shared it with others on the project. But they have made some suggestions in comments. Please incorporate them, leave a final comment, "Done!", and mark it complete.
JSON: {"intent_type":"appworld_spotify_apply_todoist_playlist_suggestions","slots":{"destination":"Edinburgh","relationship_type":"siblings","final_comment":"Done!"}}

Task: My roommates and I are preparing a playlist for a roadtrip together. I prepared the initial playlist on Spotify and shared it with them on phone messages. They have replied with suggested changes. Please update this playlist accordingly.
JSON: {"intent_type":"appworld_spotify_apply_phone_playlist_suggestions","slots":{"relationship_type":"roommates"}}

Task: My siblings and I are preparing a playlist for a roadtrip together. I prepared the initial playlist on Spotify and shared it with them on phone messages. They have replied with suggested changes. Please update this playlist accordingly.
JSON: {"intent_type":"appworld_spotify_apply_phone_playlist_suggestions","slots":{"relationship_type":"siblings"}}

Task: My workout partner has sent me some songs over email. Make a new Spotify playlist titled "Workout Playlist" with those songs in it.
JSON: {"intent_type":"appworld_spotify_playlist_from_workout_email","slots":{"playlist_title":"Workout Playlist"}}

Task: One of my coworkers has asked me for song recommendations over email. Reply them with a list of my liked songs that are in my Spotify song library. It should say "Sure! These are my favorite songs." and then a comma-separated list of song titles.
JSON: {"intent_type":"appworld_spotify_reply_liked_song_recommendations_email","slots":{"relationship":"coworker","message_prefix":"Sure! These are my favorite songs."}}

Task: Angelica asked me for my song recommendations over email. I started drafting the response email off the top of my head. But then realized I can mine it from my Spotify account! Please update the email draft with all of my liked songs that are in my song or album library or any of my plalists. Keep the existing format of the email, making changes only to the song entries. Once done, send the email.
JSON: {"intent_type":"appworld_spotify_update_song_recommendation_draft_from_library","slots":{"person_first_name":"Angelica"}}

Task: I have a list of people I owe money to, including amounts and descriptions, in owe_list.csv. For each person, (1) If they have a Venmo account, send the money privately with the specified amount and description. (2) If not, create an individual (non-grouped) Splitwise expense with the same details so I remember to pay them later. For Splitwise expenses, attach the PDF receipt as well. They are in the same folder as the CSV file.
JSON: {"intent_type":"appworld_pay_csv_debts_via_venmo_or_splitwise","slots":{"csv_file_name":"owe_list.csv","private":true}}

Task: I have a list of people I owe money to, including amounts and descriptions, in debt_list.csv. For each person, (1) If they have a Venmo account, send the money publicly with the specified amount and description. (2) If not, create an individual (non-grouped) Splitwise expense with the same details so I remember to pay them later. For Splitwise expenses, attach the PDF receipt as well. They are in the same folder as the CSV file.
JSON: {"intent_type":"appworld_pay_csv_debts_via_venmo_or_splitwise","slots":{"csv_file_name":"debt_list.csv","private":false}}

Task: I maintain my work schedule in SimpleNote and track my tasks in Todoist. Every night, I delete the completed tasks from my "Today's Goal" project. Then, I move the maximum number of incomplete tasks from my Inbox to the "Today's Goal" project. The maximum here is assuming I work back-to-back as per my schedule and I find time for the left overs from the current day first. I am busy tonight, please do it for me. Note that the moved tasks must be identical to the original ones.
JSON: {"intent_type":"appworld_todoist_fill_today_from_schedule","slots":{"target_project_name":"Today's Goal"}}

Task: Send $91 privately on Venmo to the person with this phone number 2192158297.
JSON: {"intent_type":"appworld_venmo_send_to_phone_number","slots":{"phone_number":"2192158297","amount":91,"private":true}}

Task: Send $250 on venmo to Catherine.
JSON: {"intent_type":"appworld_venmo_send_to_named_user","slots":{"person_first_name":"Catherine","amount":250}}

Task: Connor booked a flight for me. They have sent me my part of the bill recently over email. Send them the owed amount on venmo with a description note, "For flight ticket.".
JSON: {"intent_type":"appworld_venmo_pay_flight_bill_from_email","slots":{"person_first_name":"Connor","note":"For flight ticket."}}

Task: Send $100 to each of my coworkers privately on venmo with a note
"Thank you for the extra hard work during the sprint!". Then send an email with all of them in the recipients with
the subject, "Successful Sprint Completion", and body "I've sent all of you a small gift on venmo for the hard work you put in our sprint. Great work!"
JSON: {"intent_type":"appworld_venmo_pay_coworkers_and_email","slots":{"relationships":["coworker"],"amount":100,"note":"Thank you for the extra hard work during the sprint!","email_subject":"Successful Sprint Completion","email_body":"I've sent all of you a small gift on venmo for the hard work you put in our sprint. Great work!"}}

Task: Chelsea and I have been carpooling to work this month. They have requested money for it on venmo. Accept it.
JSON: {"intent_type":"appworld_venmo_accept_named_carpool_request_this_month","slots":{"person_first_name":"Chelsea"}}

Task: My roommate requested me to pay for my share of the housing bill this month on venmo today. But they forgot about the 5% rent increase starting this month. So reject that payment request and send them the corrected amount of money with a note, "You forgot about the 5% increase!".
JSON: {"intent_type":"appworld_venmo_correct_housing_bill_request","slots":{"percent":5,"adjustment":"increase","note":"You forgot about the 5% increase!"}}

Task: Approve all pending venmo payment requests I have received in this or the last month, and withdraw the remaining venmo balance, if any, to my card ending in 1102.
JSON: {"intent_type":"appworld_venmo_approve_requests_and_withdraw_balance","slots":{"date_window":"this_or_the_last_month","card_last4":"1102"}}

Task: Request $28 privately on Venmo from my roommate, Melissa, with a note, "For the movie tickets".
JSON: {"intent_type":"appworld_venmo_request_money_from_contact","slots":{"relationships":["roommate"],"person_first_name":"Melissa","amount":28,"private":true,"note":"For the movie tickets"}}

Task: I went on a trip with friends to Maui recently. I have maintained a note of money I owe to others and others owe me from the trip in simple note. Make private venmo payments or requests accordingly. In the payments/requests, add a note, "For Maui trip".
JSON: {"intent_type":"appworld_venmo_settle_trip_note_debts","slots":{"relationship":"friend","trip_name":"Maui","note":"For Maui trip"}}

Task: My roommates and I went for a dinner yesterday. I paid for the taxi back and forth (total $60) and Nancy paid for everyone's food (total $128). Both food and commute are supposed to be shared equally among all. Make necessary payment requests with a note "For Taxi", and a payment to Nancy with a note "For Food", on venmo.
JSON: {"intent_type":"appworld_venmo_settle_roommate_dinner","slots":{"taxi_total":60,"food_total":128,"food_payer_first_name":"Nancy","taxi_note":"For Taxi","food_note":"For Food"}}

Task: Send $30 to each of my roommates via venmo with a note, "For Drinks". Refill venmo balance if you need to.
JSON: {"intent_type":"appworld_venmo_send_to_each_relationship_with_refill","slots":{"relationships":["roommate"],"amount":30,"note":"For Drinks"}}

Task: Today is my son's birthday. Venmo him twice the money I sent him on his last birthday, privately, with a description note, "Happy Birthday". Then leave him a phone text message, "Happy Birthday son! Give a call when you are free.".
JSON: {"intent_type":"appworld_venmo_birthday_child_payment_and_text","slots":{"relationship":"son","multiplier":2,"note":"Happy Birthday","message":"Happy Birthday son! Give a call when you are free."}}

Task: I made venmo payment requests to some of my friends yesterday evening. Unfortunately, I have made a mistake in calculation. Each of them owes me $5 less than the requested amount. So delete those requests and make new ones with everything else the same, but with the corrected amount.
JSON: {"intent_type":"appworld_venmo_correct_sent_requests_yesterday_evening","slots":{"relationships":["friend"],"adjustment":"decrease","difference_amount":5}}

Task: Send a reminder on Venmo for all my payment requests to my roommates which have not been approved or denied for 30 or more days.
JSON: {"intent_type":"appworld_venmo_remind_old_payment_requests","slots":{"relationships":["roommate"],"min_days":30}}

Task: Accept all pending Venmo payment requests from my roommates and coworkers.
JSON: {"intent_type":"appworld_venmo_process_pending_payment_requests","slots":{"decision":"approve","relationships":["roommate","coworker"]}}

Task: Reject all pending Venmo payment requests from my friends and roommates.
JSON: {"intent_type":"appworld_venmo_process_pending_payment_requests","slots":{"decision":"deny","relationships":["friend","roommate"]}}

Task: Add all my coworkers and roommates as friends on venmo, if they are not already.
JSON: {"intent_type":"appworld_venmo_add_friends_by_relationships","slots":{"relationships":["coworker","roommate"]}}

Task: All phone text messages and voice messages from 3654328626 are spam, delete them.
JSON: {"intent_type":"appworld_delete_phone_spam_messages","slots":{"phone_number":"3654328626"}}

Task: Set my weekday wake up alarm snooze to 5 minutes.
JSON: {"intent_type":"appworld_phone_update_wake_alarm_snooze","slots":{"day_type":"weekday","snooze_minutes":5}}

Task: Set my weekend wake up alarm snooze to 15 minutes.
JSON: {"intent_type":"appworld_phone_update_wake_alarm_snooze","slots":{"day_type":"weekend","snooze_minutes":15}}

Task: Move all products with under 4.2 rating from my amazon cart to wish list.
JSON: {"intent_type":"appworld_amazon_move_rating_filtered_products","slots":{"source_container":"cart","target_container":"wish_list","comparison":"under","threshold_rating":4.2}}

Task: Move all products with over 3.7 rating from my amazon wish list to cart.
JSON: {"intent_type":"appworld_amazon_move_rating_filtered_products","slots":{"source_container":"wish_list","target_container":"cart","comparison":"over","threshold_rating":3.7}}

Task: Move all food processors from my amazon cart to wish list.
JSON: {"intent_type":"appworld_amazon_move_product_type_between_saved_lists","slots":{"source_container":"cart","target_container":"wish_list","product_type":"food processor"}}

Task: Place an order for all weightlifting benches in my amazon cart.
JSON: {"intent_type":"appworld_amazon_order_product_type_from_saved_list","slots":{"source_container":"cart","product_type":"weightlifting bench","address_name":"Home","card_name":""}}

Task: Place an order for all wrench sets in my amazon wish list.
JSON: {"intent_type":"appworld_amazon_order_product_type_from_saved_list","slots":{"source_container":"wish_list","product_type":"wrench set","address_name":"Home","card_name":""}}

Task: Buy me a stand mixer as Connor recommended in their phone message.
JSON: {"intent_type":"appworld_amazon_purchase_phone_recommendation","slots":{"recommender_first_name":"Connor","product_type":"stand mixer","address_name":"Home","card_name":""}}

Task: Send an itemized list of my amazon wish list to my husband via a phone text. The message should be a newline-separated list of '<product_name> => $<total_price>'. Replace <total_price> with the price of the product times its quantity in the wish list, rounded to the nearest whole number, and <product_name> with the product name. Ignore potential tax or delivery fees.
JSON: {"intent_type":"appworld_amazon_text_wishlist_itemized_costs","slots":{"relationship":"husband"}}

Task: How much does my amazon cart and wishlist cost in total, ignoring potential tax and delivery fees?
JSON: {"intent_type":"appworld_amazon_answer_cart_wishlist_total","slots":{}}

Task: Buy everything on my amazon wishlist, and have it delivered to my work address.
JSON: {"intent_type":"appworld_amazon_order_saved_collections","slots":{"containers":["wish_list"],"address_name":"Work","card_name":""}}

Task: Place an order for everything in my amazon cart and wishlist for my home address.
JSON: {"intent_type":"appworld_amazon_order_saved_collections","slots":{"containers":["cart","wish_list"],"address_name":"Home","card_name":""}}

Task: I have a few things in my amazon cart. For each product type in it, buy the cheapest product and move the rest to the wish list.
JSON: {"intent_type":"appworld_amazon_cart_buy_cheapest_per_type_move_rest","slots":{"address_name":"Home","card_name":""}}

Task: Place an amazon order for 1 quantity of 'Sony PlayStation 5', 1 quantity of 'Etekcity Food Kitchen Scale' and 1 quantity of 'Xbox Series S Console', and have it delivered to my home. Use Discover payment card if it's already in my account, otherwise use what I have in it. Also, I have important things in my cart, so revert its state to as it is now after the order.
JSON: {"intent_type":"appworld_amazon_order_exact_products_restore_cart","slots":{"items":[{"product_name":"Sony PlayStation 5","quantity":1},{"product_name":"Etekcity Food Kitchen Scale","quantity":1},{"product_name":"Xbox Series S Console","quantity":1}],"address_name":"Home","preferred_card_name":"Discover","restore_cart":true}}

Task: Order one Apple Watch Series 7 on Amazon for home delivery. Save the receipt in the "~/bills/" folder. I keep my receipts well-organized by category in that folder. So make sure the file location and name are as per the existing organization.
JSON: {"intent_type":"appworld_amazon_order_product_and_archive_receipt","slots":{"product_name":"Apple Watch Series 7","quantity":1,"address_name":"Home","bills_root":"~/bills/"}}

Task: Download receipts of all my amazon orders in "~/bills/shopping_amazon/" folder in my file system. Name the files in the format, "ordered-at-yyyy-mm-dd-order-id-<order_id>.txt". Replace <order_id> with the actual order id, and yyyy-mm-dd with the date when the order was placed. You should be able to find receipts from order confirmation emails.
JSON: {"intent_type":"appworld_amazon_download_all_order_receipts","slots":{"directory_path":"~/bills/shopping_amazon/","file_format":"ordered-at-yyyy-mm-dd-order-id-<order_id>.txt"}}

Task: I am going on a trip with friends this Saturday. For it, I need 3 kites and sleeping pads, each. Place an amazon order for them, making sure everything reaches my home by the end of the day before I leave.
JSON: {"intent_type":"appworld_amazon_order_trip_supplies_by_deadline","slots":{"product_types":["kite","sleeping pad"],"quantity":3,"trip_day":"saturday","address_name":"Home","card_name":""}}

Task: Initiate returns via FedEx for everything in my last 3 amazon order.
JSON: {"intent_type":"appworld_amazon_return_recent_orders","slots":{"order_count":3,"deliverer_name":"FedEx"}}

Task: I bought a few Hanes Men's Tagless Crewneck Undershirts on amazon this week. But only the one in extra-large size fits me well. Initiate a return for the rest. Prefer UPS as a deliverer, if available.
JSON: {"intent_type":"appworld_amazon_return_same_product_except_size_this_week","slots":{"product_name":"Hanes Men's Tagless Crewneck Undershirts","keep_size":"extra-large","deliverer_name":"UPS"}}

Task: I liked that last t-shirt I bought on amazon. Place a new order for the same in navy blue and black, one each. Make sure to get the size as per that order, and have them delivered home.
JSON: {"intent_type":"appworld_amazon_buy_last_product_variants","slots":{"product_type":"t-shirt","colors":["navy blue","black"],"address_name":"Home","card_name":""}}

Task: The last t-shirt I bought on Amazon is a bit too small for me. Initiate a return for it, and buy a replacement of the same in the next larger size. If it's available now in white, prefer it, otherwise go with the same color.
JSON: {"intent_type":"appworld_amazon_replace_last_product_adjacent_size","slots":{"product_type":"t-shirt","size_direction":"larger","preferred_color":"white","address_name":"Home","card_name":""}}

Task: Make an order for two same-colored Hanes Men's ComfortSoft Short Sleeve T-Shirt in extra-large size on Amazon. My color preference is, red > black > navy blue. Pick the most preferred color that is available.
JSON: {"intent_type":"appworld_amazon_order_preferred_color_size_product","slots":{"product_name":"Hanes Men's ComfortSoft Short Sleeve T-Shirt","relative_size":"extra-large","color_preferences":["red","black","navy blue"],"quantity":2,"address_name":"Home","card_name":""}}

Task: Buy me a kitchen timer on amazon within $10 (excluding tax) and have it delivered to my home address.
JSON: {"intent_type":"appworld_amazon_order_filtered_product","slots":{"product_type":"kitchen timer","max_price":10,"min_product_rating":null,"min_product_reviews":null,"quantity":1,"address_name":"Home","card_name":""}}

Task: Buy me a cutting board from amazon within $30 (excluding tax). Only trust sellers I have ordered from in the past.
JSON: {"intent_type":"appworld_amazon_order_filtered_product","slots":{"product_type":"cutting board","max_price":30,"min_product_rating":null,"min_product_reviews":null,"prior_ordered_sellers_only":true,"quantity":1,"address_name":"Home","card_name":""}}

Task: Buy me a board game on amazon under $20 (excluding tax), over 3.9 rating, and over 4 reviews, and have it delivered to home address.
JSON: {"intent_type":"appworld_amazon_order_filtered_product","slots":{"product_type":"board game","max_price":20,"min_product_rating":3.9,"min_product_reviews":4,"quantity":1,"address_name":"Home","card_name":""}}

Task: Buy me a extension cord on amazon with a rating over 4.5 and have it delivered to my home address.
JSON: {"intent_type":"appworld_amazon_order_filtered_product","slots":{"product_type":"extension cord","max_price":null,"min_product_rating":4.5,"min_product_reviews":null,"quantity":1,"address_name":"Home","card_name":""}}

Task: Post a question about the last t-shirt I ordered on amazon, "Has anyone experienced the color fade after the first wash?".
JSON: {"intent_type":"appworld_amazon_post_question_last_ordered_product","slots":{"product_type":"t-shirt","question":"Has anyone experienced the color fade after the first wash?"}}

Task: Change my amazon review about the grey t-shirt I ordered last calendar month. Make it 1 star with the title "Shrunk and Misshaped After First Wash!".
JSON: {"intent_type":"appworld_amazon_update_last_month_order_review","slots":{"product_color":"grey","product_type":"t-shirt","target_rating":1,"title":"Shrunk and Misshaped After First Wash!"}}

Task: Based on the question I posted about my last t-shirt order on amazon, has anyone experienced color fading after the first wash? Say yes or no.
JSON: {"intent_type":"appworld_amazon_answer_last_order_question_yes_no","slots":{"product_type":"t-shirt","question":"has anyone experienced color fading after the first wash"}}

Task: How many hours does the battery of HP Pavilion 15 Laptop last? Please answer as per its amazon reviews or questions/answers and and only trust information from its verified purchasers.
JSON: {"intent_type":"appworld_amazon_answer_verified_battery_life_hours","slots":{"product_name":"HP Pavilion 15 Laptop"}}

Task: Have I returned any office desk on amazon in this month? Say yes or no.
JSON: {"intent_type":"appworld_amazon_answer_returned_product_yes_no","slots":{"product_type":"office desk","period":"this month"}}

Task: By when should everything from my yesterday's amazon order arrive? Tell me the date in DD-MM format.
JSON: {"intent_type":"appworld_amazon_answer_order_arrival_date","slots":{"day_offset":1,"date_format":"DD-MM"}}

Task: How much did I spend on amazon in this calendar year?
JSON: {"intent_type":"appworld_amazon_answer_spending_total","slots":{"period":"this calendar year"}}

Task: I ordered a drone on amazon on my mother's birthday last year. How much does it cost now, ignoring tax and delivery fees?
JSON: {"intent_type":"appworld_amazon_answer_current_price_from_birthday_order","slots":{"product_type":"drone","relationship":"mother"}}

Task: How much have I paid in premium membership since I made the spotify account?
JSON: {"intent_type":"appworld_membership_paid_total","slots":{"app_name":"spotify"}}

Task: Tell me the card name I used for my last amazon prime membership payment?
JSON: {"intent_type":"appworld_membership_last_payment_card_name","slots":{"app_name":"amazon"}}

Task: How many months of amazon prime subscription do I still have left? Round to the nearest number.
JSON: {"intent_type":"appworld_membership_remaining_duration","slots":{"app_name":"amazon","unit":"months"}}

Task: Delete all my Gmail drafts that have empty subject and body.
JSON: {"intent_type":"appworld_delete_gmail_empty_drafts","slots":{"condition":"both"}}

Task: Delete all my Gmail drafts that have empty subject or body.
JSON: {"intent_type":"appworld_delete_gmail_empty_drafts","slots":{"condition":"either"}}

Task: Send all my future-scheduled emails on Gmail right away.
JSON: {"intent_type":"appworld_gmail_send_future_scheduled_drafts_now","slots":{}}

Task: Find all Amazon promo codes from my Gmail account, including spam and archived emails, and give it to me in a comma-separated list.
JSON: {"intent_type":"appworld_gmail_amazon_promo_codes_answer","slots":{}}

Task: How many unread email threads are in my Gmail inbox?
JSON: {"intent_type":"appworld_gmail_count_threads","slots":{"mailbox":"inbox","read_state":"unread","label":""}}

Task: How many priority-2 read email threads are in my Gmail inbox?
JSON: {"intent_type":"appworld_gmail_count_threads","slots":{"mailbox":"inbox","read_state":"read","label":"priority-2"}}

Task: I have drafted my resignation email on Gmail. Attach "~/documents/work/resignation.pdf" from my file system to it and schedule it to be sent to my manager on next Monday at 9 am.
JSON: {"intent_type":"appworld_gmail_schedule_resignation_draft","slots":{"attachment_path":"~/documents/work/resignation.pdf","weekday":"monday","week_offset":1,"hour":9}}

Task: Archive all my read Gmail threads from inbox/outbox, except the ones that have some priority label or are starred.
JSON: {"intent_type":"appworld_gmail_thread_cleanup","slots":{"action":"archive","exception_mode":"or"}}

Task: Delete all my read Gmail threads from inbox/outbox, except the ones that have some priority label and are also starred.
JSON: {"intent_type":"appworld_gmail_thread_cleanup","slots":{"action":"delete","exception_mode":"and"}}

Task: Delete all my read Gmail threads from inbox/outbox, except the ones that have some priority label or are starred.
JSON: {"intent_type":"appworld_gmail_thread_cleanup","slots":{"action":"delete","exception_mode":"or"}}

Task: Mark everything in my Gmail inbox and outbox before the last calendar month as read.
JSON: {"intent_type":"appworld_gmail_mark_threads_read_state_by_calendar_window","slots":{"target_state":"read","window":"before_the_last_calendar_month"}}

Task: Delete all my archived gmail threads that are from before this calendar month.
JSON: {"intent_type":"appworld_gmail_delete_archived_threads_by_calendar_window","slots":{"window":"before_this_calendar_month"}}

Task: I just made an announcement about our company's anniversary celebration but I forgot br_ritt@gmail.com. Please forward the announcement email (not the entire thread) to them.
JSON: {"intent_type":"appworld_gmail_forward_anniversary_announcement_email","slots":{"recipient_email":"br_ritt@gmail.com"}}

Task: I helped organize my company celebration recently. The caterers have emailed me the bill. Forward it to my manager with a note prefixed to its body, "Bill for our last celebration.".
JSON: {"intent_type":"appworld_gmail_forward_caterer_bill_to_manager_with_note","slots":{"note_prefix":"Bill for our last celebration."}}

Task: My roommate sent me "internet_bill.pdf" on Gmail sometime ago. Please find it and forward that email to the rest of my roommates in a single email.
JSON: {"intent_type":"appworld_gmail_forward_roommate_bill_to_other_roommates","slots":{"file_name":"internet_bill.pdf"}}

Task: Denise, Glenn and I went on a trip recently. Yesterday, Denise emailed me their expenses in a pdf. Forward that thread to Glenn with an additional attachment of "~/documents/personal/expenses_james.pdf" from my file system, and a note prefixed to its body, "Can you please take care of splitting expenses? PFA for both of our expenses.".
JSON: {"intent_type":"appworld_gmail_forward_trip_expenses_thread_with_attachment","slots":{"sender_first_name":"Denise","recipient_first_name":"Glenn","attachment_path":"~/documents/personal/expenses_james.pdf","note_prefix":"Can you please take care of splitting expenses? PFA for both of our expenses."}}

Task: My manager assigns me tasks at the beginning of every week with a subject starting with "TODO". At the end of each week, I reply to them "Done." or "Not Done.". For this week, I have starred the emails/tasks which I finished working on, and left the others unstarred. I am closing off this week now, please reply accordingly, and unstar those threads. I may have non-todo emails starred, please keep them as is.
JSON: {"intent_type":"appworld_gmail_reply_weekly_manager_tasks_by_star_state","slots":{"subject_prefix":"TODO","done_reply":"Done.","not_done_reply":"Not Done."}}

Task: Label all email threads in my Gmail inbox from notifications@<app>.com with the label of the respective app. Ignore spam and archived ones.
JSON: {"intent_type":"appworld_gmail_label_notification_threads_by_app","slots":{}}

Task: Relabel all my priority-1 and priority-2 email threads with P1 and P2, respectively, and remove all priority-3 labels.
JSON: {"intent_type":"appworld_gmail_relabel_priority_threads","slots":{"source_label_1":"priority-1","source_label_2":"priority-2","target_label_1":"P1","target_label_2":"P2","remove_label":"priority-3"}}

Task: For my job search, I've drafted emails to all potential employers in the last 3 days. Attach cv.pdf from my file system to each of them. If it's already attached, update it as I just made some changes to it. Then send the emails.
JSON: {"intent_type":"appworld_gmail_attach_job_search_files_and_send","slots":{"days_back":3,"file_name":"cv.pdf"}}

Task: Download the ticket for my flight to Tokyo this weekend from gmail into the "~/downloads" folder of my file system.
JSON: {"intent_type":"appworld_gmail_download_flight_ticket_attachment","slots":{"destination":"Tokyo","directory_path":"~/downloads/"}}

Task: Email the driving license found in my file system to my partner.
JSON: {"intent_type":"appworld_gmail_email_named_file_to_relationship","slots":{"file_description":"driving license","relationship":"partner"}}

Task: Mark "Learning to cook a signature dish from scratch" in my Bucket List Simple Note as done.
JSON: {"intent_type":"appworld_bucket_list_status_update","slots":{"item":"Learning to cook a signature dish from scratch","done":true}}

Task: How many activities are completed in my bucket list as per my SimpleNote note?
JSON: {"intent_type":"appworld_simple_note_count_bucket_list_status","slots":{"status":"done"}}

Task: How many activities are left to do in my bucket list as per my SimpleNote note?
JSON: {"intent_type":"appworld_simple_note_count_bucket_list_status","slots":{"status":"todo"}}

Task: I keep a log of all my liked songs and respective artists in a note in simple_note. I want to add release month information for them as well. I have added it for the first few songs. Add it for the rest.
JSON: {"intent_type":"appworld_simple_note_fill_liked_song_release_months","slots":{}}

Task: Follow all the classical artists on Spotify that have at least 22 followers.
JSON: {"intent_type":"appworld_spotify_follow_artists_by_genre_followers","slots":{"genre":"classical","min_follower_count":22}}

Task: Add all the songs from Lily Moon that have been played over 980 times to my Spotify player queue.
JSON: {"intent_type":"appworld_spotify_add_artist_playcount_songs_to_queue","slots":{"artist_name":"Lily Moon","min_play_count":980}}

Task: Add all the songs from Aria Sterling that have been played over 990 times to my Spotify player queue.
JSON: {"intent_type":"appworld_spotify_add_artist_playcount_songs_to_queue","slots":{"artist_name":"Aria Sterling","min_play_count":990}}

Task: Like all the songs from the artists I follow on Spotify.
JSON: {"intent_type":"appworld_spotify_like_songs_from_followed_artists","slots":{}}

Task: Make a new public playlist from all my liked songs from my Spotify song, album and playlist libraries, and share its URL with my wife via phone text message.
JSON: {"intent_type":"appworld_spotify_public_liked_library_playlist_share","slots":{"partner_relationship":"wife"}}

Task: Make a new public playlist from all my liked songs from my Spotify song, album and playlist libraries, and share its URL with my husband via phone text message.
JSON: {"intent_type":"appworld_spotify_public_liked_library_playlist_share","slots":{"partner_relationship":"husband"}}

Task: Follow all the artists who have sung at least one song I have liked on Spotify.
JSON: {"intent_type":"appworld_spotify_sync_following_by_liked_song_artists","slots":{"operation":"follow_liked_song_artists"}}

Task: Unfollow all the artists who have not sung even a single song I have liked on Spotify.
JSON: {"intent_type":"appworld_spotify_sync_following_by_liked_song_artists","slots":{"operation":"unfollow_non_liked_song_artists"}}

Task: Make me a Spotify playlist called "My Highest Rated Playlist Songs" containing only the highest-rated song from each of my playlists.
JSON: {"intent_type":"appworld_spotify_playlist_best_song_per_collection","slots":{"playlist_title":"My Highest Rated Playlist Songs","song_metric":"rating","collection_type":"playlist_library"}}

Task: Make me a Spotify playlist called "My Most Played Album Songs" containing only the most-played song from each album in my album library.
JSON: {"intent_type":"appworld_spotify_playlist_best_song_per_collection","slots":{"playlist_title":"My Most Played Album Songs","song_metric":"play_count","collection_type":"album_library"}}

Task: I jotted down some songs in Simple Note recently. Make a playlist titled "Songs from Simple Note" out of it.
JSON: {"intent_type":"appworld_spotify_playlist_from_recent_simple_note","slots":{"playlist_title":"Songs from Simple Note"}}

Task: Update all my Spotify playlist titles with the most common song genre in that playlist in this format: "<original_title> | <most_common_genre>". Replace <original_title> and <most_common_genre> with the actual values.
JSON: {"intent_type":"appworld_spotify_append_most_common_playlist_genre","slots":{}}

Task: Like all the songs and albums in my Spotify song and album library, respectively, that I have not liked yet.
JSON: {"intent_type":"appworld_spotify_like_all_library_items","slots":{}}

Task: Download all the songs from my Spotify playlists that I have liked.
JSON: {"intent_type":"appworld_spotify_download_liked_library_songs","slots":{"collection_type":"playlist_library"}}

Task: Download all the songs from my Spotify song library that I have liked.
JSON: {"intent_type":"appworld_spotify_download_liked_library_songs","slots":{"collection_type":"song_library"}}

Task: Download all the songs from my Spotify album library that I have liked.
JSON: {"intent_type":"appworld_spotify_download_liked_library_songs","slots":{"collection_type":"album_library"}}

Task: I am going for a 15-minute drive without internet. Play an album from my Spotify library that already has enough downloaded songs for it, so I do not have to repeat.
JSON: {"intent_type":"unsupported","slots":{}}

Task: Give a 5-star rating to all songs in my Spotify playlists which I have liked. If I have already rated it lower, increase it to 5.
JSON: {"intent_type":"appworld_spotify_rate_library_songs_by_liked_status","slots":{"collection_type":"playlist_library","liked_filter":"liked","target_rating":5}}

Task: Give a 1-star rating to all songs in my Spotify song library which I have not liked. If I have already rated it higher, decrease it to 1.
JSON: {"intent_type":"appworld_spotify_rate_library_songs_by_liked_status","slots":{"collection_type":"song_library","liked_filter":"not_liked","target_rating":1}}

Task: Give a 4-star rating to all songs in my Spotify album library which I have liked. If I have already rated it lower, increase it to 4.
JSON: {"intent_type":"appworld_spotify_rate_library_songs_by_liked_status","slots":{"collection_type":"album_library","liked_filter":"liked","target_rating":4}}

Task: Follow artists of all the songs and albums I have ever liked on Spotify.
JSON: {"intent_type":"appworld_spotify_follow_artists_from_liked_songs_and_albums","slots":{}}

Task: Follow all artists of all classical-genre songs in any of my playlists on Spotify.
JSON: {"intent_type":"appworld_spotify_follow_playlist_song_artists_by_genre","slots":{"genre":"classical"}}

Task: Give me a comma-separated list of top 4 most played r&b song titles from across my Spotify song, album and playlist libraries.
JSON: {"intent_type":"appworld_spotify_top_played_genre_titles","slots":{"genre":"r&b","limit":4}}

Task: How many unique songs are there across my Spotify song library, albums library and all playlists?
JSON: {"intent_type":"appworld_spotify_count_unique_library_songs","slots":{}}

Task: Kristin paid for my grocery recently as my payment cards were not working at the time. Send them the owed money with a description note "Groceries" as per my phone text conversation, and then send them a phone text message, "It is done.".
JSON: {"intent_type":"appworld_venmo_pay_grocery_from_text_and_notify","slots":{"person_first_name":"Kristin","note":"Groceries","message":"It is done."}}

Task: How many songs from across my spotify song and album libraries were released in this or last year?
JSON: {"intent_type":"appworld_spotify_count_recent_release_library_songs","slots":{"years_back":1,"include_current_year":true}}

Task: How many songs from across my spotify song and album libraries were released in this year?
JSON: {"intent_type":"appworld_spotify_count_recent_release_library_songs","slots":{"years_back":0,"include_current_year":true}}

Task: How many songs from across my spotify song and album libraries were released before this year?
JSON: {"intent_type":"appworld_spotify_count_recent_release_library_songs","slots":{"years_back":-1,"include_current_year":false}}

Task: Keep going to the previous song on Spotify until you reach a song by Luna Starlight.
JSON: {"intent_type":"appworld_spotify_navigate_until_artist","slots":{"direction":"previous","artist_name":"Luna Starlight"}}

Task: Keep going to the next song on Spotify until you reach a song by Lily Moon.
JSON: {"intent_type":"appworld_spotify_navigate_until_artist","slots":{"direction":"next","artist_name":"Lily Moon"}}

Task: Reset friends on venmo to be the same as my friends in my phone. Befriend and unfriend as needed.
JSON: {"intent_type":"appworld_venmo_reset_friends_to_phone_friends","slots":{}}

Task: Remove all the songs that I have liked from my Spotify queue, and then start the player.
JSON: {"intent_type":"appworld_spotify_filter_queue_by_liked_status","slots":{"remove_filter":"liked"}}

Task: Remove all the songs that I have not liked from my Spotify queue, and then start the player.
JSON: {"intent_type":"appworld_spotify_filter_queue_by_liked_status","slots":{"remove_filter":"not_liked"}}

Task: Keep going to the previous song on Spotify until you reach a liked song.
JSON: {"intent_type":"appworld_spotify_navigate_until_private_status","slots":{"direction":"previous","status_property":"liked"}}

Task: Keep going to the next song on Spotify until you reach a downloaded song.
JSON: {"intent_type":"appworld_spotify_navigate_until_private_status","slots":{"direction":"next","status_property":"downloaded"}}

Task: How much money have I sent to or received from others on venmo this month so far?
JSON: {"intent_type":"appworld_venmo_sum_month_transactions","slots":{"direction":"sent_or_received"}}

Task: How much money have I been requested on Venmo in the last 7 days (including today)?
JSON: {"intent_type":"appworld_venmo_sum_recent_received_requests","slots":{"days":7}}

Task: Reset my Spotify queue with all of its recommended songs, shuffle it, and play it.
JSON: {"intent_type":"appworld_spotify_reset_queue_with_recommendations","slots":{}}

Task: Go through all my Spotify playlists and remove all the songs from them that are in "~/documents/personal/old_songs.txt" from my file system and put them in a new playlist named "Archived Songs".
JSON: {"intent_type":"appworld_spotify_archive_playlist_songs_from_file","slots":{"source_file_path":"~/documents/personal/old_songs.txt","playlist_title":"Archived Songs"}}

Task: Import markdown notes in the "~/documents/personal/notes/" directory of my file system to my Simple Note account. Each markdown file should become a separate note in the Simple Note account. The title of each note should be taken from the name of the source file (excluding the directory path and file extension), replacing underscores in it with blank spaces.
JSON: {"intent_type":"appworld_simple_note_import_markdown_files","slots":{"source_directory":"~/documents/personal/notes/"}}

Task: How long was my workout duration yesterday, in minutes, as per my plan in Simple Note?
JSON: {"intent_type":"appworld_simple_note_workout_duration","slots":{"day_ref":"yesterday"}}

Task: How long is my workout duration on sundays, in minutes, as per my plan in Simple Note?
JSON: {"intent_type":"appworld_simple_note_workout_duration","slots":{"day_ref":"sunday"}}

Task: Give me a random funny quote from my SimpleNote note about it. Just the quote, nothing else.
JSON: {"intent_type":"appworld_simple_note_random_quote","slots":{"quote_type":"funny"}}

Task: Give me a random movie quote from my SimpleNote note about it. Just the quote, nothing else.
JSON: {"intent_type":"appworld_simple_note_random_quote","slots":{"quote_type":"movie"}}

Task: What is my longest practiced-good-posture habit streak, in number of days, as per my Simple Note habit tracking logs?
JSON: {"intent_type":"appworld_simple_note_longest_habit_streak","slots":{"habit_key":"practiced_good_posture"}}

Task: Add a new habit tracking log note for today in my Simple Note account. It should be the same as yesterday, except I did not meditate today.
JSON: {"intent_type":"appworld_simple_note_add_today_habit_log","slots":{"habit_key":"practiced_meditation","value":false}}

Task: Add a new habit tracking log note for today in my Simple Note account. It should be the same as yesterday, except I ate home-prepared meals today.
JSON: {"intent_type":"appworld_simple_note_add_today_habit_log","slots":{"habit_key":"ate_homemade_meals","value":true}}

Task: I maintain my habit tracking logs in Simple Note. Export it in "~/downloads/habit_tracker.csv" in my file system. Its first header column should be "date" and the rest should be correspond to the habits I track as per my logs. The rows for date column should be in yyyy-mm-dd format and the rest should be yes or no as per my logs. The rows should be sorted in ascending order of the date from top to bottom, and habit columns as per their order in logs.
JSON: {"intent_type":"appworld_simple_note_export_habit_tracker_csv","slots":{"destination_path":"~/downloads/habit_tracker.csv","sort_order":"ascending"}}

Task: I maintain a log of my monthly venmo expense in SimpleNote note. Update it with an entry for this month.
JSON: {"intent_type":"appworld_simple_note_update_monthly_venmo_expense","slots":{}}

Task: I went on a few trips each with some of my friends. My Simple Note has information on who owes whom what from each trip. I have already created Splitwise groups for the trips. Record the expenses accordingly in the respective groups.
JSON: {"intent_type":"appworld_splitwise_record_trip_expenses_from_simple_note","slots":{"relationship_type":"friends"}}

Task: I went on a few trips each with some of my coworkers. My Simple Note has information on who owes whom what from each trip. I have already created Splitwise groups for the trips. Record the expenses accordingly in the respective groups.
JSON: {"intent_type":"appworld_splitwise_record_trip_expenses_from_simple_note","slots":{"relationship_type":"coworkers"}}

Task: Approve all venmo payment requests from my roommates from this calendar month.
JSON: {"intent_type":"appworld_venmo_approve_roommate_requests_this_month","slots":{}}

Task: I have invited some of my friends to a reunion party via phone messages. I have made a CSV to track who is coming or not in "~/documents/personal_stuff/" in my file system. Please update RSVPs in it as per their latest replies.
JSON: {"intent_type":"appworld_file_update_reunion_rsvps_from_phone","slots":{"directory_path":"~/documents/personal_stuff/"}}

Task: Delete all .pdf files from my file system ~/downloads folder.
JSON: {"intent_type":"appworld_file_delete_downloads_by_extension","slots":{"extension":".pdf"}}

Task: Who is the most followed artist I follow on Spotify?
JSON: {"intent_type":"appworld_spotify_followed_artist_follower_extreme","slots":{"extreme":"most"}}

Task: Songs of which genre have I liked the least in my Spotify album library?
JSON: {"intent_type":"appworld_spotify_liked_genre_extreme","slots":{"collection_type":"album_library","extreme":"least"}}

Task: Give me 4 comma-separated artist names with the least songs in my Spotify playlists. If the same song is present in multiple playlists, count it once.
JSON: {"intent_type":"appworld_spotify_playlist_artist_song_count_extreme","slots":{"extreme":"least","limit":4}}

Task: How much have I paid in phone bill on venmo this year so far?
JSON: {"intent_type":"appworld_venmo_sum_year_bill_payments","slots":{"bill_type":"phone"}}

Task: Befriend on Venmo anyone I have sent or received money from this month and unfriend everyone else.
JSON: {"intent_type":"appworld_venmo_friend_transaction_counterparties","slots":{"direction":"sent_or_received","sync_mode":"sync"}}

Task: How many venmo friends have I made since the start of January this year?
JSON: {"intent_type":"appworld_venmo_count_friends_since_month_start","slots":{"month":"january","year_offset":0}}

Task: How many venmo friends have I made since the start of October last year?
JSON: {"intent_type":"appworld_venmo_count_friends_since_month_start","slots":{"month":"october","year_offset":-1}}

Task: Play any song released in 2022 from my Spotify song library.
JSON: {"intent_type":"appworld_spotify_play_released_year_from_collection","slots":{"release_year":2022,"collection_type":"song_library"}}

Task: Like all the venmo transactions of the ongoing year to and from my roommates.
JSON: {"intent_type":"appworld_venmo_like_transactions_by_relationship_period","slots":{"relationships":["roommate"],"period":"year"}}

Task: Like all the venmo transactions of the ongoing month to and from my friends.
JSON: {"intent_type":"appworld_venmo_like_transactions_by_relationship_period","slots":{"relationships":["friend"],"period":"month"}}

Task: I went on dinner with my coworkers yesterday at Azure Harbor Bistro. My manager paid for food and everyone venmoed them. Everyones' transactions except mine should be on my social feed. My share was $38. How much did my manager pay for the others, including me, yesterday?
JSON: {"intent_type":"appworld_venmo_manager_meal_total_from_social_feed","slots":{"relationships":["coworker"],"meal":"dinner","venue":"Azure Harbor Bistro","share_amount":38}}

Task: How many likes did all Venmo transactions, I sent this month, have in total?
JSON: {"intent_type":"appworld_venmo_sum_transaction_likes","slots":{"direction":"sent","period":"month"}}

Task: How many likes did all Venmo transactions, I sent or received this month, have in total?
JSON: {"intent_type":"appworld_venmo_sum_transaction_likes","slots":{"direction":"sent_or_received","period":"month"}}

Task: In my file system, add the prefix "YYYY_MM_DD-" to all file names in the ~/downloaded_files/ directory, based on their creation dates, and then move all files not from this year to ~/recycle_bin/.
JSON: {"intent_type":"appworld_file_prefix_and_move_old_files","slots":{"source_directory":"~/downloaded_files/","prefix_format":"YYYY_MM_DD-","old_destination_directory":"~/recycle_bin/"}}

Task: The work meeting files in my file system are in the ~/documents/work/meetings/ directory and are currently named <date>__<file_name>.<extension>. Reorganize them to <file_name>/<date>.<extension>.
JSON: {"intent_type":"appworld_file_reorganize_dated_meeting_files","slots":{"source_directory":"~/documents/work/meetings/"}}

Task: How many people follow the artist of the currently playing song on Spotify?
JSON: {"intent_type":"appworld_spotify_current_artist_followers","slots":{}}

Task: Export all my Simple Note notes to "~/backups/simple_note/" directory in my file system. The files should be named according to the note title, replacing white space with "_", and the extension should be ".md".
JSON: {"intent_type":"appworld_simple_note_export_markdown","slots":{"destination_directory":"~/backups/simple_note/"}}

If the task does not fit these intent types, return {"intent_type":"unsupported","slots":{}}.
""".strip()


def appworld_code_system_prompt() -> str:
    return """
You are a direct-code AppWorld baseline. Write one Python code cell that completes the task using the live `apis` object. Return only executable Python code.

Rules:
- Do not read files, ground truth, compiled solutions, task JSON, or public_data.
- Do not invent records. Query the apps through `apis`.
- After making the requested state change, call `apis.supervisor.complete_task(answer=None)`.
- The runtime provides `apis` and `DateTime`.

Common authentication pattern:
passwords = {row["account_name"]: row["password"] for row in apis.supervisor.show_account_passwords()}
profile = apis.supervisor.show_profile()
class User:
    pass
user = User()
user.email = profile["email"]
user.phone_number = profile["phone_number"]
user.account_passwords = passwords
token = apis.<app_name>.access_token_from(user)

Relevant APIs for this slice:
- apis.phone.search_contacts(access_token=..., query=..., relationship=..., page_index=0, page_limit=20)
- apis.phone.send_text_message(access_token=..., phone_number=..., message=...)
- apis.phone.send_voice_message(access_token=..., phone_number=..., message=...)
- apis.phone.search_text_messages(access_token=..., phone_number=..., page_index=0, page_limit=20)
- apis.phone.delete_text_message(access_token=..., text_message_id=...)
- apis.phone.search_voice_messages(access_token=..., phone_number=..., page_index=0, page_limit=20)
- apis.phone.delete_voice_message(access_token=..., voice_message_id=...)
- apis.phone.show_alarms(access_token=..., page_index=0, page_limit=20)
- apis.phone.update_alarm(access_token=..., alarm_id=..., snooze_minutes=...)
- apis.amazon.search_products(query=..., product_type=..., page_index=0, page_limit=20)
- apis.amazon.add_product_to_cart(access_token=..., product_id=..., quantity=1, clear_cart_first=True)
- apis.amazon.show_cart(access_token=...)
- apis.amazon.show_wish_list(access_token=...)
- apis.amazon.show_product(product_id=...)
- apis.amazon.show_addresses(access_token=...)
- apis.amazon.show_payment_cards(access_token=...)
- apis.amazon.move_product_from_cart_to_wish_list(access_token=..., product_id=..., quantity=...)
- apis.amazon.move_product_from_wish_list_to_cart(access_token=..., product_id=..., quantity=...)
- apis.amazon.delete_product_from_cart(access_token=..., product_id=..., quantity=...)
- apis.amazon.place_order(access_token=..., payment_card_id=..., address_id=...)
- apis.amazon.show_orders(access_token=..., page_index=0, page_limit=20, sort_by="-created_at")
- apis.amazon.show_product_reviews(product_id=..., user_email=..., page_index=0, page_limit=20)
- apis.amazon.update_product_review(access_token=..., review_id=..., rating=..., title=...)
- apis.amazon.show_product_questions(product_id=..., user_email=..., page_index=0, page_limit=20)
- apis.amazon.show_product_question_answers(question_id=..., page_index=0, page_limit=20)
- apis.venmo.search_users(access_token=..., query=..., page_limit=20)
- apis.venmo.search_friends(access_token=..., query=..., page_index=0, page_limit=20)
- apis.venmo.add_friend(access_token=..., user_email=...)
- apis.venmo.remove_friend(access_token=..., user_email=...)
- apis.venmo.show_account(access_token=...)
- apis.venmo.send_password_reset_code(email=...)
- apis.venmo.reset_password(email=..., password_reset_code=..., new_password=...)
- apis.venmo.show_payment_cards(access_token=...)
- apis.venmo.create_transaction(access_token=..., receiver_email=..., amount=..., private=..., payment_card_id=..., description=...)
- apis.venmo.create_payment_request(access_token=..., user_email=..., amount=..., private=..., description=...)
- apis.venmo.show_transactions(access_token=..., direction=..., min_created_at=..., max_created_at=..., page_index=0, page_limit=20)
- apis.venmo.show_sent_payment_requests(access_token=..., status=..., page_index=0, page_limit=20)
- apis.venmo.show_received_payment_requests(access_token=..., status=..., page_index=0, page_limit=20)
- apis.venmo.remind_payment_request(access_token=..., payment_request_id=...)
- apis.venmo.approve_payment_request(access_token=..., payment_request_id=..., payment_card_id=...)
- apis.venmo.deny_payment_request(access_token=..., payment_request_id=...)
- apis.gmail.show_drafts(access_token=..., page_index=0, page_limit=20)
- apis.gmail.delete_draft(access_token=..., draft_id=...)
- apis.gmail.show_inbox_threads(access_token=..., read=True, archived=False, page_index=0, page_limit=20)
- apis.gmail.show_outbox_threads(access_token=..., read=True, archived=False, page_index=0, page_limit=20)
- apis.gmail.forward_email_from_thread(access_token=..., email_thread_id=..., email_id=..., email_addresses=[...], draft_not_send=True)
- apis.gmail.show_draft(access_token=..., draft_id=...)
- apis.gmail.mark_thread_archived(access_token=..., email_thread_id=...)
- apis.gmail.delete_thread(access_token=..., email_thread_id=...)
- apis.gmail.mark_thread_starred(access_token=..., email_thread_id=...)
- apis.gmail.mark_thread_unstarred(access_token=..., email_thread_id=...)
- apis.gmail.show_thread(access_token=..., email_thread_id=...)
- apis.gmail.reply_to_email(access_token=..., email_thread_id=..., email_id=..., body=..., email_addresses=None, attachment_file_paths=[])
- apis.gmail.update_draft(access_token=..., draft_id=..., body=...)
- apis.gmail.send_email_from_draft(access_token=..., draft_id=...)
- apis.amazon.show_payment_cards(access_token=...)
- apis.amazon.delete_payment_card(access_token=..., payment_card_id=...)
- apis.spotify.show_payment_cards(access_token=...)
- apis.spotify.delete_payment_card(access_token=..., payment_card_id=...)
- apis.venmo.show_payment_cards(access_token=...)
- apis.venmo.delete_payment_card(access_token=..., payment_card_id=...)
- apis.simple_note.search_notes(access_token=..., query=..., page_index=0, page_limit=20)
- apis.simple_note.show_note(access_token=..., note_id=...)
- apis.simple_note.update_note(access_token=..., note_id=..., content=...)
- apis.simple_note.create_note(access_token=..., title=..., content=...)
- apis.spotify.search_artists(query=..., genre=..., min_follower_count=..., page_index=0, page_limit=20)
- apis.spotify.search_songs(query=..., artist_id=..., min_play_count=..., page_index=0, page_limit=20)
- apis.spotify.add_to_queue(access_token=..., song_id=...)
- apis.spotify.follow_artist(access_token=..., artist_id=...)
- apis.spotify.unfollow_artist(access_token=..., artist_id=...)
- apis.spotify.show_following_artists(access_token=..., page_index=0, page_limit=20)
- apis.spotify.show_liked_songs(access_token=..., page_index=0, page_limit=20)
- apis.spotify.show_liked_albums(access_token=..., page_index=0, page_limit=20)
- apis.spotify.show_album_library(access_token=..., page_index=0, page_limit=20)
- apis.spotify.show_playlist_library(access_token=..., page_index=0, page_limit=20)
- apis.spotify.show_album(album_id=...)
- apis.spotify.show_playlist(access_token=..., playlist_id=...)
- apis.spotify.create_playlist(access_token=..., title=..., is_public=False)
- apis.spotify.add_song_to_playlist(access_token=..., playlist_id=..., song_id=...)
- apis.spotify.show_song(song_id=...)
- apis.spotify.show_song_privates(access_token=..., song_id=...)
- apis.spotify.show_album_privates(access_token=..., album_id=...)
- apis.spotify.like_song(access_token=..., song_id=...)
- apis.spotify.like_album(access_token=..., album_id=...)
- apis.spotify.download_song(access_token=..., song_id=...)
- apis.spotify.show_downloaded_songs(access_token=..., page_index=0, page_limit=20)
- apis.spotify.show_song_queue(access_token=...)
- apis.spotify.remove_song_from_queue(access_token=..., position=...)
- apis.spotify.play_music(access_token=..., queue_position=None, song_id=None, album_id=None, playlist_id=None)
- apis.spotify.next_song(access_token=...)
- apis.spotify.previous_song(access_token=...)
- apis.spotify.show_current_song(access_token=...)
- apis.venmo.show_venmo_balance(access_token=...)
- apis.venmo.withdraw_from_venmo_balance(access_token=..., amount=..., payment_card_id=...)
- apis.spotify.show_song_reviews(song_id=..., user_email=..., page_index=0, page_limit=20)
- apis.spotify.review_song(access_token=..., song_id=..., rating=...)
- apis.spotify.update_song_review(access_token=..., review_id=..., rating=...)
- apis.spotify.create_playlist(access_token=..., title=..., is_public=False)
- apis.spotify.update_playlist(access_token=..., playlist_id=..., title=..., is_public=...)
- apis.spotify.add_song_to_playlist(access_token=..., playlist_id=..., song_id=...)
- apis.spotify.remove_song_from_playlist(access_token=..., playlist_id=..., song_id=...)
- apis.spotify.show_recommendations(access_token=..., page_index=0, page_limit=20)
- apis.spotify.clear_song_queue(access_token=...)
- apis.spotify.shuffle_song_queue(access_token=...)
- apis.file_system.show_directory(access_token=..., directory_path=..., entry_type="files", recursive=False)
- apis.file_system.show_file(access_token=..., file_path=...)
- apis.file_system.delete_file(access_token=..., file_path=...)
- apis.file_system.create_directory(access_token=..., directory_path=..., recursive=True, allow_if_exists=True)
- apis.file_system.move_file(access_token=..., source_file_path=..., destination_file_path=..., overwrite=True, retain_dates=True)

Use pagination when a search result can exceed one page. Print a small JSON summary at the end.
""".strip()


def appworld_react_code_system_prompt() -> str:
    base = appworld_code_system_prompt().replace(
        "You are a direct-code AppWorld baseline. Write one Python code cell that completes the task using the live `apis` object. Return only executable Python code.",
        "You are a multi-step AppWorld code-observation baseline. Use the live `apis` object to inspect state and complete the task.",
    )
    return (
        base
        + """

For this multi-step baseline, do not return raw Python directly. Return exactly one JSON
object on every turn:

{"action":"code","code":"<one Python code cell>"}
or
{"action":"final","message":"done"}

You may inspect live state in one code cell, read the observation, and then issue another
code cell. Do not read files, ground truth, compiled solutions, task JSON, or public_data.
Call apis.supervisor.complete_task(answer=None) once the requested state change is done.
"""
    ).strip()
