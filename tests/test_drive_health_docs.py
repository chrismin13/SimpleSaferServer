"""Verify drive_health.md references the correct Samba config paths for managed shares."""

from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
DRIVE_HEALTH_MD = DOCS_DIR / "drive_health.md"


def _manual_recovery_section():
    """Return the Manual Recovery section text from drive_health.md."""
    content = DRIVE_HEALTH_MD.read_text()
    marker = "## Manual Recovery"
    start = content.index(marker)
    # Find the next H2 or end of file
    next_h2 = content.find("\n## ", start + len(marker))
    if next_h2 == -1:
        return content[start:]
    return content[start:next_h2]


def test_manual_recovery_references_sss_shares_file():
    section = _manual_recovery_section()
    assert "/etc/samba/simple_safer_server_shares.conf" in section


def test_manual_recovery_references_network_file_sharing_page():
    section = _manual_recovery_section()
    # Should point operators to the Network File Sharing docs page
    assert "network_file_sharing" in section.lower() or "Network File Sharing" in section


def test_manual_recovery_does_not_present_smb_conf_as_managed_share_config():
    section = _manual_recovery_section()
    # The "Important file locations" list should not say
    # "Samba share config: `/etc/samba/smb.conf`" as if that's where managed shares live
    assert "Samba share config: `/etc/samba/smb.conf`" not in section


def test_manual_recovery_still_mentions_smb_conf():
    section = _manual_recovery_section()
    # smb.conf should still be referenced as Samba's main config
    assert "/etc/samba/smb.conf" in section
