"""Domain adapter registry for the universal curriculum runtime.

Adapters describe interaction affordances and safety boundaries.  They do not
decide mastery; the deterministic evidence evaluator remains the owner of
route transitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DomainAdapter:
    key: str
    aliases: tuple[str, ...]
    activity_sequence: tuple[str, ...]
    interaction_kind: str
    controls: tuple[dict[str, Any], ...]
    expected_observations: tuple[str, ...]
    rubric: tuple[str, ...]
    remediation_target: str
    transfer_target: str
    safety_mode: str = "guided"
    curriculum_sequence: tuple[str, ...] | None = None

    def matches_goal(self, goal_text: str, domain: str = "") -> bool:
        haystack = f"{domain} {goal_text}".casefold()
        return self.key in haystack or any(alias in haystack for alias in self.aliases)

    def safety_policy(self) -> dict[str, Any]:
        return {
            "mode": self.safety_mode,
            "sourceRequired": self.safety_mode == "academic_source_bound",
            "personalAdviceBoundary": self.key == "medical",
        }

    def normalize_interaction(self, interaction: dict[str, Any] | None) -> dict[str, Any]:
        return interaction if isinstance(interaction, dict) else {}

    def remediation(self, concept: str) -> str:
        return self.remediation_target.replace("{concept}", concept)

    def transfer(self, concept: str) -> str:
        return self.transfer_target.replace("{concept}", concept)

    def build_activity(
        self,
        *,
        activity_type: str,
        concept: str,
        prompt: str,
        difficulty: int,
        source_ids: list[str],
        source_anchor_ids: list[str],
        prerequisites: list[str],
        requires_source: bool,
    ) -> dict[str, Any]:
        source_required = requires_source or self.safety_mode == "academic_source_bound"
        configuration = {
            "schemaVersion": "activity.v2",
            "activityType": activity_type,
            "domain": self.key,
            "adapterKind": self.interaction_kind,
            "concept": concept,
            "difficulty": max(1, min(int(difficulty), 5)),
            "taskPrompt": prompt,
            "interactiveControls": [dict(control) for control in self.controls],
            "expectedLearnerObservations": list(self.expected_observations),
            "evaluatorRubric": list(self.rubric),
            "sourceRequirements": {
                "mode": "required" if source_required else "optional",
                "requireSelectedAnchors": source_required,
            },
            "allowedResponseTypes": [
                "written_explanation", "prediction", "interaction_state",
                "selected_options", "calculations", "trace", "learner_conclusion",
            ],
            "remediationTarget": self.remediation(concept),
            "transferTarget": self.transfer(concept),
            "sourceIds": list(source_ids),
            "sourceAnchorIds": list(source_anchor_ids),
            "citations": [
                {"sourceId": source_id, "sourceAnchorId": anchor_id}
                for source_id in source_ids
                for anchor_id in source_anchor_ids
            ][:20],
            "safetyPolicy": self.safety_policy(),
        }
        return {
            "activityType": activity_type,
            "title": f"{activity_type.replace('_', ' ').title()}: {concept}",
            "prompt": prompt,
            "difficulty": max(1, min(int(difficulty), 5)),
            "prerequisites": list(prerequisites),
            "sourceIds": list(source_ids),
            "sourceAnchorIds": list(source_anchor_ids),
            "configuration": configuration,
            "remediationTarget": self.remediation(concept),
            "transferTarget": self.transfer(concept),
        }


GENERIC_ADAPTER = DomainAdapter(
    key="general",
    aliases=(),
    activity_sequence=("predict", "explain", "apply", "transfer"),
    curriculum_sequence=("predict", "explain", "compare", "apply", "debug", "analyze", "transfer"),
    interaction_kind="source_grounded_reasoning",
    controls=(
        {"id": "prediction", "kind": "text", "required": True},
        {"id": "comparison", "kind": "table", "required": True},
        {"id": "changed_condition", "kind": "text", "required": True},
    ),
    expected_observations=("prediction", "source_citation", "relationship_explanation", "changed_condition"),
    rubric=("Uses a bounded source claim", "Explains a relationship", "Tests a changed condition", "Names uncertainty"),
    remediation_target="Return to the selected source anchor for {concept}, then explain one relationship using a concrete example.",
    transfer_target="Apply {concept} to a changed condition and state which part of the source claim no longer transfers.",
)


DOMAIN_ADAPTERS: tuple[DomainAdapter, ...] = (
    DomainAdapter(
        key="dsp", aliases=("dsp", "signal processing", "fourier", "dft", "sampling", "aliasing", "reconstruction"),
        activity_sequence=("predict", "simulate", "derive", "apply", "transfer"),
        interaction_kind="sampling_spectrum_lab",
        controls=(
            {"id": "signal_frequency", "kind": "range", "min": 1, "max": 18, "step": 1, "default": 7},
            {"id": "sample_rate", "kind": "range", "min": 2, "max": 36, "step": 1, "default": 8},
            {"id": "window", "kind": "select", "options": ["rectangular", "hann", "hamming"]},
        ),
        expected_observations=("prediction", "nyquist_or_bin_observation", "spectral_leakage_explanation"),
        rubric=("Relates sample rate to Nyquist", "Explains a spectrum observation", "Names a windowing trade-off"),
        remediation_target="Return to the sampled waveform and identify the Nyquist limit and bin spacing for {concept}.",
        transfer_target="Apply {concept} to a changed sample rate or window and explain what remains reliable.",
    ),
    DomainAdapter(
        key="operating_systems", aliases=("operating system", "scheduler", "kernel"),
        activity_sequence=("predict", "explain", "derive", "simulate", "debug", "apply", "build", "transfer"),
        interaction_kind="scheduler_trace",
        controls=({"id": "topic", "kind": "select", "options": ["scheduling", "virtual_memory", "deadlock", "system_call"]}, {"id": "policy", "kind": "select", "options": ["fcfs", "round_robin", "priority"]}, {"id": "quantum", "kind": "range", "min": 1, "max": 6, "step": 1, "default": 2}, {"id": "frame_capacity", "kind": "range", "min": 2, "max": 5, "step": 1, "default": 3}, {"id": "processes", "kind": "process_table", "required": True}),
        expected_observations=("prediction", "trace", "waiting_or_turnaround_tradeoff"),
        rubric=("Uses a concrete schedule", "Names a metric trade-off", "Explains a state transition"),
        remediation_target="Trace process ready, running, and waiting states for {concept} before changing policy.",
        transfer_target="Compare {concept} for interactive and batch workloads.",
    ),
    DomainAdapter(
        key="computer_graphics", aliases=("computer graphics", "graphics", "rendering", "camera"),
        activity_sequence=("predict", "simulate", "explain", "apply", "transfer"),
        interaction_kind="transform_camera",
        controls=({"id": "translate", "kind": "vector2", "default": [0, 0]}, {"id": "rotation", "kind": "range", "min": -180, "max": 180, "step": 5, "default": 0}, {"id": "scale", "kind": "range", "min": 0.25, "max": 3, "step": 0.25, "default": 1}, {"id": "camera", "kind": "select", "options": ["world", "view", "projection"]}, {"id": "light", "kind": "vector3", "default": [1, 1, 1]}, {"id": "depth_test", "kind": "toggle", "default": True}, {"id": "sample_count", "kind": "range", "min": 1, "max": 8, "step": 1, "default": 2}),
        expected_observations=("prediction", "coordinate_or_visual_observation", "transform_explanation"),
        rubric=("Distinguishes coordinate spaces", "Predicts a visible change", "Explains matrix order or camera effect"),
        remediation_target="Apply one transform at a time for {concept} and label the coordinate space after each step.",
        transfer_target="Explain how {concept} changes when moving from world to view space.",
    ),
    DomainAdapter(
        key="ai_ml", aliases=("machine learning", "artificial intelligence", "dataset", "classification", "model"),
        activity_sequence=("predict", "simulate", "debug", "apply", "transfer"),
        interaction_kind="classification_evaluation",
        controls=({"id": "threshold", "kind": "range", "min": 0.1, "max": 0.9, "step": 0.05, "default": 0.5}, {"id": "split", "kind": "select", "options": ["stratified", "random", "leaky"]}, {"id": "slice", "kind": "select", "options": ["all", "minority", "recent_shift"]}, {"id": "regularization", "kind": "range", "min": 0, "max": 1, "step": 0.1, "default": 0.2}),
        expected_observations=("prediction", "confusion_matrix_or_metric", "error_or_leakage_explanation"),
        rubric=("Uses a bounded evaluation slice", "Names precision/recall trade-off", "Detects leakage or distribution shift"),
        remediation_target="Inspect the train/test split and a confusion-matrix row for {concept} before changing the threshold.",
        transfer_target="Design a follow-up evaluation for a shifted deployment slice of {concept}.",
    ),
    DomainAdapter(
        key="history", aliases=("history", "historical", "primary source", "archive", "institution"),
        activity_sequence=("predict", "compare", "explain", "analyze", "apply", "transfer"),
        interaction_kind="historical_evidence_map",
        controls=(
            {"id": "timeline", "kind": "timeline", "required": True},
            {"id": "actors", "kind": "relation_table", "required": True},
            {"id": "source_stance", "kind": "select", "options": ["primary", "secondary", "uncertain"]},
        ),
        expected_observations=("chronology", "source_provenance", "causal_mechanism", "uncertainty_limit"),
        rubric=("Separates chronology from causation", "Uses a bounded source claim", "Names uncertainty or disagreement"),
        remediation_target="Return to the selected source anchor for {concept} and separate actors, evidence, and interpretation.",
        transfer_target="Apply the same evidence test to a nearby historical case without assuming the pattern transfers.",
        safety_mode="academic_source_bound",
    ),
    DomainAdapter(
        key="medical", aliases=("medical", "medicine", "anatomy", "physiology", "clinical"),
        activity_sequence=("predict", "explain", "apply", "transfer"),
        interaction_kind="source_grounded_mechanism",
        controls=({"id": "structure", "kind": "select_source_anchor", "required": True}, {"id": "mechanism_map", "kind": "relation_table", "required": True}),
        expected_observations=("selected_source_anchor", "mechanism_explanation", "uncertainty_limit"),
        rubric=("Cites selected academic material", "Explains a bounded mechanism", "States uncertainty and educational limit"),
        remediation_target="Return to the selected academic anchor for {concept} and map structure, relationship, and observable function.",
        transfer_target="Compare {concept} with a nearby academic case without making a patient-specific recommendation.",
        safety_mode="academic_source_bound",
    ),
)


def get_domain_adapter(goal_text: str = "", domain: str = "") -> DomainAdapter:
    for adapter in DOMAIN_ADAPTERS:
        if adapter.matches_goal(goal_text, domain):
            return adapter
    return GENERIC_ADAPTER


def adapter_registry() -> dict[str, DomainAdapter]:
    return {adapter.key: adapter for adapter in (*DOMAIN_ADAPTERS, GENERIC_ADAPTER)}
