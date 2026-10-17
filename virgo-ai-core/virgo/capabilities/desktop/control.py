"""Safe, explicit Windows desktop and VS Code automation."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from platform import system
from typing import Any

from virgo.contracts.errors import ProviderUnavailableError, ValidationError

ALLOWED_APPS = {
    "code": ("code", "Code.exe"),
    "vscode": ("code", "Code.exe"),
    "notepad": ("notepad.exe",),
    "calculator": ("calc.exe",),
    "explorer": ("explorer.exe",),
}
ALLOWED_HOTKEYS = {
    "ctrl+s": ("ctrl", "s"),
    "ctrl+shift+p": ("ctrl", "shift", "p"),
    "ctrl+p": ("ctrl", "p"),
    "ctrl+shift+f": ("ctrl", "shift", "f"),
    "alt+tab": ("alt", "tab"),
}


@dataclass(frozen=True, slots=True)
class DesktopWindow:
    title: str
    process_id: int | None
    process_name: str | None


class DesktopAutomationService:
    """Perform only allowlisted local GUI operations; no arbitrary shell."""

    provider_name = "windows-desktop"

    def health_check(self) -> bool:
        return system() == "Windows"

    def launch_app(self, app: str, *, arguments: tuple[str, ...] = ()) -> str:
        self._require_windows()
        key = app.strip().casefold()
        candidates = ALLOWED_APPS.get(key)
        if candidates is None:
            raise ValidationError(
                f"Application {app!r} is not allowlisted", source_module=__name__
            )
        executable = self._resolve_executable(candidates)
        try:
            subprocess.Popen(
                [executable, *arguments],
                cwd=None,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
        except OSError as error:
            raise ProviderUnavailableError(
                "The requested Windows application could not be started",
                technical_detail=str(error),
                source_module=__name__,
                cause=error,
            ) from error
        return f"Launched {key}"

    def open_vscode(self, workspace: Path) -> str:
        self._require_windows()
        if not workspace.is_absolute() or not workspace.is_dir():
            raise ValidationError(
                "VS Code requires an existing absolute workspace", source_module=__name__
            )
        return self.launch_app("vscode", arguments=(str(workspace.resolve()),))

    def active_window(self) -> DesktopWindow:
        self._require_windows()
        try:
            import pywinauto  # type: ignore[import-not-found]
        except ImportError as error:
            raise ProviderUnavailableError(
                "Desktop window inspection requires the pywinauto extra",
                technical_detail="Install the desktop optional dependency.",
                source_module=__name__,
                cause=error,
            ) from error
        try:
            desktop = pywinauto.Desktop(backend="uia")
            window = desktop.get_active()
            process_id = int(window.process_id()) if window.process_id() else None
            process_name: str | None = None
            if process_id:
                try:
                    process_name = str(
                        __import__("psutil").Process(process_id).name()
                    )
                except Exception:
                    process_name = None
            return DesktopWindow(
                title=str(window.window_text()),
                process_id=process_id,
                process_name=process_name,
            )
        except Exception as error:
            raise ProviderUnavailableError(
                "The active Windows window could not be inspected",
                technical_detail=str(error),
                source_module=__name__,
                cause=error,
            ) from error

    def type_text(self, text: str, *, interval_ms: int = 0) -> str:
        self._require_windows()
        if not isinstance(text, str) or not text.strip():
            raise ValidationError("Desktop text must not be empty", source_module=__name__)
        if len(text) > 8_000:
            raise ValidationError("Desktop text exceeds the safe limit", source_module=__name__)
        try:
            import pyautogui  # type: ignore[import-not-found]
        except ImportError as error:
            raise ProviderUnavailableError(
                "Desktop typing requires the pyautogui extra",
                technical_detail="Install the desktop optional dependency.",
                source_module=__name__,
                cause=error,
            ) from error
        try:
            pyautogui.write(text, interval=max(0, interval_ms) / 1000.0)
        except Exception as error:
            raise ProviderUnavailableError(
                "Windows text input failed",
                technical_detail=str(error),
                source_module=__name__,
                cause=error,
            ) from error
        return f"Typed {len(text)} characters"

    def hotkey(self, shortcut: str) -> str:
        self._require_windows()
        normalized = shortcut.strip().casefold()
        keys = ALLOWED_HOTKEYS.get(normalized)
        if keys is None:
            raise ValidationError(
                f"Hotkey {shortcut!r} is not allowlisted", source_module=__name__
            )
        try:
            import pyautogui  # type: ignore[import-not-found]
        except ImportError as error:
            raise ProviderUnavailableError(
                "Desktop hotkeys require the pyautogui extra",
                technical_detail="Install the desktop optional dependency.",
                source_module=__name__,
                cause=error,
            ) from error
        pyautogui.hotkey(*keys)
        return f"Pressed {normalized}"

    def execute(self, objective: str, *, workspace: Path | None = None) -> str:
        """Map natural-language desktop requests to a tiny allowlisted action set."""
        text = objective.casefold()
        if "vs code" in text or "vscode" in text or "visual studio code" in text:
            if workspace is None:
                raise ValidationError(
                    "VS Code actions require an explicit workspace", source_module=__name__
                )
            if any(value in text for value in ("type", "write", "paste")):
                return self.type_text(_extract_quoted_text(objective))
            return self.open_vscode(workspace)
        for name in ALLOWED_APPS:
            if any(marker in text for marker in (f"open {name}", f"launch {name}")):
                return self.launch_app(name)
        if "active window" in text or "current window" in text:
            window = self.active_window()
            return f"Active window: {window.title or '[untitled]'}"
        raise ValidationError(
            "Desktop request is outside the allowlisted local actions",
            source_module=__name__,
        )

    @staticmethod
    def _resolve_executable(candidates: tuple[str, ...]) -> str:
        for candidate in candidates:
            if Path(candidate).is_absolute() and Path(candidate).exists():
                return candidate
            found = shutil.which(candidate)
            if found:
                return found
            local_candidates = (
                os.path.expandvars(r"%LOCALAPPDATA%\\Programs\\Microsoft VS Code\\Code.exe"),
                os.path.expandvars(r"%PROGRAMFILES%\\Microsoft VS Code\\Code.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\\Microsoft VS Code\\Code.exe"),
            )
            for value in local_candidates:
                if value and Path(value).exists():
                    return value
        raise ProviderUnavailableError(
            "The requested Windows application is not installed or discoverable",
            source_module=__name__,
        )

    @staticmethod
    def _require_windows() -> None:
        if system() != "Windows":
            raise ProviderUnavailableError(
                "Windows desktop automation is only available on Windows",
                source_module=__name__,
            )


def _extract_quoted_text(objective: str) -> str:
    for delimiter in ('"', "'"):
        parts = objective.split(delimiter)
        if len(parts) >= 3 and parts[1].strip():
            return parts[1]
    raise ValidationError(
        "Desktop typing requires the text in quotes", source_module=__name__
    )
