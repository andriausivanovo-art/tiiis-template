# -*- coding: utf-8 -*-
"""Testai: python -m unittest (paleisti iš programos aplanko)."""
import contextlib
import io
import os
import shutil
import tempfile


@contextlib.contextmanager
def quiet():
    """Nuslopina komandų išvestį, kad testų rezultatai būtų skaitomi."""
    with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
        yield out


class TempDir:
    """Laikinas aplankas testui (setUp/tearDown pagalbininkas)."""

    def __init__(self):
        self.path = tempfile.mkdtemp(prefix="signalai_test_")

    def file(self, *parts):
        p = os.path.join(self.path, *parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def cleanup(self):
        shutil.rmtree(self.path, ignore_errors=True)
