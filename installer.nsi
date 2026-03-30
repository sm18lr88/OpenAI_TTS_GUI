!include "MUI2.nsh"

!define APP_VERSION "1.2.0"

Name "OpenAI TTS"
OutFile "dist\OpenAI-TTS-Setup.exe"
InstallDir "$PROGRAMFILES\OpenAI-TTS"
InstallDirRegKey HKLM "Software\OpenAI-TTS" "InstallDir"
RequestExecutionLevel admin

!define MUI_ABORTWARNING

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "Install"
    SetOutPath "$INSTDIR"
    File /r "dist\OpenAI-TTS\*.*"

    WriteRegStr HKLM "Software\OpenAI-TTS" "InstallDir" "$INSTDIR"

    WriteUninstaller "$INSTDIR\Uninstall.exe"

    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS" \
        "DisplayName" "OpenAI TTS"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS" \
        "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS" \
        "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS" \
        "Publisher" "OpenAI TTS Project"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS" \
        "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS" \
        "NoRepair" 1

    CreateDirectory "$SMPROGRAMS\OpenAI TTS"
    CreateShortcut "$SMPROGRAMS\OpenAI TTS\OpenAI TTS.lnk" "$INSTDIR\openai_tts_bin.exe"
    CreateShortcut "$SMPROGRAMS\OpenAI TTS\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
    CreateShortcut "$DESKTOP\OpenAI TTS.lnk" "$INSTDIR\openai_tts_bin.exe"
SectionEnd

Section "Uninstall"
    RMDir /r "$INSTDIR"

    Delete "$SMPROGRAMS\OpenAI TTS\OpenAI TTS.lnk"
    Delete "$SMPROGRAMS\OpenAI TTS\Uninstall.lnk"
    RMDir "$SMPROGRAMS\OpenAI TTS"
    Delete "$DESKTOP\OpenAI TTS.lnk"

    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenAI-TTS"
    DeleteRegKey HKLM "Software\OpenAI-TTS"
SectionEnd
