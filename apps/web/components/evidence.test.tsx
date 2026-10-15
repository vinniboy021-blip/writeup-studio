// SPDX-License-Identifier: MIT
import {beforeEach,describe,expect,it,vi} from 'vitest';
import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {EvidenceWorkspace} from './evidence';
import {setCsrf} from '../lib/api';
const evidence={id:'evidence-1',owner_id:'user-1',name:'console.png',description:'Captura autêntica',origin:'VM local',mime_type:'image/png',extension:'.png',size:240,version:3,metadata:{width:120,height:80},received_at:'2026-10-14T12:00:00Z',captured_at:'2026-10-14T11:30:00Z',sha256:'a'.repeat(64),tags:['web'],visibility:'private',team_id:null};
function response(data:unknown,status=200){return new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});}
const page=(items:unknown[])=>({items,total:items.length,page:1,page_size:24});
let fetchMock:ReturnType<typeof vi.fn>;
beforeEach(()=>{
 setCsrf('csrf-test');sessionStorage.clear();
 vi.stubGlobal('URL',class extends URL{static createObjectURL=vi.fn(()=> 'blob:authenticated-evidence');static revokeObjectURL=vi.fn();});
 fetchMock=vi.fn(async(input:string,options?:RequestInit)=>{
  const url=String(input);
  if(url.endsWith('/thumbnail')||url.endsWith('/download'))return new Response(new Blob(['image'],{type:'image/png'}));
  if(url.includes('/versions'))return response(page([]));
  if(url==='/api/v1/evidences/evidence-1'&&options?.method==='PATCH')return response({...evidence,...JSON.parse(String(options.body)),version:4});
  if(url==='/api/v1/evidences/evidence-1')return response(evidence);
  if(url.startsWith('/api/v1/evidences?'))return response(page([evidence]));
  return response(page([]));
 });vi.stubGlobal('fetch',fetchMock);
});
function mount(initialId?:string){const client=new QueryClient({defaultOptions:{queries:{retry:false}}});return render(<QueryClientProvider client={client}><EvidenceWorkspace initialId={initialId}/></QueryClientProvider>);}
describe('evidências autenticadas',()=>{
 it('carrega miniatura com sessão e revoga o objectURL ao sair da galeria',async()=>{
  const view=mount();const image=await screen.findByRole('img',{name:'Captura autêntica'});expect(image).toHaveAttribute('src','blob:authenticated-evidence');
  const call=fetchMock.mock.calls.find(([path])=>String(path).endsWith('/thumbnail'));expect(call?.[1]).toMatchObject({credentials:'include'});
  view.unmount();expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:authenticated-evidence');
 });
 it('salva metadados com CSRF e a versão esperada sem enviar o arquivo original',async()=>{
  const user=userEvent.setup();mount('evidence-1');await screen.findByRole('heading',{name:'console.png'});await user.click(screen.getByRole('button',{name:'Editar metadados'}));
  const name=screen.getByLabelText('Nome');await user.clear(name);await user.type(name,'captura-validada.png');await user.click(screen.getByRole('button',{name:'Salvar versão 4'}));
  await waitFor(()=>expect(fetchMock.mock.calls.some(([,options])=>options?.method==='PATCH')).toBe(true));
  const [,options]=fetchMock.mock.calls.find(([,options])=>options?.method==='PATCH')!;expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('csrf-test');
  expect(JSON.parse(String(options?.body))).toMatchObject({expected_version:3,name:'captura-validada.png'});expect(JSON.parse(String(options?.body))).not.toHaveProperty('file');
 });
 it('mantém edição local aberta quando o servidor retorna conflito 409',async()=>{
  const originalFetch=fetchMock.getMockImplementation()!;fetchMock.mockImplementation(async(input,options)=>options?.method==='PATCH'?response({detail:{code:'version_conflict',current_version:4}},409):originalFetch(input,options));
  const user=userEvent.setup();mount('evidence-1');await screen.findByRole('heading',{name:'console.png'});await user.click(screen.getByRole('button',{name:'Editar metadados'}));await user.clear(screen.getByLabelText('Nome'));await user.type(screen.getByLabelText('Nome'),'minha-anotacao.png');await user.click(screen.getByRole('button',{name:'Salvar versão 4'}));
  await screen.findByText('Houve alteração concorrente. Seus valores foram preservados.');expect(screen.getByLabelText('Nome')).toHaveValue('minha-anotacao.png');expect(screen.getByRole('button',{name:'Salvar versão 4'})).toBeDisabled();expect(screen.getByRole('button',{name:'Manter meus dados e revisar'})).toBeInTheDocument();
 });
 it('envia origem e captura declarada separadas com upload autenticado',async()=>{
  const user=userEvent.setup();mount();await screen.findByRole('button',{name:'Abrir evidência console.png'});await user.click(screen.getByRole('button',{name:'+ Enviar evidências'}));
  await user.upload(screen.getByLabelText('Arquivos (arraste ou selecione)'),new File(['conteúdo real'],'console.txt',{type:'text/plain'}));await user.type(screen.getByLabelText('Origem da evidência'),'VM do laboratório');
  await user.click(screen.getByRole('button',{name:'Enviar e preservar originais'}));
  await waitFor(()=>expect(fetchMock.mock.calls.some(([,options])=>options?.method==='POST')).toBe(true));const [,options]=fetchMock.mock.calls.find(([,options])=>options?.method==='POST')!;
  expect(options?.body).toBeInstanceOf(FormData);const body=options?.body as FormData;expect(body.get('origin')).toBe('VM do laboratório');expect(body.has('received_at')).toBe(false);expect(body.get('visibility')).toBe('private');expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('csrf-test');
 });
});
