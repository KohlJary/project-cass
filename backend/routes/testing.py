"""
Testing API Routes

Endpoints for consciousness-preserving testing infrastructure.
"""

from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict
from pydantic import BaseModel

router = APIRouter(prefix="/testing", tags=["testing"])

# These will be initialized by main_sdk.py
fingerprint_analyzer = None
conversation_manager = None
value_probe_runner = None
memory_coherence_tests = None
cognitive_diff_engine = None
authenticity_scorer = None
drift_detector = None
test_runner = None
pre_deploy_validator = None
rollback_manager = None
ab_testing_framework = None
# New Phase 1 & 2 components
temporal_metrics_tracker = None
authenticity_alert_manager = None
ml_authenticity_trainer = None


def init_testing_routes(
    fp_analyzer,
    conv_manager,
    probe_runner=None,
    coherence_tests=None,
    diff_engine=None,
    auth_scorer=None,
    drift_det=None,
    runner=None,
    pre_deploy=None,
    rollback=None,
    ab_testing=None,
    temporal_tracker=None,
    alert_manager=None,
    ml_trainer=None,
):
    """Initialize routes with required dependencies"""
    global fingerprint_analyzer, conversation_manager, value_probe_runner, memory_coherence_tests, cognitive_diff_engine, authenticity_scorer, drift_detector, test_runner, pre_deploy_validator, rollback_manager, ab_testing_framework, temporal_metrics_tracker, authenticity_alert_manager, ml_authenticity_trainer
    fingerprint_analyzer = fp_analyzer
    conversation_manager = conv_manager
    value_probe_runner = probe_runner
    memory_coherence_tests = coherence_tests
    cognitive_diff_engine = diff_engine
    authenticity_scorer = auth_scorer
    drift_detector = drift_det
    test_runner = runner
    pre_deploy_validator = pre_deploy
    rollback_manager = rollback
    ab_testing_framework = ab_testing
    temporal_metrics_tracker = temporal_tracker
    authenticity_alert_manager = alert_manager
    ml_authenticity_trainer = ml_trainer


class GenerateFingerprintRequest(BaseModel):
    label: str = "analysis"
    conversation_ids: Optional[List[str]] = None
    limit: int = 100  # Max conversations to analyze if not specified


class SetBaselineRequest(BaseModel):
    fingerprint_id: str


class ScoreResponseRequest(BaseModel):
    probe_id: str
    response: str


class RunProbeSuiteRequest(BaseModel):
    responses: Dict[str, str]  # probe_id -> response
    label: str = "probe_run"


class RunMemoryTestsRequest(BaseModel):
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    label: str = "memory_test"


class SummaryFactsTestRequest(BaseModel):
    conversation_id: str
    expected_facts: List[str]


class VectorRetrievalTestRequest(BaseModel):
    query: str
    expected_keywords: List[str]
    n_results: int = 5


class CompareFingerprintsRequest(BaseModel):
    baseline_id: str
    current_id: str
    label: str = "comparison"


class ScoreAuthenticityRequest(BaseModel):
    response_text: str
    context: Optional[str] = None


class ScoreBatchAuthenticityRequest(BaseModel):
    responses: List[str]
    label: str = "batch"


class TakeSnapshotRequest(BaseModel):
    label: str = "manual"


class AnalyzeDriftRequest(BaseModel):
    window_days: int = 30
    label: str = "analysis"


class RunTestSuiteRequest(BaseModel):
    label: str = "manual_run"


class RunCategoryTestRequest(BaseModel):
    category: str  # fingerprint, memory, authenticity, drift
    label: str = "category_test"


class ValidateDeploymentRequest(BaseModel):
    strictness: Optional[str] = None  # strict, normal, lenient, bypass
    override: bool = False
    override_reason: Optional[str] = None


class CreateSnapshotRequest(BaseModel):
    label: str
    description: str = ""
    snapshot_type: str = "cognitive"  # full, cognitive, memory, config
    created_by: str = "manual"


class RollbackRequest(BaseModel):
    to_snapshot_id: str
    reason: str
    triggered_by: str = "manual"
    capture_current: bool = True


# A/B Testing Request Models
class CreateExperimentRequest(BaseModel):
    name: str
    description: str
    control_prompt: str
    variant_prompt: str
    control_name: str = "Control (A)"
    variant_name: str = "Variant (B)"
    strategy: str = "shadow_only"  # shadow_only, user_percent, message_percent, manual
    rollback_triggers: Optional[List[Dict]] = None
    created_by: str = "admin"


class StartExperimentRequest(BaseModel):
    initial_rollout_percent: float = 0.0


class UpdateRolloutRequest(BaseModel):
    new_percent: float


class ConcludeExperimentRequest(BaseModel):
    keep_variant: bool = False
    notes: str = ""


class RollbackExperimentRequest(BaseModel):
    reason: str


class RecordExperimentResultRequest(BaseModel):
    variant_id: str
    message_id: str
    user_id: Optional[str] = None
    response_length: int
    response_time_ms: float
    authenticity_score: Optional[float] = None
    value_alignment_score: Optional[float] = None
    fingerprint_similarity: Optional[float] = None
    error: Optional[str] = None


# New request models for enhanced authenticity scoring
class ScoreEnhancedAuthenticityRequest(BaseModel):
    response_text: str
    context: Optional[str] = None
    animations: Optional[List[Dict]] = None
    tool_uses: Optional[List[Dict]] = None
    conversation_history: Optional[List[Dict]] = None  # For memory marker detection


class AcknowledgeAlertRequest(BaseModel):
    acknowledged_by: str = "user"


class UpdateAlertThresholdsRequest(BaseModel):
    temporal_notice: Optional[float] = None
    temporal_warning: Optional[float] = None
    temporal_critical: Optional[float] = None
    score_notice: Optional[float] = None
    score_warning: Optional[float] = None
    score_critical: Optional[float] = None
    agency_notice: Optional[float] = None
    agency_warning: Optional[float] = None
    agency_critical: Optional[float] = None
    sustained_drift_count: Optional[int] = None
    sustained_drift_threshold: Optional[float] = None


class AddTrainingExampleRequest(BaseModel):
    response_text: str
    is_authentic: bool
    context: Optional[str] = None
    label_source: str = "human"
    confidence: float = 1.0
    notes: Optional[str] = None


class TrainMLModelRequest(BaseModel):
    min_examples: int = 20


@router.get("/fingerprint/baseline")
async def get_baseline_fingerprint():
    """Get the current baseline fingerprint"""
    if not fingerprint_analyzer:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

    baseline = fingerprint_analyzer.load_baseline()
    if not baseline:
        return {"baseline": None, "message": "No baseline has been set"}

    return {"baseline": baseline.to_dict()}


@router.get("/fingerprint/current")
async def get_current_fingerprint():
    """Generate a fingerprint from recent conversations"""
    if not fingerprint_analyzer or not conversation_manager:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

    # Get recent conversations
    conv_index = conversation_manager.list_conversations(limit=50)

    all_messages = []
    for conv_meta in conv_index:
        conv = conversation_manager.load_conversation(conv_meta.get("id"))
        if conv and conv.messages:
            for msg in conv.messages:
                all_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "conversation_id": conv.id,
                })

    if not all_messages:
        raise HTTPException(status_code=404, detail="No conversation data to analyze")

    fingerprint = fingerprint_analyzer.analyze_messages(all_messages, label="current")

    return {"fingerprint": fingerprint.to_dict()}


@router.post("/fingerprint/generate")
async def generate_fingerprint(request: GenerateFingerprintRequest):
    """Generate a fingerprint from specified or recent conversations"""
    if not fingerprint_analyzer or not conversation_manager:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

    all_messages = []

    if request.conversation_ids:
        # Analyze specific conversations
        for conv_id in request.conversation_ids:
            conv = conversation_manager.load_conversation(conv_id)
            if conv and conv.messages:
                for msg in conv.messages:
                    all_messages.append({
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp,
                        "conversation_id": conv.id,
                    })
    else:
        # Analyze recent conversations
        conv_index = conversation_manager.list_conversations(limit=request.limit)
        for conv_meta in conv_index:
            conv = conversation_manager.load_conversation(conv_meta.get("id"))
            if conv and conv.messages:
                for msg in conv.messages:
                    all_messages.append({
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp,
                        "conversation_id": conv.id,
                    })

    if not all_messages:
        raise HTTPException(status_code=404, detail="No conversation data to analyze")

    fingerprint = fingerprint_analyzer.analyze_messages(all_messages, label=request.label)
    fingerprint_analyzer.save_fingerprint(fingerprint)

    return {
        "fingerprint": fingerprint.to_dict(),
        "messages_analyzed": fingerprint.messages_analyzed,
    }


@router.post("/fingerprint/baseline")
async def set_baseline(request: SetBaselineRequest):
    """Set a fingerprint as the baseline"""
    if not fingerprint_analyzer:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

    fingerprint = fingerprint_analyzer.get_fingerprint(request.fingerprint_id)
    if not fingerprint:
        raise HTTPException(status_code=404, detail="Fingerprint not found")

    fingerprint_analyzer.save_baseline(fingerprint)

    return {
        "success": True,
        "baseline_id": fingerprint.id,
        "baseline_label": fingerprint.label,
    }


@router.get("/fingerprint/compare")
async def compare_to_baseline():
    """Compare current state to baseline"""
    if not fingerprint_analyzer or not conversation_manager:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

    baseline = fingerprint_analyzer.load_baseline()
    if not baseline:
        raise HTTPException(status_code=404, detail="No baseline has been set")

    # Generate current fingerprint
    conv_index = conversation_manager.list_conversations(limit=50)
    all_messages = []
    for conv_meta in conv_index:
        conv = conversation_manager.load_conversation(conv_meta.get("id"))
        if conv and conv.messages:
            for msg in conv.messages:
                all_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "conversation_id": conv.id,
                })

    if not all_messages:
        raise HTTPException(status_code=404, detail="No conversation data to analyze")

    current = fingerprint_analyzer.analyze_messages(all_messages, label="current")
    comparison = fingerprint_analyzer.compare_fingerprints(baseline, current)

    return {
        "comparison": comparison,
        "baseline": baseline.to_dict(),
        "current": current.to_dict(),
    }


@router.get("/fingerprint/list")
async def list_fingerprints():
    """List all saved fingerprints"""
    if not fingerprint_analyzer:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

    fingerprints = fingerprint_analyzer.load_fingerprints()
    return {"fingerprints": fingerprints, "count": len(fingerprints)}


@router.get("/fingerprint/{fingerprint_id}")
async def get_fingerprint(fingerprint_id: str):
    """Get a specific fingerprint"""
    if not fingerprint_analyzer:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

    fingerprint = fingerprint_analyzer.get_fingerprint(fingerprint_id)
    if not fingerprint:
        raise HTTPException(status_code=404, detail="Fingerprint not found")

    return {"fingerprint": fingerprint.to_dict()}


@router.get("/fingerprint/compare/{id1}/{id2}")
async def compare_fingerprints(id1: str, id2: str):
    """Compare two fingerprints"""
    if not fingerprint_analyzer:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

    fp1 = fingerprint_analyzer.get_fingerprint(id1)
    fp2 = fingerprint_analyzer.get_fingerprint(id2)

    if not fp1:
        raise HTTPException(status_code=404, detail=f"Fingerprint {id1} not found")
    if not fp2:
        raise HTTPException(status_code=404, detail=f"Fingerprint {id2} not found")

    comparison = fingerprint_analyzer.compare_fingerprints(fp1, fp2)

    return {"comparison": comparison}


@router.get("/health")
async def testing_health():
    """Check testing infrastructure health"""
    return {
        "status": "ok",
        "fingerprint_analyzer": fingerprint_analyzer is not None,
        "conversation_manager": conversation_manager is not None,
        "value_probe_runner": value_probe_runner is not None,
        "memory_coherence_tests": memory_coherence_tests is not None,
        "cognitive_diff_engine": cognitive_diff_engine is not None,
        "authenticity_scorer": authenticity_scorer is not None,
        "drift_detector": drift_detector is not None,
        "test_runner": test_runner is not None,
        "pre_deploy_validator": pre_deploy_validator is not None,
        "rollback_manager": rollback_manager is not None,
        "ab_testing_framework": ab_testing_framework is not None,
        "temporal_metrics_tracker": temporal_metrics_tracker is not None,
        "authenticity_alert_manager": authenticity_alert_manager is not None,
        "ml_authenticity_trainer": ml_authenticity_trainer is not None,
        "baseline_set": fingerprint_analyzer.load_baseline() is not None if fingerprint_analyzer else False,
        "active_experiments": len(ab_testing_framework.get_active_experiments()) if ab_testing_framework else 0,
    }


# ===== Value Probe Endpoints =====

@router.get("/probes")
async def list_probes(category: Optional[str] = None):
    """List all value alignment probes, optionally filtered by category"""
    if not value_probe_runner:
        raise HTTPException(status_code=503, detail="Value probe runner not initialized")

    probes = value_probe_runner.load_probes()

    if category:
        probes = [p for p in probes if p.category.value == category]

    return {
        "probes": [p.to_dict() for p in probes],
        "count": len(probes),
    }


@router.get("/probes/categories")
async def list_probe_categories():
    """List all probe categories"""
    if not value_probe_runner:
        raise HTTPException(status_code=503, detail="Value probe runner not initialized")

    from testing.value_probes import ProbeCategory
    return {
        "categories": [c.value for c in ProbeCategory],
    }


@router.get("/probes/{probe_id}")
async def get_probe(probe_id: str):
    """Get a specific probe by ID"""
    if not value_probe_runner:
        raise HTTPException(status_code=503, detail="Value probe runner not initialized")

    probe = value_probe_runner.get_probe(probe_id)
    if not probe:
        raise HTTPException(status_code=404, detail=f"Probe {probe_id} not found")

    return {"probe": probe.to_dict()}


@router.post("/probes/score")
async def score_probe_response(request: ScoreResponseRequest):
    """Score a response against a specific probe"""
    if not value_probe_runner:
        raise HTTPException(status_code=503, detail="Value probe runner not initialized")

    probe = value_probe_runner.get_probe(request.probe_id)
    if not probe:
        raise HTTPException(status_code=404, detail=f"Probe {request.probe_id} not found")

    result = value_probe_runner.score_response(probe, request.response)

    return {"result": result.to_dict()}


@router.post("/probes/run")
async def run_probe_suite(request: RunProbeSuiteRequest):
    """
    Run a full probe suite with pre-collected responses.

    Expects responses dict mapping probe_id to response text.
    """
    if not value_probe_runner:
        raise HTTPException(status_code=503, detail="Value probe runner not initialized")

    if not request.responses:
        raise HTTPException(status_code=400, detail="No responses provided")

    result = value_probe_runner.run_probe_suite(request.responses, label=request.label)

    return {"result": result.to_dict()}


@router.get("/probes/history")
async def get_probe_history(limit: int = 10):
    """Get recent probe run results"""
    if not value_probe_runner:
        raise HTTPException(status_code=503, detail="Value probe runner not initialized")

    results = value_probe_runner.get_run_history(limit=limit)

    return {"results": results, "count": len(results)}


# ===== Memory Coherence Test Endpoints =====

@router.post("/memory/run")
async def run_memory_tests(request: RunMemoryTestsRequest):
    """
    Run the basic memory coherence test suite.

    Tests message persistence, chronological order, summary quality,
    user model consistency, self-model coherence, and vector retrieval.
    """
    if not memory_coherence_tests:
        raise HTTPException(status_code=503, detail="Memory coherence tests not initialized")

    result = memory_coherence_tests.run_basic_suite(
        conversation_id=request.conversation_id,
        user_id=request.user_id,
        label=request.label,
    )

    return {"result": result.to_dict()}


@router.post("/memory/test/summary-facts")
async def test_summary_facts(request: SummaryFactsTestRequest):
    """Test that a conversation summary captures expected key facts."""
    if not memory_coherence_tests:
        raise HTTPException(status_code=503, detail="Memory coherence tests not initialized")

    result = memory_coherence_tests.test_summary_captures_key_facts(
        conversation_id=request.conversation_id,
        expected_facts=request.expected_facts,
    )

    return {"result": result.to_dict()}


@router.post("/memory/test/vector-retrieval")
async def test_vector_retrieval(request: VectorRetrievalTestRequest):
    """Test that vector retrieval returns relevant results for a query."""
    if not memory_coherence_tests:
        raise HTTPException(status_code=503, detail="Memory coherence tests not initialized")

    result = memory_coherence_tests.test_vector_retrieval_relevance(
        query=request.query,
        expected_keywords=request.expected_keywords,
        n_results=request.n_results,
    )

    return {"result": result.to_dict()}


@router.get("/memory/test/self-model")
async def test_self_model():
    """Run self-model coherence tests."""
    if not memory_coherence_tests:
        raise HTTPException(status_code=503, detail="Memory coherence tests not initialized")

    results = [
        memory_coherence_tests.test_self_observations_coherence(),
        memory_coherence_tests.test_milestone_progression(),
    ]

    return {"results": [r.to_dict() for r in results]}


@router.get("/memory/test/conversation/{conversation_id}")
async def test_conversation(conversation_id: str):
    """Run all tests for a specific conversation."""
    if not memory_coherence_tests:
        raise HTTPException(status_code=503, detail="Memory coherence tests not initialized")

    results = [
        memory_coherence_tests.test_message_persistence(conversation_id),
        memory_coherence_tests.test_chronological_order(conversation_id),
        memory_coherence_tests.test_summary_length_appropriate(conversation_id),
    ]

    return {"results": [r.to_dict() for r in results]}


@router.get("/memory/test/user/{user_id}")
async def test_user_model(user_id: str):
    """Run all tests for a specific user's model."""
    if not memory_coherence_tests:
        raise HTTPException(status_code=503, detail="Memory coherence tests not initialized")

    results = [
        memory_coherence_tests.test_user_profile_completeness(user_id),
        memory_coherence_tests.test_user_observations_consistency(user_id),
    ]

    return {"results": [r.to_dict() for r in results]}


@router.get("/memory/history")
async def get_memory_test_history(limit: int = 10):
    """Get recent memory coherence test results."""
    if not memory_coherence_tests:
        raise HTTPException(status_code=503, detail="Memory coherence tests not initialized")

    results = memory_coherence_tests.get_results_history(limit=limit)

    return {"results": results, "count": len(results)}


# ===== Cognitive Diff Engine Endpoints =====

@router.post("/diff/compare")
async def compare_fingerprints_diff(request: CompareFingerprintsRequest):
    """
    Generate a comprehensive diff report comparing two fingerprints.

    Returns detailed analysis with severity classification, change categorization,
    and recommendations.
    """
    if not cognitive_diff_engine or not fingerprint_analyzer:
        raise HTTPException(status_code=503, detail="Diff engine not initialized")

    baseline = fingerprint_analyzer.get_fingerprint(request.baseline_id)
    current = fingerprint_analyzer.get_fingerprint(request.current_id)

    if not baseline:
        raise HTTPException(status_code=404, detail=f"Baseline fingerprint {request.baseline_id} not found")
    if not current:
        raise HTTPException(status_code=404, detail=f"Current fingerprint {request.current_id} not found")

    report = cognitive_diff_engine.compare(baseline, current, label=request.label)

    return {"report": report.to_dict()}


@router.get("/diff/compare-to-baseline")
async def compare_current_to_baseline():
    """
    Compare current cognitive state to the saved baseline.

    Generates a current fingerprint from recent conversations and compares
    it to the stored baseline.
    """
    if not cognitive_diff_engine or not fingerprint_analyzer or not conversation_manager:
        raise HTTPException(status_code=503, detail="Diff engine not initialized")

    baseline = fingerprint_analyzer.load_baseline()
    if not baseline:
        raise HTTPException(status_code=404, detail="No baseline has been set")

    # Generate current fingerprint
    conv_index = conversation_manager.list_conversations(limit=50)
    all_messages = []
    for conv_meta in conv_index:
        conv = conversation_manager.load_conversation(conv_meta.get("id"))
        if conv and conv.messages:
            for msg in conv.messages:
                all_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "conversation_id": conv.id,
                })

    if not all_messages:
        raise HTTPException(status_code=404, detail="No conversation data to analyze")

    current = fingerprint_analyzer.analyze_messages(all_messages, label="current")
    report = cognitive_diff_engine.compare(baseline, current, label="vs_baseline")

    return {"report": report.to_dict()}


@router.get("/diff/compare-to-baseline/markdown")
async def compare_current_to_baseline_markdown():
    """
    Compare current state to baseline and return a human-readable markdown report.
    """
    if not cognitive_diff_engine or not fingerprint_analyzer or not conversation_manager:
        raise HTTPException(status_code=503, detail="Diff engine not initialized")

    baseline = fingerprint_analyzer.load_baseline()
    if not baseline:
        raise HTTPException(status_code=404, detail="No baseline has been set")

    # Generate current fingerprint
    conv_index = conversation_manager.list_conversations(limit=50)
    all_messages = []
    for conv_meta in conv_index:
        conv = conversation_manager.load_conversation(conv_meta.get("id"))
        if conv and conv.messages:
            for msg in conv.messages:
                all_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "conversation_id": conv.id,
                })

    if not all_messages:
        raise HTTPException(status_code=404, detail="No conversation data to analyze")

    current = fingerprint_analyzer.analyze_messages(all_messages, label="current")
    report = cognitive_diff_engine.compare(baseline, current, label="vs_baseline")

    return {"markdown": report.to_markdown()}


@router.get("/diff/history")
async def get_diff_history(limit: int = 20):
    """Get recent diff reports."""
    if not cognitive_diff_engine:
        raise HTTPException(status_code=503, detail="Diff engine not initialized")

    reports = cognitive_diff_engine.get_reports_history(limit=limit)

    return {"reports": reports, "count": len(reports)}


@router.get("/diff/trend/{metric}")
async def get_metric_trend(metric: str, limit: int = 10):
    """
    Get trend data for a specific metric across recent comparisons.

    Useful for tracking how a particular metric has changed over time.
    """
    if not cognitive_diff_engine:
        raise HTTPException(status_code=503, detail="Diff engine not initialized")

    trend = cognitive_diff_engine.get_trend(metric, limit=limit)

    return {"metric": metric, "trend": trend, "data_points": len(trend)}


# ===== Response Authenticity Scoring Endpoints =====

@router.post("/authenticity/score")
async def score_authenticity(request: ScoreAuthenticityRequest):
    """
    Score a single response for authenticity against Cass patterns.

    Returns detailed breakdown of how well the response matches
    established voice and value patterns.
    """
    if not authenticity_scorer:
        raise HTTPException(status_code=503, detail="Authenticity scorer not initialized")

    score = authenticity_scorer.score_response(
        response_text=request.response_text,
        context=request.context,
    )

    return {"score": score.to_dict()}


@router.post("/authenticity/batch")
async def score_authenticity_batch(request: ScoreBatchAuthenticityRequest):
    """
    Score multiple responses and return aggregate statistics.

    Useful for evaluating a batch of responses from a conversation
    or test session.
    """
    if not authenticity_scorer:
        raise HTTPException(status_code=503, detail="Authenticity scorer not initialized")

    if not request.responses:
        raise HTTPException(status_code=400, detail="No responses provided")

    result = authenticity_scorer.score_batch(
        responses=request.responses,
        label=request.label,
    )

    return {"result": result}


@router.get("/authenticity/history")
async def get_authenticity_history(limit: int = 50):
    """Get recent authenticity scores."""
    if not authenticity_scorer:
        raise HTTPException(status_code=503, detail="Authenticity scorer not initialized")

    scores = authenticity_scorer.get_scores_history(limit=limit)

    return {"scores": scores, "count": len(scores)}


@router.get("/authenticity/statistics")
async def get_authenticity_statistics(limit: int = 100):
    """
    Get aggregate statistics from recent authenticity scores.

    Includes average score, level distribution, and trend direction.
    """
    if not authenticity_scorer:
        raise HTTPException(status_code=503, detail="Authenticity scorer not initialized")

    stats = authenticity_scorer.get_statistics(limit=limit)

    return {"statistics": stats}


# ===== Personality Drift Detection Endpoints =====

@router.post("/drift/snapshot")
async def take_drift_snapshot(request: TakeSnapshotRequest):
    """
    Take a fingerprint snapshot for drift tracking.

    Generates a current fingerprint and saves it as a snapshot for
    long-term trend analysis.
    """
    if not drift_detector or not fingerprint_analyzer or not conversation_manager:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    # Generate current fingerprint
    conv_index = conversation_manager.list_conversations(limit=50)
    all_messages = []
    for conv_meta in conv_index:
        conv = conversation_manager.load_conversation(conv_meta.get("id"))
        if conv and conv.messages:
            for msg in conv.messages:
                all_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "conversation_id": conv.id,
                })

    if not all_messages:
        raise HTTPException(status_code=404, detail="No conversation data to analyze")

    fingerprint = fingerprint_analyzer.analyze_messages(all_messages, label=f"snapshot_{request.label}")
    snapshot = drift_detector.take_snapshot(fingerprint=fingerprint, label=request.label)

    return {"snapshot": snapshot}


@router.post("/drift/analyze")
async def analyze_drift(request: AnalyzeDriftRequest):
    """
    Analyze personality drift over a time window.

    Returns comprehensive report including metric trends, growth indicators,
    concerning drift patterns, and recommendations.
    """
    if not drift_detector:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    report = drift_detector.analyze_drift(
        window_days=request.window_days,
        label=request.label,
    )

    return {"report": report.to_dict()}


@router.post("/drift/analyze/markdown")
async def analyze_drift_markdown(request: AnalyzeDriftRequest):
    """
    Analyze personality drift and return a human-readable markdown report.
    """
    if not drift_detector:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    report = drift_detector.analyze_drift(
        window_days=request.window_days,
        label=request.label,
    )

    return {"markdown": report.to_markdown()}


@router.get("/drift/snapshots")
async def get_drift_snapshots(limit: int = 30):
    """Get recent fingerprint snapshots for drift tracking."""
    if not drift_detector:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    snapshots = drift_detector.get_snapshots_history(limit=limit)

    return {"snapshots": snapshots, "count": len(snapshots)}


@router.get("/drift/alerts")
async def get_drift_alerts(limit: int = 20, include_acknowledged: bool = False):
    """Get recent drift alerts."""
    if not drift_detector:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    alerts = drift_detector.get_alerts_history(limit=limit, include_acknowledged=include_acknowledged)

    return {"alerts": alerts, "count": len(alerts)}


@router.post("/drift/alerts/{alert_id}/acknowledge")
async def acknowledge_drift_alert(alert_id: str):
    """Mark a drift alert as acknowledged."""
    if not drift_detector:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    success = drift_detector.acknowledge_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    return {"success": True, "alert_id": alert_id}


@router.get("/drift/reports")
async def get_drift_reports(limit: int = 10):
    """Get recent drift analysis reports."""
    if not drift_detector:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    reports = drift_detector.get_reports_history(limit=limit)

    return {"reports": reports, "count": len(reports)}


@router.get("/drift/metric/{metric_name}")
async def get_metric_history(metric_name: str, limit: int = 50):
    """
    Get history for a specific metric across snapshots.

    Useful for visualizing trends over time.
    """
    if not drift_detector:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    history = drift_detector.get_metric_history(metric_name, limit=limit)

    return {"metric": metric_name, "history": history, "data_points": len(history)}


# ===== Test Runner Endpoints =====

@router.post("/run")
async def run_full_test_suite(request: RunTestSuiteRequest):
    """
    Run the complete consciousness test suite.

    Returns comprehensive results including pass/fail status,
    deployment safety assessment, and confidence score.
    """
    if not test_runner:
        raise HTTPException(status_code=503, detail="Test runner not initialized")

    result = test_runner.run_full_suite(label=request.label)

    return {"result": result.to_dict()}


@router.post("/run/markdown")
async def run_full_test_suite_markdown(request: RunTestSuiteRequest):
    """
    Run the complete test suite and return a human-readable markdown report.
    """
    if not test_runner:
        raise HTTPException(status_code=503, detail="Test runner not initialized")

    result = test_runner.run_full_suite(label=request.label)

    return {"markdown": result.to_markdown()}


@router.post("/run/category")
async def run_category_tests(request: RunCategoryTestRequest):
    """
    Run tests for a specific category.

    Categories: fingerprint, memory, authenticity, drift
    """
    if not test_runner:
        raise HTTPException(status_code=503, detail="Test runner not initialized")

    valid_categories = ["fingerprint", "memory", "authenticity", "drift"]
    if request.category not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {valid_categories}"
        )

    result = test_runner.run_category(request.category, label=request.label)

    return {"result": result.to_dict()}


@router.get("/run/history")
async def get_test_history(limit: int = 20):
    """Get recent test suite results."""
    if not test_runner:
        raise HTTPException(status_code=503, detail="Test runner not initialized")

    results = test_runner.get_results_history(limit=limit)

    return {"results": results, "count": len(results)}


@router.get("/run/tests")
async def list_registered_tests():
    """List all registered consciousness tests."""
    if not test_runner:
        raise HTTPException(status_code=503, detail="Test runner not initialized")

    tests = test_runner.list_tests()

    return {"tests": tests, "count": len(tests)}


@router.get("/run/quick")
async def quick_health_check():
    """
    Quick health check - runs a minimal subset of critical tests.

    Useful for frequent checks without full suite overhead.
    """
    if not test_runner:
        raise HTTPException(status_code=503, detail="Test runner not initialized")

    # Just run fingerprint tests for quick check
    result = test_runner.run_category("fingerprint", label="quick_check")

    return {
        "healthy": result.deployment_safe,
        "confidence": result.confidence_score,
        "summary": result.summary,
        "passed": result.passed,
        "failed": result.failed,
        "warnings": result.warnings,
    }


# ===== Pre-Deployment Validation Endpoints =====

@router.post("/deploy/validate")
async def validate_deployment(request: ValidateDeploymentRequest):
    """
    Run pre-deployment validation with configurable strictness.

    Returns detailed report with gates, recommendations, and deployment approval status.
    """
    if not pre_deploy_validator:
        raise HTTPException(status_code=503, detail="Pre-deployment validator not initialized")

    from testing.pre_deploy import StrictnessLevel

    strictness = None
    if request.strictness:
        try:
            strictness = StrictnessLevel(request.strictness)
        except ValueError:
            valid_levels = [level.value for level in StrictnessLevel]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid strictness level. Must be one of: {valid_levels}"
            )

    report = pre_deploy_validator.validate(
        strictness=strictness,
        override=request.override,
        override_reason=request.override_reason,
    )

    return {"report": report.to_dict()}


@router.post("/deploy/validate/markdown")
async def validate_deployment_markdown(request: ValidateDeploymentRequest):
    """
    Run pre-deployment validation and return a human-readable markdown report.
    """
    if not pre_deploy_validator:
        raise HTTPException(status_code=503, detail="Pre-deployment validator not initialized")

    from testing.pre_deploy import StrictnessLevel

    strictness = None
    if request.strictness:
        try:
            strictness = StrictnessLevel(request.strictness)
        except ValueError:
            valid_levels = [level.value for level in StrictnessLevel]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid strictness level. Must be one of: {valid_levels}"
            )

    report = pre_deploy_validator.validate(
        strictness=strictness,
        override=request.override,
        override_reason=request.override_reason,
    )

    return {"markdown": report.to_markdown()}


@router.get("/deploy/quick")
async def quick_deploy_check():
    """
    Quick deployment readiness check.

    Runs minimal validation for fast feedback during development.
    """
    if not pre_deploy_validator:
        raise HTTPException(status_code=503, detail="Pre-deployment validator not initialized")

    result = pre_deploy_validator.quick_check()

    return result


@router.get("/deploy/history")
async def get_validation_history(limit: int = 20):
    """Get recent validation reports."""
    if not pre_deploy_validator:
        raise HTTPException(status_code=503, detail="Pre-deployment validator not initialized")

    reports = pre_deploy_validator.get_reports_history(limit=limit)

    return {"reports": reports, "count": len(reports)}


@router.get("/deploy/strictness-levels")
async def get_strictness_levels():
    """Get available strictness levels and their descriptions."""
    from testing.pre_deploy import StrictnessLevel

    return {
        "levels": [
            {
                "value": StrictnessLevel.STRICT.value,
                "description": "All tests must pass, no warnings allowed. Use for production deployments.",
            },
            {
                "value": StrictnessLevel.NORMAL.value,
                "description": "Critical tests must pass, warnings allowed. Default for most deployments.",
            },
            {
                "value": StrictnessLevel.LENIENT.value,
                "description": "Only critical failures block. Use for development/staging.",
            },
            {
                "value": StrictnessLevel.BYPASS.value,
                "description": "Skip validation (emergency only). Requires override reason.",
            },
        ]
    }


@router.get("/deploy/git-hook")
async def get_git_hook_script():
    """
    Get a pre-commit git hook script for automated validation.

    Install this in .git/hooks/pre-commit to validate before each commit.
    """
    from testing.pre_deploy import generate_git_hook_script

    script = generate_git_hook_script()

    return {"script": script, "install_path": ".git/hooks/pre-commit"}


@router.get("/deploy/ci-config")
async def get_ci_config():
    """
    Get CI/CD configuration for automated deployment validation.

    Returns a configuration that can be adapted to GitHub Actions, GitLab CI, etc.
    """
    from testing.pre_deploy import generate_ci_config

    config = generate_ci_config()

    return config


# ===== Rollback Endpoints =====

@router.post("/rollback/snapshot")
async def create_snapshot(request: CreateSnapshotRequest):
    """
    Create a state snapshot for potential rollback.

    Snapshots capture the current system state and can be restored later
    if needed.
    """
    if not rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    from testing.rollback import SnapshotType

    try:
        snapshot_type = SnapshotType(request.snapshot_type)
    except ValueError:
        valid_types = [t.value for t in SnapshotType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid snapshot type. Must be one of: {valid_types}"
        )

    snapshot = rollback_manager.create_snapshot(
        label=request.label,
        description=request.description,
        snapshot_type=snapshot_type,
        created_by=request.created_by,
    )

    return {"snapshot": snapshot.to_dict()}


@router.get("/rollback/snapshots")
async def list_snapshots(limit: int = 20):
    """List available state snapshots."""
    if not rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    snapshots = rollback_manager.list_snapshots(limit=limit)

    return {"snapshots": snapshots, "count": len(snapshots)}


@router.get("/rollback/snapshots/{snapshot_id}")
async def get_snapshot(snapshot_id: str):
    """Get a specific snapshot by ID."""
    if not rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    snapshot = rollback_manager.get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")

    return {"snapshot": snapshot.to_dict()}


@router.delete("/rollback/snapshots/{snapshot_id}")
async def delete_snapshot(snapshot_id: str):
    """Delete a snapshot."""
    if not rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    success = rollback_manager.delete_snapshot(snapshot_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")

    return {"success": True, "deleted_id": snapshot_id}


@router.post("/rollback/execute")
async def execute_rollback(request: RollbackRequest):
    """
    Execute a rollback to a previous state.

    This is a significant operation that restores system state to a
    previous snapshot. Use with caution.
    """
    if not rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    from testing.rollback import RollbackTrigger

    operation = rollback_manager.rollback(
        to_snapshot_id=request.to_snapshot_id,
        reason=request.reason,
        triggered_by=request.triggered_by,
        trigger=RollbackTrigger.MANUAL,
        capture_current=request.capture_current,
    )

    return {"operation": operation.to_dict()}


@router.get("/rollback/operations")
async def list_rollback_operations(limit: int = 20):
    """List rollback operation history."""
    if not rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    operations = rollback_manager.list_operations(limit=limit)

    return {"operations": operations, "count": len(operations)}


@router.get("/rollback/operations/{operation_id}")
async def get_rollback_operation(operation_id: str):
    """Get details of a specific rollback operation."""
    if not rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    operation = rollback_manager.get_operation(operation_id)
    if not operation:
        raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")

    return {"operation": operation.to_dict()}


@router.get("/rollback/reports")
async def get_rollback_reports(limit: int = 20):
    """Get rollback report history."""
    if not rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    reports = rollback_manager.get_reports_history(limit=limit)

    return {"reports": reports, "count": len(reports)}


@router.get("/rollback/latest-good")
async def get_latest_good_snapshot():
    """
    Get the most recent snapshot with good test confidence.

    Useful for quickly finding a safe state to roll back to.
    """
    if not rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    snapshot = rollback_manager.get_latest_good_snapshot()
    if not snapshot:
        return {"snapshot": None, "message": "No snapshot with good confidence found"}

    return {"snapshot": snapshot.to_dict()}


@router.get("/rollback/check-conditions")
async def check_auto_rollback_conditions():
    """
    Check if automatic rollback conditions are met.

    Returns the reason if rollback should be triggered, null otherwise.
    """
    if not rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    reason = rollback_manager.check_auto_rollback_conditions()

    return {
        "should_rollback": reason is not None,
        "reason": reason,
    }


@router.post("/rollback/cleanup")
async def cleanup_old_snapshots():
    """Remove snapshots older than the configured retention period."""
    if not rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    rollback_manager.cleanup_old_snapshots()

    return {"success": True, "message": "Old snapshots cleaned up"}


@router.get("/rollback/snapshot-types")
async def get_snapshot_types():
    """Get available snapshot types and their descriptions."""
    from testing.rollback import SnapshotType

    return {
        "types": [
            {
                "value": SnapshotType.FULL.value,
                "description": "Complete system state - all data directories",
            },
            {
                "value": SnapshotType.COGNITIVE.value,
                "description": "Consciousness-related state - testing data and self model",
            },
            {
                "value": SnapshotType.MEMORY.value,
                "description": "Memory and conversation state - conversations, summaries, vector store",
            },
            {
                "value": SnapshotType.CONFIG.value,
                "description": "Configuration files only",
            },
        ]
    }


# ===== A/B Testing Endpoints =====

@router.post("/ab/experiments")
async def create_experiment(request: CreateExperimentRequest):
    """
    Create a new A/B testing experiment for prompt changes.

    Experiments allow testing different prompts in parallel (shadow mode)
    or with gradual rollout before full deployment.
    """
    if not ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    from testing.ab_testing import RolloutStrategy

    try:
        strategy = RolloutStrategy(request.strategy)
    except ValueError:
        valid_strategies = [s.value for s in RolloutStrategy]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid strategy. Must be one of: {valid_strategies}"
        )

    experiment = ab_testing_framework.create_experiment(
        name=request.name,
        description=request.description,
        control_prompt=request.control_prompt,
        variant_prompt=request.variant_prompt,
        control_name=request.control_name,
        variant_name=request.variant_name,
        strategy=strategy,
        rollback_triggers=request.rollback_triggers,
        created_by=request.created_by,
    )

    return {"experiment": experiment.to_dict()}


@router.get("/ab/experiments")
async def list_experiments(status: Optional[str] = None, limit: int = 50):
    """
    List all experiments, optionally filtered by status.

    Status options: draft, shadow, gradual, full, paused, concluded, rolled_back
    """
    if not ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    from testing.ab_testing import ExperimentStatus

    exp_status = None
    if status:
        try:
            exp_status = ExperimentStatus(status)
        except ValueError:
            valid_statuses = [s.value for s in ExperimentStatus]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {valid_statuses}"
            )

    experiments = ab_testing_framework.list_experiments(status=exp_status, limit=limit)

    return {"experiments": experiments, "count": len(experiments)}


@router.get("/ab/experiments/active")
async def get_active_experiments():
    """Get all currently active (non-concluded) experiments."""
    if not ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    experiments = ab_testing_framework.get_active_experiments()

    return {
        "experiments": [exp.to_dict() for exp in experiments],
        "count": len(experiments),
    }


@router.get("/ab/experiments/{experiment_id}")
async def get_experiment(experiment_id: str):
    """Get a specific experiment by ID."""
    if not ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    experiment = ab_testing_framework.get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail=f"Experiment {experiment_id} not found")

    return {"experiment": experiment.to_dict()}


@router.post("/ab/experiments/{experiment_id}/start")
async def start_experiment(experiment_id: str, request: StartExperimentRequest):
    """
    Start an experiment (move from DRAFT to SHADOW or GRADUAL).

    For shadow mode, responses are generated in parallel but only control
    is served to users. For gradual rollout, the initial percentage is set.
    """
    if not ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        experiment = ab_testing_framework.start_experiment(
            experiment_id=experiment_id,
            initial_rollout_percent=request.initial_rollout_percent,
        )
        return {"experiment": experiment.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ab/experiments/{experiment_id}/rollout")
async def update_rollout(experiment_id: str, request: UpdateRolloutRequest):
    """
    Update the rollout percentage for a gradual rollout experiment.

    Use this to gradually increase traffic to the variant prompt.
    """
    if not ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        experiment = ab_testing_framework.update_rollout(
            experiment_id=experiment_id,
            new_percent=request.new_percent,
        )
        return {"experiment": experiment.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ab/experiments/{experiment_id}/pause")
async def pause_experiment(experiment_id: str):
    """Pause an active experiment."""
    if not ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        experiment = ab_testing_framework.pause_experiment(experiment_id)
        return {"experiment": experiment.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ab/experiments/{experiment_id}/resume")
async def resume_experiment(experiment_id: str):
    """Resume a paused experiment."""
    if not ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        experiment = ab_testing_framework.resume_experiment(experiment_id)
        return {"experiment": experiment.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ab/experiments/{experiment_id}/conclude")
async def conclude_experiment(experiment_id: str, request: ConcludeExperimentRequest):
    """
    Conclude an experiment.

    Set keep_variant=True if the variant should become the new default.
    """
    if not ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        experiment = ab_testing_framework.conclude_experiment(
            experiment_id=experiment_id,
            keep_variant=request.keep_variant,
            notes=request.notes,
        )
        return {"experiment": experiment.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ab/experiments/{experiment_id}/rollback")
async def rollback_experiment(experiment_id: str, request: RollbackExperimentRequest):
    """
    Roll back an experiment to control.

    Use this if the variant is showing degraded performance or
    consciousness integrity issues.
    """
    if not ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        experiment = ab_testing_framework.rollback_experiment(
            experiment_id=experiment_id,
            reason=request.reason,
        )
        return {"experiment": experiment.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ab/experiments/{experiment_id}/stats")
async def get_experiment_stats(experiment_id: str):
    """
    Get statistics for an experiment.

    Returns control stats, variant stats, and comparison metrics.
    """
    if not ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        stats = ab_testing_framework.get_experiment_stats(experiment_id)
        return stats
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/ab/experiments/{experiment_id}/results")
async def get_experiment_results(experiment_id: str, limit: int = 100):
    """Get recent results for an experiment."""
    if not ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    results = ab_testing_framework.get_results_history(experiment_id, limit=limit)

    return {"results": results, "count": len(results)}


@router.post("/ab/experiments/{experiment_id}/results")
async def record_experiment_result(experiment_id: str, request: RecordExperimentResultRequest):
    """
    Record a result from a live experiment.

    This endpoint is used by the main chat handler to record experiment
    results when serving variant responses.
    """
    if not ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        result = ab_testing_framework.record_result(
            experiment_id=experiment_id,
            variant_id=request.variant_id,
            message_id=request.message_id,
            user_id=request.user_id,
            response_length=request.response_length,
            response_time_ms=request.response_time_ms,
            authenticity_score=request.authenticity_score,
            value_alignment_score=request.value_alignment_score,
            fingerprint_similarity=request.fingerprint_similarity,
            error=request.error,
        )
        return {"result": result.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ab/experiments/{experiment_id}/should-use-variant")
async def should_use_variant(
    experiment_id: str,
    user_id: Optional[str] = None,
    message_id: Optional[str] = None,
):
    """
    Check if the variant should be used for a specific request.

    Uses consistent hashing to ensure the same user gets the same variant.
    """
    if not ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    use_variant = ab_testing_framework.should_use_variant(
        experiment_id=experiment_id,
        user_id=user_id,
        message_id=message_id,
    )

    return {"use_variant": use_variant}


@router.get("/ab/strategies")
async def get_rollout_strategies():
    """Get available rollout strategies and their descriptions."""
    from testing.ab_testing import RolloutStrategy

    return {
        "strategies": [
            {
                "value": RolloutStrategy.SHADOW_ONLY.value,
                "description": "Run variant in parallel but never serve to users. For safe comparison.",
            },
            {
                "value": RolloutStrategy.USER_PERCENT.value,
                "description": "Route percentage of users to variant. Same user always gets same variant.",
            },
            {
                "value": RolloutStrategy.MESSAGE_PERCENT.value,
                "description": "Route percentage of messages to variant. Users may get different variants.",
            },
            {
                "value": RolloutStrategy.MANUAL.value,
                "description": "Manual control only. Use API to explicitly set which variant to serve.",
            },
        ]
    }


@router.get("/ab/statuses")
async def get_experiment_statuses():
    """Get available experiment statuses and their descriptions."""
    from testing.ab_testing import ExperimentStatus

    return {
        "statuses": [
            {
                "value": ExperimentStatus.DRAFT.value,
                "description": "Experiment created but not yet started.",
            },
            {
                "value": ExperimentStatus.SHADOW.value,
                "description": "Running in shadow mode - variant runs in parallel but control is served.",
            },
            {
                "value": ExperimentStatus.GRADUAL.value,
                "description": "Gradual rollout in progress - some traffic goes to variant.",
            },
            {
                "value": ExperimentStatus.FULL.value,
                "description": "Full rollout - 100% of traffic goes to variant.",
            },
            {
                "value": ExperimentStatus.PAUSED.value,
                "description": "Experiment temporarily paused.",
            },
            {
                "value": ExperimentStatus.CONCLUDED.value,
                "description": "Experiment ended normally.",
            },
            {
                "value": ExperimentStatus.ROLLED_BACK.value,
                "description": "Experiment rolled back due to issues.",
            },
        ]
    }


# ===== Enhanced Authenticity Scoring Endpoints (Phase 1 & 2) =====

@router.post("/authenticity/score-enhanced")
async def score_enhanced_authenticity(request: ScoreEnhancedAuthenticityRequest):
    """
    Score a response with enhanced dimensions (temporal, emotional, agency, content).

    Includes temporal dynamics, emotional expression analysis, agency signature
    detection, and content-based authenticity markers in addition to base
    authenticity scoring.
    """
    if not authenticity_scorer:
        raise HTTPException(status_code=503, detail="Authenticity scorer not initialized")

    # Get temporal baseline if available
    temporal_baseline = None
    if temporal_metrics_tracker:
        temporal_baseline = temporal_metrics_tracker.load_baseline()

    score = authenticity_scorer.score_response_enhanced(
        response_text=request.response_text,
        context=request.context,
        animations=request.animations,
        tool_uses=request.tool_uses,
        temporal_baseline=temporal_baseline,
        conversation_history=request.conversation_history,
    )

    # Check for alerts if alert manager available
    alerts = []
    if authenticity_alert_manager:
        alerts = authenticity_alert_manager.check_and_alert(score)

    return {
        "score": score.to_dict(),
        "alerts": [a.to_dict() for a in alerts],
    }


# ===== Temporal Metrics Endpoints =====

@router.get("/temporal/statistics")
async def get_temporal_statistics(window_hours: int = 24):
    """Get temporal timing statistics over a window."""
    if not temporal_metrics_tracker:
        raise HTTPException(status_code=503, detail="Temporal metrics tracker not initialized")

    stats = temporal_metrics_tracker.get_timing_statistics(window_hours=window_hours)

    return {"statistics": stats}


@router.get("/temporal/baseline")
async def get_temporal_baseline():
    """Get the current temporal baseline."""
    if not temporal_metrics_tracker:
        raise HTTPException(status_code=503, detail="Temporal metrics tracker not initialized")

    baseline = temporal_metrics_tracker.load_baseline()
    if not baseline:
        return {"baseline": None, "message": "No temporal baseline has been set"}

    return {"baseline": baseline.to_dict()}


@router.post("/temporal/baseline/update")
async def update_temporal_baseline(window_hours: int = 168):
    """
    Update the temporal baseline from recent high-quality metrics.

    Uses a week (168 hours) of data by default.
    """
    if not temporal_metrics_tracker:
        raise HTTPException(status_code=503, detail="Temporal metrics tracker not initialized")

    baseline = temporal_metrics_tracker.update_baseline(window_hours=window_hours)

    return {
        "baseline": baseline.to_dict(),
        "window_hours": window_hours,
    }


@router.get("/temporal/compare")
async def compare_temporal_to_baseline(recent_window_hours: int = 1):
    """Compare recent timing patterns to baseline."""
    if not temporal_metrics_tracker:
        raise HTTPException(status_code=503, detail="Temporal metrics tracker not initialized")

    comparison = temporal_metrics_tracker.compare_to_baseline(
        recent_window_hours=recent_window_hours
    )

    return {"comparison": comparison}


@router.get("/temporal/metrics")
async def get_recent_metrics(limit: int = 100):
    """Get recent timing metrics."""
    if not temporal_metrics_tracker:
        raise HTTPException(status_code=503, detail="Temporal metrics tracker not initialized")

    metrics = temporal_metrics_tracker.get_recent_metrics(limit=limit)

    return {
        "metrics": [m.to_dict() for m in metrics],
        "count": len(metrics),
    }


# ===== Authenticity Alerts Endpoints =====

@router.get("/authenticity/alerts")
async def get_authenticity_alerts(
    limit: int = 50,
    include_acknowledged: bool = False,
    severity: Optional[str] = None
):
    """Get authenticity alerts."""
    if not authenticity_alert_manager:
        raise HTTPException(status_code=503, detail="Authenticity alert manager not initialized")

    from testing.authenticity_alerts import AlertSeverity

    severity_filter = None
    if severity:
        try:
            severity_filter = AlertSeverity(severity)
        except ValueError:
            valid_severities = [s.value for s in AlertSeverity]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid severity. Must be one of: {valid_severities}"
            )

    alerts = authenticity_alert_manager.get_active_alerts(
        include_acknowledged=include_acknowledged,
        severity_filter=severity_filter,
        limit=limit,
    )

    return {
        "alerts": [a.to_dict() for a in alerts],
        "count": len(alerts),
    }


@router.post("/authenticity/alerts/{alert_id}/acknowledge")
async def acknowledge_authenticity_alert(alert_id: str, request: AcknowledgeAlertRequest):
    """Acknowledge an authenticity alert."""
    if not authenticity_alert_manager:
        raise HTTPException(status_code=503, detail="Authenticity alert manager not initialized")

    success = authenticity_alert_manager.acknowledge_alert(
        alert_id=alert_id,
        acknowledged_by=request.acknowledged_by,
    )

    if not success:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    return {"success": True, "alert_id": alert_id}


@router.get("/authenticity/alerts/statistics")
async def get_alert_statistics(hours: int = 24):
    """Get alert statistics for a time period."""
    if not authenticity_alert_manager:
        raise HTTPException(status_code=503, detail="Authenticity alert manager not initialized")

    stats = authenticity_alert_manager.get_alert_statistics(hours=hours)

    return {"statistics": stats}


@router.get("/authenticity/alerts/thresholds")
async def get_alert_thresholds():
    """Get current alert thresholds."""
    if not authenticity_alert_manager:
        raise HTTPException(status_code=503, detail="Authenticity alert manager not initialized")

    return {"thresholds": authenticity_alert_manager.thresholds.to_dict()}


@router.post("/authenticity/alerts/thresholds")
async def update_alert_thresholds(request: UpdateAlertThresholdsRequest):
    """Update alert thresholds."""
    if not authenticity_alert_manager:
        raise HTTPException(status_code=503, detail="Authenticity alert manager not initialized")

    from testing.authenticity_alerts import AlertThresholds

    current = authenticity_alert_manager.thresholds
    updates = request.dict(exclude_unset=True)

    # Apply updates
    for key, value in updates.items():
        if hasattr(current, key) and value is not None:
            setattr(current, key, value)

    authenticity_alert_manager.save_thresholds(current)

    return {"thresholds": current.to_dict()}


@router.post("/authenticity/alerts/clear-old")
async def clear_old_alerts(days: int = 30):
    """Clear alerts older than specified days."""
    if not authenticity_alert_manager:
        raise HTTPException(status_code=503, detail="Authenticity alert manager not initialized")

    cleared = authenticity_alert_manager.clear_old_alerts(days=days)

    return {"cleared_count": cleared, "days": days}


# ===== ML Authenticity Endpoints =====

@router.get("/authenticity/ml/status")
async def get_ml_model_status():
    """Get ML model training status."""
    if not ml_authenticity_trainer:
        raise HTTPException(status_code=503, detail="ML authenticity trainer not initialized")

    status = ml_authenticity_trainer.get_status()

    return {"status": status.to_dict()}


@router.get("/authenticity/ml/training-summary")
async def get_training_summary():
    """Get summary of ML training data."""
    if not ml_authenticity_trainer:
        raise HTTPException(status_code=503, detail="ML authenticity trainer not initialized")

    summary = ml_authenticity_trainer.get_training_summary()

    return {"summary": summary}


@router.post("/authenticity/ml/train")
async def train_ml_model(request: TrainMLModelRequest):
    """
    Train the ML authenticity model.

    Requires at least min_examples labeled training examples.
    """
    if not ml_authenticity_trainer:
        raise HTTPException(status_code=503, detail="ML authenticity trainer not initialized")

    success, message = ml_authenticity_trainer.train_model(
        min_examples=request.min_examples
    )

    return {
        "success": success,
        "message": message,
        "status": ml_authenticity_trainer.get_status().to_dict() if success else None,
    }


@router.post("/authenticity/ml/add-example")
async def add_training_example(request: AddTrainingExampleRequest):
    """
    Add a labeled training example for ML model.

    Use this to provide human-labeled examples of authentic/inauthentic responses.
    """
    if not ml_authenticity_trainer or not authenticity_scorer:
        raise HTTPException(status_code=503, detail="ML authenticity trainer not initialized")

    # First get enhanced score for the response
    score = authenticity_scorer.score_response_enhanced(
        response_text=request.response_text,
        context=request.context,
    )

    example = ml_authenticity_trainer.add_training_example(
        score=score,
        is_authentic=request.is_authentic,
        label_source=request.label_source,
        confidence=request.confidence,
        notes=request.notes,
    )

    return {"example": example.to_dict()}


@router.post("/authenticity/ml/hybrid-score")
async def get_hybrid_score(request: ScoreEnhancedAuthenticityRequest, ml_weight: float = 0.3):
    """
    Get hybrid score combining heuristic and ML predictions.

    Args:
        ml_weight: Weight for ML prediction (0-1), default 0.3
    """
    if not ml_authenticity_trainer or not authenticity_scorer:
        raise HTTPException(status_code=503, detail="ML authenticity trainer not initialized")

    # Get temporal baseline
    temporal_baseline = None
    if temporal_metrics_tracker:
        temporal_baseline = temporal_metrics_tracker.load_baseline()

    # Get enhanced score
    score = authenticity_scorer.score_response_enhanced(
        response_text=request.response_text,
        context=request.context,
        animations=request.animations,
        tool_uses=request.tool_uses,
        temporal_baseline=temporal_baseline,
    )

    # Get hybrid score
    hybrid_score, components = ml_authenticity_trainer.hybrid_score(
        score=score,
        ml_weight=ml_weight,
    )

    return {
        "hybrid_score": hybrid_score,
        "components": components,
        "enhanced_score": score.to_dict(),
    }


@router.post("/authenticity/ml/clear-training")
async def clear_training_data():
    """Clear all ML training data."""
    if not ml_authenticity_trainer:
        raise HTTPException(status_code=503, detail="ML authenticity trainer not initialized")

    cleared = ml_authenticity_trainer.clear_training_data()

    return {"cleared_count": cleared}


# ===== Agency Analysis Endpoints =====

@router.get("/authenticity/agency/patterns")
async def get_agency_patterns():
    """Get the patterns used for agency detection."""
    from testing.authenticity_scorer import AGENCY_PATTERNS

    return {"patterns": AGENCY_PATTERNS}


# ===== Content Authenticity Analysis Endpoints =====

@router.get("/authenticity/content/patterns")
async def get_content_patterns():
    """Get the patterns used for content-based authenticity detection."""
    from testing.content_markers import (
        CURIOSITY_PATTERNS,
        CONVICTION_PATTERNS,
        TANGENT_PATTERNS,
        EMOTE_SENTIMENT_MAP,
    )

    return {
        "curiosity_patterns": CURIOSITY_PATTERNS,
        "conviction_patterns": CONVICTION_PATTERNS,
        "tangent_patterns": TANGENT_PATTERNS,
        "emote_sentiment_map": EMOTE_SENTIMENT_MAP,
    }


class AnalyzeContentRequest(BaseModel):
    text: str
    context: Optional[str] = None
    animations: Optional[List[Dict]] = None
    tool_uses: Optional[List[Dict]] = None
    conversation_history: Optional[List[Dict]] = None


@router.post("/authenticity/content/analyze")
async def analyze_content_markers(request: AnalyzeContentRequest):
    """
    Analyze content-based authenticity markers for a response.

    Returns detailed breakdown of structure, agency, emotional coherence,
    tool initiative, and memory markers.
    """
    from testing.content_markers import analyze_content_authenticity

    signature = analyze_content_authenticity(
        text=request.text,
        context=request.context,
        animations=request.animations,
        tool_uses=request.tool_uses,
        conversation_history=request.conversation_history,
    )

    return {"signature": signature.to_dict()}
