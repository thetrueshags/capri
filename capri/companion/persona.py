"""Keep each user's seed prompt in their private, ignored profile directory."""
from pathlib import Path

def ensure_persona(directory):
    path=Path(directory)/'persona.txt'
    template=Path(__file__).resolve().parents[2]/'persona.template.txt'
    if not path.exists():
        contents=template.read_bytes() if template.exists() else b''
        try:
            with path.open('xb') as output:output.write(contents)
        except FileExistsError:
            pass
    return path

def load_persona(config):
    return ensure_persona(config.directory).read_text(encoding='utf-8-sig')
