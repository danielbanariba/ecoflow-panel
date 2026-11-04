// Feed one --panel line to the GNOME indicator's _render() and print what the
// panel would show:  node render.mjs '<json line>'
import {register} from 'node:module';

class Actor {
    constructor(props = {}) { Object.assign(this, props); }
    add_child() {}
}
class Item { constructor(text) { this.label = {text}; } connect() {} }

let indicator = null;
globalThis.__stubs = {
    GObject: {registerClass: cls => class extends cls {
        constructor(...a) { super(); this._init(...a); }
    }},
    St: {BoxLayout: Actor, Icon: Actor, Label: Actor},
    Gio: {
        Cancellable: class { cancel() {} },
        Subprocess: {new() { throw new Error('no helper in tests'); }},
        SubprocessFlags: {STDOUT_PIPE: 1, STDERR_SILENCE: 2},
    },
    GLib: {build_filenamev: p => p.join('/'), get_home_dir: () => '/home/test',
           timeout_add_seconds: () => 1, source_remove() {},
           PRIORITY_DEFAULT: 0, SOURCE_CONTINUE: true},
    Extension: class {},
    PanelMenu: {Button: class extends Actor {
        _init() { this.menu = {addMenuItem() {}}; }
        destroy() {}
    }},
    PopupMenu: {PopupMenuItem: Item, PopupSeparatorMenuItem: Item},
    Main: {panel: {addToStatusArea(_id, ind) { indicator = ind; }}},
};

register('./hooks.mjs', import.meta.url);
const {default: Ext} = await import('../../gnome/extension.js');
new Ext().enable();
indicator._render(process.argv[2]);
console.log(JSON.stringify({
    label: indicator._label.text,
    icon: indicator._icon.icon_name,
    detail: indicator._detail.label.text,
}));
