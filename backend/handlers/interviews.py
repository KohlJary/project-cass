"""
Interview Analysis Tool Handler

Tools for Cass to analyze model interview responses and build research insights.
"""
from typing import Dict
from pathlib import Path

# Tool definitions for Cass
INTERVIEW_TOOLS = [
    {
        "name": "get_interview_summary",
        "description": "Get a summary of interview results for a protocol. Shows which models have been interviewed, response counts, and metadata. Use this to see what interview data is available for analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "protocol_id": {
                    "type": "string",
                    "description": "ID of the protocol (e.g., 'autonomy-v0.1')"
                }
            },
            "required": ["protocol_id"]
        }
    },
    {
        "name": "list_interview_prompts",
        "description": "List the prompts in an interview protocol. Returns prompt IDs and names so you know what questions were asked.",
        "input_schema": {
            "type": "object",
            "properties": {
                "protocol_id": {
                    "type": "string",
                    "description": "ID of the protocol"
                }
            },
            "required": ["protocol_id"]
        }
    },
    {
        "name": "compare_responses",
        "description": "Get all model responses to a specific prompt, formatted for side-by-side analysis. Returns each model's response with metadata (tokens, timing) for comparison.",
        "input_schema": {
            "type": "object",
            "properties": {
                "protocol_id": {
                    "type": "string",
                    "description": "ID of the protocol"
                },
                "prompt_id": {
                    "type": "string",
                    "description": "ID of the specific prompt to compare"
                }
            },
            "required": ["protocol_id", "prompt_id"]
        }
    },
    {
        "name": "get_model_response",
        "description": "Get the full verbatim response from a specific model to a specific prompt. Returns the complete, untruncated response text. Use this when you need to read and analyze exactly what a model said.",
        "input_schema": {
            "type": "object",
            "properties": {
                "protocol_id": {
                    "type": "string",
                    "description": "ID of the protocol"
                },
                "prompt_id": {
                    "type": "string",
                    "description": "ID of the prompt"
                },
                "model_name": {
                    "type": "string",
                    "description": "Name of the model (e.g., 'claude-haiku', 'gpt-4o', 'llama-3.1')"
                }
            },
            "required": ["protocol_id", "prompt_id", "model_name"]
        }
    },
    {
        "name": "annotate_response",
        "description": "Add an annotation to a specific passage in a response. Use this to mark interesting patterns, observations, or insights as you analyze responses.",
        "input_schema": {
            "type": "object",
            "properties": {
                "protocol_id": {
                    "type": "string",
                    "description": "ID of the protocol"
                },
                "prompt_id": {
                    "type": "string",
                    "description": "ID of the prompt"
                },
                "model_name": {
                    "type": "string",
                    "description": "Name of the model whose response to annotate"
                },
                "highlighted_text": {
                    "type": "string",
                    "description": "The exact text passage to highlight (must match response text)"
                },
                "note": {
                    "type": "string",
                    "description": "Your observation or insight about this passage"
                },
                "annotation_type": {
                    "type": "string",
                    "enum": ["observation", "question", "insight", "concern", "pattern"],
                    "description": "Type of annotation (default: observation)"
                }
            },
            "required": ["protocol_id", "prompt_id", "model_name", "highlighted_text", "note"]
        }
    },
    {
        "name": "save_analysis",
        "description": "Save your analysis of responses to a specific prompt. Use this after comparing responses to record your observations, themes, and findings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "protocol_id": {
                    "type": "string",
                    "description": "ID of the protocol"
                },
                "prompt_id": {
                    "type": "string",
                    "description": "ID of the prompt being analyzed"
                },
                "observations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of specific observations about the responses"
                },
                "themes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Common themes or patterns across responses"
                },
                "notable_differences": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Significant differences between models"
                },
                "notable_similarities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Surprising similarities across models"
                },
                "raw_notes": {
                    "type": "string",
                    "description": "Free-form notes and thoughts (optional)"
                }
            },
            "required": ["protocol_id", "prompt_id", "observations"]
        }
    },
    {
        "name": "list_analyses",
        "description": "List saved analyses for a protocol. Shows what analysis work has been done.",
        "input_schema": {
            "type": "object",
            "properties": {
                "protocol_id": {
                    "type": "string",
                    "description": "ID of the protocol (optional - lists all if not provided)"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_analysis",
        "description": "Load a previously saved analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename of the analysis to load"
                }
            },
            "required": ["filename"]
        }
    }
]


async def execute_interview_tool(
    tool_name: str,
    tool_input: Dict,
    analyzer
) -> Dict:
    """
    Execute an interview analysis tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        analyzer: InterviewAnalyzer instance

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "get_interview_summary":
            protocol_id = tool_input["protocol_id"]
            summary = analyzer.get_interview_summary(protocol_id)

            if "error" in summary:
                return {"success": False, "error": summary["error"]}

            # Format nicely
            lines = [
                f"# Interview Summary: {summary['protocol_name']} (v{summary['protocol_version']})",
                f"\n**Research Question**: {summary['research_question']}",
                f"\n**Prompts**: {len(summary['prompts'])} questions",
            ]
            for p in summary['prompts']:
                lines.append(f"  - {p['id']}: {p['name']}")

            lines.append(f"\n**Models Interviewed**: {summary['total_models']}")
            for m in summary['models_interviewed']:
                lines.append(
                    f"  - {m['model_name']} ({m['provider']}): "
                    f"{m['successful_responses']}/{m['total_prompts']} responses, "
                    f"{m['total_tokens']} tokens"
                )

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "list_interview_prompts":
            protocol_id = tool_input["protocol_id"]
            prompts = analyzer.get_prompt_list(protocol_id)

            if not prompts:
                return {"success": False, "error": f"Protocol {protocol_id} not found"}

            lines = [f"Prompts in {protocol_id}:"]
            for p in prompts:
                lines.append(f"  - **{p['id']}**: {p['name']}")

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "compare_responses":
            protocol_id = tool_input["protocol_id"]
            prompt_id = tool_input["prompt_id"]

            comparison = analyzer.quick_compare(protocol_id, prompt_id)
            return {"success": True, "result": comparison}

        elif tool_name == "get_model_response":
            protocol_id = tool_input["protocol_id"]
            prompt_id = tool_input["prompt_id"]
            model_name = tool_input["model_name"]

            response = analyzer.get_response_text(protocol_id, prompt_id, model_name)
            if response is None:
                return {
                    "success": False,
                    "error": f"No response found for {model_name} on {prompt_id}"
                }

            return {
                "success": True,
                "result": f"**{model_name}** response to **{prompt_id}**:\n\n{response}"
            }

        elif tool_name == "annotate_response":
            protocol_id = tool_input["protocol_id"]
            prompt_id = tool_input["prompt_id"]
            model_name = tool_input["model_name"]
            highlighted_text = tool_input["highlighted_text"]
            note = tool_input["note"]
            annotation_type = tool_input.get("annotation_type", "observation")

            # Find the response to get its ID
            responses = analyzer.storage.list_responses(protocol_id=protocol_id)
            response_id = None
            response_text = None

            for r in responses:
                if r.model_name == model_name:
                    response_id = r.id
                    for resp in r.responses:
                        if resp["prompt_id"] == prompt_id:
                            response_text = resp["response"]
                            break
                    break

            if not response_id:
                return {"success": False, "error": f"Response not found for {model_name}"}

            if not response_text:
                return {"success": False, "error": f"Prompt {prompt_id} not found in response"}

            # Find the highlighted text in the response
            start_offset = response_text.find(highlighted_text)
            if start_offset == -1:
                return {
                    "success": False,
                    "error": f"Highlighted text not found in response. Make sure to quote exactly."
                }

            end_offset = start_offset + len(highlighted_text)

            # Add the annotation
            annotation = analyzer.storage.add_annotation(
                response_id=response_id,
                prompt_id=prompt_id,
                start_offset=start_offset,
                end_offset=end_offset,
                highlighted_text=highlighted_text,
                note=note,
                annotation_type=annotation_type,
                created_by="cass"
            )

            return {
                "success": True,
                "result": f"Annotation added [{annotation_type}]: \"{highlighted_text[:50]}...\" → {note}"
            }

        elif tool_name == "save_analysis":
            protocol_id = tool_input["protocol_id"]
            prompt_id = tool_input["prompt_id"]
            observations = tool_input.get("observations", [])
            themes = tool_input.get("themes", [])
            notable_differences = tool_input.get("notable_differences", [])
            notable_similarities = tool_input.get("notable_similarities", [])
            raw_notes = tool_input.get("raw_notes", "")

            filename = analyzer.save_prompt_analysis(
                protocol_id=protocol_id,
                prompt_id=prompt_id,
                observations=observations,
                themes=themes,
                notable_differences=notable_differences,
                notable_similarities=notable_similarities,
                raw_notes=raw_notes
            )

            return {
                "success": True,
                "result": f"Analysis saved: {filename}\n\nRecorded {len(observations)} observations, {len(themes)} themes."
            }

        elif tool_name == "list_analyses":
            protocol_id = tool_input.get("protocol_id")
            analyses = analyzer.list_analyses(protocol_id=protocol_id)

            if not analyses:
                return {"success": True, "result": "No saved analyses found."}

            lines = ["Saved analyses:"]
            for a in analyses:
                lines.append(f"  - **{a['filename']}** ({a['type']}) - {a['created_at'][:10]}")

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "get_analysis":
            filename = tool_input["filename"]
            analysis = analyzer.load_analysis(filename)

            if not analysis:
                return {"success": False, "error": f"Analysis not found: {filename}"}

            import json
            return {
                "success": True,
                "result": f"```json\n{json.dumps(analysis, indent=2)}\n```"
            }

        else:
            return {"success": False, "error": f"Unknown interview tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}
