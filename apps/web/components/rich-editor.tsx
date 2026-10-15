// SPDX-License-Identifier: MIT
"use client";
import {useEffect,useRef,useState} from 'react';
import {EditorContent,useEditor} from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Image from '@tiptap/extension-image';
import {TableKit} from '@tiptap/extension-table';
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight';
import {common,createLowlight} from 'lowlight';
import DOMPurify from 'dompurify';
import {htmlToMarkdown,markdownToHtml} from '../lib/rich-markdown';
import {Button} from './ui';

const lowlight=createLowlight(common);
const languages=['plaintext','bash','python','javascript','typescript','sql','json','yaml','html','css','c','cpp','rust','go','mermaid'];
export function RichEditor({value,onChange,label,readOnly=false}:{value:string;onChange:(value:string)=>void;label:string;readOnly?:boolean}){
 const latest=useRef(value),update=useRef(onChange);update.current=onChange;
 const [language,setLanguage]=useState('bash'),[link,setLink]=useState(''),[image,setImage]=useState('');
 const editor=useEditor({immediatelyRender:false,shouldRerenderOnTransaction:true,
  extensions:[StarterKit.configure({codeBlock:false,link:{openOnClick:false,HTMLAttributes:{rel:'noopener noreferrer'}}}),Image.configure({allowBase64:false}),TableKit.configure({table:{resizable:false}}),CodeBlockLowlight.configure({lowlight})],
  content:typeof window==='undefined'?markdownToHtml(value):DOMPurify.sanitize(markdownToHtml(value)),editable:!readOnly,
  editorProps:{attributes:{'aria-label':label,role:'textbox','aria-multiline':'true',class:'rich-content'}},
  onUpdate:({editor:current})=>{const markdown=htmlToMarkdown(current.getHTML());latest.current=markdown;update.current(markdown);}
 });
 useEffect(()=>{if(editor&&value!==latest.current){latest.current=value;editor.commands.setContent(DOMPurify.sanitize(markdownToHtml(value)),{emitUpdate:false});}},[editor,value]);
 useEffect(()=>{editor?.setEditable(!readOnly);},[editor,readOnly]);
 if(!editor)return <p role="status">Carregando editor…</p>;
 function safeUrl(value:string){return /^https?:\/\//i.test(value)||/^#section-[A-Za-z0-9_-]+$/.test(value)||/^\/api\/v1\/evidences\/[A-Za-z0-9_-]+\/download$/.test(value);}
 return <div className="rich-editor"><div className="rich-toolbar" role="toolbar" aria-label={'Formatação de '+label}>
  <Button type="button" disabled={readOnly} aria-label="Negrito" aria-pressed={editor.isActive('bold')} onClick={()=>editor.chain().focus().toggleBold().run()}><strong>B</strong></Button>
  <Button type="button" disabled={readOnly} aria-label="Itálico" aria-pressed={editor.isActive('italic')} onClick={()=>editor.chain().focus().toggleItalic().run()}><em>I</em></Button>
  <Button type="button" disabled={readOnly} aria-label="Riscar texto" onClick={()=>editor.chain().focus().toggleStrike().run()}>S̶</Button>
  <Button type="button" disabled={readOnly} aria-label="Código inline" onClick={()=>editor.chain().focus().toggleCode().run()}>Código</Button>
  <Button type="button" disabled={readOnly} onClick={()=>editor.chain().focus().toggleHeading({level:3}).run()}>Título</Button>
  <Button type="button" disabled={readOnly} onClick={()=>editor.chain().focus().toggleBulletList().run()}>Lista</Button>
  <Button type="button" disabled={readOnly} onClick={()=>editor.chain().focus().toggleOrderedList().run()}>Etapas 1–2–3</Button>
  <Button type="button" disabled={readOnly} onClick={()=>editor.chain().focus().toggleBlockquote().run()}>Citação</Button>
  <Button type="button" disabled={readOnly} onClick={()=>editor.chain().focus().insertContent({type:'blockquote',content:[{type:'paragraph',content:[{type:'text',text:'[!NOTE] ' }]}]}).run()}>Callout</Button>
  <label>Linguagem <select aria-label="Linguagem do bloco de código" value={language} onChange={e=>{setLanguage(e.target.value);if(editor.isActive('codeBlock')&&!readOnly)editor.chain().focus().updateAttributes('codeBlock',{language:e.target.value}).run();}}>{languages.map(l=><option key={l}>{l}</option>)}</select></label>
  <Button type="button" disabled={readOnly} onClick={()=>editor.chain().focus().toggleCodeBlock({language}).run()}>Bloco de código</Button>
  <Button type="button" disabled={readOnly} onClick={()=>editor.chain().focus().insertContent({type:'codeBlock',attrs:{language:'mermaid'},content:[]}).run()}>Mermaid</Button>
  <Button type="button" disabled={readOnly} onClick={()=>editor.chain().focus().insertTable({rows:3,cols:3,withHeaderRow:true}).run()}>Tabela</Button>
  {editor.isActive('table')&&<><Button disabled={readOnly} type="button" onClick={()=>editor.chain().focus().addRowAfter().run()}>+ Linha</Button><Button disabled={readOnly} type="button" onClick={()=>editor.chain().focus().addColumnAfter().run()}>+ Coluna</Button><Button disabled={readOnly} type="button" onClick={()=>editor.chain().focus().deleteTable().run()}>Remover tabela</Button></>}
  <Button type="button" aria-label="Desfazer" disabled={readOnly||!editor.can().undo()} onClick={()=>editor.chain().focus().undo().run()}>↶</Button>
  <Button type="button" aria-label="Refazer" disabled={readOnly||!editor.can().redo()} onClick={()=>editor.chain().focus().redo().run()}>↷</Button>
 </div><details className="rich-links"><summary>Links e imagens</summary><div className="inline-form"><label>URL ou link interno<input aria-label="URL do link" value={link} onChange={e=>setLink(e.target.value)} placeholder="https://… ou #section-id"/></label><Button type="button" disabled={readOnly||!safeUrl(link)} onClick={()=>{editor.chain().focus().setLink({href:link}).run();setLink('');}}>Aplicar link à seleção</Button><Button type="button" disabled={readOnly} onClick={()=>editor.chain().focus().unsetLink().run()}>Remover link</Button></div><div className="inline-form"><label>URL da imagem<input aria-label="URL da imagem" value={image} onChange={e=>setImage(e.target.value)} placeholder="URL autorizada de evidência"/></label><Button type="button" disabled={readOnly||!safeUrl(image)||image.startsWith('#')} onClick={()=>{editor.chain().focus().setImage({src:image,alt:'Imagem inserida pelo autor'}).run();setImage('');}}>Inserir imagem</Button></div><p className="muted">Para imagens privadas, prefira vincular uma evidência abaixo. Imagens externas são carregadas pelo navegador.</p></details><EditorContent editor={editor}/></div>;
}
