#!/usr/bin/env bash
set +e
R='/mnt/o/tij gt 1000/keycrack/rootfs/rootfs_full.img'
B='/mnt/o/tij gt 1000/balea'
python3 - "$R" "$B" <<'PY'
import sys,os,hashlib
R,B=sys.argv[1],sys.argv[2]
p7=143360*512
print('p7 byte offset',p7,hex(p7))
# compare e00[73.4MB:256MB] with rootfs[0:182.6MB]
def h(fn,off,size):
    m=hashlib.md5()
    with open(fn,'rb') as f:
        f.seek(off)
        left=size
        while left>0:
            b=f.read(min(8*1024*1024,left))
            if not b: break
            m.update(b); left-=len(b)
    return m.hexdigest(), size-left
for i,name in enumerate(['e00.bin','e01.bin','e02.bin','e03.bin','e04.bin','e05.bin','e06.bin','e07.bin']):
    fn=os.path.join(B,'New folder',name)
    sz=os.path.getsize(fn)
    roff=i*sz
    if i==0:
        eoff=p7; rstart=0; size=sz-p7
    else:
        eoff=0; rstart=roff; size=sz
    if rstart+size>os.path.getsize(R):
        size=os.path.getsize(R)-rstart
    h1,n1=h(fn,eoff,size)
    h2,n2=h(R,rstart,size)
    print(f'{name}: eMMC {i*256}MB.. eoff {eoff} rstart {rstart} size {size}  e={h1[:12]} r={h2[:12]}  MATCH={h1==h2}')
# per-1MB match map for first 768MB
print('--- per 16MB block compare rootfs vs concatenated eMMC ---')
def read(fn,off,size):
    with open(fn,'rb') as f:
        f.seek(off); return f.read(size)
for mb in range(0,768,16):
    rstart=mb*1024*1024
    eabs=p7+rstart
    chunk=16*1024*1024
    # find which e dump
    i=eabs//(256*1024*1024)
    if i>7: break
    eoff=eabs-i*256*1024*1024
    fn=os.path.join(B,'New folder',f'e0{i}.bin')
    try:
        a=read(R,rstart,chunk); b=read(fn,eoff,chunk)
    except Exception as e:
        print(mb,'ERR',e); continue
    same=a==b
    # count nonzero
    nz=sum(1 for x in b if x not in (0,255))
    print(f'{mb:4d}MB r={rstart//1048576:4d} e0{i} eoff={eoff//1048576:3d}MB same={same} e_nonzero={nz}')
PY
echo DONE
