"""UI and field-map palettes for Gravity Lab 3D."""

THEMES = {
    "Midnight Dark": {
        "app_bg": "#0b1120", "panel_bg": "#111b2d", "plot_bg": "#0b1422",
        "text": "#e2e8f0", "muted": "#94a3b8", "accent": "#9fd8ff",
        "entry_bg": "#172338", "border": "#29364c", "button_bg": "#22334d",
        "button_active": "#315073", "grid": "#8da2bd", "field_stops": ["#0b1026", "#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"],
    },
    "Light Minimal": {
        "app_bg": "#eef2f7", "panel_bg": "#ffffff", "plot_bg": "#f8fafc",
        "text": "#172033", "muted": "#526176", "accent": "#0369a1",
        "entry_bg": "#ffffff", "border": "#cbd5e1", "button_bg": "#e2e8f0",
        "button_active": "#cbd5e1", "grid": "#64748b", "field_stops": ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"],
    },
    "Ocean Blue": {
        "app_bg": "#061923", "panel_bg": "#0c2a3a", "plot_bg": "#082331",
        "text": "#d9faff", "muted": "#83b7c6", "accent": "#39c6d9",
        "entry_bg": "#123648", "border": "#205366", "button_bg": "#13475b",
        "button_active": "#17657d", "grid": "#6ab7c8", "field_stops": ["#00204c", "#155f83", "#2f9c95", "#a4d65e", "#fff3a6"],
    },
    "Solarized Light": {
        "app_bg": "#fdf6e3", "panel_bg": "#eee8d5", "plot_bg": "#fdf6e3",
        "text": "#586e75", "muted": "#657b83", "accent": "#268bd2",
        "entry_bg": "#fffdf5", "border": "#d3cbb7", "button_bg": "#e3dcc8",
        "button_active": "#d6ceb8", "grid": "#93a1a1", "field_stops": ["#002b36", "#268bd2", "#2aa198", "#b58900", "#dc322f"],
    },
    "Purple Nebula": {
        "app_bg": "#130d22", "panel_bg": "#211637", "plot_bg": "#180f2c",
        "text": "#f3e8ff", "muted": "#c4b5fd", "accent": "#d8b4fe",
        "entry_bg": "#2b1d45", "border": "#493263", "button_bg": "#382450",
        "button_active": "#50316f", "grid": "#a78bfa", "field_stops": ["#0d0887", "#7e03a8", "#cc4778", "#f89540", "#f0f921"],
    },
    "High Contrast": {
        "app_bg": "#000000", "panel_bg": "#101010", "plot_bg": "#000000",
        "text": "#ffffff", "muted": "#e5e7eb", "accent": "#00e5ff",
        "entry_bg": "#171717", "border": "#ffffff", "button_bg": "#292929",
        "button_active": "#444444", "grid": "#ffffff", "field_stops": ["#000000", "#4d0000", "#d50000", "#ffd600", "#ffffff"],
    },
    # Low-decoration theme with restrained contrast and no neon accents.
    "Minimal Dark": {
        "app_bg": "#0c0d0f", "panel_bg": "#131518", "plot_bg": "#090a0c",
        "text": "#e2e4e7", "muted": "#8b9098", "accent": "#b8c0cc",
        "entry_bg": "#17191d", "border": "#282b30", "button_bg": "#1c1f24",
        "button_active": "#292d34", "grid": "#747b85", "field_stops": ["#090a0c", "#20242b", "#3b414a", "#7d858f", "#d8dce2"],
    },
    "Graphite": {
        "app_bg": "#202225", "panel_bg": "#292c30", "plot_bg": "#17191c",
        "text": "#eff0f1", "muted": "#a3a8af", "accent": "#d2d6dc",
        "entry_bg": "#22252a", "border": "#41454c", "button_bg": "#34383e",
        "button_active": "#474d55", "grid": "#858b94", "field_stops": ["#17191c", "#313841", "#58616c", "#8c949e", "#e5e8ec"],
    },
    "Aurora": {
        "app_bg": "#07151a", "panel_bg": "#0c2428", "plot_bg": "#041115",
        "text": "#e0fff5", "muted": "#8abdb2", "accent": "#57e3c0",
        "entry_bg": "#103237", "border": "#215158", "button_bg": "#153d42",
        "button_active": "#1f5957", "grid": "#579f98", "field_stops": ["#06141d", "#164f68", "#167c71", "#61b76f", "#e1ef9a"],
    },
    "Solar Flare": {
        "app_bg": "#1a0d0a", "panel_bg": "#2a1711", "plot_bg": "#130806",
        "text": "#fff0df", "muted": "#c8a18c", "accent": "#ff9b62",
        "entry_bg": "#321d15", "border": "#5a3022", "button_bg": "#48251a",
        "button_active": "#66331f", "grid": "#ba7958", "field_stops": ["#140805", "#5d160e", "#a72c13", "#ef6c22", "#ffe39a"],
    },
    "Cyberpunk": {
        "app_bg": "#10091b", "panel_bg": "#1b1030", "plot_bg": "#0b0613",
        "text": "#f6eaff", "muted": "#b9a1d1", "accent": "#ff63d8",
        "entry_bg": "#24153b", "border": "#492b64", "button_bg": "#301a4c",
        "button_active": "#4a236d", "grid": "#8a64aa", "field_stops": ["#0b0613", "#4a167b", "#a31fa8", "#f34d91", "#ffd166"],
    },
    "Dark": {
        "app_bg": "#141414", "panel_bg": "#1e1e1e", "plot_bg": "#101010",
        "text": "#f1f1f1", "muted": "#b0b0b0", "accent": "#d0d0d0",
        "entry_bg": "#282828", "border": "#3b3b3b", "button_bg": "#303030",
        "button_active": "#424242", "grid": "#696969", "field_stops": ["#101010", "#353535", "#666666", "#b0b0b0", "#f0f0f0"],
    },
    "Light": {
        "app_bg": "#f3f5f7", "panel_bg": "#ffffff", "plot_bg": "#fbfcfd",
        "text": "#20242a", "muted": "#5c6570", "accent": "#1769aa",
        "entry_bg": "#ffffff", "border": "#c9d0d8", "button_bg": "#e4e8ed",
        "button_active": "#d2dae3", "grid": "#9aa4af", "field_stops": ["#f7fbff", "#b9d8ef", "#4ea3c8", "#2166ac", "#142850"],
    },
}

BODY_COLORS = ("#40c4ff", "#ff6685", "#ffd166")
BODY_NAMES = ("CYAN", "CORAL", "GOLD")
