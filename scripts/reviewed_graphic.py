"""Last-resort original explanatory text graphic, not real stock or AI imagery."""
import textwrap
from pathlib import Path

def reviewed_graphic(scene,index,work,language):
    from PIL import Image,ImageDraw,ImageFont
    narration=str(scene.get("narration","")).strip()
    subject=str(scene.get("visual_subject","")).strip()
    if not narration or not subject:
        raise ValueError("No reviewed narration or subject for fallback graphic")
    path=Path(work)/f"reviewed-graphic-{index}.png"
    image=Image.new("RGB",(1080,1920),(39,38,35))
    draw=ImageDraw.Draw(image)
    font="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    def face(p,size):
        return ImageFont.truetype(p,size)
    draw.rectangle((70,125,1010,185),fill=(220,179,88))
    label="GRAFIK • KEINE REALAUFNAHME" if language=="de" else "GRAPHIC • NOT REAL FOOTAGE"
    draw.text((90,138),label,font=face(bold,29),fill=(30,29,27))
    def wrapped(value,f,limit):
        lines=[]
        for line in textwrap.wrap(value,width=limit,break_long_words=True):
            while draw.textlength(line,font=f)>900:
                cut=max(1,len(line)-1)
                while cut>1 and draw.textlength(line[:cut],font=f)>900:
                    cut-=1
                lines.append(line[:cut])
                line=line[cut:].lstrip()
            if line:
                lines.append(line)
        return lines
    title=wrapped(subject.upper(),face(bold,62),22)[:3]
    for i,line in enumerate(title):
        draw.text((90,270+i*83),line,font=face(bold,62),fill=(247,241,225))
    draw.line((90,540,990,540),fill=(220,179,88),width=4)
    # No invented facts: excerpt comes from the actual reviewed speech.
    body=wrapped(narration,face(font,46),34)[:6]
    for i,line in enumerate(body):
        draw.text((90,600+i*65),line,font=face(font,46),fill=(247,241,225))
    # Leave the locked active-word caption band free.
    image.save(path)
    return path,{"source":"original-reviewed-text-graphic","id":str(index),
                 "media_type":"illustration","visual_check":"not_real_footage",
                 "visual_role":"last_resort","source_reviewed_narration":True}
