; arnhem_sync.ahk  -- AutoHotkey v2
; Reloads the NEWEST .vsav from C:\VassalArnhem\live\ into a running VASSAL,
; so a move Claude wrote to a save appears on the board with one hotkey.
;
; HOTKEY:  Ctrl+Alt+R  -> reload newest save
;
; NOTE (honest): GUI automation of VASSAL's Java/Swing menus is the one piece
; that needs a live tuning pass with Bruce watching -- the exact menu path and
; the "discard current game?" prompt handling may need adjustment for this build.
; Everything it depends on (the saves themselves) is already proven correct.

#Requires AutoHotkey v2.0
SetTitleMatchMode 2          ; match partial window titles

LIVE := "C:\VassalArnhem\live\"

NewestSave(dir) {
    newest := "", best := 0
    Loop Files dir "*.vsav" {
        if (A_LoopFileTimeModified > best) {
            best := A_LoopFileTimeModified
            newest := A_LoopFileFullPath
        }
    }
    return newest
}

^!r:: {
    save := NewestSave(LIVE)
    if (save = "") {
        MsgBox "No .vsav found in " LIVE
        return
    }
    ; Bring VASSAL to the front. Title usually contains the module/map name.
    if !WinExist("Westwall") and !WinExist("VASSAL") and !WinExist("Arnhem") {
        MsgBox "VASSAL window not found - is the module open?"
        return
    }
    WinActivate
    WinWaitActive , , 3
    Sleep 200

    ; Open the File menu and choose "Open Game..." (Alt+F mnemonic).
    Send "!f"
    Sleep 300
    ; 'o' = Open Game in most VASSAL builds. If wrong, change this letter.
    Send "o"
    Sleep 600

    ; If VASSAL asks to discard the current game, accept it.
    if WinWait("Discard", , 1) {
        Send "{Enter}"
        Sleep 300
    }

    ; In the file chooser, type the full path and confirm.
    WinWaitActive "Open", , 3
    Sleep 200
    SendText save
    Sleep 200
    Send "{Enter}"

    ; Some builds re-prompt for version/continuation -- accept.
    if WinWait("created with", , 1)
        Send "{Enter}"

    ToolTip "Reloaded: " save
    SetTimer () => ToolTip(), -1500
}

; Ctrl+Alt+D  -> show which save WOULD be loaded (dry run / sanity check)
^!d:: {
    save := NewestSave(LIVE)
    ToolTip (save = "" ? "no save found" : "newest: " save)
    SetTimer () => ToolTip(), -2500
}
