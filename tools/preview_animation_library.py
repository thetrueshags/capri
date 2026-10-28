"""Render the imported library in the native pet widget, without desktop capture."""
from pathlib import Path
from unittest.mock import patch
import json
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw
from PySide6.QtWidgets import QApplication
from capri.companion.config import Config
from capri.companion.window import DesktopPet

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/animation-library'
OUT.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
config=Config(OUT/'fixture-profile')
config.set('quiet',True);config.set('mouse_reactions',False)
pet=DesktopPet(config);pet.timer.stop()
states=[state for state in pet.loops if not state.startswith('library:')]
contact=Image.new('RGB',(4*240,((len(states)+3)//4)*280),'#23222a')
draw=ImageDraw.Draw(contact)
report={'desktop_capture':False,'loops':{}}

def render():
    path=OUT/'render-current.png'
    assert pet.grab().save(str(path))
    with Image.open(path) as image:
        rgba=image.convert('RGBA')
    backdrop=Image.new('RGBA',rgba.size,'#23222a');backdrop.alpha_composite(rgba)
    return backdrop.convert('RGB')

for row,state in enumerate(states):
    for loop in pet.loops[state]:
        pet._target_loop=loop;pet.commit_loop(time.monotonic(),state);pet._transition=None
        frames=[];elapsed=0
        for index,duration in enumerate(loop.durations_ms):
            pet.advance_loop(pet._loop_started+elapsed/1000+.001)
            assert pet._frame_index==index,(state,loop.name,index,pet._frame_index)
            frames.append(render());elapsed+=duration
        frames[0].save(OUT/f'{state}-{loop.name}.gif',save_all=True,append_images=frames[1:],
                       duration=list(loop.durations_ms),loop=0)
        report['loops'][state+'/'+loop.name]={'frames':len(frames),'durations_ms':list(loop.durations_ms)}
    x=(row%4)*240;y=(row//4)*280
    draw.text((x+8,y+8),state,fill='white')
    thumb=frames[0].crop((20,50,260,290))
    contact.paste(thumb,(x,y+30))
contact.save(OUT/'desktop-contact.png')

# Native transition: its core-only stages must render without the old body.
pet._target_loop=pet.loops['idle'][0];pet.commit_loop(time.monotonic(),'idle')
pet.morph('working',target=(pet.x()-200,pet.y()))
transition=pet._transition;frames=[]
fixed=time.monotonic();dwell=0
clip=transition['clip']
for index,duration in enumerate(clip.durations_ms):
    progress=(dwell+duration/2)/sum(clip.durations_ms)
    transition['start']=fixed-progress*transition['duration']
    with patch('capri.companion.window.time.monotonic',return_value=fixed):
        pet.tick();frames.append(render())
    dwell+=duration
frames[0].save(OUT/'decompile-zip-recompile.gif',save_all=True,append_images=frames[1:],
               duration=[round(d*transition['duration']/clip.duration) for d in clip.durations_ms],loop=0)
strip=Image.new('RGB',(270*8,290),'#23222a')
for index,frame in enumerate(frames):strip.paste(frame,(270*index,0))
strip.save(OUT/'transition-contact.png')
report['transition']={'direction':clip.name,'frames':len(frames),'core_frames':[3,4]}
(OUT/'render-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
pet.close()
print(json.dumps({'rendered_loops':len(report['loops']),'transition_frames':len(frames),'output':str(OUT)}))
