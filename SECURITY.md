# Política de Segurança

## Relatar uma vulnerabilidade

Use **Security → Report a vulnerability** no GitHub para relatos privados. Para instalações privadas, encaminhe ao administrador da implantação.

**Inclua no relato:**
- Versão e configuração relevante (sem segredos)
- Comportamento esperado vs. observado
- Reprodução mínima com dados sintéticos identificados como teste

**Não inclua:** credenciais, tokens, documentos privados ou evidências reais.

O mantenedor confirma recebimento, avalia impacto e combina correção e divulgação com o relator. Prazos dependem da manutenção ativa do projeto.

## Escopo

Vulnerabilidades relevantes para este projeto:

- Bypass de autenticação ou autorização (RBAC, escopo de equipe)
- Exposição de evidências privadas ou writeups de outras equipes
- XSS persistente ou refletido no editor / preview
- SSRF via Ollama URL, S3 endpoint ou Kali MCP URL
- Execução de código indevida via upload de evidências
- Perda de versões ou violação de integridade de hash SHA-256
- Escalada de privilégio entre papéis ou equipes

## Fora de escopo

- Testes de segurança contra instalações de terceiros sem autorização explícita
- Ataques que exigem acesso físico ou comprometimento prévio do host
- Rate limiting em ambientes de desenvolvimento (sem Redis)

## Referências

Controles implementados: [docs/SECURITY.md](docs/SECURITY.md)
