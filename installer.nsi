!include "MUI2.nsh"

!define APP_VERSION "1.3.4"

Name "OpenAI TTS"
OutFile "dist\OpenAI-TTS-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\OpenAI-TTS"
InstallDirRegKey HKCU "Software\OpenAI-TTS" "InstallDir"
RequestExecutionLevel user

!define MUI_ABORTWARNING

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "Install"
    IfFileExists "$INSTDIR\.openai-tts-install" install.continue
    IfFileExists "$INSTDIR\*.*" 0 install.continue
    MessageBox MB_ICONSTOP "The selected folder is not empty. Choose an empty OpenAI TTS folder or the existing app install folder."
    Abort

    install.continue:
    SetOutPath "$INSTDIR"
    File /r "dist\OpenAI-TTS\*.*"
    FileOpen $0 "$INSTDIR\.openai-tts-install" w
    FileWrite $0 "OpenAI TTS ${APP_VERSION}$\r$\n"
    FileClose $0

    WriteRegStr HKCU "Software\OpenAI-TTS" "InstallDir" "$INSTDIR"

    WriteUninstaller "$INSTDIR\Uninstall.exe"

    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS" \
        "DisplayName" "OpenAI TTS"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS" \
        "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS" \
        "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS" \
        "DisplayIcon" "$INSTDIR\openai_tts_bin.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS" \
        "Publisher" "Leo Riera / sm18lr88"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS" \
        "URLInfoAbout" "https://github.com/sm18lr88/OpenAI_TTS_GUI"
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS" \
        "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS" \
        "NoRepair" 1

    CreateDirectory "$SMPROGRAMS\OpenAI TTS"
    CreateShortcut "$SMPROGRAMS\OpenAI TTS\OpenAI TTS.lnk" "$INSTDIR\openai_tts_bin.exe"
    CreateShortcut "$SMPROGRAMS\OpenAI TTS\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
    ReadRegStr $0 HKCU "Software\OpenAI-TTS" "InstallDir"
    StrCmp $0 "$INSTDIR" 0 un.safe_abort
    IfFileExists "$INSTDIR\openai_tts_bin.exe" 0 un.safe_abort
    IfFileExists "$INSTDIR\.openai-tts-install" 0 un.safe_abort

    Delete "$SMPROGRAMS\OpenAI TTS\OpenAI TTS.lnk"
    Delete "$SMPROGRAMS\OpenAI TTS\Uninstall.lnk"
    RMDir "$SMPROGRAMS\OpenAI TTS"

    Delete "$INSTDIR\.openai-tts-install"
    Delete "$INSTDIR\openai_tts_bin.exe"
    RMDir /r "$INSTDIR\_internal"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir "$INSTDIR"

    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS"
    DeleteRegKey HKCU "Software\OpenAI-TTS"
    Return

    un.safe_abort:
        MessageBox MB_ICONSTOP "Uninstall path verification failed. Refusing to remove $INSTDIR."
        Abort
SectionEnd
