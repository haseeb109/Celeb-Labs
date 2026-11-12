# voice/os_voice.py — operating-system voice fallback: macOS `say`, Windows SAPI, Linux espeak.
# Quality is low; only used when the owner allows fallback. Writes a WAV/AIFF file.
import platform
import shutil
import subprocess


def synth_to_file(text: str, out_path: str) -> bool:
    sysname = platform.system()
    try:
        if sysname == "Darwin":
            subprocess.run(["say", "-o", out_path.replace(".wav", ".aiff"), text], check=True)
            return True
        if sysname == "Windows":
            ps = ("Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                  f"$s.SetOutputToWaveFile('{out_path}'); $s.Speak([Console]::In.ReadToEnd())")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], input=text.encode(), check=True)
            return True
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if exe:
            subprocess.run([exe, "-w", out_path, text], check=True)
            return True
    except Exception:
        return False
    return False
