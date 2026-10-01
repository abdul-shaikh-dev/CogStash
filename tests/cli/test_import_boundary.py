from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_cogstash_cli_imports_without_gui_dependencies(tmp_path):
    script = tmp_path / "import_cli.py"
    script.write_text(
        "import builtins\n"
        "import json\n"
        "from pathlib import Path\n"
        "import sys\n"
        "blocked = {'tkinter', 'pystray', 'PIL', 'Pillow', 'PySide6'}\n"
        "orig = builtins.__import__\n"
        "def guarded(name, *args, **kwargs):\n"
        "    if name.split('.')[0] in blocked:\n"
        "        raise AssertionError(f'unexpected GUI import: {name}')\n"
        "    return orig(name, *args, **kwargs)\n"
        "builtins.__import__ = guarded\n"
        "import cogstash.cli as cli\n"
        "json.dump(\n"
        "    {\n"
        "        'is_package': cli.__spec__.submodule_search_locations is not None,\n"
        "        'module_file': str(Path(cli.__file__).resolve()),\n"
        "    },\n"
        "    sys.stdout,\n"
        ")\n",
        encoding="utf-8",
    )
    result = subprocess.run([sys.executable, str(script)], check=True, capture_output=True, text=True)

    payload = json.loads(result.stdout)
    module_file = Path(payload["module_file"])

    assert payload["is_package"] is True
    assert module_file.name == "__init__.py"
    assert module_file.parent.name == "cli"
