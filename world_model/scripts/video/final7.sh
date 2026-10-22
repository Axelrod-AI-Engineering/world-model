set -e
S=/private/tmp/claude-501/-Users-karthiksing05-Documents-Axelrod-AI-karthik-world-model/30c82e23-1d79-4de4-a5fa-fd924b15d7d1/scratchpad
V=$S/video
cd /Users/karthiksing05/Documents/Axelrod-AI/karthik-world-model
pkill -f "axelrod demo --scenario small_demo --port 8766" || true
sleep 1.5
nohup ~/.local/bin/uv run axelrod demo --scenario small_demo --port 8766 > $S/srv.log 2>&1 &
for i in $(seq 30); do curl -s -o /dev/null http://127.0.0.1:8766/ && break; sleep 1; done
env -u VIRTUAL_ENV ~/.local/bin/uv run --with "playwright==1.58.0" python $V/record7.py 4 final 7 > $V/rec7.log 2>&1
grep -i "late\|error" $V/rec7.log | head || true
cd $V && python3 edit4.py 7 final12.mp4 2>&1 | tail -4
python3 - <<PY
import subprocess, numpy as np
raw=subprocess.run(["ffmpeg","-loglevel","error","-i","$V/final12.mp4","-vf","scale=96:60,format=gray","-f","rawvideo","-"],capture_output=True).stdout
f=np.frombuffer(raw,np.uint8).reshape(-1,60,96)
g=[i for i in range(len(f)) if (np.abs(f[i,30:,40:].astype(int)-128)<6).mean()>0.9]
print("gray frames", [round(i/30,2) for i in g])
PY
