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

    #doc-viewer-container {
        width: 2fr;
        height: 1fr;
    }

    #doc-viewer-actions {
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
    }

    #doc-viewer-actions.hidden {
        display: none;
    }

    #doc-viewer {
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

    /* Split view for thinking/response columns */
    .message-split-view {
        width: 100%;
        height: auto;
        padding: 0 0 0 2;
    }

    .thinking-column {
        width: 1fr;
        height: auto;
        border-right: solid $surface-lighten-1;
        padding-right: 1;
        margin-right: 1;
    }

    .thinking-header {
        margin-bottom: 1;
        color: $text-muted;
    }

    .thinking-text {
        width: 100%;
        color: $text-muted;
        text-style: italic;
    }

    .thinking-code-block {
        height: auto;
        margin: 1 0;
        background: $surface-darken-3;
        border: solid $surface-darken-1;
        color: $text-muted;
    }

    .response-column {
        width: 1fr;
        height: auto;
    }

    .response-header {
        margin-bottom: 1;
        color: $text-muted;
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

    /* File dialog modals (NewFileScreen, NewFolderScreen, RenameFileScreen) */
    NewFileScreen, NewFolderScreen, RenameFileScreen {
        align: center middle;
    }

    #file-dialog {
        width: 60;
        height: auto;
        background: $panel;
        border: thick $primary;
        padding: 1 2;
    }

    #file-dialog-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    .dialog-path {
        color: $text-muted;
        text-align: center;
        margin-bottom: 1;
    }

    #file-name-input, #folder-name-input, #rename-input {
        width: 100%;
        margin-bottom: 1;
    }

    #file-dialog-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #file-dialog-buttons Button {
        margin: 0 1;
    }

    /* Delete file/folder confirmation dialog */
    DeleteConfirmScreen {
        align: center middle;
    }

    #delete-file-dialog {
        width: 60;
        height: auto;
        background: $panel;
        border: thick $error;
        padding: 1 2;
    }

    #delete-dialog-title {
        text-align: center;
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }

    #delete-message {
        text-align: center;
        margin-bottom: 1;
    }

    #delete-dialog-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #delete-dialog-buttons Button {
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

    /* Solo Reflection Panel styling */
    #reflection-panel {
        height: 1fr;
        background: $surface;
    }

    #reflection-layout {
        height: 1fr;
        width: 100%;
    }

    #reflection-sidebar {
        width: 30%;
        min-width: 25;
        max-width: 40;
        height: 1fr;
        border-right: solid $surface-darken-1;
        padding: 1;
    }

    #reflection-stats {
        height: auto;
        margin-bottom: 1;
        padding-bottom: 1;
        border-bottom: solid $surface-darken-1;
    }

    #reflection-header {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #stats-display {
        height: auto;
    }

    #new-session-form {
        height: auto;
        margin-bottom: 1;
        padding-bottom: 1;
        border-bottom: solid $surface-darken-1;
    }

    .section-label {
        text-style: bold;
        color: $text-muted;
        margin-bottom: 1;
    }

    #duration-row {
        height: 3;
        align: left middle;
        margin-bottom: 1;
    }

    .form-label {
        width: auto;
        margin-right: 1;
        color: $text-muted;
    }

    .form-suffix {
        width: auto;
        margin-left: 1;
        color: $text-muted;
    }

    #duration-input {
        width: 6;
    }

    #theme-input {
        width: 100%;
        margin-bottom: 1;
    }

    #start-session-btn {
        width: 100%;
        margin-bottom: 1;
    }

    #stop-session-btn {
        width: 100%;
    }

    #sessions-list-container {
        height: 1fr;
    }

    #sessions-scroll {
        height: 1fr;
    }

    #sessions-list {
        height: auto;
        width: 100%;
    }

    .session-btn {
        width: 100%;
        min-width: 20;
        height: auto;
        min-height: 2;
        margin-bottom: 1;
        text-align: left;
        background: $surface-darken-1;
        border: none;
    }

    .session-btn:hover {
        background: $primary-darken-2;
    }

    .session-btn:focus {
        background: $primary-darken-1;
    }

    .empty-sessions {
        color: $text-muted;
        text-style: italic;
    }

    #reflection-detail {
        width: 1fr;
        height: 1fr;
        padding: 1;
    }

    #session-detail-content {
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

    /* ─────────────────────────────────────────────────────────────────────────
       Daedalus Panels (Sessions, Files, Git)
       ───────────────────────────────────────────────────────────────────────── */

    #sessions-panel {
        height: 1fr;
        padding: 1;
        background: $surface;
    }

    #sessions-panel .panel-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $primary;
    }

    #sessions-panel #sessions-list {
        height: 1fr;
        border: solid $surface-darken-1;
        padding: 0 1;
    }

    #sessions-panel .session-controls {
        height: auto;
        margin-top: 1;
        layout: horizontal;
        align: center middle;
    }

    #sessions-panel .control-btn {
        margin: 0 1;
    }

    #files-panel {
        height: 1fr;
        padding: 1;
        background: $surface;
    }

    #files-panel .panel-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $primary;
    }

    #files-panel .file-search-input {
        width: 100%;
        margin-bottom: 1;
    }

    #files-panel .file-search-results {
        height: 1fr;
        border: solid $surface-darken-1;
        padding: 0 1;
    }

    #files-panel .file-search-results.hidden {
        display: none;
    }

    #files-panel #files-content.hidden {
        display: none;
    }

    #files-panel #files-tree {
        height: 1fr;
        border: solid $surface-darken-1;
        padding: 0 1;
    }

    #files-panel #files-content {
        height: 1fr;
    }

    #files-panel #files-tree {
        height: 40%;
        min-height: 5;
    }

    #files-panel .file-info {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-style: italic;
    }

    #files-panel #file-preview {
        height: 1fr;
        border: solid $surface-darken-1;
        padding: 0;
        margin-top: 1;
    }

    #files-panel #file-preview-content {
        padding: 1;
    }

    #files-panel .preview-placeholder {
        color: $text-muted;
        text-style: italic;
        text-align: center;
        padding: 2;
    }

    #files-panel .file-controls {
        height: auto;
        margin-top: 1;
        layout: horizontal;
        align: center middle;
    }

    #git-panel {
        height: 1fr;
        padding: 1;
        background: $surface;
    }

    #git-panel .panel-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $primary;
    }

    #git-panel #git-content {
        height: 1fr;
        border: solid $surface-darken-1;
        padding: 1;
    }

    #git-panel .git-controls {
        height: auto;
        margin-top: 1;
        layout: horizontal;
        align: center middle;
    }

    #git-panel .control-btn {
        margin: 0 1;
    }

    #git-panel .git-commit-section {
        height: auto;
        margin-top: 1;
        layout: horizontal;
        align: center middle;
    }

    #git-panel .commit-input {
        width: 1fr;
        margin-right: 1;
    }

    #git-panel #commit-btn {
        min-width: 10;
    }

    /* ─────────────────────────────────────────────────────────────────────────
       Build Panel - Build/Test Commands
       ───────────────────────────────────────────────────────────────────────── */

    #build-panel {
        height: 1fr;
        padding: 1;
        background: $surface;
    }

    #build-panel .panel-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $primary;
    }

    #build-panel .build-project-type {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    #build-panel #build-commands-list {
        height: 1fr;
        border: solid $surface-darken-1;
        padding: 0 1;
    }

    #build-panel .build-controls {
        height: auto;
        margin-top: 1;
        layout: horizontal;
        align: center middle;
    }

    #build-panel .control-btn {
        margin: 0 1;
    }

    /* ─────────────────────────────────────────────────────────────────────────
       Diff Viewer Modal
       ───────────────────────────────────────────────────────────────────────── */

    #diff-viewer-dialog {
        width: 90%;
        height: 85%;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }

    #diff-viewer-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #diff-viewer-content {
        height: 1fr;
        layout: horizontal;
    }

    #diff-file-list-container {
        width: 25%;
        height: 1fr;
        border-right: solid $surface-darken-1;
        padding-right: 1;
    }

    #diff-file-list-container .section-label {
        text-style: bold;
        color: $secondary;
        margin-bottom: 1;
    }

    #diff-file-list {
        height: 1fr;
        margin-bottom: 1;
    }

    #diff-file-controls {
        height: auto;
        align: center middle;
    }

    #diff-file-controls Button {
        margin: 0 1;
    }

    #diff-content-container {
        width: 75%;
        height: 1fr;
        padding-left: 1;
    }

    #diff-content {
        width: 100%;
    }

    #diff-viewer-buttons {
        height: auto;
        margin-top: 1;
        align: center middle;
    }

    /* ─────────────────────────────────────────────────────────────────────────
       Roadmap Panel
       ───────────────────────────────────────────────────────────────────────── */

    #roadmap-panel {
        height: 1fr;
        padding: 1;
        background: $surface;
    }

    #roadmap-content {
        height: 1fr;
    }

    #roadmap-header {
        height: auto;
        margin-bottom: 1;
    }

    #roadmap-title {
        text-style: bold;
        color: $primary;
    }

    #roadmap-scope-label {
        margin-left: 1;
        width: auto;
    }

    #toggle-all-projects-btn {
        margin-left: 1;
        min-width: 16;
    }

    #refresh-roadmap-btn {
        dock: right;
    }

    #roadmap-filters {
        height: auto;
        margin-bottom: 1;
    }

    #roadmap-filters .filter-btn {
        margin-right: 1;
        min-width: 8;
    }

    #roadmap-list {
        height: 40%;
        min-height: 5;
        border: solid $surface-darken-1;
        padding: 0 1;
    }

    .roadmap-item {
        padding: 0;
        margin-bottom: 1;
        border-bottom: dashed $surface-darken-2;
    }

    .roadmap-item:hover {
        background: $surface-lighten-1;
    }

    #roadmap-detail {
        height: 1fr;
        border: solid $surface-darken-1;
        padding: 1;
        margin-top: 1;
    }

    #detail-content {
        height: 1fr;
        overflow-y: auto;
    }

    #roadmap-actions {
        height: auto;
        margin-top: 1;
        layout: horizontal;
        align: center middle;
    }

    #roadmap-actions Button {
        margin: 0 1;
    }

    #roadmap-actions.hidden {
        display: none;
    }

    /* Milestone sections */
    .milestone-section {
        margin-bottom: 1;
        height: auto;
    }

    .milestone-section Collapsible {
        border: solid $surface-darken-1;
        padding: 0;
        height: auto;
    }

    .milestone-section Collapsible > Contents {
        height: auto;
    }

    .milestone-section.completed Collapsible {
        border: solid $success-darken-2;
    }

    .milestone-section.completed CollapsibleTitle {
        color: $success;
    }

    .milestone-section.unassigned Collapsible {
        border: dashed $surface-darken-2;
    }

    .milestone-section.unassigned CollapsibleTitle {
        color: $text-muted;
    }

    #toggle-milestone-group-btn {
        margin-left: 1;
    }

    /* Expandable items with children */
    .expandable-item {
        padding: 0;
        margin-bottom: 0;
        height: auto;
    }

    .expandable-collapsible {
        padding: 0;
        margin: 0;
        height: auto;
    }

    .expandable-collapsible > CollapsibleTitle {
        padding: 0 1;
    }

    .expandable-collapsible > Contents {
        padding-left: 2;
        height: auto;
    }

    .expandable-item .parent-status {
        color: $text-muted;
        padding-left: 2;
    }

    .expandable-item .child-item {
        margin-bottom: 0;
        border-bottom: none;
        padding-left: 2;
    }

    /* ─────────────────────────────────────────────────────────────────────────
       Settings Screen
       ───────────────────────────────────────────────────────────────────────── */

    SettingsScreen {
        align: center middle;
    }

    #settings-dialog {
        width: 70;
        height: auto;
        max-height: 80%;
        background: $panel;
        border: thick $primary;
        padding: 1 2;
    }

    #settings-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #settings-tabs {
        height: auto;
        max-height: 50;
    }

    #settings-tabs TabPane {
        padding: 1;
    }

    #appearance-scroll, #keybindings-scroll, #audio-scroll, #llm-scroll, #behavior-scroll {
        height: auto;
        max-height: 40;
    }

    .setting-label {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    .setting-hint {
        color: $text-muted;
        text-style: italic;
        margin-top: 1;
        margin-bottom: 1;
    }

    .setting-divider {
        margin: 1 0;
    }

    .setting-row {
        height: 3;
        width: 100%;
        align: left middle;
        margin-bottom: 1;
    }

    .setting-name {
        width: 1fr;
    }

    .setting-row Switch {
        width: auto;
    }

    .shortcuts-list {
        padding: 1;
        background: $surface-darken-1;
        margin-top: 1;
    }

    #settings-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #settings-buttons Button {
        margin: 0 1;
    }

    #theme-select, #llm-provider-select {
        width: 100%;
        margin-bottom: 1;
    }

    /* Settings button in sidebar */
    #settings-btn {
        width: 100%;
        margin-top: 1;
    }

    /* ─────────────────────────────────────────────────────────────────────────
       Session Quick Switcher
       ───────────────────────────────────────────────────────────────────────── */

    SessionSwitcherScreen {
        align: center middle;
    }

    #session-switcher {
        width: 70;
        height: 35;
        background: $panel;
        border: thick $primary;
        padding: 1 2;
    }

    #switcher-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #session-search-input {
        width: 100%;
        margin-bottom: 1;
    }

    #session-list {
        height: 1fr;
        border: solid $surface-darken-1;
        padding: 0 1;
    }

    .session-item-content {
        height: auto;
        padding: 0;
    }

    .session-name {
        text-style: bold;
        color: $text;
    }

    .session-path {
        color: $text-muted;
        text-style: italic;
    }

    .current-session {
        background: $primary-darken-2;
    }

    .current-session .session-name {
        color: $primary;
    }

    .no-sessions {
        color: $text-muted;
        text-style: italic;
        text-align: center;
        padding: 2;
    }

    #switcher-hints {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }

    /* ─────────────────────────────────────────────────────────────────────────
       New Session Dialog
       ───────────────────────────────────────────────────────────────────────── */

    NewSessionScreen {
        align: center middle;
    }

    #new-session-dialog {
        width: 60;
        height: auto;
        background: $panel;
        border: thick $primary;
        padding: 1 2;
    }

    #new-session-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #new-session-dialog .dialog-path {
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }

    #new-session-dialog .input-label {
        margin-bottom: 0;
    }

    #session-name-input {
        width: 100%;
        margin-bottom: 0;
    }

    #new-session-dialog .input-hint {
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }

    #new-session-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #new-session-buttons Button {
        margin: 0 1;
    }

    /* ─────────────────────────────────────────────────────────────────────────
       Project Quick Switcher
       ───────────────────────────────────────────────────────────────────────── */

    ProjectSwitcherScreen {
        align: center middle;
    }

    #project-switcher {
        width: 70;
        height: 40;
        background: $panel;
        border: thick $secondary;
        padding: 1 2;
    }

    #project-switcher-title {
        text-align: center;
        text-style: bold;
        color: $secondary;
        margin-bottom: 1;
    }

    #project-search-input {
        width: 100%;
        margin-bottom: 1;
    }

    #project-list {
        height: 1fr;
        border: solid $surface-darken-1;
        padding: 0 1;
    }

    .project-item-content {
        height: auto;
        padding: 0;
    }

    .project-item-header {
        height: auto;
    }

    .project-indicator {
        width: 2;
        color: $secondary;
    }

    .project-name {
        text-style: bold;
        color: $text;
    }

    .project-path {
        color: $text-muted;
        text-style: italic;
        padding-left: 2;
    }

    .current-project {
        background: $secondary-darken-2;
    }

    .current-project .project-name {
        color: $secondary;
    }

    .no-projects {
        color: $text-muted;
        text-style: italic;
        text-align: center;
        padding: 2;
    }

    #project-switcher-options {
        height: auto;
        margin-top: 1;
        align: center middle;
    }

    #spawn-session-checkbox {
        margin-right: 1;
    }

    #project-switcher-hints {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }

    /* ─────────────────────────────────────────────────────────────────────────
       Command Palette
       ───────────────────────────────────────────────────────────────────────── */

    CommandPaletteScreen {
        align: center middle;
    }

    #command-palette {
        width: 70;
        height: 45;
        background: $panel;
        border: thick $warning;
        padding: 1 2;
    }

    #palette-title {
        text-align: center;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }

    #command-search-input {
        width: 100%;
        margin-bottom: 1;
    }

    #command-list {
        height: 1fr;
        border: solid $surface-darken-1;
        padding: 0 1;
    }

    .command-item-content {
        height: auto;
        padding: 0;
    }

    .command-item-header {
        height: auto;
        width: 100%;
    }

    .command-name {
        text-style: bold;
        color: $text;
        width: 1fr;
    }

    .command-keybinding {
        color: $warning;
        text-style: italic;
        width: auto;
    }

    .command-description {
        color: $text-muted;
        text-style: italic;
    }

    .no-commands {
        color: $text-muted;
        text-style: italic;
        text-align: center;
        padding: 2;
    }

    #palette-hints {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }

    /* ─────────────────────────────────────────────────────────────────────────
       Terminal History Search
       ───────────────────────────────────────────────────────────────────────── */

    #terminal-search {
        width: 90%;
        height: 80%;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }

    #terminal-search-title {
        text-style: bold;
        color: $primary;
        text-align: center;
        margin-bottom: 1;
    }

    #terminal-search-input {
        width: 100%;
        margin-bottom: 1;
    }

    #terminal-search-status {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    #terminal-search-list {
        height: 1fr;
        border: solid $surface-darken-1;
        padding: 0 1;
    }

    #terminal-search-list .no-results {
        color: $text-muted;
        text-style: italic;
        text-align: center;
        padding: 2;
    }

    #terminal-search-hints {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }

    /* Daedalus Conversations Panel styling */
    #daedalus-convs-panel {
        height: 1fr;
        background: $surface;
    }

    #daedalus-convs-layout {
        height: 1fr;
        width: 100%;
    }

    #daedalus-convs-sidebar {
        width: 30%;
        min-width: 25;
        max-width: 40;
        height: 1fr;
        border-right: solid $surface-darken-1;
        padding: 1;
    }

    #daedalus-convs-header {
        text-style: bold;
        color: $secondary;
        margin-bottom: 0;
    }

    #daedalus-convs-subtitle {
        margin-bottom: 1;
    }

    #daedalus-convs-scroll {
        height: 1fr;
    }

    #daedalus-convs-list {
        height: auto;
    }

    .daedalus-conv-btn {
        width: 100%;
        height: auto;
        min-height: 3;
        margin-bottom: 1;
        text-align: left;
        padding: 0 1;
    }

    .daedalus-conv-btn:hover {
        background: $surface-lighten-1;
    }

    #daedalus-messages-scroll {
        height: 1fr;
        padding: 1;
    }

    #daedalus-messages-content {
        width: 100%;
    }

    .empty-convs {
        text-style: italic;
        padding: 2;
    }

    /* Interview panel styling */
    #interview-panel {
        height: 1fr;
        background: $surface;
    }

    #interview-content {
        height: 1fr;
        width: 100%;
    }

    #interview-header {
        height: auto;
        dock: top;
        padding: 0 1;
        margin-bottom: 1;
    }

    #interview-header Button {
        margin-right: 1;
        min-width: 12;
    }

    .active-view-btn {
        background: $primary;
    }

    #overview-section, #compare-section {
        height: 1fr;
        width: 100%;
    }

    .hidden-section {
        display: none;
    }

    #overview-layout {
        height: 1fr;
        width: 100%;
    }

    .interview-list-pane {
        width: 30%;
        min-width: 20;
        max-width: 40;
        border-right: solid $secondary;
        padding-right: 1;
    }

    .interview-detail-pane {
        width: 1fr;
        padding-left: 1;
    }

    .interview-list-header {
        text-style: bold;
        background: $primary;
        padding: 0 1;
        margin-bottom: 1;
    }

    #protocol-list {
        height: 1fr;
        border: none;
    }

    #protocol-detail-scroll {
        height: 1fr;
    }

    #protocol-detail {
        padding: 1;
    }

    #compare-controls {
        height: auto;
        dock: top;
        padding: 1;
        background: $surface-darken-1;
        margin-bottom: 1;
    }

    #compare-controls Label {
        margin-right: 1;
        padding-top: 1;
    }

    #prompt-select {
        width: 40;
        margin-right: 1;
    }

    #compare-viewer {
        height: 1fr;
        padding: 1;
    }

    #compare-content {
        width: 100%;
    }
    """