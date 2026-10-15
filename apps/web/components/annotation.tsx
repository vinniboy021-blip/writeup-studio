// SPDX-License-Identifier: MIT
"use client";
import {useCallback,useEffect,useRef,useState,type PointerEvent} from 'react';
import {ApiError,api,items,mutate,type Row} from '../lib/api';
import {Button,ErrorBox,Field,Loading,useData} from './ui';
import {commit,emptyAnnotation,hitTest,moveShape,numbered,pointerPoint,rectangle,redo,reorderShape,serializeAnnotation,shapeLabels,undo,type AnnotationData,type AnnotationHistory,type Point,type Shape,type ShapeType} from './annotation-state';

function paintShape(ctx:CanvasRenderingContext2D,shape:Shape){
 ctx.save();ctx.strokeStyle=shape.color;ctx.fillStyle=shape.color;ctx.lineWidth=shape.strokeWidth;ctx.lineCap='round';
 const width=shape.width??0,height=shape.height??0;
 if(shape.type==='rect')ctx.strokeRect(shape.x,shape.y,width,height);
 if(shape.type==='circle'){ctx.beginPath();ctx.ellipse(shape.x+width/2,shape.y+height/2,width/2,height/2,0,0,Math.PI*2);ctx.stroke();}
 if(shape.type==='line'||shape.type==='arrow'){
  const x2=shape.x2??shape.x,y2=shape.y2??shape.y;ctx.beginPath();ctx.moveTo(shape.x,shape.y);ctx.lineTo(x2,y2);ctx.stroke();
  if(shape.type==='arrow'){const angle=Math.atan2(y2-shape.y,x2-shape.x),length=Math.max(10,shape.strokeWidth*4);ctx.beginPath();ctx.moveTo(x2,y2);ctx.lineTo(x2-length*Math.cos(angle-Math.PI/6),y2-length*Math.sin(angle-Math.PI/6));ctx.lineTo(x2-length*Math.cos(angle+Math.PI/6),y2-length*Math.sin(angle+Math.PI/6));ctx.closePath();ctx.fill();}
 }
 if(shape.type==='text'){ctx.font=`${Math.max(12,shape.strokeWidth*5)}px sans-serif`;ctx.textBaseline='top';ctx.fillText(shape.text??'',shape.x,shape.y);}
 if(shape.type==='step'){ctx.beginPath();ctx.arc(shape.x,shape.y,14,0,Math.PI*2);ctx.fill();ctx.fillStyle='#fff';ctx.font='17px sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(String(shape.number),shape.x,shape.y);}
 if(shape.type==='highlight'){ctx.fillStyle=shape.color+'55';ctx.fillRect(shape.x,shape.y,width,height);}
 if(shape.type==='redact'){ctx.globalAlpha=1;ctx.fillStyle='#000';ctx.fillRect(shape.x,shape.y,width,height);}
 if(shape.type==='blur'){
  const buffer=document.createElement('canvas');buffer.width=Math.max(1,Math.round(width));buffer.height=Math.max(1,Math.round(height));
  const copy=buffer.getContext('2d');if(copy){copy.drawImage(ctx.canvas,shape.x,shape.y,width,height,0,0,buffer.width,buffer.height);ctx.beginPath();ctx.rect(shape.x,shape.y,width,height);ctx.clip();ctx.filter=`blur(${Math.max(8,shape.strokeWidth*3)}px)`;ctx.drawImage(buffer,shape.x,shape.y,width,height);}
 }
 ctx.restore();
}

type Drag = {start:Point;type:ShapeType|'select'|'crop';shape?:Shape};
export function AnnotationEditor({evidence,originalURL,onSaved}:{evidence:Row;originalURL:string;onSaved:()=>Promise<unknown>|void}){
 const width=Number(evidence.metadata?.width||0),height=Number(evidence.metadata?.height||0);
 const annotations=useData(`/evidences/${evidence.id}/annotations?page_size=1`);
 const [history,setHistory]=useState<AnnotationHistory>({past:[],present:emptyAnnotation(width,height),future:[]});
 const [baseline,setBaseline]=useState(''),[initialized,setInitialized]=useState(false),[version,setVersion]=useState(Number(evidence.version));
 const [tool,setTool]=useState<ShapeType|'select'|'crop'>('arrow'),[color,setColor]=useState('#ef4444'),[stroke,setStroke]=useState(3),[text,setText]=useState('');
 const [zoom,setZoom]=useState(Math.min(1,720/Math.max(1,width))),[selected,setSelected]=useState(''),[error,setError]=useState<unknown>(),[busy,setBusy]=useState(false),[conflict,setConflict]=useState(false);
 const [preview,setPreview]=useState<AnnotationData|null>(null),[imageReady,setImageReady]=useState(false),[message,setMessage]=useState('');
 const [coordinates,setCoordinates]=useState({x:10,y:10,x2:100,y2:70});
 const recoveryKey=`ctf-annotation-draft:${evidence.id}`;
 const canvas=useRef<HTMLCanvasElement>(null),image=useRef<HTMLImageElement|null>(null),drag=useRef<Drag|null>(null);
 const current=history.present,dirty=initialized&&JSON.stringify(serializeAnnotation(current))!==baseline;
 useEffect(()=>{if(!initialized&&annotations.isSuccess){const latest=items(annotations.data)[0]?.data as AnnotationData|undefined;const data=numbered(latest||emptyAnnotation(width,height));let recovered:AnnotationData|undefined;
  try{const draft=JSON.parse(sessionStorage.getItem(recoveryKey)||'null');if(draft?.data?.schema_version===1&&draft.data.width===width&&draft.data.height===height&&Array.isArray(draft.data.shapes)&&draft.data.shapes.length<=500){recovered=numbered(draft.data);setVersion(draft.version);setMessage('Anotações não salvas foram recuperadas nesta aba. Revise antes de salvar.');}}catch{ /* A storage quota or disabled storage does not block editing. */ }
  setHistory({past:[],present:recovered||data,future:[]});setBaseline(JSON.stringify(serializeAnnotation(data)));setInitialized(true);}},[annotations.data,annotations.isSuccess,initialized,width,height,recoveryKey]);
 useEffect(()=>{if(!initialized)return;try{if(dirty)sessionStorage.setItem(recoveryKey,JSON.stringify({version,data:serializeAnnotation(current)}));else sessionStorage.removeItem(recoveryKey);}catch{ /* Editing remains available when browser storage is disabled. */ }},[current,dirty,initialized,recoveryKey,version]);
 useEffect(()=>{const img=new Image();let active=true;img.onload=()=>{if(active){image.current=img;setImageReady(true);}};img.onerror=()=>{if(active)setError(new Error('Não foi possível abrir a imagem original.'));};img.src=originalURL;return()=>{active=false;image.current=null;};},[originalURL]);
 const change=useCallback((data:AnnotationData)=>{setHistory(h=>commit(h,data));setMessage('');},[]);
 useEffect(()=>{
  const ctx=canvas.current?.getContext('2d');if(!ctx||!imageReady||!image.current)return;
  ctx.clearRect(0,0,width,height);ctx.drawImage(image.current,0,0,width,height);const view=preview||current;view.shapes.forEach(shape=>paintShape(ctx,shape));
  if(view.crop){const c=view.crop;ctx.save();ctx.fillStyle='rgba(15,23,42,.6)';ctx.beginPath();ctx.rect(0,0,width,height);ctx.rect(c.x,c.y,c.width,c.height);ctx.fill('evenodd');ctx.strokeStyle='#fff';ctx.lineWidth=2;ctx.setLineDash([8,6]);ctx.strokeRect(c.x,c.y,c.width,c.height);ctx.restore();}
  const layer=view.shapes.find(s=>s.id===selected);if(layer){ctx.save();ctx.strokeStyle='#38bdf8';ctx.lineWidth=2;ctx.setLineDash([6,4]);const x=Math.min(layer.x,layer.x2??layer.x),y=Math.min(layer.y,layer.y2??layer.y);ctx.strokeRect(x-3,y-3,Math.max(20,layer.width??Math.abs((layer.x2??layer.x)-layer.x))+6,Math.max(20,layer.height??Math.abs((layer.y2??layer.y)-layer.y))+6);ctx.restore();}
 },[current,preview,imageReady,width,height,selected]);
 useEffect(()=>{function keyboard(e:KeyboardEvent){const target=e.target as HTMLElement;if(target.matches('input,textarea,select,[contenteditable="true"]'))return;if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();setHistory(h=>e.shiftKey?redo(h):undo(h));}if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();setHistory(redo);}if(e.key==='Delete'&&selected){e.preventDefault();change({...current,shapes:current.shapes.filter(s=>s.id!==selected)});setSelected('');}if(e.key==='Escape'){drag.current=null;setPreview(null);setSelected('');}}
  window.addEventListener('keydown',keyboard);return()=>window.removeEventListener('keydown',keyboard);
 },[change,current,selected]);
 useEffect(()=>{function leave(e:BeforeUnloadEvent){if(dirty){e.preventDefault();e.returnValue='';}}window.addEventListener('beforeunload',leave);return()=>window.removeEventListener('beforeunload',leave);},[dirty]);
 function point(e:PointerEvent<HTMLCanvasElement>){return pointerPoint({x:e.clientX,y:e.clientY},e.currentTarget.getBoundingClientRect(),{width,height});}
 function newShape(type:ShapeType,start:Point,end:Point,id:string):Shape{
  const base={id,type,color,strokeWidth:stroke,...start};if(type==='line'||type==='arrow')return {...base,x2:end.x,y2:end.y};
  if(type==='text')return {...base,text};if(type==='step')return {...base,number:current.shapes.filter(s=>s.type==='step').length+1};return {...base,...rectangle(start,end)};
 }
 function down(e:PointerEvent<HTMLCanvasElement>){
  if(!initialized||!imageReady||busy)return;e.preventDefault();const p=point(e);e.currentTarget.setPointerCapture(e.pointerId);
  if(current.shapes.length>=500&&tool!=='select'&&tool!=='crop'){setError(new Error('Limite de 500 camadas atingido.'));return;}
  if(tool==='select'){const shape=[...current.shapes].reverse().find(s=>hitTest(s,p));setSelected(shape?.id||'');drag.current={start:p,type:tool,shape};return;}
  if(tool==='text'&&!text.trim()){setError(new Error('Escreva o texto da anotação antes de clicar na imagem.'));return;}
  setError(undefined);if(tool==='step'||tool==='text'){const shape=newShape(tool,p,p,crypto.randomUUID());change({...current,shapes:[...current.shapes,shape]});setSelected(shape.id);return;}
  drag.current={start:p,type:tool};setSelected('');
 }
 function moving(e:PointerEvent<HTMLCanvasElement>){const operation=drag.current;if(!operation)return;const p=point(e);
  if(operation.type==='select'){if(operation.shape)setPreview({...current,shapes:current.shapes.map(s=>s.id===operation.shape?.id?moveShape(operation.shape,{x:p.x-operation.start.x,y:p.y-operation.start.y},width,height):s)});}
  else if(operation.type==='crop')setPreview({...current,crop:rectangle(operation.start,p)});
  else setPreview({...current,shapes:[...current.shapes,newShape(operation.type,operation.start,p,'preview')]});
 }
 function up(e:PointerEvent<HTMLCanvasElement>){const operation=drag.current;drag.current=null;if(!operation)return;const p=point(e);setPreview(null);
  if(operation.type==='select'){if(operation.shape)change({...current,shapes:current.shapes.map(s=>s.id===operation.shape?.id?moveShape(operation.shape,{x:p.x-operation.start.x,y:p.y-operation.start.y},width,height):s)});return;}
  if(Math.hypot(p.x-operation.start.x,p.y-operation.start.y)<2)return;
  if(operation.type==='crop'){change({...current,crop:rectangle(operation.start,p)});return;}
  const shape=newShape(operation.type,operation.start,p,crypto.randomUUID());change({...current,shapes:[...current.shapes,shape]});setSelected(shape.id);
 }
 function addByCoordinates(){if(tool==='select')return;if(tool==='text'&&!text.trim()){setError(new Error('Informe um texto para a anotação.'));return;}if(current.shapes.length>=500&&tool!=='crop'){setError(new Error('Limite de 500 camadas atingido.'));return;}
  const start={x:Math.max(0,Math.min(width-1,coordinates.x)),y:Math.max(0,Math.min(height-1,coordinates.y))},end={x:Math.max(0,Math.min(width-1,coordinates.x2)),y:Math.max(0,Math.min(height-1,coordinates.y2))};
  if(tool==='crop'){change({...current,crop:rectangle(start,end)});return;}const shape=newShape(tool,start,end,crypto.randomUUID());change({...current,shapes:[...current.shapes,shape]});setSelected(shape.id);setError(undefined);
 }
 async function save(){setBusy(true);setError(undefined);try{const result=await mutate(`/evidences/${evidence.id}/annotations`,'POST',{expected_version:version,data:serializeAnnotation(current)});const saved=result.annotation.data as AnnotationData;setHistory({past:[],present:saved,future:[]});setBaseline(JSON.stringify(serializeAnnotation(saved)));setVersion(result.version);setConflict(false);setMessage(`Versão anotada ${result.version} salva. O original foi preservado.`);await onSaved();}catch(e){setError(e);if(e instanceof ApiError&&e.status===409)setConflict(true);}finally{setBusy(false);}}
 async function resolve(loadRemote:boolean){setBusy(true);setError(undefined);try{const [remote,remoteAnnotations]=await Promise.all([api(`/evidences/${evidence.id}`),api(`/evidences/${evidence.id}/annotations?page_size=1`)]);const data=(items(remoteAnnotations)[0]?.data||emptyAnnotation(width,height)) as AnnotationData;setVersion(remote.version);setBaseline(JSON.stringify(serializeAnnotation(data)));if(loadRemote){setHistory({past:[],present:data,future:[]});setSelected('');}setConflict(false);setMessage(loadRemote?'Anotações do servidor carregadas.':'Suas anotações foram mantidas. Revise e salve para criar uma nova versão.');await onSaved();}catch(e){setError(e);}finally{setBusy(false);}}
 const selectedShape=current.shapes.find(s=>s.id===selected);
 if(!width||!height)return <ErrorBox error="A imagem não possui dimensões válidas para anotação."/>;
 return <section className="annotation-editor" aria-label="Editor visual de evidências"><div className="annotation-toolbar" role="toolbar" aria-label="Ferramentas de anotação"><Field label="Ferramenta"><select value={tool} onChange={e=>setTool(e.target.value as typeof tool)}><option value="select">Selecionar e mover</option>{Object.entries(shapeLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}<option value="crop">Recortar</option></select></Field><Field label="Cor"><input type="color" value={color} onChange={e=>setColor(e.target.value)}/></Field><Field label="Espessura"><input type="number" min={1} max={100} value={stroke} onChange={e=>setStroke(Math.max(1,Math.min(100,Number(e.target.value)||1)))}/></Field><Field label="Texto da anotação"><input value={text} maxLength={2000} onChange={e=>setText(e.target.value)} placeholder="Clique na imagem para inserir"/></Field><Field label={`Zoom ${Math.round(zoom*100)}%`}><input type="range" min="0.1" max="3" step="0.05" value={zoom} onChange={e=>setZoom(Number(e.target.value))}/></Field><Button type="button" onClick={()=>setZoom(Math.min(1,720/width))}>Ajustar à tela</Button></div>
 <div className="actions"><Button type="button" disabled={!history.past.length||busy} onClick={()=>setHistory(undo)} title="Ctrl+Z">Desfazer</Button><Button type="button" disabled={!history.future.length||busy} onClick={()=>setHistory(redo)} title="Ctrl+Shift+Z">Refazer</Button><Button type="button" disabled={!current.crop} onClick={()=>{const {crop,...data}=current;void crop;change(data);}}>Remover recorte</Button><Button type="button" variant="primary" disabled={!initialized||!imageReady||busy||!dirty||conflict} onClick={save}>{busy?'Salvando…':'Salvar imagem anotada'}</Button><span role="status" className="muted">{dirty?'Alterações pendentes':`Versão ${version}`} · {width} × {height} px</span></div>
 <ErrorBox error={error||annotations.error}/>{message&&<p role="status" className="success">{message}</p>}{conflict&&<div className="conflict" role="alert"><p>Outra pessoa alterou esta evidência. Suas anotações continuam abertas; escolha qual versão usar antes de salvar.</p><Button disabled={busy} onClick={()=>resolve(true)}>Carregar anotações do servidor</Button><Button disabled={busy} onClick={()=>resolve(false)}>Manter minhas anotações e atualizar versão</Button></div>}
 <details><summary>Adicionar anotação por coordenadas (teclado)</summary><div className="annotation-toolbar">{(['x','y','x2','y2'] as const).map(key=><Field key={key} label={`${key.toUpperCase()} em pixels`}><input type="number" min={0} max={key.includes('x')?width-1:height-1} value={coordinates[key]} onChange={e=>setCoordinates(previous=>({...previous,[key]:Number(e.target.value)||0}))}/></Field>)}<Button disabled={!initialized||!imageReady||tool==='select'||busy} onClick={addByCoordinates}>Inserir {tool==='crop'?'recorte':tool==='select'?'anotação':shapeLabels[tool]}</Button></div></details>
 {!initialized||!imageReady?<Loading/>:null}<div className="annotation-layout"><div className="annotation-stage" style={{overflow:'auto',maxHeight:'70vh',border:'1px solid var(--line)',background:'#111827'}}><canvas ref={canvas} width={width} height={height} style={{width:width*zoom,height:height*zoom,maxWidth:'none',touchAction:'none',display:'block',cursor:tool==='select'?'move':'crosshair'}} aria-label="Imagem original com prévia das anotações" onPointerDown={down} onPointerMove={moving} onPointerUp={up} onPointerCancel={()=>{drag.current=null;setPreview(null);}} tabIndex={0}/></div>
 <aside className="annotation-layers" aria-label="Camadas de anotação"><h3>Camadas ({current.shapes.length})</h3><p className="muted">A última camada aparece por cima. Ctrl+Z desfaz; Delete remove a camada selecionada.</p><ol>{current.shapes.map((shape,index)=><li key={shape.id}><Button type="button" variant={selected===shape.id?'active':''} onClick={()=>{setSelected(shape.id);setTool('select');}}>{index+1}. {shapeLabels[shape.type]} {shape.type==='step'?shape.number:shape.type==='text'?shape.text?.slice(0,24):''}</Button><span className="actions"><Button type="button" aria-label={`Mover camada ${index+1} para trás`} disabled={!index} onClick={()=>change(reorderShape(current,shape.id,-1))}>↓</Button><Button type="button" aria-label={`Mover camada ${index+1} para frente`} disabled={index===current.shapes.length-1} onClick={()=>change(reorderShape(current,shape.id,1))}>↑</Button><Button type="button" aria-label={`Excluir camada ${index+1}`} onClick={()=>{change({...current,shapes:current.shapes.filter(s=>s.id!==shape.id)});setSelected('');}}>×</Button></span></li>)}</ol>{selectedShape&&<div className="form-grid"><Field label="Texto selecionado"><input disabled={selectedShape.type!=='text'} value={selectedShape.text||''} maxLength={2000} onChange={e=>change({...current,shapes:current.shapes.map(s=>s.id===selected?{...s,text:e.target.value}:s)})}/></Field><Field label="Cor da camada"><input type="color" value={selectedShape.color} onChange={e=>change({...current,shapes:current.shapes.map(s=>s.id===selected?{...s,color:e.target.value}:s)})}/></Field><Field label="Espessura da camada"><input type="number" min={1} max={100} value={selectedShape.strokeWidth} onChange={e=>change({...current,shapes:current.shapes.map(s=>s.id===selected?{...s,strokeWidth:Math.max(1,Math.min(100,Number(e.target.value)||1))}:s)})}/></Field></div>}</aside></div><p className="muted">Arraste para desenhar ou recortar. Redação opaca remove os pixels apenas da versão anotada. O desfoque tem prévia aproximada; confira o arquivo gerado antes de compartilhá-lo.</p></section>;
}
