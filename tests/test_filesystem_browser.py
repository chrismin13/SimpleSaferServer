from pathlib import Path

from simple_safer_server.services.filesystem_browser import list_local_path


def test_list_local_path_returns_folders_and_files(tmp_path):
    (tmp_path / "folder-b").mkdir()
    (tmp_path / "file-a.txt").write_text("data", encoding="utf-8")
    (tmp_path / "folder-a").mkdir()

    result = list_local_path(str(tmp_path))

    assert result.path == str(tmp_path)
    assert result.parent == str(Path(tmp_path).parent)
    assert result.dirs == ["folder-a", "folder-b"]
    assert result.files == ["file-a.txt"]
    assert [(entry.name, entry.type) for entry in result.entries] == [
        ("folder-a", "folder"),
        ("folder-b", "folder"),
        ("file-a.txt", "file"),
    ]


def test_list_local_path_rejects_files(tmp_path):
    file_path = tmp_path / "not-a-folder.txt"
    file_path.write_text("data", encoding="utf-8")

    try:
        list_local_path(str(file_path))
    except NotADirectoryError as exc:
        assert str(exc) == "Not a directory."
    else:
        raise AssertionError("Expected files to be rejected")


def test_list_local_path_rejects_non_string_paths():
    try:
        list_local_path(123)
    except NotADirectoryError as exc:
        assert str(exc) == "Not a directory."
    else:
        raise AssertionError("Expected non-string paths to be rejected")
