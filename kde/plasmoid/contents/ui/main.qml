/*
 * EcoFlow battery readout.
 *
 * The unit exposes nothing on the LAN -- a sweep of the network finds no port
 * to query, because its WiFi only reaches EcoFlow's cloud. The reading comes
 * back through api.ecoflow.com, so the request lives in
 * ~/.local/bin/ecoflow-battery where the credentials and HMAC signing stay out
 * of QML and can be tested from a shell.
 */
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    // Same standard the other custom widgets in this panel use.
    readonly property int  uiIconSize: 15
    readonly property real uiFontSize: 9
    readonly property int  uiGapInner: Kirigami.Units.smallSpacing

    property int    soc: -1
    property string state: ""
    property int    watts: 0
    property int    minutes: -1
    property string errorText: ""

    readonly property bool healthy: soc >= 0 && errorText === ""

    function bandColor(v) {
        if (v < 0)   return Kirigami.Theme.disabledTextColor;
        if (v <= 15) return Kirigami.Theme.negativeTextColor;
        if (v <= 30) return Kirigami.Theme.neutralTextColor;
        return Kirigami.Theme.textColor;
    }

    // Breeze ships stepped battery glyphs; pick the one nearest the reading so
    // the icon carries the level too, not just the number beside it.
    function batteryIcon(v) {
        if (v < 0) return "battery-missing";
        var step = Math.max(0, Math.min(100, Math.round(v / 10) * 10));
        return (root.state === "charging" ? "battery-charging-0" : "battery-0")
               .replace("0", String(step));
    }

    function humanTime(m) {
        if (m <= 0) return "";
        if (m < 60) return m + " min";
        return Math.floor(m / 60) + " h " + (m % 60) + " min";
    }

    Plasma5Support.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        onNewData: function(source, data) {
            disconnectSource(source);
            var out = (data["stdout"] || "").trim();
            try {
                var j = JSON.parse(out);
                root.soc = j.soc;
                root.state = j.state || "";
                root.watts = j.watts || 0;
                root.minutes = (j.minutes === null || j.minutes === undefined) ? -1 : j.minutes;
                root.errorText = "";
            } catch (e) {
                root.errorText = out || "sin respuesta";
                root.soc = -1;
            }
        }
        function poll() {
            var cmd = "$HOME/.local/bin/ecoflow-battery --panel";
            disconnectSource(cmd);
            connectSource(cmd);
        }
    }

    Timer {
        // The helper caches for a minute, so this only costs a request when the
        // cache is cold. The figure moves slowly; there is nothing to gain from
        // polling harder.
        interval: 2 * 60 * 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: exec.poll()
    }

    preferredRepresentation: compactRepresentation

    compactRepresentation: MouseArea {
        Layout.minimumWidth: row.implicitWidth + Kirigami.Units.smallSpacing * 2
        hoverEnabled: true
        onClicked: exec.poll()

        RowLayout {
            id: row
            anchors.centerIn: parent
            spacing: root.uiGapInner

            Kirigami.Icon {
                source: root.batteryIcon(root.soc)
                fallback: "battery"
                Layout.preferredWidth: root.uiIconSize
                Layout.preferredHeight: root.uiIconSize
                isMask: true
                color: root.bandColor(root.soc)
            }
            PlasmaComponents.Label {
                text: root.healthy ? root.soc + "%" : "—"
                color: root.bandColor(root.soc)
                font.pointSize: root.uiFontSize
                Layout.preferredWidth: socMetrics.width
                horizontalAlignment: Text.AlignLeft
            }
        }

        TextMetrics {
            id: socMetrics
            font.pointSize: root.uiFontSize
            text: "100%"
        }

        PlasmaCore.ToolTipArea {
            anchors.fill: parent
            mainText: "EcoFlow"
            subText: root.healthy
                ? root.soc + "% · " +
                  (root.state === "charging"    ? "cargando " + root.watts + " W"
                 : root.state === "discharging" ? "descargando " + root.watts + " W"
                 :                                "en reposo") +
                  (root.minutes > 0 ? "\n" + root.humanTime(root.minutes) + " restantes" : "") +
                  "\n\nClic para actualizar"
                : "Sin lectura: " + root.errorText + "\n\nClic para reintentar"
        }
    }

    fullRepresentation: PlasmaExtras.Representation {
        Layout.minimumWidth:  Kirigami.Units.gridUnit * 14
        Layout.minimumHeight: Kirigami.Units.gridUnit * 8
        contentItem: ColumnLayout {
            spacing: Kirigami.Units.smallSpacing
            PlasmaExtras.Heading { level: 4; text: "EcoFlow DELTA Pro" }
            GridLayout {
                columns: 2
                columnSpacing: Kirigami.Units.largeSpacing
                PlasmaComponents.Label { text: "Carga" }
                PlasmaComponents.Label {
                    text: root.soc >= 0 ? root.soc + "%" : "—"
                    color: root.bandColor(root.soc)
                }
                PlasmaComponents.Label { text: "Estado" }
                PlasmaComponents.Label {
                    text: root.state === "charging"    ? "Cargando"
                        : root.state === "discharging" ? "Descargando"
                        : root.state === "idle"        ? "En reposo" : "—"
                }
                PlasmaComponents.Label { text: "Potencia"; visible: root.watts > 0 }
                PlasmaComponents.Label { text: root.watts + " W"; visible: root.watts > 0 }
                PlasmaComponents.Label { text: "Restante"; visible: root.minutes > 0 }
                PlasmaComponents.Label { text: root.humanTime(root.minutes); visible: root.minutes > 0 }
            }
            PlasmaComponents.Button { text: "Actualizar"; onClicked: exec.poll() }
            Item { Layout.fillHeight: true }
        }
    }
}
