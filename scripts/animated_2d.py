"""Original 2D animation renderer. No still photographs, stock footage, or paid API."""
import math
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw

W,H,FPS=540,960,12

def make_scene(topic, path, scene=0, duration=9):
    octopus=any(w in topic.lower() for w in ("octopus","oktopus","oktopusse","kraken"))
    frames=int(duration*FPS)
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-y","-f","rawvideo",
         "-pixel_format","rgb24","-video_size",f"{W}x{H}","-framerate",str(FPS),
         "-i","-","-an","-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p",str(path)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for i in range(frames):
            t=i/FPS
            im=Image.new("RGB",(W,H),(5,30,54))
            d=ImageDraw.Draw(im)
            for j in range(14):
                y=int(j*75+18*math.sin(t*.6+j*.4))
                d.line((0,y,W,y-30),fill=(9,47+j,73+j),width=2)
            for j in range(18):
                x=int((j*73+scene*51+25*math.sin(j))%W)
                y=int((H-(j*137+t*(24+j%5*7))%1100))
                radius=3+j%6
                d.ellipse((x-radius,y-radius,x+radius,y+radius),outline=(75,155,182),width=2)
            if octopus:
                cx=270+35*math.sin(t*.7+scene)
                cy=465+35*math.cos(t*.8+scene)
                for arm in range(8):
                    pts=[]
                    for k in range(25):
                        a=(arm/8)*math.tau
                        dist=k*9
                        pts.append((cx+math.cos(a)*dist+20*math.sin(t*2+k*.28+arm),
                                    cy+math.sin(a)*dist+15*math.cos(t*1.7+k*.3+arm)))
                    d.line(pts,fill=(190,79+scene*15%70,115),width=20,joint="curve")
                    for x,y in pts[4::5]:
                        d.ellipse((x-3,y-3,x+3,y+3),fill=(242,176,188))
                d.ellipse((cx-95,cy-125,cx+95,cy+70),fill=(214,101,140))
                for ex in (-35,35):
                    d.ellipse((cx+ex-14,cy-30,cx+ex+14,cy+4),fill="white")
                    d.ellipse((cx+ex-5,cy-20,cx+ex+7,cy-5),fill=(13,32,45))
                if scene%2==1:
                    for j in range(3):
                        hx=160+j*110
                        hy=260+12*math.sin(t*4+j)
                        s=12+5*math.sin(t*6+j)
                        d.ellipse((hx-s,hy-s,hx+s,hy+s),fill=(244,60,92))
            else:
                # Generic animated scientific infographic, never a blank color screen.
                for j in range(5):
                    a=t*(.4+j*.13)+j*math.tau/5
                    x=270+175*math.cos(a)
                    y=455+210*math.sin(a)
                    r=24+5*math.sin(t*3+j)
                    d.ellipse((x-r,y-r,x+r,y+r),fill=(45+j*24,165-j*14,213-j*10))
                    d.line((270,455,x,y),fill=(47,115,154),width=5)
                d.ellipse((195,380,345,530),fill=(38,180,215))
                d.ellipse((215,400,325,510),outline=(195,245,255),width=8)
            proc.stdin.write(im.tobytes())
        proc.stdin.close()
        err=proc.stderr.read().decode(errors="replace")
        if proc.wait()!=0: raise RuntimeError(err[-1000:])
    except Exception:
        proc.kill()
        raise
    if not Path(path).exists() or Path(path).stat().st_size<15000:
        raise RuntimeError("2D scene output missing")
    return str(path)

if __name__=="__main__":
    make_scene(sys.argv[1],sys.argv[2],int(sys.argv[3]) if len(sys.argv)>3 else 0)
