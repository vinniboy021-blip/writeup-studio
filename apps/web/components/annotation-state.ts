// SPDX-License-Identifier: MIT
export type ShapeType = 'arrow'|'rect'|'circle'|'line'|'text'|'highlight'|'step'|'blur'|'redact';
export type Point = {x:number;y:number};
export type Shape = Point & {id:string;type:ShapeType;x2?:number;y2?:number;width?:number;height?:number;text?:string;color:string;strokeWidth:number;number?:number};
export type Crop = Point & {width:number;height:number};
export type AnnotationData = {schema_version:1;width:number;height:number;shapes:Shape[];crop?:Crop};
export type AnnotationHistory = {past:AnnotationData[];present:AnnotationData;future:AnnotationData[]};
export const shapeLabels:Record<ShapeType,string> = {arrow:'Seta',rect:'Retângulo',circle:'Círculo',line:'Linha',text:'Texto',highlight:'Destaque',step:'Etapa',blur:'Desfoque',redact:'Redação opaca'};
export function emptyAnnotation(width:number,height:number):AnnotationData{return {schema_version:1,width,height,shapes:[]};}
export function pointerPoint(client:Point,rect:{left:number;top:number;width:number;height:number},size:{width:number;height:number}):Point{
 return {x:Math.max(0,Math.min(size.width-1,(client.x-rect.left)*size.width/rect.width)),y:Math.max(0,Math.min(size.height-1,(client.y-rect.top)*size.height/rect.height))};
}
export function rectangle(a:Point,b:Point):Crop{return {x:Math.floor(Math.min(a.x,b.x)),y:Math.floor(Math.min(a.y,b.y)),width:Math.max(1,Math.ceil(Math.abs(b.x-a.x))),height:Math.max(1,Math.ceil(Math.abs(b.y-a.y)))};}
export function numbered(data:AnnotationData):AnnotationData{let step=0;return {...data,shapes:data.shapes.map(shape=>shape.type==='step'?{...shape,number:++step}:shape)};}
export function commit(history:AnnotationHistory,next:AnnotationData):AnnotationHistory{
 const normalized=numbered(next);if(JSON.stringify(normalized)===JSON.stringify(history.present))return history;
 return {past:[...history.past,history.present].slice(-60),present:normalized,future:[]};
}
export function undo(history:AnnotationHistory):AnnotationHistory{
 if(!history.past.length)return history;return {past:history.past.slice(0,-1),present:history.past[history.past.length-1],future:[history.present,...history.future]};
}
export function redo(history:AnnotationHistory):AnnotationHistory{
 if(!history.future.length)return history;return {past:[...history.past,history.present],present:history.future[0],future:history.future.slice(1)};
}
export function moveShape(shape:Shape,delta:Point,width:number,height:number):Shape{
 const minX=Math.min(shape.x,shape.x2??shape.x),maxX=Math.max(shape.x+(shape.width??0),shape.x2??shape.x);
 const minY=Math.min(shape.y,shape.y2??shape.y),maxY=Math.max(shape.y+(shape.height??0),shape.y2??shape.y);
 const dx=Math.max(-minX,Math.min(width-1-maxX,delta.x)),dy=Math.max(-minY,Math.min(height-1-maxY,delta.y));
 return {...shape,x:shape.x+dx,y:shape.y+dy,...(shape.x2!==undefined?{x2:shape.x2+dx}:{}),...(shape.y2!==undefined?{y2:shape.y2+dy}:{})};
}
export function hitTest(shape:Shape,p:Point):boolean{
 if(shape.type==='line'||shape.type==='arrow'){
  const dx=(shape.x2??shape.x)-shape.x,dy=(shape.y2??shape.y)-shape.y,len=dx*dx+dy*dy;
  const t=len?Math.max(0,Math.min(1,((p.x-shape.x)*dx+(p.y-shape.y)*dy)/len)):0;
  return Math.hypot(p.x-shape.x-t*dx,p.y-shape.y-t*dy)<=Math.max(8,shape.strokeWidth*2);
 }
 if(shape.type==='step')return Math.hypot(p.x-shape.x,p.y-shape.y)<=18;
 if(shape.type==='text')return p.x>=shape.x&&p.x<=shape.x+Math.max(24,(shape.text?.length??1)*shape.strokeWidth*3)&&p.y>=shape.y&&p.y<=shape.y+Math.max(12,shape.strokeWidth*5);
 return p.x>=shape.x&&p.x<=shape.x+(shape.width??0)&&p.y>=shape.y&&p.y<=shape.y+(shape.height??0);
}
export function reorderShape(data:AnnotationData,id:string,offset:number):AnnotationData{
 const shapes=[...data.shapes],index=shapes.findIndex(s=>s.id===id),target=index+offset;
 if(index<0||target<0||target>=shapes.length)return data;const [shape]=shapes.splice(index,1);shapes.splice(target,0,shape);return numbered({...data,shapes});
}
export function serializeAnnotation(data:AnnotationData):AnnotationData{
 // Persist only the versioned annotation schema, never browser image data or preview pixels.
 return numbered({schema_version:1,width:data.width,height:data.height,shapes:data.shapes.map(s=>({id:s.id,type:s.type,x:s.x,y:s.y,color:s.color,strokeWidth:s.strokeWidth,
  ...(s.x2!==undefined?{x2:s.x2}:{}),...(s.y2!==undefined?{y2:s.y2}:{}),...(s.width!==undefined?{width:s.width}:{}),...(s.height!==undefined?{height:s.height}:{}),...(s.text!==undefined?{text:s.text}:{}),...(s.type==='step'?{number:s.number}:{} )})),...(data.crop?{crop:{...data.crop}}:{})});
}
