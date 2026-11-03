#!/usr/bin/env python3
import os, sys, time
f='/mnt/o/tij gt 1000/keycrack/rootfs/rootfs_full.img'
sz=os.path.getsize(f)
pats=[b'System.mky',b'cleanCartridge',b'LOOGAL',b'.mky',b'ExtAuth',b'EXTERNAL AUTH',b'GET CHALLENGE',b'FM1208',b'FMCOS',b'Mifare',b'MIFARE',b'RFID',b'/dev/i2c',b'AN_ARM',b'EAJet',b'EAN']
res={p:[] for p in pats}
nonzero=0; ffblocks=0; zeroblocks=0; otherblocks=0; totalblocks=0
samples=[]
t0=time.time()
with open(f,'rb',buffering=0) as fh:
    pos=0
    while True:
        b=fh.read(8*1024*1024)
        if not b: break
        # pattern search
        for p in pats:
            start=0
            while True:
                i=b.find(p,start)
                if i<0: break
                if len(res[p])<200:
                    res[p].append(pos+i)
                start=i+1
        # block stats at 4K
        for off in range(0,len(b),4096):
            blk=b[off:off+4096]
            if len(blk)<4096: break
            totalblocks+=1
            s=set(blk)
            if s=={0}: zeroblocks+=1
            elif s=={255}: ffblocks+=1
            elif len(s)<=2:
                otherblocks+=1
            else:
                nonzero+=1
                if len(samples)<20:
                    samples.append((pos+off,len(s),blk[:32].hex()))
        pos+=len(b)
        if pos % (512*1024*1024) < 8*1024*1024:
            print(f"progress {pos/1e9:.2f} GB, real blocks {nonzero}", flush=True)
print('DONE size',sz,'blocks',totalblocks,'real',nonzero,'ff',ffblocks,'zero',zeroblocks,'lowuniq',otherblocks)
print('samples',samples)
for p,offs in res.items():
    print('PAT',p.decode('latin1'),'hits',len(offs),[hex(x) for x in offs[:40]])
