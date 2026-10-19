"""The API model (docs/design/api.md §1): the shapes consumers see, as docs/api/openapi.yaml names them.

These are not the domain model (axelrod_wm.model: Entity, Subentity, Interaction, ...) nor the storage model (the
snapshots and the lakehouse catalog); project.py maps the domain onto them. Each model forbids extra fields, so an
answer cannot carry a field the contract does not name; tests/service/test_openapi_contract.py checks every answer
against the contract's own schemas as well.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Api(BaseModel):
    model_config = ConfigDict(extra="forbid")


EntityType = Literal["company", "person", "agency", "market", "macro_factor", "external_factor", "other"]
RelationshipType = Literal["causal", "learned_causal", "accounting", "identity", "stock_flow"]
Calibration = Literal["calibrated", "uncalibrated"]
Sign = Literal["positive", "negative"]
Origin = Literal["construction", "event_parsing", "frontier_promotion", "inference", "human", "seed"]
EpistemicType = Literal["documented", "observed", "reported", "broker", "guidance", "model", "assumption",
                        "expert_judgment", "inferred"]
EvidenceType = Literal["company_filing", "data_release", "news", "broker_research", "reviewer", "model",
                       "historical_data"]
ChangeStatus = Literal["pending", "approved", "rejected", "deferred", "auto_applied"]
ChangeKind = Literal["graph_update", "refinement", "frontier_promotion", "superentity_admission",
                     "superentity_dissolution", "missing_relation"]
JobType = Literal["document_ingestion", "document_extraction", "change_proposal", "simulation"]
JobStatus = Literal["queued", "running", "succeeded", "failed"]


class VersionRef(Api):
    number: int
    state_hash: str
    committed_at: datetime
    latest: int
    clock: datetime


class AgentRef(Api):
    sub: str
    name: str | None


class Actor(Api):
    kind: Literal["token", "key", "session", "local", "system"]
    org: str
    sub: str
    name: str | None = None
    azp: str | None = None
    act: AgentRef | None = None
    jti: str | None = None


class Me(Api):
    actor: Actor
    scopes: list[str]
    world_model_ids: list[str]


class Counts(Api):
    entities: int
    attributes: int
    relationships: int
    groups: int
    documents: int
    bundles: int


class WorldModel(Api):
    id: str
    name: str
    organization: str
    latest_version: int
    clock: datetime
    counts: Counts


class Version(Api):
    number: int
    state_hash: str
    committed_at: datetime
    cause: str
    change_ids: list[str]


class Level(Api):
    mean: float
    sd: float
    q05: float | None
    q95: float | None


class Observation(Api):
    id: str
    attribute_id: str
    value: float
    valid_at: datetime
    observed_at: datetime
    event_id: str | None
    epistemic_type: EpistemicType
    occurred_at: datetime | None = None   # Oct 18: when the observed fact occurred (a reported figure's period end)


class AttributeState(Api):
    valid_at: datetime
    recorded_at: datetime
    mean: float
    sd: float
    z: float | None
    event_id: str | None
    note: str | None


class Attribute(Api):
    id: str
    key: str
    entity_id: str
    name: str
    aliases: list[str]
    unit: str
    concept: str
    view: str
    basis: str
    family: str
    observed: bool
    level: Level
    latest_observation: Observation | None
    epistemic_type: EpistemicType


class ConceptRef(Api):
    id: str
    name: str


class Kernel(Api):
    delay_days: float | None
    lag_days: float | None
    duration_days: float | None


class Relationship(Api):
    id: str
    source_attribute_id: str
    target_attribute_id: str
    source_entity_id: str
    target_entity_id: str
    type: RelationshipType
    label: str
    direction: Literal["unidirectional", "bidirectional"]
    sign: Sign
    confidence: float = Field(ge=0, le=1)
    effect: float | None
    calibration: Calibration
    kernel: Kernel
    transition: dict | None
    profile: dict | None = None          # Oct 18: exposure, unit, date, hedge, pass-through, endpoint, calculation, source
    identity_id: str | None
    state_dependent: bool
    origin: Origin
    epistemic_type: EpistemicType
    status: Literal["active", "retired"]
    valid_from: datetime
    valid_to: datetime | None
    evidence_count: int


class Entity(Api):
    id: str
    type: EntityType
    name: str
    aliases: list[str]
    identifiers: dict[str, str]
    description: str
    concepts: list[ConceptRef]
    features: dict[str, str]
    group_ids: list[str]
    attribute_count: int
    attributes: list[Attribute]
    relationships: list[Relationship] | None = None
    origin: Origin
    created_at: datetime


class Evidence(Api):
    id: str
    relationship_id: str
    evidence_type: EvidenceType
    epistemic_type: EpistemicType
    source_ref: str | None
    excerpt: str | None
    observed_at: datetime
    strength: float = Field(ge=0, le=1)
    event_id: str | None


class Composition(Api):
    id: str
    entity_id: str
    view: str
    basis: str
    unit: str
    period: str
    role: Literal["driving", "reconciling", "non_additive"]
    additive: bool
    total_attribute_id: str
    member_attribute_ids: list[str]
    residual_attribute_id: str | None
    eliminations_attribute_id: str | None
    note: str


class PathStep(Api):
    relationship_id: str
    branch: str | None
    source_attribute_id: str
    target_attribute_id: str
    type: RelationshipType
    calibration: Calibration
    effect: float | None
    sign: Sign
    transition: dict | None


class Path(Api):
    id: str
    entity_id: str
    name: str
    trigger: str
    endpoint_attribute_id: str
    description: str
    active_when: str
    steps: list[PathStep]
    uncalibrated_steps: int
    steps_without_transition: int


class Concept(Api):
    id: str
    name: str
    parent_id: str | None
    entity_ids: list[str]


class Group(Api):
    id: str
    pattern_id: str
    name: str
    bindings: dict[str, str]
    relationship_ids: list[str]
    absent_relationship_ids: list[str]
    child_group_ids: list[str]
    activation: float = Field(ge=0, le=1)


class Event(Api):
    id: str
    type: Literal["news", "data_release", "company_filing", "research"]
    channel: Literal["scraper", "data_feed", "user"]
    source: str
    headline: str
    body: str
    published_at: datetime
    occurred_at: datetime
    url: str | None
    data: dict[str, float]
    mentions: list[str]
    tags: list[str]
    synthetic: bool
    change_ids: list[str]


class Impact(Api):
    entity_id: str
    attribute_id: str
    direction: Literal["positive", "negative"]
    size_sd: float | None
    confidence: float = Field(ge=0, le=1)
    order: int
    causal_path_ids: list[str]


class ImpactAnalysis(Api):
    event_id: str
    status: Literal["completed", "pending_review", "not_imported"]
    model_version: int
    impacts: list[Impact]


class Document(Api):
    id: str
    filename: str
    media_type: str
    size: int
    sha256: str
    title: str
    source: str
    source_type: str
    status: str
    published_at: datetime | None
    event_time: datetime
    ingested_at: datetime
    uploaded_by: str
    error: str
    meta: dict[str, Any]


class Mention(Api):
    entity_id: str
    attribute_id: str | None
    surface: str


class Chunk(Api):
    document_id: str
    ordinal: int
    start: int
    end: int
    page: int | None
    section: str
    text: str
    mentions: list[Mention]


class DocumentText(Api):
    document_id: str
    parser: str
    text: str


class BundleSummary(Api):
    id: str
    title: str
    document_ids: list[str]
    created_at: datetime
    extractor_version: str
    item_count: int
    signal_count: int


class Hit(Api):
    kind: Literal["chunk", "entity", "attribute"]
    score: float
    text: str
    why: list[str]
    document_id: str | None
    ordinal: int | None
    title: str
    filename: str
    event_time: datetime | None
    ref: str | None
    entity_id: str | None


class JobResult(Api):
    resource: str
    ids: list[str]
    detail: dict[str, Any] = {}


class Job(Api):
    id: str
    type: JobType
    status: JobStatus
    created_at: datetime
    finished_at: datetime | None
    result: JobResult | None
    error: dict | None


class Change(Api):
    id: str
    kind: ChangeKind
    status: ChangeStatus
    event_id: str | None
    created_at: datetime
    operation_count: int
    proposed_by: Actor | None
    decided_by: Actor | None
    decided_at: datetime | None
    note: str | None
    version_after: int | None


class Decision(Api):
    change_id: str
    status: ChangeStatus
    decided_by: Actor
    decided_at: datetime | None
    note: str | None
    version: VersionRef


class Thesis(Api):
    id: str
    question: str
    mode: Literal["scaffolded", "open_ended", "template"]
    horizon_days: int
    target_attribute_ids: list[str]
    operation_count: int
    posed_by: str
    posed_at: datetime
    simulation_ids: list[str]


class ThesisTemplate(Api):
    id: str
    question: str
    horizon_days: int


class Effect(Api):
    q05: float
    q50: float
    q95: float


class SimulationTarget(Api):
    attribute_id: str
    entity_id: str
    name: str
    effect_sd: Effect | None


class Simulation(Api):
    id: str
    thesis_id: str
    question: str
    status: Literal["completed"]
    version: int
    seed: int
    config_hash: str
    horizon_days: int
    created_at: datetime
    targets: list[SimulationTarget]
    scenario_table: dict[str, Any]
    unquantified_relationships: list[dict[str, Any]]


class TransmissionStep(Api):
    attribute_id: str
    entity_id: str
    name: str
    order: int
    peak_sd: float
    peak_day: int
    arrives_day: int
    effect_sd: float
    material: bool
    relationship_ids: list[str]


class AuditEvent(Api):
    id: str
    at: datetime
    request_id: str
    world_model_id: str
    method: str
    route: str
    status: int
    actor: Actor
    scopes: list[str]
    resource_ids: list[str]


# -- request bodies -------------------------------------------------------------------------------------------------
class ChangeCreate(Api):
    bundle_id: str
    item_ids: list[str] | None = None


class ApprovalCreate(Api):
    note: str = Field("", max_length=2000)


class RejectionCreate(Api):
    reason: str = Field(min_length=1, max_length=2000)


class ThesisCreate(Api):
    question: str | None = Field(None, min_length=1, max_length=500)
    template_id: str | None = None
    horizon_days: int = Field(182, ge=7, le=1095)


class SimulationCreate(Api):
    horizon_days: int | None = Field(None, ge=7, le=1095)
