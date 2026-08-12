from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class SessionArtifacts:
    session_dir: str
    run_id: str
    transcript: List[Dict[str, Any]] = field(default_factory=list)
    moderator_log: List[Dict[str, Any]] = field(default_factory=list)
    run_metadata: Dict[str, Any] = field(default_factory=dict)
    session_state_final: Dict[str, Any] = field(default_factory=dict)
    config_used: Dict[str, Any] = field(default_factory=dict)
    api_calls: List[Dict[str, Any]] = field(default_factory=list)
    missing_files: List[str] = field(default_factory=list)
    missing_required_files: List[str] = field(default_factory=list)
    missing_optional_files: List[str] = field(default_factory=list)
    load_errors: List[str] = field(default_factory=list)

@dataclass
class EvidenceSpan:
    run_id: str
    turn: Optional[int]
    speaker_id: Optional[str]
    speaker_name: Optional[str]
    excerpt: str
    source_file: str
    field: Optional[str] = None

@dataclass
class Flag:
    flag_id: str
    severity: str  # critical, fail, warning, info
    track: str
    message: str
    evidence: List[EvidenceSpan] = field(default_factory=list)
    suggested_follow_up: Optional[str] = None
    metric_value: Optional[Any] = None

@dataclass
class MetricResult:
    metric_id: str
    value: Any
    status: str = "OK"  # OK, INSUFFICIENT_SAMPLE, FAILED, WARNING

@dataclass
class TrackResult:
    track_id: str
    metrics: Dict[str, MetricResult] = field(default_factory=dict)
    flags: List[Flag] = field(default_factory=list)
    status: str = "PASS" # PASS, WARNING, FAIL, BLOCKED

@dataclass
class SpeakerStats:
    speaker_id: str
    speaker_name: str
    turn_count: int = 0
    word_count: int = 0
    words_per_turn_avg: float = 0.0
    first_turn_index: Optional[int] = None
    lexical_diversity: Optional[float] = None
    topic_reference_rate: Optional[float] = None
    concrete_example_rate: Optional[float] = None
    hedging_rate: Optional[float] = None
    certainty_rate: Optional[float] = None
    first_person_rate: Optional[float] = None

@dataclass
class RecommendationResult:
    recommendation: str
    triggered_rules: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)
    failed_tracks: List[str] = field(default_factory=list)
    warning_tracks: List[str] = field(default_factory=list)
    why_not_other_buckets: Dict[str, str] = field(default_factory=dict)

@dataclass
class AssessmentResult:
    run_id: str
    tracks: Dict[str, TrackResult] = field(default_factory=dict)
    speaker_stats: Dict[str, SpeakerStats] = field(default_factory=dict)
    interaction_edges: List[Dict[str, Any]] = field(default_factory=list)
    recommendation: Optional[RecommendationResult] = None
    manifest: Dict[str, Any] = field(default_factory=dict)
