/* hud-weather.js - ATMOSPHERICS "DETAILS" view: weather over the day (layout like the iOS weather app), HUD colors.
   Shown only inside the ATMOSPHERICS box. Data: Open-Meteo (public https, no key).
   Opened by the DETAILS button that hud.html draws (window.WXBTN, window.WXBOX). While open, hud.html skips the normal rows (window.WXD). */
(()=>{
'use strict';
const C1='#19d3ff',OR='#ff9a3d',RN='#2b9bff',GR='#8fe6b8',SN='#cfe8ff',CL='#8a929a',DM='rgba(127,220,255,.6)';
const MET=[['cond','CONDITIONS'],['uv','UV INDEX'],['wind','WIND'],['prec','PRECIPITATION'],['hum','HUMIDITY'],['vis','VISIBILITY'],['pres','PRESSURE']];
const S={open:false,j:null,t:0,day:-1,met:'cond',feels:false,hov:null,busy:false,err:'',geo:null,dk:''};
let H=null;
window.WXD=false;
const cfg=()=>window.HOME_CFG||(typeof HOME_CFG!=='undefined'?HOME_CFG:null);
const st=document.createElement('style');
st.textContent='#wxD{position:fixed;z-index:7;display:none;flex-direction:column;box-sizing:border-box;font-family:Consolas,monospace;color:#7fdcff;background:rgba(2,10,16,.95);border:1px solid rgba(25,211,255,.3);padding:.45em .7em;overflow:hidden;user-select:none}'+
'#wxD .days{display:flex;flex:none}#wxD .days>div{flex:1;min-width:0;text-align:center;cursor:pointer;font-size:.8em;color:rgba(127,220,255,.85)}#wxD .days b{display:block;font-weight:normal;margin-bottom:.15em}'+
'#wxD .days i{display:inline-block;font-style:normal;width:2.1em;height:2.1em;line-height:2.1em;border-radius:50%;font-size:1.1em}#wxD .days>div.on i{background:#19d3ff;color:#02060b}#wxD .days>div.ps{opacity:.45}'+
'#wxD .dl{text-align:center;font-size:.85em;padding:.25em 0 .35em;border-bottom:1px solid rgba(25,211,255,.15);flex:none}'+
'#wxD .hd{display:flex;justify-content:space-between;align-items:flex-start;margin:.35em 0 .2em;flex:none}#wxD .vv{display:flex;align-items:center;gap:.3em}'+
'#wxD .big{font-size:2.4em;color:#19d3ff;line-height:1}#wxD .sub{color:#ff9a3d;margin-top:.15em}#wxD .sm{color:rgba(127,220,255,.6);font-size:.8em;margin-top:.15em}'+
'#wxD .ctl{position:relative;display:flex;align-items:center;white-space:nowrap}#wxD .mb{cursor:pointer;border:1px solid #19d3ff;color:#19d3ff;padding:.15em .5em;font-size:.85em;background:rgba(0,16,26,.9)}'+
'#wxD .mn{position:absolute;right:0;top:120%;z-index:2;display:none;background:rgba(2,12,20,.98);border:1px solid #19d3ff;padding:.2em 0;min-width:13em}#wxD .mn div{padding:.3em .8em .3em 1.7em;cursor:pointer;position:relative;font-size:.9em}'+
'#wxD .mn div:hover{background:rgba(25,211,255,.12)}#wxD .mn div.on::before{content:"\\2713";position:absolute;left:.55em;color:#ff9a3d}#wxD .mn small{display:block;color:rgba(127,220,255,.5);font-size:.8em}'+
'#wxD .x{cursor:pointer;border:1px solid #ff9a3d;color:#ff9a3d;padding:.1em .45em;font-size:.9em;margin-left:.4em}'+
'#wxD canvas{position:static!important;inset:auto!important;transform:none!important;z-index:auto!important;pointer-events:auto!important;opacity:1!important}'+
'#wxD canvas.ch{display:block;width:100%!important;height:auto!important;flex:1 1 0;min-height:0;cursor:crosshair}'+
'#wxD .seg{display:flex;margin-top:.35em;border:1px solid rgba(25,211,255,.3);flex:none}#wxD .seg div{flex:1;text-align:center;padding:.2em;cursor:pointer;font-size:.85em}#wxD .seg div.on{background:rgba(25,211,255,.18);color:#19d3ff}'+
'#wxD .sum{flex:none;font-size:.78em;color:rgba(127,220,255,.75);margin-top:.3em}';
document.head.append(st);
const el=document.createElement('div');el.id='wxD';
el.innerHTML='<div class="days" id="wxDays"></div><div class="dl" id="wxDL"></div>'+
 '<div class="hd"><div><div class="vv"><span class="big" id="wxV">--</span><canvas id="wxI"></canvas></div><div class="sub" id="wxS"></div><div class="sm" id="wxT"></div></div>'+
 '<div class="ctl"><span class="mb" id="wxMB"></span><div class="mn" id="wxMN"></div><span class="x" id="wxX" title="Close">✕</span></div></div>'+
 '<canvas class="ch" id="wxC"></canvas><div class="seg" id="wxSeg"><div data-f="0">ACTUAL</div><div data-f="1">FEELS LIKE</div></div><div class="sum" id="wxSum"></div>';
document.body.append(el);
const $=id=>el.querySelector('#'+id);
const mb=$('wxMB'),mn=$('wxMN');
try{const m=localStorage.getItem('jvWxMet');if(m&&MET.some(x=>x[0]===m))S.met=m}catch(e){}
function menu(){mn.textContent='';MET.forEach(([k,n])=>{const o=document.createElement('div');if(k===S.met)o.className='on';o.textContent=n;
 if(k==='cond'){const s=document.createElement('small');s.textContent='TEMPERATURE · FEELS LIKE';o.append(s)}
 o.onclick=ev=>{ev.stopPropagation();S.met=k;S.hov=null;mn.style.display='none';try{localStorage.setItem('jvWxMet',k)}catch(e){}render()};mn.append(o)})}
mb.onclick=ev=>{ev.stopPropagation();menu();mn.style.display=mn.style.display==='block'?'none':'block'};
el.addEventListener('click',()=>{mn.style.display='none'});
el.querySelectorAll('#wxSeg div').forEach(d=>d.onclick=()=>{S.feels=d.dataset.f==='1';S.hov=null;render()});
$('wxX').onclick=()=>toggle(false);

/* ---------- helpers ---------- */
const hexA=(h,a)=>'rgba('+parseInt(h.slice(1,3),16)+','+parseInt(h.slice(3,5),16)+','+parseInt(h.slice(5,7),16)+','+a+')';
const WM=c=>{try{if(typeof wm==='function')return String(wm(c))}catch(e){}return c<=1?'CLEAR':c==2?'PARTLY CLOUDY':c==3?'OVERCAST':c<=48?'FOG':c<=57?'DRIZZLE':c<=67?'RAIN':c<=77?'SNOW':c<=82?'SHOWERS':c<=86?'SNOW SHOWERS':'THUNDERSTORM'};
const uvL=v=>v<3?'LOW':v<6?'MODERATE':v<8?'HIGH':v<11?'VERY HIGH':'EXTREME';
const dir16=d=>['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'][Math.round(d/22.5)%16];
const visL=v=>v>=10?'CLEAR':v>=5?'GOOD':v>=2?'MODERATE':v>=1?'POOR':'FOG';
const DOW=['SUNDAY','MONDAY','TUESDAY','WEDNESDAY','THURSDAY','FRIDAY','SATURDAY'],MON=['JANUARY','FEBRUARY','MARCH','APRIL','MAY','JUNE','JULY','AUGUST','SEPTEMBER','OCTOBER','NOVEMBER','DECEMBER'];
const dname=ds=>DOW[new Date(ds+'T12:00:00').getDay()];
const dlong=ds=>dname(ds)+', '+MON[+ds.slice(5,7)-1]+' '+(+ds.slice(8,10))+', '+ds.slice(0,4);
const hh=i=>(H.time[i]||'').slice(11,16);
const r=v=>v==null||!isFinite(v)?'--':Math.round(v);
function now(){const c=cfg();let s;try{s=new Intl.DateTimeFormat('sv-SE',{timeZone:(c&&c.tz)||undefined,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date())}catch(e){const d=new Date(Date.now()-new Date().getTimezoneOffset()*6e4);s=d.toISOString().slice(0,16).replace('T',' ')}return{day:s.slice(0,10),h:+s.slice(11,13)+(+s.slice(14,16))/60}}

/* ---------- data (yesterday + 9 days, like iOS) ---------- */
async function load(force){const c=cfg();if(!c){S.err='NO HOME LOCATION';return}
 if(S.busy||(!force&&S.j&&Date.now()-S.t<9e5))return;S.busy=true;
 const HV='temperature_2m,apparent_temperature,relative_humidity_2m,dew_point_2m,precipitation_probability,precipitation,weather_code,uv_index,wind_speed_10m,wind_gusts_10m,wind_direction_10m,visibility,pressure_msl,is_day';
 const DV='weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,precipitation_sum,precipitation_probability_max,uv_index_max,wind_speed_10m_max,wind_gusts_10m_max';
 try{const q=await fetch('https://api.open-meteo.com/v1/forecast?latitude='+encodeURIComponent(c.lat)+'&longitude='+encodeURIComponent(c.lon)+'&hourly='+HV+'&daily='+DV+'&past_days=1&forecast_days=9&timezone='+encodeURIComponent(c.tz||'auto'));
  if(!q.ok)throw new Error('http');const j=await q.json();if(!j.hourly||!j.daily||!Array.isArray(j.hourly.time))throw new Error('data');
  j.idx=j.daily.time.map(d=>{const a=[];j.hourly.time.forEach((t,i)=>{if(t.slice(0,10)===d)a.push(i)});return a});
  S.j=j;S.t=Date.now();S.err='';S.dk=''}catch(e){S.err='NO WEATHER DATA (OPEN-METEO)'}
 S.busy=false}

function spec(m){switch(m){
 case 'uv':return{a:H.uv_index,col:OR,fmt:v=>String(r(v)),ticks:[0,3,6,8,11],bands:true};
 case 'wind':return{a:H.wind_speed_10m,b:H.wind_gusts_10m,col:GR,bcol:OR,fmt:v=>r(v)+' km/h',min:0,arrows:true};
 case 'prec':return{a:H.precipitation,col:RN,fmt:v=>(v==null?'--':(Math.round(v*10)/10))+' mm',min:0,bars:true,p2:H.precipitation_probability};
 case 'feels':return{a:H.apparent_temperature,col:OR,fmt:v=>r(v)+'°',tk:v=>v+'°',icons:true,hl:true};
 case 'hum':return{a:H.relative_humidity_2m,col:RN,fmt:v=>r(v)+'%',ticks:[0,25,50,75,100],tk:v=>v+'%',bars:true};
 case 'vis':return{a:H.visibility.map(v=>v==null?null:v/1000),col:C1,fmt:v=>(v==null?'--':v>=10?Math.round(v):Math.round(v*10)/10)+' km',min:0};
 case 'pres':return{a:H.pressure_msl,col:C1,fmt:v=>r(v)+' hPa'};
 default:return{a:H.temperature_2m,col:C1,fmt:v=>r(v)+'°',tk:v=>v+'°',icons:true,hl:true}}}

/* ---------- icons ---------- */
function icon(c,code,day,x,y,s){c.save();c.lineCap='round';const lw=Math.max(1,s*.065);
 const sun=(cx,cy,q)=>{c.fillStyle=OR;c.strokeStyle=OR;c.lineWidth=lw;c.beginPath();c.arc(cx,cy,q,0,7);c.fill();for(let a=0;a<8;a++){const w=a*Math.PI/4;c.beginPath();c.moveTo(cx+Math.cos(w)*q*1.45,cy+Math.sin(w)*q*1.45);c.lineTo(cx+Math.cos(w)*q*1.95,cy+Math.sin(w)*q*1.95);c.stroke()}};
 const moon=(cx,cy,q)=>{c.fillStyle=C1;c.beginPath();c.arc(cx,cy,q,0,7);c.fill();c.globalCompositeOperation='destination-out';c.beginPath();c.arc(cx+q*.45,cy-q*.3,q*.85,0,7);c.fill();c.globalCompositeOperation='source-over'};
 const cloud=(cx,cy)=>{c.fillStyle=CL;[[-.17,.04,.16],[.04,-.07,.21],[.22,.06,.14]].forEach(([dx,dy,q])=>{c.beginPath();c.arc(cx+dx*s,cy+dy*s,q*s,0,7);c.fill()});c.fillRect(cx-.17*s,cy+.04*s,.39*s,.16*s)};
 if(code<=1){day?sun(x,y,s*.2):moon(x,y,s*.24)}
 else if(code==2){day?sun(x-s*.12,y-s*.12,s*.14):moon(x-s*.12,y-s*.12,s*.17);cloud(x+s*.04,y+s*.04)}
 else if(code==3){cloud(x-s*.02,y-s*.05)}
 else if(code==45||code==48){c.strokeStyle=CL;c.lineWidth=lw*1.2;[-.15,0,.15].forEach((d,k)=>{c.beginPath();c.moveTo(x-s*(.32-k*.06),y+d*s);c.lineTo(x+s*(.32-k*.03),y+d*s);c.stroke()})}
 else{const sn=(code>=71&&code<=77)||code==85||code==86,th=code>=95;cloud(x-s*.02,y-s*.16);
  if(th){c.fillStyle=OR;c.beginPath();c.moveTo(x+s*.05,y+s*.04);c.lineTo(x-s*.1,y+s*.24);c.lineTo(x,y+s*.24);c.lineTo(x-s*.07,y+s*.42);c.lineTo(x+s*.13,y+s*.18);c.lineTo(x+s*.03,y+s*.18);c.closePath();c.fill()}
  else if(sn){c.fillStyle=SN;[-.16,0,.16].forEach((d,k)=>{c.beginPath();c.arc(x+d*s,y+s*(.16+(k%2)*.13),s*.05,0,7);c.fill()})}
  else{c.strokeStyle=RN;c.lineWidth=lw;[-.16,0,.16].forEach(d=>{c.beginPath();c.moveTo(x+d*s+s*.04,y+s*.1);c.lineTo(x+d*s-s*.04,y+s*.32);c.stroke()})}}
 c.restore()}
function arrow(c,x,y,s,deg){c.save();c.translate(x,y);c.rotate((deg+180)*Math.PI/180);c.strokeStyle=GR;c.fillStyle=GR;c.lineWidth=Math.max(1,s*.1);c.beginPath();c.moveTo(0,s*.4);c.lineTo(0,-s*.25);c.stroke();c.beginPath();c.moveTo(0,-s*.45);c.lineTo(-s*.18,-s*.15);c.lineTo(s*.18,-s*.15);c.closePath();c.fill();c.restore()}

/* ---------- chart ---------- */
function chart(sp,ix,today,nh){
 const cv=$('wxC'),b=cv.getBoundingClientRect(),dpr=window.devicePixelRatio||1,W=Math.max(60,b.width),Hc=Math.max(40,b.height);
 if(cv.width!==Math.round(W*dpr))cv.width=Math.round(W*dpr);if(cv.height!==Math.round(Hc*dpr))cv.height=Math.round(Hc*dpr);
 const c=cv.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,W,Hc);
 const f=parseFloat(el.style.fontSize)||14,fs=Math.max(9,f*.72),n=ix.length;S.geo=null;if(!n)return;
 c.font=fs+'px Consolas,monospace';c.textBaseline='middle';
 const top=(sp.icons||sp.arrows)?f*2.6:f*.7,L=2,R=fs*3.6,B=fs*1.8,gw=W-L-R,gh=Hc-top-B;if(gh<20||gw<40)return;
 S.geo={L,gw,n};const T=t=>L+(t+.5)*gw/n,kc=today?Math.min(n-1,Math.floor(nh)):-1;
 const va=ix.map(i=>sp.a[i]),vb=sp.b?ix.map(i=>sp.b[i]):null,all=va.concat(vb||[]).filter(v=>v!=null&&isFinite(v));
 if(!all.length){c.fillStyle=DM;c.fillText('NO DATA',L+4,top+gh/2);return}
 let lo=Math.min(...all),hi=Math.max(...all),ticks=sp.ticks;
 if(ticks){lo=ticks[0];hi=Math.max(ticks[ticks.length-1],hi)}
 else{let span=hi-lo;if(span<1)span=1;const raw=span/3,p=Math.pow(10,Math.floor(Math.log10(raw))),stp=[1,2,2.5,5,10].map(x=>x*p).find(x=>x>=raw)||10*p;
  lo=sp.min!=null?sp.min:Math.floor(lo/stp)*stp;hi=Math.ceil(hi/stp)*stp;if(hi<=lo)hi=lo+stp;ticks=[];for(let v=lo;v<=hi+stp/2;v+=stp)ticks.push(+v.toFixed(2))}
 const Y=v=>top+gh-(v-lo)/(hi-lo)*gh;
 const line=(arr,YY)=>{c.beginPath();let pen=false;arr.forEach((v,k)=>{if(v==null){pen=false;return}const x=T(k),y=YY(v);pen?c.lineTo(x,y):c.moveTo(x,y);pen=true});c.stroke()};
 const pf=(arr,YY)=>{if(kc<0){line(arr,YY);return}const a=c.globalAlpha;c.globalAlpha=a*.55;c.setLineDash([6,5]);line(arr.map((v,k)=>k<=kc+1?v:null),YY);c.setLineDash([]);c.globalAlpha=a;line(arr.map((v,k)=>k>=kc?v:null),YY)};
 if(sp.bands){[[0,3,GR],[3,6,'#e6d45a'],[6,8,OR],[8,11,'#ff5a4a'],[11,99,'#c77dff']].forEach(([a,z,col])=>{if(a>=hi)return;const y1=Y(Math.min(z,hi)),y0=Y(a);c.globalAlpha=.08;c.fillStyle=col;c.fillRect(L,y1,gw,y0-y1)});c.globalAlpha=1}
 c.lineWidth=1;c.strokeStyle='rgba(25,211,255,.13)';c.fillStyle=DM;c.textAlign='left';
 ticks.forEach(v=>{const y=Y(v);c.beginPath();c.moveTo(L,y);c.lineTo(L+gw,y);c.stroke();c.fillText(sp.tk?sp.tk(v):String(Math.round(v*10)/10),L+gw+fs*.4,y)});
 c.textAlign='center';c.setLineDash([2,3]);
 ix.forEach((i,k)=>{const h=+H.time[i].slice(11,13);if(h%6===0){const x=T(k);c.beginPath();c.moveTo(x,top);c.lineTo(x,top+gh+B*.3);c.stroke();c.fillText(H.time[i].slice(11,13),x,top+gh+B*.6)}});c.setLineDash([]);
 if(sp.bars){const bw=Math.max(1,gw/n*.62);c.fillStyle=sp.col;c.globalAlpha=.75;va.forEach((v,k)=>{if(v==null)return;const y=Y(v),y0=Y(lo);c.fillRect(T(k)-bw/2,y,bw,Math.max(v>0?1:0,y0-y))});c.globalAlpha=1}
 else{const gr=c.createLinearGradient(0,top,0,top+gh);gr.addColorStop(0,hexA(sp.col,.3));gr.addColorStop(1,hexA(sp.col,.03));c.fillStyle=gr;c.beginPath();let s0=-1,last=-1;
  va.forEach((v,k)=>{if(v==null)return;const x=T(k),y=Y(v);if(s0<0){c.moveTo(x,Y(lo));c.lineTo(x,y);s0=k}else c.lineTo(x,y);last=k});if(s0>=0){c.lineTo(T(last),Y(lo));c.closePath();c.fill()}
  if(vb){c.strokeStyle=sp.bcol;c.lineWidth=1.3;c.globalAlpha=.8;pf(vb,Y);c.globalAlpha=1}
  c.strokeStyle=sp.col;c.lineWidth=2.2;pf(va,Y)}
 if(sp.p2){c.strokeStyle=C1;c.globalAlpha=.7;c.lineWidth=1.2;pf(ix.map(i=>sp.p2[i]),t=>top+gh-t/100*gh);c.globalAlpha=1}
 if(sp.hl){let mi=-1,ma=-1;va.forEach((v,k)=>{if(v==null)return;if(mi<0||v<va[mi])mi=k;if(ma<0||v>va[ma])ma=k});
  [[ma,'H',-1],[mi,'L',1]].forEach(([k,t,s])=>{if(k<0)return;const x=T(k),y=Y(va[k]);c.fillStyle='#02060b';c.beginPath();c.arc(x,y,4,0,7);c.fill();c.fillStyle=OR;c.beginPath();c.arc(x,y,2.5,0,7);c.fill();c.fillText(t,x,y+s*fs*1.1)})}
 if(sp.icons)ix.forEach((i,k)=>{if(+H.time[i].slice(11,13)%2===0)icon(c,H.weather_code[i],H.is_day[i]===1,T(k),top*.45,Math.min(f*1.8,gw/n*2.5))});
 if(sp.arrows)ix.forEach((i,k)=>{if(+H.time[i].slice(11,13)%2===0&&H.wind_direction_10m[i]!=null)arrow(c,T(k),top*.45,Math.min(f*1.2,gw/n*2.1),H.wind_direction_10m[i])});
 if(today){const x=T(nh);c.fillStyle='rgba(3,9,14,.5)';c.fillRect(L,top,Math.max(0,x-L),gh);c.strokeStyle=hexA(OR,.8);c.lineWidth=1.2;c.beginPath();c.moveTo(x,top);c.lineTo(x,top+gh);c.stroke();
  const k1=Math.min(n-1,kc+1),a0=va[kc],a1=va[k1];if(a0!=null&&!sp.bars){const v=a1==null?a0:a0+(a1-a0)*(nh-kc);c.fillStyle='#02060b';c.beginPath();c.arc(x,Y(v),4.5,0,7);c.fill();c.fillStyle=OR;c.beginPath();c.arc(x,Y(v),3,0,7);c.fill()}}
 if(S.hov!=null&&S.hov<n){const x=T(S.hov),v=va[S.hov];c.strokeStyle=C1;c.lineWidth=1;c.beginPath();c.moveTo(x,top);c.lineTo(x,top+gh);c.stroke();if(v!=null){c.fillStyle=C1;c.beginPath();c.arc(x,Y(v),3.5,0,7);c.fill()}}
}
$('wxC').addEventListener('mousemove',e=>{const g=S.geo;if(!g)return;const b=e.currentTarget.getBoundingClientRect();let k=Math.round((e.clientX-b.left-g.L)/(g.gw/g.n)-.5);k=Math.max(0,Math.min(g.n-1,k));if(k!==S.hov){S.hov=k;render()}});
$('wxC').addEventListener('mouseleave',()=>{if(S.hov!=null){S.hov=null;render()}});

/* ---------- texts ---------- */
function info(m,sp,ix,d,i){const D=S.j.daily,vals=ix.map(k=>sp.a[k]).filter(v=>v!=null),mx=vals.length?Math.max(...vals):null,mn=vals.length?Math.min(...vals):null,
 at=v=>{const k=ix.find(q=>sp.a[q]===v);return k==null?'--':hh(k)},avg=a=>a.length?a.reduce((x,y)=>x+y,0)/a.length:null,has=i!=null&&sp.a[i]!=null,D3='  ·  ';
 let V='--',Sb='',Tt='',sum='';
 switch(m){
 case 'uv':{const v=has?sp.a[i]:mx;V=v==null?'--':String(r(v));Sb=v==null?'':uvL(v)+(has?'':' (PEAK)');const hi=ix.filter(k=>sp.a[k]>=3);
  sum='PEAK '+(mx==null?'--':r(mx)+' '+uvL(mx)+' AT '+at(mx))+(hi.length?D3+'PROTECTION '+hh(hi[0])+'-'+hh(hi[hi.length-1]):D3+'NO PROTECTION NEEDED');break}
 case 'wind':{V=has?sp.fmt(sp.a[i]):sp.fmt(mx);const gi=has?H.wind_gusts_10m[i]:D.wind_gusts_10m_max[d];Sb=(has&&H.wind_direction_10m[i]!=null?dir16(H.wind_direction_10m[i])+'  ':'')+'GUSTS '+r(gi)+' km/h';
  sum='MAX '+r(mx)+' km/h AT '+at(mx)+D3+'GUSTS UP TO '+r(D.wind_gusts_10m_max[d])+' km/h'+D3+'SOLID = WIND, ORANGE = GUSTS';break}
 case 'prec':{const tot=vals.reduce((x,y)=>x+y,0),wet=vals.filter(v=>v>=0.1).length;V=has?sp.fmt(sp.a[i]):sp.fmt(tot);Sb=has?'CHANCE '+r(H.precipitation_probability[i])+'%':'TOTAL FOR THE DAY';
  sum='TOTAL '+sp.fmt(tot)+D3+'WET HOURS '+wet+D3+'DAY CHANCE '+r(D.precipitation_probability_max[d])+'%'+D3+'BARS = mm, LINE = CHANCE';break}
 case 'feels':V=has?sp.fmt(sp.a[i]):r(D.apparent_temperature_max[d])+'°';Sb=has?'ACTUAL '+r(H.temperature_2m[i])+'°':WM(D.weather_code[d]);Tt='H:'+r(D.apparent_temperature_max[d])+'°  L:'+r(D.apparent_temperature_min[d])+'°';
  sum='HOW WARM OR COLD IT FEELS (WIND, HUMIDITY).'+D3+'ACTUAL H:'+r(D.temperature_2m_max[d])+'° L:'+r(D.temperature_2m_min[d])+'°';break;
 case 'hum':{const dv=ix.map(k=>H.dew_point_2m[k]).filter(v=>v!=null);V=has?sp.fmt(sp.a[i]):sp.fmt(avg(vals));Sb=has?'DEW POINT '+r(H.dew_point_2m[i])+'°':'DAY AVERAGE';
  sum='RANGE '+r(mn)+'% TO '+r(mx)+'%'+D3+'DEW POINT '+r(dv.length?Math.min(...dv):null)+'° TO '+r(dv.length?Math.max(...dv):null)+'°';break}
 case 'vis':{V=has?sp.fmt(sp.a[i]):sp.fmt(mn);Sb=has?visL(sp.a[i]):(mn==null?'':'LOWEST: '+visL(mn));sum='RANGE '+sp.fmt(mn)+' TO '+sp.fmt(mx);break}
 case 'pres':{const k=i!=null?ix.indexOf(i):-1,p3=k>=3?sp.a[ix[k-3]]:null,tr=(a,z)=>a==null||z==null?'--':(z-a>1?'RISING':z-a<-1?'FALLING':'STEADY');
  V=has?sp.fmt(sp.a[i]):sp.fmt(avg(vals));Sb=has?tr(p3,sp.a[i]):'DAY AVERAGE';sum=vals.length?'FROM '+sp.fmt(vals[0])+' TO '+sp.fmt(vals[vals.length-1])+D3+tr(vals[0],vals[vals.length-1]):'';break}
 default:V=has?sp.fmt(sp.a[i]):r(D.temperature_2m_max[d])+'°';Sb=WM(has?H.weather_code[i]:D.weather_code[d]);Tt='H:'+r(D.temperature_2m_max[d])+'°  L:'+r(D.temperature_2m_min[d])+'°';
  sum='THE ACTUAL TEMPERATURE.'+D3+'RAIN CHANCE '+r(D.precipitation_probability_max[d])+'%'}
 return{V,Sb,Tt,sum}}

function days(){const key=S.t+'|'+S.day;if(S.dk===key)return;S.dk=key;const D=S.j.daily,bx=$('wxDays'),td=now().day;bx.textContent='';
 D.time.forEach((t,d)=>{const c=document.createElement('div');c.className=(d===S.day?'on ':'')+(t<td?'ps':'');const a=document.createElement('b');a.textContent=dname(t).charAt(0);
  const b=document.createElement('i');b.textContent=String(+t.slice(8,10));c.append(a,b);c.onclick=()=>{S.day=d;S.hov=null;render()};bx.append(c)})}

/* ---------- view (inside the ATMOSPHERICS box only) ---------- */
function place(){const b=window.WXBOX;if(!b){el.style.display='none';return false}const u=b.u||1;
 el.style.left=(b.x+10*u)+'px';el.style.top=(b.y+28*u)+'px';el.style.width=Math.max(10,b.w-20*u)+'px';el.style.height=Math.max(10,b.h-36*u)+'px';el.style.fontSize=Math.max(9,13*u)+'px';el.style.display='flex';return true}
function render(){if(!S.open||!place())return;
 const V=$('wxV'),Sb=$('wxS'),Tt=$('wxT'),sm=$('wxSum'),mk=S.met==='cond'&&S.feels?'feels':S.met;
 mb.textContent=(MET.find(x=>x[0]===S.met)||MET[0])[1]+' ▾';
 $('wxSeg').style.display=S.met==='cond'?'flex':'none';el.querySelectorAll('#wxSeg div').forEach(x=>x.className=(x.dataset.f==='1')===S.feels?'on':'');
 if(!S.j){V.textContent='--';Sb.textContent=(S.busy||!S.err)?'ACQUIRING SIGNAL...':S.err;Tt.textContent='';sm.textContent='';$('wxDays').textContent='';$('wxDL').textContent='';S.dk='';$('wxI').style.display='none';const cv=$('wxC');cv.getContext('2d').clearRect(0,0,cv.width,cv.height);return}
 H=S.j.hourly;const D=S.j.daily,nw=now();if(S.day<0||S.day>=D.time.length){const k=D.time.indexOf(nw.day);S.day=k<0?0:k}
 const d=S.day,ix=S.j.idx[d]||[],today=D.time[d]===nw.day,sp=spec(mk);
 const i=S.hov!=null?ix[S.hov]:(today&&ix.length?ix[Math.min(ix.length-1,Math.floor(nw.h))]:null);
 days();$('wxDL').textContent=dlong(D.time[d]);chart(sp,ix,today,nw.h);
 const o=info(mk,sp,ix,d,i==null?null:i);
 V.textContent=o.V;Sb.textContent=o.Sb;sm.textContent=o.sum;
 V.style.color=mk==='uv'&&o.V!=='--'?(+o.V<3?GR:+o.V<6?'#e6d45a':+o.V<8?OR:+o.V<11?'#ff5a4a':'#c77dff'):C1;
 Tt.textContent=(o.Tt?o.Tt+'   ':'')+(i!=null?(S.hov==null?'NOW ':'')+hh(i):'ALL DAY');
 {const k=$('wxI'),f=parseFloat(el.style.fontSize)||14,s=Math.round(f*3),dpr=window.devicePixelRatio||1;k.style.display=S.met==='cond'?'block':'none';
  if(S.met==='cond'){k.width=s*dpr;k.height=s*dpr;k.style.width=k.style.height=s+'px';const x=k.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);x.clearRect(0,0,s,s);
   icon(x,i!=null?H.weather_code[i]:D.weather_code[d],i!=null?H.is_day[i]===1:true,s/2,s/2,s)}}}
function toggle(on){S.open=on==null?!S.open:!!on;window.WXD=S.open;mn.style.display='none';if(!S.open){el.style.display='none';S.hov=null;return}
 S.day=-1;S.dk='';render();load().then(render)}
window.jvWeatherDetails=toggle;
document.addEventListener('click',e=>{const b=window.WXBTN;if(!b||!e.target||e.target.tagName!=='CANVAS'||el.contains(e.target))return;if(e.clientX>=b.x&&e.clientX<=b.x+b.w&&e.clientY>=b.y&&e.clientY<=b.y+b.h)toggle()});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&S.open)toggle(false)});
addEventListener('resize',()=>{if(S.open){S.dk='';setTimeout(render,150)}});
setInterval(()=>{if(!S.open)return;if(Date.now()-S.t>9e5&&!S.busy)load(true).then(render);else render()},30000);
})();
