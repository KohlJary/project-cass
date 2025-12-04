"""
Cass Vessel TUI - CSS Styles
Extracted from main tui.py for maintainability
"""

CSS = """
    Screen {
        background: $surface;
    }

    #status {
        dock: top;
        height: 1;
        background: $surface-darken-1;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }


    #debug-panel {
        height: 8;
        background: $surface-darken-1;
        border-bottom: solid $warning;
        display: none;
    }

    #debug-panel.visible {
        display: block;
    }

    #main-container {
        height: 1fr;
    }

    #sidebar {
        width: 32;
        background: $panel;
        border-right: solid $primary;
        padding: 1;
    }

    #projects-header, #conversations-header {
        text-align: center;
        text-style: bold;
        background: $primary;
        color: $text;
        padding: 0 1;
        margin-bottom: 1;
    }

    #conversations-header {
        margin-top: 1;
    }

    #new-project-btn, #new-conversation-btn {
        width: 100%;
        margin-bottom: 1;
    }

    #project-list {
        height: auto;
        min-height: 5;
        max-height: 12;
        border: none;
    }

    #project-list > ListItem {
        padding: 0 1;
    }

    #conversation-list {
        height: 1fr;
        border: none;
    }

    #conversation-list > ListItem {
        padding: 1;
        margin-bottom: 1;
    }

    #conversation-list > ListItem:hover {
        background: $primary 30%;
    }

    #conversation-list > ListItem.-selected {
        background: $primary;
    }

    /* LLM Provider Selector */
    #llm-selector {
        height: auto;
        margin-top: 1;
    }

    #llm-collapsible {
        padding: 0;
    }

    #llm-collapsible > CollapsibleTitle {
        padding: 0 1;
        background: $surface;
    }

    #llm-collapsible > Contents {
        padding: 0 1;
    }

    .llm-section-header {
        text-style: bold;
        color: $text-muted;
        margin-top: 1;
        margin-bottom: 0;
    }

    #provider-radio, #model-radio {
        height: auto;
        border: none;
        padding: 0;
    }

    #provider-radio > RadioButton,
    #model-radio > RadioButton {
        height: auto;
        padding: 0;
        margin: 0;
    }

    #provider-radio > RadioButton:disabled {
        opacity: 0.5;
    }

    #chat-area {
        width: 1fr;
    }

    #content-columns {
        height: 1fr;
        margin: 1 0;
    }

    #chat-column {
        width: 2fr;
    }

    /* Main tabs (Cass / Daedalus) */
    #main-tabs {
        height: 1fr;
    }

    #main-tabs > ContentSwitcher {
        height: 1fr;
    }

    #cass-tab, #daedalus-tab {
        height: 1fr;
    }

    /* Daedalus (Claude Code) tab styling */
    #daedalus-widget {
        height: 1fr;
        background: #1e1e1e;
        padding: 0;
    }

    #daedalus-widget .daedalus-no-session {
        height: 1fr;
        align: center middle;
        padding: 2;
        background: $surface;
    }

    #daedalus-widget .daedalus-content {
        height: 1fr;
        background: #1e1e1e;
    }

    #daedalus-widget .hidden {
        display: none;
    }

    #daedalus-widget .session-info {
        text-align: center;
        margin-bottom: 2;
    }

    #daedalus-widget .spawn-btn {
        margin: 1 2;
    }

    #daedalus-widget .session-list {
        height: auto;
        max-height: 50%;
        margin-top: 2;
    }

    #daedalus-widget .session-btn {
        margin: 0 2 1 2;
    }

    #right-panel {
        width: 1fr;
    }

    #chat-container {
        height: 1fr;
        border: solid $primary;
        margin: 0 1 0 2;
        padding: 1 2;
        background: $surface;
    }

    #right-tabs {
        height: 1fr;
        margin: 0 2 0 1;
    }

    #summary-panel {
        height: 1fr;
        padding: 1;
        background: $surface;
    }

    /* Project panel styling */
    #project-panel {
        height: 1fr;
        background: $surface;
    }

    #project-panel-content {
        height: 1fr;
        width: 100%;
    }

    #doc-list-container {
        width: 1fr;
        max-width: 35;
        height: 1fr;
        border-right: solid $surface-darken-1;
    }

    #doc-list-header {
        height: 1;
        padding: 0 1;
        background: $surface-darken-1;
        text-style: bold;
        color: $primary;
    }

    #doc-list {
        height: 1fr;
        padding: 0;
    }

    #doc-list > ListItem {
        padding: 1;
        height: auto;
    }

    #doc-list > ListItem:hover {
        background: $surface-lighten-1;
    }

    #doc-list > ListItem.-selected {
        background: $primary-darken-2;
    }

    #doc-viewer {
        width: 2fr;
        height: 1fr;
        padding: 1;
    }

    #doc-content {
        width: 100%;
        height: auto;
    }

    #doc-content.doc-placeholder {
        color: $text-muted;
        text-style: italic;
    }

    #terminal, #terminal-placeholder {
        height: 1fr;
        background: $surface;
    }

    #terminal-placeholder {
        padding: 2;
        color: $text-muted;
    }

    .chat-message {
        height: auto;
        width: 100%;
        margin-bottom: 1;
        padding: 0 0 1 0;
        border-bottom: solid $surface-darken-1;
    }

    .chat-message .message-header {
        height: auto;
        width: 100%;
        margin-bottom: 0;
    }

    .chat-message .message-role {
        width: 1fr;
    }

    .chat-message .message-header Button {
        width: auto;
        min-width: 4;
        height: 1;
        margin: 0;
        padding: 0 1;
        border: none;
        background: $primary-darken-2;
    }

    .chat-message .message-header .replay-btn {
        background: $success-darken-2;
        margin-right: 1;
    }

    .chat-message .message-header .replay-btn:hover {
        background: $success;
    }

    .chat-message .message-header .exclude-btn {
        background: $warning-darken-2;
        margin-left: 1;
    }

    .chat-message .message-header .exclude-btn:hover {
        background: $warning;
    }

    .chat-message .message-text {
        width: 100%;
        padding: 0 0 0 2;
    }

    .chat-message .message-indicators {
        padding: 0 0 0 2;
        margin-top: 1;
    }

    /* Code block styling */
    .message-code-block {
        height: auto;
        margin: 1 0 1 2;
        background: $surface-darken-2;
        border: solid $primary-darken-2;
    }

    .message-code-block .code-header {
        height: 1;
        background: $primary-darken-3;
        padding: 0 1;
    }

    .message-code-block .code-language {
        width: 1fr;
        color: $text-muted;
        text-style: italic;
    }

    .message-code-block .code-copy-btn {
        width: auto;
        min-width: 4;
        height: 1;
        margin: 0;
        padding: 0 1;
        border: none;
        background: $primary-darken-1;
    }

    .message-code-block .code-content {
        height: auto;
        padding: 1;
        overflow-x: auto;
    }

    #thinking-indicator {
        height: auto;
        padding: 0 1;
        margin: 0 1 0 2;
        color: $warning;
        text-style: italic;
        display: none;
    }

    #thinking-indicator.visible {
        display: block;
    }

    #input-container {
        height: auto;
        min-height: 3;
        max-height: 5;
        background: $panel;
        padding: 0 1;
        margin: 0 1 0 2;
    }

    #attachment-indicator {
        height: 1;
        padding: 0;
        color: $success;
        text-style: bold;
    }

    #attachment-indicator.hidden {
        display: none;
    }

    #input {
        width: 1fr;
    }

    /* Rename dialog modal */
    RenameConversationScreen {
        align: center middle;
    }

    #rename-dialog {
        width: 60;
        height: auto;
        background: $panel;
        border: thick $primary;
        padding: 1 2;
    }

    #rename-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #rename-input {
        width: 100%;
        margin-bottom: 1;
    }

    #rename-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #rename-buttons Button {
        margin: 0 1;
    }

    /* Delete confirmation dialog modal */
    DeleteConversationScreen {
        align: center middle;
    }

    #delete-dialog {
        width: 60;
        height: auto;
        background: $panel;
        border: thick $error;
        padding: 1 2;
    }

    #delete-title {
        text-align: center;
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }

    #delete-message {
        text-align: center;
        margin-bottom: 1;
    }

    #delete-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #delete-buttons Button {
        margin: 0 1;
    }

    /* New project dialog modal */
    NewProjectScreen {
        align: center middle;
    }

    #project-dialog {
        width: 60;
        height: auto;
        background: $panel;
        border: thick $primary;
        padding: 1 2;
    }

    #project-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    .field-label {
        margin-top: 1;
        color: $text-muted;
    }

    #project-name-input, #project-path-input {
        width: 100%;
        margin-bottom: 1;
    }

    #project-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #project-buttons Button {
        margin: 0 1;
    }

    /* User selector in sidebar */
    #user-selector {
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
    }

    #user-header {
        text-style: bold;
        color: $primary;
        margin-bottom: 0;
    }

    #current-user-display {
        color: $text;
        margin: 0 0 0 1;
    }

    #switch-user-btn {
        width: 100%;
        margin-top: 1;
    }

    /* User select dialog modal */
    UserSelectScreen {
        align: center middle;
    }

    #user-dialog {
        width: 50;
        height: auto;
        max-height: 80%;
        background: $panel;
        border: thick $primary;
        padding: 1 2;
    }

    #user-dialog-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #user-select-list {
        height: auto;
        max-height: 15;
        margin-bottom: 1;
    }

    #user-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #create-user-btn {
        width: 100%;
        margin-bottom: 1;
    }

    /* Create user dialog modal - onboarding form */
    CreateUserScreen {
        align: center middle;
    }

    #create-user-dialog {
        width: 70;
        height: auto;
        max-height: 80%;
        background: $panel;
        border: thick $primary;
        padding: 2 3;
    }

    #create-user-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 0;
    }

    #create-user-subtitle {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    #create-user-dialog Rule {
        margin: 1 0;
    }

    #user-name-input {
        width: 100%;
        margin-bottom: 1;
    }

    #user-relationship-select {
        width: 100%;
        margin-bottom: 1;
    }

    .field-hint {
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }

    #user-notes-input {
        width: 100%;
        height: 6;
        margin-bottom: 1;
    }

    #create-user-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 2;
    }

    #create-user-buttons Button {
        margin: 0 1;
    }

    #create-user-buttons #create-user-submit {
        min-width: 16;
    }

    /* User panel styling */
    #user-panel {
        height: 1fr;
        background: $surface;
    }

    #user-content {
        height: 1fr;
        padding: 1;
    }

    #user-panel-header {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #profile-section {
        height: auto;
        max-height: 40%;
        margin-bottom: 1;
    }

    #profile-display {
        padding: 1;
    }

    #observations-header {
        text-style: bold;
        margin-top: 1;
    }

    #observations-count {
        color: $text-muted;
        margin-bottom: 1;
    }

    #observations-list {
        height: 1fr;
    }

    ObservationItem {
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
        layout: horizontal;
    }

    .obs-text {
        width: 1fr;
    }

    .obs-delete-btn {
        width: 3;
        min-width: 3;
        height: 1;
        margin-left: 1;
    }

    /* Growth panel styling */
    #growth-panel {
        height: 1fr;
        background: $surface;
    }

    #growth-content {
        height: 1fr;
        width: 100%;
    }

    #calendar-section {
        height: auto;
        max-height: 16;
        padding: 1;
        border-bottom: solid $surface-darken-1;
    }

    #calendar-header {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #calendar-widget {
        width: 100%;
        height: auto;
    }

    #calendar-nav {
        height: 1;
        width: 100%;
        align: center middle;
        margin-bottom: 1;
    }

    #calendar-nav .nav-btn {
        width: 3;
        min-width: 3;
        height: 1;
        border: none;
        background: $primary-darken-2;
    }

    #month-label {
        width: 1fr;
        text-align: center;
        text-style: bold;
        color: $text;
    }

    #weekday-headers {
        height: 1;
        width: 100%;
    }

    .weekday-header {
        width: 1fr;
        text-align: center;
        color: $text-muted;
        text-style: bold;
    }

    #calendar-grid {
        width: 100%;
        height: auto;
    }

    .calendar-week {
        height: 2;
        width: 100%;
    }

    .calendar-day {
        width: 1fr;
        height: 2;
        min-width: 3;
        border: none;
        background: $surface;
        color: $text;
    }

    .calendar-day:hover {
        background: $primary-darken-2;
    }

    .calendar-day.other-month {
        color: $text-muted;
        background: $surface-darken-1;
    }

    .calendar-day.empty-day {
        background: $surface-darken-1;
    }

    .calendar-day.has-journal {
        background: $success-darken-2;
        color: $text;
        text-style: bold;
    }

    .calendar-day.has-journal:hover {
        background: $success;
    }

    .calendar-day.is-today {
        border: solid $warning;
    }

    #journal-viewer-section {
        height: 1fr;
    }

    #journal-viewer-header {
        height: 3;
        align: center middle;
        padding: 0 1;
    }

    #journal-viewer-title {
        width: 1fr;
        text-style: bold;
        color: $primary;
    }

    #regenerate-journal-btn {
        min-width: 16;
    }

    #extract-observations-btn {
        min-width: 16;
    }

    #journal-viewer {
        height: 1fr;
        padding: 1;
    }

    #lock-journal-btn {
        min-width: 4;
        max-width: 6;
    }

    #journal-content {
        width: 100%;
        height: auto;
    }

    #journal-content.journal-placeholder {
        color: $text-muted;
        text-style: italic;
    }

    /* Growth Panel Tab Bar */
    #growth-tab-bar {
        height: 3;
        padding: 0 1;
        align: left middle;
        border-bottom: solid $surface-darken-1;
    }

    .growth-tab {
        min-width: 12;
        height: 2;
        margin-right: 1;
    }

    .growth-tab.active-tab {
        text-style: bold;
    }

    /* Growth Section Visibility */
    .growth-section {
        height: 1fr;
    }

    .hidden-section {
        display: none;
    }

    /* Evaluations Section */
    #evaluations-section {
        height: 1fr;
    }

    #evaluations-header {
        height: 3;
        align: center middle;
        padding: 0 1;
    }

    #evaluations-title {
        width: 1fr;
        text-style: bold;
        color: $primary;
    }

    #evaluations-viewer {
        height: 1fr;
        padding: 1;
    }

    #evaluations-content {
        width: 100%;
        height: auto;
    }

    /* Pending Edges Section */
    #pending-section {
        height: 1fr;
    }

    #pending-header {
        height: 3;
        align: center middle;
        padding: 0 1;
    }

    #pending-title {
        width: 1fr;
        text-style: bold;
        color: $primary;
    }

    #pending-viewer {
        height: 1fr;
        padding: 1;
    }

    #pending-content {
        width: 100%;
        height: auto;
    }

    .pending-edge-item {
        margin-bottom: 1;
    }

    .pending-edge-actions {
        height: 3;
        align: left middle;
        margin-bottom: 1;
    }

    .edge-action-btn {
        min-width: 10;
        margin-right: 1;
    }

    .pending-edge-divider {
        margin-bottom: 1;
    }

    /* Questions Section */
    #questions-section {
        height: 1fr;
    }

    #questions-header {
        height: 3;
        align: center middle;
        padding: 0 1;
    }

    #questions-title {
        width: 1fr;
        text-style: bold;
        color: $primary;
    }

    #questions-viewer {
        height: 1fr;
        padding: 1;
    }

    #questions-content {
        width: 100%;
        height: auto;
    }

    /* Calendar Events Panel styling */
    #calendar-events-panel {
        height: 1fr;
        background: $surface;
    }

    #calendar-events-content {
        height: 1fr;
        width: 100%;
    }

    #calendar-events-header {
        height: 1;
        align: center middle;
        padding: 0 1;
    }

    #calendar-events-title {
        width: 1fr;
        text-style: bold;
        color: $primary;
    }

    #refresh-calendar-btn {
        width: 3;
        min-width: 3;
        height: 1;
        border: none;
    }

    #event-calendar-section {
        height: auto;
        max-height: 14;
        padding: 0 1;
        border-bottom: solid $surface-darken-1;
    }

    #event-calendar-widget {
        width: 100%;
        height: auto;
    }

    #event-calendar-nav {
        height: 1;
        width: 100%;
        align: center middle;
        margin-bottom: 1;
    }

    #event-month-label {
        width: 1fr;
        text-align: center;
        text-style: bold;
        color: $text;
    }

    #event-weekday-headers {
        height: 1;
        width: 100%;
    }

    #event-calendar-grid {
        width: 100%;
        height: auto;
    }

    .event-calendar-day.has-events {
        background: $primary-darken-2;
        color: $text;
        text-style: bold;
    }

    .event-calendar-day.has-events:hover {
        background: $primary;
    }

    #selected-date-section {
        height: 1fr;
        padding: 1;
    }

    #selected-date-header {
        text-style: bold;
        color: $secondary;
        margin-bottom: 1;
        padding-bottom: 1;
        border-bottom: solid $surface-darken-1;
    }

    #selected-date-events {
        height: 1fr;
    }

    .event-item {
        padding: 0 1;
        margin-bottom: 1;
        border-left: solid $primary;
    }

    .event-item:hover {
        background: $surface-darken-1;
    }

    .event-content {
        width: 100%;
    }

    .no-events {
        padding: 1;
        color: $text-muted;
        text-style: italic;
    }

    /* Tasks Panel styling */
    #tasks-panel {
        height: 1fr;
        background: $surface;
    }

    #tasks-content {
        height: 1fr;
        width: 100%;
    }

    #tasks-header {
        height: auto;
        padding: 0 1;
        background: $surface-darken-1;
    }

    #tasks-title {
        width: 1fr;
        text-style: bold;
        color: $secondary;
    }

    #refresh-tasks-btn {
        width: auto;
        min-width: 3;
    }

    #task-filter-input {
        margin: 1;
    }

    #tasks-list {
        height: 1fr;
        padding: 0 1;
    }

    .task-item {
        padding: 0 1;
        margin-bottom: 1;
        border-left: solid $warning;
    }

    .task-item:hover {
        background: $surface-darken-1;
    }

    .task-content {
        width: 100%;
    }

    .no-tasks {
        padding: 1;
        color: $text-muted;
        text-style: italic;
    }

    #tasks-summary {
        padding: 1;
        background: $surface-darken-1;
        border-top: solid $surface-darken-2;
    }
    """