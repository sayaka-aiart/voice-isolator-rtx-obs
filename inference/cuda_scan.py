"""FP32 stateful selective scan for the Windows RTX 4070 comparison.

No upstream source or model weights are changed. Validate against Inworld's
plain PyTorch recurrence and independent golden output before benchmarking.
"""
import json
from pathlib import Path
import torch
import triton
import triton.language as tl
from inworld.voice_isolation import scan

NATIVE=scan.selective_scan


@triton.jit
def combine(a1,b1,a2,b2):
    return a2*a1,a2*b1+b2


@triton.jit
def kernel(U,DT,A,B,C,D,Z,H,Y,LAST,L:tl.constexpr,DIM:tl.constexpr,
           N:tl.constexpr,TILE:tl.constexpr,GATED:tl.constexpr,CARRIED:tl.constexpr):
    bd=tl.program_id(0)
    batch=bd//DIM
    channel=bd%DIM
    ns=tl.arange(0,N)
    ts=tl.arange(0,TILE)
    avec=tl.load(A+channel*N+ns)
    skip=tl.load(D+channel)
    if CARRIED:
        carry=tl.load(H+bd*N+ns)
    else:
        carry=tl.full((N,),0,tl.float32)
    for start in range(tl.cdiv(L,TILE)):
        t=start*TILE+ts
        u=tl.load(U+bd*L+t,t<L,0)
        dt=tl.load(DT+bd*L+t,t<L,0)
        bv=tl.load(B+batch*L*N+ns[None,:]*L+t[:,None],t[:,None]<L,0)
        cv=tl.load(C+batch*L*N+ns[None,:]*L+t[:,None],t[:,None]<L,0)
        decay=tl.exp(dt[:,None]*avec[None,:])
        driven=(dt*u)[:,None]*bv
        pa,pb=tl.associative_scan((decay,driven),0,combine)
        states=pb+pa*carry[None,:]
        carry=tl.sum(tl.where(ts[:,None]==TILE-1,states,0),axis=0)
        out=tl.sum(states*cv,axis=1)+u*skip
        if GATED:
            z=tl.load(Z+bd*L+t,t<L,0)
            out=out*z/(1+tl.exp(-z))
        tl.store(Y+bd*L+t,out,t<L)
    tl.store(LAST+bd*N+ns,carry)


def selective_scan(u,delta,a,b,c,d,z=None,state=None):
    assert u.is_cuda and a.shape[-1]==16
    # Same input casting and output precision as the official PyTorch path.
    u,delta,b,c=(v.float().transpose(1,2).contiguous() for v in (u,delta,b,c))
    a,d=a.float().contiguous(),d.float().contiguous()
    if z is not None:
        z=z.float().transpose(1,2).contiguous()
    if state is not None:
        state=state.float().contiguous()
    batch,dim,length=u.shape
    out=torch.empty_like(u)
    last=torch.empty((batch,dim,16),device=u.device,dtype=torch.float32)
    kernel[(batch*dim,)](u,delta,a,b,c,d,u if z is None else z,
        last if state is None else state,out,last,L=length,DIM=dim,N=16,
        TILE=min(128,triton.next_power_of_2(length)),GATED=z is not None,
        CARRIED=state is not None,num_warps=4,enable_fp_fusion=False)
    return out.transpose(1,2),last


def set_backend(name):
    # RE-USE's local Mamba shim is unrelated to Inworld's optional extension.
    scan._KERNEL['scan']=None
    scan.selective_scan=selective_scan if name=='triton' else NATIVE


def validate():
    rows=[]
    torch.manual_seed(77)
    with torch.inference_mode():
        for length in [1,2,4,46,129,257]:
            batch,dim,n=2,32,16
            u=torch.randn(batch,length,dim,device='cuda')
            dt=torch.nn.functional.softplus(torch.randn_like(u)-2)
            a=-torch.rand(dim,n,device='cuda')*3
            b=torch.randn(batch,length,n,device='cuda')
            c=torch.randn_like(b)
            d=torch.randn(dim,device='cuda')
            for carried in [False,True]:
                state=torch.randn(batch,dim,n,device='cuda') if carried else None
                expected,eh=scan.selective_scan_reference(u,dt,a,b,c,d,u,state)
                actual,ah=selective_scan(u,dt,a,b,c,d,u,state)
                torch.testing.assert_close(actual,expected,atol=2e-4,rtol=3e-4)
                torch.testing.assert_close(ah,eh,atol=2e-4,rtol=3e-4)
                rows.append(dict(length=length,carried=carried,
                    max_output_error=float((actual-expected).abs().max().item()),
                    max_state_error=float((ah-eh).abs().max().item())))
        # Split-stream state must agree with a single scan over every frame.
        whole,wh=selective_scan(u,dt,a,b,c,d,u)
        one,oh=selective_scan(u[:,:17],dt[:,:17],a,b[:,:17],c[:,:17],d,u[:,:17])
        two,th=selective_scan(u[:,17:],dt[:,17:],a,b[:,17:],c[:,17:],d,u[:,17:],oh)
        torch.testing.assert_close(torch.cat([one,two],1),whole,atol=2e-4,rtol=3e-4)
        torch.testing.assert_close(th,wh,atol=2e-4,rtol=3e-4)
    return rows


if __name__=='__main__':
    rows=validate()
    print(json.dumps(rows,indent=2))
    (Path(__file__).parent/'scan_validation.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
