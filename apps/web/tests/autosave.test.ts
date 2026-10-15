// SPDX-License-Identifier: MIT
import {describe,it,expect,vi} from 'vitest';
import {ApiError} from '../lib/api';
import {SerialSaver} from '../lib/autosave';

function deferred<T>(){let resolve!:(value:T)=>void;let reject!:(error:Error)=>void;const promise=new Promise<T>((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
describe('autosave serial com concorrência otimista',()=>{
 it('envia apenas uma requisição por vez e usa a versão confirmada para o próximo rascunho',async()=>{
  const first=deferred<{version:number}>(),second=deferred<{version:number}>();
  const save=vi.fn().mockImplementationOnce(()=>first.promise).mockImplementationOnce(()=>second.promise),ack=vi.fn();
  const saver=new SerialSaver(4,save,vi.fn(),ack);
  saver.enqueue({text:'primeiro'});const flush=saver.flush();
  saver.enqueue({text:'intermediário'});saver.enqueue({text:'último'});
  expect(saver.flush()).toBe(flush);expect(save).toHaveBeenCalledTimes(1);
  first.resolve({version:5});await Promise.resolve();await Promise.resolve();
  expect(save).toHaveBeenNthCalledWith(2,{text:'último'},5);
  second.resolve({version:6});await flush;
  expect(saver.version).toBe(6);expect(saver.hasPending()).toBe(false);expect(ack).toHaveBeenLastCalledWith({text:'último'},6);
 });
 it('preserva o rascunho mais recente se a requisição anterior falhar',async()=>{
  const failing=deferred<{version:number}>(),save=vi.fn().mockImplementationOnce(()=>failing.promise).mockResolvedValue({version:8});
  const notify=vi.fn(),saver=new SerialSaver(7,save,notify);
  saver.enqueue({text:'antigo'});const flush=saver.flush();saver.enqueue({text:'novo'});
  failing.reject(new Error('rede indisponível'));await flush;
  expect(saver.hasPending()).toBe(true);expect(notify).toHaveBeenLastCalledWith('error',expect.any(Error));
  await saver.flush();expect(save).toHaveBeenLastCalledWith({text:'novo'},7);expect(saver.version).toBe(8);
 });
 it('pausa em HTTP 409 e só retenta depois de uma decisão explícita com nova versão',async()=>{
  const save=vi.fn().mockRejectedValueOnce(new ApiError(409,'Outra versão')).mockResolvedValue({version:12});
  const notify=vi.fn(),saver=new SerialSaver(9,save,notify);
  saver.enqueue({text:'local'});await saver.flush();saver.enqueue({text:'local revisado'});await saver.flush();
  expect(save).toHaveBeenCalledTimes(1);expect(notify).toHaveBeenCalledWith('conflict',expect.any(ApiError));
  saver.resume(11);await saver.flush();expect(save).toHaveBeenLastCalledWith({text:'local revisado'},11);
 });
 it('retém o mesmo rascunho em falha sem edição nova e nunca avança a versão antes do ACK',async()=>{
  const request=deferred<{version:number}>(),save=vi.fn().mockImplementationOnce(()=>request.promise).mockResolvedValue({version:2});
  const saver=new SerialSaver(1,save,vi.fn());saver.enqueue({text:'persistir'});const flush=saver.flush();expect(saver.version).toBe(1);
  request.reject(new Error('timeout'));await flush;expect(saver.version).toBe(1);await saver.flush();expect(save).toHaveBeenLastCalledWith({text:'persistir'},1);
 });
 it('clona a entrada e bloqueia troca de versão enquanto existe requisição em andamento',async()=>{
  const request=deferred<{version:number}>(),save=vi.fn(()=>request.promise),saver=new SerialSaver(1,save,vi.fn());
  const draft={text:'original'};saver.enqueue(draft);draft.text='mutado externamente';const flush=saver.flush();
  expect(save).toHaveBeenCalledWith({text:'original'},1);expect(()=>saver.resume(99)).toThrow();expect(()=>saver.discard()).toThrow();
  request.resolve({version:2});await flush;
 });
 it('não inicia o rascunho pendente após desmontar o editor',async()=>{
  const request=deferred<{version:number}>(),save=vi.fn(()=>request.promise),ack=vi.fn(),saver=new SerialSaver(1,save,vi.fn(),ack);
  saver.enqueue('primeiro');const flush=saver.flush();saver.enqueue('segundo');saver.dispose();request.resolve({version:2});await flush;
  expect(save).toHaveBeenCalledTimes(1);expect(ack).not.toHaveBeenCalled();expect(saver.hasPending()).toBe(true);
 });
});
