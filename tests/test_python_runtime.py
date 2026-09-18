from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch

import pytest

from agape_mainframe import python_runtime
from agape_mainframe import capabilities


def setup_function():
    python_runtime.external_python_command.cache_clear()


def teardown_function():
    python_runtime.external_python_command.cache_clear()


def test_source_pip_command_uses_current_python():
    with patch.object(python_runtime, "is_frozen", return_value=False):
        python_runtime.external_python_command.cache_clear()
        command = python_runtime.pip_install_command("example-package")
    assert command[:4] == [sys.executable, "-m", "pip", "install"]
    assert command[-1] == "example-package"


def test_frozen_pip_uses_separate_validated_python():
    completed = subprocess.CompletedProcess(
        ["/usr/bin/python3"], 0, stdout="/usr/bin/python3\n3.12.0\n", stderr=""
    )
    with patch.object(python_runtime, "is_frozen", return_value=True), \
         patch.object(python_runtime, "_candidate_commands", return_value=[["/usr/bin/python3"]]), \
         patch.object(python_runtime.subprocess, "run", return_value=completed):
        python_runtime.external_python_command.cache_clear()
        command = python_runtime.pip_install_command("schemathesis", user=True)
    assert command == [
        "/usr/bin/python3", "-m", "pip", "install", "--disable-pip-version-check", "--user", "schemathesis"
    ]


def test_frozen_pip_without_external_python_fails_cleanly():
    with patch.object(python_runtime, "is_frozen", return_value=True), \
         patch.object(python_runtime, "_candidate_commands", return_value=[]):
        python_runtime.external_python_command.cache_clear()
        with pytest.raises(RuntimeError, match="EXTERNAL_PYTHON_REQUIRED"):
            python_runtime.pip_install_command("schemathesis")


def test_frozen_capability_does_not_try_to_extend_embedded_python():
    with patch.object(capabilities, "is_frozen", return_value=True), \
         patch.object(capabilities, "record_event"):
        with pytest.raises(RuntimeError, match="PACKAGED_PIP_EXTENSION_UNSUPPORTED=playwright"):
            capabilities.install_support("pip", "playwright")
