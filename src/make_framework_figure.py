"""Draw Figure 1 (evaluation framework). Usage: python src/make_framework_figure.py figures/fig1_framework.png"""
import sys, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Ellipse
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman", "Liberation Serif", "DejaVu Serif"]
DARK="#3A5F80"; LIGHT="#E9EDF0"; RULE="#738492"; TXT="#1f2a33"
W,H=6.25,1.72
fig=plt.figure(figsize=(W,H),dpi=250.0)
ax=fig.add_axes([0,0,1,1]); ax.set_xlim(0,W); ax.set_ylim(0,H); ax.axis("off")
TF, CF = 10.5, 9.6

def group(x,y,w,h,title,dashed=True,color=DARK):
    ax.add_patch(Rectangle((x,y),w,h,fill=False,ec=color,lw=1.1,ls=(0,(4,2.5)) if dashed else "-"))
    ax.text(x+w/2,y+h-0.13,title,ha="center",va="center",fontsize=TF,weight="bold",color=color)
def comp(x,y,w,h,text,fs=None):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0,rounding_size=0.04",fc=LIGHT,ec=DARK,lw=0.9))
    ax.text(x+w/2,y+h/2,text,ha="center",va="center",fontsize=fs or CF,color=TXT,linespacing=1.05)
arrow=dict(arrowstyle="-|>",color=DARK,lw=1.1,mutation_scale=11,shrinkA=0,shrinkB=0)
def arr(x0,y0,x1,y1): ax.annotate("",xy=(x1,y1),xytext=(x0,y0),arrowprops=arrow)

ytop, ybot = 1.64, 0.22          # main row
ymid = (ytop+ybot)/2
gap=0.16
# 1 dataset icon
x=0.06; w=0.86
cx=x+w/2; cy=ymid+0.10
from matplotlib.patches import Arc
cw,ch,ce=0.50,0.42,0.13
ax.add_patch(Rectangle((cx-cw/2,cy),cw,ch,fc="white",ec="none"))
ax.plot([cx-cw/2,cx-cw/2],[cy,cy+ch],color=DARK,lw=1.0); ax.plot([cx+cw/2,cx+cw/2],[cy,cy+ch],color=DARK,lw=1.0)
ax.add_patch(Ellipse((cx,cy+ch),cw,ce,fc="white",ec=DARK,lw=1.0))
for dy in (0.0,ch/2.6,2*ch/2.6):
    ax.add_patch(Arc((cx,cy+dy),cw,ce,theta1=180,theta2=360,ec=DARK,lw=1.0))
ax.text(cx,cy-0.25,"Natural errors\n+ human fixes",ha="center",va="center",fontsize=CF,color=TXT,linespacing=1.05)
x1=x+w
# 2 pair construction
x2=x1+gap; w2=1.30
group(x2,ybot,w2,ytop-ybot,"Pair construction")
bw=w2-0.16; bh=0.27; by=ytop-0.30
for t,h,fs in (("Inject error into\nhuman-corrected code",0.36,8.6),("Isolated-repair\nverification",0.36,8.6),("300-pair sample",0.25,None)):
    by-=h; comp(x2+0.08,by,bw,h,t,fs=fs); by-=0.06
arr(cx+0.30,cy+ch/2,x2,cy+ch/2)
# 3 LLM chip
x3=x2+w2+gap; w3=0.98
chip_w,chip_h=0.56,0.42; ccx=x3+w3/2; ccy=ymid+0.17
ax.add_patch(Rectangle((ccx-chip_w/2,ccy-chip_h/2),chip_w,chip_h,fc="white",ec=DARK,lw=1.2))
for i in range(4):
    px=ccx-chip_w/2+0.08+i*(chip_w-0.16)/3
    ax.plot([px,px],[ccy+chip_h/2,ccy+chip_h/2+0.08],color=DARK,lw=1.0)
    ax.plot([px,px],[ccy-chip_h/2,ccy-chip_h/2-0.08],color=DARK,lw=1.0)
for j in range(3):
    py=ccy-chip_h/2+0.08+j*(chip_h-0.16)/2
    ax.plot([ccx-chip_w/2-0.08,ccx-chip_w/2],[py,py],color=DARK,lw=1.0)
    ax.plot([ccx+chip_w/2,ccx+chip_w/2+0.08],[py,py],color=DARK,lw=1.0)
ax.text(ccx,ccy,"LLM",ha="center",va="center",fontsize=TF,weight="bold",color=DARK)
ax.text(ccx,ccy-0.50,"DeepSeek, Claude\nboth arms sent\nseparately",ha="center",va="center",fontsize=CF,color=TXT,linespacing=1.05)
arr(x2+w2,ymid,ccx-chip_w/2-0.10,ymid)
# 4 evaluation
x4=x3+w3+gap; w4=1.30
group(x4,ybot,w4,ytop-ybot,"Evaluation")
by=ytop-0.30
for i,t in enumerate(("AST agreement","Parsing success","Error family and line","Normalized text")):
    h=0.235; by-=h
    if i==0:
        ax.add_patch(FancyBboxPatch((x4+0.08,by),bw,h,boxstyle="round,pad=0,rounding_size=0.04",fc=DARK,ec=DARK,lw=0.9))
        ax.text(x4+0.08+bw/2,by+h/2,t,ha="center",va="center",fontsize=8.8,color="white",weight="bold")
    else:
        comp(x4+0.08,by,bw,h,t,fs=8.8)
    by-=0.05
arr(ccx+chip_w/2+0.10,ymid,x4,ymid)
# 5 statistics
x5=x4+w4+gap; w5=W-0.06-x5
group(x5,ybot,w5,ytop-ybot,"Statistics")
sbw=w5-0.16; sbh=0.42; sby=ytop-0.36-sbh
comp(x5+0.08,sby,sbw,sbh,"Exact\nMcNemar")
comp(x5+0.08,sby-0.08-sbh,sbw,sbh,"Paired\nbootstrap")
arr(x4+w4,ymid,x5,ymid)
fig.savefig(sys.argv[1],dpi=250.0)
