"use client";
import {useState} from 'react';
import {useForm} from 'react-hook-form';
import {zodResolver} from '@hookform/resolvers/zod';
import {z} from 'zod';
import {mutate,setCsrf,type User} from '../lib/api';
import {Button,Field,ErrorBox} from './ui';
const schema=z.object({email:z.email('Informe um email válido'),password:z.string().min(12,'Use pelo menos 12 caracteres').max(128),name:z.string().max(120)});
export function Auth({onSession}:{onSession:(user:User)=>void}){const [register,setRegister]=useState(false);const [error,setError]=useState<unknown>();const {register:field,handleSubmit,formState:{errors,isSubmitting}}=useForm<z.infer<typeof schema>>({resolver:zodResolver(schema),defaultValues:{email:'',password:'',name:''}});
 const submit=handleSubmit(async values=>{setError(undefined);try{const data=await mutate('/auth/'+(register?'register':'login'),'POST',register?values:{email:values.email,password:values.password});setCsrf(data.csrf_token);onSession(data.user);}catch(e){setError(e);}});
 return <div className="auth-layout"><div className="auth-brand"><p className="eyebrow">CTF WRITEUP STUDIO</p><h1>Evidências reais.<br/>Conhecimento compartilhado.</h1><p>Organize desafios, documente cada etapa e publique com revisão e proveniência.</p><div className="auth-tags"><span>MIT · Open source</span><span>Self hosted</span><span>IA opcional</span></div></div><form className="panel auth-form" onSubmit={submit}><h2>{register?'Criar sua conta':'Entrar no workspace'}</h2><p className="muted">Seus documentos permanecem privados por padrão.</p>{register&&<Field label="Nome"><input autoComplete="name" required {...field('name')}/></Field>}<Field label="Email"><input type="email" autoComplete="email" {...field('email')}/></Field>{errors.email&&<p role="alert">{errors.email.message}</p>}<Field label="Senha"><input type="password" autoComplete={register?'new-password':'current-password'} {...field('password')}/></Field>{errors.password&&<p role="alert">{errors.password.message}</p>}<ErrorBox error={error}/><Button variant="primary" disabled={isSubmitting}>{isSubmitting?'Aguarde…':register?'Criar conta':'Entrar'}</Button><Button type="button" onClick={()=>setRegister(!register)}>{register?'Já tenho uma conta':'Criar uma conta'}</Button></form></div>;
}
