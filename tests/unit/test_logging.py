import logging

from backend.logging_setup import setup_logging


def _bim_handlers():
    return [h for h in logging.getLogger().handlers if getattr(h, "_bim6g", False)]


def test_file_logging_writes_message(tmp_path, clean_logging):
    log_file = tmp_path / "logs" / "app.log"
    setup_logging("INFO", log_file)
    logging.getLogger("test").info("hello-m00")
    for h in _bim_handlers():
        h.flush()
    assert "hello-m00" in log_file.read_text()


def test_setup_is_idempotent(tmp_path, clean_logging):
    setup_logging("INFO", tmp_path / "a.log")
    setup_logging("INFO", tmp_path / "a.log")
    assert len(_bim_handlers()) == 2  # console + file, not 4


def test_level_is_respected(tmp_path, clean_logging):
    log_file = tmp_path / "a.log"
    setup_logging("WARNING", log_file)
    logging.getLogger("test").info("should-not-appear")
    logging.getLogger("test").warning("should-appear")
    for h in _bim_handlers():
        h.flush()
    text = log_file.read_text()
    assert "should-appear" in text and "should-not-appear" not in text


def test_console_only_when_no_file(clean_logging):
    setup_logging("INFO", None)
    assert len(_bim_handlers()) == 1
