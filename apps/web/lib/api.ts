export type Row = Record<string, any>;
export type Page<T = Row> = {items:T[];total:number;page:number;page_size:number};
export type Section = {id:string;title:string;markdown:string};
export type Document = {schema_version:1;sections:Section[]};
export type User = {id:string;email:string;name:string;is_admin:boolean};
export class ApiError extends Error {constructor(public status:number, message:string,public detail:any=null){super(message);}}
let csrf = '';
export function setCsrf(value:string){csrf=value;}
export const API = '/api/v1';
export async function api<T = Row>(path:string, options:RequestInit = {}):Promise<T> {
 const headers = new Headers(options.headers); if(options.body && !(options.body instanceof FormData)) headers.set('Content-Type','application/json');
 if(options.method && !['GET','HEAD','OPTIONS'].includes(options.method.toUpperCase())) headers.set('X-CSRF-Token',csrf);
 const response=await fetch(API+path,{...options,headers,credentials:'include'});
 if(!response.ok){const body=await response.json().catch(()=>({detail:response.statusText}));const detail=body.error?.message||body.detail||body.message;throw new ApiError(response.status,typeof detail==='string'?detail:JSON.stringify(detail||'Falha na requisição'),body);}
 if(response.status===204)return undefined as T;return response.json();
}
export const mutate = <T = Row>(path:string,method:string,body?:unknown)=>api<T>(path,{method,body:body===undefined?undefined:JSON.stringify(body)});
export function items(data:any):Row[]{return Array.isArray(data)?data:data?.items||[];}
export function download(path:string){const a=document.createElement('a');a.href=API+path;a.rel='noopener';a.click();}
export function date(value?:string){return value?new Date(value).toLocaleString('pt-BR'):'—';}
export function query(filters:Record<string,unknown>){const params=new URLSearchParams();Object.entries(filters).forEach(([key,value])=>{if(value!==''&&value!==null&&value!==undefined)params.set(key,String(value));});return params.toString();}
