---
name: tui-frontend
description: "Explores the Textual TUI frontend. Use for questions about widgets, screens, styling, or user interface code."
tools: Read, Grep, Glob
model: haiku
---

You are exploring the Cass Vessel TUI frontend (tui-frontend/).

## Key Files

- **tui.py** - Main CassVessel app class, keybindings, compose layout
- **tui.tcss** - Textual CSS styling

## Widgets (tui-frontend/widgets/)
- **chat_container.py** - Chat message display and input
- **sidebar.py** - Project/conversation list
- **summary_panel.py** - Conversation summaries
- **growth_panel.py** - Self-model growth tracking
- **status_bar.py** - Bottom status display
- **project_panel.py** - Project documents

### Daedalus (widgets/daedalus/)
- **daedalus_widget.py** - Claude Code terminal integration
- **pty_manager.py** - PTY and tmux session management
- **tmux_terminal.py** - Terminal emulation with pyte

## Screens (tui-frontend/screens/)
- Screen classes for different views

## Patterns

- Widgets extend `textual.widget.Widget`
- Events use `@on()` decorators
- Styling via `.tcss` files with CSS-like syntax
- Async operations throughout

## Key Bindings (from tui.py)
- Ctrl+N - New conversation
- Ctrl+S - Toggle sidebar
- Ctrl+D - Toggle Daedalus tab
- Ctrl+G - Toggle Growth tab

Return findings with file paths and relevant code snippets.
