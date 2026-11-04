import QtQuick
// Stand-in for Plasma5Support.DataSource: records what the plasmoid asks to
// run, and lets the test hand back an executable engine's reply.
QtObject {
    objectName: "dataSource"
    property string engine
    property var connectedSources: []
    signal newData(string source, var data)
    function connectSource(s) { connectedSources = connectedSources.concat([s]) }
    function disconnectSource(s) {}
}
