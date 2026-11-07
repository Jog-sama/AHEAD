from scripts.upgrade_existing import rollback, upgrade


def test_upgrade_preserves_hardware_credentials_and_rolls_back(tmp_path):
    src = tmp_path / "update"
    target = tmp_path / "working"
    for root in [src, target]:
        for name in [
            "backend/app.py",
            "backend/device.py",
            "web/app.js",
            "firmware/device.ino",
            ".env",
            "certs/server.pem",
        ]:
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(root.name)
    (src / "backend/new.py").write_text("new")
    backup = upgrade(src, target)
    assert (target / "backend/app.py").read_text() == "update"
    for name in ["firmware/device.ino", ".env", "certs/server.pem"]:
        assert (target / name).read_text() == "working"
    rollback(backup)
    assert (target / "backend/app.py").read_text() == "working"
    assert not (target / "backend/new.py").exists()
