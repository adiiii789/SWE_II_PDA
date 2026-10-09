"""Qt-Hülle: Tray-Icon und Popup-Fenster, in dem das Frontend angezeigt wird.

  application.py   setzt alles zusammen (Composition Root)
  tray_icon.py     Tray-Icon: Linksklick → Signal, Rechtsklick → Kontextmenü
  popup_window.py  rahmenloses Popup mit Einfahr-Animation
  web_view.py      Browser-Ansicht, die frontend/popup.html lädt und die Bridge anhängt
"""
