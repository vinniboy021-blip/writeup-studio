// SPDX-License-Identifier: MIT
import type {Document, Row, Section} from './api';

export type WriteupDraft = {title:string;document:Document;status:'draft'|'in_progress'|'completed';visibility:'private'|'team';tags:string[];tools:string[];languages:string[]};
export type RecoveredDraft = {schema_version:1;writeup_id:string;base_version:number;draft:WriteupDraft;saved_at:string};
export const draftKey = (id:string) => 'ctf-studio:draft:'+id;
export const signature = (value:unknown) => JSON.stringify(value);
export function asDraft(row:Row):WriteupDraft {
 return {title:row.title,document:structuredClone(row.document),status:['draft','in_progress','completed'].includes(row.status)?row.status:'draft',visibility:row.visibility==='team'?'team':'private',tags:row.tags||[],tools:row.tools||[],languages:row.languages||[]};
}
export function validateDocument(value:unknown):value is Document {
 if(!value||typeof value!=='object')return false;
 const row=value as Document;
 if(row.schema_version!==1||!Array.isArray(row.sections)||row.sections.length>200)return false;
 const ids=new Set<string>();
 return row.sections.every(s=>s&&typeof s.id==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(s.id)&&!ids.has(s.id)&&Boolean(ids.add(s.id))&&typeof s.title==='string'&&s.title.length>0&&s.title.length<=240&&typeof s.markdown==='string'&&s.markdown.length<=1000000)&&new TextEncoder().encode(JSON.stringify(row)).length<=2097152;
}
export function readRecovery(raw:string|null,id:string):RecoveredDraft|null {
 if(!raw)return null;
 try {const row=JSON.parse(raw) as RecoveredDraft;const d=row.draft;
  return row.schema_version===1&&row.writeup_id===id&&Number.isSafeInteger(row.base_version)&&row.base_version>=1&&typeof row.saved_at==='string'&&d&&typeof d.title==='string'&&d.title.length>0&&d.title.length<=240&&['draft','in_progress','completed'].includes(d.status)&&['private','team'].includes(d.visibility)&&[d.tags,d.tools,d.languages].every(a=>Array.isArray(a)&&a.every(v=>typeof v==='string'))&&validateDocument(d.document)?row:null;
 } catch{return null;}
}
/** Explicit section choices preserve only reviewed content, including deliberate deletions. */
export function mergeSections(local:Document,remote:Document,choices:Record<string,'local'|'remote'|'remove'>):Document {
 const ids=Array.from(new Set([...local.sections.map(s=>s.id),...remote.sections.map(s=>s.id)]));
 const sections:Section[]=[];
 for(const id of ids){const choice=choices[id];if(!choice)throw new Error('Revise todas as seções antes de mesclar.');if(choice==='remove')continue;const section=(choice==='local'?local:remote).sections.find(s=>s.id===id);if(section)sections.push(structuredClone(section));}
 const doc:Document={schema_version:1,sections};if(!validateDocument(doc))throw new Error('Documento combinado inválido.');return doc;
}
