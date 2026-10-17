// Small, dependency-free slippy map. Replace this adapter with MapLibre if needed.
// OpenStreetMap raster tiles; no API key. Issue locations use Web Mercator projection.
const tileSize = 256;
function project([lng,lat],z) {
  const size=tileSize*2**z, sin=Math.sin(lat*Math.PI/180);
  return [(lng+180)/360*size,(0.5-Math.log((1+sin)/(1-sin))/(4*Math.PI))*size];
}
function unproject([x,y],z) {
  const size=tileSize*2**z;
  return [x/size*360-180,Math.atan(Math.sinh(Math.PI*(1-2*y/size)))*180/Math.PI];
}
export class CivicMap {
  constructor(element,{onSelect,onEmpty,onMove,icon}) {
    Object.assign(this,{element,onSelect,onEmpty,onMove,icon,center:[-79.397,43.661],zoom:13,issues:[],selected:[],layers:[],mode:'pan',drag:null,showHeat:false});
    element.innerHTML='<div class="map-fallback" aria-hidden="true"><div class="fallback-grid"></div><span>TORONTO</span><i>Lake Ontario</i></div><div class="tile-layer"></div><div class="infrastructure-layer"></div><div class="marker-layer"></div><div class="box-drawing"></div><div class="tile-warning" hidden>Map tiles unavailable · schematic background</div>';
    this.tiles=element.querySelector('.tile-layer');this.markers=element.querySelector('.marker-layer');
    this.box=element.querySelector('.box-drawing');
    this.handlers={down:e=>this.pointerDown(e),move:e=>this.pointerMove(e),up:e=>this.pointerUp(e),wheel:e=>{e.preventDefault();this.setZoom(this.zoom+(e.deltaY<0?1:-1));}};
    element.addEventListener('pointerdown',this.handlers.down);
    element.addEventListener('pointermove',this.handlers.move);
    element.addEventListener('pointerup',this.handlers.up);
    element.addEventListener('pointercancel',()=>{this.drag=null;this.box.style.display='none';});
    element.addEventListener('wheel',this.handlers.wheel,{passive:false});
    this.observer=new ResizeObserver(()=>this.render());this.observer.observe(element);
  }
  destroy(){this.observer.disconnect(); for(const [key,event] of [['down','pointerdown'],['move','pointermove'],['up','pointerup'],['wheel','wheel']]) this.element.removeEventListener(event,this.handlers[key]);}
  setData(issues,selected=[]){this.issues=issues;this.selected=selected;this.render();}
  setZoom(z){this.zoom=Math.max(10,Math.min(18,z));this.render();this.onMove?.();}
  flyTo(coords,z=14){this.center=coords;this.zoom=z;this.render();}
  position(coords){const p=project(coords,this.zoom),c=project(this.center,this.zoom);return [p[0]-c[0]+this.element.clientWidth/2,p[1]-c[1]+this.element.clientHeight/2];}
  pointerDown(e){if(e.target.closest('button')||e.button!==0)return;this.element.setPointerCapture(e.pointerId);this.drag={x:e.clientX,y:e.clientY,center:project(this.center,this.zoom),moved:false};}
  pointerMove(e){if(!this.drag)return;const dx=e.clientX-this.drag.x,dy=e.clientY-this.drag.y;this.drag.moved ||=Math.abs(dx)+Math.abs(dy)>5;
    if(this.mode==='box'){const r=this.element.getBoundingClientRect();Object.assign(this.box.style,{display:'block',left:Math.min(e.clientX,this.drag.x)-r.left+'px',top:Math.min(e.clientY,this.drag.y)-r.top+'px',width:Math.abs(dx)+'px',height:Math.abs(dy)+'px'});}
    else {this.center=unproject([this.drag.center[0]-dx,this.drag.center[1]-dy],this.zoom);this.render();}
  }
  pointerUp(e){if(!this.drag)return;const d=this.drag;this.drag=null;this.box.style.display='none';
    if(this.mode==='box'&&d.moved){const r=this.element.getBoundingClientRect(),x1=Math.min(d.x,e.clientX)-r.left,x2=Math.max(d.x,e.clientX)-r.left,y1=Math.min(d.y,e.clientY)-r.top,y2=Math.max(d.y,e.clientY)-r.top;
      const ids=this.issues.filter(i=>{const [x,y]=this.position(i.geometry.coordinates);return x>=x1&&x<=x2&&y>=y1&&y<=y2;}).map(i=>i.issue_id);this.onSelect(ids,'multi',e);}
    else if(!d.moved)this.onEmpty();else this.onMove?.();
  }
  render(){
    const width=this.element.clientWidth,height=this.element.clientHeight;if(!width||!height)return;
    const c=project(this.center,this.zoom),left=c[0]-width/2,top=c[1]-height/2;
    const fragment=document.createDocumentFragment();
    for(let x=Math.floor(left/256);x<=Math.floor((left+width)/256);x++)for(let y=Math.floor(top/256);y<=Math.floor((top+height)/256);y++){
      const img=document.createElement('img');img.src=`https://tile.openstreetmap.org/${this.zoom}/${x}/${y}.png`;img.alt='';img.draggable=false;img.style.cssText=`left:${x*256-left}px;top:${y*256-top}px;`;
      img.onerror=()=>{this.element.querySelector('.tile-warning').hidden=false;img.style.opacity=0;};
      fragment.append(img);
    }
    // Reuse loaded tiles when their URLs match, so panning never flashes the map.
    const old=new Map([...this.tiles.children].map(i=>[i.src,i]));
    for(const img of [...fragment.children]){const prior=old.get(img.src);if(prior){prior.style.cssText=img.style.cssText;img.replaceWith(prior);}}
    this.tiles.replaceChildren(fragment);
    const visible=this.issues.map(i=>({issue:i,p:this.position(i.geometry.coordinates)})).filter(({p})=>p[0]>-25&&p[0]<width+25&&p[1]>-25&&p[1]<height+25);
    const groups=[];for(const point of visible){const group=groups.find(g=>Math.hypot(g.p[0]-point.p[0],g.p[1]-point.p[1])<(this.zoom<14?48:25));if(group)group.items.push(point.issue);else groups.push({p:point.p,items:[point.issue]});}
    this.markers.replaceChildren();
    for(const group of groups){const first=group.items[0],multi=group.items.length>1,button=document.createElement('button');
      button.className=`map-pin ${multi?'cluster':''} ${group.items.some(i=>this.selected.includes(i.issue_id))?'selected':''} ${this.showHeat?'heat-pin':''}`;
      button.style.cssText=`left:${group.p[0]}px;top:${group.p[1]}px;--pin:${this.color(first.issue_type)}`;
      button.innerHTML=multi?`<span>${group.items.length}</span>`:this.icon(first.issue_type);button.title=multi?`${group.items.length} issues · click to explore`:`${first.issue_type} · ${first.address}`;button.setAttribute('aria-label',button.title);
      button.addEventListener('click',e=>{e.stopPropagation();this.onSelect(group.items.map(i=>i.issue_id),multi?'cluster':'issue',e);});this.markers.append(button);
    }
    this.element.classList.toggle('box-mode',this.mode==='box');
    this.renderInfrastructure();
  }
  color(type){return {Pothole:'#fa6575','Sidewalk damage':'#ffb452',Graffiti:'#ba80f6',Litter:'#25d5ac',Flooding:'#4ea8ff',Other:'#9daec3'}[type];}
  renderInfrastructure(){const layer=this.element.querySelector('.infrastructure-layer');layer.replaceChildren();
    const assets=[['TTC','Union',-79.38,43.645],['TTC','Spadina',-79.403,43.667],['TTC','Osgoode',-79.386,43.65],['Schools','U of T',-79.396,43.663],['Schools','TMU',-79.379,43.657],['Roads','Gardiner Expressway',-79.40,43.637]];
    for(const [type,name,lng,lat] of assets){if(!this.layers.includes(type))continue;const [x,y]=this.position([lng,lat]);const el=document.createElement('span');el.className='asset-label';el.style.cssText=`left:${x}px;top:${y}px`;el.textContent=`${type==='TTC'?'Ⓜ':'◇'} ${name}`;layer.append(el);}
  }
}
