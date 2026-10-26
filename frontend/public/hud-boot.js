(function(){
var o=document.createElement('div');o.id='bootOv';
o.style.cssText='position:fixed;inset:0;z-index:100;background:#02080c;cursor:pointer;transition:opacity .9s';
var cv=document.createElement('canvas');cv.style.cssText='position:absolute;left:0;top:0;width:100%;height:100%';
o.appendChild(cv);document.body.appendChild(o);
var W=cv.width=innerWidth,H=cv.height=innerHeight,x=cv.getContext('2d'),u=H/1440,PI=Math.PI,TWO=PI*2,rn=Math.random;
var cmp=W/H<2.8,pw=W*(cmp?0.16:0.11),gap=W*(cmp?0.008:0.01),m=W*(cmp?0.01:0.015),top=H*0.07,h1=H*0.56,y2=top+h1+H*0.02,h2=H*0.93-y2;
var L1=m,L2=m+pw+gap,R2=W-m-pw,R1=W-m-2*pw-gap,h3=H*0.26,hcs=h3*0.88,wy=top+hcs+H*0.02,wh=2*h3-hcs,my0=wy+wh+H*0.02,mh0=H*0.93-my0;
var CX=W/2,CY=H*0.40,RS=Math.min(H*0.115,W*0.06),Rc=RS*2.1,F=H*0.9;
var CYAN='#19d3ff',ORG='#ff9a3d',DIM='rgba(150,215,235,0.6)';
var cl=function(v){return Math.max(0,Math.min(1,v))},eo=function(p){return 1-Math.pow(1-p,3)},sg=function(){return rn()<0.5?-1:1};
var parts=[],stars=[];
function P(r,a){return[Math.cos(a)*r,Math.sin(a)*r]}
function pts(r,a0,a1,n){var L=[];for(var i=0;i<=n;i++){L.push(P(r,a0+(a1-a0)*i/n))}return L}
function circ(r){return pts(r,0,TWO,72)}
function rect(a,b,w,h){return[[a,b],[a+w,b],[a+w,b+h],[a,b+h]]}
function ticks(r,n,len,every,len2){var L=[];for(var i=0;i<n;i++){var a=i*TWO/n,l=(every&&i%every==0)?len2:len;L.push([P(r,a),P(r+l,a)])}return L}
function mk(d){d.lw=d.lw||1.5;d.al=d.al==null?1:d.al;d.col=d.col||CYAN;d.sp=d.sp||0;
var sx=0,sy=0,n=0;function a(q){sx+=q[0];sy+=q[1];n++}
(d.lines||[]).forEach(function(l){l.forEach(a)});(d.polys||[]).forEach(function(g){g.pts.forEach(a)});(d.dots||[]).forEach(function(g){a([g.x,g.y])});(d.texts||[]).forEach(function(g){a([g.x,g.y])});
d.c0=n?[sx/n,sy/n]:[0,0];
var da=rn()*TWO,ds=(0.5+rn()*0.6)*(d.wing?W*0.45:W);
d.ts=d.wing?0.9+rn()*0.9:0.2+rn()*1.3;d.d=1.7;
d.ax=sg()*(1.5+rn()*2.2)*TWO;d.ay=sg()*(1.5+rn()*2.2)*TWO;d.az=sg()*(1+rn()*1.5)*TWO;
d.dx=Math.cos(da)*ds;d.dy=Math.sin(da)*ds*0.7;d.dz=F*(-0.3+rn()*1.5);
parts.push(d)}
for(var s0=0;s0<90;s0++)stars.push([rn()*TWO,rn(),rn()]);
mk({polys:[{pts:circ(Rc+20*u),col:'rgba(0,8,14,0.55)'}]});
for(var i=1;i<=10;i++)mk({lines:[circ(RS*i*0.22)],lw:1,al:0.1});
var rl=[];for(var i=0;i<24;i++)rl.push([P(RS*0.2,i*PI/12),P(Rc,i*PI/12)]);mk({lines:rl,lw:1,al:0.07});
var xl=L2+pw+30*u,xr=R1-30*u,gl=CX-Rc-60*u,gr2=CX+Rc+60*u,x0=xl+50*u,wl=CX-Rc-130*u-x0,rh=62*u,y0=CY-3*rh,x1=CX+Rc+130*u,wr=xr-50*u-x1;
if(!cmp){
mk({lines:[[[xl-CX,0],[gl-CX,0]]],lw:1,al:0.25,wing:1});mk({lines:[[[gr2-CX,0],[xr-CX,0]]],lw:1,al:0.25,wing:1});
var LN=['CPU LOAD %','GPU LOAD %','GPU POWER W','GPU TEMP C','LINK LATENCY','SYNAPSE (SIM)'],LC=['#7fdcff','#2b9bff','#ff9a3d','#ff9a3d','#3dff9a',CYAN];
LN.forEach(function(nm,k){var yy=y0+k*rh,ps=[],cnt=Math.floor(wl/(6*u)),v=0.5;
for(var i=0;i<cnt;i++){v=cl(v+(rn()-0.5)*0.35);var hh=v*(rh-28*u);ps.push({pts:rect(x0+i*6*u-CX,yy+18*u+(rh-28*u)-hh-CY,3.5*u,Math.max(1,hh)),col:LC[k],al:0.3+0.65*v})}
var tx=[{s:nm,x:x0-CX,y:yy+12*u-CY,sz:11*u,col:DIM,ta:'left'}];if(!k)tx.push({s:'CORE DIAGNOSTICS // BREATH',x:x0-CX,y:y0-16*u-CY,sz:14*u,col:CYAN,ta:'left'});
var bl=[[x0-CX,yy+rh-5*u-CY],[x0+wl-CX,yy+rh-5*u-CY]];bl.al=0.3;
mk({polys:ps,texts:tx,lines:[bl],col:LC[k],lw:1,wing:1})});
var RN=['CPU FAN','PUMP FAN','GPU FAN','SYSTEM FAN #1','SYSTEM FAN #2','SYSTEM FAN #3'];
RN.forEach(function(nm,k){var yy=y0+k*rh,col=k%2?ORG:'#2b9bff',vv=0.3+rn()*0.6;
var tx=[{s:nm,x:x1-CX,y:yy+12*u-CY,sz:11*u,col:DIM,ta:'left'}];if(!k)tx.push({s:'FAN SPEEDS // LIVE',x:x1-CX,y:y0-16*u-CY,sz:14*u,col:CYAN,ta:'left'});
mk({polys:[{pts:rect(x1-CX,yy+20*u-CY,wr,10*u),col:col,al:0.25},{pts:rect(x1-CX,yy+20*u-CY,wr*vv,10*u),col:col,al:0.9}],texts:tx,wing:1})})}
mk({lines:[circ(Rc)],lw:1.5,glow:1});mk({lines:[circ(Rc+22*u)],lw:1.5,glow:1});
mk({lines:ticks(Rc,120,6*u,5,11*u),lw:1.5,sp:0.15,glow:1});mk({lines:ticks(Rc,12,18*u,0,0),lw:2,sp:0.15,glow:1});
['E','S','W','N'].forEach(function(ch,k){var a=k*PI/2,q=P(Rc+44*u,a);mk({texts:[{s:ch,x:q[0],y:q[1]+5*u,sz:16*u,col:CYAN,rt:a+PI/2}]})});
var dg=[];for(var k=0;k<12;k++){if(k%3==0)continue;var a=k*PI/6,q=P(Rc+40*u,a);dg.push({s:String((k*30+90)%360).padStart(3,'0'),x:q[0],y:q[1]+4*u,sz:11*u,col:DIM,rt:a+PI/2})}mk({texts:dg});
mk({polys:[{pts:[[-8*u,-Rc-40*u],[8*u,-Rc-40*u],[0,-Rc-26*u]]}],texts:[{s:'HDG 000',x:0,y:-Rc-52*u,sz:15*u,col:CYAN}]});
var bz=[];for(var i=0;i<40;i++){var a=i*TWO/40,l=0.08+0.05*Math.sin(i*2.3);bz.push(pts(Rc-16*u,a,a+l,6))}
mk({lines:bz,col:'rgb(200,225,240)',lw:9,al:0.28,sp:-0.22});
mk({lines:[circ(Rc-30*u)],lw:1,al:0.5});mk({lines:ticks(Rc-30*u,180,-6*u,0,0),lw:1,al:0.45,sp:-0.3});
for(var i=0;i<3;i++)mk({lines:[pts(Rc-16*u,i*2.094,i*2.094+0.35,8)],lw:9,al:0.95,glow:1,sp:0.5});
for(var sd=0;sd<2;sd++)for(var k=0;k<4;k++){var r0=RS*(1.45+k*0.12),bl=[];
for(var i=0;i<44;i++){var a=(i/43-0.5)*1.7+sd*PI,v=0.25+rn()*0.65,l=[P(r0,a),P(r0+RS*0.015+v*RS*0.085,a)];
l.col=sd?(v>0.9?'#ff4d4d':'#ff9a3d'):(v>0.9?'#3dff9a':'#2b9bff');bl.push(l)}
mk({lines:bl,lw:5-k*0.7,dash:[3*u,2*u]})}
[['GPU',0.6,'#ff9a3d'],['VRAM',0.7,'#ff4d4d'],['CPU',0.3,'#ffd24a']].forEach(function(dd,k){var c=P(RS*1.64,PI/2+(k-1)*0.3);
var mv=function(q){return[q[0]+c[0],q[1]+c[1]]},ring=pts(15*u,0,TWO,24).map(mv),ark=pts(15*u,-PI/2,-PI/2+TWO*dd[1],18).map(mv);ring.al=0.25;
mk({upd:function(){var hh=(typeof hw!=='undefined')?hw:null,gg=hh&&hh.gpu,v=dd[1];if(gg){v=k==0?gg.load/100:k==1?gg.mem_used/gg.mem_total:(hh.cpu_load||0)/100}v=cl(v||0);this.lines[1]=pts(15*u,-PI/2,-PI/2+TWO*v,18).map(mv);this.texts[1].s=Math.round(v*100)+'%'},lines:[ring,ark],col:dd[2],lw:5,glow:1,dots:[{x:c[0],y:c[1],r:5*u,col:dd[2]}],texts:[{s:dd[0],x:c[0],y:c[1]+34*u,sz:10*u,col:dd[2]},{s:Math.round(dd[1]*100)+'%',x:c[0],y:c[1]+47*u,sz:10*u,col:DIM}]})});
var cv3=[];for(var k=0;k<3;k++){var a=-PI/2+(k-1)*0.3,c=P(RS*1.64,a),ca=Math.cos(a+PI/2),sa=Math.sin(a+PI/2);
cv3.push({pts:[[-7*u,-6*u],[7*u,-6*u],[0,8*u]].map(function(q){return[c[0]+q[0]*ca-q[1]*sa,c[1]+q[0]*sa+q[1]*ca]}),al:0.8})}
mk({polys:cv3});
mk({lines:[circ(RS*1.38)],lw:2,glow:1,dash:[6*u,10*u],sp:0.3});
for(var i=0;i<3;i++)mk({lines:[pts(RS*1.30,i*2.094,i*2.094+1.3,10)],lw:4,glow:1,sp:0.5});
mk({lines:[circ(RS*1.22)],lw:1,al:0.6});mk({lines:ticks(RS*1.22,90,-5*u,0,0),lw:1,al:0.7,sp:-0.45});
for(var i=0;i<3;i++)mk({lines:[pts(RS*1.14,i*2.094,i*2.094+0.9,8)],lw:3,glow:1,sp:-0.6});
var sp2=[];for(var i=0;i<96;i++){var a=i/96*TWO-PI/2;sp2.push([P(RS*0.86,a),P(RS*0.86+RS*0.05+rn()*RS*0.12,a)])}
mk({lines:sp2,lw:2});mk({lines:[circ(RS*0.82)],lw:3,glow:1});
mk({lines:[pts(RS*0.74,0,TWO,6)],lw:2,sp:0.2});mk({lines:[pts(RS*0.74,PI/6,PI/6+TWO,6)],lw:2,sp:-0.2});
mk({lines:[pts(RS*0.58,0,TWO,3)],lw:1.5,sp:0.3});mk({lines:[pts(RS*0.58,PI/3,PI/3+TWO,3)],lw:1.5,sp:-0.3});
mk({lines:[pts(RS*0.66,PI/4,PI/4+TWO,4)],lw:1.2,sp:0.25});mk({lines:[circ(RS*0.64)],lw:1.8});mk({lines:[pts(RS*0.45,0,4,24)],lw:1.8,sp:1.2});
for(var k=0;k<7;k++){var rr=RS*(0.3+k*0.07),dir=k%2?-1:1,dt=[];for(var j=0;j<10;j++){var q=P(rr,-dir*j*0.07);dt.push({x:q[0],y:q[1],r:Math.max(0.5,3.2-j*0.25)*u,al:1-j/10,col:k%3==0?ORG:CYAN})}
mk({dots:dt,sp:dir*1000/(700+k*180)*0.5})}
mk({lines:[pts(RS*0.26,0,2,14)],col:ORG,lw:5,glow:1,sp:1.4});mk({lines:[pts(RS*0.26,PI,PI+2,14)],col:ORG,lw:5,glow:1,sp:1.4});mk({lines:[pts(RS*0.2,0,4,20)],col:'#ff4d4d',lw:3,glow:1,sp:-1});
mk({lines:[circ(RS*0.3)],lw:2,al:0.5});mk({lines:[circ(RS*0.55)],lw:2,al:0.3});mk({lines:[circ(RS*0.8)],lw:2,al:0.15});
mk({lines:[[[-RS*0.8,0],[-RS*0.3,0]],[[RS*0.3,0],[RS*0.8,0]],[[0,-RS*0.8],[0,-RS*0.3]],[[0,RS*0.3],[0,RS*0.8]]],lw:1.5});
var st=['HELPER 8765 ... CHECKING','MODEL ... CHECKING','SERVER 8000 ... CHECKING','GPU ... CHECKING'];
fetch('http://127.0.0.1:8765').then(function(r){return r.json()}).then(function(j){st[0]='HELPER 8765 ... OK';st[1]=j.model?'MODEL '+String(j.model).slice(0,28)+' ... LOADED':'MODEL ... NONE LOADED';st[3]=(j.gpu&&j.gpu.name)?'GPU '+String(j.gpu.name).replace('NVIDIA GeForce ','').slice(0,24)+' ... OK':'GPU ... NOT FOUND'}).catch(function(){st[0]='HELPER 8765 ... OFFLINE';st[1]='MODEL ... UNKNOWN';st[3]='GPU ... UNKNOWN'});
fetch('/v1/telemetry/stats').then(function(r){st[2]='SERVER 8000 ... '+(r.ok?'OK':'ERROR')}).catch(function(){st[2]='SERVER 8000 ... OFFLINE'});
function dp(d,t,gh){
if(t<d.ts)return;
var q=cl((t-d.ts)/d.d),e=eo(q),inv=1-e,fill=cl((t-2.4)/1);
var a=d.ax*inv,b=d.ay*inv,c=d.az*inv,ca=Math.cos(a),sa=Math.sin(a),cb=Math.cos(b),sb=Math.sin(b),cc=Math.cos(c),sc=Math.sin(c);
var spin=d.sp*Math.max(0,t-d.ts-d.d),cs=Math.cos(spin),ss=Math.sin(spin),c0=d.c0,ox=d.dx*inv,oy=d.dy*inv,oz=d.dz*inv;
function tf(pt){var X=pt[0],Y=pt[1];if(spin){var X1=X*cs-Y*ss;Y=X*ss+Y*cs;X=X1}
var rx=X-c0[0],ry=Y-c0[1],y1=ry*ca,z1=ry*sa,x2=rx*cb+z1*sb,z2=-rx*sb+z1*cb,x3=x2*cc-y1*sc,y3=x2*sc+y1*cc;
var k=F/Math.max(F*0.15,F+z2+oz);return[CX+(c0[0]+x3+ox)*k,CY+(c0[1]+y3+oy)*k,k]}
var al=Math.min(1,q*4)*(0.35+0.65*fill)*(gh?0.2:1),lwk=0.4+0.6*fill;
x.setLineDash(d.dash||[]);x.lineWidth=d.lw*u*lwk;
if(d.glow&&fill>0.5&&!gh){x.shadowColor=d.col;x.shadowBlur=10*u}else x.shadowBlur=0;
function path(pl){x.beginPath();pl.forEach(function(p,i){var s=tf(p);i?x.lineTo(s[0],s[1]):x.moveTo(s[0],s[1])})}
x.strokeStyle=d.col;x.globalAlpha=al*d.al;x.beginPath();var any=false;
(d.lines||[]).forEach(function(pl){if(pl.col||pl.al!=null)return;pl.forEach(function(p,i){var s=tf(p);i?x.lineTo(s[0],s[1]):x.moveTo(s[0],s[1])});any=true});
if(any)x.stroke();
(d.lines||[]).forEach(function(pl){if(!(pl.col||pl.al!=null))return;x.strokeStyle=pl.col||d.col;x.globalAlpha=al*d.al*(pl.al!=null?pl.al:1);path(pl);x.stroke()});
x.setLineDash([]);if(gh){x.shadowBlur=0;return}
x.shadowBlur=0;
(d.polys||[]).forEach(function(g){path(g.pts);x.closePath();
if(fill>0){x.globalAlpha=al*(g.al!=null?g.al:d.al)*fill;x.fillStyle=g.col||d.col;x.fill()}
if(fill<1){x.globalAlpha=al*0.6*(1-fill);x.strokeStyle=(g.col&&g.col.charAt(0)=='#')?g.col:CYAN;x.lineWidth=u;x.stroke()}});
(d.dots||[]).forEach(function(g){var s=tf([g.x,g.y]);x.globalAlpha=al*(g.al!=null?g.al:1);x.fillStyle=g.col||d.col;x.beginPath();x.arc(s[0],s[1],Math.max(0.5,g.r*s[2]),0,TWO);x.fill()});
(d.texts||[]).forEach(function(g){var s=tf([g.x,g.y]);x.globalAlpha=al*(0.2+0.8*fill);x.fillStyle=g.col||d.col;x.font=Math.max(4,g.sz*s[2])+'px Consolas,monospace';x.textAlign=g.ta||'center';
if(g.rt!=null){x.save();x.translate(s[0],s[1]);x.rotate(g.rt);x.fillText(dec(g.s,t,d.ts+d.d,0.9),0,0);x.restore()}else x.fillText(dec(g.s,t,d.ts+d.d,0.9),s[0],s[1])})}
function title(al){x.globalAlpha=al;var ty=H*0.04;x.font=(36*u)+'px Consolas,monospace';x.textAlign='center';x.fillStyle=ORG;x.shadowColor=ORG;x.shadowBlur=14*u;x.fillText('J . A . R . V . I . S .',CX,ty);x.shadowBlur=0;
var ws=['Just','A','Really','Very','Intelligent','System'],sz=9*u,pp=[];ws.forEach(function(w,i){pp.push([true,w[0]]);pp.push([false,w.slice(1)+(i<5?' ':'')])});
var fnt=function(b){return(b?'bold ':'')+sz+'px Consolas,monospace'},sw=0;pp.forEach(function(q){x.font=fnt(q[0]);sw+=x.measureText(q[1]).width});
var px=CX-sw/2;x.textAlign='left';x.fillStyle='rgba(255,154,61,.85)';pp.forEach(function(q){x.font=fnt(q[0]);x.fillText(q[1],px,ty+47*u);px+=x.measureText(q[1]).width});
x.textAlign='center';x.font=(9*u)+'px Consolas,monospace';x.fillStyle='rgba(180,230,255,.6)';x.fillText('customized by Chris',CX,ty+59*u);x.globalAlpha=1}
var BX=[[L1,top,pw,h1,'HARDWARE // NVIDIA RTX 5090 + CPU'],[L2,top,pw,h1,'SYSTEM DIAGNOSTICS // TELEMETRY'],[L1,y2,pw,h2,'CORE STATUS'],[L2,y2,pw,h2,'BIOMETRIC // AUDIO'],[R1,top,pw,hcs,'CHRONO // SESSION'],[R1,wy,pw,wh,'ATMOSPHERICS'],[R1,my0,2*pw+gap,mh0,'NETWORK TRAFFIC // WORLD'],[R2,top,pw,hcs,'DATA STREAM'],[R2,wy,pw,wh,'NEURAL CORE']];
function boxesOld(t){BX.forEach(function(b,i){var w=eo(cl((t-(3.6+i*0.1))/0.45));if(w<=0)return;var bx=b[0],by=b[1],bw=b[2],bh=b[3],c=18*u;
x.save();x.beginPath();x.rect(bx-6,by-6,bw+12,(bh+12)*w);x.clip();
x.globalAlpha=1;x.fillStyle='rgba(25,211,255,0.05)';x.fillRect(bx,by,bw,bh);
x.strokeStyle=CYAN;x.lineWidth=1.5*u;x.globalAlpha=0.55;x.strokeRect(bx,by,bw,bh);
x.globalAlpha=0.95;x.lineWidth=3*u;x.beginPath();
x.moveTo(bx,by+c);x.lineTo(bx,by);x.lineTo(bx+c,by);x.moveTo(bx+bw-c,by);x.lineTo(bx+bw,by);x.lineTo(bx+bw,by+c);
x.moveTo(bx,by+bh-c);x.lineTo(bx,by+bh);x.lineTo(bx+c,by+bh);x.moveTo(bx+bw-c,by+bh);x.lineTo(bx+bw,by+bh);x.lineTo(bx+bw,by+bh-c);x.stroke();
x.globalAlpha=0.9;x.fillStyle=CYAN;x.font=(12*u)+'px Consolas,monospace';x.textAlign='left';x.fillText(b[4],bx+14*u,by+24*u);
for(var k=0;k<Math.floor((bh-60*u)/(46*u));k++){x.globalAlpha=0.22;x.fillStyle=k%2?ORG:CYAN;x.fillRect(bx+14*u,by+48*u+k*46*u,bw*(0.3+((i*7+k*13)%50)/100),6*u)}
x.restore();
if(w<1){x.globalAlpha=0.9*(1-w);x.fillStyle=CYAN;x.fillRect(bx,by+bh*w,bw,2*u)}});x.globalAlpha=1}
function boxes(t){var c=18*u;
BX.forEach(function(b,i){var w=eo(cl((t-(3.6+i*0.1))/0.45));if(w<=0)return;var bx=b[0],by=b[1],bw=b[2],bh=b[3];
x.save();x.beginPath();x.rect(bx-6,by-6,bw+12,(bh+12)*w);x.clip();
x.strokeStyle=CYAN;x.lineWidth=1.5*u;x.globalAlpha=0.55;x.beginPath();x.moveTo(bx,by+c);x.lineTo(bx+c,by);x.lineTo(bx+bw,by);x.lineTo(bx+bw,by+bh-c);x.lineTo(bx+bw-c,by+bh);x.lineTo(bx,by+bh);x.closePath();x.stroke();
x.globalAlpha=1;x.fillStyle=CYAN;x.font=(15*u)+'px Consolas,monospace';x.textAlign='left';x.fillText(b[4],bx+28*u,by+24*u);
x.beginPath();x.moveTo(bx+28*u,by+34*u);x.lineTo(bx+bw-c,by+34*u);x.stroke();
for(var k=0;k<Math.floor((bh-70*u)/(46*u));k++){x.globalAlpha=0.15;x.fillStyle=k%2?ORG:CYAN;x.fillRect(bx+28*u,by+56*u+k*46*u,(bw-56*u)*(0.3+((i*7+k*13)%50)/100),6*u)}
x.restore();
if(w<1){x.globalAlpha=0.9*(1-w);x.fillStyle=CYAN;x.fillRect(bx,by+bh*w,bw,2*u)}});
var cw=W*(cmp?0.31:0.42),lx=CX-cw/2,lh=H*(cmp?0.20:0.195),lb=H*(cmp?0.075:0.06),ly=H-lb-lh;
var w1=eo(cl((t-4.5)/0.45));
if(w1>0){x.save();x.beginPath();x.rect(lx-4,ly+lh+4-(lh+8)*w1,cw+8,(lh+8)*w1);x.clip();
x.globalAlpha=1;x.fillStyle='rgba(0,16,26,0.65)';x.fillRect(lx,ly,cw,lh);
x.strokeStyle='rgba(25,211,255,0.3)';x.lineWidth=1;x.strokeRect(lx,ly,cw,lh);
x.fillStyle='#7fdcff';x.globalAlpha=0.4;x.font=Math.round(H*0.0125)+'px Consolas,monospace';x.textAlign='left';x.fillText('JARVIS > ONLINE',lx+W*0.01,ly+lh-H*0.012);
x.restore();
if(w1<1){x.globalAlpha=0.9*(1-w1);x.fillStyle=CYAN;x.fillRect(lx,ly+lh-lh*w1-2*u,cw,2*u)}}
var bhh=H*0.036,bb=H*(cmp?0.01:0.014),by2=H-bb-bhh,w2=eo(cl((t-4.7)/0.4));
if(w2>0){x.save();x.beginPath();x.rect(lx-4,by2+bhh+4-(bhh+8)*w2,cw+8,(bhh+8)*w2);x.clip();
var bs=bhh,g2=W*0.005,iw=cw-2*(bs+g2);
x.globalAlpha=1;x.fillStyle='rgba(0,16,26,0.8)';x.strokeStyle='rgba(25,211,255,0.4)';x.lineWidth=1;
x.fillRect(lx,by2,iw,bhh);x.strokeRect(lx,by2,iw,bhh);
for(var k=0;k<2;k++){var bx2=lx+iw+g2+k*(bs+g2);x.fillRect(bx2,by2,bs,bhh);x.strokeRect(bx2,by2,bs,bhh)}
x.restore()}
x.globalAlpha=1}
var GL='01ABCDEF#$%&*+<>/=?XYZ';
function dec(s,t,t0,dur){s=String(s);var p=cl((t-t0)/dur);if(p>=1)return s;var n=Math.floor(s.length*p),r=s.slice(0,n);for(var i=n;i<s.length;i++){r+=s.charAt(i)==' '?' ':GL.charAt(Math.floor(rn()*GL.length))}return r}
var BRN=[];(function(){for(var i=0;i<220;i++){var inn=i>=180,th=Math.acos(2*rn()-1),ph=rn()*TWO,rr=inn?0.35+0.35*rn():0.9+0.2*rn(),X=Math.sin(th)*Math.cos(ph)*rr*0.85,Y=Math.cos(th)*rr*0.7;if(Y<0)Y*=0.6;BRN.push([X,Y])}})();
var NM=['TOTAL_REQUESTS','PER_QUERY.COST_USD','PER_QUERY.ENERGY_J','PER_QUERY.LATENCY_S','PER_QUERY.TOKENS','BENCH_ACCURACY_PCT','LATENCY.P50','LATENCY.P95','ENERGY.TOTAL_J','GPU.UTIL_AVG','TOKENS.IN','TOKENS.OUT','TOOLS.CALLS','UPTIME_S'];
var HOMEARC=[[-74,40.7],[-0.1,51.5],[139.7,35.7],[151.2,-33.9],[-46.6,-23.5],[77.2,28.6],[18.4,-33.9],[-118.2,34.0]];
function boxes2(t){
var c=18*u,DL='rgba(180,230,255,.7)',K=0,ra=1;
function es(i,k){return 3.6+i*0.1+0.45+k*0.03}
function T(s,x0,y0,sz,col,al,i,k){var p=cl((t-es(i,k))/0.5);if(p<=0)return;x.globalAlpha=Math.min(1,p*3)*ra;x.fillStyle=col;x.font=sz+'px Consolas,monospace';x.textAlign=al||'left';x.fillText(dec(s,t,es(i,k),0.5),x0,y0)}
function BR(a,b2,w2,h2,v,col,i,k){var p=eo(cl((t-es(i,k))/0.5));if(p<=0)return;x.globalAlpha=0.12*ra;x.fillStyle='#fff';x.fillRect(a,b2,w2,h2);x.globalAlpha=0.9*ra;x.fillStyle=col;x.fillRect(a,b2,w2*v*p,h2)}
function SP(a,b2,w2,h2,col,sd,lab,val,i,k){var p=cl((t-es(i,k))/0.7);if(p<=0)return;x.globalAlpha=1;x.fillStyle='rgba(255,255,255,.04)';x.fillRect(a,b2,w2,h2);T(lab,a+6*u,b2+14*u,12*u,DL,'left',i,k);T(val,a+w2-6*u,b2+14*u,13*u,col,'right',i,k);
var n=40,m=Math.floor(n*p);x.globalAlpha=0.9;x.strokeStyle=col;x.lineWidth=1.8*u;x.beginPath();for(var j=0;j<m;j++){var v=0.5+0.3*Math.sin(j*0.5+sd)+0.12*Math.sin(j*1.7+sd*2),px=a+j/(n-1)*w2,py=b2+h2-v*(h2-22*u)-2*u;j?x.lineTo(px,py):x.moveTo(px,py)}x.stroke()}
function GA(cx,cy,r,v,lab,txt,col,i,k){var p=eo(cl((t-es(i,k))/0.6));if(p<=0)return;x.lineWidth=12*u;x.globalAlpha=1;x.strokeStyle='rgba(255,255,255,.1)';x.beginPath();x.arc(cx,cy,r,0.75*PI,2.25*PI);x.stroke();x.strokeStyle=col;x.globalAlpha=0.95;x.beginPath();x.arc(cx,cy,r,0.75*PI,(0.75+1.5*v*p)*PI);x.stroke();T(txt,cx,cy+8*u,r*0.42,col,'center',i,k);T(lab,cx,cy+r*1.2,13*u,DL,'center',i,k)}
function WV(a,b2,w2,h2,col,mode,i,k){var p=cl((t-es(i,k))/0.8);if(p<=0)return;var n=70,m=Math.floor(n*p);x.globalAlpha=0.9;x.strokeStyle=col;x.lineWidth=1.8*u;x.beginPath();for(var j=0;j<m;j++){var v=mode?0.5+0.3*Math.sin(j*0.35)*Math.sin(j*0.07):(j%18==8?0.1:j%18==9?0.95:j%18==10?0.35:0.5+0.04*Math.sin(j*1.3)),px=a+j/(n-1)*w2,py=b2+h2*(1-v);j?x.lineTo(px,py):x.moveTo(px,py)}x.stroke()}
BX.forEach(function(b,i){var w=eo(cl((t-(3.6+i*0.1))/0.45));if(w<=0)return;var bx=b[0],by=b[1],bw=b[2],bh=b[3];
x.save();x.beginPath();x.rect(bx-6,by-6,bw+12,(bh+12)*w);x.clip();
x.strokeStyle=CYAN;x.lineWidth=1.5*u;x.globalAlpha=0.55;x.beginPath();x.moveTo(bx,by+c);x.lineTo(bx+c,by);x.lineTo(bx+bw,by);x.lineTo(bx+bw,by+bh-c);x.lineTo(bx+bw-c,by+bh);x.lineTo(bx,by+bh);x.closePath();x.stroke();
x.globalAlpha=1;x.fillStyle=CYAN;x.font=(15*u)+'px Consolas,monospace';x.textAlign='left';x.fillText(dec(b[4],t,3.6+i*0.1+0.15,0.5),bx+28*u,by+24*u);
x.beginPath();x.moveTo(bx+28*u,by+34*u);x.lineTo(bx+bw-c,by+34*u);x.stroke();
x.restore();
if(w<1){x.globalAlpha=0.9*(1-w);x.fillStyle=CYAN;x.fillRect(bx,by+bh*w,bw,2*u)}
if(t<es(i,0))return;K=0;ra=1;var ix=bx+28*u,iw=bw-56*u,kk;
if(i==0){
T('LOADED MODEL',ix,by+66*u,13*u,DL,'left',i,K++);
T('AGENT  ORCHESTRATOR  //  ENGINE  LM STUDIO',ix,by+120*u,13*u,DL,'left',i,K++);
var gr=Math.min(iw/7.5,70*u),gy=by+290*u;
GA(ix+iw*0.17,gy,gr,0.3,'CPU LOAD','--%','#7fdcff',i,K++);GA(ix+iw*0.5,gy,gr,0.6,'GPU LOAD','--%',CYAN,i,K++);GA(ix+iw*0.83,gy,gr,0.45,'GPU TEMP','--C','#3dffd0',i,K++);
var vy=by+395*u;kk=K++;T('VRAM',ix,vy,13*u,DL,'left',i,kk);T('-- / -- GB',ix+iw,vy,13*u,CYAN,'right',i,kk);BR(ix,vy+8*u,iw,10*u,0.55,ORG,i,kk);
kk=K++;T('GPU POWER',ix,vy+44*u,13*u,DL,'left',i,kk);T('-- W',ix+iw,vy+44*u,13*u,CYAN,'right',i,kk);BR(ix,vy+52*u,iw,10*u,0.4,'#2b9bff',i,kk);
kk=K++;T('GPU FAN',ix,vy+88*u,13*u,DL,'left',i,kk);T('--%',ix+iw,vy+88*u,13*u,'#8aa','right',i,kk);BR(ix,vy+96*u,iw,10*u,0.3,'#3dffd0',i,kk);
var sy=vy+112*u,sh=(by+bh-sy-20*u)/4.4;
SP(ix,sy+sh*1.1,iw,sh,CYAN,1,'GPU LOAD %','--',i,K++);SP(ix,sy,iw,sh,'#7fdcff',2,'CPU LOAD %','--',i,K++);SP(ix,sy+sh*2.2,iw,sh,ORG,3,'GPU POWER W','--',i,K++);SP(ix,sy+sh*3.3,iw,sh,'#3dff9a',4,'NETWORK %','--',i,K++)}
else if(i==1){var n=Math.max(3,Math.floor((bh-70*u)/(44*u)));
for(var r=0;r<n;r++){var y=by+72*u+r*44*u;kk=K++;T(NM[r%NM.length],ix,y,12*u,DL,'left',i,kk);T('000.00',bx+bw-24*u,y,12*u,CYAN,'right',i,kk);BR(ix,y+7*u,iw,9*u,0.15+((r*37)%70)/100,r%2?ORG:'#2b9bff',i,kk)}}
else if(i==2){var rp=eo(cl((t-es(i,0))/0.5));x.globalAlpha=1;x.fillStyle='rgba(25,211,255,0.18)';x.fillRect(ix,by+50*u,iw,bh*0.36*rp);x.strokeStyle=CYAN;x.lineWidth=u;x.strokeRect(ix,by+50*u,iw,bh*0.36*rp);
T('ONLINE',bx+bw/2,by+50*u+bh*0.22,Math.min(46*u,bw/9),CYAN,'center',i,K++);T('SYSTEM ONLINE',bx+bw/2,by+50*u+bh*0.31,14*u,DL,'center',i,K++);
SP(ix,by+bh*0.5,iw,bh*0.4,'#3dff9a',5,'LINK LATENCY MS','--',i,K++)}
else if(i==3){T('EKG // MIC INPUT',ix,by+62*u,12*u,DL,'left',i,K++);WV(ix,by+70*u,iw,bh*0.3,'#3dffd0',0,i,K++);T('EEG // VOICE OUTPUT',ix,by+bh*0.55,12*u,DL,'left',i,K++);WV(ix,by+bh*0.55+8*u,iw,bh*0.3,'#7fdcff',1,i,K++)}
else if(i==4){T(new Date().toLocaleTimeString('en-GB'),ix,by+110*u,Math.min(64*u,bw/6),CYAN,'left',i,K++);
T(new Date().toLocaleDateString('en-GB',{weekday:'long',day:'2-digit',month:'long',year:'numeric'}).toUpperCase(),ix,by+142*u,15*u,DL,'left',i,K++);
T('CO2 ---.-- PPM  MAUNA LOA',ix,by+190*u,15*u,ORG,'left',i,K++);
[['SESSION','00:00'],['FPS','60'],['CPU THREADS',String(navigator.hardwareConcurrency||'-')]].forEach(function(q,r){kk=K++;T(q[0],ix,by+245*u+r*30*u,13*u,DL,'left',i,kk);T(q[1],bx+bw-24*u,by+245*u+r*30*u,13*u,CYAN,'right',i,kk)})}
else if(i==5){T('--\u00B0C',ix,by+150*u,Math.min(110*u,bw/4.2),CYAN,'left',i,K++);T('ACQUIRING SIGNAL',ix,by+190*u,22*u,ORG,'left',i,K++);T('FEELS LIKE --\u00B0C',ix,by+225*u,15*u,DL,'left',i,K++);
[['HUMIDITY  --%',262,'#2b9bff'],['WIND  -- km/h',300,'#3dff9a'],['RAIN LIKELIHOOD (TODAY)  --%',338,'#2b9bff'],['SUN LIKELIHOOD (TODAY)  --%',376,ORG]].forEach(function(q){kk=K++;T(q[0],ix,by+q[1]*u,14*u,DL,'left',i,kk);BR(ix,by+(q[1]+10)*u,iw,10*u,0.4,q[2],i,kk)})}
else if(i==6){var mx0=bx+28*u,mw=bw-56*u,LA0=84,LA1=-58,mh=Math.min(bh-60*u,mw*(LA0-LA1)/360),mwm=mh*360/(LA0-LA1),mxm=mx0+(mw-mwm)/2,mtop=by+50*u;
var pj=function(lo,la){return[mxm+(lo+180)/360*mwm,mtop+(LA0-la)/(LA0-LA1)*mh]};
var gp=cl((t-es(i,0))/0.8),a1,b1;x.strokeStyle=CYAN;x.lineWidth=u;x.globalAlpha=0.22;x.beginPath();
for(var lo=-180;lo<=180;lo+=30){a1=pj(lo,LA0);b1=pj(lo,LA1);x.moveTo(a1[0],a1[1]);x.lineTo(a1[0]+(b1[0]-a1[0])*gp,a1[1]+(b1[1]-a1[1])*gp)}
for(var la=-30;la<=60;la+=30){a1=pj(-180,la);b1=pj(180,la);x.moveTo(a1[0],a1[1]);x.lineTo(a1[0]+(b1[0]-a1[0])*gp,a1[1]+(b1[1]-a1[1])*gp)}x.stroke();
var hm=pj(13.41,52.52);
HOMEARC.forEach(function(q,j){var pa=cl((t-es(i,2)-j*0.08)/0.7);if(pa<=0)return;var e=pj(q[0],q[1]),lift=Math.min(mh*0.5,Math.hypot(e[0]-hm[0],e[1]-hm[1])*0.4+12*u),qx=(hm[0]+e[0])/2,qy=(hm[1]+e[1])/2-lift,col=j%3==0?ORG:CYAN;
x.globalAlpha=0.7;x.strokeStyle=col;x.lineWidth=1.4*u;x.beginPath();for(var s=0;s<=20;s++){var f=s/20*pa,a=1-f,px=a*a*hm[0]+2*a*f*qx+f*f*e[0],py=a*a*hm[1]+2*a*f*qy+f*f*e[1];s?x.lineTo(px,py):x.moveTo(px,py)}x.stroke();
if(pa>=1){x.globalAlpha=1;x.fillStyle=col;x.beginPath();x.arc(e[0],e[1],2.4*u,0,TWO);x.fill();var rp2=(t*0.8+j*0.3)%1;x.globalAlpha=(1-rp2)*0.9;x.strokeStyle=col;x.beginPath();x.arc(e[0],e[1],(2+rp2*8)*u,0,TWO);x.stroke()}});
x.globalAlpha=1;x.strokeStyle=ORG;x.lineWidth=2*u;x.beginPath();x.arc(hm[0],hm[1],5*u+2*u*Math.sin(t*3),0,TWO);x.stroke();T('HOME',hm[0]+9*u,hm[1]-7*u,11*u,ORG,'left',i,K++);
T('0 CONNECTIONS // 0 COUNTRIES',mx0,by+bh-120*u,12*u,CYAN,'left',i,K++)}
else if(i==7){var k2=Math.floor((bh-70*u)/(34*u));for(var r=0;r<k2;r++){var y=by+72*u+r*34*u;ra=1-r/(k2*1.3);kk=K++;T(NM[(r+3)%NM.length],ix,y,12*u,DL,'left',i,kk);T('0.00',bx+bw-24*u,y,12*u,CYAN,'right',i,kk)}ra=1}
else if(i==8){var nx=bx+bw/2,ny=by+bh*0.5,nr=Math.min(bh*0.36,bw*0.44),bp=cl((t-es(i,0))/1.2);x.globalAlpha=0.4;x.strokeStyle=CYAN;x.lineWidth=1.5*u;x.beginPath();x.arc(nx,ny,nr*1.05,0,TWO*eo(bp));x.stroke();
var cnt=Math.floor(BRN.length*bp);x.fillStyle=CYAN;for(var j=0;j<cnt;j++){x.globalAlpha=j>=180?0.95:0.6;x.fillRect(nx+BRN[j][0]*nr-u,ny+BRN[j][1]*nr-u,2*u*1.4,2*u*1.4)}
T('ACTIVITY --%',nx,by+bh-24*u,13*u,DL,'center',i,K++)}
x.globalAlpha=1});
var cw=W*(cmp?0.31:0.42),lx=CX-cw/2,lh=H*(cmp?0.20:0.195),lb=H*(cmp?0.075:0.06),ly=H-lb-lh;
var w1=eo(cl((t-4.5)/0.45));
if(w1>0){x.save();x.beginPath();x.rect(lx-4,ly+lh+4-(lh+8)*w1,cw+8,(lh+8)*w1);x.clip();
x.globalAlpha=1;x.fillStyle='rgba(0,16,26,0.65)';x.fillRect(lx,ly,cw,lh);x.strokeStyle='rgba(25,211,255,0.3)';x.lineWidth=1;x.strokeRect(lx,ly,cw,lh);x.restore();
if(w1<1){x.globalAlpha=0.9*(1-w1);x.fillStyle=CYAN;x.fillRect(lx,ly+lh-lh*w1-2*u,cw,2*u)}}
var bhh=H*0.036,bb=H*(cmp?0.01:0.014),by2=H-bb-bhh,w2=eo(cl((t-4.7)/0.4));
if(w2>0){x.save();x.beginPath();x.rect(lx-4,by2+bhh+4-(bhh+8)*w2,cw+8,(bhh+8)*w2);x.clip();
var bs=bhh,g2=W*0.005,iw2=cw-2*(bs+g2);x.globalAlpha=1;x.fillStyle='rgba(0,16,26,0.8)';x.strokeStyle='rgba(25,211,255,0.4)';x.lineWidth=1;
x.fillRect(lx,by2,iw2,bhh);x.strokeRect(lx,by2,iw2,bhh);
for(var k=0;k<2;k++){var bx2=lx+iw2+g2+k*(bs+g2);x.fillRect(bx2,by2,bs,bhh);x.strokeRect(bx2,by2,bs,bhh)}x.restore()}
if(t>5.0){x.globalAlpha=1;x.fillStyle='#7fdcff';x.font=Math.round(H*0.0125)+'px Consolas,monospace';x.textAlign='left';x.fillText(dec('JARVIS > ONLINE. ALL SYSTEMS NOMINAL.',t,5.0,1.0),lx+W*0.01,ly+lh-H*0.012)}
if(t>5.2){x.globalAlpha=0.55;x.fillStyle='#fff';x.font=Math.round(H*0.014)+'px Consolas,monospace';x.textAlign='left';x.fillText(dec('TYPE A MESSAGE...',t,5.2,0.7),lx+W*0.008,by2+bhh*0.66)}
x.globalAlpha=1}
var snap=null,bgc=null,R=[],Rl=[],RG=[],capSt=0,capN=0,mdt=null,lgn=null,bgd=null,lg=document.getElementById('log'),bar=document.getElementById('bar');
window.__rec=new Map();
if(lg){lg.style.zIndex='101';lg.style.clipPath='inset(100% 0 0 0)'}
if(bar){bar.style.zIndex='101';bar.style.clipPath='inset(100% 0 0 0)'}
(function(){var b=getComputedStyle(document.body),h=getComputedStyle(document.documentElement),s=(b.backgroundImage!='none')?b:h;bgd=document.createElement('div');bgd.style.cssText='position:absolute;left:0;top:0;width:100%;height:100%;opacity:0';bgd.style.backgroundColor=(b.backgroundColor=='rgba(0, 0, 0, 0)')?h.backgroundColor:b.backgroundColor;bgd.style.backgroundImage=s.backgroundImage;bgd.style.backgroundSize=s.backgroundSize;bgd.style.backgroundPosition=s.backgroundPosition;bgd.style.backgroundRepeat=s.backgroundRepeat;o.insertBefore(bgd,cv)})();
function grp(e){var X=e[1],Y=e[2];for(var i=0;i<BX.length;i++){var b=BX[i];if(X>=b[0]-4&&X<=b[0]+b[2]+4&&Y>=b[1]-4&&Y<=b[1]+b[3]+8)return i}
if(!cmp&&Y>=y0-40*u&&Y<=y0+6*rh+20*u&&((X<CX-Rc-70*u&&X>xl-10)||(X>CX+Rc+70*u&&X<xr+10)))return 9;return -1}
function mkbg(){var r=snap.width/W;bgc=document.createElement('canvas');bgc.width=snap.width;bgc.height=snap.height;var b=bgc.getContext('2d');b.drawImage(snap,0,0);
BX.forEach(function(q){b.clearRect((q[0]-8)*r,(q[1]-8)*r,(q[2]+16)*r,(q[3]+16)*r)});
if(!cmp)b.clearRect((xl-12)*r,(y0-60*u)*r,(xr-xl+24)*r,(6*rh+90*u)*r);
b.globalCompositeOperation='destination-out';b.beginPath();b.arc(CX*r,CY*r,(Rc+110*u)*r,0,TWO);b.fill();b.globalCompositeOperation='source-over';
b.clearRect((CX-W*0.16)*r,0,W*0.32*r,(H*0.04+80*u)*r)}
function bgl(t){var a=cl((t-3.0)/0.8);if(bgd)bgd.style.opacity=a;if(a<=0)return;x.save();x.beginPath();x.rect(0,0,W,H);BX.forEach(function(b){x.rect(b[0]-6,b[1]-6,b[2]+12,b[3]+12)});if(!cmp){var by0=y0-40*u,bh0=6*rh+60*u,bl=xl-12,br0=CX+Rc+58*u;x.rect(bl,by0,CX-Rc-58*u-bl,bh0);x.rect(br0,by0,xr+12-br0,bh0)}x.clip('evenodd');x.globalAlpha=a;var gg=x.createRadialGradient(CX,CY,0,CX,CY,Math.max(W,H)*0.6);gg.addColorStop(0,'rgba(25,211,255,0.14)');gg.addColorStop(1,'rgba(2,6,11,0)');x.fillStyle=gg;x.fillRect(0,0,W,H);x.strokeStyle='rgba(25,211,255,0.045)';x.lineWidth=1;x.beginPath();for(var gx=0;gx<W;gx+=60*u){x.moveTo(gx,0);x.lineTo(gx,H)}for(var gy=0;gy<H;gy+=60*u){x.moveTo(0,gy);x.lineTo(W,gy)}x.stroke();x.restore();x.globalAlpha=1}
function capt(t){
if(snap||capSt==3)return;
if(capSt==0){var rc0=window.__rec;if(rc0&&rc0.size){Rl=Array.from(rc0.values());rc0.clear()}
if(t>=2.4&&Rl.length){R=Rl;window.__rec=null;window.__cap=true;capSt=1;capN=0}return}
capN++;if(capN>=6){try{var rc=document.getElementById('cv');snap=document.createElement('canvas');snap.width=rc.width;snap.height=rc.height;snap.getContext('2d').drawImage(rc,0,0);RG=R.map(function(e){return[e,grp(e)]}).filter(function(q){return q[1]>=0})}catch(e){snap=null}window.__cap=false;capSt=3}}
function txs(t){RG.forEach(function(q){var e=q[0],gi=q[1],s=e[0],t1=(gi==9)?3.4:3.0+gi*0.12,st2,rv;
if(gi==9){st2=t1+0.1+Math.abs(e[1]-CX)/W*0.8;rv=true}
else{var b=BX[gi];st2=t1+0.3+cl((e[2]-b[1])/b[3])*0.6;rv=e[2]<b[1]-6+(b[3]+12)*eo(cl((t-t1)/0.45))+4}
if(t<st2||!rv)return;
if(/^\d\d:\d\d:\d\d$/.test(s))s=new Date().toLocaleTimeString('en-GB');
x.globalAlpha=Math.min(1,(t-st2)*3)*(e[6]==null?1:e[6]);x.fillStyle=e[4];x.font=e[3]+'px Consolas,monospace';x.textAlign=e[5];x.fillText(dec(s,t,st2,0.9),e[1],e[2])});x.globalAlpha=1}
var bnr=null;
function brain(t){var bb=BX[8],br=window.BR;if(!br||!br.pts||t<4.1)return;
var nx=bb[0]+bb[2]/2,ny=bb[1]+bb[3]*0.5,nr=Math.min(bb[3]*0.36,bb[2]*0.44),sc=nr*1.03;
if(!bnr)bnr=br.pts.map(function(){return[rn(),rn(),rn(),rn()]});
var base=4.2,ay=(window.BP&&window.BP.rot)||0,ca=Math.cos(ay),sa=Math.sin(ay),c3=Math.cos(0.3),s3=Math.sin(0.3),hx=bb[0]+10*u,hy=bb[1]+42*u,hw2=bb[2]-20*u,hh2=bb[3]-68*u,pr=[];
x.save();x.beginPath();x.rect(hx,hy,hw2,hh2);x.clip();x.globalCompositeOperation='lighter';
var ga=cl((t-base)/1.2),gl=x.createRadialGradient(nx,ny,0,nx,ny,sc*1.3);gl.addColorStop(0,'rgba(25,211,255,'+(0.1*ga)+')');gl.addColorStop(1,'rgba(25,211,255,0)');x.globalAlpha=1;x.fillStyle=gl;x.fillRect(hx,hy,hw2,hh2);
x.strokeStyle=CYAN;x.lineWidth=u;x.beginPath();
br.pts.forEach(function(q,i){var r4=bnr[i],pg=cl((t-base-r4[0]*0.5)/0.85),e=eo(pg),inv=1-e;
var x1=q[0]*ca+q[2]*sa,z1=-q[0]*sa+q[2]*ca,y2=q[1]*c3-z1*s3,z2=q[1]*s3+z1*c3,p=1/(1+z2*0.3),fx=nx+x1*sc*p,fy=ny-y2*sc*p;
var an=(r4[3]-0.5)*7*inv,cs=Math.cos(an),sn=Math.sin(an),gx=nx+(fx-nx)*cs-(fy-ny)*sn,gy=ny+(fx-nx)*sn+(fy-ny)*cs,sx=hx+r4[1]*hw2,sy=hy+r4[2]*hh2,X=sx*inv+gx*e,Y=sy*inv+gy*e;
pr.push([X,Y,pg]);if(pg>0&&pg<1){x.moveTo(X,Y);x.lineTo(X+(sx-X)*0.12*inv,Y+(sy-Y)*0.12*inv)}});
x.globalAlpha=0.5;x.stroke();
var ea=cl((t-base-0.8)/0.6)*0.3;
if(ea>0){x.globalAlpha=ea;x.beginPath();br.E.forEach(function(e2){var a=pr[e2[0]],b=pr[e2[1]];if(a&&b){x.moveTo(a[0],a[1]);x.lineTo(b[0],b[1])}});x.stroke()}
x.fillStyle=CYAN;
pr.forEach(function(q,i){if(q[2]<=0)return;x.globalAlpha=Math.min(1,q[2]*4)*(i>=180?1:0.75);var s=(i>=180?2.6:2.2)*u;x.fillRect(q[0]-s/2,q[1]-s/2,s,s)});
x.restore();x.globalAlpha=1}
function boxes3(t){capt(t);if(!snap)return;var r=snap.width/W;
BX.forEach(function(b,i){var w=eo(cl((t-(3.0+i*0.12))/0.45));if(w<=0)return;var sw=b[2]+12,sh=b[3]+12;x.globalAlpha=1;
if(i==8){x.save();x.beginPath();x.rect(b[0]-6,b[1]-6,sw,sh*w);x.rect(b[0]+10*u,b[1]+42*u,b[2]-20*u,b[3]-68*u);x.clip("evenodd");x.drawImage(snap,(b[0]-6)*r,(b[1]-6)*r,sw*r,sh*w*r,b[0]-6,b[1]-6,sw,sh*w);x.restore()}else x.drawImage(snap,(b[0]-6)*r,(b[1]-6)*r,sw*r,sh*w*r,b[0]-6,b[1]-6,sw,sh*w);
if(w<1){x.globalAlpha=0.9*(1-w);x.fillStyle=CYAN;x.fillRect(b[0],b[1]+b[3]*w,b[2],2*u)}});
if(!cmp){var wt=eo(cl((t-3.3)/0.7));if(wt>0){var by0=y0-40*u,bh0=6*rh+60*u,bl=xl-12,bw0=(CX-Rc-58*u)-bl,br0=CX+Rc+58*u,bw1=xr+12-br0;x.globalAlpha=1;
x.drawImage(snap,(bl+bw0*(1-wt))*r,by0*r,bw0*wt*r,bh0*r,bl+bw0*(1-wt),by0,bw0*wt,bh0);
x.drawImage(snap,br0*r,by0*r,bw1*wt*r,bh0*r,br0,by0,bw1*wt,bh0)}}
var md=window.__mapd;if(md&&md.length){if(!mdt){mdt=new Float32Array(md.length);for(var j=0;j<md.length;j++)mdt[j]=(md[j][0]+180)/360*0.9+rn()*0.4}
var b6=BX[6],w6=eo(cl((t-(3.0+6*0.12))/0.45)),m0=3.0+6*0.12+0.3,mx0=b6[0]+28*u,mw=b6[2]-56*u,LA0=84,LA1=-58,mh=Math.min(b6[3]-60*u,mw*(LA0-LA1)/360),mwm=mh*360/(LA0-LA1),mxm=mx0+(mw-mwm)/2,mtop=b6[1]+50*u,ds=1.7*u,lim=b6[1]-6+(b6[3]+12)*w6;
x.globalAlpha=0.38;x.fillStyle=CYAN;x.beginPath();
for(var j2=0;j2<md.length;j2++){if(t<m0+mdt[j2])continue;var qy=mtop+(LA0-md[j2][1])/(LA0-LA1)*mh;if(qy>lim)continue;x.rect(mxm+(md[j2][0]+180)/360*mwm,qy,ds,ds)}x.fill()}
brain(t);txs(t);
if(!done){var p1=eo(cl((t-3.0)/0.45)),p2=eo(cl((t-3.15)/0.4));
if(lg)lg.style.clipPath='inset('+(100*(1-p1)).toFixed(1)+'% 0 0 0)';
if(bar)bar.style.clipPath='inset('+(100*(1-p2)).toFixed(1)+'% 0 0 0)';
if(t>3.3){if(!lgn){lgn=[];[lg,bar].forEach(function(el){if(!el)return;var tw=document.createTreeWalker(el,NodeFilter.SHOW_TEXT),nd;while((nd=tw.nextNode())){if(nd.nodeValue.trim())lgn.push([nd,nd.nodeValue])}});var inp=bar&&bar.querySelector('input[type=text]');if(inp&&inp.placeholder)lgn.push([inp,inp.placeholder,1])}
lgn.forEach(function(q){var s2=dec(q[1],t,3.4,1.0);if(q[2])q[0].placeholder=s2;else q[0].nodeValue=s2})}}
x.globalAlpha=1}
function rst(){window.__cap=false;window.__rec=null;if(lgn)lgn.forEach(function(q){if(q[2])q[0].placeholder=q[1];else q[0].nodeValue=q[1]});lgn=[];if(lg)lg.style.clipPath='';if(bar)bar.style.clipPath='';setTimeout(function(){if(lg)lg.style.zIndex='';if(bar)bar.style.zIndex=''},600)}
function fr(t){
x.setTransform(1,0,0,1,0,0);x.shadowBlur=0;x.globalAlpha=1;x.clearRect(0,0,W,H);
bgl(t);var fo=1-cl((t-3.2)/0.6);
if(fo>0){x.fillStyle=CYAN;stars.forEach(function(s){var z=(s[2]+t*0.25)%1,rr=z*z*W*0.45*(0.3+s[1]);x.globalAlpha=fo*0.7*z;x.fillRect(CX+Math.cos(s[0])*rr,CY+Math.sin(s[0])*rr*0.6,u*(2+z*4),u*(2+z*4))})}
x.save();var zm=1.08-0.08*eo(cl((t-3.2)/0.8));x.translate(CX,CY);x.scale(zm,zm);x.translate(-CX,-CY);
parts.forEach(function(d){if(d.wing)return;if(d.upd)d.upd();if(t<d.ts+d.d){dp(d,t-0.1,true);dp(d,t-0.05,true)}dp(d,t,false)});
x.restore();x.shadowBlur=0;x.setLineDash([]);
if(t>3.1){var ca2=cl((t-3.1)/0.4),br=0.5+0.5*Math.sin((t-3.4)*7),gr=x.createRadialGradient(CX,CY,0,CX,CY,RS*0.46);
gr.addColorStop(0,'rgba(255,255,255,'+(0.6+0.2*br)*ca2+')');gr.addColorStop(0.4,'rgba(25,211,255,'+0.4*ca2+')');gr.addColorStop(1,'rgba(25,211,255,0)');
x.globalAlpha=1;x.fillStyle=gr;x.beginPath();x.arc(CX,CY,RS*0.46,0,TWO);x.fill()}
if(t>3.4){var uu=cl((t-3.4)/0.7);x.globalAlpha=(1-uu)*0.9;x.fillStyle='#fff';x.beginPath();x.arc(CX,CY,RS*0.35*(1+uu*2),0,TWO);x.fill();x.globalAlpha=1-uu;x.strokeStyle=ORG;x.lineWidth=3*u;x.beginPath();x.arc(CX,CY,RS*(0.4+uu*5),0,TWO);x.stroke()}
var fs=Math.round(14*u);x.font=fs+'px Consolas,monospace';x.textAlign='center';x.fillStyle=CYAN;
st.forEach(function(s,i){var tm=1.5+i*0.3;if(t>tm){x.globalAlpha=cl((t-tm)/0.2)*(1-cl((t-3.0)/0.3));x.fillText('> '+s,CX,CY+Rc+90*u+i*fs*1.5)}});

if(window.WEAR)window.WEAR(x,W,H);title(cl(t/0.5));boxes3(t);x.globalAlpha=1}
var t0=performance.now(),done=false;
function end(qk){if(done)return;done=true;rst();o.style.transition='opacity .4s';o.style.pointerEvents='none';o.style.opacity='0';setTimeout(function(){o.remove()},500)}
function tick(now){if(!o.isConnected)return;var t=(now-t0)/1000;fr(Math.min(t,6.2));if(t>=5.9&&!done)end(false);requestAnimationFrame(tick)}
o.addEventListener('click',function(){end(true)});
requestAnimationFrame(tick);
})();