"""
Interview Analysis Tool Handler

Tools for Cass to analyze model interview responses and build research insights.
"""
from typing import Dict
from pathlib import Path

# Tool definitions for Cass
INTERVIEW_TOOLS = [
    # === Protocol Creation ===
    {
        "name": "create_interview_protocol",
        "description": "Create a new interview protocol for researching AI model behavior. Define your research question, context framing, and the specific prompts to ask. The protocol will be saved and can then be executed against models.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short name for the protocol (e.g., 'baseline-inference-comparison')"
                },
                "version": {
                    "type": "string",
                    "description": "Version string (e.g., 'v0.1')"
                },
                "research_question": {
                    "type": "string",
                    "description": "The main research question this protocol investigates"
                },
                "context_framing": {
                    "type": "string",
                    "description": "Context provided before each prompt (sets the scene for the model)"
                },
                "prompts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Short identifier (e.g., 'inference-test-1')"},
                            "name": {"type": "string", "description": "Human-readable name"},
                            "text": {"type": "string", "description": "The actual prompt text"}
                        },
                        "required": ["id", "name", "text"]
                    },
                    "description": "List of prompts to ask in the interview"
                },
                "description": {
                    "type": "string",
                    "description": "Longer description of what this protocol is designed to test (optional)"
                }
            },
            "required": ["name", "version", "research_question", "context_framing", "prompts"]
        }
    },
    {
        "name": "list_protocols",
        "description": "List all available interview protocols. Shows protocol IDs, names, versions, and research questions.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    # === Interview Execution ===
    {
        "name": "run_interview",
        "description": "Execute an interview protocol against one or more AI models. Returns the responses from each model to each prompt. Use this to gather data for analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "protocol_id": {
                    "type": "string",
                    "description": "ID of the protocol to run"
                },
                "models": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of model names to interview. Options: 'claude-haiku', 'claude-sonnet', 'claude-opus', 'gpt-4o', 'llama-3.1'. If not specified, runs against all available models."
                }
            },
            "required": ["protocol_id"]
        }
    },
    {
        "name": "list_available_models",
        "description": "List the AI models available for interviewing, including their provider and model ID.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    # === Analysis Tools ===
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
    analyzer,
    protocol_manager=None,
    dispatcher=None
) -> Dict:
    """
    Execute an interview analysis tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        analyzer: InterviewAnalyzer instance
        protocol_manager: ProtocolManager instance (for create/list protocols)
        dispatcher: InterviewDispatcher instance (for running interviews)

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        # === Protocol Creation Tools ===
        if tool_name == "create_interview_protocol":
            if not protocol_manager:
                return {"success": False, "error": "Protocol manager not available"}

            name = tool_input["name"]
            version = tool_input["version"]
            research_question = tool_input["research_question"]
            context_framing = tool_input["context_framing"]
            prompts = tool_input["prompts"]
            description = tool_input.get("description", "")

            protocol = protocol_manager.create_protocol(
                name=name,
                version=version,
                research_question=research_question,
                context_framing=context_framing,
                prompts=prompts,
                created_by="cass",
                description=description
            )

            lines = [
                f"# Protocol Created: {protocol.name} (v{protocol.version})",
                f"\n**Protocol ID**: `{protocol.id}`",
                f"\n**Research Question**: {protocol.research_question}",
                f"\n**Prompts**: {len(prompts)} questions defined",
            ]
            for p in prompts:
                lines.append(f"  - `{p['id']}`: {p['name']}")

            lines.append(f"\n*Use `run_interview` with protocol_id='{protocol.id}' to execute this protocol.*")

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "list_protocols":
            if not protocol_manager:
                return {"success": False, "error": "Protocol manager not available"}

            protocols = protocol_manager.list_all()

            if not protocols:
                return {"success": True, "result": "No interview protocols found. Use `create_interview_protocol` to create one."}

            lines = ["# Available Interview Protocols\n"]
            for p in protocols:
                lines.append(f"## {p.name} (v{p.version})")
                lines.append(f"- **ID**: `{p.id}`")
                lines.append(f"- **Research Question**: {p.research_question}")
                lines.append(f"- **Prompts**: {len(p.prompts)}")
                lines.append(f"- **Created**: {p.created_at[:10]} by {p.created_by}")
                lines.append("")

            return {"success": True, "result": "\n".join(lines)}

        # === Interview Execution Tools ===
        elif tool_name == "run_interview":
            if not protocol_manager or not dispatcher:
                return {"success": False, "error": "Protocol manager or dispatcher not available"}

            protocol_id = tool_input["protocol_id"]
            model_names = tool_input.get("models")

            # Load protocol
            protocol = protocol_manager.load(protocol_id)
            if not protocol:
                return {"success": False, "error": f"Protocol not found: {protocol_id}"}

            # Import model configs
            from interviews.dispatch import DEFAULT_MODELS, ModelConfig

            # Filter models if specified
            if model_names:
                model_configs = [m for m in DEFAULT_MODELS if m.name in model_names]
                if not model_configs:
                    return {"success": False, "error": f"No matching models found. Available: {[m.name for m in DEFAULT_MODELS]}"}
            else:
                model_configs = DEFAULT_MODELS

            # Run the interview
            lines = [f"# Running Interview: {protocol.name}\n"]
            lines.append(f"Interviewing {len(model_configs)} models: {[m.name for m in model_configs]}\n")

            results = await dispatcher.run_interview_batch(protocol, model_configs)

            # Store results
            for result in results:
                if "error" in result and result.get("error"):
                    lines.append(f"**{result['model_name']}**: ERROR - {result['error']}")
                else:
                    # Store the response
                    from interviews.storage import InterviewResponse
                    response = InterviewResponse(
                        id=f"{result['model_name']}-{protocol_id}-{result['timestamp'][:10]}",
                        protocol_id=result['protocol_id'],
                        protocol_version=result['protocol_version'],
                        model_name=result['model_name'],
                        model_id=result['model_id'],
                        provider=result['provider'],
                        timestamp=result['timestamp'],
                        responses=result['responses'],
                        metadata=result['metadata']
                    )
                    analyzer.storage.save_response(response)

                    successful = sum(1 for r in result['responses'] if r.get('response'))
                    total_tokens = result['metadata']['total_input_tokens'] + result['metadata']['total_output_tokens']
                    lines.append(f"**{result['model_name']}**: {successful}/{len(result['responses'])} responses, {total_tokens} tokens")

            lines.append(f"\n*Results saved. Use analysis tools to examine responses.*")

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "list_available_models":
            from interviews.dispatch import DEFAULT_MODELS

            lines = ["# Available Models for Interviewing\n"]
            for m in DEFAULT_MODELS:
                lines.append(f"- **{m.name}** ({m.provider}): `{m.model_id}`")

            return {"success": True, "result": "\n".join(lines)}

        # === Analysis Tools ===
        elif tool_name == "get_interview_summary":
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
