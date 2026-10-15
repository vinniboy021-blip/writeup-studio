import {FlatCompat} from '@eslint/eslintrc';
const compat=new FlatCompat({baseDirectory:import.meta.dirname});
export default [...compat.extends('next/core-web-vitals','next/typescript'),{ignores:['node_modules/**','.next/**','playwright-report/**','test-results/**','next-env.d.ts']},{rules:{'@typescript-eslint/no-explicit-any':'off','@typescript-eslint/no-unused-vars':['warn',{argsIgnorePattern:'^_'}],'react-hooks/exhaustive-deps':'warn','@next/next/no-img-element':'off'}}];
