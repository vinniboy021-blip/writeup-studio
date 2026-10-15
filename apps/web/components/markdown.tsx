"use client";
import {useEffect,useRef,useState} from 'react';
import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';
import {common,createLowlight} from 'lowlight';
const lowlight=createLowlight(common);
function highlight(code:string,language:string){try{if(language&&lowlight.registered(language)){const tree=lowlight.highlight(language,code);const serialize=(node:any):string=>node.type==='text'?escape(node.value):`<span class="${(node.properties?.className||[]).join(' ')}">${node.children?.map(serialize).join('')||''}</span>`;return tree.children.map(serialize).join('');}}catch{}return escape(code);}
function escape(text:string){return text.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');}
export const markdown=new MarkdownIt({html:false,linkify:true,breaks:true,highlight});
const defaultFence=markdown.renderer.rules.fence!;
markdown.renderer.rules.fence=(tokens,index,options,env,self)=>tokens[index].info.trim()==='mermaid'?`<div class="mermaid-source" data-source="${escape(tokens[index].content)}"></div>`:defaultFence(tokens,index,options,env,self);
export function Markdown({value}:{value:string}){const ref=useRef<HTMLDivElement>(null);const [html,setHtml]=useState('');useEffect(()=>{setHtml(DOMPurify.sanitize(markdown.render(value),{ADD_ATTR:['data-source']}));},[value]);useEffect(()=>{let alive=true;const nodes=ref.current?.querySelectorAll('.mermaid-source');if(!nodes?.length)return;import('mermaid').then(async({default:mermaid})=>{mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'neutral',maxTextSize:50000});for(const node of Array.from(nodes)){try{const result=await mermaid.render('m'+crypto.randomUUID().replaceAll('-',''),node.getAttribute('data-source')||'');if(alive)node.innerHTML=DOMPurify.sanitize(result.svg,{USE_PROFILES:{svg:true,svgFilters:true}});}catch{if(alive)node.textContent='Diagrama Mermaid inválido. Revise o código.';}}});return()=>{alive=false;};},[html]);return <div className="markdown" ref={ref} dangerouslySetInnerHTML={{__html:html}}/>;}
