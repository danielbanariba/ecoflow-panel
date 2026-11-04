// Node module hooks: GNOME Shell's gi:// and resource:/// imports resolve to
// stubs that render.mjs installs on globalThis.__stubs before loading.
const NAMES = {
    'gi://GObject': 'GObject', 'gi://St': 'St', 'gi://Gio': 'Gio', 'gi://GLib': 'GLib',
    'resource:///org/gnome/shell/extensions/extension.js': 'Extension',
    'resource:///org/gnome/shell/ui/panelMenu.js': 'PanelMenu',
    'resource:///org/gnome/shell/ui/popupMenu.js': 'PopupMenu',
    'resource:///org/gnome/shell/ui/main.js': 'Main',
};

export async function resolve(specifier, context, next) {
    const name = NAMES[specifier];
    if (!name)
        return next(specifier, context);
    const src = name === 'Extension'
        ? 'export const Extension = globalThis.__stubs.Extension;'
        : `const m = globalThis.__stubs.${name}; export default m; ` +
          `export const {${Object.keys(STUB_KEYS[name]).join(', ')}} = m;`;
    return {url: 'data:text/javascript,' + encodeURIComponent(src), shortCircuit: true};
}

const STUB_KEYS = {
    GObject: {registerClass: 1}, St: {BoxLayout: 1, Icon: 1, Label: 1},
    Gio: {Cancellable: 1, Subprocess: 1, SubprocessFlags: 1},
    GLib: {build_filenamev: 1, get_home_dir: 1, timeout_add_seconds: 1, source_remove: 1,
           PRIORITY_DEFAULT: 1, SOURCE_CONTINUE: 1},
    PanelMenu: {Button: 1}, PopupMenu: {PopupMenuItem: 1, PopupSeparatorMenuItem: 1},
    Main: {panel: 1},
};
