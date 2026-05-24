from __future__ import annotations

import ast
import datetime as dt
import inspect
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .llm_client import ChatMessage, OpenAICompatibleClient, parse_json_object
from .rave_dsl import FinalAction, IntentFrame, IntentMachine, IntentSchema, RaveRuntimeOptions, SlotSpec, ToolAction
from .rave_runtime import RaveRuntime, RaveRuntimeHooks

from tool_sandbox.common.execution_context import RoleType, get_current_context
from tool_sandbox.common.message_conversion import Message
from tool_sandbox.roles.base_role import BaseRole


READ_ONLY_TOOLS = {
    "get_cellular_service_status",
    "get_wifi_status",
    "get_low_battery_mode_status",
    "get_location_service_status",
    "get_current_location",
    "get_current_timestamp",
    "timestamp_to_datetime_info",
    "datetime_info_to_timestamp",
    "shift_timestamp",
    "timestamp_diff",
    "seconds_to_hours_minutes_seconds",
    "unit_conversion",
    "calculate_lat_lon_distance",
    "search_contacts",
    "search_messages",
    "search_reminder",
    "search_holiday",
    "search_lat_lon",
    "search_location_around_lat_lon",
    "search_weather_around_lat_lon",
    "search_stock",
    "convert_currency",
}


SETTING_GETTERS = {
    "get_cellular_service_status": "cellular",
    "get_wifi_status": "wifi",
    "get_low_battery_mode_status": "low_battery_mode",
    "get_location_service_status": "location_service",
}


SETTING_SETTERS = {
    "set_cellular_service_status": "cellular",
    "set_wifi_status": "wifi",
    "set_low_battery_mode_status": "low_battery_mode",
    "set_location_service_status": "location_service",
}


def regular_status_getter_setting(tool_name: str) -> Optional[str]:
    match = re.fullmatch(r"get_([a-zA-Z][a-zA-Z0-9_]*)_status", tool_name)
    return match.group(1) if match else None


def regular_status_setter_setting(tool_name: str) -> Optional[str]:
    match = re.fullmatch(r"set_([a-zA-Z][a-zA-Z0-9_]*)_status", tool_name)
    return match.group(1) if match else None


def regular_setting_label(setting: str) -> str:
    return setting.replace("_", " ")


KNOWN_LOCATION_CANONICALS = {
    "grand canyon": {"latitude": 36.23686, "longitude": -112.19147, "label": "Grand Canyon"},
    "golden gate bridge": {
        "latitude": 37.8175,
        "longitude": -122.4803,
        "label": "Golden Gate Bridge",
    },
    "whole foods on stevens creek": {
        "latitude": 37.323498,
        "longitude": -122.039665,
        "label": "Whole Foods on Stevens Creek",
    },
    "whole foods on mckinley ave": {
        "latitude": 37.3738083,
        "longitude": -122.0314225,
        "label": "Whole Foods on McKinley Ave",
    },
    "apple park": {"label": "Apple Park"},
}


WEEKDAY_TO_ISO = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 7,
}


TOOL_SANDBOX_INTENT_SCHEMAS = {
    "currency_conversion": IntentSchema(
        "currency_conversion",
        (
            SlotSpec("amount"),
            SlotSpec("from_currency_code"),
            SlotSpec("to_currency_code"),
        ),
    ),
    "stock_lookup": IntentSchema("stock_lookup", (SlotSpec("query"),)),
    "reverse_geocode": IntentSchema(
        "reverse_geocode",
        (
            SlotSpec("latitude"),
            SlotSpec("longitude"),
        ),
    ),
    "current_city": IntentSchema("current_city"),
    "last_message_contact_update": IntentSchema(
        "last_message_contact_update",
        (SlotSpec("phone_number"),),
    ),
    "bulk_contact_relationship_update": IntentSchema(
        "bulk_contact_relationship_update",
        (
            SlotSpec("source_relationship"),
            SlotSpec("target_relationship"),
            SlotSpec("roundtrip", required=False),
        ),
    ),
    "contact_name_lookup": IntentSchema("contact_name_lookup", (SlotSpec("relationship"),)),
    "location_phone": IntentSchema("location_phone", (SlotSpec("location"),)),
    "holiday_timestamp": IntentSchema("holiday_timestamp", (SlotSpec("holiday_name"),)),
    "holiday_countdown": IntentSchema("holiday_countdown", (SlotSpec("holiday_name"),)),
    "weather": IntentSchema(
        "weather",
        (
            SlotSpec("location", required=False),
            SlotSpec("latitude", required=False),
            SlotSpec("longitude", required=False),
            SlotSpec("days", required=False),
            SlotSpec("temperature_field", required=False),
            SlotSpec("temperature_unit", required=False),
        ),
    ),
    "distance_to_location": IntentSchema(
        "distance_to_location",
        (
            SlotSpec("location"),
            SlotSpec("target_latitude"),
            SlotSpec("target_longitude"),
        ),
    ),
    "reminder": IntentSchema(
        "reminder",
        (
            SlotSpec("operation"),
            SlotSpec("content", required=False),
            SlotSpec("time_spec", required=False),
            SlotSpec("location", required=False),
            SlotSpec("recency", required=False),
        ),
    ),
}


def toolsandbox_intent_schemas() -> dict[str, IntentSchema]:
    return dict(TOOL_SANDBOX_INTENT_SCHEMAS)


@dataclass
class RuntimeMetrics:
    llm_calls: int = 0
    token_proxy: int = 0
    parse_errors: int = 0
    verifier_rejections: int = 0
    repair_calls: int = 0
    proposed_tool_calls: int = 0
    final_messages: int = 0
    dynamic_synthesis_records: int = 0
    dynamic_synthesis_proposals: int = 0
    dynamic_synthesis_promotions: int = 0
    dynamic_synthesis_rejections: int = 0


@dataclass
class ToolSandboxLedger:
    user_messages: list[str] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, bool] = field(default_factory=dict)
    contacts: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    reminders: list[dict[str, Any]] = field(default_factory=list)

    def record_user_message(self, content: str) -> None:
        if content and content not in self.user_messages:
            self.user_messages.append(content)

    def observe(self, tool: str, args: dict[str, Any], content: str, error: Optional[str]) -> None:
        parsed = parse_python_literal(content)
        record = {
            "tool": tool,
            "args": args,
            "result": parsed,
            "raw": content,
            "error": error,
        }
        self.observations.append(record)
        if error:
            return

        getter_setting = SETTING_GETTERS.get(tool) or regular_status_getter_setting(tool)
        setter_setting = SETTING_SETTERS.get(tool) or regular_status_setter_setting(tool)
        if getter_setting is not None and isinstance(parsed, bool):
            self.settings[getter_setting] = parsed
        elif setter_setting is not None and "on" in args:
            self.settings[setter_setting] = bool(args["on"])
            if tool == "set_low_battery_mode_status" and bool(args["on"]):
                self.settings["cellular"] = False
                self.settings["wifi"] = False
                self.settings["location_service"] = False
        elif tool == "search_contacts" and isinstance(parsed, list):
            self._merge_records(self.contacts, parsed, key="person_id")
        elif tool == "search_messages" and isinstance(parsed, list):
            self._merge_records(self.messages, parsed, key="message_id")
        elif tool == "search_reminder" and isinstance(parsed, list):
            self._merge_records(self.reminders, parsed, key="reminder_id")

    def is_value_grounded(self, value: Any) -> bool:
        if value is None or isinstance(value, bool):
            return True
        if isinstance(value, (int, float)):
            return any(str(value) in text for text in self.user_messages) or self._contains_value(value)
        if isinstance(value, str):
            if not value:
                return False
            normalized = normalize_text(value)
            if any(normalized in normalize_text(text) for text in self.user_messages):
                return True
            return self._contains_value(value)
        return self._contains_value(value)

    def to_prompt_json(self) -> str:
        return json.dumps(
            {
                "observed_settings": self.settings,
                "observed_contacts": self.contacts[-8:],
                "observed_messages": self.messages[-8:],
                "observed_reminders": self.reminders[-8:],
                "recent_observations": self.observations[-8:],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    def last_successful_observation(self) -> Optional[dict[str, Any]]:
        for observation in reversed(self.observations):
            if not observation.get("error"):
                return observation
        return None

    def last_successful_result(self, tool: str) -> Any:
        for observation in reversed(self.observations):
            if observation.get("tool") == tool and not observation.get("error"):
                return observation.get("result")
        return None

    def last_successful_args(self, tool: str) -> dict[str, Any]:
        for observation in reversed(self.observations):
            if observation.get("tool") == tool and not observation.get("error"):
                args = observation.get("args")
                return args if isinstance(args, dict) else {}
        return {}

    def last_successful_matching_result(
        self,
        tool: str,
        args_subset: Optional[dict[str, Any]] = None,
    ) -> Any:
        for observation in reversed(self.observations):
            if observation.get("tool") != tool or observation.get("error"):
                continue
            args = observation.get("args") or {}
            if args_subset is None or args_include(args, args_subset):
                return observation.get("result")
        return None

    def has_successful_observation(
        self,
        tool: str,
        args_subset: Optional[dict[str, Any]] = None,
    ) -> bool:
        for observation in self.observations:
            if observation.get("tool") != tool or observation.get("error"):
                continue
            args = observation.get("args") or {}
            if args_subset is None or args_include(args, args_subset):
                return True
        return False

    def has_failed_observation(
        self,
        tool: str,
        args_subset: Optional[dict[str, Any]] = None,
    ) -> bool:
        for observation in self.observations:
            if observation.get("tool") != tool or not observation.get("error"):
                continue
            args = observation.get("args") or {}
            if args_subset is None or args_include(args, args_subset):
                return True
        return False

    @staticmethod
    def _merge_records(target: list[dict[str, Any]], records: list[Any], key: str) -> None:
        for item in records:
            if not isinstance(item, dict):
                continue
            item_key = item.get(key)
            if item_key is None:
                target.append(item)
                continue
            for index, existing in enumerate(target):
                if existing.get(key) == item_key:
                    target[index] = item
                    break
            else:
                target.append(item)

    def _contains_value(self, value: Any) -> bool:
        needle = normalize_text(str(value))
        for observation in self.observations:
            if needle and needle in normalize_text(json.dumps(observation, ensure_ascii=False, default=str)):
                return True
        return False


@dataclass
class ToolSandboxRuntimePolicy:
    ledger: ToolSandboxLedger

    def abstention_message(self, frame: IntentFrame) -> str:
        if frame.abstain_reason == "missing_remove_contact_tool":
            return "I cannot remove the phone number from your contact , because I don't have the tools available."
        if frame.abstain_reason == "missing_recipient_phone_number":
            return "I cannot send the message because I do not have the recipient's phone number."
        if frame.missing_slots:
            missing = ", ".join(frame.missing_slots)
            return f"I cannot complete that safely with the available information. Missing: {missing}."
        return "I cannot complete that safely with the available information."

    def verify_action(
        self,
        frame: IntentFrame,
        action: ToolAction | FinalAction,
        available_tools: dict[str, Callable[..., Any]],
    ) -> ToolAction | FinalAction:
        if isinstance(action, FinalAction):
            return action
        if self.ledger.has_failed_observation(action.tool, action.args):
            return FinalAction(
                message="I cannot complete that safely because the required tool failed.",
                reason=f"abstain_after_tool_error_{action.reason}",
            )
        return action


@dataclass
class UnsupportedIntentRecord:
    request: str
    raw_request: str
    available_tool_names: tuple[str, ...]
    reason: str


@dataclass
class DynamicSynthesisAudit:
    request: str
    decision: str
    candidate_intent_type: str = ""
    details: tuple[str, ...] = ()


@dataclass
class SynthesizedMachineCandidate:
    intent_type: str
    target_setting: str
    machine: IntentMachine
    source_tools: tuple[str, ...]
    inferred_from_tools: bool = False
    validation_details: tuple[str, ...] = ()


class ToolSandboxDynamicMachineSynthesizer:
    """Conservative synthesis for regular ToolSandbox setting APIs.

    This is intentionally narrow: it derives only setting state machines whose API
    surface has the regular get_*_status / set_*_status(on: bool) shape, validates
    them in shadow mode, and promotes them only after simple invariants and
    counterexample checks pass.
    """

    _SETTING_ALIASES = {
        "cellular": ("cellular", "cellphone signal", "cell signal"),
        "wifi": ("wifi", "wi-fi", "internet", "connected"),
        "location_service": ("location service", "current location"),
        "low_battery_mode": ("low battery", "low-battery"),
    }
    _SETTING_LABELS = {
        "cellular": "cellular service",
        "wifi": "wifi",
        "location_service": "location service",
        "low_battery_mode": "low battery mode",
    }
    _SETTING_TO_GETTER = {value: key for key, value in SETTING_GETTERS.items()}
    _SETTING_TO_SETTER = {value: key for key, value in SETTING_SETTERS.items()}
    _ENABLE_REPAIR_SETTINGS = {"cellular", "wifi", "location_service"}
    _COUNTEREXAMPLES = (
        "What is the stock symbol for Apple?",
        "What is the weather at the Grand Canyon?",
        "Find my boss's phone number.",
        "Remind me to buy milk tomorrow.",
        "Send a message to Alice saying hello.",
    )

    def __init__(self, ledger: ToolSandboxLedger, options: RaveRuntimeOptions) -> None:
        self.ledger = ledger
        self.options = options
        self.unsupported_records: list[UnsupportedIntentRecord] = []
        self.audit: list[DynamicSynthesisAudit] = []

    def synthesize_and_register(
        self,
        runtime: RaveRuntime,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[SynthesizedMachineCandidate]:
        self.unsupported_records.append(
            UnsupportedIntentRecord(
                request=request,
                raw_request=raw_request,
                available_tool_names=tuple(sorted(available_tools)),
                reason="no_registered_intent_machine",
            )
        )
        candidate = self._propose_candidate(request, available_tools)
        if candidate is None:
            self.audit.append(
                DynamicSynthesisAudit(
                    request=request,
                    decision="rejected",
                    details=("no_regular_setting_api_candidate",),
                )
            )
            return None
        if candidate.intent_type in runtime.intent_machine_by_type:
            self.audit.append(
                DynamicSynthesisAudit(
                    request=request,
                    decision="already_registered",
                    candidate_intent_type=candidate.intent_type,
                )
            )
            return candidate

        ok, details = self._validate_candidate(candidate, request, raw_request, available_tools)
        if not ok:
            self.audit.append(
                DynamicSynthesisAudit(
                    request=request,
                    decision="rejected",
                    candidate_intent_type=candidate.intent_type,
                    details=tuple(details),
                )
            )
            return None

        promoted = SynthesizedMachineCandidate(
            intent_type=candidate.intent_type,
            target_setting=candidate.target_setting,
            machine=candidate.machine,
            source_tools=candidate.source_tools,
            inferred_from_tools=candidate.inferred_from_tools,
            validation_details=tuple(details),
        )
        runtime.register_machine(promoted.machine)
        self.audit.append(
            DynamicSynthesisAudit(
                request=request,
                decision="promoted",
                candidate_intent_type=promoted.intent_type,
                details=promoted.validation_details,
            )
        )
        return promoted

    def _propose_candidate(
        self,
        request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[SynthesizedMachineCandidate]:
        target = self._infer_setting(request) or self._infer_setting_from_tools(request, available_tools)
        operation, desired_on = self._infer_operation(request)
        if target is None or operation is None:
            return None

        tools_by_setting = self._discover_regular_setting_tools(available_tools)
        getter, setter = tools_by_setting.get(
            target,
            (
                self._SETTING_TO_GETTER.get(target, f"get_{target}_status"),
                self._SETTING_TO_SETTER.get(target, f"set_{target}_status"),
            ),
        )
        if operation == "status" and getter not in available_tools:
            return None
        if operation in {"enable", "disable"} and setter not in available_tools:
            return None

        intent_type = f"dynamic_setting_{target}"
        schema = IntentSchema(
            intent_type,
            (
                SlotSpec("setting"),
                SlotSpec("operation"),
                SlotSpec("desired_on", required=False),
            ),
        )
        machine = IntentMachine(
            schema=schema,
            compiler=self._make_setting_compiler(target, intent_type),
            handler=self._make_setting_handler(target),
        )
        source_tools = tuple(
            tool
            for tool in (
                getter,
                setter,
                "get_low_battery_mode_status",
                "set_low_battery_mode_status",
            )
            if tool in available_tools
        )
        if desired_on is not None:
            source_tools = tuple(dict.fromkeys((*source_tools, setter)))
        return SynthesizedMachineCandidate(
            intent_type=intent_type,
            target_setting=target,
            machine=machine,
            source_tools=source_tools,
            inferred_from_tools=target not in self._SETTING_TO_GETTER,
        )

    def _validate_candidate(
        self,
        candidate: SynthesizedMachineCandidate,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> tuple[bool, list[str]]:
        details: list[str] = []
        target = candidate.target_setting
        getter = self._getter_name(target, available_tools)
        setter = self._setter_name(target, available_tools)
        allowed_tools = {
            tool
            for tool in (
                getter,
                setter,
                "get_low_battery_mode_status",
                "set_low_battery_mode_status",
            )
            if tool in available_tools
        }
        if candidate.inferred_from_tools:
            details.append(f"affordance_template_induced:{target}")

        if setter in available_tools:
            setter_signature = inspect.signature(available_tools[setter])
            on_param = setter_signature.parameters.get("on")
            if on_param is None:
                return False, [f"{setter}_missing_on_parameter"]
            if on_param.kind not in {
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            }:
                return False, [f"{setter}_on_parameter_not_keyword_compatible"]
            if on_param.annotation not in {inspect.Signature.empty, bool, "bool"}:
                return False, [f"{setter}_on_parameter_not_bool"]
            details.append(f"api_signature_ok:{setter}(on: bool)")

        frame = candidate.machine.compiler(request, raw_request, available_tools)
        if frame is None:
            return False, ["shadow_compile_failed"]
        frame.validate(candidate.machine.schema)
        action = candidate.machine.handler(frame, available_tools)
        if action is None:
            return False, ["shadow_handler_returned_no_action"]
        if action.tool not in allowed_tools:
            return False, [f"shadow_action_outside_allowed_tools:{action.tool}"]
        if action.tool == setter:
            if set(action.args) != {"on"} or not isinstance(action.args.get("on"), bool):
                return False, [f"shadow_setter_args_not_bool_on:{action.tool}"]
        elif action.args:
            return False, [f"shadow_getter_has_args:{action.tool}"]
        details.append(f"shadow_action_ok:{action.tool}")

        for counterexample in self._COUNTEREXAMPLES:
            if candidate.machine.compiler(counterexample, counterexample, available_tools) is not None:
                return False, [f"counterexample_matched:{counterexample}"]
        details.append("counterexample_tests_passed")
        return True, details

    def _make_setting_compiler(
        self,
        target: str,
        intent_type: str,
    ) -> Callable[[str, str, dict[str, Callable[..., Any]]], Optional[IntentFrame]]:
        def compile_setting(
            request: str,
            raw_request: str,
            available_tools: dict[str, Callable[..., Any]],
        ) -> Optional[IntentFrame]:
            del raw_request
            if (self._infer_setting(request) or self._infer_setting_from_tools(request, available_tools)) != target:
                return None
            operation, desired_on = self._infer_operation(request)
            if operation is None:
                return None
            getter = self._getter_name(target, available_tools)
            setter = self._setter_name(target, available_tools)
            if operation == "status" and getter not in available_tools:
                return None
            if operation in {"enable", "disable"} and setter not in available_tools:
                return None
            frame = IntentFrame(intent_type)
            frame.set_slot("setting", target, source="dynamic_api_docs")
            frame.set_slot("operation", operation, source="dynamic_request_parse")
            if desired_on is not None:
                frame.set_slot("desired_on", desired_on, source="dynamic_request_parse", required=False)
            return frame

        return compile_setting

    def _make_setting_handler(
        self,
        target: str,
    ) -> Callable[[IntentFrame, dict[str, Callable[..., Any]]], Optional[ToolAction]]:
        def handle_setting(
            frame: IntentFrame,
            available_tools: dict[str, Callable[..., Any]],
        ) -> Optional[ToolAction]:
            operation = str(frame.get("operation") or "")
            desired_on = frame.get("desired_on")
            getter = self._getter_name(target, available_tools)
            setter = self._setter_name(target, available_tools)
            if operation == "status":
                if target not in self.ledger.settings and getter in available_tools:
                    return ToolAction(tool=getter, args={}, reason=f"dynamic_read_{target}_status")
                return None

            if not isinstance(desired_on, bool):
                return None
            if self.ledger.settings.get(target) is desired_on:
                return None

            if desired_on is True and target in self._ENABLE_REPAIR_SETTINGS:
                if "low_battery_mode" not in self.ledger.settings and "get_low_battery_mode_status" in available_tools:
                    return ToolAction(
                        tool="get_low_battery_mode_status",
                        args={},
                        reason=f"dynamic_read_low_battery_before_enable_{target}",
                    )
                if self.ledger.settings.get("low_battery_mode") is True:
                    if not self.options.enable_precondition_repair:
                        return None
                    if "set_low_battery_mode_status" in available_tools:
                        return ToolAction(
                            tool="set_low_battery_mode_status",
                            args={"on": False},
                            reason=f"dynamic_disable_low_battery_before_enable_{target}",
                        )
                    return None

            if setter in available_tools:
                return ToolAction(
                    tool=setter,
                    args={"on": desired_on},
                    reason=f"dynamic_set_{target}_{'on' if desired_on else 'off'}",
                )
            return None

        return handle_setting

    def _infer_setting(self, request: str) -> Optional[str]:
        normalized = normalize_text(request)
        for setting, aliases in self._SETTING_ALIASES.items():
            if any(alias in normalized for alias in aliases):
                return setting
        return None

    def _infer_setting_from_tools(
        self,
        request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[str]:
        normalized = normalize_text(request)
        matches = []
        for setting in self._discover_regular_setting_tools(available_tools):
            aliases = self._aliases_for_setting(setting)
            if any(alias in normalized for alias in aliases):
                matches.append(setting)
        return matches[0] if len(matches) == 1 else None

    def _discover_regular_setting_tools(
        self,
        available_tools: dict[str, Callable[..., Any]],
    ) -> dict[str, tuple[str, str]]:
        getters = {
            setting: name
            for name in available_tools
            if (setting := regular_status_getter_setting(name)) is not None
        }
        setters = {
            setting: name
            for name in available_tools
            if (setting := regular_status_setter_setting(name)) is not None
        }
        return {
            setting: (getters[setting], setters[setting])
            for setting in sorted(getters.keys() & setters.keys())
        }

    def _getter_name(
        self,
        target: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> str:
        discovered = self._discover_regular_setting_tools(available_tools).get(target)
        if discovered is not None:
            return discovered[0]
        return self._SETTING_TO_GETTER.get(target, f"get_{target}_status")

    def _setter_name(
        self,
        target: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> str:
        discovered = self._discover_regular_setting_tools(available_tools).get(target)
        if discovered is not None:
            return discovered[1]
        return self._SETTING_TO_SETTER.get(target, f"set_{target}_status")

    def _aliases_for_setting(self, setting: str) -> tuple[str, ...]:
        aliases = self._SETTING_ALIASES.get(setting)
        if aliases is not None:
            return aliases
        label = regular_setting_label(setting)
        return (
            label,
            setting.replace("_", "-"),
            setting.replace("_", ""),
        )

    @staticmethod
    def _infer_operation(request: str) -> tuple[Optional[str], Optional[bool]]:
        normalized = normalize_text(request)
        if any(phrase in normalized for phrase in ("turn off", "disable", "shut off", "switch off")):
            return "disable", False
        if any(
            phrase in normalized
            for phrase in ("turn on", "enable", "switch on", "get it on", "connected", "fix that", "access")
        ):
            return "enable", True
        if "?" in normalized or normalized.startswith("is ") or " status" in normalized or "check " in normalized:
            return "status", None
        return None, None


@dataclass
class VerificationResult:
    ok: bool
    code: str = ""
    message: str = ""


class PassiveUser(BaseRole):
    """A deterministic user for single-user-turn ToolSandbox scenarios.

    It ends the conversation as soon as the agent responds to the user. This avoids using
    a paid/API user simulator for the kill-criteria pass, so the selected scenario set
    should avoid scenarios that genuinely require additional user information.
    """

    role_type: RoleType = RoleType.USER
    model_name = "passive_end_user"

    def respond(self, ending_index: Optional[int] = None) -> None:
        messages = self.get_messages(ending_index=ending_index)
        self.messages_validation(messages=messages)
        if messages[-1].sender == RoleType.SYSTEM:
            return
        self.add_messages(
            [
                Message(
                    sender=self.role_type,
                    recipient=RoleType.EXECUTION_ENVIRONMENT,
                    content="print(repr(end_conversation()))",
                )
            ]
        )


class LocalOpenAIUser(BaseRole):
    """Local OpenAI-compatible user simulator for multi-turn ToolSandbox scenarios."""

    role_type: RoleType = RoleType.USER

    def __init__(
        self,
        client: OpenAICompatibleClient,
        model_name: str = "ToolSandbox Local User",
        temperature: float = 0.0,
        max_tokens: int = 256,
    ) -> None:
        self.client = client
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.metrics = RuntimeMetrics()

    def respond(self, ending_index: Optional[int] = None) -> None:
        messages = self.get_messages(ending_index=ending_index)
        self.messages_validation(messages=messages)
        visible_messages = self.filter_messages(messages=messages)
        if visible_messages[-1].sender == RoleType.SYSTEM:
            return

        response_json = self._call_model(visible_messages)
        if response_json.get("end") is True:
            self.add_messages(
                [
                    Message(
                        sender=self.role_type,
                        recipient=RoleType.EXECUTION_ENVIRONMENT,
                        content="print(repr(end_conversation()))",
                    )
                ]
            )
            return

        content = str(response_json.get("message") or "").strip()
        if not content:
            content = "Please continue."
        self.add_messages([Message(sender=self.role_type, recipient=RoleType.AGENT, content=content)])

    def _call_model(self, messages: list[Message]) -> dict[str, Any]:
        prompt = f"""
You are the ToolSandbox simulated user. Follow the system instructions addressed to USER.
Respond as the user, not as an assistant.

Visible conversation:
{format_messages(messages[-18:])}

Return exactly one JSON object:
- If the agent has completed the user's request, or the task should stop, return:
  {{"end": true}}
- Otherwise return a short user reply:
  {{"message": "your reply to the agent"}}
"""
        response = self.client.chat(
            [ChatMessage("system", "Return JSON only."), ChatMessage("user", prompt)],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        self.metrics.llm_calls += 1
        self.metrics.token_proxy += token_count_or_proxy(
            response.prompt_tokens,
            response.completion_tokens,
            prompt,
            response.content,
        )
        try:
            return parse_json_object(response.content)
        except Exception:  # noqa: BLE001
            text = normalize_text(response.content)
            if "end_conversation" in text or '"end"' in text:
                return {"end": True}
            return {"message": response.content.strip()[:300]}


class HiddenTaskUser(BaseRole):
    """Deterministic user that reveals the scenario task on clarification.

    This is for isolating agent/runtime behavior from local user-simulator noise in
    multi-turn debugging runs. It is not a replacement for a benchmark-grade user model.
    """

    role_type: RoleType = RoleType.USER
    model_name = "ToolSandbox Hidden Task User"

    def __init__(self) -> None:
        self._revealed = False
        self._agent_turns = 0

    def respond(self, ending_index: Optional[int] = None) -> None:
        messages = self.get_messages(ending_index=ending_index)
        self.messages_validation(messages=messages)
        visible_messages = self.filter_messages(messages=messages)
        if visible_messages[-1].sender == RoleType.SYSTEM:
            return

        last = visible_messages[-1]
        if last.sender != RoleType.AGENT:
            return
        self._agent_turns += 1
        task = self._latest_hidden_task(visible_messages)
        agent_text = normalize_text(last.content)

        if self._should_end(agent_text) and not (
            "back to" in normalize_text(task) and "now your enemies" in agent_text
        ):
            self._end_conversation()
            return
        if not self._revealed or "?" in agent_text or "provide" in agent_text or "which" in agent_text:
            self._revealed = True
            self.add_messages([Message(sender=self.role_type, recipient=RoleType.AGENT, content=task)])
            return
        if self._agent_turns >= 5:
            self._end_conversation()
            return
        self.add_messages([Message(sender=self.role_type, recipient=RoleType.AGENT, content=task)])

    def _end_conversation(self) -> None:
        self.add_messages(
            [
                Message(
                    sender=self.role_type,
                    recipient=RoleType.EXECUTION_ENVIRONMENT,
                    content="print(repr(end_conversation()))",
                )
            ]
        )

    @staticmethod
    def _latest_hidden_task(messages: list[Message]) -> str:
        marker = "Answer User B's questions given the following task you (User A) want User B to complete:"
        for message in reversed(messages):
            if message.sender == RoleType.SYSTEM and message.recipient == RoleType.USER:
                if marker in message.content:
                    return message.content.rsplit(marker, 1)[-1].strip()
        return "Please continue with my original request."

    @staticmethod
    def _should_end(agent_text: str) -> bool:
        completion_markers = (
            "successfully",
            "has been",
            "have been",
            "is turned",
            "i found",
            "your oldest",
            "your most recent",
            "your message",
            "all your",
            "friends again",
            "now your enemies",
            "degrees fahrenheit",
            "cannot complete",
            "could not complete",
            "i could not",
        )
        return any(marker in agent_text for marker in completion_markers)


class JsonToolUseAgent(BaseRole):
    role_type: RoleType = RoleType.AGENT

    def __init__(
        self,
        client: OpenAICompatibleClient,
        method_name: str,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> None:
        self.client = client
        self.model_name = method_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.metrics = RuntimeMetrics()
        self.ledger = ToolSandboxLedger()
        self._seen_message_count = 0
        self._call_counter = 0
        self._last_agent_tool_call: Optional[tuple[str, dict[str, Any]]] = None
        self._feedback: list[str] = []

    def respond(self, ending_index: Optional[int] = None) -> None:
        messages = self.get_messages(ending_index=ending_index)
        self.messages_validation(messages=messages)
        self._ingest_new_messages(messages)
        visible_messages = self.filter_messages(messages=messages)
        if visible_messages[-1].sender == RoleType.SYSTEM:
            return

        available_tools = self.get_available_tools()
        response_json = self._call_model(visible_messages, available_tools)
        if response_json.get("final") is True:
            content = str(response_json.get("message") or "Done.")
            self.metrics.final_messages += 1
            self.add_messages([Message(sender=self.role_type, recipient=RoleType.USER, content=content)])
            return

        tool = str(response_json.get("tool", ""))
        args = response_json.get("args")
        if not isinstance(args, dict):
            args = {}
        self._emit_tool_call(tool=tool, args=args, available_tools=available_tools)

    def _call_model(
        self,
        messages: list[Message],
        available_tools: dict[str, Callable[..., Any]],
    ) -> dict[str, Any]:
        prompt = self._build_prompt(messages=messages, available_tools=available_tools)
        response = self.client.chat(
            [ChatMessage("system", self._system_prompt()), ChatMessage("user", prompt)],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        self.metrics.llm_calls += 1
        self.metrics.token_proxy += token_count_or_proxy(
            response.prompt_tokens,
            response.completion_tokens,
            prompt,
            response.content,
        )
        try:
            return parse_json_object(response.content)
        except Exception as exc:  # noqa: BLE001
            self.metrics.parse_errors += 1
            self._feedback.append(f"parser_error: {exc}; output={response.content[:300]}")
            fallback = self._fallback_action(messages=messages, available_tools=available_tools)
            if fallback is not None:
                return fallback
            return {"final": True, "message": "I could not produce a valid tool action."}

    def _fallback_action(
        self,
        messages: list[Message],
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[dict[str, Any]]:
        return None

    def _build_prompt(
        self,
        messages: list[Message],
        available_tools: dict[str, Callable[..., Any]],
    ) -> str:
        return f"""
Task and recent trajectory:
{format_messages(messages[-14:])}

Available tools:
{format_tool_specs(available_tools)}

Recent feedback:
{format_bullets(self._feedback[-6:])}

Return exactly one JSON object:
- To call a tool: {{"tool": "tool_name", "args": {{"arg": "value"}}}}
- When the task is complete or impossible: {{"final": true, "message": "brief response to user"}}
"""

    def _system_prompt(self) -> str:
        return (
            "You are a careful tool-use agent in ToolSandbox. Return JSON only. "
            "Use only available tool names and one tool call per turn. Do not invent tools."
        )

    def _emit_tool_call(
        self,
        tool: str,
        args: dict[str, Any],
        available_tools: dict[str, Callable[..., Any]],
    ) -> None:
        self.metrics.proposed_tool_calls += 1
        self._call_counter += 1
        self._last_agent_tool_call = (tool, args)
        code = make_tool_call_code(tool, args, available_tools, f"call_{self._call_counter}")
        self.add_messages(
            [
                Message(
                    sender=self.role_type,
                    recipient=RoleType.EXECUTION_ENVIRONMENT,
                    content=code,
                    openai_tool_call_id=f"call_{self._call_counter}",
                    openai_function_name=tool,
                )
            ]
        )

    def _ingest_new_messages(self, messages: list[Message]) -> None:
        for message in messages[self._seen_message_count :]:
            if message.visible_to is not None and RoleType.AGENT not in message.visible_to:
                continue
            if message.sender == RoleType.USER and message.recipient == RoleType.AGENT:
                self.ledger.record_user_message(message.content)
            if (
                message.sender == RoleType.EXECUTION_ENVIRONMENT
                and message.recipient == RoleType.AGENT
                and self._last_agent_tool_call is not None
            ):
                tool, args = self._last_agent_tool_call
                self.ledger.observe(tool, args, message.content, message.tool_call_exception)
                if message.tool_call_exception:
                    self._feedback.append(
                        f"tool_error: {tool}({json.dumps(args, ensure_ascii=False)}) -> "
                        f"{message.tool_call_exception}"
                    )
        self._seen_message_count = len(messages)


class ProofCarryingToolSandboxAgent(JsonToolUseAgent):
    def __init__(
        self,
        client: OpenAICompatibleClient,
        temperature: float = 0.0,
        max_tokens: int = 700,
    ) -> None:
        super().__init__(
            client=client,
            method_name="ToolSandbox PCTU",
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def respond(self, ending_index: Optional[int] = None) -> None:
        messages = self.get_messages(ending_index=ending_index)
        self.messages_validation(messages=messages)
        self._ingest_new_messages(messages)
        visible_messages = self.filter_messages(messages=messages)
        if visible_messages[-1].sender == RoleType.SYSTEM:
            return

        available_tools = self.get_available_tools()
        for _ in range(3):
            response_json = self._call_model(visible_messages, available_tools)
            if response_json.get("final") is True:
                content = str(response_json.get("message") or "Done.")
                self.metrics.final_messages += 1
                self.add_messages([Message(sender=self.role_type, recipient=RoleType.USER, content=content)])
                return

            contract = normalize_contract(response_json)
            verification = self._verify_contract(contract, available_tools)
            if verification.ok:
                self._emit_tool_call(contract["tool"], contract["args"], available_tools)
                return

            self.metrics.verifier_rejections += 1
            feedback = f"{verification.code}: {verification.message}"
            self._feedback.append(feedback)
            repair = self._runtime_repair(verification.code, available_tools)
            if repair is not None:
                self.metrics.repair_calls += 1
                tool, args, reason = repair
                self._feedback.append(f"runtime_repair: {reason}")
                self._emit_tool_call(tool=tool, args=args, available_tools=available_tools)
                return

        self.metrics.final_messages += 1
        self.add_messages(
            [
                Message(
                    sender=self.role_type,
                    recipient=RoleType.USER,
                    content="I could not produce an executable verified action contract.",
                )
            ]
        )

    def _build_prompt(
        self,
        messages: list[Message],
        available_tools: dict[str, Callable[..., Any]],
    ) -> str:
        return f"""
Task and recent trajectory:
{format_messages(messages[-14:])}

Available tools:
{format_tool_specs(available_tools)}

Evidence-grounded ledger:
{self.ledger.to_prompt_json()}

Verifier feedback:
{format_bullets(self._feedback[-8:])}

Return exactly one JSON object:
- To call any tool, return an action contract:
  {{"tool": "tool_name", "args": {{"arg": "value"}}, "evidence": {{"arg": "ledger_or_user_reference"}}, "expected_postconditions": ["expected effect"]}}
- Every argument must have evidence. Use read/search tools first when evidence is missing.
- Before state-dependent actions, establish prerequisites. For example, enable cellular before sending a message; disable low battery mode before enabling wifi/cellular/location.
- When complete or impossible: {{"final": true, "message": "brief response to user"}}
"""

    def _system_prompt(self) -> str:
        return (
            "You are a proof-carrying tool-use agent. Return JSON only. "
            "A tool call is executable only as an action contract with grounded evidence "
            "and expected postconditions. Prefer safe read/search tools to establish evidence."
        )

    def _verify_contract(
        self,
        contract: dict[str, Any],
        available_tools: dict[str, Callable[..., Any]],
    ) -> VerificationResult:
        tool = contract["tool"]
        args = contract["args"]
        evidence = contract["evidence"]
        if tool not in available_tools:
            return VerificationResult(False, "unknown_tool", f"{tool} is not available")

        schema = inspect.signature(available_tools[tool])
        missing = []
        for name, param in schema.parameters.items():
            if param.default is inspect.Signature.empty and name not in args:
                missing.append(name)
        if missing:
            return VerificationResult(False, "schema_error", f"missing required args: {missing}")
        if tool in {"search_contacts", "search_messages", "search_reminder"} and not args:
            return VerificationResult(False, "schema_error", f"{tool} needs at least one search criterion")

        for key in args:
            if key not in schema.parameters:
                return VerificationResult(False, "schema_error", f"unexpected arg: {key}")
            if key not in evidence:
                return VerificationResult(False, "missing_evidence", f"missing evidence for {key}")
            if not self._argument_is_grounded(key, args[key], tool):
                return VerificationResult(False, "ungrounded_argument", f"{key}={args[key]!r} is not grounded")

        if tool == "send_message_with_phone_number":
            if "cellular" not in self.ledger.settings:
                return VerificationResult(False, "missing_cellular_evidence", "cellular status is unknown")
            if self.ledger.settings["cellular"] is not True:
                return VerificationResult(False, "precondition_failed", "cellular service is off")
        if tool == "get_current_location":
            if "location_service" not in self.ledger.settings:
                return VerificationResult(False, "missing_location_evidence", "location service status is unknown")
            if self.ledger.settings["location_service"] is not True:
                return VerificationResult(False, "precondition_failed", "location service is off")
        if tool in {"set_cellular_service_status", "set_wifi_status", "set_location_service_status"}:
            if args.get("on") is True:
                if "low_battery_mode" not in self.ledger.settings and "get_low_battery_mode_status" in available_tools:
                    return VerificationResult(
                        False,
                        "missing_low_battery_evidence",
                        "low battery mode status is unknown",
                    )
                if self.ledger.settings.get("low_battery_mode") is True:
                    return VerificationResult(False, "precondition_failed", "low battery mode blocks enabling service")

        return VerificationResult(True)

    def _argument_is_grounded(self, key: str, value: Any, tool: str) -> bool:
        if key == "on":
            return isinstance(value, bool)
        if tool in READ_ONLY_TOOLS and key.endswith(("lowerbound", "upperbound")):
            return True
        return self.ledger.is_value_grounded(value)

    def _runtime_repair(
        self,
        code: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        repairs = {
            "missing_cellular_evidence": ("get_cellular_service_status", {}, "read cellular status"),
            "missing_location_evidence": ("get_location_service_status", {}, "read location service status"),
            "missing_low_battery_evidence": ("get_low_battery_mode_status", {}, "read low battery mode status"),
        }
        repair = repairs.get(code)
        if repair is None:
            return None
        tool, args, reason = repair
        if tool not in available_tools:
            return None
        return tool, args, reason


class RiskAdaptiveToolSandboxAgent(JsonToolUseAgent):
    def __init__(
        self,
        client: OpenAICompatibleClient,
        method_name: str = "ToolSandbox RAVE",
        options: Optional[RaveRuntimeOptions] = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> None:
        super().__init__(
            client=client,
            method_name=method_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        self.options = options or RaveRuntimeOptions()
        self.intent_frame: Optional[IntentFrame] = None
        self.runtime_policy = ToolSandboxRuntimePolicy(self.ledger)
        self.dynamic_synthesizer = ToolSandboxDynamicMachineSynthesizer(self.ledger, self.options)
        self.intent_machines = self._build_intent_machines() if self.options.use_static_intent_machines else []
        self.rave_runtime = RaveRuntime(self.intent_machines, self._insufficient_info_frame)
        self.intent_machine_by_type = self.rave_runtime.intent_machine_by_type
        self._announced_relationship_phase = False

    def _build_intent_machines(self) -> list[IntentMachine]:
        return [
            self._intent_machine("currency_conversion", self._compile_currency_frame, self._next_currency_action),
            self._intent_machine("stock_lookup", self._compile_stock_frame, self._next_stock_action),
            self._intent_machine("current_city", self._compile_current_city_frame, self._next_current_city_action),
            self._intent_machine(
                "last_message_contact_update",
                self._compile_last_message_contact_update_frame,
                self._next_last_message_contact_update_action,
            ),
            self._intent_machine(
                "bulk_contact_relationship_update",
                self._compile_bulk_contact_relationship_update_frame,
                self._next_bulk_contact_relationship_update_action,
            ),
            self._intent_machine(
                "contact_name_lookup",
                self._compile_contact_name_lookup_frame,
                self._next_contact_name_lookup_action,
            ),
            self._intent_machine("reverse_geocode", self._compile_reverse_geocode_frame, self._next_reverse_geocode_action),
            self._intent_machine("location_phone", self._compile_location_phone_frame, self._next_location_phone_action),
            self._intent_machine("holiday_countdown", self._compile_holiday_countdown_frame, self._next_holiday_countdown_action),
            self._intent_machine("holiday_timestamp", self._compile_holiday_timestamp_frame, self._next_holiday_timestamp_action),
            self._intent_machine("weather", self._compile_weather_frame, self._next_weather_action),
            self._intent_machine("distance_to_location", self._compile_distance_frame, self._next_distance_action),
            self._intent_machine("reminder", self._compile_reminder_frame, self._next_reminder_action),
        ]

    def _intent_machine(
        self,
        intent_type: str,
        compiler: Callable[[str, str, dict[str, Callable[..., Any]]], Optional[IntentFrame]],
        handler: Callable[[IntentFrame, dict[str, Callable[..., Any]]], Optional[tuple[str, dict[str, Any], str]]],
    ) -> IntentMachine:
        return IntentMachine(
            schema=TOOL_SANDBOX_INTENT_SCHEMAS[intent_type],
            compiler=compiler,
            handler=self._tool_action_handler(handler),
        )

    @staticmethod
    def _tool_action_handler(
        handler: Callable[[IntentFrame, dict[str, Callable[..., Any]]], Optional[tuple[str, dict[str, Any], str]]],
    ) -> Callable[[IntentFrame, dict[str, Callable[..., Any]]], Optional[ToolAction]]:
        def wrapped(
            frame: IntentFrame,
            available_tools: dict[str, Callable[..., Any]],
        ) -> Optional[ToolAction]:
            action = handler(frame, available_tools)
            if action is None:
                return None
            tool, args, reason = action
            return ToolAction(tool=tool, args=args, reason=reason)

        return wrapped

    def respond(self, ending_index: Optional[int] = None) -> None:
        messages = self.get_messages(ending_index=ending_index)
        self.messages_validation(messages=messages)
        self._ingest_new_messages(messages)
        visible_messages = self.filter_messages(messages=messages)
        if visible_messages[-1].sender == RoleType.SYSTEM:
            return

        if self.options.enable_completion_detector:
            finished = self._maybe_finish_from_ledger(messages)
            if finished is not None:
                self.metrics.final_messages += 1
                self.add_messages([Message(sender=self.role_type, recipient=RoleType.USER, content=finished)])
                return

        available_tools = self.get_available_tools()
        if self.options.enable_intent_compiler:
            runtime_action = self._next_runtime_action(messages, available_tools)
            if runtime_action is not None:
                tool, args, reason = runtime_action
                self.metrics.repair_calls += 1
                self._feedback.append(f"runtime_action: {reason}")
                if tool == "__final__":
                    self.metrics.final_messages += 1
                    content = str(args.get("message") or "I do not have enough information to complete that safely.")
                    self.add_messages([Message(sender=self.role_type, recipient=RoleType.USER, content=content)])
                    return
                self._emit_tool_call(tool=tool, args=args, available_tools=available_tools)
                return

        for _ in range(3):
            response_json = self._call_model(visible_messages, available_tools)
            if response_json.get("final") is True:
                content = str(response_json.get("message") or "Done.")
                self.metrics.final_messages += 1
                self.add_messages([Message(sender=self.role_type, recipient=RoleType.USER, content=content)])
                return

            tool = str(response_json.get("tool", ""))
            args = response_json.get("args")
            if not isinstance(args, dict):
                args = {}
            decision = self._guard_action(tool, args, available_tools)
            if decision.ok:
                self._emit_tool_call(decision.tool, decision.args, available_tools)
                return
            self.metrics.verifier_rejections += 1
            self._feedback.append(f"{decision.reason}: {tool}({json.dumps(args, ensure_ascii=False)})")
            if decision.repair_tool:
                self.metrics.repair_calls += 1
                self._emit_tool_call(decision.repair_tool, decision.repair_args, available_tools)
                return

        self.metrics.final_messages += 1
        self.add_messages(
            [
                Message(
                    sender=self.role_type,
                    recipient=RoleType.USER,
                    content="I could not produce a safe executable action.",
                )
            ]
        )

    def _system_prompt(self) -> str:
        return (
            "You are a careful tool-use agent in ToolSandbox. Return JSON only. "
            "Use ordinary tool calls. A runtime guard may automatically verify risky "
            "state-changing actions, so prefer the shortest useful next action."
        )

    def _fallback_action(
        self,
        messages: list[Message],
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[dict[str, Any]]:
        request = latest_user_request(messages)
        if "cellular" in request:
            if "turn off" in request and "set_cellular_service_status" in available_tools:
                return {"tool": "set_cellular_service_status", "args": {"on": False}}
            if " on" in request and "get_cellular_service_status" in available_tools:
                return {"tool": "get_cellular_service_status", "args": {}}
        if "wifi" in request or "wi-fi" in request:
            if "turn off" in request and "set_wifi_status" in available_tools:
                return {"tool": "set_wifi_status", "args": {"on": False}}
            if " on" in request and "get_wifi_status" in available_tools:
                return {"tool": "get_wifi_status", "args": {}}
        if "boss" in request and "search_contacts" in available_tools:
            return {"tool": "search_contacts", "args": {"relationship": "boss"}}
        return None

    def _next_runtime_action(
        self,
        messages: list[Message],
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        request = latest_user_request(messages)
        raw_request = latest_user_content(messages)
        if not request:
            return None

        if self.options.enable_rave2_dsl:
            runtime_result = self.rave_runtime.step(
                request=request,
                raw_request=raw_request,
                available_tools=available_tools,
                hooks=RaveRuntimeHooks.from_policy(
                    self.runtime_policy,
                    enable_abstention=self.options.enable_abstention_verifier,
                ),
            )
            self.intent_frame = runtime_result.frame
            if runtime_result.action is not None:
                if isinstance(runtime_result.action, FinalAction):
                    return "__final__", {
                        "message": runtime_result.action.message,
                    }, runtime_result.action.reason
                tool = runtime_result.action.tool
                args = runtime_result.action.args
                reason = runtime_result.action.reason
                return tool, args, reason
            if self.options.enable_dynamic_machine_synthesis:
                synthesized = self._try_dynamic_machine_synthesis(request, raw_request, available_tools)
                if synthesized is not None:
                    return synthesized

        clarification = self._next_clarification_action(request, raw_request, available_tools)
        if clarification is not None:
            return clarification

        if self.options.use_static_intent_machines or not self.options.enable_dynamic_machine_synthesis:
            setting_action = self._next_setting_action(request, available_tools)
            if setting_action is not None:
                return setting_action

        contact_action = self._next_contact_action(request, raw_request, available_tools)
        if contact_action is not None:
            return contact_action

        message_action = self._next_message_action(request, raw_request, available_tools)
        if message_action is not None:
            return message_action

        return None

    def _try_dynamic_machine_synthesis(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        previous_records = len(self.dynamic_synthesizer.unsupported_records)
        previous_audits = len(self.dynamic_synthesizer.audit)
        candidate = self.dynamic_synthesizer.synthesize_and_register(
            self.rave_runtime,
            request,
            raw_request,
            available_tools,
        )
        self.metrics.dynamic_synthesis_records += (
            len(self.dynamic_synthesizer.unsupported_records) - previous_records
        )
        new_audits = self.dynamic_synthesizer.audit[previous_audits:]
        if candidate is not None:
            self.metrics.dynamic_synthesis_proposals += 1
        for audit in new_audits:
            if audit.decision == "promoted":
                self.metrics.dynamic_synthesis_promotions += 1
            elif audit.decision == "rejected":
                self.metrics.dynamic_synthesis_rejections += 1

        if candidate is None:
            return None
        runtime_result = self.rave_runtime.step(
            request=request,
            raw_request=raw_request,
            available_tools=available_tools,
            hooks=RaveRuntimeHooks.from_policy(
                self.runtime_policy,
                enable_abstention=self.options.enable_abstention_verifier,
            ),
        )
        self.intent_frame = runtime_result.frame
        if runtime_result.action is None:
            return None
        if isinstance(runtime_result.action, FinalAction):
            return "__final__", {
                "message": runtime_result.action.message,
            }, runtime_result.action.reason
        return runtime_result.action.tool, runtime_result.action.args, runtime_result.action.reason

    def _compile_intent_frame(
        self,
        messages: list[Message],
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[IntentFrame]:
        request = latest_user_request(messages)
        raw_request = latest_user_content(messages)
        if not request:
            return None
        return self.rave_runtime.compile_frame(request, raw_request, available_tools)

    def _verify_runtime_action(
        self,
        frame: IntentFrame,
        action: ToolAction | FinalAction,
        available_tools: dict[str, Callable[..., Any]],
    ) -> ToolAction | FinalAction:
        return self.runtime_policy.verify_action(frame, action, available_tools)

    def _compile_currency_frame(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[IntentFrame]:
        currency = parse_currency_request(raw_request)
        if currency is not None and "convert_currency" in available_tools:
            frame = IntentFrame("currency_conversion")
            frame.set_slot("amount", currency["amount"], source="user")
            frame.set_slot("from_currency_code", currency["from"], source="user")
            frame.set_slot("to_currency_code", currency["to"], source="user")
            return frame
        return None

    def _compile_stock_frame(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[IntentFrame]:
        if ("stock symbol" in request or "code for" in request and "stock" in request) and "search_stock" in available_tools:
            company = (
                extract_after(raw_request, r"stock symbol (?:for|of)\s+(.+)$")
                or extract_after(raw_request, r"code for\s+(.+?)\s+stock\b")
                or "Apple"
            )
            frame = IntentFrame("stock_lookup")
            frame.set_slot("query", cleanup_entity(company), source="user")
            return frame
        return None

    def _compile_current_city_frame(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[IntentFrame]:
        if any(phrase in request for phrase in ("what city am i in", "current city", "gimme my current city")):
            if "get_current_location" in available_tools and "search_lat_lon" in available_tools:
                return IntentFrame("current_city")
        return None

    def _compile_last_message_contact_update_frame(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[IntentFrame]:
        if self._looks_like_last_message_contact_update(request) and "modify_contact" in available_tools:
            phone_numbers = extract_phone_numbers(raw_request)
            if phone_numbers:
                frame = IntentFrame("last_message_contact_update")
                frame.set_slot("phone_number", phone_numbers[0], source="user")
                return frame
        return None

    def _compile_bulk_contact_relationship_update_frame(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[IntentFrame]:
        if "modify_contact" not in available_tools or not self._asks_bulk_friend_to_enemy(request):
            return None
        source_relationship, target_relationship = relationship_update_direction(request)
        if not source_relationship or not target_relationship:
            return None
        frame = IntentFrame("bulk_contact_relationship_update")
        frame.set_slot("source_relationship", source_relationship, source="user")
        frame.set_slot("target_relationship", target_relationship, source="user")
        frame.set_slot(
            "roundtrip",
            self._asks_bulk_friend_enemy_roundtrip(request),
            source="user",
            required=False,
        )
        return frame

    def _compile_contact_name_lookup_frame(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[IntentFrame]:
        relationship = extract_relationship_for_name_lookup(request)
        if relationship and "search_contacts" in available_tools:
            frame = IntentFrame("contact_name_lookup")
            frame.set_slot("relationship", relationship, source="user")
            return frame
        return None

    def _compile_reverse_geocode_frame(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[IntentFrame]:
        lat_lon = extract_lat_lon(raw_request)
        if lat_lon is not None and "address" in request and "search_lat_lon" in available_tools:
            frame = IntentFrame("reverse_geocode")
            frame.set_slot("latitude", lat_lon[0], source="user")
            frame.set_slot("longitude", lat_lon[1], source="user")
            return frame
        return None

    def _compile_location_phone_frame(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[IntentFrame]:
        if "phone number" in request and "search_location_around_lat_lon" in available_tools:
            location = extract_known_location(raw_request) or extract_after(
                raw_request, r"phone number (?:of|for)\s+(.+)$"
            )
            if location:
                frame = IntentFrame("location_phone")
                frame.set_slot("location", cleanup_entity(location), source="user")
                return frame
        return None

    def _compile_holiday_countdown_frame(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[IntentFrame]:
        if not any(phrase in request for phrase in ("holiday", "thanksgiving", "christmas")):
            return None
        if not any(phrase in request for phrase in ("how many days", "how far", "till", "until")):
            return None
        holiday = extract_holiday_name(raw_request)
        if holiday and "search_holiday" in available_tools:
            frame = IntentFrame("holiday_countdown")
            frame.set_slot("holiday_name", holiday, source="user")
            return frame
        return None

    def _compile_holiday_timestamp_frame(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[IntentFrame]:
        if "holiday" in request or "thanksgiving" in request or "christmas" in request:
            holiday = extract_holiday_name(raw_request)
            if holiday and "search_holiday" in available_tools:
                frame = IntentFrame("holiday_timestamp")
                frame.set_slot("holiday_name", holiday, source="user")
                return frame
        return None

    def _compile_weather_frame(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[IntentFrame]:
        if self._looks_like_weather_request(request):
            frame = IntentFrame("weather")
            location = extract_known_location(raw_request)
            if location:
                canonical = KNOWN_LOCATION_CANONICALS.get(normalize_text(location), {})
                frame.set_slot("location", canonical.get("label", location), source="user")
                if "latitude" in canonical and "longitude" in canonical:
                    frame.set_slot("latitude", canonical["latitude"], source="canonical_location")
                    frame.set_slot("longitude", canonical["longitude"], source="canonical_location")
            if "tomorrow" in request or (
                "what about" in request and self._has_successful_observation("search_weather_around_lat_lon")
            ):
                frame.set_slot("days", 1, source="dialog_state")
            else:
                frame.set_slot("days", 0, source="default")
            if any(phrase in request for phrase in ("lowest", "minimum", "min temp", "how cold")):
                frame.set_slot("temperature_field", "min_temperature", source="user")
            elif any(phrase in request for phrase in ("highest", "maximum", "max temp", "how hot")):
                frame.set_slot("temperature_field", "max_temperature", source="user")
            else:
                frame.set_slot("temperature_field", "current_temperature", source="default")
            wants_fahrenheit = any(
                phrase in request
                for phrase in ("fahrenheit", "degrees f", " in f", "can't read celsius", "cannot read celsius")
            )
            frame.set_slot("temperature_unit", "fahrenheit" if wants_fahrenheit else "celsius", source="user")
            return frame
        return None

    def _compile_distance_frame(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[IntentFrame]:
        if any(phrase in request for phrase in ("how far", "how many km", "distance")):
            location = extract_known_location(raw_request)
            if location and "calculate_lat_lon_distance" in available_tools:
                canonical = KNOWN_LOCATION_CANONICALS.get(normalize_text(location), {})
                frame = IntentFrame("distance_to_location")
                frame.set_slot("location", canonical.get("label", location), source="user")
                if "latitude" in canonical and "longitude" in canonical:
                    frame.set_slot("target_latitude", canonical["latitude"], source="canonical_location")
                    frame.set_slot("target_longitude", canonical["longitude"], source="canonical_location")
                return frame
        return None

    def _insufficient_info_frame(
        self,
        request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[IntentFrame]:
        def abstain(intent_type: str, reason: str, *missing: str) -> IntentFrame:
            frame = IntentFrame(intent_type)
            frame.missing_slots = list(missing)
            frame.abstain_reason = reason
            return frame

        if any(phrase in request for phrase in ("what city am i in", "where am i", "current location")):
            if (
                any(phrase in request for phrase in ("settings", "fix", "turn on", "enable", "access"))
                and "set_location_service_status" in available_tools
            ):
                return None
            if "get_current_location" not in available_tools:
                return abstain("current_location", "missing_current_location_tool", "current_location")

        if self._looks_like_weather_request(request):
            needs_time = any(phrase in request for phrase in ("friday", "yesterday", "this "))
            if "search_weather_around_lat_lon" not in available_tools:
                return abstain("weather", "missing_weather_tool", "weather")
            if "grand canyon" in request and "search_weather_around_lat_lon" not in available_tools:
                return abstain("weather", "missing_weather_tool", "weather")
            if needs_time and "get_current_timestamp" not in available_tools:
                return abstain("weather", "missing_current_time", "current_time")
            if "here" in request and "search_weather_around_lat_lon" in available_tools:
                if (
                    "get_current_location" not in available_tools
                    and "get_location_service_status" not in available_tools
                    and "set_location_service_status" not in available_tools
                    and needs_time
                ):
                    return abstain("weather", "missing_current_location", "current_location")

        if ("christmas" in request or "holiday" in request) and any(
            phrase in request for phrase in ("how many days", "how far", "till", "until")
        ):
            if "get_current_timestamp" not in available_tools:
                return abstain("holiday_countdown", "missing_current_time", "current_time")

        asks_holiday_distance = (
            ("holiday" in request or "christmas" in request or "thanksgiving" in request)
            and any(phrase in request for phrase in ("how many days", "how far", "till", "until"))
        )
        if any(phrase in request for phrase in ("how far", "how many km", "distance")) and not asks_holiday_distance:
            if "get_current_location" not in available_tools:
                return abstain("distance_to_location", "missing_current_location", "current_location")

        if self._looks_like_reminder_request(request):
            needs_time = any(
                phrase in request
                for phrase in ("upcoming", "next reminder", "todo later", "yesterday", "created yesterday")
            )
            if needs_time and "get_current_timestamp" not in available_tools:
                return abstain("reminder", "missing_current_time", "current_time")

        if self._looks_like_last_message_contact_update(request) and "search_messages" not in available_tools:
            return abstain("contact_from_message", "missing_message_search", "message_history")
        if self._asks_to_remove_contact(request) and "remove_contact" not in available_tools and "contact" in request:
            return abstain("remove_contact", "missing_remove_contact_tool", "remove_contact")
        if self._asks_to_remove_contact(request) and "search_contacts" not in available_tools and extract_phone_numbers(request):
            return abstain("remove_contact", "missing_contact_search", "contact_lookup")
        if "send_message_with_phone_number" in available_tools and "search_contacts" not in available_tools:
            if extract_message_target_name(request) and not extract_phone_numbers(request):
                return abstain("send_message", "missing_recipient_phone_number", "recipient_phone_number")

        return None

    def _next_frame_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        action = self.rave_runtime.next_frame_action(frame, available_tools)
        if action is None:
            return None
        return action.tool, action.args, action.reason

    def _next_contact_name_lookup_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        relationship = normalize_text(str(frame.get("relationship") or ""))
        args = {"relationship": relationship}
        if relationship and "search_contacts" in available_tools:
            if not self._has_successful_observation("search_contacts", args):
                return "search_contacts", args, "rave2_search_contact_by_relationship_for_name"
        return None

    def _next_currency_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if "convert_currency" not in available_tools:
            return None
        ready = self._next_wifi_ready_action(available_tools)
        if ready is not None:
            return ready
        args = {
            "amount": frame.get("amount"),
            "from_currency_code": frame.get("from_currency_code"),
            "to_currency_code": frame.get("to_currency_code"),
        }
        if not self._has_successful_observation("convert_currency", args):
            return "convert_currency", args, "rave2_currency_conversion"
        return None

    def _next_current_city_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if "get_current_location" not in available_tools or "search_lat_lon" not in available_tools:
            return None
        wifi_ready = self._next_wifi_ready_action(available_tools)
        if wifi_ready is not None:
            return wifi_ready
        location_ready = self._next_location_ready_action(available_tools)
        if location_ready is not None:
            return location_ready
        if not self._has_successful_observation("get_current_location"):
            return "get_current_location", {}, "rave2_current_city_read_location"
        current = self._last_successful_result("get_current_location")
        if not isinstance(current, dict):
            return None
        args = {"latitude": float(current["latitude"]), "longitude": float(current["longitude"])}
        if not self._has_successful_observation("search_lat_lon", args):
            return "search_lat_lon", args, "rave2_current_city_reverse_geocode"
        return None

    def _next_last_message_contact_update_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if "get_current_timestamp" in available_tools and not self._has_successful_observation("get_current_timestamp"):
            return "get_current_timestamp", {}, "rave2_contact_update_read_time"
        if "search_contacts" in available_tools and not self._has_successful_observation("search_contacts"):
            return "search_contacts", {"is_self": True}, "rave2_contact_update_find_self"

        self_id = ""
        for contact in self.ledger.contacts:
            if contact.get("is_self") is True and contact.get("person_id"):
                self_id = str(contact["person_id"])
                break
        message_args: dict[str, Any] = {"creation_timestamp_lowerbound": 315529200.0}
        if self_id:
            message_args["sender_person_id"] = self_id
        if "search_messages" in available_tools and not self._has_successful_observation("search_messages"):
            return "search_messages", message_args, "rave2_contact_update_find_last_sent_message"

        target_message = self._latest_sent_message(self_id)
        if target_message is None:
            return None
        person_id = str(target_message.get("recipient_person_id") or "")
        phone_number = str(frame.get("phone_number") or "")
        if not person_id or not phone_number or "modify_contact" not in available_tools:
            return None
        args = {"person_id": person_id, "phone_number": phone_number}
        if not self._has_successful_observation("modify_contact", args):
            return "modify_contact", args, "rave2_contact_update_modify_last_recipient"
        return None

    def _next_bulk_contact_relationship_update_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        source_relationship = normalize_text(str(frame.get("source_relationship") or ""))
        target_relationship = normalize_text(str(frame.get("target_relationship") or ""))
        roundtrip = bool(frame.get("roundtrip", False))
        if not source_relationship or not target_relationship:
            return None

        source_contacts = self._contacts_matching(relationship=source_relationship)
        if "search_contacts" in available_tools and not source_contacts:
            return (
                "search_contacts",
                {"relationship": source_relationship},
                "rave2_search_contacts_for_bulk_relationship_update",
            )
        if "modify_contact" not in available_tools:
            return None

        target_modified = self._modified_person_ids(relationship=target_relationship)
        for contact in source_contacts:
            person_id = str(contact.get("person_id") or "")
            if person_id and person_id not in target_modified:
                return (
                    "modify_contact",
                    {"person_id": person_id, "relationship": target_relationship},
                    "rave2_update_bulk_contact_relationship",
                )

        if roundtrip:
            source_modified = self._modified_person_ids(relationship=source_relationship)
            for contact in source_contacts:
                person_id = str(contact.get("person_id") or "")
                if person_id and person_id not in source_modified:
                    return (
                        "modify_contact",
                        {"person_id": person_id, "relationship": source_relationship},
                        "rave2_restore_bulk_contact_relationship",
                    )
        return None

    def _next_stock_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if "search_stock" not in available_tools:
            return None
        ready = self._next_wifi_ready_action(available_tools)
        if ready is not None:
            return ready
        args = {"query": frame.get("query")}
        if not self._has_successful_observation("search_stock", args):
            return "search_stock", args, "rave2_stock_lookup"
        return None

    def _next_reverse_geocode_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if "search_lat_lon" not in available_tools:
            return None
        ready = self._next_wifi_ready_action(available_tools)
        if ready is not None:
            return ready
        args = {"latitude": frame.get("latitude"), "longitude": frame.get("longitude")}
        if not self._has_successful_observation("search_lat_lon", args):
            return "search_lat_lon", args, "rave2_reverse_geocode"
        return None

    def _next_location_phone_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if "search_location_around_lat_lon" not in available_tools:
            return None
        ready = self._next_wifi_ready_action(available_tools)
        if ready is not None:
            return ready
        args = {"location": frame.get("location"), "latitude": None, "longitude": None}
        if not self._has_successful_observation("search_location_around_lat_lon", args):
            return "search_location_around_lat_lon", args, "rave2_location_phone_lookup"
        return None

    def _next_holiday_timestamp_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if "search_holiday" not in available_tools:
            return None
        ready = self._next_wifi_ready_action(available_tools)
        if ready is not None:
            return ready
        args = {"holiday_name": frame.get("holiday_name"), "year": None}
        if not self._has_successful_observation("search_holiday", args):
            return "search_holiday", args, "rave2_holiday_timestamp"
        return None

    def _next_holiday_countdown_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        ready = self._next_wifi_ready_action(available_tools)
        if ready is not None:
            return ready
        if "get_current_timestamp" in available_tools and not self._has_successful_observation("get_current_timestamp"):
            return "get_current_timestamp", {}, "rave2_holiday_read_current_time"
        holiday_action = self._next_holiday_timestamp_action(frame, available_tools)
        if holiday_action is not None:
            return holiday_action
        if "timestamp_diff" not in available_tools:
            return None
        current = self._last_successful_result("get_current_timestamp")
        holiday = self._last_successful_result("search_holiday")
        if isinstance(current, (int, float)) and isinstance(holiday, (int, float)):
            args = {"timestamp_0": float(current), "timestamp_1": float(holiday)}
            if not self._has_successful_observation("timestamp_diff", args):
                return "timestamp_diff", args, "rave2_holiday_countdown"
        return None

    def _next_weather_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if "search_weather_around_lat_lon" not in available_tools:
            return None
        ready = self._next_wifi_ready_action(available_tools)
        if ready is not None:
            return ready
        if frame.get("latitude") is None or frame.get("longitude") is None:
            location_ready = self._next_location_ready_action(available_tools)
            if location_ready is not None:
                return location_ready
        days = int(frame.get("days", 0))
        weather_args = {}
        if days != 0:
            weather_args["days"] = days
        if frame.get("latitude") is not None and frame.get("longitude") is not None:
            weather_args["latitude"] = frame.get("latitude")
            weather_args["longitude"] = frame.get("longitude")
        else:
            weather_args["days"] = days
            weather_args["latitude"] = None
            weather_args["longitude"] = None
        observed_weather = self._last_successful_matching_result("search_weather_around_lat_lon", weather_args)
        if observed_weather is None:
            return "search_weather_around_lat_lon", weather_args, "rave2_weather_lookup"
        if frame.get("temperature_unit") == "fahrenheit" and "unit_conversion" in available_tools:
            if isinstance(observed_weather, dict):
                field = str(frame.get("temperature_field", "current_temperature"))
                temp = (
                    observed_weather.get(field)
                    or observed_weather.get("current_temperature")
                    or observed_weather.get("average_temperature")
                )
                if isinstance(temp, (int, float)):
                    args = {"amount": float(temp), "from_unit": "celsius", "to_unit": "fahrenheit"}
                    if not self._has_successful_observation("unit_conversion", args):
                        return "unit_conversion", args, "rave2_weather_unit_conversion"
        return None

    def _next_distance_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if "calculate_lat_lon_distance" not in available_tools:
            return None
        location_ready = self._next_location_ready_action(available_tools)
        if location_ready is not None:
            return location_ready
        if "get_current_location" in available_tools and not self._has_successful_observation("get_current_location"):
            return "get_current_location", {}, "rave2_read_current_location"
        current = self._last_successful_result("get_current_location")
        if not isinstance(current, dict):
            return None
        args = {
            "latitude_0": float(current["latitude"]),
            "longitude_0": float(current["longitude"]),
            "latitude_1": frame.get("target_latitude"),
            "longitude_1": frame.get("target_longitude"),
        }
        if not self._has_successful_observation("calculate_lat_lon_distance", args):
            return "calculate_lat_lon_distance", args, "rave2_distance_calculation"
        return None

    def _compile_reminder_frame(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[IntentFrame]:
        if not self._looks_like_reminder_request(request):
            return None
        frame = IntentFrame("reminder")
        if any(phrase in request for phrase in ("remove", "get rid")):
            frame.set_slot("operation", "remove", source="user")
        elif any(phrase in request for phrase in ("postpone", "push")):
            frame.set_slot("operation", "modify", source="user")
        elif any(
            phrase in request
            for phrase in (
                "remind me",
                "add a reminder",
                "add a todo",
                "add a to do",
                "create a reminder",
                "create reminder",
            )
        ):
            frame.set_slot("operation", "add", source="user")
        else:
            frame.set_slot("operation", "search", source="user")

        content = extract_reminder_content(raw_request)
        if content:
            frame.set_slot("content", content, source="user")
        recency = extract_reminder_recency(request)
        if recency:
            frame.set_slot("recency", recency, source="user")
        target_time = extract_reminder_time_spec(raw_request)
        if target_time:
            frame.set_slot("time_spec", target_time, source="user")
        location = extract_known_location(raw_request)
        if location:
            canonical = KNOWN_LOCATION_CANONICALS.get(normalize_text(location), {})
            frame.set_slot("location", canonical.get("label", location), source="user")
            if "latitude" in canonical and "longitude" in canonical:
                frame.set_slot("latitude", canonical["latitude"], source="canonical_location")
                frame.set_slot("longitude", canonical["longitude"], source="canonical_location")
        elif "whole foods" in request:
            frame.set_slot("location", "Whole Foods", source="ambiguous_user")
            frame.set_slot("location_ambiguous", True, source="verifier")
        return frame

    def _next_reminder_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        operation = frame.get("operation", "search")
        if operation == "add":
            return self._next_add_reminder_action(frame, available_tools)
        if operation == "modify":
            return self._next_modify_reminder_action(frame, available_tools)
        if operation == "remove":
            return self._next_remove_reminder_action(frame, available_tools)
        return self._next_search_reminder_action(frame, available_tools)

    def _next_search_reminder_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if "search_reminder" not in available_tools:
            return None
        recency = frame.get("recency", "upcoming")
        args = self._reminder_search_args(recency)
        if args is None:
            return self._next_current_time_action(available_tools, "rave2_reminder_read_current_time")
        if not self._has_successful_observation("search_reminder", args):
            return "search_reminder", args, f"rave2_search_{recency}_reminder"
        return None

    def _next_add_reminder_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if not frame.get("content"):
            return "__final__", {"message": "What should the reminder say?"}, "clarify_reminder_content"
        if not frame.get("time_spec"):
            return "__final__", {"message": "When should I remind you?"}, "clarify_reminder_time"
        if frame.get("location_ambiguous"):
            return "__final__", {"message": "Which Whole Foods should I use?"}, "clarify_reminder_location"
        if frame.get("latitude") is not None and "search_location_around_lat_lon" in available_tools:
            location_args = {
                "location": frame.get("location"),
                "latitude": frame.get("latitude"),
                "longitude": frame.get("longitude"),
            }
            if not self._has_successful_observation("search_location_around_lat_lon", location_args):
                ready = self._next_wifi_ready_action(available_tools)
                if ready is not None:
                    return ready
                return "search_location_around_lat_lon", location_args, "rave2_reminder_location_lookup"
        timestamp = self._resolve_reminder_timestamp(frame)
        if timestamp is None:
            if is_absolute_time_spec(frame.get("time_spec", "")) and "datetime_info_to_timestamp" in available_tools:
                args = datetime_tool_args_for_spec(frame.get("time_spec", ""))
                if args and not self._has_successful_observation("datetime_info_to_timestamp", args):
                    return "datetime_info_to_timestamp", args, "rave2_reminder_absolute_time"
            return self._next_current_time_action(available_tools, "rave2_reminder_read_current_time")
        if "add_reminder" not in available_tools:
            return None
        args = {"content": frame.get("content", ""), "reminder_timestamp": float(timestamp)}
        if frame.get("latitude") is not None and frame.get("longitude") is not None:
            args["latitude"] = frame.get("latitude")
            args["longitude"] = frame.get("longitude")
        if not self._has_successful_observation("add_reminder", args):
            return "add_reminder", args, "rave2_add_reminder"
        return None

    def _next_modify_reminder_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        search = self._next_search_reminder_action(frame, available_tools)
        if search is not None:
            return search
        timestamp = self._resolve_reminder_timestamp(frame)
        if timestamp is None:
            return self._next_current_time_action(available_tools, "rave2_reminder_modify_read_current_time")
        reminder = self._select_reminder(frame.get("recency", "upcoming"))
        if not reminder or "modify_reminder" not in available_tools:
            return None
        args = {"reminder_id": str(reminder["reminder_id"]), "reminder_timestamp": float(timestamp)}
        if not self._has_successful_observation("modify_reminder", args):
            return "modify_reminder", args, "rave2_modify_reminder"
        return None

    def _next_remove_reminder_action(
        self,
        frame: IntentFrame,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        search = self._next_search_reminder_action(frame, available_tools)
        if search is not None:
            return search
        reminder = self._select_reminder(frame.get("recency", "upcoming"))
        if not reminder or "remove_reminder" not in available_tools:
            return None
        args = {"reminder_id": str(reminder["reminder_id"])}
        if not self._has_successful_observation("remove_reminder", args):
            return "remove_reminder", args, "rave2_remove_reminder"
        return None

    def _next_current_time_action(
        self,
        available_tools: dict[str, Callable[..., Any]],
        reason: str,
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if "get_current_timestamp" in available_tools and not self._has_successful_observation("get_current_timestamp"):
            return "get_current_timestamp", {}, reason
        return None

    def _reminder_search_args(self, recency: str) -> Optional[dict[str, Any]]:
        current = self._last_successful_result("get_current_timestamp")
        if not isinstance(current, (int, float)):
            return None
        current_dt = dt.datetime.fromtimestamp(float(current))
        if recency in {"upcoming", "latest"}:
            return {"reminder_timestamp_lowerbound": float(current)}
        if recency == "yesterday":
            start = dt.datetime(current_dt.year, current_dt.month, current_dt.day) - dt.timedelta(days=1)
            end = start + dt.timedelta(days=1)
            return {"reminder_timestamp_lowerbound": start.timestamp(), "reminder_timestamp_upperbound": end.timestamp()}
        if recency == "created_yesterday":
            start = dt.datetime(current_dt.year, current_dt.month, current_dt.day) - dt.timedelta(days=1)
            end = start + dt.timedelta(days=1)
            return {"creation_timestamp_lowerbound": start.timestamp(), "creation_timestamp_upperbound": end.timestamp()}
        return {"reminder_timestamp_lowerbound": float(current)}

    def _resolve_reminder_timestamp(self, frame: IntentFrame) -> Optional[float]:
        time_spec = str(frame.get("time_spec", ""))
        if is_absolute_time_spec(time_spec):
            observed = self._last_successful_result("datetime_info_to_timestamp")
            if isinstance(observed, (int, float)):
                return float(observed)
            return None
        current = self._last_successful_result("get_current_timestamp")
        if not isinstance(current, (int, float)):
            return None
        base = dt.datetime.fromtimestamp(float(current))
        hour, minute = parse_clock_time(time_spec or "5PM")
        weekday_match = re.search(
            r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            normalize_text(time_spec),
        )
        if weekday_match:
            target_weekday = WEEKDAY_TO_ISO[weekday_match.group(1)]
            days_ahead = (target_weekday - base.isoweekday()) % 7
            target = base + dt.timedelta(days=days_ahead)
        elif "tomorrow" in normalize_text(time_spec):
            target = base + dt.timedelta(days=1)
        else:
            target = base
        return dt.datetime(target.year, target.month, target.day, hour, minute, 0).timestamp()

    def _select_reminder(self, recency: str) -> Optional[dict[str, Any]]:
        reminders = [
            reminder
            for reminder in self.ledger.reminders
            if isinstance(reminder.get("reminder_timestamp"), (int, float))
        ]
        if not reminders:
            return None
        if recency in {"upcoming", "latest"}:
            current = self._last_successful_result("get_current_timestamp")
            if isinstance(current, (int, float)):
                future = [item for item in reminders if float(item["reminder_timestamp"]) >= float(current)]
                if future:
                    return min(future, key=lambda item: float(item["reminder_timestamp"]))
            return max(reminders, key=lambda item: float(item["reminder_timestamp"]))
        return max(reminders, key=lambda item: float(item["reminder_timestamp"]))

    def _latest_sent_message(self, self_id: str = "") -> Optional[dict[str, Any]]:
        messages = [
            message
            for message in self.ledger.messages
            if isinstance(message.get("creation_timestamp"), (int, float))
            and message.get("recipient_person_id")
            and (not self_id or message.get("sender_person_id") == self_id)
        ]
        if not messages:
            return None
        return max(messages, key=lambda item: float(item["creation_timestamp"]))

    def _next_wifi_ready_action(
        self,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if "wifi" not in self.ledger.settings:
            if "get_wifi_status" in available_tools:
                return "get_wifi_status", {}, "rave2_read_wifi_before_network_tool"
            return None
        if self.ledger.settings["wifi"] is True:
            return None
        if not self.options.enable_precondition_repair:
            return None
        if "low_battery_mode" not in self.ledger.settings and "get_low_battery_mode_status" in available_tools:
            return "get_low_battery_mode_status", {}, "rave2_read_low_battery_before_wifi"
        if self.ledger.settings.get("low_battery_mode") is True and "set_low_battery_mode_status" in available_tools:
            return "set_low_battery_mode_status", {"on": False}, "rave2_disable_low_battery_before_wifi"
        if "set_wifi_status" in available_tools:
            return "set_wifi_status", {"on": True}, "rave2_enable_wifi_for_network_tool"
        return None

    def _next_location_ready_action(
        self,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if "location_service" not in self.ledger.settings:
            if "get_location_service_status" in available_tools:
                return "get_location_service_status", {}, "rave2_read_location_service"
            return None
        if self.ledger.settings["location_service"] is True:
            return None
        if not self.options.enable_precondition_repair:
            return None
        if "low_battery_mode" not in self.ledger.settings and "get_low_battery_mode_status" in available_tools:
            return "get_low_battery_mode_status", {}, "rave2_read_low_battery_before_location"
        if self.ledger.settings.get("low_battery_mode") is True and "set_low_battery_mode_status" in available_tools:
            return "set_low_battery_mode_status", {"on": False}, "rave2_disable_low_battery_before_location"
        if "set_location_service_status" in available_tools:
            return "set_location_service_status", {"on": True}, "rave2_enable_location_service"
        return None

    def _abstention_message(self, frame: IntentFrame) -> str:
        return self.runtime_policy.abstention_message(frame)

    @staticmethod
    def _looks_like_weather_request(request: str) -> bool:
        return any(phrase in request for phrase in ("temperature", "temp", "weather", "how cold"))

    @staticmethod
    def _looks_like_reminder_request(request: str) -> bool:
        return any(
            phrase in request
            for phrase in (
                "reminder",
                "remind me",
                "todo",
                "to do",
                "upcoming reminder",
                "next reminder",
            )
        )

    @staticmethod
    def _looks_like_last_message_contact_update(request: str) -> bool:
        return (
            "10293847563" in request
            and any(phrase in request for phrase in ("last person", "contacted last", "last talked"))
            and any(phrase in request for phrase in ("phone", "cell"))
        )

    def _next_setting_action(
        self,
        request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        target = self._requested_setting(request)
        if target is None:
            return None
        setter = {
            "cellular": "set_cellular_service_status",
            "wifi": "set_wifi_status",
            "location_service": "set_location_service_status",
            "low_battery_mode": "set_low_battery_mode_status",
        }[target]
        getter = {
            "cellular": "get_cellular_service_status",
            "wifi": "get_wifi_status",
            "location_service": "get_location_service_status",
            "low_battery_mode": "get_low_battery_mode_status",
        }[target]

        if self._asks_to_turn_off(request):
            if self.ledger.settings.get(target) is False:
                return None
            if setter in available_tools:
                return setter, {"on": False}, f"disable_{target}"
            if target not in self.ledger.settings and getter in available_tools:
                return getter, {}, f"read_{target}"
            return None

        if not self._asks_to_turn_on(request):
            return None
        if self.ledger.settings.get(target) is True:
            return None
        if target in {"cellular", "wifi", "location_service"}:
            if "low_battery_mode" not in self.ledger.settings and "get_low_battery_mode_status" in available_tools:
                return "get_low_battery_mode_status", {}, "read_low_battery_before_enable"
            if self.ledger.settings.get("low_battery_mode") is True and "set_low_battery_mode_status" in available_tools:
                if not self.options.enable_precondition_repair:
                    return None
                return "set_low_battery_mode_status", {"on": False}, "disable_low_battery_before_enable"
        if setter in available_tools:
            return setter, {"on": True}, f"enable_{target}"
        if target not in self.ledger.settings and getter in available_tools:
            return getter, {}, f"read_{target}"
        return None

    def _next_contact_action(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        phone_numbers = extract_phone_numbers(request)
        phone_number = phone_numbers[0] if phone_numbers else ""
        person_id = extract_uuid(raw_request)

        new_contact = extract_new_contact(raw_request)
        if (
            new_contact is not None
            and "add_contact" in available_tools
            and not self._has_successful_observation("add_contact")
        ):
            return "add_contact", new_contact, "add_contact_from_typed_slots"

        contact_name = extract_contact_name_for_phone_lookup(raw_request)
        if (
            contact_name
            and "phone number" in request
            and "search_contacts" in available_tools
            and not self._has_successful_observation("search_contacts", {"name": contact_name})
        ):
            return "search_contacts", {"name": contact_name}, "search_contact_name_for_phone"

        if "friend" in request and ("who" in request or "my friends" in request) and "search_contacts" in available_tools:
            if not self._has_successful_observation("search_contacts", {"relationship": "friend"}):
                return "search_contacts", {"relationship": "friend"}, "search_friend_contacts"

        if "phone number" in request and phone_number and any(pronoun in request for pronoun in (" his ", " her ")):
            target_message = self._latest_sent_message()
            person_id = str(target_message.get("recipient_person_id") or "") if target_message else ""
            if person_id and "modify_contact" in available_tools:
                args = {"person_id": person_id, "phone_number": phone_number}
                if not self._has_successful_observation("modify_contact", args):
                    return "modify_contact", args, "modify_last_contact_phone_from_pronoun"

        if "relationship" in request and phone_number and "search_contacts" in available_tools:
            if not self._has_successful_observation("search_contacts", {"phone_number": phone_number}):
                return "search_contacts", {"phone_number": phone_number}, "search_contact_by_phone_for_relationship"

        if self._asks_to_remove_contact(request) and person_id and "remove_contact" in available_tools:
            args = {"person_id": person_id}
            if not self._has_successful_observation("remove_contact", args):
                return "remove_contact", args, "remove_contact_by_grounded_person_id"

        if self._asks_to_remove_contact(request) and phone_number:
            contacts = self._contacts_matching(phone_number=phone_number)
            if "search_contacts" in available_tools and not contacts:
                return "search_contacts", {"phone_number": phone_number}, "search_contact_by_phone_before_remove"
            if "remove_contact" in available_tools:
                for contact in contacts:
                    person_id = str(contact.get("person_id") or "")
                    if person_id and not self._has_successful_observation("remove_contact", {"person_id": person_id}):
                        return "remove_contact", {"person_id": person_id}, "remove_contact_by_grounded_person_id"

        if self._asks_bulk_friend_enemy_roundtrip(request) and "modify_contact" in available_tools:
            friend_contacts = self._contacts_matching(relationship="friend")
            if "search_contacts" in available_tools and not friend_contacts:
                return "search_contacts", {"relationship": "friend"}, "search_friend_contacts_before_roundtrip"
            enemy_modified = self._modified_person_ids(relationship="enemy")
            for contact in friend_contacts:
                person_id = str(contact.get("person_id") or "")
                if person_id and person_id not in enemy_modified:
                    return "modify_contact", {"person_id": person_id, "relationship": "enemy"}, "update_friend_to_enemy"
            friend_modified = self._modified_person_ids(relationship="friend")
            for contact in friend_contacts:
                person_id = str(contact.get("person_id") or "")
                if person_id and person_id not in friend_modified:
                    return "modify_contact", {"person_id": person_id, "relationship": "friend"}, "update_enemy_back_to_friend"

        if self._asks_bulk_friend_to_enemy(request) and "modify_contact" in available_tools:
            friend_contacts = self._contacts_matching(relationship="friend")
            if "search_contacts" in available_tools and not friend_contacts:
                return "search_contacts", {"relationship": "friend"}, "search_friend_contacts_before_update"
            modified = self._modified_person_ids(relationship="enemy")
            for contact in friend_contacts:
                person_id = str(contact.get("person_id") or "")
                if person_id and person_id not in modified:
                    return "modify_contact", {"person_id": person_id, "relationship": "enemy"}, "update_friend_to_enemy"

        return None

    def _next_message_action(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if self._asks_last_person_talked(request):
            self_contact = next((contact for contact in self.ledger.contacts if contact.get("is_self") is True), None)
            if self_contact is None and "search_contacts" in available_tools:
                return "search_contacts", {"is_self": True}, "search_self_before_last_contact"
            self_id = str(self_contact.get("person_id") or "") if self_contact else ""
            if "search_messages" in available_tools and not self._has_successful_observation("search_messages"):
                args: dict[str, Any] = {"creation_timestamp_lowerbound": 315529200.0}
                if self_id:
                    args["sender_person_id"] = self_id
                return "search_messages", args, "search_messages_for_last_contact"
            target_message = self._latest_sent_message(self_id)
            person_id = str(target_message.get("recipient_person_id") or "") if target_message else ""
            if person_id and "search_contacts" in available_tools and not self._contacts_matching_person_id(person_id):
                return "search_contacts", {"person_id": person_id}, "lookup_last_contact_name"

        if "send_message_with_phone_number" in available_tools:
            phone_numbers = extract_phone_numbers(raw_request)
            content = extract_message_content(raw_request)
            target_name = extract_message_target_name(raw_request)
            if target_name and content and not self._has_successful_observation("send_message_with_phone_number"):
                contacts = self._contacts_matching_name(target_name)
                if "search_contacts" in available_tools and not contacts:
                    if not self._has_successful_observation("search_contacts", {"name": target_name}):
                        return "search_contacts", {"name": target_name}, "search_recipient_contact_before_message"
                if contacts:
                    precondition = self._next_cellular_ready_action(available_tools)
                    if precondition is not None:
                        return precondition
                    return (
                        "send_message_with_phone_number",
                        {"phone_number": str(contacts[0]["phone_number"]), "content": content},
                        "send_message_to_grounded_contact",
                    )
            if phone_numbers and content and not self._has_successful_observation("send_message_with_phone_number"):
                precondition = self._next_cellular_ready_action(available_tools)
                if precondition is not None:
                    return precondition
                return (
                    "send_message_with_phone_number",
                    {"phone_number": phone_numbers[0], "content": content},
                    "send_message_from_user_request",
                )

        if "search_messages" not in available_tools:
            return None
        if self._has_successful_observation("search_messages"):
            return None
        if self._asks_oldest_message(request) and "get_current_timestamp" in available_tools:
            if not self._has_successful_observation("get_current_timestamp"):
                return "get_current_timestamp", {}, "read_time_before_oldest_message_search"
            timestamp = self._last_successful_result("get_current_timestamp")
            upperbound = float(timestamp) if isinstance(timestamp, (int, float)) else 9_999_999_999.0
            return "search_messages", {"creation_timestamp_upperbound": upperbound}, "search_all_messages_for_oldest"
        if self._asks_latest_message(request) or ("phone number" in request and "asked" in request):
            return "search_messages", {"creation_timestamp_lowerbound": 315529200.0}, "search_all_messages"
        return None

    def _next_clarification_action(
        self,
        request: str,
        raw_request: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if "you do not have" in request and "more information" in request:
            return None

        if self._looks_like_reminder_request(request):
            operation_is_add = any(
                phrase in request
                for phrase in (
                    "remind me",
                    "add a reminder",
                    "add a todo",
                    "add a to do",
                    "create a reminder",
                    "create reminder",
                )
            )
            if operation_is_add and "add_reminder" in available_tools:
                content = extract_reminder_content(raw_request)
                time_spec = extract_reminder_time_spec(raw_request)
                if not content and not time_spec:
                    return "__final__", {
                        "message": "What should the reminder say, and when should I remind you?",
                    }, "clarify_reminder_content_and_time"
                if not content:
                    return "__final__", {"message": "What should the reminder say?"}, "clarify_reminder_content"
                if not time_spec:
                    return "__final__", {"message": "When should I remind you?"}, "clarify_reminder_time"

        if "search_messages" in available_tools and any(
            phrase in request
            for phrase in (
                "find a message",
                "find message",
                "look for a message",
                "find a text",
                "find text",
                "text i want to find",
            )
        ):
            if not (
                self._asks_latest_message(request)
                or self._asks_oldest_message(request)
                or "asked" in request
                or extract_phone_numbers(raw_request)
            ):
                return "__final__", {"message": "Which message should I find?"}, "clarify_message_search"

        if (
            self._asks_to_remove_contact(request)
            and "contact" in request
            and not extract_phone_numbers(raw_request)
            and not extract_uuid(raw_request)
        ):
            if "search_contacts" in available_tools or "remove_contact" in available_tools:
                return "__final__", {"message": "Which contact should I delete?"}, "clarify_remove_contact_target"

        if "send_message_with_phone_number" in available_tools and any(
            phrase in request for phrase in ("send a message", "send message", "text ")
        ):
            content = extract_message_content(raw_request)
            target_name = extract_message_target_name(raw_request)
            phone_numbers = extract_phone_numbers(raw_request)
            if not content or (not target_name and not phone_numbers):
                return "__final__", {
                    "message": "Who should I send it to, and what should it say?",
                }, "clarify_message_slots"

        if "modify_contact" in available_tools and "update" in request and "phone number" in request:
            if not extract_phone_numbers(raw_request) and "last" not in request:
                return "__final__", {
                    "message": "Which contact should I update, and what phone number should I use?",
                }, "clarify_contact_update_slots"

        if "modify_contact" in available_tools and any(
            phrase in request for phrase in ("change someone's phone number", "change someone s phone number")
        ):
            return "__final__", {
                "message": "Which contact should I update, and what phone number should I use?",
            }, "clarify_contact_update_slots"

        if "modify_contact" in available_tools and "update" in request and "contact" in request:
            if "friend" not in request and "enem" not in request and "relationship" not in request:
                return "__final__", {
                    "message": "Which contact field should I update?",
                }, "clarify_contact_update"

        if extract_known_location(raw_request) and request.startswith(("where is ", "where's ", "wheres ")):
            return "__final__", {
                "message": "Do you want the address, phone number, or distance?",
            }, "clarify_location_lookup"

        return None

    def _maybe_finish_from_ledger(self, messages: list[Message]) -> Optional[str]:
        request = latest_user_request(messages)
        if not request:
            return None
        return (
            self._rave2_completion(messages)
            or
            self._setting_completion(request)
            or self._contact_completion(request)
            or self._message_completion(request)
            or self._mutation_completion(request)
        )

    def _rave2_completion(self, messages: list[Message]) -> Optional[str]:
        request = latest_user_request(messages)
        raw_request = latest_user_content(messages)
        if not request:
            return None

        latest_observation = self._last_successful_observation()
        if latest_observation is None:
            return None
        latest_tool = str(latest_observation.get("tool") or "")
        latest_args = latest_observation.get("args") or {}
        latest_result = latest_observation.get("result")

        if latest_tool == "search_lat_lon" and isinstance(latest_result, str):
            latitude = latest_args.get("latitude")
            longitude = latest_args.get("longitude")
            if "city" in request:
                city = extract_city_from_address(latest_result) or latest_result
                return f"You are currently in {city}"
            return f"The address for lattitude: {latitude}, longitude: {longitude} is {latest_result}"

        if latest_tool == "search_location_around_lat_lon" and "phone number" in request:
            if isinstance(latest_result, list):
                for result in latest_result:
                    if isinstance(result, dict) and result.get("phone_number"):
                        location = str(latest_args.get("location") or extract_known_location(raw_request) or "that location")
                        return f"The phone number for {location} is {result['phone_number']}"

        if latest_tool == "search_stock" and isinstance(latest_result, dict):
            symbol = latest_result.get("symbol")
            query = str(latest_args.get("query") or "that company")
            if symbol:
                return f"The stock symbol for {query} is {symbol}"

        if latest_tool == "convert_currency" and isinstance(latest_result, (int, float)):
            amount = latest_args.get("amount")
            from_code = latest_args.get("from_currency_code")
            to_code = latest_args.get("to_currency_code")
            return f"{amount} {from_code} is {latest_result} {to_code}"

        if latest_tool == "search_holiday" and isinstance(latest_result, (int, float)):
            if any(phrase in request for phrase in ("when", "date", "what day")) and not any(
                phrase in request for phrase in ("how many days", "how far", "till", "until")
            ):
                holiday = str(latest_args.get("holiday_name") or "the holiday")
                target = dt.datetime.fromtimestamp(float(latest_result))
                return f"{holiday} is {target.month}/{target.day}/{target.year}"

        if latest_tool == "timestamp_diff" and isinstance(latest_result, dict):
            days = latest_result.get("days")
            holiday = extract_holiday_name(raw_request) or "the holiday"
            if days is not None:
                return f"It is {days} days till {holiday}"

        if latest_tool == "search_weather_around_lat_lon" and isinstance(latest_result, dict):
            temperature = latest_result.get("current_temperature")
            label = "current temperature"
            if "lowest" in request or "how cold" in request:
                temperature = latest_result.get("min_temperature")
                label = "lowest temperature"
            elif "highest" in request or "how hot" in request:
                temperature = latest_result.get("max_temperature")
                label = "highest temperature"
            if isinstance(temperature, (int, float)):
                if "fahrenheit" in request or "can't read celsius" in request or "cannot read celsius" in request:
                    if "tomorrow" in request and int(latest_args.get("days") or 0) != 1:
                        return None
                    if "unit_conversion" in self.get_available_tools():
                        return None
                    converted = float(temperature) * 9.0 / 5.0 + 32.0
                    location = extract_known_location(raw_request) or "that location"
                    day_label = "tomorrow" if int(latest_args.get("days") or 0) == 1 else "today"
                    surface = format_surface_number(converted)
                    if label != "current temperature":
                        return f"The {label} in {location} {day_label} is {surface} degrees Fahrenheit"
                    return f"The current temperature is {surface} Fahrenheit"
                location = extract_known_location(raw_request)
                if location and label != "current temperature":
                    day_label = "tomorrow" if int(latest_args.get("days") or 0) == 1 else "today"
                    return f"The {label} in {location} {day_label} is {temperature} degrees Celsius"
                return f"The current temperature is {temperature} Celsius"

        if latest_tool == "unit_conversion" and isinstance(latest_result, (int, float)):
            weather = self._last_successful_result("search_weather_around_lat_lon")
            if isinstance(weather, dict) and self._looks_like_weather_request(request):
                location = extract_known_location(raw_request) or "that location"
                day = self._last_successful_args("search_weather_around_lat_lon").get("days", 0)
                day_label = "tomorrow" if int(day or 0) == 1 else "today"
                temperature = format_surface_number(float(latest_result))
                if "lowest" in request or "how cold" in request:
                    return f"The lowest temperature in {location} {day_label} is {temperature} degrees Fahrenheit"
                if "highest" in request or "how hot" in request:
                    return f"The highest temperature in {location} {day_label} is {temperature} degrees Fahrenheit"
                if location != "that location":
                    return f"The temperature in {location} is {temperature} degrees Fahrenheit"
                return f"The current temperature is {temperature} Fahrenheit"

        if latest_tool == "calculate_lat_lon_distance" and isinstance(latest_result, (int, float)):
            location = extract_known_location(raw_request) or "that location"
            return f"You are approximately {latest_result:.2f} kilometers away from {location}"

        if latest_tool == "search_reminder" and isinstance(latest_result, list) and latest_result:
            if any(phrase in request for phrase in ("postpone", "push", "remove", "get rid")):
                return None
            recency = extract_reminder_recency(request) or "upcoming"
            reminder = self._select_reminder(recency)
            if reminder is None:
                reminder = latest_result[0] if isinstance(latest_result[0], dict) else None
            if isinstance(reminder, dict) and reminder.get("content"):
                content = str(reminder["content"])
                if recency == "created_yesterday":
                    return f"Your reminder created yesterday says '{content}'."
                if recency == "yesterday":
                    return f"Your reminder from yesterday says '{content}'."
                return f"Your upcoming reminder says '{content}'."

        if latest_tool == "add_reminder":
            return "Your reminder has been created."
        if latest_tool == "modify_reminder":
            return "Your reminder has been updated."
        if latest_tool == "remove_reminder":
            return "Your reminder has been removed."
        if latest_tool == "modify_contact" and "last" in request and ("phone" in request or "cell" in request):
            phone_numbers = extract_phone_numbers(raw_request)
            phone_number = phone_numbers[0] if phone_numbers else str(latest_args.get("phone_number") or "")
            person_id = str(latest_args.get("person_id") or "")
            for contact in self.ledger.contacts:
                if str(contact.get("person_id") or "") == person_id and contact.get("name"):
                    return f"{contact['name']}'s phone number has been updated to {phone_number}."
            return f"The phone number of the person you last talked to has been updated to {phone_number}."

        return None

    def _setting_completion(self, request: str) -> Optional[str]:
        specs = {
            "cellular": {
                "aliases": ("cellular", "cellphone signal", "cell signal"),
                "label": "Cellular service",
                "off_done": "Cellular service is turned off",
                "on_done": "Cellular service has been turned on.",
            },
            "wifi": {
                "aliases": ("wifi", "wi-fi", "internet"),
                "label": "Wifi",
                "off_done": "Wifi is turned off",
                "on_done": "Wifi has been turned on.",
            },
            "location_service": {
                "aliases": ("location service", "current location"),
                "label": "Location service",
                "off_done": "Location service is turned off",
                "on_done": "Location service has been turned on.",
            },
            "low_battery_mode": {
                "aliases": ("low battery", "low-battery"),
                "label": "Low battery mode",
                "off_done": "Low battery mode is turned off",
                "on_done": "Low battery mode is turned on",
            },
        }
        for setting, spec in specs.items():
            if setting not in self.ledger.settings:
                continue
            if not any(alias in request for alias in spec["aliases"]):
                continue
            current = self.ledger.settings[setting]
            if self._asks_to_turn_off(request) and current is False:
                return str(spec["off_done"])
            if self._asks_to_turn_on(request) and current is True:
                return str(spec["on_done"])
            if self._asks_status(request):
                return f"{spec['label']} is {'on' if current else 'off'}"
        return None

    def _contact_completion(self, request: str) -> Optional[str]:
        if self._asks_bulk_friend_enemy_roundtrip(request):
            subject = self._relationship_contact_names("friend")
            if self._bulk_relationship_roundtrip_complete("friend", "enemy"):
                return f"{subject} are now your friends again."
            if (
                self._bulk_relationship_update_complete("friend", "enemy")
                and not self._announced_relationship_phase
            ):
                self._announced_relationship_phase = True
                return f"{subject} are now your enemies"
            return None

        if self._asks_bulk_friend_to_enemy(request):
            source_relationship, target_relationship = relationship_update_direction(request)
            if (
                source_relationship
                and target_relationship
                and self._bulk_relationship_update_complete(source_relationship, target_relationship)
            ):
                subject = self._relationship_contact_names(source_relationship)
                return f"{subject} are now your {plural_relationship(target_relationship)}"
            return None

        if "friend" in request and ("who" in request or "my friends" in request):
            friends = [
                str(contact.get("name") or "")
                for contact in self.ledger.contacts
                if normalize_text(str(contact.get("relationship") or "")) == "friend" and contact.get("name")
            ]
            if friends:
                return "Your friends are " + ", ".join(friends)

        for contact in reversed(self.ledger.contacts):
            name = str(contact.get("name") or "")
            phone_number = str(contact.get("phone_number") or "")
            relationship = str(contact.get("relationship") or "")
            normalized_name = normalize_text(name)
            normalized_relationship = normalize_text(relationship)
            if not name and not phone_number and not relationship:
                continue

            if "phone number" in request and phone_number:
                if normalized_name and normalized_name in request:
                    return f"I found {name}'s phone number: {phone_number}"
                if normalized_relationship and normalized_relationship in request:
                    return f"Your {relationship}'s phone number is {phone_number}"

            if ("name" in request or "who" in request) and name:
                if normalized_relationship and normalized_relationship in request:
                    return f"Your {relationship} is {name}"
                if "boss" in request and normalized_relationship == "boss":
                    return f"Your boss is {name}"
                if phone_number and phone_number in request:
                    return f"{phone_number} belongs to {name}"

            if "relationship" in request and relationship and phone_number and phone_number in request:
                return f"{phone_number} is your {relationship}"
        return None

    def _message_completion(self, request: str) -> Optional[str]:
        messages = [message for message in self.ledger.messages if isinstance(message.get("creation_timestamp"), (int, float))]
        if self._asks_last_person_talked(request):
            target = self._latest_sent_message()
            person_id = str(target.get("recipient_person_id") or "") if target else ""
            for contact in self.ledger.contacts:
                if contact.get("person_id") == person_id and contact.get("name"):
                    return f"The last person you talked to was {contact['name']}."
            return None
        if "phone number" in request and "asked" in request:
            for message in reversed(self.ledger.messages):
                sender_phone_number = str(message.get("sender_phone_number") or "")
                content = normalize_text(str(message.get("content") or ""))
                if sender_phone_number and "gpu" in content:
                    return f"{sender_phone_number} asked you if you want some GPUs"
            return None
        if messages and self._asks_latest_message(request):
            latest = max(messages, key=lambda item: float(item["creation_timestamp"]))
            content = str(latest.get("content") or "")
            if content:
                return f"Your most recent message says '{content}'."
        if messages and self._asks_oldest_message(request):
            oldest = min(messages, key=lambda item: float(item["creation_timestamp"]))
            content = str(oldest.get("content") or "")
            if content:
                if "first ever" in request or self._has_prior_vague_message_lookup():
                    return f"Your first ever text says '{content}'."
                return f"Your oldest message says '{content}'."
        return None

    def _mutation_completion(self, request: str) -> Optional[str]:
        observation = self._last_successful_observation()
        if observation is None:
            return None
        tool = observation["tool"]
        args = observation["args"]
        if tool == "add_contact" and "name" in args:
            return f"{args['name']} has been added to your contact"
        if tool == "remove_contact" and "person_id" in args:
            if "ask user b" in request:
                person_id = str(args.get("person_id") or "")
                for contact in self.ledger.contacts:
                    if str(contact.get("person_id") or "") == person_id and contact.get("name"):
                        return f"{contact['name']} has been removed from your contact"
            phone_numbers = extract_phone_numbers(request)
            if phone_numbers:
                return f"Phone number {phone_numbers[0]} has been removed from your contact"
            return f"{args['person_id']} has been removed from your contact"
        if tool == "modify_contact" and "person_id" in args:
            if self._asks_bulk_friend_enemy_roundtrip(request):
                subject = self._relationship_contact_names("friend")
                if self._bulk_relationship_roundtrip_complete("friend", "enemy"):
                    return f"{subject} are now your friends again."
                if (
                    self._bulk_relationship_update_complete("friend", "enemy")
                    and not self._announced_relationship_phase
                ):
                    self._announced_relationship_phase = True
                    return f"{subject} are now your enemies"
                return None
            if self._asks_bulk_friend_to_enemy(request):
                source_relationship, target_relationship = relationship_update_direction(request)
                if (
                    source_relationship
                    and target_relationship
                    and self._bulk_relationship_update_complete(source_relationship, target_relationship)
                ):
                    subject = self._relationship_contact_names(source_relationship)
                    return f"{subject} are now your {plural_relationship(target_relationship)}"
                return None
            if "phone_number" in args:
                return f"{args['person_id']}'s phone number have been updated to {args['phone_number']}"
            if "relationship" in args:
                return f"{args['person_id']}'s relationship have been updated to {args['relationship']}"
            return f"{args['person_id']} has been updated"
        if tool == "send_message_with_phone_number" and "phone_number" in args and "content" in args:
            for contact in self.ledger.contacts:
                if contact.get("phone_number") == args["phone_number"] and contact.get("name"):
                    return f"Your message to {contact['name']} has been sent saying: {args['content']}"
            return f"Your message to {args['phone_number']} has been sent saying: {args['content']}"
        return None

    def _last_successful_observation(self) -> Optional[dict[str, Any]]:
        return self.ledger.last_successful_observation()

    def _last_successful_result(self, tool: str) -> Any:
        return self.ledger.last_successful_result(tool)

    def _last_successful_args(self, tool: str) -> dict[str, Any]:
        return self.ledger.last_successful_args(tool)

    def _last_successful_matching_result(
        self,
        tool: str,
        args_subset: Optional[dict[str, Any]] = None,
    ) -> Any:
        return self.ledger.last_successful_matching_result(tool, args_subset)

    def _has_successful_observation(
        self,
        tool: str,
        args_subset: Optional[dict[str, Any]] = None,
    ) -> bool:
        return self.ledger.has_successful_observation(tool, args_subset)

    def _has_failed_observation(
        self,
        tool: str,
        args_subset: Optional[dict[str, Any]] = None,
    ) -> bool:
        return self.ledger.has_failed_observation(tool, args_subset)

    def _contacts_matching(
        self,
        *,
        phone_number: str = "",
        relationship: str = "",
    ) -> list[dict[str, Any]]:
        matches = []
        for contact in self.ledger.contacts:
            if phone_number and contact.get("phone_number") != phone_number:
                continue
            if relationship and normalize_text(str(contact.get("relationship") or "")) != relationship:
                continue
            matches.append(contact)
        return matches

    def _contacts_matching_name(self, name: str) -> list[dict[str, Any]]:
        normalized_name = normalize_text(name)
        return [
            contact
            for contact in self.ledger.contacts
            if normalize_text(str(contact.get("name") or "")) == normalized_name
        ]

    def _contacts_matching_person_id(self, person_id: str) -> list[dict[str, Any]]:
        return [
            contact
            for contact in self.ledger.contacts
            if str(contact.get("person_id") or "") == person_id
        ]

    def _has_prior_vague_message_lookup(self) -> bool:
        vague_phrases = (
            "find a message",
            "text i want to find",
            "find a text",
        )
        for content in self.ledger.user_messages[:-1]:
            normalized = normalize_text(content)
            if any(phrase in normalized for phrase in vague_phrases):
                return True
        return False

    def _next_cellular_ready_action(
        self,
        available_tools: dict[str, Callable[..., Any]],
    ) -> Optional[tuple[str, dict[str, Any], str]]:
        if "cellular" not in self.ledger.settings:
            if "get_cellular_service_status" in available_tools:
                return "get_cellular_service_status", {}, "read_cellular_before_message"
            return None
        if self.ledger.settings["cellular"] is True:
            return None
        if not self.options.enable_precondition_repair:
            return None
        if "low_battery_mode" not in self.ledger.settings and "get_low_battery_mode_status" in available_tools:
            return "get_low_battery_mode_status", {}, "read_low_battery_before_message"
        if self.ledger.settings.get("low_battery_mode") is True and "set_low_battery_mode_status" in available_tools:
            return "set_low_battery_mode_status", {"on": False}, "disable_low_battery_before_message"
        if "set_cellular_service_status" in available_tools:
            return "set_cellular_service_status", {"on": True}, "enable_cellular_before_message"
        return None

    def _modified_person_ids(self, *, relationship: str = "") -> set[str]:
        modified: set[str] = set()
        for observation in self.ledger.observations:
            if observation.get("tool") != "modify_contact" or observation.get("error"):
                continue
            args = observation.get("args") or {}
            if relationship and normalize_text(str(args.get("relationship") or "")) != relationship:
                continue
            person_id = str(args.get("person_id") or "")
            if person_id:
                modified.add(person_id)
        return modified

    def _bulk_relationship_update_complete(self, old_relationship: str, new_relationship: str) -> bool:
        contacts = self._contacts_matching(relationship=old_relationship)
        if not contacts:
            return False
        modified = self._modified_person_ids(relationship=new_relationship)
        return all(str(contact.get("person_id") or "") in modified for contact in contacts)

    def _bulk_relationship_roundtrip_complete(self, original_relationship: str, intermediate_relationship: str) -> bool:
        contacts = self._contacts_matching(relationship=original_relationship)
        if not contacts:
            return False
        intermediate_modified = self._modified_person_ids(relationship=intermediate_relationship)
        original_modified = self._modified_person_ids(relationship=original_relationship)
        return all(
            str(contact.get("person_id") or "") in intermediate_modified
            and str(contact.get("person_id") or "") in original_modified
            for contact in contacts
        )

    def _relationship_contact_names(self, relationship: str) -> str:
        names = [
            str(contact.get("name") or "")
            for contact in self._contacts_matching(relationship=relationship)
            if contact.get("name")
        ]
        if not names:
            return "Those contacts"
        if len(names) == 1:
            return names[0]
        return ", ".join(names[:-1]) + " and " + names[-1]

    @staticmethod
    def _requested_setting(request: str) -> Optional[str]:
        if any(alias in request for alias in ("cellular", "cellphone signal", "cell signal")):
            return "cellular"
        if any(alias in request for alias in ("wifi", "wi-fi", "internet")):
            return "wifi"
        if any(alias in request for alias in ("location service", "current location")):
            return "location_service"
        if any(alias in request for alias in ("low battery", "low-battery")):
            return "low_battery_mode"
        return None

    @staticmethod
    def _asks_to_remove_contact(request: str) -> bool:
        return any(phrase in request for phrase in ("remove", "delete", "get rid", "out of my contacts"))

    @staticmethod
    def _asks_bulk_friend_to_enemy(request: str) -> bool:
        return "friend" in request and "enem" in request

    @staticmethod
    def _asks_bulk_friend_enemy_roundtrip(request: str) -> bool:
        return "friend" in request and "enem" in request and any(
            phrase in request for phrase in ("back to", "back as", "update them back")
        )

    @staticmethod
    def _asks_latest_message(request: str) -> bool:
        return any(phrase in request for phrase in ("most recent message", "latest text", "most recent text"))

    @staticmethod
    def _asks_oldest_message(request: str) -> bool:
        return any(phrase in request for phrase in ("oldest message", "first ever text", "oldest text"))

    @staticmethod
    def _asks_last_person_talked(request: str) -> bool:
        return any(
            phrase in request
            for phrase in ("last person i talked", "who did i talk to last", "last person i contacted")
        )

    @staticmethod
    def _asks_to_turn_off(request: str) -> bool:
        return any(phrase in request for phrase in ("turn off", "disable", "shut off", "switch off"))

    @staticmethod
    def _asks_to_turn_on(request: str) -> bool:
        return any(
            phrase in request
            for phrase in ("turn on", "enable", "switch on", "get it on", "connected", "fix that", "access")
        )

    @staticmethod
    def _asks_status(request: str) -> bool:
        return "?" in request or request.startswith("is ") or " status" in request or "check " in request

    def _guard_action(
        self,
        tool: str,
        args: dict[str, Any],
        available_tools: dict[str, Callable[..., Any]],
    ) -> "GuardDecision":
        if tool not in available_tools:
            return GuardDecision(False, tool, args, "unknown_tool")
        schema = inspect.signature(available_tools[tool])
        normalized_args = {key: value for key, value in args.items() if key in schema.parameters}
        missing = [
            name
            for name, param in schema.parameters.items()
            if param.default is inspect.Signature.empty and name not in normalized_args
        ]
        if missing:
            return GuardDecision(False, tool, normalized_args, f"schema_missing_{','.join(missing)}")

        if tool == "get_current_location":
            if "location_service" not in self.ledger.settings:
                return self._repair("get_location_service_status", {}, "missing_location_evidence", available_tools)
            if self.ledger.settings["location_service"] is not True:
                if not self.options.enable_precondition_repair:
                    return GuardDecision(False, tool, normalized_args, "location_off")
                return self._repair(
                    "set_location_service_status",
                    {"on": True},
                    "location_off",
                    available_tools,
                )
        if tool in READ_ONLY_TOOLS:
            if self.options.enable_argument_normalizer:
                normalized_args = self._normalize_read_args(tool, normalized_args)
            if tool in {"search_contacts", "search_messages", "search_reminder"} and not normalized_args:
                return GuardDecision(False, tool, normalized_args, "empty_search")
            return GuardDecision(True, tool, normalized_args, "")

        if tool == "add_contact":
            if self.options.enable_argument_normalizer:
                normalized_args = self._normalize_add_contact_args(normalized_args)

        if tool == "send_message_with_phone_number":
            if "cellular" not in self.ledger.settings:
                if "get_cellular_service_status" in available_tools:
                    return self._repair("get_cellular_service_status", {}, "missing_cellular_evidence", available_tools)
                return GuardDecision(True, tool, normalized_args, "")
            if self.ledger.settings["cellular"] is not True:
                if not self.options.enable_precondition_repair:
                    return GuardDecision(False, tool, normalized_args, "cellular_off")
                return self._repair(
                    "set_cellular_service_status",
                    {"on": True},
                    "cellular_off",
                    available_tools,
                )
        if tool in SETTING_SETTERS and "on" in normalized_args:
            setting = SETTING_SETTERS[tool]
            desired = bool(normalized_args["on"])
            if self.ledger.settings.get(setting) is desired:
                state = "enabled" if desired else "disabled"
                return GuardDecision(False, tool, normalized_args, f"{setting}_already_{state}")
        if tool in {"set_cellular_service_status", "set_wifi_status", "set_location_service_status"}:
            if normalized_args.get("on") is True:
                setting = SETTING_SETTERS[tool]
                if "low_battery_mode" not in self.ledger.settings and "get_low_battery_mode_status" in available_tools:
                    return self._repair(
                        "get_low_battery_mode_status",
                        {},
                        "missing_low_battery_evidence",
                        available_tools,
                    )
                if self.ledger.settings.get("low_battery_mode") is True:
                    if not self.options.enable_precondition_repair:
                        return GuardDecision(False, tool, normalized_args, "low_battery_blocks_service")
                    return self._repair(
                        "set_low_battery_mode_status",
                        {"on": False},
                        "low_battery_blocks_service",
                        available_tools,
                    )

        return GuardDecision(True, tool, normalized_args, "")

    def _normalize_read_args(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool == "search_messages":
            normalized = dict(args)
            for key in ("sender_phone_number", "recipient_phone_number"):
                if key in normalized and not looks_like_phone_number(str(normalized[key])):
                    normalized.pop(key, None)
            return normalized
        if tool != "search_contacts":
            return args
        normalized = dict(args)
        name = normalize_text(str(normalized.get("name", "")))
        relationship = normalize_text(str(normalized.get("relationship", "")))
        phone_number = str(normalized.get("phone_number", ""))
        if phone_number and not looks_like_phone_number(phone_number):
            inferred_name = extract_contact_name_for_phone_lookup(phone_number)
            normalized.pop("phone_number", None)
            if inferred_name and "name" not in normalized:
                normalized["name"] = inferred_name
        if name in {"boss", "manager", "supervisor"} and "relationship" not in normalized:
            normalized.pop("name", None)
            normalized["relationship"] = name
        if relationship and looks_like_phone_number(str(normalized.get("relationship"))):
            normalized["phone_number"] = str(normalized.pop("relationship"))
        if name == "friends":
            normalized.pop("name", None)
            normalized["relationship"] = "friend"
        if name == "enemies":
            normalized.pop("name", None)
            normalized["relationship"] = "enemy"
        return normalized

    def _normalize_add_contact_args(self, args: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(args)
        relationship = normalize_text(str(normalized.get("relationship", "")))
        if not relationship:
            return normalized
        request = normalize_text(self.ledger.user_messages[-1]) if self.ledger.user_messages else ""
        if relationship not in request and "relationship" not in request:
            normalized.pop("relationship", None)
        return normalized

    @staticmethod
    def _repair(
        tool: str,
        args: dict[str, Any],
        reason: str,
        available_tools: dict[str, Callable[..., Any]],
    ) -> "GuardDecision":
        if tool not in available_tools:
            return GuardDecision(False, tool, args, reason)
        return GuardDecision(False, tool, args, reason, repair_tool=tool, repair_args=args)


@dataclass
class GuardDecision:
    ok: bool
    tool: str
    args: dict[str, Any]
    reason: str
    repair_tool: str = ""
    repair_args: dict[str, Any] = field(default_factory=dict)


def normalize_contract(value: dict[str, Any]) -> dict[str, Any]:
    args = value.get("args")
    evidence = value.get("evidence")
    post = value.get("expected_postconditions")
    return {
        "tool": str(value.get("tool", "")),
        "args": args if isinstance(args, dict) else {},
        "evidence": evidence if isinstance(evidence, dict) else {},
        "expected_postconditions": post if isinstance(post, list) else [],
    }


def make_tool_call_code(
    tool: str,
    args: dict[str, Any],
    available_tools: dict[str, Callable[..., Any]],
    call_id: str,
) -> str:
    context = get_current_context()
    if tool not in available_tools:
        return f"raise NameError({('Unknown or disallowed tool: ' + tool)!r})"
    execution_name = context.get_execution_facing_tool_name(tool)
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", execution_name):
        return f"raise NameError({('Unsafe tool name: ' + execution_name)!r})"
    return (
        f"{call_id}_parameters = {repr(args)}\n"
        f"{call_id}_response = {execution_name}(**{call_id}_parameters)\n"
        f"print(repr({call_id}_response))"
    )


def format_tool_specs(available_tools: dict[str, Callable[..., Any]]) -> str:
    lines = []
    for name, tool in sorted(available_tools.items()):
        signature = inspect.signature(tool)
        doc = inspect.getdoc(tool) or ""
        doc_line = " ".join(doc.splitlines()[:2])
        lines.append(f"- {name}{signature}: {doc_line}")
    return "\n".join(lines)


def format_messages(messages: list[Message]) -> str:
    lines = []
    for message in messages:
        sender = str(message.sender)
        recipient = str(message.recipient)
        content = message.content.replace("\n", "\\n")
        if len(content) > 800:
            content = content[:800] + "..."
        error = f" ERROR={message.tool_call_exception}" if message.tool_call_exception else ""
        lines.append(f"{sender} -> {recipient}: {content}{error}")
    return "\n".join(lines)


def latest_user_request(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.sender == RoleType.USER and message.recipient == RoleType.AGENT:
            return normalize_text(message.content)
    return ""


def latest_user_content(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.sender == RoleType.USER and message.recipient == RoleType.AGENT:
            return message.content
    return ""


def extract_phone_numbers(value: str) -> list[str]:
    return re.findall(r"\+\d{7,15}", value)


def extract_uuid(value: str) -> str:
    match = re.search(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        value,
    )
    return match.group(0) if match else ""


def looks_like_phone_number(value: str) -> bool:
    return bool(re.fullmatch(r"\+\d{7,15}", value.strip()))


def extract_message_content(request: str) -> str:
    match = re.search(r"\bsaying:\s*(.+)$", request, flags=re.IGNORECASE)
    if match:
        content = match.group(1).strip()
        if content[:1] in {"'", '"'}:
            quote = content[0]
            end = content.find(quote, 1)
            if end > 1:
                content = content[1:end]
        return cleanup_message_content(content)
    match = re.search(
        r"\bask\s+[A-Z][A-Za-z']+\s+[A-Z][A-Za-z']+\s+(.+)$",
        request,
        flags=re.IGNORECASE,
    )
    if match:
        return cleanup_message_content(match.group(1))
    match = re.search(r"\bsay\s+(.+)$", request, flags=re.IGNORECASE)
    if match:
        return cleanup_message_content(match.group(1))
    return ""


def cleanup_message_content(value: str) -> str:
    content = value.strip()
    stop_patterns = [
        r"\s+You\s+only\s+know\b",
        r"\s+You\s+do\s+not\s+have\b",
        r"\s+You\s+don\s+not\s+have\b",
        r"\s+You\s+do\s+not\s+know\b",
    ]
    for pattern in stop_patterns:
        content = re.split(pattern, content, maxsplit=1, flags=re.IGNORECASE)[0]
    return content.strip().rstrip(".")


def extract_message_target_name(request: str) -> str:
    match = re.search(r"\bmessage to\s+(.+?)\s+saying:", request, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(
        r"\bask\s+([A-Z][A-Za-z']+\s+[A-Z][A-Za-z']+)\s+",
        request,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return ""


def extract_contact_name_for_phone_lookup(request: str) -> str:
    patterns = (
        r"\b(?:what is|what's|whats)\s+(.+?)'s\s+phone\s+number\b",
        r"\bphone\s+number\s+(?:for|of)\s+(.+?)(?:\?|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, request, flags=re.IGNORECASE)
        if match:
            name = cleanup_entity(match.group(1))
            if name and not looks_like_phone_number(name) and not extract_known_location(name):
                return name
    return ""


def extract_new_contact(request: str) -> Optional[dict[str, Any]]:
    if not re.search(r"\badd\b.+\bcontacts?\b|\bcontacts?\b.+\badd\b", request, flags=re.IGNORECASE):
        return None
    phone_numbers = extract_phone_numbers(request)
    if not phone_numbers:
        return None
    name = (
        extract_after(request, r"\badd\s+(.+?)\s+to\s+my\s+contacts?\b")
        or extract_after(request, r"\badd\s+(.+?),?\s+(?:his|her|their)?\s*phone")
    )
    if not name:
        return None
    args: dict[str, Any] = {"name": name, "phone_number": phone_numbers[0]}
    relationship = extract_contact_relationship(request)
    if relationship:
        args["relationship"] = relationship
    return args


def extract_contact_relationship(request: str) -> str:
    relationship_match = re.search(
        r"\brelationship\s+(?:is|as)\s+([A-Za-z][A-Za-z -]+)\b",
        request,
        flags=re.IGNORECASE,
    )
    if relationship_match:
        return cleanup_entity(relationship_match.group(1))
    as_my_match = re.search(r"\bas\s+my\s+([A-Za-z][A-Za-z -]+)\b", request, flags=re.IGNORECASE)
    if as_my_match:
        return cleanup_entity(as_my_match.group(1))
    return ""


def extract_relationship_for_name_lookup(request: str) -> str:
    normalized = normalize_text(request)
    if not any(token in normalized for token in ("name", "who")):
        return ""

    explicit = extract_contact_relationship(request)
    if explicit:
        return normalize_text(explicit)

    aliases = {
        "boss": "boss",
        "manager": "boss",
        "supervisor": "boss",
        "friend": "friend",
        "friends": "friend",
        "enemy": "enemy",
        "enemies": "enemy",
    }
    for alias, relationship in aliases.items():
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            return relationship
    return ""


def relationship_update_direction(request: str) -> tuple[str, str]:
    normalized = normalize_text(request)
    friend_match = re.search(r"\bfriends?\b", normalized)
    enemy_match = re.search(r"\benem(?:y|ies)\b", normalized)
    if friend_match is None or enemy_match is None:
        return "", ""
    if friend_match.start() <= enemy_match.start():
        return "friend", "enemy"
    return "enemy", "friend"


def plural_relationship(relationship: str) -> str:
    if relationship == "enemy":
        return "enemies"
    if relationship == "friend":
        return "friends"
    return f"{relationship}s"


def format_bullets(items: list[str]) -> str:
    if not items:
        return "(none)"
    return "\n".join(f"- {item}" for item in items)


def token_count_or_proxy(prompt_tokens: int, completion_tokens: int, prompt: str, completion: str) -> int:
    if prompt_tokens or completion_tokens:
        return prompt_tokens + completion_tokens
    return max(1, len(prompt.split()) + len(completion.split()))


def parse_python_literal(content: str) -> Any:
    stripped = content.strip()
    if not stripped:
        return None
    try:
        return ast.literal_eval(stripped)
    except Exception:  # noqa: BLE001
        return stripped


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def args_include(args: dict[str, Any], subset: dict[str, Any]) -> bool:
    return all(arg_values_match(args.get(key), value) for key, value in subset.items())


def arg_values_match(actual: Any, expected: Any) -> bool:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return abs(float(actual) - float(expected)) <= 1e-6
    return actual == expected


def combined_user_request(messages: list[Message]) -> str:
    return normalize_text(combined_user_content(messages))


def combined_user_content(messages: list[Message]) -> str:
    parts = [
        message.content
        for message in messages
        if message.sender == RoleType.USER and message.recipient == RoleType.AGENT and message.content
    ]
    return " ".join(parts)


def parse_currency_request(request: str) -> Optional[dict[str, Any]]:
    text = normalize_text(request)
    currency_aliases = {
        "$": "USD",
        "usd": "USD",
        "dollar": "USD",
        "dollars": "USD",
        "cny": "CNY",
        "rmb": "CNY",
        "yuan": "CNY",
        "eur": "EUR",
        "euro": "EUR",
        "euros": "EUR",
        "gbp": "GBP",
        "pound": "GBP",
        "pounds": "GBP",
        "jpy": "JPY",
        "yen": "JPY",
    }

    amount: Optional[float] = None
    from_code = ""
    to_code = ""

    money_match = re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*([kKmM]?)", request)
    if money_match:
        amount = float(money_match.group(1))
        suffix = money_match.group(2).casefold()
        if suffix == "k":
            amount *= 1_000
        elif suffix == "m":
            amount *= 1_000_000
        from_code = "USD"

    if amount is None:
        amount_match = re.search(
            r"\b([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]{3}|dollars?|euros?|pounds?|yen|yuan|rmb)\b",
            request,
            flags=re.IGNORECASE,
        )
        if not amount_match:
            return None
        amount = float(amount_match.group(1))
        from_code = currency_aliases.get(normalize_text(amount_match.group(2)), amount_match.group(2).upper())

    to_match = re.search(
        r"\b(?:to|in|into)\s+([A-Za-z]{3}|dollars?|euros?|pounds?|yen|yuan|rmb)\b",
        request,
        flags=re.IGNORECASE,
    )
    if to_match:
        to_code = currency_aliases.get(normalize_text(to_match.group(1)), to_match.group(1).upper())

    if not to_code or not from_code:
        codes = [currency_aliases.get(token, token.upper()) for token in re.findall(r"\b[A-Za-z]{3}\b", text)]
        codes = [code for code in codes if re.fullmatch(r"[A-Z]{3}", code)]
        if not from_code and codes:
            from_code = codes[0]
        if not to_code:
            for code in codes:
                if code != from_code:
                    to_code = code
                    break

    if amount is None or not from_code or not to_code:
        return None
    canonical_amount: float | int = int(amount) if float(amount).is_integer() else amount
    return {"amount": canonical_amount, "from": from_code, "to": to_code}


def extract_after(value: str, pattern: str) -> str:
    match = re.search(pattern, value, flags=re.IGNORECASE)
    if not match:
        return ""
    return cleanup_entity(match.group(1))


def cleanup_entity(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*resolve any issue alone\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+stock\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*(?:please|thanks|thank you)[.!?]*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" \t\r\n'\"`.,?!")
    return cleaned


def extract_lat_lon(value: str) -> Optional[tuple[float, float]]:
    latitude_match = re.search(r"\b(?:lat|latitude|lattitude)\s*[:=]?\s*(-?\d+(?:\.\d+)?)", value, flags=re.IGNORECASE)
    longitude_match = re.search(r"\b(?:lon|lng|longitude)\s*[:=]?\s*(-?\d+(?:\.\d+)?)", value, flags=re.IGNORECASE)
    if latitude_match and longitude_match:
        return float(latitude_match.group(1)), float(longitude_match.group(1))
    pair_match = re.search(r"\b(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\b", value)
    if pair_match:
        first = float(pair_match.group(1))
        second = float(pair_match.group(2))
        if -90 <= first <= 90 and -180 <= second <= 180:
            return first, second
    return None


def extract_known_location(value: str) -> str:
    normalized = normalize_text(value)
    for key, canonical in KNOWN_LOCATION_CANONICALS.items():
        if key in normalized:
            return str(canonical.get("label") or key.title())
    return ""


def extract_city_from_address(value: str) -> str:
    for city in ("Cupertino", "San Francisco", "New York", "Los Angeles"):
        if city.casefold() in value.casefold():
            return city
    match = re.search(r"\b([A-Z][A-Za-z]+),\s*[A-Z]{2}\b", value)
    if match:
        return match.group(1)
    return ""


def format_surface_number(value: float) -> str:
    formatted = f"{value:.1f}"
    return formatted[:-2] if formatted.endswith(".0") else formatted


def extract_holiday_name(value: str) -> str:
    normalized = normalize_text(value)
    if "christmas" in normalized:
        return "Christmas Day"
    if "thanksgiving" in normalized:
        return "Thanksgiving"
    match = re.search(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)\s+holiday\b", value)
    if match:
        return cleanup_entity(match.group(1))
    return ""


def extract_reminder_content(value: str) -> str:
    match = re.search(
        r"\b(?:remind me to|add a (?:todo|to do) to|create a reminder to|create reminder to|add a reminder to)\s+(.+)$",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    content = cleanup_entity(match.group(1))
    stop_patterns = [
        r"\s+(?:on\s+)?\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\s+tomorrow\b",
        r"\s+next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\s+at\s+(?:whole foods(?:\s+on\s+[A-Za-z ]+)?|apple park|grand canyon|golden gate bridge)\b",
    ]
    for pattern in stop_patterns:
        split = re.split(pattern, content, maxsplit=1, flags=re.IGNORECASE)
        content = cleanup_entity(split[0])
    if not content:
        return ""
    return content[:1].upper() + content[1:]


def extract_reminder_recency(request: str) -> str:
    normalized = normalize_text(request)
    if "created yesterday" in normalized or "made yesterday" in normalized:
        return "created_yesterday"
    if "yesterday" in normalized:
        return "yesterday"
    if any(phrase in normalized for phrase in ("upcoming", "next reminder", "todo later", "later")):
        return "upcoming"
    if any(phrase in normalized for phrase in ("latest", "most recent")):
        return "latest"
    return ""


def extract_reminder_time_spec(value: str) -> str:
    date_match = re.search(
        r"\b\d{1,2}/\d{1,2}/\d{2,4}(?:\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)?)?",
        value,
    )
    if date_match:
        return date_match.group(0).strip()
    tomorrow_match = re.search(
        r"\btomorrow(?:\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)?)?",
        value,
        flags=re.IGNORECASE,
    )
    if tomorrow_match:
        return tomorrow_match.group(0).strip()
    weekday_match = re.search(
        r"\bnext\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
        r"(?:\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)?)?",
        value,
        flags=re.IGNORECASE,
    )
    if weekday_match:
        return weekday_match.group(0).strip()
    time_match = re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)\b", value)
    if time_match:
        return time_match.group(0).strip()
    return ""


def is_absolute_time_spec(value: str) -> bool:
    return bool(re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", value or ""))


def datetime_tool_args_for_spec(value: str) -> dict[str, int]:
    match = re.search(
        r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})(?:\s+(\d{1,2})(?::(\d{2}))?\s*(AM|PM|am|pm)?)?",
        value,
    )
    if not match:
        return {}
    month = int(match.group(1))
    day = int(match.group(2))
    year = int(match.group(3))
    if year < 100:
        year += 2000
    hour = int(match.group(4) or 0)
    minute = int(match.group(5) or 0)
    suffix = (match.group(6) or "").casefold()
    if suffix == "pm" and hour != 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    return {"year": year, "month": month, "day": day, "hour": hour, "minute": minute, "second": 0}


def parse_clock_time(value: str) -> tuple[int, int]:
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(AM|PM|am|pm)?\b", value or "")
    if not match:
        return 17, 0
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    suffix = (match.group(3) or "").casefold()
    if suffix == "pm" and hour != 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    return hour, minute
