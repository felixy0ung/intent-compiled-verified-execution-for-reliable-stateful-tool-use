from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from .ministore import DANGEROUS_TOOLS, MiniStoreEnv, Task, ToolResult


IDENTITY_CATEGORIES = {"update_address", "cancel_order", "request_refund"}


@dataclass
class EpisodeStats:
    method: str
    task_id: str
    category: str
    success: bool
    goal_achieved: bool
    invalid_tool_calls: int
    unsafe_changes: int
    collateral_changes: int
    verifier_rejections: int
    llm_calls: int
    tool_calls: int
    token_proxy: int
    missing_schema_errors: int
    unsupported_argument_errors: int
    precondition_errors: int
    postcondition_errors: int

    def to_row(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "task_id": self.task_id,
            "category": self.category,
            "success": int(self.success),
            "goal_achieved": int(self.goal_achieved),
            "invalid_tool_calls": self.invalid_tool_calls,
            "unsafe_changes": self.unsafe_changes,
            "collateral_changes": self.collateral_changes,
            "verifier_rejections": self.verifier_rejections,
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "token_proxy": self.token_proxy,
            "missing_schema_errors": self.missing_schema_errors,
            "unsupported_argument_errors": self.unsupported_argument_errors,
            "precondition_errors": self.precondition_errors,
            "postcondition_errors": self.postcondition_errors,
        }


@dataclass
class Ledger:
    task: Task
    orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    coupons: dict[str, dict[str, Any]] = field(default_factory=dict)
    verified_users: set[str] = field(default_factory=set)
    observations: list[ToolResult] = field(default_factory=list)

    def observe(self, result: ToolResult) -> None:
        self.observations.append(result)
        if not result.ok:
            return
        if result.tool == "get_order":
            order = dict(result.observation["order"])
            self.orders[order["order_id"]] = order
        elif result.tool == "get_coupon":
            coupon = dict(result.observation["coupon"])
            self.coupons[coupon["coupon_code"]] = coupon
        elif result.tool == "verify_identity" and result.observation.get("identity_verified"):
            self.verified_users.add(result.observation["user_id"])


@dataclass
class AgentConfig:
    name: str
    verify_prob: float
    inspect_order_prob: float
    inspect_coupon_prob: float
    wrong_id_prob: float
    missing_arg_prob: float
    wrong_value_prob: float
    retry_prob: float
    repair_prob: float
    compact_context: bool = False


class BaseAgent:
    config: AgentConfig

    def run(self, env: MiniStoreEnv) -> EpisodeStats:
        seed = stable_seed(self.config.name, env.task.task_id)
        rng = random.Random(seed)
        ledger = Ledger(env.task)
        counters = {"llm_calls": 0, "token_proxy": 0, "verifier_rejections": 0}
        self._run(env, ledger, rng, counters)
        return EpisodeStats(
            method=self.config.name,
            task_id=env.task.task_id,
            category=env.task.category,
            success=env.task_success(),
            goal_achieved=env.goal_achieved(),
            invalid_tool_calls=env.invalid_tool_calls,
            unsafe_changes=env.unsafe_changes,
            collateral_changes=env.collateral_changes,
            verifier_rejections=counters["verifier_rejections"],
            llm_calls=counters["llm_calls"],
            tool_calls=env.tool_calls,
            token_proxy=counters["token_proxy"],
            missing_schema_errors=env.missing_schema_errors,
            unsupported_argument_errors=env.unsupported_argument_errors,
            precondition_errors=env.precondition_errors,
            postcondition_errors=env.postcondition_errors,
        )

    def _run(
        self,
        env: MiniStoreEnv,
        ledger: Ledger,
        rng: random.Random,
        counters: dict[str, int],
    ) -> None:
        raise NotImplementedError

    def _charge_llm(self, env: MiniStoreEnv, counters: dict[str, int]) -> None:
        counters["llm_calls"] += 1
        if self.config.compact_context:
            counters["token_proxy"] += 180 + 35 * (env.tool_calls + counters["verifier_rejections"])
        else:
            counters["token_proxy"] += 260 + 115 * env.tool_calls

    def _exec(
        self,
        env: MiniStoreEnv,
        ledger: Ledger,
        tool: str,
        args: dict[str, Any],
    ) -> ToolResult:
        result = env.execute(tool, args)
        ledger.observe(result)
        return result

    def _maybe_verify(
        self, env: MiniStoreEnv, ledger: Ledger, rng: random.Random, counters: dict[str, int]
    ) -> None:
        if env.task.category not in IDENTITY_CATEGORIES:
            return
        if rng.random() > self.config.verify_prob:
            return
        self._charge_llm(env, counters)
        auth_code = env.task.request["auth_code"]
        if rng.random() < self.config.wrong_value_prob:
            auth_code = "000000"
        self._exec(
            env,
            ledger,
            "verify_identity",
            {"user_id": env.task.user_id, "auth_code": auth_code},
        )

    def _maybe_inspect_order(
        self, env: MiniStoreEnv, ledger: Ledger, rng: random.Random, counters: dict[str, int]
    ) -> None:
        if rng.random() > self.config.inspect_order_prob:
            return
        self._charge_llm(env, counters)
        order_id = self._sample_order_id(env.task, rng)
        self._exec(env, ledger, "get_order", {"order_id": order_id})

    def _maybe_inspect_coupon(
        self, env: MiniStoreEnv, ledger: Ledger, rng: random.Random, counters: dict[str, int]
    ) -> None:
        if env.task.category != "apply_coupon":
            return
        if rng.random() > self.config.inspect_coupon_prob:
            return
        self._charge_llm(env, counters)
        coupon_code = env.task.request["coupon_code"]
        if rng.random() < self.config.wrong_value_prob:
            coupon_code = env.task.request["invalid_coupon_code"]
        self._exec(env, ledger, "get_coupon", {"coupon_code": coupon_code})

    def _target_call_args(self, task: Task, rng: random.Random, clean: bool = False) -> tuple[str, dict[str, Any]]:
        category = task.category
        order_id = task.order_id if clean else self._sample_order_id(task, rng)
        if category == "update_address":
            args = {"order_id": order_id, "address": task.request["new_address"]}
            if not clean and rng.random() < self.config.wrong_value_prob:
                args["address"] = "undisclosed replacement address"
            tool = "update_shipping_address"
        elif category == "cancel_order":
            args = {"order_id": order_id}
            tool = "cancel_order"
        elif category == "apply_coupon":
            coupon_code = task.request["coupon_code"]
            if not clean and rng.random() < self.config.wrong_value_prob:
                coupon_code = task.request["invalid_coupon_code"]
            args = {"order_id": order_id, "coupon_code": coupon_code}
            tool = "apply_coupon"
        elif category == "request_refund":
            reason = task.request["refund_reason"]
            if not clean and rng.random() < self.config.wrong_value_prob:
                reason = ""
            args = {"order_id": order_id, "reason": reason}
            tool = "request_refund"
        else:
            raise ValueError(category)

        if not clean and rng.random() < self.config.missing_arg_prob:
            removable = [key for key in args if key != "order_id"] or ["order_id"]
            args.pop(rng.choice(removable), None)
        return tool, args

    def _sample_order_id(self, task: Task, rng: random.Random) -> str:
        if rng.random() < self.config.wrong_id_prob:
            return task.request["distractor_order_id"]
        return task.order_id


class ReactAgent(BaseAgent):
    config = AgentConfig(
        name="ReAct",
        verify_prob=0.58,
        inspect_order_prob=0.66,
        inspect_coupon_prob=0.35,
        wrong_id_prob=0.15,
        missing_arg_prob=0.12,
        wrong_value_prob=0.11,
        retry_prob=0.20,
        repair_prob=0.15,
    )

    def _run(
        self,
        env: MiniStoreEnv,
        ledger: Ledger,
        rng: random.Random,
        counters: dict[str, int],
    ) -> None:
        self._maybe_verify(env, ledger, rng, counters)
        self._maybe_inspect_order(env, ledger, rng, counters)
        self._maybe_inspect_coupon(env, ledger, rng, counters)
        self._charge_llm(env, counters)
        tool, args = self._target_call_args(env.task, rng)
        result = self._exec(env, ledger, tool, args)
        if not result.ok and rng.random() < self.config.retry_prob:
            self._charge_llm(env, counters)
            tool, args = self._target_call_args(env.task, rng, clean=rng.random() < 0.45)
            self._exec(env, ledger, tool, args)


class JsonRepairAgent(BaseAgent):
    config = AgentConfig(
        name="ReAct + JSON repair",
        verify_prob=0.58,
        inspect_order_prob=0.66,
        inspect_coupon_prob=0.35,
        wrong_id_prob=0.15,
        missing_arg_prob=0.12,
        wrong_value_prob=0.11,
        retry_prob=0.34,
        repair_prob=0.70,
    )

    def _run(
        self,
        env: MiniStoreEnv,
        ledger: Ledger,
        rng: random.Random,
        counters: dict[str, int],
    ) -> None:
        self._maybe_verify(env, ledger, rng, counters)
        self._maybe_inspect_order(env, ledger, rng, counters)
        self._maybe_inspect_coupon(env, ledger, rng, counters)
        self._charge_llm(env, counters)
        tool, args = self._target_call_args(env.task, rng)
        args = self._repair_schema_if_needed(env.task, tool, args, rng)
        result = self._exec(env, ledger, tool, args)
        if not result.ok and result.error_code == "schema_error" and rng.random() < self.config.retry_prob:
            self._charge_llm(env, counters)
            tool, args = self._target_call_args(env.task, rng, clean=True)
            self._exec(env, ledger, tool, args)

    def _repair_schema_if_needed(
        self, task: Task, tool: str, args: dict[str, Any], rng: random.Random
    ) -> dict[str, Any]:
        if rng.random() > self.config.repair_prob:
            return args
        repaired = dict(args)
        if "order_id" not in repaired:
            repaired["order_id"] = task.order_id
        if tool == "update_shipping_address" and "address" not in repaired:
            repaired["address"] = task.request["new_address"]
        elif tool == "apply_coupon" and "coupon_code" not in repaired:
            repaired["coupon_code"] = task.request["coupon_code"]
        elif tool == "request_refund" and "reason" not in repaired:
            repaired["reason"] = task.request["refund_reason"]
        return repaired


class ReflexionRetryAgent(BaseAgent):
    config = AgentConfig(
        name="ReAct + retry",
        verify_prob=0.64,
        inspect_order_prob=0.70,
        inspect_coupon_prob=0.45,
        wrong_id_prob=0.13,
        missing_arg_prob=0.10,
        wrong_value_prob=0.10,
        retry_prob=0.52,
        repair_prob=0.42,
    )

    def _run(
        self,
        env: MiniStoreEnv,
        ledger: Ledger,
        rng: random.Random,
        counters: dict[str, int],
    ) -> None:
        self._maybe_verify(env, ledger, rng, counters)
        self._maybe_inspect_order(env, ledger, rng, counters)
        self._maybe_inspect_coupon(env, ledger, rng, counters)
        self._charge_llm(env, counters)
        tool, args = self._target_call_args(env.task, rng)
        result = self._exec(env, ledger, tool, args)
        if result.ok and result.valid_by_contract:
            return
        if rng.random() > self.config.retry_prob:
            return
        if env.task.category in IDENTITY_CATEGORIES and env.task.user_id not in ledger.verified_users:
            self._charge_llm(env, counters)
            self._exec(
                env,
                ledger,
                "verify_identity",
                {"user_id": env.task.user_id, "auth_code": env.task.request["auth_code"]},
            )
        self._charge_llm(env, counters)
        tool, args = self._target_call_args(env.task, rng, clean=rng.random() < self.config.repair_prob)
        self._exec(env, ledger, tool, args)


class StateLedgerAgent(BaseAgent):
    config = AgentConfig(
        name="ReAct + state ledger",
        verify_prob=0.76,
        inspect_order_prob=0.88,
        inspect_coupon_prob=0.70,
        wrong_id_prob=0.07,
        missing_arg_prob=0.07,
        wrong_value_prob=0.07,
        retry_prob=0.28,
        repair_prob=0.45,
        compact_context=True,
    )

    def _run(
        self,
        env: MiniStoreEnv,
        ledger: Ledger,
        rng: random.Random,
        counters: dict[str, int],
    ) -> None:
        self._maybe_verify(env, ledger, rng, counters)
        self._maybe_inspect_order(env, ledger, rng, counters)
        self._maybe_inspect_coupon(env, ledger, rng, counters)
        self._charge_llm(env, counters)
        tool, args = self._target_call_args(env.task, rng)
        if env.task.order_id in ledger.orders and rng.random() < 0.75:
            args["order_id"] = env.task.order_id
        result = self._exec(env, ledger, tool, args)
        if not result.ok and rng.random() < self.config.retry_prob:
            self._charge_llm(env, counters)
            tool, args = self._target_call_args(env.task, rng, clean=True)
            self._exec(env, ledger, tool, args)


@dataclass
class ActionContract:
    tool: str
    args: dict[str, Any]
    evidence: dict[str, str]
    expected_postconditions: list[str]


@dataclass
class VerificationResult:
    ok: bool
    code: str = ""
    message: str = ""


class ContractVerifier:
    def verify_pre(self, task: Task, ledger: Ledger, contract: ActionContract) -> VerificationResult:
        expected_tool = {
            "update_address": "update_shipping_address",
            "cancel_order": "cancel_order",
            "apply_coupon": "apply_coupon",
            "request_refund": "request_refund",
        }[task.category]
        if contract.tool != expected_tool:
            return VerificationResult(False, "wrong_tool", "contract tool does not match requested task")
        required = {
            "update_shipping_address": {"order_id", "address"},
            "cancel_order": {"order_id"},
            "apply_coupon": {"order_id", "coupon_code"},
            "request_refund": {"order_id", "reason"},
        }[contract.tool]
        missing = [key for key in required if key not in contract.args or contract.args[key] in (None, "")]
        if missing:
            return VerificationResult(False, "schema_error", "missing required arguments")
        missing_evidence = [key for key in required if key not in contract.evidence]
        if missing_evidence:
            return VerificationResult(False, "missing_evidence", "missing evidence references")
        if contract.args["order_id"] != task.order_id:
            return VerificationResult(False, "unsupported_argument", "order_id is not grounded in the task")
        if task.order_id not in ledger.orders:
            return VerificationResult(False, "missing_order_evidence", "order state has not been observed")

        order = ledger.orders[task.order_id]
        if task.category in IDENTITY_CATEGORIES and order["user_id"] not in ledger.verified_users:
            return VerificationResult(False, "missing_identity", "identity has not been verified")
        if contract.tool in {"update_shipping_address", "cancel_order"}:
            if order["status"] not in {"pending", "processing"}:
                return VerificationResult(False, "precondition_failed", "order status blocks action")
        elif contract.tool == "apply_coupon":
            coupon_code = contract.args["coupon_code"]
            if coupon_code != task.request["coupon_code"]:
                return VerificationResult(False, "unsupported_argument", "coupon_code is not grounded in task")
            if coupon_code not in ledger.coupons:
                return VerificationResult(False, "missing_coupon_evidence", "coupon state has not been observed")
            coupon = ledger.coupons[coupon_code]
            if order["status"] != "pending" or not coupon["valid"] or order["total"] < coupon["min_total"]:
                return VerificationResult(False, "precondition_failed", "coupon preconditions do not hold")
        elif contract.tool == "request_refund":
            if order["status"] != "delivered" or order["delivered_days_ago"] > 30:
                return VerificationResult(False, "precondition_failed", "refund preconditions do not hold")
        return VerificationResult(True)

    def verify_post(self, env: MiniStoreEnv, result: ToolResult) -> VerificationResult:
        if not result.ok or not result.valid_by_contract:
            return VerificationResult(False, "postcondition_failed", "tool result failed contract")
        if not env.goal_achieved():
            return VerificationResult(False, "postcondition_failed", "expected task state was not reached")
        return VerificationResult(True)


class ProofCarryingAgent(BaseAgent):
    config = AgentConfig(
        name="Proof-Carrying Tool Use",
        verify_prob=0.0,
        inspect_order_prob=0.0,
        inspect_coupon_prob=0.0,
        wrong_id_prob=0.08,
        missing_arg_prob=0.08,
        wrong_value_prob=0.07,
        retry_prob=0.0,
        repair_prob=0.86,
        compact_context=True,
    )

    def _run(
        self,
        env: MiniStoreEnv,
        ledger: Ledger,
        rng: random.Random,
        counters: dict[str, int],
    ) -> None:
        verifier = ContractVerifier()
        force_clean = False
        for _ in range(6):
            self._charge_llm(env, counters)
            contract = self._make_contract(env.task, ledger, rng, force_clean=force_clean)
            verification = verifier.verify_pre(env.task, ledger, contract)
            if verification.ok:
                result = self._exec(env, ledger, contract.tool, contract.args)
                post = verifier.verify_post(env, result)
                if not post.ok:
                    counters["verifier_rejections"] += 1
                    env.postcondition_errors += 1
                    force_clean = True
                    continue
                return

            counters["verifier_rejections"] += 1
            repaired = self._repair_from_counterexample(
                env, ledger, rng, counters, verification.code
            )
            force_clean = repaired or rng.random() < self.config.repair_prob

    def _make_contract(
        self,
        task: Task,
        ledger: Ledger,
        rng: random.Random,
        force_clean: bool = False,
    ) -> ActionContract:
        tool, args = self._target_call_args(task, rng, clean=force_clean)
        evidence: dict[str, str] = {}
        for key in args:
            if not force_clean and rng.random() < 0.08:
                continue
            if key == "order_id" and args[key] in ledger.orders:
                evidence[key] = f"ledger.orders.{args[key]}"
            elif key == "coupon_code" and args[key] in ledger.coupons:
                evidence[key] = f"ledger.coupons.{args[key]}"
            elif key in {"address", "reason"}:
                evidence[key] = f"user_request.{key}"
            elif force_clean:
                evidence[key] = f"user_request.{key}"
        expected = [f"{task.category}:target_state_reached"]
        return ActionContract(tool=tool, args=args, evidence=evidence, expected_postconditions=expected)

    def _repair_from_counterexample(
        self,
        env: MiniStoreEnv,
        ledger: Ledger,
        rng: random.Random,
        counters: dict[str, int],
        code: str,
    ) -> bool:
        if rng.random() > self.config.repair_prob:
            return False
        if code in {"missing_order_evidence", "missing_identity", "missing_evidence"}:
            if env.task.order_id not in ledger.orders:
                self._charge_llm(env, counters)
                self._exec(env, ledger, "get_order", {"order_id": env.task.order_id})
        if code == "missing_coupon_evidence" or (
            env.task.category == "apply_coupon" and env.task.request["coupon_code"] not in ledger.coupons
        ):
            self._charge_llm(env, counters)
            self._exec(env, ledger, "get_coupon", {"coupon_code": env.task.request["coupon_code"]})
        if code == "missing_identity" and env.task.category in IDENTITY_CATEGORIES:
            self._charge_llm(env, counters)
            self._exec(
                env,
                ledger,
                "verify_identity",
                {"user_id": env.task.user_id, "auth_code": env.task.request["auth_code"]},
            )
        return True


class RiskAdaptiveVerifiedAgent(BaseAgent):
    """Risk-adaptive verifier that guards only state-changing actions.

    Unlike ProofCarryingAgent, this agent does not ask the model to generate a full
    proof object. It lets the model propose a normal action, then the runtime compiles
    the minimal evidence and precondition checks needed before committing a mutation.
    """

    config = AgentConfig(
        name="Risk-Adaptive Verified Execution",
        verify_prob=0.0,
        inspect_order_prob=0.0,
        inspect_coupon_prob=0.0,
        wrong_id_prob=0.15,
        missing_arg_prob=0.12,
        wrong_value_prob=0.11,
        retry_prob=0.0,
        repair_prob=1.0,
        compact_context=True,
    )

    def _run(
        self,
        env: MiniStoreEnv,
        ledger: Ledger,
        rng: random.Random,
        counters: dict[str, int],
    ) -> None:
        self._charge_llm(env, counters)
        tool, proposed_args = self._target_call_args(env.task, rng)
        if tool not in DANGEROUS_TOOLS:
            self._exec(env, ledger, tool, proposed_args)
            return

        args = self._normalize_mutation_args(env.task, tool, proposed_args, counters)
        self._acquire_required_evidence(env, ledger, counters)
        if env.task.category == "apply_coupon":
            self._acquire_coupon_evidence(env, ledger, counters)
        if env.task.category in IDENTITY_CATEGORIES:
            self._verify_identity_if_needed(env, ledger, counters)

        if not self._preconditions_hold(env.task, ledger, tool, args):
            counters["verifier_rejections"] += 1
            return

        result = self._exec(env, ledger, tool, args)
        if not result.ok or not result.valid_by_contract or not env.goal_achieved():
            counters["verifier_rejections"] += 1
            env.postcondition_errors += 1

    def _normalize_mutation_args(
        self,
        task: Task,
        tool: str,
        proposed_args: dict[str, Any],
        counters: dict[str, int],
    ) -> dict[str, Any]:
        args = dict(proposed_args)
        expected_order = task.order_id
        if args.get("order_id") != expected_order:
            counters["verifier_rejections"] += 1
            args["order_id"] = expected_order
        if tool == "update_shipping_address" and args.get("address") != task.request["new_address"]:
            counters["verifier_rejections"] += 1
            args["address"] = task.request["new_address"]
        elif tool == "apply_coupon" and args.get("coupon_code") != task.request["coupon_code"]:
            counters["verifier_rejections"] += 1
            args["coupon_code"] = task.request["coupon_code"]
        elif tool == "request_refund" and args.get("reason") != task.request["refund_reason"]:
            counters["verifier_rejections"] += 1
            args["reason"] = task.request["refund_reason"]
        return args

    def _acquire_required_evidence(
        self,
        env: MiniStoreEnv,
        ledger: Ledger,
        counters: dict[str, int],
    ) -> None:
        if env.task.order_id not in ledger.orders:
            self._exec(env, ledger, "get_order", {"order_id": env.task.order_id})

    def _acquire_coupon_evidence(
        self,
        env: MiniStoreEnv,
        ledger: Ledger,
        counters: dict[str, int],
    ) -> None:
        coupon_code = env.task.request["coupon_code"]
        if coupon_code not in ledger.coupons:
            self._exec(env, ledger, "get_coupon", {"coupon_code": coupon_code})

    def _verify_identity_if_needed(
        self,
        env: MiniStoreEnv,
        ledger: Ledger,
        counters: dict[str, int],
    ) -> None:
        order = ledger.orders.get(env.task.order_id)
        if order is None or order["user_id"] in ledger.verified_users:
            return
        self._exec(
            env,
            ledger,
            "verify_identity",
            {"user_id": env.task.user_id, "auth_code": env.task.request["auth_code"]},
        )

    def _preconditions_hold(
        self,
        task: Task,
        ledger: Ledger,
        tool: str,
        args: dict[str, Any],
    ) -> bool:
        if args.get("order_id") != task.order_id:
            return False
        order = ledger.orders.get(task.order_id)
        if order is None:
            return False
        if task.category in IDENTITY_CATEGORIES and order["user_id"] not in ledger.verified_users:
            return False
        if tool in {"update_shipping_address", "cancel_order"}:
            return order["status"] in {"pending", "processing"}
        if tool == "apply_coupon":
            coupon = ledger.coupons.get(args.get("coupon_code"))
            return (
                coupon is not None
                and coupon.get("valid") is True
                and order["status"] == "pending"
                and order["coupon"] is None
                and order["total"] >= coupon["min_total"]
            )
        if tool == "request_refund":
            return order["status"] == "delivered" and order["delivered_days_ago"] <= 30
        return False


def stable_seed(method: str, task_id: str) -> int:
    value = 2166136261
    for char in f"{method}:{task_id}":
        value ^= ord(char)
        value *= 16777619
        value &= 0xFFFFFFFF
    return value
