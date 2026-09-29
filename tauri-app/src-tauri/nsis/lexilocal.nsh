; LexiLocal NSIS installer hooks
; Adds a desktop shortcut during installation and removes it on uninstall.

!macro customInstall
  CreateShortcut "$DESKTOP\LexiLocal UI.lnk" "$INSTDIR\${MAIN_APP_EXE}"
!macroend

!macro customUnInstall
  Delete "$DESKTOP\LexiLocal UI.lnk"
!macroend
