"""Connect-inspired navy/orange palette; project artwork remains independent."""

CSS = b"""
window, dialog { background: #101325; color: #edf0f7; font-family: Inter, sans-serif; font-size: 14px; }
headerbar { background: #101325; color: #edf0f7; border-bottom: 1px solid #2b3148; box-shadow: none; }
headerbar .subtitle { color: #aeb8ce; }
.sidebar { background: #0c1020; border-right: 1px solid #2b3148; padding: 24px 12px 18px; }
.sidebar image, .sidebar label { color: #b7c0d5; }
.sidebar list { background: transparent; }
.sidebar row { border-radius: 8px; border-left: 3px solid transparent; margin: 4px 0; padding: 13px 10px; }
.sidebar row:hover { background: #1d243b; }
.sidebar row:selected { background: #2c2630; border-left-color: #ed7f22; }
.sidebar row:selected label, .sidebar row:selected image { color: #ffb574; }
.sidebar .brand { font-size: 18px; font-weight: bold; color: #ffffff; }
.sidebar .sidebar-note { color: #aeb8ce; font-size: 12px; }
.sidebar .brand-caption { font-size: 10px; color: #b7c0d5; letter-spacing: 1px; }
.page-title { font-size: 29px; font-weight: bold; color: #ffffff; }
.section-title { font-size: 21px; font-weight: bold; color: #ffffff; }
.eyebrow { font-size: 11px; font-weight: bold; color: #b7c0d5; letter-spacing: 1px; }
.muted { color: #b7c0d5; font-size: 13px; }
.card { background: #191e32; border: 1px solid #3a435e; border-radius: 16px; padding: 22px; }
.card.connected { border-color: #39b78f; }
.metric { background: #191e32; border: 1px solid #30394f; border-radius: 12px; padding: 12px 18px; }
.metric-value { font-size: 26px; font-weight: bold; color: #ffffff; }
.metric-icon { color: #ed7f22; padding-right: 14px; }
.vpn-list { background: #191e32; border: 1px solid #30394f; border-radius: 16px; padding: 12px; }
.connection-icon { background: #252d47; border-radius: 12px; padding: 10px; }
.status-pill { border-radius: 14px; padding: 7px 12px; font-size: 12px; font-weight: bold; background: #2e354c; color: #d0d8e9; }
.status-pill.online { background: #163c34; color: #8ce6c3; }
.status-pill.pending { background: #493524; color: #ffca8d; }
.status-pill.failed { background: #4b2933; color: #ffbec8; }
.connection-note { font-size: 13px; color: #b7c0d5; }
.command-preview { font-family: monospace; font-size: 12px; color: #d4ddf1; background: #232b43; padding: 12px; border-radius: 9px; }
.error-banner { background: #4b2933; color: #ffbec8; padding: 12px; border-radius: 9px; }
.success-banner { background: #163c34; color: #8ce6c3; padding: 12px; border-radius: 9px; }
.notice { margin-top: 8px; }
button { background-image: none; background-color: #29324b; color: #edf0f7; border: 1px solid #4b5774; border-radius: 8px; padding: 9px 13px; box-shadow: none; text-shadow: none; }
button:hover { background-color: #36425e; border-color: #8392b1; }
button:disabled { background-color: #20273b; color: #8b97b0; border-color: #36405a; }
button.suggested-action { background-color: #ed7f22; color: #162146; border-color: #ed7f22; font-weight: bold; }
button.suggested-action:hover { background-color: #ffa04e; border-color: #ffa04e; }
button.suggested-action:disabled { background-color: #443528; color: #bca58e; border-color: #594633; }
button.connection-active { background-color: #3d4966; color: #ffffff; border-color: #586887; }
button.connection-active:hover { background-color: #4b5a7b; border-color: #8294b8; }
button.destructive-action { background-color: #4b2933; color: #ffbec8; border-color: #9c5668; }
button:focus, entry:focus { outline-color: #ffb574; outline-style: solid; outline-width: 2px; outline-offset: 2px; }
treeview { background: #191e32; color: #edf0f7; padding: 13px 8px; border-color: #30394f; }
treeview:selected { background: #3b2d25; color: #ffbd85; }
treeview header button { background: #191e32; color: #b7c0d5; border: none; border-radius: 0; font-size: 12px; padding: 8px; }
entry { background: #141a2d; color: #edf0f7; border: 1px solid #4b5774; border-radius: 8px; padding: 9px; box-shadow: none; }
entry selection { background: #ed7f22; color: #162146; }
checkbutton check:checked, radiobutton radio:checked { background-image: none; background-color: #ed7f22; border-color: #ed7f22; color: #162146; }
expander { color: #c4cee4; }
separator { background: #353e57; min-height: 1px; }
.option-row { background: #191e32; border: 1px solid #3a435e; border-radius: 9px; padding: 12px; }
popover, menu { background: #191e32; color: #edf0f7; }
textview text { background: #141a2d; color: #edf0f7; }
"""

# Both palettes share sizing and layout. Semantic replacements keep every
# surface (including dialogs and generated command forms) in the chosen mode.
LIGHT_COLORS = {
    "#101325": "#f5f6fa",
    "#edf0f7": "#243047",
    "#2b3148": "#dce1eb",
    "#aeb8ce": "#56627a",
    "#0c1020": "#eef1f7",
    "#b7c0d5": "#53617a",
    "#1d243b": "#e1e6f0",
    "#2c2630": "#fff0e2",
    "#ffb574": "#934000",
    "#ffffff": "#17243b",
    "#191e32": "#ffffff",
    "#3a435e": "#d7deeb",
    "#39b78f": "#138364",
    "#30394f": "#dce2ee",
    "#252d47": "#eef1f8",
    "#2e354c": "#edf0f5",
    "#d0d8e9": "#526078",
    "#163c34": "#e1f5ec",
    "#8ce6c3": "#146448",
    "#493524": "#fff0da",
    "#ffca8d": "#80500a",
    "#4b2933": "#fbe8ed",
    "#ffbec8": "#9a2942",
    "#d4ddf1": "#354661",
    "#232b43": "#edf1f8",
    "#29324b": "#f1f4fa",
    "#4b5774": "#bac5d8",
    "#36425e": "#e6ebf5",
    "#8392b1": "#8695b0",
    "#20273b": "#f3f4f7",
    "#8b97b0": "#757f90",
    "#36405a": "#dce1e9",
    "#443528": "#f5e6d9",
    "#bca58e": "#8c7664",
    "#594633": "#e6cdb8",
    "#3d4966": "#e5eaf4",
    "#586887": "#b2bfd3",
    "#4b5a7b": "#d9e1ef",
    "#8294b8": "#899bb9",
    "#9c5668": "#d79aaa",
    "#3b2d25": "#fff0e2",
    "#ffbd85": "#934000",
    "#141a2d": "#ffffff",
    "#c4cee4": "#53617a",
    "#353e57": "#dce2ee",
}


def css_for(dark):
    import re

    css = CSS.decode()
    if not dark:
        css = re.sub(
            r"#[0-9a-f]{6}", lambda match: LIGHT_COLORS.get(match[0], match[0]), css
        )
    css += "\n.traffic-value { font-size: 20px; font-weight: bold; }\n"
    css += ".traffic-received { color: " + ("#70dfc0" if dark else "#08785f") + "; }\n"
    css += ".traffic-sent { color: " + ("#ffb574" if dark else "#a64900") + "; }\n"
    return css.encode()
