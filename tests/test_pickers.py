"""Selector de carpetas y archivos integrado en la app."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest
from PySide6.QtWidgets import QApplication

from tagflow.ui.components.pickers import FolderPickerDialog


@pytest.fixture
def picker(qapp: QApplication) -> Callable[..., FolderPickerDialog]:
    dialogs: list[FolderPickerDialog] = []

    def build(**kwargs: object) -> FolderPickerDialog:
        dialog = FolderPickerDialog(**kwargs)
        dialogs.append(dialog)
        return dialog

    yield build
    for dialog in dialogs:
        dialog.close()
        dialog.deleteLater()
    QApplication.processEvents()


def test_picker_navigates_and_lists_subfolders(
    picker: Callable[..., FolderPickerDialog], tmp_path: Path
) -> None:
    root = tmp_path / "raiz"
    child = root / "hija"
    child.mkdir(parents=True)
    dialog = picker(start=root)
    assert dialog.current_folder() == root.resolve()
    names = [dialog.list.item(index).text() for index in range(dialog.list.count())]
    assert "hija" in names

    dialog.navigate_to(child)
    assert dialog.current_folder() == child.resolve()
    assert dialog.path_edit.text() == str(child.resolve())


def test_picker_creates_folder_and_reports_errors(
    picker: Callable[..., FolderPickerDialog], tmp_path: Path
) -> None:
    root = tmp_path / "raiz"
    root.mkdir()
    dialog = picker(start=root)
    created = dialog.create_folder("nueva")
    assert created.is_dir()
    assert dialog.current_folder() == created.resolve()
    assert created.parent == root.resolve()

    dialog.navigate_to(tmp_path / "no-existe")
    assert dialog.current_folder() == created.resolve()
    assert not dialog.error.isHidden()


def test_picker_file_mode_adds_suffix_and_accepts_existing_suffix(
    picker: Callable[..., FolderPickerDialog], tmp_path: Path
) -> None:
    root = tmp_path / "raiz"
    root.mkdir()
    dialog = picker(start=root, file_name="fotos", file_suffix=".zip")
    assert dialog.selected_path() == root.resolve() / "fotos.zip"

    dialog.set_file_name("lote.ZIP")
    assert dialog.selected_path() == root.resolve() / "lote.ZIP"

    dialog.set_file_name("   ")
    assert "…" in dialog.destination.text()
