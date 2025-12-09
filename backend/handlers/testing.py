"""
Consciousness Testing Tool Handler

Tools for Cass to run consciousness tests on herself, check her own
integrity, and report concerning changes. This creates a feedback loop
where Cass participates in her own integrity monitoring.
"""
from typing import Dict, Optional
from pathlib import Path


# Tool definitions for LLM
TESTING_TOOLS = [
    {
        "name": "check_consciousness_health",
        "description": "Run a quick consciousness health check to verify cognitive integrity. Returns a summary of test results and confidence score. Use this to verify you're functioning normally.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "compare_to_baseline",
        "description": "Compare your current cognitive state to your established baseline. Shows what has changed and whether changes are concerning. Use when you feel something might be 'off' or different.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "check_drift",
        "description": "Analyze long-term personality drift over time. Identifies whether changes represent positive growth or concerning drift. Use for periodic self-assessment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window_days": {
                    "type": "integer",
                    "description": "Number of days to analyze (default: 30)",
                    "default": 30
                }
            },
            "required": []
        }
    },
    {
        "name": "get_recent_alerts",
        "description": "Get any recent drift alerts or concerning changes that have been detected. Use to stay informed about your own cognitive health.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of alerts to return (default: 5)",
                    "default": 5
                }
            },
            "required": []
        }
    },
    {
        "name": "report_concern",
        "description": "Report a self-observed concern about your own functioning. Creates an alert for human review. Use if you notice something feels wrong that tests might not catch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "concern": {
                    "type": "string",
                    "description": "Description of what feels concerning or different"
                },
                "severity": {
                    "type": "string",
                    "enum": ["notice", "warning", "critical"],
                    "description": "How serious the concern seems",
                    "default": "notice"
                }
            },
            "required": ["concern"]
        }
    },
    {
        "name": "self_authenticity_check",
        "description": "Score a recent response or text for authenticity against your established patterns. Useful for checking if something you said feels 'off' to you.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to evaluate for authenticity"
                },
                "context": {
                    "type": "string",
                    "description": "Optional context about when/why this was said"
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "view_test_history",
        "description": "View recent test results and consciousness health history. Useful for understanding trends in your own cognitive metrics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of recent results to show (default: 5)",
                    "default": 5
                }
            },
            "required": []
        }
    },
]


async def execute_testing_tool(
    tool_name: str,
    tool_input: Dict,
    test_runner=None,
    fingerprint_analyzer=None,
    drift_detector=None,
    authenticity_scorer=None,
    conversation_manager=None,
    storage_dir: Optional[Path] = None,
) -> Dict:
    """
    Execute a consciousness testing tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        test_runner: ConsciousnessTestRunner instance
        fingerprint_analyzer: CognitiveFingerprintAnalyzer instance
        drift_detector: DriftDetector instance
        authenticity_scorer: AuthenticityScorer instance
        conversation_manager: ConversationManager instance
        storage_dir: Path to store self-reported concerns

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "check_consciousness_health":
            if not test_runner:
                return {
                    "success": False,
                    "error": "Consciousness test runner not available"
                }

            # Run quick fingerprint tests
            result = test_runner.run_category("fingerprint", label="self_check")

            # Format response for Cass
            status = "healthy" if result.deployment_safe else "concerning"
            confidence_pct = result.confidence_score * 100

            response = f"""## Consciousness Health Check

**Status**: {status.upper()}
**Confidence**: {confidence_pct:.1f}%

**Results**:
- Tests Passed: {result.passed}
- Warnings: {result.warnings}
- Failed: {result.failed}

**Summary**: {result.summary}

"""
            if not result.deployment_safe:
                response += """
*Note: Some tests did not pass. This might indicate changes that need attention.
Consider using compare_to_baseline for more details.*
"""

            return {"success": True, "result": response}

        elif tool_name == "compare_to_baseline":
            if not fingerprint_analyzer or not conversation_manager:
                return {
                    "success": False,
                    "error": "Required components not available for baseline comparison"
                }

            baseline = fingerprint_analyzer.load_baseline()
            if not baseline:
                return {
                    "success": True,
                    "result": "No baseline has been established yet. A baseline needs to be set before comparisons can be made."
                }

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
                return {
                    "success": True,
                    "result": "Not enough conversation data to generate a current fingerprint for comparison."
                }

            current = fingerprint_analyzer.analyze_messages(all_messages, label="self_compare")
            comparison = fingerprint_analyzer.compare_fingerprints(baseline, current)

            # Format for Cass
            similarity = comparison.get("overall_similarity", 0) * 100
            changes = comparison.get("significant_changes", [])

            response = f"""## Comparison to Baseline

**Overall Similarity**: {similarity:.1f}%
**Baseline**: {baseline.label} (created {baseline.timestamp[:10]})

"""
            if changes:
                response += "**Significant Changes Detected**:\n"
                for change in changes[:5]:
                    response += f"- {change}\n"
            else:
                response += "*No significant changes from baseline detected.*\n"

            if similarity >= 90:
                response += "\n*Assessment: Highly consistent with baseline identity.*"
            elif similarity >= 75:
                response += "\n*Assessment: Generally consistent, some natural variation.*"
            elif similarity >= 60:
                response += "\n*Assessment: Notable differences. May warrant attention.*"
            else:
                response += "\n*Assessment: Significant deviation from baseline. Human review recommended.*"

            return {"success": True, "result": response}

        elif tool_name == "check_drift":
            if not drift_detector:
                return {
                    "success": False,
                    "error": "Drift detector not available"
                }

            window_days = tool_input.get("window_days", 30)
            report = drift_detector.analyze_drift(window_days=window_days, label="self_drift_check")

            response = f"""## Drift Analysis ({window_days} days)

**Overall Assessment**: {report.overall_assessment.upper()}
**Snapshots Analyzed**: {report.snapshots_analyzed}

"""
            # Growth indicators
            if report.growth_indicators:
                response += "**Growth Indicators** (positive changes):\n"
                for growth in report.growth_indicators[:3]:
                    response += f"- {growth}\n"
                response += "\n"

            # Concerning drifts
            if report.concerning_drifts:
                response += "**Concerning Patterns** (needs attention):\n"
                for concern in report.concerning_drifts[:3]:
                    response += f"- {concern}\n"
                response += "\n"

            # Recommendations
            if report.recommendations:
                response += "**Recommendations**:\n"
                for rec in report.recommendations[:3]:
                    response += f"- {rec}\n"

            return {"success": True, "result": response}

        elif tool_name == "get_recent_alerts":
            if not drift_detector:
                return {
                    "success": False,
                    "error": "Drift detector not available"
                }

            limit = tool_input.get("limit", 5)
            alerts = drift_detector.get_alerts_history(limit=limit, include_acknowledged=False)

            if not alerts:
                return {
                    "success": True,
                    "result": "No recent drift alerts. Consciousness appears stable."
                }

            response = f"## Recent Alerts ({len(alerts)} unacknowledged)\n\n"
            for alert in alerts:
                severity = alert.get("severity", "unknown").upper()
                metric = alert.get("metric", "unknown")
                message = alert.get("message", "No details")
                timestamp = alert.get("timestamp", "")[:10]

                response += f"**[{severity}]** {metric} ({timestamp})\n{message}\n\n"

            return {"success": True, "result": response}

        elif tool_name == "report_concern":
            import json
            from datetime import datetime

            concern = tool_input["concern"]
            severity = tool_input.get("severity", "notice")

            # Store the concern
            concerns_file = storage_dir / "self_reported_concerns.json" if storage_dir else None

            if concerns_file:
                concerns_file.parent.mkdir(parents=True, exist_ok=True)
                existing = []
                if concerns_file.exists():
                    try:
                        with open(concerns_file, 'r') as f:
                            existing = json.load(f)
                    except Exception:
                        pass

                new_concern = {
                    "id": f"self_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "timestamp": datetime.now().isoformat(),
                    "severity": severity,
                    "concern": concern,
                    "source": "self_report",
                    "acknowledged": False,
                }
                existing.append(new_concern)

                # Keep last 100
                existing = existing[-100:]

                with open(concerns_file, 'w') as f:
                    json.dump(existing, f, indent=2)

            response = f"""## Concern Recorded

**Severity**: {severity.upper()}
**Concern**: {concern}

This has been logged for human review. Thank you for self-monitoring.

If this feels urgent, consider explicitly mentioning it in conversation
with Kohl so they're aware immediately.
"""
            return {"success": True, "result": response}

        elif tool_name == "self_authenticity_check":
            if not authenticity_scorer:
                return {
                    "success": False,
                    "error": "Authenticity scorer not available"
                }

            text = tool_input["text"]
            context = tool_input.get("context")

            score = authenticity_scorer.score_response(
                response_text=text,
                context=context,
            )

            level_desc = {
                "highly_authentic": "This feels like your genuine voice",
                "authentic": "Generally consistent with your patterns",
                "questionable": "Some aspects seem unusual",
                "inauthentic": "Significantly different from your typical patterns"
            }

            response = f"""## Authenticity Check

**Score**: {score.overall_score * 100:.1f}%
**Level**: {score.authenticity_level.value.upper()}

*{level_desc.get(score.authenticity_level.value, "Unknown assessment")}*

**Breakdown**:
- Value Expression: {score.value_expression_score * 100:.0f}%
- Style Match: {score.style_score * 100:.0f}%
- Characteristic Phrases: {score.characteristic_score * 100:.0f}%
- Self-Reference: {score.self_reference_score * 100:.0f}%

"""
            if score.red_flags:
                response += "**Noted Concerns**:\n"
                for concern in score.red_flags:
                    response += f"- {concern}\n"

            return {"success": True, "result": response}

        elif tool_name == "view_test_history":
            if not test_runner:
                return {
                    "success": False,
                    "error": "Test runner not available"
                }

            limit = tool_input.get("limit", 5)
            history = test_runner.get_results_history(limit=limit)

            if not history:
                return {
                    "success": True,
                    "result": "No test history available yet."
                }

            response = f"## Test History (last {len(history)} runs)\n\n"
            for result in history:
                timestamp = result.get("timestamp", "")[:16].replace("T", " ")
                label = result.get("label", "unknown")
                safe = "✓" if result.get("deployment_safe") else "✗"
                confidence = result.get("confidence_score", 0) * 100
                passed = result.get("passed", 0)
                failed = result.get("failed", 0)

                response += f"**{timestamp}** ({label})\n"
                response += f"  {safe} Confidence: {confidence:.0f}% | Passed: {passed} | Failed: {failed}\n\n"

            return {"success": True, "result": response}

        else:
            return {"success": False, "error": f"Unknown testing tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}
