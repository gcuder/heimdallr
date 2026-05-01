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
