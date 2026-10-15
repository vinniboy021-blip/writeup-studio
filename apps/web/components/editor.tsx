// SPDX-License-Identifier: MIT
"use client";
import {useCallback,useEffect,useRef,useState,type FormEvent} from 'react';
import {useQueryClient} from '@tanstack/react-query';
import {useForm} from 'react-hook-form';
import {zodResolver} from '@hookform/resolvers/zod';
import {z} from 'zod';
import {DndContext,KeyboardSensor,PointerSensor,closestCenter,useSensor,useSensors,type DragEndEvent} from '@dnd-kit/core';
import {SortableContext,arrayMove,sortableKeyboardCoordinates,useSortable,verticalListSortingStrategy} from '@dnd-kit/sortable';
import {CSS} from '@dnd-kit/utilities';
import {api,mutate,items,date,query,type Row,type Section,type User} from '../lib/api';
import {SerialSaver,type SaveState} from '../lib/autosave';
import {asDraft,draftKey,mergeSections,readRecovery,signature,validateDocument,type RecoveredDraft,type WriteupDraft} from '../lib/editor-document';
import {Button,Empty,ErrorBox,Field,Loading,Modal,Pager,ResourceSelect,Table,useData} from './ui';
import {Markdown} from './markdown';
import {RichEditor} from './rich-editor';
import {CollaborationPanel} from './collaboration';
import {ExportPanel} from './exports';

const states:Record<SaveState,string>={saved:'Salvo',pending:'Alterações pendentes',saving:'Salvando…',error:'Falha ao salvar',conflict:'Conflito de versões'};
const createSchema=z.object({title:z.string().trim().min(1,'Informe um título.').max(240),challenge_id:z.string(),team_id:z.string(),template_id:z.string(),visibility:z.enum(['private','team'])}).refine(v=>v.visibility!=='team'||Boolean(v.team_id),{path:['team_id'],message:'Escolha uma equipe para compartilhar.'});
type CreateValues=z.infer<typeof createSchema>;
type Props={user?:User;initialId?:string;onOpenEvidence?:(id:string)=>void;onChange?:(id:string)=>void;onDirtyChange?:(dirty:boolean)=>void};

export function WriteupStudio({user,initialId,onOpenEvidence,onChange,onDirtyChange}:Props){
 const client=useQueryClient();
 const [row,setRow]=useState<Row|null>(null),[draft,setDraft]=useState<WriteupDraft|null>(null);
 const [saveState,setSaveState]=useState<SaveState>('saved'),[error,setError]=useState<unknown>();
 const [loading,setLoading]=useState(false),[creating,setCreating]=useState(false),[mode,setMode]=useState<'markdown'|'rich'>('markdown');
 const [preview,setPreview]=useState(true),[numbered,setNumbered]=useState(true),[fullscreen,setFullscreen]=useState(false);
 const [recovery,setRecovery]=useState<RecoveredDraft|null>(null),[conflict,setConflict]=useState<Row|null>(null),[showConflict,setShowConflict]=useState(false);
 const [page,setPage]=useState(1),[filter,setFilter]=useState(''),[statusFilter,setStatusFilter]=useState('');
 const [localError,setLocalError]=useState(''),[busy,setBusy]=useState(false);
 const saver=useRef<SerialSaver<WriteupDraft>|null>(null),latest=useRef<WriteupDraft|null>(null),activeId=useRef(''),mounted=useRef(true),openRequest=useRef(0),timer=useRef<ReturnType<typeof setTimeout>|null>(null);
 const dirtyCallback=useRef(onDirtyChange);dirtyCallback.current=onDirtyChange;
 useEffect(()=>{dirtyCallback.current?.(saveState!=='saved');},[saveState]);
 const list=useData('/writeups?'+query({page,page_size:20,q:filter,status:statusFilter}));
 const memberships=useData(row?.team_id?'/teams/'+row.team_id+'/members':'/teams',Boolean(row?.team_id));
 const member=items(memberships.data).find(m=>m.user_id===user?.id);
 const readOnly=Boolean(user&&row&&row.owner_id!==user.id&&!user.is_admin&&!(row.visibility==='team'&&member&&['manager','editor'].includes(member.role)));
 const sensors=useSensors(useSensor(PointerSensor,{activationConstraint:{distance:8}}),useSensor(KeyboardSensor,{coordinateGetter:sortableKeyboardCoordinates}));

 const loadConflict=useCallback(async()=>{if(!activeId.current)return;setShowConflict(true);try{const remote=await api('/writeups/'+activeId.current);if(mounted.current)setConflict(remote);}catch(e){if(mounted.current)setError(e);}},[]);
 function persist(value:WriteupDraft,version=saver.current?.version||row?.version||1){
  if(!activeId.current)return;
  try{localStorage.setItem(draftKey(activeId.current),JSON.stringify({schema_version:1,writeup_id:activeId.current,base_version:version,draft:value,saved_at:new Date().toISOString()}));setLocalError('');}
  catch{setLocalError('Não foi possível manter uma cópia local. Mantenha esta janela aberta até salvar no servidor.');}
 }
 function install(value:Row,inspectRecovery=true){
  saver.current?.dispose();if(timer.current)clearTimeout(timer.current);
  activeId.current=value.id;const initial=asDraft(value);latest.current=initial;
  setRow(value);setDraft(initial);setSaveState('saved');setError(undefined);setConflict(null);setShowConflict(false);setRecovery(null);
  saver.current=new SerialSaver<WriteupDraft>(value.version,async(snapshot,version)=>{
   if(!snapshot.title.trim())throw new Error('O título do writeup é obrigatório.');
   if(!validateDocument(snapshot.document))throw new Error('Revise títulos, tamanho e identificadores das seções.');
   const result=await mutate('/writeups/'+value.id,'PATCH',{...snapshot,expected_version:version});
   if(mounted.current&&activeId.current===value.id)setRow(result);
   return result as {version:number};
  },(state,e)=>{if(mounted.current&&activeId.current===value.id){setSaveState(state);setError(e);if(state==='conflict')void loadConflict();}},(snapshot,version)=>{
   if(!mounted.current||activeId.current!==value.id)return;
   try{if(signature(latest.current)===signature(snapshot))localStorage.removeItem(draftKey(value.id));else if(latest.current)persist(latest.current,version);}catch{}
   void client.invalidateQueries({predicate:q=>typeof q.queryKey[0]==='string'&&q.queryKey[0].startsWith('/writeups')});
   void list.refetch();
  });
  if(inspectRecovery){try{const found=readRecovery(localStorage.getItem(draftKey(value.id)),value.id);if(found&&signature(found.draft)!==signature(initial))setRecovery(found);else if(found)localStorage.removeItem(draftKey(value.id));}catch{}}
 }
 async function open(id:string){
  if(saver.current?.hasPending()){setError(new Error('Salve ou resolva as alterações atuais antes de abrir outro documento.'));return;}
  const request=++openRequest.current;setLoading(true);setError(undefined);
  try{const value=await api('/writeups/'+id);if(request===openRequest.current&&mounted.current){install(value);onChange?.(id);}}
  catch(e){if(request===openRequest.current)setError(e);}finally{if(request===openRequest.current)setLoading(false);}
 }
 // Initial document comes from shell links. A changing ID never silently drops pending edits.
 useEffect(()=>{if(initialId&&initialId!==activeId.current)void open(initialId);},[initialId]); // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;saver.current?.dispose();if(timer.current)clearTimeout(timer.current);};},[]);
 function edit(next:WriteupDraft){if(readOnly)return;latest.current=next;setDraft(next);persist(next);saver.current?.enqueue(next);if(timer.current)clearTimeout(timer.current);timer.current=setTimeout(()=>void saver.current?.flush(),900);}
 function editSection(id:string,key:'title'|'markdown',value:string){if(!latest.current)return;edit({...latest.current,document:{schema_version:1,sections:latest.current.document.sections.map(s=>s.id===id?{...s,[key]:value}:s)}});}
 async function saveNow(){if(timer.current)clearTimeout(timer.current);await saver.current?.flush();return !saver.current?.hasPending();}
 async function refresh(){if(saver.current?.hasPending()){await loadConflict();return;}if(activeId.current){const value=await api('/writeups/'+activeId.current);install(value);}}
 useEffect(()=>{const before=(event:BeforeUnloadEvent)=>{if(saver.current?.hasPending()){event.preventDefault();event.returnValue='';}};const key=(event:KeyboardEvent)=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();void saveNow();}if(event.key==='Escape')setFullscreen(false);};window.addEventListener('beforeunload',before);window.addEventListener('keydown',key);return()=>{window.removeEventListener('beforeunload',before);window.removeEventListener('keydown',key);};},[]); // eslint-disable-line react-hooks/exhaustive-deps
 function reorder(event:DragEndEvent){if(!latest.current||readOnly||!event.over||event.active.id===event.over.id)return;const sections=latest.current.document.sections;edit({...latest.current,document:{schema_version:1,sections:arrayMove(sections,sections.findIndex(s=>s.id===event.active.id),sections.findIndex(s=>s.id===event.over?.id))}});}
 function move(id:string,offset:number){if(!latest.current)return;const sections=latest.current.document.sections;const index=sections.findIndex(s=>s.id===id);if(index+offset<0||index+offset>=sections.length)return;edit({...latest.current,document:{schema_version:1,sections:arrayMove(sections,index,index+offset)}});}
 async function recover(){if(!recovery||!row)return;latest.current=recovery.draft;setDraft(recovery.draft);setRecovery(null);persist(recovery.draft,recovery.base_version);saver.current?.enqueue(recovery.draft);if(recovery.base_version!==row.version){setSaveState('conflict');await loadConflict();}else await saver.current?.flush();}
 async function discardRemote(){setBusy(true);try{const remote=await api('/writeups/'+activeId.current);if(saver.current?.isRunning())await saver.current.flush();saver.current?.discard();localStorage.removeItem(draftKey(remote.id));install(remote,false);}catch(e){setError(e);}finally{setBusy(false);}}
 async function resolveConflict(selected:WriteupDraft,remoteVersion:number){setBusy(true);try{const remote=await api('/writeups/'+activeId.current);if(remote.version!==remoteVersion){setConflict(remote);throw new Error('Outra edição chegou durante a revisão. Revise a nova versão do servidor.');}await saver.current?.flush();saver.current?.resume(remote.version);latest.current=selected;setDraft(selected);persist(selected,remote.version);saver.current?.enqueue(selected);setShowConflict(false);setConflict(null);await saver.current?.flush();}catch(e){setError(e);}finally{setBusy(false);}}
 async function restored(value:Row){install(value,false);try{localStorage.removeItem(draftKey(value.id));}catch{}await list.refetch();}
 async function evidenceChange(action:()=>Promise<unknown>){if(!await saveNow())throw new Error('Resolva o salvamento antes de associar evidências.');const response=await action() as Row;saver.current?.resume(response.writeup_version);await refresh();}
 function insertEvidence(item:Row,sectionId:string){if(!latest.current)return;const section=latest.current.document.sections.find(s=>s.id===sectionId);if(!section)return;const image=String(item.mime_type||'').startsWith('image/');const caption=String(item.name||'Evidência').replace(/[\[\]\n]/g,'');const link=(image?'!':'')+'['+caption+'](/api/v1/evidences/'+item.evidence_id+'/download)';editSection(sectionId,'markdown',section.markdown+'\n\n'+link+'\n');}

 return <div className={'studio-shell'+(fullscreen?' studio-fullscreen':'')}>
  <div className="toolbar"><Field label="Pesquisar writeups"><input value={filter} onChange={e=>{setFilter(e.target.value);setPage(1);}} placeholder="Título do documento"/></Field><Field label="Filtrar status"><select value={statusFilter} onChange={e=>{setStatusFilter(e.target.value);setPage(1);}}><option value="">Todos</option>{[['draft','Rascunho'],['in_progress','Em andamento'],['completed','Concluído'],['approved','Aprovado'],['published','Publicado']].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></Field><Button variant="primary" disabled={Boolean(saver.current?.hasPending())} onClick={()=>setCreating(true)}>+ Novo writeup</Button></div>
  <ErrorBox error={error||list.error}/>{localError&&<p role="alert">{localError}</p>}
  <details open={!row} className="panel"><summary>Documentos disponíveis · {list.data?.total||0}</summary>{list.isPending?<Loading/>:<Table rows={items(list.data)} columns={[{key:'title',label:'Título'},{key:'status',label:'Status'},{key:'version',label:'Versão'},{key:'updated_at',label:'Atualizado',render:r=>date(r.updated_at)}]} onOpen={r=>void open(r.id)}/>}<Pager page={page} total={list.data?.total||0} onChange={setPage}/></details>
  {loading&&<Loading/>}
  {!row&&!loading&&<Empty>Crie um writeup a partir de um template ou reabra um documento existente.</Empty>}
  {row&&draft&&<>
   <section className="panel studio-toolbar" aria-label="Documento atual">
    <Field label="Título do writeup"><input value={draft.title} maxLength={240} disabled={readOnly} onChange={e=>edit({...draft,title:e.target.value})}/></Field>
    <div className="actions"><span role="status" aria-live="polite">{states[saveState]} · versão {row.version}</span><Button disabled={readOnly||saveState==='conflict'} onClick={()=>void saveNow()}>Salvar agora</Button>{saveState==='error'&&<Button onClick={()=>void saveNow()}>Tentar novamente</Button>}{saveState==='conflict'&&<Button onClick={()=>void loadConflict()}>Revisar conflito</Button>}<Button onClick={()=>setFullscreen(!fullscreen)} aria-pressed={fullscreen}>{fullscreen?'Sair da tela cheia':'Tela cheia'}</Button></div>
    {readOnly&&<p className="muted">Acesso de leitura. As permissões de edição são verificadas pelo servidor.</p>}
    <div className="form-grid"><Field label="Status do documento"><select disabled={readOnly} value={draft.status} onChange={e=>edit({...draft,status:e.target.value as WriteupDraft['status']})}><option value="draft">Rascunho</option><option value="in_progress">Em andamento</option><option value="completed">Concluído</option></select></Field><Field label="Visibilidade do documento"><select disabled={readOnly||Boolean(user&&row.owner_id!==user.id&&!user.is_admin&&member?.role!=='manager')} value={draft.visibility} onChange={e=>edit({...draft,visibility:e.target.value as WriteupDraft['visibility']})}><option value="private">Privado</option>{row.team_id&&<option value="team">Equipe</option>}</select></Field>{(['tags','tools','languages'] as const).map((key,i)=><Field key={key} label={['Tags','Ferramentas utilizadas','Linguagens utilizadas'][i]}><input disabled={readOnly} value={draft[key].join(', ')} onChange={e=>edit({...draft,[key]:e.target.value.split(',').map(v=>v.trim()).filter(Boolean)})}/></Field>)}</div>
    <p className="muted">Estado da versão salva: {row.status}. Ctrl/⌘+S salva · Escape sai da tela cheia · autosave após 0,9 s. Documente somente comandos e resultados com origem identificável.</p>
   </section>
   {recovery&&<section className="panel" role="alert"><h3>Alterações locais recuperáveis</h3><p>Existe um rascunho de {date(recovery.saved_at)} baseado na versão {recovery.base_version}. A versão do servidor é {row.version}.</p><div className="actions"><Button disabled={readOnly} onClick={()=>void recover()}>Revisar e recuperar rascunho</Button><Button onClick={()=>{localStorage.removeItem(draftKey(row.id));setRecovery(null);}}>Descartar cópia local</Button></div></section>}
   <div className="toolbar"><div className="actions" role="group" aria-label="Modo de edição"><Button aria-pressed={mode==='markdown'} onClick={()=>setMode('markdown')}>Markdown</Button><Button aria-pressed={mode==='rich'} onClick={()=>setMode('rich')}>Rich-text</Button><Button aria-pressed={preview} onClick={()=>setPreview(!preview)}>Visualização prévia</Button><Button aria-pressed={numbered} onClick={()=>setNumbered(!numbered)}>Numerar seções</Button></div></div>
   <nav className="studio-toc" aria-label="Índice do writeup"><strong>Índice</strong>{draft.document.sections.map((section,index)=><a href={'#section-'+section.id} key={section.id}>{numbered?`${index+1}. `:''}{section.title||'Seção sem título'}</a>)}</nav>
   <div className={'section-grid'+(preview?' with-preview':'')}><article aria-label="Seções editáveis">
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={reorder}><SortableContext items={draft.document.sections.map(s=>s.id)} strategy={verticalListSortingStrategy}>
     {draft.document.sections.map((section,index)=><SortableSection key={section.id} section={section} index={index} count={draft.document.sections.length} mode={mode} readOnly={readOnly} numbered={numbered} onEdit={(key,value)=>editSection(section.id,key,value)} onMove={offset=>move(section.id,offset)} onRemove={()=>edit({...draft,document:{schema_version:1,sections:draft.document.sections.filter(s=>s.id!==section.id)}})}/>)}
    </SortableContext></DndContext>
    <Button disabled={readOnly||draft.document.sections.length>=200} onClick={()=>edit({...draft,document:{schema_version:1,sections:[...draft.document.sections,{id:crypto.randomUUID(),title:'Nova seção',markdown:''}]}})}>+ Adicionar seção</Button>
   </article>{preview&&<article className="panel studio-preview" aria-label="Visualização prévia"><h1>{draft.title}</h1>{draft.document.sections.map((section,index)=><section key={section.id}><h2>{numbered?`${index+1}. `:''}{section.title}</h2><Markdown value={section.markdown}/></section>)}</article>}</div>
   <Revisions writeup={row} disabled={readOnly||saveState!=='saved'} onRestored={restored}/>
   <EvidenceLinks writeup={row} sections={draft.document.sections} disabled={readOnly||saveState!=='saved'} onMutate={evidenceChange} onInsert={insertEvidence} onOpenEvidence={onOpenEvidence}/>
   <fieldset disabled={saveState!=='saved'} className="studio-workflow"><legend>Revisão e exportação da versão salva</legend><CollaborationPanel writeup={row} onChanged={()=>void refresh().catch(setError)}/><ExportPanel writeup={row} onChanged={()=>void refresh().catch(setError)}/></fieldset>
  </>}
  {creating&&<CreateWriteup onClose={()=>setCreating(false)} onCreated={async value=>{setCreating(false);install(value,false);onChange?.(value.id);await list.refetch();}}/>}
  {showConflict&&draft&&<Modal title="Conflito de versões — revisão obrigatória" onClose={()=>setShowConflict(false)}>{conflict?<ConflictReview key={conflict.version} local={draft} remote={conflict} busy={busy} onRefresh={()=>void loadConflict()} onRemote={()=>void discardRemote()} onResolve={(value)=>void resolveConflict(value,conflict.version)}/>:<Loading/>}<ErrorBox error={error}/></Modal>}
 </div>;
}

function CreateWriteup({onCreated,onClose}:{onCreated:(row:Row)=>Promise<void>;onClose:()=>void}){
 const [error,setError]=useState<unknown>(),locked=useRef(false);
 const {register,handleSubmit,formState:{errors,isSubmitting},watch,setValue}=useForm<CreateValues>({resolver:zodResolver(createSchema),defaultValues:{title:'',challenge_id:'',team_id:'',template_id:'',visibility:'private'}});
 const values=watch();
 async function submit(value:CreateValues){if(locked.current)return;locked.current=true;try{const result=await mutate('/writeups','POST',{title:value.title,challenge_id:value.challenge_id||null,team_id:value.team_id||null,template_id:value.template_id||null,visibility:value.visibility});await onCreated(result);}catch(e){setError(e);}finally{locked.current=false;}}
 return <Modal title="Criar writeup" onClose={()=>{if(!locked.current)onClose();}}><form onSubmit={handleSubmit(submit)} className="form-grid"><Field label="Título"><input {...register('title')} maxLength={240} autoFocus aria-invalid={Boolean(errors.title)}/></Field>{errors.title&&<p role="alert">{errors.title.message}</p>}<ResourceSelect path="/templates?page_size=100" label="Template" value={values.template_id} onChange={v=>setValue('template_id',v)}/><ResourceSelect path="/challenges?page_size=100" label="Desafio associado" value={values.challenge_id} onChange={v=>setValue('challenge_id',v)}/><ResourceSelect path="/teams?page_size=100" label="Equipe" value={values.team_id} onChange={v=>setValue('team_id',v,{shouldValidate:true})}/>{errors.team_id&&<p role="alert">{errors.team_id.message}</p>}<Field label="Visibilidade"><select {...register('visibility')}><option value="private">Privado</option><option value="team">Equipe</option></select></Field><ErrorBox error={error}/><Button variant="primary" disabled={isSubmitting}>{isSubmitting?'Criando…':'Criar documento'}</Button></form></Modal>;
}

function SortableSection({section,index,count,mode,readOnly,numbered,onEdit,onMove,onRemove}:{section:Section;index:number;count:number;mode:'markdown'|'rich';readOnly:boolean;numbered:boolean;onEdit:(key:'title'|'markdown',value:string)=>void;onMove:(offset:number)=>void;onRemove:()=>void}){
 const {attributes,listeners,setNodeRef,transform,transition,isDragging}=useSortable({id:section.id,disabled:readOnly});
 return <section id={'section-'+section.id} ref={setNodeRef} style={{transform:CSS.Transform.toString(transform),transition,opacity:isDragging?0.6:1}} className="panel section-card"><div className="actions"><Button type="button" disabled={readOnly} {...attributes} {...listeners} aria-label={'Arrastar seção '+section.title} title="Use espaço e setas para reordenar">⠿</Button><strong>{numbered?`${index+1}. `:''}Seção</strong><Button type="button" aria-label={'Mover '+section.title+' para cima'} disabled={readOnly||index===0} onClick={()=>onMove(-1)}>↑</Button><Button type="button" aria-label={'Mover '+section.title+' para baixo'} disabled={readOnly||index===count-1} onClick={()=>onMove(1)}>↓</Button><Button type="button" disabled={readOnly} aria-label={'Remover seção '+section.title} onClick={onRemove}>Remover</Button></div><Field label="Título da seção"><input disabled={readOnly} maxLength={240} value={section.title} onChange={e=>onEdit('title',e.target.value)}/></Field>{mode==='markdown'?<Field label={'Markdown de '+section.title}><textarea className="markdown-input" disabled={readOnly} value={section.markdown} maxLength={1000000} rows={10} onChange={e=>onEdit('markdown',e.target.value)}/></Field>:<RichEditor label={'Conteúdo de '+section.title} readOnly={readOnly} value={section.markdown} onChange={value=>onEdit('markdown',value)}/>}<small>ID para links internos: #section-{section.id}</small></section>;
}

function ConflictReview({local,remote,busy,onRemote,onRefresh,onResolve}:{local:WriteupDraft;remote:Row;busy:boolean;onRemote:()=>void;onRefresh:()=>void;onResolve:(value:WriteupDraft)=>void}){
 const remoteDraft=asDraft(remote),ids=Array.from(new Set([...local.document.sections.map(s=>s.id),...remoteDraft.document.sections.map(s=>s.id)]));
 const [title,setTitle]=useState<'local'|'remote'|''>(local.title===remote.title?'remote':''),[metadata,setMetadata]=useState<'local'|'remote'>('remote');
 const [choices,setChoices]=useState<Record<string,'local'|'remote'|'remove'|''>>(()=>Object.fromEntries(ids.map(id=>[id,signature(local.document.sections.find(s=>s.id===id))===signature(remoteDraft.document.sections.find(s=>s.id===id))?'remote':''])));
 const ready=Boolean(title)&&ids.every(id=>Boolean(choices[id]));
 return <><p>O servidor está na versão {remote.version}. Autosave está pausado; seu texto local permanece disponível. Selecione a origem de cada seção diferente antes de mesclar.</p><div className="actions"><Button disabled={busy} onClick={onRefresh}>Buscar versão mais recente</Button><Button disabled={busy} onClick={onRemote}>Descartar alterações locais e usar servidor</Button></div><div className="two-columns"><article><h3>Local</h3><strong>{local.title}</strong></article><article><h3>Servidor</h3><strong>{remote.title}</strong></article></div><Field label="Título a manter"><select value={title} onChange={e=>setTitle(e.target.value as typeof title)}><option value="">Escolha o título</option><option value="local">Título local</option><option value="remote">Título do servidor</option></select></Field><Field label="Status, visibilidade e tags a manter"><select value={metadata} onChange={e=>setMetadata(e.target.value as typeof metadata)}><option value="remote">Metadados do servidor</option><option value="local">Metadados locais</option></select></Field>{ids.map(id=>{const a=local.document.sections.find(s=>s.id===id),b=remoteDraft.document.sections.find(s=>s.id===id);return <section className="panel" key={id}><h3>{a?.title||b?.title}</h3><div className="two-columns"><pre>{a?`${a.title}\n\n${a.markdown}`:'Seção removida localmente'}</pre><pre>{b?`${b.title}\n\n${b.markdown}`:'Seção removida no servidor'}</pre></div><Field label={'Escolher versão da seção '+(a?.title||b?.title)}><select value={choices[id]} onChange={e=>setChoices({...choices,[id]:e.target.value as 'local'|'remote'|'remove'})}><option value="">Escolha a origem</option><option value="local">Local{!a?' (removida)':''}</option><option value="remote">Servidor{!b?' (removida)':''}</option><option value="remove">Remover seção</option></select></Field></section>;})}<p className="muted">A mesclagem mantém a ordem local e acrescenta seções exclusivas do servidor. Você poderá reorganizar depois.</p><Button variant="primary" disabled={busy||!ready} onClick={()=>onResolve({... (metadata==='local'?local:remoteDraft),title:title==='local'?local.title:remote.title,document:mergeSections(local.document,remoteDraft.document,choices as Record<string,'local'|'remote'|'remove'>)})}>Salvar mesclagem revisada</Button></>;
}

function Revisions({writeup,disabled,onRestored}:{writeup:Row;disabled:boolean;onRestored:(value:Row)=>Promise<void>}){
 const [page,setPage]=useState(1),[from,setFrom]=useState(''),[to,setTo]=useState(''),[diff,setDiff]=useState(''),[error,setError]=useState<unknown>(),[busy,setBusy]=useState(false),[selected,setSelected]=useState<Row|null>(null);
 const data=useData('/writeups/'+writeup.id+'/revisions?'+query({page,page_size:20}));
 useEffect(()=>{setPage(1);setFrom('');setTo('');setDiff('');},[writeup.id]);
 async function restore(revision:Row){setBusy(true);try{const value=await mutate('/writeups/'+writeup.id+'/revisions/'+revision.id+'/restore','POST',{expected_version:writeup.version});await onRestored(value);setSelected(null);await data.refetch();}catch(e){setError(e);}finally{setBusy(false);}}
 return <details className="panel"><summary>Histórico, comparação e restauração</summary><ErrorBox error={error||data.error}/>{data.isPending?<Loading/>:<Table rows={items(data.data)} columns={[{key:'version',label:'Versão'},{key:'title',label:'Título'},{key:'message',label:'Alteração'},{key:'author_id',label:'Autor'},{key:'created_at',label:'Data',render:r=>date(r.created_at)}]} onOpen={setSelected}/>}<Pager page={page} total={data.data?.total||0} onChange={setPage}/><form className="inline-form" onSubmit={async e=>{e.preventDefault();try{const result=await api('/writeups/'+writeup.id+'/diff?'+query({from_version:Number(from),to_version:Number(to)}));setDiff(result.diff||'Nenhuma alteração entre as revisões.');setError(undefined);}catch(err){setError(err);}}}><Field label="Versão inicial"><input type="number" min={1} max={writeup.version} required value={from} onChange={e=>setFrom(e.target.value)}/></Field><Field label="Versão final"><input type="number" min={1} max={writeup.version} required value={to} onChange={e=>setTo(e.target.value)}/></Field><Button>Comparar versões</Button></form>{diff&&<pre className="revision-diff" aria-label="Diferenças entre versões">{diff}</pre>}{selected&&<Modal title={'Revisão '+selected.version} onClose={()=>setSelected(null)}><h3>{selected.title}</h3>{selected.document.sections.map((section:Section)=><section key={section.id}><h4>{section.title}</h4><Markdown value={section.markdown}/></section>)}<p>A restauração cria uma nova revisão; o histórico original permanece intacto.</p><Button disabled={disabled||busy} variant="primary" onClick={()=>void restore(selected)}>{busy?'Restaurando…':'Restaurar esta versão'}</Button></Modal>}</details>;
}

function EvidenceLinks({writeup,sections,disabled,onMutate,onInsert,onOpenEvidence}:{writeup:Row;sections:Section[];disabled:boolean;onMutate:(action:()=>Promise<unknown>)=>Promise<void>;onInsert:(row:Row,sectionId:string)=>void;onOpenEvidence?:(id:string)=>void}){
 const [evidenceId,setEvidenceId]=useState(''),[sectionId,setSectionId]=useState(''),[error,setError]=useState<unknown>(),[busy,setBusy]=useState(false);
 const links=useData('/writeups/'+writeup.id+'/evidences');
 useEffect(()=>{setEvidenceId('');setSectionId('');},[writeup.id]);
 async function act(action:()=>Promise<unknown>){setBusy(true);try{await onMutate(action);await links.refetch();setError(undefined);}catch(e){setError(e);}finally{setBusy(false);}}
 async function attach(e:FormEvent){e.preventDefault();await act(()=>mutate('/writeups/'+writeup.id+'/evidences','POST',{evidence_id:evidenceId,section_id:sectionId||null,position:items(links.data).length}));}
 return <details className="panel"><summary>Evidências associadas ao documento</summary><ErrorBox error={error||links.error}/><form onSubmit={attach} className="inline-form"><ResourceSelect path="/evidences?page_size=100" label="Evidência autorizada" value={evidenceId} onChange={setEvidenceId}/><Field label="Seção da evidência"><select value={sectionId} onChange={e=>setSectionId(e.target.value)}><option value="">Documento inteiro</option>{sections.map(s=><option value={s.id} key={s.id}>{s.title}</option>)}</select></Field><Button disabled={disabled||busy||!evidenceId}>Associar evidência</Button></form>{items(links.data).map(item=><article className="evidence-link" key={item.id}><strong>{item.name}</strong><small>SHA-256: {item.sha256}</small><div className="actions">{onOpenEvidence&&<Button onClick={()=>onOpenEvidence(item.evidence_id)}>Abrir evidência</Button>}<a className="button" href={'/api/v1/evidences/'+item.evidence_id+'/download'}>Baixar original autenticado</a><Button disabled={disabled||!sections.length} onClick={()=>onInsert(item,item.section_id||sectionId||sections[0].id)}>Inserir no texto da seção</Button><Button disabled={disabled||busy} onClick={()=>void act(()=>mutate('/writeups/'+writeup.id+'/evidences/'+item.evidence_id,'DELETE'))}>Remover associação</Button></div></article>)}</details>;
}
