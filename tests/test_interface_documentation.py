from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_ddns_page_warns_against_direct_internet_access():
    template = read("templates/ddns.html")
    docs = read("docs/ddns.md")

    assert "Do not open SimpleSaferServer directly to the internet" in template
    assert "local network, or through a private VPN such as Tailscale" in template
    assert "Do not open the SimpleSaferServer web interface directly to the internet" in docs
    assert "private VPN such as Tailscale" in docs


def test_ntfs_recovery_help_is_in_drive_interfaces_and_docs():
    setup_template = read("templates/setup.html")
    drive_health_template = read("templates/drive_health.html")
    setup_docs = read("docs/setup.md")
    drive_health_docs = read("docs/drive_health.md")

    assert "SimpleSaferServer uses NTFS" in setup_template
    assert "NTFS keeps the backup drive easy to recover" in setup_template
    assert "NTFS keeps the backup drive easy to recover" in drive_health_template
    assert "common off-the-shelf recovery tools" in setup_template
    assert "common off-the-shelf recovery tools" in drive_health_template
    assert "common off-the-shelf recovery tools" in setup_docs
    assert "common off-the-shelf recovery tools" in drive_health_docs
