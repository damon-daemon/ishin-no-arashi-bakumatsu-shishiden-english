# pens.py <file> <base> [lo hi]: every call of the pen setter 0x800a3ef0 with its constant x / y and the
# string or format address used by the next print call
import struct,sys
f,base=sys.argv[1],int(sys.argv[2],16)
d=open(f,'rb').read()
if f.endswith('.44'): d=d[0x800:]
lo=int(sys.argv[3],16) if len(sys.argv)>3 else base; hi=int(sys.argv[4],16) if len(sys.argv)>4 else base+len(d)
W=lambda a: struct.unpack_from('<I',d,a-base)[0]
def strat(a):
    try:
        o=a-base; return d[o:d.index(b'\0',o)].decode('cp932','replace')[:24]
    except Exception: return '?'
a=lo&~3
while a<hi-8:
    if W(a)==0x0c028fbc:
        x=y=None
        for b in (a-12,a-8,a-4,a+4):
            w=W(b)
            if w>>16==0x2404: x=w&0xffff
            if w>>16==0x2405: y=w&0xffff
            if w==0x00802821: y='=x'
        # next string: lui a1 / addiu a1 within 10 words
        s=''
        for b in range(a+8,a+48,4):
            w=W(b)
            if w>>16 in (0x24a5,0x2484,0x2631,0x2610) and (w&0x8000):
                for hi16 in (0x8016,0x8002,0x8003,0x8004,0x801e):
                    t=(hi16<<16)+(w&0xffff)-0x10000
                    if base<=t<base+len(d): s='%08x %r'%(t,strat(t)); break
                break
            if w==0x0c028fbc: break
        print('%08x x=%s y=%s %s'%(a,x if x is None or isinstance(x,str) else hex(x),y if y is None or isinstance(y,str) else hex(y),s))
    a+=4
