// SPDX-License-Identifier: MIT
import {describe,expect,it} from 'vitest';
import {commit,emptyAnnotation,hitTest,moveShape,pointerPoint,rectangle,redo,reorderShape,serializeAnnotation,undo,type AnnotationHistory,type Shape} from './annotation-state';
const redact:Shape={id:'redact-1',type:'redact',x:20,y:20,width:30,height:15,color:'#ef4444',strokeWidth:3};
describe('geometria de anotações em pixels originais',()=>{
 it('converte pontos da prévia escalada sem alterar as dimensões do original',()=>{
  expect(pointerPoint({x:170,y:95},{left:10,top:15,width:320,height:160},{width:1280,height:640})).toEqual({x:640,y:320});
  expect(pointerPoint({x:900,y:-4},{left:0,top:0,width:320,height:160},{width:1280,height:640})).toEqual({x:1279,y:0});
 });
 it('normaliza seleção de recorte feita em qualquer direção',()=>{
  expect(rectangle({x:100,y:80},{x:20,y:25})).toEqual({x:20,y:25,width:80,height:55});
 });
 it('mantém redatores e extremos de linhas dentro da imagem ao mover',()=>{
  const result=moveShape(redact,{x:900,y:-100},100,70);expect(result.x).toBe(69);expect(result.y).toBe(0);expect(result.width).toBe(30);
  const arrow:Shape={id:'line',type:'arrow',x:70,y:50,x2:10,y2:10,color:'#ffffff',strokeWidth:3};
  expect(moveShape(arrow,{x:-40,y:0},100,70)).toMatchObject({x:60,x2:0});
 });
 it('seleciona linhas pela distância ao segmento e respeita redação retangular',()=>{
  expect(hitTest(redact,{x:25,y:25})).toBe(true);expect(hitTest(redact,{x:51,y:25})).toBe(false);
  const line:Shape={id:'line',type:'line',x:0,y:0,x2:100,y2:100,color:'#ffffff',strokeWidth:2};expect(hitTest(line,{x:50,y:55})).toBe(true);expect(hitTest(line,{x:80,y:20})).toBe(false);
 });
});
describe('histórico e dados editáveis sem sobrescrever o original',()=>{
 it('desfaz/refaz e invalida o redo após uma edição nova',()=>{
  const original=emptyAnnotation(200,120),initial:AnnotationHistory={past:[],present:original,future:[]};
  const edited=commit(initial,{...original,shapes:[redact]});const reverted=undo(edited);
  expect(reverted.present.shapes).toEqual([]);expect(redo(reverted).present.shapes).toEqual([redact]);
  expect(commit(reverted,{...original,crop:{x:0,y:0,width:50,height:50}}).future).toEqual([]);
  expect(original.shapes).toEqual([]);
 });
 it('mantém redação opaca no schema e não serializa previews/pixels do original',()=>{
  const data={...emptyAnnotation(200,120),shapes:[redact],preview:'data:image/png;base64,private'};
  const serialized=serializeAnnotation(data);expect(serialized.shapes[0]).toEqual(redact);expect(serialized).not.toHaveProperty('preview');expect(JSON.stringify(serialized)).not.toContain('base64');
 });
 it('numera etapas novamente ao reorganizar camadas sem mutar a revisão antiga',()=>{
  const one:Shape={id:'one',type:'step',x:10,y:10,color:'#ff0000',strokeWidth:3,number:1},two:Shape={...one,id:'two',x:20,number:2};
  const data={...emptyAnnotation(200,120),shapes:[one,redact,two]};const moved=reorderShape(data,'two',-1);const again=reorderShape(moved,'two',-1);
  expect(again.shapes.map(s=>s.id)).toEqual(['two','one','redact-1']);expect(again.shapes[0].number).toBe(1);expect(again.shapes[1].number).toBe(2);expect(data.shapes[2].number).toBe(2);
 });
});
