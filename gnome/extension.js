/*
 * EcoFlow battery indicator for GNOME Shell.
 *
 * The unit exposes nothing on the LAN, so the reading comes from EcoFlow's
 * cloud. All of that -- credentials, HMAC signing, caching -- lives in
 * ~/.local/bin/ecoflow-battery, which prints one JSON line with --panel. The
 * extension only renders it, which keeps the network code testable from a
 * shell and identical across every desktop this project supports.
 */
import GObject from 'gi://GObject';
import St from 'gi://St';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const HELPER = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'ecoflow-battery']);
const REFRESH_SECONDS = 120;

const EcoFlowIndicator = GObject.registerClass(
class EcoFlowIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'EcoFlow');

        this._cancellable = new Gio.Cancellable();
        this._timeout = null;

        const box = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        this._icon = new St.Icon({
            icon_name: 'battery-symbolic',
            style_class: 'system-status-icon',
        });
        this._label = new St.Label({
            text: '--',
            y_align: 2,               // Clutter.ActorAlign.CENTER
            style_class: 'ecoflow-label',
        });
        box.add_child(this._icon);
        box.add_child(this._label);
        this.add_child(box);

        this._detail = new PopupMenu.PopupMenuItem('Leyendo…', {reactive: false});
        this.menu.addMenuItem(this._detail);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        const refresh = new PopupMenu.PopupMenuItem('Actualizar');
        refresh.connect('activate', () => this._refresh());
        this.menu.addMenuItem(refresh);

        this._refresh();
        this._timeout = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT, REFRESH_SECONDS, () => {
                this._refresh();
                return GLib.SOURCE_CONTINUE;
            });
    }

    _refresh() {
        try {
            const proc = Gio.Subprocess.new(
                [HELPER, '--panel'],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE);
            proc.communicate_utf8_async(null, this._cancellable, (p, res) => {
                let out = '';
                try {
                    [, out] = p.communicate_utf8_finish(res);
                } catch (_e) {
                    return;                       // cancelled on disable()
                }
                this._render(out);
            });
        } catch (_e) {
            this._label.text = '--';
        }
    }

    _render(out) {
        let d;
        try {
            d = JSON.parse(out.trim());
        } catch (_e) {
            this._label.text = '--';
            this._detail.label.text = 'Sin lectura';
            return;
        }

        this._label.text = `${d.soc}%`;
        // Ten steps is all the icon set has; rounding to it keeps the glyph in
        // step with the number instead of drifting between them.
        const step = Math.max(0, Math.min(100, Math.round(d.soc / 10) * 10));
        this._icon.icon_name = d.state === 'charging'
            ? `battery-level-${step}-charging-symbolic`
            : `battery-level-${step}-symbolic`;

        const estado = d.state === 'charging' ? 'Cargando'
                     : d.state === 'discharging' ? 'Descargando'
                     : 'En reposo';
        let text = `${d.soc}% · ${estado}`;
        if (d.watts) text += ` ${d.watts} W`;
        if (d.minutes) {
            const h = Math.floor(d.minutes / 60), m = d.minutes % 60;
            text += ` · ${h > 0 ? `${h} h ${m} min` : `${m} min`} restantes`;
        }
        this._detail.label.text = text;
    }

    destroy() {
        if (this._timeout) {
            GLib.source_remove(this._timeout);
            this._timeout = null;
        }
        this._cancellable?.cancel();
        this._cancellable = null;
        super.destroy();
    }
});

export default class EcoFlowExtension extends Extension {
    enable() {
        this._indicator = new EcoFlowIndicator();
        Main.panel.addToStatusArea('ecoflow-indicator', this._indicator, 0, 'right');
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
