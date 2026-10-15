// @vitest-environment jsdom
// SPDX-License-Identifier: MIT
import {describe,it,expect} from 'vitest';
import {htmlToMarkdown,markdownToHtml} from '../lib/rich-markdown';
describe('conversão rich-text para Markdown canônico',()=>{
 it('preserva linguagem, linhas e cercas dentro do código',()=>{const value='```python\nprint("observado")\n```';expect(htmlToMarkdown(markdownToHtml(value))).toBe(value);const html='<pre><code class="language-bash">texto ``` original\n</code></pre>';expect(htmlToMarkdown(html)).toContain('````bash\ntexto ``` original\n````');});
 it('preserva cabeçalhos, tabela, links e ênfase',()=>{const value='## Resultado\n\n| Item | Valor |\n| --- | --- |\n| **Hash** | [origem](https://example.org) |';const result=htmlToMarkdown(markdownToHtml(value));expect(result).toContain('## Resultado');expect(result).toContain('| Item | Valor |');expect(result).toContain('**Hash**');expect(result).toContain('[origem](https://example.org)');});
 it('mantém diagramas Mermaid como código e HTML arbitrário como texto',()=>{const result=htmlToMarkdown(markdownToHtml('```mermaid\ngraph TD\nA --> B\n```'));expect(result).toContain('```mermaid');expect(result).toContain('A --> B');expect(markdownToHtml('<script>alert(1)</script>')).not.toContain('<script>');expect(markdownToHtml('[x](javascript:alert(1))')).not.toContain('href="javascript:');});
 it('preserva citações, callouts, numeração, imagens e código inline',()=>{const value='> [!NOTE] Dado observado\n\n1. Etapa registrada\n2. Validação\n\n![Evidência](/api/v1/evidences/one/download)\n\n`sha256`';const result=htmlToMarkdown(markdownToHtml(value));expect(result).toContain('>');expect(result).toContain('NOTE');expect(result).toContain('1.');expect(result).toContain('2.');expect(result).toContain('![Evidência](/api/v1/evidences/one/download)');expect(result).toContain('`sha256`');});
});
