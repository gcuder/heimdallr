"""CSS for the heimdallr TUI."""

HELP_MODAL_CSS = """
HelpModal {
    align: center middle;
    background: rgba(0, 0, 0, 0.6);
}

HelpModal > Vertical {
    width: 80;
    height: auto;
    max-height: 90%;
    background: $surface;
    border: thick $primary 80%;
    padding: 1 2;
}

HelpModal #title {
    text-align: center;
    text-style: bold;
    width: 100%;
    margin-bottom: 1;
}

HelpModal .help-section {
    text-style: bold;
    color: $accent;
    margin-top: 1;
}

HelpModal .help-row {
    height: 1;
}

HelpModal .help-key {
    width: 18;
    color: #facc15;
    text-style: bold;
}

HelpModal .help-desc {
    width: 1fr;
    color: $text;
}

HelpModal #footer {
    text-align: center;
    color: $text-muted;
    margin-top: 1;
}
"""

TRANSFER_MODAL_CSS = """
TransferModal {
    align: center middle;
    background: rgba(0, 0, 0, 0.6);
}

TransferModal > Vertical {
    width: 70;
    height: auto;
    background: $surface;
    border: thick $primary 80%;
    padding: 1 2;
}

TransferModal #title {
    text-align: center;
    text-style: bold;
    width: 100%;
    margin-bottom: 1;
}

TransferModal .section-label {
    text-style: bold;
    margin-top: 1;
}

TransferModal RadioSet {
    border: none;
    background: transparent;
    padding: 0;
    height: auto;
}

TransferModal RadioButton {
    background: transparent;
}

TransferModal #estimate {
    color: $text-muted;
    margin-top: 1;
    text-align: center;
}

TransferModal #buttons {
    width: 100%;
    height: auto;
    align: center middle;
    margin-top: 1;
}

TransferModal Button {
    margin: 0 1;
    min-width: 14;
}

TransferModal Button:focus {
    background: $accent;
}
"""

SETTINGS_MODAL_CSS = """
SettingsModal {
    align: center middle;
    background: rgba(0, 0, 0, 0.6);
}

#settings-root {
    width: 90%;
    height: 85%;
    max-width: 120;
    max-height: 40;
    background: $surface;
    border: thick $primary 80%;
    padding: 1 2;
}

#settings-title {
    text-align: center;
    text-style: bold;
    width: 100%;
    margin-bottom: 1;
    color: $accent;
}

#settings-body {
    height: 1fr;
    width: 100%;
}

#settings-nav {
    width: 22;
    height: 100%;
    margin-right: 1;
}

#section-list {
    height: 100%;
    background: transparent;
    border: solid $primary-background-lighten-2;
}

#section-list > ListItem {
    padding: 0 1;
    background: transparent;
}

#section-list > ListItem:hover {
    background: $accent 15%;
}

#section-list > ListItem.--highlight {
    background: $accent 25%;
    color: $accent;
    text-style: bold;
}

#settings-pane {
    width: 1fr;
    height: 100%;
    padding: 0 2;
}

.section-panel {
    height: auto;
    width: 100%;
}

.section-panel.hidden {
    display: none;
}

.section-heading {
    text-style: bold;
    color: $accent;
    margin-bottom: 1;
}

.setting-row {
    height: auto;
    margin-bottom: 1;
    align: left middle;
}

.setting-label {
    width: 28;
    color: $text-muted;
    padding: 0 1 0 0;
    content-align: left middle;
}

.setting-help {
    color: $text-muted;
    margin-bottom: 1;
    padding: 0 0 0 28;
}

.settings-textarea {
    height: 6;
    width: 100%;
    border: solid $primary-background-lighten-2;
    background: $surface;
    margin-bottom: 1;
}

.settings-input-narrow {
    width: 12;
    border: solid $primary-background-lighten-2;
    background: $surface;
}

.diag-value {
    width: 1fr;
    color: $text;
}

.key-current {
    width: 16;
    color: #facc15;
    text-style: bold;
    content-align: left middle;
}

.capture-btn {
    margin: 0 1;
    min-width: 10;
}

.reset-section-btn {
    margin-top: 1;
    background: $primary-background-lighten-1;
}

#settings-hint {
    text-align: center;
    color: $text-muted;
    margin-top: 1;
    width: 100%;
}

SettingsModal Switch {
    background: $primary-background-lighten-1;
}

SettingsModal Switch.-on {
    background: $accent 70%;
}

SettingsModal Select {
    width: 32;
    background: $primary-background-lighten-1;
}
"""

APP_CSS = """
Screen {
    layout: vertical;
    width: 100%;
    background: $surface;
}

#title-bar {
    height: 4;
    width: 100%;
    padding: 0 1;
    background: $surface;
}

LogoWidget {
    width: 10;
    height: 4;
    margin-right: 1;
}

#logo-img {
    width: 10;
    height: 4;
}

#title-text {
    width: 1fr;
    height: 4;
}

#app-title {
    width: 1fr;
    color: $accent;
    text-style: bold;
}

#session-count {
    color: $text-muted;
    width: 1fr;
}

#search-row {
    height: 3;
    width: 100%;
    padding: 0 1;
}

#search-box {
    width: 100%;
    height: 3;
    border: solid $primary-background-lighten-2;
    background: $surface;
    padding: 0 1;
}

#search-box:focus-within {
    border: solid $accent;
}

#search-icon {
    width: 3;
    color: $text-muted;
    content-align: center middle;
}

#search-input {
    width: 1fr;
    border: none;
    background: transparent;
}

#search-input:focus {
    border: none;
}

#filter-container {
    height: 1;
    width: 100%;
    padding: 0 1;
    margin-bottom: 1;
}

.filter-btn {
    width: auto;
    height: 1;
    margin: 0 1 0 0;
    padding: 0 1;
    border: none;
    background: transparent;
    color: $text-muted;
}

.filter-btn:hover {
    color: $text;
}

.filter-btn.-active {
    background: $accent 20%;
    color: $accent;
}

.filter-label {
    height: 1;
}

.filter-btn.-active .filter-label {
    text-style: bold;
}

.filter-divider {
    width: auto;
    color: $text-muted;
    margin: 0 1;
}

#filter-claude { color: #E87B35; }
#filter-claude.-active { background: #E87B35 20%; color: #E87B35; }
#filter-codex { color: #00A67E; }
#filter-codex.-active { background: #00A67E 20%; color: #00A67E; }

#filter-running.-active { background: #4ade80 20%; color: #4ade80; }
#filter-recent.-active { background: #facc15 20%; color: #facc15; }

#filter-mem { color: $text-muted; }
#filter-mem.-active { background: #a78bfa 20%; color: #a78bfa; }

#main-container {
    height: 1fr;
    width: 100%;
}

#results-container {
    height: 12;
    width: 100%;
    overflow-x: hidden;
}

#results-table {
    height: 100%;
    width: 100%;
    overflow-x: hidden;
}

DataTable {
    background: transparent;
    overflow-x: hidden;
}

DataTable > .datatable--header {
    text-style: bold;
    color: $text;
}

DataTable > .datatable--cursor {
    background: $accent 30%;
}

DataTable > .datatable--hover {
    background: $surface-lighten-1;
}

#preview-container {
    height: 1fr;
    border-top: solid $accent 50%;
    background: $surface;
    padding: 0 1;
}

#preview-container.hidden {
    display: none;
}

#preview {
    height: auto;
}

#status-bar {
    height: 1;
    width: 100%;
    padding: 0 1;
    background: $surface;
    color: $text-muted;
}

Footer {
    background: $primary-background;
}

Footer > .footer--key {
    background: $surface;
    color: $text;
}

Footer > .footer--description {
    color: $text-muted;
}

#query-time {
    width: auto;
    padding: 0 1;
    color: $text-muted;
}
"""
