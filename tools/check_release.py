"""Check Git's public file candidates without reading ignored local profiles."""
from pathlib import Path
import json
import math
import re
import struct
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def candidates():
    result=subprocess.run(['git','-C',str(ROOT),'ls-files','-z','--cached','--others',
        '--exclude-standard'],capture_output=True)
    if result.returncode:
        raise SystemExit('Release checks require Git and a checkout. For an extracted source ZIP, run git init first.')
    return sorted(set(name for name in result.stdout.decode('utf-8').split('\0') if name))

def validate(names):
    errors=[]
    template=ROOT/'persona.template.txt'
    if not template.exists() or template.read_bytes()!=b'':errors.append('Public persona.template.txt must be empty')
    if 'persona.template.txt' not in names:errors.append('Blank template is missing from public candidates')
    for name in names:
        relative=Path(name);path=ROOT/relative
        lowered={part.lower() for part in relative.parts}
        if lowered.intersection({'data','evidence','.venv','__pycache__','.cache','.git'}):
            errors.append('Local-only path included: '+name)
        if path.name.lower() in ('persona.txt','behavior-profile.json','config.json'):
            errors.append('Private profile file included: '+name)
        if path.suffix.lower() in ('.sqlite','.sqlite3','.db','.log','.lnk','.zip') or path.name.startswith('.env'):
            errors.append('Local state/archive included: '+name)
        if not path.is_file():
            errors.append('Missing candidate: '+name);continue
        if path.suffix.lower() in ('.py','.ps1','.cmd','.md','.txt','.json','.yml'):
            text=path.read_text(encoding='utf-8-sig')
            if re.search(r'[A-Za-z]:[\\/](?:Users|capri-pet-work)[\\/]',text,re.I):
                errors.append('Machine-specific user/development path: '+name)
            if '-----BEGIN '+'PRIVATE KEY-----' in text:
                errors.append('Private key marker: '+name)
    folder=ROOT/'assets/companion'
    for manifest in ('animations.json','transitions.json'):
        value=json.loads((folder/manifest).read_text(encoding='utf-8'))
        clips=[clip for items in value.values() for clip in items] if manifest=='animations.json' else list(value.values())
        for clip in clips:
            frames=clip['frames'];durations=clip['durations_ms']
            if len(frames)<2 or len(frames)!=len(durations) or any(
                isinstance(t,bool) or not isinstance(t,(int,float)) or not math.isfinite(t) or t<=0 for t in durations):
                errors.append('Invalid frame timings: '+clip['name'])
            for filename in frames:
                path=(folder/filename).resolve()
                if not path.is_relative_to(folder.resolve()) or not path.is_file():
                    errors.append('Invalid animation path: '+filename);continue
                if path.relative_to(ROOT).as_posix() not in names:
                    errors.append('Animation frame excluded from release: '+filename)
                header=path.read_bytes()[:24]
                if header[:8]!=b'\x89PNG\r\n\x1a\n' or struct.unpack('>II',header[16:24])!=(192,208):
                    errors.append('Unexpected frame canvas: '+filename)
    if errors:raise ValueError('\n'.join(sorted(set(errors))))

def main():
    names=candidates();validate(names)
    print(f'Release check passed: {len(names)} public files, blank seed template, valid runtime artwork.')

if __name__=='__main__':main()
