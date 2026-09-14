import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import Quickshell.Wayland
import qs.Commons

Item {
  id: root
  property var shell: null
  property string omarchyPath: Quickshell.env("OMARCHY_PATH")
  property var workspaceState: ({})
  property var panels: []
  property var mainWindows: ({})
  property bool showHeader: true
  property bool showFooter: true
  property real backgroundOpacity: 0
  FileView {
    id: settingsFile
    path: Quickshell.env("HOME") + "/.config/omarchy/shell.json"
    watchChanges: true
    onFileChanged: reload()
    onLoaded: {
      try {
        var entries = JSON.parse(text()).plugins || []
        var settings = entries.find(function(entry) { return entry.id === "mtaggart.filmstrip" }) || {}
        root.showHeader = settings.showHeader !== false
        root.showFooter = settings.showFooter !== false
        root.backgroundOpacity = typeof settings.backgroundOpacity === "number" && isFinite(settings.backgroundOpacity)
          ? Math.max(0, Math.min(1, settings.backgroundOpacity)) : 0
      } catch (e) { console.warn("Filmstrip: cannot read settings: " + e) }
    }
  }
  readonly property string controller: Quickshell.env("HOME") + "/.local/bin/omarchy-filmstrip"

  function refresh() {
    if (!stateProcess.running) stateProcess.running = true
  }
  function status() {
    return JSON.stringify(root.panels.map(function(p) {
      return {screen: p.screen ? p.screen.name : "", visible: p.visible,
              width: p.width, height: p.height, workspace: p.workspaceId, showHeader: root.showHeader, showFooter: root.showFooter, backgroundOpacity: root.backgroundOpacity, background: String(p.color), cardBackground: String(Color.popups.background), textColor: String(Color.popups.text), selectedBorder: String(Color.imagePicker.selectedBorder), windows: p.captureStatus()}
    }))
  }
  IpcHandler {
    target: "filmstrip"
    function status(): string { return root.status() }
    function refresh(): void { root.refresh() }
  }
  Process {
    id: stateProcess
    command: ["hyprctl", "workspaces", "-j"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var states = {}
          JSON.parse(text).forEach(function(w) {
            states[String(w.id)] = {layout: w.tiledLayout, fullscreen: w.hasfullscreen, lastWindow: (w.lastwindow || "").replace(/^0x/, "")}
          })
          if (JSON.stringify(states) !== JSON.stringify(root.workspaceState)) root.workspaceState = states
          root.panels.forEach(function(p) { p.syncWindows() })
        } catch (e) { console.warn("Filmstrip: workspace refresh failed: " + e) }
      }
    }
  }
  Timer { id: refreshDebounce; interval: 60; onTriggered: root.refresh() }
  Timer { interval: 2000; running: true; repeat: true; triggeredOnStart: true; onTriggered: root.refresh() }
  Connections {
    target: Hyprland
    function onRawEvent(event) {
      if (["openwindow", "closewindow", "movewindow", "movewindowv2", "workspace", "workspacev2", "focusedmon", "fullscreen", "configreloaded", "monitoradded", "monitorremoved", "custom"].indexOf(event.name) >= 0)
        refreshDebounce.restart()
    }
  }
  Variants {
    model: Quickshell.screens
    delegate: PanelWindow {
      id: panel
      required property var modelData
      screen: modelData
      readonly property var monitor: Hyprland.monitors.values.find(function(m) { return m.name === panel.screen.name }) || null
      readonly property int workspaceId: monitor && monitor.activeWorkspace ? monitor.activeWorkspace.id : -1
      readonly property var state: root.workspaceState[String(workspaceId)] || ({})
      property var windows: []
      readonly property string mainAddress: root.mainWindows[String(workspaceId)] || state.lastWindow || ""
      function rememberMain(address) {
        if (root.mainWindows[String(workspaceId)] === address) return
        var next = Object.assign({}, root.mainWindows)
        next[String(workspaceId)] = address
        root.mainWindows = next
      }
      readonly property bool filmstrip: state.layout === "monocle"
      visible: filmstrip && !state.fullscreen && !(monitor && monitor.lastIpcObject.specialWorkspace && monitor.lastIpcObject.specialWorkspace.id) && windows.length > 1
      anchors { right: true; top: true; bottom: true }
      implicitWidth: Math.round(screen.width * 0.10)
      exclusiveZone: implicitWidth
      color: Qt.alpha(Color.background, root.backgroundOpacity)
      WlrLayershell.namespace: "omarchy-filmstrip"
      WlrLayershell.layer: WlrLayer.Top
      WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

      function syncWindows() {
        var next = Hyprland.toplevels.values.filter(function(t) {
          return t.workspace && t.workspace.id === panel.workspaceId && !t.lastIpcObject.floating && !t.lastIpcObject.hidden
        }).sort(function(a, b) { return a.address.localeCompare(b.address) })
        var active = next.find(function(t) { return t.activated })
        if (active) rememberMain(active.address)
        else if (next.length && !next.some(function(t) { return t.address === panel.mainAddress })) rememberMain(next[0].address)
        if (next.map(function(t) {return t.address}).join(",") !== windows.map(function(t) {return t.address}).join(",")) windows = next
      }
      function captureStatus() {
        var result = []
        for (var i = 0; i < cards.count; i++) {
          var c = cards.itemAt(i)
          if (c && c.visible) {
            var center = c.mapToItem(panel.contentItem, c.width / 2, c.height / 2)
            result.push({address: c.modelData.address, ready: c.ready, sourceWidth: c.sourceWidth, sourceHeight: c.sourceHeight, centerX: center.x, centerY: center.y})
          }
        }
        return result
      }
      onWorkspaceIdChanged: syncWindows()
      Component.onCompleted: { root.panels = root.panels.concat([panel]); syncWindows() }
      Component.onDestruction: root.panels = root.panels.filter(function(p) { return p !== panel })

      Column {
        visible: root.showHeader
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
        spacing: 4
        Text { text: "FILMSTRIP"; color: Color.foreground; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.1 }
        Text { text: panel.windows.length + (panel.windows.length === 1 ? " window" : " windows"); color: Color.muted; font.pixelSize: 10 }
      }
      Flickable {
        id: scroll
        anchors { left: parent.left; right: parent.right; top: parent.top; bottom: root.showFooter ? footer.top : parent.bottom; leftMargin: 6; rightMargin: 6; topMargin: root.showHeader ? 52 : 8; bottomMargin: 8 }
        contentHeight: strip.height
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        Column {
          id: strip
          width: scroll.width
          spacing: 10
          Repeater {
            id: cards
            model: panel.windows
            delegate: Rectangle {
              id: card
              required property var modelData
              required property int index
              readonly property bool selected: modelData.address === panel.mainAddress
              visible: !selected
              Connections {
                target: card.modelData
                function onActivatedChanged() {
                  if (card.modelData.activated) panel.rememberMain(card.modelData.address)
                }
              }
              readonly property bool inView: y + height >= scroll.contentY && y <= scroll.contentY + scroll.height
              readonly property bool ready: preview.hasContent
              readonly property int sourceWidth: preview.sourceSize.width
              readonly property int sourceHeight: preview.sourceSize.height
              width: strip.width
              height: previewBox.height + title.height + 22
              radius: 5
              color: mouse.containsMouse ? Qt.tint(Color.popups.background, Style.hoverFill) : Color.popups.background
              border.width: selected ? 2 : 1
              border.color: selected ? Color.imagePicker.selectedBorder : (mouse.containsMouse ? Style.hoverBorderColor : Color.imagePicker.unselectedBorder)
              Item {
                id: previewBox
                anchors { top: parent.top; left: parent.left; right: parent.right; margins: 5 }
                height: width * 0.68
                ScreencopyView {
                  id: preview
                  anchors.centerIn: parent
                  captureSource: panel.visible && card.visible && card.modelData ? card.modelData.wayland : null
                  live: false
                  paintCursor: false
                  constraintSize: Qt.size(previewBox.width, previewBox.height)
                  width: implicitWidth
                  height: implicitHeight
                }
                Timer {
                  interval: mouse.containsMouse ? 150 : 750
                  running: panel.visible && card.visible && card.inView && preview.captureSource !== null
                  repeat: true
                  onTriggered: preview.captureFrame()
                }
                Text {
                  anchors.centerIn: parent
                  visible: !preview.hasContent
                  text: card.modelData.wayland ? "Loading preview…" : "Preview unavailable"
                  width: parent.width
                  horizontalAlignment: Text.AlignHCenter
                  wrapMode: Text.WordWrap
                  color: Color.muted
                  font.pixelSize: 10
                }
              }
              Text {
                id: title
                anchors { left: parent.left; right: parent.right; top: previewBox.bottom; leftMargin: 7; rightMargin: 7; topMargin: 7 }
                text: card.modelData.title || card.modelData.lastIpcObject.class || "Window"
                color: Color.popups.text
                font.family: Style.fontFamily
                font.pixelSize: 11
                maximumLineCount: 2
                wrapMode: Text.Wrap
                elide: Text.ElideRight
              }
              MouseArea {
                id: mouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: Quickshell.execDetached([root.controller, "focus", card.modelData.address, String(panel.workspaceId)])
              }

            }
          }
        }
      }
      Column {
        id: footer
        visible: root.showFooter
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 8 }
        spacing: 4
        Text { text: "Alt+Tab  ·  Switch"; font.pixelSize: 10; color: Color.muted }
        Text { text: "Super+L  ·  Tile"; font.pixelSize: 10; color: Color.muted }
      }
    }
  }
}
