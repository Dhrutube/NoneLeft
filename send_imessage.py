#!/usr/bin/env python3
"""Send a real iMessage via the Mac's Messages app (AppleScript). Send-only, no disk access needed."""
import subprocess

def send(to, text):
    """Returns (ok: bool, error: str|None). First send triggers macOS automation permission popup."""
    # Escape for AppleScript string
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    script = f'''
    tell application "Messages"
        set targetService to 1st account whose service type is iMessage
        set targetBuddy to participant "{to}" of targetService
        send "{escaped}" to targetBuddy
    end tell'''
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            return True, None
        return False, (r.stderr or "unknown osascript error").strip()[:300]
    except Exception as e:
        return False, str(e)[:300]

if __name__ == "__main__":
    import sys
    to = sys.argv[1]; msg = " ".join(sys.argv[2:]) or "Muster test message"
    ok, err = send(to, msg)
    print("SENT" if ok else f"FAILED: {err}")
