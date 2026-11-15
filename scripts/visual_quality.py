"""Check whether a rendered MP4 has real visual detail (not a flat color)."""
import subprocess

def has_visual_detail(path):
    try:
        p=subprocess.run(["ffmpeg","-v","error","-ss","5","-i",str(path),
            "-frames:v","1","-vf","scale=64:64,format=gray",
            "-f","rawvideo","-"],capture_output=True,timeout=20,check=True)
        pixels=p.stdout
        if len(pixels)!=4096: return False
        # Check center/top and bottom regions, avoiding the central subtitle line.
        samples=[pixels[y*64+x] for y in list(range(5,23))+list(range(42,59)) for x in range(4,60)]
        mean=sum(samples)/len(samples)
        variance=sum((v-mean)**2 for v in samples)/len(samples)
        print("Visual variance:",round(variance,1),flush=True)
        return variance>130
    except Exception as exc:
        print("Visual quality probe failed:",repr(exc),flush=True)
        return False
