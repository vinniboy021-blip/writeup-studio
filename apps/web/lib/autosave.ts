import {ApiError} from './api';
export type SaveState = 'saved'|'pending'|'saving'|'error'|'conflict';
/** One request at a time; captures drafts and advances CAS only after acknowledgement. */
export class SerialSaver<T> {
 private pending:T|undefined;
 private running:Promise<void>|undefined;
 private stopped=false;
 private disposed=false;
 constructor(public version:number,private save:(draft:T,version:number)=>Promise<{version:number}>,private notify:(state:SaveState,error?:Error)=>void,private acknowledged?:(draft:T,version:number)=>void){}
 enqueue(draft:T){if(this.disposed)return;this.pending=structuredClone(draft);if(!this.stopped)this.notify(this.running?'saving':'pending');}
 hasPending(){return this.pending!==undefined||this.running!==undefined;}
 isRunning(){return this.running!==undefined;}
 /** All callers await the same drain. A newer draft is coalesced, never sent concurrently. */
 flush():Promise<void>{
  if(this.running)return this.running;
  if(this.stopped||this.disposed||this.pending===undefined)return Promise.resolve();
  this.running=this.drain().finally(()=>{this.running=undefined;});
  return this.running;
 }
 private async drain(){
  while(this.pending!==undefined&&!this.stopped&&!this.disposed){
   const draft=this.pending;this.pending=undefined;this.notify('saving');
   try{
    const result=await this.save(draft,this.version);
    this.version=result.version;
    if(!this.disposed){this.acknowledged?.(draft,this.version);this.notify(this.pending===undefined?'saved':'pending');}
   }catch(error){
    // A new draft remains newer than the failing request; never put the old one on top.
    if(this.pending===undefined)this.pending=draft;
    const e=error instanceof Error?error:new Error(String(error));
    if(e instanceof ApiError&&e.status===409){this.stopped=true;if(!this.disposed)this.notify('conflict',e);}
    else if(!this.disposed)this.notify('error',e);
    break;
   }
  }
 }
 resume(version:number){if(this.running)throw new Error('Aguarde a requisição em andamento.');this.version=version;this.stopped=false;}
 discard(){if(this.running)throw new Error('Aguarde a requisição em andamento.');this.pending=undefined;this.stopped=false;}
 /** In-flight acknowledgement may finish, but no pending save is started after unmount. */
 dispose(){this.disposed=true;}
}
