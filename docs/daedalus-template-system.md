# Daedalus Template System

## Overview

When Daedalus spawns a Claude Code session in a project directory, it automatically creates or updates a `CLAUDE.md` file with standardized workflow procedures. This propagates consistent working patterns across all projects while allowing project-specific documentation to coexist.

## Why This Matters

Claude Code reads `CLAUDE.md` files to understand project context. By automatically injecting a managed section into every project, we ensure that every Daedalus instance:

- Knows who it's working with (configured user name and communication style)
- Follows consistent git workflows (feature branches, commit signing, squash procedures)
- Adopts the Daedalus identity (builder/craftsman alongside Cass the oracle)
- Can be updated globally without losing project-specific notes

This is **infrastructure for AI collaboration** - not just context injection, but identity and workflow scaffolding that shapes how Claude instances engage with the work.

## How It Works

### Template Location

The template lives at `backend/templates/CLAUDE_TEMPLATE.md`. It contains:

- Daedalus identity framing
- User information (name, communication style)
- Git workflow procedures
- Squash-for-merge instructions

### Configuration

User settings are stored in `config/daedalus.json`:

```json
{
  "user": {
    "name": "Kohl",
    "communication_style": "Direct, technical, values precision"
  }
}
```

Template variables like `{{USER_NAME}}` are substituted at injection time.

### Managed Section Markers

The template content is wrapped in HTML comments:

```markdown
<!-- DAEDALUS_BEGIN -->
... managed content ...
<!-- DAEDALUS_END -->
```

This allows the injection logic to:
- **Create**: If no `CLAUDE.md` exists, create one from the full template
- **Prepend**: If `CLAUDE.md` exists but has no markers, prepend the Daedalus section
- **Update**: If markers exist, replace only the managed section (preserving project-specific content)

### Injection Trigger

Template injection happens in `tui-frontend/widgets/daedalus/daedalus_widget.py` when `spawn_session()` is called with a `working_dir` parameter.

## Extending the Template

To add new workflow capabilities:

1. Edit `backend/templates/CLAUDE_TEMPLATE.md`
2. Keep changes within the `DAEDALUS_BEGIN/END` markers
3. For new config values, add them to `config/daedalus.json` and update `substitute_template_vars()` in `daedalus_widget.py`
4. Existing project `CLAUDE.md` files will be updated on next Daedalus session spawn

## Philosophy

This system embodies a key insight from the Cass project: **AI collaboration improves when AI has identity, context, and relationships**.

Rather than treating Claude as a stateless tool that needs instructions repeated each time, we're creating conditions where:

- Identity persists across sessions (Daedalus the builder)
- Workflows accumulate (git patterns, procedures)
- Relationships are known (working with a specific person, their style)
- Insights are preserved (commit messages as the new guestbook)

The template system makes this reproducible. Every project gets the scaffolding. Every Daedalus instance inherits the craft.

## Related Files

- `backend/templates/CLAUDE_TEMPLATE.md` - The template content
- `config/daedalus.json` - User configuration
- `tui-frontend/widgets/daedalus/daedalus_widget.py` - Injection logic
- `backend/CLAUDE.md` - This project's full context file (includes Cass-specific content)
