# -*- coding: utf-8 -*-
"""Testai: python -m unittest (paleisti iš programos aplanko)."""
import contextlib
import io
import os
import shutil
import tempfile
import urllib.request


def _no_network(req, *a, **kw):
    url = getattr(req, "full_url", req)
    raise AssertionError(f"testai neturi kreiptis į tinklą: {url}")


# Apsauga: testas, netyčia pasiekęs tikrą šaltinį, iš karto krenta (o ne laukia ar apkrauna registrą)
urllib.request.urlopen = _no_network


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
