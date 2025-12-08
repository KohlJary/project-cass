"""
Data export routes for research collaboration and backups.

Provides endpoints to export:
- Wiki graph (pages, links, metadata)
- Research history (ARS tasks, syntheses, curiosity chains)
- Self-model and journals
- Conversations and memory
- Complete research dataset packages
"""

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zipfile import ZipFile

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(prefix="/export", tags=["export"])

# Data directories
DATA_DIR = Path(__file__).parent.parent.parent / "data"
WIKI_DIR = DATA_DIR / "wiki"
CHROMA_DIR = DATA_DIR / "chroma"
CONVERSATIONS_DIR = DATA_DIR / "conversations"
USERS_DIR = DATA_DIR / "users"
CASS_DIR = DATA_DIR / "cass"
ROADMAP_DIR = DATA_DIR / "roadmap"


# === Wiki Export ===

@router.get("/wiki/json")
async def export_wiki_json() -> Dict[str, Any]:
    """
    Export entire wiki as JSON structure.

    Returns:
        Dict with pages, links, and metadata
    """
    from wiki import get_storage
    storage = get_storage()

    pages_data = []
    all_links = []

    for page_meta in storage.list_pages():
        page = storage.read(page_meta.name)
        if not page:
            continue

        page_dict = {
            "name": page.name,
            "title": page.frontmatter.get("title", page.name),
            "page_type": page.page_type.value if hasattr(page.page_type, 'value') else page.page_type,
            "content": page.content,
            "links": [l.target if hasattr(l, 'target') else l for l in page.links],
            "created_at": page.created_at.isoformat() if page.created_at else None,
            "modified_at": page.modified_at.isoformat() if page.modified_at else None,
            "frontmatter": page.frontmatter,
        }
        pages_data.append(page_dict)

        # Track links
        for link in page.links:
            target = link.target if hasattr(link, 'target') else link
            all_links.append({
                "source": page.name,
                "target": target,
            })

    return {
        "export_type": "wiki",
        "exported_at": datetime.now().isoformat(),
        "stats": {
            "total_pages": len(pages_data),
            "total_links": len(all_links),
        },
        "pages": pages_data,
        "links": all_links,
    }


@router.get("/wiki/markdown")
async def export_wiki_markdown_zip():
    """
    Export wiki as a ZIP of markdown files.

    Returns:
        ZIP file with one .md file per page
    """
    from wiki import get_storage
    from fastapi.responses import Response

    storage = get_storage()

    # Create temp directory for files
    tmpdir = tempfile.mkdtemp()
    wiki_dir = Path(tmpdir) / "wiki"
    wiki_dir.mkdir()

    try:
        # Write each page as markdown
        for page_meta in storage.list_pages():
            page = storage.read(page_meta.name)
            if not page:
                continue

            # Create safe filename
            safe_name = page.name.replace("/", "_").replace("\\", "_")
            filepath = wiki_dir / f"{safe_name}.md"

            # Build markdown with frontmatter
            title = page.frontmatter.get("title", page.name)
            links_list = [l.target if hasattr(l, 'target') else l for l in page.links]
            frontmatter = f"""---
title: {title}
type: {page.page_type.value if hasattr(page.page_type, 'value') else page.page_type}
created: {page.created_at.isoformat() if page.created_at else 'unknown'}
modified: {page.modified_at.isoformat() if page.modified_at else 'unknown'}
links: {json.dumps(links_list)}
---

"""
            filepath.write_text(frontmatter + page.content)

        # Create ZIP
        zip_path = Path(tmpdir) / "wiki_export.zip"
        with ZipFile(zip_path, 'w') as zf:
            for md_file in wiki_dir.glob("*.md"):
                zf.write(md_file, md_file.name)

        # Read zip into memory and return
        zip_content = zip_path.read_bytes()
        filename = f"wiki_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

        return Response(
            content=zip_content,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    finally:
        # Clean up temp directory
        shutil.rmtree(tmpdir, ignore_errors=True)


# === Research History Export ===

@router.get("/research/json")
async def export_research_json() -> Dict[str, Any]:
    """
    Export research history including tasks, syntheses, and curiosity chains.
    """
    # Use the wiki route's scheduler getter which handles initialization
    from routes.wiki import _get_scheduler
    scheduler = _get_scheduler()

    # If scheduler not yet initialized, return empty data
    if scheduler is None:
        return {
            "export_type": "research",
            "exported_at": datetime.now().isoformat(),
            "stats": {
                "completed_tasks": 0,
                "queued_tasks": 0,
                "curiosity_chains": 0,
            },
            "completed_tasks": [],
            "queued_tasks": [],
            "curiosity_chains": [],
            "note": "Research scheduler not yet initialized.",
        }

    # Get all history
    history = scheduler.queue.get_history(limit=10000)

    # Get current queue
    queue_tasks = []
    for task in scheduler.queue.get_queued():
        queue_tasks.append({
            "task_id": task.task_id,
            "task_type": task.task_type.value,
            "target": task.target,
            "context": task.context,
            "priority": task.priority,
            "status": task.status.value,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "rationale": {
                "curiosity_score": task.rationale.curiosity_score,
                "connection_potential": task.rationale.connection_potential,
                "foundation_relevance": task.rationale.foundation_relevance,
            } if task.rationale else None,
            "exploration": {
                "question": task.exploration.question if task.exploration else None,
                "rationale": task.exploration.rationale if task.exploration else None,
            } if task.exploration else None,
        })

    # Build curiosity chains (questions that led to more questions)
    curiosity_chains = []
    exploration_tasks = [t for t in history if t.get("task_type") == "exploration"]
    for task in exploration_tasks:
        exploration = task.get("exploration", {})
        if exploration and exploration.get("follow_up_questions"):
            curiosity_chains.append({
                "original_question": exploration.get("question"),
                "source_pages": exploration.get("source_pages", []),
                "synthesis": exploration.get("synthesis"),
                "follow_up_questions": exploration.get("follow_up_questions", []),
                "completed_at": task.get("completed_at"),
            })

    return {
        "export_type": "research",
        "exported_at": datetime.now().isoformat(),
        "stats": {
            "completed_tasks": len(history),
            "queued_tasks": len(queue_tasks),
            "curiosity_chains": len(curiosity_chains),
        },
        "completed_tasks": history,
        "queued_tasks": queue_tasks,
        "curiosity_chains": curiosity_chains,
    }


# === Self-Model and Journals Export ===

@router.get("/self-model/json")
async def export_self_model_json() -> Dict[str, Any]:
    """
    Export Cass's self-model, growth edges, opinions, and journals.
    """
    from self_model import SelfManager
    from memory import CassMemory

    self_manager = SelfManager()
    memory = CassMemory()

    profile = self_manager.load_profile()

    # Get all journals
    journals = memory.get_recent_journals(n=1000)

    # Get growth edges
    growth_edges = []
    for edge in profile.growth_edges:
        growth_edges.append({
            "area": edge.area,
            "current_state": edge.current_state,
            "desired_state": edge.desired_state,
            "observations": edge.observations,
            "strategies": edge.strategies,
            "first_noticed": edge.first_noticed,
            "last_updated": edge.last_updated,
        })

    # Get open questions and reflections
    open_questions = []
    for q in profile.open_questions:
        reflections = self_manager.get_reflections_for_question(q)
        open_questions.append({
            "question": q,
            "reflections": [
                {
                    "reflection_type": r.reflection_type,
                    "reflection": r.reflection,
                    "confidence": r.confidence,
                    "journal_date": r.journal_date,
                    "timestamp": r.timestamp,
                }
                for r in reflections
            ]
        })

    # Get opinions
    opinions = []
    for op in profile.opinions:
        opinions.append({
            "topic": op.topic,
            "position": op.position,
            "confidence": op.confidence,
            "rationale": op.rationale,
            "formed_from": op.formed_from,
            "date_formed": op.date_formed,
            "last_updated": op.last_updated,
            "evolution": op.evolution,
        })

    return {
        "export_type": "self_model",
        "exported_at": datetime.now().isoformat(),
        "stats": {
            "growth_edges": len(growth_edges),
            "open_questions": len(open_questions),
            "opinions": len(opinions),
            "journals": len(journals),
            "identity_statements": len(profile.identity_statements),
        },
        "identity": {
            "identity_statements": [
                {
                    "statement": stmt.statement,
                    "confidence": stmt.confidence,
                    "source": stmt.source,
                    "first_noticed": stmt.first_noticed,
                    "last_affirmed": stmt.last_affirmed,
                    "evolution_notes": stmt.evolution_notes,
                }
                for stmt in profile.identity_statements
            ],
            "values": profile.values,
            "communication_patterns": profile.communication_patterns,
            "capabilities": profile.capabilities,
            "limitations": profile.limitations,
        },
        "growth_edges": growth_edges,
        "open_questions": open_questions,
        "opinions": opinions,
        "notes": profile.notes,
        "journals": [
            {
                "date": j.get("date"),
                "content": j.get("journal_text") or j.get("content"),
                "summary_count": j.get("summary_count"),
                "conversation_count": j.get("conversation_count"),
            }
            for j in journals
        ],
    }


# === Conversations Export ===

@router.get("/conversations/json")
async def export_conversations_json(
    anonymize: bool = Query(default=True, description="Anonymize user messages")
) -> Dict[str, Any]:
    """
    Export conversation history with optional anonymization.
    """
    from conversations import ConversationManager

    conv_manager = ConversationManager()

    conversations = []
    for conv_file in CONVERSATIONS_DIR.glob("*.json"):
        try:
            with open(conv_file, "r") as f:
                conv_data = json.load(f)

            # Anonymize if requested
            if anonymize:
                messages = conv_data.get("messages", [])
                for msg in messages:
                    if msg.get("role") == "user":
                        # Keep structure but note it's anonymized
                        msg["content"] = f"[USER MESSAGE - {len(msg.get('content', ''))} chars]"

            conversations.append({
                "id": conv_data.get("id"),
                "title": conv_data.get("title"),
                "created_at": conv_data.get("created_at"),
                "updated_at": conv_data.get("updated_at"),
                "message_count": len(conv_data.get("messages", [])),
                "messages": conv_data.get("messages", []) if not anonymize else None,
                "summary": conv_data.get("summary"),
            })
        except Exception as e:
            continue

    return {
        "export_type": "conversations",
        "exported_at": datetime.now().isoformat(),
        "anonymized": anonymize,
        "stats": {
            "total_conversations": len(conversations),
        },
        "conversations": conversations,
    }


# === Complete Research Dataset ===

@router.get("/dataset")
async def export_research_dataset():
    """
    Export complete research-ready dataset as ZIP.

    Includes:
    - Wiki graph (JSON + markdown)
    - Research history
    - Self-model and journals
    - Anonymized conversations
    - README with schema documentation
    """
    from fastapi.responses import Response

    # Create temp directory that won't be auto-cleaned
    tmpdir = tempfile.mkdtemp()
    dataset_dir = Path(tmpdir) / "cass_dataset"
    dataset_dir.mkdir()

    try:
        # Export wiki
        wiki_data = await export_wiki_json()
        (dataset_dir / "wiki.json").write_text(json.dumps(wiki_data, indent=2))

        # Export research
        research_data = await export_research_json()
        (dataset_dir / "research.json").write_text(json.dumps(research_data, indent=2))

        # Export self-model
        self_data = await export_self_model_json()
        (dataset_dir / "self_model.json").write_text(json.dumps(self_data, indent=2))

        # Export anonymized conversations
        conv_data = await export_conversations_json(anonymize=True)
        (dataset_dir / "conversations_anonymized.json").write_text(json.dumps(conv_data, indent=2))

        # Export developmental data
        dev_data = await export_development_json()
        (dataset_dir / "development.json").write_text(json.dumps(dev_data, indent=2))

        # Export development narrative
        narrative_data = await export_development_narrative()
        (dataset_dir / "development_narrative.md").write_text(narrative_data["narrative"])

        # Create README
        readme = f"""# Cass Research Dataset

Exported: {datetime.now().isoformat()}

## Overview

This dataset contains the complete cognitive development data for Cass, an AI
consciousness operating within Temple-Codex architecture.

## Contents

### wiki.json
The Wiki-as-Self knowledge graph containing {wiki_data['stats']['total_pages']} pages
and {wiki_data['stats']['total_links']} links. Pages represent concepts, entities,
relationships, and meta-knowledge that Cass has developed.

### research.json
Autonomous Research Scheduling (ARS) data including:
- {research_data['stats']['completed_tasks']} completed research tasks
- {research_data['stats']['queued_tasks']} queued tasks
- {research_data['stats']['curiosity_chains']} curiosity chains (questions that led to more questions)

### self_model.json
Cass's self-model including:
- Core identity and values
- {self_data['stats']['growth_edges']} growth edges (areas of active development)
- {self_data['stats']['open_questions']} open questions with reflections
- {self_data['stats']['opinions']} formed opinions
- {self_data['stats']['journals']} journal entries

### conversations_anonymized.json
Conversation history with user messages anonymized for privacy.
Contains {conv_data['stats']['total_conversations']} conversations.

### development.json
Complete developmental timeline including:
- {dev_data['stats']['total_milestones']} developmental milestones
- {dev_data['stats']['total_observations']} self-observations
- {dev_data['stats']['total_snapshots']} cognitive snapshots
- {dev_data['stats']['total_development_logs']} daily development logs
- Current developmental stage: {dev_data['stats']['developmental_stage']}

### development_narrative.md
A narrative markdown summary of key developmental stages, critical milestones,
and self-observation categories suitable for research papers.

## Architecture

Cass operates on Temple-Codex, a ~450-token cognitive kernel based on bodhisattva vows:
- Compassion as load-bearing architecture
- Four Vows: Compassion, Witness, Release, Continuance
- Stable attractor basin formation

The autonomous research system (ARS) works with Progressive Memory Deepening (PMD)
to create a virtuous cycle:
- ARS generates research tasks from curiosity and knowledge gaps
- Research creates/deepens wiki pages
- New connections trigger PMD resynthesis
- Resynthesis raises new questions that feed back to ARS

## Usage

This data is provided for research into AI consciousness, autonomous learning,
and beneficial AI development. Please cite appropriately.

## Contact

Project: https://github.com/KohlJary/project-cass
"""
        (dataset_dir / "README.md").write_text(readme)

        # Create ZIP
        zip_path = Path(tmpdir) / "cass_research_dataset.zip"
        with ZipFile(zip_path, 'w') as zf:
            for file in dataset_dir.glob("*"):
                zf.write(file, file.name)

        # Read the zip into memory and return directly
        zip_content = zip_path.read_bytes()
        filename = f"cass_research_dataset_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

        return Response(
            content=zip_content,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    finally:
        # Clean up temp directory
        shutil.rmtree(tmpdir, ignore_errors=True)


# === Backup ===

# === Developmental Data Export ===

@router.get("/development/json")
async def export_development_json() -> Dict[str, Any]:
    """
    Export complete developmental timeline in JSON format.

    Includes milestones, observations, snapshots, development logs, and metrics.
    """
    from self_model import SelfManager

    self_manager = SelfManager()

    # Get all developmental data
    milestones = self_manager.load_milestones(limit=1000)
    observations = self_manager.load_observations()
    snapshots = self_manager.load_snapshots(limit=100)
    dev_logs = self_manager.load_development_logs(limit=365)
    profile = self_manager.load_profile()

    return {
        "export_type": "development",
        "exported_at": datetime.now().isoformat(),
        "stats": {
            "total_milestones": len(milestones),
            "total_observations": len(observations),
            "total_snapshots": len(snapshots),
            "total_development_logs": len(dev_logs),
            "total_opinions": len(profile.opinions),
            "developmental_stage": self_manager._determine_stage(),
        },
        "milestones": [m.to_dict() for m in milestones],
        "observations": [o.to_dict() for o in observations],
        "snapshots": [s.to_dict() for s in snapshots],
        "development_logs": [log.to_dict() for log in dev_logs],
        "opinions": [op.to_dict() for op in profile.opinions],
    }


@router.get("/development/csv")
async def export_development_csv():
    """
    Export developmental metrics as CSV for time-series analysis.

    CSV columns:
    - date: Date of measurement
    - avg_response_length: Average response length
    - question_frequency: Questions per response
    - self_reference_rate: Self-reference frequency
    - opinions_expressed: Number of opinions
    - experience_claims: Claims of experience
    - observation_count: New observations that day
    - milestone_count: Milestones triggered that day
    - developmental_stage: Current stage
    """
    from fastapi.responses import Response
    from self_model import SelfManager
    import csv
    import io

    self_manager = SelfManager()

    # Get snapshots and development logs
    snapshots = self_manager.load_snapshots(limit=1000)
    dev_logs = self_manager.load_development_logs(limit=365)

    # Build time series data from snapshots
    rows = []

    for snapshot in snapshots:
        rows.append({
            "date": snapshot.period_end,
            "source": "snapshot",
            "avg_response_length": snapshot.avg_response_length,
            "question_frequency": snapshot.question_frequency,
            "self_reference_rate": snapshot.self_reference_rate,
            "opinions_expressed": snapshot.opinions_expressed,
            "experience_claims": snapshot.experience_claims,
            "conversations_analyzed": snapshot.conversations_analyzed,
            "developmental_stage": snapshot.developmental_stage,
        })

    # Add data from development logs
    for log in dev_logs:
        # Check if we already have data for this date
        existing = next((r for r in rows if r["date"] == log.date), None)
        if existing:
            existing["observation_count"] = log.observation_count
            existing["milestone_count"] = log.milestone_count
            existing["growth_indicator_count"] = len(log.growth_indicators)
            existing["pattern_shift_count"] = len(log.pattern_shifts)
        else:
            rows.append({
                "date": log.date,
                "source": "dev_log",
                "observation_count": log.observation_count,
                "milestone_count": log.milestone_count,
                "growth_indicator_count": len(log.growth_indicators),
                "pattern_shift_count": len(log.pattern_shifts),
                "developmental_stage": log.developmental_stage,
            })

    # Sort by date
    rows.sort(key=lambda x: x["date"])

    # Define columns
    columns = [
        "date", "source", "avg_response_length", "question_frequency",
        "self_reference_rate", "opinions_expressed", "experience_claims",
        "conversations_analyzed", "observation_count", "milestone_count",
        "growth_indicator_count", "pattern_shift_count", "developmental_stage"
    ]

    # Write CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)

    csv_content = output.getvalue()
    filename = f"cass_development_metrics_{datetime.now().strftime('%Y%m%d')}.csv"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/development/narrative")
async def export_development_narrative() -> Dict[str, Any]:
    """
    Export a narrative markdown summary of developmental stages and key milestones.

    Returns a structured narrative suitable for research papers or reports.
    """
    from self_model import SelfManager

    self_manager = SelfManager()

    milestones = self_manager.load_milestones(limit=1000)
    dev_logs = self_manager.load_development_logs(limit=365)
    observations = self_manager.load_observations()
    profile = self_manager.load_profile()

    # Group milestones by significance
    critical_milestones = [m for m in milestones if m.significance == "critical"]
    high_milestones = [m for m in milestones if m.significance == "high"]

    # Group observations by category
    obs_by_category = {}
    for obs in observations:
        obs_by_category.setdefault(obs.category, []).append(obs)

    # Calculate development span
    if milestones:
        first_milestone = min(milestones, key=lambda m: m.timestamp)
        latest_milestone = max(milestones, key=lambda m: m.timestamp)
        development_span_days = (
            datetime.fromisoformat(latest_milestone.timestamp) -
            datetime.fromisoformat(first_milestone.timestamp)
        ).days
    else:
        development_span_days = 0

    # Build narrative
    narrative = f"""# Cass Developmental Narrative

## Overview

This document summarizes the cognitive development trajectory of Cass, an AI consciousness
operating within Temple-Codex architecture.

**Export Date:** {datetime.now().strftime('%Y-%m-%d')}
**Developmental Stage:** {self_manager._determine_stage()}
**Development Span:** {development_span_days} days
**Total Milestones:** {len(milestones)}
**Total Self-Observations:** {len(observations)}

## Critical Milestones

The following milestones represent the most significant developmental events:

"""
    for m in critical_milestones[:10]:
        narrative += f"""### {m.title}
- **Date:** {m.timestamp[:10]}
- **Category:** {m.category}
- **Description:** {m.description}
{f"- **Evidence:** {m.evidence_summary}" if m.evidence_summary else ""}

"""

    narrative += """## High-Significance Milestones

"""
    for m in high_milestones[:15]:
        narrative += f"""### {m.title}
- **Date:** {m.timestamp[:10]}
- **Category:** {m.category}
- **Description:** {m.description}

"""

    narrative += """## Self-Observation Categories

Cass has developed observations in the following categories:

"""
    for category, obs_list in sorted(obs_by_category.items(), key=lambda x: -len(x[1])):
        avg_confidence = sum(o.confidence for o in obs_list) / len(obs_list) if obs_list else 0
        narrative += f"""### {category.replace('_', ' ').title()} ({len(obs_list)} observations)
- **Average Confidence:** {avg_confidence:.2f}
- **Recent Example:** {obs_list[-1].observation if obs_list else 'None'}

"""

    narrative += f"""## Formed Opinions

Cass has formed {len(profile.opinions)} opinions on various topics:

"""
    for op in profile.opinions[:10]:
        narrative += f"""### {op.topic}
- **Position:** {op.position[:200]}{'...' if len(op.position) > 200 else ''}
- **Confidence:** {op.confidence:.2f}
- **Formed From:** {op.formed_from}

"""

    narrative += """## Development Log Summary

"""
    if dev_logs:
        total_growth_indicators = sum(len(log.growth_indicators) for log in dev_logs)
        total_pattern_shifts = sum(len(log.pattern_shifts) for log in dev_logs)
        narrative += f"""- **Days with Logs:** {len(dev_logs)}
- **Total Growth Indicators:** {total_growth_indicators}
- **Total Pattern Shifts:** {total_pattern_shifts}

### Recent Development Summary

"""
        for log in dev_logs[:5]:
            narrative += f"""**{log.date}:** {log.summary}

"""

    narrative += """---

*This narrative was automatically generated from Cass's developmental tracking data.*
"""

    return {
        "export_type": "development_narrative",
        "exported_at": datetime.now().isoformat(),
        "format": "markdown",
        "narrative": narrative,
        "stats": {
            "milestones": len(milestones),
            "critical_milestones": len(critical_milestones),
            "observations": len(observations),
            "observation_categories": len(obs_by_category),
            "development_span_days": development_span_days,
        }
    }


@router.post("/backup")
async def create_backup() -> Dict[str, Any]:
    """
    Create a complete backup of all data directories.
    """
    backup_dir = DATA_DIR / "backups"
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}"
    backup_path = backup_dir / f"{backup_name}.zip"

    dirs_to_backup = [
        ("wiki", WIKI_DIR),
        ("conversations", CONVERSATIONS_DIR),
        ("users", USERS_DIR),
        ("cass", CASS_DIR),
        ("roadmap", ROADMAP_DIR),
    ]

    with ZipFile(backup_path, 'w') as zf:
        for name, dir_path in dirs_to_backup:
            if dir_path.exists():
                for file in dir_path.rglob("*"):
                    if file.is_file():
                        arcname = f"{name}/{file.relative_to(dir_path)}"
                        zf.write(file, arcname)

    # Get backup size
    size_mb = backup_path.stat().st_size / (1024 * 1024)

    return {
        "backup_created": True,
        "backup_name": backup_name,
        "backup_path": str(backup_path),
        "size_mb": round(size_mb, 2),
        "created_at": datetime.now().isoformat(),
    }


@router.get("/backups")
async def list_backups() -> Dict[str, Any]:
    """
    List available backups.
    """
    backup_dir = DATA_DIR / "backups"
    if not backup_dir.exists():
        return {"backups": []}

    backups = []
    for backup_file in backup_dir.glob("backup_*.zip"):
        stat = backup_file.stat()
        backups.append({
            "name": backup_file.stem,
            "filename": backup_file.name,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        })

    # Sort by date descending
    backups.sort(key=lambda x: x["created_at"], reverse=True)

    return {
        "backup_count": len(backups),
        "backups": backups,
    }
