// SPDX-License-Identifier: MIT
import {describe,it,expect} from 'vitest';
import {asDraft,mergeSections,readRecovery,validateDocument} from '../lib/editor-document';
import type {Document} from '../lib/api';
const local:Document={schema_version:1,sections:[{id:'first',title:'Local',markdown:'observação registrada'},{id:'local-only',title:'Notas',markdown:'dados'}]};
const remote:Document={schema_version:1,sections:[{id:'first',title:'Servidor',markdown:'segunda observação'},{id:'remote-only',title:'Referências',markdown:'https://example.org'}]};
describe('documento canônico e recuperação',()=>{
 it('valida IDs únicos, títulos, formato e limites',()=>{expect(validateDocument(local)).toBe(true);expect(validateDocument({...local,sections:[local.sections[0],local.sections[0]]})).toBe(false);expect(validateDocument({schema_version:2,sections:[]})).toBe(false);expect(validateDocument({schema_version:1,sections:[{id:'<script>',title:'Título',markdown:''}]})).toBe(false);});
 it('recupera somente a cópia pertencente ao documento aberto',()=>{const draft=asDraft({title:'Rascunho',document:local,status:'draft',visibility:'private'});const value=JSON.stringify({schema_version:1,writeup_id:'one',base_version:2,draft,saved_at:new Date().toISOString()});expect(readRecovery(value,'one')?.draft).toEqual(draft);expect(readRecovery(value,'two')).toBeNull();expect(readRecovery('{malformed','one')).toBeNull();});
 it('exige decisões para diferenças e preserva remoções explícitas',()=>{expect(()=>mergeSections(local,remote,{first:'local'})).toThrow('Revise todas');expect(mergeSections(local,remote,{first:'remote','local-only':'remove','remote-only':'remote'})).toEqual({schema_version:1,sections:remote.sections});expect(local.sections).toHaveLength(2);});
 it('separa snapshots do rascunho editável',()=>{const row={title:'Título',document:local,status:'approved',visibility:'private'};const draft=asDraft(row);draft.document.sections[0].markdown='nova alteração';expect(row.document.sections[0].markdown).toBe('observação registrada');expect(draft.status).toBe('draft');});
});
