"""Application palette with readable states and visible keyboard focus."""

CSS = b"""
window, dialog { background: #f3f5fa; color: #18243a; font-family: sans-serif; font-size: 14px; }
headerbar { background: #ffffff; color: #18243a; border-bottom: 1px solid #e3e8f0; box-shadow: none; }
headerbar .subtitle { color: #66758d; }
.sidebar { background: #142238; padding: 24px 12px 18px; }
.sidebar image { color: #bbc9dd; }
.sidebar label { color: #bbc9dd; }
.sidebar list { background: transparent; }
.sidebar row { border-radius: 10px; margin: 4px 0; padding: 13px 12px; }
.sidebar row:hover { background: #21334e; }
.sidebar row:selected { background: #2c4162; }
.sidebar row:selected label, .sidebar row:selected image { color: #ffffff; }
.brand { font-size: 19px; font-weight: bold; color: #ffffff; }
.brand-icon { background: #4265ed; color: white; padding: 10px; border-radius: 12px; }
.sidebar .sidebar-note { color: #a8bad2; font-size: 12px; }
.page-title { font-size: 29px; font-weight: bold; color: #18243a; }
.section-title { font-size: 21px; font-weight: bold; color: #18243a; }
.eyebrow { font-size: 11px; font-weight: bold; color: #64748b; letter-spacing: 1px; }
.muted { color: #596b82; font-size: 13px; }
.card { background: #ffffff; border: 1px solid #e1e7f0; border-radius: 14px; padding: 22px; }
.metric { background: #ffffff; border: 1px solid #e1e7f0; border-radius: 12px; padding: 12px 18px; }
.metric-value { font-size: 26px; font-weight: bold; color: #243855; }
.metric-icon { color: #4968cf; padding-right: 14px; }
.vpn-list { background: #ffffff; border: 1px solid #e1e7f0; border-radius: 14px; padding: 12px; }
.connection-icon { background: #eff2ff; color: #4c64d9; border-radius: 14px; padding: 12px; }
.status-pill { border-radius: 14px; padding: 7px 12px; font-size: 12px; font-weight: bold; background: #edf1f6; color: #506078; }
.status-pill.online { background: #e4f5ed; color: #126b47; }
.status-pill.pending { background: #fff3d9; color: #86520b; }
.status-pill.failed { background: #ffebeb; color: #9e3030; }
.connection-note { font-size: 13px; color: #596b82; }
.command-preview { font-family: monospace; font-size: 12px; color: #334c76; background: #edf1f9; padding: 12px; border-radius: 9px; }
.error-banner { background: #ffeded; color: #8d2c35; padding: 12px; border-radius: 9px; }
.success-banner { background: #e8f4ef; color: #196247; padding: 12px; border-radius: 9px; }
.notice { margin-top: 8px; }
button { background-image: none; background-color: #ffffff; color: #344562; border: 1px solid #d7dfea; border-radius: 8px; padding: 9px 13px; box-shadow: none; text-shadow: none; }
button:hover { background-color: #f0f3fa; border-color: #b3c0d6; }
button:disabled { background-color: #f6f7fa; color: #7c8799; border-color: #e3e7ee; }
button.suggested-action { background-color: #4763df; color: #ffffff; border-color: #4763df; font-weight: bold; }
button.suggested-action:hover { background-color: #3452ce; }
button.suggested-action:disabled { background-color: #d7deef; color: #61708f; border-color: #d7deef; }
button.destructive-action { background-color: #fff1f1; color: #a0353d; border-color: #efcbd0; }
button:focus, entry:focus { outline-color: #687ff0; outline-style: solid; outline-width: 2px; outline-offset: 2px; }
treeview { background: #ffffff; color: #243855; padding: 13px 8px; border-color: #edf1f6; }
treeview:selected { background: #eaf0ff; color: #2b46a6; }
treeview header button { background: #ffffff; border: none; border-radius: 0; font-size: 12px; color: #66758d; padding: 8px; }
entry { background: #ffffff; color: #243855; border: 1px solid #d7dfea; border-radius: 8px; padding: 9px; box-shadow: none; }
expander { color: #52647d; }
separator { background: #e8edf4; min-height: 1px; }
.option-row { background: #ffffff; border: 1px solid #e2e8f1; border-radius: 9px; padding: 12px; }
"""
