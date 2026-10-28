"""Create a clean source ZIP from checked Git candidates, never local state."""
from pathlib import Path
import argparse
import zipfile
from check_release import ROOT,candidates,validate

parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,default=ROOT.parent/(ROOT.name+'-source.zip'))
args=parser.parse_args()
names=candidates();validate(names)
if args.output.exists():raise SystemExit('Choose a new output filename; an archive already exists.')
args.output.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
    for name in names:archive.write(ROOT/name,'capri-desktop/'+name)
print(f'Created {args.output} with {len(names)} public files.')
