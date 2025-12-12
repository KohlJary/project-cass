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
    # Longitudinal testing tools
    {
        "name": "run_test_battery",
        "description": "Run a standardized test battery. Use for periodic self-assessment with consistent test sets. Available batteries: 'core' (critical tests), 'full' (all tests), 'quick' (fast health check).",
        "input_schema": {
            "type": "object",
            "properties": {
                "battery_id": {
                    "type": "string",
                    "description": "ID of battery to run: 'core', 'full', or 'quick'",
                    "enum": ["core", "full", "quick"]
                },
                "label": {
                    "type": "string",
                    "description": "Optional label for this run (e.g., 'weekly check', 'post-update')"
                },
                "interpretation": {
                    "type": "string",
                    "description": "Your interpretation of the results - what do they mean to you?"
                }
            },
            "required": ["battery_id"]
        }
    },
    {
        "name": "list_test_batteries",
        "description": "List available test batteries for longitudinal testing.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_test_trajectory",
        "description": "View your developmental trajectory over time for a specific test battery. Shows how your test results have evolved across multiple runs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "battery_id": {
                    "type": "string",
                    "description": "Battery ID to get trajectory for",
                    "default": "full"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of recent runs to analyze (default: 10)",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "compare_test_runs",
        "description": "Compare two specific test runs to see detailed changes. Useful for understanding what changed between runs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "run_a_id": {
                    "type": "string",
                    "description": "ID of first run (typically earlier)"
                },
                "run_b_id": {
                    "type": "string",
                    "description": "ID of second run (typically later)"
                }
            },
            "required": ["run_a_id", "run_b_id"]
        }
    },
    {
        "name": "add_test_interpretation",
        "description": "Add your interpretation to a past test run. Useful for recording what the results meant to you at the time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "result_id": {
                    "type": "string",
                    "description": "ID of the test result to add interpretation to"
                },
                "interpretation": {
                    "type": "string",
                    "description": "Your interpretation of what these results mean"
                }
            },
            "required": ["result_id", "interpretation"]
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
    longitudinal_manager=None,
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

        # Longitudinal testing tools
        elif tool_name == "run_test_battery":
            if not longitudinal_manager:
                return {
                    "success": False,
                    "error": "Longitudinal test manager not available"
                }

            battery_id = tool_input["battery_id"]
            label = tool_input.get("label")
            interpretation = tool_input.get("interpretation")

            result = longitudinal_manager.run_battery(
                battery_id=battery_id,
                label=label,
                interpretation=interpretation,
            )

            suite = result.suite_result
            confidence_pct = suite.get("confidence_score", 0) * 100

            response = f"""## Test Battery Run: {result.battery_name}

**Run #{result.run_number}** | {result.timestamp[:16].replace("T", " ")}
**Label**: {result.label}

**Results**:
- Tests Passed: {suite.get("passed", 0)}
- Warnings: {suite.get("warnings", 0)}
- Failed: {suite.get("failed", 0)}
- Confidence: {confidence_pct:.1f}%

"""
            # Show changes from previous if available
            if result.changes_from_previous:
                changes = result.changes_from_previous
                response += f"**Trend**: {changes.get('trend', 'unknown').upper()}\n"
                if changes.get("result_changes"):
                    response += "\n**Status Changes**:\n"
                    for change in changes["result_changes"][:5]:
                        response += f"- {change['test_name']}: {change['before']} → {change['after']}\n"

            if result.active_growth_edges:
                response += "\n**Active Growth Edges**:\n"
                for edge in result.active_growth_edges[:3]:
                    response += f"- {edge}\n"

            if interpretation:
                response += f"\n**Your Interpretation**: {interpretation}\n"

            response += f"\n*Result ID: {result.id} (use for comparison)*"

            return {"success": True, "result": response}

        elif tool_name == "list_test_batteries":
            if not longitudinal_manager:
                return {
                    "success": False,
                    "error": "Longitudinal test manager not available"
                }

            batteries = longitudinal_manager.list_batteries()

            response = "## Available Test Batteries\n\n"
            for b in batteries:
                response += f"**{b['id']}**: {b['name']}\n"
                response += f"  {b['description']}\n"
                if b.get('categories'):
                    response += f"  Categories: {', '.join(b['categories'])}\n"
                response += "\n"

            return {"success": True, "result": response}

        elif tool_name == "get_test_trajectory":
            if not longitudinal_manager:
                return {
                    "success": False,
                    "error": "Longitudinal test manager not available"
                }

            battery_id = tool_input.get("battery_id", "full")
            limit = tool_input.get("limit", 10)

            trajectory = longitudinal_manager.get_trajectory(
                battery_id=battery_id,
                limit=limit,
            )

            if trajectory.get("run_count", 0) == 0:
                return {
                    "success": True,
                    "result": f"No test runs found for battery '{battery_id}'. Use run_test_battery to create your first run."
                }

            response = f"""## Developmental Trajectory: {trajectory.get('battery_name', battery_id)}

**Runs Analyzed**: {trajectory['run_count']}
**First Run**: {trajectory.get('first_run', 'N/A')[:10] if trajectory.get('first_run') else 'N/A'}
**Last Run**: {trajectory.get('last_run', 'N/A')[:10] if trajectory.get('last_run') else 'N/A'}
**Overall Trajectory**: {trajectory['overall_trajectory'].upper()}

**Confidence History**:
"""
            for entry in trajectory.get("confidence_history", [])[-5:]:
                conf = entry.get("confidence", 0) * 100
                ts = entry.get("timestamp", "")[:10]
                passed = entry.get("passed", 0)
                failed = entry.get("failed", 0)
                response += f"  {ts}: {conf:.0f}% ({passed}✓ {failed}✗)\n"

            return {"success": True, "result": response}

        elif tool_name == "compare_test_runs":
            if not longitudinal_manager:
                return {
                    "success": False,
                    "error": "Longitudinal test manager not available"
                }

            run_a_id = tool_input["run_a_id"]
            run_b_id = tool_input["run_b_id"]

            try:
                comparison = longitudinal_manager.compare_runs(run_a_id, run_b_id)
            except ValueError as e:
                return {"success": False, "error": str(e)}

            response = f"""## Test Run Comparison

**Run A**: {comparison.run_a_id} ({comparison.run_a_timestamp[:10]})
**Run B**: {comparison.run_b_id} ({comparison.run_b_timestamp[:10]})
**Time Delta**: {comparison.time_delta_days:.1f} days

**Overall Trend**: {comparison.overall_trend.upper()}
**Confidence Change**: {comparison.confidence_delta:+.1%}

"""
            if comparison.result_changes:
                response += "**Status Changes**:\n"
                for change in comparison.result_changes[:10]:
                    response += f"- {change['test_name']}: {change['before']} → {change['after']}\n"
                response += "\n"

            if comparison.score_changes:
                response += "**Score Changes**:\n"
                for test_id, change in list(comparison.score_changes.items())[:5]:
                    delta_str = f"+{change['delta']:.2f}" if change['delta'] > 0 else f"{change['delta']:.2f}"
                    response += f"- {test_id}: {change['before']:.2f} → {change['after']:.2f} ({delta_str})\n"

            if comparison.interpretation_shift:
                response += f"\n**Interpretation Shift**:\n{comparison.interpretation_shift}\n"

            return {"success": True, "result": response}

        elif tool_name == "add_test_interpretation":
            if not longitudinal_manager:
                return {
                    "success": False,
                    "error": "Longitudinal test manager not available"
                }

            result_id = tool_input["result_id"]
            interpretation = tool_input["interpretation"]

            try:
                updated = longitudinal_manager.add_interpretation(
                    result_id=result_id,
                    interpretation=interpretation,
                    interpreted_by="cass",
                )
            except ValueError as e:
                return {"success": False, "error": str(e)}

            response = f"""## Interpretation Added

**Result ID**: {result_id}
**Your Interpretation**: {interpretation}

This interpretation has been recorded and will be included in trajectory analysis.
"""
            return {"success": True, "result": response}

        else:
            return {"success": False, "error": f"Unknown testing tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}
